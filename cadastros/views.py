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
from django.urls import reverse
from django.utils.http import urlencode
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

# `icone` e `cor` alimentam os cartões da página inicial de cadastros;
# `singular`, `genitivo`, `novo` e `exemplo` alimentam listas e formulários.
CADASTROS = {
    "tipos-evento": {
        "model": TipoEvento,
        "titulo": "Tipos de evento",
        "campos": ["nome"],
        "icone": "calendar",
        "cor": "#bea45a",
        "singular": "tipo de evento",
        "genitivo": "do tipo de evento",
        "novo": "Novo tipo de evento",
        "exemplo": "Ex.: PCPR na Comunidade",
    },
    "servicos": {
        "model": Servico,
        "titulo": "Serviços",
        "campos": ["nome"],
        "icone": "checklist",
        "cor": "#bea45a",
        "singular": "serviço",
        "genitivo": "do serviço",
        "novo": "Novo serviço",
        "exemplo": "Ex.: Apresentação da banda institucional",
    },
    "equipes": {
        "model": Equipe,
        "titulo": "Equipes",
        "campos": ["nome"],
        "icone": "users",
        "cor": "#d9c58c",
        "singular": "equipe",
        "genitivo": "da equipe",
        "novo": "Nova equipe",
        "exemplo": "Ex.: Ascom",
    },
    "orgaos": {
        "model": OrgaoResponsavel,
        "titulo": "Órgãos responsáveis",
        "campos": ["nome"],
        "icone": "landmark",
        "cor": "#d9c58c",
        "singular": "órgão responsável",
        "genitivo": "do órgão responsável",
        "novo": "Novo órgão responsável",
        "exemplo": "Ex.: PCPR",
    },
    "municipios": {
        "model": Municipio,
        "titulo": "Municípios",
        "campos": ["nome", "estado", "regiao"],
        "icone": "map-pin",
        "cor": "#9fd6b1",
        "singular": "município",
        "genitivo": "do município",
        "novo": "Novo município",
        "exemplo": "Ex.: Curitiba",
    },
    "motoristas": {
        "model": Motorista,
        "titulo": "Motoristas",
        "campos": ["nome", "telefone"],
        "icone": "volante",
        "cor": "#b9c9ec",
        "singular": "motorista",
        "genitivo": "do motorista",
        "novo": "Novo motorista",
        "exemplo": "Ex.: João da Silva",
    },
    "unidades-moveis": {
        "model": UnidadeMovel,
        "titulo": "Unidades móveis",
        "campos": ["nome"],
        "icone": "truck",
        "cor": "#cdb4e4",
        "singular": "unidade móvel",
        "genitivo": "da unidade móvel",
        "novo": "Nova unidade móvel",
        "exemplo": "Ex.: Caminhão",
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
        {
            "slug": slug,
            "titulo": config["titulo"],
            "total": config["model"].objects.count(),
            "icone": config["icone"],
            "cor": config["cor"],
        }
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
    situacao = request.GET.get("situacao", "").strip()
    if situacao == "ativos":
        queryset = queryset.filter(ativo=True)
    elif situacao == "inativos":
        queryset = queryset.filter(ativo=False)
    paginator = Paginator(queryset, ITENS_POR_PAGINA)
    pagina = paginator.get_page(request.GET.get("pagina"))
    parametros = {}
    if termo:
        parametros["q"] = termo
    if situacao:
        parametros["situacao"] = situacao
    return render(
        request,
        "pages/cadastros/lista.html",
        {
            "slug": slug,
            "titulo": config["titulo"],
            "singular": config["singular"],
            "pagina": pagina,
            "termo": termo,
            "situacao": situacao,
            "tem_filtros": bool(termo or situacao),
            "opcoes_situacao": [
                {"valor": "ativos", "rotulo": "Ativos"},
                {"valor": "inativos", "rotulo": "Inativos"},
            ],
            "querystring": urlencode(parametros),
            "paginas_visiveis": list(
                paginator.get_elided_page_range(pagina.number, on_each_side=2, on_ends=1)
            ),
            "elipse": paginator.ELLIPSIS,
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
    apenas_nome = config["campos"] == ["nome"]
    if apenas_nome:
        intro = f"Informe o nome {config['genitivo']} que poderá ser utilizado nas solicitações."
    else:
        intro = f"Informe os dados {config['genitivo']} que poderão ser utilizados nas solicitações."
    return render(
        request,
        "pages/cadastros/form.html",
        {
            "slug": slug,
            "titulo": config["titulo"],
            "instancia": instancia,
            "campos": _campos_para_template(form),
            "cartao_titulo": f"Editar {config['singular']}" if pk else config["novo"],
            "cartao_intro": intro,
            "exemplo": config["exemplo"],
            "genitivo": config["genitivo"],
            "subtitulo_pagina": (
                "Atualize os dados deste registro"
                if pk
                else "Cadastre uma opção disponível nas solicitações"
            ),
            "breadcrumb": [
                {"label": config["titulo"], "url": reverse("cadastros:lista", args=[slug])},
                {"label": "Editar registro" if pk else "Novo registro"},
            ],
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
