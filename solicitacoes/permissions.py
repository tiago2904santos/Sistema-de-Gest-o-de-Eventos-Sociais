"""Política de acesso das solicitações.

Centraliza todas as regras de perfil (Groups) e de estado, usadas pelas views
para autorizar ações e pelos templates para exibir/ocultar botões.

Modelo de perfis:
- SOLICITANTE: todo usuário — cria, revisa e envia para a DG.
- GESTOR_DG: o único que despacha/autoriza; também gerencia usuários.
- ADMINISTRADOR: um solicitante que gerencia usuários e cadastros, mas NÃO
  pode despachar.
- Superusuário ignora todas as restrições.

Fluxo: RASCUNHO → (enviar) → AGUARDANDO_DESPACHO → decisão da DG. A DG
só mexe na quantidade de servidores das equipes; o resto ela manda para
correção. Enviado, o pedido só muda pelo "Editar", que o devolve à DG.
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


def _autor(user, solicitacao):
    return user.is_superuser or solicitacao.criado_por_id == user.pk


def pode_editar_dados(user, solicitacao):
    """Só o rascunho e a devolvida para correção se editam livremente.

    Depois do envio os dados ficam travados para todos (inclusive o
    superusuário): mudar exige o "Editar" (`pode_reabrir`), que devolve o
    pedido para novo despacho da DG.
    """
    return solicitacao.status in STATUS_EDITAVEIS and _autor(user, solicitacao)


STATUS_REABRIVEIS = {
    StatusSolicitacao.AGUARDANDO_DESPACHO,
    StatusSolicitacao.DEFERIDA_EM_ANDAMENTO,
}


def pode_reabrir(user, solicitacao):
    """O "Editar" de um pedido já enviado: altera e volta para a DG."""
    return solicitacao.status in STATUS_REABRIVEIS and _autor(user, solicitacao)


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


def pode_gerar_viagem(user):
    """"Gerar viagem" pela tela: a DG, que deferiu, ou quem opera Viagens."""
    # Import tardio: as permissões de Viagens importam este módulo.
    from viagens_cadastros.permissions import pode_editar_cadastros

    return eh_gestor_dg(user) or pode_editar_cadastros(user)


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
    """Terminado o evento, o solicitante confirma que foi atendido."""
    return (
        aguarda_atendimento(user, solicitacao) and solicitacao.evento_encerrado
    )


def aguarda_atendimento(user, solicitacao):
    """Deferida e do usuário: só falta o evento acabar para confirmar."""
    return solicitacao.status == StatusSolicitacao.DEFERIDA_EM_ANDAMENTO and _autor(
        user, solicitacao
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
        "reabrir": pode_reabrir(user, solicitacao),
        "aguarda_atendimento": aguarda_atendimento(user, solicitacao),
        "enviar": pode_enviar(user, solicitacao),
        "excluir": pode_excluir(user, solicitacao),
        "despachar": pode_despachar(user, solicitacao),
        "concluir": pode_concluir(user, solicitacao),
        "cancelar": pode_cancelar(user, solicitacao),
        "gerenciar_anexos": pode_gerenciar_anexos(user, solicitacao),
    }
