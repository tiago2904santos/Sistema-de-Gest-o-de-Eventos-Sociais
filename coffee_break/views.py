"""Views do módulo de Coffee Break da ASCOM.

Todas as rotas exigem o módulo ASCOM_COFFEE_BREAK (decorator + middleware);
ocultar o menu nunca é a única barreira.
"""

from django import forms
from django.contrib import messages
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.db.models import Q, Sum
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from .forms import (
    ContratoCoffeeBreakForm,
    FiltroLotesForm,
    FiltroSolicitacoesCoffeeForm,
    FornecedorForm,
    LoteCoffeeBreakForm,
    SolicitacaoCoffeeBreakForm,
)
from .models import (
    AcaoHistoricoCoffeeBreak,
    ContratoCoffeeBreak,
    Fornecedor,
    LoteCoffeeBreak,
    SituacaoFinanceira,
    SolicitacaoCoffeeBreak,
)
from core.listagens import trilha_de_situacoes

from .permissions import acesso_ao_modulo, gerenciamento_de_cadastros
from .presenters import filas_de_situacao, linha_da_lista, linha_do_cadastro, linha_do_lote, selo_do_consumo
from . import documents, services

ITENS_POR_PAGINA = 15


# ---------------------------------------------------------------------------
# Helpers de contexto para os components do design system
# ---------------------------------------------------------------------------

def _opcoes(iteravel):
    return [
        {"valor": str(getattr(item, "pk", item)), "rotulo": str(item)}
        for item in iteravel
    ]


def _opcoes_choices(choices):
    return [{"valor": str(valor), "rotulo": str(rotulo)} for valor, rotulo in choices]


def _breadcrumb(*itens):
    trilha = [{"label": "Coffee Break", "url": reverse("coffee_break:painel")}]
    trilha.extend(itens)
    return trilha


def _valores_filtro(filtros):
    return {
        nome: ("" if filtros[nome].value() is None else str(filtros[nome].value()))
        for nome in filtros.fields
    }


def _paginar(request, queryset):
    paginador = Paginator(queryset, ITENS_POR_PAGINA)
    pagina = paginador.get_page(request.GET.get("pagina"))
    paginas_visiveis = list(
        paginador.get_elided_page_range(pagina.number, on_each_side=1, on_ends=1)
    )
    parametros = request.GET.copy()
    parametros.pop("pagina", None)
    return pagina, paginas_visiveis, parametros.urlencode()


CADASTROS_COFFEE = {
    "fornecedores": {
        "model": Fornecedor,
        "form": FornecedorForm,
        "titulo": "Fornecedores",
        "singular": "fornecedor",
        "icone": "landmark",
        "busca": ("razao_social", "cnpj", "contato", "email"),
    },
    "contratos": {
        "model": ContratoCoffeeBreak,
        "form": ContratoCoffeeBreakForm,
        "titulo": "Contratos",
        "singular": "contrato",
        "icone": "document",
        "busca": ("numero", "numero_gms", "fornecedor__razao_social"),
    },
    "lotes": {
        "model": LoteCoffeeBreak,
        "form": LoteCoffeeBreakForm,
        "titulo": "Lotes contratados",
        "singular": "lote",
        "icone": "coffee",
        "busca": (
            "exercicio",
            "empenho",
            "contrato__numero",
            "contrato__fornecedor__razao_social",
        ),
    },
}


def _config_cadastro(tipo):
    config = CADASTROS_COFFEE.get(tipo)
    if not config:
        from django.http import Http404

        raise Http404
    return config


def _campos_cadastro(form):
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
        if isinstance(campo, forms.ModelMultipleChoiceField):
            item.update(
                {
                    "tipo": "multiplo",
                    "opcoes": _opcoes(campo.queryset),
                    "marcados": [
                        str(getattr(v, "pk", v)) for v in (valor or [])
                    ],
                }
            )
        elif isinstance(campo, forms.ModelChoiceField):
            item.update({"tipo": "select", "opcoes": _opcoes(campo.queryset)})
        elif isinstance(campo.widget, forms.Textarea):
            item["tipo"] = "textarea"
        elif isinstance(campo, forms.BooleanField):
            item["tipo"] = "boolean"
            item["valor"] = bool(valor)
        else:
            item["tipo"] = getattr(campo.widget, "input_type", "text")
        campos.append(item)
    return campos


def _colunas_ordenaveis(request, pedido, colunas, ordenacoes):
    parametros = request.GET.copy()
    parametros.pop("pagina", None)
    parametros.pop("ordem", None)
    base = parametros.urlencode()
    atual = pedido.lstrip("-")
    decrescente = pedido.startswith("-")

    resultado = []
    for chave, rotulo in colunas:
        if chave not in ordenacoes:
            resultado.append({"chave": chave, "rotulo": rotulo, "url": ""})
            continue
        ativa = chave == atual
        proximo = f"-{chave}" if ativa and not decrescente else chave
        resultado.append(
            {
                "chave": chave,
                "rotulo": rotulo,
                "ativa": ativa,
                "descendente": ativa and decrescente,
                "url": f"?{base}&ordem={proximo}" if base else f"?ordem={proximo}",
            }
        )
    return resultado


def _ordenacao(request, ordenacoes, padrao):
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


# ---------------------------------------------------------------------------
# Painel
# ---------------------------------------------------------------------------

@acesso_ao_modulo
def painel(request):
    lotes_ativos = list(
        LoteCoffeeBreak.objects.filter(ativo=True)
        .com_consumo()
        .select_related("contrato__fornecedor")
    )
    capacidade_total = sum(lote.quantidade_total for lote in lotes_ativos)
    consumido_total = sum(lote.consumido for lote in lotes_ativos)
    restante_total = capacidade_total - consumido_total
    em_alerta = services.lotes_em_alerta(lotes_ativos)

    ativas = SolicitacaoCoffeeBreak.objects.filter(cancelada=False)
    pendencias = sum(
        1
        for s in ativas.only(
            "cancelada",
            "numero_nota_fiscal",
            "protocolo_pagamento",
            "data_atesto_gaf",
            "data_ordem_bancaria",
            "data_envio_empresa",
        )
        if s.situacao_financeira != SituacaoFinanceira.CONCLUIDA
    )

    url_lotes = reverse("coffee_break:lotes")
    url_solicitacoes = reverse("coffee_break:solicitacoes")
    resumo = [
        {
            "titulo": "Capacidade contratada",
            "valor": capacidade_total,
            "icone": "coffee",
            "cor": "neutra",
            "variacao": f"{len(lotes_ativos)} lote{'s' if len(lotes_ativos) != 1 else ''} ativo{'s' if len(lotes_ativos) != 1 else ''}",
            "url": url_lotes,
        },
        {
            "titulo": "Unidades consumidas",
            "valor": consumido_total,
            "icone": "chart",
            "cor": "info",
            "variacao": (
                f"{round(consumido_total * 100 / capacidade_total)}% da capacidade"
                if capacidade_total
                else "Sem lotes ativos"
            ),
            "url": url_solicitacoes,
        },
        {
            "titulo": "Saldo restante",
            "valor": restante_total,
            "icone": "check-circle",
            "cor": "sucesso",
            "variacao": "Somando todos os lotes ativos",
            "url": url_lotes,
        },
        {
            "titulo": "Pendências financeiras",
            "valor": pendencias,
            "icone": "hourglass",
            "cor": "dourada",
            "destaque": pendencias > 0,
            "variacao": "Solicitações sem envio da OB à empresa",
            "url": f"{url_solicitacoes}?pendentes=1",
        },
    ]

    recentes = (
        SolicitacaoCoffeeBreak.objects.select_related("lote__contrato__fornecedor")
        .order_by("-criado_em")[:5]
    )

    return render(
        request,
        "pages/coffee_break/painel.html",
        {
            "titulo_pagina": "Coffee Break",
            "resumo": resumo,
            "lotes": lotes_ativos,
            # As duas listas do painel usam a mesma linha das listagens.
            "linhas_lotes": [linha_do_lote(lote) for lote in lotes_ativos],
            "lotes_em_alerta": em_alerta,
            "limiar_alerta": services.LIMIAR_ALERTA_SALDO,
            "recentes": recentes,
            "linhas_recentes": [linha_da_lista(s) for s in recentes],
            "url_lotes": url_lotes,
            "url_solicitacoes": url_solicitacoes,
        },
    )


# ---------------------------------------------------------------------------
# Lotes
# ---------------------------------------------------------------------------

ORDENACOES_LOTES = {
    "lote": ["numero", "-exercicio"],
    "fornecedor": ["contrato__fornecedor__razao_social", "numero"],
    "contrato": ["contrato__numero", "numero"],
    "exercicio": ["exercicio", "numero"],
    "capacidade": ["quantidade_total", "numero"],
    "restante": ["restante", "numero"],
}


@acesso_ao_modulo
def lista_lotes(request):
    filtros = FiltroLotesForm(request.GET or None)
    _pedido, campos_ordem = _ordenacao(request, ORDENACOES_LOTES, "-exercicio")
    base = (
        LoteCoffeeBreak.objects.com_consumo()
        .select_related("contrato__fornecedor")
        .order_by(*campos_ordem, "numero")
    )
    queryset = base
    if filtros.is_valid():
        dados = filtros.cleaned_data
        if dados.get("q"):
            termo = dados["q"]
            queryset = queryset.filter(
                Q(contrato__fornecedor__razao_social__icontains=termo)
                | Q(contrato__numero__icontains=termo)
                | Q(municipios_texto__icontains=termo)
                | Q(municipios__nome__icontains=termo)
            ).distinct()
        if dados.get("exercicio"):
            queryset = queryset.filter(exercicio=dados["exercicio"].strip())
        if dados.get("situacao") == "ativos":
            queryset = queryset.filter(ativo=True)
        elif dados.get("situacao") == "inativos":
            queryset = queryset.filter(ativo=False)

    pagina, paginas_visiveis, querystring = _paginar(request, queryset)
    # A trilha lateral recorta por exercício, o agrupador natural dos lotes.
    contagens = {}
    for exercicio in LoteCoffeeBreak.objects.values_list("exercicio", flat=True):
        contagens[exercicio] = contagens.get(exercicio, 0) + 1
    filas = [
        {"chave": exercicio, "rotulo": f"Exercício {exercicio}", "total": total}
        for exercicio, total in sorted(contagens.items(), reverse=True)
    ]
    valores = _valores_filtro(filtros)
    return render(
        request,
        "pages/coffee_break/lotes_lista.html",
        {
            "breadcrumb": _breadcrumb({"label": "Lotes"}),
            "pagina": pagina,
            "linhas": [linha_do_lote(lote) for lote in pagina],
            "paginas_visiveis": paginas_visiveis,
            "elipse": Paginator.ELLIPSIS,
            "querystring": querystring,
            "q": valores.get("q", ""),
            "situacoes": trilha_de_situacoes(
                request,
                filas,
                sum(contagens.values()),
                {chave: "calendar" for chave in contagens},
                parametro="exercicio",
            ),
            # Chip aceso: sem exercício escolhido, "Todas".
            "situacao_ativa": valores.get("exercicio") or "todas",
            "exercicio_escolhido": valores.get("exercicio", ""),
            "tem_filtros": any(
                request.GET.get(nome) for nome in ("q", "exercicio", "situacao")
            ),
        },
    )


@acesso_ao_modulo
def detalhe_lote(request, pk):
    lote = get_object_or_404(
        LoteCoffeeBreak.objects.com_consumo().select_related(
            "contrato__fornecedor"
        ).prefetch_related("municipios"),
        pk=pk,
    )
    solicitacoes = (
        lote.solicitacoes.select_related("criado_por")
        .order_by("-data_solicitacao", "-criado_em")
    )
    return render(
        request,
        "pages/coffee_break/lote_detalhe.html",
        {
            "breadcrumb": _breadcrumb(
                {"label": "Lotes", "url": reverse("coffee_break:lotes")},
                {"label": lote.rotulo_curto},
            ),
            "lote": lote,
            "contrato": lote.contrato,
            "fornecedor": lote.contrato.fornecedor,
            "municipios": lote.municipios.all(),
            "solicitacoes": solicitacoes,
            # As solicitações do lote usam a mesma linha da listagem.
            "linhas": [linha_da_lista(s) for s in solicitacoes],
            "consumo": selo_do_consumo(lote)[0],
            "consumo_tom": selo_do_consumo(lote)[1],
            "percentual": (
                round(lote.consumido * 100 / lote.quantidade_total)
                if lote.quantidade_total
                else 0
            ),
        },
    )


# ---------------------------------------------------------------------------
# Solicitações
# ---------------------------------------------------------------------------

ORDENACOES_SOLICITACOES = {
    "numero": ["numero", "-data_solicitacao"],
    "lote": ["lote__numero", "-data_solicitacao"],
    "descricao": ["descricao_evento", "-data_solicitacao"],
    "data": ["data_solicitacao", "-pk"],
    "evento": ["data_inicio_evento", "-pk"],
    "quantidade": ["quantidade", "-data_solicitacao"],
}

CAMPOS_FILTRO_SOLICITACOES = ["q", "lote", "fornecedor", "situacao", "inicio", "fim", "pendentes"]


def _filtrar_solicitacoes(request):
    filtros = FiltroSolicitacoesCoffeeForm(request.GET or None)
    pedido, campos_ordem = _ordenacao(request, ORDENACOES_SOLICITACOES, "-data")
    queryset = (
        SolicitacaoCoffeeBreak.objects.select_related(
            "lote__contrato__fornecedor", "criado_por"
        ).order_by(*campos_ordem)
    )
    situacao = ""
    if filtros.is_valid():
        dados = filtros.cleaned_data
        if dados.get("q"):
            termo = dados["q"]
            queryset = queryset.filter(
                Q(descricao_evento__icontains=termo)
                | Q(numero__icontains=termo)
                | Q(numero_nota_fiscal__icontains=termo)
                | Q(protocolo_pagamento__icontains=termo)
            )
        if dados.get("lote"):
            queryset = queryset.filter(lote=dados["lote"])
        if dados.get("fornecedor"):
            queryset = queryset.filter(
                lote__contrato__fornecedor=dados["fornecedor"]
            )
        if dados.get("inicio"):
            queryset = queryset.filter(data_inicio_evento__gte=dados["inicio"])
        if dados.get("fim"):
            queryset = queryset.filter(data_inicio_evento__lte=dados["fim"])
        situacao = dados.get("situacao") or ""

    # Situação financeira é derivada — o recorte é feito em Python, depois
    # dos filtros de banco, preservando a ordenação.
    pendentes = request.GET.get("pendentes") == "1"
    if situacao or pendentes:
        itens = [
            s
            for s in queryset
            if (not situacao or s.situacao_financeira == situacao)
            and (
                not pendentes
                or (
                    not s.cancelada
                    and s.situacao_financeira != SituacaoFinanceira.CONCLUIDA
                )
            )
        ]
    else:
        itens = queryset
    # `base` é o recorte do banco sem o filtro de situação: é dele que sai a
    # contagem de cada item da trilha lateral.
    return itens, list(queryset), filtros, pedido


# Ícone de cada situação financeira na trilha lateral.
ICONES_SITUACAO = {
    SituacaoFinanceira.AGUARDANDO_NOTA_FISCAL: "document",
    SituacaoFinanceira.AGUARDANDO_PROTOCOLO: "clipboard",
    SituacaoFinanceira.AGUARDANDO_ATESTO: "check",
    SituacaoFinanceira.AGUARDANDO_ORDEM_BANCARIA: "hourglass",
    SituacaoFinanceira.AGUARDANDO_ENVIO_EMPRESA: "send",
    SituacaoFinanceira.CONCLUIDA: "check-circle",
    SituacaoFinanceira.CANCELADA: "ban",
}


@acesso_ao_modulo
def lista_solicitacoes(request):
    itens, base, filtros, _pedido = _filtrar_solicitacoes(request)
    pagina, paginas_visiveis, querystring = _paginar(request, itens)
    valores = _valores_filtro(filtros)
    hoje = timezone.localdate()
    return render(
        request,
        "pages/coffee_break/solicitacoes_lista.html",
        {
            "breadcrumb": _breadcrumb({"label": "Solicitações"}),
            "pagina": pagina,
            "linhas": [linha_da_lista(s, hoje) for s in pagina],
            "paginas_visiveis": paginas_visiveis,
            "elipse": Paginator.ELLIPSIS,
            "querystring": querystring,
            "q": valores.get("q", ""),
            "situacoes": trilha_de_situacoes(
                request,
                filas_de_situacao(base),
                len(base),
                ICONES_SITUACAO,
                parametro="situacao",
            ),
            # Chip aceso: sem situação escolhida, "Todas".
            "situacao_ativa": valores.get("situacao") or "todas",
            "situacao_escolhida": valores.get("situacao", ""),
            "tem_filtros": any(
                request.GET.get(nome) for nome in CAMPOS_FILTRO_SOLICITACOES
            ),
        },
    )


@acesso_ao_modulo
def exportar_solicitacoes(request):
    """Exporta o recorte atual para conciliação operacional e financeira."""
    import csv

    from django.http import HttpResponse
    from django.utils import timezone as tz

    itens, _base, _filtros, _pedido = _filtrar_solicitacoes(request)
    resposta = HttpResponse(content_type="text/csv; charset=utf-8")
    resposta["Content-Disposition"] = (
        f'attachment; filename="coffee-break-{tz.localdate():%Y-%m-%d}.csv"'
    )
    resposta.write("﻿")
    escritor = csv.writer(resposta, delimiter=";", lineterminator="\r\n")
    escritor.writerow(
        [
            "Nº", "Lote", "Fornecedor", "Data da solicitação", "Evento",
            "Período", "Quantidade", "Nota fiscal", "Protocolo",
            "Atesto GAF", "Ordem bancária", "Envio à empresa", "Situação",
            "Criado por",
        ]
    )
    for solicitacao in itens:
        escritor.writerow(
            [
                solicitacao.numero,
                solicitacao.lote.rotulo_curto,
                solicitacao.lote.contrato.fornecedor.razao_social,
                solicitacao.data_solicitacao.strftime("%d/%m/%Y"),
                solicitacao.descricao_evento,
                solicitacao.periodo_evento_display,
                solicitacao.quantidade,
                solicitacao.numero_nota_fiscal,
                solicitacao.protocolo_pagamento,
                solicitacao.data_atesto_gaf.strftime("%d/%m/%Y") if solicitacao.data_atesto_gaf else "",
                solicitacao.data_ordem_bancaria.strftime("%d/%m/%Y") if solicitacao.data_ordem_bancaria else "",
                solicitacao.data_envio_empresa.strftime("%d/%m/%Y") if solicitacao.data_envio_empresa else "",
                solicitacao.situacao_financeira_display,
                solicitacao.criado_por,
            ]
        )
    return resposta


def _contexto_formulario(request, form, solicitacao=None, somente_leitura=False):
    lotes_com_saldo = (
        LoteCoffeeBreak.objects.filter(
            pk__in=[l.pk for l in form.fields["lote"].queryset]
        )
        .com_consumo()
        .select_related("contrato__fornecedor")
    )
    saldos = {
        str(lote.pk): {
            "restante": lote.restante,
            "total": lote.quantidade_total,
            "rotulo": str(lote),
        }
        for lote in lotes_com_saldo
    }
    valores = {}
    for nome in form.fields:
        valor = form[nome].value()
        valores[nome] = "" if valor is None else str(valor)
    contexto = {
        "form": form,
        "solicitacao": solicitacao,
        "erros": form.errors,
        "erros_gerais": form.non_field_errors(),
        "erro_periodo": form.errors.get("data_inicio_evento")
        or form.errors.get("data_fim_evento"),
        "valores": valores,
        "lotes": _opcoes(form.fields["lote"].queryset),
        "saldos_lotes": saldos,
        "somente_leitura": somente_leitura,
        "dados_base_bloqueados": bool(
            solicitacao and (solicitacao.financeiro_iniciado or somente_leitura)
        ),
        # Cabeçalho da tela de edição: só o título e o selo da situação.
        "selo": solicitacao.situacao_financeira_display if solicitacao else "Nova",
        "selo_tom": solicitacao.situacao_financeira_css if solicitacao else "pendente",
    }
    if solicitacao is not None:
        # O formulário é a única tela do registro: além dos campos editáveis ele
        # carrega o vínculo com o lote, os dados de auditoria e o histórico.
        contexto["lote"] = (
            LoteCoffeeBreak.objects.com_consumo()
            .select_related("contrato__fornecedor")
            .get(pk=solicitacao.lote_id)
        )
        contexto["historico"] = solicitacao.historico.select_related("usuario")
    return contexto


@acesso_ao_modulo
def nova_solicitacao(request):
    if request.method == "POST":
        form = SolicitacaoCoffeeBreakForm(request.POST)
        if form.is_valid():
            try:
                solicitacao = form.save(criado_por=request.user)
            except ValidationError as erro:
                for campo, mensagens in erro.message_dict.items():
                    for mensagem in mensagens:
                        form.add_error(
                            campo if campo in form.fields else None, mensagem
                        )
                messages.error(request, "Corrija os campos destacados para continuar.")
            else:
                services.registrar_historico(
                    solicitacao,
                    request.user,
                    AcaoHistoricoCoffeeBreak.CRIACAO,
                    "Solicitação registrada no sistema.",
                )
                messages.success(
                    request,
                    f"Solicitação de coffee break registrada no {solicitacao.lote.rotulo_curto}.",
                )
                return redirect("coffee_break:editar", pk=solicitacao.pk)
        else:
            messages.error(request, "Corrija os campos destacados para continuar.")
    else:
        form = SolicitacaoCoffeeBreakForm()
    contexto = _contexto_formulario(request, form)
    contexto["titulo_pagina"] = "Nova Solicitação de Coffee Break"
    contexto["breadcrumb"] = _breadcrumb(
        {"label": "Solicitações", "url": reverse("coffee_break:solicitacoes")},
        {"label": "Nova solicitação"},
    )
    return render(request, "pages/coffee_break/form.html", contexto)


@acesso_ao_modulo
def editar_solicitacao(request, pk):
    solicitacao = get_object_or_404(
        SolicitacaoCoffeeBreak.objects.select_related(
            "lote__contrato__fornecedor", "criado_por", "cancelada_por"
        ),
        pk=pk,
    )
    somente_leitura = solicitacao.cancelada or solicitacao.concluida
    if somente_leitura:
        # O formulário é a única tela do registro: canceladas e concluídas
        # continuam abrindo aqui, mas sem gravar — só para consulta, ações de
        # situação e histórico.
        messages.warning(
            request,
            "Solicitações canceladas ou concluídas ficam bloqueadas para edição. Use o histórico para consultar as alterações.",
        )
        if request.method == "POST":
            return redirect("coffee_break:editar", pk=solicitacao.pk)
        form = SolicitacaoCoffeeBreakForm(instance=solicitacao)
        contexto = _contexto_formulario(
            request, form, solicitacao, somente_leitura=True
        )
        contexto["titulo_pagina"] = "Solicitação de Coffee Break"
        contexto["breadcrumb"] = _breadcrumb(
            {"label": "Solicitações", "url": reverse("coffee_break:solicitacoes")},
            {"label": solicitacao.numero or f"#{solicitacao.pk}"},
        )
        return render(request, "pages/coffee_break/form.html", contexto)
    if request.method == "POST":
        form = SolicitacaoCoffeeBreakForm(request.POST, instance=solicitacao)
        if form.is_valid():
            try:
                solicitacao = form.save()
            except ValidationError as erro:
                for campo, mensagens in erro.message_dict.items():
                    for mensagem in mensagens:
                        form.add_error(
                            campo if campo in form.fields else None, mensagem
                        )
                messages.error(request, "Corrija os campos destacados para continuar.")
            else:
                alterados = [
                    form.fields[nome].label
                    for nome in form.changed_data
                    if nome in form.fields and nome != "versao"
                ]
                services.registrar_historico(
                    solicitacao,
                    request.user,
                    AcaoHistoricoCoffeeBreak.ATUALIZACAO,
                    "Campos atualizados: " + ", ".join(alterados)
                    if alterados
                    else "Solicitação salva sem alteração de campos.",
                )
                messages.success(request, "Solicitação de coffee break atualizada.")
                return redirect("coffee_break:editar", pk=solicitacao.pk)
        else:
            messages.error(request, "Corrija os campos destacados para continuar.")
    else:
        form = SolicitacaoCoffeeBreakForm(instance=solicitacao)
    contexto = _contexto_formulario(request, form, solicitacao)
    contexto["titulo_pagina"] = "Editar Solicitação de Coffee Break"
    contexto["breadcrumb"] = _breadcrumb(
        {"label": "Solicitações", "url": reverse("coffee_break:solicitacoes")},
        {"label": f"Editar #{solicitacao.pk}"},
    )
    return render(request, "pages/coffee_break/form.html", contexto)


@acesso_ao_modulo
def certificado_solicitacao(request, pk):
    """Certificado da solicitação em PDF: o espelho do registro, para o processo.

    Sai sempre recalculado do banco — inclusive para cancelada ou concluída,
    que é justamente quando alguém precisa do papel. Nada é gravado, então a
    rota é um GET sem efeito colateral.
    """
    from django.http import HttpResponse

    from documentos.services.exceptions import DocumentRendererUnavailable

    solicitacao = get_object_or_404(
        SolicitacaoCoffeeBreak.objects.select_related(
            "lote__contrato__fornecedor", "criado_por"
        ),
        pk=pk,
    )
    try:
        pdf = documents.gerar_pdf(solicitacao, usuario=request.user)
    except DocumentRendererUnavailable as erro:
        # Servidor sem o runtime do WeasyPrint: o pedido continua acessível,
        # só o papel não sai. Dizer qual é a falta é o que permite corrigi-la.
        messages.error(
            request,
            f"Não foi possível gerar o certificado agora. {erro}",
        )
        return redirect("coffee_break:editar", pk=solicitacao.pk)
    resposta = HttpResponse(pdf, content_type="application/pdf")
    resposta["Content-Disposition"] = (
        f'inline; filename="{documents.nome_arquivo(solicitacao)}"'
    )
    return resposta


@acesso_ao_modulo
@require_POST
def cancelar_solicitacao(request, pk):
    solicitacao = get_object_or_404(SolicitacaoCoffeeBreak, pk=pk)
    try:
        services.cancelar(
            solicitacao, request.user, request.POST.get("motivo", "")
        )
    except ValidationError as erro:
        for mensagem in erro.messages:
            messages.error(request, mensagem)
    else:
        messages.success(
            request,
            "Solicitação cancelada — a quantidade voltou ao saldo do lote.",
        )
    return redirect("coffee_break:editar", pk=solicitacao.pk)


@acesso_ao_modulo
@require_POST
def reativar_solicitacao(request, pk):
    solicitacao = get_object_or_404(SolicitacaoCoffeeBreak, pk=pk)
    try:
        services.reativar(solicitacao, request.user)
    except ValidationError as erro:
        for mensagem in erro.messages:
            messages.error(request, mensagem)
    else:
        messages.success(request, "Solicitação reativada e saldo consumido.")
    return redirect("coffee_break:editar", pk=solicitacao.pk)


# ---------------------------------------------------------------------------
# Cadastros contratuais — backoffice institucional, restrito a administradores
# ---------------------------------------------------------------------------

@gerenciamento_de_cadastros
def cadastros(request):
    return redirect("coffee_break:cadastro_lista", tipo="fornecedores")


@gerenciamento_de_cadastros
def lista_cadastro(request, tipo):
    config = _config_cadastro(tipo)
    q = request.GET.get("q", "").strip()
    queryset = config["model"].objects.all()
    if tipo == "contratos":
        queryset = queryset.select_related("fornecedor")
    elif tipo == "lotes":
        queryset = queryset.select_related("contrato__fornecedor").com_consumo()
    if q:
        busca = Q()
        for campo in config["busca"]:
            busca |= Q(**{f"{campo}__icontains": q})
        queryset = queryset.filter(busca)
    pagina, paginas_visiveis, querystring = _paginar(request, queryset)
    # Trilha lateral com os três cadastros do módulo, como nos cadastros de
    # apoio de Viagens: um item por tabela, com o total de cada uma.
    grupos = [
        {
            "slug": chave,
            "titulo": outra["titulo"],
            "total": outra["model"].objects.count(),
            "icone": outra["icone"],
            "url": reverse("coffee_break:cadastro_lista", args=[chave]),
        }
        for chave, outra in CADASTROS_COFFEE.items()
    ]
    return render(
        request,
        "pages/coffee_break/cadastro_lista.html",
        {
            "config": config,
            "tipo": tipo,
            "q": q,
            "grupos": grupos,
            "pagina": pagina,
            "linhas": [linha_do_cadastro(item, tipo) for item in pagina],
            "paginas_visiveis": paginas_visiveis,
            "elipse": Paginator.ELLIPSIS,
            "querystring": querystring,
            "tem_filtros": bool(q),
            "breadcrumb": _breadcrumb({"label": "Cadastros"}, {"label": config["titulo"]}),
        },
    )


@gerenciamento_de_cadastros
def editar_cadastro(request, tipo, pk=None):
    config = _config_cadastro(tipo)
    instancia = get_object_or_404(config["model"], pk=pk) if pk else None
    if request.method == "POST":
        form = config["form"](request.POST, instance=instancia)
        if form.is_valid():
            form.save()
            messages.success(
                request,
                f"{config['singular'].capitalize()} salvo com sucesso.",
            )
            return redirect("coffee_break:cadastro_lista", tipo=tipo)
        messages.error(request, "Corrija os campos destacados para continuar.")
    else:
        form = config["form"](instance=instancia)
    return render(
        request,
        "pages/coffee_break/cadastro_form.html",
        {
            "config": config,
            "tipo": tipo,
            "instancia": instancia,
            "form": form,
            "campos": _campos_cadastro(form),
            "breadcrumb": _breadcrumb(
                {
                    "label": "Cadastros",
                    "url": reverse("coffee_break:cadastro_lista", args=[tipo]),
                },
                {
                    "label": (
                        f"Editar {config['singular']}"
                        if instancia
                        else f"Novo {config['singular']}"
                    )
                },
            ),
        },
    )
