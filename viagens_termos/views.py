"""Termos de autorização — lista, cadastro, documentos e downloads.

O app `termos` da origem: lista com busca e situação, termo avulso ou preso a
um ofício (o que fica em branco herda do ofício), documentos por servidor, o
genérico (semipreenchido), o da viatura, todos num PDF só ou em ZIP, anexação
do PDF assinado e a exclusão.
"""

import io

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST, require_http_methods

from core.listagens import ITENS_POR_PAGINA
from core.retorno import daqui, next_valido, voltar_para
from documentos.services.exceptions import DocumentError
from documentos.services.types import DocumentoFormato
from viagens_cadastros.permissions import acesso_ao_modulo, pode_editar_cadastros
from viagens_oficios.busca_oficios import buscar_oficios as buscar_oficios_para_picker, opcao_do_oficio
from viagens_oficios.views import exigir_operador, resposta_documento, resposta_lote

from . import abas as abas_de_termo
from .forms import TermoAutorizacaoForm
from .models import TermoAutorizacao
from .presenters import artefatos_pdf_por_termo, documentos_do_termo, heranca_do_termo, herdados_do_termo, linha_da_lista, selo_do_termo, titulo_do_termo
from .selectors import get_termo_by_id, listar_termos
from .services import build_termo_cadastro_payload, dados_eprotocolo_termo, gerar_termo_cadastro_lote, gerar_termo_cadastro_um


api_buscar_oficios = buscar_oficios_para_picker


def opcoes_de_viatura():
    """Viaturas do seletor, com o contexto que a tela usa para ordená-las.

    `unidade` e `motoristas` viajam em `data-*` porque a ordem muda enquanto se
    escolhem os servidores, sem ida ao servidor: viatura de um servidor
    escolhido vai para o topo, depois as da lotação deles.
    """
    from viagens_cadastros.models import Viatura

    opcoes = []
    for v in Viatura.objects.select_related("unidade").prefetch_related("motoristas").order_by("placa"):
        motoristas = list(v.motoristas.all())
        # O selo diz a quem a viatura está presa: o motorista é o vínculo mais
        # estreito e prevalece sobre a lotação.
        # Verde para motorista, azul para unidade.
        if motoristas:
            chip = motoristas[0].nome if len(motoristas) == 1 else f"{motoristas[0].nome} +{len(motoristas) - 1}"
            tom = "atendido"
        elif v.unidade_id:
            chip, tom = v.unidade.sigla or v.unidade.nome, "em_andamento"
        else:
            chip, tom = "", ""
        opcoes.append({
            "valor": str(v.pk),
            "rotulo": f"{v.placa_formatada} — {v.modelo}" if v.modelo else v.placa_formatada,
            "chip": chip,
            "chip_tom": tom,
            "busca": " ".join([m.nome for m in motoristas] + ([v.unidade.nome, v.unidade.sigla or ""] if v.unidade_id else [])),
            "dados": {"unidade": str(v.unidade_id or ""),
                      "motoristas": " ".join(str(m.pk) for m in motoristas)},
        })
    return opcoes


def opcoes_de_oficio(termo):
    """Ofícios do select da seção 1, no formato do `components/select.html`.

    Só os que ainda valem, mais o do próprio termo — que pode ter sido
    cancelado depois do vínculo e sumiria da lista, apagando a escolha em
    qualquer salvamento seguinte. A segunda linha (`detalhes`) traz período,
    destinos e protocolo; `busca` leva o que não aparece mas deve casar na
    busca, como o nome dos viajantes.
    """
    from viagens_oficios.busca_oficios import oficios_para_escolha as _oficios_para_escolha, resumo_para_busca
    from viagens_oficios.selectors import base_oficios

    queryset = _oficios_para_escolha()
    if termo.oficio_id:
        queryset = queryset | base_oficios().filter(pk=termo.oficio_id)
    opcoes = []
    for oficio in queryset.distinct():
        dados = opcao_do_oficio(oficio)
        opcoes.append({"valor": str(oficio.pk), "rotulo": dados["main"], "detalhes": dados["meta"],
                       "busca": resumo_para_busca(oficio)["search_text"]})
    return opcoes


@acesso_ao_modulo
def lista(request):
    q = request.GET.get("q", "").strip()
    escolhidas = abas_de_termo.normalizar_abas(request.GET.getlist("situacao"))
    # Contrato anterior: `?cancelados=1` continua mostrando os cancelados.
    if request.GET.get("cancelados") == "1" and not escolhidas:
        escolhidas = [abas_de_termo.ABA_CANCELADOS]
    base = listar_termos(q)
    queryset = listar_termos(q, situacoes=escolhidas)
    paginator = Paginator(queryset, ITENS_POR_PAGINA)
    pagina = paginator.get_page(request.GET.get("pagina"))
    parametros = request.GET.copy()
    parametros.pop("pagina", None)
    artefatos = artefatos_pdf_por_termo(pagina.object_list)
    linhas = [linha_da_lista(t, artefatos_pdf=artefatos.get(t.pk, {})) for t in pagina]

    # Situações como chips da trilha, iguais à lista de roteiros: cada chip
    # troca só a situação e mantém a busca.
    def url_da_situacao(aba=None):
        destino = parametros.copy()
        destino.pop("situacao", None)
        destino.pop("cancelados", None)
        if aba:
            destino["situacao"] = aba
        return "?" + destino.urlencode()

    icones = {
        abas_de_termo.ABA_FUTURAS: "calendar",
        abas_de_termo.ABA_ATUAIS: "clock",
        abas_de_termo.ABA_FINALIZADOS: "check-circle",
        abas_de_termo.ABA_CANCELADOS: "ban",
    }
    situacoes = [{"slug": "todas", "titulo": "Todas", "total": base.count(), "icone": "checklist", "url": url_da_situacao()}] + [
        {"slug": chave, "titulo": rotulo, "total": base.filter(abas_de_termo.q_da_aba(chave)).count(),
         "icone": icones[chave], "url": url_da_situacao(chave)}
        for chave, rotulo in abas_de_termo.ABA_ROTULOS
    ]

    from viagens_prestacoes.importacao.entrada import limite_de_bytes

    return render(request, "pages/viagens_termos/lista.html", {
        "linhas": linhas, "pagina": pagina, "querystring": parametros.urlencode(), "q": q,
        "paginas_visiveis": list(paginator.get_elided_page_range(pagina.number, on_each_side=1, on_ends=1)),
        "elipse": paginator.ELLIPSIS,
        "situacoes": situacoes,
        "situacoes_escolhidas": escolhidas,
        # Chip aceso: nenhuma situação é "Todas"; várias (link antigo) não acendem nenhum.
        "situacao_ativa": "todas" if not escolhidas else escolhidas[0] if len(escolhidas) == 1 else "",
        "tem_filtros": bool(q or escolhidas), "url_atual": daqui(request),
        "pode_editar": pode_editar_cadastros(request.user),
        # O modal "Importar processo do eProtocolo" (importador da prestação) diz o limite do arquivo.
        "importacao_limite_mb": limite_de_bytes() // (1024 * 1024),
    })


def _contexto_form(form, termo, request):
    from cadastros.models import Estado, Municipio
    from viagens_cadastros.models import Servidor, Viatura
    from viagens_oficios.picker import pks_ja_escolhidos

    escolhidos = set(pks_ja_escolhidos(form, "servidores"))
    servidores = []
    for s in Servidor.objects.select_related("cargo", "unidade").order_by("nome"):
        from viagens_oficios.presenters import iniciais
        # A unidade vai junto: é por ela que a tela sobe as viaturas da lotação
        # dos servidores escolhidos para o topo do seletor de viatura.
        servidores.append({"valor": str(s.pk), "rotulo": s.nome, "iniciais": iniciais(s.nome), "selecionado": str(s.pk) in escolhidos,
                           "dados": {"unidade": str(s.unidade_id or "")},
                           "detalhes": " · ".join(p for p in [str(s.cargo) if s.cargo_id else "", (s.unidade.sigla or s.unidade.nome) if s.unidade_id else ""] if p)})
    estados = [{"valor": str(e.pk), "rotulo": f"{e.sigla} — {e.nome}"} for e in Estado.objects.order_by("sigla")]
    municipios = [{"valor": str(m.pk), "rotulo": m.nome, "estado": str(m.estado_id)} for m in Municipio.objects.select_related("estado").order_by("nome")]
    valor = lambda nome: (str(getattr(form[nome].value(), "pk", form[nome].value())) if form[nome].value() not in (None, "") else "")
    adicionais = []
    for i in range(form.quantidade_destinos):
        adicionais.append({"i": i, "indice": str(i), "nome_estado": f"extra_estado_{i}", "nome_cidade": f"extra_cidade_{i}", "id_estado": f"id_extra_estado_{i}",
                           "estado": valor(f"extra_estado_{i}"), "cidade": valor(f"extra_cidade_{i}"),
                           "erros_estado": form.errors.get(f"extra_estado_{i}"), "erros_cidade": form.errors.get(f"extra_cidade_{i}")})
    oficios = opcoes_de_oficio(termo)
    return {
        "form": form, "termo": termo, "valores": {n: valor(n) for n in ["oficio", "destino_estado", "destino_cidade", "data_evento_inicio", "data_evento_fim", "viatura"]},
        "erros": {n: form.errors.get(n) for n in form.fields}, "servidores": servidores, "estados": estados, "municipios": municipios,
        "viaturas": opcoes_de_viatura(),
        "adicionais": adicionais, "quantidade_destinos": str(form.quantidade_destinos),
        "oficios": oficios,
        "herdados": herdados_do_termo(termo) if termo.pk else [],
        # A herança com os valores: o aviso mostra o que vem do ofício em cada campo.
        "heranca": heranca_do_termo(termo) if termo.pk else [],
        "next": next_valido(request),
        # "Cancelar" volta para a lista (ou para de onde se veio): o termo não
        # tem mais tela de detalhe para onde voltar.
        "url_voltar": voltar_para(request, _url_de_volta(termo)),
        "viagem_id": termo.viagem_id if not termo.pk else None,
        "titulo": f"Termo #{termo.pk}" if termo.pk else "Novo termo",
        "pode_editar": pode_editar_cadastros(request.user),
        **_contexto_do_registro(termo, request),
    }


def _contexto_do_registro(termo, request):
    """As seções que só existem num termo já salvo, na mesma tela do cadastro.

    Vieram do antigo detalhe: os documentos para baixar (o termo vazio e um
    por servidor), cada um com o seu estado — sem PDF, PDF gerado ou
    assinado — e a anexação do assinado.
    """
    if not termo.pk:
        return {}
    artefatos_pdf = artefatos_pdf_por_termo([termo]).get(termo.pk, {})
    selo, tom = selo_do_termo(termo)
    return {
        "selo": selo, "selo_tom": tom,
        "documentos": documentos_do_termo(termo, artefatos_pdf),
        "eprotocolo": dados_eprotocolo_termo(termo),
        "servidores_do_termo": list(termo.servidores_efetivos()),
        "viatura": termo.viatura_efetiva(),
        "pode_editar": pode_editar_cadastros(request.user),
        "url_atual": daqui(request),
    }


def _url_de_volta(termo):
    """Para onde se volta ao sair do termo: a etapa 5 da viagem dele, ou a lista."""
    if termo.viagem_id:
        return reverse("viagens_viagem:etapa", args=[termo.viagem_id, 5])
    return reverse("viagens_termos:lista")


def _termo_da_viagem(viagem):
    """Termo novo nascido do painel da viagem: herda ofício, destinos, datas,
    servidores e viatura da semente — como o `novo` da origem."""
    from viagens_viagem.services import destinos_para_formulario, semente_de_documentos

    semente = semente_de_documentos(viagem)
    termo = TermoAutorizacao(
        viagem=viagem, oficio=semente["oficio"], destino_estado=semente["estado"], destino_cidade=semente["cidade"],
        data_evento_inicio=semente["data_inicio"], data_evento_fim=semente["data_fim"] or semente["data_inicio"],
        viatura=semente["viatura"],
    )
    # Do segundo destino em diante: o form monta as linhas adicionais por aqui.
    termo.destinos_extras = [{"estado_id": e, "cidade_id": c} for e, c in destinos_para_formulario(semente)[1:]]
    servidores = semente["servidores_termo"] or semente["servidores"]
    initial = {"servidores": [s.pk for s in servidores]} if servidores else {}
    return termo, initial


@acesso_ao_modulo
@require_http_methods(["GET", "POST"])
def editar(request, pk=None):
    from viagens_viagem.services import viagem_do_request
    # Sem tela de detalhe, esta é a única tela do termo: quem só consulta
    # precisa poder abri-la. Criar e gravar seguem exigindo operador.
    if request.method == "POST" or not pk:
        exigir_operador(request)
    initial = None
    if pk:
        termo = get_termo_by_id(pk)
    else:
        viagem = viagem_do_request(request)
        termo, initial = _termo_da_viagem(viagem) if viagem is not None else (TermoAutorizacao(), None)
    form = TermoAutorizacaoForm(request.POST or None, instance=termo, initial=initial)
    if request.method == "POST" and request.POST.get("acao") != "adicionar_destino":
        if form.is_valid():
            termo = form.save()
            messages.success(request, f"Termo #{termo.pk} salvo.")
            # Salvou, acabou: a lista (ou a etapa 5 da viagem) é para onde se
            # volta. Quem chegou com `next` continua voltando para lá.
            return redirect(voltar_para(request, _url_de_volta(termo)))
        messages.error(request, "Não foi possível salvar o termo. Revise os campos indicados.")
    return render(request, "pages/viagens_termos/form.html", _contexto_form(form, termo, request))


@acesso_ao_modulo
def preview(request, pk, servidor_id=None):
    termo = get_termo_by_id(pk)
    servidor = get_object_or_404(termo.servidores_efetivos(), pk=servidor_id) if servidor_id else termo.servidores_efetivos().first()
    payload = build_termo_cadastro_payload(termo, servidor)
    variantes = {"completo_com_viatura": "Com viatura", "completo_sem_viatura": "Sem viatura", "semipreenchido": "Genérico"}
    return render(request, "pages/viagens_termos/preview.html", {
        "termo": termo, "payload": payload, "servidor": servidor, "titulo": titulo_do_termo(termo),
        "servidores": list(termo.servidores_efetivos()),
        "variante_rotulo": variantes.get(str(payload["termo"]["variante"]), str(payload["termo"]["variante"]).replace("_", " ").capitalize()),
    })


def _bloqueado(termo):
    return termo.cancelado or (termo.oficio_id and termo.oficio.cancelado)


def resposta_pdf_consolidado(documentos, nome):
    """Um PDF só com todos os termos, na ordem dos servidores — o `todos/pdf` da origem."""
    from pypdf import PdfWriter
    escritor = PdfWriter()
    for doc in documentos:
        escritor.append(io.BytesIO(doc.conteudo))
    buffer = io.BytesIO()
    escritor.write(buffer)
    response = HttpResponse(buffer.getvalue(), content_type="application/pdf")
    response["Content-Disposition"] = f'attachment; filename="{nome}"'
    response["Cache-Control"] = "no-store"
    return response


@acesso_ao_modulo
@require_POST
def gerar(request, pk, formato, servidor_id=None, viatura=False, todos=False):
    exigir_operador(request)
    termo = get_termo_by_id(pk)
    if formato not in ["docx", "pdf"]:
        raise Http404
    if _bloqueado(termo):
        messages.error(request, "Reative o termo e o ofício antes de gerar documentos.")
        return redirect("viagens_termos:editar", pk=pk)
    fmt = DocumentoFormato(formato)
    try:
        if todos:
            documentos = gerar_termo_cadastro_lote(termo, fmt)
            if fmt == DocumentoFormato.PDF and request.resolver_match.url_name == "todos_pdf":
                return resposta_pdf_consolidado(documentos, f"termo-{termo.pk}-todos.pdf")
            return resposta_lote(documentos)
        if viatura:
            return resposta_documento(request, gerar_termo_cadastro_um(termo, None, fmt, forcar_viatura=True))
        servidor = get_object_or_404(termo.servidores_efetivos(), pk=servidor_id) if servidor_id else None
        return resposta_documento(request, gerar_termo_cadastro_um(termo, servidor, fmt))
    except (ValidationError, DocumentError) as exc:
        messages.error(request, "; ".join(exc.messages) if isinstance(exc, ValidationError) else str(exc))
        return redirect("viagens_termos:editar", pk=pk)


@acesso_ao_modulo
@require_POST
def baixar(request, pk):
    """Os documentos marcados no modal "Baixar documentos".

    `itens`: "0" é o termo vazio; os demais, ids de servidores do termo.
    `formato`: pdf ou docx. `saida`: `separados` (um arquivo, ou ZIP quando
    são vários) ou `unico` (um PDF só, na ordem da lista). DOCX não se junta:
    vários DOCX saem sempre em ZIP. `versao`: `assinado` (padrão; o PDF de um
    documento com versão assinada é o anexado) ou `original` (o gerado pelo
    sistema, mesmo que haja assinado).
    """
    exigir_operador(request)
    termo = get_termo_by_id(pk)
    retorno = voltar_para(request, reverse("viagens_termos:lista"))
    if _bloqueado(termo):
        messages.error(request, "Reative o termo e o ofício antes de baixar documentos.")
        return redirect(retorno)
    formato = request.POST.get("formato", "pdf")
    if formato not in ("pdf", "docx"):
        raise Http404
    fmt = DocumentoFormato(formato)
    servidores = {str(s.pk): s for s in termo.servidores_efetivos()}
    pedidos = []
    for valor in request.POST.getlist("itens"):
        if valor != "0" and valor not in servidores:
            raise Http404
        if valor not in pedidos:
            pedidos.append(valor)
    if not pedidos:
        messages.error(request, "Marque ao menos um documento para baixar.")
        return redirect(retorno)
    # Na ordem da tela: termo vazio primeiro, depois os servidores.
    ordem = ["0"] + list(servidores)
    pedidos.sort(key=ordem.index)
    try:
        usar_assinado = request.POST.get("versao", "assinado") != "original"
        documentos = [gerar_termo_cadastro_um(termo, servidores.get(v), fmt, usar_assinado=usar_assinado) for v in pedidos]
    except (ValidationError, DocumentError) as exc:
        messages.error(request, "; ".join(exc.messages) if isinstance(exc, ValidationError) else str(exc))
        return redirect(retorno)
    if len(documentos) == 1:
        return resposta_documento(request, documentos[0])
    if fmt == DocumentoFormato.PDF and request.POST.get("saida") == "unico":
        return resposta_pdf_consolidado(documentos, f"termo-{termo.pk}-documentos.pdf")
    return resposta_lote(documentos)


def gerar_viatura(request, pk, formato):
    return gerar(request, pk, formato, viatura=True)


def gerar_lote(request, pk, formato):
    return gerar(request, pk, formato, todos=True)


def gerar_todos_pdf(request, pk):
    return gerar(request, pk, "pdf", todos=True)


@acesso_ao_modulo
@require_POST
def acao(request, pk, acao):
    from .services import excluir_termo
    exigir_operador(request)
    termo = get_termo_by_id(pk)
    destino = voltar_para(request, reverse("viagens_termos:editar", args=[pk]))
    if acao == "cancelar":
        termo.cancelar(request.POST.get("motivo", ""))
        messages.success(request, f"Termo #{termo.pk} cancelado. O histórico foi mantido.")
    elif acao == "reativar":
        termo.reativar()
        messages.success(request, f"Termo #{termo.pk} reativado.")
    elif acao == "excluir":
        numero = termo.pk
        volta = _url_de_volta(termo)
        excluir_termo(termo)
        messages.success(request, f"Termo #{numero} excluído.")
        return redirect(voltar_para(request, volta))
    else:
        raise Http404
    return redirect(destino)
