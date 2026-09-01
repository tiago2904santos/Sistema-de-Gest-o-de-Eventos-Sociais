"""Política de acesso dos cadastros de viagens.

Duas camadas, como no resto do sistema:

1. **Módulo** ``VIAGENS`` (Setor ↔ Modulo) — decide quem enxerga o módulo. É
   aplicado pelo middleware sobre o namespace inteiro e pelo decorator nas
   views.
2. **Grupos** — dentro do módulo, decidem quem escreve:

   - ``VIAGENS_GESTOR`` — administra tudo, inclusive a **tabela de diárias**.
   - ``VIAGENS_OPERADOR`` — mantém servidores, viaturas e catálogos de apoio,
     mas não toca em valor de diária.
   - quem tem o módulo e nenhum dos dois grupos **consulta**, sem escrever.

A tabela de diárias é dinheiro que vai para documento oficial e prestação de
contas; por isso é a única superfície restrita ao gestor. Administrador do
sistema e superusuário passam por tudo.
"""

from accounts.modulos import modulo_requerido, usuario_tem_modulo
from solicitacoes.permissions import eh_administrador

CODIGO_MODULO = "VIAGENS"

GRUPO_GESTOR = "VIAGENS_GESTOR"
GRUPO_OPERADOR = "VIAGENS_OPERADOR"


def acesso_ao_modulo(view):
    """Decorator das views do módulo: login + módulo ``VIAGENS``."""
    return modulo_requerido(CODIGO_MODULO)(view)


def pode_acessar(usuario):
    return usuario_tem_modulo(usuario, CODIGO_MODULO)


def _em_grupo(usuario, *grupos):
    if not usuario or not usuario.is_authenticated:
        return False
    if usuario.is_superuser:
        return True
    return usuario.groups.filter(name__in=grupos).exists()


def eh_gestor_viagens(usuario):
    return _em_grupo(usuario, GRUPO_GESTOR) or eh_administrador(usuario)


def pode_editar_cadastros(usuario):
    """Servidores, viaturas, unidades, cargos e combustíveis."""
    return _em_grupo(usuario, GRUPO_GESTOR, GRUPO_OPERADOR) or eh_administrador(usuario)


def pode_editar_diarias(usuario):
    """Valores de diária — só gestor, porque é dinheiro."""
    return eh_gestor_viagens(usuario)
