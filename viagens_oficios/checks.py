"""Contrato das rotas que substituem o wizard do GV no formulário V3.2."""
from django.core.checks import Error, Tags, register
from django.urls import NoReverseMatch, reverse


@register(Tags.urls)
def check_rotas_documentais(app_configs, **kwargs):
    errors = []
    for nome, args in [
        ('viagens_oficios:novo', []), ('viagens_oficios:editar', [1]),
        ('viagens_oficios:gerar', [1, 'oficio', 'pdf']),
        ('viagens_termos:novo', []), ('viagens_termos:preview', [1]),
    ]:
        try:
            reverse(nome, args=args)
        except NoReverseMatch:
            errors.append(Error(f'Rota documental não resolve: {nome}.', id='viagens_oficios.E001'))
    return errors
