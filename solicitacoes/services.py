"""Camada de serviço do workflow de solicitações.

Fluxo enxuto: o solicitante cria/revisa e envia direto para a DG; a DG
despacha. Todas as mudanças de status passam por aqui: as views nunca alteram
o campo `status` diretamente, e transições inválidas levantam
`TransicaoInvalida`.
"""

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.urls import reverse
from django.utils import timezone

from core.notificacoes import notificar, usuarios_do_grupo

from .models import (
    AcaoHistorico,
    DecisaoDG,
    HistoricoSolicitacao,
    SolicitacaoEvento,
    StatusSolicitacao,
)


class TransicaoInvalida(ValidationError):
    """Transição de status não permitida pelo workflow."""


TRANSICOES_VALIDAS = {
    StatusSolicitacao.RASCUNHO: {StatusSolicitacao.AGUARDANDO_DESPACHO},
    StatusSolicitacao.AGUARDANDO_DESPACHO: {
        StatusSolicitacao.DEFERIDA_EM_ANDAMENTO,
        StatusSolicitacao.NAO_ATENDIDA,
        StatusSolicitacao.CANCELADA,
        StatusSolicitacao.DEVOLVIDA,
    },
    StatusSolicitacao.DEVOLVIDA: {
        StatusSolicitacao.AGUARDANDO_DESPACHO,
        StatusSolicitacao.CANCELADA,
    },
    # Deferida: o evento acontece e o solicitante confirma o atendimento —
    # ou o evento é cancelado no caminho.
    StatusSolicitacao.DEFERIDA_EM_ANDAMENTO: {
        StatusSolicitacao.ATENDIDA,
        StatusSolicitacao.CANCELADA,
    },
}

STATUS_EDITAVEIS = {StatusSolicitacao.RASCUNHO, StatusSolicitacao.DEVOLVIDA}

STATUS_POR_DECISAO = {
    DecisaoDG.ATENDER: StatusSolicitacao.DEFERIDA_EM_ANDAMENTO,
    DecisaoDG.NAO_ATENDER: StatusSolicitacao.NAO_ATENDIDA,
    DecisaoDG.CANCELADO: StatusSolicitacao.CANCELADA,
}

DECISOES_COM_OBSERVACAO_OBRIGATORIA = {DecisaoDG.NAO_ATENDER, DecisaoDG.CANCELADO}

CAMPOS_OBRIGATORIOS_ENVIO = {
    "data_solicitacao": "Data da solicitação",
    "data_inicio_evento": "Início do evento",
    "data_fim_evento": "Fim do evento",
    "tipo_evento": "Tipo do evento",
    "municipio": "Município",
    "solicitante_nome": "Solicitante",
    "solicitante_cargo_unidade": "Cargo / unidade",
    "orgao_responsavel": "Órgão responsável",
}


def registrar_historico(
    solicitacao,
    usuario,
    acao,
    status_anterior="",
    status_novo="",
    observacao="",
):
    return HistoricoSolicitacao.objects.create(
        solicitacao=solicitacao,
        usuario=usuario,
        acao=acao,
        status_anterior=status_anterior,
        status_novo=status_novo,
        observacao=observacao,
    )


def _transicionar(solicitacao, novo_status):
    permitidos = TRANSICOES_VALIDAS.get(solicitacao.status, set())
    if novo_status not in permitidos:
        raise TransicaoInvalida(
            f"Transição de {solicitacao.get_status_display()} para "
            f"{StatusSolicitacao(novo_status).label} não é permitida."
        )
    anterior = solicitacao.status
    solicitacao.status = novo_status
    return anterior


def pendencias_para_envio(solicitacao):
    """Pendências para enviar à DG: dados, serviços e planejamento mínimo."""
    faltas = [
        rotulo
        for campo, rotulo in CAMPOS_OBRIGATORIOS_ENVIO.items()
        if not getattr(solicitacao, campo)
    ]
    if solicitacao.pk:
        if not solicitacao.itens_servico.exists():
            faltas.append("Ao menos um serviço solicitado")
        if not solicitacao.itens_equipe.exists():
            faltas.append("Ao menos uma equipe designada")
        elif solicitacao.itens_equipe.exclude(quantidade_servidores__gt=0).exists():
            faltas.append("Quantidade de servidores de cada equipe")
    if not solicitacao.tipo_operacao:
        faltas.append("Tipo de operação")
    if solicitacao.unidade_movel and not solicitacao.unidade_movel_designada_id:
        faltas.append("Qual unidade móvel vai ao evento")
    return faltas


@transaction.atomic
def enviar(solicitacao, usuario):
    """Envia a solicitação revisada (nova ou devolvida) para o despacho da DG."""
    if solicitacao.status not in STATUS_EDITAVEIS:
        raise TransicaoInvalida(
            "Apenas rascunhos ou solicitações devolvidas podem ser enviados."
        )
    faltas = pendencias_para_envio(solicitacao)
    if faltas:
        raise ValidationError(
            "Preencha os campos obrigatórios antes de enviar: " + ", ".join(faltas) + "."
        )
    anterior = _transicionar(solicitacao, StatusSolicitacao.AGUARDANDO_DESPACHO)
    solicitacao.save()
    registrar_historico(
        solicitacao,
        usuario,
        AcaoHistorico.ENVIO,
        status_anterior=anterior,
        status_novo=solicitacao.status,
    )
    link_detalhe = reverse("solicitacoes:detalhe", args=[solicitacao.pk])
    notificar(
        usuarios_do_grupo("GESTOR_DG"),
        f"Solicitação #{solicitacao.pk} aguardando despacho",
        f"{solicitacao.municipio or 'Município a definir'} — "
        f"{solicitacao.tipo_evento or 'tipo a definir'}.",
        link=f"{link_detalhe}#despacho-dg",
        solicitacao=solicitacao,
        exceto=usuario,
    )
    return solicitacao


@transaction.atomic
def devolver(solicitacao, usuario, observacao):
    """A DG devolve para o criador ajustar e reenviar, com o motivo."""
    if solicitacao.status != StatusSolicitacao.AGUARDANDO_DESPACHO:
        raise TransicaoInvalida(
            "Somente solicitações aguardando despacho podem ser devolvidas."
        )
    observacao = (observacao or "").strip()
    if not observacao:
        raise ValidationError(
            "Informe o motivo da devolução para o solicitante ajustar."
        )
    anterior = _transicionar(solicitacao, StatusSolicitacao.DEVOLVIDA)
    solicitacao.save()
    registrar_historico(
        solicitacao,
        usuario,
        AcaoHistorico.DEVOLUCAO,
        status_anterior=anterior,
        status_novo=solicitacao.status,
        observacao=observacao,
    )
    notificar(
        [solicitacao.criado_por],
        f"Solicitação #{solicitacao.pk} devolvida para ajuste",
        observacao,
        link=reverse("solicitacoes:editar", args=[solicitacao.pk]),
        solicitacao=solicitacao,
        exceto=usuario,
    )
    return solicitacao


def ajustar_quantidades_dg(solicitacao, usuario, quantidades):
    """A DG aceita ou altera a quantidade de servidores de cada equipe.

    `quantidades` mapeia equipe_id -> nova quantidade (int >= 1). Alterações
    são aplicadas e registradas no histórico; valores iguais são ignorados.
    """
    itens = {item.equipe_id: item for item in solicitacao.itens_equipe.select_related("equipe")}
    mudancas = []
    for equipe_id, quantidade in (quantidades or {}).items():
        item = itens.get(equipe_id)
        if item is None:
            continue
        if not isinstance(quantidade, int) or quantidade < 1:
            raise ValidationError(
                f"Informe uma quantidade válida de servidores para {item.equipe}."
            )
        if item.quantidade_servidores != quantidade:
            mudancas.append(
                f"{item.equipe}: {item.quantidade_servidores or 0} → {quantidade}"
            )
            item.quantidade_servidores = quantidade
            item.save(update_fields=["quantidade_servidores"])
    if mudancas:
        solicitacao.recalcular_quantidade_servidores()
        registrar_historico(
            solicitacao,
            usuario,
            AcaoHistorico.AJUSTE_DG,
            status_novo=solicitacao.status,
            observacao="; ".join(mudancas),
        )
    return mudancas


@transaction.atomic
def salvar_ajustes_dg(solicitacao, usuario, quantidades):
    """A DG salva ajustes de quantidade sem registrar a decisão ainda."""
    if solicitacao.status != StatusSolicitacao.AGUARDANDO_DESPACHO:
        raise TransicaoInvalida(
            "Somente solicitações aguardando despacho podem ser ajustadas pela DG."
        )
    return ajustar_quantidades_dg(solicitacao, usuario, quantidades)


@transaction.atomic
def despachar(solicitacao, usuario, decisao, observacao="", quantidades=None):
    if solicitacao.finalizada:
        raise TransicaoInvalida("A solicitação já foi finalizada e não aceita novo despacho.")
    if solicitacao.status != StatusSolicitacao.AGUARDANDO_DESPACHO:
        raise TransicaoInvalida(
            "Somente solicitações aguardando despacho podem receber decisão da DG."
        )
    if decisao not in STATUS_POR_DECISAO:
        raise ValidationError("Decisão inválida.")
    observacao = (observacao or "").strip()
    if decisao in DECISOES_COM_OBSERVACAO_OBRIGATORIA and not observacao:
        raise ValidationError(
            "A observação da DG é obrigatória para decisões de não atendimento ou cancelamento."
        )
    # A DG pode aceitar as quantidades propostas ou ajustá-las ao decidir.
    ajustar_quantidades_dg(solicitacao, usuario, quantidades)
    anterior = _transicionar(solicitacao, STATUS_POR_DECISAO[decisao])
    solicitacao.decisao_dg = decisao
    solicitacao.observacoes_dg = observacao
    solicitacao.decidido_por = usuario
    solicitacao.decidido_em = timezone.now()
    solicitacao.save()
    registrar_historico(
        solicitacao,
        usuario,
        AcaoHistorico.DECISAO,
        status_anterior=anterior,
        status_novo=solicitacao.status,
        observacao=observacao,
    )
    notificar(
        [solicitacao.criado_por],
        f"Solicitação #{solicitacao.pk}: {solicitacao.get_status_display().lower()}",
        observacao or "A Diretoria-Geral registrou a decisão.",
        link=reverse("solicitacoes:detalhe", args=[solicitacao.pk]),
        solicitacao=solicitacao,
        exceto=usuario,
    )
    return solicitacao


@transaction.atomic
def concluir_atendimento(solicitacao, usuario):
    """O solicitante confirma que o evento aconteceu e foi atendido."""
    if solicitacao.status != StatusSolicitacao.DEFERIDA_EM_ANDAMENTO:
        raise TransicaoInvalida(
            "Somente solicitações deferidas em andamento podem ser confirmadas."
        )
    anterior = _transicionar(solicitacao, StatusSolicitacao.ATENDIDA)
    solicitacao.save()
    registrar_historico(
        solicitacao,
        usuario,
        AcaoHistorico.CONCLUSAO,
        status_anterior=anterior,
        status_novo=solicitacao.status,
    )
    notificar(
        usuarios_do_grupo("GESTOR_DG", exceto=usuario),
        f"Solicitação #{solicitacao.pk}: atendimento confirmado",
        f"{solicitacao.municipio or 'Município a definir'} — o solicitante "
        "confirmou que o evento foi atendido.",
        link=reverse("solicitacoes:detalhe", args=[solicitacao.pk]),
        solicitacao=solicitacao,
        exceto=usuario,
    )
    return solicitacao


@transaction.atomic
def cancelar_evento(solicitacao, usuario, observacao):
    """Registra cancelamento apenas para autoria ou alçada autorizada."""
    from .permissions import STATUS_CANCELAVEIS, pode_cancelar

    if solicitacao.status not in STATUS_CANCELAVEIS:
        raise TransicaoInvalida(
            "Apenas solicitações em andamento podem ser canceladas."
        )
    if not pode_cancelar(usuario, solicitacao):
        raise PermissionDenied("Você não pode cancelar esta solicitação.")
    observacao = (observacao or "").strip()
    if not observacao:
        raise ValidationError("Informe o motivo do cancelamento do evento.")
    anterior = _transicionar(solicitacao, StatusSolicitacao.CANCELADA)
    solicitacao.save()
    registrar_historico(
        solicitacao,
        usuario,
        AcaoHistorico.CANCELAMENTO,
        status_anterior=anterior,
        status_novo=solicitacao.status,
        observacao=observacao,
    )
    interessados = set(usuarios_do_grupo("GESTOR_DG"))
    interessados.add(solicitacao.criado_por)
    interessados.discard(usuario)
    notificar(
        list(interessados),
        f"Solicitação #{solicitacao.pk}: evento cancelado",
        observacao,
        link=reverse("solicitacoes:detalhe", args=[solicitacao.pk]),
        solicitacao=solicitacao,
        exceto=usuario,
    )
    return solicitacao


def montar_timeline(solicitacao=None):
    """Etapas da timeline lateral a partir do status e histórico reais.

    Cada etapa vencida traz quem fez, quando e a observação do histórico —
    o mesmo rastro do processo que a tela de cadastro registra. Sem
    solicitação (tela de criação), devolve o estado inicial de rascunho.
    """

    def registro_de(*acoes):
        if not solicitacao or not solicitacao.pk:
            return None
        return next(
            (h for h in solicitacao.historico.all() if h.acao in acoes), None
        )

    def detalhes(registro):
        """Data/hora, autor e observação de um registro do histórico."""
        if registro is None:
            return {}
        return {
            "quando": timezone.localtime(registro.criado_em).strftime(
                "%d/%m/%Y %H:%M"
            ),
            "usuario": str(registro.usuario) if registro.usuario else "",
            "observacao": registro.observacao,
        }

    status = solicitacao.status if solicitacao else StatusSolicitacao.RASCUNHO
    rascunho = status == StatusSolicitacao.RASCUNHO
    devolvida = status == StatusSolicitacao.DEVOLVIDA
    aguardando = status == StatusSolicitacao.AGUARDANDO_DESPACHO
    deferida = status == StatusSolicitacao.DEFERIDA_EM_ANDAMENTO
    finalizada = bool(solicitacao) and solicitacao.finalizada

    if devolvida:
        subtitulo_envio = "Devolvida para ajuste — revise e reenvie"
    elif rascunho:
        subtitulo_envio = "Aguardando preenchimento"
    else:
        subtitulo_envio = "Concluída"

    # Origem da etapa de envio: o envio em si ou, nas importadas da
    # planilha, o registro de importação.
    registro_envio = registro_de(
        AcaoHistorico.ENVIO, AcaoHistorico.IMPORTACAO, AcaoHistorico.CRIACAO
    )

    etapas = [
        {
            "titulo": "Enviar para a DG",
            "subtitulo": subtitulo_envio,
            "estado": "atual" if rascunho or devolvida else "concluido",
            **(detalhes(registro_envio) if not (rascunho or devolvida) else {}),
        },
        {
            "titulo": "Aguardando despacho DG",
            "subtitulo": "Concluída" if finalizada or deferida else "Pendente",
            "estado": "concluido"
            if finalizada or deferida
            else ("atual" if aguardando else "pendente"),
            **(detalhes(registro_envio) if aguardando else {}),
        },
    ]

    registro_decisao = registro_de(AcaoHistorico.DECISAO)

    if deferida:
        etapas.append(
            {
                "titulo": "Deferida — em andamento",
                "subtitulo": "Deferida pela DG",
                "estado": "atual",
                **detalhes(registro_decisao),
            }
        )
        etapas.append(
            {
                "titulo": "Atendimento do evento",
                "subtitulo": "Confirme após o evento acontecer",
                "estado": "pendente",
            }
        )

    if finalizada:
        # Atendida passou pela fase deferida; mostra o caminho completo.
        if status == StatusSolicitacao.ATENDIDA and registro_decisao:
            etapas.append(
                {
                    "titulo": "Deferida — em andamento",
                    "subtitulo": "Deferida pela DG",
                    "estado": "concluido",
                    **detalhes(registro_decisao),
                }
            )
        rotulos = {
            StatusSolicitacao.ATENDIDA: "Atendida",
            StatusSolicitacao.NAO_ATENDIDA: "Não atendida",
            StatusSolicitacao.CANCELADA: "Cancelada",
        }
        registro_final = (
            registro_de(AcaoHistorico.CONCLUSAO)
            or registro_de(AcaoHistorico.CANCELAMENTO)
            or registro_decisao
        )
        etapas.append(
            {
                "titulo": rotulos[solicitacao.status],
                "subtitulo": "Encerrada",
                "estado": "concluido",
                **detalhes(registro_final),
            }
        )
    return etapas
