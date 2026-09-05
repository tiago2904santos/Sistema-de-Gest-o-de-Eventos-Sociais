"""Política de acesso do módulo de Publicações da ASCOM.

O relatório é centralizado na assessoria: quem tem o módulo enxerga e edita
todas as pautas. Os cadastros de apoio (equipe e unidades) ficam com o perfil
administrador, como nos demais módulos.
"""

from functools import wraps

from django.core.exceptions import PermissionDenied

from accounts.modulos import modulo_requerido, usuario_tem_modulo
from solicitacoes.permissions import eh_administrador

CODIGO_MODULO = "ASCOM_PUBLICACOES"


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
