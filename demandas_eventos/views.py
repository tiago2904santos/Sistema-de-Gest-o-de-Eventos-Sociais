import csv

from django import forms
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.db.models import ProtectedError, Q
from django.http import Http404, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.dateparse import parse_date
from django.views.decorators.http import require_POST

from core import preencher_por_email
from core.conflitos import conflitos_da_demanda
from integracoes.eprotocolo import andamento as andamento_eprotocolo
from core.listagens import trilha_de_situacoes

from solicitacoes import permissions as permissoes_solicitacoes

from . import encaminhamento, preenchimento, services
from .forms import DemandaEventoForm, PalestranteForm, RespostaPadraoForm, TemaForm
from .models import (
    AcaoHistoricoDemanda,
    CanalSolicitacao,
    DemandaEvento,
    HistoricoDemanda,
    Palestrante,
    RespostaPadrao,
    StatusDemanda,
    Tema,
    TipoEventoPalestra,
)
from .permissions import pode_editar, queryset_visivel
from .planilha import chave
from .presenters import ICONES_EVENTO, ICONES_STATUS, linha_da_lista, linha_do_cadastro

ITENS_POR_PAGINA = 20

MESES = [
    "JANEIRO", "FEVEREIRO", "MARÇO", "ABRIL", "MAIO", "JUNHO",
    "JULHO", "AGOSTO", "SETEMBRO", "OUTUBRO", "NOVEMBRO", "DEZEMBRO",
]


def _opcoes(iteravel):
    return [{"valor": str(item.pk), "rotulo": str(item)} for item in iteravel]


def _opcoes_choices(choices):
    return [{"valor": valor, "rotulo": rotulo} for valor, rotulo in choices]


def _demanda_visivel(request, pk):
    return get_object_or_404(
        queryset_visivel(
            request.user,
            DemandaEvento.objects.select_related("municipio__estado", "criado_por", "solicitacao_dg").prefetch_related("temas", "palestrantes"),
        ),
        pk=pk,
    )


@login_required
def dashboard(request):
    visiveis = queryset_visivel(request.user, DemandaEvento.objects.all())
    hoje = timezone.localdate()
    lista = reverse("demandas_eventos:lista")
    resumo = [
        {"titulo": "Em aberto", "valor": visiveis.exclude(status__in=[StatusDemanda.ATENDIDA, StatusDemanda.CANCELADA]).count(), "icone": "document", "cor": "dourada", "url": lista},
        {"titulo": "Agendadas", "valor": visiveis.filter(status=StatusDemanda.EVENTO_AGENDADO).count(), "icone": "calendar", "cor": "info", "url": f"{lista}?status={StatusDemanda.EVENTO_AGENDADO}"},
        # Pelo ano do evento; sem data do evento, pelo da solicitação (o "Mês" da planilha).
        {"titulo": "Atendidas no ano", "valor": visiveis.filter(Q(data_inicio_evento__year=hoje.year) | Q(data_inicio_evento__isnull=True, data_solicitacao__year=hoje.year), status=StatusDemanda.ATENDIDA).count(), "icone": "check-circle", "cor": "sucesso", "url": f"{lista}?status={StatusDemanda.ATENDIDA}"},
        {"titulo": "Aguardando retorno", "valor": visiveis.filter(status=StatusDemanda.AGUARDANDO_RETORNO).count(), "icone": "hourglass", "cor": "neutra", "url": f"{lista}?status={StatusDemanda.AGUARDANDO_RETORNO}"},
    ]
    proximas = visiveis.filter(data_inicio_evento__gte=hoje).exclude(
        status=StatusDemanda.CANCELADA
    ).select_related("municipio").prefetch_related("temas", "palestrantes").order_by("data_inicio_evento")[:8]
    return render(
        request,
        "pages/demandas_eventos/dashboard.html",
        {
            "resumo": resumo,
            # A lista do painel usa a mesma linha da listagem.
            "linhas_proximas": [linha_da_lista(d) for d in proximas],
        },
    )


def _filtrar(request, queryset):
    """Os filtros da lista, também usados pela exportação."""
    q = request.GET.get("q", "").strip()
    if q:
        queryset = queryset.filter(
            Q(solicitante__icontains=q)
            | Q(descricao__icontains=q)
            | Q(pedido_contato__icontains=q)
            | Q(assunto_email__icontains=q)
            | Q(servidor__icontains=q)
            | Q(palestrantes__nome__icontains=q)
            | Q(protocolo__icontains=q)
            | Q(telefone__icontains=q)
            | Q(email__icontains=q)
            | Q(municipio__nome__icontains=q)
            | Q(municipio_texto__icontains=q)
            | Q(temas__nome__icontains=q)
        )
    status = request.GET.get("status", "").strip()
    if status in StatusDemanda.values:
        queryset = queryset.filter(status=status)
    evento = request.GET.get("evento", "").strip()
    if evento in TipoEventoPalestra.values:
        queryset = queryset.filter(evento=evento)
    for parametro, campo in (("municipio", "municipio_id"), ("tema", "temas__id")):
        valor = request.GET.get(parametro, "").strip()
        if valor.isdigit():
            queryset = queryset.filter(**{campo: valor})
    inicio = parse_date(request.GET.get("inicio", "").strip() or "0")
    fim = parse_date(request.GET.get("fim", "").strip() or "0")
    if inicio:
        queryset = queryset.filter(data_solicitacao__gte=inicio)
    if fim:
        queryset = queryset.filter(data_solicitacao__lte=fim)
    return queryset.distinct()


@login_required
def lista_demandas(request):
    visiveis = queryset_visivel(
        request.user, DemandaEvento.objects.select_related("municipio").prefetch_related("temas", "palestrantes")
    )
    queryset = _filtrar(request, visiveis).order_by("-data_solicitacao", "-pk")
    status = request.GET.get("status", "").strip()
    evento = request.GET.get("evento", "").strip()
    paginator = Paginator(queryset, ITENS_POR_PAGINA)
    pagina = paginator.get_page(request.GET.get("pagina"))
    parametros = request.GET.copy()
    parametros.pop("pagina", None)
    return render(
        request,
        "pages/demandas_eventos/lista.html",
        {
            "pagina": pagina,
            "q": request.GET.get("q", "").strip(),
            "status": status,
            "evento": evento,
            "linhas": [linha_da_lista(d) for d in pagina],
            # As situações na trilha lateral, como nas listas de Viagens.
            "situacoes": trilha_de_situacoes(
                request,
                [
                    {
                        "chave": valor,
                        "rotulo": rotulo,
                        "total": visiveis.filter(status=valor).count(),
                    }
                    for valor, rotulo in StatusDemanda.choices
                ],
                visiveis.count(),
                ICONES_STATUS,
                parametro="status",
            ),
            "situacao_ativa": status or "todas",
            # O tipo de evento (a coluna "Evento") como segundo grupo da trilha.
            "tipos_evento": trilha_de_situacoes(
                request,
                [
                    {
                        "chave": valor,
                        "rotulo": rotulo,
                        "total": visiveis.filter(evento=valor).count(),
                    }
                    for valor, rotulo in TipoEventoPalestra.choices
                ],
                visiveis.count(),
                ICONES_EVENTO,
                parametro="evento",
            )[1:],
            "evento_ativo": evento or "todas",
            "querystring": parametros.urlencode(),
            "paginas_visiveis": list(paginator.get_elided_page_range(pagina.number, on_each_side=2, on_ends=1)),
            "elipse": paginator.ELLIPSIS,
            "tem_filtros": bool(request.GET.get("q") or status or evento),
        },
    )


def _contexto_form(form, instancia):
    def valor(nome):
        value = form[nome].value()
        if hasattr(value, "strftime") and nome.startswith("hora_"):
            return value.strftime("%H:%M")
        return "" if value is None else str(value)

    def marcados(nome):
        return {str(getattr(item, "pk", item)) for item in (form[nome].value() or [])}

    evento_atual = valor("evento")
    temas_marcados = marcados("temas")
    palestrantes_marcados = marcados("palestrantes")
    # Conflitos de agenda (core/conflitos.py): palestrante na mesma data e
    # pedido repetido no município. Com o formulário recusado, os enviados.
    if instancia is not None and instancia.status == StatusDemanda.CANCELADA:
        conflitos = []
    elif form.is_bound:
        conflitos = conflitos_da_demanda(form.instance, palestrantes=sorted(palestrantes_marcados))
    else:
        conflitos = conflitos_da_demanda(instancia) if instancia is not None else []
    return {
        "form": form,
        "instancia": instancia,
        "conflitos": conflitos,
        "conflitos_fixos": "pedido=demanda" + (f"&excluir_demanda={instancia.pk}" if instancia else ""),
        "valores": {nome: valor(nome) for nome in form.fields if nome not in {"temas", "palestrantes"}},
        "erros": form.errors,
        "opcoes_eventos": [
            {
                "valor": chave,
                "rotulo": rotulo,
                "icone": ICONES_EVENTO[chave],
                "marcado": chave == evento_atual,
            }
            for chave, rotulo in TipoEventoPalestra.choices
        ],
        "opcoes_status": _opcoes_choices(StatusDemanda.choices),
        # Os temas como as atividades do plano de trabalho: cartões marcáveis.
        "opcoes_temas": [
            {"valor": str(t.pk), "rotulo": t.nome, "marcado": str(t.pk) in temas_marcados, "chave": chave(t.nome).lower()}
            for t in form.fields["temas"].queryset
        ],
        "temas_marcados_total": len(temas_marcados),
        # Os palestrantes como os ofícios vinculados da OS: busca e linhas.
        # `tema` alimenta a recomendação pelo tema escolhido (palestras-form.js).
        "opcoes_palestrantes": [
            {
                "valor": str(p.pk),
                "rotulo": p.nome,
                "detalhes": " · ".join(
                    x for x in (p.tema_abordagem, p.lotacao, str(p.municipio) if p.municipio_id else p.municipio_texto) if x
                ),
                "busca": f"{p.divisao} {p.contato} {p.email}",
                "dados": {"tema": chave(p.tema_abordagem).lower()},
                "selecionado": str(p.pk) in palestrantes_marcados,
            }
            for p in form.fields["palestrantes"].queryset
        ],
        "opcoes_canais": _opcoes_choices(CanalSolicitacao.choices),
        # O componente de destinos da OS: estado e, dependente dele, município.
        "estados": [{"valor": str(e.pk), "rotulo": f"{e.sigla} — {e.nome}"} for e in form.fields["estado"].queryset],
        "municipios": [
            {"valor": str(m.pk), "rotulo": m.nome, "estado": str(m.estado_id)}
            for m in form.fields["municipio"].queryset.order_by("nome")
        ],
    }


def _duplicados_do_email(usuario):
    """Palestras que este usuário vê e que já saíram do mesmo e-mail (pelo histórico)."""

    def buscar(texto_origem):
        visiveis = queryset_visivel(usuario, DemandaEvento.objects.all()).values("pk")
        historicos = (
            HistoricoDemanda.objects.filter(
                acao=AcaoHistoricoDemanda.CRIACAO, descricao__contains=texto_origem, demanda__in=visiveis
            )
            .select_related("demanda")
            .order_by("-criado_em")[:5]
        )
        return [
            {
                "titulo": f"{h.demanda.get_evento_display()} #{h.demanda.pk}",
                "url": reverse("demandas_eventos:editar", args=[h.demanda.pk]),
            }
            for h in historicos
        ]

    return buscar


@login_required
@require_POST
def ler_email(request):
    """Lê o e-mail do pedido (arquivo ou texto colado) para a tela "Nova palestra".

    Não grava nada: devolve as sugestões em JSON (`core.preencher_por_email`)
    e guarda o original até a palestra ser salva, para o histórico dizer de
    onde ela veio.
    """
    return preencher_por_email.responder_leitura(
        request,
        modulo="demandas_eventos",
        sugerir=preenchimento.sugestoes,
        formulario=DemandaEventoForm,
        duplicados=_duplicados_do_email(request.user),
    )


@login_required
def editar_demanda(request, pk=None):
    instancia = _demanda_visivel(request, pk) if pk else None
    if instancia and not pode_editar(request.user, instancia):
        raise Http404
    email_origem = None
    if request.method == "POST":
        form = DemandaEventoForm(request.POST, instance=instancia, usuario=request.user)
        # O e-mail lido em "Preencher com um e-mail", se a palestra nova veio dele.
        origem = None if instancia else preencher_por_email.origem_do_pedido(request, "demandas_eventos")
        if form.is_valid():
            demanda = form.save(criado_por=request.user)
            if not instancia:
                descricao = "Registro criado no sistema."
                if origem:
                    descricao += f" {preencher_por_email.texto_da_origem(origem)}."
                services.registrar_historico(
                    demanda, request.user, AcaoHistoricoDemanda.CRIACAO,
                    descricao, status_novo=demanda.status,
                )
                preencher_por_email.concluir_origem(request, origem)
            else:
                alterados = [
                    form.fields[nome].label
                    for nome in form.changed_data
                    if nome in form.fields and nome not in {"versao", "status"}
                ]
                alterados = [rotulo for rotulo in alterados if rotulo != "Estado"]
                if alterados:
                    services.registrar_historico(
                        demanda, request.user, AcaoHistoricoDemanda.ATUALIZACAO,
                        "Campos atualizados: " + ", ".join(alterados),
                        status_novo=demanda.status,
                    )
            messages.success(request, f"{demanda.get_evento_display()} #{demanda.pk} salva com sucesso.")
            return redirect("demandas_eventos:editar", pk=demanda.pk)
        messages.error(request, "Corrija os campos destacados para continuar.")
        if not instancia:
            email_origem = preencher_por_email.origem_pendente(request, "demandas_eventos")
    else:
        form = DemandaEventoForm(instance=instancia, usuario=request.user)
    contexto = _contexto_form(form, instancia)
    contexto["email_origem"] = email_origem
    contexto["breadcrumb"] = [
        {"label": "Palestras", "url": reverse("demandas_eventos:lista")},
        {"label": f"{instancia.get_evento_display()} #{instancia.pk}" if instancia else "Nova palestra"},
    ]
    if instancia:
        contexto.update({
            "historico": instancia.historico.select_related("usuario"),
            "solicitacao_dg": _solicitacao_dg(request.user, instancia),
            # O andamento como nas Solicitações: etapas no stepper e os
            # cartões do próximo status, com a anotação que vai ao histórico.
            **_contexto_andamento(instancia),
            "andamento_protocolo": andamento_eprotocolo.andamento_guardado(
                request, "demandas_eventos", instancia.pk
            ),
        })
    return render(request, "pages/demandas_eventos/form.html", contexto)


@login_required
def anexo_pedido(request, pk):
    """O anexo que veio pelo formulário público, só para quem enxerga a linha."""
    from core.private_media import private_file_response

    demanda = _demanda_visivel(request, pk)
    return private_file_response(demanda.anexo_pedido)


def _solicitacao_dg(usuario, demanda):
    """A solicitação de evento ligada pelo "Encaminhar à DG", como a tela a mostra."""
    solicitacao = demanda.solicitacao_dg
    if solicitacao is None:
        return None
    return {
        "numero": solicitacao.pk,
        "status": solicitacao.get_status_display(),
        "status_tom": solicitacao.status.lower(),
        # Quem não enxerga a solicitação (não criou e não é da DG) vê só a situação.
        "url": reverse("solicitacoes:editar", args=[solicitacao.pk])
        if permissoes_solicitacoes.pode_ver(usuario, solicitacao)
        else "",
    }


@login_required
@require_POST
def encaminhar_dg(request, pk):
    """Cria a solicitação de evento da palestra (rascunho) e abre para completar."""
    demanda = _demanda_visivel(request, pk)
    if not pode_editar(request.user, demanda):
        raise Http404
    try:
        solicitacao = encaminhamento.encaminhar_a_dg(demanda, request.user)
    except ValidationError as erro:
        for mensagem in erro.messages:
            messages.error(request, mensagem)
        return redirect("demandas_eventos:editar", pk=demanda.pk)
    messages.success(
        request,
        f"Solicitação #{solicitacao.pk} criada a partir da {demanda.get_evento_display().lower()}. "
        "Complete o que falta e envie à DG.",
    )
    return redirect("solicitacoes:editar", pk=solicitacao.pk)


@login_required
@require_POST
def consultar_protocolo(request, pk):
    """"Consultar andamento" do protocolo da palestra, como nas Solicitações."""
    demanda = _demanda_visivel(request, pk)
    if not demanda.protocolo:
        messages.error(request, "Informe e salve o número do protocolo antes de consultar.")
    else:
        erro = andamento_eprotocolo.consultar_e_guardar(
            request, "demandas_eventos", demanda.pk, demanda.protocolo
        )
        if erro:
            messages.error(request, erro)
    url = reverse("demandas_eventos:editar", args=[demanda.pk])
    return redirect(f"{url}#sec-solicitacao")


def _contexto_andamento(demanda, erro="", escolhido="", texto="", extras=None):
    faltas = services.faltas_do_andamento(demanda)
    return {
        "demanda": demanda,
        # O que Agendada e Atendida pedem e a palestra ainda não tem: só isso
        # aparece no formulário do andamento.
        "faltas_andamento": faltas,
        "extras_andamento": extras or {},
        "opcoes_palestrante_andamento": (
            [
                {"valor": str(p.pk), "rotulo": p.nome}
                for p in Palestrante.objects.only("pk", "nome")
            ]
            if faltas["palestrante"]
            else []
        ),
        "opcoes_andamento": [
            {**opcao, "marcado": opcao["valor"] == escolhido}
            for opcao in services.opcoes_de_status(demanda, ICONES_STATUS)
        ],
        "etapas": services.etapas(demanda),
        # A anotação da última mudança de status (pode não ter): é ela que a
        # faixa do topo mostra, para não apresentar um recado antigo como motivo.
        "ultima_anotacao": services.ultima_anotacao(demanda),
        "erro_andamento": erro,
        "texto_andamento": texto,
    }


def _extras_do_andamento(extras):
    """Data, palestrante e público que o formulário do andamento pediu, já convertidos."""
    texto_data, texto_palestrante, texto_publico = (
        extras["andamento_data"], extras["andamento_palestrante"], extras["andamento_publico"]
    )
    try:
        data_evento = parse_date(texto_data) if texto_data else None
    except ValueError:
        data_evento = None
    if texto_data and data_evento is None:
        raise ValidationError("Informe a data do evento no formato dd/mm/aaaa.")
    palestrante = None
    if texto_palestrante:
        palestrante = Palestrante.objects.filter(pk=texto_palestrante).first() if texto_palestrante.isdigit() else None
        if palestrante is None:
            raise ValidationError("Escolha um palestrante da lista.")
    publico = None
    if texto_publico:
        if not texto_publico.isdigit():
            raise ValidationError("A quantidade de público é um número inteiro.")
        publico = int(texto_publico)
    return {"data_evento": data_evento, "palestrante": palestrante, "quantidade_publico": publico}


@login_required
def registrar_andamento(request, pk):
    """Registra o próximo status — na tela da palestra ou num modal da lista.

    No modal vale o protocolo dos cadastros (`X-Cadastro-Modal`): o GET devolve
    o trecho do formulário, o POST devolve `{"ok": true}` ou o trecho de novo,
    com o erro. Sem o cabeçalho, volta para a palestra.
    """
    demanda = _demanda_visivel(request, pk)
    via_modal = request.headers.get("X-Cadastro-Modal") == "1"
    destino = reverse("demandas_eventos:editar", args=[demanda.pk]) + "#sec-andamento"
    if request.method != "POST":
        if not via_modal:
            return redirect(destino)
        return render(request, "pages/demandas_eventos/_modal_andamento.html", _contexto_andamento(demanda))
    novo_status = request.POST.get("novo_status", "")
    texto = request.POST.get("andamento", "")
    extras = {nome: request.POST.get(nome, "").strip() for nome in ("andamento_data", "andamento_palestrante", "andamento_publico")}
    try:
        services.registrar_andamento(demanda, request.user, novo_status, texto, **_extras_do_andamento(extras))
    except ValidationError as erro:
        # A palestra pode ter ficado com dados da tentativa: volta ao banco.
        demanda.refresh_from_db()
        if via_modal:
            return render(
                request,
                "pages/demandas_eventos/_modal_andamento.html",
                _contexto_andamento(demanda, " ".join(erro.messages), novo_status, texto, extras),
            )
        for mensagem in erro.messages:
            messages.error(request, mensagem)
        return redirect(destino)
    messages.success(request, f"Status atualizado para {demanda.get_status_display()}.")
    if via_modal:
        return JsonResponse({"ok": True})
    return redirect(destino)


# Para onde a palestra costuma ir depois de respondida.
STATUS_APOS_RESPOSTA = [StatusDemanda.EM_ANDAMENTO, StatusDemanda.AGUARDANDO_RETORNO]


def _contexto_resposta(demanda, erro="", escolhida="", status=""):
    respostas = []
    for resposta in RespostaPadrao.objects.all():
        texto = services.preencher_resposta(resposta, demanda)
        respostas.append({
            "valor": str(resposta.pk),
            "rotulo": resposta.tipo,
            "texto": texto,
            "link_email": services.link_email(demanda, texto),
            "link_whatsapp": services.link_whatsapp(demanda, texto),
            "marcado": str(resposta.pk) == escolhida,
        })
    return {
        "demanda": demanda,
        "respostas": respostas,
        "opcoes_status_resposta": [
            {"valor": valor, "rotulo": StatusDemanda(valor).label}
            for valor in STATUS_APOS_RESPOSTA
            if valor != demanda.status
        ],
        "status_resposta": status,
        "erro_resposta": erro,
        "breadcrumb": [
            {"label": "Palestras", "url": reverse("demandas_eventos:lista")},
            {"label": f"{demanda.get_evento_display()} #{demanda.pk}", "url": reverse("demandas_eventos:editar", args=[demanda.pk])},
            {"label": "Responder"},
        ],
    }


@login_required
def responder(request, pk):
    """Responde o pedido com uma resposta padrão preenchida com os dados da palestra.

    A tela mostra cada resposta já preenchida, com o e-mail (com assunto) e
    o WhatsApp do contato prontos para abrir; o POST registra no histórico a
    que foi enviada e, se pedido, muda o status. Mesmo protocolo de modal do
    andamento (`X-Cadastro-Modal`).
    """
    demanda = _demanda_visivel(request, pk)
    if not pode_editar(request.user, demanda):
        raise Http404
    via_modal = request.headers.get("X-Cadastro-Modal") == "1"
    modelo = "pages/demandas_eventos/_modal_responder.html" if via_modal else "pages/demandas_eventos/responder.html"
    destino = reverse("demandas_eventos:editar", args=[demanda.pk])
    if request.method != "POST":
        return render(request, modelo, _contexto_resposta(demanda))
    escolhida = request.POST.get("resposta", "")
    status = request.POST.get("novo_status", "")
    resposta = RespostaPadrao.objects.filter(pk=escolhida).first() if escolhida.isdigit() else None
    try:
        if resposta is None:
            raise ValidationError("Escolha a resposta enviada.")
        if status and status not in STATUS_APOS_RESPOSTA:
            raise ValidationError("Escolha um status válido.")
        services.registrar_resposta(
            demanda, request.user, resposta, services.preencher_resposta(resposta, demanda), status
        )
    except ValidationError as erro:
        return render(request, modelo, _contexto_resposta(demanda, " ".join(erro.messages), escolhida, status))
    messages.success(request, f"Resposta \"{resposta.tipo}\" registrada no histórico.")
    if via_modal:
        return JsonResponse({"ok": True})
    return redirect(destino)


# As colunas da aba do ano da planilha, na mesma ordem, e como sair de cada
# registro para elas.
COLUNAS_EXPORTACAO = [
    ("MÊS", lambda d: MESES[d.mes_referencia.month - 1]),
    ("MUNICIPIO", lambda d: d.municipio_display),
    ("DATA DO EVENTO E HORA (PERÍODO)", lambda d: d.periodo_evento_display or "À definir"),
    ("EVENTO", lambda d: d.get_evento_display().upper()),
    ("STATUS DA DEMANDA", lambda d: d.get_status_display().upper()),
    ("ANDAMENTO", lambda d: d.andamento),
    ("INFORMAÇÕES PRÉVIAS", lambda d: d.informacoes_previas),
    ("SOLICITANTE", lambda d: d.solicitante),
    ("CONTATO", lambda d: d.contato_display),
    ("DATA DA SOLICITAÇÃO", lambda d: f"{d.data_solicitacao:%d/%m/%Y}"),
    ("FOI SOLICITADO VIA:", lambda d: d.canal_display.upper()),
    ("DESCRIÇÃO", lambda d: d.descricao),
    ("QUANTIDADE DE PÚBLICO", lambda d: d.quantidade_publico if d.quantidade_publico is not None else ""),
    ("ASSUNTO E-MAIL", lambda d: d.assunto_email),
    ("PEDIDO/CONTATO", lambda d: d.pedido_contato),
    ("TEMA", lambda d: d.temas_display),
    ("SERVIDOR", lambda d: d.servidores_display),
]


@login_required
def solicitantes_anteriores(request):
    """Solicitantes de palestras anteriores, para sugerir ao digitar (só leitura)."""
    from solicitacoes.sugestoes import ultimos_por_nome

    achados = ultimos_por_nome(
        queryset_visivel(request.user, DemandaEvento.objects.all()),
        "solicitante",
        request.GET.get("q", ""),
        {"telefone": "telefone", "email": "email"},
        ordem=["-data_solicitacao", "-pk"],
    )
    for achado in achados:
        achado["detalhe"] = " · ".join(v for v in achado["campos"].values() if v)
    return JsonResponse({"resultados": achados})


@login_required
def exportar_demandas(request):
    queryset = _filtrar(
        request,
        queryset_visivel(
            request.user, DemandaEvento.objects.select_related("municipio").prefetch_related("temas", "palestrantes")
        ),
    ).order_by("data_solicitacao", "pk")
    resposta = HttpResponse(content_type="text/csv; charset=utf-8")
    resposta["Content-Disposition"] = 'attachment; filename="palestras-e-eventos-ascom.csv"'
    resposta.write("﻿")
    escritor = csv.writer(resposta, delimiter=";", lineterminator="\r\n")
    escritor.writerow([titulo for titulo, _ in COLUNAS_EXPORTACAO])
    for demanda in queryset:
        escritor.writerow([extrair(demanda) for _, extrair in COLUNAS_EXPORTACAO])
    return resposta


CADASTROS = {
    "palestrantes": {"model": Palestrante, "form": PalestranteForm, "titulo": "Palestrantes", "singular": "palestrante", "novo": "Novo palestrante", "busca": "nome"},
    "temas": {"model": Tema, "form": TemaForm, "titulo": "Temas", "singular": "tema", "novo": "Novo tema", "busca": "nome"},
    "respostas": {"model": RespostaPadrao, "form": RespostaPadraoForm, "titulo": "Respostas padrão", "singular": "resposta padrão", "novo": "Nova resposta padrão", "busca": "tipo"},
}


def _cadastro(tipo):
    if tipo not in CADASTROS:
        raise Http404
    return CADASTROS[tipo]


@login_required
def lista_cadastro(request, tipo, modal=None):
    """A lista do cadastro; criar e editar abrem num modal sobre ela.

    O protocolo é o dos cadastros de Eventos (`data-cadastro-modal`, cabeçalho
    `X-Cadastro-Modal`, `{"ok": true}` no sucesso). Sem JavaScript, `?novo=1`
    ou `?editar=<pk>` abrem a lista já com o modal aberto.
    """
    config = _cadastro(tipo)
    if modal is None and request.method == "GET":
        editar = request.GET.get("editar", "")
        if request.GET.get("novo"):
            modal = _contexto_modal(tipo, config, config["form"](), None)
        elif editar.isdigit():
            instancia = get_object_or_404(config["model"], pk=editar)
            modal = _contexto_modal(tipo, config, config["form"](instance=instancia), instancia)
    q = request.GET.get("q", "").strip()
    queryset = config["model"].objects.all()
    if tipo == "palestrantes":
        queryset = queryset.select_related("municipio")
    if q:
        queryset = queryset.filter(**{f"{config['busca']}__icontains": q})
    paginador = Paginator(queryset, ITENS_POR_PAGINA)
    pagina = paginador.get_page(request.GET.get("pagina"))
    parametros = request.GET.copy()
    for chave in ("pagina", "novo", "editar"):
        parametros.pop(chave, None)
    return render(
        request,
        "pages/demandas_eventos/cadastro_lista.html",
        {
            "tipo": tipo,
            "config": config,
            "pagina": pagina,
            "linhas": [linha_do_cadastro(item, tipo) for item in pagina],
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


# Largura de cada campo no modal (colunas de uma grade de 12).
LARGURAS = {"nome": "", "tipo": "", "mensagem": "", "tema_abordagem": "", "municipio": "4", "divisao": "4", "lotacao": "4", "contato": "6", "email": "6"}


def _campos_cadastro(form):
    campos = []
    for nome, campo in form.fields.items():
        value = form[nome].value()
        item = {
            "name": nome,
            "label": campo.label,
            "erros": form.errors.get(nome),
            "obrigatorio": campo.required,
            "valor": "" if value is None else str(value),
            "largura": LARGURAS.get(nome, ""),
            "ajuda": campo.help_text,
        }
        if isinstance(campo, forms.ModelChoiceField):
            item.update({"tipo": "select", "opcoes": _opcoes(campo.queryset)})
        elif isinstance(campo.widget, forms.Textarea):
            item["tipo"] = "textarea"
        else:
            item["tipo"] = "input"
        campos.append(item)
    return campos


def _contexto_modal(tipo, config, form, instancia):
    if tipo == "palestrantes":
        # A aba PALESTRANTES é do Paraná: a lista não precisa dos 5.570 municípios.
        from cadastros.models import Municipio

        atual = instancia.municipio_id if instancia else None
        form.fields["municipio"].queryset = Municipio.objects.filter(
            Q(estado__sigla="PR") | Q(pk=atual)
        ).order_by("nome")
    campos = _campos_cadastro(form)
    erros_gerais = list(form.non_field_errors())
    return {
        "url_acao": (
            reverse("demandas_eventos:cadastro_editar", args=[tipo, instancia.pk])
            if instancia
            else reverse("demandas_eventos:cadastro_novo", args=[tipo])
        ),
        "titulo": f"Editar {config['singular']}" if instancia else config["novo"],
        "singular": config["singular"],
        "campos": campos,
        "erros_gerais": erros_gerais,
        "erros_total": sum(1 for campo in campos if campo["erros"]) + len(erros_gerais),
        "municipio_planilha": (
            instancia.municipio_texto
            if tipo == "palestrantes" and instancia and not instancia.municipio_id
            else ""
        ),
    }


@login_required
def editar_cadastro(request, tipo, pk=None):
    config = _cadastro(tipo)
    instancia = get_object_or_404(config["model"], pk=pk) if pk else None
    via_modal = request.headers.get("X-Cadastro-Modal") == "1"
    if request.method == "GET" and not via_modal:
        destino = reverse("demandas_eventos:cadastro_lista", args=[tipo])
        return redirect(f"{destino}?{'editar=' + str(pk) if pk else 'novo=1'}")
    if request.method == "POST":
        form = config["form"](request.POST, instance=instancia)
        if form.is_valid():
            form.save()
            messages.success(request, f"{config['singular'].capitalize()} salvo com sucesso.")
            if via_modal:
                return JsonResponse({"ok": True})
            return redirect("demandas_eventos:cadastro_lista", tipo=tipo)
    else:
        form = config["form"](instance=instancia)
    modal = _contexto_modal(tipo, config, form, instancia)
    if via_modal:
        return render(request, "pages/demandas_eventos/_modal_cadastro.html", {"dados": modal})
    return lista_cadastro(request, tipo, modal=modal)


@login_required
@require_POST
def excluir_cadastro(request, tipo, pk):
    config = _cadastro(tipo)
    objeto = get_object_or_404(config["model"], pk=pk)
    try:
        # Tema e palestrante são escolhas múltiplas nas palestras: apagar um em
        # uso sumiria com ele das linhas sem aviso. Em uso, não sai.
        if tipo in {"temas", "palestrantes"} and objeto.demandas.exists():
            raise ProtectedError("em uso", [objeto])
        objeto.delete()
    except ProtectedError:
        messages.error(
            request,
            f"Não é possível excluir: {config['singular']} está em uso em palestras registradas.",
        )
    else:
        messages.success(request, f"{config['singular'].capitalize()} excluído.")
    return redirect("demandas_eventos:cadastro_lista", tipo=tipo)
