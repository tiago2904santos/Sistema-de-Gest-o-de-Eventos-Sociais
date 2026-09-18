"""Download privado dos arquivos documentais, servido pelo próprio Django."""

from io import BytesIO
from pathlib import Path

from django.contrib.auth.decorators import login_required
from django.http import FileResponse, Http404
from django.views.decorators.http import require_GET

from .services.access import obter_artefato_para_download
from .services.regeneracao import precisa_regerar, regerar
from .services.responses import get_content_type_for_format
from .services.types import DocumentoFormato


def _resposta(handle, *, nome, formato):
    response = FileResponse(
        handle, as_attachment=True, filename=nome,
        content_type=get_content_type_for_format(formato),
    )
    response["Cache-Control"] = "no-store, must-revalidate"
    response["Pragma"] = "no-cache"
    response["X-Content-Type-Options"] = "nosniff"
    return response


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
    # Artefato do caminho antigo (Word/LibreOffice): entrega o documento
    # refeito pelo motor de hoje. Se não der para refazer, segue o arquivado.
    if precisa_regerar(artefato, assinado=assinado):
        conteudo = regerar(artefato)
        if conteudo is not None:
            return _resposta(BytesIO(conteudo), nome=nome, formato=formato)
    try:
        handle = arquivo.open("rb")
    except FileNotFoundError as exc:
        raise Http404("Arquivo documental não encontrado.") from exc
    return _resposta(handle, nome=nome, formato=formato)
