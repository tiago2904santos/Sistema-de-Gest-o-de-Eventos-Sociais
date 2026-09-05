"""Views do módulo de Publicações da ASCOM.

Todas as rotas exigem o módulo ASCOM_PUBLICACOES (decorator + middleware).
As telas seguem o Design System V3.2 (shell `app_shell_v32`).
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
    FiltroPublicacoesForm,
    PublicacaoForm,
    ResponsavelForm,
    UnidadeForm,
)
from .models import (
    CSS_STATUS_PUBLICACAO,
    Publicacao,
    Responsavel,
    StatusPublicacao,
    Unidade,
)
from .permissions import acesso_ao_modulo, gerenciamento_de_cadastros

KICKER = "Publicações"

FILAS = [
    ("pendentes", "Pendentes", [StatusPublicacao.PENDENTE]),
    ("andamento", "Em andamento", [StatusPublicacao.EM_ANDAMENTO]),
    ("publicadas", "Publicadas", [StatusPublicacao.PUBLICADA]),
    ("canceladas", "Canceladas", [StatusPublicacao.CANCELADA]),
]

ORDENACOES = {
    "data": ["data", "inicio_pauta", "pk"],
    "titulo": ["titulo", "-data"],
    "jornalista": ["jornalista__nome", "-data"],
    "unidade": ["unidade__nome", "-data"],
    "status": ["status", "-data"],
    "publicacao": ["data_publicacao", "horario_publicacao", "-pk"],
}

COLUNAS = [
    ("data", "Data", "c-data"),
    ("status", "Status", "c-status"),
    ("titulo", "Título", "c-sol"),
    ("unidade", "Unidade", "c-mun"),
    ("jornalista", "Jornalista", "c-tipo"),
    ("publicacao", "Publicada em", "c-per"),
]

ORDENACOES_MOBILE = [
    {"valor": "-data", "rotulo": "Mais recentes"},
    {"valor": "data", "rotulo": "Mais antigas"},
    {"valor": "titulo", "rotulo": "Título (A–Z)"},
    {"valor": "unidade", "rotulo": "Unidade (A–Z)"},
    {"valor": "-publicacao", "rotulo": "Publicadas por último"},
]

CAMPOS_FILTRO = ["q", "status", "jornalista", "unidade", "inicio", "fim"]


def _opcoes_status():
    return opcoes_choices(StatusPublicacao.choices)


# ---------------------------------------------------------------------------
# Painel
# ---------------------------------------------------------------------------

@acesso_ao_modulo
def painel(request):
    hoje = timezone.localdate()
    inicio_mes = services.inicio_do_mes(hoje)
    mes = services.resumo_periodo(inicio_mes)
    abertas = services.em_aberto().count()
    tempo_medio, amostra = services.tempo_medio_display(inicio_mes)
    url_lista = reverse("publicacoes:lista")

    resumo = [
        {
            "titulo": "Pautas no mês",
            "valor": mes["total"],
            "icone": "document",
            "variacao": formatar_data(hoje, r"F \d\e Y"),
            "url": f"{url_lista}?inicio={inicio_mes:%Y-%m-%d}",
        },
        {
            "titulo": "Publicadas no mês",
            "valor": mes["publicadas"],
            "icone": "check-circle",
            "variacao": (
                f"{round(mes['publicadas'] * 100 / mes['total'])}% das pautas"
                if mes["total"]
                else "Nenhuma pauta ainda"
            ),
            "url": f"{url_lista}?fila=publicadas&inicio={inicio_mes:%Y-%m-%d}",
        },
        {
            "titulo": "Em aberto",
            "valor": abertas,
            "icone": "hourglass",
            "destaque": abertas > 0,
            "variacao": "Pendentes ou em andamento",
            "url": f"{url_lista}?fila=pendentes",
        },
        {
            "titulo": "Tempo médio até publicar",
            "valor": tempo_medio,
            "icone": "clock",
            "variacao": (
                f"{amostra} pauta{'s' if amostra != 1 else ''} com horários no mês"
                if amostra
                else "Sem horários registrados no mês"
            ),
            "url": f"{url_lista}?fila=publicadas",
        },
    ]

    recentes = Publicacao.objects.select_related("jornalista", "unidade").order_by(
        "-data", "-inicio_pauta", "-pk"
    )[:8]
    return render(
        request,
        "pages/publicacoes/painel.html",
        {
            "kicker": KICKER,
            "resumo": resumo,
            "mes": mes,
            "mes_rotulo": formatar_data(hoje, "F/Y").lower(),
            "por_jornalista": services.por_jornalista(inicio_mes),
            "por_unidade": services.por_unidade(inicio_mes),
            "grafico": services.serie_mensal(6, hoje),
            "recentes": recentes,
            "url_lista": url_lista,
        },
    )


# ---------------------------------------------------------------------------
# Listagem e exportação
# ---------------------------------------------------------------------------

def _filtrar(request):
    filtros = FiltroPublicacoesForm(request.GET or None)
    pedido, campos_ordem = ordenacao(request, ORDENACOES, "-data")
    queryset = Publicacao.objects.select_related(
        "jornalista", "unidade", "revisao", "galeria_fotos"
    ).order_by(*campos_ordem)

    fila_ativa = request.GET.get("fila", "")
    for chave, _rotulo, statuses in FILAS:
        if chave == fila_ativa:
            queryset = queryset.filter(status__in=statuses)
            break
    else:
        fila_ativa = ""

    if filtros.is_valid():
        dados = filtros.cleaned_data
        if dados.get("q"):
            termo = dados["q"]
            queryset = queryset.filter(
                Q(titulo__icontains=termo)
                | Q(fonte__icontains=termo)
                | Q(unidade__nome__icontains=termo)
                | Q(andamento__icontains=termo)
                | Q(link_site__icontains=termo)
            )
        if dados.get("status"):
            queryset = queryset.filter(status=dados["status"])
        if dados.get("jornalista"):
            queryset = queryset.filter(jornalista=dados["jornalista"])
        if dados.get("unidade"):
            queryset = queryset.filter(unidade=dados["unidade"])
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
        Publicacao.objects.values_list("status").annotate(total=Count("pk"))
    )
    filas = [
        {
            "chave": chave,
            "rotulo": rotulo,
            "total": sum(contagens.get(s, 0) for s in statuses),
            "destaque": chave == "pendentes",
        }
        for chave, rotulo, statuses in FILAS
    ]
    valores = valores_filtro(filtros)
    filtros_ativos = sum(1 for nome in CAMPOS_FILTRO if request.GET.get(nome))
    return render(
        request,
        "pages/publicacoes/lista.html",
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
            "valores_filtro": valores,
            "opcoes_status": _opcoes_status(),
            "opcoes_jornalistas": opcoes(Responsavel.objects.filter(ativo=True)),
            "opcoes_unidades": opcoes(Unidade.objects.filter(ativo=True)),
            "filas": filas,
            "fila_ativa": fila_ativa,
            "total_geral": sum(contagens.values()),
            "total_resultados": pagina.paginator.count,
            "tem_filtros": filtros_ativos > 0,
            "filtros_ativos": filtros_ativos,
        },
    )


def _sim_nao(valor):
    if valor is None:
        return ""
    return "Sim" if valor else "Não"


@acesso_ao_modulo
def exportar(request):
    queryset, _filtros, _pedido, _fila = _filtrar(request)
    resposta = HttpResponse(content_type="text/csv; charset=utf-8")
    resposta["Content-Disposition"] = (
        f'attachment; filename="publicacoes-{timezone.localdate():%Y-%m-%d}.csv"'
    )
    resposta.write("﻿")
    escritor = csv.writer(resposta, delimiter=";", lineterminator="\r\n")
    escritor.writerow(
        [
            "Data", "Jornalista", "Unidade", "Fonte", "Início da pauta",
            "Título", "Status", "Andamento", "Colocada para edição",
            "Data de publicação", "Horário de publicação", "Revisão",
            "Galeria de fotos", "Bitly nos grupos", "Enviado à SESP",
            "Publicado na AEN", "Link PCPR", "Link AEN", "Tempo até publicar",
        ]
    )
    for p in queryset:
        escritor.writerow(
            [
                p.data.strftime("%d/%m/%Y"),
                p.jornalista.nome,
                p.unidade.nome if p.unidade else "",
                p.fonte,
                p.inicio_pauta.strftime("%H:%M") if p.inicio_pauta else "",
                p.titulo,
                p.get_status_display(),
                p.andamento,
                p.colocada_edicao.strftime("%H:%M") if p.colocada_edicao else "",
                p.data_publicacao.strftime("%d/%m/%Y") if p.data_publicacao else "",
                p.horario_publicacao.strftime("%H:%M") if p.horario_publicacao else "",
                p.revisao.nome if p.revisao else "",
                p.galeria_fotos.nome if p.galeria_fotos else "",
                _sim_nao(p.bitly_grupos),
                _sim_nao(p.enviado_sesp),
                _sim_nao(p.publicado_aen),
                p.link_site,
                p.link_aen,
                p.tempo_ate_publicacao_display,
            ]
        )
    return resposta


# ---------------------------------------------------------------------------
# Formulário e detalhe
# ---------------------------------------------------------------------------

def _valores(form):
    """Valores dos campos como texto, no formato que os components esperam."""
    valores = {}
    for nome in form.fields:
        valor = form[nome].value()
        if isinstance(valor, dt.time):
            valor = valor.strftime("%H:%M")
        valores[nome] = "" if valor is None else str(valor)
    for nome in ("bitly_grupos", "enviado_sesp", "publicado_aen"):
        valores[nome] = form.fields[nome].prepare_value(form[nome].value())
    return valores


def _contexto_formulario(form, publicacao=None):
    return {
        "kicker": KICKER,
        "form": form,
        "publicacao": publicacao,
        "erros": form.errors,
        "erros_gerais": form.non_field_errors(),
        "valores": _valores(form),
        "opcoes_jornalistas": opcoes(form.fields["jornalista"].queryset),
        "opcoes_revisao": opcoes(form.fields["revisao"].queryset),
        "opcoes_unidades": opcoes(form.fields["unidade"].queryset),
        "opcoes_status": _opcoes_status(),
        "opcoes_sim_nao": [{"valor": "1", "rotulo": "Sim"}, {"valor": "0", "rotulo": "Não"}],
    }


def _salvar(request, form):
    publicacao = form.save(commit=False)
    if not publicacao.pk:
        publicacao.criado_por = request.user
    publicacao.full_clean()
    publicacao.save()
    return publicacao


@acesso_ao_modulo
def nova(request):
    if request.method == "POST":
        form = PublicacaoForm(request.POST)
        if form.is_valid():
            try:
                publicacao = _salvar(request, form)
            except ValidationError as erro:
                for campo, mensagens in erro.message_dict.items():
                    for mensagem in mensagens:
                        form.add_error(campo if campo in form.fields else None, mensagem)
            else:
                messages.success(request, "Pauta registrada.")
                return redirect("publicacoes:detalhe", pk=publicacao.pk)
        messages.error(request, "Corrija os campos destacados para continuar.")
    else:
        form = PublicacaoForm(initial={"data": timezone.localdate()})
    contexto = _contexto_formulario(form)
    contexto["titulo_pagina"] = "Nova pauta"
    return render(request, "pages/publicacoes/form.html", contexto)


@acesso_ao_modulo
def editar(request, pk):
    publicacao = get_object_or_404(Publicacao, pk=pk)
    if request.method == "POST":
        form = PublicacaoForm(request.POST, instance=publicacao)
        if form.is_valid():
            try:
                publicacao = _salvar(request, form)
            except ValidationError as erro:
                for campo, mensagens in erro.message_dict.items():
                    for mensagem in mensagens:
                        form.add_error(campo if campo in form.fields else None, mensagem)
            else:
                messages.success(request, "Pauta atualizada.")
                return redirect("publicacoes:detalhe", pk=publicacao.pk)
        messages.error(request, "Corrija os campos destacados para continuar.")
    else:
        form = PublicacaoForm(instance=publicacao)
    contexto = _contexto_formulario(form, publicacao)
    contexto["titulo_pagina"] = f"Editar pauta #{publicacao.pk}"
    return render(request, "pages/publicacoes/form.html", contexto)


@acesso_ao_modulo
def detalhe(request, pk):
    publicacao = get_object_or_404(
        Publicacao.objects.select_related(
            "jornalista", "unidade", "revisao", "galeria_fotos", "criado_por"
        ),
        pk=pk,
    )
    etapas = [
        {
            "titulo": "Pauta recebida",
            "subtitulo": f"{publicacao.data:%d/%m/%Y}"
            + (f" · {publicacao.inicio_pauta:%H:%M}" if publicacao.inicio_pauta else ""),
            "estado": "concluido",
        },
        {
            "titulo": "Colocada para edição",
            "subtitulo": (
                f"{publicacao.colocada_edicao:%H:%M}"
                if publicacao.colocada_edicao
                else "Sem horário registrado"
            ),
            "estado": "concluido" if publicacao.colocada_edicao else "pendente",
        },
        {
            "titulo": "Publicada",
            "subtitulo": (
                f"{publicacao.data_publicacao:%d/%m/%Y}"
                + (
                    f" · {publicacao.horario_publicacao:%H:%M}"
                    if publicacao.horario_publicacao
                    else ""
                )
                if publicacao.data_publicacao
                else "Aguardando publicação"
            ),
            "estado": "concluido" if publicacao.publicada else "pendente",
        },
    ]
    if publicacao.status == StatusPublicacao.CANCELADA:
        etapas[-1] = {
            "titulo": "Cancelada",
            "subtitulo": "Pauta não publicada",
            "estado": "cancelado",
        }
    return render(
        request,
        "pages/publicacoes/detalhe.html",
        {
            "kicker": KICKER,
            "publicacao": publicacao,
            "titulo_pagina": f"Pauta #{publicacao.pk}",
            "etapas": etapas,
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
        "exemplo": "Ex.: Gabriela",
        "icone": "users",
        "intro": "Nome curto usado nas colunas Jornalista, Revisão e Galeria de fotos.",
    },
    "unidades": {
        "model": Unidade,
        "form": UnidadeForm,
        "titulo": "Unidades",
        "singular": "unidade",
        "genitivo": "da unidade",
        "novo": "Nova unidade",
        "exemplo": "Ex.: DP Ponta Grossa",
        "icone": "landmark",
        "intro": "Unidade policial responsável pela pauta (DP, DHPP, DPC...).",
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
            "url": reverse("publicacoes:cadastro_lista", args=[slug]),
        }
        for slug, config in CADASTROS.items()
    ]


def _contexto_cadastros(tipo, config):
    return {
        "kicker": KICKER,
        "modulo_titulo": "Publicações",
        "modulo_sub": "Tabelas de apoio usadas no registro das pautas.",
        "slug": tipo,
        "titulo": config["titulo"],
        "singular": config["singular"],
        "genitivo": config["genitivo"],
        "novo": config["novo"],
        "exemplo": config["exemplo"],
        "grupos": _grupos(),
        "url_lista": "publicacoes:cadastro_lista",
        "url_novo": "publicacoes:cadastro_novo",
        "url_editar": "publicacoes:cadastro_editar",
        "url_alternar": "publicacoes:cadastro_alternar",
    }


@gerenciamento_de_cadastros
def cadastros(request):
    return redirect("publicacoes:cadastro_lista", tipo="equipe")


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
            return redirect("publicacoes:cadastro_lista", tipo=tipo)
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
        request,
        f"{objeto.nome} {'ativado' if objeto.ativo else 'inativado'}.",
    )
    return redirect("publicacoes:cadastro_lista", tipo=tipo)
