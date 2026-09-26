"""Lembretes automáticos das solicitações (sino e e-mail).

Três avisos, cada um enviado uma vez só por solicitação e data de referência
(`LembreteSolicitacao`), então rodar de novo no mesmo dia não repete nada:

- o autor, no dia seguinte ao fim do evento deferido: confirmar o atendimento;
- a DG, quando um pedido aguarda despacho e o evento começa em até 7 dias;
- o autor, quando a devolução para correção está parada há mais de 3 dias.

Só entram eventos e devoluções recentes (`JANELA_DIAS`): na primeira
execução, os pedidos antigos esquecidos não viram uma enxurrada de avisos —
eles continuam na fila "Confirmar atendimento" da lista.

Quem agenda é o comando `manage.py enviar_lembretes_solicitacoes` (cron ou
timer do servidor, uma vez por dia).
"""

from datetime import timedelta

from django.db import IntegrityError, transaction
from django.db.models import Max, Q
from django.urls import reverse
from django.utils import timezone

from core.notificacoes import notificar, usuarios_do_grupo

from .models import (
    AcaoHistorico,
    LembreteSolicitacao,
    SolicitacaoEvento,
    StatusSolicitacao,
    TipoLembrete,
)

DIAS_ANTES_DO_EVENTO = 7
DIAS_DEVOLUCAO_PARADA = 3
JANELA_DIAS = 30


def condicao_evento_encerrado(hoje=None):
    """Q do evento que já terminou (o último dia ficou para trás)."""
    hoje = hoje or timezone.localdate()
    return Q(data_fim_evento__lt=hoje) | Q(
        data_fim_evento__isnull=True, data_inicio_evento__lt=hoje
    )


def _registrar(solicitacao, tipo, referencia):
    """Grava o lembrete; False se ele já tinha sido enviado."""
    try:
        with transaction.atomic():
            _, criado = LembreteSolicitacao.objects.get_or_create(
                solicitacao=solicitacao, tipo=tipo, referencia=referencia
            )
    except IntegrityError:  # outra execução gravou no mesmo instante
        return False
    return criado


def _ja_enviado(solicitacao, tipo, referencia):
    return LembreteSolicitacao.objects.filter(
        solicitacao=solicitacao, tipo=tipo, referencia=referencia
    ).exists()


def _pendentes_de_confirmacao(hoje):
    return (
        SolicitacaoEvento.objects.filter(status=StatusSolicitacao.DEFERIDA_EM_ANDAMENTO)
        .filter(condicao_evento_encerrado(hoje))
        .filter(
            Q(data_fim_evento__gte=hoje - timedelta(days=JANELA_DIAS))
            | Q(
                data_fim_evento__isnull=True,
                data_inicio_evento__gte=hoje - timedelta(days=JANELA_DIAS),
            )
        )
        .select_related("municipio", "criado_por")
    )


def _despachos_proximos(hoje):
    return SolicitacaoEvento.objects.filter(
        status=StatusSolicitacao.AGUARDANDO_DESPACHO,
        data_inicio_evento__gte=hoje,
        data_inicio_evento__lte=hoje + timedelta(days=DIAS_ANTES_DO_EVENTO),
    ).select_related("municipio", "tipo_evento")


def _devolucoes_paradas(hoje):
    limite = hoje - timedelta(days=DIAS_DEVOLUCAO_PARADA)
    candidatas = (
        SolicitacaoEvento.objects.filter(status=StatusSolicitacao.DEVOLVIDA)
        .annotate(
            devolvida_em=Max(
                "historico__criado_em",
                filter=Q(historico__acao=AcaoHistorico.DEVOLUCAO),
            )
        )
        .select_related("municipio", "criado_por")
    )
    for solicitacao in candidatas:
        if solicitacao.devolvida_em is None:
            continue
        dia = timezone.localdate(solicitacao.devolvida_em)
        if hoje - timedelta(days=JANELA_DIAS) <= dia < limite:
            yield solicitacao, dia


def enviar_lembretes(hoje=None, simular=False):
    """Envia o que estiver pendente; devolve {tipo: quantidade}.

    `simular` só conta, sem gravar nem avisar ninguém.
    """
    hoje = hoje or timezone.localdate()
    enviados = {tipo: 0 for tipo in TipoLembrete.values}

    def avisar(solicitacao, tipo, referencia, destinatarios, titulo, mensagem, ancora=""):
        if simular:
            if not _ja_enviado(solicitacao, tipo, referencia):
                enviados[tipo] += 1
            return
        with transaction.atomic():
            if not _registrar(solicitacao, tipo, referencia):
                return
            notificar(
                destinatarios,
                titulo,
                mensagem,
                link=reverse("solicitacoes:editar", args=[solicitacao.pk]) + ancora,
                solicitacao=solicitacao,
            )
        enviados[tipo] += 1

    for solicitacao in _pendentes_de_confirmacao(hoje):
        ultimo = solicitacao.ultimo_dia_evento
        avisar(
            solicitacao,
            TipoLembrete.CONFIRMAR_ATENDIMENTO,
            ultimo,
            [solicitacao.criado_por],
            f"Solicitação #{solicitacao.pk}: confirme o atendimento",
            f"O evento em {solicitacao.municipio or 'município a definir'} terminou em "
            f"{ultimo:%d/%m/%Y}. Se foi atendido, marque a solicitação como atendida.",
            "#encerramento",
        )

    gestores = list(usuarios_do_grupo("GESTOR_DG"))
    for solicitacao in _despachos_proximos(hoje):
        faltam = (solicitacao.data_inicio_evento - hoje).days
        quando = "hoje" if faltam == 0 else "amanhã" if faltam == 1 else f"em {faltam} dias"
        avisar(
            solicitacao,
            TipoLembrete.DESPACHO_PROXIMO,
            solicitacao.data_inicio_evento,
            gestores,
            f"Solicitação #{solicitacao.pk} aguarda despacho: evento {quando}",
            f"{solicitacao.tipo_evento or 'Evento'} em "
            f"{solicitacao.municipio or 'município a definir'} começa em "
            f"{solicitacao.data_inicio_evento:%d/%m/%Y}.",
            "#despacho-dg",
        )

    for solicitacao, dia in _devolucoes_paradas(hoje):
        avisar(
            solicitacao,
            TipoLembrete.DEVOLUCAO_PARADA,
            dia,
            [solicitacao.criado_por],
            f"Solicitação #{solicitacao.pk} aguarda a sua correção",
            f"A Diretoria-Geral devolveu a solicitação em {dia:%d/%m/%Y}. "
            "Faça os ajustes pedidos e reenvie para o despacho.",
        )

    return enviados
