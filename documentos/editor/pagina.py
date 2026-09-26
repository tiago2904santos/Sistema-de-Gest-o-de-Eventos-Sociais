"""O editor de documento, para qualquer tipo, embutido no fim do formulário.

Não há tela própria: o editor é o visualizador de documentos de cada
cadastro. `contexto_da_pagina` monta o `doc` que
`documentos/editor/embutido.html` usa, a partir do vínculo do tipo
(documentos/editor/vinculos.py): nome, situação, rota do PDF, pendências de
emissão, histórico e as rotas da API. `embutido` devolve o editor (HTML que o
formulário busca quando o cartão do documento abre), `folha` o documento do
iframe, e `pagina` — o endereço antigo da tela — leva ao formulário, no
cartão do documento.
"""

from __future__ import annotations

from django.core.exceptions import PermissionDenied
from django.http import Http404, HttpResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.clickjacking import xframe_options_sameorigin
from django.views.decorators.http import require_GET

from .blocos import quebras_do_tipo
from .campos import ORIGENS_POR_OBJETO, campos_do_tipo
from .vinculos import vinculo_do_tipo



def contexto_da_pagina(request, vinculo, objeto) -> dict:
    from .completo import situacao_da_edicao, url_do_editor_completo

    tipo = vinculo.tipo.value
    pode_editar = vinculo.pode_editar(request.user, objeto)
    origens = vinculo.origens_editaveis(request.user) if pode_editar else set()
    # O menu "Campos" lista o que não depende de uma linha do documento (o
    # servidor de uma linha, o trecho do diário se editam na própria folha).
    menu = [
        campo for campo in campos_do_tipo(vinculo.chave).values()
        if campo.origem in origens and campo.origem not in ORIGENS_POR_OBJETO
    ]
    return {
        "doc": {
            "tipo": tipo,
            "rotulo": vinculo.rotulo(objeto),
            "situacao": vinculo.situacao(objeto),
            "subtitulo": vinculo.subtitulo(objeto),
            "url_voltar": vinculo.url_voltar(objeto),
            "rotulo_voltar": vinculo.rotulo_voltar,
            "url_pdf": vinculo.url_pdf(objeto),
            "pode_emitir": vinculo.pode_emitir(request.user, objeto),
            "pendencias": vinculo.pendencias(objeto),
            "historico": vinculo.historico(objeto),
            "url_folha": vinculo.url("folha", objeto),
            "api": {especie: vinculo.url(especie, objeto, "CHAVE") for especie in ("campo", "bloco", "quebra")},
            "principais": " ".join(vinculo.principais),
            "versao": vinculo.versao(objeto),
            "pode_editar": pode_editar,
            "campos_menu": menu,
            "tem_quebras": bool(quebras_do_tipo(vinculo.tipo)),
            # Editor completo (m057): o documento inteiro, editado à mão.
            "url_completo": url_do_editor_completo(vinculo, objeto),
            "edicao_completa": situacao_da_edicao(vinculo, objeto),
        },
    }


def _carregar(request, tipo, pk):
    if not request.user.is_authenticated:
        raise PermissionDenied
    vinculo = vinculo_do_tipo(tipo)
    if vinculo is None:
        raise Http404("Tipo de documento sem editor.")
    objeto = vinculo.carregar(pk, request.GET.get("v", ""))
    if not vinculo.pode_ver(request.user):
        raise PermissionDenied
    return vinculo, objeto


def id_do_cartao(chave, variante="") -> str:
    """O id do cartão do documento no formulário (o atalho das listas o abre)."""
    return f"documento-{chave}-{variante}" if variante not in ("", None) else f"documento-{chave}"


def cartao(chave, pk, titulo, variante="") -> dict:
    """Um documento para o visualizador do formulário
    (`documentos/editor/_visualizador.html` e os cartões do ofício)."""
    url = reverse("documentos:editor_embutido", args=[chave, pk])
    if variante not in ("", None):
        url += f"?v={variante}"
    return {"id": id_do_cartao(chave, variante), "titulo": titulo, "url": url}


@require_GET
def pagina(request, tipo, pk):
    """O endereço da antiga tela do editor: leva ao formulário do documento,
    com o cartão dele aberto."""
    vinculo, objeto = _carregar(request, tipo, pk)
    destino = vinculo.url_voltar(objeto)
    if not destino:
        raise Http404
    return redirect(f"{destino}#{id_do_cartao(vinculo.chave, vinculo.variante(objeto))}")


@require_GET
def embutido(request, tipo, pk):
    """O editor do documento, para o cartão do formulário."""
    vinculo, objeto = _carregar(request, tipo, pk)
    return render(request, "documentos/editor/embutido.html", contexto_da_pagina(request, vinculo, objeto))


@require_GET
@xframe_options_sameorigin
def folha(request, tipo, pk):
    """O documento no modo editor: o que o iframe da tela mostra."""
    vinculo, objeto = _carregar(request, tipo, pk)
    response = HttpResponse(vinculo.folha(objeto, request.user))
    response["Cache-Control"] = "no-store"
    return response
