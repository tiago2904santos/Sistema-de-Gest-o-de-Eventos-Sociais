from django import forms
from cadastros.models import Estado, Municipio
from .models import TermoAutorizacao
from viagens_oficios.roteiro_context import periodo_roteiro


class TermoAutorizacaoForm(forms.ModelForm):
    class Meta:
        model = TermoAutorizacao
        fields = ['oficio', 'destino_estado', 'destino_cidade',
                  'data_evento_inicio', 'data_evento_fim', 'servidores', 'viatura']
        labels = {'data_evento_inicio': 'Data inicial', 'data_evento_fim': 'Data final',
                  'destino_cidade': 'Município do destino'}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['oficio'].queryset = self.fields['oficio'].queryset.filter(cancelado=False)
        if not self.is_bound and self.instance.destino_cidade_id:
            self.initial['destino_estado'] = self.instance.destino_cidade.estado_id
        extras = self.instance.destinos_extras or []
        # Quantos pares de destino adicional a tela tem. Sem linha de sobra: ao
        # abrir, só os destinos que o termo já tem — quem quiser outro usa o "+".
        enviado = str(self.data.get('quantidade_destinos', '')) if self.is_bound else ''
        solicitado = min(100, int(enviado)) if enviado.isdigit() else 0
        self.quantidade_destinos = max(len(extras), solicitado)
        if self.is_bound and self.data.get('acao') == 'adicionar_destino':
            self.quantidade_destinos = min(100, self.quantidade_destinos + 1)
        for i in range(self.quantidade_destinos):
            extra = extras[i] if i < len(extras) else {}
            self.fields[f'extra_estado_{i}'] = forms.ModelChoiceField(Estado.objects.all(), required=False, label=f'Estado adicional {i+1}', initial=extra.get('estado_id'))
            self.fields[f'extra_cidade_{i}'] = forms.ModelChoiceField(Municipio.objects.all(), required=False, label=f'Município adicional {i+1}', initial=extra.get('cidade_id'))

    def clean(self):
        cd = super().clean()
        cidade, estado = cd.get('destino_cidade'), cd.get('destino_estado')
        if cidade and (not estado or cidade.estado_id != estado.pk):
            self.add_error('destino_cidade', 'Escolha um município do estado selecionado.')
        oficio = cd.get('oficio')
        roteiro = oficio.roteiro if oficio and oficio.roteiro_id else None
        if estado and not cidade:
            self.add_error('destino_cidade', 'Informe o município do destino.')
        if not cidade and not (roteiro and roteiro.destinos.exists()):
            self.add_error('destino_cidade', 'Informe o destino ou selecione um ofício com roteiro.')
        inicio, fim = cd.get('data_evento_inicio'), cd.get('data_evento_fim')
        if inicio and fim and fim < inicio:
            self.add_error('data_evento_fim', 'A data final não pode ser anterior à inicial.')
        if not inicio and not periodo_roteiro(roteiro)[0]:
            self.add_error('data_evento_inicio', 'Informe a data ou selecione um ofício com período.')
        if inicio and not fim:
            cd['data_evento_fim'] = inicio
        self.destinos_adicionais = []
        for name in self.fields:
            if not name.startswith('extra_cidade_'):
                continue
            c = cd.get(name)
            e = cd.get(name.replace('cidade', 'estado'))
            if e and not c:
                self.add_error(name, 'Selecione o município adicional.')
            elif c and (not e or c.estado_id != e.pk):
                self.add_error(name, 'Selecione um município do estado informado.')
            elif c:
                self.destinos_adicionais.append({'cidade_id': c.pk, 'estado_id': e.pk, 'cidade': c.nome, 'estado': e.sigla})
        return cd

    def save(self, commit=True):
        obj = super().save(commit=False)
        obj.destinos_extras = self.destinos_adicionais
        if commit:
            obj.save()
            self.save_m2m()
        return obj
