from datetime import date, datetime
from django import forms
from core.listagens import campos_formulario, opcoes_choices


def campos_v32(form):
    """Completa o descritor comum com datas ISO, múltiplos e dependências."""
    campos = campos_formulario(form)
    for item in campos:
        nome = item['name']
        campo = form.fields[nome]
        valor = form[nome].value()
        item['name'] = form[nome].html_name
        item['label'] = form[nome].label
        if isinstance(campo, forms.ModelMultipleChoiceField):
            item.update(tipo='select', multiplo=True, marcados=[str(v) for v in (valor or [])])
        elif isinstance(campo, forms.ChoiceField) and not isinstance(campo, forms.ModelChoiceField):
            item.update(tipo='select', opcoes=opcoes_choices(campo.choices))
        elif isinstance(campo, forms.DateField):
            item.update(tipo='date', valor=valor.isoformat() if isinstance(valor, (date, datetime)) else valor or '')
        elif isinstance(campo, (forms.IntegerField, forms.DecimalField)):
            item['input_tipo'] = 'number'
        if isinstance(campo, forms.ModelChoiceField) and campo.queryset.model._meta.label == 'cadastros.Municipio':
            item['opcoes'] = [{'valor': str(o.pk), 'rotulo': str(o), 'estado': str(o.estado_id)} for o in campo.queryset.select_related('estado')]
            if nome == 'destino_cidade':
                item['dependente_de'] = 'id_destino_estado'
            elif nome == 'cidade_sede_padrao':
                item['dependente_de'] = 'id_sede_estado'
            elif nome.startswith('extra_cidade_'):
                item['dependente_de'] = 'id_' + nome.replace('cidade', 'estado')
    return campos


def secoes_oficio(form, justificativa):
    campos = {c['name']: c for c in campos_v32(form)}
    grupos = [
        ('viajantes', 'Viajantes e solicitação', ['data_criacao', 'protocolo', 'assunto', 'solicitante', 'modelo_motivo', 'motivo', 'custeio', 'custeio_observacao', 'servidores', 'servidores_termo_autorizacao']),
        ('transporte', 'Transporte', [n for n in campos if n.startswith(('motorista', 'transporte')) or n in ['viatura', 'porte_transporte_armas']]),
        ('roteiro', 'Roteiro e diárias', ['roteiro']),
    ]
    return [{'id': id_, 'titulo': titulo, 'campos': [campos[n] for n in nomes]} for id_, titulo, nomes in grupos] + [{'id': 'justificativa', 'titulo': 'Justificativa', 'campos': campos_v32(justificativa)}]
