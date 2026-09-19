"""A view do editor documental: GET devolve o painel de um campo; PATCH grava.

Só chaves do registro passam; o valor entra no formulário do domínio junto
com o resto do objeto, para as regras de negócio valerem inteiras. A versão
que o navegador leu (`atualizado_em`) vem no corpo; se o objeto mudou desde
então, é 409 e nada é gravado — quem edita decide o que fazer com a versão
nova. Toda gravação daqui entra na auditoria com origem "editor".
"""

from __future__ import annotations

import json

from django.core.exceptions import PermissionDenied, ValidationError
from django.http import Http404, JsonResponse
from django.template.loader import render_to_string
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


def _url_do_campo(vinculo, objeto, definicao, objeto_id):
    url = vinculo.url("campo", objeto, definicao.chave)
    if not objeto_id:
        return url
    return f"{url}{'&' if '?' in url else '?'}objeto={objeto_id}"


def _fragmento(request, vinculo, objeto, definicao, fonte, alvo, objeto_id, *, erros_gerais=()):
    form = fonte.form(alvo)
    atuais = fonte.dados_atuais(alvo)
    valores = {nome: atuais.get(nome) for nome in definicao.nomes}
    partes = []
    for parte in definicao.partes:
        valor = _valor_para_painel(parte, valores.get(parte.nome))
        partes.append({
            "definicao": parte,
            "valor": valor,
            "opcoes": fonte.opcoes(parte, form, valor) if parte.tipo in ("escolha", "escolha_multipla") else None,
            "erros": None,
            "quando": f"{parte.apenas_quando[0]}={parte.apenas_quando[1]}" if parte.apenas_quando else "",
        })
    return render_to_string("documentos/editor/campo.html", {
        "campo": definicao,
        "partes": partes,
        "erros_gerais": list(erros_gerais),
        "versao": fonte.versao(alvo),
        "links": fonte.links(definicao, objeto, alvo),
        "objeto_id": objeto_id or "",
        "url": _url_do_campo(vinculo, objeto, definicao, objeto_id),
    }, request=request)


def _acesso(request, tipo, pk):
    """Quem pode editar o quê: autenticado, tipo com vínculo, objeto
    existente e permissão do domínio. Vale para campo, bloco e quebra."""
    if not request.user.is_authenticated:
        raise PermissionDenied
    vinculo = vinculo_do_tipo(tipo)
    if vinculo is None:
        raise Http404
    # A variante (o servidor do termo) vem na URL de todas as chamadas.
    objeto = vinculo.carregar(pk, request.GET.get("v", ""))
    if not vinculo.pode_editar(request.user, objeto):
        raise PermissionDenied
    return vinculo, objeto


def _corpo(request):
    if len(request.body) > TAMANHO_MAXIMO_CORPO:
        return None, JsonResponse({"ok": False, "mensagem": "Conteúdo grande demais."}, status=400)
    try:
        corpo = json.loads(request.body or b"{}")
        if not isinstance(corpo, dict):
            raise ValueError
    except ValueError:
        return None, JsonResponse({"ok": False, "mensagem": "Corpo inválido."}, status=400)
    return corpo, None


def _gravado(request, vinculo, objeto, *, versao=None, **extra):
    """Resposta de gravação: além da versão, a folha já remontada.

    Quem grava atualiza o documento na hora com esse HTML, em vez de mandar o
    iframe recarregar. Vínculo sem `folha` devolve `None` e o navegador cai no
    recarregamento de antes. `versao` entra explícita para o bloco, cuja versão
    é a do override e não a do objeto.
    """
    montar = getattr(vinculo, "folha", None)
    return JsonResponse({
        "ok": True,
        "versao": vinculo.versao(objeto) if versao is None else versao,
        "folha": montar(objeto, request.user) if montar else None,
        **extra,
    })


def _conflito(versao_atual):
    return JsonResponse({
        "ok": False, "conflito": True, "versao": versao_atual,
        "mensagem": "Este documento foi alterado por outra pessoa desde que você o abriu. Recarregue para ver a versão atual.",
    }, status=409)


@require_http_methods(["GET", "PATCH"])
def campo(request, tipo, pk, chave):
    vinculo, objeto = _acesso(request, tipo, pk)
    definicao = registro.campo(vinculo.chave, chave)
    if definicao is None:
        raise Http404("Campo fora do registro do editor.")
    # A origem do trecho decide o registro que muda (o ofício, o cadastro do
    # servidor, a prestação, a configuração) e quem pode mudá-lo.

    fonte = vinculo.fonte(definicao.origem)
    if fonte is None:
        raise Http404
    if not fonte.pode_editar(request.user, objeto):
        raise PermissionDenied
    objeto_id = request.GET.get("objeto") or ""
    alvo = fonte.alvo(objeto, objeto_id, request.user)

    if request.method == "GET":
        return JsonResponse({"ok": True, "versao": fonte.versao(alvo), "fragmento": _fragmento(request, vinculo, objeto, definicao, fonte, alvo, objeto_id)})

    corpo, erro = _corpo(request)
    if erro is not None:
        return erro
    versao_lida = corpo.get("versao")
    if versao_lida is not None and versao_lida != fonte.versao(alvo):
        return _conflito(fonte.versao(alvo))

    valores = corpo.get("valores")
    if not isinstance(valores, dict) or not valores or set(valores) - set(definicao.nomes):
        return JsonResponse({"ok": False, "mensagem": "Valores fora do campo pedido."}, status=400)
    dados = fonte.dados_atuais(alvo)
    try:
        for parte in definicao.partes:
            if parte.nome in valores:
                dados[parte.nome] = _normalizar(parte, valores[parte.nome])
    except ValueError as exc:
        return JsonResponse({"ok": False, "mensagem": str(exc)}, status=400)

    request.auditoria_origem = "editor"
    form = fonte.form(alvo, dados)
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
    try:
        fonte.gravar(form, definicao.nomes, alvo)
    except ValidationError as exc:
        # Regra do domínio que só o serviço conhece (a diária recebida acima
        # do liberado): volta como erro do campo, como os do formulário.
        erros = exc.message_dict if hasattr(exc, "error_dict") else {definicao.nomes[0]: exc.messages}
        return JsonResponse({"ok": False, "erros": erros, "outros_erros": []}, status=400)
    objeto = vinculo.carregar(objeto.pk, request.GET.get("v", ""))
    alvo = fonte.alvo(objeto, objeto_id, request.user)
    return _gravado(request, vinculo, objeto, versao=fonte.versao(alvo), avisos=outros)


def _fragmento_bloco(request, vinculo, objeto, definicao):
    from documentos.services.document_blocks import bloco_gravado

    gravado = bloco_gravado(vinculo.tipo, vinculo.dono_dos_blocos(objeto), definicao.chave)
    editado = bool(gravado and gravado.editado_manualmente)
    return render_to_string("documentos/editor/bloco.html", {
        "bloco": definicao,
        "conteudo": gravado.conteudo_atual if editado else definicao.padrao,
        "editado": editado,
        "editado_por": str(gravado.editado_por) if editado and gravado.editado_por_id else "",
        "editado_em": gravado.editado_em if editado else None,
        "url": vinculo.url("bloco", objeto, definicao.chave),
    }, request=request)


@require_http_methods(["GET", "PATCH", "DELETE"])
def bloco(request, tipo, pk, chave):
    """Parágrafo do modelo: GET devolve o painel, PATCH grava o override
    (texto vazio ou igual ao modelo restaura), DELETE restaura."""
    from documentos.editor import blocos as registro_blocos
    from documentos.services.document_blocks import gravar_override, restaurar, versao_do_bloco

    vinculo, objeto = _acesso(request, tipo, pk)
    definicao = registro_blocos.bloco(vinculo.tipo, chave)
    if definicao is None:
        raise Http404("Bloco fora do registro do editor.")
    dono = vinculo.dono_dos_blocos(objeto)

    if request.method == "GET":
        return JsonResponse({"ok": True, "versao": versao_do_bloco(vinculo.tipo, dono, chave), "fragmento": _fragmento_bloco(request, vinculo, objeto, definicao)})

    request.auditoria_origem = "editor"
    if request.method == "DELETE":
        restaurar(vinculo.tipo, dono, chave)
        return _gravado(request, vinculo, objeto, versao=versao_do_bloco(vinculo.tipo, dono, chave), editado=False)

    corpo, erro = _corpo(request)
    if erro is not None:
        return erro
    versao_lida = corpo.get("versao")
    if versao_lida is not None and versao_lida != versao_do_bloco(vinculo.tipo, dono, chave):
        return _conflito(versao_do_bloco(vinculo.tipo, dono, chave))
    valores = corpo.get("valores")
    if not isinstance(valores, dict) or set(valores) != {"conteudo"} or isinstance(valores["conteudo"], (dict, list)):
        return JsonResponse({"ok": False, "mensagem": "Esperava só o texto do parágrafo."}, status=400)
    conteudo = str(valores["conteudo"] or "").replace("\r\n", "\n").strip()[:TAMANHO_MAXIMO_TEXTO]
    # O texto do modelo com o marcador já preenchido (como a folha o mostra e
    # quem digita nela o devolve) também é o modelo: restaura, não grava.
    iguais_ao_modelo = {definicao.padrao} | {definicao.padrao.replace("{assunto}", termo) for termo in ("autorização", "convalidação")}
    if not conteudo or conteudo in iguais_ao_modelo:
        restaurar(vinculo.tipo, dono, chave)
        editado = False
    else:
        gravar_override(vinculo.tipo, dono, chave, conteudo, request.user)
        editado = True
    return _gravado(request, vinculo, objeto, versao=versao_do_bloco(vinculo.tipo, dono, chave), editado=editado)


@require_http_methods(["PATCH"])
def quebra(request, tipo, pk, chave):
    """Liga ou desliga a quebra de página num ponto registrado."""
    from documentos.editor import blocos as registro_blocos
    from documentos.services.document_blocks import definir_quebra

    vinculo, objeto = _acesso(request, tipo, pk)
    if registro_blocos.ponto_de_quebra(vinculo.tipo, chave) is None:
        raise Http404("Ponto de quebra fora do registro.")
    corpo, erro = _corpo(request)
    if erro is not None:
        return erro
    if not isinstance(corpo.get("ativa"), bool):
        return JsonResponse({"ok": False, "mensagem": "Informe se a quebra fica ativa."}, status=400)
    request.auditoria_origem = "editor"
    ativa = definir_quebra(vinculo.tipo, vinculo.dono_dos_blocos(objeto), chave, corpo["ativa"], request.user)
    return _gravado(request, vinculo, objeto, ativa=ativa)
