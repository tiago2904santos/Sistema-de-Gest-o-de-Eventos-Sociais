from solicitacoes.permissions import eh_administrador, pode_gerenciar_usuarios


def perfis(request):
    """Disponibiliza flags de perfil para a navegação."""
    usuario = getattr(request, "user", None)
    if not usuario or not usuario.is_authenticated:
        return {
            "usuario_eh_administrador": False,
            "usuario_gerencia_usuarios": False,
        }
    return {
        "usuario_eh_administrador": eh_administrador(usuario),
        "usuario_gerencia_usuarios": pode_gerenciar_usuarios(usuario),
    }


def notificacoes(request):
    """Contador de notificações não lidas para o sino do cabeçalho."""
    usuario = getattr(request, "user", None)
    if not usuario or not usuario.is_authenticated:
        return {"notificacoes_nao_lidas": 0}
    return {
        "notificacoes_nao_lidas": usuario.notificacoes.filter(lida=False).count()
    }
