"""A ordem de serviço do Coffee Break no editor de documentos de Viagens.

É o mesmo editor dos ofícios (`documentos/editor/`): a barra (desfazer,
zoom, Campos, Imprimir, "Tudo salvo"), o aviso de pendências e a folha A4
editável. Cada trecho editável da folha é um campo da solicitação — editar
no documento muda a solicitação, e o PDF (o modelo da OS 41/2026, em
`coffee_break/documentos/ordem_servico.html`) sai com o que foi editado.

O tipo não entra em `DocumentoTipo`: a OS do Coffee Break não passa pela
cadeia de geração de Viagens (DOCX, cache), só pelo editor. O registro é
feito no `ready()` do app (`registrar()`).
"""

from __future__ import annotations

from enum import Enum

from django.urls import reverse

from documentos.editor.campos import CampoEditavel, Parte
from documentos.editor.vinculos import FonteBase, VinculoBase, _gravar_recorte, _historico


class TipoCoffee(str, Enum):
    ORDEM_SERVICO = "coffee_break_ordem_servico"


CHAVE_OS = TipoCoffee.ORDEM_SERVICO.value

CAMPOS_OS = (
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
)

# Dados do pedido que a nota fiscal trava (como na etapa 1).
CAMPOS_BASE = ("data_solicitacao", "descricao_evento")


def versao_da_solicitacao(solicitacao) -> str:
    """A mesma versão do campo oculto da tela (`versao` do formulário), para
    o documento e o formulário da etapa 1 falarem da mesma coisa."""
    momento = solicitacao.atualizado_em
    return str(int(momento.timestamp() * 1_000_000)) if momento else ""


class FonteSolicitacaoCoffee(FonteBase):
    CAMPOS = ("data_solicitacao", "descricao_evento", "detalhamento_pedido", "local_entrega", "responsavel_recebimento")

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


class VinculoCoffeeOS(VinculoBase):
    tipo = TipoCoffee.ORDEM_SERVICO
    rotulo_voltar = "Voltar à solicitação"

    def montar_fontes(self):
        return {"documento": FonteSolicitacaoCoffee(self)}

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
        return set(self.fontes)

    def versao(self, solicitacao):
        return versao_da_solicitacao(solicitacao)

    def contexto(self, solicitacao, *, modo, campos_editaveis):
        from django.templatetags.static import static

        from documentos.services.document_context import _do_editor

        from .documentos import _contexto, data_extenso

        contexto = _contexto(solicitacao)
        contexto["data_extenso"] = data_extenso(solicitacao.data_solicitacao)
        return {
            **contexto,
            "institucional": {"nome_orgao": "POLÍCIA CIVIL DO PARANÁ", "unidade_cabecalho": "ASSESSORIA DE COMUNICAÇÃO SOCIAL"},
            "imagens": {"brasao": static("img/brasao-pcpr-timbre.png"), "marca": static("img/marca-pcpr-timbre.png")},
            **_do_editor(self.tipo, {}, campos_editaveis, None),
            "modo": modo,
        }

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
        return _historico([("coffee_break.solicitacaocoffeebreak", [solicitacao.pk])])


def registrar():
    """Liga a OS ao editor: o vínculo, os campos e o módulo que dá acesso às
    rotas do editor para este tipo (as demais seguem sendo de Viagens)."""
    from accounts.modulos import registrar_documento
    from documentos.editor import campos, vinculos

    from .permissions import CODIGO_MODULO

    vinculo = VinculoCoffeeOS()
    vinculos.VINCULOS[vinculo.chave] = vinculo
    campos.REGISTRO[vinculo.chave] = {campo.chave: campo for campo in CAMPOS_OS}
    registrar_documento("documentos", vinculo.chave, CODIGO_MODULO)
