import re

from django import forms
from django.db import transaction
from django.utils import timezone
from core.utils.masks import normalize_protocolo
from core.normalizers import normalize_plate, normalize_spaces
from .models import Oficio, Justificativa, ModeloMotivoOficio, ModeloJustificativa, ConfiguracaoNumeracaoOficio


REFERENCIA_OFICIO = re.compile(r"^\s*(\d{1,6})\s*(?:/\s*(\d{4}))?\s*$")


class OficioForm(forms.ModelForm):
    """Dados e viajantes do cadastro de ofício, com os campos do Gerenciador de Viagens.

    Identificação (número, data, protocolo, custeio e nome da instituição),
    finalidade (modelo de motivo e descrição), equipe com termo e motorista,
    viatura e o cartão do motorista quando ele não é da equipe. O que a
    origem não mostra nesta tela (assunto, unidade solicitante, viatura
    não cadastrada, porte de armas, documentos do motorista externo) fica fora
    do formulário: o valor gravado é preservado.
    """

    modelo_motivo = forms.ModelChoiceField(queryset=ModeloMotivoOficio.objects.all(), required=False, label='Modelo de motivo')

    class Meta:
        model = Oficio
        labels = {
            'numero': 'N° do Ofício', 'data_criacao': 'Data do ofício', 'protocolo': 'Protocolo', 'custeio': 'Custeio',
            'custeio_observacao': 'Nome da Instituição', 'motivo': 'Descrição',
            'servidores': 'Servidores', 'viatura': 'Viatura',
            'motorista': 'Buscar motorista no sistema', 'motorista_manual_nome': 'Nome completo',
            'motorista_oficio_referencia': 'N° do Ofício', 'motorista_protocolo_ref': 'Protocolo',
        }
        fields = ['numero', 'data_criacao', 'protocolo', 'custeio', 'custeio_observacao', 'modelo_motivo', 'motivo',
                  'servidores', 'servidores_termo_autorizacao', 'viatura',
                  'motorista_modo', 'motorista', 'motorista_manual_nome',
                  'motorista_oficio_referencia', 'motorista_protocolo_ref']

    def __init__(self, *args, unidade_emissora=None, **kwargs):
        # Quem é lotado na unidade que emite o ofício não precisa de termo de autorização.
        self.unidade_emissora = unidade_emissora
        super().__init__(*args, **kwargs)
        self._servidores_anteriores = set(self.instance.servidores.values_list('pk', flat=True)) if self.instance.pk else None
        for nome in ('numero', 'data_criacao', 'protocolo', 'motivo', 'custeio', 'servidores', 'servidores_termo_autorizacao',
                     'viatura', 'motorista', 'motorista_modo'):
            self.fields[nome].required = False
        self.fields['modelo_motivo'].queryset = ModeloMotivoOficio.objects.order_by('nome')
        if not self.is_bound:
            motivo = (self.instance.motivo or '').strip()
            modelos = self.fields['modelo_motivo'].queryset
            if not motivo:
                padrao = modelos.filter(is_padrao=True).first()
                if padrao:
                    self.initial.update(modelo_motivo=padrao.pk, motivo=padrao.texto)
            else:
                correspondente = modelos.filter(texto=motivo).first()
                if correspondente:
                    self.initial['modelo_motivo'] = correspondente.pk
            # Sem termo escolhido ainda, a origem marca toda a equipe — menos quem é da unidade emissora.
            if self.instance.pk and not self.instance.servidores_termo_autorizacao.exists():
                self.initial['servidores_termo_autorizacao'] = [
                    s.pk for s in self.instance.servidores.all() if self.precisa_de_termo(s)
                ]
            if self.instance.motorista_oficio_referencia:
                self.initial['motorista_oficio_referencia'] = self.instance.motorista_oficio_referencia.split('/')[0]

    def precisa_de_termo(self, servidor):
        return not (self.unidade_emissora and servidor.unidade_id == self.unidade_emissora)

    @property
    def ano(self):
        return self.instance.ano or timezone.localdate().year

    def clean_numero(self):
        """Em branco, mantém o número já reservado."""
        numero = self.cleaned_data.get('numero')
        if numero is None:
            return self.instance.numero
        if numero < 1:
            raise forms.ValidationError('Informe um número de ofício válido (maior que zero).')
        conflito = Oficio.objects.filter(ano=self.ano, numero=numero).exclude(pk=self.instance.pk)
        if conflito.exists():
            raise forms.ValidationError(f'Já existe um ofício com o número {numero} em {self.ano}.')
        return numero

    def clean_data_criacao(self):
        """Em branco, mantém a data já gravada."""
        return self.cleaned_data.get('data_criacao') or self.instance.data_criacao or timezone.localdate()

    def clean_protocolo(self):
        valor = normalize_protocolo(self.cleaned_data.get('protocolo'))
        if valor and len(valor) != 9:
            raise forms.ValidationError('Informe um protocolo válido com 9 dígitos.')
        return valor

    def clean_custeio(self):
        return self.cleaned_data.get('custeio') or Oficio.CUSTEIO_UNIDADE_DPC

    def clean_custeio_observacao(self):
        return normalize_spaces(self.cleaned_data.get('custeio_observacao'))

    def clean_motivo(self):
        return normalize_spaces(self.cleaned_data.get('motivo'))

    def clean_motorista_modo(self):
        return self.cleaned_data.get('motorista_modo') or Oficio.MOTORISTA_MODO_SERVIDOR

    def clean_motorista_oficio_referencia(self):
        """"15" vira "15/<ano do ofício>", como o campo de número da origem."""
        bruto = (self.cleaned_data.get('motorista_oficio_referencia') or '').strip()
        if not bruto:
            return ''
        encontrado = REFERENCIA_OFICIO.match(bruto)
        if encontrado:
            return f"{int(encontrado.group(1))}/{encontrado.group(2) or self.ano}"
        return bruto[:self.fields['motorista_oficio_referencia'].max_length]

    def clean_motorista_protocolo_ref(self):
        return normalize_protocolo(self.cleaned_data.get('motorista_protocolo_ref'))

    def clean(self):
        cd = super().clean()
        servidores = list(cd.get('servidores') or [])
        viajantes = {s.pk for s in servidores}
        termos = list(cd.get('servidores_termo_autorizacao') or [])
        # Sem o campo-sentinela, "desmarquei todos os termos" e "não enviei" chegam iguais.
        if self.is_bound and 'servidores_termo_autorizacao_present' not in self.data:
            termos = servidores
        cd['servidores_termo_autorizacao'] = [s for s in termos if s.pk in viajantes]
        if cd.get('motorista_modo') == Oficio.MOTORISTA_MODO_MANUAL:
            cd['motorista'] = None
            cd['motorista_manual_nome'] = normalize_spaces(cd.get('motorista_manual_nome')).upper()
        else:
            cd['motorista_manual_nome'] = ''
            if cd.get('motorista') and cd['motorista'].pk in viajantes:
                cd['motorista_oficio_referencia'] = ''
                cd['motorista_protocolo_ref'] = ''
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


class OficioDocumentoForm(forms.ModelForm):
    """Todos os campos do ofício que o documento mostra — o formulário do
    editor documental (`documentos.editor.vinculos`), que edita o ofício pela
    prévia A4. O cadastro usa `OficioForm`, só com os campos da origem."""

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
