"""Formulário da ordem de serviço — os campos de `ordens_servico/forms.py` da origem.

Os destinos seguem o mecanismo do termo: a primeira linha é `destino_estado` +
`destino_cidade` e as seguintes são `extra_estado_N` + `extra_cidade_N`, com
`quantidade_destinos` dizendo quantas linhas a tela tem. Os sete papéis fixos
(motorista, técnico, apoios...) continuam no formulário como campos ocultos:
as OS antigas os têm gravados e o documento ainda recorre a eles quando a
equipe não tem função.
"""

from django import forms
from django.db.models import Q
from django.utils import timezone

from cadastros.models import Estado, Municipio
from viagens_cadastros.models import Servidor
from viagens_oficios.models import ModeloMotivoOficio, Oficio

from .models import OrdemServico

FUNCOES_SERVIDOR_VALIDAS = {chave for chave, _ in OrdemServico.FUNCAO_SERVIDOR_CHOICES}

CAMPOS_DE_PAPEL = (
    "motorista_equipe", "tecnico_equipe", "apoio_montagem", "apoio_escolta",
    "coordenador_cerimonial", "apoio_cerimonial", "apoio_preparacao",
)


class OrdemServicoForm(forms.ModelForm):
    destino_estado = forms.ModelChoiceField(queryset=Estado.objects.all(), required=False, label="Estado")
    destino_cidade = forms.ModelChoiceField(queryset=Municipio.objects.all(), required=False, label="Cidade")
    modelo_motivo = forms.ModelChoiceField(
        label="Modelo de motivo", queryset=ModeloMotivoOficio.objects.order_by("nome"), required=False,
        empty_label="Selecione um modelo (opcional)",
    )

    class Meta:
        model = OrdemServico
        fields = [
            "numero", "oficios", "data_evento_inicio", "data_evento_fim", "servidores", "tipo_necessidade",
            *CAMPOS_DE_PAPEL, "motivo",
        ]
        widgets = {campo: forms.HiddenInput() for campo in CAMPOS_DE_PAPEL}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        ja_vinculados = list(self.instance.oficios.values_list("pk", flat=True)) if self.instance.pk else []
        self.fields["oficios"].required = False
        # Como o N° do Ofício: em branco, fica o reservado (ou o próximo livre).
        self.fields["numero"].required = False
        self.fields["numero"].label = "N° da OS"
        # Ofício cancelado não é oferecido como vínculo novo, mas o já vinculado
        # continua válido — senão qualquer salvamento seguinte o apagaria.
        self.fields["oficios"].queryset = Oficio.objects.filter(Q(cancelado=False) | Q(pk__in=ja_vinculados)).order_by("-ano", "-numero", "-pk")
        self.fields["data_evento_inicio"].required = False
        self.fields["data_evento_fim"].required = False
        self.fields["servidores"].required = False
        self.fields["servidores"].queryset = Servidor.objects.select_related("cargo", "unidade").order_by("nome")
        for campo in CAMPOS_DE_PAPEL:
            self.fields[campo].required = False
        self.fields["tipo_necessidade"].required = True
        self.fields["motivo"].required = False

        destinos = self._destinos_iniciais()
        if not self.is_bound and destinos:
            self.initial.setdefault("destino_estado", destinos[0][0])
            self.initial.setdefault("destino_cidade", destinos[0][1])
        extras = destinos[1:]
        # Quantas linhas de destino adicional a tela tem. Sem linha de sobra:
        # quem quiser outro destino usa o "+".
        enviado = str(self.data.get("quantidade_destinos", "")) if self.is_bound else ""
        solicitado = min(100, int(enviado)) if enviado.isdigit() else 0
        self.quantidade_destinos = max(len(extras), solicitado)
        if self.is_bound and self.data.get("acao") == "adicionar_destino":
            self.quantidade_destinos = min(100, self.quantidade_destinos + 1)
        for i in range(self.quantidade_destinos):
            extra = extras[i] if i < len(extras) else (None, None)
            self.fields[f"extra_estado_{i}"] = forms.ModelChoiceField(Estado.objects.all(), required=False, label=f"Estado adicional {i + 1}", initial=extra[0])
            self.fields[f"extra_cidade_{i}"] = forms.ModelChoiceField(Municipio.objects.all(), required=False, label=f"Município adicional {i + 1}", initial=extra[1])

    def _destinos_iniciais(self):
        """[(estado_id, municipio_id)] das linhas de destino ao abrir a tela.

        Da OS salva vêm os destinos gravados; a OS nova semeada pela viagem traz
        `destinos_seed` em `initial`; senão, nenhuma linha preenchida.
        """
        if self.is_bound:
            return []
        if self.instance.pk:
            return [(m.estado_id, m.pk) for m in self.instance.destinos.select_related("estado").order_by("nome", "pk")]
        semente = self.initial.get("destinos_seed") or []
        if semente:
            return [(e, c) for e, c in semente]
        if self.initial.get("destino_cidade") or self.initial.get("destino_estado"):
            return [(self.initial.get("destino_estado"), self.initial.get("destino_cidade"))]
        return []

    @property
    def ano_do_numero(self):
        return self.instance.ano or timezone.localdate().year

    def clean_numero(self):
        from core.numeracao import NAMESPACE_ORDEM_SERVICO, conferir_numero_digitado
        return conferir_numero_digitado(
            self.cleaned_data.get("numero"), ano=self.ano_do_numero, instancia=self.instance,
            namespace=NAMESPACE_ORDEM_SERVICO, documento="uma Ordem de Serviço", externo="uma OS do Coffee Break",
        )

    def clean(self):
        cd = super().clean()
        cidade, estado = cd.get("destino_cidade"), cd.get("destino_estado")
        if cidade and (not estado or cidade.estado_id != estado.pk):
            self.add_error("destino_cidade", "Selecione uma cidade do estado informado.")
        elif estado and not cidade:
            self.add_error("destino_cidade", "Informe a cidade do destino.")
        inicio, fim = cd.get("data_evento_inicio"), cd.get("data_evento_fim")
        if inicio and fim and fim < inicio:
            self.add_error("data_evento_fim", "A data final não pode ser anterior à inicial.")
        if inicio and not fim:
            cd["data_evento_fim"] = inicio
        destinos = [cidade.pk] if cidade and not self.errors.get("destino_cidade") else []
        for i in range(self.quantidade_destinos):
            c = cd.get(f"extra_cidade_{i}")
            e = cd.get(f"extra_estado_{i}")
            if e and not c:
                self.add_error(f"extra_cidade_{i}", f"Informe a cidade do destino adicional {i + 1}.")
            elif c and (not e or c.estado_id != e.pk):
                self.add_error(f"extra_cidade_{i}", f"Selecione uma cidade válida para o destino adicional {i + 1}.")
            elif c and c.pk not in destinos:
                destinos.append(c.pk)
        self.cleaned_destinos = destinos
        self.cleaned_funcoes_servidores = self._clean_funcoes_servidores(cd)
        return cd

    def _clean_funcoes_servidores(self, cd):
        """`funcao_servidor_<id>` de cada um da equipe, só nos tipos que têm função."""
        if cd.get("tipo_necessidade") not in OrdemServico.TIPOS_COM_FUNCOES:
            return {}
        servidores = cd.get("servidores")
        servidor_ids = {str(s.pk) for s in servidores} if servidores is not None else set()
        funcoes = {}
        for nome, valor in self.data.items():
            if not nome.startswith("funcao_servidor_"):
                continue
            servidor_id = nome.removeprefix("funcao_servidor_").strip()
            funcao = (valor or "").strip().upper()
            if not servidor_id or servidor_id not in servidor_ids or not funcao:
                continue
            if funcao not in FUNCOES_SERVIDOR_VALIDAS:
                self.add_error(None, "Selecione uma função válida para os servidores da equipe.")
                continue
            funcoes[servidor_id] = funcao
        return funcoes

    def save(self, commit=True):
        ordem = super().save(commit=False)
        ordem.funcoes_servidores = getattr(self, "cleaned_funcoes_servidores", {}) or {}
        if commit:
            ordem.save()
            self.save_m2m()
            ordem.destinos.set(getattr(self, "cleaned_destinos", []) or [])
        return ordem
