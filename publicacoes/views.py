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
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.dateformat import format as formatar_data
from django.views.decorators.http import require_POST

from core import andamento as fluxo_andamento
from core import cadastros_modal
from core import preencher_por_email
from core.listagens import (
    opcoes,
    ordenacao,
    paginar,
    trilha_de_situacoes,
    valores_filtro,
)

from . import preenchimento, services
from .presenters import linha_da_lista
from .forms import (
    FiltroPublicacoesForm,
    PublicacaoForm,
    ResponsavelForm,
    UnidadeForm,
)
from .models import (
    AcaoHistorico,
    HistoricoPublicacao,
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

# A ordenação não tem mais controles na tela (a lista segue a composição de
# Viagens), mas `?ordem=` continua valendo para os links antigos.
ORDENACOES = {
    "data": ["data", "inicio_pauta", "pk"],
    "titulo": ["titulo", "-data"],
    "jornalista": ["jornalista__nome", "-data"],
    "unidade": ["unidade__nome", "-data"],
    "status": ["status", "-data"],
    "publicacao": ["data_publicacao", "horario_publicacao", "-pk"],
}

CAMPOS_FILTRO = ["q", "status", "jornalista", "unidade", "inicio", "fim"]


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
            # A lista do painel usa a mesma linha da listagem.
            "linhas_recentes": [linha_da_lista(p) for p in recentes],
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


# Ícone de cada fila na trilha lateral das situações.
ICONES_FILA = {
    "pendentes": "hourglass",
    "andamento": "activity",
    "publicadas": "check-circle",
    "canceladas": "ban",
}


@acesso_ao_modulo
def lista(request):
    queryset, filtros, _pedido, fila_ativa = _filtrar(request)
    pagina, paginas_visiveis, querystring = paginar(request, queryset)
    contagens = dict(
        Publicacao.objects.values_list("status").annotate(total=Count("pk"))
    )
    filas = [
        {
            "chave": chave,
            "rotulo": rotulo,
            "total": sum(contagens.get(s, 0) for s in statuses),
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
            "linhas": [linha_da_lista(p) for p in pagina.object_list],
            "paginas_visiveis": paginas_visiveis,
            "elipse": Paginator.ELLIPSIS,
            "querystring": querystring,
            "q": valores.get("q", ""),
            "situacoes": trilha_de_situacoes(
                request, filas, sum(contagens.values()), ICONES_FILA
            ),
            # Chip aceso: sem fila escolhida, "Todas".
            "situacao_ativa": fila_ativa or "todas",
            "fila_ativa": fila_ativa,
            "tem_filtros": filtros_ativos > 0,
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
# Formulário (tela única do registro)
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


def _contexto_andamento(publicacao, erro="", escolhido="", texto=""):
    return fluxo_andamento.contexto(
        services.FLUXO,
        publicacao.status,
        url=reverse("publicacoes:andamento", args=[publicacao.pk]),
        ultima_anotacao=services.ultima_anotacao(publicacao),
        erro=erro,
        escolhido=escolhido,
        texto=texto,
        placeholder="O que aconteceu: aguardando fotos, texto com a revisão, motivo do cancelamento…",
    )


def _contexto_formulario(form, publicacao=None):
    contexto = {
        "kicker": KICKER,
        "form": form,
        "publicacao": publicacao,
        # Cabeçalho da tela de edição: só o título e o selo da situação.
        "selo": publicacao.get_status_display() if publicacao else "Nova",
        "selo_tom": publicacao.status_css if publicacao else "pendente",
        "erros": form.errors,
        "erros_gerais": form.non_field_errors(),
        "valores": _valores(form),
        "opcoes_jornalistas": opcoes(form.fields["jornalista"].queryset),
        "opcoes_revisao": opcoes(form.fields["revisao"].queryset),
        "opcoes_unidades": opcoes(form.fields["unidade"].queryset),
        "opcoes_sim_nao": [{"valor": "1", "rotulo": "Sim"}, {"valor": "0", "rotulo": "Não"}],
    }
    if publicacao:
        contexto.update(_contexto_andamento(publicacao))
        contexto["historico"] = publicacao.historico.select_related("usuario")
    return contexto


def _registrar_edicao(request, form, publicacao, nova, origem=None):
    if nova:
        descricao = "Pauta registrada no sistema."
        if origem:
            descricao += f" {preencher_por_email.texto_da_origem(origem)}."
        services.registrar_historico(
            publicacao, request.user, AcaoHistorico.CRIACAO,
            descricao, status_novo=publicacao.status,
        )
        return
    alterados = [
        form.fields[nome].label
        for nome in form.changed_data
        if nome in form.fields and nome != "unidade_nova"
    ]
    if alterados:
        services.registrar_historico(
            publicacao, request.user, AcaoHistorico.ATUALIZACAO,
            "Campos atualizados: " + ", ".join(alterados),
        )


def _salvar(request, form):
    publicacao = form.save(commit=False)
    if not publicacao.pk:
        publicacao.criado_por = request.user
    publicacao.full_clean()
    publicacao.save()
    return publicacao


def _duplicados_do_email(texto_origem):
    """Pautas que já saíram do mesmo e-mail (pelo histórico)."""
    historicos = (
        HistoricoPublicacao.objects.filter(acao=AcaoHistorico.CRIACAO, descricao__contains=texto_origem)
        .select_related("publicacao")
        .order_by("-criado_em")[:5]
    )
    return [
        {
            "titulo": f"Pauta “{h.publicacao.titulo[:60]}”",
            "url": reverse("publicacoes:editar", args=[h.publicacao.pk]),
        }
        for h in historicos
    ]


@acesso_ao_modulo
@require_POST
def ler_email(request):
    """Lê o e-mail da pauta (arquivo ou texto colado) para a tela "Nova pauta".

    Não grava nada: devolve as sugestões em JSON (`core.preencher_por_email`)
    e guarda o original até a pauta ser salva, para o histórico dizer de
    onde ela veio. Unidade nova nunca é criada aqui: só sugerida.
    """
    return preencher_por_email.responder_leitura(
        request,
        modulo="publicacoes",
        sugerir=preenchimento.sugestoes,
        formulario=PublicacaoForm,
        duplicados=_duplicados_do_email,
    )


@acesso_ao_modulo
def nova(request):
    email_origem = None
    if request.method == "POST":
        form = PublicacaoForm(request.POST)
        # O e-mail lido em "Preencher com um e-mail", se a pauta veio dele.
        origem = preencher_por_email.origem_do_pedido(request, "publicacoes")
        if form.is_valid():
            try:
                publicacao = _salvar(request, form)
            except ValidationError as erro:
                for campo, mensagens in erro.message_dict.items():
                    for mensagem in mensagens:
                        form.add_error(campo if campo in form.fields else None, mensagem)
            else:
                _registrar_edicao(request, form, publicacao, nova=True, origem=origem)
                preencher_por_email.concluir_origem(request, origem)
                messages.success(request, "Pauta registrada.")
                return redirect("publicacoes:editar", pk=publicacao.pk)
        messages.error(request, "Corrija os campos destacados para continuar.")
        email_origem = preencher_por_email.origem_pendente(request, "publicacoes")
    else:
        form = PublicacaoForm(initial={"data": timezone.localdate()})
    contexto = _contexto_formulario(form)
    contexto["email_origem"] = email_origem
    contexto["titulo_pagina"] = "Nova pauta"
    return render(request, "pages/publicacoes/form.html", contexto)


@acesso_ao_modulo
def editar(request, pk):
    publicacao = get_object_or_404(
        Publicacao.objects.select_related(
            "jornalista", "unidade", "revisao", "galeria_fotos", "criado_por"
        ),
        pk=pk,
    )
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
                _registrar_edicao(request, form, publicacao, nova=False)
                messages.success(request, "Pauta atualizada.")
                return redirect("publicacoes:editar", pk=publicacao.pk)
        messages.error(request, "Corrija os campos destacados para continuar.")
    else:
        form = PublicacaoForm(instance=publicacao)
    contexto = _contexto_formulario(form, publicacao)
    contexto["titulo_pagina"] = f"Editar pauta #{publicacao.pk}"
    return render(request, "pages/publicacoes/form.html", contexto)


@acesso_ao_modulo
def registrar_andamento(request, pk):
    """Registra o próximo status — na tela da pauta ou num modal da lista.

    No modal vale o protocolo dos cadastros (`X-Cadastro-Modal`): o GET
    devolve o trecho, o POST devolve `{"ok": true}` ou o trecho com o erro.
    """
    publicacao = get_object_or_404(Publicacao, pk=pk)
    via_modal = request.headers.get("X-Cadastro-Modal") == "1"
    destino = reverse("publicacoes:editar", args=[publicacao.pk]) + "#sec-andamento"

    def modal(**extra):
        return render(
            request,
            "components/v32/andamento_modal.html",
            {
                **_contexto_andamento(publicacao, **extra),
                "titulo_modal": f"Andamento — {publicacao.titulo[:80]}",
                "selo_tom": publicacao.status_css,
            },
        )

    if request.method != "POST":
        return modal() if via_modal else redirect(destino)
    novo = request.POST.get("novo_status", "")
    texto = request.POST.get("andamento", "")
    try:
        services.registrar_andamento(publicacao, request.user, novo, texto)
    except ValidationError as erro:
        if via_modal:
            return modal(erro=" ".join(erro.messages), escolhido=novo, texto=texto)
        for mensagem in erro.messages:
            messages.error(request, mensagem)
        return redirect(destino)
    messages.success(request, f"Status atualizado para {publicacao.get_status_display()}.")
    return JsonResponse({"ok": True}) if via_modal else redirect(destino)


# ---------------------------------------------------------------------------
# Cadastros de apoio (administradores)
# ---------------------------------------------------------------------------

CADASTROS = {
    "equipe": {
        "model": Responsavel,
        "form": ResponsavelForm,
        "titulo": "Equipe",
        "singular": "integrante",
        "novo": "Novo integrante",
        "exemplo": "Ex.: Gabriela",
        "icone": "users",
        "intro": "Nome curto usado nas colunas Jornalista, Revisão e Galeria de fotos.",
        "uso": lambda r: Publicacao.objects.filter(
            Q(jornalista=r) | Q(revisao=r) | Q(galeria_fotos=r)
        ).count(),
        "uso_rotulo": ("pauta", "pautas"),
    },
    "unidades": {
        "model": Unidade,
        "form": UnidadeForm,
        "titulo": "Unidades",
        "singular": "unidade",
        "novo": "Nova unidade",
        "exemplo": "Ex.: DP Ponta Grossa",
        "icone": "landmark",
        "intro": "Unidade policial responsável pela pauta (DP, DHPP, DPC...).",
        "uso": lambda u: u.pautas.count(),
        "uso_rotulo": ("pauta", "pautas"),
    },
}

_CADASTRO = {"cadastros": CADASTROS, "ns": "publicacoes"}
_CONTEXTO_CADASTRO = {"kicker": KICKER, "modulo_titulo": "Publicações"}


@gerenciamento_de_cadastros
def cadastros(request):
    return redirect("publicacoes:cadastro_lista", tipo="equipe")


@gerenciamento_de_cadastros
def lista_cadastro(request, tipo):
    return cadastros_modal.lista(request, tipo, **_CADASTRO, **_CONTEXTO_CADASTRO)


@gerenciamento_de_cadastros
def editar_cadastro(request, tipo, pk=None):
    return cadastros_modal.editar(request, tipo, pk, **_CADASTRO, **_CONTEXTO_CADASTRO)


@gerenciamento_de_cadastros
@require_POST
def excluir_cadastro(request, tipo, pk):
    return cadastros_modal.excluir(request, tipo, pk, **_CADASTRO)
