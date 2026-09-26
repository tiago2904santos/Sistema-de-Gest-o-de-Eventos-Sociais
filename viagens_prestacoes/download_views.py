from django.http import Http404
from django.http import HttpResponse
from django.http import JsonResponse
from django.views.decorators.http import require_GET

from documentos.services.exceptions import DocumentValidationError

from .download_services import TIPOS
from .download_services import compilar_download
from .download_services import payload_downloads
from .download_services import pdf_assinado
from .view_common import _prestacao_servidor_full


def _sufixo_servidor(ps) -> str:
    """m098: o primeiro nome do servidor no arquivo avulso, para os da equipe não se sobrescreverem."""
    from .filenames import nome_arquivo_ascii, primeiro_nome

    nome = primeiro_nome(ps.servidor)
    return f"_{nome_arquivo_ascii(nome)}" if nome else ""


@require_GET
def prestacao_downloads(request, ps_pk):
    return JsonResponse(payload_downloads(_prestacao_servidor_full(ps_pk)))


@require_GET
def prestacao_download_assinado(request, ps_pk, item_id, formato):
    if formato != "pdf" or item_id not in TIPOS:
        raise Http404
    ps = _prestacao_servidor_full(ps_pk)
    try:
        conteudo = pdf_assinado(ps, item_id)
    except DocumentValidationError as exc:
        raise Http404(str(exc)) from exc
    nome = f"{item_id}_{ps.prestacao.oficio.numero_formatado.replace('/', '-')}{_sufixo_servidor(ps)}.pdf"
    response = HttpResponse(conteudo, content_type="application/pdf")
    response["Content-Disposition"] = f'attachment; filename="{nome}"'
    response["X-Content-Type-Options"] = "nosniff"
    return response


@require_GET
def prestacao_download_compilado(request, ps_pk):
    ps = _prestacao_servidor_full(ps_pk)
    origem = request.GET.get("origem", "original")
    formato = request.GET.get("formato", "pdf")
    escolhidos = [item for item in request.GET.get("itens", "").split(",") if item in TIPOS]
    if formato not in {"pdf", "docx"} or origem not in {"original", "assinado"}:
        raise Http404
    try:
        conteudo = compilar_download(
            ps,
            origem=origem,
            formato=formato,
            escolhidos=escolhidos,
        )
    except DocumentValidationError as exc:
        return JsonResponse({"error": str(exc)}, status=400)
    tipo = "application/pdf" if formato == "pdf" else "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    response = HttpResponse(conteudo, content_type=tipo)
    response["Content-Disposition"] = f'attachment; filename="documentos_prestacao_{ps.prestacao.oficio.numero_formatado.replace('/', '-')}{_sufixo_servidor(ps)}.{formato}"'
    response["X-Content-Type-Options"] = "nosniff"
    return response



def prestacao_baixar(request, ps_pk):
    """Os documentos marcados no modal "Baixar documentos" da lista (POST).

    `itens`: ids de `payload_downloads` (oficio, despacho, rt, diario,
    comprovante). `formato`: pdf ou docx. `versao`: `assinado` (padrão; usa o
    PDF assinado de quem tem) ou `original`. `saida`: `separados` (um arquivo,
    ou ZIP) ou `unico` (um PDF só). A ordem é sempre a da prestação
    (`ORDEM_DOCUMENTOS_PRESTACAO`), e cada item leva todos os anexos dele — os
    dois despachos, os três comprovantes (pela data da operação).
    """
    import io
    from zipfile import ZipFile

    from django.contrib import messages
    from django.shortcuts import redirect
    from django.urls import reverse

    from core.retorno import voltar_para
    from .download_services import anexo_do_item, compilar_download

    ps = _prestacao_servidor_full(ps_pk)
    retorno = voltar_para(request, reverse("viagens_prestacoes:index"))
    formato = request.POST.get("formato", "pdf")
    if formato not in {"pdf", "docx"}:
        raise Http404
    disponiveis = [item["id"] for item in payload_downloads(ps)["itens"]]
    marcados = request.POST.getlist("itens")
    if set(marcados) - set(disponiveis):
        raise Http404
    pedidos = [item for item in disponiveis if item in marcados]
    if not pedidos:
        messages.error(request, "Marque ao menos um documento para baixar.")
        return redirect(retorno)
    usar_assinado = request.POST.get("versao", "assinado") != "original"
    referencia = ps.prestacao.oficio.numero_formatado.replace("/", "-") + _sufixo_servidor(ps)

    def origem_de(item):
        # O assinado só existe em PDF; sem ele, vai o original do sistema.
        return "assinado" if usar_assinado and formato == "pdf" and anexo_do_item(ps, item) else "original"

    try:
        partes = []
        for item in pedidos:
            origem = origem_de(item)
            try:
                partes.append((item, compilar_download(ps, origem=origem, formato=formato, escolhidos=[item])))
            except DocumentValidationError:
                # Sem original gerável (despacho, comprovante) e sem assinado: o item fica de fora.
                continue
        if not partes:
            raise DocumentValidationError("Nenhum documento está disponível nesta combinação.")
        if len(partes) > 1 and formato == "pdf" and request.POST.get("saida") == "unico":
            from pypdf import PdfWriter
            escritor = PdfWriter()
            for _, conteudo in partes:
                escritor.append(io.BytesIO(conteudo))
            buffer = io.BytesIO()
            escritor.write(buffer)
            conteudo, nome, tipo = buffer.getvalue(), f"prestacao_{referencia}.pdf", "application/pdf"
        elif len(partes) == 1:
            item, conteudo = partes[0]
            nome = f"{item}_{referencia}.{formato}"
            tipo = "application/pdf" if formato == "pdf" else "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        else:
            buffer = io.BytesIO()
            with ZipFile(buffer, "w") as arquivo_zip:
                for item, dados in partes:
                    arquivo_zip.writestr(f"{item}_{referencia}.{formato}", dados)
            conteudo, nome, tipo = buffer.getvalue(), f"prestacao_{referencia}.zip", "application/zip"
    except DocumentValidationError as exc:
        messages.error(request, str(exc))
        return redirect(retorno)
    response = HttpResponse(conteudo, content_type=tipo)
    response["Content-Disposition"] = f'attachment; filename="{nome}"'
    response["X-Content-Type-Options"] = "nosniff"
    response["Cache-Control"] = "no-store"
    return response


def prestacao_pacotes_zip(request, pc_pk):
    """m098: os pacotes finais da equipe inteira num ZIP, com o que falta em PENDENCIAS.txt."""
    from django.shortcuts import get_object_or_404

    from .services import nome_arquivo_pacotes_da_equipe, pacotes_da_equipe_zip
    from .view_common import _prestacao_queryset

    prestacao = get_object_or_404(_prestacao_queryset(), pk=pc_pk)
    conteudo, _ = pacotes_da_equipe_zip(prestacao)
    response = HttpResponse(conteudo, content_type="application/zip")
    response["Content-Disposition"] = f'attachment; filename="{nome_arquivo_pacotes_da_equipe(prestacao)}"'
    response["X-Content-Type-Options"] = "nosniff"
    response["Cache-Control"] = "no-store"
    return response

from .ui import render
