"""Os documentos do Coffee Break no editor de documentos de Viagens.

É o mesmo editor dos ofícios (`documentos/editor/`): a barra (desfazer,
zoom, Campos, Quebras de página, Imprimir, "Tudo salvo"), o aviso de
pendências e a folha A4 editável. Três documentos: a ordem de serviço
(etapa 1), o ofício ao GAF e o certifico digital (etapa 2).

Tudo na folha se edita, como no ofício de Viagens:
- o que vem da solicitação (números, datas, objeto, pedido, local, nota
  fiscal...) muda a solicitação;
- o que vem dos cadastros (fornecedor, contrato, lote e a configuração do
  ofício) muda o cadastro — só para quem administra os cadastros do módulo;
- o texto do modelo (cabeçalho, rótulos, parágrafos, rodapé) é bloco
  documental, que vale só para aquele documento daquela solicitação;
- e há pontos de quebra de página.

Os PDFs (os modelos medidos do processo 26.617.058-0, em
`templates/coffee_break/documentos/`) saem com o que foi editado.

Os tipos não entram em `DocumentoTipo`: não passam pela cadeia de geração
de Viagens (DOCX, cache), só pelo editor. O registro é feito no `ready()` do
app (`registrar()`).
"""

from __future__ import annotations

from enum import Enum

from django.urls import reverse

from documentos.editor.blocos import BlocoDocumental, PontoDeQuebra
from documentos.editor.campos import CampoEditavel, Parte
from documentos.editor.vinculos import FonteBase, VinculoBase, _gravar_recorte, _historico


class TipoCoffee(str, Enum):
    ORDEM_SERVICO = "coffee_break_ordem_servico"
    OFICIO = "coffee_break_oficio"
    CERTIFICO = "coffee_break_certifico"


CHAVE_OS = TipoCoffee.ORDEM_SERVICO.value
CHAVE_OFICIO = TipoCoffee.OFICIO.value
CHAVE_CERTIFICO = TipoCoffee.CERTIFICO.value

# ---------------------------------------------------------------------------
# Campos (o que vem de um registro)
# ---------------------------------------------------------------------------

_CADASTRO = "Muda o cadastro, em todos os documentos deste {}."
_CONFIG = "Muda a configuração do ofício, em todos os ofícios do Coffee Break."


def _texto(chave, rotulo, nome, origem="documento", ajuda="", tipo="texto", **parte):
    return CampoEditavel(chave, rotulo, (Parte(nome, tipo, rotulo, **parte),), origem=origem, ajuda=ajuda)


C_NUMERO_OS = _texto("cb_numero", "Número da OS", "numero",
                     ajuda="Só a sequência (42) ou com o ano (42/2026). Não se repete.")
C_DATA_OS = CampoEditavel("cb_data", "Data da OS", (Parte("data_solicitacao", "data", "Data da solicitação"),),
                          origem="documento", ajuda="É a data da solicitação; muda também na etapa 1.")
C_OBJETO = _texto("cb_objeto", "Objeto", "descricao_evento", ajuda="A descrição do evento da solicitação.")
C_DETALHAMENTO = _texto("cb_detalhamento", "Detalhamento do pedido", "detalhamento_pedido", tipo="texto_longo", linhas=4,
                        ajuda="Apagar o texto volta ao automático, feito da data, do horário e da quantidade.")
C_LOCAL = _texto("cb_local", "Local de entrega", "local_entrega")
C_RESPONSAVEL = _texto("cb_responsavel", "Responsável pelo recebimento", "responsavel_recebimento")
C_NOTA = _texto("cb_nota", "Número da nota fiscal", "numero_nota_fiscal")
C_NUMERO_OFICIO = _texto("cb_oficio_numero", "Número do ofício", "numero_oficio",
                         ajuda="Só a sequência (125) ou com o ano (125/2026). Não se repete.")
C_DATA_OFICIO = CampoEditavel("cb_oficio_data", "Data do ofício", (Parte("data_oficio", "data", "Data do ofício"),),
                              origem="documento")
C_PROTOCOLO_PCPR = _texto("cb_oficio_protocolo", "PCPR protocolo n.º", "protocolo_pcpr_oficio")

C_FORNECEDOR = _texto("cb_fornecedor", "Fornecedor", "razao_social", origem="fornecedor", ajuda=_CADASTRO.format("fornecedor"))
C_CNPJ = _texto("cb_cnpj", "CNPJ do fornecedor", "cnpj", origem="fornecedor", ajuda=_CADASTRO.format("fornecedor"))
C_CONTRATO = CampoEditavel("cb_contrato", "Contrato", (
    Parte("numero", "texto", "Número do contrato"),
    Parte("numero_gms", "texto", "Número GMS"),
    Parte("termo_aditivo", "texto", "Termo aditivo"),
), origem="contrato", ajuda=_CADASTRO.format("contrato"))
C_CONTRATO_NUMERO = _texto("cb_contrato_numero", "Número do contrato", "numero", origem="contrato",
                           ajuda=_CADASTRO.format("contrato"))
C_CLAUSULA = _texto("cb_clausula", "Cláusula de pagamento", "clausula_pagamento", origem="contrato",
                    ajuda=_CADASTRO.format("contrato"))
C_FISCAL = _texto("cb_fiscal", "Fiscal do contrato", "fiscal_responsavel", origem="contrato", ajuda=_CADASTRO.format("contrato"))
C_CARGO_FISCAL = _texto("cb_cargo_fiscal", "Cargo do fiscal", "cargo_fiscal", origem="contrato", ajuda=_CADASTRO.format("contrato"))
C_EMPENHO = _texto("cb_empenho", "Empenho", "empenho", origem="lote", ajuda=_CADASTRO.format("lote"))

C_VOCATIVO = _texto("cb_vocativo", "Vocativo", "oficio_vocativo", origem="configuracao", ajuda=_CONFIG)
C_ASSINANTE = _texto("cb_assinante", "Quem assina", "oficio_assinante", origem="configuracao", ajuda=_CONFIG)
C_CARGO_ASSINANTE = _texto("cb_cargo_assinante", "Cargo de quem assina", "oficio_cargo_assinante", origem="configuracao",
                           ajuda=_CONFIG)
C_DESTINATARIO = _texto("cb_destinatario", "Destinatário", "oficio_destinatario", origem="configuracao",
                        tipo="texto_longo", linhas=5, ajuda=_CONFIG)

CAMPOS_OS = (
    C_NUMERO_OS, C_DATA_OS, C_OBJETO, C_DETALHAMENTO, C_LOCAL, C_RESPONSAVEL,
    C_FORNECEDOR, C_CONTRATO, C_FISCAL, C_CARGO_FISCAL, C_EMPENHO,
)
CAMPOS_OFICIO = (
    C_NUMERO_OFICIO, C_DATA_OFICIO, C_PROTOCOLO_PCPR, C_OBJETO, C_NOTA,
    C_CONTRATO, C_CLAUSULA, C_VOCATIVO, C_ASSINANTE, C_CARGO_ASSINANTE, C_DESTINATARIO,
)
CAMPOS_CERTIFICO = (
    C_NOTA, C_FORNECEDOR, C_CNPJ, C_CONTRATO, C_CONTRATO_NUMERO, C_FISCAL, C_CARGO_FISCAL,
)

# ---------------------------------------------------------------------------
# Blocos (o texto do modelo) e quebras de página
# ---------------------------------------------------------------------------

_SO_ESTE = "Texto do modelo. O texto alterado vale só para este documento."


def _blocos(*trios):
    return tuple(BlocoDocumental(chave, rotulo, padrao, ajuda=_SO_ESTE) for chave, rotulo, padrao in trios)


_TIMBRE = (
    ("cb_secretaria", "Cabeçalho — secretaria", "SECRETARIA DE ESTADO DA SEGURANÇA PÚBLICA"),
    ("cb_orgao", "Cabeçalho — órgão", "POLÍCIA CIVIL DO PARANÁ"),
    ("cb_unidade", "Cabeçalho — unidade", "ASSESSORIA DE COMUNICAÇÃO SOCIAL"),
)
# O rodapé da OS e do certifico (o do ofício do processo é com hífens).
_RODAPE = (
    ("cb_rodape_endereco", "Rodapé — endereço", "Avenida Iguaçu, 470 – Rebouças – Curitiba/PR—CEP: 80.230-020"),
    ("cb_rodape_contato", "Rodapé — contato", "Fone: (41) 3235-6477 – e-mail:  comunicacao@pc.pr.gov.br"),
)

BLOCOS_OS = _blocos(
    *_TIMBRE, *_RODAPE,
    ("cb_cidade", "Cidade da data", "Curitiba"),
    ("cb_titulo", "Título", "ORDEM DE SERVIÇO"),
    ("cb_rotulo_contrato", "Rótulo do contrato", "Contrato:"),
    ("cb_rotulo_empenho", "Rótulo do empenho", "Empenho:"),
    ("cb_rotulo_objeto", "Rótulo do objeto", "OBJETO:"),
    ("cb_rotulo_detalhamento", "Rótulo do detalhamento", "DETALHAMENTO DO PEDIDO:"),
    ("cb_rotulo_local", "Rótulo do local de entrega", "LOCAL DE ENTREGA:"),
    ("cb_rotulo_responsavel", "Rótulo do responsável", "RESPONSÁVEL PELO RECEBIMENTO:"),
    ("cb_linha_assinatura", "Linha da assinatura", "______________________________________________"),
)
QUEBRAS_OS = (
    PontoDeQuebra("antes_objeto", "Antes do objeto"),
    PontoDeQuebra("antes_local", "Antes do local de entrega"),
    PontoDeQuebra("antes_assinatura", "Antes da assinatura"),
)

BLOCOS_OFICIO = _blocos(
    *_TIMBRE,
    ("cb_rodape_endereco", "Rodapé — endereço", "Avenida Iguaçu, 470 - Rebouças - Curitiba/PR - CEP: 80230-020"),
    ("cb_rodape_contato", "Rodapé — contato", "Fone: (41) 3235-6477 - e-mail: comunicacao@pc.pr.gov.br"),
    ("cb_titulo", "Título", "OFÍCIO"),
    ("cb_rotulo_protocolo", "Rótulo do protocolo PCPR", "PCPR Protocolo n.º:"),
    ("cb_cidade", "Cidade da data", "Curitiba"),
    ("cb_paragrafo_entrega", "Primeiro parágrafo",
     "Venho, por meio deste, informar e certificar que os serviços de Coffee Break foram devidamente entregues, "
     "conforme solicitado, para o seguinte evento:"),
    ("cb_item_marcador", "Marcador do evento", "•"),
    ("cb_item_coffee", "Texto do evento", "- Coffee Break para"),
    ("cb_item_pessoas", "Fim do item", "pessoas."),
    ("cb_encaminho", "Encaminhamento — começo", "Encaminho, em anexo, a Nota Fiscal n°"),
    ("cb_encaminho_meio", "Encaminhamento — meio",
     ", devidamente atestada, juntamente com os demais documentos necessários, para que seja efetuado o pagamento "
     "ao CONTRATADO, nos termos da"),
    ("cb_encaminho_contrato", "Encaminhamento — contrato", ", do CONTRATO"),
    ("cb_fecho", "Fecho", "Atenciosamente,"),
)
QUEBRAS_OFICIO = (
    PontoDeQuebra("antes_encaminho", "Antes do encaminhamento"),
    PontoDeQuebra("antes_assinatura", "Antes da assinatura"),
    PontoDeQuebra("antes_destinatario", "Antes do destinatário"),
)

BLOCOS_CERTIFICO = _blocos(
    *_TIMBRE, *_RODAPE,
    ("cb_titulo", "Título", "CERTIFICO DIGITAL"),
    ("cb_nota_rotulo", "Nota — começo", "Nota Fiscal nº"),
    ("cb_nota_emitida", "Nota — empresa", ", emitida pela empresa"),
    ("cb_nota_cnpj", "Nota — CNPJ", ", inscrita no CNPJ nº"),
    ("cb_nota_contrato", "Nota — contrato", "(CONTRATO"),
    ("cb_nota_fim", "Nota — fim", ")."),
    ("cb_atesto_rotulo", "Atesto — palavra", "ATESTO"),
    ("cb_atesto_texto", "Atesto — texto",
     "que os serviços e/ou bens acima identificados foram devidamente executados/entregues e atendem às "
     "exigências especificadas no (Termo de Referência/Edital)."),
    ("cb_assinado", "Assinatura digital", "(assinado e datado digitalmente)"),
    ("cb_fiscal_rotulo", "Fiscal — rótulo", "Fiscal do Contrato n°"),
)
QUEBRAS_CERTIFICO = (PontoDeQuebra("antes_atesto", "Antes do atesto"),)


def textos_do_documento(tipo, solicitacao):
    """O texto em vigor de cada bloco (`b`) e as quebras, para os PDFs."""
    from documentos.services.document_blocks import conteudo_documental

    documental = conteudo_documental(tipo, solicitacao)
    textos = {
        chave: bloco["padrao"] if bloco["conteudo"] is None else bloco["conteudo"]
        for chave, bloco in documental["blocos"].items()
    }
    return textos, set(documental["quebras"])


# ---------------------------------------------------------------------------
# Fontes (onde o dado mora)
# ---------------------------------------------------------------------------

# Dados do pedido que a nota fiscal trava (como na etapa 1).
CAMPOS_BASE = ("numero", "data_solicitacao", "descricao_evento")


def versao_da_solicitacao(solicitacao) -> str:
    """A mesma versão do campo oculto da tela (`versao` do formulário), para
    o documento e o formulário da etapa falarem da mesma coisa."""
    momento = solicitacao.atualizado_em
    return str(int(momento.timestamp() * 1_000_000)) if momento else ""


def _uma_linha(valor):
    return " ".join((valor or "").split())


def _numero_com_ano(forms, numero, atual, data, repetido, rotulo):
    """"42" vira "42/AAAA" (o ano do número atual, senão o da data); não repete."""
    from . import services

    numero = _uma_linha(numero)
    if not numero:
        raise forms.ValidationError(f"Informe o número {rotulo}.")
    if numero.isdigit():
        partes = services.partes_numero(atual)
        ano = partes[1] if partes else (data.year if data else None)
        if int(numero) < 1 or ano is None:
            raise forms.ValidationError(f"O número {rotulo} deve ser 1 ou mais.")
        numero = services.formatar_numero(int(numero), ano)
    if numero != atual and repetido(numero):
        raise forms.ValidationError(f"O número {numero} já existe.")
    return numero


class FonteSolicitacaoCoffee(FonteBase):
    CAMPOS = (
        "numero", "data_solicitacao", "descricao_evento", "detalhamento_pedido", "local_entrega",
        "responsavel_recebimento", "numero_nota_fiscal", "numero_oficio", "data_oficio", "protocolo_pcpr_oficio",
    )

    def versao(self, alvo):
        return versao_da_solicitacao(alvo)

    def form(self, alvo, dados=None):
        from django import forms
        from django.utils import timezone

        from django.core.exceptions import NON_FIELD_ERRORS

        from . import services
        from .models import SolicitacaoCoffeeBreak

        travados = CAMPOS_BASE if alvo.financeiro_iniciado else ()

        class Form(forms.ModelForm):
            class Meta:
                model = SolicitacaoCoffeeBreak
                fields = list(FonteSolicitacaoCoffee.CAMPOS)

            def _update_errors(self, errors):
                # Erro do modelo num campo que o documento não tem sobe para o topo.
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

            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs)
                for campo in self.fields.values():
                    campo.required = False
                for nome in travados:
                    self.fields[nome].disabled = True

            def clean_numero(self):
                return _numero_com_ano(
                    forms, self.cleaned_data.get("numero"), alvo.numero, alvo.data_solicitacao,
                    lambda n: services.numero_em_uso(n, excluir_pk=alvo.pk), "da OS",
                )

            def clean_numero_oficio(self):
                valor = self.cleaned_data.get("numero_oficio")
                if not _uma_linha(valor) and not alvo.numero_oficio:
                    return ""
                return _numero_com_ano(
                    forms, valor, alvo.numero_oficio, alvo.data_oficio or timezone.localdate(),
                    lambda n: SolicitacaoCoffeeBreak.objects.filter(numero_oficio=n).exclude(pk=alvo.pk).exists(),
                    "do ofício",
                )

            def clean_descricao_evento(self):
                # Uma linha só, como no formulário da etapa 1.
                texto = _uma_linha(self.cleaned_data.get("descricao_evento"))
                if not texto:
                    raise forms.ValidationError("Informe a descrição do evento.")
                return texto

            def clean_data_solicitacao(self):
                data = self.cleaned_data.get("data_solicitacao")
                if not data:
                    raise forms.ValidationError("Informe a data.")
                return data

            def clean_numero_nota_fiscal(self):
                numero = _uma_linha(self.cleaned_data.get("numero_nota_fiscal"))
                if not numero and alvo.protocolo_pagamento:
                    raise forms.ValidationError("O protocolo de pagamento já foi registrado: a nota não pode ficar em branco.")
                return numero

            def clean_local_entrega(self):
                return _uma_linha(self.cleaned_data.get("local_entrega"))

            def clean_responsavel_recebimento(self):
                return _uma_linha(self.cleaned_data.get("responsavel_recebimento"))

            def clean_protocolo_pcpr_oficio(self):
                return _uma_linha(self.cleaned_data.get("protocolo_pcpr_oficio"))

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
        return []


class FonteCadastroCoffee(FonteBase):
    """Um cadastro que o documento mostra (o fornecedor, o contrato ou o lote
    da solicitação, a configuração do ofício): editar na folha muda o
    cadastro. Só quem administra os cadastros do módulo, como na tela de
    Cadastros."""

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

        campos = list(self.campos)

        class Form(forms.ModelForm):
            class Meta:
                model = type(alvo)
                fields = campos

            def clean(self):
                dados = super().clean()
                for nome in campos:
                    valor = dados.get(nome)
                    if nome == "cnpj" and isinstance(valor, str):
                        # O CNPJ vem com pontos da folha; guarda-se só os dígitos.
                        dados[nome] = "".join(ch for ch in valor if ch.isdigit())
                    elif isinstance(valor, str) and nome != "oficio_destinatario":
                        dados[nome] = _uma_linha(valor)
                return dados

        return Form(dados, instance=alvo)

    def links(self, definicao, solicitacao, alvo):
        return []


def _lote(s):
    return s.lote if s.lote_id else None


def _contrato(s):
    return s.lote.contrato if s.lote_id else None


def _fornecedor(s):
    return s.lote.contrato.fornecedor if s.lote_id else None


def _configuracao(s):
    from .models import ConfiguracaoCoffeeBreak

    return ConfiguracaoCoffeeBreak.atual()


# ---------------------------------------------------------------------------
# Vínculos
# ---------------------------------------------------------------------------


class VinculoCoffee(VinculoBase):
    """O que os três documentos têm em comum: a solicitação é o objeto, o
    módulo Coffee Break dá acesso e a folha é `documentos/pdf/<tipo>.html`."""

    rotulo_voltar = "Voltar à solicitação"
    tela = "coffee_break:editar"
    rota_pdf = ""

    def montar_fontes(self):
        return {
            "documento": FonteSolicitacaoCoffee(self),
            "fornecedor": FonteCadastroCoffee(self, _fornecedor, ("razao_social", "cnpj")),
            "contrato": FonteCadastroCoffee(self, _contrato, (
                "numero", "numero_gms", "termo_aditivo", "fiscal_responsavel", "cargo_fiscal", "clausula_pagamento",
            )),
            "lote": FonteCadastroCoffee(self, _lote, ("empenho",)),
            "configuracao": FonteCadastroCoffee(self, _configuracao, (
                "oficio_vocativo", "oficio_assinante", "oficio_cargo_assinante", "oficio_destinatario",
            )),
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

        # Os cadastros (fornecedor, contrato, lote, configuração) são da administração do módulo.
        return set(self.fontes) if eh_administrador(usuario) else {"documento"}

    def versao(self, solicitacao):
        return versao_da_solicitacao(solicitacao)

    def contexto(self, solicitacao, *, modo, campos_editaveis):
        return contexto_da_folha(self.tipo, solicitacao, modo=modo, campos_editaveis=campos_editaveis)

    def situacao(self, solicitacao):
        if solicitacao.cancelada:
            return "Cancelada"
        return "Concluída" if solicitacao.concluida else ""

    def subtitulo(self, solicitacao):
        return solicitacao.descricao_evento

    def url_voltar(self, solicitacao):
        return reverse(self.tela, args=[solicitacao.pk])

    def url_pdf(self, solicitacao):
        return reverse(self.rota_pdf, args=[solicitacao.pk])

    def pode_emitir(self, usuario, solicitacao):
        # Cancelada ou concluída não se edita, mas o documento ainda se imprime.
        return self.pode_ver(usuario) and not self.pendencias(solicitacao)

    def historico(self, solicitacao):
        blocos = list(solicitacao.blocos_documentais.filter(tipo_documento=self.tipo.value).values_list("pk", flat=True))
        return _historico([("coffee_break.solicitacaocoffeebreak", [solicitacao.pk]), ("documentos.documentobloco", blocos)])


class VinculoCoffeeOS(VinculoCoffee):
    tipo = TipoCoffee.ORDEM_SERVICO
    rota_pdf = "coffee_break:ordem_servico"

    def rotulo(self, solicitacao):
        return f"Ordem de Serviço {solicitacao.numero}".strip()

    def pendencias(self, solicitacao):
        from .documentos import pendencias_ordem_servico

        return pendencias_ordem_servico(solicitacao)


class VinculoCoffeeOficio(VinculoCoffee):
    tipo = TipoCoffee.OFICIO
    tela = "coffee_break:etapa_nota"
    rota_pdf = "coffee_break:oficio"

    def rotulo(self, solicitacao):
        return f"Ofício {solicitacao.numero_oficio}".strip()

    def pendencias(self, solicitacao):
        from .documentos import pendencias_oficio

        return pendencias_oficio(solicitacao)


class VinculoCoffeeCertifico(VinculoCoffee):
    tipo = TipoCoffee.CERTIFICO
    tela = "coffee_break:etapa_nota"
    rota_pdf = "coffee_break:certifico"

    def rotulo(self, solicitacao):
        return "Certifico digital"

    def pendencias(self, solicitacao):
        from .documentos import pendencias_certifico

        return pendencias_certifico(solicitacao)


# ---------------------------------------------------------------------------
# A folha
# ---------------------------------------------------------------------------

IMAGENS = {"brasao": "img/brasao-pcpr-timbre.png", "marca": "img/marca-pcpr-timbre.png"}


def contexto_da_folha(tipo, solicitacao, *, modo="editor", campos_editaveis=None):
    """O que a folha recebe; aceita solicitação ainda não salva (a nova
    solicitação: sem lote enquanto o município não foi escolhido)."""
    from django.templatetags.static import static
    from django.utils import timezone

    from documentos.services.document_blocks import conteudo_documental
    from documentos.services.document_context import _do_editor

    from .documentos import data_extenso, data_extenso_oficio
    from .models import ConfiguracaoCoffeeBreak

    lote = solicitacao.lote if solicitacao.lote_id else None
    contrato = lote.contrato if lote else None
    contexto = {
        "s": solicitacao,
        "lote": lote,
        "contrato": contrato,
        "fornecedor": contrato.fornecedor if contrato else None,
        "data_extenso": data_extenso(solicitacao.data_solicitacao or timezone.localdate()),
        "imagens": {nome: static(caminho) for nome, caminho in IMAGENS.items()},
        **_do_editor(tipo, {"documento": conteudo_documental(tipo, solicitacao)}, campos_editaveis, None),
        "modo": modo,
    }
    if tipo == TipoCoffee.OFICIO:
        from viagens_roteiros.services.valor_extenso import _numero_por_extenso

        contexto["config"] = ConfiguracaoCoffeeBreak.atual()
        contexto["data_oficio_extenso"] = data_extenso_oficio(solicitacao.data_oficio or timezone.localdate())
        contexto["quantidade_extenso"] = _numero_por_extenso(solicitacao.quantidade or 0)
        if not solicitacao.numero_oficio:
            # Antes de salvar a etapa, o número que o ofício vai receber (em cinza).
            from . import services

            ano = (solicitacao.data_oficio or timezone.localdate()).year
            contexto["numero_oficio_sugerido"] = services.formatar_numero(services.proxima_sequencia_oficio(ano), ano)
    return contexto


def folha_da_nova(dados):
    """A folha da OS de uma solicitação que ainda está sendo preenchida: o
    formulário da nova solicitação, com os valores digitados, sem gravar."""
    from django.utils import timezone

    from documentos.services.pdf_renderer import renderizar_html

    from . import services
    from .forms import PedidoCoffeeBreakForm

    form = PedidoCoffeeBreakForm(dados)
    form.is_valid()  # só para montar a instância; erros não impedem a prévia
    solicitacao = form.instance
    for nome in ("descricao_evento", "local_entrega", "responsavel_recebimento"):
        if not getattr(solicitacao, nome, "") and dados.get(nome):
            setattr(solicitacao, nome, _uma_linha(str(dados.get(nome))))
    if not solicitacao.numero:
        ano = (solicitacao.data_solicitacao or timezone.localdate()).year
        solicitacao.numero = services.proximo_numero(ano)
    return renderizar_html(TipoCoffee.ORDEM_SERVICO, contexto_da_folha(TipoCoffee.ORDEM_SERVICO, solicitacao), modo="editor")


# ---------------------------------------------------------------------------
# Registro no editor
# ---------------------------------------------------------------------------

DOCUMENTOS = (
    (VinculoCoffeeOS, CAMPOS_OS, BLOCOS_OS, QUEBRAS_OS),
    (VinculoCoffeeOficio, CAMPOS_OFICIO, BLOCOS_OFICIO, QUEBRAS_OFICIO),
    (VinculoCoffeeCertifico, CAMPOS_CERTIFICO, BLOCOS_CERTIFICO, QUEBRAS_CERTIFICO),
)


def registrar():
    """Liga os documentos ao editor: o vínculo, os campos, os blocos, as
    quebras e o módulo que dá acesso às rotas do editor para estes tipos (as
    demais seguem sendo de Viagens)."""
    from accounts.modulos import registrar_documento
    from documentos.editor import blocos, campos, vinculos

    from .permissions import CODIGO_MODULO

    for classe, campos_do_tipo, blocos_do_tipo, quebras_do_tipo in DOCUMENTOS:
        vinculo = classe()
        vinculos.VINCULOS[vinculo.chave] = vinculo
        campos.REGISTRO[vinculo.chave] = {campo.chave: campo for campo in campos_do_tipo}
        blocos.REGISTRO_BLOCOS[vinculo.tipo] = {bloco.chave: bloco for bloco in blocos_do_tipo}
        blocos.REGISTRO_QUEBRAS[vinculo.tipo] = {ponto.chave: ponto for ponto in quebras_do_tipo}
        registrar_documento("documentos", vinculo.chave, CODIGO_MODULO)
