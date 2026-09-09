"""Desenhar por cima de um PDF já pronto, sem regerá-lo.

Duas telas fazem isso hoje: a assinatura eletrônica carimba um PNG sobre o snapshot
do RT/diário, e a prestação carimba o número de solicitação sobre o ofício que voltou
assinado do eProtocolo. O que as duas compartilham não é o desenho — é a manipulação
do PDF em volta dele, que é a parte que morde:

- PDF cifrado com senha vazia precisa ser decifrado antes de qualquer leitura;
- página girada precisa ter a rotação transferida para o conteúdo, senão a `mediabox`
  não bate com o que foi exibido na tela e o carimbo cai em outro lugar (medido no
  diário de bordo, que sai em paisagem);
- o overlay é uma página inteira do tamanho da original, fundida com `merge_page`.

Por isso o helper recebe **funções de desenho**, uma por página, e cuida do resto. Quem
chama só sabe de reportlab.

Convenção de coordenadas, a mesma nas duas telas: `x` e `y` são **frações da página com
origem no topo-esquerdo**, porque é assim que o navegador mede. A conversão para o
sistema do PDF (origem embaixo) é feita por `y_pdf`, e não por cada chamador — foi um
sinal trocado espalhado por dois arquivos que motivou este módulo.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from io import BytesIO

from core.errors import capture


class PdfOverlayError(Exception):
    """Erro amigável: PDF ilegível ou sem páginas."""


@dataclass(frozen=True)
class Pagina:
    """Medidas da página que está sendo desenhada, em pontos."""

    indice: int
    largura: float
    altura: float

    def x_pdf(self, fracao: float) -> float:
        """Fração horizontal (0 à esquerda) → pontos."""
        return float(fracao) * self.largura

    def y_pdf(self, fracao: float, altura_caixa: float = 0.0) -> float:
        """Fração vertical medida do TOPO → coordenada do PDF, medida de baixo.

        `altura_caixa` (em pontos) desce a origem para o rodapé da caixa, que é o que
        reportlab espera em `drawImage`. Para texto, deixe em zero: `drawString` já
        assenta na linha de base.
        """
        return self.altura - (float(fracao) * self.altura) - float(altura_caixa)


#: Assinatura de quem desenha: recebe o canvas reportlab e as medidas da página.
Desenho = Callable[[object, Pagina], None]


def desenhar_overlay(origem_bytes: bytes, por_pagina: dict[int, Desenho]) -> bytes:
    """Devolve o PDF com o desenho de cada índice fundido na sua página.

    Índice fora do documento é ignorado em silêncio — quem chama já resolveu para qual
    página vai, e derrubar a requisição por causa de um carimbo perdido custaria o
    documento inteiro.
    """
    from pypdf import PdfReader
    from pypdf import PdfWriter
    from reportlab.pdfgen import canvas

    reader = PdfReader(BytesIO(origem_bytes))
    if getattr(reader, "is_encrypted", False):
        try:
            reader.decrypt("")
        except Exception as exc:
            capture(exc, "documentos.pdf_overlay.decrypt")

    total = len(reader.pages)
    if total == 0:
        raise PdfOverlayError("O documento não possui páginas.")

    for indice, desenho in sorted(por_pagina.items()):
        if not (0 <= int(indice) < total):
            continue
        page = reader.pages[int(indice)]
        if page.rotation:
            page.transfer_rotation_to_content()

        medidas = Pagina(
            indice=int(indice),
            largura=float(page.mediabox.width),
            altura=float(page.mediabox.height),
        )

        buffer = BytesIO()
        c = canvas.Canvas(buffer, pagesize=(medidas.largura, medidas.altura))
        desenho(c, medidas)
        c.save()
        buffer.seek(0)
        page.merge_page(PdfReader(buffer).pages[0])

    writer = PdfWriter()
    for page in reader.pages:
        writer.add_page(page)
    saida = BytesIO()
    writer.write(saida)
    writer.close()
    return saida.getvalue()
