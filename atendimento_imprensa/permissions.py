"""Política de acesso do módulo de Atendimento à Imprensa da ASCOM.

Quem tem o módulo enxerga e edita todos os atendimentos; os cadastros de
apoio (equipe e veículos) ficam com o perfil administrador.
"""

from functools import wraps

from django.core.exceptions import PermissionDenied

from accounts.modulos import modulo_requerido, usuario_tem_modulo
from solicitacoes.permissions import eh_administrador

CODIGO_MODULO = "ASCOM_ATENDIMENTO_IMPRENSA"


def acesso_ao_modulo(view):
    return modulo_requerido(CODIGO_MODULO)(view)


def pode_acessar(usuario):
    return usuario_tem_modulo(usuario, CODIGO_MODULO)


def gerenciamento_de_cadastros(view):
    @acesso_ao_modulo
    @wraps(view)
    def wrapper(request, *args, **kwargs):
        if not eh_administrador(request.user):
            raise PermissionDenied
        return view(request, *args, **kwargs)

    return wrapper
