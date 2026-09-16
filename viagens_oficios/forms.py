from django import forms
from django.db import transaction
from core.utils.masks import normalize_protocolo
from core.normalizers import normalize_plate, normalize_spaces
from .models import Oficio, Justificativa, ModeloMotivoOficio, ModeloJustificativa, ConfiguracaoNumeracaoOficio


class OficioForm(forms.ModelForm):
    modelo_motivo = forms.ModelChoiceField(queryset=ModeloMotivoOficio.objects.all(), required=False, label='Modelo de motivo')

    class Meta:
        model = Oficio
        labels = {
            'data_criacao': 'Data do ofício', 'modelo_motivo': 'Modelo de motivo',
            'solicitante': 'Unidade solicitante', 'servidores': 'Viajantes',
            'custeio_observacao': 'Observação do custeio', 'motorista_modo': 'Identificação do motorista',
            'motorista_manual_nome': 'Nome do motorista externo', 'motorista_manual_rg': 'RG do motorista externo',
            'motorista_manual_cpf': 'CPF do motorista externo', 'motorista_manual_cargo': 'Cargo do motorista externo',
            'motorista_manual_unidade': 'Unidade do motorista externo', 'motorista_manual_observacao': 'Observação sobre o motorista',
            'transporte_placa_manual': 'Placa da viatura não cadastrada',
            'transporte_modelo_manual': 'Modelo da viatura não cadastrada',
            'transporte_combustivel_manual': 'Combustível da viatura não cadastrada',
            'transporte_tipo_manual': 'Tipo da viatura não cadastrada',
        }
        fields = ['data_criacao', 'protocolo', 'assunto', 'modelo_motivo', 'motivo', 'solicitante',
                  'custeio', 'custeio_observacao', 'servidores', 'servidores_termo_autorizacao',
                  'viatura', 'motorista_modo', 'motorista', 'motorista_manual_nome',
                  'motorista_manual_rg', 'motorista_manual_cpf', 'motorista_manual_cargo',
                  'motorista_manual_unidade', 'motorista_manual_observacao',
                  'motorista_oficio_referencia', 'motorista_protocolo_ref',
                  'transporte_placa_manual', 'transporte_modelo_manual',
                  'transporte_combustivel_manual', 'transporte_tipo_manual',
                  'porte_transporte_armas', 'roteiro']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._servidores_anteriores = set(self.instance.servidores.values_list('pk', flat=True)) if self.instance.pk else None
        self.fields['roteiro'].queryset = self.fields['roteiro'].queryset.filter(cancelado=False).prefetch_related('destinos__municipio')
        if not self.is_bound and not self.instance.motivo:
            padrao = ModeloMotivoOficio.objects.filter(is_padrao=True).first()
            if padrao:
                self.initial.update(modelo_motivo=padrao.pk, motivo=padrao.texto)
        # Combustível padrão já escolhido para a viatura não cadastrada.
        if not self.is_bound and not self.instance.transporte_combustivel_manual_id:
            from viagens_cadastros.models import Combustivel
            combustivel = Combustivel.objects.filter(is_padrao=True).first()
            if combustivel:
                self.initial.setdefault('transporte_combustivel_manual', combustivel.pk)

    def clean_protocolo(self):
        valor = normalize_protocolo(self.cleaned_data.get('protocolo'))
        if valor and len(valor) != 9:
            raise forms.ValidationError('Informe um protocolo válido com 9 dígitos.')
        return valor

    def clean_motorista_protocolo_ref(self):
        return normalize_protocolo(self.cleaned_data.get('motorista_protocolo_ref'))

    def clean_transporte_placa_manual(self):
        valor = normalize_plate(self.cleaned_data.get('transporte_placa_manual'))
        if valor and len(valor) != 7:
            raise forms.ValidationError('Use o formato de placa Mercosul ou antiga (7 caracteres).')
        return valor

    def clean(self):
        cd = super().clean()
        viajantes = set(s.pk for s in cd.get('servidores', []))
        cd['servidores_termo_autorizacao'] = [s for s in cd.get('servidores_termo_autorizacao', []) if s.pk in viajantes]
        if cd.get('motorista_modo') == Oficio.MOTORISTA_MODO_MANUAL:
            cd['motorista'] = None
        else:
            cd['motorista_manual_nome'] = ''
            if cd.get('motorista') and cd['motorista'].pk in viajantes:
                cd['motorista_oficio_referencia'] = ''
                cd['motorista_protocolo_ref'] = ''
        # Viatura cadastrada e viatura manual são alternativas: escolher uma
        # do cadastro apaga o que sobrou digitado no cartão da não cadastrada.
        if cd.get('viatura'):
            cd['transporte_placa_manual'] = ''
            cd['transporte_modelo_manual'] = ''
            cd['transporte_combustivel_manual'] = None
            cd['transporte_tipo_manual'] = ''
        if cd.get('custeio') == Oficio.CUSTEIO_OUTRA_INSTITUICAO and not (cd.get('custeio_observacao') or '').strip():
            self.add_error('custeio_observacao', 'Informe a observação de custeio quando o custeio é de outra instituição.')
        cd['motivo'] = normalize_spaces(cd.get('motivo'))
        return cd

    @transaction.atomic
    def save(self, commit=True):
        obj = super().save(commit=False)
        selecionados = {s.pk for s in self.cleaned_data.get('servidores', [])}
        if self._servidores_anteriores != selecionados or obj.diarias_quantidade_servidores is None:
            obj.diarias_quantidade_servidores = len(selecionados)
        if commit:
            obj.save()
            self.save_m2m()
        return obj


class JustificativaForm(forms.ModelForm):
    class Meta:
        model = Justificativa
        fields = ['modelo', 'texto']

    def __init__(self, *args, obrigatoria=False, **kwargs):
        super().__init__(*args, **kwargs)
        self._obrigatoria = obrigatoria
        self.fields['modelo'].queryset = ModeloJustificativa.objects.all()
        if not self.is_bound and not self.instance.texto:
            padrao = self.fields['modelo'].queryset.filter(is_padrao=True).first()
            if padrao:
                self.initial.update(modelo=padrao.pk, texto=padrao.texto)

    def clean_texto(self):
        texto = (self.cleaned_data.get('texto') or '').strip()
        if self._obrigatoria and not texto:
            raise forms.ValidationError('Informe o texto da justificativa.')
        return texto


class JustificativaCadastroForm(forms.Form):
    """Cadastro e edição de uma justificativa, no modal da lista.

    Nova: escolhe-se o ofício entre os que ainda não têm texto. Edição: o
    ofício é o da justificativa e não muda; só modelo e texto.
    """

    oficio = forms.ModelChoiceField(queryset=Oficio.objects.none(), label='Ofício',
                                    error_messages={'required': 'Escolha o ofício.',
                                                    'invalid_choice': 'Escolha um ofício sem justificativa.'})
    modelo = forms.ModelChoiceField(queryset=ModeloJustificativa.objects.none(), required=False, label='Modelo de justificativa')
    texto = forms.CharField(label='Justificativa', widget=forms.Textarea(attrs={'rows': 6}),
                            error_messages={'required': 'Informe o texto da justificativa.'})

    def __init__(self, *args, justificativa=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.justificativa = justificativa
        self.fields['modelo'].queryset = ModeloJustificativa.objects.order_by('nome')
        if justificativa is not None:
            del self.fields['oficio']
            if not self.is_bound:
                self.initial.update(modelo=justificativa.modelo_id, texto=justificativa.texto)
        else:
            # Nova: o modelo padrão já vem escolhido, com o texto dele.
            padrao = self.fields['modelo'].queryset.filter(is_padrao=True).first()
            if padrao and not self.is_bound:
                self.initial.update(modelo=padrao.pk, texto=padrao.texto)
            self.fields['oficio'].queryset = (
                Oficio.objects.filter(cancelado=False)
                .exclude(justificativa__texto__gt='')
                .select_related('roteiro')
                .prefetch_related('roteiro__destinos__municipio__estado', 'roteiro__trechos')
                .order_by('-ano', '-numero', '-pk')
            )

    def clean_texto(self):
        texto = normalize_spaces(self.cleaned_data.get('texto') or '')
        if not texto:
            raise forms.ValidationError('Informe o texto da justificativa.')
        return texto


class ModeloMotivoOficioForm(forms.ModelForm):
    def _get_validation_exclusions(self):
        # A troca de padrão é validada e gravada pelo save do catálogo.
        return super()._get_validation_exclusions() | {'is_padrao'}

    class Meta:
        model = ModeloMotivoOficio
        fields = ['nome', 'texto', 'is_padrao']
        labels = {'nome': 'Nome do modelo', 'texto': 'Texto', 'is_padrao': 'Usar como padrão'}
        help_texts = {
            'is_padrao': 'Será sugerido automaticamente nos ofícios novos.',
        }
        widgets = {
            'nome': forms.TextInput(attrs={'placeholder': 'Ex.: COBERTURA JORNALÍSTICA', 'data-uppercase': 'true'}),
            'texto': forms.Textarea(attrs={'rows': 5, 'placeholder': 'Texto que vai para o ofício ao escolher este modelo'}),
        }


class ModeloJustificativaForm(ModeloMotivoOficioForm):
    class Meta(ModeloMotivoOficioForm.Meta):
        model = ModeloJustificativa


class NumeracaoForm(forms.ModelForm):
    class Meta:
        model = ConfiguracaoNumeracaoOficio
        fields = ['ano', 'numero_inicial']
        labels = {'numero_inicial': 'Número inicial'}

    def clean_numero_inicial(self):
        valor = self.cleaned_data['numero_inicial']
        if valor < 1:
            raise forms.ValidationError('O piso deve ser maior que zero.')
        return valor
