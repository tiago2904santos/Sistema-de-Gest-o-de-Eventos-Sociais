"""m099: revisar o pacote final página por página antes de baixar.

A tela mostra as miniaturas de todas as páginas do pacote na ordem oficial,
agrupadas por documento; o operador arrasta, gira ou oculta páginas, e o ajuste
fica gravado no servidor da prestação (`PrestacaoServidor.ajuste_pacote`), para
o "Pacote final (PDF)" e o ZIP da equipe saírem já corrigidos.
"""

import json

from django.contrib import messages
from django.shortcuts import redirect
from django.urls import reverse

from documentos.services.exceptions import DocumentValidationError

from .services import (
    ajuste_valido,
    assinatura_do_pacote,
    gerar_prestacao_consolidado_pdf,
    mapa_do_pacote,
    partes_do_pacote,
    pendencias_consolidado,
    salvar_ajuste_do_pacote,
)
from .view_common import _build_identificacao, _prestacao_servidor_full, contexto_do_fluxo

__all__ = ["pacote_revisar", "pacote_revisar_pdf"]


def pacote_revisar(request, ps_pk):
    ps = _prestacao_servidor_full(ps_pk)
    documentos_url = reverse("viagens_prestacoes:documentos_servidor", args=[ps.pk])
    pendencias = pendencias_consolidado(ps)
    if pendencias:
        messages.error(request, " ".join(pendencias))
        return redirect(documentos_url)

    if request.method == "POST":
        if request.POST.get("acao") == "descartar":
            ps.ajuste_pacote = {}
            ps.save(update_fields=["ajuste_pacote", "atualizado_em"])
            messages.success(request, "O pacote voltou à ordem oficial.")
            return redirect(documentos_url)
        try:
            paginas = json.loads(request.POST.get("paginas") or "[]")
            salvar_ajuste_do_pacote(ps, assinatura=request.POST.get("assinatura", ""), paginas=paginas)
        except (ValueError, DocumentValidationError) as exc:
            messages.error(request, str(exc))
            return redirect(reverse("viagens_prestacoes:pacote_revisar", args=[ps.pk]))
        messages.success(request, "Ajuste do pacote salvo." if ps.ajuste_pacote else "O pacote segue a ordem oficial.")
        return redirect(documentos_url)

    try:
        partes = partes_do_pacote(ps)
        mapa = mapa_do_pacote(partes)
    except DocumentValidationError as exc:
        messages.error(request, str(exc))
        return redirect(documentos_url)
    ajuste = ajuste_valido(ps, partes)
    # A ordem de partida: o ajuste gravado, ou a oficial.
    paginas = ajuste or [[item["parte"], pagina, 0, False] for item in mapa for pagina in range(item["paginas"])]
    # Índice de cada página no PDF da ordem oficial, que é o que a tela desenha.
    inicio = {}
    corrente = 0
    for item in mapa:
        inicio[item["parte"]] = corrente
        corrente += item["paginas"]
    return render(
        request,
        "pages/viagens_prestacoes/pacote_revisar.html",
        {
            "page_title": f"Revisar pacote final — {ps.servidor.nome}",
            "prestacao": ps.prestacao,
            "ps": ps,
            "identificacao": _build_identificacao(ps.prestacao),
            **contexto_do_fluxo(ps, "documentos"),
            "mapa": mapa,
            "estado": {
                "documentos": [{"parte": i["parte"], "rotulo": i["rotulo"], "inicio": inicio[i["parte"]]} for i in mapa],
                "paginas": paginas,
            },
            "assinatura": assinatura_do_pacote(mapa),
            "ajustado": bool(ajuste),
            "pdf_url": reverse("viagens_prestacoes:pacote_revisar_pdf", args=[ps.pk]),
            "documentos_url": documentos_url,
        },
    )


def pacote_revisar_pdf(request, ps_pk):
    """O pacote na ordem oficial, sem ajuste: a base que a tela de revisão desenha."""
    from .view_common import _preview_error_response

    ps = _prestacao_servidor_full(ps_pk)
    try:
        pdf = gerar_prestacao_consolidado_pdf(ps, com_ajuste=False)
    except DocumentValidationError as exc:
        return _preview_error_response(exc)
    response = resposta_bytes(request, pdf, "pacote_revisao.pdf", "pdf")
    response["Content-Disposition"] = 'inline; filename="pacote_revisao.pdf"'
    return response


from .ui import render, resposta_bytes  # noqa: E402
