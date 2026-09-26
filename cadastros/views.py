"""CRUD administrativo dos cadastros de apoio.

Um registro genérico por tipo de cadastro, renderizado com os components do
design system. Restrito ao perfil administrador (a UI esconde, o backend nega).
"""

from django import forms
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import Http404, JsonResponse
from django.core.paginator import Paginator
from django.db.models import ProtectedError
from django.forms import modelform_factory
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.http import urlencode
from django.views.decorators.http import require_POST

from auditoria.models import LogAuditoria
from solicitacoes.permissions import eh_administrador, eh_gestor_dg

from .models import (
    Equipe,
    Municipio,
    OrgaoResponsavel,
    Servico,
    TextoDespacho,
    TipoEvento,
    TipoEventoEquipe,
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
    "textos-despacho": {
        "model": TextoDespacho,
        "titulo": "Textos prontos do despacho",
        "campos": ["nome", "texto"],
        "icone": "gavel",
        "cor": "#bea45a",
        "singular": "texto pronto",
        "genitivo": "do texto pronto",
        "novo": "Novo texto pronto",
        "exemplo": "Ex.: Falta o ofício do solicitante",
        # Quem despacha mantém os próprios textos, mesmo sem ser administrador.
        "gestor_dg": True,
    },
}

ITENS_POR_PAGINA = 20


def _exigir_administrador(request, slug=None):
    if eh_administrador(request.user):
        return
    if slug in CADASTROS and CADASTROS[slug].get("gestor_dg") and eh_gestor_dg(request.user):
        return
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


def _grupos():
    """Trilha lateral dos cadastros: um item por tabela, com o total de registros."""
    return [
        {
            "slug": slug,
            "titulo": config["titulo"],
            "total": config["model"].objects.count(),
            "icone": config["icone"],
            "cor": config["cor"],
            "novo": config["novo"],
        }
        for slug, config in CADASTROS.items()
    ]


@login_required
def index(request):
    _exigir_administrador(request)
    return render(request, "pages/cadastros/index.html", {"grupos": _grupos()})


@login_required
def lista(request, slug):
    _exigir_administrador(request, slug)
    config = _config(slug)
    modal = None
    if request.GET.get("novo") or request.GET.get("editar"):
        pk = request.GET.get("editar")
        if pk and not pk.isdecimal():
            raise Http404
        instancia = get_object_or_404(config["model"], pk=pk) if pk else None
        modal = _contexto_modal(slug, config, _form_class(config)(instance=instancia), instancia)
    return _render_lista(request, slug, modal)


def _render_lista(request, slug, modal=None):
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
            "novo": config["novo"],
            "grupos": _grupos(),
            "total_registros": config["model"].objects.count(),
            "total_ativos": config["model"].objects.filter(ativo=True).count(),
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
            "modal": modal,
        },
    )


@login_required
def editar(request, slug, pk=None):
    _exigir_administrador(request, slug)
    config = _config(slug)
    instancia = get_object_or_404(config["model"], pk=pk) if pk else None
    FormClass = _form_class(config)
    via_modal = request.headers.get("X-Cadastro-Modal") == "1"
    if request.method == "GET" and not via_modal:
        parametros = request.GET.copy()
        parametros.pop("novo", None)
        parametros.pop("editar", None)
        parametros["editar" if pk else "novo"] = str(pk) if pk else "1"
        return redirect(f"{reverse('cadastros:lista', args=[slug])}?{parametros.urlencode()}")
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
            if via_modal:
                return JsonResponse({"ok": True})
            return redirect("cadastros:lista", slug=slug)
        if not via_modal:
            messages.error(request, "Corrija os campos destacados para continuar.")
    else:
        form = FormClass(instance=instancia)
    contexto = _contexto_modal(slug, config, form, instancia)
    if via_modal:
        return render(request, "pages/cadastros/_modal_form.html", {"dados": contexto})
    return _render_lista(request, slug, contexto)


def _contexto_modal(slug, config, form, instancia):
    pk = instancia.pk if instancia else None
    apenas_nome = config["campos"] == ["nome"]
    campos = _campos_para_template(form)
    erros_gerais = list(form.non_field_errors())
    erros_total = sum(1 for campo in campos if campo["erros"]) + len(erros_gerais)
    if apenas_nome:
        intro = f"Informe o nome {config['genitivo']} que poderá ser utilizado nas solicitações."
    else:
        intro = f"Informe os dados {config['genitivo']} que poderão ser utilizados nas solicitações."
    return {
        "url_acao": reverse("cadastros:editar", args=[slug, pk]) if pk else reverse("cadastros:novo", args=[slug]),
        "slug": slug,
        "titulo": config["titulo"],
        "instancia": instancia,
        "singular": config["singular"],
        "apenas_nome": apenas_nome,
        "campos": campos,
        "erros_gerais": erros_gerais,
        "erros_total": erros_total,
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
    }


@login_required
@require_POST
def alternar_ativo(request, slug, pk):
    _exigir_administrador(request, slug)
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
    _exigir_administrador(request, slug)
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


class ModeloTipoEventoForm(forms.ModelForm):
    """Os padrões de um tipo de evento: solicitante, cargo, órgão e serviços."""

    class Meta:
        model = TipoEvento
        fields = ["solicitante_padrao", "cargo_padrao", "orgao_padrao", "servicos_sugeridos"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        tipo = self.instance
        self.fields["orgao_padrao"].queryset = (
            OrgaoResponsavel.objects.filter(ativo=True)
            | OrgaoResponsavel.objects.filter(pk=tipo.orgao_padrao_id)
        ).distinct()
        self.fields["servicos_sugeridos"].queryset = (
            Servico.objects.filter(ativo=True) | tipo.servicos_sugeridos.all()
        ).distinct()


def _equipes_do_modelo(request, tipo, form):
    """Linhas de equipe do modelo; no POST, lê marcação e quantidade."""
    salvas = {item.equipe_id: item.quantidade for item in tipo.equipes_sugeridas.all()}
    equipes = (Equipe.objects.filter(ativo=True) | Equipe.objects.filter(pk__in=salvas)).distinct()
    linhas, escolhidas = [], {}
    marcadas = set(request.POST.getlist("equipes")) if request.method == "POST" else None
    for equipe in equipes.order_by("nome"):
        chave = str(equipe.pk)
        if marcadas is None:
            selecionada = equipe.pk in salvas
            quantidade = salvas.get(equipe.pk) or ""
        else:
            selecionada = chave in marcadas
            quantidade = str(request.POST.get(f"quantidade_{chave}", "")).strip()
            if selecionada:
                if quantidade and (not quantidade.isdigit() or int(quantidade) < 1):
                    form.add_error(None, f"Informe uma quantidade válida para {equipe}.")
                escolhidas[equipe.pk] = int(quantidade) if quantidade.isdigit() and int(quantidade) > 0 else None
        linhas.append(
            {"valor": chave, "rotulo": equipe.nome, "selecionada": selecionada, "quantidade": quantidade}
        )
    return linhas, escolhidas


@login_required
def modelo_tipo_evento(request, pk):
    """Modelo da solicitação de um tipo: sugerido na tela, aplicado com um clique."""
    _exigir_administrador(request, "tipos-evento")
    tipo = get_object_or_404(TipoEvento, pk=pk)
    form = ModeloTipoEventoForm(request.POST or None, instance=tipo)
    if request.method == "POST":
        form.full_clean()  # antes das equipes, que acrescentam os próprios erros
    linhas_equipes, escolhidas = _equipes_do_modelo(request, tipo, form)
    if request.method == "POST" and not form.errors:
        tipo = form.save()
        tipo.equipes_sugeridas.exclude(equipe_id__in=escolhidas).delete()
        for equipe_id, quantidade in escolhidas.items():
            TipoEventoEquipe.objects.update_or_create(
                tipo_evento=tipo, equipe_id=equipe_id, defaults={"quantidade": quantidade}
            )
        _registrar_auditoria(request.user, "CADASTRO_ATUALIZADO", tipo)
        messages.success(request, f"Modelo do tipo {tipo} salvo.")
        return redirect("cadastros:lista", slug="tipos-evento")
    marcados = {str(valor) for valor in (form["servicos_sugeridos"].value() or [])}
    valores = {
        nome: "" if form[nome].value() is None else str(form[nome].value())
        for nome in ["solicitante_padrao", "cargo_padrao", "orgao_padrao"]
    }
    return render(
        request,
        "pages/cadastros/modelo_tipo_evento.html",
        {
            "tipo": tipo,
            "form": form,
            "valores": valores,
            "erros": form.errors,
            "servicos": [
                {"valor": str(s.pk), "rotulo": s.nome, "marcado": str(s.pk) in marcados}
                for s in form.fields["servicos_sugeridos"].queryset.order_by("nome")
            ],
            "orgaos": [
                {"valor": str(o.pk), "rotulo": o.nome}
                for o in form.fields["orgao_padrao"].queryset.order_by("nome")
            ],
            "equipes": linhas_equipes,
            "breadcrumb": [
                {"label": "Tipos de evento", "url": reverse("cadastros:lista", args=["tipos-evento"])},
                {"label": f"Modelo — {tipo}"},
            ],
        },
    )
