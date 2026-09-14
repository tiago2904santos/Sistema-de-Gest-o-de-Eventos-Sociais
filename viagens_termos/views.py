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
from viagens_oficios.justificativas_views import buscar_oficios as buscar_oficios_para_picker, opcao_do_oficio
from viagens_oficios.views import exigir_operador, resposta_documento, resposta_lote

from . import abas as abas_de_termo
from .forms import TermoAutorizacaoForm
from .models import TermoAutorizacao
from .presenters import artefatos_pdf_por_termo, documentos_do_termo, herdados_do_termo, linha_da_lista, selo_do_termo, titulo_do_termo
from .selectors import get_termo_by_id, listar_termos
from .services import build_termo_cadastro_payload, gerar_termo_cadastro_lote, gerar_termo_cadastro_um


api_buscar_oficios = buscar_oficios_para_picker


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
    pagina = paginator.get_page(request.GET.get("page"))
    parametros = request.GET.copy()
    parametros.pop("page", None)
    artefatos = artefatos_pdf_por_termo(pagina.object_list)
    linhas = [linha_da_lista(t, artefatos_pdf=artefatos.get(t.pk, {})) for t in pagina]
    return render(request, "pages/viagens_termos/lista.html", {
        "linhas": linhas, "pagina": pagina, "querystring": parametros.urlencode(), "q": q,
        "paginas_visiveis": list(paginator.get_elided_page_range(pagina.number, on_each_side=1, on_ends=1)),
        "elipse": paginator.ELLIPSIS,
        "opcoes_situacao": abas_de_termo.opcoes_de_aba(base, escolhidas),
        "tem_filtros": bool(q or escolhidas), "url_atual": daqui(request),
        "pode_editar": pode_editar_cadastros(request.user),
    })


def _contexto_form(form, termo, request):
    from cadastros.models import Estado, Municipio
    from viagens_cadastros.models import Servidor, Viatura
    from viagens_oficios.picker import pks_ja_escolhidos

    escolhidos = set(pks_ja_escolhidos(form, "servidores"))
    servidores = []
    for s in Servidor.objects.select_related("cargo", "unidade").order_by("nome"):
        from viagens_oficios.presenters import iniciais
        servidores.append({"valor": str(s.pk), "rotulo": s.nome, "iniciais": iniciais(s.nome), "selecionado": str(s.pk) in escolhidos,
                           "detalhes": " · ".join(p for p in [str(s.cargo) if s.cargo_id else "", (s.unidade.sigla or s.unidade.nome) if s.unidade_id else ""] if p)})
    estados = [{"valor": str(e.pk), "rotulo": f"{e.sigla} — {e.nome}"} for e in Estado.objects.order_by("sigla")]
    municipios = [{"valor": str(m.pk), "rotulo": m.nome, "estado": str(m.estado_id)} for m in Municipio.objects.select_related("estado").order_by("nome")]
    valor = lambda nome: (str(getattr(form[nome].value(), "pk", form[nome].value())) if form[nome].value() not in (None, "") else "")
    adicionais = []
    for i in range(form.quantidade_destinos):
        adicionais.append({"i": i, "nome_estado": f"extra_estado_{i}", "nome_cidade": f"extra_cidade_{i}", "id_estado": f"id_extra_estado_{i}",
                           "estado": valor(f"extra_estado_{i}"), "cidade": valor(f"extra_cidade_{i}"),
                           "erros_estado": form.errors.get(f"extra_estado_{i}"), "erros_cidade": form.errors.get(f"extra_cidade_{i}")})
    oficio_escolhido = None
    pk_oficio = valor("oficio")
    if pk_oficio.isdigit():
        from viagens_oficios.selectors import base_oficios
        oficio = base_oficios().filter(pk=int(pk_oficio)).first()
        if oficio:
            oficio_escolhido = opcao_do_oficio(oficio)
    return {
        "form": form, "termo": termo, "valores": {n: valor(n) for n in ["oficio", "destino_estado", "destino_cidade", "data_evento_inicio", "data_evento_fim", "viatura"]},
        "erros": {n: form.errors.get(n) for n in form.fields}, "servidores": servidores, "estados": estados, "municipios": municipios,
        "viaturas": [{"valor": str(v.pk), "rotulo": f"{v.placa_formatada} — {v.modelo}" if v.modelo else v.placa_formatada} for v in Viatura.objects.order_by("placa")],
        "adicionais": adicionais, "quantidade_destinos": str(form.quantidade_destinos),
        "oficio_escolhido": oficio_escolhido, "url_busca": reverse("viagens_termos:api_buscar_oficios"),
        "herdados": herdados_do_termo(termo) if termo.pk else [],
        "next": next_valido(request),
        "url_voltar": voltar_para(request, reverse("viagens_termos:detalhe", args=[termo.pk]) if termo.pk else reverse("viagens_termos:lista")),
        "titulo": f"Termo #{termo.pk}" if termo.pk else "Novo termo",
    }


@acesso_ao_modulo
@require_http_methods(["GET", "POST"])
def editar(request, pk=None):
    exigir_operador(request)
    termo = get_termo_by_id(pk) if pk else TermoAutorizacao()
    form = TermoAutorizacaoForm(request.POST or None, instance=termo)
    if request.method == "POST" and request.POST.get("acao") != "adicionar_destino":
        if form.is_valid():
            termo = form.save()
            messages.success(request, f"Termo #{termo.pk} salvo.")
            return redirect(voltar_para(request, reverse("viagens_termos:detalhe", args=[termo.pk])))
        messages.error(request, "Não foi possível salvar o termo. Revise os campos indicados.")
    return render(request, "pages/viagens_termos/form.html", _contexto_form(form, termo, request))


@acesso_ao_modulo
def detalhe(request, pk):
    termo = get_termo_by_id(pk)
    artefatos = artefatos_pdf_por_termo([termo]).get(termo.pk, {})
    selo, tom = selo_do_termo(termo)
    return render(request, "pages/viagens_termos/detalhe.html", {
        "termo": termo, "titulo": titulo_do_termo(termo), "selo": selo, "selo_tom": tom,
        "herdados": herdados_do_termo(termo), "documentos": documentos_do_termo(termo, artefatos),
        "servidores": list(termo.servidores_efetivos()), "viatura": termo.viatura_efetiva(),
        "pode_editar": pode_editar_cadastros(request.user),
        "artefatos": termo.artefatos.select_related("servidor").order_by("-criado_em")[:30],
        "url_atual": daqui(request),
    })


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
        return redirect("viagens_termos:detalhe", pk=pk)
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
        return redirect("viagens_termos:detalhe", pk=pk)


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
    destino = voltar_para(request, reverse("viagens_termos:detalhe", args=[pk]))
    if acao == "cancelar":
        termo.cancelar(request.POST.get("motivo", ""))
        messages.success(request, f"Termo #{termo.pk} cancelado. O histórico foi mantido.")
    elif acao == "reativar":
        termo.reativar()
        messages.success(request, f"Termo #{termo.pk} reativado.")
    elif acao == "excluir":
        numero = termo.pk
        excluir_termo(termo)
        messages.success(request, f"Termo #{numero} excluído.")
        return redirect(voltar_para(request, reverse("viagens_termos:lista")))
    else:
        raise Http404
    return redirect(destino)
