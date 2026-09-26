"""Edição completa de um documento (m057): o documento inteiro, já montado,
editado à mão no navegador e gravado como uma versão editada.

A folha de cada documento marca, com comentários HTML, as regiões que se
editam: `<!--ed:cabecalho-->…<!--/ed:cabecalho-->`, o mesmo para `corpo` e
`rodape` (templates/documentos/pdf/base_institucional.html e o timbre do
Coffee Break). O editor completo torna editável o elemento que contém cada
região; o que volta é o HTML de dentro dela, que passa pela lista branca de
`sanitizar` antes de ser gravado. Na saída (prévia, PDF, DOCX), a região da
folha montada dos dados é trocada pela da versão editada — a geometria da
página, as margens e o CSS institucional continuam os do modelo.

As imagens do papel timbrado (brasão e marca) são as únicas que entram: o
HTML guarda só o nome delas (`data-imagem`), e a saída põe o caminho certo
para o modo (arquivo local no PDF, `/static/` na tela).

A versão editada é do documento (tipo, dono e variante; ver
`DocumentoVersaoEditada`) e entra no payload de geração por
`document_blocks.conteudo_documental` — por isso muda a chave de cache do PDF,
e um PDF antigo nunca é servido no lugar dela.
"""

from __future__ import annotations

import hashlib
import re
from html import escape
from html.parser import HTMLParser

REGIOES = ("cabecalho", "corpo", "rodape")
ROTULOS_REGIOES = {"cabecalho": "Cabeçalho", "corpo": "Corpo", "rodape": "Rodapé"}
TAMANHO_MAXIMO_REGIAO = 400 * 1024

# ---- Lista branca ---------------------------------------------------------

TAGS_PERMITIDAS = frozenset({
    "p", "br", "strong", "b", "em", "i", "u", "s", "strike", "sub", "sup", "small",
    "span", "div", "h1", "h2", "h3", "h4", "ul", "ol", "li", "blockquote", "hr",
    "table", "thead", "tbody", "tfoot", "tr", "th", "td", "colgroup", "col", "img",
})
# Somem com tudo o que têm dentro.
TAGS_DESCARTADAS = frozenset({
    "script", "style", "iframe", "frame", "frameset", "object", "embed", "applet",
    "noscript", "template", "svg", "math", "textarea", "select", "option", "button",
    "input", "form", "link", "meta", "title", "head", "base", "audio", "video", "canvas",
})
TAGS_VAZIAS = frozenset({"br", "hr", "img", "col"})
# Descartadas sem conteúdo (não têm fechamento): só a tag some.
TAGS_DESCARTADAS_VAZIAS = frozenset({"input", "link", "meta", "base", "embed", "frame", "source", "track", "param", "area", "wbr"})

# As imagens do papel timbrado, pelo nome do arquivo.
IMAGENS_PERMITIDAS = {
    "brasao-pcpr.png": "brasao",
    "marca-pcpr.png": "marca",
    "brasao-pcpr-timbre.png": "brasao",
    "marca-pcpr-timbre.png": "marca",
}

_CLASSE = re.compile(r"^[A-Za-z][A-Za-z0-9_-]{0,63}$")
# Classes do editor de campos: não são do documento.
_CLASSES_DO_EDITOR = ("doc-editavel", "doc-vazio", "doc-quebra-slot", "ed-")
_MEDIDA = r"-?\d{1,4}(?:\.\d{1,3})?(?:pt|px|em|rem|%|cm|mm)|0"
ESTILOS_PERMITIDOS = {
    "text-align": re.compile(r"^(left|right|center|justify|start|end)$"),
    "font-weight": re.compile(r"^(bold|bolder|normal|[1-9]00)$"),
    "font-style": re.compile(r"^(italic|normal)$"),
    "text-decoration": re.compile(r"^(underline|line-through|none)( (underline|line-through))?$"),
    "text-decoration-line": re.compile(r"^(underline|line-through|none)( (underline|line-through))?$"),
    "text-indent": re.compile(rf"^({_MEDIDA})$"),
    "margin-left": re.compile(rf"^({_MEDIDA})$"),
    "padding-left": re.compile(rf"^({_MEDIDA})$"),
    "width": re.compile(rf"^({_MEDIDA}|auto)$"),
    "vertical-align": re.compile(r"^(top|middle|bottom|baseline)$"),
    "font-size": re.compile(rf"^({_MEDIDA})$"),
}


def _estilo_limpo(valor: str) -> str:
    partes = []
    for declaracao in (valor or "").split(";"):
        if ":" not in declaracao:
            continue
        nome, _, conteudo = declaracao.partition(":")
        nome, conteudo = nome.strip().lower(), conteudo.strip().lower()
        regra = ESTILOS_PERMITIDOS.get(nome)
        if regra and regra.match(conteudo):
            partes.append(f"{nome}: {conteudo}")
    return "; ".join(partes)


def _classes_limpas(valor: str) -> str:
    return " ".join(
        c for c in (valor or "").split()
        if _CLASSE.match(c) and not c.startswith(_CLASSES_DO_EDITOR)
    )


def _imagem(atributos) -> str | None:
    dados = dict(atributos)
    nome = dados.get("data-imagem")
    if nome in IMAGENS_PERMITIDAS.values():
        return nome
    src = (dados.get("src") or "").split("?")[0].split("#")[0]
    return IMAGENS_PERMITIDAS.get(src.rsplit("/", 1)[-1]) if src else None


class _Sanitizador(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.saida: list[str] = []
        self.pilha: list[str] = []
        self.descartando = 0

    def _atributos(self, tag, atributos) -> str:
        limpos = []
        for nome, valor in atributos:
            nome = (nome or "").lower()
            valor = valor or ""
            if nome == "class":
                valor = _classes_limpas(valor)
            elif nome == "style":
                valor = _estilo_limpo(valor)
            elif nome in ("colspan", "rowspan") and tag in ("td", "th"):
                valor = valor if valor.isdigit() and 0 < int(valor) <= 50 else ""
            elif nome == "alt" and tag == "img":
                valor = valor[:200]
            elif nome == "align" and valor.lower() in ("left", "right", "center", "justify"):
                # O `align` antigo que alguns navegadores põem ao alinhar vira estilo.
                nome, valor = "style", f"text-align: {valor.lower()}"
            else:
                continue
            if valor:
                limpos.append(f' {nome}="{escape(valor, quote=True)}"')
        return "".join(limpos)

    def handle_starttag(self, tag, atributos):
        tag = tag.lower()
        if tag in TAGS_DESCARTADAS_VAZIAS:
            return
        if self.descartando:
            if tag in TAGS_DESCARTADAS:
                self.descartando += 1
            return
        if tag in TAGS_DESCARTADAS:
            self.descartando = 1
            return
        if tag not in TAGS_PERMITIDAS:
            return  # a tag some; o texto dentro dela fica
        if tag == "img":
            nome = _imagem(atributos)
            if nome:
                self.saida.append(f'<img data-imagem="{nome}"{self._atributos(tag, atributos)}>')
            return
        self.saida.append(f"<{tag}{self._atributos(tag, atributos)}>")
        if tag not in TAGS_VAZIAS:
            self.pilha.append(tag)

    def handle_startendtag(self, tag, atributos):
        tag = tag.lower()
        if tag in TAGS_DESCARTADAS and tag not in TAGS_DESCARTADAS_VAZIAS:
            return  # `<script/>`: nada a descartar depois dela
        self.handle_starttag(tag, atributos)
        if tag not in TAGS_VAZIAS and self.pilha and self.pilha[-1] == tag and not self.descartando:
            self.handle_endtag(tag)

    def handle_endtag(self, tag):
        tag = tag.lower()
        if tag in TAGS_DESCARTADAS_VAZIAS:
            return
        if self.descartando:
            if tag in TAGS_DESCARTADAS:
                self.descartando -= 1
            return
        if tag not in self.pilha:
            return
        while self.pilha:
            aberta = self.pilha.pop()
            self.saida.append(f"</{aberta}>")
            if aberta == tag:
                break

    def handle_data(self, dados):
        if not self.descartando:
            self.saida.append(escape(dados, quote=False))

    def resultado(self) -> str:
        self.close()
        while self.pilha:
            self.saida.append(f"</{self.pilha.pop()}>")
        return "".join(self.saida)


def sanitizar(html: str) -> str:
    """HTML pela lista branca: só tags de texto, lista e tabela; atributos
    `class` (nomes simples), `style` (alinhamento, ênfase, recuo, largura e
    tamanho da letra, com valores conferidos), `colspan`/`rowspan` e as
    imagens do timbre. Comentários, scripts, estilos, eventos (`on*`),
    endereços e o resto somem."""
    parser = _Sanitizador()
    parser.feed(str(html or "")[:TAMANHO_MAXIMO_REGIAO * 2])
    return parser.resultado().strip()


def sanitizar_regioes(regioes) -> dict[str, str]:
    """Só as regiões conhecidas, cada uma sanitizada e no limite de tamanho."""
    if not isinstance(regioes, dict):
        raise ValueError("Regiões inválidas.")
    limpas = {}
    for nome in REGIOES:
        if nome not in regioes:
            continue
        valor = regioes[nome]
        if not isinstance(valor, str):
            raise ValueError(f"{ROTULOS_REGIOES[nome]}: esperava o HTML da região.")
        if len(valor) > TAMANHO_MAXIMO_REGIAO:
            raise ValueError(f"{ROTULOS_REGIOES[nome]}: conteúdo grande demais.")
        limpas[nome] = sanitizar(valor)
    return limpas


# ---- Regiões na folha -----------------------------------------------------


def _padrao(nome):
    return re.compile(rf"<!--ed:{nome}-->(.*?)<!--/ed:{nome}-->", re.DOTALL)


def extrair_regioes(html: str) -> dict[str, str]:
    """O HTML de dentro de cada região marcada na folha."""
    regioes = {}
    for nome in REGIOES:
        achado = _padrao(nome).search(html or "")
        if achado:
            regioes[nome] = achado.group(1)
    return regioes


def _com_imagens(html: str, imagens) -> str:
    imagens = imagens or {}

    def trocar(achado):
        nome = achado.group(1)
        src = imagens.get(nome)
        return f'<img src="{escape(src, quote=True)}" data-imagem="{nome}"' if src else achado.group(0)

    return re.sub(r'<img data-imagem="(\w+)"', trocar, html)


def aplicar_regioes(html: str, regioes, imagens=None) -> str:
    """A folha com as regiões da versão editada no lugar das do modelo. As
    marcas ficam (o editor completo as usa para achar a região de novo)."""
    for nome, conteudo in (regioes or {}).items():
        if nome not in REGIOES:
            continue
        novo = f"<!--ed:{nome}-->{_com_imagens(conteudo, imagens)}<!--/ed:{nome}-->"
        html = _padrao(nome).sub(lambda _achado, novo=novo: novo, html, count=1)
    return html


def _texto_visivel(html: str) -> str:
    sem_tags = re.sub(r"<[^>]+>", " ", html or "")
    return re.sub(r"\s+", " ", sem_tags).strip()


def impressao_digital(html: str) -> str:
    """O que o documento diz (o texto de cada região), resumido num hash: muda
    quando os dados que o montam mudam, não quando muda só o CSS."""
    regioes = extrair_regioes(html)
    base = "\n".join(f"{nome}:{_texto_visivel(regioes.get(nome, ''))}" for nome in REGIOES)
    return hashlib.sha256(base.encode("utf-8")).hexdigest()


# ---- Gravação -------------------------------------------------------------


def _filtro(tipo, dono, variante) -> dict:
    from documentos.services.document_blocks import _filtro as filtro_do_bloco

    return {**filtro_do_bloco(tipo, dono), "variante": str(variante or "")}


def versoes(tipo, dono, variante=""):
    """Todas as linhas do documento, da mais recente à mais antiga."""
    from documentos.models import DocumentoVersaoEditada

    return DocumentoVersaoEditada.objects.filter(**_filtro(tipo, dono, variante)).select_related("criado_por").order_by("-criado_em", "-pk")


def estado(tipo, dono, variante=""):
    """A linha mais recente do documento (edição ou volta ao modelo), ou None."""
    return versoes(tipo, dono, variante).first()


def vigente(tipo, dono, variante=""):
    """A versão editada em vigor, ou None quando o documento sai do modelo."""
    atual = estado(tipo, dono, variante)
    return atual if atual is not None and atual.vigora else None


def para_payload(tipo, dono, variante=""):
    """O que entra no payload de geração (e, por ele, na chave de cache)."""
    atual = vigente(tipo, dono, variante)
    if atual is None:
        return None
    return {
        "id": atual.pk,
        "regioes": dict(atual.regioes or {}),
        "criado_em": atual.criado_em.isoformat() if atual.criado_em else "",
        "criado_por": str(atual.criado_por) if atual.criado_por_id else "",
    }


def _usuario(usuario):
    return usuario if getattr(usuario, "is_authenticated", False) else None


def salvar(tipo, dono, variante, regioes, usuario, *, impressao_base=""):
    """Grava uma versão editada nova (as regiões passam por `sanitizar`)."""
    from documentos.models import DocumentoVersaoEditada

    limpas = sanitizar_regioes(regioes)
    if not limpas:
        raise ValueError("Nada para gravar.")
    return DocumentoVersaoEditada.objects.create(
        **_filtro(tipo, dono, variante), acao=DocumentoVersaoEditada.Acao.EDICAO,
        regioes=limpas, impressao_base=impressao_base, criado_por=_usuario(usuario),
    )


def voltar_ao_modelo(tipo, dono, variante, usuario):
    """O documento volta a sair dos dados e do modelo. Nada se apaga."""
    from documentos.models import DocumentoVersaoEditada

    if vigente(tipo, dono, variante) is None:
        return None
    return DocumentoVersaoEditada.objects.create(
        **_filtro(tipo, dono, variante), acao=DocumentoVersaoEditada.Acao.MODELO, criado_por=_usuario(usuario),
    )


def restaurar(tipo, dono, variante, versao_id, usuario, *, impressao_base=""):
    """Uma versão antiga volta a valer, copiada numa linha nova."""
    from documentos.models import DocumentoVersaoEditada

    antiga = versoes(tipo, dono, variante).filter(pk=versao_id).exclude(acao=DocumentoVersaoEditada.Acao.MODELO).first()
    if antiga is None:
        raise ValueError("Versão não encontrada neste documento.")
    return DocumentoVersaoEditada.objects.create(
        **_filtro(tipo, dono, variante), acao=DocumentoVersaoEditada.Acao.RESTAURACAO,
        regioes=sanitizar_regioes(antiga.regioes or {}), impressao_base=impressao_base or antiga.impressao_base,
        restaurada_de=antiga, criado_por=_usuario(usuario),
    )
