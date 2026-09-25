"""Páginas de um PDF: texto, orientação do conteúdo e recorte.

**Orientação pela matriz completa.** O pypdf, ao entrar num Form XObject,
recomeça a matriz do zero (ignora o `cm` de fora e a `/Matrix` do form). O
eProtocolo embrulha a página original num form cujo conteúdo usa o eixo Y
invertido e desfaz a inversão por fora (`1 0 0 -1 0 H cm`). Quem olha só o
de dentro — como `extract_text(orientations=...)` — vê o texto de cabeça
para baixo e mandaria girar 180° uma página que está em pé. Aqui a matriz é
acompanhada de ponta a ponta (q/Q, cm, /Matrix do form, Tm/Td/TD/T*), e a
direção de cada trecho de texto é a da linha de base na página:
`atan2(b, a)` da matriz final. Inverter só o Y não muda essa direção;
girar muda.

**A moldura do eProtocolo não vota.** O rodapé ("Inserido ao protocolo…",
na faixa abaixo de y=0 que o eProtocolo acrescenta) e o carimbo Fls./Mov.
(canto superior direito) estão sempre a 0°, qualquer que seja o conteúdo.
Num diário de bordo deitado dentro da moldura, contá-los puxaria o voto para
"em pé".

**Uma leitura só.** O texto sai do `extract_text` do pypdf e a matriz é
acompanhada pelos visitantes de operador do mesmo passe (o `Do` de um form
chega ao visitante "antes" e, depois de todo o conteúdo do form, ao
"depois"), então cada página é interpretada uma vez.

Nada aqui grava arquivo nem registra texto em log: as páginas têm nomes e
CPFs.
"""

from __future__ import annotations

import logging
import math
import re
from collections import Counter
from dataclasses import dataclass
from io import BytesIO

from core.errors import capture

__all__ = [
    "Pagina",
    "ArquivoIlegivel",
    "ImagemInvalida",
    "eh_pdf",
    "eh_imagem",
    "como_pdf",
    "imagem_para_pdf",
    "ler_paginas",
    "separar_moldura",
    "rotacao_para_ficar_em_pe",
    "fica_em_paisagem",
    "recortar",
    "normalizar_orientacao",
]

_IDENTIDADE = (1.0, 0.0, 0.0, 1.0, 0.0, 0.0)

#: Corpo (sem moldura) com menos caracteres que isto é página "sem texto".
MINIMO_CARACTERES = 20
#: Página coberta por imagem nesta fração ou mais, com pouco texto, é escaneada.
COBERTURA_ESCANEADA = 0.5
#: "Pouco texto" para página coberta por imagem (o cabeçalho do navegador num
#: print de certidão, por exemplo, dá uns 100 caracteres).
POUCO_TEXTO = 150
#: Quanto o ângulo de um trecho pode fugir de 0/90/180/270 e ainda votar.
TOLERANCIA_ANGULO = 20.0
#: Fração mínima do voto para o ângulo dominante valer.
MAIORIA = 0.6


class ArquivoIlegivel(ValueError):
    """O arquivo não é um PDF (nem imagem) que dê para abrir."""


class ImagemInvalida(ValueError):
    """A imagem não tem nenhum quadro legível."""


@dataclass
class Pagina:
    """Uma página lida do PDF.

    - `indice`: posição no PDF, a partir de 0.
    - `texto`: tudo o que o pypdf extraiu, na ordem dele.
    - `corpo`: o texto sem a moldura do eProtocolo (carimbo Fls./Mov. e
      rodapé); na folha de assinatura ("2a"), vazio. Em PDF que não é do
      eProtocolo, igual a `texto`. Com OCR (`ocr=True`), o texto lido da
      imagem.
    - `largura`, `altura`: da mediabox, antes do /Rotate.
    - `rotacao`: o /Rotate atual, normalizado em 0/90/180/270.
    - `angulo_texto`: direção dominante do conteúdo na página, sem o /Rotate
      (0 = em pé; 90 = linhas subindo; 180 = de cabeça para baixo; 270 =
      linhas descendo), pela matriz completa e sem a moldura. None quando
      não há texto que decida. É também o /Rotate que deixa a página em pé.
    - `cobertura_imagem`: fração da página coberta por imagens (0 a 1).
    - `sem_texto`: página que precisa de OCR para ser lida (escaneada ou
      foto), a não ser a folha de assinatura, que é só moldura.
    - `base`: onde a mediabox começa em y (negativo no eProtocolo, que
      acrescenta embaixo a faixa do rodapé: −40, ou −80 se o documento já
      tinha passado por outro protocolo).
    - `ocr`: `corpo` veio do OCR.
    """

    indice: int
    texto: str
    corpo: str
    largura: float
    altura: float
    rotacao: int
    angulo_texto: int | None
    cobertura_imagem: float
    sem_texto: bool
    base: float = 0.0
    ocr: bool = False

    @property
    def em_paisagem(self) -> bool:
        """Como a página aparece hoje (com o /Rotate atual) é mais larga que alta."""
        return fica_em_paisagem(self, self.rotacao)


# ─────────────────────────────────────────────────────────────────
# Tipo do arquivo
# ─────────────────────────────────────────────────────────────────

def eh_pdf(dados: bytes) -> bool:
    """O arquivo começa (nos primeiros 1024 bytes, como o leitor tolera) com %PDF-."""
    return b"%PDF-" in bytes(dados[:1024] or b"")


def eh_imagem(dados: bytes) -> bool:
    """PNG ou JPEG, pela assinatura do arquivo (não pela extensão)."""
    cabeca = bytes(dados[:8] or b"")
    return cabeca.startswith(b"\x89PNG\r\n\x1a\n") or cabeca.startswith(b"\xff\xd8\xff")


def imagem_para_pdf(dados: bytes, *, corrigir_exif: bool = False) -> bytes:
    """PDF com uma página por quadro da imagem.

    Transparência vira fundo branco (o PDF não tem canal alfa). Com
    `corrigir_exif`, a foto de celular é desvirada pela etiqueta EXIF de
    orientação antes de virar página — sem isso, a foto aparece como o
    sensor gravou, muitas vezes deitada.
    """
    from PIL import Image
    from PIL import ImageSequence

    def normalizar(quadro):
        quadro = quadro.copy()
        if quadro.mode in ("RGBA", "LA") or (quadro.mode == "P" and "transparency" in quadro.info):
            fundo = Image.new("RGB", quadro.size, "white")
            rgba = quadro.convert("RGBA")
            fundo.paste(rgba, mask=rgba.getchannel("A"))
            return fundo
        return quadro.convert("RGB")

    with Image.open(BytesIO(dados)) as imagem:
        orientacao = _orientacao_exif(imagem) if corrigir_exif else 1
        quadros = [normalizar(quadro) for quadro in ImageSequence.Iterator(imagem)]

    if not quadros:
        raise ImagemInvalida("Não foi possível ler a imagem anexada.")
    if orientacao != 1:
        quadros[0] = _desvirar(quadros[0], orientacao)

    saida = BytesIO()
    primeiro, *resto = quadros
    primeiro.save(saida, format="PDF", save_all=True, append_images=resto)
    return saida.getvalue()


def _orientacao_exif(imagem) -> int:
    try:
        return int(imagem.getexif().get(0x0112, 1) or 1)
    except Exception:
        return 1


def _desvirar(quadro, orientacao: int):
    """O quadro como a câmera quis mostrar, pela etiqueta EXIF de orientação (1 a 8)."""
    from PIL import Image

    operacao = {
        2: Image.Transpose.FLIP_LEFT_RIGHT,
        3: Image.Transpose.ROTATE_180,
        4: Image.Transpose.FLIP_TOP_BOTTOM,
        5: Image.Transpose.TRANSPOSE,
        6: Image.Transpose.ROTATE_270,
        7: Image.Transpose.TRANSVERSE,
        8: Image.Transpose.ROTATE_90,
    }.get(orientacao)
    return quadro.transpose(operacao) if operacao is not None else quadro


def como_pdf(dados: bytes) -> bytes:
    """O próprio PDF, ou a imagem (PNG/JPG) convertida em PDF de uma página.

    A imagem é desvirada pela etiqueta EXIF, como o celular mostra a foto.
    Levanta `ArquivoIlegivel` para qualquer outra coisa.
    """
    dados = bytes(dados or b"")
    if eh_pdf(dados):
        return dados
    if eh_imagem(dados):
        try:
            return imagem_para_pdf(dados, corrigir_exif=True)
        except Exception as exc:
            raise ArquivoIlegivel("Não foi possível ler a imagem.") from exc
    raise ArquivoIlegivel("O arquivo não é um PDF nem uma imagem PNG ou JPG.")


def _abrir(dados: bytes):
    from pypdf import PdfReader

    try:
        leitor = PdfReader(BytesIO(dados))
        if getattr(leitor, "is_encrypted", False):
            leitor.decrypt("")
        _ = len(leitor.pages)
    except Exception as exc:
        raise ArquivoIlegivel("Não foi possível abrir o PDF.") from exc
    return leitor


# ─────────────────────────────────────────────────────────────────
# Moldura do eProtocolo no texto
# ─────────────────────────────────────────────────────────────────

#: Nº do protocolo como o eProtocolo escreve ("26.613.666-8").
PROTOCOLO = r"\d{2}\.\d{3}\.\d{3}-\d"
#: Carimbo Fls./Mov.: duas linhas curtas logo antes do rodapé. Documentos
#: aninhados (que já passaram por outro protocolo) trazem carimbos antigos
#: no corpo; o do protocolo atual é sempre o ÚLTIMO.
RX_CARIMBO = re.compile(
    r"(?m)^[ \t]*(\d{1,4}[a-z]?)[ \t]*\n[ \t]*(\d{1,4})[ \t]*\n"
    r"(?=[ \t]*(?:Assinatura (?:Avan[çc]ada|Qualificada)|Inserido ao protocolo))",
    re.IGNORECASE,
)
#: Folha de assinatura do eProtocolo ("2a" / "2" / "Documento: arquivo.pdf.").
RX_FOLHA_ASSINATURA = re.compile(
    r"^\s*(\d{1,4}[a-z])[ \t]*\n[ \t]*(\d{1,4})[ \t]*\n[ \t]*Documento:\s*(.+?\.pdf)\.?[ \t]*(?:\n|$)",
    re.IGNORECASE | re.DOTALL,
)
#: Fim do rodapé: o código de validação (30 a 32 hexadecimais; os zeros à
#: esquerda somem). Nos aninhados vem colado: "validarDocumentocom o código:".
RX_CODIGO = re.compile(r"validarDocumento\s*com o c[óo]digo:\s*([0-9a-f]{20,32})\b\.?", re.IGNORECASE)


def separar_moldura(texto: str) -> tuple[str, str, bool]:
    """Divide o texto da página em (corpo, moldura, é_folha_de_assinatura).

    O corpo é o que vem antes do último carimbo Fls./Mov. (e, se o gerador
    tiver desenhado algo depois do rodapé, também o que vem depois do código
    de validação). A folha de assinatura é toda moldura. Página sem moldura
    devolve o texto inteiro como corpo.
    """
    texto = texto or ""
    carimbos = list(RX_CARIMBO.finditer(texto))
    if carimbos:
        inicio = carimbos[-1].start()
        codigo = RX_CODIGO.search(texto, inicio)
        fim = codigo.end() if codigo else len(texto)
        corpo = (texto[:inicio].rstrip() + "\n" + texto[fim:].strip()).strip()
        return corpo, texto[inicio:fim], False
    if RX_FOLHA_ASSINATURA.match(texto):
        return "", texto, True
    return texto.strip(), "", False


# ─────────────────────────────────────────────────────────────────
# Matriz completa
# ─────────────────────────────────────────────────────────────────

def _mul(m, n):
    """m × n na convenção do PDF ([a b c d e f], vetor-linha)."""
    a, b, c, d, e, f = m
    A, B, C, D, E, F = n
    return (a * A + b * C, a * B + b * D, c * A + d * C, c * B + d * D, e * A + f * C + E, e * B + f * D + F)


def _numeros(operandos):
    try:
        return tuple(float(x) for x in operandos)
    except (TypeError, ValueError):
        return None


def _tamanho(operando) -> int:
    bruto = getattr(operando, "original_bytes", None)
    if bruto is not None:
        return len(bruto)
    if isinstance(operando, (bytes, str)):
        return len(operando)
    return 0


class _Coletor:
    """Acompanha a matriz durante o `extract_text` e junta votos de direção e área de imagem.

    Recebe os operadores pelos visitantes do pypdf. Ao ver um `Do`, empilha
    o estado e, se o objeto for um form, entra nele (matriz = /Matrix × CTM,
    recursos do form); o visitante "depois" do mesmo `Do` desempilha — o
    pypdf só o chama quando termina o conteúdo do form.
    """

    def __init__(self, recursos, mediabox):
        self.ctm = _IDENTIDADE
        self.pilha: list = []
        self.tm = self.tlm = _IDENTIDADE
        self.entrelinha = 0.0
        self.recursos = recursos
        self.estados_do: list = []
        self.votos: Counter = Counter()
        self.area_imagem = 0.0
        self.esquerda = float(mediabox.left)
        self.base = float(mediabox.bottom)
        self.direita = float(mediabox.right)
        self.topo = float(mediabox.top)

    # -- recursos -------------------------------------------------------
    def _xobjeto(self, nome):
        try:
            recursos = self.recursos.get_object() if self.recursos is not None else None
            xobjetos = recursos.get("/XObject") if recursos is not None else None
            if xobjetos is None:
                return None
            objeto = xobjetos.get_object().get(nome)
            return objeto.get_object() if objeto is not None else None
        except Exception:
            return None

    # -- moldura ----------------------------------------------------------
    def _na_moldura(self, x, y) -> bool:
        """Rodapé na faixa abaixo de y=0 e carimbo no canto superior direito — só no eProtocolo."""
        if self.base >= 0:
            return False
        if y < -0.5:
            return True
        return x > self.direita - 90 and y > self.topo - 70

    # -- visitantes -------------------------------------------------------
    def antes(self, operador, operandos, _cm, _tm):
        if operador == b"q":
            self.pilha.append(self.ctm)
        elif operador == b"Q":
            if self.pilha:
                self.ctm = self.pilha.pop()
        elif operador == b"cm":
            m = _numeros(operandos)
            if m and len(m) == 6:
                self.ctm = _mul(m, self.ctm)
        elif operador == b"BT":
            self.tm = self.tlm = _IDENTIDADE
        elif operador == b"Tm":
            m = _numeros(operandos)
            if m and len(m) == 6:
                self.tm = self.tlm = m
        elif operador in (b"Td", b"TD"):
            m = _numeros(operandos)
            if m and len(m) == 2:
                if operador == b"TD":
                    self.entrelinha = -m[1]
                self.tm = self.tlm = _mul((1.0, 0.0, 0.0, 1.0, m[0], m[1]), self.tlm)
        elif operador == b"TL":
            m = _numeros(operandos[:1])
            if m:
                self.entrelinha = m[0]
        elif operador in (b"T*", b"'", b'"'):
            self.tm = self.tlm = _mul((1.0, 0.0, 0.0, 1.0, 0.0, -self.entrelinha), self.tlm)

        if operador in (b"Tj", b"TJ", b"'", b'"'):
            self._votar(operador, operandos)
        elif operador == b"Do":
            self._entrar(operandos)
        elif operador == b"INLINE IMAGE":
            self.area_imagem += abs(self.ctm[0] * self.ctm[3] - self.ctm[1] * self.ctm[2])

    def depois(self, operador, _operandos, _cm, _tm):
        if operador == b"Do" and self.estados_do:
            (self.ctm, self.pilha, self.tm, self.tlm, self.entrelinha, self.recursos) = self.estados_do.pop()

    def _votar(self, operador, operandos):
        if not operandos:
            return
        if operador == b"TJ":
            itens = operandos[0] if isinstance(operandos[0], (list, tuple)) else []
            n = sum(_tamanho(item) for item in itens)
        else:
            n = _tamanho(operandos[-1])
        if n <= 0:
            return
        m = _mul(self.tm, self.ctm)
        if abs(m[0]) < 1e-9 and abs(m[1]) < 1e-9:
            return
        if self._na_moldura(m[4], m[5]):
            return
        angulo = math.degrees(math.atan2(m[1], m[0])) % 360
        quadrante = int(round(angulo / 90.0)) % 4
        desvio = abs(angulo - quadrante * 90)
        if min(desvio, 360 - desvio) > TOLERANCIA_ANGULO:
            return
        self.votos[quadrante * 90] += n

    def _entrar(self, operandos):
        self.estados_do.append((self.ctm, self.pilha, self.tm, self.tlm, self.entrelinha, self.recursos))
        objeto = self._xobjeto(operandos[0]) if operandos else None
        if objeto is None:
            return
        subtipo = objeto.get("/Subtype")
        if subtipo == "/Image":
            self.area_imagem += abs(self.ctm[0] * self.ctm[3] - self.ctm[1] * self.ctm[2])
        elif subtipo == "/Form":
            matriz = _numeros(objeto.get("/Matrix", _IDENTIDADE)) or _IDENTIDADE
            if len(matriz) != 6:
                matriz = _IDENTIDADE
            self.ctm = _mul(matriz, self.ctm)
            self.pilha = []
            self.tm = self.tlm = _IDENTIDADE
            self.recursos = objeto.get("/Resources", self.recursos)

    # -- resultado --------------------------------------------------------
    def angulo(self) -> int | None:
        total = sum(self.votos.values())
        if total < 5:
            return None
        angulo, votos = self.votos.most_common(1)[0]
        if votos / total < MAIORIA:
            return None
        return angulo

    def cobertura(self) -> float:
        area = (self.direita - self.esquerda) * (self.topo - self.base)
        if area <= 0:
            return 0.0
        return round(min(self.area_imagem / area, 1.0), 3)


def _rotacao(pagina_pdf) -> int:
    try:
        return int(pagina_pdf.get("/Rotate", 0) or 0) % 360
    except (TypeError, ValueError):
        return 0


def _contar(texto: str) -> int:
    return len("".join((texto or "").split()))


def _ler_pagina(indice: int, pagina_pdf) -> Pagina:
    mediabox = pagina_pdf.mediabox
    coletor = _Coletor(pagina_pdf.get("/Resources"), mediabox)
    try:
        texto = pagina_pdf.extract_text(
            visitor_operand_before=coletor.antes,
            visitor_operand_after=coletor.depois,
        ) or ""
    except Exception as exc:  # página corrompida: segue sem texto
        capture(exc, "leitura.pdf.extrair_texto", level=logging.WARNING, pagina=indice)
        texto = ""
    corpo, _moldura, folha_assinatura = separar_moldura(texto)
    cobertura = coletor.cobertura()
    n_corpo = _contar(corpo)
    sem_texto = not folha_assinatura and (
        n_corpo < MINIMO_CARACTERES or (cobertura >= COBERTURA_ESCANEADA and n_corpo < POUCO_TEXTO)
    )
    return Pagina(
        indice=indice,
        texto=texto,
        corpo=corpo,
        largura=round(float(mediabox.width), 2),
        altura=round(float(mediabox.height), 2),
        rotacao=_rotacao(pagina_pdf),
        angulo_texto=coletor.angulo(),
        cobertura_imagem=cobertura,
        sem_texto=sem_texto,
        base=round(float(mediabox.bottom), 2),
    )


def ler_paginas(dados: bytes) -> list[Pagina]:
    """Lê todas as páginas do PDF (ou da imagem PNG/JPG, que vira PDF de 1 página).

    Levanta `ArquivoIlegivel` se o arquivo não abrir. Página que não dá para
    interpretar volta vazia (e `sem_texto`), sem derrubar as outras.
    """
    leitor = _abrir(como_pdf(dados))
    return [_ler_pagina(indice, pagina) for indice, pagina in enumerate(leitor.pages)]


# ─────────────────────────────────────────────────────────────────
# Rotação
# ─────────────────────────────────────────────────────────────────

def rotacao_para_ficar_em_pe(pagina: Pagina) -> int | None:
    """O /Rotate final que deixa o texto da página em pé; None se não dá para saber.

    O texto aparece na tela a (ângulo no conteúdo − /Rotate); para ficar a
    0°, o /Rotate tem de ser o próprio ângulo do conteúdo. Um diário
    paisagem que veio deitado numa página retrato (conteúdo a 90° ou 270°)
    fica, com isso, em paisagem.
    """
    if pagina.angulo_texto is None:
        return None
    return int(pagina.angulo_texto) % 360


def fica_em_paisagem(pagina: Pagina, rotacao: int | None = None) -> bool:
    """Se, com o /Rotate dado (ou o atual), a página aparece mais larga que alta."""
    rotacao = pagina.rotacao if rotacao is None else rotacao
    deitada = (rotacao % 180) == 90
    return (pagina.largura > pagina.altura) != deitada


def recortar(dados: bytes, indices: list[int], rotacoes: dict[int, int] | None = None) -> bytes:
    """PDF só com as páginas `indices` (na ordem dada), com o /Rotate de `rotacoes`.

    `rotacoes` mapeia índice da página → /Rotate final (valores fora de
    0..359 são normalizados; None deixa como está). O resultado não leva
    marcadores nem metadados do original — o /Author do eProtocolo é o CPF
    de quem baixou o arquivo.
    """
    from pypdf import PdfWriter
    from pypdf.generic import NameObject
    from pypdf.generic import NumberObject

    leitor = _abrir(como_pdf(dados))
    total = len(leitor.pages)
    rotacoes = rotacoes or {}
    escritor = PdfWriter()
    for indice in indices:
        if not 0 <= int(indice) < total:
            raise IndexError(f"Página {indice} fora do PDF ({total} páginas).")
        escritor.add_page(leitor.pages[int(indice)])
        rotacao = rotacoes.get(indice)
        if rotacao is not None:
            escritor.pages[-1][NameObject("/Rotate")] = NumberObject(int(rotacao) % 360)
    saida = BytesIO()
    escritor.write(saida)
    return saida.getvalue()


def normalizar_orientacao(dados: bytes, *, exigir_paisagem: bool = False) -> tuple[bytes, list[int | None]]:
    """Deixa cada página em pé; devolve (PDF, /Rotate aplicado por página).

    Página com texto: /Rotate = direção do conteúdo (em pé, e em paisagem
    quando o conteúdo é paisagem). Página só de imagem: quem decide é o OCR
    (tesseract, se houver; até `OCR_MAX_PAGINAS` páginas), não o pouco texto
    que ela tenha; sem OCR, vale esse pouco texto, se houver. Sem resposta
    nenhuma, a página fica como está — ou, com `exigir_paisagem` (diário de
    bordo), deitada em 90° só para ficar em paisagem — e o item da lista é
    None, para a tela pedir conferência (botões ↺ ↻). Página com texto em
    pé nunca é deitada só por causa de `exigir_paisagem`.

    Se nada muda, devolve os mesmos bytes (não reescreve o PDF — uma
    assinatura digital embutida continua válida).
    """
    from . import ocr

    pdf = como_pdf(dados)
    paginas = ler_paginas(pdf)
    orcamento = ocr.max_paginas() if ocr.disponivel() else 0
    finais: dict[int, int] = {}
    decididas: list[int | None] = []
    for pagina in paginas:
        rotacao = rotacao_para_ficar_em_pe(pagina)
        if pagina.sem_texto and orcamento > 0:
            # Na página só de imagem, o OCR vale mais que o pouco texto que ela tenha.
            orcamento -= 1
            pelo_ocr = ocr.orientacao_da_pagina(pdf, pagina.indice)
            rotacao = pelo_ocr if pelo_ocr is not None else rotacao
        if rotacao is None:
            final = pagina.rotacao
            if exigir_paisagem and not fica_em_paisagem(pagina, final):
                final = (final + 90) % 360
            finais[pagina.indice] = final
            decididas.append(None)
        else:
            finais[pagina.indice] = rotacao
            decididas.append(rotacao)
    if all(finais[p.indice] == p.rotacao for p in paginas):
        return pdf, decididas
    return recortar(pdf, [p.indice for p in paginas], finais), decididas
