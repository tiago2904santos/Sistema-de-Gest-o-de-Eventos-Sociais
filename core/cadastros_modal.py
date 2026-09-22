"""Cadastros de apoio em modal, no desenho dos cadastros das Palestras.

Publicações e Atendimento à Imprensa têm cadastros de um campo só (nome): a
lista em `pages/ascom_cadastros/lista.html`, criar e editar num modal sobre
ela (protocolo `X-Cadastro-Modal` do `ds-v32.js`: GET devolve o trecho, POST
devolve `{"ok": true}` ou o trecho com os erros) e excluir no menu ⋮ — sem
Ativo/Inativo: o que não serve se apaga, e o que está em uso não sai.

Cada módulo descreve os seus cadastros num dicionário `{slug: config}` com
`model`, `form`, `titulo`, `singular`, `novo`, `exemplo`, `icone`, `intro`,
`uso` (função item -> quantos registros o usam) e `uso_rotulo` (singular,
plural), e passa o namespace das rotas (`<ns>:cadastro_lista`, `_novo`,
`_editar`, `_excluir`).
"""

from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import ProtectedError
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse

from .listagens import ITENS_POR_PAGINA


def config_de(cadastros, tipo):
    if tipo not in cadastros:
        raise Http404
    return cadastros[tipo]


def _linha(item, tipo, config, ns):
    uso = config["uso"](item)
    singular, plural = config["uso_rotulo"]
    return {
        "item": item,
        "titulo": str(item),
        "em_uso": uso,
        "uso_rotulo": singular if uso == 1 else plural,
        "icone_uso": config["icone"],
        "url_editar": reverse(f"{ns}:cadastro_editar", args=[tipo, item.pk]),
        "url_excluir": reverse(f"{ns}:cadastro_excluir", args=[tipo, item.pk]),
        "cancelada": False,
    }


def _modal(tipo, config, form, instancia, ns):
    campos = [
        {
            "name": nome,
            "label": campo.label,
            "erros": form.errors.get(nome),
            "obrigatorio": campo.required,
            "valor": "" if form[nome].value() is None else str(form[nome].value()),
        }
        for nome, campo in form.fields.items()
    ]
    erros_gerais = list(form.non_field_errors())
    return {
        "url_acao": (
            reverse(f"{ns}:cadastro_editar", args=[tipo, instancia.pk])
            if instancia
            else reverse(f"{ns}:cadastro_novo", args=[tipo])
        ),
        "titulo": f"Editar {config['singular']}" if instancia else config["novo"],
        "singular": config["singular"],
        "exemplo": config["exemplo"],
        "intro": config["intro"],
        "campos": campos,
        "erros_gerais": erros_gerais,
        "erros_total": sum(1 for c in campos if c["erros"]) + len(erros_gerais),
    }


def lista(request, tipo, *, cadastros, ns, kicker, modulo_titulo, modal=None):
    config = config_de(cadastros, tipo)
    if modal is None and request.method == "GET":
        editar = request.GET.get("editar", "")
        if request.GET.get("novo"):
            modal = _modal(tipo, config, config["form"](), None, ns)
        elif editar.isdigit():
            instancia = get_object_or_404(config["model"], pk=editar)
            modal = _modal(tipo, config, config["form"](instance=instancia), instancia, ns)
    q = request.GET.get("q", "").strip()
    queryset = config["model"].objects.order_by("nome")
    if q:
        queryset = queryset.filter(nome__icontains=q)
    paginador = Paginator(queryset, ITENS_POR_PAGINA)
    pagina = paginador.get_page(request.GET.get("pagina"))
    parametros = request.GET.copy()
    for chave in ("pagina", "novo", "editar"):
        parametros.pop(chave, None)
    grupos = [
        {
            "slug": slug,
            "titulo": outro["titulo"],
            "total": outro["model"].objects.count(),
            "icone": outro["icone"],
            "url": reverse(f"{ns}:cadastro_lista", args=[slug]),
        }
        for slug, outro in cadastros.items()
    ]
    return render(
        request,
        "pages/ascom_cadastros/lista.html",
        {
            "kicker": kicker,
            "modulo_titulo": modulo_titulo,
            "slug": tipo,
            "titulo": config["titulo"],
            "singular": config["singular"],
            "novo": config["novo"],
            "grupos": grupos,
            "url_lista": f"{ns}:cadastro_lista",
            "url_novo": f"{ns}:cadastro_novo",
            "pagina": pagina,
            "linhas": [_linha(item, tipo, config, ns) for item in pagina],
            "paginas_visiveis": list(
                paginador.get_elided_page_range(pagina.number, on_each_side=1, on_ends=1)
            ),
            "elipse": Paginator.ELLIPSIS,
            "querystring": parametros.urlencode(),
            "q": q,
            "tem_filtros": bool(q),
            "modal": modal,
        },
    )


def editar(request, tipo, pk=None, *, cadastros, ns, **contexto):
    config = config_de(cadastros, tipo)
    instancia = get_object_or_404(config["model"], pk=pk) if pk else None
    via_modal = request.headers.get("X-Cadastro-Modal") == "1"
    if request.method == "GET" and not via_modal:
        destino = reverse(f"{ns}:cadastro_lista", args=[tipo])
        return redirect(f"{destino}?{'editar=' + str(pk) if pk else 'novo=1'}")
    if request.method == "POST":
        form = config["form"](request.POST, instance=instancia)
        if form.is_valid():
            form.save()
            messages.success(request, f"{config['singular'].capitalize()} salvo com sucesso.")
            if via_modal:
                return JsonResponse({"ok": True})
            return redirect(f"{ns}:cadastro_lista", tipo=tipo)
    else:
        form = config["form"](instance=instancia)
    modal = _modal(tipo, config, form, instancia, ns)
    if via_modal:
        return render(request, "pages/ascom_cadastros/_modal.html", {"dados": modal})
    return lista(request, tipo, cadastros=cadastros, ns=ns, modal=modal, **contexto)


def excluir(request, tipo, pk, *, cadastros, ns):
    config = config_de(cadastros, tipo)
    objeto = get_object_or_404(config["model"], pk=pk)
    try:
        if config["uso"](objeto):
            raise ProtectedError("em uso", [objeto])
        objeto.delete()
    except ProtectedError:
        messages.error(
            request,
            f"Não é possível excluir: {config['singular']} em uso em registros já feitos.",
        )
    else:
        messages.success(request, f"{config['singular'].capitalize()} excluído.")
    return redirect(f"{ns}:cadastro_lista", tipo=tipo)
