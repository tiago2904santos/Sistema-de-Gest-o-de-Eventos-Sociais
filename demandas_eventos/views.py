from django import forms
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone

from cadastros.models import Municipio, TipoEvento

from .forms import DemandaEventoForm, PalestranteForm, RespostaPadraoForm, TemaForm
from .models import DemandaEvento, Palestrante, RespostaPadrao, StatusDemanda, Tema
from .permissions import pode_editar, queryset_visivel

ITENS_POR_PAGINA = 20


def _opcoes(iteravel):
    return [{"valor": str(item.pk), "rotulo": str(item)} for item in iteravel]


def _opcoes_choices(choices):
    return [{"valor": valor, "rotulo": rotulo} for valor, rotulo in choices]


def _demanda_visivel(request, pk):
    return get_object_or_404(
        queryset_visivel(
            request.user,
            DemandaEvento.objects.select_related(
                "tipo_evento", "tema", "municipio__estado", "responsavel_atendimento", "criado_por"
            ).prefetch_related("setores", "palestrantes"),
        ),
        pk=pk,
    )


@login_required
def dashboard(request):
    visiveis = queryset_visivel(request.user, DemandaEvento.objects.all())
    hoje = timezone.localdate()
    resumo = [
        {"titulo": "Demandas abertas", "valor": visiveis.exclude(status__in=[StatusDemanda.ATENDIDA, StatusDemanda.CANCELADA, StatusDemanda.NAO_ATENDER]).count(), "icone": "document", "cor": "dourada", "url": reverse("demandas_eventos:lista")},
        {"titulo": "Eventos agendados", "valor": visiveis.filter(status=StatusDemanda.EVENTO_AGENDADO).count(), "icone": "calendar", "cor": "info", "url": reverse("demandas_eventos:lista") + f"?status={StatusDemanda.EVENTO_AGENDADO}"},
        {"titulo": "Atendidas no ano", "valor": visiveis.filter(status=StatusDemanda.ATENDIDA, data_solicitacao__year=hoje.year).count(), "icone": "check-circle", "cor": "sucesso", "url": reverse("demandas_eventos:lista") + f"?status={StatusDemanda.ATENDIDA}"},
        {"titulo": "Aguardando retorno", "valor": visiveis.filter(status=StatusDemanda.AGUARDANDO_RETORNO).count(), "icone": "hourglass", "cor": "neutra", "url": reverse("demandas_eventos:lista") + f"?status={StatusDemanda.AGUARDANDO_RETORNO}"},
    ]
    proximas = visiveis.filter(data_inicio_evento__gte=hoje).exclude(
        status__in=[StatusDemanda.CANCELADA, StatusDemanda.NAO_ATENDER]
    ).select_related("tipo_evento", "municipio").order_by("data_inicio_evento")[:8]
    return render(request, "pages/demandas_eventos/dashboard.html", {"resumo": resumo, "proximas": proximas})


@login_required
def lista_demandas(request):
    queryset = queryset_visivel(
        request.user,
        DemandaEvento.objects.select_related("tipo_evento", "tema", "municipio", "responsavel_atendimento"),
    )
    q = request.GET.get("q", "").strip()
    status = request.GET.get("status", "").strip()
    tipo = request.GET.get("tipo", "").strip()
    municipio = request.GET.get("municipio", "").strip()
    if q:
        queryset = queryset.filter(
            Q(solicitante__icontains=q)
            | Q(descricao__icontains=q)
            | Q(pedido_contato__icontains=q)
            | Q(assunto_email__icontains=q)
            | Q(municipio_texto__icontains=q)
        )
    if status in StatusDemanda.values:
        queryset = queryset.filter(status=status)
    if tipo.isdigit():
        queryset = queryset.filter(tipo_evento_id=tipo)
    if municipio.isdigit():
        queryset = queryset.filter(municipio_id=municipio)
    queryset = queryset.order_by("-data_solicitacao", "-pk")
    paginator = Paginator(queryset, ITENS_POR_PAGINA)
    pagina = paginator.get_page(request.GET.get("pagina"))
    parametros = request.GET.copy()
    parametros.pop("pagina", None)
    return render(
        request,
        "pages/demandas_eventos/lista.html",
        {
            "pagina": pagina,
            "q": q,
            "status": status,
            "tipo": tipo,
            "municipio": municipio,
            "opcoes_status": _opcoes_choices(StatusDemanda.choices),
            "opcoes_tipos": _opcoes(TipoEvento.objects.filter(ativo=True)),
            "opcoes_municipios": _opcoes(Municipio.objects.filter(demandas_ascom__isnull=False).distinct()),
            "querystring": parametros.urlencode(),
            "paginas_visiveis": list(paginator.get_elided_page_range(pagina.number, on_each_side=2, on_ends=1)),
            "elipse": paginator.ELLIPSIS,
            "tem_filtros": bool(q or status or tipo or municipio),
        },
    )


def _contexto_form(form, instancia):
    def valor(nome):
        value = form[nome].value()
        return "" if value is None else str(value)

    def marcados(nome):
        return [str(getattr(item, "pk", item)) for item in (form[nome].value() or [])]

    return {
        "form": form,
        "instancia": instancia,
        "valores": {nome: valor(nome) for nome in form.fields if nome not in {"palestrantes", "setores"}},
        "erros": form.errors,
        "opcoes_tipos": _opcoes(form.fields["tipo_evento"].queryset),
        "opcoes_temas": _opcoes(form.fields["tema"].queryset),
        "opcoes_municipios": _opcoes(form.fields["municipio"].queryset),
        "opcoes_responsaveis": _opcoes(form.fields["responsavel_atendimento"].queryset),
        "opcoes_status": _opcoes_choices(StatusDemanda.choices),
        "opcoes_palestrantes": _opcoes(form.fields["palestrantes"].queryset),
        "palestrantes_marcados": marcados("palestrantes"),
        "opcoes_setores": _opcoes(form.fields["setores"].queryset),
        "setores_marcados": marcados("setores"),
    }


@login_required
def editar_demanda(request, pk=None):
    instancia = _demanda_visivel(request, pk) if pk else None
    if instancia and not pode_editar(request.user, instancia):
        raise PermissionDenied
    if request.method == "POST":
        form = DemandaEventoForm(request.POST, instance=instancia, usuario=request.user)
        if form.is_valid():
            demanda = form.save(criado_por=request.user)
            messages.success(request, f"Demanda #{demanda.pk} salva com sucesso.")
            return redirect("demandas_eventos:detalhe", pk=demanda.pk)
        messages.error(request, "Corrija os campos destacados para continuar.")
    else:
        form = DemandaEventoForm(instance=instancia, usuario=request.user)
    contexto = _contexto_form(form, instancia)
    contexto.update(
        {
            "titulo": f"Editar demanda #{instancia.pk}" if instancia else "Nova demanda de evento",
            "breadcrumb": [
                {"label": "Demandas ASCOM", "url": reverse("demandas_eventos:lista")},
                {"label": "Editar" if instancia else "Nova demanda"},
            ],
        }
    )
    return render(request, "pages/demandas_eventos/form.html", contexto)


@login_required
def detalhe_demanda(request, pk):
    demanda = _demanda_visivel(request, pk)
    return render(
        request,
        "pages/demandas_eventos/detalhe.html",
        {
            "demanda": demanda,
            "breadcrumb": [
                {"label": "Demandas ASCOM", "url": reverse("demandas_eventos:lista")},
                {"label": f"Demanda #{demanda.pk}"},
            ],
        },
    )


CADASTROS = {
    "temas": {"model": Tema, "form": TemaForm, "titulo": "Temas", "singular": "tema"},
    "palestrantes": {"model": Palestrante, "form": PalestranteForm, "titulo": "Palestrantes", "singular": "palestrante"},
    "respostas": {"model": RespostaPadrao, "form": RespostaPadraoForm, "titulo": "Respostas padrão", "singular": "resposta padrão"},
}


def _cadastro(tipo):
    if tipo not in CADASTROS:
        from django.http import Http404
        raise Http404
    return CADASTROS[tipo]


@login_required
def lista_cadastro(request, tipo):
    config = _cadastro(tipo)
    q = request.GET.get("q", "").strip()
    queryset = config["model"].objects.all()
    campo_busca = "tipo" if tipo == "respostas" else "nome"
    if q:
        queryset = queryset.filter(**{f"{campo_busca}__icontains": q})
    pagina = Paginator(queryset, ITENS_POR_PAGINA).get_page(request.GET.get("pagina"))
    return render(request, "pages/demandas_eventos/cadastro_lista.html", {"tipo": tipo, "config": config, "pagina": pagina, "q": q})


def _campos_cadastro(form):
    campos = []
    for nome, campo in form.fields.items():
        value = form[nome].value()
        item = {"name": nome, "label": campo.label, "erros": form.errors.get(nome), "obrigatorio": campo.required, "valor": "" if value is None else str(value)}
        if isinstance(campo, forms.ModelMultipleChoiceField):
            item.update({"tipo": "multiplo", "opcoes": _opcoes(campo.queryset), "marcados": [str(getattr(v, "pk", v)) for v in (value or [])]})
        elif isinstance(campo, forms.ModelChoiceField):
            item.update({"tipo": "select", "opcoes": _opcoes(campo.queryset)})
        elif isinstance(campo.widget, forms.Textarea):
            item["tipo"] = "textarea"
        elif isinstance(campo, forms.BooleanField):
            item["tipo"] = "boolean"
            item["valor"] = bool(value)
        else:
            item["tipo"] = "input"
        campos.append(item)
    return campos


@login_required
def editar_cadastro(request, tipo, pk=None):
    config = _cadastro(tipo)
    instancia = get_object_or_404(config["model"], pk=pk) if pk else None
    if request.method == "POST":
        form = config["form"](request.POST, instance=instancia)
        if form.is_valid():
            form.save()
            messages.success(request, f"{config['singular'].capitalize()} salvo com sucesso.")
            return redirect("demandas_eventos:cadastro_lista", tipo=tipo)
    else:
        form = config["form"](instance=instancia)
    return render(request, "pages/demandas_eventos/cadastro_form.html", {"tipo": tipo, "config": config, "instancia": instancia, "campos": _campos_cadastro(form), "breadcrumb": [{"label": config["titulo"], "url": reverse("demandas_eventos:cadastro_lista", args=[tipo])}, {"label": "Editar" if instancia else "Novo"}]})
