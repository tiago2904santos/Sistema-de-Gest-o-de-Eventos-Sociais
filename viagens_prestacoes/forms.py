import re
from pathlib import Path
from django import forms
from django.forms import modelformset_factory
from django.forms.renderers import TemplatesSetting
from viagens_cadastros.models import Servidor
from viagens_cadastros.models import Viatura
from core.normalizers import normalize_spaces
from core.uploads import validate_private_document_upload
from core.utils.masks import normalize_protocolo
from .models import DiarioBordo
from .models import DiarioBordoTrecho
from .models import ModeloTextoRelatorioTecnico
from .models import PrestacaoContas
from .models import PrestacaoDocumentoAnexo
from .models import PrestacaoServidor
from .models import RelatorioTecnico
ABASTECIMENTO_CHOICES = [('sim', 'Sim'), ('nao', 'Não')]

class DiarioBordoTrechoForm(forms.ModelForm):
    """KM inicial/final e necessidade de abastecimento de um trecho do diário."""
    abastecimento = forms.ChoiceField(label='Necessidade de abastecimento', choices=ABASTECIMENTO_CHOICES, required=False, widget=forms.Select())
    km_inicial = forms.CharField(required=False, widget=forms.TextInput(attrs={**{'class': 'campo__input'}, 'inputmode': 'numeric', 'placeholder': '0', 'autocomplete': 'off', 'data-mask': 'milhar'}))
    km_final = forms.CharField(required=False, widget=forms.TextInput(attrs={**{'class': 'campo__input'}, 'inputmode': 'numeric', 'placeholder': '0', 'autocomplete': 'off', 'data-mask': 'milhar'}))

    class Meta:
        model = DiarioBordoTrecho
        fields = ['km_inicial', 'km_final', 'abastecimento']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not self.is_bound:
            valor = getattr(self.instance, 'abastecimento', None)
            self.initial['abastecimento'] = 'nao' if valor is False else 'sim'

    def clean_abastecimento(self):
        return self.cleaned_data.get('abastecimento') != 'nao'

    def _parse_km(self, campo):
        digitos = re.sub('\\D', '', str(self.cleaned_data.get(campo) or ''))
        return int(digitos) if digitos else None

    def clean_km_inicial(self):
        return self._parse_km('km_inicial')

    def clean_km_final(self):
        return self._parse_km('km_final')
DiarioBordoTrechoFormSet = modelformset_factory(DiarioBordoTrecho, form=DiarioBordoTrechoForm, extra=0, can_delete=False)

class DiarioMotoristaForm(forms.ModelForm):
    """Troca o motorista apenas deste diário — o ofício original não é alterado.

    Três modos: manter o do ofício, escolher outro servidor do mesmo ofício ou
    informar um motorista de outro ofício (nome/CPF + nº do ofício e protocolo).
    """
    motorista_manual_cpf = forms.CharField(required=False, max_length=14, widget=forms.TextInput(attrs={**{'class': 'campo__input'}, 'placeholder': '000.000.000-00', 'autocomplete': 'off', 'inputmode': 'numeric', 'data-mask': 'cpf'}))
    motorista_protocolo_ref = forms.CharField(required=False, max_length=30, widget=forms.TextInput(attrs={**{'class': 'campo__input'}, 'placeholder': '00.000.000-0', 'autocomplete': 'off', 'inputmode': 'numeric', 'data-mask': 'protocolo'}))
    viatura_manual_placa = forms.CharField(required=False, max_length=8, widget=forms.TextInput(attrs={**{'class': 'campo__input'}, 'placeholder': 'ABC-1D23', 'autocomplete': 'off', 'data-mask': 'placa'}))

    class Meta:
        model = DiarioBordo
        fields = ['motorista_modo', 'motorista_servidor', 'motorista_manual_nome', 'motorista_manual_cpf', 'motorista_oficio_referencia', 'motorista_protocolo_ref', 'viatura_modo', 'viatura', 'viatura_manual_modelo', 'viatura_manual_placa', 'viatura_manual_tipo', 'viatura_manual_combustivel']
        widgets = {'motorista_modo': forms.RadioSelect(), 'motorista_manual_nome': forms.TextInput(attrs={**{'class': 'campo__input'}, 'placeholder': 'Nome do motorista', 'autocomplete': 'off'}), 'motorista_oficio_referencia': forms.TextInput(attrs={**{'class': 'campo__input'}, 'placeholder': '15/2026', 'autocomplete': 'off'}), 'viatura_modo': forms.RadioSelect(), 'viatura_manual_modelo': forms.TextInput(attrs={**{'class': 'campo__input'}, 'placeholder': 'Ex.: Onix', 'autocomplete': 'off'}), 'viatura_manual_combustivel': forms.TextInput(attrs={**{'class': 'campo__input'}, 'placeholder': 'Ex.: Gasolina', 'autocomplete': 'off'})}

    def __init__(self, *args, oficio=None, **kwargs):
        super().__init__(*args, **kwargs)
        self._oficio = oficio
        if oficio is not None:
            servidores = oficio.servidores.select_related('cargo', 'unidade').order_by('nome')
        else:
            servidores = Servidor.objects.none()
        servidor_field = self.fields['motorista_servidor']
        servidor_field.queryset = servidores
        servidor_field.required = False
        servidor_field.empty_label = 'Selecione um servidor'
        servidor_field.widget.attrs.update({'class': 'campo__input'})
        self.fields['motorista_modo'].required = False
        viatura_field = self.fields['viatura']
        viatura_field.queryset = Viatura.objects.select_related('combustivel').order_by('modelo', 'placa')
        viatura_field.required = False
        viatura_field.empty_label = 'Selecione uma viatura'
        viatura_field.widget.attrs.update({'class': 'campo__input'})
        tipo_field = self.fields['viatura_manual_tipo']
        tipo_field.required = False
        tipo_field.widget = forms.Select(choices=[('', 'Selecione')] + list(Viatura.Tipo.choices), attrs={**{'class': 'campo__input'}})
        self.fields['viatura_modo'].required = False

    def clean_motorista_manual_cpf(self):
        return re.sub('\\D', '', self.cleaned_data.get('motorista_manual_cpf') or '')[:11]

    def clean_motorista_protocolo_ref(self):
        return normalize_protocolo(self.cleaned_data.get('motorista_protocolo_ref') or '')

    def clean_motorista_oficio_referencia(self):
        return (self.cleaned_data.get('motorista_oficio_referencia') or '').strip()[:16]

    def clean_motorista_manual_nome(self):
        return normalize_spaces(self.cleaned_data.get('motorista_manual_nome') or '')

    def clean_viatura_manual_placa(self):
        return re.sub('[^A-Za-z0-9]', '', self.cleaned_data.get('viatura_manual_placa') or '').upper()[:8]

    def clean_viatura_manual_modelo(self):
        return normalize_spaces(self.cleaned_data.get('viatura_manual_modelo') or '')

    def clean_viatura_manual_combustivel(self):
        return normalize_spaces(self.cleaned_data.get('viatura_manual_combustivel') or '')

    def clean(self):
        cleaned = super().clean()
        modo = cleaned.get('motorista_modo') or DiarioBordo.MOTORISTA_MODO_OFICIO
        cleaned['motorista_modo'] = modo
        if modo == DiarioBordo.MOTORISTA_MODO_SERVIDOR:
            if not cleaned.get('motorista_servidor'):
                self.add_error('motorista_servidor', 'Selecione um servidor do ofício.')
        elif modo == DiarioBordo.MOTORISTA_MODO_OUTRO:
            if not cleaned.get('motorista_manual_nome'):
                self.add_error('motorista_manual_nome', 'Informe o nome do motorista.')
        viatura_modo = cleaned.get('viatura_modo') or DiarioBordo.VIATURA_MODO_OFICIO
        cleaned['viatura_modo'] = viatura_modo
        if viatura_modo == DiarioBordo.VIATURA_MODO_BANCO:
            if not cleaned.get('viatura'):
                self.add_error('viatura', 'Selecione uma viatura do cadastro.')
        elif viatura_modo == DiarioBordo.VIATURA_MODO_MANUAL:
            if not cleaned.get('viatura_manual_modelo'):
                self.add_error('viatura_manual_modelo', 'Informe o modelo da viatura.')
        return cleaned

    def save(self, commit=True):
        diario = super().save(commit=False)
        modo = self.cleaned_data.get('motorista_modo') or DiarioBordo.MOTORISTA_MODO_OFICIO
        diario.motorista_modo = modo
        if modo == DiarioBordo.MOTORISTA_MODO_SERVIDOR:
            diario.motorista_manual_nome = ''
            diario.motorista_manual_cpf = ''
            diario.motorista_oficio_referencia = ''
            diario.motorista_protocolo_ref = ''
        elif modo == DiarioBordo.MOTORISTA_MODO_OUTRO:
            diario.motorista_servidor = None
        else:
            diario.motorista_servidor = None
            diario.motorista_manual_nome = ''
            diario.motorista_manual_cpf = ''
            diario.motorista_oficio_referencia = ''
            diario.motorista_protocolo_ref = ''
        viatura_modo = self.cleaned_data.get('viatura_modo') or DiarioBordo.VIATURA_MODO_OFICIO
        diario.viatura_modo = viatura_modo
        if viatura_modo == DiarioBordo.VIATURA_MODO_BANCO:
            diario.viatura_manual_modelo = ''
            diario.viatura_manual_placa = ''
            diario.viatura_manual_tipo = ''
            diario.viatura_manual_combustivel = ''
        elif viatura_modo == DiarioBordo.VIATURA_MODO_MANUAL:
            diario.viatura = None
        else:
            diario.viatura = None
            diario.viatura_manual_modelo = ''
            diario.viatura_manual_placa = ''
            diario.viatura_manual_tipo = ''
            diario.viatura_manual_combustivel = ''
        if commit:
            diario.save()
        return diario
CAMPOS_COM_MODELO = [('motivo', 'Descrição do evento'), ('atividade', 'Objetivo da participação'), ('conclusao', 'Conclusão'), ('medidas', 'Medidas a serem adotadas pelo órgão'), ('info_complementares', 'Informações complementares')]
OUTRO_VALUE = '__outro__'
CAMPOS_CUSTEIO_COM_OUTRO = [('translado', 'Translado'), ('combustivel', 'Combustível'), ('passagem', 'Passagem')]
CUSTEIO_CHOICES = [('', 'Selecione'), ('Não houve', 'Não houve'), ('Houve', 'Houve'), ('Cartão Prime', 'Cartão Prime'), (OUTRO_VALUE, 'Outro')]
CUSTEIO_CHOICES_BY_FIELD = {'translado': [('Não houve', 'Não houve'), (OUTRO_VALUE, 'Outro')], 'combustivel': [('Cartão Prime', 'Cartão Prime'), (OUTRO_VALUE, 'Outro')], 'passagem': [('Não houve', 'Não houve'), (OUTRO_VALUE, 'Outro')]}
DEFAULT_CUSTEIO_VALUES = {'translado': 'Não houve', 'combustivel': 'Cartão Prime', 'passagem': 'Não houve'}
_CUSTEIO_VALORES_FIXOS = {campo: {value for value, _label in CUSTEIO_CHOICES_BY_FIELD.get(campo, CUSTEIO_CHOICES) if value and value != OUTRO_VALUE} for campo, _label in CAMPOS_CUSTEIO_COM_OUTRO}

def get_custeio_choices(campo):
    return CUSTEIO_CHOICES_BY_FIELD.get(campo, CUSTEIO_CHOICES)

def get_custeio_valores_fixos(campo):
    return _CUSTEIO_VALORES_FIXOS.get(campo, set())

class ModeloTextoSelect(forms.Select):
    """Select que injeta o texto do modelo em cada <option> via data-attr."""

    def create_option(self, name, value, label, selected, index, subindex=None, attrs=None):
        option = super().create_option(name, value, label, selected, index, subindex=subindex, attrs=attrs)
        modelo = getattr(value, 'instance', None)
        if modelo is not None:
            option['attrs']['data-texto-modelo'] = (modelo.texto or '').strip()
        return option

class PrestacaoMultipleFileInput(forms.FileInput):
    allow_multiple_selected = True
    template_name = 'django/forms/widgets/file.html'
    project_template_renderer = None

    def _render(self, template_name, context, renderer=None):
        return super()._render(template_name, context, self.project_template_renderer)

class PrestacaoMultipleFileField(forms.FileField):
    widget = PrestacaoMultipleFileInput

    def clean(self, data, initial=None):
        if not data:
            return []
        if isinstance(data, (list, tuple)):
            return [self._clean_um(item, initial) for item in data]
        return [self._clean_um(data, initial)]

    def _clean_um(self, item, initial):
        """Guarda o nome recebido antes de validar.

        `validate_private_document_upload` normaliza `uploaded_file.name` como efeito
        colateral (é o nome com que o arquivo vai para o disco). Quem lê o nome depois
        da validação recebe "Saque-Agosto.pdf" onde o usuário enviou "Saque Agosto.pdf"
        — e `nome_original` existe justamente para mostrar o que o usuário enviou.
        """
        nome_recebido = Path(getattr(item, 'name', '') or '').name
        limpo = super().clean(item, initial)
        if limpo is not None:
            limpo.nome_recebido = nome_recebido
        return limpo

def _nome_recebido(arquivo):
    """Nome como o usuário enviou, não o nome normalizado para o disco (ver `_clean_um`)."""
    guardado = getattr(arquivo, 'nome_recebido', None)
    return guardado or Path(getattr(arquivo, 'name', '') or '').name

def _anexo_multiple_file_field(label):
    return PrestacaoMultipleFileField(label=label, required=False, validators=[validate_private_document_upload], help_text='Anexe PDF, PNG, JPG ou JPEG.', widget=PrestacaoMultipleFileInput(attrs={**{'class': 'campo__input'}, 'accept': 'application/pdf,image/png,image/jpeg,image/*'}))

class PrestacaoDespachoForm(forms.ModelForm):
    """Despacho assinado do ofício — compartilhado por todos os servidores."""
    despacho_arquivos = _anexo_multiple_file_field('Despacho assinado do ofício')

    class Meta:
        model = PrestacaoContas
        fields = []

    def save(self, commit=True):
        prestacao = super().save(commit=commit)
        if commit:
            self.save_anexos(prestacao)
        return prestacao

    def save_anexos(self, prestacao):
        for arquivo in self.cleaned_data.get('despacho_arquivos') or []:
            PrestacaoDocumentoAnexo.objects.create(prestacao=prestacao, servidor_prestacao=None, tipo=PrestacaoDocumentoAnexo.TIPO_DESPACHO, arquivo=arquivo, nome_original=_nome_recebido(arquivo))

class PrestacaoServidorDocumentosForm(forms.ModelForm):
    """Dados individuais do servidor: número da solicitação + arquivos assinados.

    Cada servidor anexa o comprovante de saque/transferência e o relatório técnico
    assinado; quando o servidor é o motorista do ofício, anexa também o diário de
    bordo assinado.
    """
    comprovante_arquivos = _anexo_multiple_file_field('Comprovante de saque/transferência')
    rt_assinado_arquivos = _anexo_multiple_file_field('Relatório técnico assinado')
    diario_assinado_arquivos = _anexo_multiple_file_field('Diário de bordo assinado')

    class Meta:
        model = PrestacaoServidor
        fields = ['numero_solicitacao']
        labels = {'numero_solicitacao': 'Número da solicitação'}
        widgets = {'numero_solicitacao': forms.TextInput(attrs={**{'class': 'campo__input'}, 'placeholder': 'Informe o número da solicitação', 'autocomplete': 'off'})}

    def save(self, commit=True):
        servidor_prestacao = super().save(commit=commit)
        if commit:
            self.save_anexos(servidor_prestacao)
        return servidor_prestacao

    def _criar_anexos(self, servidor_prestacao, campo, tipo):
        for arquivo in self.cleaned_data.get(campo) or []:
            PrestacaoDocumentoAnexo.objects.create(prestacao=servidor_prestacao.prestacao, servidor_prestacao=servidor_prestacao, tipo=tipo, arquivo=arquivo, nome_original=_nome_recebido(arquivo))

    def save_anexos(self, servidor_prestacao):
        self._criar_anexos(servidor_prestacao, 'comprovante_arquivos', PrestacaoDocumentoAnexo.TIPO_COMPROVANTE)
        self._criar_anexos(servidor_prestacao, 'rt_assinado_arquivos', PrestacaoDocumentoAnexo.TIPO_RT_ASSINADO)
        if servidor_prestacao.is_motorista:
            self._criar_anexos(servidor_prestacao, 'diario_assinado_arquivos', PrestacaoDocumentoAnexo.TIPO_DB_ASSINADO)

class PrestacaoSolicitacaoForm(forms.ModelForm):

    class Meta:
        model = PrestacaoServidor
        fields = ['numero_solicitacao']
        labels = {'numero_solicitacao': 'Número da solicitação'}
        widgets = {'numero_solicitacao': forms.TextInput(attrs={**{'class': 'campo__input'}, 'placeholder': 'Número da solicitação', 'autocomplete': 'off'})}

class PrestacaoServidorDiariaForm(forms.Form):
    """Valor de diária efetivamente recebido por um servidor, usado só no RT dele.

    Deixou de ser ``ModelForm``: na tela é **um** campo de texto, no banco são
    dois (número e observação). Quem separa é ``aplicar_diaria_recebida`` — o
    mesmo serviço que o autosave usa, para que os dois caminhos de gravação não
    validem por regras diferentes.
    """
    diaria_valor_override = forms.CharField(label='Diária recebida por este servidor', required=False, help_text='Ex.: "R$ 87,00 (saque)". Preencha só quando o servidor recebeu valor diferente do liberado — no saque o caixa não entrega centavos. Nunca pode ser maior que o valor liberado.', widget=forms.TextInput(attrs={**{'class': 'campo__input'}, 'placeholder': 'Deixe em branco para usar o valor padrão acima', 'autocomplete': 'off'}))

    def __init__(self, *args, instance=None, **kwargs):
        from .services import diaria_recebida_display
        self.instance = instance
        if instance is not None and (not kwargs.get('initial')):
            kwargs['initial'] = {'diaria_valor_override': diaria_recebida_display(instance)}
        super().__init__(*args, **kwargs)

    def clean_diaria_valor_override(self):
        from .services import aplicar_diaria_recebida
        texto = self.cleaned_data.get('diaria_valor_override') or ''
        if self.instance is None:
            return texto
        problemas = aplicar_diaria_recebida(self.instance, texto)
        if problemas:
            raise forms.ValidationError(problemas)
        return texto

class RelatorioTecnicoForm(forms.ModelForm):
    translado_outro = forms.CharField(label='Translado - outro', required=False, widget=forms.TextInput(attrs={**{'class': 'campo__input'}, 'data-rt-other-input': 'translado'}))
    combustivel_outro = forms.CharField(label='Combustível - outro', required=False, widget=forms.TextInput(attrs={**{'class': 'campo__input'}, 'data-rt-other-input': 'combustivel'}))
    passagem_outro = forms.CharField(label='Passagem - outro', required=False, widget=forms.TextInput(attrs={**{'class': 'campo__input'}, 'data-rt-other-input': 'passagem'}))

    class Meta:
        model = RelatorioTecnico
        fields = ['diaria', 'translado', 'combustivel', 'passagem', 'motivo', 'atividade', 'conclusao', 'medidas', 'info_complementares']
        labels = {'diaria': 'Diária', 'translado': 'Translado', 'combustivel': 'Combustível', 'passagem': 'Passagem', 'motivo': 'Descrição do evento', 'atividade': 'Objetivo da participação', 'conclusao': 'Conclusão', 'medidas': 'Medidas a serem adotadas pelo órgão', 'info_complementares': 'Informações complementares'}
        help_texts = {'diaria': 'Ex.: "R$ 150,00" ou "não houve"', 'translado': 'Ex.: "R$ 45,00" ou "não houve"', 'combustivel': 'Ex.: "R$ 120,00" ou "não houve"', 'passagem': 'Ex.: "R$ 280,00" ou "não houve"'}

    def __init__(self, *args, relatorio=None, **kwargs):
        super().__init__(*args, **kwargs)
        self._relatorio = relatorio
        self.fields['diaria'].widget.attrs.update({'class': 'campo__input'})
        for campo, label in CAMPOS_CUSTEIO_COM_OUTRO:
            self.fields[campo] = forms.ChoiceField(label=label, choices=get_custeio_choices(campo), required=False, widget=forms.Select(attrs={**{'class': 'campo__input'}, 'data-rt-other-select': campo, 'data-rt-other-value': OUTRO_VALUE}))
            self.fields[f'{campo}_outro'].widget.attrs.setdefault('placeholder', f'Informe {label.lower()}')
            self._set_initial_custeio_value(campo)
        rows = {'motivo': 4, 'atividade': 4, 'conclusao': 4, 'medidas': 3, 'info_complementares': 3}
        for campo, _label in CAMPOS_COM_MODELO:
            self.fields[campo].required = False
            self.fields[campo].widget = forms.Textarea(attrs={**{'class': 'campo__input'}, 'rows': rows.get(campo, 4), 'data-rt-textarea': campo})
        for campo, label in CAMPOS_COM_MODELO:
            field_name = f'modelo_{campo}'
            field = forms.ModelChoiceField(label=f'Modelo de {label.lower()}', queryset=ModeloTextoRelatorioTecnico.objects.filter(campo=campo).order_by('ordem', 'nome'), required=False, empty_label='Selecione um modelo (opcional)', widget=ModeloTextoSelect(attrs={**{'class': 'campo__input'}, 'data-rt-modelo-select': 'true', 'data-rt-target': campo}))
            field.label_from_instance = lambda obj: obj.nome
            self.fields[field_name] = field

    def _set_initial_custeio_value(self, campo):
        if self.is_bound:
            return
        valor = normalize_spaces(self.initial.get(campo) or getattr(self.instance, campo, '') or '')
        if not valor:
            valor = DEFAULT_CUSTEIO_VALUES.get(campo, '')
        if not valor:
            return
        if valor in get_custeio_valores_fixos(campo):
            self.initial[campo] = valor
            return
        self.initial[campo] = OUTRO_VALUE
        self.initial[f'{campo}_outro'] = valor

    def clean(self):
        cleaned = super().clean()
        for campo, label in CAMPOS_CUSTEIO_COM_OUTRO:
            valor = cleaned.get(campo) or ''
            outro = normalize_spaces(cleaned.get(f'{campo}_outro') or '')
            if valor == OUTRO_VALUE:
                if not outro:
                    self.add_error(f'{campo}_outro', f'Informe o valor de {label.lower()}.')
                cleaned[campo] = outro
            else:
                cleaned[campo] = normalize_spaces(valor)
        return cleaned

class ModeloTextoRelatorioTecnicoForm(forms.ModelForm):
    campo = forms.ChoiceField(label='Campo do relatório', choices=ModeloTextoRelatorioTecnico.CAMPO_CHOICES, widget=forms.Select(attrs={**{'class': 'campo__input'}}))
    nome = forms.CharField(label='Nome', help_text='Use um nome curto para identificar o modelo.', widget=forms.TextInput(attrs={**{'class': 'campo__input'}}))
    texto = forms.CharField(label='Texto do modelo', help_text='Este texto será copiado para o campo do relatório e poderá ser editado antes de gerar.', widget=forms.Textarea(attrs={**{'class': 'campo__input'}, 'rows': 6}))

    class Meta:
        model = ModeloTextoRelatorioTecnico
        fields = ['campo', 'nome', 'texto']
