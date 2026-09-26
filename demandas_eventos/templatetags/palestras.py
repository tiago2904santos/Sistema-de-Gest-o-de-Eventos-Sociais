from django import template

from ..permissions import pode_ver

register = template.Library()


@register.filter
def palestra_visivel_para(demanda, usuario):
    """Se o usuário enxerga a palestra (a solicitação só põe o link quando abre)."""
    return bool(demanda) and pode_ver(usuario, demanda)
