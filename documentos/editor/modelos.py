"""Tela dos textos-base dos modelos de documento (m057).

Para cada tipo de documento, os blocos do modelo (documentos/editor/
blocos.py: título, linhas do cabeçalho, parágrafos fixos, rótulos) com o
texto em vigor, o padrão do sistema e os campos automáticos que o bloco
aceita. O texto gravado aqui vale para os documentos desse tipo que não
tenham o parágrafo reescrito nem uma versão editada; o que já foi emitido
fica no artefato guardado, e a via assinada nunca muda.

Quem administra: o gestor de Viagens (os documentos de Viagens) e o
administrador do Coffee Break (os do Coffee Break).
"""

from __future__ import annotations

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import Http404
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.http import require_http_methods

from documentos.editor.blocos import REGISTRO_BLOCOS
from documentos.services import modelos_texto

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


def _valor(tipo) -> str:
    return str(getattr(tipo, "value", tipo))


def _do_coffee(tipo) -> bool:
    return _valor(tipo).startswith("coffee_break")


def pode_administrar(usuario, tipo) -> bool:
    if not getattr(usuario, "is_authenticated", False):
        return False
    if _do_coffee(tipo):
        from coffee_break.permissions import pode_acessar
        from solicitacoes.permissions import eh_administrador

        return pode_acessar(usuario) and eh_administrador(usuario)
    from viagens_cadastros.permissions import eh_gestor_viagens, pode_acessar

    return pode_acessar(usuario) and eh_gestor_viagens(usuario)


def tipos_do_usuario(usuario) -> list[dict]:
    tipos = [t for t in REGISTRO_BLOCOS if REGISTRO_BLOCOS[t] and pode_administrar(usuario, t)]
    ordem = list(ROTULOS)
    tipos.sort(key=lambda t: ordem.index(_valor(t)) if _valor(t) in ordem else len(ordem))
    return [{"tipo": t, "valor": _valor(t), "rotulo": ROTULOS.get(_valor(t), _valor(t)),
             "url": reverse("documentos:modelos_tipo", args=[_valor(t)])} for t in tipos]


def _tipo_da_url(valor):
    return next((t for t in REGISTRO_BLOCOS if _valor(t) == valor), None)


@login_required
def indice(request):
    tipos = tipos_do_usuario(request.user)
    if not tipos:
        raise PermissionDenied
    return redirect(tipos[0]["url"])


@login_required
@require_http_methods(["GET", "POST"])
def tipo(request, tipo):
    tipo_doc = _tipo_da_url(tipo)
    if tipo_doc is None:
        raise Http404("Tipo de documento sem modelo.")
    if not pode_administrar(request.user, tipo_doc):
        raise PermissionDenied
    blocos = REGISTRO_BLOCOS[tipo_doc]

    if request.method == "POST":
        request.auditoria_origem = "editor"
        if request.POST.get("padrao") in blocos:
            modelos_texto.gravar(tipo_doc, request.POST["padrao"], "", request.user)
            messages.success(request, f"“{blocos[request.POST['padrao']].rotulo}” voltou ao texto padrão do sistema.")
        elif request.POST.get("usar"):
            linha = modelos_texto.linhas(tipo_doc).filter(pk=request.POST["usar"]).first()
            if linha is None or linha.chave not in blocos:
                raise Http404
            modelos_texto.gravar(tipo_doc, linha.chave, linha.texto, request.user)
            messages.success(request, f"“{blocos[linha.chave].rotulo}” voltou ao texto de {linha.criado_em:%d/%m/%Y %H:%M}.")
        else:
            alterados = 0
            for chave in blocos:
                campo = f"texto__{chave}"
                if campo not in request.POST:
                    continue
                antes = modelos_texto.texto_vigente(tipo_doc, chave)
                modelos_texto.gravar(tipo_doc, chave, request.POST[campo], request.user)
                if modelos_texto.texto_vigente(tipo_doc, chave) != antes:
                    alterados += 1
            if alterados:
                messages.success(request, "Modelo salvo. Os próximos documentos já saem com o texto novo; os já emitidos e os assinados não mudam.")
            else:
                messages.info(request, "Nada mudou no modelo.")
        return redirect(request.path)

    vigentes = modelos_texto.textos_vigentes(tipo_doc)
    ultimas = {}
    for linha in modelos_texto.linhas(tipo_doc)[:200]:
        ultimas.setdefault(linha.chave, linha)
    itens = []
    for chave, bloco in blocos.items():
        texto = vigentes.get(chave, bloco.padrao)
        itens.append({
            "bloco": bloco,
            "campo": f"texto__{chave}",
            "texto": texto,
            "alterado": chave in vigentes,
            "ultima": ultimas.get(chave),
            "campos": modelos_texto.campos_do_bloco(bloco),
            "desconhecidos": modelos_texto.marcadores_desconhecidos(bloco, texto),
            "linhas": max(2, min(8, len(texto) // 70 + 1)),
        })
    rotulo = ROTULOS.get(_valor(tipo_doc), _valor(tipo_doc))
    return render(request, "pages/documentos/modelos.html", {
        "titulo": "Textos dos modelos de documento",
        "rotulo": rotulo,
        "tipo": _valor(tipo_doc),
        "tipos": tipos_do_usuario(request.user),
        "itens": itens,
        "historico": [
            {"linha": linha, "rotulo": blocos[linha.chave].rotulo if linha.chave in blocos else linha.chave}
            for linha in modelos_texto.linhas(tipo_doc)[:30]
        ],
        "breadcrumb": [{"label": "Modelos de documento"}, {"label": rotulo}],
    })
