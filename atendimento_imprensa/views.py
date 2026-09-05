"""Views do módulo de Atendimento à Imprensa da ASCOM.

Todas as rotas exigem o módulo ASCOM_ATENDIMENTO_IMPRENSA (decorator +
middleware). As telas seguem o Design System V3.2 (shell `app_shell_v32`),
espelhando as telas de Solicitações do módulo Eventos Sociais.
"""

import csv
import datetime as dt

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.db.models import Count, Q
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.dateformat import format as formatar_data
from django.views.decorators.http import require_POST

from core.listagens import (
    campos_formulario,
    colunas_ordenaveis,
    opcoes,
    opcoes_choices,
    ordenacao,
    paginar,
    valores_filtro,
)

from . import services
from .forms import (
    AtendimentoForm,
    FiltroAtendimentosForm,
    ResponsavelForm,
    VeiculoForm,
)
from .models import (
    SITUACOES_ABERTAS,
    Atendimento,
    Responsavel,
    SituacaoAtendimento,
    Veiculo,
)
from .permissions import acesso_ao_modulo, gerenciamento_de_cadastros

KICKER = "Atendimento à Imprensa"

FILAS = [
    ("abertos", "Em aberto", list(SITUACOES_ABERTAS)),
    ("aguardando", "Aguardando fonte", [SituacaoAtendimento.AGUARDANDO_FONTE]),
    ("atendidos", "Atendidos", [SituacaoAtendimento.ATENDIDO]),
    ("nao_responder", "Não responder", [SituacaoAtendimento.NAO_RESPONDER]),
]

ORDENACOES = {
    "data": ["data", "horario", "pk"],
    "jornalista": ["jornalista", "-data"],
    "veiculo": ["veiculo__nome", "-data"],
    "situacao": ["situacao", "-data"],
    "responsavel": ["responsavel__nome", "-data"],
    "deadline": ["deadline", "-data"],
}

COLUNAS = [
    ("data", "Data", "c-data"),
    ("situacao", "Situação", "c-status"),
    ("jornalista", "Jornalista", "c-sol"),
    ("veiculo", "Veículo", "c-tipo"),
    ("pedido", "Pedido", "c-pedido"),
    ("responsavel", "Responsável", "c-mun"),
    ("deadline", "Deadline", "c-per"),
]

ORDENACOES_MOBILE = [
    {"valor": "-data", "rotulo": "Mais recentes"},
    {"valor": "data", "rotulo": "Mais antigos"},
    {"valor": "deadline", "rotulo": "Deadline mais próximo"},
    {"valor": "jornalista", "rotulo": "Jornalista (A–Z)"},
    {"valor": "veiculo", "rotulo": "Veículo (A–Z)"},
]

CAMPOS_FILTRO = ["q", "situacao", "veiculo", "responsavel", "inicio", "fim"]


def _opcoes_situacao():
    return opcoes_choices(SituacaoAtendimento.choices)


# ---------------------------------------------------------------------------
# Painel
# ---------------------------------------------------------------------------

@acesso_ao_modulo
def painel(request):
    hoje = timezone.localdate()
    inicio_mes = services.inicio_do_mes(hoje)
    mes = services.resumo_periodo(inicio_mes)
    abertos = services.em_aberto().count()
    vencidos = services.deadline_vencido(hoje).count()
    url_lista = reverse("atendimento_imprensa:lista")

    resumo = [
        {
            "titulo": "Pedidos no mês",
            "valor": mes["total"],
            "icone": "mail",
            "variacao": formatar_data(hoje, r"F \d\e Y"),
            "url": f"{url_lista}?inicio={inicio_mes:%Y-%m-%d}",
        },
        {
            "titulo": "Atendidos no mês",
            "valor": mes["atendidos"],
            "icone": "check-circle",
            "variacao": (
                f"{round(mes['atendidos'] * 100 / mes['total'])}% dos pedidos"
                if mes["total"]
                else "Nenhum pedido ainda"
            ),
            "url": f"{url_lista}?fila=atendidos&inicio={inicio_mes:%Y-%m-%d}",
        },
        {
            "titulo": "Em aberto",
            "valor": abertos,
            "icone": "hourglass",
            "destaque": abertos > 0,
            "variacao": "Em andamento ou aguardando fonte",
            "url": f"{url_lista}?fila=abertos",
        },
        {
            "titulo": "Deadline vencido",
            "valor": vencidos,
            "icone": "alert",
            "destaque": vencidos > 0,
            "variacao": "Em aberto com prazo já passado",
            "url": f"{url_lista}?fila=abertos&ordem=deadline",
        },
    ]

    recentes = Atendimento.objects.select_related("veiculo", "responsavel").order_by(
        "-data", "-horario", "-pk"
    )[:8]
    pendentes = (
        services.em_aberto()
        .select_related("veiculo", "responsavel")
        .order_by("deadline", "data", "horario")[:8]
    )
    return render(
        request,
        "pages/atendimento_imprensa/painel.html",
        {
            "kicker": KICKER,
            "resumo": resumo,
            "mes": mes,
            "mes_rotulo": formatar_data(hoje, "F/Y").lower(),
            "por_veiculo": services.por_veiculo(inicio_mes),
            "por_responsavel": services.por_responsavel(inicio_mes),
            "grafico": services.serie_mensal(6, hoje),
            "recentes": recentes,
            "pendentes": pendentes,
            "hoje": hoje,
            "url_lista": url_lista,
        },
    )


# ---------------------------------------------------------------------------
# Listagem e exportação
# ---------------------------------------------------------------------------

def _filtrar(request):
    filtros = FiltroAtendimentosForm(request.GET or None)
    pedido, campos_ordem = ordenacao(request, ORDENACOES, "-data")
    queryset = Atendimento.objects.select_related(
        "veiculo", "responsavel", "responsavel_resposta"
    ).order_by(*campos_ordem)

    fila_ativa = request.GET.get("fila", "")
    for chave, _rotulo, situacoes in FILAS:
        if chave == fila_ativa:
            queryset = queryset.filter(situacao__in=situacoes)
            break
    else:
        fila_ativa = ""

    if filtros.is_valid():
        dados = filtros.cleaned_data
        if dados.get("q"):
            termo = dados["q"]
            queryset = queryset.filter(
                Q(jornalista__icontains=termo)
                | Q(pedido__icontains=termo)
                | Q(contato__icontains=termo)
                | Q(fonte__icontains=termo)
                | Q(resposta__icontains=termo)
                | Q(veiculo__nome__icontains=termo)
            )
        if dados.get("situacao"):
            queryset = queryset.filter(situacao=dados["situacao"])
        if dados.get("veiculo"):
            queryset = queryset.filter(veiculo=dados["veiculo"])
        if dados.get("responsavel"):
            queryset = queryset.filter(
                Q(responsavel=dados["responsavel"])
                | Q(responsavel_resposta=dados["responsavel"])
            )
        if dados.get("inicio"):
            queryset = queryset.filter(data__gte=dados["inicio"])
        if dados.get("fim"):
            queryset = queryset.filter(data__lte=dados["fim"])
    return queryset, filtros, pedido, fila_ativa


@acesso_ao_modulo
def lista(request):
    queryset, filtros, pedido, fila_ativa = _filtrar(request)
    pagina, paginas_visiveis, querystring = paginar(request, queryset)
    contagens = dict(
        Atendimento.objects.values_list("situacao").annotate(total=Count("pk"))
    )
    filas = [
        {
            "chave": chave,
            "rotulo": rotulo,
            "total": sum(contagens.get(s, 0) for s in situacoes),
            "destaque": chave == "abertos",
        }
        for chave, rotulo, situacoes in FILAS
    ]
    filtros_ativos = sum(1 for nome in CAMPOS_FILTRO if request.GET.get(nome))
    return render(
        request,
        "pages/atendimento_imprensa/lista.html",
        {
            "kicker": KICKER,
            "pagina": pagina,
            "linhas": pagina.object_list,
            "paginas_visiveis": paginas_visiveis,
            "elipse": Paginator.ELLIPSIS,
            "querystring": querystring,
            "colunas": colunas_ordenaveis(request, pedido, COLUNAS, ORDENACOES),
            "ordem_atual": pedido,
            "ordenacoes_mobile": ORDENACOES_MOBILE,
            "valores_filtro": valores_filtro(filtros),
            "opcoes_situacao": _opcoes_situacao(),
            "opcoes_veiculos": opcoes(Veiculo.objects.filter(ativo=True)),
            "opcoes_responsaveis": opcoes(Responsavel.objects.filter(ativo=True)),
            "filas": filas,
            "fila_ativa": fila_ativa,
            "total_geral": sum(contagens.values()),
            "total_resultados": pagina.paginator.count,
            "tem_filtros": filtros_ativos > 0,
            "filtros_ativos": filtros_ativos,
            "hoje": timezone.localdate(),
        },
    )


@acesso_ao_modulo
def exportar(request):
    queryset, _filtros, _pedido, _fila = _filtrar(request)
    resposta = HttpResponse(content_type="text/csv; charset=utf-8")
    resposta["Content-Disposition"] = (
        f'attachment; filename="atendimento-imprensa-{timezone.localdate():%Y-%m-%d}.csv"'
    )
    resposta.write("﻿")
    escritor = csv.writer(resposta, delimiter=";", lineterminator="\r\n")
    escritor.writerow(
        [
            "Data", "Horário", "Jornalista", "Veículo", "Contato", "Pedido",
            "Situação", "Responsável", "Deadline / veiculação",
            "Horário da resposta", "Responsável pela resposta", "Fontes",
            "Início do pedido", "Retorno das fontes", "Andamento", "Resposta",
        ]
    )
    for a in queryset:
        escritor.writerow(
            [
                a.data.strftime("%d/%m/%Y"),
                a.horario.strftime("%H:%M") if a.horario else "",
                a.jornalista,
                a.veiculo.nome if a.veiculo else "",
                a.contato,
                a.pedido,
                a.get_situacao_display(),
                a.responsavel.nome if a.responsavel else "",
                a.deadline.strftime("%d/%m/%Y") if a.deadline else "",
                a.horario_resposta.strftime("%H:%M") if a.horario_resposta else "",
                a.responsavel_resposta.nome if a.responsavel_resposta else "",
                a.fonte,
                a.inicio_pedido,
                a.final_pedido,
                a.andamento,
                a.resposta,
            ]
        )
    return resposta


# ---------------------------------------------------------------------------
# Formulário e detalhe
# ---------------------------------------------------------------------------

def _valores(form):
    valores = {}
    for nome in form.fields:
        valor = form[nome].value()
        if isinstance(valor, dt.time):
            valor = valor.strftime("%H:%M")
        valores[nome] = "" if valor is None else str(valor)
    return valores


def _contexto_formulario(form, atendimento=None):
    return {
        "kicker": KICKER,
        "form": form,
        "atendimento": atendimento,
        "erros": form.errors,
        "erros_gerais": form.non_field_errors(),
        "valores": _valores(form),
        "opcoes_veiculos": opcoes(form.fields["veiculo"].queryset),
        "opcoes_responsaveis": opcoes(form.fields["responsavel"].queryset),
        "opcoes_situacao": _opcoes_situacao(),
        "jornalistas_sugeridos": list(
            Atendimento.objects.order_by("jornalista")
            .values_list("jornalista", flat=True)
            .distinct()[:400]
        ),
    }


def _salvar(request, form):
    atendimento = form.save(commit=False)
    if not atendimento.pk:
        atendimento.criado_por = request.user
    atendimento.full_clean()
    atendimento.save()
    return atendimento


@acesso_ao_modulo
def novo(request):
    if request.method == "POST":
        form = AtendimentoForm(request.POST)
        if form.is_valid():
            try:
                atendimento = _salvar(request, form)
            except ValidationError as erro:
                for campo, mensagens in erro.message_dict.items():
                    for mensagem in mensagens:
                        form.add_error(campo if campo in form.fields else None, mensagem)
            else:
                messages.success(request, "Atendimento registrado.")
                return redirect("atendimento_imprensa:detalhe", pk=atendimento.pk)
        messages.error(request, "Corrija os campos destacados para continuar.")
    else:
        agora = timezone.localtime()
        form = AtendimentoForm(
            initial={"data": agora.date(), "horario": agora.time().replace(second=0, microsecond=0)}
        )
    contexto = _contexto_formulario(form)
    contexto["titulo_pagina"] = "Novo atendimento"
    return render(request, "pages/atendimento_imprensa/form.html", contexto)


@acesso_ao_modulo
def editar(request, pk):
    atendimento = get_object_or_404(Atendimento, pk=pk)
    if request.method == "POST":
        form = AtendimentoForm(request.POST, instance=atendimento)
        if form.is_valid():
            try:
                atendimento = _salvar(request, form)
            except ValidationError as erro:
                for campo, mensagens in erro.message_dict.items():
                    for mensagem in mensagens:
                        form.add_error(campo if campo in form.fields else None, mensagem)
            else:
                messages.success(request, "Atendimento atualizado.")
                return redirect("atendimento_imprensa:detalhe", pk=atendimento.pk)
        messages.error(request, "Corrija os campos destacados para continuar.")
    else:
        form = AtendimentoForm(instance=atendimento)
    contexto = _contexto_formulario(form, atendimento)
    contexto["titulo_pagina"] = f"Editar atendimento #{atendimento.pk}"
    return render(request, "pages/atendimento_imprensa/form.html", contexto)


@acesso_ao_modulo
def detalhe(request, pk):
    atendimento = get_object_or_404(
        Atendimento.objects.select_related(
            "veiculo", "responsavel", "responsavel_resposta", "criado_por"
        ),
        pk=pk,
    )
    hoje = timezone.localdate()
    etapas = [
        {
            "titulo": "Pedido recebido",
            "subtitulo": f"{atendimento.data:%d/%m/%Y}"
            + (f" · {atendimento.horario:%H:%M}" if atendimento.horario else ""),
            "estado": "concluido",
        },
        {
            "titulo": "Fontes consultadas",
            "subtitulo": (
                f"{len(atendimento.fontes_alinhadas)} fonte"
                f"{'s' if len(atendimento.fontes_alinhadas) != 1 else ''} acionada"
                f"{'s' if len(atendimento.fontes_alinhadas) != 1 else ''}"
                if atendimento.fonte
                else "Nenhuma fonte registrada"
            ),
            "estado": "concluido" if atendimento.fonte else "pendente",
        },
        {
            "titulo": "Resposta enviada",
            "subtitulo": (
                (f"{atendimento.horario_resposta:%H:%M}" if atendimento.horario_resposta else "Horário não registrado")
                + (f" · {atendimento.responsavel_resposta}" if atendimento.responsavel_resposta else "")
                if atendimento.atendido
                else atendimento.get_situacao_display()
            ),
            "estado": "concluido" if atendimento.atendido else (
                "cancelado" if atendimento.situacao == SituacaoAtendimento.NAO_RESPONDER else "pendente"
            ),
        },
    ]
    return render(
        request,
        "pages/atendimento_imprensa/detalhe.html",
        {
            "kicker": KICKER,
            "atendimento": atendimento,
            "titulo_pagina": f"Atendimento #{atendimento.pk}",
            "etapas": etapas,
            "fontes": atendimento.fontes_alinhadas,
            "deadline_vencido": bool(
                atendimento.aberto and atendimento.deadline and atendimento.deadline < hoje
            ),
        },
    )


# ---------------------------------------------------------------------------
# Cadastros de apoio (administradores)
# ---------------------------------------------------------------------------

CADASTROS = {
    "equipe": {
        "model": Responsavel,
        "form": ResponsavelForm,
        "titulo": "Equipe",
        "singular": "integrante",
        "genitivo": "do integrante",
        "novo": "Novo integrante",
        "exemplo": "Ex.: Mariana",
        "icone": "users",
        "intro": "Nome curto usado nas colunas de responsável pelo atendimento e pela resposta.",
    },
    "veiculos": {
        "model": Veiculo,
        "form": VeiculoForm,
        "titulo": "Veículos",
        "singular": "veículo",
        "genitivo": "do veículo",
        "novo": "Novo veículo",
        "exemplo": "Ex.: RPC",
        "icone": "mail",
        "intro": "Veículo de imprensa que fez o pedido (TV, rádio, portal, jornal).",
    },
}


def _config_cadastro(tipo):
    config = CADASTROS.get(tipo)
    if not config:
        raise Http404
    return config


def _grupos():
    return [
        {
            "slug": slug,
            "titulo": config["titulo"],
            "total": config["model"].objects.count(),
            "icone": config["icone"],
            "url": reverse("atendimento_imprensa:cadastro_lista", args=[slug]),
        }
        for slug, config in CADASTROS.items()
    ]


def _contexto_cadastros(tipo, config):
    return {
        "kicker": KICKER,
        "modulo_titulo": "Atendimento à Imprensa",
        "modulo_sub": "Tabelas de apoio usadas no registro dos atendimentos.",
        "slug": tipo,
        "titulo": config["titulo"],
        "singular": config["singular"],
        "genitivo": config["genitivo"],
        "novo": config["novo"],
        "exemplo": config["exemplo"],
        "grupos": _grupos(),
        "url_lista": "atendimento_imprensa:cadastro_lista",
        "url_novo": "atendimento_imprensa:cadastro_novo",
        "url_editar": "atendimento_imprensa:cadastro_editar",
        "url_alternar": "atendimento_imprensa:cadastro_alternar",
    }


@gerenciamento_de_cadastros
def cadastros(request):
    return redirect("atendimento_imprensa:cadastro_lista", tipo="equipe")


@gerenciamento_de_cadastros
def lista_cadastro(request, tipo):
    config = _config_cadastro(tipo)
    queryset = config["model"].objects.all()
    termo = request.GET.get("q", "").strip()
    if termo:
        queryset = queryset.filter(nome__icontains=termo)
    situacao = request.GET.get("situacao", "").strip()
    if situacao == "ativos":
        queryset = queryset.filter(ativo=True)
    elif situacao == "inativos":
        queryset = queryset.filter(ativo=False)
    pagina, paginas_visiveis, querystring = paginar(request, queryset)
    contexto = _contexto_cadastros(tipo, config)
    contexto.update(
        {
            "total_registros": config["model"].objects.count(),
            "total_ativos": config["model"].objects.filter(ativo=True).count(),
            "pagina": pagina,
            "paginas_visiveis": paginas_visiveis,
            "elipse": Paginator.ELLIPSIS,
            "querystring": querystring,
            "termo": termo,
            "situacao": situacao,
            "tem_filtros": bool(termo or situacao),
            "opcoes_situacao": [
                {"valor": "ativos", "rotulo": "Ativos"},
                {"valor": "inativos", "rotulo": "Inativos"},
            ],
        }
    )
    return render(request, "pages/ascom_cadastros/lista.html", contexto)


@gerenciamento_de_cadastros
def editar_cadastro(request, tipo, pk=None):
    config = _config_cadastro(tipo)
    instancia = get_object_or_404(config["model"], pk=pk) if pk else None
    if request.method == "POST":
        form = config["form"](request.POST, instance=instancia)
        if form.is_valid():
            form.save()
            messages.success(request, f"{config['titulo']}: registro salvo com sucesso.")
            return redirect("atendimento_imprensa:cadastro_lista", tipo=tipo)
        messages.error(request, "Corrija os campos destacados para continuar.")
    else:
        form = config["form"](instance=instancia)
    campos = campos_formulario(form)
    erros_gerais = list(form.non_field_errors())
    contexto = _contexto_cadastros(tipo, config)
    contexto.update(
        {
            "instancia": instancia,
            "form": form,
            "campos": campos,
            "erros_gerais": erros_gerais,
            "erros_total": sum(1 for c in campos if c["erros"]) + len(erros_gerais),
            "cartao_titulo": f"Editar {config['singular']}" if pk else config["novo"],
            "cartao_intro": config["intro"],
        }
    )
    return render(request, "pages/ascom_cadastros/form.html", contexto)


@gerenciamento_de_cadastros
@require_POST
def alternar_cadastro(request, tipo, pk):
    config = _config_cadastro(tipo)
    objeto = get_object_or_404(config["model"], pk=pk)
    objeto.ativo = not objeto.ativo
    objeto.save(update_fields=["ativo", "atualizado_em"])
    messages.success(
        request, f"{objeto.nome} {'ativado' if objeto.ativo else 'inativado'}."
    )
    return redirect("atendimento_imprensa:cadastro_lista", tipo=tipo)
