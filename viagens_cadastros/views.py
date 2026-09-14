"""CRUD dos cadastros de viagens.

Mesma forma do CRUD de cadastros de eventos — registro genérico por slug,
components do design system — com duas diferenças que o domínio exige:

- cada cadastro tem **form próprio** (CPF, placa e telefone têm validação de
  conteúdo, não cabem no ``modelform_factory``);
- a **tabela de diárias** tem tela separada, porque não é "nome + ativo": tem
  vigência, é dinheiro e só o gestor escreve nela.
"""

import unicodedata

from django import forms
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.db.models import PROTECT, RESTRICT, Count, ProtectedError, Q, RestrictedError
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.formats import number_format
from django.utils.http import urlencode, url_has_allowed_host_and_scheme
from django.views.decorators.http import require_http_methods

from auditoria.models import LogAuditoria

from .cep import CEPIndisponivel, CEPNaoEncontrado, consultar_cep
from core.normalizers import normalize_digits

from .forms import (
    CargoForm,
    CombustivelForm,
    ServidorForm,
    TabelaDiariaForm,
    UnidadeForm,
    UnidadeInclusaoForm,
    ViaturaForm,
)
from .models import Cargo, Combustivel, ConfiguracaoSistema, Servidor, TabelaDiaria, Unidade, Viatura
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


def _campo_para_template(form, nome, *, detalhes_unidade=False):
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
            {"valor": str(obj.pk), "rotulo": str(obj),
             **({"detalhes": obj.nome} if detalhes_unidade else {})}
            for obj in campo.queryset
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
    modulos = [
        {"titulo": "Servidores", "descricao": "Pessoas vinculadas aos fluxos.", "slug": "servidores", "iniciais": "SE"},
        {"titulo": "Cargos", "descricao": "Cargos utilizados em servidores.", "slug": "cargos", "iniciais": "CA"},
        {"titulo": "Viaturas", "descricao": "Veículos operacionais.", "slug": "viaturas", "iniciais": "VI"},
        {"titulo": "Combustíveis", "descricao": "Tipos de combustível.", "slug": "combustiveis", "iniciais": "CO"},
        {"titulo": "Unidades", "descricao": "Unidades administrativas.", "slug": "unidades", "iniciais": "UN"},
        {"titulo": "Configurações do sistema", "descricao": "Dados institucionais e assinaturas por tipo de documento.",
         "url": reverse("viagens_oficios:institucional"), "iniciais": "CO", "categoria": "Sistema"},
    ]
    return render(request, "pages/viagens_cadastros/index.html", {"modulos": modulos})


@acesso_ao_modulo
def lista(request, slug):
    config = _config(slug)
    if slug == "servidores":
        return _lista_servidores(request)
    if slug == "viaturas":
        return _lista_viaturas(request)
    if slug in {"cargos", "combustiveis", "unidades"}:
        return _lista_catalogo(request, slug)
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
    retorno = _retorno_cadastro(request)
    if retorno:
        parametros["next"] = retorno
    url_novo = reverse("viagens_cadastros:novo", args=[slug])
    if retorno:
        url_novo += "?" + urlencode({"next": retorno})
    return render(
        request,
        "pages/viagens_cadastros/lista.html",
        {
            "slug": slug,
            "titulo": config["titulo"],
            "singular": config["singular"],
            "novo": config["novo"],
            "url_novo": url_novo,
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
                paginator.get_elided_page_range(pagina.number, on_each_side=1, on_ends=1)
            ),
            "elipse": paginator.ELLIPSIS,
            "url_retorno": _retorno_cadastro(request),
        },
    )


def _retorno_cadastro(request):
    destino = request.POST.get("next") or request.GET.get("next", "")
    if destino and url_has_allowed_host_and_scheme(
        destino, allowed_hosts={request.get_host()}, require_https=request.is_secure()
    ):
        return destino
    return ""


def _texto_busca(valor):
    return "".join(
        letra for letra in unicodedata.normalize("NFKD", str(valor or ""))
        if not unicodedata.combining(letra)
    ).casefold()


def _url_catalogo(slug, retorno=""):
    url = reverse("viagens_cadastros:lista", args=[slug])
    return url + ("?" + urlencode({"next": retorno}) if retorno else "")


def _iniciais_catalogo(nome):
    partes = str(nome or "").split()
    if not partes:
        return "??"
    return (partes[0][:2] if len(partes) == 1 else partes[0][0] + partes[-1][0]).upper()


def _lista_viaturas(request):
    termo = request.GET.get("q", "").strip()
    base = Viatura.objects.select_related("combustivel", "unidade").prefetch_related("motoristas").order_by("placa")
    if termo:
        procurado = _texto_busca(termo)
        campos = ("pk", "placa", "modelo", "combustivel__nome", "tipo", "unidade__nome", "unidade__sigla", "motoristas__nome")
        ids = {linha[0] for linha in base.values_list(*campos)
               if any(procurado in _texto_busca(valor) for valor in linha[1:])}
        base = base.filter(pk__in=ids)

    def selecionado(nome, modelo):
        raw = request.GET.get(nome, "").strip()
        return modelo.objects.filter(pk=raw).first() if raw.isdecimal() and len(raw) < 19 else None

    combustivel = selecionado("combustivel", Combustivel)
    unidade = None if combustivel else selecionado("unidade", Unidade)
    # Consultar a configuração não cria um singleton ao abrir uma lista.
    cfg = ConfiguracaoSistema.objects.select_related("unidade").filter(chave=1).first()
    unidade_cfg = cfg.unidade if cfg else None
    combustiveis = Combustivel.objects.annotate(total=Count("viaturas")).filter(total__gt=0).order_by("-total", "nome")[:3]
    url_lista = reverse("viagens_cadastros:lista", args=["viaturas"])
    parametros = {"q": termo} if termo else {}

    def url_filtro(**extra):
        params = {**parametros, **extra}
        return url_lista + ("?" + urlencode(params) if params else "")

    filtros = [{"valor": url_filtro(), "rotulo": f"Todos ({base.count()})", "ativo": not combustivel and not unidade}]
    if unidade_cfg:
        filtros.append({"valor": url_filtro(unidade=unidade_cfg.pk),
                        "rotulo": f"{unidade_cfg.sigla or unidade_cfg.nome} ({base.filter(unidade=unidade_cfg).count()})",
                        "ativo": unidade == unidade_cfg})
    for item in combustiveis:
        filtros.append({"valor": url_filtro(combustivel=item.pk),
                        "rotulo": f"{item.nome} ({base.filter(combustivel=item).count()})",
                        "ativo": combustivel == item})
    if len(filtros) == 1:
        filtros = []
    queryset = base
    if combustivel:
        queryset = queryset.filter(combustivel=combustivel)
        parametros["combustivel"] = combustivel.pk
    elif unidade:
        queryset = queryset.filter(unidade=unidade)
        parametros["unidade"] = unidade.pk
    paginator = Paginator(queryset, 15)
    pagina = paginator.get_page(request.GET.get("page") or request.GET.get("pagina"))
    linhas = []
    for viatura in pagina:
        modelo = viatura.modelo.strip()
        titulo = f"{modelo} — {viatura.placa_formatada}" if modelo else viatura.placa_formatada
        linhas.append({"objeto": viatura, "titulo": titulo,
                       "iniciais": _iniciais_catalogo(modelo or viatura.placa_formatada),
                       "motoristas": ", ".join(m.nome for m in viatura.motoristas.all()) or "Nenhum motorista vinculado"})
    return render(request, "pages/viagens_cadastros/viaturas/lista.html", {
        "viaturas": linhas, "termo": termo, "combustivel": combustivel, "unidade": unidade,
        "filtros": filtros, "filtro_selecionado": next((f["valor"] for f in filtros if f["ativo"]), ""),
        "pagina": pagina, "querystring": urlencode(parametros),
        "paginas_visiveis": list(paginator.get_elided_page_range(pagina.number, on_each_side=1, on_ends=1)),
        "elipse": paginator.ELLIPSIS, "pode_editar": pode_editar_cadastros(request.user),
    })


def _lista_catalogo(request, slug):
    """Catálogos com campos explícitos e inclusão no próprio painel."""
    config = _config(slug)
    retorno = _retorno_cadastro(request)
    form_class = UnidadeInclusaoForm if slug == "unidades" else config["form"]
    form = form_class(request.POST if request.method == "POST" else None)
    if request.method == "POST":
        _exigir_edicao(request)
        if form.is_valid():
            objeto = form.save()
            _registrar_auditoria(request.user, "VIAGENS_CADASTRO_CRIADO", objeto)
            criado = "criada" if slug == "unidades" else "criado"
            messages.success(request, f"{config['singular'].capitalize()} {criado} com sucesso.")
            return redirect(_url_catalogo(slug, retorno))
    termo = request.GET.get("q", "").strip()
    queryset = config["model"].objects.order_by("nome")
    if termo:
        procurado = _texto_busca(termo)
        campos = ("pk", "nome", "sigla") if slug == "unidades" else ("pk", "nome")
        ids = [linha[0] for linha in queryset.values_list(*campos)
               if any(procurado in _texto_busca(valor) for valor in linha[1:])]
        queryset = queryset.filter(pk__in=ids)
    paginator = Paginator(queryset, 15)
    pagina = paginator.get_page(request.GET.get("page") or request.GET.get("pagina"))
    parametros = {"q": termo} if termo else {}
    if retorno:
        parametros["next"] = retorno
    return render(request, f"pages/viagens_cadastros/{slug}/lista.html", {
        "slug": slug, "titulo": config["titulo"], "singular": config["singular"],
        "form": form, "nome": _campo_para_template(form, "nome"),
        "sigla": _campo_para_template(form, "sigla") if slug == "unidades" else None,
        "tem_padrao": slug in {"cargos", "combustiveis"},
        "texto_vazio": "Nenhuma unidade cadastrada ainda." if slug == "unidades" else f"Nenhum {config['singular']} cadastrado ainda.",
        "termo": termo, "pagina": pagina,
        "itens": [{"objeto": item, "iniciais": "CT" if slug == "combustiveis" else _iniciais_catalogo((item.sigla or item.nome) if slug == "unidades" else item.nome)} for item in pagina],
        "pode_editar": pode_editar_cadastros(request.user),
        "url_retorno": retorno, "url_lista": _url_catalogo(slug, retorno),
        "rotulo_retorno": ("Voltar à viatura" if slug == "combustiveis" else
                           "Voltar ao servidor" if slug == "unidades" else
                           "Voltar ao servidor" if retorno.startswith("/viagens/cadastros/servidores/") else
                           "Voltar ao formulário"),
        "querystring": urlencode(parametros),
        "paginas_visiveis": list(paginator.get_elided_page_range(pagina.number, on_each_side=1, on_ends=1)),
        "elipse": paginator.ELLIPSIS,
    })


@acesso_ao_modulo
@require_http_methods(["GET", "POST"])
def definir_padrao(request, slug, pk):
    _exigir_edicao(request)
    if slug not in {"cargos", "combustiveis"}:
        raise Http404
    config = _config(slug)
    objeto = get_object_or_404(config["model"], pk=pk)
    if request.method == "POST":
        objeto.is_padrao = True
        # O modelo já troca o padrão anterior dentro de uma transação.
        objeto.save()
        _registrar_auditoria(request.user, "VIAGENS_CADASTRO_ATUALIZADO", objeto)
        messages.success(request, f"{config['singular'].capitalize()} definido como padrão com sucesso.")
    return redirect(_url_catalogo(slug, _retorno_cadastro(request)))


def _lista_servidores(request):
    termo = request.GET.get("q", "").strip()
    base = Servidor.objects.select_related("cargo", "unidade").order_by("nome")
    if termo:
        # A mesma busca sem acentos funciona nos bancos PostgreSQL e SQLite,
        # sem exigir extensão ou alterar os dados compartilhados de servidores.
        campos = ("pk", "nome", "cpf", "rg", "cargo__nome", "unidade__nome", "unidade__sigla")
        procurado = _texto_busca(termo)
        ids = [linha[0] for linha in base.values_list(*campos)
               if any(procurado in _texto_busca(valor) for valor in linha[1:])]
        base = base.filter(pk__in=ids)
    raw_cargo = request.GET.get("cargo", "")
    cargo = Cargo.objects.filter(pk=raw_cargo).first() if raw_cargo.isdecimal() and len(raw_cargo) < 19 else None
    parametros = {"q": termo} if termo else {}
    retorno = _retorno_cadastro(request)
    if retorno:
        parametros["next"] = retorno
    url_lista = reverse("viagens_cadastros:lista", args=["servidores"])

    def url_filtro(cargo_id=None):
        filtros = dict(parametros)
        if cargo_id:
            filtros["cargo"] = cargo_id
        return url_lista + ("?" + urlencode(filtros) if filtros else "")

    cargos = Cargo.objects.annotate(total=Count("servidores")).filter(total__gt=0).order_by("-total", "nome")[:3]
    filtros = [{"nome": "Todos", "total": base.count(), "url": url_filtro(), "ativo": cargo is None}]
    filtros.extend({"nome": item.nome, "total": base.filter(cargo=item).count(),
                    "url": url_filtro(item.pk), "ativo": cargo == item} for item in cargos)
    queryset = base.filter(cargo=cargo) if cargo else base
    if cargo:
        parametros["cargo"] = cargo.pk
    paginator = Paginator(queryset, 25)
    pagina = paginator.get_page(request.GET.get("page") or request.GET.get("pagina"))
    return render(request, "pages/viagens_cadastros/servidores/lista.html", {
        "pagina": pagina,
        "servidores": [{"objeto": item, "iniciais": _iniciais_catalogo(item.nome)} for item in pagina],
        "termo": termo, "cargo": cargo, "filtros_cargo": filtros if len(filtros) > 1 else [],
        "opcoes_cargo": [{"valor": item["url"], "rotulo": f"{item['nome']} ({item['total']})"} for item in filtros] if len(filtros) > 1 else [],
        "cargo_selecionado": next((item["url"] for item in filtros if item["ativo"]), ""),
        "filtro_cargo_rotulo": next((f"{item['nome']} ({item['total']})" for item in filtros if item["ativo"]), "Filtrar servidores por cargo"),
        "querystring": urlencode(parametros), "tem_filtros": bool(termo or cargo),
        "paginas_visiveis": list(paginator.get_elided_page_range(pagina.number, on_each_side=1, on_ends=1)),
        "elipse": paginator.ELLIPSIS, "pode_editar": pode_editar_cadastros(request.user),
        "url_retorno": retorno,
    })


@acesso_ao_modulo
def editar(request, slug, pk=None):
    _exigir_edicao(request)
    config = _config(slug)
    if slug in {"cargos", "combustiveis"} and pk is None:
        return _lista_catalogo(request, slug)
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
            if slug == "servidores":
                mensagem = (
                    "Servidor salvo como rascunho. Complete cargo e CPF quando possível."
                    if objeto.status == Servidor.Status.RASCUNHO else
                    "Servidor atualizado com sucesso." if pk else "Servidor criado com sucesso."
                )
                messages.success(request, mensagem)
            elif slug == "viaturas":
                mensagem = (
                    "Viatura salva como rascunho. Complete modelo, combustível e tipo quando possível."
                    if objeto.status == Viatura.Status.RASCUNHO else
                    "Viatura atualizada com sucesso." if pk else "Viatura criada com sucesso."
                )
                messages.success(request, mensagem)
            else:
                messages.success(request, f"{config['titulo']}: registro salvo com sucesso.")
            retorno = "" if pk and slug in {"servidores", "viaturas"} else _retorno_cadastro(request)
            return redirect(retorno) if retorno else redirect("viagens_cadastros:lista", slug=slug)
        if slug not in {"viaturas", "servidores"}:
            messages.error(request, "Corrija os campos destacados para continuar.")
    else:
        form = FormClass(instance=instancia)
    if slug == "viaturas":
        retorno = ("" if instancia else _retorno_cadastro(request)) or reverse("viagens_cadastros:lista", args=[slug])
        selecionados = {str(pk) for pk in (form["motoristas"].value() or [])}
        pessoas = []
        for servidor in form.fields["motoristas"].queryset:
            cargo = servidor.cargo.nome if servidor.cargo else ""
            unidade = (servidor.unidade.sigla or servidor.unidade.nome) if servidor.unidade else ""
            pessoas.append({"valor": str(servidor.pk), "nome": servidor.nome,
                            "detalhes": " • ".join(v for v in [cargo, unidade] if v),
                            "busca": _texto_busca(" ".join(v for v in [
                                servidor.nome, cargo,
                                servidor.cpf_formatado if servidor.cpf else "",
                                servidor.rg_formatado if servidor.rg or servidor.sem_rg else "",
                                unidade, servidor.unidade.nome if servidor.unidade else "",
                            ] if v)),
                            "iniciais": _iniciais_catalogo(servidor.nome),
                            "rascunho": servidor.status == Servidor.Status.RASCUNHO,
                            "selecionado": str(servidor.pk) in selecionados})
        return render(request, "pages/viagens_cadastros/viaturas/form.html", {
            "form": form, "instancia": instancia, "url_voltar": retorno,
            "placa": _campo_para_template(form, "placa"),
            "modelo": _campo_para_template(form, "modelo"),
            "tipo": _campo_para_template(form, "tipo"),
            "combustivel": _campo_para_template(form, "combustivel"),
            "unidade": _campo_para_template(form, "unidade", detalhes_unidade=True),
            "pessoas": pessoas, "motoristas_selecionados": bool(selecionados),
            "url_combustiveis": _url_catalogo("combustiveis", request.path),
            "url_unidades": _url_catalogo("unidades", request.path),
            "url_servidores": _url_catalogo("servidores", request.path),
            # Mantido para consumidores anteriores; o formulário não usa laço de campos.
            "campos": _campos_para_template(form),
        })
    if slug == "servidores":
        propria_url = request.path
        return render(request, "pages/viagens_cadastros/servidores/form.html", {
            "form": form, "instancia": instancia,
            "nome": _campo_para_template(form, "nome"),
            "cargo": _campo_para_template(form, "cargo"),
            "cpf": _campo_para_template(form, "cpf"),
            "rg": _campo_para_template(form, "rg"),
            "telefone": _campo_para_template(form, "telefone"),
            "unidade": _campo_para_template(form, "unidade", detalhes_unidade=True),
            "url_voltar": ("" if instancia else _retorno_cadastro(request)) or reverse("viagens_cadastros:lista", args=[slug]),
            "url_cargos": reverse("viagens_cadastros:lista", args=["cargos"]) + "?" + urlencode({"next": propria_url}),
            "url_unidades": reverse("viagens_cadastros:lista", args=["unidades"]) + "?" + urlencode({"next": propria_url}),
        })
    return render(
        request,
        "pages/viagens_cadastros/form.html",
        {
            "slug": slug,
            "url_retorno": _retorno_cadastro(request),
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
            "url_voltar": reverse("viagens_cadastros:lista", args=[slug]) + ("?" + urlencode({"next": _retorno_cadastro(request)}) if _retorno_cadastro(request) else ""),
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
    if slug == "viaturas" and request.method == "GET":
        return render(request, "pages/viagens_cadastros/viaturas/confirmar_exclusao.html", {
            "viatura": objeto, "url_voltar": reverse("viagens_cadastros:lista", args=[slug]),
        })
    return _excluir_catalogo(request, slug, objeto)


def _excluir_catalogo(request, slug, objeto):
    """O diálogo fica na lista; respostas de exclusão voltam ao catálogo."""
    voltar = _url_catalogo(slug, "" if slug == "viaturas" else _retorno_cadastro(request))
    if request.method == "GET":
        return redirect(voltar)
    mensagem_vinculo = (
        "Não foi possível excluir este cadastro porque ele está vinculado a outros registros."
    )
    if _dependencias_protegidas(objeto):
        messages.error(request, mensagem_vinculo)
        return redirect(voltar)
    descricao = f"{objeto._meta.verbose_name} '{objeto}' (id {objeto.pk})"
    try:
        objeto.delete()
    except (ProtectedError, RestrictedError):
        messages.error(request, mensagem_vinculo)
    else:
        LogAuditoria.objects.create(
            usuario=request.user, acao="VIAGENS_CADASTRO_EXCLUIDO", descricao=descricao,
        )
        excluido = "excluída" if slug in {"unidades", "viaturas"} else "excluído"
        messages.success(request, f"{CADASTROS[slug]['singular'].capitalize()} {excluido} com sucesso.")
    return redirect(voltar)


def _reais(valor):
    """Mesma formatação que o template aplica na tabela logo abaixo dos cartões.

    Um f-string cru escreveria "43.58" ao lado de um "43,58" renderizado pelo
    Django — dois números iguais com aparências diferentes na mesma tela.
    """
    return number_format(valor, decimal_pos=2, force_grouping=True)


@acesso_ao_modulo
@require_http_methods(["GET", "POST"])
def diarias(request):
    return _tela_diarias(request)


@acesso_ao_modulo
@require_http_methods(["GET", "POST"])
def diaria_editar(request, pk=None):
    if not pode_editar_diarias(request.user):
        raise PermissionDenied
    instancia = get_object_or_404(TabelaDiaria, pk=pk) if pk else None
    return _tela_diarias(request, instancia=instancia)


def _tela_diarias(request, *, instancia=None):
    pode_editar = pode_editar_diarias(request.user)
    if request.method == "POST" and not pode_editar:
        raise PermissionDenied
    form = TabelaDiariaForm(request.POST if request.method == "POST" else None, instance=instancia)
    if request.method == "POST" and form.is_valid():
        tabela = form.save()
        _registrar_auditoria(
            request.user,
            "VIAGENS_DIARIA_ATUALIZADA" if instancia else "VIAGENS_DIARIA_CRIADA",
            tabela,
        )
        messages.success(
            request,
            f"Valores de {tabela.get_faixa_display()} valendo a partir de "
            f"{tabela.vigencia_inicio:%d/%m/%Y}. Roteiros anteriores mantêm o valor da época.",
        )
        return redirect("viagens_cadastros:diarias")
    return render(request, "pages/viagens_cadastros/diarias.html", {
        "form": form, "instancia": instancia,
        "tabelas": TabelaDiaria.objects.all(), "pode_editar": pode_editar,
        "faixa": _campo_para_template(form, "faixa"),
        "vigencia": _campo_para_template(form, "vigencia_inicio"),
        "valor_24h": _campo_para_template(form, "valor_24h"),
        "url_voltar": reverse("viagens_cadastros:diarias") if instancia else "/",
        "url_salvar": (reverse("viagens_cadastros:diaria_editar", args=[instancia.pk]) if instancia
                       else reverse("viagens_cadastros:diarias")),
    })


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


@acesso_ao_modulo
@require_http_methods(["GET"])
def api_consulta_cep(request, cep):
    cep_limpo = normalize_digits(cep)
    if len(cep_limpo) != 8:
        return JsonResponse({"erro": "CEP deve ter 8 dígitos."}, status=400)
    try:
        dados = consultar_cep(cep_limpo)
    except CEPIndisponivel:
        return JsonResponse({"erro": "Erro ao consultar serviço externo de CEP."}, status=502)
    except CEPNaoEncontrado:
        return JsonResponse({"erro": "CEP não encontrado."}, status=404)
    return JsonResponse(dados)
