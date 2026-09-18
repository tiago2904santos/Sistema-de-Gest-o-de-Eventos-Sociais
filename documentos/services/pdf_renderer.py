"""Renderização de documentos a partir de HTML: prévia e PDF de uma fonte só.

O documento é um template Django (`documentos/pdf/<tipo>.html`, estendendo
`base_institucional.html`) renderizado com o contexto único de
`document_context.py`. Do mesmo HTML saem a prévia A4 na tela e o PDF; a
diferença é o `modo` no contexto e a folha de impressão que só o motor de
PDF recebe.

O motor de PDF é o WeasyPrint. No Windows ele depende do runtime GTK; quando
não carrega, `render_pdf` levanta `DocumentRendererUnavailable` e quem chama
decide o que fazer (a façade avisa e, só em desenvolvimento, pode cair no
caminho antigo pelo DOCX). A abstração aqui — `renderizar_html` separado de
`render_pdf` — é o que permite trocar o motor sem tocar no resto.
"""

from __future__ import annotations

import logging
from pathlib import Path

from django.conf import settings
from django.template.loader import render_to_string

from documentos.services.exceptions import DocumentRendererUnavailable
from documentos.services.timing import measure_step

logger = logging.getLogger(__name__)

CSS_COMUM = "documentos/pdf/documento.css"
CSS_IMPRESSAO = "documentos/pdf/documento-impressao.css"
CSS_EDITOR = "documentos/pdf/documento-editor.css"
TEMPLATE_BASE = "documentos/pdf/base_institucional.html"


def tipos_html_nativo() -> frozenset[str]:
    """Tipos cujo PDF nasce do HTML; os demais seguem, por enquanto, a cadeia
    antiga. Lido a cada chamada para `override_settings` valer nos testes."""
    return frozenset(getattr(settings, "DOCUMENTOS_PDF_HTML_NATIVO", ("oficio",)))


def tipo_e_html_nativo(tipo) -> bool:
    valor = getattr(tipo, "value", tipo)
    return str(valor) in tipos_html_nativo()


def template_do_tipo(tipo) -> str:
    valor = getattr(tipo, "value", tipo)
    return f"documentos/pdf/{valor}.html"


def caminho_css(nome: str) -> Path:
    """Os CSS moram ao lado dos templates, em `templates/`."""
    return Path(settings.BASE_DIR) / "templates" / nome


def css_do_tipo(tipo) -> list[str]:
    """Camada própria do documento (`documentos/pdf/<tipo>.css`: geometria e
    tipografia do modelo), por cima do CSS comum. Opcional."""
    if tipo is None:
        return []
    nome = f"documentos/pdf/{getattr(tipo, 'value', tipo)}.css"
    return [nome] if caminho_css(nome).is_file() else []


def renderizar_html(tipo, contexto: dict, *, modo: str) -> str:
    """HTML do documento. `modo` é `editor` (tela) ou `pdf`."""
    dados = dict(contexto)
    dados["modo"] = modo
    if modo == "editor":
        # Na tela o CSS comum entra inline, para a folha não depender do
        # pipeline de estáticos e ficar idêntica ao que o PDF recebe; o CSS
        # de tela (folha sobre o fundo, marcação de editável) vai junto, e a
        # camada do tipo por último, como no PDF.
        nomes = (CSS_COMUM, CSS_EDITOR, *css_do_tipo(tipo))
        dados["css_inline"] = "\n".join(caminho_css(nome).read_text(encoding="utf-8") for nome in nomes)
    with measure_step("renderizar_html", {"tipo": getattr(tipo, "value", tipo), "modo": modo}):
        return render_to_string(template_do_tipo(tipo), dados)


def _weasyprint():
    try:
        from weasyprint import CSS, HTML
    except OSError as exc:  # GTK/Pango/Cairo ausentes (Windows sem runtime)
        raise DocumentRendererUnavailable(
            "WeasyPrint não pôde carregar as bibliotecas nativas (GTK/Pango/Cairo). "
            "Instale o runtime GTK3 e reinicie o serviço."
        ) from exc
    except ImportError as exc:
        raise DocumentRendererUnavailable("WeasyPrint não está instalado.") from exc
    return CSS, HTML


def weasyprint_disponivel() -> bool:
    try:
        _weasyprint()
    except DocumentRendererUnavailable:
        return False
    return True


# Documentos que devem caber numa página: quantos degraus de compactação o CSS
# do tipo define (`.doc-compacto-1`, `.doc-compacto-2`, ...). Se o PDF passar de
# uma página, é refeito com o degrau seguinte; esgotados os degraus, sai como
# couber (texto longo demais pagina normalmente).
CABER_EM_UMA_PAGINA = {"oficio": 2, "relatorio_tecnico": 2}


def render_pdf(html: str, *, tipo=None) -> bytes:
    """PDF em memória a partir do HTML já renderizado (modo `pdf`)."""
    CSS, HTML = _weasyprint()
    base_url = Path(settings.BASE_DIR).resolve().as_uri() + "/"
    folhas = [CSS(filename=str(caminho_css(nome))) for nome in (CSS_COMUM, CSS_IMPRESSAO, *css_do_tipo(tipo))]
    degraus = CABER_EM_UMA_PAGINA.get(str(getattr(tipo, "value", tipo) or ""), 0)
    with measure_step("render_pdf_html", {"tipo": getattr(tipo, "value", tipo) or "—"}):
        # `presentational_hints=False`: nada de cor/fundo vindos de atributos
        # HTML — os textos de campo são conteúdo do usuário, escapado, e o
        # visual é só do CSS institucional.
        documento = HTML(string=html, base_url=base_url).render(stylesheets=folhas, presentational_hints=False)
        for degrau in range(1, degraus + 1):
            if len(documento.pages) <= 1:
                break
            compacto = html.replace('class="documento ', f'class="documento doc-compacto-{degrau} ', 1)
            documento = HTML(string=compacto, base_url=base_url).render(stylesheets=folhas, presentational_hints=False)
        return documento.write_pdf()


def caminhos_dos_templates(tipo) -> tuple[Path, ...]:
    """Arquivos cuja mudança deve invalidar o cache do PDF deste tipo."""
    from django.template.loader import get_template

    caminhos = []
    for nome in (template_do_tipo(tipo), TEMPLATE_BASE):
        try:
            origem = getattr(get_template(nome).origin, "name", "")
        except Exception:  # noqa: BLE001 - template ausente entra como "missing"
            origem = ""
        caminhos.append(Path(origem) if origem else Path(settings.BASE_DIR) / "templates" / nome)
    caminhos.append(caminho_css(CSS_COMUM))
    caminhos.append(caminho_css(CSS_IMPRESSAO))
    caminhos.extend(caminho_css(nome) for nome in css_do_tipo(tipo))
    return tuple(caminhos)
