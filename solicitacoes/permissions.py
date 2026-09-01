"""Política de acesso das solicitações.

Centraliza todas as regras de perfil (Groups) e de estado, usadas pelas views
para autorizar ações e pelos templates para exibir/ocultar botões.

Modelo de perfis:
- SOLICITANTE: todo usuário — cria, revisa e envia para a DG.
- GESTOR_DG: o único que despacha/autoriza; também gerencia usuários.
- ADMINISTRADOR: um solicitante que gerencia usuários e cadastros, mas NÃO
  pode despachar.
- Superusuário ignora todas as restrições.

Fluxo: RASCUNHO → (enviar) → AGUARDANDO_DESPACHO → decisão da DG.
"""

from .models import StatusSolicitacao

GRUPO_SOLICITANTE = "SOLICITANTE"
GRUPO_GESTOR_DG = "GESTOR_DG"
GRUPO_ADMINISTRADOR = "ADMINISTRADOR"

# Perfil legado, migrado para SOLICITANTE pelo seed.
GRUPO_ANALISTA_LEGADO = "ANALISTA"

GRUPOS_PADRAO = [GRUPO_SOLICITANTE, GRUPO_GESTOR_DG, GRUPO_ADMINISTRADOR]

STATUS_FINAIS = {
    StatusSolicitacao.ATENDIDA,
    StatusSolicitacao.NAO_ATENDIDA,
    StatusSolicitacao.CANCELADA,
}


def _pertence(user, *grupos):
    return user.groups.filter(name__in=grupos).exists()


def eh_administrador(user):
    return user.is_superuser or _pertence(user, GRUPO_ADMINISTRADOR)


def eh_gestor_dg(user):
    """Alçada de despacho: apenas o grupo GESTOR_DG (administrador NÃO)."""
    return user.is_superuser or _pertence(user, GRUPO_GESTOR_DG)


def pode_gerenciar_usuarios(user):
    """Gestão de usuários: administrador ou gestor DG."""
    return eh_administrador(user) or eh_gestor_dg(user)


def pode_ver(user, solicitacao):
    """Dossiê pertence ao criador; DG e administração têm visão transversal."""
    return (
        user.is_superuser
        or solicitacao.criado_por_id == user.pk
        or eh_gestor_dg(user)
        or eh_administrador(user)
    )


def queryset_visivel(user, queryset):
    """Restringe um queryset de solicitações ao que o usuário pode ver."""
    if user.is_superuser or eh_gestor_dg(user) or eh_administrador(user):
        return queryset
    return queryset.filter(criado_por=user)


STATUS_EDITAVEIS = {StatusSolicitacao.RASCUNHO, StatusSolicitacao.DEVOLVIDA}


def pode_editar_dados(user, solicitacao):
    """Rascunhos e devolvidas são editáveis pelo criador (ou superusuário)."""
    if solicitacao.finalizada:
        return user.is_superuser
    return user.is_superuser or (
        solicitacao.criado_por_id == user.pk
        and solicitacao.status in STATUS_EDITAVEIS
    )


def pode_editar(user, solicitacao):
    return pode_editar_dados(user, solicitacao)


def pode_enviar(user, solicitacao):
    return solicitacao.status in STATUS_EDITAVEIS and (
        user.is_superuser or solicitacao.criado_por_id == user.pk
    )


def pode_excluir(user, solicitacao):
    """Só rascunhos podem ser excluídos — depois do envio fica o histórico."""
    return solicitacao.status == StatusSolicitacao.RASCUNHO and (
        user.is_superuser or solicitacao.criado_por_id == user.pk
    )


def pode_despachar(user, solicitacao):
    return solicitacao.status == StatusSolicitacao.AGUARDANDO_DESPACHO and eh_gestor_dg(
        user
    )


def pode_gerenciar_anexos(user, solicitacao):
    """Anexos seguem a edição dos dados, mas param na finalização.

    Depois de atendida, não atendida ou cancelada o dossiê fecha — inclusive
    para o superusuário, que ainda pode corrigir dados mas não deve alterar
    os documentos que instruíram um evento já encerrado.
    """
    if solicitacao.finalizada:
        return False
    return pode_editar_dados(user, solicitacao)


def pode_concluir(user, solicitacao):
    """Após o evento, o solicitante confirma que foi atendido."""
    return solicitacao.status == StatusSolicitacao.DEFERIDA_EM_ANDAMENTO and (
        user.is_superuser or solicitacao.criado_por_id == user.pk
    )


STATUS_CANCELAVEIS = {
    StatusSolicitacao.AGUARDANDO_DESPACHO,
    StatusSolicitacao.DEVOLVIDA,
    StatusSolicitacao.DEFERIDA_EM_ANDAMENTO,
}


def pode_cancelar(user, solicitacao):
    """Cancelamento exige autoria ou alçada institucional explícita."""
    if solicitacao.status not in STATUS_CANCELAVEIS:
        return False
    return (
        user.is_superuser
        or solicitacao.criado_por_id == user.pk
        or eh_gestor_dg(user)
        or eh_administrador(user)
    )


def acoes_permitidas(user, solicitacao):
    """Mapa de ações para os templates decidirem o que exibir."""
    return {
        "ver": pode_ver(user, solicitacao),
        "editar": pode_editar(user, solicitacao),
        "editar_dados": pode_editar_dados(user, solicitacao),
        "enviar": pode_enviar(user, solicitacao),
        "excluir": pode_excluir(user, solicitacao),
        "despachar": pode_despachar(user, solicitacao),
        "concluir": pode_concluir(user, solicitacao),
        "cancelar": pode_cancelar(user, solicitacao),
        "gerenciar_anexos": pode_gerenciar_anexos(user, solicitacao),
    }
