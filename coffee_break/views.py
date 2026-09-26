"""Views do módulo de Coffee Break da ASCOM.

Todas as rotas exigem o módulo ASCOM_COFFEE_BREAK (decorator + middleware);
ocultar o menu nunca é a única barreira.
"""

import io
from pathlib import Path

from django import forms
from django.contrib import messages
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.db.models import Max, Q, Sum
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.clickjacking import xframe_options_sameorigin
from django.views.decorators.http import require_GET, require_POST
from django.db import transaction
from django.db.models import ProtectedError
from django.http import FileResponse, Http404, HttpResponse, JsonResponse

from documentos.editor.pagina import cartao

from .editor import CHAVE_CERTIFICO, CHAVE_OFICIO, CHAVE_OS
from .forms import (
    ConfiguracaoCoffeeBreakForm,
    NotaCoffeeBreakForm,
    PedidoCoffeeBreakForm,
    ProtocoloCoffeeBreakForm,
    ContratoCoffeeBreakForm,
    FiltroLotesForm,
    FiltroSolicitacoesCoffeeForm,
    FornecedorForm,
    LoteCoffeeBreakForm,
    SolicitacaoCoffeeBreakForm,
)
from .models import (
    AcaoHistoricoCoffeeBreak,
    CertidaoFornecedor,
    HistoricoCoffeeBreak,
    ConfiguracaoCoffeeBreak,
    ContratoCoffeeBreak,
    Fornecedor,
    LoteCoffeeBreak,
    SituacaoFinanceira,
    SolicitacaoCoffeeBreak,
    TipoCertidao,
)
from core import preencher_por_email
from core.listagens import trilha_de_situacoes

from solicitacoes.permissions import eh_administrador

from .permissions import acesso_ao_modulo, gerenciamento_de_cadastros
from .presenters import filas_de_situacao, linha_da_acao, linha_da_lista, linha_do_cadastro, linha_do_lote, selo_do_consumo
from . import certidoes, documentos, documents, preenchimento, services

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
    # Registro único: quem assina o ofício, a quem vai e os campos fixos do
    # eProtocolo. Edita-se; não se cria nem se exclui.
    "oficio": {
        "model": ConfiguracaoCoffeeBreak,
        "form": ConfiguracaoCoffeeBreakForm,
        "titulo": "Ofício e eProtocolo",
        "singular": "configuração",
        "icone": "mail",
        "busca": ("oficio_assinante",),
        "unico": True,
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
        if isinstance(campo, forms.FileField):
            atual = getattr(form.instance, nome, None)
            item.update(
                {
                    "tipo": "arquivo",
                    "valor": Path(atual.name).name if atual else "",
                    "url_atual": (
                        reverse("coffee_break:contrato_arquivo", args=[form.instance.pk, nome])
                        if atual and form.instance.pk
                        and isinstance(form.instance, ContratoCoffeeBreak)
                        else ""
                    ),
                }
            )
        elif isinstance(campo, forms.ModelMultipleChoiceField):
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
    # Controle em reais: quantidade × preço unitário guardado na OS.
    hoje = timezone.localdate()
    gasto = services.gasto_no_ano(hoje.year)
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
            "titulo": f"Gasto em {hoje.year}",
            "valor": services.formatar_reais(gasto["total"]),
            "icone": "chart",
            "cor": "info",
            "variacao": f"{services.formatar_reais(gasto['pago'])} com ordem bancária",
            "url": url_solicitacoes,
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
    # "O que fazer hoje": as OS que dependem da equipe, agrupadas pela próxima ação.
    fila = services.fila_de_trabalho(hoje)
    for grupo in fila:
        grupo["linhas"] = [linha_da_acao(item, grupo["chave"], hoje) for item in grupo["itens"]]
    alertas_certidoes = certidoes.fornecedores_com_alerta(_fornecedores_com_lote_ativo())
    # Fim da vigência a 90, 60 e 30 dias: prazo para o aditivo de prorrogação.
    alertas_vigencia = services.contratos_perto_do_fim()

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
            "recentes": recentes,
            "linhas_recentes": [linha_da_lista(s) for s in recentes],
            "url_lotes": url_lotes,
            "url_solicitacoes": url_solicitacoes,
            "alertas_certidoes": alertas_certidoes,
            "alertas_vigencia": alertas_vigencia,
            "fila": fila,
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
            "proximo_exercicio": _proximo_exercicio(),
            "tem_filtros": any(
                request.GET.get(nome) for nome in ("q", "exercicio", "situacao")
            ),
        },
    )


def _proximo_exercicio():
    from .virada import exercicio_de_origem

    origem = exercicio_de_origem()
    return origem + 1 if origem else None


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
            "valores": {
                chave: services.formatar_reais(valor)
                for chave, valor in services.valores_do_lote(lote).items()
            },
            "valor_empenho": services.formatar_reais(lote.valor_empenho),
            "consumo": selo_do_consumo(lote)[0],
            "consumo_tom": selo_do_consumo(lote)[1],
            "percentual": (
                round(lote.consumido * 100 / lote.quantidade_total)
                if lote.quantidade_total
                else 0
            ),
        },
    )


@gerenciamento_de_cadastros
def virada_exercicio(request):
    """"Abrir exercício N+1": copia os lotes vigentes de N, pedindo só a
    quantidade e o empenho de cada um (administradores do módulo)."""
    from . import virada

    origem = request.GET.get("de") or request.POST.get("de") or ""
    origem = int(origem) if origem.isdigit() else virada.exercicio_de_origem()
    if origem is None:
        messages.info(request, "Não há lotes vigentes para copiar.")
        return redirect("coffee_break:lotes")
    destino = origem + 1
    lotes = virada.lotes_de_origem(origem)
    por_pk = {lote.pk: lote for lote in lotes}
    if request.method == "POST":
        formset = virada.ViradaFormSet(request.POST)
        if formset.is_valid():
            linhas = [
                (por_pk[f.cleaned_data["lote"]], f.cleaned_data)
                for f in formset.forms
                if f.cleaned_data.get("criar") and f.cleaned_data.get("lote") in por_pk
            ]
            if not linhas:
                messages.error(request, "Marque ao menos um lote para abrir o exercício.")
            else:
                try:
                    criados = virada.abrir_exercicio(linhas, destino, request.POST.get("desativar") == "1")
                except ValidationError as erro:
                    for mensagem in erro.messages:
                        messages.error(request, mensagem)
                else:
                    messages.success(
                        request,
                        f"Exercício {destino} aberto: {len(criados)} lote{'s' if len(criados) != 1 else ''} criado"
                        f"{'s' if len(criados) != 1 else ''} com os municípios, orientações e especificações de {origem}."
                        + (f" Os lotes de {origem} copiados foram encerrados." if request.POST.get("desativar") == "1" else ""),
                    )
                    return redirect(f"{reverse('coffee_break:lotes')}?exercicio={destino}")
        else:
            messages.error(request, "Corrija as linhas destacadas.")
    else:
        formset = virada.ViradaFormSet(initial=virada.iniciais(lotes, destino))
    linhas = []
    for form in formset.forms:
        pk = form["lote"].value()
        lote = por_pk.get(int(pk)) if str(pk).isdigit() else None
        if lote is None:
            continue
        linhas.append({
            "form": form,
            "lote": lote,
            "impedimento": virada.impedimento(lote, destino),
            "aviso": virada.aviso_de_vigencia(lote, destino),
            "marcado": bool(form["criar"].value()),
        })
    return render(
        request,
        "pages/coffee_break/virada_exercicio.html",
        {
            "breadcrumb": _breadcrumb(
                {"label": "Lotes", "url": reverse("coffee_break:lotes")},
                {"label": f"Abrir exercício {destino}"},
            ),
            "origem": origem,
            "destino": destino,
            "formset": formset,
            "linhas": linhas,
            "desativar": request.POST.get("desativar") == "1",
        },
    )


@acesso_ao_modulo
def relatorio_contrato(request, pk):
    """Relatório do contrato na tela, em PDF (`?formato=pdf`) ou planilha (`?formato=csv`)."""
    import csv

    from django.template.loader import render_to_string

    from . import relatorio_contrato as relatorio

    contrato = get_object_or_404(ContratoCoffeeBreak.objects.select_related("fornecedor"), pk=pk)
    dados = relatorio.montar(contrato)
    nome = f"Relatorio do contrato {contrato.numero}".replace("/", "-")
    formato = request.GET.get("formato")
    if formato == "csv":
        resposta = HttpResponse(content_type="text/csv; charset=utf-8")
        resposta["Content-Disposition"] = f'attachment; filename="{nome}.csv"'
        resposta.write("﻿")
        escritor = csv.writer(resposta, delimiter=";", lineterminator="\r\n")
        for linha in relatorio.linhas_csv(dados):
            escritor.writerow(linha)
        return resposta
    if formato == "pdf":
        try:
            pdf = documentos._pdf("coffee_break/documentos/relatorio_contrato.html", dados)
        except ValidationError as erro:
            for mensagem in erro.messages:
                messages.error(request, mensagem)
            return redirect("coffee_break:relatorio_contrato", pk=contrato.pk)
        resposta = HttpResponse(pdf, content_type="application/pdf")
        resposta["Content-Disposition"] = f'inline; filename="{nome}.pdf"'
        return resposta
    dados["breadcrumb"] = _breadcrumb(
        {"label": "Lotes", "url": reverse("coffee_break:lotes")},
        {"label": f"Relatório do contrato {contrato.numero}"},
    )
    return render(request, "pages/coffee_break/relatorio_contrato.html", dados)


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
        )
        # O último registro do histórico: o "parada há N dias" da linha.
        .annotate(ultimo_historico=Max("historico__criado_em"))
        .order_by(*campos_ordem)
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


def _decimal_csv(valor):
    """Número com vírgula decimal, como a planilha em português espera."""
    return "" if valor is None else f"{valor:.2f}".replace(".", ",")


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
            "Período", "Quantidade", "Quantidade faturada", "Valor unitário", "Valor",
            "Nota fiscal", "Protocolo",
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
                "" if solicitacao.quantidade_faturada is None else solicitacao.quantidade_faturada,
                _decimal_csv(solicitacao.valor_unitario_efetivo),
                _decimal_csv(solicitacao.valor),
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


def _opcoes_municipios(form):
    """Municípios com o lote que cada um recebe, para a tela mostrar na hora."""
    escolha = services.EscolhaDeLotes()
    opcoes = []
    for municipio in form.fields["municipio"].queryset:
        lote, distancia = escolha.escolher(municipio)
        dados = {}
        if lote is not None:
            contrato = lote.contrato
            # A 2ª linha da etapa 1 mostra o lote que o município recebe (coffee-break-lote.js).
            dados = {
                "lote": f"{lote.rotulo_curto} — {contrato.fornecedor.razao_social}",
                "lote-rotulo": lote.rotulo_curto,
                "lote-url": reverse("coffee_break:lote_detalhe", args=[lote.pk]),
                "fornecedor": contrato.fornecedor.razao_social,
                "contrato": f"Contrato {contrato.numero}" + (f" · Aditivo {contrato.termo_aditivo}" if contrato.termo_aditivo else ""),
                "saldo": f"{lote.restante} de {lote.quantidade_total} unidades",
            }
            if lote.empenho:
                dados["empenho"] = f"Empenho {lote.empenho}"
            fim = services.fim_da_vigencia(contrato)
            if fim:
                vencido = fim < timezone.localdate()
                dados["vigencia"] = f"{'Vencido em' if vencido else 'Vigente até'} {fim:%d/%m/%Y}"
            if distancia:
                dados["perto"] = f"{lote.sede_mais_proxima.nome}, a {distancia} km"
        opcoes.append({"valor": str(municipio.pk), "rotulo": municipio.nome, "dados": dados})
    return opcoes


# As três etapas da solicitação, como as da prestação de contas: cada uma
# com a sua tela, o seu formulário e os documentos que nascem nela.
ETAPAS = (
    {"chave": "pedido", "titulo": "Solicitação e OS", "rota": "editar", "form": PedidoCoffeeBreakForm},
    {"chave": "nota", "titulo": "Nota fiscal, ofício e certifico", "rota": "etapa_nota", "form": NotaCoffeeBreakForm},
    {"chave": "protocolo", "titulo": "Protocolo e pagamento", "rota": "etapa_protocolo", "form": ProtocoloCoffeeBreakForm},
)
ETAPA_POR_CHAVE = {etapa["chave"]: etapa for etapa in ETAPAS}


def _etapas_concluidas(solicitacao):
    """Quais etapas já estão feitas — o que o stepper marca com o check."""
    if solicitacao is None:
        return set()
    feitas = set()
    # A OS pronta (sem pendências) fecha a etapa 1.
    if solicitacao.financeiro_iniciado or not documentos.pendencias_ordem_servico(solicitacao):
        feitas.add("pedido")
    if solicitacao.protocolo_pagamento or (
        solicitacao.numero_nota_fiscal
        and solicitacao.arquivo_nota_fiscal
        and solicitacao.numero_oficio
    ):
        feitas.add("nota")
    if solicitacao.concluida:
        feitas.add("protocolo")
    return feitas


def _stepper(solicitacao, atual):
    feitas = _etapas_concluidas(solicitacao)
    return [
        {
            "titulo": etapa["titulo"],
            "url": reverse(f"coffee_break:{etapa['rota']}", args=[solicitacao.pk]) if solicitacao else "",
            "estado": "atual" if etapa["chave"] == atual else ("concluido" if etapa["chave"] in feitas else "pendente"),
        }
        for etapa in ETAPAS
    ]


def _etapa_do_marco(solicitacao):
    """A tela onde se preenche o próximo marco do fluxo."""
    marco = services.proximo_marco(solicitacao)
    campo = marco["campo"] if marco else "data_envio_empresa"
    if campo == "numero_nota_fiscal":
        return "etapa_nota"
    return "etapa_protocolo"


def _ano_do_numero(form):
    """O ano ao lado do número da OS: o do número atual, senão o da data."""
    atual = services.partes_numero(form.instance.numero) if form.instance.pk else None
    if atual:
        return atual[1]
    valor = form["data_solicitacao"].value() if "data_solicitacao" in form.fields else None
    try:
        return int(str(valor)[:4])
    except (TypeError, ValueError):
        return timezone.localdate().year


def _contexto_formulario(request, form, solicitacao=None, somente_leitura=False, etapa="pedido"):
    valores = {}
    for nome in form.fields:
        valor = form[nome].value()
        valores[nome] = "" if valor is None else str(valor)
    contexto = {
        "form": form,
        "etapa": etapa,
        "solicitacao": solicitacao,
        "erros": form.errors,
        "erros_gerais": form.non_field_errors(),
        "erro_periodo": form.errors.get("data_inicio_evento")
        or form.errors.get("data_fim_evento"),
        "valores": valores,
        "somente_leitura": somente_leitura,
        "dados_base_bloqueados": bool(
            solicitacao and (solicitacao.financeiro_iniciado or somente_leitura)
        ),
        "stepper": _stepper(solicitacao, etapa),
        # Reabrir a concluída para correção: só administrador do módulo.
        "pode_reabrir": bool(solicitacao and solicitacao.concluida and eh_administrador(request.user)),
        "hoje": timezone.localdate(),
        # Cabeçalho da tela de edição: só o título e o selo da situação.
        "selo": solicitacao.situacao_financeira_display if solicitacao else "Nova",
        "selo_tom": solicitacao.situacao_financeira_css if solicitacao else "pendente",
    }
    if "municipio" in form.fields:
        contexto["municipios"] = _opcoes_municipios(form)
    if "registro_retroativo" in form.fields:
        # O "registro retroativo" só aparece quando o evento vem antes da solicitação.
        contexto["mostrar_retroativo"] = bool(
            getattr(form, "evento_retroativo", False) or valores.get("registro_retroativo") in ("True", "on", "1")
        )
    if solicitacao is not None and etapa == "pedido":
        contexto["aviso_antecedencia"] = services.aviso_de_antecedencia(solicitacao)
        from . import origem as origem_evento

        # Pedida do evento ou da palestra: o link de lá e o aviso de remarcação.
        contexto["origem_evento"] = origem_evento.cartao(solicitacao, request.user)
    if "numero" in form.fields:
        contexto["numero_ano"] = _ano_do_numero(form)
        # Número fora do "NN/AAAA" (texto antigo da planilha): campo de texto livre.
        contexto["numero_livre"] = bool(
            solicitacao and solicitacao.numero and not services.partes_numero(solicitacao.numero)
        )
        if solicitacao is None and not valores.get("numero"):
            # A nova OS já vem com o próximo número (numeração única, a maior + 1); pode alterar.
            valores["numero"] = str(services.proxima_sequencia(contexto["numero_ano"]))
    if solicitacao is not None:
        contexto["lote"] = (
            LoteCoffeeBreak.objects.com_consumo()
            .select_related("contrato__fornecedor")
            .get(pk=solicitacao.lote_id)
        )
        contexto["historico"] = solicitacao.historico.select_related("usuario")
        contexto["ultima_anotacao"] = services.ultima_anotacao(solicitacao)
        contexto["pendencias_os"] = documentos.pendencias_ordem_servico(solicitacao)
        url_os = reverse("coffee_break:ordem_servico", args=[solicitacao.pk])
        # No formato do `_documento_inline` de Viagens (título, PDF, baixar).
        contexto["doc_os"] = {
            "titulo": f"Ordem de serviço {solicitacao.numero}".strip(),
            "disponivel": not contexto["pendencias_os"],
            "mensagem": "Falta: " + " ".join(contexto["pendencias_os"]) + " Salve para gerar a OS.",
            # O quadro mostra a folha em HTML; "Visualizar" e "Baixar" levam ao PDF.
            "quadro": reverse("coffee_break:ordem_servico_previa", args=[solicitacao.pk]),
            "src": url_os,
            "url_pdf": url_os + "?baixar=1",
            # O editor de documentos de Viagens: barra, pendências e a folha editável.
            "embutido": cartao(CHAVE_OS, solicitacao.pk, f"Ordem de serviço {solicitacao.numero}".strip()),
            # A via emitida e a assinada (anexar assinado no menu do cartão).
            **_vias_do_documento("os", solicitacao),
        }
        contexto["usa_dialogo_assinado"] = True
        contexto["pendencias_oficio"] = documentos.pendencias_oficio(solicitacao)
        contexto["pendencias_certifico"] = documentos.pendencias_certifico(solicitacao)
        if etapa == "nota":
            _contexto_da_nota(contexto, form, solicitacao)
        if etapa == "protocolo":
            itens = documentos.itens_anexo(solicitacao)
            contexto["itens_anexo"] = itens
            contexto["anexo_pronto"] = all(item["pronto"] for item in itens)
            contexto["anexo_faltando"] = sum(1 for item in itens if not item["pronto"])
            # O PDF único junta o que existe; a tela avisa vencida e o que falta.
            contexto["anexo_disponivel"] = any(item["disponivel"] for item in itens)
            contexto["partes_anexo"] = documentos.partes_do_anexo(solicitacao)
            contexto["avisos_anexo"] = documentos.avisos_do_pacote(itens)
            contexto["eprotocolo"] = documentos.textos_eprotocolo(solicitacao)
            # O comprovante da OB: anexar (modal de anexo de documentos) e enviar ao fornecedor.
            contexto["usa_dialogo_assinado"] = True
            contexto["url_anexar_ob"] = reverse("coffee_break:anexar_ob", args=[solicitacao.pk])
            contexto["avisos_ob"] = services.avisos_da_ob(solicitacao)
    return contexto


def _vias_do_documento(documento, solicitacao):
    """O que o cartão do documento mostra das vias guardadas (coffee_break/vias.py):
    a assinada, se houver, a última emitida e o anexar assinado."""
    from . import vias

    tipo = vias.TIPOS[documento]
    lista = list(vias.vias(tipo, solicitacao)[:10])
    versoes = {}
    if lista:
        from documentos.models import DocumentoAssinaturaVersao

        for versao in DocumentoAssinaturaVersao.objects.filter(artefato__in=lista).select_related("criado_por"):
            versoes.setdefault(versao.artefato_id, []).append(versao)
    vigente = vias.assinada(tipo, solicitacao)
    return {
        "assinado": vigente is not None,
        "assinatura": vigente,
        "url_anexar": "" if solicitacao.bloqueada_para_edicao else reverse(
            "coffee_break:anexar_assinado", args=[solicitacao.pk, documento]
        ),
        "vias": [
            {
                "via": via,
                "url": reverse("coffee_break:via_arquivo", args=[via.pk]),
                "assinadas": [
                    {"versao": v, "url": reverse("coffee_break:via_arquivo", args=[via.pk]) + f"?assinada={v.pk}"}
                    for v in versoes.get(via.pk, [])
                ],
            }
            for via in lista
        ],
    }


def _contexto_da_nota(contexto, form, solicitacao):
    """Etapa 2 como a etapa 1: o número e a data do ofício já vêm preenchidos
    (o próximo da numeração e o dia de hoje; pode alterar), a nota fiscal se
    anexa pelo modal de anexo de documentos, e o ofício e o certifico abrem no
    editor de documentos, tudo editável."""
    valores = contexto["valores"]
    atual = services.partes_numero(solicitacao.numero_oficio)
    data = solicitacao.data_oficio or timezone.localdate()
    contexto["oficio_ano"] = atual[1] if atual else data.year
    contexto["oficio_livre"] = bool(solicitacao.numero_oficio and not atual)
    if not valores.get("numero_oficio") and not form.is_bound:
        valores["numero_oficio"] = str(services.proxima_sequencia_oficio(contexto["oficio_ano"]))
    if not valores.get("data_oficio") and not form.is_bound:
        valores["data_oficio"] = data.isoformat()
    contexto["usa_dialogo_assinado"] = True
    # Conferência da nota anexada (fornecedor, valor, data e duplicidade).
    contexto["avisos_nota"] = services.avisos_da_nota(solicitacao) if solicitacao.numero_nota_fiscal else []
    contexto["ajuda_faturada"] = (
        f"Pedido: {solicitacao.quantidade}. Em branco, o lote desconta o pedido; "
        "com a nota, desconta o faturado e a diferença volta ao saldo."
    )
    contexto["url_anexar_nota"] = reverse("coffee_break:anexar_nota", args=[solicitacao.pk])
    # Pagamento conjunto: as OS do mesmo pagamento e as que podem entrar
    # (mesmo lote, sem protocolo, não pagas), na lista de escolha do cabeçalho.
    grupo = solicitacao.grupo_pagamento()
    outras = [membro for membro in grupo if membro.pk != solicitacao.pk]
    contexto["outras_do_pagamento"] = [
        {
            "s": membro,
            "url_anexar": reverse("coffee_break:anexar_nota", args=[membro.pk]),
            "url_etapa": reverse("coffee_break:etapa_nota", args=[membro.pk]),
        }
        for membro in outras
    ]

    def _opcao(membro, marcada):
        quando = membro.data_inicio_evento.strftime("%d/%m/%Y") if membro.data_inicio_evento else (membro.periodo_evento_texto or "sem data")
        nota = f"NF {membro.numero_nota_fiscal}" if membro.numero_nota_fiscal else "sem nota"
        return {
            "valor": str(membro.pk),
            "rotulo": f"OS {membro.numero} — {membro.descricao_evento}",
            "detalhes": f"{quando} · {membro.quantidade} pessoas · {nota}",
            "selecionado": marcada,
            "chip": "No pagamento" if marcada else "",
            "chip_tom": "atendido",
        }

    contexto["opcoes_vinculo"] = [_opcao(m, True) for m in outras] + [
        _opcao(m, False) for m in services.candidatas_ao_pagamento(solicitacao)
    ]
    contexto["pagamento_conjunto"] = bool(outras)
    url_oficio = reverse("coffee_break:oficio", args=[solicitacao.pk])
    url_certifico = reverse("coffee_break:certifico", args=[solicitacao.pk])
    titulo_oficio = f"Ofício {solicitacao.numero_oficio}".strip()
    contexto["doc_oficio"] = {
        "titulo": titulo_oficio,
        "disponivel": not contexto["pendencias_oficio"],
        "src": url_oficio,
        "url_pdf": url_oficio + "?baixar=1",
        "embutido": cartao(CHAVE_OFICIO, solicitacao.pk, titulo_oficio),
        **_vias_do_documento("oficio", solicitacao),
    }
    contexto["doc_certifico"] = {
        "titulo": "Certifico digital",
        "disponivel": not contexto["pendencias_certifico"],
        "src": url_certifico,
        "url_pdf": url_certifico + "?baixar=1",
        "embutido": cartao(CHAVE_CERTIFICO, solicitacao.pk, "Certifico digital"),
    }
    # Um certifico por nota: com pagamento conjunto, um cartão por OS.
    contexto["docs_certifico"] = []
    for membro in grupo:
        url_m = reverse("coffee_break:certifico", args=[membro.pk])
        nf_m = membro.numero_nota_fiscal.strip()
        titulo_m = "Certifico digital" + (f" — NF {nf_m}" if outras and nf_m else f" — OS {membro.numero}" if outras else "")
        contexto["docs_certifico"].append({
            "titulo": titulo_m,
            "disponivel": bool(nf_m),
            "src": url_m,
            "url_pdf": url_m + "?baixar=1",
            "embutido": cartao(CHAVE_CERTIFICO, membro.pk, titulo_m),
            **_vias_do_documento("certifico", membro),
        })


def _titulo_e_trilha(contexto, solicitacao, etapa):
    rotulo = solicitacao.numero or f"#{solicitacao.pk}"
    contexto["titulo_pagina"] = f"Solicitação {rotulo} — {ETAPA_POR_CHAVE[etapa]['titulo']}"
    contexto["breadcrumb"] = _breadcrumb(
        {"label": "Solicitações", "url": reverse("coffee_break:solicitacoes")},
        {"label": rotulo},
    )


TEMPLATES_ETAPA = {
    "pedido": "pages/coffee_break/form.html",
    "nota": "pages/coffee_break/etapa_nota.html",
    "protocolo": "pages/coffee_break/etapa_protocolo.html",
}


def _duplicados_do_email(texto_origem):
    """Solicitações de coffee break que já saíram do mesmo e-mail."""
    historicos = (
        HistoricoCoffeeBreak.objects.filter(
            acao=AcaoHistoricoCoffeeBreak.CRIACAO, descricao__contains=texto_origem
        )
        .select_related("solicitacao")
        .order_by("-criado_em")[:5]
    )
    return [
        {
            "titulo": f"Solicitação {h.solicitacao.numero or '#' + str(h.solicitacao.pk)}",
            "url": reverse("coffee_break:editar", args=[h.solicitacao.pk]),
        }
        for h in historicos
    ]


@acesso_ao_modulo
@require_POST
def ler_email(request):
    """Lê o e-mail do pedido (arquivo ou texto colado) para a tela "Nova solicitação".

    Não grava nada: devolve as sugestões em JSON (`core.preencher_por_email`)
    — com o aviso de lote e saldo do município — e guarda o original até a
    solicitação ser salva, para o histórico dizer de onde ela veio.
    """
    return preencher_por_email.responder_leitura(
        request,
        modulo="coffee_break",
        sugerir=preenchimento.sugestoes,
        formulario=PedidoCoffeeBreakForm,
        duplicados=_duplicados_do_email,
    )


# O que a cópia leva da solicitação original: o evento que se repete. Nunca
# datas, número, nota, ofício, protocolo nem pagamento — esses são da nova.
CAMPOS_DUPLICADOS = ("municipio", "descricao_evento", "quantidade", "horario_evento", "local_entrega", "responsavel_recebimento")


def _origem_da_copia(dados):
    """A solicitação que se duplica (?duplicar=<pk>), ou None."""
    pk = dados.get("duplicar")
    if not pk or not str(pk).isdigit():
        return None
    return SolicitacaoCoffeeBreak.objects.filter(pk=pk).first()


@acesso_ao_modulo
def duplicar_solicitacao(request, pk):
    """"Duplicar" da lista: abre a nova solicitação com o evento copiado e a data em branco."""
    get_object_or_404(SolicitacaoCoffeeBreak, pk=pk)
    return redirect(f"{reverse('coffee_break:nova')}?duplicar={pk}")


@acesso_ao_modulo
@require_GET
def locais_entrega(request):
    """Local de entrega e responsável já usados no município (JSON), do mais
    recente ao mais antigo, sem repetir. A tela sugere; só o clique preenche."""
    municipio = request.GET.get("municipio") or ""
    resultados = []
    if municipio.isdigit():
        vistos = set()
        recentes = (
            SolicitacaoCoffeeBreak.objects.filter(municipio_id=municipio)
            .exclude(local_entrega="")
            .order_by("-data_inicio_evento", "-pk")
            .values_list("local_entrega", "responsavel_recebimento", "numero", "data_inicio_evento")[:200]
        )
        for local, responsavel, numero, data in recentes:
            chave = (local.strip().casefold(), responsavel.strip().casefold())
            if chave in vistos:
                continue
            vistos.add(chave)
            detalhe = " · ".join(p for p in (responsavel, f"OS {numero}" if numero else "", f"{data:%d/%m/%Y}" if data else "") if p)
            resultados.append({
                "nome": local,
                "detalhe": detalhe,
                "campos": {"local_entrega": local, "responsavel_recebimento": responsavel},
            })
            if len(resultados) == 10:
                break
    return JsonResponse({"resultados": resultados})


@acesso_ao_modulo
def nova_solicitacao(request):
    from . import origem as origem_evento

    email_origem = None
    # "Duplicar" da lista: ?duplicar=<pk> (e o campo oculto no POST, para o histórico).
    copia_de = _origem_da_copia(request.POST if request.method == "POST" else request.GET)
    # "Pedir coffee break" do evento ou da palestra: ?solicitacao=<pk> ou ?demanda=<pk>.
    campo_origem, evento_origem = origem_evento.origem_do_pedido(
        request.POST if request.method == "POST" else request.GET, request.user
    )
    if request.method == "POST":
        form = PedidoCoffeeBreakForm(request.POST, request.FILES)
        # O e-mail lido em "Preencher com um e-mail", se a tela veio dele.
        origem = preencher_por_email.origem_do_pedido(request, "coffee_break")
        if form.is_valid():
            if evento_origem is not None:
                setattr(form.instance, campo_origem, evento_origem)
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
                descricao = "Solicitação registrada no sistema."
                if evento_origem is not None:
                    descricao += f" Pedida a partir de: {origem_evento.rotulo(campo_origem, evento_origem)}."
                if copia_de is not None:
                    descricao += f" Duplicada da solicitação {copia_de.numero or '#' + str(copia_de.pk)}."
                if origem:
                    descricao += f" {preencher_por_email.texto_da_origem(origem)}."
                services.registrar_historico(
                    solicitacao,
                    request.user,
                    AcaoHistoricoCoffeeBreak.CRIACAO,
                    descricao,
                )
                preencher_por_email.concluir_origem(request, origem)
                _registrar_retroativo(form, solicitacao, request.user)
                messages.success(
                    request,
                    f"Solicitação {solicitacao.numero} registrada no {solicitacao.lote.rotulo_curto}"
                    f" ({solicitacao.lote.contrato.fornecedor.razao_social}). A ordem de serviço já pode ser gerada.",
                )
                _avisar_antecedencia(request, solicitacao)
                return redirect("coffee_break:solicitacoes")
        else:
            messages.error(request, "Corrija os campos destacados para continuar.")
        email_origem = preencher_por_email.origem_pendente(request, "coffee_break")
    else:
        iniciais = origem_evento.valores_iniciais(campo_origem, evento_origem) if evento_origem is not None else {}
        if copia_de is not None:
            iniciais = {
                campo: getattr(copia_de, f"{campo}_id" if campo == "municipio" else campo)
                for campo in CAMPOS_DUPLICADOS
                if getattr(copia_de, f"{campo}_id" if campo == "municipio" else campo) not in ("", None)
            }
        form = PedidoCoffeeBreakForm(initial=iniciais)
    contexto = _contexto_formulario(request, form)
    contexto["email_origem"] = email_origem
    if copia_de is not None:
        contexto["copia_de"] = {
            "pk": copia_de.pk,
            "rotulo": f"Solicitação {copia_de.numero or '#' + str(copia_de.pk)} — {copia_de.descricao_evento}",
            "url": reverse("coffee_break:editar", args=[copia_de.pk]),
        }
    if evento_origem is not None:
        parametro = "solicitacao" if campo_origem == "solicitacao_evento" else "demanda"
        contexto["origem_evento"] = {
            "rotulo": origem_evento.rotulo(campo_origem, evento_origem),
            "url": origem_evento.url(campo_origem, evento_origem),
            "parametro": parametro,
            "pk": evento_origem.pk,
        }
    # A OS abre já na nova solicitação, no editor de documentos, e acompanha o preenchimento.
    contexto["doc_os_nova"] = {
        "titulo": "Ordem de serviço",
        "embutido": {"id": "documento-coffee-os-nova", "url": reverse("coffee_break:nova_os_embutido")},
    }
    contexto["titulo_pagina"] = "Nova Solicitação de Coffee Break"
    contexto["breadcrumb"] = _breadcrumb(
        {"label": "Solicitações", "url": reverse("coffee_break:solicitacoes")},
        {"label": "Nova solicitação"},
    )
    return render(request, "pages/coffee_break/form.html", contexto)


def _registrar_retroativo(form, solicitacao, usuario):
    """Evento anterior à solicitação, aceito como registro retroativo: a justificativa vai para o histórico."""
    dados = getattr(form, "cleaned_data", {})
    if getattr(form, "evento_retroativo", False) and dados.get("registro_retroativo"):
        services.registrar_historico(
            solicitacao, usuario, AcaoHistoricoCoffeeBreak.ATUALIZACAO,
            f"Registro retroativo (evento anterior à data da solicitação): {dados.get('justificativa_retroativo', '').strip()}",
        )


def _registrar_correcao(form, anterior, solicitacao, usuario):
    """Na solicitação reaberta, cada campo corrigido: o valor anterior e o novo."""
    mudancas = []
    for nome in form.changed_data:
        if nome not in form._meta.fields:
            continue
        antes, depois = getattr(anterior, nome), getattr(solicitacao, nome)
        if antes != depois:
            mudancas.append(
                f"{form.fields[nome].label}: {services._valor_legivel(antes)} → {services._valor_legivel(depois)}"
            )
    if mudancas:
        services.registrar_historico(
            solicitacao, usuario, AcaoHistoricoCoffeeBreak.ATUALIZACAO, "Correção — " + "; ".join(mudancas) + "."
        )


def _registrar_faturada(solicitacao, usuario):
    """A quantidade da nota no histórico, com a diferença que voltou (ou saiu) do lote."""
    faturada = solicitacao.quantidade_faturada
    if faturada is None:
        texto = f"Quantidade faturada removida: o lote volta a descontar as {solicitacao.quantidade} pedidas."
    else:
        diferenca = solicitacao.quantidade - faturada
        texto = f"Quantidade faturada: {faturada} de {solicitacao.quantidade} pedidas"
        if diferenca > 0:
            texto += f"; {diferenca} voltaram ao saldo do lote."
        elif diferenca < 0:
            texto += f"; {-diferenca} a mais saíram do saldo do lote."
        else:
            texto += "."
    services.registrar_historico(solicitacao, usuario, AcaoHistoricoCoffeeBreak.ATUALIZACAO, texto)


def _avisar_antecedencia(request, solicitacao):
    aviso = services.aviso_de_antecedencia(solicitacao)
    if aviso:
        messages.warning(request, aviso)


def _tela_da_etapa(request, pk, etapa):
    """Uma etapa da solicitação: mostra e grava só os campos dela."""
    config = ETAPA_POR_CHAVE[etapa]
    rota = f"coffee_break:{config['rota']}"
    solicitacao = get_object_or_404(
        SolicitacaoCoffeeBreak.objects.select_related(
            "lote__contrato__fornecedor", "criado_por", "cancelada_por"
        ),
        pk=pk,
    )
    Formulario = config["form"]
    somente_leitura = solicitacao.bloqueada_para_edicao
    # Reaberta para correção: o histórico guarda o valor anterior e o novo.
    anterior = (
        SolicitacaoCoffeeBreak.objects.get(pk=solicitacao.pk)
        if solicitacao.em_correcao and request.method == "POST" else None
    )
    if somente_leitura:
        # Canceladas e concluídas continuam abrindo, mas sem gravar — só para
        # consulta, documentos, ações de situação e histórico.
        if request.method == "POST":
            messages.warning(
                request,
                "Solicitações canceladas ou concluídas ficam bloqueadas para edição.",
            )
            return redirect(rota, pk=solicitacao.pk)
        form = Formulario(instance=solicitacao)
        for campo in form.fields.values():
            campo.disabled = True
    elif request.method == "POST":
        form = Formulario(request.POST, request.FILES, instance=solicitacao)
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
                # O que é do pagamento (ofício, protocolo, marcos) vale para as OS do mesmo pagamento.
                services.espelhar(solicitacao, form.changed_data, request.user)
                if etapa == "nota":
                    services.sincronizar_protocolo(solicitacao, request.user)
                if etapa == "nota" and "vinculadas_enviado" in request.POST and not somente_leitura:
                    try:
                        services.definir_pagamento_conjunto(
                            solicitacao, request.POST.getlist("vinculadas"), request.user
                        )
                    except ValidationError as erro:
                        for mensagem in erro.messages:
                            messages.error(request, mensagem)
                    solicitacao.refresh_from_db()
                alterados = [
                    form.fields[nome].label
                    for nome in form.changed_data
                    if nome in form.fields and nome not in ("versao", "registro_retroativo", "justificativa_retroativo")
                ]
                services.registrar_historico(
                    solicitacao,
                    request.user,
                    AcaoHistoricoCoffeeBreak.ATUALIZACAO,
                    "Campos atualizados: " + ", ".join(alterados)
                    if alterados
                    else "Solicitação salva sem alteração de campos.",
                )
                if anterior is not None:
                    _registrar_correcao(form, anterior, solicitacao, request.user)
                if "quantidade_faturada" in form.changed_data:
                    _registrar_faturada(solicitacao, request.user)
                if etapa == "pedido":
                    _registrar_retroativo(form, solicitacao, request.user)
                messages.success(request, "Solicitação de coffee break atualizada.")
                if etapa == "pedido" and {"data_inicio_evento", "municipio"}.intersection(form.changed_data):
                    _avisar_antecedencia(request, solicitacao)
                # Etapa 2 segue para a etapa 3; as etapas 1 e 3 voltam para a lista.
                if etapa == "nota":
                    return redirect("coffee_break:etapa_protocolo", pk=solicitacao.pk)
                return redirect("coffee_break:solicitacoes")
        else:
            messages.error(request, "Corrija os campos destacados para continuar.")
    else:
        form = Formulario(instance=solicitacao)
    contexto = _contexto_formulario(
        request, form, solicitacao, somente_leitura=somente_leitura, etapa=etapa
    )
    _titulo_e_trilha(contexto, solicitacao, etapa)
    return render(request, TEMPLATES_ETAPA[etapa], contexto)


@acesso_ao_modulo
def editar_solicitacao(request, pk):
    """Etapa 1 — o pedido e a ordem de serviço."""
    return _tela_da_etapa(request, pk, "pedido")


@acesso_ao_modulo
def etapa_nota(request, pk):
    """Etapa 2 — a nota recebida; dela saem o ofício e o certifico."""
    return _tela_da_etapa(request, pk, "nota")


@acesso_ao_modulo
def etapa_protocolo(request, pk):
    """Etapa 3 — os textos do eProtocolo, o anexo completo e o pagamento."""
    return _tela_da_etapa(request, pk, "protocolo")


def _contexto_andamento(solicitacao, erro="", valor="", texto=""):
    """O stepper dos marcos e o campo do próximo, como o andamento das Palestras."""
    marco = services.proximo_marco(solicitacao)
    if marco and not valor and marco["tipo"] == "date":
        valor = f"{timezone.localdate():%Y-%m-%d}"
    return {
        "etapas": services.etapas(solicitacao),
        "marco": marco,
        "ultima_anotacao": services.ultima_anotacao(solicitacao),
        "andamento_erro": erro,
        "andamento_valor": valor,
        "andamento_texto": texto,
    }


@acesso_ao_modulo
def registrar_andamento(request, pk):
    """Registra o próximo marco — na tela da solicitação ou num modal da lista.

    No modal vale o protocolo dos cadastros (`X-Cadastro-Modal`): o GET
    devolve o trecho, o POST devolve `{"ok": true}` ou o trecho com o erro.
    """
    solicitacao = _solicitacao_documental(pk)
    via_modal = request.headers.get("X-Cadastro-Modal") == "1"
    destino = reverse(f"coffee_break:{_etapa_do_marco(solicitacao)}", args=[solicitacao.pk])

    def modal(**extra):
        return render(
            request,
            "pages/coffee_break/_modal_andamento.html",
            {"solicitacao": solicitacao, **_contexto_andamento(solicitacao, **extra)},
        )

    if request.method != "POST":
        return modal() if via_modal else redirect(destino)
    valor = request.POST.get("valor", "")
    texto = request.POST.get("andamento", "")
    try:
        services.registrar_marco(solicitacao, request.user, valor, texto)
    except ValidationError as erro:
        if via_modal:
            return modal(erro=" ".join(erro.messages), valor=valor, texto=texto)
        for mensagem in erro.messages:
            messages.error(request, mensagem)
        return redirect(destino)
    messages.success(request, f"Andamento registrado: {solicitacao.situacao_financeira_display}.")
    return JsonResponse({"ok": True}) if via_modal else redirect(destino)


@acesso_ao_modulo
def registrar_entrega(request, pk):
    """A entrega e as ocorrências com o fornecedor, depois do evento.

    Da lista abre em modal (protocolo dos cadastros, `X-Cadastro-Modal`); sem
    ele, é uma página com as entregas já registradas e o formulário.
    """
    from .forms import OcorrenciaEntregaForm

    solicitacao = _solicitacao_documental(pk)
    via_modal = _modal(request)
    liberada = services.entrega_liberada(solicitacao)
    form = OcorrenciaEntregaForm(request.POST or None, request.FILES or None)
    erro = ""
    if request.method == "POST":
        if not liberada:
            erro = "A entrega se registra a partir do dia do evento."
        elif form.is_valid():
            ocorrencia = services.registrar_entrega(solicitacao, request.user, form)
            messages.success(request, f"Entrega registrada: {ocorrencia.get_tipo_display().lower()}.")
            if via_modal:
                return JsonResponse({"ok": True})
            return redirect("coffee_break:entrega", pk=solicitacao.pk)
    contexto = {
        "solicitacao": solicitacao,
        "form": form,
        "valores": {nome: "" if form[nome].value() is None else str(form[nome].value()) for nome in form.fields},
        "tipos": _opcoes_choices(form.fields["tipo"].choices),
        "liberada": liberada,
        "erro": erro,
        "ocorrencias": solicitacao.ocorrencias.select_related("registrada_por"),
    }
    if via_modal:
        return render(request, "pages/coffee_break/_modal_entrega.html", contexto)
    rotulo = solicitacao.numero or f"#{solicitacao.pk}"
    contexto["breadcrumb"] = _breadcrumb(
        {"label": "Solicitações", "url": reverse("coffee_break:solicitacoes")},
        {"label": rotulo, "url": reverse("coffee_break:editar", args=[solicitacao.pk])},
        {"label": "Entrega"},
    )
    return render(request, "pages/coffee_break/entrega.html", contexto)


@acesso_ao_modulo
def ocorrencia_arquivo(request, pk):
    from .models import OcorrenciaEntrega

    return _arquivo(get_object_or_404(OcorrenciaEntrega, pk=pk).foto)


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


def _modal(request):
    return request.headers.get("X-Cadastro-Modal") == "1"


@acesso_ao_modulo
def cancelar_solicitacao(request, pk):
    """Cancela com o motivo. Da lista, abre no modal (GET mostra o motivo)."""
    solicitacao = get_object_or_404(SolicitacaoCoffeeBreak, pk=pk)
    if request.method != "POST":
        if not _modal(request):
            return redirect("coffee_break:editar", pk=solicitacao.pk)
        return render(request, "pages/coffee_break/_modal_cancelar.html", {"solicitacao": solicitacao, "erro": ""})
    try:
        services.cancelar(
            solicitacao, request.user, request.POST.get("motivo", "")
        )
    except ValidationError as erro:
        if _modal(request):
            return render(request, "pages/coffee_break/_modal_cancelar.html", {"solicitacao": solicitacao, "erro": " ".join(erro.messages)})
        for mensagem in erro.messages:
            messages.error(request, mensagem)
    else:
        messages.success(
            request,
            "Solicitação cancelada — a quantidade voltou ao saldo do lote.",
        )
        if _modal(request):
            return JsonResponse({"ok": True})
    return redirect("coffee_break:editar", pk=solicitacao.pk)


@acesso_ao_modulo
@require_POST
def excluir_solicitacao(request, pk):
    """Exclui a solicitação que ainda não entrou no pagamento (sem nota nem
    protocolo); depois disso, o caminho é cancelar."""
    solicitacao = get_object_or_404(SolicitacaoCoffeeBreak, pk=pk)
    if solicitacao.financeiro_iniciado:
        messages.error(request, f"A solicitação {solicitacao.numero} já tem nota ou protocolo: cancele em vez de excluir.")
        return redirect("coffee_break:solicitacoes")
    numero = solicitacao.numero or f"#{solicitacao.pk}"
    with transaction.atomic():
        # Se era a principal de um pagamento conjunto, a próxima assume.
        services.sair_do_pagamento_conjunto(
            solicitacao, request.user, f"A OS {numero} foi excluída e saiu do pagamento conjunto."
        )
        solicitacao.delete()
    messages.success(request, f"Solicitação {numero} excluída — a quantidade voltou ao saldo do lote.")
    return redirect("coffee_break:solicitacoes")


@acesso_ao_modulo
@require_POST
def baixar_arquivos(request, pk):
    """Da lista: o modal "Baixar documentos" de Viagens com os quatro
    arquivos do protocolo. `itens`: os, oficio, notas, contratos; `saida`:
    `separados` (um PDF, ou ZIP com um PDF cada) ou `unico` (um PDF só, na
    ordem). Baixar conclui a etapa 3 (é o dia do atesto e do envio ao GAF)."""
    import zipfile

    from pypdf import PdfReader, PdfWriter

    solicitacao = _solicitacao_documental(pk)
    escolhidas = [p for p in documentos.PARTES if p in request.POST.getlist("itens")]
    if not escolhidas:
        messages.error(request, "Marque ao menos um arquivo para baixar.")
        return redirect("coffee_break:solicitacoes")
    nomes = {"os": "1 - Ordem de servico", "oficio": "2 - Oficio", "notas": "3 - Notas e certificos", "contratos": "4 - Contratos e certidoes"}
    arquivos = []
    for parte in escolhidas:
        try:
            arquivos.append((documentos.nome_arquivo(nomes[parte], solicitacao), documentos.parte_pdf(solicitacao, parte)))
        except ValidationError as erro:
            for mensagem in erro.messages:
                messages.warning(request, mensagem)
    if not arquivos:
        return redirect("coffee_break:solicitacoes")
    services.marcar_atesto(solicitacao, request.user)
    if request.POST.get("saida") == "unico" and len(arquivos) > 1:
        escritor = PdfWriter()
        for _nome, conteudo in arquivos:
            escritor.append(PdfReader(io.BytesIO(conteudo)))
        saida = io.BytesIO()
        escritor.write(saida)
        nome = documentos.nome_arquivo("Arquivos do protocolo", solicitacao)
        resposta = HttpResponse(saida.getvalue(), content_type="application/pdf")
    elif len(arquivos) == 1:
        nome, conteudo = arquivos[0]
        resposta = HttpResponse(conteudo, content_type="application/pdf")
    else:
        saida = io.BytesIO()
        with zipfile.ZipFile(saida, "w", zipfile.ZIP_DEFLATED) as pacote:
            for nome_arquivo, conteudo in arquivos:
                pacote.writestr(nome_arquivo, conteudo)
        nome = documentos.nome_arquivo("Arquivos do protocolo", solicitacao)[: -len(".pdf")] + ".zip"
        resposta = HttpResponse(saida.getvalue(), content_type="application/zip")
    resposta["Content-Disposition"] = f'attachment; filename="{nome}"'
    return resposta


@gerenciamento_de_cadastros
@require_POST
def reabrir_solicitacao(request, pk):
    """Reabre a concluída para correção (ou encerra a correção), só para administradores do módulo."""
    solicitacao = get_object_or_404(SolicitacaoCoffeeBreak, pk=pk)
    try:
        if request.POST.get("acao") == "encerrar":
            services.encerrar_correcao(solicitacao, request.user)
            messages.success(request, "Correção encerrada: a solicitação voltou a ficar só para consulta.")
        else:
            services.reabrir_para_correcao(solicitacao, request.user, request.POST.get("motivo", ""))
            messages.success(request, "Solicitação reaberta para correção. O que mudar fica no histórico.")
    except ValidationError as erro:
        for mensagem in erro.messages:
            messages.error(request, mensagem)
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

def _rodar_importacao(caminho, usuario, simular):
    """Roda o importar_coffee_break e devolve (resumo, avisos) ou levanta o erro."""
    import io

    from django.core.management import call_command

    from .management.commands.importar_coffee_break import Command

    comando = Command(stdout=io.StringIO(), stderr=io.StringIO())
    call_command(comando, str(caminho), usuario=usuario.get_username(), dry_run=simular)
    return comando.resumo, comando.avisos


@gerenciamento_de_cadastros
def importar_planilha(request):
    """A planilha "CONTROLE COFFE ASCOM" pelo navegador: simula e só depois grava.

    O arquivo enviado fica numa pasta temporária do servidor, com o nome
    guardado na sessão, até a confirmação (ou a próxima simulação). A
    importação é idempotente: enviar a planilha de novo atualiza sem duplicar.
    """
    import tempfile
    import uuid

    from django.core.management.base import CommandError

    pasta = Path(tempfile.gettempdir()) / "coffee-break-importacao"
    pasta.mkdir(exist_ok=True)
    contexto = {
        "breadcrumb": _breadcrumb(
            {"label": "Cadastros", "url": reverse("coffee_break:cadastros")},
            {"label": "Importar planilha"},
        ),
        "simulacao": None,
        "importado": None,
        "avisos": [],
        "original": "",
    }
    if request.method == "POST":
        acao = request.POST.get("acao")
        if acao == "simular":
            arquivo = request.FILES.get("planilha")
            if not arquivo or not arquivo.name.lower().endswith(".xlsx"):
                messages.error(request, "Escolha a planilha em .xlsx.")
                return redirect("coffee_break:importar_planilha")
            if arquivo.size > 20 * 1024 * 1024:
                messages.error(request, "A planilha passa de 20 MB.")
                return redirect("coffee_break:importar_planilha")
            anterior = request.session.pop("coffee_importacao", None)
            if anterior:
                (pasta / anterior["arquivo"]).unlink(missing_ok=True)
            nome = f"{uuid.uuid4().hex}.xlsx"
            with open(pasta / nome, "wb") as destino:
                for pedaco in arquivo.chunks():
                    destino.write(pedaco)
            try:
                resumo, avisos = _rodar_importacao(pasta / nome, request.user, simular=True)
            except (CommandError, Exception) as erro:  # planilha fora do formato
                (pasta / nome).unlink(missing_ok=True)
                messages.error(request, f"Não foi possível ler a planilha: {erro}")
                return redirect("coffee_break:importar_planilha")
            request.session["coffee_importacao"] = {"arquivo": nome, "original": arquivo.name}
            contexto.update({"simulacao": resumo, "avisos": avisos, "original": arquivo.name})
        elif acao == "importar":
            pendente = request.session.get("coffee_importacao")
            caminho = pasta / pendente["arquivo"] if pendente else None
            if not caminho or not caminho.exists():
                messages.error(request, "Envie a planilha e simule de novo antes de importar.")
                return redirect("coffee_break:importar_planilha")
            try:
                resumo, avisos = _rodar_importacao(caminho, request.user, simular=False)
            except (CommandError, Exception) as erro:
                messages.error(request, f"A importação não foi feita: {erro}")
                return redirect("coffee_break:importar_planilha")
            finally:
                caminho.unlink(missing_ok=True)
                request.session.pop("coffee_importacao", None)
            messages.success(
                request,
                f"Planilha importada: {resumo['criados']} registros criados e "
                f"{resumo['atualizados']} atualizados.",
            )
            contexto.update({"importado": resumo, "avisos": avisos, "original": pendente["original"]})
    return render(request, "pages/coffee_break/importar_planilha.html", contexto)


@gerenciamento_de_cadastros
def cadastros(request):
    return redirect("coffee_break:cadastro_lista", tipo="fornecedores")


@gerenciamento_de_cadastros
def lista_cadastro(request, tipo, modal=None):
    """A lista do cadastro; criar e editar abrem num modal sobre ela.

    Protocolo dos cadastros das Palestras (`data-cadastro-modal`, cabeçalho
    `X-Cadastro-Modal`, `{"ok": true}` no sucesso). Sem JavaScript, `?novo=1`
    ou `?editar=<pk>` abrem a lista já com o modal aberto.
    """
    config = _config_cadastro(tipo)
    if config.get("unico"):
        ConfiguracaoCoffeeBreak.atual()
    if modal is None and request.method == "GET":
        editar = request.GET.get("editar", "")
        if request.GET.get("novo"):
            modal = _contexto_modal(tipo, config, config["form"](), None)
        elif editar.isdigit():
            instancia = get_object_or_404(config["model"], pk=editar)
            modal = _contexto_modal(tipo, config, config["form"](instance=instancia), instancia)
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
    pagina, paginas_visiveis, _querystring = _paginar(request, queryset)
    parametros = request.GET.copy()
    for chave in ("pagina", "novo", "editar"):
        parametros.pop(chave, None)
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
            "querystring": parametros.urlencode(),
            "tem_filtros": bool(q),
            "modal": modal,
            # Contratos: "Anexar contrato ou aditivo" usa o modal de anexo de documentos.
            "usa_dialogo_assinado": tipo == "contratos",
            "breadcrumb": _breadcrumb({"label": "Cadastros"}, {"label": config["titulo"]}),
        },
    )


def _contexto_modal(tipo, config, form, instancia):
    campos = _campos_cadastro(form)
    erros_gerais = list(form.non_field_errors())
    return {
        "url_acao": (
            reverse("coffee_break:cadastro_editar", args=[tipo, instancia.pk])
            if instancia
            else reverse("coffee_break:cadastro_novo", args=[tipo])
        ),
        "titulo": f"Editar {config['singular']}" if instancia else f"Novo {config['singular']}",
        "singular": config["singular"],
        "versao": form["versao"].value() or "",
        "campos": campos,
        "erros_gerais": erros_gerais,
        "erros_total": sum(1 for campo in campos if campo["erros"]) + len(erros_gerais),
    }


@gerenciamento_de_cadastros
def editar_cadastro(request, tipo, pk=None):
    config = _config_cadastro(tipo)
    if config.get("unico") and not pk:
        return redirect("coffee_break:cadastro_lista", tipo=tipo)
    instancia = get_object_or_404(config["model"], pk=pk) if pk else None
    via_modal = request.headers.get("X-Cadastro-Modal") == "1"
    if request.method == "GET" and not via_modal:
        destino = reverse("coffee_break:cadastro_lista", args=[tipo])
        return redirect(f"{destino}?{'editar=' + str(pk) if pk else 'novo=1'}")
    if request.method == "POST":
        form = config["form"](request.POST, request.FILES, instance=instancia)
        if form.is_valid():
            form.save()
            messages.success(request, f"{config['singular'].capitalize()} salvo com sucesso.")
            if via_modal:
                return JsonResponse({"ok": True})
            return redirect("coffee_break:cadastro_lista", tipo=tipo)
    else:
        form = config["form"](instance=instancia)
    modal = _contexto_modal(tipo, config, form, instancia)
    if via_modal:
        return render(request, "pages/coffee_break/_modal_cadastro.html", {"dados": modal, "tipo": tipo})
    return lista_cadastro(request, tipo, modal=modal)


@gerenciamento_de_cadastros
@require_POST
def excluir_cadastro(request, tipo, pk):
    config = _config_cadastro(tipo)
    objeto = get_object_or_404(config["model"], pk=pk)
    if config.get("unico"):
        messages.error(request, "Esta configuração não se exclui; edite os campos.")
        return redirect("coffee_break:cadastro_lista", tipo=tipo)
    try:
        objeto.delete()
    except ProtectedError:
        messages.error(
            request,
            f"Não é possível excluir: {config['singular']} em uso (contratos, lotes ou solicitações).",
        )
    else:
        messages.success(request, f"{config['singular'].capitalize()} excluído.")
    return redirect("coffee_break:cadastro_lista", tipo=tipo)


# ---------------------------------------------------------------------------
# Documentos: ordem de serviço, certifico e pacote do protocolo
# ---------------------------------------------------------------------------

def _solicitacao_documental(pk):
    return get_object_or_404(
        SolicitacaoCoffeeBreak.objects.select_related("lote__contrato__fornecedor"),
        pk=pk,
    )


def _pdf_ou_volta(request, solicitacao, gerar, prefixo, volta="editar", tipo="application/pdf", extensao=".pdf"):
    try:
        conteudo = gerar(solicitacao)
    except ValidationError as erro:
        for mensagem in erro.messages:
            messages.error(request, mensagem)
        return redirect(f"coffee_break:{volta}", pk=solicitacao.pk)
    resposta = HttpResponse(conteudo, content_type=tipo)
    nome = documentos.nome_arquivo(prefixo, solicitacao)
    if extensao != ".pdf":
        nome = nome[: -len(".pdf")] + extensao
    disposicao = "attachment" if request.GET.get("baixar") else "inline"
    resposta["Content-Disposition"] = f'{disposicao}; filename="{nome}"'
    return resposta


# Mostrado no visualizador da própria tela (iframe), como os documentos de Viagens.
@xframe_options_sameorigin
@acesso_ao_modulo
def ordem_servico(request, pk):
    return _pdf_ou_volta(
        request, _solicitacao_documental(pk), documentos.ordem_servico_pdf, "Ordem de Servico"
    )


@acesso_ao_modulo
def nova_os_embutido(request):
    """O editor de documentos de Viagens na nova solicitação: a mesma barra e
    a folha da OS, que acompanha o formulário enquanto se preenche. Editar na
    folha e imprimir vêm depois de salvar (a OS ainda não existe)."""
    doc = {
        "tipo": CHAVE_OS,
        "rotulo": "Ordem de serviço",
        "url_pdf": "",
        "pode_emitir": False,
        "pode_editar": False,
        "pendencias": ["Salve a solicitação para emitir a OS em PDF e editar o texto na própria folha."],
        "historico": [],
        "url_folha": reverse("coffee_break:nova_os_folha"),
    }
    return render(request, "documentos/editor/embutido.html", {"doc": doc})


@xframe_options_sameorigin
@acesso_ao_modulo
def nova_os_folha(request):
    """A folha da OS com o que está no formulário da nova solicitação (GET), sem gravar."""
    from .editor import folha_da_nova

    resposta = HttpResponse(folha_da_nova(request.GET))
    resposta["Cache-Control"] = "no-store"
    return resposta


@xframe_options_sameorigin
@acesso_ao_modulo
def ordem_servico_previa(request, pk):
    """A OS desenhada em HTML para o visualizador da etapa 1."""
    solicitacao = _solicitacao_documental(pk)
    try:
        html = documentos.ordem_servico_previa(solicitacao)
    except ValidationError as erro:
        html = "<p style='font:14px sans-serif;padding:16px'>" + " ".join(erro.messages) + "</p>"
    return HttpResponse(html)


# Mostrado no visualizador da própria tela (iframe), como os documentos de Viagens.
@xframe_options_sameorigin
@acesso_ao_modulo
def oficio(request, pk):
    return _pdf_ou_volta(
        request, _solicitacao_documental(pk), documentos.oficio_pdf, "Oficio", volta="etapa_nota"
    )


# Mostrado no visualizador da própria tela (iframe), como os documentos de Viagens.
@xframe_options_sameorigin
@acesso_ao_modulo
def certifico(request, pk):
    return _pdf_ou_volta(
        request, _solicitacao_documental(pk), documentos.certifico_pdf, "Certifico", volta="etapa_nota"
    )


@acesso_ao_modulo
def pacote_parte(request, pk, parte):
    """Um dos quatro arquivos da etapa 3 (OS, ofício, notas e certificos,
    contratos e certidões)."""
    if parte not in documentos.PARTES:
        raise Http404
    nomes = {"os": "Ordem de servico", "oficio": "Oficio", "notas": "Notas e certificos", "contratos": "Contratos e certidoes"}
    solicitacao = _solicitacao_documental(pk)
    resposta = _pdf_ou_volta(
        request, solicitacao, lambda s: documentos.parte_pdf(s, parte), nomes[parte], volta="etapa_protocolo",
    )
    if request.GET.get("baixar") and resposta.get("Content-Type") == "application/pdf":
        # Baixar os arquivos conclui a etapa 3: é o dia do atesto e do envio ao GAF.
        services.marcar_atesto(solicitacao, request.user)
    return resposta


# ---------------------------------------------------------------------------
# Vias guardadas: a emitida e a assinada da OS, do ofício e do certifico
# ---------------------------------------------------------------------------

@require_POST
@acesso_ao_modulo
def anexar_assinado(request, pk, documento):
    """A via assinada da OS, do ofício ou do certifico, pelo modal de anexo de
    documentos: anexa (ou troca) e passa a valer no lugar da gerada; remover
    revoga a assinada (o arquivo fica guardado) e a gerada volta a valer."""
    from django.utils.http import url_has_allowed_host_and_scheme

    from documentos.services.exceptions import DocumentError
    from documentos.services.persistence import anexar_arquivo_assinado, remover_arquivo_assinado

    from . import vias

    if documento not in vias.TIPOS:
        raise Http404
    tipo = vias.TIPOS[documento]
    solicitacao = _solicitacao_documental(pk)
    tela = "coffee_break:editar" if documento == "os" else "coffee_break:etapa_nota"
    destino = request.POST.get("next") or reverse(tela, args=[pk])
    if not url_has_allowed_host_and_scheme(destino, allowed_hosts={request.get_host()}, require_https=request.is_secure()):
        destino = reverse(tela, args=[pk])
    if solicitacao.bloqueada_para_edicao:
        messages.warning(request, "Solicitações canceladas ou concluídas ficam bloqueadas para edição.")
        return redirect(destino)
    rotulo = {"os": "da ordem de serviço", "oficio": "do ofício", "certifico": "do certifico"}[documento]
    dono = vias.dono(tipo, solicitacao)
    if request.POST.get("acao") == "remover":
        versao = vias.assinada(tipo, solicitacao)
        if versao is not None:
            remover_arquivo_assinado(versao.artefato)
            services.registrar_historico(
                dono, request.user, AcaoHistoricoCoffeeBreak.ATUALIZACAO,
                f"Via assinada {rotulo} removida; o PDF gerado volta a valer.",
            )
            messages.success(request, "Versão assinada removida. O PDF gerado volta a valer.")
        return redirect(destino)
    arquivo = request.FILES.get("arquivo")
    if arquivo is None:
        messages.error(request, "Escolha o PDF assinado.")
        return redirect(destino)
    gerar = {"os": documentos.ordem_servico_pdf, "oficio": documentos.oficio_pdf, "certifico": documentos.certifico_pdf}[documento]
    via = vias.ultima_via(tipo, solicitacao)
    try:
        if via is None:
            # Ainda não saiu nenhuma via: a gerada agora é a que se assinou.
            gerar(solicitacao)
            via = vias.ultima_via(tipo, solicitacao)
        if via is None:
            raise ValidationError("Não foi possível guardar a via emitida deste documento.")
        anexar_arquivo_assinado(via, arquivo)
    except (ValidationError, DocumentError) as erro:
        for mensagem in getattr(erro, "messages", [str(erro)]):
            messages.error(request, mensagem)
        return redirect(destino)
    services.registrar_historico(
        dono, request.user, AcaoHistoricoCoffeeBreak.ATUALIZACAO,
        f"Via assinada {rotulo} anexada ({arquivo.name}); passa a valer nos downloads e no pagamento.",
    )
    messages.success(request, "Documento assinado anexado. Ele passa a valer no lugar do gerado; a versão anterior fica guardada.")
    return redirect(destino)


@acesso_ao_modulo
def via_arquivo(request, pk):
    """Uma via guardada (a emitida) ou, com `?assinada=<id>`, uma versão assinada dela."""
    from documentos.models import DocumentoArtefato

    via = get_object_or_404(DocumentoArtefato, pk=pk, coffee_break_solicitacao__isnull=False)
    assinada = request.GET.get("assinada")
    if assinada:
        versao = get_object_or_404(via.versoes_assinadas, pk=assinada)
        return _arquivo(versao.arquivo, nome=versao.nome_original or None)
    return _arquivo(via.arquivo, nome=via.nome_exibicao or None)


# ---------------------------------------------------------------------------
# E-mails ao fornecedor (a OS; a ordem bancária)
# ---------------------------------------------------------------------------

def _tela_de_email(request, solicitacao, envio, modelo_assunto, modelo_texto, gerar_anexos, depois):
    """Mostra o e-mail pronto (editável) e, no POST confirmado, envia.

    `envio`: titulo, o_que (como o histórico chama o documento), ja_enviado,
    anexos (nome e url, para a tela), volta, pendencias. `gerar_anexos()`
    devolve [(nome, bytes, tipo)] na hora de enviar; `depois(solicitacao)`
    grava o que o envio conclui (a data) e devolve a mensagem de sucesso.
    """
    from smtplib import SMTPException

    from . import emails

    fornecedor = solicitacao.lote.contrato.fornecedor
    envio.setdefault(
        "url_fornecedor",
        reverse("coffee_break:cadastro_lista", args=["fornecedores"]) + f"?editar={fornecedor.pk}"
        if eh_administrador(request.user) else "",
    )
    valores = emails.rascunho(solicitacao, modelo_assunto, modelo_texto)
    erro = ""
    if request.method == "POST" and not envio["pendencias"]:
        valores = {chave: request.POST.get(chave, "") for chave in ("para", "copia", "assunto", "texto")}
        try:
            anexos = gerar_anexos()
            emails.enviar(
                solicitacao, request.user, anexos=anexos, o_que=envio["o_que"],
                tambem_em=envio.get("tambem_em", ()), **{
                    "para": valores["para"], "copia": valores["copia"],
                    "assunto": valores["assunto"], "texto": valores["texto"],
                },
            )
        except ValidationError as exc:
            erro = " ".join(exc.messages)
        except (SMTPException, OSError) as exc:
            erro = f"O e-mail não foi enviado: o servidor de e-mail recusou ou não respondeu ({exc}). Tente de novo."
        else:
            messages.success(request, depois(solicitacao))
            return redirect(envio["volta"])
    rotulo = solicitacao.numero or f"#{solicitacao.pk}"
    return render(
        request,
        "pages/coffee_break/enviar_email.html",
        {
            "solicitacao": solicitacao,
            "envio": envio,
            "valores": valores,
            "erro": erro,
            "breadcrumb": _breadcrumb(
                {"label": "Solicitações", "url": reverse("coffee_break:solicitacoes")},
                {"label": rotulo, "url": envio["volta"]},
                {"label": envio["titulo"]},
            ),
        },
    )


@acesso_ao_modulo
def enviar_os(request, pk):
    """"Enviar ao fornecedor": a OS em PDF, com o texto padrão, para o e-mail
    do cadastro do fornecedor e cópia para a ASCOM. Grava a data do envio."""
    solicitacao = _solicitacao_documental(pk)
    config = ConfiguracaoCoffeeBreak.atual()
    nome = documentos.nome_arquivo("Ordem de Servico", solicitacao)
    pendencias = list(documentos.pendencias_ordem_servico(solicitacao))
    if solicitacao.cancelada:
        pendencias.insert(0, "A solicitação está cancelada.")
    enviada = solicitacao.data_envio_ordem_servico
    envio = {
        "titulo": f"Enviar a OS {solicitacao.numero} ao fornecedor".replace("  ", " "),
        "o_que": f"Ordem de serviço {solicitacao.numero}".strip(),
        "ja_enviado": f"A OS já foi enviada ao fornecedor em {enviada:%d/%m/%Y}." if enviada else "",
        "anexos": [{"nome": nome, "url": reverse("coffee_break:ordem_servico", args=[solicitacao.pk])}],
        "volta": reverse("coffee_break:editar", args=[solicitacao.pk]),
        "pendencias": pendencias,
    }

    def anexos():
        return [(nome, documentos.ordem_servico_pdf(solicitacao), "application/pdf")]

    def depois(s):
        s.data_envio_ordem_servico = timezone.localdate()
        s.save(update_fields=["data_envio_ordem_servico", "atualizado_em"])
        return f"OS {s.numero} enviada ao fornecedor por e-mail. O envio ficou no histórico."

    return _tela_de_email(request, solicitacao, envio, config.email_os_assunto, config.email_os_texto, anexos, depois)


@acesso_ao_modulo
def enviar_ob(request, pk):
    """"Enviar OB ao fornecedor": o comprovante da ordem bancária por e-mail.
    Enviado, registra o envio à empresa (o último marco) em todas as OS do
    mesmo pagamento, e o pagamento se encerra."""
    solicitacao = _solicitacao_documental(pk)
    config = ConfiguracaoCoffeeBreak.atual()
    arquivo = solicitacao.arquivo_ordem_bancaria
    nome = f"Ordem bancaria {solicitacao.numero_ordem_bancaria or solicitacao.numero}".replace("/", "-").strip() + ".pdf"
    pendencias = []
    if solicitacao.cancelada:
        pendencias.append("A solicitação está cancelada.")
    if not arquivo:
        pendencias.append("Anexe o PDF da ordem bancária na etapa 3.")
    if not solicitacao.data_ordem_bancaria:
        pendencias.append("Registre a data da ordem bancária (o atesto vem antes).")
    grupo = solicitacao.grupo_pagamento()
    outras = [m for m in grupo if m.pk != solicitacao.pk]
    enviada = solicitacao.data_envio_empresa
    os_do_pagamento = ", ".join(m.numero or f"#{m.pk}" for m in grupo)
    envio = {
        "titulo": "Enviar a ordem bancária ao fornecedor",
        "o_que": f"Ordem bancária {solicitacao.numero_ordem_bancaria}".strip()
        + (f" (pagamento das OS {os_do_pagamento})" if outras else ""),
        "ja_enviado": f"A ordem bancária já foi enviada à empresa em {enviada:%d/%m/%Y}." if enviada else "",
        "anexos": [{"nome": nome, "url": reverse("coffee_break:ordem_bancaria_arquivo", args=[solicitacao.pk])}] if arquivo else [],
        "volta": reverse("coffee_break:etapa_protocolo", args=[solicitacao.pk]),
        "pendencias": pendencias,
        "tambem_em": outras,
    }

    def anexos():
        with arquivo.open("rb") as aberto:
            return [(nome, aberto.read(), "application/pdf")]

    def depois(s):
        marco = services.proximo_marco(s)
        if marco and marco["campo"] == "data_envio_empresa":
            services.registrar_marco(s, request.user, timezone.localdate(), "por e-mail, do sistema")
            return "Ordem bancária enviada ao fornecedor. O pagamento foi concluído" + (
                " em todas as OS dele." if outras else "."
            )
        return "Ordem bancária enviada ao fornecedor. O envio ficou no histórico."

    return _tela_de_email(request, solicitacao, envio, config.email_ob_assunto, config.email_ob_texto, anexos, depois)


@require_POST
@acesso_ao_modulo
def anexar_ob(request, pk):
    """O PDF da ordem bancária pelo modal de anexo de documentos (etapa 3):
    lê número, data e valor, guarda em todas as OS do pagamento e registra a
    data da OB quando ela é o próximo marco. Também troca ou remove."""
    from .forms import validar_pdf
    from .ordem_bancaria import dados_da_ob

    solicitacao = get_object_or_404(SolicitacaoCoffeeBreak, pk=pk)
    destino = reverse("coffee_break:etapa_protocolo", args=[pk])
    if solicitacao.bloqueada_para_edicao:
        messages.warning(request, "Solicitações canceladas ou concluídas ficam bloqueadas para edição.")
        return redirect(destino)
    if not solicitacao.numero_nota_fiscal.strip():
        messages.error(request, "Registre a nota fiscal antes da ordem bancária.")
        return redirect(destino)
    if request.POST.get("acao") == "remover":
        if services.remover_ordem_bancaria(solicitacao, request.user):
            messages.success(request, "Ordem bancária removida.")
        return redirect(destino)
    arquivo = request.FILES.get("arquivo")
    if arquivo is None:
        messages.error(request, "Escolha o PDF da ordem bancária.")
        return redirect(destino)
    try:
        validar_pdf(arquivo)
    except ValidationError as erro:
        for mensagem in erro.messages:
            messages.error(request, mensagem)
        return redirect(destino)
    arquivo.seek(0)
    lidos = dados_da_ob(arquivo.read())
    arquivo.seek(0)
    try:
        dia = services.anexar_ordem_bancaria(solicitacao, request.user, arquivo, lidos)
    except ValidationError as erro:
        for mensagem in erro.messages:
            messages.error(request, mensagem)
        return redirect(destino)
    texto = "Ordem bancária anexada"
    if lidos.get("numero"):
        texto += f" — nº {lidos['numero']} lido do PDF"
    if dia:
        texto += f"; OB emitida em {dia:%d/%m/%Y}" + (" (data lida do PDF)" if lidos.get("data") == dia else "")
    elif not solicitacao.data_ordem_bancaria:
        texto += "; registre o atesto para a data da OB entrar"
    messages.success(request, texto + ".")
    solicitacao.refresh_from_db()
    for aviso in services.avisos_da_ob(solicitacao):
        messages.warning(request, aviso)
    return redirect(destino)


@acesso_ao_modulo
def ordem_bancaria_arquivo(request, pk):
    return _arquivo(_solicitacao_documental(pk).arquivo_ordem_bancaria)


@acesso_ao_modulo
def aditivo_arquivo(request, pk):
    from .models import AditivoContrato

    return _arquivo(get_object_or_404(AditivoContrato, pk=pk).arquivo)


def _arquivo(campo, nome=None):
    if not campo:
        raise Http404
    try:
        aberto = campo.open("rb")
    except FileNotFoundError as exc:
        raise Http404 from exc
    return FileResponse(aberto, filename=nome or Path(campo.name).name, as_attachment=False)


@require_POST
@acesso_ao_modulo
def vincular_pagamento(request, pk):
    """Marcar ou desmarcar uma OS na lista "Vincular outra OS" já vincula,
    sem salvar a etapa (JSON para a tela)."""
    solicitacao = get_object_or_404(SolicitacaoCoffeeBreak, pk=pk)
    if solicitacao.bloqueada_para_edicao:
        return JsonResponse({"ok": False, "mensagem": "Solicitações canceladas ou concluídas ficam bloqueadas."}, status=400)
    try:
        services.definir_pagamento_conjunto(solicitacao, request.POST.getlist("vinculadas"), request.user)
    except (ValidationError, ValueError) as erro:
        mensagem = " ".join(erro.messages) if isinstance(erro, ValidationError) else "OS inválida."
        return JsonResponse({"ok": False, "mensagem": mensagem}, status=400)
    return JsonResponse({"ok": True})


@require_POST
@acesso_ao_modulo
def anexar_nota(request, pk):
    """A nota fiscal pelo modal de anexo de documentos (o de Viagens): envia o
    PDF, troca ou remove. Volta para a tela de onde se abriu."""
    from django.utils.http import url_has_allowed_host_and_scheme

    from .forms import validar_pdf

    solicitacao = get_object_or_404(SolicitacaoCoffeeBreak, pk=pk)
    destino = request.POST.get("next") or reverse("coffee_break:etapa_nota", args=[pk])
    if not url_has_allowed_host_and_scheme(destino, allowed_hosts={request.get_host()}, require_https=request.is_secure()):
        destino = reverse("coffee_break:etapa_nota", args=[pk])
    if solicitacao.bloqueada_para_edicao:
        messages.warning(request, "Solicitações canceladas ou concluídas ficam bloqueadas para edição.")
        return redirect(destino)
    if request.POST.get("acao") == "remover":
        if solicitacao.arquivo_nota_fiscal:
            solicitacao.arquivo_nota_fiscal.delete(save=False)
            solicitacao.arquivo_nota_fiscal = None
            # O que foi lido da nota removida não se confere mais.
            solicitacao.valor_nota_fiscal = None
            solicitacao.data_emissao_nf = None
            solicitacao.cnpj_emitente_nf = ""
            solicitacao.save(update_fields=[
                "arquivo_nota_fiscal", "valor_nota_fiscal", "data_emissao_nf", "cnpj_emitente_nf", "atualizado_em",
            ])
            services.registrar_historico(
                solicitacao, request.user, AcaoHistoricoCoffeeBreak.ATUALIZACAO, "Nota fiscal (PDF) removida."
            )
            messages.success(request, "Nota fiscal removida.")
        return redirect(destino)
    arquivo = request.FILES.get("arquivo")
    if arquivo is None:
        messages.error(request, "Escolha o PDF da nota fiscal.")
        return redirect(destino)
    try:
        validar_pdf(arquivo)
    except ValidationError as erro:
        for mensagem in erro.messages:
            messages.error(request, mensagem)
        return redirect(destino)
    from .nota_fiscal import dados_da_nota, numero_da_nota

    # Basta anexar: o número da nota sai do próprio PDF (e, para a
    # conferência, o emitente, o valor e a data de emissão).
    arquivo.seek(0)
    conteudo = arquivo.read()
    numero = numero_da_nota(conteudo)
    lidos = dados_da_nota(conteudo)
    arquivo.seek(0)
    trocou = bool(solicitacao.arquivo_nota_fiscal)
    solicitacao.arquivo_nota_fiscal = arquivo
    solicitacao.valor_nota_fiscal = lidos["valor"]
    solicitacao.data_emissao_nf = lidos["emissao"]
    solicitacao.cnpj_emitente_nf = lidos["cnpj"]
    campos = ["arquivo_nota_fiscal", "valor_nota_fiscal", "data_emissao_nf", "cnpj_emitente_nf", "atualizado_em"]
    if numero:
        solicitacao.numero_nota_fiscal = numero
        campos.append("numero_nota_fiscal")
    solicitacao.save(update_fields=campos)
    services.registrar_historico(
        solicitacao, request.user, AcaoHistoricoCoffeeBreak.ATUALIZACAO,
        ("Nota fiscal (PDF) substituída" if trocou else "Nota fiscal (PDF) anexada")
        + (f"; número {numero} lido do PDF." if numero else "."),
    )
    if numero:
        messages.success(request, f"Nota fiscal {numero} anexada — o número foi lido do PDF.")
    else:
        messages.warning(request, "Nota fiscal anexada, mas não deu para ler o número no PDF: informe-o no campo ao lado.")
    # Conferência: fornecedor, valor, data e duplicidade (só avisa).
    for aviso in services.avisos_da_nota(solicitacao):
        messages.warning(request, aviso)
    return redirect(destino)


@acesso_ao_modulo
def nota_fiscal(request, pk):
    solicitacao = _solicitacao_documental(pk)
    return _arquivo(solicitacao.arquivo_nota_fiscal)


@acesso_ao_modulo
def contrato_arquivo(request, pk, campo):
    if campo not in ("arquivo_contrato", "arquivo_termo_aditivo"):
        raise Http404
    contrato = get_object_or_404(ContratoCoffeeBreak, pk=pk)
    return _arquivo(getattr(contrato, campo))


# ---------------------------------------------------------------------------
# Certidões dos fornecedores
# ---------------------------------------------------------------------------

def _fornecedores_com_lote_ativo():
    return Fornecedor.objects.filter(
        contratos__lotes__ativo=True
    ).distinct().prefetch_related("certidoes")


@require_GET
@acesso_ao_modulo
def lista_certidoes(request):
    """O quadro das certidões. Anexar é só pelo modal (anexar_certidao),
    que confere se o PDF é a certidão certa, do CNPJ do fornecedor."""
    hoje = timezone.localdate()
    fornecedores = [
        {"fornecedor": f, "linhas": certidoes.quadro(f, hoje)}
        for f in _fornecedores_com_lote_ativo()
    ]
    return render(
        request,
        "pages/coffee_break/certidoes.html",
        {
            "breadcrumb": _breadcrumb({"label": "Certidões"}),
            "fornecedores": fornecedores,
            "dias_aviso": certidoes.DIAS_AVISO,
            "usa_dialogo_assinado": True,
        },
    )


@require_POST
@gerenciamento_de_cadastros
def anexar_contrato(request):
    """Contrato ou termo aditivo pelo modal de anexo de documentos: basta
    anexar o PDF. O sistema diz o que ele é, confere de quem é (o CNPJ do
    contratado) e preenche tudo — fornecedor, número, GMS, aditivo, lote,
    quantidade, valores e vigência (coffee_break/contratos_pdf.py)."""
    from . import contratos_pdf
    from .forms import validar_pdf

    destino = reverse("coffee_break:cadastro_lista", args=["contratos"])
    arquivo = request.FILES.get("arquivo")
    if arquivo is None:
        messages.error(request, "Escolha o PDF do contrato ou do termo aditivo.")
        return redirect(destino)
    try:
        validar_pdf(arquivo)
    except ValidationError as erro:
        for mensagem in erro.messages:
            messages.error(request, mensagem)
        return redirect(destino)
    arquivo.seek(0)
    dados = contratos_pdf.ler(contratos_pdf.texto_do_pdf(arquivo.read()))
    arquivo.seek(0)
    if not dados.get("tipo") or not dados.get("numero"):
        messages.error(request, "Este PDF não parece ser um contrato nem um termo aditivo da SESP (não achei o número do contrato).")
        return redirect(destino)
    if not dados.get("cnpj"):
        messages.error(request, f"Não achei o CNPJ do contratado no documento do contrato {dados['numero']}.")
        return redirect(destino)
    with transaction.atomic():
        fornecedor = Fornecedor.objects.filter(cnpj=dados["cnpj"]).first()
        if fornecedor is None:
            fornecedor = Fornecedor.objects.create(razao_social=dados.get("razao_social") or dados["cnpj"], cnpj=dados["cnpj"])
        contrato = ContratoCoffeeBreak.objects.select_for_update().filter(numero=dados["numero"]).first()
        if contrato and contrato.fornecedor_id != fornecedor.pk:
            messages.error(
                request,
                f"O contrato {contrato.numero} está cadastrado para {contrato.fornecedor.razao_social}, "
                f"mas este documento é de {fornecedor.razao_social}.",
            )
            return redirect(destino)
        novo = contrato is None
        if novo:
            contrato = ContratoCoffeeBreak(fornecedor=fornecedor, numero=dados["numero"])
        contrato.numero_gms = dados.get("numero_gms") or contrato.numero_gms
        for campo, chave in (("quantidade_contratada", "quantidade"), ("valor_unitario", "valor_unitario"), ("valor_total", "valor_total")):
            if dados.get(chave) is not None:
                setattr(contrato, campo, dados[chave])
        # A vigência escrita (do aditivo) vale sobre a estimada; entre duas, a mais longa.
        fim = dados.get("vigencia_fim")
        if fim and (
            not contrato.vigencia_fim
            or (contrato.vigencia_estimada and not dados.get("vigencia_estimada"))
            or (fim > contrato.vigencia_fim and not (dados.get("vigencia_estimada") and not contrato.vigencia_estimada))
        ):
            contrato.vigencia_inicio = dados.get("vigencia_inicio")
            contrato.vigencia_fim = fim
            contrato.vigencia_estimada = bool(dados.get("vigencia_estimada"))
        if dados["tipo"] != "aditivo":
            contrato.arquivo_contrato = arquivo
        contrato.save()
        if dados["tipo"] == "aditivo":
            # Todos os aditivos ficam (o anexo leva todos); o contrato cita o de vigência mais longa.
            from .models import AditivoContrato

            aditivo, _ = AditivoContrato.objects.update_or_create(
                contrato=contrato, numero=dados["termo_aditivo"],
                defaults={"vigencia_inicio": dados.get("vigencia_inicio"), "vigencia_fim": dados.get("vigencia_fim")},
            )
            aditivo.arquivo = arquivo
            aditivo.save()
            vigente = contrato.aditivos.order_by("-vigencia_fim", "-criado_em").first()
            contrato.termo_aditivo = vigente.numero
            contrato.arquivo_termo_aditivo = vigente.arquivo.name
            contrato.save(update_fields=["termo_aditivo", "arquivo_termo_aditivo", "atualizado_em"])
        # Sem lote ainda: nasce o do documento (número e quantidade); os municípios se escolhem no lote.
        lote_criado = None
        if not contrato.lotes.exists() and dados.get("numero_lote") and dados.get("quantidade"):
            ano = (contrato.vigencia_inicio or timezone.localdate()).year
            lote_criado = LoteCoffeeBreak.objects.create(
                contrato=contrato, numero=dados["numero_lote"], exercicio=str(ano), quantidade_total=dados["quantidade"],
            )
    o_que = f"Termo aditivo {contrato.termo_aditivo} do contrato {contrato.numero}" if dados["tipo"] == "aditivo" else f"Contrato {contrato.numero}"
    partes = [f"{o_que} ({fornecedor.razao_social}) anexado e conferido"]
    if contrato.vigencia_fim:
        partes.append(
            f"vigente até {contrato.vigencia_fim:%d/%m/%Y}" + (" (estimada pelo prazo; o termo aditivo confirma)" if contrato.vigencia_estimada else "")
        )
    if contrato.quantidade_contratada:
        partes.append(f"{contrato.quantidade_contratada:,} unidades".replace(",", "."))
    if lote_criado:
        partes.append(f"lote {lote_criado.numero} criado — escolha os municípios dele em Lotes")
    vencido = contrato.vigencia_fim and contrato.vigencia_fim < timezone.localdate()
    (messages.warning if vencido else messages.success)(request, "; ".join(partes) + ".")
    return redirect(destino)


@require_POST
@acesso_ao_modulo
def anexar_certidao(request, fornecedor_pk, tipo):
    """A certidão pelo modal de anexo de documentos: basta anexar o PDF. O
    sistema confere se é a certidão certa, do CNPJ do fornecedor, e lê até
    quando vale (PDF só de imagem: vale a data informada no modal)."""
    from datetime import date

    from .forms import validar_pdf

    fornecedor = get_object_or_404(Fornecedor, pk=fornecedor_pk)
    if tipo not in TipoCertidao.values:
        raise Http404
    rotulo = dict(TipoCertidao.choices)[tipo]
    destino = f"{reverse('coffee_break:certidoes')}#fornecedor-{fornecedor.pk}"
    arquivo = request.FILES.get("arquivo")
    if arquivo is None:
        messages.error(request, "Escolha o PDF da certidão.")
        return redirect(destino)
    informada = None
    try:
        informada = date.fromisoformat(request.POST.get("validade") or "") if request.POST.get("validade") else None
    except ValueError:
        messages.error(request, "Data de validade inválida.")
        return redirect(destino)
    try:
        validar_pdf(arquivo)
        validade, aviso = certidoes.conferir(fornecedor, tipo, arquivo, informada)
    except ValidationError as erro:
        for mensagem in erro.messages:
            messages.error(request, f"Certidão {rotulo}: {mensagem}")
        return redirect(destino)
    certidao = certidoes.registrar(fornecedor, tipo, arquivo, validade, request.user)
    situacao = "vencida em" if validade < timezone.localdate() else "válida até"
    texto = f"Certidão {rotulo} de {fornecedor.razao_social} conferida e anexada — {situacao} {certidao.validade:%d/%m/%Y}."
    if aviso:
        messages.warning(request, f"{texto} {aviso}")
    elif validade < timezone.localdate():
        messages.warning(request, texto)
    else:
        messages.success(request, texto)
    return redirect(destino)


@acesso_ao_modulo
def certidao_arquivo(request, pk):
    certidao = get_object_or_404(CertidaoFornecedor, pk=pk)
    return _arquivo(certidao.arquivo)
