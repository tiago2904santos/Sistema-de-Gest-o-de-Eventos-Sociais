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
from django.db.models import PROTECT, RESTRICT, ProtectedError, Q
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.formats import number_format
from django.utils.http import urlencode
from django.views.decorators.http import require_http_methods

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
        "descricao": "Pessoas, documentos, contato e lotação usados nas viagens.",
        "exemplo": "Ex.: MARIA DA SILVA",
        "busca": ["nome__icontains", "cpf__icontains"],
        "select_related": ["cargo", "unidade"],
        "colunas": [
            {"rotulo": "Cargo", "attr": "cargo"},
            {"rotulo": "Unidade", "attr": "unidade"},
            {"rotulo": "CPF", "attr": "cpf_formatado"},
            {"rotulo": "Telefone", "attr": "telefone_formatado"},
        ],
        "secoes": [
            {
                "titulo": "Identificação funcional",
                "subtitulo": "Nome e cargo que aparecerão nos documentos oficiais.",
                "campos": ["nome", "cargo"],
            },
            {
                "titulo": "Documentos pessoais",
                "subtitulo": "CPF e RG são validados antes da gravação.",
                "campos": ["cpf", "rg"],
            },
            {
                "titulo": "Contato e lotação",
                "subtitulo": "Dados para comunicação e vínculo administrativo.",
                "campos": ["telefone", "unidade"],
            },
        ],
    },
    "viaturas": {
        "model": Viatura,
        "form": ViaturaForm,
        "titulo": "Viaturas",
        "singular": "viatura",
        "novo": "Nova viatura",
        "icone": "truck",
        "descricao": "Veículos, características, lotação e condutores autorizados.",
        "exemplo": "Ex.: ABC1D23",
        "busca": ["placa__icontains", "modelo__icontains"],
        "select_related": ["combustivel", "unidade"],
        "prefetch_related": ["motoristas"],
        "rotulo_principal": "Placa",
        "attr_principal": "placa_formatada",
        "colunas": [
            {"rotulo": "Modelo", "attr": "modelo"},
            {"rotulo": "Tipo", "attr": "get_tipo_display"},
            {"rotulo": "Combustível", "attr": "combustivel"},
            {"rotulo": "Unidade", "attr": "unidade"},
            {"rotulo": "Condutores", "attr": "motoristas", "contagem": True},
        ],
        "secoes": [
            {
                "titulo": "Identificação do veículo",
                "subtitulo": "Placa, modelo e tipo operacional.",
                "campos": ["placa", "modelo", "tipo"],
            },
            {
                "titulo": "Abastecimento e lotação",
                "subtitulo": "Referências usadas no planejamento da viagem.",
                "campos": ["combustivel", "unidade"],
            },
            {
                "titulo": "Condutores autorizados",
                "subtitulo": "Escolha todos os servidores que podem dirigir esta viatura.",
                "campos": ["motoristas"],
            },
        ],
    },
    "unidades": {
        "model": Unidade,
        "form": UnidadeForm,
        "titulo": "Unidades",
        "singular": "unidade",
        "novo": "Nova unidade",
        "icone": "landmark",
        "descricao": "Unidades administrativas e respectivos servidores lotados.",
        "exemplo": "Ex.: DELEGACIA DE CURITIBA",
        "busca": ["nome__icontains", "sigla__icontains"],
        "prefetch_related": ["servidores"],
        "colunas": [
            {"rotulo": "Sigla", "attr": "sigla"},
            {"rotulo": "Servidores", "attr": "servidores", "contagem": True},
        ],
        "secoes": [
            {
                "titulo": "Identificação da unidade",
                "subtitulo": "Nome por extenso e sigla institucional.",
                "campos": ["nome", "sigla"],
            },
            {
                "titulo": "Servidores lotados",
                "subtitulo": "Gerencie a lotação sem precisar editar cada pessoa separadamente.",
                "campos": ["servidores"],
            },
        ],
    },
    "cargos": {
        "model": Cargo,
        "form": CargoForm,
        "titulo": "Cargos",
        "singular": "cargo",
        "novo": "Novo cargo",
        "icone": "shield",
        "descricao": "Funções dos servidores e cargo sugerido nos novos cadastros.",
        "exemplo": "Ex.: INVESTIGADOR",
        "busca": ["nome__icontains"],
        "colunas": [{"rotulo": "Padrão", "attr": "is_padrao", "booleano": True}],
        "secoes": [
            {
                "titulo": "Dados do cargo",
                "subtitulo": "Defina o nome e, se desejar, marque-o como sugestão padrão.",
                "campos": ["nome", "is_padrao"],
            }
        ],
    },
    "combustiveis": {
        "model": Combustivel,
        "form": CombustivelForm,
        "titulo": "Combustíveis",
        "singular": "combustível",
        "novo": "Novo combustível",
        "icone": "activity",
        "descricao": "Tipos de combustível e opção sugerida nas novas viaturas.",
        "exemplo": "Ex.: GASOLINA",
        "busca": ["nome__icontains"],
        "colunas": [{"rotulo": "Padrão", "attr": "is_padrao", "booleano": True}],
        "secoes": [
            {
                "titulo": "Dados do combustível",
                "subtitulo": "Defina o nome e, se desejar, marque-o como sugestão padrão.",
                "campos": ["nome", "is_padrao"],
            }
        ],
    },
}

DIARIA_SECOES = [
    {
        "titulo": "Vigência e faixa",
        "subtitulo": "Escolha onde o valor se aplica e a data em que passa a valer.",
        "campos": ["faixa", "vigencia_inicio"],
    },
    {
        "titulo": "Valor-base",
        "subtitulo": "Os valores de 15% e 30% serão calculados automaticamente.",
        "campos": ["valor_24h"],
        "preview_diaria": True,
    },
]


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


def _iniciais(nome):
    partes = [parte for parte in str(nome).split() if parte]
    return "".join(parte[0] for parte in partes[:2]).upper()


def _campo_para_template(form, nome):
    """Descreve um campo sem perder atributos e estados do ModelForm."""
    campo = form.fields[nome]
    bound = form[nome]
    valor = bound.value()
    attrs = campo.widget.attrs
    descricao = {
        "name": nome,
        "label": campo.label,
        "obrigatorio": campo.required,
        "erros": form.errors.get(nome),
        "ajuda": campo.help_text,
        "valor": "" if valor is None else str(valor),
        "placeholder": attrs.get("placeholder", ""),
        "inputmode": attrs.get("inputmode", ""),
        "autocomplete": attrs.get("autocomplete", ""),
        "maxlength": attrs.get("maxlength", ""),
        "step": attrs.get("step", ""),
        "min": attrs.get("min", ""),
        "mascara": attrs.get("data-mask", ""),
        "uppercase": attrs.get("data-uppercase") == "true",
    }
    if isinstance(campo, forms.ModelMultipleChoiceField):
        selecionados = {str(item) for item in (valor or [])}
        descricao["tipo"] = "multiselect"
        opcoes = []
        for obj in campo.queryset:
            detalhes = []
            if getattr(obj, "cargo_id", None):
                detalhes.append(str(obj.cargo))
            if getattr(obj, "unidade_id", None):
                detalhes.append(str(obj.unidade))
            opcoes.append(
                {
                    "valor": str(obj.pk),
                    "rotulo": str(obj),
                    "detalhes": " · ".join(detalhes),
                    "iniciais": _iniciais(obj),
                    "selecionado": str(obj.pk) in selecionados,
                }
            )
        descricao["opcoes"] = opcoes
        descricao["selecionados"] = len(selecionados)
    elif isinstance(campo, forms.ModelChoiceField):
        descricao["tipo"] = "select"
        descricao["pesquisavel"] = campo.queryset.count() > 8
        descricao["placeholder"] = campo.empty_label or "Selecione..."
        descricao["opcoes"] = [
            {"valor": str(obj.pk), "rotulo": str(obj)} for obj in campo.queryset
        ]
    elif isinstance(campo, (forms.TypedChoiceField, forms.ChoiceField)):
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
        descricao["tipo"] = getattr(campo.widget, "input_type", "text") or "text"
    return descricao


def _secoes_para_template(form, definicoes):
    """Agrupa os campos na ordem editorial da tela."""
    secoes = []
    incluidos = set()
    for numero, definicao in enumerate(definicoes, start=1):
        nomes = [nome for nome in definicao["campos"] if nome in form.fields]
        incluidos.update(nomes)
        secao = {**definicao, "numero": numero}
        secao["campos"] = [_campo_para_template(form, nome) for nome in nomes]
        secoes.append(secao)
    restantes = [nome for nome in form.fields if nome not in incluidos]
    if restantes:
        secoes.append(
            {
                "numero": len(secoes) + 1,
                "titulo": "Outros dados",
                "subtitulo": "Informações complementares do registro.",
                "campos": [_campo_para_template(form, nome) for nome in restantes],
            }
        )
    return secoes


def _campos_para_template(form):
    """Compatibilidade para testes e consumidores que usam a lista plana."""
    campos = []
    for nome, campo in form.fields.items():
        campos.append(_campo_para_template(form, nome))
    return campos


def _linhas_da_lista(config, pagina):
    """Achata os objetos em linhas prontas: o template não chama método."""
    attr_principal = config.get("attr_principal", "nome")
    linhas = []
    for objeto in pagina:
        celulas = []
        for coluna in config["colunas"]:
            valor = getattr(objeto, coluna["attr"], "")
            if coluna.get("contagem"):
                valor = valor.count()
                valor = f"{valor} vinculado{'s' if valor != 1 else ''}"
            elif callable(valor):
                valor = valor()
            if coluna.get("booleano"):
                valor = "Sim" if valor else "—"
            celulas.append({"rotulo": coluna["rotulo"], "valor": valor or "—"})
        linhas.append(
            {
                "objeto": objeto,
                "principal": getattr(objeto, attr_principal, "") or "—",
                "celulas": celulas,
                "status": getattr(objeto, "status", ""),
                "status_label": (
                    objeto.get_status_display() if getattr(objeto, "status", "") else ""
                ),
            }
        )
    return linhas


@acesso_ao_modulo
def index(request):
    pode_criar_cadastros = pode_editar_cadastros(request.user)
    grupos = [
        {
            "slug": slug,
            "titulo": config["titulo"],
            "total": config["model"].objects.count(),
            "icone": config["icone"],
            "descricao": config["descricao"],
            "url_novo": reverse("viagens_cadastros:novo", args=[slug]),
            "pode_criar": pode_criar_cadastros,
        }
        for slug, config in CADASTROS.items()
    ]
    grupos.append(
        {
            "slug": None,
            "titulo": "Tabela de diárias",
            "total": TabelaDiaria.objects.count(),
            "icone": "chart",
            "descricao": "Valores por faixa e histórico completo de vigências.",
            "url": reverse("viagens_cadastros:diarias"),
            "url_novo": reverse("viagens_cadastros:diaria_nova"),
            "pode_criar": pode_editar_diarias(request.user),
        }
    )
    return render(
        request,
        "pages/viagens_cadastros/index.html",
        {"grupos": grupos},
    )


@acesso_ao_modulo
def lista(request, slug):
    config = _config(slug)
    queryset = config["model"].objects.all()
    if config.get("select_related"):
        queryset = queryset.select_related(*config["select_related"])
    if config.get("prefetch_related"):
        queryset = queryset.prefetch_related(*config["prefetch_related"])
    termo = request.GET.get("q", "").strip()
    if termo:
        filtro = Q()
        for campo in config["busca"]:
            filtro |= Q(**{campo: termo})
        queryset = queryset.filter(filtro)
    paginator = Paginator(queryset, ITENS_POR_PAGINA)
    pagina = paginator.get_page(request.GET.get("pagina"))
    parametros = {}
    if termo:
        parametros["q"] = termo
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
            "tem_filtros": bool(termo),
            "pode_editar": pode_editar_cadastros(request.user),
            "icone": config["icone"],
            "descricao": config["descricao"],
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
            "secoes": _secoes_para_template(form, config["secoes"]),
            "erros_gerais": form.non_field_errors(),
            "tem_erros": bool(form.errors),
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


def _dependencias_protegidas(objeto):
    """Resume vínculos que impedem exclusão, antes de o usuário confirmar."""
    dependencias = []
    for relacao in objeto._meta.related_objects:
        if relacao.on_delete not in {PROTECT, RESTRICT}:
            continue
        try:
            relacionado = getattr(objeto, relacao.get_accessor_name())
            if relacao.one_to_one:
                itens = [relacionado]
                total = 1
            else:
                consulta = relacionado.all()
                total = consulta.count()
                itens = list(consulta[:3])
        except relacao.related_model.DoesNotExist:
            continue
        if not total:
            continue
        nome = relacao.related_model._meta.verbose_name_plural
        dependencias.append(
            {
                "nome": str(nome).capitalize(),
                "total": total,
                "amostras": [str(item) for item in itens],
            }
        )
    return dependencias


def _contexto_exclusao(*, objeto, titulo, voltar, dependencias, diaria=False):
    return {
        "objeto": objeto,
        "titulo": titulo,
        "url_voltar": voltar,
        "dependencias": dependencias,
        "bloqueada": bool(dependencias),
        "diaria": diaria,
        "breadcrumb": [
            {"label": titulo, "url": voltar},
            {"label": "Excluir registro"},
        ],
    }


@acesso_ao_modulo
@require_http_methods(["GET", "POST"])
def excluir(request, slug, pk):
    _exigir_edicao(request)
    config = _config(slug)
    objeto = get_object_or_404(config["model"], pk=pk)
    voltar = reverse("viagens_cadastros:lista", args=[slug])
    dependencias = _dependencias_protegidas(objeto)
    if request.method == "GET" or dependencias:
        if request.method == "POST" and dependencias:
            messages.error(
                request,
                "A exclusão foi bloqueada porque este registro ainda possui vínculos.",
            )
        return render(
            request,
            "pages/viagens_cadastros/confirmar_exclusao.html",
            _contexto_exclusao(
                objeto=objeto,
                titulo=config["titulo"],
                voltar=voltar,
                dependencias=dependencias,
            ),
        )
    descricao = f"{objeto._meta.verbose_name} '{objeto}' (id {objeto.pk})"
    try:
        objeto.delete()
    except ProtectedError:
        messages.error(
            request,
            "Este registro ganhou um novo vínculo e não pôde ser excluído. "
            "Revise os registros relacionados e tente novamente.",
        )
    else:
        LogAuditoria.objects.create(
            usuario=request.user,
            acao="VIAGENS_CADASTRO_EXCLUIDO",
            descricao=descricao,
        )
        messages.success(request, "Registro excluído com sucesso.")
    return redirect(voltar)


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
            "secoes": _secoes_para_template(form, DIARIA_SECOES),
            "erros_gerais": form.non_field_errors(),
            "tem_erros": bool(form.errors),
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


@acesso_ao_modulo
@require_http_methods(["GET", "POST"])
def diaria_excluir(request, pk):
    if not pode_editar_diarias(request.user):
        raise PermissionDenied
    tabela = get_object_or_404(TabelaDiaria, pk=pk)
    voltar = reverse("viagens_cadastros:diarias")
    if request.method == "GET":
        return render(
            request,
            "pages/viagens_cadastros/confirmar_exclusao.html",
            _contexto_exclusao(
                objeto=tabela,
                titulo="Tabela de diárias",
                voltar=voltar,
                dependencias=[],
                diaria=True,
            ),
        )
    descricao = f"{tabela._meta.verbose_name} '{tabela}' (id {tabela.pk})"
    tabela.delete()
    LogAuditoria.objects.create(
        usuario=request.user,
        acao="VIAGENS_DIARIA_EXCLUIDA",
        descricao=descricao,
    )
    messages.success(request, "Vigência excluída com sucesso.")
    return redirect(voltar)
