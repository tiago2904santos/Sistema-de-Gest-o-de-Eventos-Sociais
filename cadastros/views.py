"""CRUD administrativo dos cadastros de apoio.

Um registro genérico por tipo de cadastro, renderizado com os components do
design system. Restrito ao perfil administrador (a UI esconde, o backend nega).
"""

from django import forms
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import Http404
from django.core.paginator import Paginator
from django.db.models import ProtectedError
from django.forms import modelform_factory
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from auditoria.models import LogAuditoria
from solicitacoes.permissions import eh_administrador

from .models import (
    Equipe,
    Motorista,
    Municipio,
    OrgaoResponsavel,
    Servico,
    TipoEvento,
    UnidadeMovel,
)

CADASTROS = {
    "tipos-evento": {"model": TipoEvento, "titulo": "Tipos de evento", "campos": ["nome"]},
    "servicos": {"model": Servico, "titulo": "Serviços", "campos": ["nome"]},
    "equipes": {"model": Equipe, "titulo": "Equipes", "campos": ["nome"]},
    "orgaos": {
        "model": OrgaoResponsavel,
        "titulo": "Órgãos responsáveis",
        "campos": ["nome"],
    },
    "municipios": {
        "model": Municipio,
        "titulo": "Municípios",
        "campos": ["nome", "estado", "regiao"],
    },
    "motoristas": {"model": Motorista, "titulo": "Motoristas", "campos": ["nome", "telefone"]},
    "unidades-moveis": {
        "model": UnidadeMovel,
        "titulo": "Unidades móveis",
        "campos": ["nome"],
    },
}

ITENS_POR_PAGINA = 20


def _exigir_administrador(request):
    if not eh_administrador(request.user):
        raise PermissionDenied


def _config(slug):
    if slug not in CADASTROS:
        raise Http404
    return CADASTROS[slug]


def _form_class(config):
    return modelform_factory(config["model"], fields=config["campos"])


def _campos_para_template(form):
    """Descreve os campos do form para os components genéricos."""
    campos = []
    for nome, campo in form.fields.items():
        valor = form[nome].value()
        descricao = {
            "name": nome,
            "label": campo.label,
            "obrigatorio": campo.required,
            "erros": form.errors.get(nome),
            "valor": "" if valor is None else str(valor),
        }
        if isinstance(campo, forms.ModelChoiceField):
            descricao["tipo"] = "select"
            descricao["opcoes"] = [
                {"valor": str(obj.pk), "rotulo": str(obj)} for obj in campo.queryset
            ]
        elif isinstance(campo.widget, forms.Textarea):
            descricao["tipo"] = "textarea"
        else:
            descricao["tipo"] = "input"
        campos.append(descricao)
    return campos


def _registrar_auditoria(usuario, acao, objeto):
    LogAuditoria.objects.create(
        usuario=usuario,
        acao=acao,
        descricao=f"{objeto._meta.verbose_name} '{objeto}' (id {objeto.pk})",
    )


@login_required
def index(request):
    _exigir_administrador(request)
    grupos = [
        {"slug": slug, "titulo": config["titulo"], "total": config["model"].objects.count()}
        for slug, config in CADASTROS.items()
    ]
    return render(request, "pages/cadastros/index.html", {"grupos": grupos})


@login_required
def lista(request, slug):
    _exigir_administrador(request)
    config = _config(slug)
    queryset = config["model"].objects.all()
    if slug == "municipios":
        queryset = queryset.select_related("estado", "regiao")
    termo = request.GET.get("q", "").strip()
    if termo:
        queryset = queryset.filter(nome__icontains=termo)
    pagina = Paginator(queryset, ITENS_POR_PAGINA).get_page(request.GET.get("pagina"))
    return render(
        request,
        "pages/cadastros/lista.html",
        {
            "slug": slug,
            "titulo": config["titulo"],
            "pagina": pagina,
            "termo": termo,
            "eh_municipio": slug == "municipios",
        },
    )


@login_required
def editar(request, slug, pk=None):
    _exigir_administrador(request)
    config = _config(slug)
    instancia = get_object_or_404(config["model"], pk=pk) if pk else None
    FormClass = _form_class(config)
    if request.method == "POST":
        form = FormClass(request.POST, instance=instancia)
        if form.is_valid():
            objeto = form.save()
            _registrar_auditoria(
                request.user,
                "CADASTRO_ATUALIZADO" if pk else "CADASTRO_CRIADO",
                objeto,
            )
            messages.success(request, f"{config['titulo']}: registro salvo com sucesso.")
            return redirect("cadastros:lista", slug=slug)
        messages.error(request, "Corrija os campos destacados para continuar.")
    else:
        form = FormClass(instance=instancia)
    return render(
        request,
        "pages/cadastros/form.html",
        {
            "slug": slug,
            "titulo": config["titulo"],
            "instancia": instancia,
            "campos": _campos_para_template(form),
        },
    )


@login_required
@require_POST
def alternar_ativo(request, slug, pk):
    _exigir_administrador(request)
    config = _config(slug)
    objeto = get_object_or_404(config["model"], pk=pk)
    objeto.ativo = not objeto.ativo
    objeto.save(update_fields=["ativo", "atualizado_em"])
    _registrar_auditoria(
        request.user,
        "CADASTRO_ATIVADO" if objeto.ativo else "CADASTRO_INATIVADO",
        objeto,
    )
    messages.success(
        request,
        f"Registro {'ativado' if objeto.ativo else 'inativado'} com sucesso.",
    )
    return redirect("cadastros:lista", slug=slug)


@login_required
@require_POST
def excluir(request, slug, pk):
    _exigir_administrador(request)
    config = _config(slug)
    objeto = get_object_or_404(config["model"], pk=pk)
    descricao = f"{objeto._meta.verbose_name} '{objeto}' (id {objeto.pk})"
    try:
        objeto.delete()
    except ProtectedError:
        messages.error(
            request,
            "Este registro não pode ser excluído porque está vinculado a "
            "solicitações ou a outros cadastros. Use a ação Inativar para "
            "retirá-lo dos novos formulários.",
        )
    else:
        LogAuditoria.objects.create(
            usuario=request.user, acao="CADASTRO_EXCLUIDO", descricao=descricao
        )
        messages.success(request, "Registro excluído com sucesso.")
    return redirect("cadastros:lista", slug=slug)
