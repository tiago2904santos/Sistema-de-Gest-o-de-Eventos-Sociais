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
from viagens_oficios.forms import ModeloJustificativaForm, ModeloMotivoOficioForm
from viagens_prestacoes.forms import ModeloTextoRelatorioTecnicoForm
from viagens_prestacoes.models import ModeloTextoRelatorioTecnico
from viagens_oficios.models import ModeloJustificativa, ModeloMotivoOficio

from .cep import CEPIndisponivel, CEPNaoEncontrado, consultar_cep
from core.normalizers import normalize_digits

from .forms import (
    CargoForm,
    CombustivelForm,
    ServidorForm,
    TabelaDiariaForm,
    UnidadeForm,
    ViaturaForm,
)
from .models import Cargo, Combustivel, ConfiguracaoSistema, Servidor, TabelaDiaria, Unidade, Viatura, setor_de_viagens
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
        "busca_rotulo": "Buscar servidor por nome, CPF, cargo ou unidade",
        "vazio": "Nenhum servidor cadastrado ainda.",
        "intro_modal": "Só o nome é obrigatório; documentos e lotação podem ser completados depois.",
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
            # Documentos e telefone não quebram linha na tabela.
            {"rotulo": "CPF", "attr": "cpf_formatado", "classe": "c-fixo"},
            {"rotulo": "RG", "attr": "rg_formatado", "classe": "c-fixo"},
            {"rotulo": "Telefone", "attr": "telefone_formatado", "classe": "c-fixo"},
        ],
        "secoes": [
            {
                "titulo": "Dados do servidor",
                "subtitulo": "Identificação, documentos e lotação.",
                "campos": ["nome", "cargo", "cpf", "rg", "telefone", "unidade"],
                # Uma linha para identificação, uma para documentos e contato,
                # e a lotação fechando o formulário.
                "larguras": {"nome": "6", "cargo": "6", "cpf": "4", "rg": "4",
                             "telefone": "4", "unidade": "12"},
            },
        ],
    },
    "viaturas": {
        "model": Viatura,
        "form": ViaturaForm,
        "busca_rotulo": "Buscar viatura por placa, modelo, combustível ou condutor",
        "vazio": "Nenhuma viatura cadastrada ainda.",
        "intro_modal": "Só a placa é obrigatória; modelo, tipo e condutores podem ser completados depois.",
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
            {"rotulo": "Condutores", "attr": "motoristas", "nomes": True,
             "vazio": "Nenhum motorista vinculado"},
        ],
        "secoes": [
            {
                "titulo": "Dados da viatura",
                "subtitulo": "Identificação, abastecimento e lotação.",
                "campos": ["placa", "modelo", "tipo", "combustivel", "unidade"],
                "larguras": {"placa": "4", "modelo": "4", "tipo": "4",
                             "combustivel": "6", "unidade": "6"},
            },
            {
                "titulo": "Condutores autorizados",
                "subtitulo": "Servidores que podem dirigir esta viatura.",
                "campos": ["motoristas"],
            },
        ],
    },
    "unidades": {
        "model": Unidade,
        "form": UnidadeForm,
        "busca_rotulo": "Buscar unidade por nome ou sigla",
        "vazio": "Nenhuma unidade cadastrada ainda.",
        "intro_modal": "Nome por extenso e sigla da unidade. A lotação é definida no cadastro do servidor.",
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
                "titulo": "Dados da unidade",
                "subtitulo": "Nome por extenso e sigla institucional. A lotação é definida no cadastro do servidor.",
                "campos": ["nome", "sigla"],
                "larguras": {"nome": "8", "sigla": "4"},
            },
        ],
    },
    "cargos": {
        "model": Cargo,
        "form": CargoForm,
        "busca_rotulo": "Buscar cargo pelo nome",
        "vazio": "Nenhum cargo cadastrado ainda.",
        "intro_modal": "Nome do cargo usado nos servidores e nos documentos.",
        "titulo": "Cargos",
        "singular": "cargo",
        "novo": "Novo cargo",
        "icone": "shield",
        "descricao": "Funções dos servidores e cargo sugerido nos novos cadastros.",
        "exemplo": "Ex.: INVESTIGADOR",
        "busca": ["nome__icontains"],
        "colunas": [],
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
        "busca_rotulo": "Buscar combustível pelo nome",
        "vazio": "Nenhum combustível cadastrado ainda.",
        "intro_modal": "Nome do combustível usado nas viaturas.",
        "titulo": "Combustíveis",
        "singular": "combustível",
        "novo": "Novo combustível",
        "icone": "activity",
        "descricao": "Tipos de combustível e opção sugerida nas novas viaturas.",
        "exemplo": "Ex.: GASOLINA",
        "busca": ["nome__icontains"],
        "colunas": [],
        "secoes": [
            {
                "titulo": "Dados do combustível",
                "subtitulo": "Defina o nome e, se desejar, marque-o como sugestão padrão.",
                "campos": ["nome", "is_padrao"],
            }
        ],
    },
    # Catálogos dos ofícios (Meta 3): vivem em `/oficios/modelos-motivo/` e
    # `/justificativas/modelos/` na origem, e aqui seguem o mesmo padrão de
    # lista, modal, padrão e exclusão dos demais cadastros. Não entram no
    # trilho nem nos cartões da entrada de Cadastros, que a Meta 1 certificou
    # com os seis grupos da origem.
    "motivos-oficio": {
        "model": ModeloMotivoOficio,
        "form": ModeloMotivoOficioForm,
        "busca_rotulo": "Buscar modelo de motivo pelo nome",
        "vazio": "Nenhum modelo de motivo cadastrado ainda.",
        "intro_modal": "Nome curto para escolher no ofício e o texto que vai para o campo Motivo. O padrão é sugerido em todo ofício novo.",
        "titulo": "Motivos de ofício",
        "singular": "modelo de motivo",
        "novo": "Novo modelo de motivo",
        "icone": "document",
        "descricao": "Textos reutilizáveis para o motivo do ofício.",
        "exemplo": "Ex.: COBERTURA JORNALÍSTICA",
        "busca": ["nome__icontains", "texto__icontains"],
        "situacao_ativo": True,
        "colunas": [
            {"rotulo": "Ordem", "attr": "ordem"},        ],
        "secoes": [
            {
                "titulo": "Modelo de motivo",
                "subtitulo": "Nome, texto e ordem de exibição; marque-o como padrão para ser sugerido nos novos ofícios.",
                "campos": ["nome", "texto", "ordem", "ativo", "is_padrao"],
                "larguras": {"nome": "8", "ordem": "4"},
            }
        ],
    },
    "modelos-justificativa": {
        "model": ModeloJustificativa,
        "form": ModeloJustificativaForm,
        "busca_rotulo": "Buscar modelo de justificativa pelo nome",
        "vazio": "Nenhum modelo de justificativa cadastrado ainda.",
        "intro_modal": "Nome curto para escolher no ofício e o texto da justificativa. O padrão é sugerido quando a justificativa é exigida.",
        "titulo": "Modelos de justificativa",
        "singular": "modelo de justificativa",
        "novo": "Novo modelo de justificativa",
        "icone": "document",
        "descricao": "Textos reutilizáveis para a justificativa de prazo do ofício.",
        "exemplo": "Ex.: DEMANDA URGENTE",
        "busca": ["nome__icontains", "texto__icontains"],
        "situacao_ativo": True,
        "colunas": [
            {"rotulo": "Ordem", "attr": "ordem"},        ],
        "secoes": [
            {
                "titulo": "Modelo de justificativa",
                "subtitulo": "Nome, texto e ordem de exibição; marque-o como padrão para ser sugerido nos ofícios que exigem justificativa.",
                "campos": ["nome", "texto", "ordem", "ativo", "is_padrao"],
                "larguras": {"nome": "8", "ordem": "4"},
            }
        ],
    },
    "modelos-texto-rt": {
        "model": ModeloTextoRelatorioTecnico,
        "form": ModeloTextoRelatorioTecnicoForm,
        "busca_rotulo": "Buscar modelo de texto pelo nome",
        "vazio": "Nenhum modelo de texto cadastrado ainda.",
        "intro_modal": "Escolha o campo do relatório técnico, dê um nome curto e escreva o texto que será copiado para o campo.",
        "titulo": "Modelos de texto do RT",
        "singular": "modelo de texto",
        "novo": "Novo modelo de texto",
        "icone": "document",
        "descricao": "Textos reutilizáveis para os campos do relatório técnico.",
        "exemplo": "Ex.: PARTICIPAÇÃO EM EVENTO",
        "busca": ["nome__icontains", "texto__icontains"],
        "colunas": [
            {"rotulo": "Campo", "attr": "get_campo_display"},
            {"rotulo": "Ordem", "attr": "ordem"},
        ],
        "secoes": [
            {
                "titulo": "Modelo de texto",
                "subtitulo": "O campo do relatório em que o modelo entra, o nome e o texto.",
                "campos": ["campo", "ordem", "nome", "texto"],
                "larguras": {"campo": "8", "ordem": "4"},
            }
        ],
    },
}

DIARIAS = {
    "model": TabelaDiaria,
    "form": TabelaDiariaForm,
    "titulo": "Diárias",
    "singular": "vigência",
    "novo": "Nova vigência",
    "rotulo_principal": "Faixa",
    "colunas": [
        {"rotulo": "Vigente a partir de"},
        {"rotulo": "24 horas"},
        {"rotulo": "15%"},
        {"rotulo": "30%"},
    ],
    "busca_rotulo": "",
    "vazio": "Nenhuma vigência cadastrada.",
    "intro_modal": (
        "Informe apenas o valor de 24 horas; 15% e 30% são calculados. A tabela "
        "passa a valer hoje e roteiros com saída anterior mantêm o valor da época."
    ),
}

DIARIA_SECOES = [
    {
        "titulo": "Valor da diária",
        "subtitulo": (
            "A tabela passa a valer hoje; roteiros com saída anterior mantêm o "
            "valor que valia na época."
        ),
        "campos": ["faixa", "valor_24h"],
        "larguras": {"faixa": "6", "valor_24h": "6"},
        "preview_diaria": True,
    },
]

DIARIAS["secoes"] = DIARIA_SECOES


# Catálogos com "usar como padrão" no menu da linha.
CATALOGOS_DE_OFICIO = {"motivos-oficio", "modelos-justificativa"}
# Modelos de texto: vivem na seção "Modelos" da navegação, com trilha própria.
CATALOGOS_DE_MODELO = ("motivos-oficio", "modelos-justificativa", "modelos-texto-rt")
COM_PADRAO = {"cargos", "combustiveis", *CATALOGOS_DE_OFICIO}


def _config(slug):
    if slug not in CADASTROS:
        raise Http404
    return CADASTROS[slug]


# Trilha lateral dos cadastros de viagens, no mesmo formato da trilha de
# Eventos: um item por tabela, com o total de registros. Cidades e Estados são
# bases compartilhadas com Eventos e têm rota própria; diárias também.
RAIL = [
    ("servidores", "Servidores", "users"),
    ("viaturas", "Viaturas", "truck"),
    ("unidades", "Unidades", "landmark"),
    ("cargos", "Cargos", "shield"),
    ("combustiveis", "Combustíveis", "activity"),
]


# Rótulo de contagem de cada tabela: "5 registros cadastrados" não serve para
# viatura nem unidade, que são femininas — singular e plural vêm escritos.
CONTAGEM_CARTAO = {
    "servidores": ("servidor cadastrado", "servidores cadastrados"),
    "viaturas": ("viatura cadastrada", "viaturas cadastradas"),
    "unidades": ("unidade cadastrada", "unidades cadastradas"),
    "cargos": ("cargo cadastrado", "cargos cadastrados"),
    "combustiveis": ("combustível cadastrado", "combustíveis cadastrados"),
    "diarias": ("vigência cadastrada", "vigências cadastradas"),
    "motivos-oficio": ("modelo cadastrado", "modelos cadastrados"),
    "modelos-justificativa": ("modelo cadastrado", "modelos cadastrados"),
    "modelos-texto-rt": ("modelo cadastrado", "modelos cadastrados"),
}


def _palavras(total, slug):
    """"servidores cadastrados" / "servidor cadastrado" — sem adivinhar plural."""
    singular, plural = CONTAGEM_CARTAO[slug]
    return singular if total == 1 else plural


def _grupos():
    grupos = [
        {
            "slug": slug,
            "titulo": titulo,
            "icone": icone,
            "total": CADASTROS[slug]["model"].objects.count(),
            "url": reverse("viagens_cadastros:lista", args=[slug]),
        }
        for slug, titulo, icone in RAIL
    ]
    grupos.append({
        "slug": "diarias", "titulo": "Diárias", "icone": "chart",
        "total": TabelaDiaria.objects.count(),
        "url": reverse("viagens_cadastros:diarias"),
    })
    return grupos


def _grupos_modelos():
    """Trilha da seção Modelos: um item por catálogo de texto."""
    return [
        {
            "slug": slug,
            "titulo": CADASTROS[slug]["titulo"],
            "icone": CADASTROS[slug]["icone"],
            "total": CADASTROS[slug]["model"].objects.count(),
            "url": reverse("viagens_cadastros:lista", args=[slug]),
        }
        for slug in CATALOGOS_DE_MODELO
    ]


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
        "diaria_base": attrs.get("data-diaria-base") == "true",
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
    elif isinstance(campo.widget, forms.Textarea):
        descricao["tipo"] = "textarea"
        descricao["linhas"] = attrs.get("rows", "4")
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
        larguras = definicao.get("larguras", {})
        secao["campos"] = []
        for nome in nomes:
            campo = _campo_para_template(form, nome)
            campo["largura"] = larguras.get(nome, "")
            secao["campos"].append(campo)
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


SITUACAO_CHIP = {"RASCUNHO": "st--rascunho", "COMPLETO": "st--ativo"}


def _linhas_da_lista(config, slug, pagina, *, tem_acoes=True, retorno="", padrao=False):
    """Achata os objetos em linhas prontas: o template não chama método."""
    attr_principal = config.get("attr_principal", "nome")
    sufixo = "?" + urlencode({"next": retorno}) if retorno else ""
    linhas = []
    for objeto in pagina:
        celulas = []
        for coluna in config["colunas"]:
            valor = getattr(objeto, coluna["attr"], "")
            if coluna.get("contagem"):
                valor = valor.count()
                valor = f"{valor} vinculado{'s' if valor != 1 else ''}"
            elif coluna.get("nomes"):
                valor = ", ".join(str(item) for item in valor.all())
            elif callable(valor):
                valor = valor()
            if coluna.get("booleano"):
                valor = "Sim" if valor else "—"
            celulas.append({"rotulo": coluna["rotulo"], "valor": valor or coluna.get("vazio", "—"),
                            "classe": coluna.get("classe", "")})
        principal = getattr(objeto, attr_principal, "") or "—"
        status = getattr(objeto, "status", "")
        badge = {"texto": objeto.get_status_display(), "classe": SITUACAO_CHIP.get(status, "")} if status else None
        if badge is None and config.get("situacao_ativo"):
            ativo = bool(getattr(objeto, "ativo", True))
            badge = {"texto": "Ativo" if ativo else "Inativo", "classe": "st--ativo" if ativo else "st--inativo"}
        linhas.append(
            {
                "objeto": objeto,
                "principal": principal,
                "nome": str(principal),
                "celulas": celulas,
                "status": status,
                "status_label": objeto.get_status_display() if status else "",
                "badge": badge,
                # Registro sugerido nos formulários: vira chip ao lado do nome.
                "padrao": bool(getattr(objeto, "is_padrao", False)),
                "url_editar": reverse("viagens_cadastros:editar", args=[slug, objeto.pk]) + sufixo if tem_acoes else "",
                "url_excluir": reverse("viagens_cadastros:excluir", args=[slug, objeto.pk]) + sufixo if tem_acoes else "",
                "url_padrao": (
                    reverse("viagens_cadastros:definir_padrao", args=[slug, objeto.pk])
                    if padrao and tem_acoes and not objeto.is_padrao else ""
                ),
            }
        )
    return linhas


def _contexto_lista(request, slug, config, *, pagina, linhas, termo, parametros,
                    tem_acoes, tem_filtros=False, tem_situacao=False,
                    acoes_template="", retorno="", texto_vazio="", modal=None):
    """Chassi comum das listas: trilha, resumo, busca, tabela e paginação."""
    url_lista = reverse("viagens_cadastros:lista", args=[slug]) if slug in CADASTROS else request.path
    total = config["model"].objects.count()
    ocultos = [{"nome": nome, "valor": valor} for nome, valor in parametros.items() if nome != "q"]
    return {
        "slug": slug,
        "grupos": _grupos_modelos() if slug in CATALOGOS_DE_MODELO else _grupos(),
        "secao_titulo": "Modelos" if slug in CATALOGOS_DE_MODELO else "Cadastros",
        "titulo": config["titulo"],
        "singular": config["singular"],
        "novo": config["novo"],
        "total_registros": total,
        "resumo": _palavras(total, slug),
        "rotulo_principal": config.get("rotulo_principal", "Nome"),
        "colunas": config["colunas"],
        "linhas": linhas,
        "pagina": pagina,
        "paginas_visiveis": list(
            pagina.paginator.get_elided_page_range(pagina.number, on_each_side=1, on_ends=1)
        ),
        "elipse": pagina.paginator.ELLIPSIS,
        "querystring": urlencode(parametros),
        "campos_ocultos": ocultos,
        "termo": termo,
        "tem_filtros": tem_filtros,
        "tem_situacao": tem_situacao,
        "tem_acoes": tem_acoes,
        "acoes_template": acoes_template,
        "placeholder_busca": config["busca_rotulo"],
        "texto_vazio": texto_vazio or config["vazio"],
        "pode_editar": tem_acoes,
        "url_novo": (
            reverse("viagens_cadastros:novo", args=[slug]) + ("?" + urlencode({"next": retorno}) if retorno else "")
            if tem_acoes and slug in CADASTROS else ""
        ),
        "url_lista": url_lista,
        "url_retorno": retorno,
        "modal": modal,
    }


@acesso_ao_modulo
def index(request):
    # Sem hub: Cadastros abre direto em Servidores; a rota fica para links antigos.
    return redirect("viagens_cadastros:lista", slug="servidores")


@acesso_ao_modulo
@require_http_methods(["GET"])
def lista(request, slug):
    config = _config(slug)
    modal = _modal_pedido(request, slug, config)
    if slug == "servidores":
        return _lista_servidores(request, modal)
    if slug == "viaturas":
        return _lista_viaturas(request, modal)
    return _lista_catalogo(request, slug, modal)


def _modal_pedido(request, slug, config):
    """`?novo=1` ou `?editar=<pk>` abrem a lista já com o cadastro no modal."""
    if not (request.GET.get("novo") or request.GET.get("editar")):
        return None
    if not pode_editar_cadastros(request.user):
        return None
    pk = request.GET.get("editar")
    if pk and not pk.isdecimal():
        raise Http404
    instancia = get_object_or_404(config["model"], pk=pk) if pk else None
    return _contexto_modal(slug, config, config["form"](instance=instancia), instancia)


def _contexto_modal(slug, config, form, instancia, url_acao=""):
    """Dados do formulário em modal — o mesmo desenho dos cadastros de Eventos.

    `url_acao` cobre os cadastros com rota própria (estados); os do registro
    resolvem sozinhos a rota de criar ou editar.
    """
    pk = instancia.pk if instancia else None
    secoes = _secoes_para_template(form, config["secoes"])
    erros_gerais = list(form.non_field_errors())
    erros_campos = sum(1 for secao in secoes for campo in secao["campos"] if campo["erros"])
    if not url_acao:
        url_acao = (reverse("viagens_cadastros:editar", args=[slug, pk]) if pk
                    else reverse("viagens_cadastros:novo", args=[slug]))
    return {
        "url_acao": url_acao,
        "titulo": f"Editar {config['singular']}" if pk else config["novo"],
        "intro": config["intro_modal"],
        "singular": config["singular"],
        "secoes": secoes,
        "varias_secoes": len(secoes) > 1,
        "erros_gerais": erros_gerais,
        "erros_total": erros_campos + len(erros_gerais),
    }


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


def _lista_viaturas(request, modal=None):
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
    # Consultar a configuração não cria uma ao abrir uma lista: a do setor de
    # quem consulta ou, se ele ainda não tem, a global.
    configuracoes = ConfiguracaoSistema.objects.select_related("unidade")
    cfg = configuracoes.filter(setor=setor_de_viagens(request.user)).first() or configuracoes.filter(setor=None).first()
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
    config = _config("viaturas")
    pode_editar = pode_editar_cadastros(request.user)
    linhas = _linhas_da_lista(config, "viaturas", pagina, tem_acoes=pode_editar)
    for linha in linhas:
        # A identificação da viatura junta modelo e placa, como na origem.
        viatura = linha["objeto"]
        modelo = viatura.modelo.strip()
        linha["principal"] = linha["nome"] = (
            f"{modelo} — {viatura.placa_formatada}" if modelo else viatura.placa_formatada
        )
    contexto = _contexto_lista(
        request, "viaturas", config, pagina=pagina, linhas=linhas, termo=termo,
        parametros=parametros, tem_acoes=pode_editar, tem_filtros=bool(termo or combustivel or unidade),
        tem_situacao=True, modal=modal,
    )
    contexto.update({
        "viaturas": linhas,
        "rotulo_principal": "Viatura",
        "combustivel": combustivel,
        "unidade": unidade,
        "filtros": filtros,
        "filtro_rotulo": next((f["rotulo"] for f in filtros if f["ativo"]), "Todos"),
        "filtro_selecionado": next((f["valor"] for f in filtros if f["ativo"]), ""),
    })
    return render(request, "pages/viagens_cadastros/viaturas/lista.html", contexto)


def _lista_catalogo(request, slug, modal=None):
    """Catálogos de apoio: lista simples; criar e editar acontecem no modal."""
    config = _config(slug)
    retorno = _retorno_cadastro(request)
    termo = request.GET.get("q", "").strip()
    if slug in CATALOGOS_DE_OFICIO:
        queryset = config["model"].objects.order_by("ordem", "nome")
    elif slug == "modelos-texto-rt":
        queryset = config["model"].objects.order_by("campo", "ordem", "nome")
    else:
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
    pode_editar = pode_editar_cadastros(request.user)
    tem_padrao = slug in COM_PADRAO
    linhas = _linhas_da_lista(config, slug, pagina, tem_acoes=pode_editar, retorno=retorno, padrao=tem_padrao)
    contexto = _contexto_lista(
        request, slug, config, pagina=pagina, linhas=linhas, termo=termo,
        parametros=parametros, tem_acoes=pode_editar, tem_filtros=bool(termo),
        tem_situacao=bool(config.get("situacao_ativo")),
        retorno=retorno, modal=modal,
        acoes_template="pages/viagens_cadastros/_acoes_com_padrao.html" if tem_padrao else "",
    )
    contexto.update({
        "itens": linhas,
        "tem_padrao": tem_padrao,
        "url_lista": _url_catalogo(slug, retorno),
        "rotulo_retorno": ("Voltar aos ofícios" if slug in CATALOGOS_DE_OFICIO else
                           "Voltar ao relatório técnico" if slug == "modelos-texto-rt" else
                           "Voltar à viatura" if slug == "combustiveis" else
                           "Voltar ao servidor" if slug == "unidades" else
                           "Voltar ao servidor" if retorno.startswith("/viagens/cadastros/servidores/") else
                           "Voltar ao formulário"),
    })
    return render(request, "pages/viagens_cadastros/lista.html", contexto)


@acesso_ao_modulo
@require_http_methods(["GET", "POST"])
def definir_padrao(request, slug, pk):
    _exigir_edicao(request)
    if slug not in COM_PADRAO:
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


def _lista_servidores(request, modal=None):
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
    config = _config("servidores")
    pode_editar = pode_editar_cadastros(request.user)
    linhas = _linhas_da_lista(config, "servidores", pagina, tem_acoes=pode_editar, retorno=retorno)
    contexto = _contexto_lista(
        request, "servidores", config, pagina=pagina, linhas=linhas, termo=termo,
        parametros=parametros, tem_acoes=pode_editar, tem_filtros=bool(termo or cargo),
        tem_situacao=True, retorno=retorno, modal=modal,
    )
    contexto.update({
        "servidores": linhas,
        "cargo": cargo,
        "cargo_valor": str(cargo.pk) if cargo else "",
        "filtros_cargo": filtros if len(filtros) > 1 else [],
        # O controle de filtro da barra reescreve a querystring pelo id do cargo.
        "opcoes_cargo": [
            {"valor": item.pk, "rotulo": f"{item.nome} ({base.filter(cargo=item).count()})"}
            for item in cargos
        ] if len(filtros) > 1 else [],
        "rotulo_retorno": "Voltar à viatura",
    })
    return render(request, "pages/viagens_cadastros/servidores/lista.html", contexto)


MENSAGEM_RASCUNHO = {
    "servidores": "Servidor salvo como rascunho. Complete cargo e CPF quando possível.",
    "viaturas": "Viatura salva como rascunho. Complete modelo, combustível e tipo quando possível.",
}


def _mensagem_salvo(slug, config, objeto, editando):
    """Rascunho avisa o que falta; o resto confirma a gravação."""
    if getattr(objeto, "status", "") == "RASCUNHO" and slug in MENSAGEM_RASCUNHO:
        return MENSAGEM_RASCUNHO[slug]
    singular = config["singular"].capitalize()
    concordancia = "a" if slug in {"viaturas", "unidades"} else "o"
    acao = "atualizad" if editando else "criad"
    return f"{singular} {acao}{concordancia} com sucesso."


@acesso_ao_modulo
def editar(request, slug, pk=None):
    _exigir_edicao(request)
    config = _config(slug)
    instancia = get_object_or_404(config["model"], pk=pk) if pk else None
    FormClass = config["form"]
    via_modal = request.headers.get("X-Cadastro-Modal") == "1"
    if request.method == "GET" and not via_modal:
        # O formulário vive na listagem: sem JS, a lista abre já com o modal.
        parametros = request.GET.copy()
        parametros.pop("novo", None)
        parametros.pop("editar", None)
        parametros["editar" if pk else "novo"] = str(pk) if pk else "1"
        return redirect(f"{reverse('viagens_cadastros:lista', args=[slug])}?{parametros.urlencode()}")
    if request.method == "POST":
        form = FormClass(request.POST, instance=instancia)
        if form.is_valid():
            objeto = form.save()
            _registrar_auditoria(
                request.user,
                "VIAGENS_CADASTRO_ATUALIZADO" if pk else "VIAGENS_CADASTRO_CRIADO",
                objeto,
            )
            messages.success(request, _mensagem_salvo(slug, config, objeto, bool(pk)))
            if via_modal:
                return JsonResponse({"ok": True})
            retorno = _retorno_cadastro(request)
            return redirect(retorno) if retorno else redirect("viagens_cadastros:lista", slug=slug)
    else:
        form = FormClass(instance=instancia)
    modal = _contexto_modal(slug, config, form, instancia)
    if via_modal:
        return render(request, "pages/viagens_cadastros/_modal_form.html", {"dados": modal})
    if slug == "servidores":
        return _lista_servidores(request, modal)
    if slug == "viaturas":
        return _lista_viaturas(request, modal)
    return _lista_catalogo(request, slug, modal)


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
@require_http_methods(["GET"])
def diarias(request):
    """Histórico de vigências; criar e editar acontecem no modal da lista."""
    return _render_diarias(request, _modal_diaria(request))


def _modal_diaria(request):
    if not (request.GET.get("novo") or request.GET.get("editar")):
        return None
    if not pode_editar_diarias(request.user):
        return None
    pk = request.GET.get("editar")
    if pk and not pk.isdecimal():
        raise Http404
    instancia = get_object_or_404(TabelaDiaria, pk=pk) if pk else None
    return _contexto_modal_diaria(TabelaDiariaForm(instance=instancia), instancia)


def _contexto_modal_diaria(form, instancia):
    url = (reverse("viagens_cadastros:diaria_editar", args=[instancia.pk]) if instancia
           else reverse("viagens_cadastros:diaria_nova"))
    return _contexto_modal("diarias", DIARIAS, form, instancia, url)


def _render_diarias(request, modal=None):
    pode_editar = pode_editar_diarias(request.user)
    paginator = Paginator(TabelaDiaria.objects.all(), ITENS_POR_PAGINA)
    pagina = paginator.get_page(request.GET.get("page") or request.GET.get("pagina"))
    linhas = [
        {
            "objeto": tabela,
            "principal": tabela.get_faixa_display(),
            "nome": f"{tabela.get_faixa_display()} a partir de {tabela.vigencia_inicio:%d/%m/%Y}",
            "celulas": [
                {"rotulo": "Vigente a partir de", "valor": f"{tabela.vigencia_inicio:%d/%m/%Y}"},
                {"rotulo": "24 horas", "valor": f"R$ {_reais(tabela.valor_24h)}", "classe": "c-num"},
                {"rotulo": "15%", "valor": f"R$ {_reais(tabela.valor_15)}", "classe": "c-num"},
                {"rotulo": "30%", "valor": f"R$ {_reais(tabela.valor_30)}", "classe": "c-num"},
            ],
            "url_editar": reverse("viagens_cadastros:diaria_editar", args=[tabela.pk]) if pode_editar else "",
            "url_excluir": reverse("viagens_cadastros:diaria_excluir", args=[tabela.pk]) if pode_editar else "",
        }
        for tabela in pagina
    ]
    contexto = _contexto_lista(
        request, "diarias", DIARIAS, pagina=pagina, linhas=linhas, termo="",
        parametros={}, tem_acoes=pode_editar, modal=modal,
    )
    contexto.update({
        "sem_busca": True,
        "url_novo": reverse("viagens_cadastros:diaria_nova") if pode_editar else "",
        "aviso": "" if pode_editar else (
            "Os valores de diária vêm de norma externa e valem para todas as unidades. "
            "Só os perfis autorizados para gestão de diárias podem alterá-los."
        ),
    })
    return render(request, "pages/viagens_cadastros/lista.html", contexto)


@acesso_ao_modulo
@require_http_methods(["GET", "POST"])
def diaria_editar(request, pk=None):
    if not pode_editar_diarias(request.user):
        raise PermissionDenied
    instancia = get_object_or_404(TabelaDiaria, pk=pk) if pk else None
    via_modal = request.headers.get("X-Cadastro-Modal") == "1"
    if request.method == "GET" and not via_modal:
        destino = reverse("viagens_cadastros:diarias")
        return redirect(f"{destino}?{'editar=' + str(pk) if pk else 'novo=1'}")
    if request.method == "POST":
        form = TabelaDiariaForm(request.POST, instance=instancia)
        if form.is_valid():
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
            if via_modal:
                return JsonResponse({"ok": True})
            return redirect("viagens_cadastros:diarias")
    else:
        form = TabelaDiariaForm(instance=instancia)
    modal = _contexto_modal_diaria(form, instancia)
    if via_modal:
        return render(request, "pages/viagens_cadastros/_modal_form.html", {"dados": modal})
    return _render_diarias(request, modal)


@acesso_ao_modulo
@require_http_methods(["GET", "POST"])
def diaria_excluir(request, pk):
    if not pode_editar_diarias(request.user):
        raise PermissionDenied
    tabela = get_object_or_404(TabelaDiaria, pk=pk)
    voltar = reverse("viagens_cadastros:diarias")
    if request.method == "GET":
        return redirect(voltar)
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
