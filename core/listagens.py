"""Utilidades compartilhadas das listagens e cadastros dos módulos.

Paginação, ordenação segura por colunas e descrição de campos de formulário
para os components do design system — o mesmo contrato usado pelas telas
V3.2 (solicitações, cadastros), reaproveitado pelos módulos da ASCOM.
"""

from django import forms
from django.core.paginator import Paginator

ITENS_POR_PAGINA = 20


def opcoes(iteravel):
    """Lista de {valor, rotulo} a partir de objetos com pk (ou strings)."""
    return [
        {"valor": str(getattr(item, "pk", item)), "rotulo": str(item)}
        for item in iteravel
    ]


def opcoes_choices(choices):
    return [{"valor": str(valor), "rotulo": str(rotulo)} for valor, rotulo in choices]


def valores_filtro(filtros):
    """Valores atuais dos filtros como strings (para preencher os controles)."""
    return {
        nome: ("" if filtros[nome].value() is None else str(filtros[nome].value()))
        for nome in filtros.fields
    }


def paginar(request, queryset, por_pagina=ITENS_POR_PAGINA):
    paginador = Paginator(queryset, por_pagina)
    pagina = paginador.get_page(request.GET.get("pagina"))
    paginas_visiveis = list(
        paginador.get_elided_page_range(pagina.number, on_each_side=1, on_ends=1)
    )
    parametros = request.GET.copy()
    parametros.pop("pagina", None)
    return pagina, paginas_visiveis, parametros.urlencode()


def ordenacao(request, ordenacoes, padrao):
    """(pedido, campos do order_by) a partir de ?ordem=, ignorando chaves estranhas."""
    pedido = request.GET.get("ordem") or padrao
    decrescente = pedido.startswith("-")
    chave = pedido.lstrip("-")
    if chave not in ordenacoes:
        pedido = padrao
        decrescente = padrao.startswith("-")
        chave = padrao.lstrip("-")
    campos = ordenacoes[chave]
    if decrescente:
        campos = [
            campo[1:] if campo.startswith("-") else f"-{campo}" for campo in campos
        ]
    return pedido, campos


def colunas_ordenaveis(request, pedido, colunas, ordenacoes):
    """Cabeçalhos da tabela com URL de ordenação e estado ativo.

    ``colunas``: lista de (chave, rótulo) ou (chave, rótulo, classe CSS).
    """
    parametros = request.GET.copy()
    parametros.pop("pagina", None)
    parametros.pop("ordem", None)
    base = parametros.urlencode()
    atual = pedido.lstrip("-")
    decrescente = pedido.startswith("-")

    resultado = []
    for coluna in colunas:
        chave, rotulo = coluna[0], coluna[1]
        classe = coluna[2] if len(coluna) > 2 else ""
        if chave not in ordenacoes:
            resultado.append(
                {"chave": chave, "rotulo": rotulo, "url": "", "classe": classe}
            )
            continue
        ativa = chave == atual
        proximo = f"-{chave}" if ativa and not decrescente else chave
        resultado.append(
            {
                "chave": chave,
                "rotulo": rotulo,
                "classe": classe,
                "ativa": ativa,
                "descendente": ativa and decrescente,
                "url": f"?{base}&ordem={proximo}" if base else f"?ordem={proximo}",
            }
        )
    return resultado


def campos_formulario(form):
    """Descreve os campos do form para o template genérico de cadastro."""
    campos = []
    for nome, campo in form.fields.items():
        if isinstance(campo.widget, forms.HiddenInput):
            continue
        valor = form[nome].value()
        item = {
            "name": nome,
            "label": campo.label,
            "erros": form.errors.get(nome),
            "obrigatorio": campo.required,
            "ajuda": campo.help_text,
            "valor": "" if valor is None else str(valor),
        }
        if isinstance(campo, forms.ModelChoiceField):
            item.update({"tipo": "select", "opcoes": opcoes(campo.queryset)})
        elif isinstance(campo.widget, forms.Textarea):
            item["tipo"] = "textarea"
        elif isinstance(campo, forms.BooleanField):
            item["tipo"] = "boolean"
            item["valor"] = bool(valor)
        else:
            item["tipo"] = "input"
        campos.append(item)
    return campos
