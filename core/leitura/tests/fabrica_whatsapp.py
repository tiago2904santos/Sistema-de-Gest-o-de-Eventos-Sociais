"""Fábrica de conversas do WhatsApp sintéticas: exportação em .zip e print.

As conversas reais têm nomes e telefones e **nunca** entram no
repositório. Aqui tudo é fictício:

- `conversa_iphone()` / `conversa_android()`: o texto do `_chat.txt`
  (iPhone, com as marcas U+200E) e do "Conversa do WhatsApp com….txt"
  (Android), com avisos do sistema e anexos no meio;
- `png_pequeno()`: uma foto PNG mínima gerada com o PIL;
- `zip_whatsapp(...)`: o .zip da exportação, montado em memória;
- `print_whatsapp(...)`: a captura de tela de uma conversa, desenhada com o
  PIL (tema claro ou escuro), para o OCR ler.
"""

from __future__ import annotations

import io
import zipfile

FONTE = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
FONTE_NEGRITO = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"


def conversa_iphone() -> str:
    """O `_chat.txt` do iPhone: colchetes, segundos e U+200E nas linhas de sistema."""
    return (
        "‎[24/09/2026, 10:30:00] Maria Exemplo: ‎As mensagens e as ligações são protegidas com a "
        "criptografia de ponta a ponta.\n"
        "[24/09/2026, 10:35:12] Maria Exemplo: Bom dia! Aqui é a Maria, do Jornal Exemplo.\n"
        "[24/09/2026, 10:36:40] Maria Exemplo: Gostaria de uma entrevista com o delegado sobre a operação de ontem\n"
        "em Cidade Exemplo, amanhã às 14h.\n"
        "‎[24/09/2026, 10:37:05] Maria Exemplo: ‎<anexado: 00000012-PHOTO-2026-09-24-10-37-05.jpg>\n"
        "‎[24/09/2026, 10:37:30] Maria Exemplo: ‎imagem ocultada\n"
        "[24/09/2026, 10:40:00] ASCOM Exemplo: Bom dia, Maria! Vou verificar.\n"
    )


def conversa_android() -> str:
    """O "Conversa do WhatsApp com Fulano.txt" do Android: "dd/mm/aaaa hh:mm - Nome: ..."."""
    return (
        "24/09/2026 10:30 - As mensagens e ligações são protegidas com a criptografia de ponta a ponta e ficam "
        "somente entre você e os participantes desta conversa.\n"
        "24/09/2026 10:35 - Maria Exemplo: Bom dia! Aqui é a Maria, do Jornal Exemplo.\n"
        "24/09/2026 10:36 - Maria Exemplo: Gostaria de uma entrevista com o delegado sobre a operação de ontem\n"
        "em Cidade Exemplo, amanhã às 14h.\n"
        "24/09/2026 10:37 - Maria Exemplo: IMG-20260924-WA0001.jpg (arquivo anexado)\n"
        "24/09/2026 10:38 - Maria Exemplo: <Mídia oculta>\n"
        "24/09/2026 10:39 - Beto Exemplo saiu\n"
        "24/09/2026 10:40 - ASCOM Exemplo: Bom dia, Maria! Vou verificar.\n"
    )


def png_pequeno(cor=(200, 40, 40), tamanho=(8, 8)) -> bytes:
    """Uma "foto" PNG mínima, gerada na hora."""
    from PIL import Image

    saida = io.BytesIO()
    Image.new("RGB", tamanho, cor).save(saida, format="PNG")
    return saida.getvalue()


def zip_whatsapp(arquivos: dict[str, bytes | str] | None = None, *, conversa: str | None = None,
                 nome_conversa: str = "_chat.txt", fotos: int = 1) -> bytes:
    """O .zip da exportação: a conversa, `fotos` PNGs pequenos e o que vier em `arquivos`.

    `arquivos` ({nome: conteúdo}) entra como está — inclusive nomes com ".."
    ou caminho absoluto, para testar o .zip malicioso.
    """
    saida = io.BytesIO()
    with zipfile.ZipFile(saida, "w", zipfile.ZIP_DEFLATED) as zf:
        if nome_conversa:
            zf.writestr(nome_conversa, (conversa if conversa is not None else conversa_iphone()).encode("utf-8"))
        for n in range(fotos):
            zf.writestr(f"00000012-PHOTO-2026-09-24-10-37-0{n}.png", png_pequeno())
        for nome, conteudo in (arquivos or {}).items():
            zf.writestr(nome, conteudo.encode("utf-8") if isinstance(conteudo, str) else conteudo)
    return saida.getvalue()


def zip_bomba(megas: int = 60) -> bytes:
    """Um .zip pequeno que descompacta em `megas` MB de zeros (a "bomba")."""
    saida = io.BytesIO()
    with zipfile.ZipFile(saida, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("_chat.txt", conversa_iphone().encode("utf-8"))
        with zf.open("00000013-PHOTO.jpg", "w", force_zip64=True) as destino:
            bloco = b"\x00" * (1024 * 1024)
            for _ in range(megas):
                destino.write(bloco)
    return saida.getvalue()


FALAS_DO_PRINT = (
    ("in", ["Bom dia! Aqui é a Maria, do Jornal", "Exemplo de Cidade Exemplo."], "10:35"),
    ("in", ["Gostaria de uma entrevista com o", "delegado sobre a operação de ontem."], "10:36"),
    ("out", ["Bom dia, Maria! Vou verificar."], "10:40"),
    ("in", ["Pode ser amanhã às 14h?"], "10:41"),
)


def print_whatsapp(*, contato: str = "Maria Exemplo", separador: str = "24 DE SETEMBRO DE 2026",
                   falas=FALAS_DO_PRINT, escuro: bool = False, formato: str = "PNG") -> bytes:
    """A captura de tela de uma conversa: barra de status, contato, "online",
    separador de data, bolhas com a hora e a caixa "Mensagem" embaixo."""
    from PIL import Image, ImageDraw, ImageFont

    largura, altura = 720, 1280
    fundo = (17, 27, 33) if escuro else (236, 229, 221)
    tinta = (233, 237, 239) if escuro else (17, 17, 17)
    bolha_recebida = (32, 44, 51) if escuro else (255, 255, 255)
    bolha_enviada = (0, 92, 75) if escuro else (220, 248, 198)
    imagem = Image.new("RGB", (largura, altura), fundo)
    d = ImageDraw.Draw(imagem)
    fonte = ImageFont.truetype(FONTE, 26)
    pequena = ImageFont.truetype(FONTE, 20)
    negrito = ImageFont.truetype(FONTE_NEGRITO, 30)
    d.rectangle([0, 0, largura, 150], fill=(31, 44, 52) if escuro else (0, 128, 105))
    d.text((24, 12), "10:52", font=pequena, fill=(255, 255, 255))
    d.text((560, 12), "4G  87%", font=pequena, fill=(255, 255, 255))
    d.text((24, 60), "<", font=negrito, fill=(255, 255, 255))
    d.text((80, 55), contato, font=negrito, fill=(255, 255, 255))
    d.text((80, 98), "online", font=pequena, fill=(255, 255, 255))
    y = 190
    if separador:
        d.rounded_rectangle([230, y, 490, y + 40], 10, fill=bolha_recebida)
        d.text((244, y + 10), separador, font=ImageFont.truetype(FONTE, 18), fill=tinta)
        y += 80
    for lado, linhas, hora in falas:
        x = 30 if lado == "in" else 250
        alto = 40 * len(linhas) + 40
        d.rounded_rectangle([x, y, x + 440, y + alto], 14, fill=bolha_recebida if lado == "in" else bolha_enviada)
        for i, linha in enumerate(linhas):
            d.text((x + 16, y + 10 + 40 * i), linha, font=fonte, fill=tinta)
        d.text((x + 360, y + alto - 30), hora, font=pequena, fill=(120, 120, 120))
        y += alto + 24
    d.rectangle([0, altura - 90, largura, altura], fill=(31, 44, 52) if escuro else (240, 240, 240))
    d.text((40, altura - 65), "Mensagem", font=fonte, fill=(130, 130, 130))
    saida = io.BytesIO()
    imagem.save(saida, format=formato)
    return saida.getvalue()
