"""Tela dos textos-base dos modelos de documento (m057).

A lista dos tipos de documento (quantos textos foram personalizados, quando
e por quem) leva ao modelo de cada tipo: o documento montado como sai de
verdade (documentos/editor/modelo_folha.py), no desenho do editor completo,
com cada bloco do modelo (documentos/editor/blocos.py: título, linhas do
cabeçalho, parágrafos fixos, rótulos) editável no lugar e os campos
automáticos como etiquetas. O texto gravado aqui vale para os próximos
documentos desse tipo que não tenham o parágrafo reescrito nem uma versão
editada; o que já foi emitido fica no artefato guardado, e a via assinada
nunca muda.

Quem administra: o gestor de Viagens (os documentos de Viagens) e o
administrador do Coffee Break (os do Coffee Break).
"""

from __future__ import annotations

import json

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import Http404, HttpResponse, JsonResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.clickjacking import xframe_options_sameorigin
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from documentos.editor import modelo_folha
from documentos.editor.blocos import REGISTRO_BLOCOS
from documentos.services import modelos_texto

TAMANHO_MAXIMO_CORPO = 512 * 1024

ROTULOS = {
    "oficio": "Ofício",
    "justificativa": "Justificativa",
    "termo_autorizacao": "Termo de autorização",
    "ordem_servico": "Ordem de serviço",
    "plano_trabalho": "Plano de trabalho",
    "relatorio_tecnico": "Relatório técnico",
    "diario_bordo": "Diário de bordo",
    "coffee_break_ordem_servico": "Coffee Break — Ordem de serviço",
    "coffee_break_oficio": "Coffee Break — Ofício",
    "coffee_break_certifico": "Coffee Break — Certifico",
}
MODULOS = {"viagens": "Viagens", "coffee_break": "Coffee Break"}

AVISO_PROXIMOS = (
    "O texto do modelo vale para os próximos documentos deste tipo. Os já emitidos e as vias assinadas não mudam, "
    "e documento com o parágrafo reescrito ou com versão editada (“Editar documento completo”) mantém o texto dele."
)


def _valor(tipo) -> str:
    return str(getattr(tipo, "value", tipo))


def _do_coffee(tipo) -> bool:
    return _valor(tipo).startswith("coffee_break")


def _modulo(tipo) -> str:
    return "coffee_break" if _do_coffee(tipo) else "viagens"


def pode_administrar(usuario, tipo) -> bool:
    if not getattr(usuario, "is_authenticated", False):
        return False
    if _do_coffee(tipo):
        from coffee_break.permissions import pode_acessar
        from solicitacoes.permissions import eh_administrador

        return pode_acessar(usuario) and eh_administrador(usuario)
    from viagens_cadastros.permissions import eh_gestor_viagens, pode_acessar

    return pode_acessar(usuario) and eh_gestor_viagens(usuario)


def tipos_do_usuario(usuario, modulo=None) -> list[dict]:
    tipos = [
        t for t in REGISTRO_BLOCOS
        if REGISTRO_BLOCOS[t] and pode_administrar(usuario, t) and (modulo is None or _modulo(t) == modulo)
    ]
    ordem = list(ROTULOS)
    tipos.sort(key=lambda t: ordem.index(_valor(t)) if _valor(t) in ordem else len(ordem))
    return [{"tipo": t, "valor": _valor(t), "rotulo": ROTULOS.get(_valor(t), _valor(t)), "modulo": _modulo(t),
             "url": reverse("documentos:modelos_tipo", args=[_valor(t)])} for t in tipos]


def _tipo_da_url(valor):
    return next((t for t in REGISTRO_BLOCOS if _valor(t) == valor), None)


def _tipo_administrado(request, valor):
    tipo_doc = _tipo_da_url(valor)
    if tipo_doc is None or not REGISTRO_BLOCOS.get(tipo_doc):
        raise Http404("Tipo de documento sem modelo.")
    if not pode_administrar(request.user, tipo_doc):
        raise PermissionDenied
    return tipo_doc


# ---- A lista dos tipos ----------------------------------------------------


@login_required
@require_GET
def indice(request, modulo=None):
    if modulo is not None and modulo not in MODULOS:
        raise Http404
    tipos = tipos_do_usuario(request.user, modulo)
    if not tipos:
        raise PermissionDenied
    grupos = []
    for chave, nome in MODULOS.items():
        cartoes = []
        for t in tipos:
            if t["modulo"] != chave:
                continue
            cartoes.append({**t, **modelos_texto.resumo(t["tipo"]), "blocos": len(REGISTRO_BLOCOS[t["tipo"]])})
        if cartoes:
            grupos.append({"nome": nome, "cartoes": cartoes})
    return render(request, "pages/documentos/modelos.html", {
        "titulo": "Textos dos documentos",
        "grupos": grupos,
        "aviso": AVISO_PROXIMOS,
        "breadcrumb": [{"label": "Textos dos documentos"}],
    })


# ---- O modelo de um tipo --------------------------------------------------


def _url(nome, tipo_doc):
    return reverse(f"documentos:{nome}", args=[_valor(tipo_doc)])


def _usuario(linha):
    return str(linha.criado_por) if linha and linha.criado_por_id else ("Sistema" if linha else "")


@login_required
@require_http_methods(["GET", "POST"])
def tipo(request, tipo):
    """GET: a tela do modelo. POST: voltar um bloco ao padrão do sistema, ou
    usar de novo um texto do histórico (os botões da tela)."""
    tipo_doc = _tipo_administrado(request, tipo)
    blocos = REGISTRO_BLOCOS[tipo_doc]

    if request.method == "POST":
        request.auditoria_origem = "editor"
        lida = request.POST.get("estado")
        if lida is not None and lida != modelos_texto.estado(tipo_doc):
            messages.error(request, "O modelo foi alterado por outra pessoa desde que você o abriu. Veja a versão atual e tente de novo.")
        elif request.POST.get("padrao") in blocos:
            modelos_texto.gravar(tipo_doc, request.POST["padrao"], "", request.user)
            messages.success(request, f"“{blocos[request.POST['padrao']].rotulo}” voltou ao texto padrão do sistema.")
        elif request.POST.get("usar"):
            linha = modelos_texto.linhas(tipo_doc).filter(pk=request.POST["usar"]).first() if request.POST["usar"].isdigit() else None
            if linha is None or linha.chave not in blocos or linha.padrao_sistema:
                raise Http404
            modelos_texto.gravar(tipo_doc, linha.chave, linha.texto, request.user)
            messages.success(request, f"“{blocos[linha.chave].rotulo}” voltou ao texto de {linha.criado_em:%d/%m/%Y %H:%M}.")
        return redirect(request.path)

    montada = modelo_folha.folha(tipo_doc, request.user)
    vigentes = modelos_texto.textos_vigentes(tipo_doc)
    ultimas = {}
    historico = list(modelos_texto.linhas(tipo_doc)[:200])
    for linha in historico:
        ultimas.setdefault(linha.chave, linha)
    dados_dos_blocos = {}
    for chave, bloco in blocos.items():
        ultima = ultimas.get(chave) if chave in vigentes else None
        dados_dos_blocos[chave] = {
            "rotulo": bloco.rotulo,
            "campos": modelos_texto.campos_do_bloco(bloco),
            "alterado": chave in vigentes,
            "quando": f"{ultima.criado_em:%d/%m/%Y %H:%M}" if ultima else "",
            "quem": _usuario(ultima),
            "na_folha": chave in montada["na_folha"],
        }
    fora = [
        {"bloco": bloco, "html": modelo_folha.trecho_editavel(bloco, vigentes.get(chave, bloco.padrao), chave in vigentes, "div")}
        for chave, bloco in blocos.items() if chave not in montada["na_folha"]
    ]
    rotulo = ROTULOS.get(_valor(tipo_doc), _valor(tipo_doc))
    return render(request, "documentos/editor/modelo.html", {
        "doc": {
            "rotulo": rotulo,
            "tipo": _valor(tipo_doc),
            "origem": montada["origem"],
            "sintetico": montada["sintetico"],
            "url_folha": _url("modelos_folha", tipo_doc),
            "url_salvar": _url("modelos_salvar", tipo_doc),
            "url_voltar": reverse("documentos:modelos_modulo", args=[_modulo(tipo_doc)]),
            "estado": modelos_texto.estado(tipo_doc),
            "aviso": AVISO_PROXIMOS,
            "personalizados": len(vigentes),
            "fora": fora,
            "blocos": dados_dos_blocos,
            "historico": [
                {"linha": linha, "rotulo": blocos[linha.chave].rotulo if linha.chave in blocos else linha.chave,
                 # "Usar de novo" só para um texto que não é o que vale hoje.
                 "reusar": not linha.padrao_sistema and linha.chave in blocos and vigentes.get(linha.chave) != linha.texto}
                for linha in historico[:40]
            ],
        },
    })


@login_required
@require_GET
@xframe_options_sameorigin
def folha(request, tipo):
    """O documento montado com os blocos editáveis, para o iframe da tela."""
    tipo_doc = _tipo_administrado(request, tipo)
    response = HttpResponse(modelo_folha.folha(tipo_doc, request.user)["html"])
    response["Cache-Control"] = "no-store"
    return response


@require_POST
def salvar(request, tipo):
    """Grava os blocos alterados: JSON {estado, blocos: {chave: texto com
    `{campo}`}}. Quem salva manda a marca do modelo que leu; se outra pessoa
    gravou no meio, a gravação é recusada (409) e a tela pede para recarregar."""
    if not request.user.is_authenticated:
        return JsonResponse({"ok": False, "mensagem": "Entre no sistema de novo."}, status=403)
    tipo_doc = _tipo_da_url(tipo)
    if tipo_doc is None or not REGISTRO_BLOCOS.get(tipo_doc):
        raise Http404("Tipo de documento sem modelo.")
    if not pode_administrar(request.user, tipo_doc):
        return JsonResponse({"ok": False, "mensagem": "Você não tem permissão para alterar este modelo."}, status=403)
    if len(request.body) > TAMANHO_MAXIMO_CORPO:
        return JsonResponse({"ok": False, "mensagem": "Texto grande demais."}, status=400)
    try:
        corpo = json.loads(request.body or b"{}")
        if not isinstance(corpo, dict) or not isinstance(corpo.get("blocos", {}), dict):
            raise ValueError
    except ValueError:
        return JsonResponse({"ok": False, "mensagem": "Corpo inválido."}, status=400)
    if str(corpo.get("estado") or "") != modelos_texto.estado(tipo_doc):
        return JsonResponse({
            "ok": False, "conflito": True,
            "mensagem": "O modelo foi alterado por outra pessoa desde que você o abriu. Recarregue para ver a versão atual; o que você escreveu não foi salvo.",
        }, status=409)
    request.auditoria_origem = "editor"
    try:
        gravados = modelos_texto.salvar_blocos(tipo_doc, corpo.get("blocos") or {}, request.user)
    except ValueError as exc:
        return JsonResponse({"ok": False, "mensagem": str(exc)}, status=400)
    if gravados:
        messages.success(request, "Modelo salvo. Os próximos documentos já saem com o texto novo; os já emitidos e os assinados não mudam.")
    else:
        messages.info(request, "Nada mudou no modelo.")
    return JsonResponse({"ok": True, "estado": modelos_texto.estado(tipo_doc), "gravados": gravados})
