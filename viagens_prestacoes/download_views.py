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
    nome = f"{item_id}_{ps.prestacao.oficio.numero_formatado.replace('/', '-')}.pdf"
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
    response["Content-Disposition"] = f'attachment; filename="documentos_prestacao_{ps.pk}.{formato}"'
    response["X-Content-Type-Options"] = "nosniff"
    return response

from .ui import render
