"""OCR opcional com o tesseract instalado no servidor.

Serve para a página que é só imagem (comprovante fotografado, termo
escaneado): ler o texto e descobrir para que lado ela está. Sem o binário
— ou com `OCR_ATIVO = False` — `disponivel()` diz não e o resto do sistema
segue, pedindo na tela o que não conseguiu ler. Nada sai do servidor.

Ajustes (todos opcionais, lidos de `settings` com padrão):

- `TESSERACT_CMD`: caminho do executável (padrão: `tesseract` no PATH;
  no Windows, algo como `C:\\Program Files\\Tesseract-OCR\\tesseract.exe`).
- `OCR_ATIVO` (True), `OCR_MAX_PAGINAS` (12, por chamada de quem lê um
  processo inteiro), `OCR_TIMEOUT` (30 s por execução), `OCR_DPI` (200),
  `OCR_IDIOMA` ("por").

O tesseract roda com `OMP_THREAD_LIMIT=1`: sem isso, o OpenMP dele disputa
os núcleos com os outros workers e uma página que leva 1 s passa de 20 s.

**Orientação.** O detector de orientação do tesseract (OSD, `--psm 0`)
acerta o eixo (em pé × deitada), mas em texto curto e todo em maiúsculas —
justamente o comprovante — erra o sentido e diz 180° com confiança baixa.
Por isso a resposta dele é conferida: a página é lida no sentido que ele
indicou e no oposto, e vale o sentido em que sai mais palavra reconhecida
e desenhada na horizontal. Com confiança alta do OSD e leitura boa, a
segunda leitura é dispensada.

Nunca registra em log o texto lido.
"""

from __future__ import annotations

import logging
import os
import re
import shutil
import subprocess
from dataclasses import dataclass
from io import BytesIO

from django.conf import settings

from core.errors import capture

__all__ = [
    "LeituraOCR",
    "disponivel",
    "max_paginas",
    "analisar_pagina",
    "texto_da_pagina",
    "orientacao_da_pagina",
    "texto_de_foto",
]

_LOG = logging.getLogger(__name__)

#: Maior lado da imagem enviada ao tesseract, em pixels (foto de celular
#: convertida a 72 dpi vira página enorme; a 200 dpi daria 10 mil pixels).
MAIOR_LADO = 3500
#: Confiança do OSD a partir da qual o sentido dele é aceito sem contraprova.
CONFIANCA_OSD_ALTA = 5.0
#: Pontos (letras de palavras confiáveis e horizontais) para dar a leitura por boa.
PONTOS_LEITURA_BOA = 40
#: Abaixo disto, não dá para dizer para que lado a página está.
PONTOS_MINIMOS = 12


@dataclass
class LeituraOCR:
    """Resultado do OCR de uma página.

    `rotacao` é o /Rotate final que deixa a página em pé (mesma convenção de
    `pdf.rotacao_para_ficar_em_pe`), ou None se não deu para saber; `texto`
    é o que se leu com a página nesse sentido; `pontos` mede a qualidade
    da leitura (letras em palavras reconhecidas com confiança).
    """

    rotacao: int | None
    texto: str
    pontos: int = 0


def _comando() -> str:
    return str(getattr(settings, "TESSERACT_CMD", "") or "tesseract")


def _timeout() -> float:
    return float(getattr(settings, "OCR_TIMEOUT", 30) or 30)


def _dpi() -> int:
    return int(getattr(settings, "OCR_DPI", 200) or 200)


def _idioma() -> str:
    return str(getattr(settings, "OCR_IDIOMA", "por") or "")


def max_paginas() -> int:
    """Quantas páginas, no máximo, uma leitura de processo manda para o OCR."""
    try:
        return max(0, int(getattr(settings, "OCR_MAX_PAGINAS", 12)))
    except (TypeError, ValueError):
        return 12


def disponivel() -> bool:
    """O OCR pode ser usado: ligado nos ajustes, tesseract encontrado e pypdfium2 instalado."""
    if not getattr(settings, "OCR_ATIVO", True):
        return False
    if not shutil.which(_comando()):
        return False
    try:
        import pypdfium2  # noqa: F401
    except ImportError:
        return False
    return True


# ─────────────────────────────────────────────────────────────────
# Imagem da página
# ─────────────────────────────────────────────────────────────────

def _renderizar(dados: bytes, indice: int, *, giro_extra: int = 0, dpi: int | None = None, sem_rodape: bool = True):
    """(imagem em tons de cinza, /Rotate atual) da página, como aparece na tela, girada mais `giro_extra`.

    A faixa do rodapé do eProtocolo (abaixo de y=0) fica de fora: é texto
    impresso, sempre em pé, e atrapalharia o OSD de uma página deitada.
    """
    import pypdfium2 as pdfium

    documento = pdfium.PdfDocument(dados)
    try:
        pagina = documento[indice]
        rotacao = int(pagina.get_rotation() or 0) % 360
        esquerda, base, direita, topo = pagina.get_mediabox()
        largura, altura = pagina.get_size()
        escala = (dpi or _dpi()) / 72.0
        escala = min(escala, MAIOR_LADO / max(largura, altura, 1.0))
        corte = [0.0, 0.0, 0.0, 0.0]  # esquerda, baixo, direita, cima, depois de girar
        total = (rotacao + giro_extra) % 360
        if sem_rodape and base < 0:
            # A borda de baixo do conteúdo vai parar à esquerda (90), em cima (180) ou à direita (270).
            corte[{0: 1, 90: 0, 180: 3, 270: 2}[total]] = -base
        bitmap = pagina.render(scale=escala, rotation=giro_extra % 360, crop=tuple(corte), grayscale=True)
        imagem = bitmap.to_pil()
        imagem.load()
        return imagem.copy(), rotacao
    finally:
        documento.close()


def _png(imagem, dpi: int) -> bytes:
    saida = BytesIO()
    imagem.save(saida, format="PNG", dpi=(dpi, dpi))
    return saida.getvalue()


# ─────────────────────────────────────────────────────────────────
# Tesseract
# ─────────────────────────────────────────────────────────────────

def _tesseract(png: bytes, argumentos: list[str], contexto: str) -> str | None:
    """Saída padrão do tesseract lendo a imagem pela entrada padrão; None se falhar."""
    ambiente = dict(os.environ, OMP_THREAD_LIMIT="1")
    try:
        resultado = subprocess.run(
            [_comando(), "stdin", "stdout", *argumentos],
            input=png,
            capture_output=True,
            timeout=_timeout(),
            env=ambiente,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        capture(exc, f"leitura.ocr.{contexto}.timeout", level=logging.WARNING)
        return None
    except OSError as exc:
        capture(exc, f"leitura.ocr.{contexto}.executar", level=logging.WARNING)
        return None
    if resultado.returncode != 0:
        # Só o código de saída: a mensagem de erro não tem texto da página,
        # mas também não ajuda a quem lê o log.
        _LOG.warning("tesseract (%s) terminou com código %s", contexto, resultado.returncode)
        return None
    return (resultado.stdout or b"").decode("utf-8", errors="replace")


def _ocr_tsv(imagem, dpi: int) -> tuple[str, int] | None:
    """(texto, pontos) de uma leitura com `--psm 3` em TSV; None se o tesseract falhar.

    Pontos = letras de palavras com confiança ≥ 60 cuja caixa é mais larga
    que alta (texto de pé). Texto de cabeça para baixo sai como lixo de
    confiança baixa; texto deitado, que o tesseract às vezes consegue ler
    girando por conta própria, tem caixas altas e não pontua.
    """
    png = _png(imagem, dpi)
    argumentos = ["--psm", "3", "--dpi", str(dpi)]
    idioma = _idioma()
    saida = _tesseract(png, (["-l", idioma] if idioma else []) + argumentos + ["tsv"], "texto")
    if saida is None and idioma:
        # Idioma não instalado (só o inglês vem por padrão no Windows): tenta sem.
        saida = _tesseract(png, argumentos + ["tsv"], "texto")
    if saida is None:
        return None
    linhas: dict[tuple, list[str]] = {}
    pontos = 0
    for linha in saida.splitlines()[1:]:
        partes = linha.split("\t")
        if len(partes) < 12 or partes[0] != "5":
            continue
        palavra = partes[11].strip()
        if not palavra:
            continue
        chave = tuple(int(p) for p in partes[1:5])  # página, bloco, parágrafo, linha
        linhas.setdefault(chave, []).append(palavra)
        try:
            confianca = float(partes[10])
            largura, altura = int(partes[8]), int(partes[9])
        except ValueError:
            continue
        util = sum(1 for c in palavra if c.isalnum())
        if confianca >= 60 and util >= 2 and largura >= altura:
            pontos += util
    blocos: list[str] = []
    ultimo_bloco = None
    for chave in sorted(linhas):
        if ultimo_bloco is not None and chave[:2] != ultimo_bloco:
            blocos.append("")
        blocos.append(" ".join(linhas[chave]))
        ultimo_bloco = chave[:2]
    return "\n".join(blocos).strip(), pontos


_RX_OSD_GIRO = re.compile(r"Rotate:\s*(\d+)")
_RX_OSD_CONFIANCA = re.compile(r"Orientation confidence:\s*([\d.]+)")


def _osd(imagem, dpi: int) -> tuple[int, float] | None:
    """(giro horário que endireita a imagem, confiança) pelo OSD; None se não souber."""
    saida = _tesseract(_png(imagem, dpi), ["--psm", "0", "--dpi", str(dpi)], "osd")
    if not saida:
        return None
    giro = _RX_OSD_GIRO.search(saida)
    confianca = _RX_OSD_CONFIANCA.search(saida)
    if not giro:
        return None
    return int(giro.group(1)) % 360, float(confianca.group(1)) if confianca else 0.0


# ─────────────────────────────────────────────────────────────────
# API
# ─────────────────────────────────────────────────────────────────

def analisar_pagina(dados: bytes, indice: int) -> LeituraOCR:
    """Descobre para que lado a página está e lê o texto nesse sentido.

    `dados` é o PDF inteiro; `indice`, a página (a partir de 0). Sem OCR
    disponível, ou se o tesseract falhar, devolve rotação None e texto "".
    Custa de uma a três execuções do tesseract (cerca de 1 s cada a 200 dpi).
    """
    if not disponivel():
        return LeituraOCR(None, "")
    dpi = _dpi()
    try:
        imagem, rotacao_atual = _renderizar(dados, indice, dpi=dpi)
    except Exception as exc:
        capture(exc, "leitura.ocr.renderizar", level=logging.WARNING, pagina=indice)
        return LeituraOCR(None, "")

    osd = _osd(imagem, dpi)
    if osd is not None:
        giro, confianca = osd
        candidatos = [giro, (giro + 180) % 360]
    else:
        confianca = 0.0
        candidatos = [0, 180, 90, 270]

    melhor: tuple[int, str, int] | None = None
    for giro in candidatos:
        lido = _ocr_tsv(imagem.rotate(-giro, expand=True) if giro else imagem, dpi)
        if lido is None:
            continue
        texto, pontos = lido
        if melhor is None or pontos > melhor[2]:
            melhor = (giro, texto, pontos)
        if confianca >= CONFIANCA_OSD_ALTA and pontos >= PONTOS_LEITURA_BOA:
            break
    if melhor is None:
        return LeituraOCR(None, "")
    giro, texto, pontos = melhor
    if pontos < PONTOS_MINIMOS:
        return LeituraOCR(None, texto, pontos)
    return LeituraOCR((rotacao_atual + giro) % 360, texto, pontos)


def texto_da_pagina(dados: bytes, indice: int, *, rotacao: int | None = None) -> str:
    """O texto da página pelo OCR ("" se não houver OCR ou nada for lido).

    Com `rotacao` (o /Rotate final que deixa a página em pé, já conhecido),
    lê uma vez nesse sentido; sem ela, descobre o sentido antes
    (`analisar_pagina`).
    """
    if rotacao is None:
        return analisar_pagina(dados, indice).texto
    if not disponivel():
        return ""
    dpi = _dpi()
    try:
        import pypdfium2 as pdfium

        documento = pdfium.PdfDocument(dados)
        try:
            atual = int(documento[indice].get_rotation() or 0) % 360
        finally:
            documento.close()
        imagem, _ = _renderizar(dados, indice, giro_extra=(int(rotacao) - atual) % 360, dpi=dpi)
    except Exception as exc:
        capture(exc, "leitura.ocr.renderizar", level=logging.WARNING, pagina=indice)
        return ""
    lido = _ocr_tsv(imagem, dpi)
    return lido[0] if lido else ""


def orientacao_da_pagina(dados: bytes, indice: int) -> int | None:
    """O /Rotate final que deixa a página em pé, pelo OCR; None se não souber."""
    return analisar_pagina(dados, indice).rotacao


def texto_de_foto(dados: bytes) -> str:
    """Segunda leitura de uma FOTO (JPG/PNG), direto da imagem original.

    Para quando a primeira leitura (página renderizada) deixou de achar algum
    dado: tons de cinza, o dobro do tamanho, contraste esticado e `--psm 6`
    (bloco único de texto), que no papel térmico do caixa eletrônico lê
    melhor os números. "" se não houver OCR ou der errado.
    """
    if not disponivel():
        return ""
    try:
        from PIL import Image
        from PIL import ImageOps

        with Image.open(BytesIO(dados)) as original:
            imagem = ImageOps.grayscale(ImageOps.exif_transpose(original))
        fator = min(2.0, MAIOR_LADO / max(imagem.width, imagem.height, 1))
        if fator > 1:
            imagem = imagem.resize((int(imagem.width * fator), int(imagem.height * fator)), Image.LANCZOS)
        imagem = ImageOps.autocontrast(imagem, cutoff=2)
    except Exception as exc:
        capture(exc, "leitura.ocr.foto", level=logging.WARNING)
        return ""
    idioma = _idioma()
    argumentos = ["--psm", "6", "--dpi", "300"]
    png = _png(imagem, 300)
    saida = _tesseract(png, (["-l", idioma] if idioma else []) + argumentos, "foto")
    if saida is None and idioma:
        saida = _tesseract(png, argumentos, "foto")
    return (saida or "").strip()
