"""Formulário da etapa 1 do painel — o `EventoNovoCadastroForm` da origem.

Os campos são os de lá: tipos, modelo de motivo, motivo, período, destino e
os cinco seletores de documentos já existentes. O destino aqui é chave de
estado e município (na origem era texto), e os destinos adicionais seguem o
mecanismo do termo: `extra_estado_<i>`/`extra_cidade_<i>` a partir de
`quantidade_destinos`, nomeados pela tela na ordem das linhas.
"""

from django import forms
from django.db.models import Q

from cadastros.models import Estado, Municipio
from viagens_oficios.models import ModeloMotivoOficio, Oficio
from viagens_ordens.models import OrdemServico
from viagens_planos.models import PlanoTrabalho
from viagens_roteiros.models import Roteiro
from viagens_termos.models import TermoAutorizacao

from .models import TipoViagem, Viagem

# (campo do formulário, relação na viagem) dos documentos vinculáveis.
DOCUMENTOS_VINCULAVEIS = (
    ("oficios_vinculados", "oficios"),
    ("ordens_servico_vinculadas", "ordens_servico"),
    ("planos_trabalho_vinculados", "planos_trabalho"),
    ("termos_vinculados", "termos_autorizacao"),
    ("roteiros_vinculados", "roteiros"),
)


class ViagemForm(forms.ModelForm):
    modelo_motivo = forms.ModelChoiceField(
        label="Modelo de motivo", queryset=ModeloMotivoOficio.objects.order_by("nome"), required=False,
    )
    tipos = forms.ModelMultipleChoiceField(label="Tipo da viagem", queryset=TipoViagem.objects.all(), required=False)
    oficios_vinculados = forms.ModelMultipleChoiceField(label="Ofícios já existentes", queryset=Oficio.objects.none(), required=False)
    ordens_servico_vinculadas = forms.ModelMultipleChoiceField(label="Ordens de serviço já existentes", queryset=OrdemServico.objects.none(), required=False)
    planos_trabalho_vinculados = forms.ModelMultipleChoiceField(label="Planos de trabalho já existentes", queryset=PlanoTrabalho.objects.none(), required=False)
    termos_vinculados = forms.ModelMultipleChoiceField(label="Termos de autorização já existentes", queryset=TermoAutorizacao.objects.none(), required=False)
    roteiros_vinculados = forms.ModelMultipleChoiceField(label="Roteiros já existentes", queryset=Roteiro.objects.none(), required=False)

    class Meta:
        model = Viagem
        fields = ["tipos", "motivo", "data_inicio", "data_fim", "destino_estado", "destino_municipio"]
        labels = {"data_inicio": "Data de início", "data_fim": "Data de fim", "motivo": "Motivo"}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for nome in ("data_inicio", "data_fim", "destino_estado", "destino_municipio", "motivo"):
            self.fields[nome].required = False
        viagem_pk = self.instance.pk
        # Documento cancelado não entra como opção nova, mas continua visível
        # se já estiver vinculado a esta viagem.
        desta_ou_livre = Q(viagem_id=viagem_pk) | Q(viagem__isnull=True, cancelado=False)
        self.fields["oficios_vinculados"].queryset = (
            Oficio.objects.select_related("roteiro__origem_municipio", "viatura").prefetch_related("servidores", "roteiro__destinos__municipio")
            .filter(desta_ou_livre).order_by("-data_criacao", "-criado_em")
        )
        self.fields["ordens_servico_vinculadas"].queryset = (
            OrdemServico.objects.prefetch_related("destinos__estado").filter(desta_ou_livre).order_by("-ano", "-numero")
        )
        self.fields["planos_trabalho_vinculados"].queryset = (
            PlanoTrabalho.objects.select_related("programa").filter(desta_ou_livre).order_by("-ano", "-numero")
        )
        self.fields["termos_vinculados"].queryset = (
            TermoAutorizacao.objects.select_related("destino_cidade__estado", "destino_estado", "oficio__roteiro")
            .prefetch_related("oficio__roteiro__destinos__municipio__estado").filter(desta_ou_livre).order_by("-criado_em")
        )
        self.fields["roteiros_vinculados"].queryset = (
            Roteiro.objects.select_related("origem_municipio__estado").prefetch_related("trechos__destino_municipio__estado")
            .filter(desta_ou_livre).order_by("-criado_em")
        )
        if not self.is_bound:
            if viagem_pk:
                for campo, relacao in DOCUMENTOS_VINCULAVEIS:
                    self.initial[campo] = list(getattr(self.instance, relacao).values_list("pk", flat=True))
            if self.instance.destino_municipio_id and not self.instance.destino_estado_id:
                self.initial["destino_estado"] = self.instance.destino_municipio.estado_id
            elif not self.instance.destino_estado_id:
                # Como na origem: a UF nasce com a da sede das Configurações.
                from viagens_cadastros.models import ConfiguracaoSistema

                sede = ConfiguracaoSistema.atual().cidade_sede_padrao
                if sede is not None:
                    self.initial["destino_estado"] = sede.estado_id

        # Destinos adicionais, no mecanismo do termo: quantos pares a tela tem.
        extras = self.instance.destinos_extras or []
        enviado = str(self.data.get("quantidade_destinos", "")) if self.is_bound else ""
        solicitado = min(100, int(enviado)) if enviado.isdigit() else 0
        self.quantidade_destinos = max(len(extras), solicitado)
        if self.is_bound and self.data.get("acao") == "adicionar_destino":
            self.quantidade_destinos = min(100, self.quantidade_destinos + 1)
        for i in range(self.quantidade_destinos):
            extra = extras[i] if i < len(extras) else {}
            self.fields[f"extra_estado_{i}"] = forms.ModelChoiceField(
                Estado.objects.all(), required=False, label=f"Estado adicional {i + 1}", initial=extra.get("estado"))
            self.fields[f"extra_cidade_{i}"] = forms.ModelChoiceField(
                Municipio.objects.all(), required=False, label=f"Município adicional {i + 1}", initial=extra.get("municipio"))

    def clean(self):
        cd = super().clean()
        inicio, fim = cd.get("data_inicio"), cd.get("data_fim")
        if inicio and fim and fim < inicio:
            self.add_error("data_fim", "A data final não pode ser anterior à data inicial.")
        cidade, estado = cd.get("destino_municipio"), cd.get("destino_estado")
        if cidade and (not estado or cidade.estado_id != estado.pk):
            self.add_error("destino_municipio", "Escolha um município do estado selecionado.")
        self.destinos_adicionais = []
        for nome in self.fields:
            if not nome.startswith("extra_cidade_"):
                continue
            c = cd.get(nome)
            e = cd.get(nome.replace("cidade", "estado"))
            if e and not c:
                self.add_error(nome, "Selecione o município adicional.")
            elif c and (not e or c.estado_id != e.pk):
                self.add_error(nome, "Selecione um município do estado informado.")
            elif c:
                self.destinos_adicionais.append({"estado": e.pk, "municipio": c.pk})
        return cd

    def save(self, commit=True):
        viagem = super().save(commit=False)
        viagem.destinos_extras = self.destinos_adicionais
        if commit:
            viagem.save()
            self.save_m2m()
        return viagem
