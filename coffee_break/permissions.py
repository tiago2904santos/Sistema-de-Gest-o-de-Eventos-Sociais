"""Política de acesso do módulo de Coffee Break da ASCOM.

O controle da planilha é centralizado na ASCOM: não há isolamento por setor
dentro do módulo — quem tem o módulo enxerga todos os lotes e solicitações.
O que se exige é o módulo `ASCOM_COFFEE_BREAK` (via Setor ↔ Modulo), aplicado
pelo middleware de módulos e pelo decorator nas views.
"""

from functools import wraps

from django.core.exceptions import PermissionDenied

from accounts.modulos import modulo_requerido, usuario_tem_modulo
from solicitacoes.permissions import eh_administrador

CODIGO_MODULO = "ASCOM_COFFEE_BREAK"


def acesso_ao_modulo(view):
    """Decorator das views do módulo: login + módulo ASCOM_COFFEE_BREAK."""
    return modulo_requerido(CODIGO_MODULO)(view)


def pode_acessar(usuario):
    return usuario_tem_modulo(usuario, CODIGO_MODULO)


def gerenciamento_de_cadastros(view):
    """Cadastros contratuais exigem módulo e perfil administrador."""

    @acesso_ao_modulo
    @wraps(view)
    def wrapper(request, *args, **kwargs):
        if not eh_administrador(request.user):
            raise PermissionDenied
        return view(request, *args, **kwargs)

    return wrapper
