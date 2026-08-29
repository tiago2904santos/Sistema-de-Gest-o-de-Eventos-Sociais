"""Camada de serviço do workflow de solicitações.

Todas as mudanças de status passam por aqui: as views nunca alteram o campo
`status` diretamente, e transições inválidas levantam `TransicaoInvalida`.
"""

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

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
    StatusSolicitacao.RASCUNHO: {StatusSolicitacao.ENVIADA},
    StatusSolicitacao.ENVIADA: {StatusSolicitacao.EM_ANALISE},
    StatusSolicitacao.EM_ANALISE: {StatusSolicitacao.AGUARDANDO_DESPACHO},
    StatusSolicitacao.AGUARDANDO_DESPACHO: {
        StatusSolicitacao.ATENDIDA,
        StatusSolicitacao.NAO_ATENDIDA,
        StatusSolicitacao.CANCELADA,
    },
}

STATUS_POR_DECISAO = {
    DecisaoDG.ATENDER: StatusSolicitacao.ATENDIDA,
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
    """Lista de rótulos de campos ainda pendentes para o envio."""
    faltas = [
        rotulo
        for campo, rotulo in CAMPOS_OBRIGATORIOS_ENVIO.items()
        if not getattr(solicitacao, campo)
    ]
    if solicitacao.pk and not solicitacao.itens_servico.exists():
        faltas.append("Ao menos um serviço solicitado")
    return faltas


def pendencias_para_despacho(solicitacao):
    """Pendências do planejamento operacional antes do despacho."""
    faltas = []
    if not solicitacao.itens_equipe.exists():
        faltas.append("Ao menos uma equipe designada")
    elif solicitacao.itens_equipe.exclude(quantidade_servidores__gt=0).exists():
        faltas.append("Quantidade de servidores de cada equipe")
    if not solicitacao.tipo_operacao:
        faltas.append("Tipo de operação")
    return faltas


@transaction.atomic
def enviar(solicitacao, usuario):
    if solicitacao.status != StatusSolicitacao.RASCUNHO:
        raise TransicaoInvalida("Apenas rascunhos podem ser enviados.")
    faltas = pendencias_para_envio(solicitacao)
    if faltas:
        raise ValidationError(
            "Preencha os campos obrigatórios antes de enviar: " + ", ".join(faltas) + "."
        )
    anterior = _transicionar(solicitacao, StatusSolicitacao.ENVIADA)
    solicitacao.save()
    registrar_historico(
        solicitacao,
        usuario,
        AcaoHistorico.ENVIO,
        status_anterior=anterior,
        status_novo=solicitacao.status,
    )
    return solicitacao


@transaction.atomic
def iniciar_analise(solicitacao, usuario):
    anterior = _transicionar(solicitacao, StatusSolicitacao.EM_ANALISE)
    solicitacao.save()
    registrar_historico(
        solicitacao,
        usuario,
        AcaoHistorico.INICIO_ANALISE,
        status_anterior=anterior,
        status_novo=solicitacao.status,
    )
    return solicitacao


@transaction.atomic
def encaminhar_para_despacho(solicitacao, usuario):
    if solicitacao.status != StatusSolicitacao.EM_ANALISE:
        raise TransicaoInvalida(
            "Somente solicitações em análise podem ser encaminhadas para despacho."
        )
    faltas = pendencias_para_despacho(solicitacao)
    if faltas:
        raise ValidationError(
            "Complete o planejamento operacional antes do despacho: "
            + ", ".join(faltas)
            + "."
        )
    anterior = _transicionar(solicitacao, StatusSolicitacao.AGUARDANDO_DESPACHO)
    solicitacao.save()
    registrar_historico(
        solicitacao,
        usuario,
        AcaoHistorico.ENCAMINHAMENTO_DESPACHO,
        status_anterior=anterior,
        status_novo=solicitacao.status,
    )
    return solicitacao


@transaction.atomic
def despachar(solicitacao, usuario, decisao, observacao=""):
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
    return solicitacao


def montar_timeline(solicitacao=None):
    """Etapas da timeline lateral a partir do status e histórico reais.

    Sem solicitação (tela de criação), devolve o estado inicial de rascunho.
    """

    def quando(acao):
        if not solicitacao or not solicitacao.pk:
            return None
        registro = next(
            (h for h in solicitacao.historico.all() if h.acao == acao), None
        )
        return timezone.localtime(registro.criado_em).strftime("%d/%m/%Y %H:%M") if registro else None

    status = solicitacao.status if solicitacao else StatusSolicitacao.RASCUNHO
    ordem = [
        StatusSolicitacao.RASCUNHO,
        StatusSolicitacao.ENVIADA,
        StatusSolicitacao.EM_ANALISE,
        StatusSolicitacao.AGUARDANDO_DESPACHO,
    ]
    # Posição no fluxo: 0..3 conforme a ordem acima; 4 = finalizada.
    posicao = ordem.index(status) if status in ordem else len(ordem)

    etapas = [
        {
            "titulo": "Enviar solicitação",
            "subtitulo": quando(AcaoHistorico.ENVIO)
            or ("Aguardando preenchimento" if posicao == 0 else "Pendente"),
            "estado": "concluido" if posicao >= 1 else "atual",
        },
        {
            "titulo": "Análise",
            "subtitulo": quando(AcaoHistorico.INICIO_ANALISE)
            or ("Aguardando início" if posicao == 1 else "Pendente"),
            "estado": "concluido"
            if posicao >= 3
            else ("atual" if posicao in (1, 2) else "pendente"),
        },
        {
            "titulo": "Aguardando despacho DG",
            "subtitulo": quando(AcaoHistorico.ENCAMINHAMENTO_DESPACHO) or "Pendente",
            "estado": "concluido"
            if posicao >= 4
            else ("atual" if posicao == 3 else "pendente"),
        },
    ]

    if solicitacao and solicitacao.finalizada:
        rotulos = {
            StatusSolicitacao.ATENDIDA: "Atendida",
            StatusSolicitacao.NAO_ATENDIDA: "Não atendida",
            StatusSolicitacao.CANCELADA: "Cancelada",
        }
        etapas.append(
            {
                "titulo": rotulos[solicitacao.status],
                "subtitulo": quando(AcaoHistorico.DECISAO) or "Decisão registrada",
                "estado": "concluido",
            }
        )
    return etapas
