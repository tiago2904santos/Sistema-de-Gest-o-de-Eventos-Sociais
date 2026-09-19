"""Ponte entre o editor e cada domínio que tem documento editável.

Um vínculo sabe carregar o objeto do documento, dizer quem pode editá-lo,
montar a folha no modo editor e dar à tela o nome, a volta, o PDF, as
pendências e o histórico. Cada trecho do documento tem uma **origem**
(documentos/editor/campos.py), e o vínculo entrega a **fonte** dela: onde o
dado mora, o formulário que já o valida no sistema (as regras de negócio
moram nele, e o editor não as duplica) e como gravar. Editar pelo documento
muda a origem: o ofício, o termo, o cadastro do servidor, a configuração do
setor, a linha do diário.

Há um vínculo por tipo de documento, e dois para o termo de autorização: o
do cadastro de termos e o tirado do ofício. Documento que é de uma pessoa
entre várias (o termo de cada servidor) tem **variante** (`?v=` na URL).
"""

from __future__ import annotations

from django.forms.models import model_to_dict
from django.http import Http404
from django.urls import NoReverseMatch, reverse

from documentos.services.types import DocumentoTipo


def _agora():
    from django.utils import timezone

    return timezone.now()


def _versao(objeto) -> str:
    momento = getattr(objeto, "atualizado_em", None)
    return momento.isoformat() if momento else ""


def _link(rotulo, nome, *args):
    try:
        return [{"rotulo": rotulo, "url": reverse(nome, args=list(args))}]
    except NoReverseMatch:
        return []


def _dados_do_modelo(instancia, campos):
    dados = model_to_dict(instancia, fields=campos)
    for nome, valor in list(dados.items()):
        if isinstance(valor, list):  # muitos-para-muitos vem como instâncias
            dados[nome] = [getattr(item, "pk", item) for item in valor]
        elif valor is None:
            dados[nome] = ""
    return dados


def _valor_da_opcao(chave) -> str:
    return str(getattr(chave, "value", chave))


def _opcoes_do_form(parte, form, valor):
    """Opções de uma parte de escolha, no formato dos componentes globais."""
    campo = form.fields[parte.nome]
    opcoes = [{"valor": _valor_da_opcao(chave), "rotulo": str(rotulo)} for chave, rotulo in campo.choices if _valor_da_opcao(chave) != ""]
    if parte.tipo == "escolha_multipla":
        escolhidos = {str(v) for v in (valor or [])}
        for opcao in opcoes:
            opcao["selecionado"] = opcao["valor"] in escolhidos
    return opcoes


def _opcoes_de_servidores(form, valor):
    from viagens_oficios.form_context import _opcoes_servidores

    escolhidos = {str(v) for v in (valor or [])}
    opcoes = _opcoes_servidores(form)
    for opcao in opcoes:
        opcao["selecionado"] = opcao["valor"] in escolhidos
    return opcoes


def _historico(filtros, limite=20):
    """Os últimos registros da trilha de auditoria sobre os registros dados
    (`[(modelo, [pks])]`), com os campos que mudaram — para a tela."""
    from django.db.models import Q

    from auditoria.models import RegistroAuditoria
    from viagens_oficios.views import CAMPOS_FORA_DO_HISTORICO

    filtro = Q(pk__in=[])
    for modelo, pks in filtros:
        pks = [str(pk) for pk in pks if pk]
        if pks:
            filtro |= Q(modelo=modelo, objeto_id__in=pks)
    registros = list(RegistroAuditoria.objects.filter(filtro).select_related("usuario").order_by("-criado_em")[:limite])
    for registro in registros:
        registro.campos_alterados = sorted(
            campo for campo in registro.alteracoes if campo not in CAMPOS_FORA_DO_HISTORICO and campo not in ("novo", "antigo")
        )
        registro.sobre_bloco = registro.modelo == "documentos.documentobloco"
    return registros


def _gravar_recorte(form, nomes, derivados=None):
    """Persiste só os campos pedidos (e os derivados deles) de um ModelForm.

    O formulário já validou e já aplicou na instância o que passou
    (`construct_instance`), inclusive o que o `save()` do domínio deriva; aqui
    vai ao banco apenas o recorte deste campo. Um dado antigo inválido em
    outro campo não muda nem trava — continua como está, e é aviso.
    """
    from django.db import transaction

    validado = form.save(commit=False)
    campos = set(nomes)
    for nome in nomes:
        campos.update((derivados or {}).get(nome, ()))
    muitos = {campo.name for campo in validado._meta.many_to_many}
    concretos = {campo.name for campo in validado._meta.concrete_fields}
    simples = sorted((campos - muitos) & concretos)
    if validado.pk is None:
        # Registro que ainda não existe (o relatório técnico antes da primeira
        # visita): nasce com o que o formulário tem.
        with transaction.atomic():
            validado.save()
            for nome in sorted(campos & muitos):
                getattr(validado, nome).set(form.cleaned_data.get(nome, []))
        return validado
    # A instância validada carrega, em memória, tudo o que o formulário
    # recalculou (inclusive o que não se pede aqui). Grava-se a partir de uma
    # cópia fresca do banco, com só o recorte copiado: o que vai ao banco e o
    # que a auditoria vê são a mesma coisa.
    objeto = type(validado)._base_manager.get(pk=validado.pk)
    for nome in simples:
        setattr(objeto, nome, getattr(validado, nome))
    versionado = "atualizado_em" in concretos
    with transaction.atomic():
        if simples or versionado:
            objeto.save(update_fields=simples + (["atualizado_em"] if versionado else []))
        for nome in sorted(campos & muitos):
            getattr(objeto, nome).set(form.cleaned_data.get(nome, []))
    return objeto


# ---- Vínculos ------------------------------------------------------------


class VinculoBase:
    """O que todo vínculo tem; cada tipo diz o resto."""

    tipo: DocumentoTipo
    chave = ""  # a da URL; por padrão, o tipo
    rotulo_voltar = "Voltar"
    # Origens cuja versão é a da página (o registro principal do documento).
    principais = ("documento",)

    def __init__(self):
        self.chave = self.chave or self.tipo.value
        self.fontes = self.montar_fontes()

    def montar_fontes(self) -> dict:
        return {}

    # Carregar e permissões
    def carregar(self, pk, variante=""):
        raise NotImplementedError

    def pode_ver(self, usuario) -> bool:
        from viagens_cadastros.permissions import pode_acessar

        return pode_acessar(usuario)

    def cancelado(self, objeto) -> bool:
        return bool(getattr(objeto, "cancelado", False))

    def pode_editar(self, usuario, objeto) -> bool:
        from viagens_cadastros.permissions import pode_editar_cadastros

        return pode_editar_cadastros(usuario) and not self.cancelado(objeto)

    def origens_editaveis(self, usuario) -> set[str]:
        """De quais origens quem vê pode editar trechos: a configuração do
        setor e os assinantes são da gestão; o resto, de quem edita o documento."""
        from viagens_cadastros.permissions import eh_gestor_viagens

        origens = set(self.fontes)
        if not eh_gestor_viagens(usuario):
            origens.discard("configuracao")
        return origens

    def fonte(self, origem):
        return self.fontes.get(origem)

    def versao(self, objeto) -> str:
        return _versao(objeto)

    # A folha
    def dono_dos_blocos(self, objeto):
        """O registro a que os parágrafos reescritos e as quebras pertencem."""
        return objeto

    def documental(self, objeto) -> dict:
        from documentos.services.document_blocks import conteudo_documental

        return conteudo_documental(self.tipo, self.dono_dos_blocos(objeto))

    def contexto(self, objeto, *, modo, campos_editaveis):
        raise NotImplementedError

    def folha(self, objeto, usuario) -> str:
        """O documento no modo editor: o HTML que o iframe da tela mostra e que
        volta junto de cada gravação, para a folha se atualizar no lugar."""
        from documentos.editor.campos import marcacao
        from documentos.services.pdf_renderer import renderizar_html

        # Só quem pode editar vê os trechos marcados; o registro decide quais.
        campos = marcacao(self.chave, origens=self.origens_editaveis(usuario)) if self.pode_editar(usuario, objeto) else {}
        return renderizar_html(self.tipo, self.contexto(objeto, modo="editor", campos_editaveis=campos), modo="editor")

    # URLs do editor (a variante vai junto em todas)
    def variante(self, objeto) -> str:
        return ""

    def url(self, nome, objeto, *args) -> str:
        url = reverse(f"documentos:editor_{nome}", args=[self.chave, objeto.pk, *args])
        variante = self.variante(objeto)
        return f"{url}?v={variante}" if variante else url

    # A tela
    def rotulo(self, objeto) -> str:
        return str(objeto)

    def situacao(self, objeto) -> str:
        return "Cancelado" if self.cancelado(objeto) else ""

    def subtitulo(self, objeto) -> str:
        return ""

    def url_voltar(self, objeto) -> str:
        return ""

    def url_pdf(self, objeto) -> str:
        return ""

    def pendencias(self, objeto) -> list:
        return []

    def pode_emitir(self, usuario, objeto) -> bool:
        return self.pode_editar(usuario, objeto) and not self.pendencias(objeto)

    def historico(self, objeto) -> list:
        return []


class VinculoOficio(VinculoBase):
    tipo = DocumentoTipo.OFICIO
    rotulo_voltar = "Voltar ao ofício"
    principais = ("oficio", "marcacao")

    # O que mais muda quando um campo muda — as consequências que o `save()`
    # e o `clean()` do formulário calculam a partir dele. O editor grava o
    # campo pedido e estes; nada além.
    DERIVADOS = {
        "servidores": ("servidores_termo_autorizacao", "diarias_quantidade_servidores"),
    }

    def montar_fontes(self):
        return {
            "oficio": FonteOficio(self),
            "marcacao": FonteMarcacao(self),
            "servidor": FonteServidor(lambda oficio: oficio.servidores),
            "solicitacao": FonteSolicitacao(),
            "configuracao": FonteConfiguracao(),
        }

    def carregar(self, pk, variante=""):
        from viagens_oficios.selectors import get_oficio_by_id

        return get_oficio_by_id(pk)

    def form(self, oficio, dados=None):
        from viagens_oficios.forms import OficioDocumentoForm

        return OficioDocumentoForm(dados, instance=oficio)

    def contexto(self, oficio, *, modo, campos_editaveis):
        from documentos.services.document_context import contexto_do_oficio

        return contexto_do_oficio(oficio, modo=modo, campos_editaveis=campos_editaveis)

    def dados_atuais(self, oficio) -> dict:
        """O ofício inteiro como o formulário o receberia: o PATCH troca só as
        partes pedidas e o resto vai como está, para as regras de `clean()`
        enxergarem o conjunto."""
        from viagens_oficios.forms import OficioDocumentoForm

        return _dados_do_modelo(oficio, OficioDocumentoForm.Meta.fields)

    def gravar(self, form, nomes):
        return _gravar_recorte(form, nomes, self.DERIVADOS)

    def opcoes(self, parte, form, valor):
        """Opções de uma parte de escolha, prontas para os componentes globais."""
        if parte.nome == "servidores":
            return _opcoes_de_servidores(form, valor)
        return _opcoes_do_form(parte, form, valor)

    def rotulo(self, oficio):
        return f"Ofício {oficio.numero_formatado}"

    def situacao(self, oficio):
        return "Cancelado" if oficio.cancelado else oficio.get_status_display()

    def subtitulo(self, oficio):
        return "Documento montado dos dados do ofício" + (f" · Protocolo {oficio.protocolo}" if oficio.protocolo else "")

    def url_voltar(self, oficio):
        return reverse("viagens_oficios:editar", args=[oficio.pk])

    def url_pdf(self, oficio):
        return reverse("viagens_oficios:gerar", args=[oficio.pk, "oficio", "pdf"])

    def pendencias(self, oficio):
        from viagens_oficios.services import validar_oficio_para_documento

        return validar_oficio_para_documento(oficio)["pendencias"]

    def historico(self, oficio):
        from viagens_oficios.views import historico_do_oficio

        return historico_do_oficio(oficio)


def _servidores_do_documento(objeto):
    """O servidor do documento (o termo é de uma pessoa), como consulta."""
    from viagens_cadastros.models import Servidor

    servidor = getattr(objeto, "doc_servidor", None)
    return Servidor.objects.filter(pk=servidor.pk) if servidor else Servidor.objects.none()


class VinculoTermo(VinculoBase):
    """O termo do cadastro de termos: um documento por servidor (a variante é
    o id dele), mais o termo em branco (`0`) e o só da viatura (`viatura`)."""

    tipo = DocumentoTipo.TERMO_AUTORIZACAO
    rotulo_voltar = "Voltar ao termo"

    def montar_fontes(self):
        return {
            "documento": FonteTermo(self),
            "servidor": FonteServidor(_servidores_do_documento),
            "viatura": FonteViatura(lambda termo: termo.viatura_efetiva()),
            "configuracao": FonteConfiguracao(),
        }

    def carregar(self, pk, variante=""):
        from django.shortcuts import get_object_or_404

        from viagens_termos.models import TermoAutorizacao
        from viagens_termos.services import servidores_para_termo_cadastro

        termo = get_object_or_404(TermoAutorizacao.objects.select_related("oficio", "viatura", "destino_cidade"), pk=pk)
        variante = str(variante or "")
        servidores = [s for s in servidores_para_termo_cadastro(termo) if s is not None]
        termo.doc_forcar_viatura = variante == "viatura"
        termo.doc_servidor = None
        if variante.isdigit() and variante != "0":
            termo.doc_servidor = next((s for s in servidores if s.pk == int(variante)), None)
            if termo.doc_servidor is None:
                raise Http404("Servidor fora deste termo.")
        elif not variante and servidores:
            termo.doc_servidor = servidores[0]
        termo.doc_variante = str(termo.doc_servidor.pk) if termo.doc_servidor else ("viatura" if termo.doc_forcar_viatura else "0")
        return termo

    def variante(self, termo):
        return termo.doc_variante

    def contexto(self, termo, *, modo, campos_editaveis):
        from documentos.services.document_context import contexto_do_termo
        from viagens_termos.services import _legacy_docx_context, build_termo_cadastro_payload

        payload = build_termo_cadastro_payload(termo, termo.doc_servidor, forcar_viatura=termo.doc_forcar_viatura)
        payload["documento"] = self.documental(termo)
        contexto = contexto_do_termo(payload, _legacy_docx_context(payload), modo=modo, campos_editaveis=campos_editaveis)
        viatura = termo.viatura_efetiva()
        contexto["ids"] = {"servidor": termo.doc_servidor.pk if termo.doc_servidor else ""}
        # Com viatura cadastrada, modelo, placa e combustível são o cadastro
        # dela; sem, o trecho escolhe a viatura do termo.
        contexto["marcas"] = {
            "periodo": "termo_periodo", "destino": "termo_destino", "escolher_viatura": "termo_viatura",
            "modelo": "viatura_modelo" if viatura else "termo_viatura",
            "placa": "viatura_placa" if viatura else "termo_viatura",
            "combustivel": "viatura_combustivel" if viatura else "termo_viatura",
            "viatura": viatura.pk if viatura else "",
        }
        return contexto

    def rotulo(self, termo):
        nome = termo.doc_servidor.nome if termo.doc_servidor else ("só da viatura" if termo.doc_forcar_viatura else "em branco")
        return f"Termo de autorização – {nome}"

    def subtitulo(self, termo):
        return f"Termo nº {termo.pk}" + (f" · Ofício {termo.oficio.numero_formatado}" if termo.oficio_id else "")

    def url_voltar(self, termo):
        return reverse("viagens_termos:editar", args=[termo.pk])

    def url_pdf(self, termo):
        if termo.doc_forcar_viatura:
            return reverse("viagens_termos:gerar_viatura", args=[termo.pk, "pdf"])
        return reverse("viagens_termos:gerar", args=[termo.pk, termo.doc_servidor.pk if termo.doc_servidor else 0, "pdf"])

    def cancelado(self, termo):
        return bool(termo.cancelado or (termo.oficio_id and termo.oficio.cancelado))

    def historico(self, termo):
        blocos = list(termo.blocos_documentais.values_list("pk", flat=True))
        return _historico([("viagens_termos.termoautorizacao", [termo.pk]), ("documentos.documentobloco", blocos)])


class VinculoTermoOficio(VinculoBase):
    """O termo tirado do ofício, de um servidor dele: data, destino e viatura
    são os do ofício, e mudá-los muda o ofício."""

    tipo = DocumentoTipo.TERMO_AUTORIZACAO
    chave = "termo_oficio"
    rotulo_voltar = "Voltar ao ofício"
    principais = ("oficio",)

    def montar_fontes(self):
        return {
            "oficio": FonteOficio(VINCULOS_BASE["oficio"]),
            "servidor": FonteServidor(_servidores_do_documento),
            "configuracao": FonteConfiguracao(),
        }

    def carregar(self, pk, variante=""):
        from viagens_oficios.selectors import get_oficio_by_id
        from viagens_termos.services import listar_servidores_com_termo

        oficio = get_oficio_by_id(pk)
        servidores = list(listar_servidores_com_termo(oficio))
        variante = str(variante or "")
        oficio.doc_servidor = next((s for s in servidores if str(s.pk) == variante), None) if variante else (servidores[0] if servidores else None)
        if oficio.doc_servidor is None:
            raise Http404("Servidor sem termo neste ofício.")
        return oficio

    def pode_editar(self, usuario, oficio):
        return VINCULOS_BASE["oficio"].pode_editar(usuario, oficio)

    def variante(self, oficio):
        return str(oficio.doc_servidor.pk)

    def contexto(self, oficio, *, modo, campos_editaveis):
        from documentos.services.document_context import contexto_do_termo
        from viagens_oficios.documents import build_termo_payload
        from viagens_termos.services import _legacy_docx_context

        payload = build_termo_payload(oficio, oficio.doc_servidor)
        payload["documento"] = self.documental(oficio)
        contexto = contexto_do_termo(payload, _legacy_docx_context(payload), modo=modo, campos_editaveis=campos_editaveis)
        contexto["ids"] = {"servidor": oficio.doc_servidor.pk}
        # Data e destino vêm do roteiro do ofício; a viatura, do transporte dele.
        contexto["marcas"] = dict.fromkeys(("periodo", "destino"), "roteiro") | dict.fromkeys(
            ("modelo", "placa", "combustivel", "escolher_viatura"), "transporte") | {"viatura": ""}
        return contexto

    def rotulo(self, oficio):
        return f"Termo de autorização – {oficio.doc_servidor.nome}"

    def subtitulo(self, oficio):
        return f"Do ofício {oficio.numero_formatado}"

    def url_voltar(self, oficio):
        return reverse("viagens_oficios:editar", args=[oficio.pk])

    def url_pdf(self, oficio):
        return reverse("viagens_oficios:termo", args=[oficio.pk, oficio.doc_servidor.pk, "pdf"])

    def historico(self, oficio):
        blocos = list(oficio.blocos_documentais.filter(tipo_documento=self.tipo.value).values_list("pk", flat=True))
        return _historico([("viagens_oficios.oficio", [oficio.pk]), ("documentos.documentobloco", blocos)])


class VinculoJustificativa(VinculoBase):
    """A justificativa do ofício (o registro pode ainda não existir)."""

    tipo = DocumentoTipo.JUSTIFICATIVA
    rotulo_voltar = "Voltar ao ofício"

    def montar_fontes(self):
        return {"documento": FonteJustificativa(self), "configuracao": FonteConfiguracao()}

    def carregar(self, pk, variante=""):
        from viagens_oficios.selectors import get_oficio_by_id

        return get_oficio_by_id(pk)

    @staticmethod
    def registro(oficio):
        from viagens_oficios.models import Justificativa

        return Justificativa.objects.filter(oficio=oficio).first()

    def versao(self, oficio):
        return _versao(self.registro(oficio))

    def contexto(self, oficio, *, modo, campos_editaveis):
        from documentos.services.document_context import contexto_da_justificativa
        from viagens_oficios.documents import build_canonical_document_payload
        from viagens_oficios.docxtpl_context import build_justificativa_docxtpl_context

        payload = build_canonical_document_payload(oficio, self.tipo)
        payload["documento"] = self.documental(oficio)
        return contexto_da_justificativa(payload, build_justificativa_docxtpl_context(oficio), modo=modo, campos_editaveis=campos_editaveis)

    def rotulo(self, oficio):
        return f"Justificativa – Ofício {oficio.numero_formatado}"

    def url_voltar(self, oficio):
        return reverse("viagens_oficios:editar", args=[oficio.pk])

    def url_pdf(self, oficio):
        return reverse("viagens_oficios:gerar", args=[oficio.pk, "justificativa", "pdf"])

    def pendencias(self, oficio):
        from viagens_oficios.services import validar_oficio_para_documento

        return validar_oficio_para_documento(oficio)["pendencias"]

    def historico(self, oficio):
        registro = self.registro(oficio)
        blocos = list(oficio.blocos_documentais.filter(tipo_documento=self.tipo.value).values_list("pk", flat=True))
        return _historico([("viagens_oficios.justificativa", [registro.pk if registro else None]), ("documentos.documentobloco", blocos)])


class VinculoOrdem(VinculoBase):
    tipo = DocumentoTipo.ORDEM_SERVICO
    rotulo_voltar = "Voltar à ordem de serviço"

    def montar_fontes(self):
        return {"documento": FonteOrdem(self), "configuracao": FonteConfiguracao()}

    def carregar(self, pk, variante=""):
        from viagens_ordens.selectors import get_ordem_by_id

        return get_ordem_by_id(pk)

    def contexto(self, ordem, *, modo, campos_editaveis):
        from documentos.services.document_context import contexto_da_ordem_servico
        from viagens_cadastros.selectors import build_configuracao_context
        from viagens_ordens.docxtpl_context import build_os_docxtpl_context
        from viagens_ordens.services import resumo_da_ordem

        payload = {"institucional": build_configuracao_context(), "ordem_servico": resumo_da_ordem(ordem), "documento": self.documental(ordem)}
        return contexto_da_ordem_servico(payload, build_os_docxtpl_context(ordem), modo=modo, campos_editaveis=campos_editaveis)

    def rotulo(self, ordem):
        numero = f"{ordem.numero:03d}/{ordem.ano}" if ordem.numero and ordem.ano else ordem.numero_formatado
        return f"Ordem de Serviço {numero}"

    def subtitulo(self, ordem):
        return ordem.get_tipo_necessidade_display()

    def url_voltar(self, ordem):
        return reverse("viagens_ordens:editar", args=[ordem.pk])

    def url_pdf(self, ordem):
        return reverse("viagens_ordens:gerar", args=[ordem.pk, "pdf"])

    def historico(self, ordem):
        blocos = list(ordem.blocos_documentais.values_list("pk", flat=True))
        return _historico([("viagens_ordens.ordemservico", [ordem.pk]), ("documentos.documentobloco", blocos)])


class VinculoPlano(VinculoBase):
    tipo = DocumentoTipo.PLANO_TRABALHO
    rotulo_voltar = "Voltar ao plano"

    def montar_fontes(self):
        return {"documento": FontePlano(self), "configuracao": FonteConfiguracao()}

    def carregar(self, pk, variante=""):
        from viagens_planos.selectors import get_plano_by_id

        return get_plano_by_id(pk)

    def contexto(self, plano, *, modo, campos_editaveis):
        from documentos.services.document_context import contexto_do_plano_trabalho
        from viagens_cadastros.selectors import build_configuracao_context
        from viagens_planos.docxtpl_context import build_plano_docxtpl_context

        tx = build_plano_docxtpl_context(plano)
        payload = {"institucional": build_configuracao_context(), "plano": tx, "documento": self.documental(plano)}
        return contexto_do_plano_trabalho(payload, tx, modo=modo, campos_editaveis=campos_editaveis)

    def rotulo(self, plano):
        return f"Plano de Trabalho {plano.numero_formatado}"

    def situacao(self, plano):
        return "Cancelado" if plano.cancelado else plano.get_status_display()

    def url_voltar(self, plano):
        return reverse("viagens_planos:editar", args=[plano.pk])

    def url_pdf(self, plano):
        return reverse("viagens_planos:gerar", args=[plano.pk, "pdf"])

    def pendencias(self, plano):
        from viagens_planos.services import avaliar_pendencias_documento

        return list(avaliar_pendencias_documento(plano) or [])

    def historico(self, plano):
        blocos = list(plano.blocos_documentais.values_list("pk", flat=True))
        return _historico([("viagens_planos.planotrabalho", [plano.pk]), ("documentos.documentobloco", blocos)])


def _prestacao_servidor(pk):
    from django.shortcuts import get_object_or_404

    from viagens_prestacoes.models import PrestacaoServidor

    return get_object_or_404(
        PrestacaoServidor.objects.select_related("prestacao__oficio__roteiro", "servidor__cargo", "servidor__unidade"), pk=pk,
    )


def _servidor_da_prestacao(ps):
    from viagens_cadastros.models import Servidor

    return Servidor.objects.filter(pk=ps.servidor_id)


class VinculoRelatorio(VinculoBase):
    """O relatório técnico de um servidor da prestação de contas: o texto é
    da prestação (um para a equipe); nome, CPF e diária são do servidor."""

    tipo = DocumentoTipo.RELATORIO_TECNICO
    rotulo_voltar = "Voltar ao relatório"

    def montar_fontes(self):
        return {
            "documento": FonteRelatorio(self),
            "prestacao": FonteDiariaRecebida(self),
            "servidor": FonteServidor(_servidor_da_prestacao),
            "configuracao": FonteConfiguracao(),
        }

    def carregar(self, pk, variante=""):
        return _prestacao_servidor(pk)

    @staticmethod
    def relatorio(ps):
        """O relatório da prestação, ou um em branco que só nasce ao gravar —
        abrir o documento não grava nada."""
        from viagens_prestacoes.models import RelatorioTecnico

        relatorio = RelatorioTecnico.objects.filter(prestacao=ps.prestacao).first() or RelatorioTecnico(prestacao=ps.prestacao)
        relatorio.doc_ps = ps
        return relatorio

    def versao(self, ps):
        return _versao(self.relatorio(ps))

    def cancelado(self, ps):
        return bool(ps.prestacao.oficio.cancelado)

    def dono_dos_blocos(self, ps):
        return ps.prestacao

    def contexto(self, ps, *, modo, campos_editaveis):
        from documentos.services.document_context import contexto_do_relatorio_tecnico
        from viagens_prestacoes.services import build_relatorio_tecnico_context

        tx = build_relatorio_tecnico_context(self.relatorio(ps), ps)
        payload = dict(tx, documento=self.documental(ps))
        contexto = contexto_do_relatorio_tecnico(payload, tx, modo=modo, campos_editaveis=campos_editaveis)
        contexto["ids"] = {"servidor": ps.servidor_id}
        return contexto

    def rotulo(self, ps):
        return f"Relatório técnico – {ps.servidor.nome}"

    def subtitulo(self, ps):
        return f"Ofício {ps.prestacao.oficio.numero_formatado}"

    def url_voltar(self, ps):
        return reverse("viagens_prestacoes:rt_servidor", args=[ps.pk])

    def url_pdf(self, ps):
        return reverse("viagens_prestacoes:rt_download_servidor_formato", args=[ps.pk, "pdf"])

    def historico(self, ps):
        relatorio = self.relatorio(ps)
        blocos = list(ps.prestacao.blocos_documentais.filter(tipo_documento=self.tipo.value).values_list("pk", flat=True))
        return _historico([
            ("viagens_prestacoes.relatoriotecnico", [relatorio.pk]),
            ("viagens_prestacoes.prestacaoservidor", [ps.pk]),
            ("documentos.documentobloco", blocos),
        ])


class VinculoDiario(VinculoBase):
    """O diário de bordo da prestação, aberto pelo servidor (como a tela do
    diário): motorista e viatura do diário, km e abastecimento por trecho."""

    tipo = DocumentoTipo.DIARIO_BORDO
    rotulo_voltar = "Voltar ao diário"

    def montar_fontes(self):
        return {"documento": FonteDiario(self), "trecho": FonteTrecho(self), "configuracao": FonteConfiguracao()}

    def carregar(self, pk, variante=""):
        from viagens_prestacoes.diario_services import obter_ou_criar_diario

        ps = _prestacao_servidor(pk)
        # Como a tela do diário: o diário nasce na primeira visita.
        ps.doc_diario = obter_ou_criar_diario(ps.prestacao)
        ps.doc_diario.doc_ps = ps
        return ps

    def versao(self, ps):
        return _versao(ps.doc_diario)

    def cancelado(self, ps):
        return bool(ps.prestacao.oficio.cancelado)

    def dono_dos_blocos(self, ps):
        return ps.prestacao

    def contexto(self, ps, *, modo, campos_editaveis):
        from documentos.services.document_context import contexto_do_diario_bordo
        from viagens_prestacoes.diario_services import build_diario_bordo_context

        header, trechos = build_diario_bordo_context(ps.doc_diario)
        payload = {"header": header, "trechos": trechos, "documento": self.documental(ps)}
        return contexto_do_diario_bordo(payload, modo=modo, campos_editaveis=campos_editaveis)

    def rotulo(self, ps):
        return f"Diário de bordo – Ofício {ps.prestacao.oficio.numero_formatado}"

    def url_voltar(self, ps):
        return reverse("viagens_prestacoes:diario_servidor", args=[ps.pk])

    def url_pdf(self, ps):
        return reverse("viagens_prestacoes:diario_download_formato", args=[ps.doc_diario.pk, "pdf"])

    def historico(self, ps):
        trechos = list(ps.doc_diario.trechos.values_list("pk", flat=True))
        return _historico([
            ("viagens_prestacoes.diariobordo", [ps.doc_diario.pk]),
            ("viagens_prestacoes.diariobordotrecho", trechos),
        ])


# ---- Fontes: onde cada trecho do documento mora ---------------------------
#
# O campo do registro diz a origem; a fonte sabe achar o registro dela a
# partir do objeto do documento (e do id do trecho, quando há vários — a linha
# de um servidor), dizer quem pode editar, entregar o formulário que já valida
# aquele registro no sistema e gravar.


class FonteBase:
    def __init__(self, vinculo=None):
        self.vinculo = vinculo

    def alvo(self, objeto, objeto_id, usuario):
        return objeto

    def pode_editar(self, usuario, objeto):
        return self.vinculo.pode_editar(usuario, objeto)

    def versao(self, alvo):
        return _versao(alvo)

    def form(self, alvo, dados=None):
        raise NotImplementedError

    def dados_atuais(self, alvo):
        form = self.form(alvo)
        return _dados_do_modelo(alvo, [nome for nome in form.fields if nome in {c.name for c in alvo._meta.get_fields()}])

    def gravar(self, form, nomes, alvo):
        return _gravar_recorte(form, nomes)

    def opcoes(self, parte, form, valor):
        return _opcoes_do_form(parte, form, valor)

    def links(self, definicao, objeto, alvo):
        return []


class FonteOficio(FonteBase):
    """O próprio ofício: o vínculo do ofício faz tudo. No termo tirado do
    ofício, o objeto do documento também é o ofício."""

    def versao(self, alvo):
        return self.vinculo.versao(alvo)

    def form(self, alvo, dados=None):
        return self.vinculo.form(alvo, dados)

    def dados_atuais(self, alvo):
        return self.vinculo.dados_atuais(alvo)

    def gravar(self, form, nomes, alvo):
        return self.vinculo.gravar(form, nomes)

    def opcoes(self, parte, form, valor):
        return self.vinculo.opcoes(parte, form, valor)

    def links(self, definicao, oficio, alvo):
        if definicao.chave == "roteiro" and oficio.roteiro_id:
            return _link("Abrir o roteiro", "viagens_roteiros:editar", oficio.roteiro_id)
        return []


class FonteMarcacao(FonteOficio):
    """Retificado/complementar: dois marcadores do ofício que se excluem,
    mudados pelos serviços do domínio (os mesmos das ações do cadastro)."""

    ESCOLHAS = (("", "Sem marcação (autorização ou convalidação)"), ("retificado", "Retificado"), ("complementar", "Complementar"))

    def form(self, alvo, dados=None):
        from django import forms

        class MarcacaoForm(forms.Form):
            tipo_documento = forms.ChoiceField(choices=self.ESCOLHAS, required=False, label="Tipo do ofício")

        return MarcacaoForm(dados, initial=self.dados_atuais(alvo))

    def dados_atuais(self, alvo):
        valor = "retificado" if alvo.retificado_documento else "complementar" if alvo.complementar_documento else ""
        return {"tipo_documento": valor}

    def gravar(self, form, nomes, alvo):
        from viagens_oficios import services

        escolha = form.cleaned_data.get("tipo_documento") or ""
        if escolha == "retificado":
            services.retificar_oficio(alvo)
        elif escolha == "complementar":
            services.marcar_oficio_complementar(alvo)
        else:
            if alvo.retificado_documento:
                services.desfazer_retificacao_oficio(alvo)
            if alvo.complementar_documento:
                services.desfazer_complementar_oficio(alvo)
        # Os serviços gravam só os marcadores; a versão do ofício acompanha,
        # para o controle de concorrência ver a mudança.
        type(alvo).objects.filter(pk=alvo.pk).update(atualizado_em=_agora())
        return alvo

    def opcoes(self, parte, form, valor):
        return [{"valor": chave, "rotulo": rotulo} for chave, rotulo in self.ESCOLHAS]

    def links(self, definicao, oficio, alvo):
        return []


class _FonteDeCadastro(FonteBase):
    """Base das fontes que são um cadastro: o ModelForm do domínio, gravado
    inteiro (os dados atuais vão junto, só o campo pedido muda). Quem pode
    editar cadastros edita o cadastro pelo documento, se o documento não foi
    cancelado."""

    def pode_editar(self, usuario, objeto):
        from viagens_cadastros.permissions import pode_editar_cadastros

        return pode_editar_cadastros(usuario) and getattr(objeto, "cancelado", False) is not True

    def gravar(self, form, nomes, alvo):
        return form.save()


class FonteServidor(_FonteDeCadastro):
    """O cadastro de um servidor do documento — só dos que o documento mostra
    (a equipe do ofício, o servidor do termo ou do relatório); outro id é 404."""

    def __init__(self, servidores):
        super().__init__()
        self.servidores = servidores

    def alvo(self, objeto, objeto_id, usuario):
        consulta = self.servidores(objeto)
        try:
            return consulta.select_related("cargo", "unidade").get(pk=int(objeto_id))
        except (TypeError, ValueError, consulta.model.DoesNotExist):
            raise Http404("Servidor fora deste documento.")

    def form(self, alvo, dados=None):
        from viagens_cadastros.forms import ServidorForm

        return ServidorForm(dados, instance=alvo)

    def dados_atuais(self, alvo):
        from viagens_cadastros.forms import ServidorForm

        return _dados_do_modelo(alvo, ServidorForm.Meta.fields)

    def links(self, definicao, objeto, alvo):
        return _link("Abrir o cadastro do servidor", "viagens_cadastros:editar", "servidores", alvo.pk)


class FonteViatura(_FonteDeCadastro):
    """O cadastro da viatura que o documento mostra."""

    def __init__(self, viatura):
        super().__init__()
        self.viatura = viatura

    def alvo(self, objeto, objeto_id, usuario):
        viatura = self.viatura(objeto)
        if viatura is None or str(viatura.pk) != str(objeto_id):
            raise Http404("Viatura fora deste documento.")
        return viatura

    def form(self, alvo, dados=None):
        from viagens_cadastros.forms import ViaturaForm

        return ViaturaForm(dados, instance=alvo)

    def dados_atuais(self, alvo):
        from viagens_cadastros.forms import ViaturaForm

        return _dados_do_modelo(alvo, ViaturaForm.Meta.fields)

    def links(self, definicao, objeto, alvo):
        return _link("Abrir o cadastro da viatura", "viagens_cadastros:editar", "viaturas", alvo.pk)


class FonteSolicitacao(_FonteDeCadastro):
    """O número da Central de Viagens de um servidor, na prestação de contas
    deste ofício. Sem prestação para ele, não há onde gravar: 404 com o motivo."""

    def alvo(self, oficio, objeto_id, usuario):
        from viagens_prestacoes.models import PrestacaoServidor

        linha = PrestacaoServidor.objects.filter(prestacao__oficio=oficio, servidor_id=objeto_id).first() if str(objeto_id or "").isdigit() else None
        if linha is None:
            raise Http404("Este servidor ainda não tem prestação de contas neste ofício.")
        return linha

    def form(self, alvo, dados=None):
        from django import forms

        Form = forms.modelform_factory(type(alvo), fields=["numero_solicitacao"])
        return Form(dados, instance=alvo)

    def dados_atuais(self, alvo):
        return {"numero_solicitacao": alvo.numero_solicitacao or ""}


class FonteConfiguracao(_FonteDeCadastro):
    """A configuração do setor de quem edita, com os assinantes (globais):
    o mesmo formulário da tela de configurações, com a mesma permissão."""

    def pode_editar(self, usuario, objeto):
        from viagens_cadastros.permissions import eh_gestor_viagens

        return eh_gestor_viagens(usuario)

    def alvo(self, objeto, objeto_id, usuario):
        from viagens_cadastros.models import ConfiguracaoSistema

        return ConfiguracaoSistema.para_usuario(usuario)

    def form(self, alvo, dados=None):
        from viagens_oficios.catalogs import ConfiguracaoInstitucionalForm

        return ConfiguracaoInstitucionalForm(dados, instance=alvo)

    def dados_atuais(self, alvo):
        form = self.form(alvo)
        dados = _dados_do_modelo(alvo, [nome for nome in form.fields if nome not in form.ASSINANTES])
        for nome in form.ASSINANTES:
            dados[nome] = form.initial.get(nome) or ""
        return dados


# ---- Fontes do registro principal de cada documento -----------------------


def _form_de(modelo, campos, *, limpar=None, iniciar=None):
    """ModelForm só com os campos que o documento mostra, com a regra de
    datas que os formulários do domínio aplicam (fim vazio vale o início; fim
    antes do início é erro)."""
    from django import forms

    class Form(forms.ModelForm):
        class Meta:
            model = modelo
            fields = list(campos)

        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            for campo in self.fields.values():
                campo.required = False
            if iniciar:
                iniciar(self)

        def clean(self):
            dados = super().clean()
            inicio, fim = dados.get("data_evento_inicio"), dados.get("data_evento_fim")
            if inicio and fim and fim < inicio:
                self.add_error("data_evento_fim", "A data final não pode ser anterior à inicial.")
            elif inicio and not fim and "data_evento_fim" in self.fields:
                dados["data_evento_fim"] = inicio
            if limpar:
                limpar(self, dados)
            return dados

    return Form


class FonteTermo(FonteBase):
    """O termo do cadastro: data, destino principal e viatura."""

    CAMPOS = ("data_evento_inicio", "data_evento_fim", "destino_cidade", "viatura")
    # O estado acompanha o município (o formulário do termo exige os dois juntos).
    DERIVADOS = {"destino_cidade": ("destino_estado",)}

    def form(self, alvo, dados=None):
        from viagens_cadastros.models import Viatura

        def iniciar(form):
            form.fields["viatura"].queryset = Viatura.objects.order_by("placa")

        def limpar(form, dados_limpos):
            cidade = dados_limpos.get("destino_cidade")
            form.instance.destino_estado_id = cidade.estado_id if cidade else None

        return _form_de(type(alvo), self.CAMPOS, limpar=limpar, iniciar=iniciar)(dados, instance=alvo)

    def gravar(self, form, nomes, alvo):
        return _gravar_recorte(form, nomes, self.DERIVADOS)

    def opcoes(self, parte, form, valor):
        if parte.nome == "destino_cidade":
            # Os municípios do estado do destino atual (ou do Paraná): outro
            # estado se escolhe no cadastro do termo.
            from cadastros.models import Municipio

            estado = form.instance.destino_estado_id
            consulta = Municipio.objects.filter(estado_id=estado) if estado else Municipio.objects.filter(estado__sigla="PR")
            return [{"valor": str(m.pk), "rotulo": f"{m.nome}/{m.estado.sigla}"} for m in consulta.select_related("estado").order_by("nome")]
        if parte.nome == "viatura":
            from viagens_oficios.form_context import _viaturas

            return _viaturas(form)
        return super().opcoes(parte, form, valor)

    def links(self, definicao, termo, alvo):
        return _link("Abrir o termo", "viagens_termos:editar", termo.pk)


class FonteJustificativa(FonteBase):
    """O texto da justificativa do ofício, gravado pelo serviço do domínio
    (que também atualiza a regra de prazo)."""

    def versao(self, oficio):
        return self.vinculo.versao(oficio)

    def form(self, oficio, dados=None):
        from django import forms

        class JustificativaTextoForm(forms.Form):
            texto = forms.CharField(label="Texto", widget=forms.Textarea, error_messages={"required": "Escreva a justificativa."})

        return JustificativaTextoForm(dados)

    def dados_atuais(self, oficio):
        registro = self.vinculo.registro(oficio)
        return {"texto": registro.texto if registro else ""}

    def gravar(self, form, nomes, oficio):
        from viagens_oficios.justificativas_services import salvar_justificativa

        registro = self.vinculo.registro(oficio)
        return salvar_justificativa(oficio, registro.modelo if registro else None, form.cleaned_data["texto"])

    def links(self, definicao, oficio, alvo):
        return _link("Abrir o ofício", "viagens_oficios:editar", oficio.pk)


class FonteOrdem(FonteBase):
    CAMPOS = ("tipo_necessidade", "servidores", "data_evento_inicio", "data_evento_fim", "motivo")
    # Tipos que a tela oferece; os demais só aparecem se a OS já os tem.
    TIPOS_NA_TELA = ("PADRAO", "OPERACAO_RETORNO_POSTERIOR", "CERIMONIAL_ANTECIPADO")

    def form(self, alvo, dados=None):
        def iniciar(form):
            campo = form.fields["tipo_necessidade"]
            campo.choices = [(v, r) for v, r in campo.choices if v in self.TIPOS_NA_TELA or v == alvo.tipo_necessidade]

        def limpar(form, dados_limpos):
            if not dados_limpos.get("tipo_necessidade"):
                form.add_error("tipo_necessidade", "Escolha o tipo.")

        return _form_de(type(alvo), self.CAMPOS, limpar=limpar, iniciar=iniciar)(dados, instance=alvo)

    def opcoes(self, parte, form, valor):
        if parte.nome == "servidores":
            return _opcoes_de_servidores(form, valor)
        return super().opcoes(parte, form, valor)

    def links(self, definicao, ordem, alvo):
        return _link("Abrir a ordem de serviço", "viagens_ordens:editar", ordem.pk)


class FontePlano(FonteBase):
    CAMPOS = ("contextualizacao", "coordenacao", "consideracao_final", "data_evento_inicio", "data_evento_fim",
              "horario_atendimento", "atividades_selecionadas")
    # Texto automático de cada campo: o interruptor e quem o refaz.
    AUTOMATICOS = {
        "contextualizacao": ("contextualizacao_auto", "texto_padrao_contextualizacao"),
        "coordenacao": ("coordenacao_auto", "texto_padrao_coordenacao"),
        "consideracao_final": ("consideracao_auto", "texto_padrao_consideracao_final"),
    }

    def form(self, alvo, dados=None):
        from django import forms

        from viagens_planos.models import HorarioAtendimento

        def iniciar(form):
            opcoes = [(h.faixa, h.faixa) for h in HorarioAtendimento.objects.order_by("faixa")]
            atual = (alvo.horario_atendimento or "").strip()
            if atual and atual not in {v for v, _ in opcoes}:
                opcoes.append((atual, atual))
            form.fields["horario_atendimento"] = forms.ChoiceField(choices=[("", "Sem horário")] + opcoes, required=False)
            campo = form.fields["atividades_selecionadas"]
            campo.queryset = campo.queryset.order_by("nome")

        return _form_de(type(alvo), self.CAMPOS, iniciar=iniciar)(dados, instance=alvo)

    def dados_atuais(self, alvo):
        return _dados_do_modelo(alvo, self.CAMPOS)

    def gravar(self, form, nomes, alvo):
        from viagens_planos import services

        plano = _gravar_recorte(form, nomes)
        mudou = []
        for nome in nomes:
            if nome in self.AUTOMATICOS:
                interruptor, padrao = self.AUTOMATICOS[nome]
                texto = (getattr(plano, nome) or "").strip()
                automatico = getattr(services, padrao)(plano) or ""
                # Vazio ou igual ao automático volta a ser automático; o resto
                # é texto de quem escreveu e fica como está.
                ligado = not texto or texto == automatico.strip()
                setattr(plano, interruptor, ligado)
                if ligado:
                    setattr(plano, nome, automatico)
                    mudou.append(nome)
                mudou.append(interruptor)
        if "atividades_selecionadas" in nomes:
            services.sincronizar_atividades(plano)
        if mudou:
            plano.save(update_fields=[*mudou, "atualizado_em"])
        return plano

    def links(self, definicao, plano, alvo):
        return _link("Abrir o plano de trabalho", "viagens_planos:editar", plano.pk)


class FonteRelatorio(FonteBase):
    """O texto do relatório técnico (da prestação): nasce ao gravar."""

    CAMPOS = ("translado", "combustivel", "passagem", "motivo", "atividade", "conclusao", "medidas", "info_complementares")

    def alvo(self, ps, objeto_id, usuario):
        return self.vinculo.relatorio(ps)

    def form(self, alvo, dados=None):
        return _form_de(type(alvo), self.CAMPOS)(dados, instance=alvo)

    def dados_atuais(self, alvo):
        return _dados_do_modelo(alvo, self.CAMPOS)

    def gravar(self, form, nomes, alvo):
        from viagens_prestacoes.services import marcar_servidor_em_preenchimento

        relatorio = _gravar_recorte(form, nomes)
        marcar_servidor_em_preenchimento(alvo.doc_ps)
        return relatorio

    def links(self, definicao, ps, alvo):
        return _link("Abrir o relatório técnico", "viagens_prestacoes:rt_servidor", ps.pk)


class FonteDiariaRecebida(FonteBase):
    """A diária que o servidor recebeu, na prestação dele: um texto na tela,
    valor e observação no banco (o serviço do domínio separa e valida)."""

    def form(self, ps, dados=None):
        from django import forms

        from viagens_prestacoes.services import aplicar_diaria_recebida

        class DiariaForm(forms.Form):
            diaria = forms.CharField(required=False, max_length=255)

            def clean_diaria(self):
                texto = self.cleaned_data.get("diaria") or ""
                # O serviço valida e aplica na instância; nada vai ao banco aqui.
                erros = aplicar_diaria_recebida(ps, texto)
                if erros:
                    raise forms.ValidationError(erros)
                return texto

        return DiariaForm(dados)

    def dados_atuais(self, ps):
        from viagens_prestacoes.services import diaria_recebida_display

        return {"diaria": diaria_recebida_display(ps) or ""}

    def gravar(self, form, nomes, ps):
        from viagens_prestacoes.services import marcar_servidor_em_preenchimento

        ps.save(update_fields=["diaria_valor_override", "diaria_valor_override_observacao", "atualizado_em"])
        marcar_servidor_em_preenchimento(ps)
        return ps

    def links(self, definicao, ps, alvo):
        return _link("Abrir o relatório técnico", "viagens_prestacoes:rt_servidor", ps.pk)


class FonteDiario(FonteBase):
    """Motorista e viatura do diário: o formulário e o serviço da troca, os
    mesmos do modal da tela do diário."""

    def alvo(self, ps, objeto_id, usuario):
        return ps.doc_diario

    def form(self, diario, dados=None):
        from viagens_prestacoes.forms import DiarioMotoristaForm

        return DiarioMotoristaForm(dados, instance=diario, oficio=diario.prestacao.oficio)

    def dados_atuais(self, diario):
        from viagens_prestacoes.forms import DiarioMotoristaForm

        return _dados_do_modelo(diario, DiarioMotoristaForm.Meta.fields)

    def gravar(self, form, nomes, diario):
        from viagens_prestacoes.diario_services import trocar_motorista_do_diario

        trocar_motorista_do_diario(form, diario.prestacao, diario.doc_ps)
        return diario

    def links(self, definicao, ps, alvo):
        if definicao.chave == "diario_trechos":
            return _link("Abrir o roteiro do diário", "viagens_prestacoes:diario_servidor_editar_roteiro", ps.pk)
        return _link("Abrir o diário de bordo", "viagens_prestacoes:diario_servidor", ps.pk)


class FonteTrecho(FonteBase):
    """Uma linha do diário: km inicial e final e a necessidade de abastecer."""

    ESCOLHAS = (("True", "Sim"), ("False", "Não"))

    def alvo(self, ps, objeto_id, usuario):
        trechos = ps.doc_diario.trechos
        try:
            return trechos.get(pk=int(objeto_id))
        except (TypeError, ValueError, trechos.model.DoesNotExist):
            raise Http404("Trecho fora deste diário.")

    def form(self, trecho, dados=None):
        from django import forms

        def iniciar(form):
            form.fields["abastecimento"] = forms.NullBooleanField(required=False)

        return _form_de(type(trecho), ("km_inicial", "km_final", "abastecimento"), iniciar=iniciar)(dados, instance=trecho)

    def dados_atuais(self, trecho):
        return {
            "km_inicial": "" if trecho.km_inicial is None else trecho.km_inicial,
            "km_final": "" if trecho.km_final is None else trecho.km_final,
            "abastecimento": "" if trecho.abastecimento is None else str(trecho.abastecimento),
        }

    def versao(self, trecho):
        return ""

    def gravar(self, form, nomes, trecho):
        from viagens_prestacoes.models import DiarioBordo

        objeto = _gravar_recorte(form, nomes)
        # A linha não tem versão; a do diário acompanha.
        DiarioBordo.objects.filter(pk=trecho.diario_id).update(atualizado_em=_agora())
        return objeto

    def opcoes(self, parte, form, valor):
        if parte.nome == "abastecimento":
            return [{"valor": v, "rotulo": r} for v, r in self.ESCOLHAS]
        return super().opcoes(parte, form, valor)

    def links(self, definicao, ps, alvo):
        return _link("Abrir o diário de bordo", "viagens_prestacoes:diario_servidor", ps.pk)


VINCULOS_BASE = {"oficio": VinculoOficio()}

VINCULOS = {
    vinculo.chave: vinculo
    for vinculo in (
        VINCULOS_BASE["oficio"],
        VinculoTermo(),
        VinculoTermoOficio(),
        VinculoJustificativa(),
        VinculoOrdem(),
        VinculoPlano(),
        VinculoRelatorio(),
        VinculoDiario(),
    )
}

# As fontes do ofício, por origem.
FONTES = VINCULOS["oficio"].fontes


def fonte_da_origem(origem):
    return FONTES.get(origem)


def url_do_editor(chave, pk, variante="") -> str:
    """A tela do editor de um documento, para os links "Editar documento"."""
    url = reverse("documentos:editor_pagina", args=[chave, pk])
    return f"{url}?v={variante}" if variante not in ("", None) else url


def vinculo_do_tipo(tipo):
    """O vínculo pela chave da URL: o tipo do documento, ou `termo_oficio`."""
    return VINCULOS.get(str(getattr(tipo, "value", tipo)))
