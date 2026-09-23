"""A ordem de serviço do Coffee Break no editor de documentos de Viagens.

É o mesmo editor dos ofícios (`documentos/editor/`): a barra (desfazer,
zoom, Campos, Imprimir, "Tudo salvo"), o aviso de pendências e a folha A4
editável. Tudo na folha se edita, como no ofício: o que vem da solicitação
(número, data, objeto, pedido, local, responsável) muda a solicitação; o que
vem dos cadastros (fornecedor, contrato, fiscal, empenho) muda o cadastro —
só para quem administra os cadastros; e o texto do modelo (cabeçalho,
rótulos, rodapé) é bloco documental, que vale só para esta OS. O PDF (o
modelo da OS 41/2026, em `coffee_break/documentos/ordem_servico.html`) sai
com o que foi editado, inclusive as quebras de página.

O tipo não entra em `DocumentoTipo`: a OS do Coffee Break não passa pela
cadeia de geração de Viagens (DOCX, cache), só pelo editor. O registro é
feito no `ready()` do app (`registrar()`).
"""

from __future__ import annotations

from enum import Enum

from django.urls import reverse

from documentos.editor.blocos import BlocoDocumental, PontoDeQuebra
from documentos.editor.campos import CampoEditavel, Parte
from documentos.editor.vinculos import FonteBase, VinculoBase, _gravar_recorte, _historico


class TipoCoffee(str, Enum):
    ORDEM_SERVICO = "coffee_break_ordem_servico"


CHAVE_OS = TipoCoffee.ORDEM_SERVICO.value

_CADASTRO = "Muda o cadastro, em todas as OS deste {}."

CAMPOS_OS = (
    CampoEditavel("cb_numero", "Número da OS", (
        Parte("numero", "texto", "Número da OS", ajuda="Só a sequência (42) ou com o ano (42/2026). Não se repete."),
    ), origem="documento"),
    CampoEditavel("cb_data", "Data da OS", (Parte("data_solicitacao", "data", "Data da solicitação"),), origem="documento",
                  ajuda="É a data da solicitação; muda também na etapa 1."),
    CampoEditavel("cb_objeto", "Objeto", (Parte("descricao_evento", "texto", "Descrição do evento"),), origem="documento",
                  ajuda="A descrição do evento da solicitação."),
    CampoEditavel("cb_detalhamento", "Detalhamento do pedido", (
        Parte("detalhamento_pedido", "texto_longo", "Detalhamento do pedido", linhas=4),
    ), origem="documento", ajuda="Apagar o texto volta ao automático, feito da data, do horário e da quantidade."),
    CampoEditavel("cb_local", "Local de entrega", (Parte("local_entrega", "texto", "Local de entrega"),), origem="documento"),
    CampoEditavel("cb_responsavel", "Responsável pelo recebimento", (
        Parte("responsavel_recebimento", "texto", "Responsável pelo recebimento"),
    ), origem="documento"),
    CampoEditavel("cb_fornecedor", "Fornecedor", (Parte("razao_social", "texto", "Razão social"),), origem="fornecedor",
                  ajuda=_CADASTRO.format("fornecedor")),
    CampoEditavel("cb_contrato", "Contrato", (
        Parte("numero", "texto", "Número do contrato"),
        Parte("numero_gms", "texto", "Número GMS"),
        Parte("termo_aditivo", "texto", "Termo aditivo"),
    ), origem="contrato", ajuda=_CADASTRO.format("contrato")),
    CampoEditavel("cb_fiscal", "Fiscal do contrato", (Parte("fiscal_responsavel", "texto", "Fiscal do contrato"),),
                  origem="contrato", ajuda=_CADASTRO.format("contrato")),
    CampoEditavel("cb_cargo_fiscal", "Cargo do fiscal", (Parte("cargo_fiscal", "texto", "Cargo do fiscal"),),
                  origem="contrato", ajuda=_CADASTRO.format("contrato")),
    CampoEditavel("cb_empenho", "Empenho", (Parte("empenho", "texto", "Empenho"),), origem="lote",
                  ajuda=_CADASTRO.format("lote")),
)

_SO_ESTA = "Texto do modelo. O texto alterado vale só para esta OS."

BLOCOS_OS = tuple(
    BlocoDocumental(chave, rotulo, padrao, ajuda=_SO_ESTA)
    for chave, rotulo, padrao in (
        ("cb_secretaria", "Cabeçalho — secretaria", "SECRETARIA DE ESTADO DA SEGURANÇA PÚBLICA"),
        ("cb_orgao", "Cabeçalho — órgão", "POLÍCIA CIVIL DO PARANÁ"),
        ("cb_unidade", "Cabeçalho — unidade", "ASSESSORIA DE COMUNICAÇÃO SOCIAL"),
        ("cb_cidade", "Cidade da data", "Curitiba"),
        ("cb_titulo", "Título", "ORDEM DE SERVIÇO"),
        ("cb_rotulo_contrato", "Rótulo do contrato", "Contrato:"),
        ("cb_rotulo_empenho", "Rótulo do empenho", "Empenho:"),
        ("cb_rotulo_objeto", "Rótulo do objeto", "OBJETO:"),
        ("cb_rotulo_detalhamento", "Rótulo do detalhamento", "DETALHAMENTO DO PEDIDO:"),
        ("cb_rotulo_local", "Rótulo do local de entrega", "LOCAL DE ENTREGA:"),
        ("cb_rotulo_responsavel", "Rótulo do responsável", "RESPONSÁVEL PELO RECEBIMENTO:"),
        ("cb_linha_assinatura", "Linha da assinatura", "______________________________________________"),
        ("cb_rodape_endereco", "Rodapé — endereço", "Avenida Iguaçu, 470 – Rebouças – Curitiba/PR—CEP: 80.230-020"),
        ("cb_rodape_contato", "Rodapé — contato", "Fone: (41) 3235-6477 – e-mail:\u00a0 comunicacao@pc.pr.gov.br"),
    )
)

QUEBRAS_OS = (
    PontoDeQuebra("antes_objeto", "Antes do objeto"),
    PontoDeQuebra("antes_local", "Antes do local de entrega"),
    PontoDeQuebra("antes_assinatura", "Antes da assinatura"),
)

# Dados do pedido que a nota fiscal trava (como na etapa 1).
CAMPOS_BASE = ("numero", "data_solicitacao", "descricao_evento")


def versao_da_solicitacao(solicitacao) -> str:
    """A mesma versão do campo oculto da tela (`versao` do formulário), para
    o documento e o formulário da etapa 1 falarem da mesma coisa."""
    momento = solicitacao.atualizado_em
    return str(int(momento.timestamp() * 1_000_000)) if momento else ""


class FonteSolicitacaoCoffee(FonteBase):
    CAMPOS = ("numero", "data_solicitacao", "descricao_evento", "detalhamento_pedido", "local_entrega", "responsavel_recebimento")

    def versao(self, alvo):
        return versao_da_solicitacao(alvo)

    def form(self, alvo, dados=None):
        from django import forms

        from .models import SolicitacaoCoffeeBreak

        travados = CAMPOS_BASE if alvo.financeiro_iniciado else ()

        class Form(forms.ModelForm):
            class Meta:
                model = SolicitacaoCoffeeBreak
                fields = list(FonteSolicitacaoCoffee.CAMPOS)

            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs)
                for nome in travados:
                    self.fields[nome].disabled = True

            def clean_descricao_evento(self):
                # Uma linha só, como no formulário da etapa 1.
                texto = " ".join((self.cleaned_data.get("descricao_evento") or "").split())
                if not texto:
                    raise forms.ValidationError("Informe a descrição do evento.")
                return texto

            def clean_numero(self):
                from . import services

                numero = " ".join((self.cleaned_data.get("numero") or "").split())
                if not numero:
                    raise forms.ValidationError("Informe o número da OS.")
                if numero.isdigit():
                    atual = services.partes_numero(alvo.numero)
                    ano = atual[1] if atual else (alvo.data_solicitacao.year if alvo.data_solicitacao else None)
                    if int(numero) < 1 or ano is None:
                        raise forms.ValidationError("O número da OS deve ser 1 ou mais.")
                    numero = services.formatar_numero(int(numero), ano)
                if numero != alvo.numero and services.numero_em_uso(numero, excluir_pk=alvo.pk):
                    partes = services.partes_numero(numero)
                    livre = f" A próxima livre é {services.proxima_sequencia(partes[1])}." if partes else ""
                    raise forms.ValidationError(f"A OS {numero} já existe.{livre}")
                return numero

            def clean_local_entrega(self):
                return " ".join((self.cleaned_data.get("local_entrega") or "").split())

            def clean_responsavel_recebimento(self):
                return " ".join((self.cleaned_data.get("responsavel_recebimento") or "").split())

            def clean_detalhamento_pedido(self):
                return (self.cleaned_data.get("detalhamento_pedido") or "").strip()

            def clean(self):
                dados = super().clean()
                for nome in travados:
                    if nome in self.data and str(self.data[nome]) != str(self.initial.get(nome) or ""):
                        self.add_error(nome, "A nota fiscal já foi registrada: este dado não muda mais.")
                return dados

        return Form(dados, instance=alvo)

    def gravar(self, form, nomes, alvo):
        return _gravar_recorte(form, nomes)

    def links(self, definicao, solicitacao, alvo):
        return [{"rotulo": "Abrir a etapa 1", "url": reverse("coffee_break:editar", args=[solicitacao.pk])}]


class FonteCadastroCoffee(FonteBase):
    """Um cadastro que a OS mostra (o fornecedor, o contrato ou o lote da
    solicitação): editar na folha muda o cadastro. Só quem administra os
    cadastros do módulo, como na tela de Cadastros."""

    def __init__(self, vinculo, caminho, campos):
        super().__init__(vinculo)
        self.caminho = caminho
        self.campos = campos

    def alvo(self, solicitacao, objeto_id, usuario):
        from django.http import Http404

        alvo = self.caminho(solicitacao)
        if alvo is None:
            raise Http404("A solicitação ainda não tem este cadastro.")
        return alvo

    def pode_editar(self, usuario, solicitacao):
        from solicitacoes.permissions import eh_administrador

        return eh_administrador(usuario) and self.vinculo.pode_editar(usuario, solicitacao)

    def form(self, alvo, dados=None):
        from django import forms

        campos = self.campos

        class Form(forms.ModelForm):
            class Meta:
                model = type(alvo)
                fields = list(campos)

            def clean(self):
                dados = super().clean()
                for nome in campos:
                    if isinstance(dados.get(nome), str):
                        dados[nome] = " ".join(dados[nome].split())
                return dados

        return Form(dados, instance=alvo)

    def links(self, definicao, solicitacao, alvo):
        return []


class VinculoCoffeeOS(VinculoBase):
    tipo = TipoCoffee.ORDEM_SERVICO
    rotulo_voltar = "Voltar à solicitação"

    def montar_fontes(self):
        lote = lambda s: s.lote if s.lote_id else None  # noqa: E731
        contrato = lambda s: s.lote.contrato if s.lote_id else None  # noqa: E731
        return {
            "documento": FonteSolicitacaoCoffee(self),
            "fornecedor": FonteCadastroCoffee(self, lambda s: s.lote.contrato.fornecedor if s.lote_id else None, ("razao_social",)),
            "contrato": FonteCadastroCoffee(self, contrato, ("numero", "numero_gms", "termo_aditivo", "fiscal_responsavel", "cargo_fiscal")),
            "lote": FonteCadastroCoffee(self, lote, ("empenho",)),
        }

    def carregar(self, pk, variante=""):
        from django.shortcuts import get_object_or_404

        from .models import SolicitacaoCoffeeBreak

        return get_object_or_404(SolicitacaoCoffeeBreak.objects.select_related("lote__contrato__fornecedor"), pk=pk)

    def pode_ver(self, usuario):
        from .permissions import pode_acessar

        return pode_acessar(usuario)

    def cancelado(self, solicitacao):
        return bool(solicitacao.cancelada or solicitacao.concluida)

    def pode_editar(self, usuario, solicitacao):
        return self.pode_ver(usuario) and not self.cancelado(solicitacao)

    def origens_editaveis(self, usuario):
        from solicitacoes.permissions import eh_administrador

        # Os cadastros (fornecedor, contrato, lote) são da administração do módulo.
        return set(self.fontes) if eh_administrador(usuario) else {"documento"}

    def versao(self, solicitacao):
        return versao_da_solicitacao(solicitacao)

    def contexto(self, solicitacao, *, modo, campos_editaveis):
        return contexto_da_folha(solicitacao, modo=modo, campos_editaveis=campos_editaveis)

    def rotulo(self, solicitacao):
        return f"Ordem de Serviço {solicitacao.numero}".strip()

    def situacao(self, solicitacao):
        if solicitacao.cancelada:
            return "Cancelada"
        return "Concluída" if solicitacao.concluida else ""

    def subtitulo(self, solicitacao):
        return solicitacao.descricao_evento

    def url_voltar(self, solicitacao):
        return reverse("coffee_break:editar", args=[solicitacao.pk])

    def url_pdf(self, solicitacao):
        return reverse("coffee_break:ordem_servico", args=[solicitacao.pk])

    def pendencias(self, solicitacao):
        from .documentos import pendencias_ordem_servico

        return pendencias_ordem_servico(solicitacao)

    def pode_emitir(self, usuario, solicitacao):
        # Cancelada ou concluída não se edita, mas a OS ainda se imprime.
        return self.pode_ver(usuario) and not self.pendencias(solicitacao)

    def historico(self, solicitacao):
        blocos = list(solicitacao.blocos_documentais.values_list("pk", flat=True))
        return _historico([("coffee_break.solicitacaocoffeebreak", [solicitacao.pk]), ("documentos.documentobloco", blocos)])


def contexto_da_folha(solicitacao, *, modo="editor", campos_editaveis=None):
    """O que a folha da OS recebe; aceita solicitação ainda não salva (a nova
    solicitação: sem lote enquanto o município não foi escolhido)."""
    from django.templatetags.static import static
    from django.utils import timezone

    from documentos.services.document_blocks import conteudo_documental
    from documentos.services.document_context import _do_editor

    from .documentos import data_extenso

    lote = solicitacao.lote if solicitacao.lote_id else None
    contrato = lote.contrato if lote else None
    return {
        "s": solicitacao,
        "lote": lote,
        "contrato": contrato,
        "fornecedor": contrato.fornecedor if contrato else None,
        "data_extenso": data_extenso(solicitacao.data_solicitacao or timezone.localdate()),
        "institucional": {"nome_orgao": "POLÍCIA CIVIL DO PARANÁ", "unidade_cabecalho": "ASSESSORIA DE COMUNICAÇÃO SOCIAL"},
        "imagens": {"brasao": static("img/brasao-pcpr-timbre.png"), "marca": static("img/marca-pcpr-timbre.png")},
        **_do_editor(TipoCoffee.ORDEM_SERVICO, {"documento": conteudo_documental(TipoCoffee.ORDEM_SERVICO, solicitacao)}, campos_editaveis, None),
        "modo": modo,
    }


def folha_da_nova(dados):
    """A folha da OS de uma solicitação que ainda está sendo preenchida: o
    formulário da nova solicitação, com os valores digitados, sem gravar."""
    from documentos.services.pdf_renderer import renderizar_html

    from . import services
    from .forms import PedidoCoffeeBreakForm

    form = PedidoCoffeeBreakForm(dados)
    form.is_valid()  # só para montar a instância; erros não impedem a prévia
    solicitacao = form.instance
    for nome in ("descricao_evento", "local_entrega", "responsavel_recebimento", "detalhamento_pedido"):
        if not getattr(solicitacao, nome, "") and dados.get(nome):
            setattr(solicitacao, nome, " ".join(str(dados.get(nome)).split()) if nome != "detalhamento_pedido" else dados.get(nome).strip())
    if not solicitacao.numero:
        from django.utils import timezone

        ano = (solicitacao.data_solicitacao or timezone.localdate()).year
        solicitacao.numero = services.proximo_numero(ano)
    return renderizar_html(TipoCoffee.ORDEM_SERVICO, contexto_da_folha(solicitacao), modo="editor")


def registrar():
    """Liga a OS ao editor: o vínculo, os campos e o módulo que dá acesso às
    rotas do editor para este tipo (as demais seguem sendo de Viagens)."""
    from accounts.modulos import registrar_documento
    from documentos.editor import blocos, campos, vinculos

    from .permissions import CODIGO_MODULO

    vinculo = VinculoCoffeeOS()
    vinculos.VINCULOS[vinculo.chave] = vinculo
    campos.REGISTRO[vinculo.chave] = {campo.chave: campo for campo in CAMPOS_OS}
    blocos.REGISTRO_BLOCOS[vinculo.tipo] = {bloco.chave: bloco for bloco in BLOCOS_OS}
    blocos.REGISTRO_QUEBRAS[vinculo.tipo] = {ponto.chave: ponto for ponto in QUEBRAS_OS}
    registrar_documento("documentos", vinculo.chave, CODIGO_MODULO)
