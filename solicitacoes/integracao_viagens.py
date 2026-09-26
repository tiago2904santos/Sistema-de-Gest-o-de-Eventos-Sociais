"""A ponte entre o despacho da DG e o módulo de Viagens.

Quando a DG defere uma solicitação, o evento deixa de ser um pedido e passa a
ser trabalho a executar — e esse trabalho, quando há deslocamento, vive em
Viagens. Até aqui alguém relia a solicitação e redigitava tudo do outro lado:
município, datas, local, quantidade de servidores. Redigitar é onde o erro
entra, e o erro aqui vira documento oficial.

**A viagem nasce em rascunho, e só o que a solicitação sabe.** Ela não sabe
quem vai nominalmente (tem quantidade por equipe, não nomes), nem viatura, nem
motorista — e esses três é que decidem a diária. Inventar aqui seria pior que
deixar em branco: um número de diária errado atravessa a prestação de contas
inteira sem ninguém notar.

**A geração não derruba o despacho.** Se criar a viagem falhar, a decisão da
DG continua registrada: ela é o ato administrativo, e a viagem é consequência
dele. O contrário — despacho perdido porque o módulo vizinho estava com
problema — seria inaceitável.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

# Quantos servidores a solicitação previu, somando as equipes. Usado só para
# dimensionar o roteiro; a lista nominal é preenchida em Viagens.
def quantidade_prevista(solicitacao) -> int:
    direto = getattr(solicitacao, "quantidade_servidores", None)
    if direto:
        return int(direto)
    return sum(
        item.quantidade_servidores or 0
        for item in solicitacao.itens_equipe.all()
    )


def resumo_das_equipes(solicitacao) -> str:
    """"ASCOM: 2; Cerimonial (sem quantidade)" — o que a DG autorizou.

    Vai para as observações do roteiro porque é a informação que se perde no
    caminho: em Viagens só sobra o total, e quem monta a equipe precisa saber
    de que setores ela deveria vir.

    A equipe **sem quantidade aparece mesmo assim**. Nos dados reais quase
    toda solicitação tem equipe e quase nenhuma tem o número (98 de 101 contra
    6 de 101): filtrar pelo número esconderia justamente o caso comum, e quem
    fosse montar a viagem não saberia nem de que setor chamar.
    """
    partes = []
    for item in solicitacao.itens_equipe.select_related("equipe"):
        if item.quantidade_servidores:
            partes.append(f"{item.equipe}: {item.quantidade_servidores}")
        else:
            partes.append(f"{item.equipe} (sem quantidade)")
    return "; ".join(partes)


def viagem_da_solicitacao(solicitacao):
    """A viagem já gerada a partir desta solicitação, se houver."""
    from viagens_viagem.models import Viagem

    return Viagem.objects.filter(
        roteiros__solicitacao=solicitacao, cancelado=False
    ).order_by("id").first()


def pode_gerar(solicitacao) -> tuple[bool, str]:
    """Se cabe gerar viagem para esta solicitação, e por que não quando não cabe."""
    from solicitacoes.models import DecisaoDG, StatusSolicitacao

    if solicitacao.decisao_dg != DecisaoDG.ATENDER:
        return False, "A DG ainda não autorizou o atendimento desta solicitação."
    if solicitacao.status != StatusSolicitacao.DEFERIDA_EM_ANDAMENTO:
        return False, f"A solicitação está {solicitacao.get_status_display().lower()}."
    if not solicitacao.municipio_id:
        return False, "A solicitação não tem município definido."
    if not solicitacao.data_inicio_evento:
        return False, "A solicitação não tem data de início do evento."
    if viagem_da_solicitacao(solicitacao) is not None:
        return False, "Esta solicitação já tem viagem gerada."
    return True, ""


def o_que_falta(viagem) -> list[str]:
    """O que a solicitação não tinha e alguém precisa completar em Viagens.

    Devolvido em texto, para a tela listar. É a diferença entre uma viagem que
    parece pronta e uma que está pronta.
    """
    faltando = []
    roteiro = viagem.roteiros.order_by("id").first()

    if roteiro is None:
        faltando.append("Roteiro da viagem")
    else:
        if not roteiro.origem_municipio_id:
            faltando.append("Município de onde a equipe sai")
        if not roteiro.saida_dt:
            faltando.append("Data e hora da saída")

    oficios = list(viagem.oficios.filter(cancelado=False))
    if not oficios:
        faltando.append("Ofício de viagem (com a equipe nominal)")
    else:
        for oficio in oficios:
            if not oficio.servidores.exists():
                faltando.append(f"Servidores do ofício #{oficio.pk}")
            if not oficio.viatura_id and not oficio.transporte_placa_manual:
                faltando.append(f"Viatura do ofício #{oficio.pk}")
            if not oficio.motorista_id and not oficio.motorista_manual_nome:
                faltando.append(f"Motorista do ofício #{oficio.pk}")

    return faltando


def gerar_viagem(solicitacao, usuario):
    """Cria a viagem em rascunho a partir da solicitação deferida.

    Devolve a viagem criada. Levanta ``ValueError`` com o motivo quando não
    cabe gerar — quem chama decide se isso é erro ou só informação.
    """
    from django.db import transaction

    from viagens_roteiros.models import RoteiroDestino
    from viagens_viagem.models import Viagem

    cabe, motivo = pode_gerar(solicitacao)
    if not cabe:
        raise ValueError(motivo)

    municipio = solicitacao.municipio
    inicio = solicitacao.data_inicio_evento
    fim = solicitacao.data_fim_evento or inicio
    previstos = quantidade_prevista(solicitacao)

    # O motivo carrega a origem: seis meses depois, ninguém lembra de onde
    # veio uma viagem, e o número da solicitação é o fio que liga os dois.
    motivo = _motivo_da_solicitacao(solicitacao)

    with transaction.atomic():
        viagem = Viagem.objects.create(
            titulo=f"{municipio} — {inicio:%d/%m/%Y}",
            destino_municipio=municipio,
            destino_estado=municipio.estado,
            data_inicio=inicio,
            data_fim=fim,
            motivo=motivo,
            descricao=(solicitacao.descricao_complementar or "").strip(),
            status=Viagem.STATUS_EM_PREPARACAO,
        )

        from viagens_roteiros.models import Roteiro

        roteiro = Roteiro.objects.create(
            viagem=viagem,
            # A ligação que faltava: daqui para frente a solicitação e a
            # viagem se encontram pelo banco, não pela memória de alguém.
            solicitacao=solicitacao,
            tipo=Roteiro.Tipo.EVENTO,
            quantidade_servidores=max(previstos, 1),
            observacoes=_observacoes_do_roteiro(solicitacao),
        )
        RoteiroDestino.objects.create(roteiro=roteiro, municipio=municipio, ordem=1)

    logger.info(
        "Viagem %s gerada a partir da solicitação %s por %s",
        viagem.pk, solicitacao.pk, getattr(usuario, "username", "?"),
    )
    return viagem


# ---------------------------------------------------------------------------
# Depois de gerada: a viagem acompanha a solicitação
# ---------------------------------------------------------------------------

# Documentos oficiais da viagem. O roteiro fica de fora: é o planejamento que
# nasceu com ela, não um documento emitido.
DOCUMENTOS_EMITIDOS = ("oficios", "ordens_servico", "planos_trabalho", "termos_autorizacao")


def documentos_emitidos(viagem) -> bool:
    """A viagem já tem ofício, OS, plano ou termo ativo — ou passou dessa fase.

    Com documento emitido, a viagem não é mais só rascunho: mexer nela ou
    cancelá-la sozinho desfaria papel oficial. Aí quem decide é o operador
    de Viagens, que recebe o aviso.
    """
    from viagens_viagem.models import Viagem

    if viagem.status in {
        Viagem.STATUS_DOCUMENTOS_GERADOS,
        Viagem.STATUS_EM_EXECUCAO,
        Viagem.STATUS_FINALIZADO,
    }:
        return True
    return any(
        getattr(viagem, relacao).filter(cancelado=False).exists()
        for relacao in DOCUMENTOS_EMITIDOS
    )


def _avisar_operadores(viagem, titulo, mensagem, usuario):
    """Sino para gestores e operadores de Viagens, com o link do painel."""
    from django.urls import reverse

    from core.notificacoes import notificar, usuarios_do_grupo
    from viagens_cadastros.permissions import GRUPO_GESTOR, GRUPO_OPERADOR

    destinatarios = list(usuarios_do_grupo(GRUPO_GESTOR)) + list(
        usuarios_do_grupo(GRUPO_OPERADOR)
    )
    notificar(
        destinatarios,
        titulo,
        mensagem,
        link=reverse("viagens_viagem:painel", args=[viagem.pk]),
        exceto=usuario,
    )


def encerrar_viagem(solicitacao, usuario, motivo="") -> str:
    """A solicitação não vai mais acontecer (não atendida ou cancelada).

    Sem documento emitido, a viagem é cancelada junto — e com ela o roteiro.
    Com documento, ela fica como está e o operador de Viagens é avisado.
    Devolve "cancelada", "avisada" ou "" (não havia viagem).
    """
    viagem = viagem_da_solicitacao(solicitacao)
    if viagem is None:
        return ""
    situacao = solicitacao.get_status_display().lower()
    texto = f"Solicitação #{solicitacao.pk} {situacao}"
    if motivo:
        texto = f"{texto}: {motivo}"
    if not documentos_emitidos(viagem):
        viagem.cancelar(texto)
        return "cancelada"
    _avisar_operadores(
        viagem,
        f"Viagem #{viagem.pk}: solicitação {situacao}",
        f"{texto}. A viagem já tem documentos emitidos e não foi cancelada; "
        "confira e cancele pelo painel se for o caso.",
        usuario,
    )
    return "avisada"


def sincronizar_viagem(solicitacao, usuario) -> str:
    """Novo deferimento de uma solicitação que já tinha viagem.

    O pedido pode ter mudado de local, datas ou município entre um despacho e
    outro. Sem documento emitido, a viagem e o roteiro são atualizados com o
    que a DG acabou de deferir; com documento, o operador de Viagens é avisado
    para conferir. Devolve "atualizada", "avisada" ou "" (não havia viagem).
    """
    from django.db import transaction

    viagem = viagem_da_solicitacao(solicitacao)
    if viagem is None:
        return ""
    if documentos_emitidos(viagem):
        _avisar_operadores(
            viagem,
            f"Viagem #{viagem.pk}: solicitação #{solicitacao.pk} alterada",
            "A solicitação foi alterada e deferida de novo pela DG, mas a viagem "
            "já tem documentos emitidos. Confira datas, local e equipe.",
            usuario,
        )
        return "avisada"

    municipio = solicitacao.municipio
    inicio = solicitacao.data_inicio_evento
    with transaction.atomic():
        viagem.titulo = f"{municipio} — {inicio:%d/%m/%Y}"
        viagem.destino_municipio = municipio
        viagem.destino_estado = municipio.estado
        viagem.data_inicio = inicio
        viagem.data_fim = solicitacao.data_fim_evento or inicio
        viagem.motivo = _motivo_da_solicitacao(solicitacao)
        viagem.descricao = (solicitacao.descricao_complementar or "").strip()
        viagem.save()

        for roteiro in viagem.roteiros.filter(solicitacao=solicitacao, cancelado=False):
            roteiro.tipo = roteiro.Tipo.EVENTO
            roteiro.quantidade_servidores = max(quantidade_prevista(solicitacao), 1)
            roteiro.observacoes = _observacoes_do_roteiro(solicitacao)
            campos = ["tipo", "quantidade_servidores", "observacoes", "atualizado_em"]
            destino = roteiro.destinos.order_by("ordem", "pk").first()
            if destino is not None and destino.municipio_id != municipio.pk:
                destino.municipio = municipio
                destino.save(update_fields=["municipio", "atualizado_em"])
                # O percurso mudou: a rota calculada deixa de valer.
                if roteiro.rota_status == roteiro.RotaStatus.CALCULADA:
                    roteiro.rota_status = roteiro.RotaStatus.DESATUALIZADA
                    campos.append("rota_status")
            roteiro.save(update_fields=campos)
    return "atualizada"


def aviso_para_o_painel(viagem):
    """O que o painel da viagem precisa dizer sobre a solicitação de origem.

    Devolve {solicitacao, url, aviso, alteracoes} ou None quando a viagem não
    veio de solicitação. `aviso` fica vazio quando as duas estão em dia.
    """
    from django.urls import reverse

    from solicitacoes.models import AcaoHistorico, StatusSolicitacao

    roteiro = (
        viagem.roteiros.filter(solicitacao__isnull=False)
        .select_related("solicitacao")
        .order_by("id")
        .first()
    )
    if roteiro is None:
        return None
    solicitacao = roteiro.solicitacao
    reenvios = list(
        solicitacao.historico.filter(
            acao=AcaoHistorico.REENVIO, criado_em__gt=viagem.criado_em
        ).order_by("criado_em", "pk")
    )
    aviso = ""
    alteracoes = []
    if not viagem.cancelado and solicitacao.status in {
        StatusSolicitacao.NAO_ATENDIDA,
        StatusSolicitacao.CANCELADA,
    }:
        aviso = (
            f"A solicitação está {solicitacao.get_status_display().lower()}, mas a "
            "viagem tem documentos emitidos e não foi cancelada automaticamente."
        )
    elif reenvios and solicitacao.status == StatusSolicitacao.AGUARDANDO_DESPACHO:
        aviso = (
            "Viagem desatualizada: a solicitação foi alterada e aguarda novo "
            "despacho da DG."
        )
    elif reenvios and documentos_emitidos(viagem):
        aviso = (
            "A solicitação foi alterada depois que a viagem teve documentos "
            "emitidos. Confira o que mudou."
        )
    if aviso:
        for registro in reenvios:
            alteracoes.extend(registro.alteracoes or [])
    return {
        "solicitacao": solicitacao,
        "url": reverse("solicitacoes:editar", args=[solicitacao.pk]),
        "aviso": aviso,
        "alteracoes": alteracoes,
    }


def _motivo_da_solicitacao(solicitacao) -> str:
    partes = []
    if solicitacao.tipo_evento_id:
        partes.append(str(solicitacao.tipo_evento))
    if solicitacao.local_evento:
        partes.append(solicitacao.local_evento)
    texto = " — ".join(partes) or "Atendimento de solicitação de evento"
    return f"{texto} (Solicitação #{solicitacao.pk})"


def _observacoes_do_roteiro(solicitacao) -> str:
    """O que a solicitação sabia e o roteiro não tem campo para guardar."""
    linhas = [f"Gerado a partir da Solicitação de Evento #{solicitacao.pk}."]
    equipes = resumo_das_equipes(solicitacao)
    if equipes:
        linhas.append(f"Equipes autorizadas pela DG — {equipes}.")
    if solicitacao.solicitante_nome:
        linhas.append(f"Solicitante: {solicitacao.solicitante_nome}.")
    if solicitacao.local_evento:
        linhas.append(f"Local: {solicitacao.local_evento}.")
    if solicitacao.quantidade_cin:
        linhas.append(f"CIN previstas: {solicitacao.quantidade_cin}.")
    if solicitacao.observacoes_dg:
        linhas.append(f"Observação da DG: {solicitacao.observacoes_dg}")
    return "\n".join(linhas)
