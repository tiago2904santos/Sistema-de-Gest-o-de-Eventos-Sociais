from solicitacoes.permissions import eh_administrador


def perfis(request):
    """Disponibiliza flags de perfil para a navegação."""
    usuario = getattr(request, "user", None)
    if not usuario or not usuario.is_authenticated:
        return {"usuario_eh_administrador": False}
    return {"usuario_eh_administrador": eh_administrador(usuario)}
