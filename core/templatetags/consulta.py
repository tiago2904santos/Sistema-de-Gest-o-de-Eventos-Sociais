"""Reescrita de querystring para filtros, filas e paginação server-side.

A tag nativa `{% querystring %}` exige a chave literal; aqui o nome do
parâmetro vem de uma variável, o que permite um único componente de filtro
servir status, tipo e município.
"""

from django import template

register = template.Library()


@register.simple_tag(takes_context=True)
def qs_definir(context, nome, valor=None):
    """`?` + GET atual com `nome` definido (ou removido, se vazio) e sem página."""
    parametros = context["request"].GET.copy()
    parametros.pop("pagina", None)
    parametros.pop(nome, None)
    if valor not in (None, ""):
        parametros[nome] = str(valor)
    codificado = parametros.urlencode()
    return f"?{codificado}" if codificado else "?"
