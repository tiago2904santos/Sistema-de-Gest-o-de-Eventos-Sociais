"""Formulários do módulo de Coffee Break.

Como nos demais módulos, a renderização fica com os components do design
system; aqui mora a validação e a persistência.
"""

from django import forms
from django.core.exceptions import NON_FIELD_ERRORS, ValidationError
from django.utils import timezone

from cadastros.models import Municipio
from core.uploads import validate_private_document_upload
from core.utils.masks import format_protocolo

from .models import (
    CertidaoFornecedor,
    ConfiguracaoCoffeeBreak,
    ContratoCoffeeBreak,
    Fornecedor,
    LoteCoffeeBreak,
    SituacaoFinanceira,
    SolicitacaoCoffeeBreak,
    normalizar_cnpj,
)
from . import certidoes, services


def validar_pdf(arquivo):
    """Só PDF legível, até o limite de anexos privados do sistema."""
    if not arquivo.name.lower().endswith(".pdf"):
        raise ValidationError("Envie o arquivo em PDF.")
    validate_private_document_upload(arquivo)


def municipios_do_parana():
    return Municipio.objects.filter(estado__sigla="PR").order_by("nome")


class SolicitacaoCoffeeBreakForm(forms.ModelForm):
    versao = forms.CharField(required=False, widget=forms.HiddenInput)

    class Meta:
        model = SolicitacaoCoffeeBreak
        fields = [
            "municipio",
            "data_solicitacao",
            "numero",
            "descricao_evento",
            "quantidade",
            "data_inicio_evento",
            "data_fim_evento",
            "periodo_evento_texto",
            "horario_evento",
            "detalhamento_pedido",
            "local_entrega",
            "responsavel_recebimento",
            "data_envio_ordem_servico",
            "numero_nota_fiscal",
            "quantidade_faturada",
            "arquivo_nota_fiscal",
            "protocolo_pagamento",
            "data_atesto_gaf",
            "data_ordem_bancaria",
            "data_envio_empresa",
            "observacoes",
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        instancia = self.instance if self.instance.pk else None
        municipios = municipios_do_parana()
        if instancia and instancia.municipio_id:
            municipios = municipios | Municipio.objects.filter(pk=instancia.municipio_id)
        # As etapas usam só uma parte dos campos: cada ajuste vale se o campo
        # estiver no formulário.
        if "municipio" in self.fields:
            self.fields["municipio"].queryset = municipios.distinct()
            # Registros antigos (da planilha) não têm município: continuam no
            # lote em que estão até alguém informar o município.
            self.fields["municipio"].required = not (instancia and not instancia.municipio_id)
        if "numero" in self.fields:
            self.fields["numero"].help_text = "Sugerido pelo lote do município; pode alterar."
            # Na tela o número vai como no ofício de Viagens: só a sequência
            # ("41"), com o "/ 2026" ao lado. O inicial segue o mesmo formato
            # para a comparação de "mudou?" não acusar alteração à toa.
            atual = services.partes_numero(instancia.numero) if instancia else None
            if atual:
                self.initial["numero"] = str(atual[0])
        if "arquivo_nota_fiscal" in self.fields:
            self.fields["arquivo_nota_fiscal"].validators.append(validar_pdf)
        for nome in ("descricao_evento", "quantidade"):
            if nome in self.fields:
                self.fields[nome].required = True
        if instancia:
            self.initial["versao"] = str(
                int(instancia.atualizado_em.timestamp() * 1_000_000)
            )
            if instancia.financeiro_iniciado:
                for nome in (
                    "municipio",
                    "data_solicitacao",
                    "numero",
                    "descricao_evento",
                    "quantidade",
                    "data_inicio_evento",
                    "data_fim_evento",
                    "periodo_evento_texto",
                ):
                    if nome in self.fields:
                        self.fields[nome].disabled = True

    def clean_descricao_evento(self):
        """Uma linha só: quebras de linha (de registros antigos) viram espaço."""
        return " ".join((self.cleaned_data.get("descricao_evento") or "").split())

    def clean_numero(self):
        """ "41" vira "41/2026" (o ano do número atual ou o da solicitação).

        O formato completo ("41/2026") e textos antigos da planilha passam
        como vieram; em branco, o sistema numera ao salvar.
        """
        numero = (self.cleaned_data.get("numero") or "").strip()
        if numero.isdigit():
            sequencia = int(numero)
            if sequencia < 1:
                raise forms.ValidationError("O número da OS deve ser 1 ou mais.")
            numero = services.formatar_numero(sequencia, self.ano_do_numero())
        elif not services.partes_numero(numero):
            return numero
        # Uma numeração só para todos os lotes e para as ordens de serviço de
        # Viagens: o número não se repete. (Registro que já tinha este número
        # fica como está, mesmo repetido na planilha.)
        if numero == self.instance.numero:
            return numero
        ano = services.partes_numero(numero)[1]
        proxima = services.proxima_sequencia(ano)
        ocupado = services.numero_ocupado(numero, excluir_pk=self.instance.pk)
        if ocupado:
            raise forms.ValidationError(f"{ocupado} A próxima livre é {proxima}.")
        # O próximo sugerido é reservado ao gravar (sob a trava do livro); o
        # digitado é conferido de novo lá.
        self.modo_numero = services.RESERVAR if numero == services.formatar_numero(proxima, ano) else services.CONFERIR
        return numero

    def ano_do_numero(self):
        """O ano que acompanha o número: o do número atual, ou o da data."""
        atual = services.partes_numero(self.instance.numero) if self.instance.pk else None
        if atual:
            return atual[1]
        data = self.cleaned_data.get("data_solicitacao") or self.instance.data_solicitacao
        return (data or timezone.localdate()).year

    def clean_quantidade(self):
        quantidade = self.cleaned_data.get("quantidade")
        if quantidade is not None and quantidade < 1:
            raise forms.ValidationError(
                "A quantidade deve ser de pelo menos 1 unidade."
            )
        return quantidade

    def clean(self):
        dados = super().clean()
        inicio = dados.get("data_inicio_evento")
        fim = dados.get("data_fim_evento")
        if inicio and fim and fim < inicio:
            self.add_error(
                "data_fim_evento",
                "A data de fim não pode ser anterior à data de início.",
            )
        texto = (dados.get("periodo_evento_texto") or "").strip()
        campos_periodo = {
            "data_inicio_evento", "data_fim_evento", "periodo_evento_texto"
        }
        if texto and (inicio or fim) and (
            not self.instance.pk or campos_periodo.intersection(self.changed_data)
        ):
            self.add_error(
                "periodo_evento_texto",
                "Use as datas estruturadas ou o período em texto, não os dois.",
            )
        self._escolher_lote(dados)
        self._conferir_vigencia(dados)
        if self.instance.pk:
            atual = type(self.instance).objects.filter(pk=self.instance.pk).values_list(
                "atualizado_em", flat=True
            ).first()
            versao = dados.get("versao")
            if atual and versao != str(int(atual.timestamp() * 1_000_000)):
                raise forms.ValidationError(
                    "Esta solicitação foi alterada por outra pessoa. Recarregue a página antes de salvar."
                )
        # Identificadores institucionais são texto — nunca números coláveis
        # de datas: só normaliza espaços.
        for campo in (
            "numero", "numero_nota_fiscal", "protocolo_pagamento",
            "numero_oficio", "protocolo_pcpr_oficio",
        ):
            if dados.get(campo):
                dados[campo] = dados[campo].strip()
        # Protocolo com a máscara do de Viagens (00.000.000-0); outro formato fica como veio.
        for campo in ("protocolo_pagamento", "protocolo_pcpr_oficio"):
            if dados.get(campo):
                dados[campo] = format_protocolo(dados[campo])
        return dados

    def _escolher_lote(self, dados):
        """O lote sai do município; quem pede não escolhe lote."""
        municipio = dados.get("municipio")
        if municipio is None or self.fields["municipio"].disabled:
            return
        if self.instance.pk and self.instance.municipio_id == municipio.pk:
            return
        lote, _distancia = services.escolher_lote(
            municipio, dados.get("data_inicio_evento") or dados.get("data_solicitacao")
        )
        if lote is None:
            self.add_error(
                "municipio",
                f"Nenhum lote ativo atende {municipio.nome}. Inclua o município "
                "na lista de um lote em Cadastros › Lotes.",
            )
            return
        self.instance.lote = lote
        self.lote_escolhido = lote

    def _conferir_vigencia(self, dados):
        """Evento depois do fim da vigência do contrato (com o aditivo): não passa.

        Só vale para pedido novo ou quando o lote, a data ou o município mudam:
        registro antigo continua editável.
        """
        if not self.instance.lote_id:
            return
        campos = {"municipio", "data_inicio_evento", "data_solicitacao"}
        if self.instance.pk and not campos.intersection(self.changed_data):
            return
        data = dados.get("data_inicio_evento") or dados.get("data_solicitacao")
        lote = self.instance.lote
        vencido = services.contrato_vencido_em(lote.contrato, data)
        if vencido:
            campo = "data_inicio_evento" if dados.get("data_inicio_evento") and "data_inicio_evento" in self.fields else None
            if campo is None and "municipio" in self.fields:
                campo = "municipio"
            self.add_error(
                campo,
                f"Contrato vencido em {vencido:%d/%m/%Y}: o contrato {lote.contrato.numero} do "
                f"{lote.rotulo_curto} não cobre um evento em {data:%d/%m/%Y}. Providencie o aditivo "
                "de prorrogação ou cadastre outro lote para o município.",
            )

    def save(self, criado_por=None):
        solicitacao = super().save(commit=False)
        if not solicitacao.pk:
            solicitacao.criado_por = criado_por
        # Trava o lote e revalida o saldo na mesma transação da escrita.
        return services.salvar_com_saldo(
            solicitacao,
            numero=getattr(self, "modo_numero", None),
            oficio=getattr(self, "modo_oficio", None),
        )

    def _update_errors(self, errors):
        """Erro do modelo num campo de outra etapa sobe para o topo do formulário.

        A validação do modelo olha o registro inteiro (a nota antes do
        protocolo, o atesto antes da OB...), mas cada etapa só tem parte dos
        campos — e o Django recusa erro em campo que o formulário não tem.
        """
        if hasattr(errors, "error_dict"):
            proprios, alheios = {}, []
            for campo, mensagens in errors.error_dict.items():
                if campo == NON_FIELD_ERRORS or campo in self.fields:
                    proprios[campo] = mensagens
                else:
                    alheios.extend(mensagens)
            if alheios:
                proprios.setdefault(NON_FIELD_ERRORS, []).extend(alheios)
            errors = forms.ValidationError(proprios)
        super()._update_errors(errors)


# Cada etapa da solicitação grava só os seus campos: o resto fica como está.
CAMPOS_PEDIDO = [
    "municipio",
    "data_solicitacao",
    "numero",
    "descricao_evento",
    "quantidade",
    "data_inicio_evento",
    "periodo_evento_texto",
    "horario_evento",
    "local_entrega",
    "responsavel_recebimento",
]
CAMPOS_NOTA = [
    "numero_nota_fiscal",
    # O que a nota cobrou: o lote passa a descontar isso, e não o pedido.
    "quantidade_faturada",
    # A data antes do número: o ano do número sai dela.
    "data_oficio",
    "numero_oficio",
    "protocolo_pcpr_oficio",
]
CAMPOS_PROTOCOLO = [
    # O protocolo de pagamento é o do ofício (etapa 2): não se digita aqui.
    "data_atesto_gaf",
    "data_ordem_bancaria",
    "data_envio_empresa",
    "observacoes",
]


class PedidoCoffeeBreakForm(SolicitacaoCoffeeBreakForm):
    """Etapa 1 — o pedido e a ordem de serviço.

    O evento tem uma data só: a tela não pede mais o fim do período, e
    salvar com a data aberta limpa um fim antigo.
    """

    registro_retroativo = forms.BooleanField(label="Registro retroativo", required=False)
    justificativa_retroativo = forms.CharField(
        label="Justificativa do registro retroativo", required=False, max_length=255,
    )

    class Meta(SolicitacaoCoffeeBreakForm.Meta):
        fields = CAMPOS_PEDIDO

    def clean(self):
        dados = super().clean()
        self._conferir_data_do_evento(dados)
        return dados

    def _conferir_data_do_evento(self, dados):
        """Evento anterior à data da solicitação só como registro retroativo justificado.

        Vale para o pedido novo e quando a data muda: registro antigo segue editável.
        """
        inicio = dados.get("data_inicio_evento")
        pedido = dados.get("data_solicitacao")
        self.evento_retroativo = bool(inicio and pedido and inicio < pedido)
        if not self.evento_retroativo:
            return
        if self.instance.pk and not {"data_inicio_evento", "data_solicitacao"}.intersection(self.changed_data):
            return
        if not dados.get("registro_retroativo"):
            self.add_error(
                "data_inicio_evento",
                "O evento é anterior à data da solicitação. Confira a data ou marque "
                "\"registro retroativo\" e justifique.",
            )
        elif not (dados.get("justificativa_retroativo") or "").strip():
            self.add_error("justificativa_retroativo", "Justifique o registro retroativo.")

    def save(self, criado_por=None):
        if not self.fields["data_inicio_evento"].disabled:
            self.instance.data_fim_evento = None
        return super().save(criado_por=criado_por)


class NotaCoffeeBreakForm(SolicitacaoCoffeeBreakForm):
    """Etapa 2 — a nota fiscal recebida e o ofício que a encaminha."""

    class Meta(SolicitacaoCoffeeBreakForm.Meta):
        fields = CAMPOS_NOTA

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Como o Nº da OS: na tela só a sequência ("124"), com o "/ 2026" ao lado.
        atual = services.partes_numero(self.instance.numero_oficio) if self.instance.pk else None
        if atual:
            self.initial["numero_oficio"] = str(atual[0])

    def clean_numero_nota_fiscal(self):
        numero = (self.cleaned_data.get("numero_nota_fiscal") or "").strip()
        if not numero and self.instance.protocolo_pagamento:
            raise forms.ValidationError(
                "O protocolo de pagamento já foi registrado: a nota não pode ficar em branco."
            )
        return numero

    def ano_do_oficio(self):
        """O ano do número do ofício: o do número atual, ou o da data do ofício."""
        atual = services.partes_numero(self.instance.numero_oficio) if self.instance.pk else None
        if atual:
            return atual[1]
        return (self.cleaned_data.get("data_oficio") or timezone.localdate()).year

    def clean_data_oficio(self):
        # Em branco, o ofício sai com a data do dia.
        return self.cleaned_data.get("data_oficio") or timezone.localdate()

    def clean_numero_oficio(self):
        """ "125" vira "125/2026"; em branco, o próximo da numeração; não repete.

        A numeração é a dos ofícios de Viagens (livro único). Em branco ou o
        próximo sugerido, o número é reservado ao gravar, sob a trava do
        livro; o digitado é conferido de novo lá.
        """
        numero = " ".join((self.cleaned_data.get("numero_oficio") or "").split())
        ano = self.ano_do_oficio()
        if not numero:
            self.modo_oficio = services.RESERVAR
            return ""
        if numero.isdigit():
            if int(numero) < 1:
                raise forms.ValidationError("O número do ofício deve ser 1 ou mais.")
            numero = services.formatar_numero(int(numero), ano)
        partes = services.partes_numero(numero)
        if partes and numero != self.instance.numero_oficio:
            proximo = services.proxima_sequencia_oficio(partes[1])
            ocupado = services.oficio_ocupado(numero, excluir_pk=self.instance.pk)
            if ocupado:
                raise forms.ValidationError(f"{ocupado} O próximo livre é {proximo}.")
            self.modo_oficio = services.RESERVAR if partes[0] == proximo else services.CONFERIR
        return numero


class ProtocoloCoffeeBreakForm(SolicitacaoCoffeeBreakForm):
    """Etapa 3 — o protocolo de pagamento e o que vem depois dele."""

    class Meta(SolicitacaoCoffeeBreakForm.Meta):
        fields = CAMPOS_PROTOCOLO


class FiltroSolicitacoesCoffeeForm(forms.Form):
    """Filtros da listagem de solicitações (GET)."""

    q = forms.CharField(required=False, label="Busca")
    lote = forms.ModelChoiceField(
        required=False,
        label="Lote",
        queryset=LoteCoffeeBreak.objects.select_related(
            "contrato__fornecedor"
        ).all(),
    )
    fornecedor = forms.ModelChoiceField(
        required=False, label="Fornecedor", queryset=Fornecedor.objects.all()
    )
    situacao = forms.ChoiceField(
        required=False,
        label="Situação financeira",
        choices=[("", "Todas as situações")] + list(SituacaoFinanceira.choices),
    )
    inicio = forms.DateField(required=False, label="Eventos a partir de")
    fim = forms.DateField(required=False, label="Eventos até")


class FiltroLotesForm(forms.Form):
    """Filtros da listagem de lotes (GET)."""

    q = forms.CharField(required=False, label="Busca")
    exercicio = forms.CharField(required=False, label="Exercício")
    situacao = forms.ChoiceField(
        required=False,
        label="Situação",
        choices=[("", "Todas"), ("ativos", "Ativos"), ("inativos", "Inativos")],
    )


class FormularioCadastroVersionado(forms.ModelForm):
    """Evita que duas correções administrativas se sobrescrevam."""

    versao = forms.CharField(required=False, widget=forms.HiddenInput)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.pk:
            self.initial["versao"] = str(
                int(self.instance.atualizado_em.timestamp() * 1_000_000)
            )

    def clean(self):
        dados = super().clean()
        if self.instance.pk:
            atual = type(self.instance).objects.filter(pk=self.instance.pk).values_list(
                "atualizado_em", flat=True
            ).first()
            if atual and dados.get("versao") != str(
                int(atual.timestamp() * 1_000_000)
            ):
                raise forms.ValidationError(
                    "Este cadastro foi alterado por outra pessoa. Recarregue a página antes de salvar."
                )
        return dados


class FornecedorForm(FormularioCadastroVersionado):
    cnpj = forms.CharField(
        label="CNPJ",
        required=False,
        max_length=18,
        help_text="Pode ser informado com ou sem pontuação.",
    )

    class Meta:
        model = Fornecedor
        fields = (
            "razao_social", "nome_curto", "cnpj", "contato", "telefone", "email",
            "url_certidao_municipal",
        )

    def clean_cnpj(self):
        cnpj = normalizar_cnpj(self.cleaned_data.get("cnpj"))
        if cnpj and len(cnpj) != 14:
            raise forms.ValidationError("O CNPJ deve ter 14 dígitos.")
        return cnpj


class ContratoCoffeeBreakForm(FormularioCadastroVersionado):
    class Meta:
        model = ContratoCoffeeBreak
        fields = (
            "fornecedor",
            "numero",
            "numero_gms",
            "termo_aditivo",
            "fiscal_responsavel",
            "cargo_fiscal",
            "clausula_pagamento",
            "arquivo_contrato",
            "arquivo_termo_aditivo",
            "vigencia_fim",
            "quantidade_contratada",
            "valor_unitario",
            "antecedencia_minima_dias",
            "objeto",
            "observacoes",
        )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for nome in ("arquivo_contrato", "arquivo_termo_aditivo"):
            self.fields[nome].validators.append(validar_pdf)
        self.fields["fornecedor"].queryset = Fornecedor.objects.order_by("razao_social")


class ConfiguracaoCoffeeBreakForm(FormularioCadastroVersionado):
    class Meta:
        model = ConfiguracaoCoffeeBreak
        fields = (
            "oficio_vocativo",
            "oficio_assinante",
            "oficio_cargo_assinante",
            "oficio_destinatario",
            "eprotocolo_assunto",
            "eprotocolo_palavras_chave",
            "despacho_destino",
        )


class LoteCoffeeBreakForm(FormularioCadastroVersionado):
    class Meta:
        model = LoteCoffeeBreak
        fields = (
            "contrato",
            "numero",
            "exercicio",
            "quantidade_total",
            "empenho",
            "municipios",
            "municipios_texto",
            "orientacoes",
            "especificacoes_tecnicas",
            "observacoes",
            "ativo",
        )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["contrato"].queryset = ContratoCoffeeBreak.objects.select_related(
            "fornecedor"
        ).order_by("numero")
        self.fields["municipios"].queryset = self.fields["municipios"].queryset.select_related(
            "estado"
        ).order_by("nome", "estado__sigla")

    def clean_quantidade_total(self):
        quantidade = self.cleaned_data["quantidade_total"]
        if self.instance.pk:
            from .models import soma_consumida

            consumido = soma_consumida(self.instance.solicitacoes.filter(cancelada=False))
            if quantidade < consumido:
                raise forms.ValidationError(
                    f"O lote já consumiu {consumido} unidades; a capacidade não pode ficar abaixo disso."
                )
        return quantidade


class CertidaoForm(forms.Form):
    """Envio de uma certidão: o PDF e, se o sistema não conseguir ler, a validade."""

    tipo = forms.ChoiceField(choices=CertidaoFornecedor._meta.get_field("tipo").choices)
    arquivo = forms.FileField(label="Certidão (PDF)", validators=[validar_pdf])
    validade = forms.DateField(
        label="Válida até", required=False,
        help_text="Em branco, o sistema lê a validade do PDF.",
    )

    def clean(self):
        dados = super().clean()
        arquivo = dados.get("arquivo")
        if arquivo and not dados.get("validade"):
            lida = certidoes.validade_do_pdf(arquivo)
            if lida is None:
                self.add_error(
                    "validade",
                    "Não consegui ler a validade neste PDF; informe a data.",
                )
            else:
                dados["validade"] = lida
                self.validade_lida = True
        return dados
