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
    AtendimentoForm,
    FiltroAtendimentosForm,
    ResponsavelForm,
    VeiculoForm,
)
from .models import (
    SITUACOES_ABERTAS,
    AcaoHistorico,
    Atendimento,
    HistoricoAtendimento,
    Responsavel,
    SituacaoAtendimento,
    Veiculo,
)
from .permissions import acesso_ao_modulo, gerenciamento_de_cadastros

KICKER = "Atendimento à Imprensa"

# O histórico do atendimento que veio de e-mail: "Criado a partir do e-mail…".
VERBO_ORIGEM = "Criado"

FILAS = [
    ("abertos", "Em aberto", list(SITUACOES_ABERTAS)),
    ("aguardando", "Aguardando fonte", [SituacaoAtendimento.AGUARDANDO_FONTE]),
    ("atendidos", "Atendidos", [SituacaoAtendimento.ATENDIDO]),
    ("nao_responder", "Não responder", [SituacaoAtendimento.NAO_RESPONDER]),
]

# A ordenação não tem mais controles na tela (a lista segue a composição de
# Viagens), mas `?ordem=` continua valendo para os links antigos.
ORDENACOES = {
    "data": ["data", "horario", "pk"],
    "jornalista": ["jornalista", "-data"],
    "veiculo": ["veiculo__nome", "-data"],
    "situacao": ["situacao", "-data"],
    "responsavel": ["responsavel__nome", "-data"],
    "deadline": ["deadline", "-data"],
}

CAMPOS_FILTRO = ["q", "situacao", "veiculo", "responsavel", "inicio", "fim"]


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
            # As listas do painel usam a mesma linha da listagem.
            "linhas_recentes": [linha_da_lista(a, hoje) for a in recentes],
            "pendentes": pendentes,
            "linhas_pendentes": [linha_da_lista(a, hoje) for a in pendentes],
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


# Ícone de cada fila na trilha lateral das situações.
ICONES_FILA = {
    "abertos": "activity",
    "aguardando": "hourglass",
    "atendidos": "check-circle",
    "nao_responder": "ban",
}


@acesso_ao_modulo
def lista(request):
    queryset, filtros, _pedido, fila_ativa = _filtrar(request)
    pagina, paginas_visiveis, querystring = paginar(request, queryset)
    contagens = dict(
        Atendimento.objects.values_list("situacao").annotate(total=Count("pk"))
    )
    filas = [
        {
            "chave": chave,
            "rotulo": rotulo,
            "total": sum(contagens.get(s, 0) for s in situacoes),
        }
        for chave, rotulo, situacoes in FILAS
    ]
    valores = valores_filtro(filtros)
    filtros_ativos = sum(1 for nome in CAMPOS_FILTRO if request.GET.get(nome))
    hoje = timezone.localdate()
    return render(
        request,
        "pages/atendimento_imprensa/lista.html",
        {
            "kicker": KICKER,
            "pagina": pagina,
            "linhas": [linha_da_lista(a, hoje) for a in pagina.object_list],
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
            "hoje": hoje,
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
# Formulário (tela única do atendimento)
# ---------------------------------------------------------------------------

def _contexto_andamento(atendimento, erro="", escolhido="", texto=""):
    return fluxo_andamento.contexto(
        services.FLUXO,
        atendimento.situacao,
        url=reverse("atendimento_imprensa:andamento", args=[atendimento.pk]),
        ultima_anotacao=services.ultima_anotacao(atendimento),
        rotulo_status="Nova situação",
        erro=erro,
        escolhido=escolhido,
        texto=texto,
        placeholder="O que aconteceu: fonte acionada, aguardando o delegado, resposta enviada…",
    )


def _valores(form):
    valores = {}
    for nome in form.fields:
        valor = form[nome].value()
        if isinstance(valor, dt.time):
            valor = valor.strftime("%H:%M")
        valores[nome] = "" if valor is None else str(valor)
    return valores


def _contexto_formulario(form, atendimento=None):
    contexto = {
        "kicker": KICKER,
        "form": form,
        "atendimento": atendimento,
        "erros": form.errors,
        "erros_gerais": form.non_field_errors(),
        "valores": _valores(form),
        "opcoes_veiculos": opcoes(form.fields["veiculo"].queryset),
        "opcoes_responsaveis": opcoes(form.fields["responsavel"].queryset),
        "jornalistas_sugeridos": list(
            Atendimento.objects.order_by("jornalista")
            .values_list("jornalista", flat=True)
            .distinct()[:400]
        ),
        "fontes": [],
        "deadline_vencido": False,
        # Cabeçalho da tela de edição: só o título e o selo da situação.
        "selo": atendimento.get_situacao_display() if atendimento else "Novo",
        "selo_tom": atendimento.situacao_css if atendimento else "pendente",
    }
    if atendimento and atendimento.pk:
        hoje = timezone.localdate()
        contexto.update(_contexto_andamento(atendimento))
        contexto["historico"] = atendimento.historico.select_related("usuario")
        contexto.update(
            {
                "fontes": atendimento.fontes_alinhadas,
                "deadline_vencido": bool(
                    atendimento.aberto
                    and atendimento.deadline
                    and atendimento.deadline < hoje
                ),
            }
        )
    return contexto


def _registrar_edicao(request, form, atendimento, novo, origem=None):
    if novo:
        descricao = "Atendimento registrado no sistema."
        if origem:
            descricao += f" {preencher_por_email.texto_da_origem(origem, verbo=VERBO_ORIGEM)}."
        services.registrar_historico(
            atendimento, request.user, AcaoHistorico.CRIACAO,
            descricao, status_novo=atendimento.situacao,
        )
        return
    alterados = [
        form.fields[nome].label
        for nome in form.changed_data
        if nome in form.fields and nome != "veiculo_novo"
    ]
    if alterados:
        services.registrar_historico(
            atendimento, request.user, AcaoHistorico.ATUALIZACAO,
            "Campos atualizados: " + ", ".join(alterados),
        )


def _salvar(request, form):
    atendimento = form.save(commit=False)
    if not atendimento.pk:
        atendimento.criado_por = request.user
    atendimento.full_clean()
    atendimento.save()
    return atendimento


def _duplicados_do_email(texto_origem):
    """Atendimentos que já saíram do mesmo e-mail (pelo histórico)."""
    historicos = (
        HistoricoAtendimento.objects.filter(acao=AcaoHistorico.CRIACAO, descricao__contains=texto_origem)
        .select_related("atendimento")
        .order_by("-criado_em")[:5]
    )
    return [
        {
            "titulo": f"Atendimento #{h.atendimento.pk} ({h.atendimento.jornalista})",
            "url": reverse("atendimento_imprensa:editar", args=[h.atendimento.pk]),
        }
        for h in historicos
    ]


@acesso_ao_modulo
@require_POST
def ler_email(request):
    """Lê o e-mail do jornalista (arquivo ou texto colado) para a tela "Novo atendimento".

    Não grava nada: devolve as sugestões em JSON (`core.preencher_por_email`)
    e guarda o original até o atendimento ser salvo, para o histórico dizer
    de onde ele veio. Veículo novo nunca é criado aqui: só sugerido.
    """
    return preencher_por_email.responder_leitura(
        request,
        modulo="atendimento_imprensa",
        sugerir=preenchimento.sugestoes,
        formulario=AtendimentoForm,
        duplicados=_duplicados_do_email,
        verbo=VERBO_ORIGEM,
    )


@acesso_ao_modulo
def novo(request):
    # O e-mail da triagem da página inicial (?email_origem=) ou o do formulário que voltou com erro.
    email_origem = preencher_por_email.origem_da_tela(request, "atendimento_imprensa")
    if request.method == "POST":
        form = AtendimentoForm(request.POST)
        # O e-mail lido em "Preencher com um e-mail", se o atendimento veio dele.
        origem = preencher_por_email.origem_do_pedido(request, "atendimento_imprensa")
        if form.is_valid():
            try:
                atendimento = _salvar(request, form)
            except ValidationError as erro:
                for campo, mensagens in erro.message_dict.items():
                    for mensagem in mensagens:
                        form.add_error(campo if campo in form.fields else None, mensagem)
            else:
                _registrar_edicao(request, form, atendimento, novo=True, origem=origem)
                prazo = f" — deadline {atendimento.deadline:%d/%m/%Y}" if getattr(atendimento, "deadline", None) else ""
                preencher_por_email.registrar_cadastro(
                    request, origem, "atendimento_imprensa", form, preenchimento.CAMPOS_APRENDIDOS,
                    titulo=f"Pedido de imprensa por e-mail cadastrado: {atendimento.jornalista or 'jornalista'}"[:150],
                    mensagem=f"{atendimento.veiculo or 'Veículo'}{prazo}. "
                             f"Cadastrado por {request.user.get_full_name() or request.user.get_username()}.",
                    link=reverse("atendimento_imprensa:editar", args=[atendimento.pk]),
                )
                preencher_por_email.concluir_origem(request, origem)
                messages.success(request, "Atendimento registrado.")
                return redirect("atendimento_imprensa:editar", pk=atendimento.pk)
        messages.error(request, "Corrija os campos destacados para continuar.")
        email_origem = preencher_por_email.origem_da_tela(request, "atendimento_imprensa")
    else:
        agora = timezone.localtime()
        form = AtendimentoForm(
            initial={"data": agora.date(), "horario": agora.time().replace(second=0, microsecond=0)}
        )
    contexto = _contexto_formulario(form)
    contexto["email_origem"] = email_origem
    contexto["titulo_pagina"] = "Novo atendimento"
    return render(request, "pages/atendimento_imprensa/form.html", contexto)


@acesso_ao_modulo
def editar(request, pk):
    atendimento = get_object_or_404(
        Atendimento.objects.select_related(
            "veiculo", "responsavel", "responsavel_resposta", "criado_por"
        ),
        pk=pk,
    )
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
                _registrar_edicao(request, form, atendimento, novo=False)
                messages.success(request, "Atendimento atualizado.")
                return redirect("atendimento_imprensa:editar", pk=atendimento.pk)
        messages.error(request, "Corrija os campos destacados para continuar.")
    else:
        form = AtendimentoForm(instance=atendimento)
    contexto = _contexto_formulario(form, atendimento)
    contexto["titulo_pagina"] = f"Atendimento #{atendimento.pk}"
    return render(request, "pages/atendimento_imprensa/form.html", contexto)


@acesso_ao_modulo
def registrar_andamento(request, pk):
    """Registra a próxima situação — na tela do atendimento ou num modal da lista.

    No modal vale o protocolo dos cadastros (`X-Cadastro-Modal`): o GET
    devolve o trecho, o POST devolve `{"ok": true}` ou o trecho com o erro.
    """
    atendimento = get_object_or_404(Atendimento.objects.select_related("veiculo"), pk=pk)
    via_modal = request.headers.get("X-Cadastro-Modal") == "1"
    destino = reverse("atendimento_imprensa:editar", args=[atendimento.pk]) + "#sec-andamento"

    def modal(**extra):
        veiculo = f" · {atendimento.veiculo}" if atendimento.veiculo_id else ""
        return render(
            request,
            "components/v32/andamento_modal.html",
            {
                **_contexto_andamento(atendimento, **extra),
                "titulo_modal": f"Andamento — {atendimento.jornalista}{veiculo}",
                "selo_tom": atendimento.situacao_css,
            },
        )

    if request.method != "POST":
        return modal() if via_modal else redirect(destino)
    nova = request.POST.get("novo_status", "")
    texto = request.POST.get("andamento", "")
    try:
        services.registrar_andamento(atendimento, request.user, nova, texto)
    except ValidationError as erro:
        if via_modal:
            return modal(erro=" ".join(erro.messages), escolhido=nova, texto=texto)
        for mensagem in erro.messages:
            messages.error(request, mensagem)
        return redirect(destino)
    messages.success(request, f"Situação atualizada para {atendimento.get_situacao_display()}.")
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
        "exemplo": "Ex.: Mariana",
        "icone": "users",
        "intro": "Nome curto usado nas colunas de responsável pelo atendimento e pela resposta.",
        "uso": lambda r: Atendimento.objects.filter(
            Q(responsavel=r) | Q(responsavel_resposta=r)
        ).count(),
        "uso_rotulo": ("atendimento", "atendimentos"),
    },
    "veiculos": {
        "model": Veiculo,
        "form": VeiculoForm,
        "titulo": "Veículos",
        "singular": "veículo",
        "novo": "Novo veículo",
        "exemplo": "Ex.: RPC",
        "icone": "mail",
        "intro": "Veículo de imprensa que fez o pedido (TV, rádio, portal, jornal).",
        "uso": lambda v: v.atendimentos.count(),
        "uso_rotulo": ("atendimento", "atendimentos"),
    },
}

_CADASTRO = {"cadastros": CADASTROS, "ns": "atendimento_imprensa"}
_CONTEXTO_CADASTRO = {"kicker": KICKER, "modulo_titulo": "Atendimento à Imprensa"}


@gerenciamento_de_cadastros
def cadastros(request):
    return redirect("atendimento_imprensa:cadastro_lista", tipo="equipe")


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
