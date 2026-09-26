"""Formulários do plano de trabalho — os campos e as mensagens do Gerenciador de Viagens.

Os destinos seguem o mecanismo do termo: a primeira linha é `destino_estado`/
`destino_cidade` e as seguintes são `extra_estado_<i>`/`extra_cidade_<i>`,
criadas a partir de `quantidade_destinos`.
"""

from datetime import datetime

from django import forms
from django.forms import inlineformset_factory

from cadastros.models import Estado, Municipio
from core.normalizers import normalize_upper
from viagens_cadastros.models import Cargo, Servidor, Unidade

from .models import EfetivoPlano, HorarioAtendimento, PlanoDestino, PlanoTrabalho, ProgramaSolicitante


class PlanoIdentificacaoForm(forms.ModelForm):
    """Cartão 1 — programa, coordenação, período, destinos e os textos do documento."""

    PROGRAMA_OUTRO_VALUE = "__outro__"

    programa = forms.ChoiceField(required=False)
    horario_atendimento = forms.ChoiceField(required=False)

    class Meta:
        model = PlanoTrabalho
        fields = [
            "numero", "programa", "programa_outros", "destino_estado", "destino_cidade",
            "data_evento_inicio", "data_evento_fim", "horario_atendimento",
            # Contextualização, coordenação e considerações finais ficam de fora:
            # a tela não as oferece e quem as escreve é o `sincronizar_textos_padrao`,
            # na gravação. No formulário, um POST sem elas gravaria vazio por cima.
            "coordenador_adm_modo", "coordenador_adm", "coordenador_adm_nome_manual", "coordenador_adm_cargo_manual", "coordenador_adm_genero",
            "coordenador_op_modo", "coordenador_op", "coordenador_op_nome_manual", "coordenador_op_cargo_manual", "coordenador_op_genero",
        ]

    def __init__(self, *args, **kwargs):
        # "Outro programa" digitado sem a opção marcada conta como "Outro".
        dados = args[0] if args else kwargs.get("data")
        if dados is not None:
            dados = dados.copy()
            if not (dados.get("programa") or "").strip() and (dados.get("programa_outros") or "").strip():
                dados["programa"] = self.PROGRAMA_OUTRO_VALUE
            if args:
                args = (dados, *args[1:])
            else:
                kwargs["data"] = dados
        super().__init__(*args, **kwargs)
        for nome in self.fields:
            self.fields[nome].required = False
        instancia = self.instance if self.instance and self.instance.pk else None

        programa_choices = [("", "Selecione um programa (opcional)"), (self.PROGRAMA_OUTRO_VALUE, "Outro")]
        programa_choices += [(str(p.pk), p.nome) for p in ProgramaSolicitante.objects.order_by("nome")]
        self.fields["programa"].choices = programa_choices
        programa_inicial = ""
        if self.is_bound:
            programa_inicial = (self.data.get("programa") or "").strip()
        elif instancia:
            if instancia.programa_id:
                programa_inicial = str(instancia.programa_id)
            elif instancia.programa_outros:
                programa_inicial = self.PROGRAMA_OUTRO_VALUE
        self.initial["programa"] = programa_inicial
        self.programa_outros_selected = programa_inicial == self.PROGRAMA_OUTRO_VALUE

        horario_choices = [("", "Selecione um horário (opcional)")]
        horario_choices += [(h.faixa, h.faixa) for h in HorarioAtendimento.objects.order_by("faixa")]
        horario_inicial = (self.data.get("horario_atendimento") or "").strip() if self.is_bound else (instancia.horario_atendimento or "").strip() if instancia else ""
        if horario_inicial and horario_inicial not in {v for v, _ in horario_choices}:
            horario_choices.append((horario_inicial, horario_inicial))
        self.fields["horario_atendimento"].choices = horario_choices
        self.initial["horario_atendimento"] = horario_inicial

        for campo in ("coordenador_adm_genero", "coordenador_op_genero"):
            self.fields[campo].choices = PlanoTrabalho.COORDENADOR_GENERO_CHOICES
        # O modo e o servidor não vêm mais da tela: são deduzidos do nome
        # digitado, em `_normalize_coordenador`. Ficam no formulário só para o
        # que `clean()` grava neles chegar à instância.
        for papel in ("adm", "op"):
            self.fields[f"coordenador_{papel}_modo"].choices = PlanoTrabalho.COORDENADOR_MODO_CHOICES
            self.fields[f"coordenador_{papel}_modo"].required = False
            self.fields[f"coordenador_{papel}"].required = False
        cargo_choices = [("", "Selecione um cargo")] + [(c.nome, c.nome) for c in Cargo.objects.order_by("nome")]
        for campo in ("coordenador_adm_cargo_manual", "coordenador_op_cargo_manual"):
            atual = (self.data.get(campo) or "").strip() if self.is_bound else (getattr(instancia, campo, "") or "").strip() if instancia else ""
            escolhas = list(cargo_choices)
            if atual and atual not in {v for v, _ in escolhas}:
                escolhas.append((atual, atual))
            self.fields[campo] = forms.ChoiceField(required=False, choices=escolhas)
        servidores = Servidor.objects.select_related("cargo", "unidade").order_by("nome")
        self.fields["coordenador_adm"].queryset = servidores
        self.fields["coordenador_op"].queryset = servidores

        # Destinos: a primeira linha é a do plano; as extras vêm das linhas do rascunho.
        self.fields["destino_estado"].queryset = Estado.objects.order_by("sigla")
        self.fields["destino_cidade"].queryset = Municipio.objects.select_related("estado").order_by("nome")
        extras = instancia.destinos_rascunho()[1:] if instancia else []
        if not self.is_bound and instancia:
            linhas = instancia.destinos_rascunho()
            if linhas:
                self.initial["destino_estado"] = linhas[0].estado_id
                self.initial["destino_cidade"] = linhas[0].cidade_id
            elif instancia.destino_cidade_id and not instancia.destino_estado_id:
                self.initial["destino_estado"] = instancia.destino_cidade.estado_id
        enviado = str(self.data.get("quantidade_destinos", "")) if self.is_bound else ""
        solicitado = min(100, int(enviado)) if enviado.isdigit() else 0
        self.quantidade_destinos = max(len(extras), solicitado)
        if self.is_bound and self.data.get("acao") == "adicionar_destino":
            self.quantidade_destinos = min(100, self.quantidade_destinos + 1)
        for i in range(self.quantidade_destinos):
            extra = extras[i] if i < len(extras) else None
            self.fields[f"extra_estado_{i}"] = forms.ModelChoiceField(
                Estado.objects.all(), required=False, label=f"Estado adicional {i + 1}", initial=extra.estado_id if extra else None,
            )
            self.fields[f"extra_cidade_{i}"] = forms.ModelChoiceField(
                Municipio.objects.all(), required=False, label=f"Município adicional {i + 1}", initial=extra.cidade_id if extra else None,
            )

    def clean_numero(self):
        """Como o N° do Ofício: em branco mantém o reservado; não repete outro do ano."""
        from django.utils import timezone

        from core.numeracao import conferir_numero_digitado
        return conferir_numero_digitado(
            self.cleaned_data.get("numero"), ano=self.instance.ano or timezone.localdate().year,
            instancia=self.instance, documento="um Plano de Trabalho",
        )

    def clean_programa(self):
        valor = (self.cleaned_data.get("programa") or "").strip()
        self.programa_outros_selected = valor == self.PROGRAMA_OUTRO_VALUE
        if not valor or self.programa_outros_selected:
            return None
        try:
            return ProgramaSolicitante.objects.get(pk=valor)
        except (ProgramaSolicitante.DoesNotExist, TypeError, ValueError):
            raise forms.ValidationError("Selecione um programa válido.") from None

    def clean_horario_atendimento(self):
        return (self.cleaned_data.get("horario_atendimento") or "").strip()

    def clean_coordenador_adm_genero(self):
        return self.cleaned_data.get("coordenador_adm_genero") or PlanoTrabalho.COORDENADOR_GENERO_MASCULINO

    def clean_coordenador_op_genero(self):
        return self.cleaned_data.get("coordenador_op_genero") or PlanoTrabalho.COORDENADOR_GENERO_MASCULINO

    def clean(self):
        cleaned = super().clean()
        cidade, estado = cleaned.get("destino_cidade"), cleaned.get("destino_estado")
        inicio, fim = cleaned.get("data_evento_inicio"), cleaned.get("data_evento_fim")

        if cidade:
            cleaned["destino_estado"] = cidade.estado
        elif estado and not cidade:
            self.add_error("destino_cidade", "Informe a cidade do destino.")

        if inicio and not fim:
            cleaned["data_evento_fim"] = inicio
        if inicio and fim and fim < inicio:
            self.add_error("data_evento_fim", "A data final não pode ser anterior à data inicial.")

        self._normalize_coordenador(cleaned, "adm")
        self._normalize_coordenador(cleaned, "op")

        if self.programa_outros_selected:
            if not (cleaned.get("programa_outros") or "").strip():
                self.add_error("programa_outros", "Informe o outro programa.")
            cleaned["programa"] = None
        else:
            cleaned["programa_outros"] = ""

        destinos = []
        if cidade:
            destinos.append((cidade.estado_id, cidade.pk))
        for i in range(self.quantidade_destinos):
            e, c = cleaned.get(f"extra_estado_{i}"), cleaned.get(f"extra_cidade_{i}")
            if not e and not c:
                continue
            if e and not c:
                self.add_error(f"extra_cidade_{i}", f"Informe a cidade do destino adicional {i + 1}.")
                continue
            if e and c.estado_id != e.pk:
                self.add_error(f"extra_cidade_{i}", f"Selecione uma cidade válida para o destino adicional {i + 1}.")
                continue
            destinos.append((c.estado_id, c.pk))
        self.cleaned_destinos = destinos
        return cleaned

    def _normalize_coordenador(self, cleaned, papel):
        """Um campo só: o nome digitado diz se o coordenador é do sistema ou não.

        A tela oferece os servidores como sugestão, mas aceita qualquer nome.
        Bateu com um servidor, vale o cadastro dele — o nome e o cargo saem de
        lá, então os manuais são zerados. Não bateu, vale o que foi digitado.

        O nome do servidor é único no banco (`viagens_servidor_nome_unico`),
        então a busca por nome não tem empate para desfazer.
        """
        servidor_key, modo_key = f"coordenador_{papel}", f"coordenador_{papel}_modo"
        nome_key, cargo_key = f"coordenador_{papel}_nome_manual", f"coordenador_{papel}_cargo_manual"
        nome = normalize_upper(cleaned.get(nome_key) or "")
        cleaned[cargo_key] = (cleaned.get(cargo_key) or "").strip()
        servidor = Servidor.objects.filter(nome__iexact=nome).first() if nome else None
        if servidor:
            cleaned[modo_key] = PlanoTrabalho.COORDENADOR_MODO_SERVIDOR
            cleaned[servidor_key] = servidor
            cleaned[nome_key] = ""
            cleaned[cargo_key] = ""
            return
        cleaned[modo_key] = PlanoTrabalho.COORDENADOR_MODO_MANUAL
        cleaned[servidor_key] = None
        cleaned[nome_key] = nome

    def save(self, commit=True):
        instancia = super().save(commit=False)
        destinos = getattr(self, "cleaned_destinos", None) or []
        if destinos:
            instancia.destino_estado_id, instancia.destino_cidade_id = destinos[0]
        else:
            instancia.destino_estado = None
            instancia.destino_cidade = None
        if commit:
            instancia.save()
            self._save_destinos(instancia)
        return instancia

    def _save_destinos(self, instancia):
        # Só as linhas do rascunho (evento nulo); as cópias dos eventos gravados ficam.
        PlanoDestino.objects.filter(plano=instancia, evento__isnull=True).delete()
        PlanoDestino.objects.bulk_create([
            PlanoDestino(plano=instancia, estado_id=estado_id, cidade_id=cidade_id, ordem=ordem)
            for ordem, (estado_id, cidade_id) in enumerate(getattr(self, "cleaned_destinos", []) or [], 1)
        ])


class PlanoDiariasForm(forms.ModelForm):
    """Cartão 2 — saída e chegada na sede."""

    class Meta:
        model = PlanoTrabalho
        fields = ["saida_sede_data", "saida_sede_hora", "chegada_sede_data", "chegada_sede_hora"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for nome in self.fields:
            self.fields[nome].required = False

    def clean(self):
        cleaned = super().clean()
        sd, sh = cleaned.get("saida_sede_data"), cleaned.get("saida_sede_hora")
        cd, ch = cleaned.get("chegada_sede_data"), cleaned.get("chegada_sede_hora")
        if sd and cd and sh and ch and datetime.combine(cd, ch) <= datetime.combine(sd, sh):
            self.add_error("chegada_sede_data", "A chegada na sede deve ser depois da saída.")
        return cleaned


class EfetivoPlanoForm(forms.ModelForm):
    class Meta:
        model = EfetivoPlano
        fields = ["unidade", "cargo", "quantidade"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["unidade"].queryset = Unidade.objects.order_by("nome")
        self.fields["cargo"].queryset = Cargo.objects.order_by("nome")
        # Linha toda em branco é descartada; pela metade acusa erro — em clean().
        self.fields["unidade"].required = False
        self.fields["cargo"].required = False
        self.fields["quantidade"].required = False

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("DELETE"):
            return cleaned
        unidade, cargo, quantidade = cleaned.get("unidade"), cleaned.get("cargo"), cleaned.get("quantidade")
        # A quantidade nasce com 1: sozinha ela não é conteúdo. Linha sem
        # unidade e sem cargo é linha em branco e não trava o rascunho.
        if not unidade and not cargo:
            return cleaned
        if not cargo:
            self.add_error("cargo", "Selecione o cargo.")
        if not quantidade:
            self.add_error("quantidade", "Informe a quantidade.")
        return cleaned


EfetivoPlanoFormSet = inlineformset_factory(
    PlanoTrabalho, EfetivoPlano, form=EfetivoPlanoForm, extra=0, min_num=1, validate_min=False, can_delete=True,
)
