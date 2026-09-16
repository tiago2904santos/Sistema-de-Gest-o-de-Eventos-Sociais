"""A view do editor documental: GET devolve o painel de um campo; PATCH grava.

Só chaves do registro passam; o valor entra no formulário do domínio junto
com o resto do objeto, para as regras de negócio valerem inteiras. A versão
que o navegador leu (`atualizado_em`) vem no corpo; se o objeto mudou desde
então, é 409 e nada é gravado — quem edita decide o que fazer com a versão
nova. Toda gravação daqui entra na auditoria com origem "editor".
"""

from __future__ import annotations

import json

from django.core.exceptions import PermissionDenied
from django.http import Http404, JsonResponse
from django.template.loader import render_to_string
from django.urls import reverse
from django.views.decorators.http import require_http_methods

from . import campos as registro
from .vinculos import vinculo_do_tipo

TAMANHO_MAXIMO_TEXTO = 20_000
TAMANHO_MAXIMO_CORPO = 64 * 1024


def _normalizar(parte, valor):
    """Do JSON para o que o formulário espera. Nada além de tipos simples."""
    if parte.tipo == "booleano":
        return bool(valor) and valor not in ("false", "0", "")
    if parte.tipo == "escolha_multipla":
        if valor is None:
            return []
        if not isinstance(valor, list):
            raise ValueError(f"{parte.nome}: esperava uma lista")
        return [str(item)[:64] for item in valor]
    if valor is None:
        return ""
    if isinstance(valor, (dict, list)):
        raise ValueError(f"{parte.nome}: esperava um valor simples")
    return str(valor)[:TAMANHO_MAXIMO_TEXTO]


def _valor_para_painel(parte, valor):
    if parte.tipo == "booleano":
        return bool(valor) and valor not in ("false", "0", "")
    if parte.tipo == "escolha_multipla":
        return [str(getattr(v, "pk", v)) for v in (valor or [])]
    if parte.tipo == "data" and hasattr(valor, "isoformat"):
        return valor.isoformat()
    return "" if valor is None else str(getattr(valor, "pk", valor))


def _erros_do_form(form, definicao):
    proprios = {nome: [str(e) for e in form.errors.get(nome, [])] for nome in definicao.nomes if nome in form.errors}
    outros = [str(e) for nome, lista in form.errors.items() if nome not in definicao.nomes for e in lista]
    return proprios, outros


def _fragmento(request, vinculo, objeto, definicao, form, *, erros_gerais=()):
    erros_proprios = {}
    if form is not None and form.is_bound:
        erros_proprios, _ = _erros_do_form(form, definicao)
        valores = {nome: form[nome].value() for nome in definicao.nomes}
    else:
        form = vinculo.form(objeto)
        atuais = vinculo.dados_atuais(objeto)
        valores = {nome: atuais.get(nome) for nome in definicao.nomes}
    partes = []
    for parte in definicao.partes:
        valor = _valor_para_painel(parte, valores.get(parte.nome))
        partes.append({
            "definicao": parte,
            "valor": valor,
            "opcoes": vinculo.opcoes(parte, form, valor) if parte.tipo in ("escolha", "escolha_multipla") else None,
            "erros": erros_proprios.get(parte.nome),
            "quando": f"{parte.apenas_quando[0]}={parte.apenas_quando[1]}" if parte.apenas_quando else "",
        })
    return render_to_string("documentos/editor/campo.html", {
        "campo": definicao,
        "partes": partes,
        "erros_gerais": list(erros_gerais),
        "versao": vinculo.versao(objeto),
        "url": reverse("documentos:editor_campo", args=[vinculo.tipo.value, objeto.pk, definicao.chave]),
    }, request=request)


@require_http_methods(["GET", "PATCH"])
def campo(request, tipo, pk, chave):
    if not request.user.is_authenticated:
        raise PermissionDenied
    vinculo = vinculo_do_tipo(tipo)
    if vinculo is None:
        raise Http404
    definicao = registro.campo(vinculo.tipo, chave)
    if definicao is None:
        raise Http404("Campo fora do registro do editor.")
    objeto = vinculo.carregar(pk)
    if not vinculo.pode_editar(request.user, objeto):
        raise PermissionDenied

    if request.method == "GET":
        return JsonResponse({"ok": True, "versao": vinculo.versao(objeto), "fragmento": _fragmento(request, vinculo, objeto, definicao, None)})

    if len(request.body) > TAMANHO_MAXIMO_CORPO:
        return JsonResponse({"ok": False, "mensagem": "Conteúdo grande demais."}, status=400)
    try:
        corpo = json.loads(request.body or b"{}")
        if not isinstance(corpo, dict):
            raise ValueError
    except ValueError:
        return JsonResponse({"ok": False, "mensagem": "Corpo inválido."}, status=400)

    versao_lida = corpo.get("versao")
    if versao_lida is not None and versao_lida != vinculo.versao(objeto):
        return JsonResponse({
            "ok": False, "conflito": True, "versao": vinculo.versao(objeto),
            "mensagem": "Este documento foi alterado por outra pessoa desde que você o abriu. Recarregue para ver a versão atual.",
        }, status=409)

    valores = corpo.get("valores")
    if not isinstance(valores, dict) or not valores or set(valores) - set(definicao.nomes):
        return JsonResponse({"ok": False, "mensagem": "Valores fora do campo pedido."}, status=400)
    dados = vinculo.dados_atuais(objeto)
    try:
        for parte in definicao.partes:
            if parte.nome in valores:
                dados[parte.nome] = _normalizar(parte, valores[parte.nome])
    except ValueError as exc:
        return JsonResponse({"ok": False, "mensagem": str(exc)}, status=400)

    request.auditoria_origem = "editor"
    form = vinculo.form(objeto, dados)
    form.is_valid()
    proprios, outros = _erros_do_form(form, definicao)
    if proprios:
        # Erros voltam por nome; o painel os mostra no lugar sem se redesenhar
        # (redesenhar tiraria o cursor de quem está digitando).
        return JsonResponse({"ok": False, "erros": proprios, "outros_erros": outros}, status=400)
    # Erro em campo que não é este (dado antigo que a regra de hoje rejeita)
    # não trava a edição: o campo fica como está e volta como aviso.
    for nome in list(form.errors):
        if nome not in definicao.nomes:
            form.errors.pop(nome)
    objeto = vinculo.gravar(form, definicao.nomes)
    objeto = vinculo.carregar(objeto.pk)
    return JsonResponse({"ok": True, "versao": vinculo.versao(objeto), "avisos": outros})
