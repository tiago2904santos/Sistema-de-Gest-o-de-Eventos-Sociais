"""Catálogo de espécimes do UI Lab: cada componente em cada estado relevante.

Um espécime = (componente, estado, contexto). O UI Lab renderiza cada um isolado
em ``/_lab/c/<id>/`` (alvo dos testes visuais e de acessibilidade por
componente) e todos juntos em ``/_lab/``.

Para registrar um componente novo: acrescente entradas em ``SPECIMENS``. Os
estados canônicos estão em ``ESTADOS`` — use os mesmos nomes para que relatórios
e baselines fiquem comparáveis.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from django.conf import settings
from django.core.paginator import Paginator

ESTADOS = (
    "default", "hover", "focus", "active", "disabled", "loading", "empty",
    "error", "success", "long-content", "mobile",
)

TEXTO_LONGO = (
    "Secretaria de Estado da Segurança Pública — Delegacia-Geral da Polícia Civil do Paraná, "
    "Divisão de Comunicação Social, Assessoria de Imprensa e Cerimonial (texto longo de propósito)"
)

OPCOES = [{"valor": str(i), "rotulo": n} for i, n in enumerate(
    ["Curitiba", "Londrina", "Maringá", "Ponta Grossa", "Cascavel", "Foz do Iguaçu", "São José dos Pinhais"], 1)]


@dataclass(frozen=True)
class Specimen:
    id: str
    component: str
    state: str
    context: dict = field(default_factory=dict)
    note: str = ""
    # Estados de interação (hover/focus/active) são aplicados pelo Playwright
    # sobre o seletor abaixo; o HTML é o mesmo do default.
    interact: str = ""


def _pagina(total=200, numero=5):
    pag = Paginator(list(range(total)), 20)
    pagina = pag.page(numero)
    visiveis = [1, "…", numero - 1, numero, numero + 1, "…", pag.num_pages]
    return {"pagina": pagina, "paginas_visiveis": visiveis, "elipse": "…", "querystring": "", "rotulo": "registros"}


def icon_names():
    txt = (Path(settings.BASE_DIR) / "templates/components/icon.html").read_text(encoding="utf-8")
    return re.findall(r'nome == "([\w\-]+)"', txt)


B = "components/v32/button.html"
SPECIMENS: list[Specimen] = [
    # Botões
    Specimen("button-primario", B, "default", {"label": "Salvar"}),
    Specimen("button-primario-hover", B, "hover", {"label": "Salvar"}, interact="button"),
    Specimen("button-primario-focus", B, "focus", {"label": "Salvar"}, interact="button"),
    Specimen("button-secundario", B, "default", {"label": "Cancelar", "variante": "secundario"}),
    Specimen("button-perigo", B, "default", {"label": "Excluir", "variante": "perigo"}),
    Specimen("button-fantasma", B, "default", {"label": "Voltar", "variante": "fantasma"}),
    Specimen("button-link", B, "default", {"label": "Abrir registro", "href": "#"}),
    Specimen("button-link-focus", B, "focus", {"label": "Abrir registro", "href": "#"}, interact="a"),
    Specimen("button-long", B, "long-content", {"label": TEXTO_LONGO}),
    # Campos
    Specimen("input-default", "components/input.html", "default", {"name": "nome", "label": "Nome do solicitante", "placeholder": "Ex.: Maria da Silva"}),
    Specimen("input-focus", "components/input.html", "focus", {"name": "nome", "label": "Nome"}, interact="input"),
    Specimen("input-required", "components/input.html", "default", {"name": "nome", "label": "Nome", "obrigatorio": True}),
    Specimen("input-error", "components/input.html", "error", {"name": "nome", "label": "Nome", "obrigatorio": True, "erros": ["Este campo é obrigatório."]}),
    Specimen("input-help", "components/input.html", "default", {"name": "cpf", "label": "CPF", "ajuda": "Somente números."}),
    Specimen("input-disabled", "components/input.html", "disabled", {"name": "protocolo", "label": "Protocolo", "valor": "2026.00123", "desabilitado": True}),
    Specimen("input-date", "components/input.html", "default", {"name": "data", "label": "Data do evento", "tipo": "date"}),
    Specimen("input-long", "components/input.html", "long-content", {"name": "orgao", "label": TEXTO_LONGO, "valor": TEXTO_LONGO}),
    Specimen("select-default", "components/select.html", "default", {"name": "municipio", "label": "Município", "opcoes": OPCOES}),
    Specimen("select-selected", "components/select.html", "success", {"name": "municipio", "label": "Município", "opcoes": OPCOES, "selecionado": "2"}),
    Specimen("select-searchable", "components/select.html", "default", {"name": "municipio", "label": "Município", "opcoes": OPCOES, "pesquisavel": True}),
    Specimen("select-error", "components/select.html", "error", {"name": "municipio", "label": "Município", "opcoes": OPCOES, "obrigatorio": True, "erros": ["Escolha um município."]}),
    Specimen("select-disabled", "components/select.html", "disabled", {"name": "municipio", "label": "Município", "opcoes": OPCOES, "selecionado": "1", "desabilitado": True}),
    Specimen("select-empty", "components/select.html", "empty", {"name": "municipio", "label": "Município", "opcoes": [], "vazio": "Nenhum município cadastrado."}),
    Specimen("textarea-default", "components/textarea.html", "default", {"name": "obs", "label": "Observações"}),
    Specimen("textarea-error", "components/textarea.html", "error", {"name": "obs", "label": "Observações", "erros": ["Descreva o motivo."]}),
    Specimen("textarea-long", "components/textarea.html", "long-content", {"name": "obs", "label": "Observações", "valor": (TEXTO_LONGO + " ") * 6}),
    # Estrutura de página
    Specimen("page-header", "components/v32/page_header.html", "default", {"titulo": "Ofícios", "modulo_ativo": {"nome": "Viagens"}, "acao_label": "Novo ofício", "acao_url": "#"}),
    Specimen("page-header-long", "components/v32/page_header.html", "long-content", {"titulo": TEXTO_LONGO, "modulo_ativo": {"nome": "Viagens"}}),
    Specimen("breadcrumb", "components/v32/breadcrumb.html", "default", {"itens": [{"label": "Viagens", "url": "#"}, {"label": "Ofícios", "url": "#"}, {"label": "Ofício 12/2026"}]}),
    Specimen("section-card", "components/v32/section_card.html", "default", {"numero": "1", "titulo": "Dados do evento", "subtitulo": "Onde e quando acontece.", "recolhe": "sec1"}),
    Specimen("summary-card", "components/v32/summary_card.html", "default", {"titulo": "Solicitações em análise", "valor": "18", "icone": "clipboard"}),
    Specimen("summary-card-destaque", "components/v32/summary_card.html", "success", {"titulo": "Atendidas no mês", "valor": "42", "icone": "check-circle", "destaque": True, "variacao": "+12%", "tendencia": "alta"}),
    Specimen("summary-card-link", "components/v32/summary_card.html", "default", {"titulo": "Pendentes", "valor": "7", "url": "#", "icone": "hourglass"}),
    Specimen("summary-card-long", "components/v32/summary_card.html", "long-content", {"titulo": TEXTO_LONGO, "valor": "1.234.567", "icone": "chart"}),
    Specimen("paginacao", "components/v32/paginacao.html", "default", _pagina()),
    Specimen("paginacao-single", "components/v32/paginacao.html", "empty", _pagina(total=5, numero=1), note="Uma página só: o componente não deve renderizar nada."),
]


def all_specimens():
    extras = [Specimen(f"icon-{n}", "components/icon.html", "default", {"nome": n}) for n in icon_names()]
    return SPECIMENS + extras


def by_id():
    return {s.id: s for s in all_specimens()}
