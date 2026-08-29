"""Política de acesso das solicitações.

Centraliza todas as regras de perfil (Groups) e de estado, usadas pelas views
para autorizar ações e pelos templates para exibir/ocultar botões.
"""

from django.db.models import Q

from .models import StatusSolicitacao

GRUPO_SOLICITANTE = "SOLICITANTE"
GRUPO_ANALISTA = "ANALISTA"
GRUPO_GESTOR_DG = "GESTOR_DG"
GRUPO_ADMINISTRADOR = "ADMINISTRADOR"

GRUPOS_PADRAO = [GRUPO_SOLICITANTE, GRUPO_ANALISTA, GRUPO_GESTOR_DG, GRUPO_ADMINISTRADOR]

STATUS_FINAIS = {
    StatusSolicitacao.ATENDIDA,
    StatusSolicitacao.NAO_ATENDIDA,
    StatusSolicitacao.CANCELADA,
}


def _pertence(user, *grupos):
    return user.groups.filter(name__in=grupos).exists()


def eh_administrador(user):
    return user.is_superuser or _pertence(user, GRUPO_ADMINISTRADOR)


def eh_analista(user):
    return eh_administrador(user) or _pertence(user, GRUPO_ANALISTA)


def eh_gestor_dg(user):
    return eh_administrador(user) or _pertence(user, GRUPO_GESTOR_DG)


def pode_ver(user, solicitacao):
    if eh_administrador(user):
        return True
    if solicitacao.criado_por_id == user.pk:
        return True
    if solicitacao.status == StatusSolicitacao.RASCUNHO:
        return False
    if eh_analista(user):
        return True
    if eh_gestor_dg(user):
        return (
            solicitacao.status == StatusSolicitacao.AGUARDANDO_DESPACHO
            or solicitacao.status in STATUS_FINAIS
        )
    return False


def queryset_visivel(user, queryset):
    """Restringe um queryset de solicitações ao que o usuário pode ver."""
    if eh_administrador(user):
        return queryset
    filtro = Q(criado_por=user)
    if eh_analista(user):
        filtro |= ~Q(status=StatusSolicitacao.RASCUNHO)
    if eh_gestor_dg(user):
        filtro |= Q(status=StatusSolicitacao.AGUARDANDO_DESPACHO) | Q(
            status__in=STATUS_FINAIS
        )
    return queryset.filter(filtro)


def pode_editar_dados(user, solicitacao):
    if solicitacao.finalizada:
        return user.is_superuser
    if eh_administrador(user):
        return True
    return (
        solicitacao.criado_por_id == user.pk
        and solicitacao.status == StatusSolicitacao.RASCUNHO
    )


def pode_editar_planejamento(user, solicitacao):
    if solicitacao.finalizada:
        return user.is_superuser
    if eh_administrador(user):
        return True
    return eh_analista(user) and solicitacao.status == StatusSolicitacao.EM_ANALISE


def pode_editar(user, solicitacao):
    return pode_editar_dados(user, solicitacao) or pode_editar_planejamento(
        user, solicitacao
    )


def pode_enviar(user, solicitacao):
    return (
        solicitacao.status == StatusSolicitacao.RASCUNHO
        and (eh_administrador(user) or solicitacao.criado_por_id == user.pk)
    )


def pode_iniciar_analise(user, solicitacao):
    return solicitacao.status == StatusSolicitacao.ENVIADA and eh_analista(user)


def pode_analisar(user, solicitacao):
    """Acesso à tela de análise: solicitações enviadas ou já em análise."""
    return eh_analista(user) and solicitacao.status in {
        StatusSolicitacao.ENVIADA,
        StatusSolicitacao.EM_ANALISE,
    }


def pode_encaminhar_despacho(user, solicitacao):
    return solicitacao.status == StatusSolicitacao.EM_ANALISE and eh_analista(user)


def pode_despachar(user, solicitacao):
    return solicitacao.status == StatusSolicitacao.AGUARDANDO_DESPACHO and eh_gestor_dg(
        user
    )


def acoes_permitidas(user, solicitacao):
    """Mapa de ações para os templates decidirem o que exibir."""
    return {
        "ver": pode_ver(user, solicitacao),
        "editar": pode_editar(user, solicitacao),
        "editar_dados": pode_editar_dados(user, solicitacao),
        "editar_planejamento": pode_editar_planejamento(user, solicitacao),
        "enviar": pode_enviar(user, solicitacao),
        "analisar": pode_analisar(user, solicitacao),
        "iniciar_analise": pode_iniciar_analise(user, solicitacao),
        "encaminhar_despacho": pode_encaminhar_despacho(user, solicitacao),
        "despachar": pode_despachar(user, solicitacao),
    }
