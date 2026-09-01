"""CRUD dos cadastros de viagens.

Mesma forma do CRUD de cadastros de eventos — registro genérico por slug,
components do design system — com duas diferenças que o domínio exige:

- cada cadastro tem **form próprio** (CPF, placa e telefone têm validação de
  conteúdo, não cabem no ``modelform_factory``);
- a **tabela de diárias** tem tela separada, porque não é "nome + ativo": tem
  vigência, é dinheiro e só o gestor escreve nela.
"""

from django import forms
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.db.models import ProtectedError, Q
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.formats import number_format
from django.utils.http import urlencode
from django.views.decorators.http import require_POST

from auditoria.models import LogAuditoria

from .forms import (
    CargoForm,
    CombustivelForm,
    ServidorForm,
    TabelaDiariaForm,
    UnidadeForm,
    ViaturaForm,
)
from .models import Cargo, Combustivel, Servidor, TabelaDiaria, Unidade, Viatura
from .permissions import (
    acesso_ao_modulo,
    pode_editar_cadastros,
    pode_editar_diarias,
)

ITENS_POR_PAGINA = 20

CADASTROS = {
    "servidores": {
        "model": Servidor,
        "form": ServidorForm,
        "titulo": "Servidores",
        "singular": "servidor",
        "novo": "Novo servidor",
        "icone": "users",
        "cor": "#bea45a",
        "exemplo": "Ex.: MARIA DA SILVA",
        "busca": ["nome__icontains", "cpf__icontains"],
        "select_related": ["cargo", "unidade"],
        "colunas": [
            {"rotulo": "Cargo", "attr": "cargo"},
            {"rotulo": "Unidade", "attr": "unidade"},
            {"rotulo": "CPF", "attr": "cpf_formatado"},
        ],
    },
    "viaturas": {
        "model": Viatura,
        "form": ViaturaForm,
        "titulo": "Viaturas",
        "singular": "viatura",
        "novo": "Nova viatura",
        "icone": "truck",
        "cor": "#bea45a",
        "exemplo": "Ex.: ABC1D23",
        "busca": ["placa__icontains", "modelo__icontains"],
        "select_related": ["combustivel", "unidade"],
        "rotulo_principal": "Placa",
        "attr_principal": "placa_formatada",
        "colunas": [
            {"rotulo": "Modelo", "attr": "modelo"},
            {"rotulo": "Tipo", "attr": "get_tipo_display"},
            {"rotulo": "Unidade", "attr": "unidade"},
        ],
    },
    "unidades": {
        "model": Unidade,
        "form": UnidadeForm,
        "titulo": "Unidades",
        "singular": "unidade",
        "novo": "Nova unidade",
        "icone": "landmark",
        "cor": "#808080",
        "exemplo": "Ex.: DELEGACIA DE CURITIBA",
        "busca": ["nome__icontains", "sigla__icontains"],
        "colunas": [{"rotulo": "Sigla", "attr": "sigla"}],
    },
    "cargos": {
        "model": Cargo,
        "form": CargoForm,
        "titulo": "Cargos",
        "singular": "cargo",
        "novo": "Novo cargo",
        "icone": "shield",
        "cor": "#808080",
        "exemplo": "Ex.: INVESTIGADOR",
        "busca": ["nome__icontains"],
        "colunas": [{"rotulo": "Padrão", "attr": "is_padrao", "booleano": True}],
    },
    "combustiveis": {
        "model": Combustivel,
        "form": CombustivelForm,
        "titulo": "Combustíveis",
        "singular": "combustível",
        "novo": "Novo combustível",
        "icone": "activity",
        "cor": "#808080",
        "exemplo": "Ex.: GASOLINA",
        "busca": ["nome__icontains"],
        "colunas": [{"rotulo": "Padrão", "attr": "is_padrao", "booleano": True}],
    },
}


def _config(slug):
    if slug not in CADASTROS:
        raise Http404
    return CADASTROS[slug]


def _exigir_edicao(request):
    if not pode_editar_cadastros(request.user):
        raise PermissionDenied


def _registrar_auditoria(usuario, acao, objeto):
    LogAuditoria.objects.create(
        usuario=usuario,
        acao=acao,
        descricao=f"{objeto._meta.verbose_name} '{objeto}' (id {objeto.pk})",
    )


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
            "ajuda": campo.help_text,
            "valor": "" if valor is None else str(valor),
        }
        if isinstance(campo, forms.ModelMultipleChoiceField):
            selecionados = {str(item) for item in (valor or [])}
            descricao["tipo"] = "multiselect"
            descricao["opcoes"] = [
                {
                    "valor": str(obj.pk),
                    "rotulo": str(obj),
                    "selecionado": str(obj.pk) in selecionados,
                }
                for obj in campo.queryset
            ]
        elif isinstance(campo, forms.ModelChoiceField):
            descricao["tipo"] = "select"
            descricao["opcoes"] = [
                {"valor": str(obj.pk), "rotulo": str(obj)} for obj in campo.queryset
            ]
        elif isinstance(campo, forms.TypedChoiceField) or isinstance(
            campo, forms.ChoiceField
        ):
            descricao["tipo"] = "select"
            descricao["opcoes"] = [
                {"valor": str(chave), "rotulo": str(rotulo)}
                for chave, rotulo in campo.choices
                if chave != ""
            ]
        elif isinstance(campo, forms.BooleanField):
            descricao["tipo"] = "checkbox"
            descricao["marcado"] = bool(valor)
        elif isinstance(campo.widget, forms.DateInput):
            descricao["tipo"] = "data"
        else:
            descricao["tipo"] = "input"
        campos.append(descricao)
    return campos


def _linhas_da_lista(config, pagina):
    """Achata os objetos em linhas prontas: o template não chama método."""
    attr_principal = config.get("attr_principal", "nome")
    linhas = []
    for objeto in pagina:
        celulas = []
        for coluna in config["colunas"]:
            valor = getattr(objeto, coluna["attr"], "")
            if callable(valor):
                valor = valor()
            if coluna.get("booleano"):
                valor = "Sim" if valor else "—"
            celulas.append({"rotulo": coluna["rotulo"], "valor": valor or "—"})
        linhas.append(
            {
                "objeto": objeto,
                "principal": getattr(objeto, attr_principal, "") or "—",
                "celulas": celulas,
            }
        )
    return linhas


@acesso_ao_modulo
def index(request):
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
    grupos.append(
        {
            "slug": None,
            "titulo": "Tabela de diárias",
            "total": TabelaDiaria.objects.count(),
            "icone": "chart",
            "cor": "#bea45a",
            "url": reverse("viagens_cadastros:diarias"),
        }
    )
    return render(
        request,
        "pages/viagens_cadastros/index.html",
        {"grupos": grupos, "pode_editar": pode_editar_cadastros(request.user)},
    )


@acesso_ao_modulo
def lista(request, slug):
    config = _config(slug)
    queryset = config["model"].objects.all()
    if config.get("select_related"):
        queryset = queryset.select_related(*config["select_related"])
    termo = request.GET.get("q", "").strip()
    if termo:
        filtro = Q()
        for campo in config["busca"]:
            filtro |= Q(**{campo: termo})
        queryset = queryset.filter(filtro)
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
        "pages/viagens_cadastros/lista.html",
        {
            "slug": slug,
            "titulo": config["titulo"],
            "singular": config["singular"],
            "novo": config["novo"],
            "pagina": pagina,
            "linhas": _linhas_da_lista(config, pagina),
            "colunas": config["colunas"],
            "rotulo_principal": config.get("rotulo_principal", "Nome"),
            "termo": termo,
            "situacao": situacao,
            "tem_filtros": bool(termo or situacao),
            "pode_editar": pode_editar_cadastros(request.user),
            "opcoes_situacao": [
                {"valor": "ativos", "rotulo": "Ativos"},
                {"valor": "inativos", "rotulo": "Inativos"},
            ],
            "querystring": urlencode(parametros),
            "paginas_visiveis": list(
                paginator.get_elided_page_range(pagina.number, on_each_side=2, on_ends=1)
            ),
            "elipse": paginator.ELLIPSIS,
        },
    )


@acesso_ao_modulo
def editar(request, slug, pk=None):
    _exigir_edicao(request)
    config = _config(slug)
    instancia = get_object_or_404(config["model"], pk=pk) if pk else None
    FormClass = config["form"]
    if request.method == "POST":
        form = FormClass(request.POST, instance=instancia)
        if form.is_valid():
            objeto = form.save()
            _registrar_auditoria(
                request.user,
                "VIAGENS_CADASTRO_ATUALIZADO" if pk else "VIAGENS_CADASTRO_CRIADO",
                objeto,
            )
            messages.success(request, f"{config['titulo']}: registro salvo com sucesso.")
            return redirect("viagens_cadastros:lista", slug=slug)
        messages.error(request, "Corrija os campos destacados para continuar.")
    else:
        form = FormClass(instance=instancia)
    return render(
        request,
        "pages/viagens_cadastros/form.html",
        {
            "slug": slug,
            "titulo": config["titulo"],
            "instancia": instancia,
            "campos": _campos_para_template(form),
            "erros_gerais": form.non_field_errors(),
            "cartao_titulo": f"Editar {config['singular']}" if pk else config["novo"],
            "cartao_intro": (
                f"Informe os dados do cadastro de {config['singular']} usados "
                "nas viagens e nos documentos."
            ),
            "exemplo": config["exemplo"],
            "url_voltar": reverse("viagens_cadastros:lista", args=[slug]),
            "subtitulo_pagina": (
                "Atualize os dados deste registro"
                if pk
                else "Cadastre um registro do domínio de viagens"
            ),
            "breadcrumb": [
                {
                    "label": config["titulo"],
                    "url": reverse("viagens_cadastros:lista", args=[slug]),
                },
                {"label": "Editar registro" if pk else "Novo registro"},
            ],
        },
    )


@acesso_ao_modulo
@require_POST
def alternar_ativo(request, slug, pk):
    _exigir_edicao(request)
    config = _config(slug)
    objeto = get_object_or_404(config["model"], pk=pk)
    objeto.ativo = not objeto.ativo
    objeto.save(update_fields=["ativo", "atualizado_em"])
    _registrar_auditoria(
        request.user,
        "VIAGENS_CADASTRO_ATIVADO" if objeto.ativo else "VIAGENS_CADASTRO_INATIVADO",
        objeto,
    )
    messages.success(
        request,
        f"Registro {'ativado' if objeto.ativo else 'inativado'} com sucesso.",
    )
    return redirect("viagens_cadastros:lista", slug=slug)


@acesso_ao_modulo
@require_POST
def excluir(request, slug, pk):
    _exigir_edicao(request)
    config = _config(slug)
    objeto = get_object_or_404(config["model"], pk=pk)
    descricao = f"{objeto._meta.verbose_name} '{objeto}' (id {objeto.pk})"
    try:
        objeto.delete()
    except ProtectedError:
        messages.error(
            request,
            "Este registro não pode ser excluído porque está vinculado a "
            "viagens, solicitações ou a outros cadastros. Use a ação Inativar "
            "para retirá-lo dos novos formulários.",
        )
    else:
        LogAuditoria.objects.create(
            usuario=request.user,
            acao="VIAGENS_CADASTRO_EXCLUIDO",
            descricao=descricao,
        )
        messages.success(request, "Registro excluído com sucesso.")
    return redirect("viagens_cadastros:lista", slug=slug)


def _reais(valor):
    """Mesma formatação que o template aplica na tabela logo abaixo dos cartões.

    Um f-string cru escreveria "43.58" ao lado de um "43,58" renderizado pelo
    Django — dois números iguais com aparências diferentes na mesma tela.
    """
    return number_format(valor, decimal_pos=2, force_grouping=True)


@acesso_ao_modulo
def diarias(request):
    """Histórico de vigências, da mais recente para a mais antiga."""
    tabelas = TabelaDiaria.objects.all()
    hoje = timezone.localdate()
    vigentes = []
    for faixa, rotulo in TabelaDiaria.Faixa.choices:
        tabela = TabelaDiaria.vigente_em(faixa, hoje)
        vigentes.append(
            {
                "rotulo": rotulo,
                "tabela": tabela,
                "valor_24h": f"R$ {_reais(tabela.valor_24h)}" if tabela else "—",
                "resumo_percentuais": (
                    f"15%: R$ {_reais(tabela.valor_15)}"
                    f" · 30%: R$ {_reais(tabela.valor_30)}"
                    if tabela
                    else ""
                ),
            }
        )
    return render(
        request,
        "pages/viagens_cadastros/diarias.html",
        {
            "tabelas": tabelas,
            "vigentes": vigentes,
            "pode_editar": pode_editar_diarias(request.user),
        },
    )


@acesso_ao_modulo
def diaria_editar(request, pk=None):
    if not pode_editar_diarias(request.user):
        raise PermissionDenied
    instancia = get_object_or_404(TabelaDiaria, pk=pk) if pk else None
    if request.method == "POST":
        form = TabelaDiariaForm(request.POST, instance=instancia)
        if form.is_valid():
            tabela = form.save()
            _registrar_auditoria(
                request.user,
                "VIAGENS_DIARIA_ATUALIZADA" if pk else "VIAGENS_DIARIA_CRIADA",
                tabela,
            )
            messages.success(request, "Valores de diária salvos com sucesso.")
            return redirect("viagens_cadastros:diarias")
        messages.error(request, "Corrija os campos destacados para continuar.")
    else:
        form = TabelaDiariaForm(instance=instancia)
    return render(
        request,
        "pages/viagens_cadastros/form.html",
        {
            "titulo": "Tabela de diárias",
            "instancia": instancia,
            "campos": _campos_para_template(form),
            "erros_gerais": form.non_field_errors(),
            "cartao_titulo": "Editar vigência" if pk else "Nova vigência",
            "cartao_intro": (
                "Informe apenas o valor de 24 horas: os percentuais de 15% e "
                "30% são calculados e gravados a partir dele."
            ),
            "exemplo": "Ex.: 350,00",
            "url_voltar": reverse("viagens_cadastros:diarias"),
            "subtitulo_pagina": (
                "Atualize esta vigência" if pk else "Cadastre uma nova vigência"
            ),
            "breadcrumb": [
                {
                    "label": "Tabela de diárias",
                    "url": reverse("viagens_cadastros:diarias"),
                },
                {"label": "Editar vigência" if pk else "Nova vigência"},
            ],
        },
    )
