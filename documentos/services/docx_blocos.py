"""Parágrafos reescritos e quebras de página no DOCX (m111).

O DOCX sai do modelo `.docx` pelo docxtpl, e o modelo traz os parágrafos
fixos (abertura, fecho, declarações, títulos) escritos por extenso — não
conhece os blocos documentais. O PDF, montado do HTML, já respeita o texto
em vigor de cada bloco e as quebras de página; aqui o Word passa a sair
igual: depois de renderizado, ele é aberto com o python-docx e, para cada
bloco cujo texto em vigor difere do padrão do sistema (reescrito no editor,
ou trocado pela administração nos textos do modelo), o parágrafo que traz o
texto padrão é achado e trocado pelo texto em vigor. As quebras ativas
entram nos pontos que `QUEBRAS_DOCX` mapeia na estrutura do Word.

O texto padrão é procurado com os marcadores (`{assunto}`, `{periodo}`...)
valendo por qualquer trecho, para o mesmo parágrafo ser achado com o valor
preenchido ou com a linha para preencher à mão do termo semipreenchido; no
texto novo, cada marcador recebe o que se achou no lugar dele (ou o valor
do documento, quando o marcador é novo). O parágrafo trocado fica com a
formatação do primeiro trecho dele: o Word do documento editado tem o
conteúdo do PDF, não a sua tipografia fina.
"""

from __future__ import annotations

import re
from io import BytesIO

from documentos.editor.blocos import blocos_do_tipo, quebras_do_tipo
from documentos.services.types import DocumentoTipo

_MARCADOR = re.compile(r"\{(\w+)\}")

# Onde cada ponto de quebra do registro (documentos/editor/blocos.py) fica no
# .docx: antes ou depois da tabela cuja primeira célula começa pelo texto.
# As tabelas são âncoras estáveis (os parágrafos em volta podem ter sido
# reescritos). Só o ofício tem pontos de quebra.
QUEBRAS_DOCX = {
    DocumentoTipo.OFICIO: {
        "apos_equipe": ("depois", "NOME"),
        "apos_roteiro": ("antes", "Meio de Transporte"),
        "apos_transporte": ("antes", "Custos:"),
        "antes_assinatura": ("depois", "Custos:"),
    },
}

# Onde os pontos de parágrafo extra (m123) ficam no .docx, na mesma
# convenção das quebras. Fora daqui, o parágrafo sai só no PDF.
PARAGRAFOS_DOCX = {
    DocumentoTipo.OFICIO: {
        "apos_abertura": ("antes", "NOME"),
        "antes_assinatura": ("depois", "Custos:"),
    },
}

# Valor de cada marcador dos blocos no contexto do DOCX (`docxtpl_context`),
# para os marcadores que o texto novo traz e o padrão não tinha.
VALORES_DOCX = {
    DocumentoTipo.OFICIO: {"assunto": "assunto_termo"},
    DocumentoTipo.TERMO_AUTORIZACAO: {
        "periodo": "data_do_evento", "destino": "destino", "servidor": "nome_servidor", "unidade": "unidade",
    },
}


def _tipo(tipo):
    try:
        return DocumentoTipo(getattr(tipo, "value", tipo))
    except ValueError:
        return None


def _literal(texto: str) -> str:
    """O trecho fixo do padrão como expressão: espaços em qualquer quantidade."""
    return r"\s+".join(re.escape(parte) for parte in texto.split())


def _expressao(padrao: str):
    """O texto padrão como expressão regular: cada `{marcador}` vale por
    qualquer trecho (capturado, para ir ao texto novo). Devolve a expressão e
    os nomes dos marcadores, na ordem dos grupos."""
    partes, nomes, pos = [], [], 0
    for achado in _MARCADOR.finditer(padrao):
        partes.append(_literal(padrao[pos:achado.start()]))
        nomes.append(achado.group(1))
        pos = achado.end()
        # Os espaços em volta do valor ficam fora do que se captura.
        partes.append(r"\s*(.+?)\s*" if pos < len(padrao) else r"\s*(.+)")
    partes.append(_literal(padrao[pos:]))
    return re.compile("".join(p for p in partes if p), re.IGNORECASE | re.DOTALL), nomes


def _texto_novo(conteudo: str, capturados: dict, valores: dict) -> str:
    def trocar(achado):
        nome = achado.group(1)
        if nome in capturados:
            return capturados[nome]
        if nome in valores and valores[nome] not in (None, ""):
            return str(valores[nome])
        return achado.group(0)

    return _MARCADOR.sub(trocar, conteudo)


def _paragrafos(documento):
    """Todos os parágrafos do Word: corpo, tabelas (e células aninhadas),
    cabeçalhos e rodapés."""

    def de(container):
        for paragrafo in container.paragraphs:
            yield paragrafo
        for tabela in container.tables:
            for linha in tabela.rows:
                for celula in linha.cells:
                    yield from de(celula)

    yield from de(documento)
    for secao in documento.sections:
        for parte in (secao.header, secao.footer):
            yield from de(parte)


def _trocar_no_paragrafo(paragrafo, inicio: int, fim: int, novo: str):
    """Troca o trecho [inicio, fim) do texto do parágrafo (contado pelos seus
    `runs`) por `novo`, no primeiro `run` alcançado; os demais ficam só com o
    que sobra fora do trecho."""
    pos, primeiro = 0, True
    for run in paragrafo.runs:
        texto = run.text
        a, b = pos, pos + len(texto)
        pos = b
        if b <= inicio or a >= fim:
            continue
        antes = texto[: max(0, inicio - a)]
        depois = texto[max(0, fim - a):]
        run.text = (antes + novo if primeiro else "") + depois
        primeiro = False


def _aplicar_blocos(documento, tipo, blocos: dict, valores: dict) -> bool:
    mudou = False
    for chave, definicao in blocos_do_tipo(tipo).items():
        dados = blocos.get(chave) or {}
        conteudo = dados.get("conteudo")
        if conteudo is None or conteudo == definicao.padrao or not definicao.padrao.strip():
            continue
        expressao, nomes = _expressao(definicao.padrao)
        for paragrafo in _paragrafos(documento):
            texto = "".join(run.text for run in paragrafo.runs)
            achado = expressao.search(texto)
            if achado is None:
                continue
            capturados = {nome: achado.group(i + 1).strip() for i, nome in enumerate(nomes)}
            _trocar_no_paragrafo(paragrafo, achado.start(), achado.end(), _texto_novo(conteudo, capturados, valores))
            mudou = True
            break
    return mudou


def _paragrafo_da_quebra(documento, tabela, onde):
    """O parágrafo que recebe a quebra: o vizinho vazio da tabela (o modelo
    separa as tabelas com linhas em branco), ou um novo ao lado dela."""
    from docx.oxml import OxmlElement
    from docx.text.paragraph import Paragraph

    vizinho = tabela._tbl.getnext() if onde == "depois" else tabela._tbl.getprevious()
    if vizinho is not None and vizinho.tag.endswith("}p"):
        paragrafo = Paragraph(vizinho, tabela._parent)
        if not paragrafo.text.strip():
            return paragrafo
    novo = OxmlElement("w:p")
    if onde == "depois":
        tabela._tbl.addnext(novo)
    else:
        tabela._tbl.addprevious(novo)
    return Paragraph(novo, tabela._parent)


def _tabela_ancora(documento, inicio):
    return next(
        (t for t in documento.tables if t.rows and t.rows[0].cells and t.rows[0].cells[0].text.strip().startswith(inicio)),
        None,
    )


def _aplicar_paragrafos(documento, tipo, paragrafos: dict) -> bool:
    """Os parágrafos extras (m123) nos pontos do .docx: um parágrafo novo
    ao lado da tabela-âncora, antes de uma eventual quebra no mesmo lugar."""
    from docx.oxml import OxmlElement
    from docx.text.paragraph import Paragraph

    pontos = PARAGRAFOS_DOCX.get(tipo, {})
    mudou = False
    for chave, texto in sorted(paragrafos.items()):
        if chave not in pontos or not str(texto or "").strip():
            continue
        onde, inicio = pontos[chave]
        tabela = _tabela_ancora(documento, inicio)
        if tabela is None:
            continue
        novo = OxmlElement("w:p")
        if onde == "depois":
            tabela._tbl.addnext(novo)
        else:
            tabela._tbl.addprevious(novo)
        Paragraph(novo, tabela._parent).add_run(str(texto).strip())
        mudou = True
    return mudou


def _aplicar_quebras(documento, tipo, quebras) -> bool:
    from docx.enum.text import WD_BREAK

    pontos = QUEBRAS_DOCX.get(tipo, {})
    registradas = quebras_do_tipo(tipo)
    mudou = False
    for chave in sorted(set(quebras or ())):
        if chave not in pontos or chave not in registradas:
            continue
        onde, inicio = pontos[chave]
        tabela = _tabela_ancora(documento, inicio)
        if tabela is None:
            continue
        _paragrafo_da_quebra(documento, tabela, onde).add_run().add_break(WD_BREAK.PAGE)
        mudou = True
    return mudou


def aplicar_conteudo_documental(tipo, docx_bytes: bytes, documental, contexto=None) -> bytes:
    """O DOCX renderizado com os parágrafos reescritos e as quebras de página
    de `documental` (o `documento` do payload: `blocos` e `quebras`). Sem
    nada a aplicar, devolve os bytes como vieram."""
    tipo = _tipo(tipo)
    if tipo is None or not isinstance(documental, dict):
        return docx_bytes
    blocos = documental.get("blocos") or {}
    quebras = [q for q in (documental.get("quebras") or ()) if q in QUEBRAS_DOCX.get(tipo, {})]
    paragrafos = {c: t for c, t in (documental.get("paragrafos") or {}).items() if c in PARAGRAFOS_DOCX.get(tipo, {}) and str(t or "").strip()}
    registro = blocos_do_tipo(tipo)
    alterados = {
        chave: dados for chave, dados in blocos.items()
        if chave in registro and isinstance(dados, dict) and dados.get("conteudo") not in (None, registro[chave].padrao)
    }
    if not alterados and not quebras and not paragrafos:
        return docx_bytes
    from docx import Document

    documento = Document(BytesIO(docx_bytes))
    contexto = contexto or {}
    valores = {marcador: contexto.get(chave) for marcador, chave in VALORES_DOCX.get(tipo, {}).items()}
    mudou = _aplicar_blocos(documento, tipo, alterados, valores)
    mudou = _aplicar_paragrafos(documento, tipo, paragrafos) or mudou
    mudou = _aplicar_quebras(documento, tipo, quebras) or mudou
    if not mudou:
        return docx_bytes
    saida = BytesIO()
    documento.save(saida)
    return saida.getvalue()
