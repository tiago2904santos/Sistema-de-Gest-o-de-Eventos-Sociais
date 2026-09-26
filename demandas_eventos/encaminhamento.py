"""Encaminhar à DG: a palestra ou evento da ASCOM vira solicitação de evento.

O mesmo evento costumava ser digitado duas vezes — aqui, com público e
contato; em Solicitações de evento, com equipes e CIN, para o despacho da
DG. O "Encaminhar à DG" cria o rascunho da solicitação com o que a palestra
já tem e liga as duas (`DemandaEvento.solicitacao_dg`); quem encaminhou
completa na solicitação o que só ela pede (órgão, serviços, equipes) e envia.
O que a DG decide volta para o histórico da palestra.

O app de solicitações não muda: a criação usa o modelo e o histórico dele, e
o retorno da DG chega pelo `post_save` do histórico da solicitação.
"""

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from .models import AcaoHistoricoDemanda, DemandaEvento, TipoEventoPalestra
from .services import registrar_historico

# O nome do tipo de evento da solicitação que corresponde a cada "Evento" da
# planilha. O relatório consolidado reconhece o PCPR pela palavra COMUNIDADE.
PALAVRA_DO_TIPO = {
    TipoEventoPalestra.PCPR_NA_COMUNIDADE: "COMUNIDADE",
    TipoEventoPalestra.PALESTRA: "PALESTRA",
}


def _tipo_evento(demanda):
    from cadastros.models import TipoEvento

    palavra = PALAVRA_DO_TIPO.get(demanda.evento)
    if not palavra:
        return None
    return TipoEvento.objects.filter(ativo=True, nome__icontains=palavra).order_by("nome").first()


def _descricao(demanda):
    partes = [demanda.descricao.strip()] if demanda.descricao.strip() else []
    for rotulo, valor in (
        ("Tema", demanda.temas_display),
        ("Palestrante", demanda.servidores_display),
        ("Horário", demanda.horario_display or demanda.periodo_evento_texto),
        ("Público previsto", f"{demanda.quantidade_publico} pessoas" if demanda.quantidade_publico else ""),
    ):
        if valor:
            partes.append(f"{rotulo}: {valor}")
    partes.append(f"Encaminhada da {demanda.get_evento_display().lower()} #{demanda.pk} da ASCOM.")
    return "\n".join(partes)


@transaction.atomic
def encaminhar_a_dg(demanda, usuario):
    """Cria o rascunho da solicitação de evento a partir da palestra e liga os dois."""
    from solicitacoes.models import AcaoHistorico, SolicitacaoEvento, StatusSolicitacao
    from solicitacoes.services import registrar_historico as registrar_historico_solicitacao

    if demanda.solicitacao_dg_id:
        raise ValidationError(f"Já encaminhada à DG: solicitação #{demanda.solicitacao_dg_id}.")
    inicio = demanda.data_inicio_evento
    solicitacao = SolicitacaoEvento(
        status=StatusSolicitacao.RASCUNHO,
        data_solicitacao=timezone.localdate(),
        data_inicio_evento=inicio,
        # A solicitação pede o fim do evento para ir à DG: evento de um dia.
        data_fim_evento=demanda.data_fim_evento or inicio,
        municipio=demanda.municipio,
        tipo_evento=_tipo_evento(demanda),
        solicitante_nome=demanda.solicitante[:150],
        contato=demanda.contato_display[:100],
        descricao_complementar=_descricao(demanda),
        criado_por=usuario,
    )
    solicitacao.full_clean(exclude=["criado_por"])
    solicitacao.save()
    registrar_historico_solicitacao(
        solicitacao,
        usuario,
        AcaoHistorico.CRIACAO,
        status_novo=solicitacao.status,
        observacao=f"Criada a partir da {demanda.get_evento_display().lower()} #{demanda.pk} da ASCOM.",
    )
    demanda.solicitacao_dg = solicitacao
    demanda.atualizado_em = timezone.now()
    demanda.save(update_fields=["solicitacao_dg", "atualizado_em"])
    registrar_historico(
        demanda,
        usuario,
        AcaoHistoricoDemanda.ENCAMINHAMENTO_DG,
        f"Solicitação de evento #{solicitacao.pk} criada em rascunho para o despacho da DG.",
        status_novo=demanda.status,
    )
    return solicitacao


def acompanhar_solicitacao(sender, instance, created, **kwargs):
    """Leva ao histórico da palestra o envio e a decisão da DG na solicitação ligada."""
    from solicitacoes.models import AcaoHistorico

    acoes = {
        AcaoHistorico.ENVIO,
        AcaoHistorico.DEVOLUCAO,
        AcaoHistorico.DECISAO,
        AcaoHistorico.CONCLUSAO,
        AcaoHistorico.CANCELAMENTO,
    }
    if not created or instance.acao not in acoes:
        return
    demanda = DemandaEvento.objects.filter(solicitacao_dg_id=instance.solicitacao_id).first()
    if demanda is None:
        return
    solicitacao = instance.solicitacao
    texto = f"Solicitação #{solicitacao.pk} — {instance.get_acao_display()}: {solicitacao.get_status_display()}."
    if instance.observacao:
        texto += f"\n{instance.observacao}"
    registrar_historico(
        demanda,
        instance.usuario,
        AcaoHistoricoDemanda.ANDAMENTO_DG,
        texto,
        status_novo=demanda.status,
    )
