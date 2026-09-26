"""Editor completo de documento (m057): o documento inteiro, já montado —
cabeçalho, corpo com os textos fixos e as tabelas, rodapé —, editado à mão no
navegador e gravado como versão editada (documentos/services/
edicao_completa.py).

Vale para todo documento que tem vínculo no editor (documentos/editor/
vinculos.py e os do Coffee Break): ofício, justificativa, termo, OS, plano,
relatório técnico, diário de bordo e a OS, o ofício e o certifico do Coffee
Break. Quem pode editar é quem já edita o documento (`vinculo.pode_editar`:
cancelado, concluído e sem permissão ficam de fora); documento com versão
assinada valendo só se edita depois de a versão assinada ser removida.

A tela é própria (a folha num iframe, a barra de formatação por cima); a
gravação é um POST com o HTML de cada região, que passa pela lista branca
antes de ir ao banco. "Voltar ao modelo" faz o documento sair de novo dos
dados; o histórico guarda cada versão, com quem e quando, e restaura
qualquer uma.
"""

from __future__ import annotations

import json

from django.contrib import messages
from django.core.exceptions import PermissionDenied, ValidationError
from django.http import Http404, HttpResponse, JsonResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.clickjacking import xframe_options_sameorigin
from django.views.decorators.http import require_GET, require_POST

from documentos.services import edicao_completa as edicao

from .pagina import _carregar

TAMANHO_MAXIMO_CORPO = 1024 * 1024

# Só na tela do editor completo: onde se escreve, e a folha do Coffee Break
# (uma página A4 fixa na prévia) crescendo com o texto.
CSS_DO_EDITOR = """
[data-ed-regiao] { outline: 1px dashed rgba(37, 99, 235, .45); outline-offset: 3px; cursor: text; }
[data-ed-regiao]:hover { outline-color: rgba(37, 99, 235, .8); }
[data-ed-regiao]:focus { outline: 2px solid #2563eb; }
[data-ed-regiao] table td, [data-ed-regiao] table th { min-width: 1.5em; }
.folha:has(.folha__area) { height: auto !important; min-height: 841.89pt; overflow: visible !important; padding: var(--topo) 70.8pt 77pt; box-sizing: border-box; }
.folha__area { position: relative !important; inset: auto !important; min-height: 560pt; }
.folha__pagina { display: none; }
"""


def _dono(vinculo, objeto):
    return vinculo.dono_dos_blocos(objeto)


def _chaves(vinculo, objeto):
    return vinculo.tipo, _dono(vinculo, objeto), vinculo.variante_edicao(objeto)


def bloqueio(vinculo, objeto, usuario) -> str:
    """Por que este documento não se edita agora ("" = edita)."""
    if not vinculo.pode_editar(usuario, objeto):
        if vinculo.cancelado(objeto):
            return "Documento cancelado ou concluído: reative o registro para editar."
        return "Você não tem permissão para editar este documento."
    if vinculo.assinado(objeto):
        return ("Documento com versão assinada valendo: para editar, remova a versão assinada (reabre o "
                "documento). A versão assinada nunca é alterada.")
    return ""


def situacao_da_edicao(vinculo, objeto) -> dict:
    """A versão editada em vigor e se ela ficou para trás dos dados."""
    tipo, dono, variante = _chaves(vinculo, objeto)
    vigente = edicao.vigente(tipo, dono, variante)
    if vigente is None:
        return {"vigente": None, "desatualizada": False}
    try:
        atual = edicao.impressao_digital(vinculo.html_documento(objeto, com_edicao=False))
    except ValidationError:
        atual = vigente.impressao_base
    return {"vigente": vigente, "desatualizada": bool(vigente.impressao_base) and vigente.impressao_base != atual}


def _url(vinculo, objeto, nome, *args):
    url = reverse(f"documentos:{nome}", args=[vinculo.chave, objeto.pk, *args])
    variante = vinculo.variante(objeto)
    return f"{url}?v={variante}" if variante else url


def url_do_editor_completo(vinculo, objeto) -> str:
    return _url(vinculo, objeto, "editor_completo")


@require_GET
def pagina(request, tipo, pk):
    vinculo, objeto = _carregar(request, tipo, pk)
    tipo_doc, dono, variante = _chaves(vinculo, objeto)
    erro = ""
    try:
        vinculo.html_documento(objeto)
    except ValidationError as exc:
        erro = " ".join(exc.messages)
    estado = edicao.estado(tipo_doc, dono, variante)
    return render(request, "documentos/editor/completo.html", {
        "doc": {
            "rotulo": vinculo.rotulo(objeto),
            "subtitulo": vinculo.subtitulo(objeto),
            "url_voltar": vinculo.url_voltar(objeto),
            "rotulo_voltar": vinculo.rotulo_voltar,
            "url_pdf": vinculo.url_pdf(objeto),
            "url_folha": _url(vinculo, objeto, "editor_completo_folha"),
            "url_salvar": _url(vinculo, objeto, "editor_completo_salvar"),
            "url_modelo": _url(vinculo, objeto, "editor_completo_modelo"),
            "bloqueio": bloqueio(vinculo, objeto, request.user),
            "erro": erro,
            "estado": estado.pk if estado else "",
            "versoes": [
                {
                    "linha": linha,
                    "url_restaurar": _url(vinculo, objeto, "editor_completo_restaurar", linha.pk),
                }
                for linha in edicao.versoes(tipo_doc, dono, variante)[:50]
            ],
            **situacao_da_edicao(vinculo, objeto),
        },
    })


@require_GET
@xframe_options_sameorigin
def folha(request, tipo, pk):
    """O documento montado (com a versão editada, se houver) para o iframe."""
    vinculo, objeto = _carregar(request, tipo, pk)
    try:
        html = vinculo.html_documento(objeto)
    except ValidationError as exc:
        raise Http404(" ".join(exc.messages)) from exc
    html = html.replace("</head>", f"<style>{CSS_DO_EDITOR}</style></head>", 1)
    response = HttpResponse(html)
    response["Cache-Control"] = "no-store"
    return response


def _exigir_edicao(request, vinculo, objeto):
    motivo = bloqueio(vinculo, objeto, request.user)
    if motivo:
        raise PermissionDenied(motivo)


@require_POST
def salvar(request, tipo, pk):
    vinculo, objeto = _carregar(request, tipo, pk)
    motivo = bloqueio(vinculo, objeto, request.user)
    if motivo:
        return JsonResponse({"ok": False, "mensagem": motivo}, status=403)
    if len(request.body) > TAMANHO_MAXIMO_CORPO:
        return JsonResponse({"ok": False, "mensagem": "Documento grande demais."}, status=400)
    try:
        corpo = json.loads(request.body or b"{}")
        if not isinstance(corpo, dict):
            raise ValueError
    except ValueError:
        return JsonResponse({"ok": False, "mensagem": "Corpo inválido."}, status=400)
    tipo_doc, dono, variante = _chaves(vinculo, objeto)
    atual = edicao.estado(tipo_doc, dono, variante)
    lida = str(corpo.get("estado") or "")
    if lida != (str(atual.pk) if atual else ""):
        return JsonResponse({
            "ok": False, "conflito": True,
            "mensagem": "Este documento foi alterado por outra pessoa desde que você o abriu. Recarregue para ver a versão atual.",
        }, status=409)
    try:
        base = vinculo.html_documento(objeto, com_edicao=False)
        request.auditoria_origem = "editor"
        nova = edicao.salvar(tipo_doc, dono, variante, corpo.get("regioes"), request.user,
                             impressao_base=edicao.impressao_digital(base))
    except (ValueError, ValidationError) as exc:
        mensagem = " ".join(exc.messages) if isinstance(exc, ValidationError) else str(exc)
        return JsonResponse({"ok": False, "mensagem": mensagem}, status=400)
    return JsonResponse({"ok": True, "estado": nova.pk, "criado_em": nova.criado_em.isoformat()})


@require_POST
def voltar_ao_modelo(request, tipo, pk):
    vinculo, objeto = _carregar(request, tipo, pk)
    _exigir_edicao(request, vinculo, objeto)
    request.auditoria_origem = "editor"
    if edicao.voltar_ao_modelo(*_chaves(vinculo, objeto), request.user) is not None:
        messages.success(request, "O documento voltou ao modelo: sai de novo dos dados. A versão editada fica no histórico.")
    destino = request.POST.get("proximo") or ""
    if destino == "voltar" and vinculo.url_voltar(objeto):
        return redirect(vinculo.url_voltar(objeto))
    return redirect(url_do_editor_completo(vinculo, objeto))


@require_POST
def restaurar(request, tipo, pk, versao):
    vinculo, objeto = _carregar(request, tipo, pk)
    _exigir_edicao(request, vinculo, objeto)
    tipo_doc, dono, variante = _chaves(vinculo, objeto)
    request.auditoria_origem = "editor"
    try:
        # A impressão digital é a da versão restaurada: se os dados mudaram
        # desde ela, o aviso de desatualizada aparece.
        edicao.restaurar(tipo_doc, dono, variante, versao, request.user)
    except ValueError as exc:
        raise Http404(str(exc)) from exc
    messages.success(request, "Versão restaurada: é ela que sai no documento agora.")
    return redirect(url_do_editor_completo(vinculo, objeto))
