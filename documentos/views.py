"""Download privado dos arquivos documentais, servido pelo próprio Django."""

from pathlib import Path

from django.contrib.auth.decorators import login_required
from django.http import FileResponse, Http404
from django.views.decorators.http import require_GET

from .services.access import obter_artefato_para_download
from .services.responses import get_content_type_for_format
from .services.types import DocumentoFormato


@login_required
@require_GET
def baixar(request, pk):
    artefato = obter_artefato_para_download(request.user, pk)
    arquivo = artefato.arquivo_efetivo
    if not arquivo:
        raise Http404("Arquivo documental não encontrado.")
    assinado = arquivo.name != artefato.arquivo.name
    formato = DocumentoFormato.PDF if assinado else DocumentoFormato(artefato.formato)
    nome = artefato.nome_exibicao or Path(arquivo.name).name
    if assinado:
        nome = str(Path(nome).with_suffix(".pdf"))
    try:
        handle = arquivo.open("rb")
    except FileNotFoundError as exc:
        raise Http404("Arquivo documental não encontrado.") from exc
    response = FileResponse(
        handle, as_attachment=True, filename=nome,
        content_type=get_content_type_for_format(formato),
    )
    response["Cache-Control"] = "no-store, must-revalidate"
    response["Pragma"] = "no-cache"
    response["X-Content-Type-Options"] = "nosniff"
    return response
