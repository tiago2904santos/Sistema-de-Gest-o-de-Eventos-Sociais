import csv

from django import forms
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import ProtectedError, Q
from django.http import Http404, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.dateparse import parse_date
from django.views.decorators.http import require_POST

from core.listagens import trilha_de_situacoes

from . import services
from .forms import DemandaEventoForm, PalestranteForm, RespostaPadraoForm, TemaForm
from .models import (
    AcaoHistoricoDemanda,
    DemandaEvento,
    Palestrante,
    RespostaPadrao,
    StatusDemanda,
    Tema,
    TipoEventoPalestra,
)
from .permissions import pode_editar, queryset_visivel
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
            DemandaEvento.objects.select_related("tema", "municipio__estado", "criado_por"),
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
        {"titulo": "Atendidas no ano", "valor": visiveis.filter(status=StatusDemanda.ATENDIDA, data_solicitacao__year=hoje.year).count(), "icone": "check-circle", "cor": "sucesso", "url": f"{lista}?status={StatusDemanda.ATENDIDA}"},
        {"titulo": "Aguardando retorno", "valor": visiveis.filter(status=StatusDemanda.AGUARDANDO_RETORNO).count(), "icone": "hourglass", "cor": "neutra", "url": f"{lista}?status={StatusDemanda.AGUARDANDO_RETORNO}"},
    ]
    proximas = visiveis.filter(data_inicio_evento__gte=hoje).exclude(
        status=StatusDemanda.CANCELADA
    ).select_related("tema", "municipio").order_by("data_inicio_evento")[:8]
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
            | Q(municipio__nome__icontains=q)
            | Q(municipio_texto__icontains=q)
            | Q(tema__nome__icontains=q)
        )
    status = request.GET.get("status", "").strip()
    if status in StatusDemanda.values:
        queryset = queryset.filter(status=status)
    evento = request.GET.get("evento", "").strip()
    if evento in TipoEventoPalestra.values:
        queryset = queryset.filter(evento=evento)
    for parametro, campo in (("municipio", "municipio_id"), ("tema", "tema_id")):
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
        request.user, DemandaEvento.objects.select_related("tema", "municipio")
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
        return "" if value is None else str(value)

    evento_atual = valor("evento")
    return {
        "form": form,
        "instancia": instancia,
        "valores": {nome: valor(nome) for nome in form.fields},
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
        "opcoes_temas": _opcoes(form.fields["tema"].queryset),
        "opcoes_municipios": _opcoes(form.fields["municipio"].queryset),
        # A aba PALESTRANTES da planilha sugere o "Servidor" sem obrigar.
        "palestrantes": Palestrante.objects.only("nome", "lotacao"),
    }


@login_required
def editar_demanda(request, pk=None):
    instancia = _demanda_visivel(request, pk) if pk else None
    if instancia and not pode_editar(request.user, instancia):
        raise Http404
    status_anterior = instancia.status if instancia else ""
    if request.method == "POST":
        form = DemandaEventoForm(request.POST, instance=instancia, usuario=request.user)
        if form.is_valid():
            demanda = form.save(criado_por=request.user)
            if not instancia:
                services.registrar_historico(
                    demanda, request.user, AcaoHistoricoDemanda.CRIACAO,
                    "Registro criado no sistema.", status_novo=demanda.status,
                )
            else:
                alterados = [
                    form.fields[nome].label
                    for nome in form.changed_data
                    if nome in form.fields and nome not in {"versao", "status"}
                ]
                if demanda.status != status_anterior:
                    services.registrar_historico(
                        demanda, request.user, AcaoHistoricoDemanda.TRANSICAO,
                        "", status_anterior=status_anterior, status_novo=demanda.status,
                    )
                if alterados:
                    services.registrar_historico(
                        demanda, request.user, AcaoHistoricoDemanda.ATUALIZACAO,
                        "Campos atualizados: " + ", ".join(alterados),
                        status_novo=demanda.status,
                    )
            messages.success(request, f"{demanda.get_evento_display()} #{demanda.pk} salva com sucesso.")
            return redirect("demandas_eventos:editar", pk=demanda.pk)
        messages.error(request, "Corrija os campos destacados para continuar.")
    else:
        form = DemandaEventoForm(instance=instancia, usuario=request.user)
    contexto = _contexto_form(form, instancia)
    contexto["breadcrumb"] = [
        {"label": "Palestras", "url": reverse("demandas_eventos:lista")},
        {"label": f"{instancia.get_evento_display()} #{instancia.pk}" if instancia else "Nova palestra"},
    ]
    if instancia:
        contexto["historico"] = instancia.historico.select_related("usuario")
    return render(request, "pages/demandas_eventos/form.html", contexto)


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
    ("CONTATO", lambda d: d.contato),
    ("DATA DA SOLICITAÇÃO", lambda d: f"{d.data_solicitacao:%d/%m/%Y}"),
    ("FOI SOLICITADO VIA:", lambda d: d.canal_solicitacao),
    ("DESCRIÇÃO", lambda d: d.descricao),
    ("QUANTIDADE DE PÚBLICO", lambda d: d.quantidade_publico if d.quantidade_publico is not None else ""),
    ("ASSUNTO E-MAIL", lambda d: d.assunto_email),
    ("PEDIDO/CONTATO", lambda d: d.pedido_contato),
    ("TEMA", lambda d: str(d.tema) if d.tema_id else ""),
    ("SERVIDOR", lambda d: d.servidor),
]


@login_required
def exportar_demandas(request):
    queryset = _filtrar(
        request,
        queryset_visivel(
            request.user, DemandaEvento.objects.select_related("tema", "municipio")
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
        objeto.delete()
    except ProtectedError:
        messages.error(
            request,
            f"Não é possível excluir: {config['singular']} está em uso em palestras registradas.",
        )
    else:
        messages.success(request, f"{config['singular'].capitalize()} excluído.")
    return redirect("demandas_eventos:cadastro_lista", tipo=tipo)
