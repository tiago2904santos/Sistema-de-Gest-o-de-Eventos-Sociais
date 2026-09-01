CODIGO_MODULO = "ASCOM_DEMANDAS_EVENTOS"


def queryset_visivel(user, queryset):
    if user.is_superuser:
        return queryset
    return queryset.filter(
        setores__usuarios=user,
        setores__ativo=True,
    ).distinct()


def pode_ver(user, demanda):
    if user.is_superuser:
        return True
    return demanda.setores.filter(usuarios=user, ativo=True).exists()


def pode_editar(user, demanda):
    if user.is_superuser:
        return True
    return pode_ver(user, demanda) and not demanda.finalizada


def setores_do_usuario_para_modulo(user):
    from accounts.models import Setor

    if user and user.is_superuser:
        return Setor.objects.filter(
            ativo=True, modulos__codigo=CODIGO_MODULO, modulos__ativo=True
        ).distinct()
    if not user:
        return Setor.objects.none()
    return user.setores.filter(
        ativo=True, modulos__codigo=CODIGO_MODULO, modulos__ativo=True
    ).distinct()
