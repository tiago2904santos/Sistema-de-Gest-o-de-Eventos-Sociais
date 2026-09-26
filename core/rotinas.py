"""Rotinas diárias sem cron: o primeiro acesso do dia dispara os lembretes.

O servidor não tem agendador configurado, e os lembretes das solicitações
(`solicitacoes.lembretes`) e os avisos da prestação de contas
(`viagens_prestacoes.avisos`) só saíam se alguém rodasse o comando à mão.
Aqui o `RotinasDiariasMiddleware` chama `rodar_se_for_hora` a cada
requisição de usuário logado: uma vez por dia (a chave do dia no cache
compartilhado garante isso entre os workers) ele roda tudo o que é diário:

1. os lembretes das solicitações (confirmar atendimento, evento em 7 dias
   aguardando despacho, devolução parada);
2. os avisos da prestação de contas (saque, prazo, documentos, saídas e
   chegadas de viagem);
3. o resumo do dia de cada usuário ativo: o que está pendente nos módulos
   dele, no sino — a secretária dizendo "hoje você tem isto".

Cada rotina é idempotente (avisa uma vez só) e roda protegida: uma falha
vira log e não impede as outras nem a página que a pessoa abriu. O comando
`manage.py` de cada rotina continua valendo para quem tiver cron.
"""

from __future__ import annotations

import logging
from datetime import timedelta

from django.conf import settings
from django.core.cache import cache
from django.urls import reverse
from django.utils import timezone

logger = logging.getLogger(__name__)

__all__ = ["RotinasDiariasMiddleware", "resumo_do_dia", "rodar", "rodar_se_for_hora"]

#: A chave do dia fica no cache por dois dias: o suficiente para ninguém
#: repetir a rodada e curto o bastante para não acumular.
_VALIDADE_DA_CHAVE = 2 * 24 * 60 * 60
#: Usuário sem acesso há mais de tantos dias não recebe o resumo do dia.
DIAS_DE_INATIVIDADE = 30
#: Eventos "próximos" no resumo do dia.
DIAS_DE_HORIZONTE = 7

# Dia (data ISO) da última rodada vista por este processo: evita consultar o
# cache a cada requisição.
_ultimo_dia_visto = ""


def _chave(hoje) -> str:
    return f"rotinas-diarias:{hoje.isoformat()}"


def rodar_se_for_hora(hoje=None) -> bool:
    """Roda as rotinas do dia se ainda não rodaram hoje; True se rodou agora."""
    global _ultimo_dia_visto
    hoje = hoje or timezone.localdate()
    if _ultimo_dia_visto == hoje.isoformat():
        return False
    if not cache.add(_chave(hoje), timezone.now().isoformat(), timeout=_VALIDADE_DA_CHAVE):
        _ultimo_dia_visto = hoje.isoformat()
        return False
    _ultimo_dia_visto = hoje.isoformat()
    rodar(hoje)
    return True


def _protegido(nome, funcao, *args):
    try:
        resultado = funcao(*args)
        logger.info("Rotina diária %s: %s.", nome, resultado)
    except Exception:
        logger.exception("Rotina diária %s falhou.", nome)


def rodar(hoje=None) -> None:
    """Todas as rotinas do dia, cada uma protegida da falha das outras."""
    from solicitacoes.lembretes import enviar_lembretes
    from viagens_prestacoes.avisos import avisar_prazos, avisar_viagens

    hoje = hoje or timezone.localdate()
    _protegido("lembretes das solicitações", enviar_lembretes, hoje)
    _protegido("avisos da prestação de contas", avisar_prazos, hoje)
    _protegido("saídas e chegadas de viagem", avisar_viagens)
    _protegido("resumo do dia", resumo_do_dia, hoje)


def _linhas_do_resumo(usuario, hoje) -> list[str]:
    """"Palestras: 3 pendentes", "Eventos: 2 aguardando despacho, 1 evento em 7 dias"…"""
    from accounts.modulos import modulos_do_portal
    from core.views import METRICAS_POR_MODULO

    linhas = []
    for modulo in modulos_do_portal(usuario):
        calcular = METRICAS_POR_MODULO.get(modulo["slug"])
        if calcular is None:
            continue
        try:
            metricas = calcular(usuario, hoje)
        except Exception:
            logger.exception("Resumo do dia: métricas de %s falharam.", modulo["slug"])
            continue
        pendencias = [
            f"{m['valor']} {m['rotulo'].lower()}" for m in metricas
            if m.get("destaque") and m.get("valor")
        ]
        if modulo["slug"] == "eventos":
            proximos = _eventos_proximos(usuario, hoje)
            if proximos:
                pendencias.append(f"{proximos} evento{'s' if proximos > 1 else ''} em {DIAS_DE_HORIZONTE} dias")
        if pendencias:
            linhas.append(f"{modulo['nome']}: {', '.join(pendencias)}")
    return linhas


def _eventos_proximos(usuario, hoje) -> int:
    from solicitacoes.models import SolicitacaoEvento, StatusSolicitacao
    from solicitacoes.permissions import queryset_visivel

    return (
        queryset_visivel(usuario, SolicitacaoEvento.objects.all())
        .filter(data_inicio_evento__gte=hoje, data_inicio_evento__lte=hoje + timedelta(days=DIAS_DE_HORIZONTE))
        .exclude(status__in=[StatusSolicitacao.CANCELADA, StatusSolicitacao.NAO_ATENDIDA])
        .count()
    )


def resumo_do_dia(hoje=None) -> int:
    """O aviso "Resumo de hoje" no sino de cada usuário ativo, em dia útil.

    Só quem entrou no sistema nos últimos `DIAS_DE_INATIVIDADE` dias e só
    quando há alguma pendência nos módulos da pessoa: sem pendência, sem
    ruído. Devolve quantos resumos saíram.
    """
    from django.contrib.auth import get_user_model

    from core.notificacoes import notificar

    hoje = hoje or timezone.localdate()
    if hoje.weekday() >= 5:
        return 0
    limite = timezone.now() - timedelta(days=DIAS_DE_INATIVIDADE)
    usuarios = get_user_model().objects.filter(is_active=True, last_login__gte=limite)
    enviados = 0
    titulo = f"Resumo de hoje ({hoje:%d/%m}): o que está pendente"
    for usuario in usuarios:
        if usuario.notificacoes.filter(titulo=titulo).exists():
            continue
        linhas = _linhas_do_resumo(usuario, hoje)
        if not linhas:
            continue
        notificar([usuario], titulo, " · ".join(linhas), link=reverse("core:home"))
        enviados += 1
    return enviados


class RotinasDiariasMiddleware:
    """Dispara `rodar_se_for_hora` no primeiro acesso de usuário logado do dia."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        usuario = getattr(request, "user", None)
        if getattr(settings, "ROTINAS_DIARIAS_AUTOMATICAS", True) and usuario is not None and usuario.is_authenticated:
            try:
                rodar_se_for_hora()
            except Exception:  # a página da pessoa nunca cai por causa da rotina
                logger.exception("Rotinas diárias: falha ao disparar.")
        return response
