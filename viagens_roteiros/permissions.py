"""Política de acesso dos roteiros.

Mesma porta dos cadastros de viagens: o módulo ``VIAGENS`` decide quem enxerga
as telas, e os grupos decidem quem escreve. Roteiro é trabalho operacional —
gestor e operador montam e calculam; quem só tem o módulo consulta.

O valor das diárias continua restrito ao gestor lá no cadastro da vigência:
aqui ninguém digita valor, o cálculo é que os aplica.
"""

from viagens_cadastros.permissions import (  # noqa: F401  (a porta é a mesma)
    acesso_ao_modulo,
    pode_editar_cadastros,
)


def pode_editar_roteiros(usuario):
    """Quem monta e calcula roteiros: operador, gestor ou administrador."""
    return pode_editar_cadastros(usuario)
