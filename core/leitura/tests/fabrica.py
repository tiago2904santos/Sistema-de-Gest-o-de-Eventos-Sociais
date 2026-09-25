"""Fábrica de PDFs sintéticos para testar a leitura de processos e anexos.

Os processos reais têm nomes e CPFs e **nunca** entram no repositório. Esta
fábrica desenha com reportlab/pypdf o que importa deles: a moldura do
eProtocolo (carimbo Fls./Mov., rodapé "Inserido ao protocolo … código"),
a folha de assinatura "Na", a capa lida por coordenadas, os marcadores
"N - arquivo.pdf", a página "embrulhada" (Form XObject com o eixo Y
invertido e `cm` de desinversão, que engana o pypdf), documento aninhado,
diário paisagem deitado, página só de imagem e comprovantes de banco.

Uso típico num teste de outro app::

    from core.leitura.tests import fabrica as f

    cpf = f.gerar_cpf(1)
    pdf = f.processo_eprotocolo(
        [
            f.Doc(f.oficio_viagens(numero=12, ano=2026, protocolo="26.613.666-8",
                                   servidores=[("FULANO DE TAL", cpf)]),
                  arquivo="Of.12-2026.pdf", assinantes=[("Chefe da Silva", f.gerar_cpf(2))]),
            f.Doc(f.despacho(protocolo="26.613.666-8"), arquivo="DESPACHO_1.pdf"),
            f.Doc(f.relatorio_tecnico(oficio="12/2026", nome="FULANO DE TAL", cpf=cpf),
                  arquivo="RT.pdf", assinantes=[("Fulano de Tal", cpf)]),
            f.Doc(f.girar_conteudo(f.diario_bordo(oficio="12/2026"), 90), arquivo="Diario.pdf",
                  embrulhar=True),
            f.Doc(f.comprovante("bb_saque", nome="FULANO DE TAL", cpf=cpf), arquivo="saque.pdf"),
        ],
        protocolo="26.613.666-8",
    )

Atalhos prontos: `processo_viagens(servidores=[...])` (capa, ofício,
despacho, um RT por servidor, diário deitado e um comprovante por servidor)
e `processo_coffee_break()` (a mesma estrutura dos processos reais: 16
documentos).

Peças soltas, para montar o caso que o teste precisa:

- documentos: `oficio_viagens`, `oficio_coffee_break`, `despacho`,
  `relatorio_tecnico`, `diario_bordo` (A4 deitado), `termo_autorizacao`,
  `justificativa`, `ordem_servico`, `plano_trabalho`, `nota_fiscal`,
  `certifico`, `certidao`, `contrato`, `aditivo`, `nota_empenho`,
  `nota_liquidacao`, `email_impresso`, `comprovante(modelo)` (ver
  `MODELOS_COMPROVANTE`: saque em terminal, Pix, TED, transferência e
  depósito de dez bancos);
- moldura do eProtocolo: `emoldurar` (carimbo + rodapé, com `embrulhar`
  para a página de Y invertido; duas vezes = aninhado), `folha_assinatura`,
  `capa_eprotocolo`, `rodape_eprotocolo`;
- orientação: `com_rotate` (/Rotate), `girar_conteudo` (girado dentro da
  página), `em_form` (girado só pela /Matrix de um Form XObject);
- imagem: `pagina_imagem` (página sem texto), `imagem_png`;
- conferência visual: `imagem_da_pagina` + `semelhanca`;
- utilidades: `pagina`, `paginas`, `juntar`, `gerar_cpf`, `formatar_cpf`.

Todas as funções de documento devolvem `bytes` de um PDF (ou PNG, em
`imagem_png`). Os documentos imitam o texto que o próprio sistema imprime
(`templates/documentos/pdf/*.html`, `documentos/resources/*`) e, no Coffee
Break, o dos processos de pagamento reais. CPFs: use `gerar_cpf(n)` (dígito
verificador válido, número fictício). Precisa de reportlab, pypdf e — só
para `pagina_imagem`, `imagem_png` e `imagem_da_pagina` — pypdfium2.
"""

from __future__ import annotations

import hashlib
import io
import textwrap
from dataclasses import dataclass
from dataclasses import field

from reportlab.lib.pagesizes import A4
from reportlab.lib.pagesizes import landscape
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas

__all__ = [
    "Doc",
    "gerar_cpf",
    "formatar_cpf",
    "pagina",
    "paginas",
    "juntar",
    "com_rotate",
    "girar_conteudo",
    "em_form",
    "rodape_eprotocolo",
    "emoldurar",
    "folha_assinatura",
    "capa_eprotocolo",
    "processo_eprotocolo",
    "processo_viagens",
    "processo_coffee_break",
    "pagina_imagem",
    "imagem_png",
    "imagem_da_pagina",
    "semelhanca",
    "oficio_viagens",
    "oficio_coffee_break",
    "despacho",
    "relatorio_tecnico",
    "diario_bordo",
    "termo_autorizacao",
    "justificativa",
    "ordem_servico",
    "plano_trabalho",
    "nota_fiscal",
    "certifico",
    "certidao",
    "contrato",
    "aditivo",
    "nota_empenho",
    "nota_liquidacao",
    "email_impresso",
    "comprovante",
    "linhas_comprovante",
    "MODELOS_COMPROVANTE",
]


# ─────────────────────────────────────────────────────────────────
# CPF fictício
# ─────────────────────────────────────────────────────────────────

def gerar_cpf(semente: int) -> str:
    """CPF de 11 dígitos com dígito verificador válido, derivado de `semente` (sempre o mesmo)."""
    base = f"{(semente * 7919 + 123456789) % 10**9:09d}"
    if len(set(base)) == 1:
        base = "1" + base[1:-1] + "2"
    numeros = [int(c) for c in base]
    for tamanho in (9, 10):
        soma = sum(n * (tamanho + 1 - i) for i, n in enumerate(numeros[:tamanho]))
        numeros.append((soma * 10 % 11) % 10)
    return "".join(str(n) for n in numeros)


def formatar_cpf(cpf: str) -> str:
    """"52998224725" → "529.982.247-25"."""
    return f"{cpf[:3]}.{cpf[3:6]}.{cpf[6:9]}-{cpf[9:]}"


def _cpf_meio(cpf: str, mascara: str = "*") -> str:
    """"***.982.247-**" (o eProtocolo usa X; bancos, * ou •)."""
    return f"{mascara * 3}.{cpf[3:6]}.{cpf[6:9]}-{mascara * 2}"


def _cpf_pontas(cpf: str) -> str:
    """"529.***.***-25" (como o próprio sistema mascara)."""
    return f"{cpf[:3]}.***.***-{cpf[9:]}"


# ─────────────────────────────────────────────────────────────────
# Páginas de texto
# ─────────────────────────────────────────────────────────────────

def _canvas(tamanho):
    buffer = io.BytesIO()
    return buffer, canvas.Canvas(buffer, pagesize=tamanho)


def _desenhar_linhas(c, linhas, *, x=56, topo=None, fonte=10, entrelinha=None, altura=None):
    altura = altura or c._pagesize[1]
    y = (topo if topo is not None else altura - 60)
    entrelinha = entrelinha or fonte * 1.5
    for linha in linhas:
        if isinstance(linha, tuple):  # (texto, corpo, negrito)
            texto, corpo, negrito = (list(linha) + [fonte, False])[:3]
        else:
            texto, corpo, negrito = linha, fonte, False
        c.setFont("Helvetica-Bold" if negrito else "Helvetica", corpo)
        if texto:
            c.drawString(x, y, texto)
        y -= entrelinha if corpo == fonte else corpo * 1.5


def pagina(linhas, *, tamanho=A4, paisagem=False, fonte=10, x=56, topo=None, entrelinha=None) -> bytes:
    """PDF de 1 página com as `linhas` de texto, de cima para baixo.

    Cada linha é um texto ou uma tupla `(texto, corpo, negrito)`. Com
    `paisagem`, a página é A4 deitada (842 × 595).
    """
    tamanho = landscape(tamanho) if paisagem else tamanho
    buffer, c = _canvas(tamanho)
    _desenhar_linhas(c, linhas, x=x, topo=topo, fonte=fonte, entrelinha=entrelinha)
    c.showPage()
    c.save()
    return buffer.getvalue()


def paginas(lista_de_linhas, **opcoes) -> bytes:
    """PDF com uma página por item de `lista_de_linhas` (mesmas opções de `pagina`)."""
    return juntar(*(pagina(linhas, **opcoes) for linhas in lista_de_linhas))


def juntar(*pdfs: bytes) -> bytes:
    """Um PDF com as páginas de todos, na ordem."""
    from pypdf import PdfReader
    from pypdf import PdfWriter

    escritor = PdfWriter()
    for dados in pdfs:
        for pag in PdfReader(io.BytesIO(dados)).pages:
            escritor.add_page(pag)
    saida = io.BytesIO()
    escritor.write(saida)
    return saida.getvalue()


# ─────────────────────────────────────────────────────────────────
# Transformações de página
# ─────────────────────────────────────────────────────────────────

def com_rotate(pdf: bytes, graus: int) -> bytes:
    """O mesmo PDF com /Rotate = `graus` em todas as páginas (o conteúdo não muda)."""
    from pypdf import PdfReader
    from pypdf import PdfWriter
    from pypdf.generic import NameObject
    from pypdf.generic import NumberObject

    escritor = PdfWriter()
    for pag in PdfReader(io.BytesIO(pdf)).pages:
        escritor.add_page(pag)
        escritor.pages[-1][NameObject("/Rotate")] = NumberObject(graus % 360)
    saida = io.BytesIO()
    escritor.write(saida)
    return saida.getvalue()


def girar_conteudo(pdf: bytes, graus: int) -> bytes:
    """Gira o conteúdo `graus` no sentido horário DENTRO da página, com /Rotate 0.

    É como sai de scanner ou impressora virtual que "achata" a rotação: um
    diário paisagem girado 90 vira página retrato com as linhas descendo
    (conteúdo a 270°); girado 270, linhas subindo (90°); 180, de cabeça
    para baixo.
    """
    from pypdf import PdfReader
    from pypdf import PdfWriter

    escritor = PdfWriter()
    for pag in PdfReader(io.BytesIO(pdf)).pages:
        pag.rotate(graus)
        pag.transfer_rotation_to_content()
        escritor.add_page(pag)
    saida = io.BytesIO()
    escritor.write(saida)
    return saida.getvalue()


def em_form(pdf: bytes, matriz, tamanho) -> bytes:
    """A página de `pdf` dentro de um Form XObject com a `/Matrix` dada, numa página nova de `tamanho`.

    Sem nenhum `cm` por fora: só a /Matrix posiciona (e gira) o conteúdo —
    o que o pypdf ignora. Ex.: diário paisagem (842 × 595) deitado numa
    página retrato com `matriz=(0, 1, -1, 0, 595, 0)` (linhas subindo, 90°).
    """
    from pypdf import PdfReader
    from pypdf import PdfWriter
    from pypdf.generic import ArrayObject
    from pypdf.generic import DecodedStreamObject
    from pypdf.generic import DictionaryObject
    from pypdf.generic import FloatObject
    from pypdf.generic import NameObject

    origem = PdfReader(io.BytesIO(pdf)).pages[0]
    escritor = PdfWriter()
    form = DecodedStreamObject()
    form.set_data(origem.get_contents().get_data())
    form.update(
        {
            NameObject("/Type"): NameObject("/XObject"),
            NameObject("/Subtype"): NameObject("/Form"),
            NameObject("/BBox"): ArrayObject([FloatObject(v) for v in origem.mediabox]),
            NameObject("/Matrix"): ArrayObject([FloatObject(v) for v in matriz]),
            NameObject("/Resources"): origem["/Resources"].clone(escritor),
        }
    )
    nova = escritor.add_blank_page(*tamanho)
    nova[NameObject("/Resources")] = DictionaryObject(
        {NameObject("/XObject"): DictionaryObject({NameObject("/Fm0"): escritor._add_object(form)})}
    )
    conteudo = DecodedStreamObject()
    conteudo.set_data(b"q /Fm0 Do Q\n")
    nova[NameObject("/Contents")] = escritor._add_object(conteudo)
    saida = io.BytesIO()
    escritor.write(saida)
    return saida.getvalue()


def _form_embrulhado(escritor, origem, escala):
    """Form XObject com o conteúdo de `origem` em coordenadas de Y invertido (como o OpenPDF do eProtocolo)."""
    from pypdf.generic import ArrayObject
    from pypdf.generic import DecodedStreamObject
    from pypdf.generic import FloatObject
    from pypdf.generic import NameObject

    largura, altura = float(origem.mediabox.width), float(origem.mediabox.height)
    x0, y0 = float(origem.mediabox.left), float(origem.mediabox.bottom)
    form = DecodedStreamObject()
    # Leva o conteúdo original para o espaço do form: x/escala, (altura − y)/escala.
    prefixo = f"{1 / escala:.6f} 0 0 {-1 / escala:.6f} {-x0 / escala:.6f} {(altura + y0) / escala:.6f} cm\n"
    form.set_data(prefixo.encode() + origem.get_contents().get_data())
    form.update(
        {
            NameObject("/Type"): NameObject("/XObject"),
            NameObject("/Subtype"): NameObject("/Form"),
            NameObject("/BBox"): ArrayObject(
                [FloatObject(0), FloatObject(0), FloatObject(largura / escala), FloatObject(altura / escala)]
            ),
            NameObject("/Resources"): origem["/Resources"].clone(escritor) if "/Resources" in origem else {},
        }
    )
    return escritor._add_object(form), largura, altura


def _moldura_conteudo(largura, altura, base, *, fls, mov, rodape):
    """(stream, fontes) do carimbo Fls./Mov. e do rodapé, desenhados com reportlab."""
    from pypdf import PdfReader

    buffer, c = _canvas((largura, altura))
    c.setFont("Helvetica", 7)
    c.drawString(largura - 43, altura - 43, fls)
    c.drawString(largura - 40, altura - 54, mov)
    y = base + 29.5
    for linha in textwrap.wrap(rodape, 190):
        c.drawString(10, y, linha)
        y -= 10.5
    c.rect(5, base + 2, largura - 10, 38)
    c.showPage()
    c.save()
    pag = PdfReader(io.BytesIO(buffer.getvalue())).pages[0]
    return pag.get_contents().get_data(), pag["/Resources"]["/Font"]


def rodape_eprotocolo(*, protocolo, codigo, inserido_por="Maria Servidora da Silva", inserido_em="21/09/2026 10:00",
                      assinantes=(), assinado_em="21/09/2026 13:18") -> str:
    """O texto do rodapé do eProtocolo (com as assinaturas avançadas, se houver)."""
    partes = []
    for nome, cpf in assinantes:
        partes.append(
            f"Assinatura Avançada realizada por: {nome} ({_cpf_meio(cpf, 'X')}) em {assinado_em} Local: DPC/ASCOM."
        )
    partes.append(f"Inserido ao protocolo {protocolo} por: {inserido_por} em: {inserido_em}.")
    if assinantes:
        partes.append("Documento assinado nos termos do Art. 38 do Decreto Estadual nº 7304/2021.")
    partes.append(
        "A autenticidade deste documento pode ser validada no endereço: "
        f"https://www.eprotocolo.pr.gov.br/spiweb/validarDocumento com o código: {codigo}"
    )
    return " ".join(partes)


def _codigo(*partes) -> str:
    return hashlib.md5("|".join(str(p) for p in partes).encode()).hexdigest()


def emoldurar(pdf: bytes, *, fls, mov, protocolo="26.613.666-8", codigo=None, inserido_por="Maria Servidora da Silva",
              inserido_em="21/09/2026 10:00", assinantes=(), embrulhar=False, escala=0.48) -> bytes:
    """Põe a moldura do eProtocolo na (única) página de `pdf`.

    Acrescenta 40 pt embaixo (mediabox começa em base − 40), desenha o
    carimbo Fls./Mov. no canto superior direito e o rodapé na faixa nova,
    sempre a 0°. Com `embrulhar`, o conteúdo original vai para um Form
    XObject com o eixo Y invertido e a página desinverte com
    `1 0 0 -1 0 H cm` — o `extract_text(orientations=…)` do pypdf passa a
    ver o texto em pé como 180°. Chamar duas vezes simula documento
    aninhado (base −80).
    """
    from pypdf import PdfReader
    from pypdf import PdfWriter
    from pypdf.generic import ArrayObject
    from pypdf.generic import DecodedStreamObject
    from pypdf.generic import DictionaryObject
    from pypdf.generic import FloatObject
    from pypdf.generic import NameObject

    origem = PdfReader(io.BytesIO(pdf)).pages[0]
    if codigo is None:
        codigo = _codigo(protocolo, fls, mov)
    rodape = rodape_eprotocolo(protocolo=protocolo, codigo=codigo, inserido_por=inserido_por,
                               inserido_em=inserido_em, assinantes=assinantes)
    largura = float(origem.mediabox.width)
    base_antiga = float(origem.mediabox.bottom)
    topo = float(origem.mediabox.top)
    base = base_antiga - 40
    moldura, fontes = _moldura_conteudo(largura, topo, base, fls=fls, mov=mov, rodape=rodape)

    escritor = PdfWriter()
    if embrulhar:
        form, _, _ = _form_embrulhado(escritor, origem, escala)
        nova = escritor.add_blank_page(largura, topo - base)
        nova[NameObject("/Resources")] = DictionaryObject(
            {
                NameObject("/XObject"): DictionaryObject({NameObject("/Xf0"): form}),
                NameObject("/Font"): fontes.clone(escritor),
            }
        )
        corpo = (
            f"q 1 0 0 -1 0 {topo:.4f} cm q {escala} 0 0 {escala} 0 0 cm /Xf0 Do Q Q\n".encode()
        )
        conteudo = DecodedStreamObject()
        conteudo.set_data(corpo + moldura)
        nova[NameObject("/Contents")] = escritor._add_object(conteudo)
    else:
        escritor.add_page(origem)
        nova = escritor.pages[-1]
        recursos = nova["/Resources"].get_object() if "/Resources" in nova else DictionaryObject()
        fontes_pagina = recursos.get("/Font", DictionaryObject()).get_object()
        novas_fontes = DictionaryObject(dict(fontes_pagina))
        apelidos = {}
        for nome, fonte in fontes.items():
            apelido = NameObject(f"/FM{nome[1:]}")
            apelidos[nome] = apelido
            novas_fontes[apelido] = fonte.clone(escritor) if hasattr(fonte, "clone") else fonte
        recursos[NameObject("/Font")] = novas_fontes
        nova[NameObject("/Resources")] = recursos
        for nome, apelido in apelidos.items():
            moldura = moldura.replace(f"{nome} ".encode(), f"{apelido} ".encode())
        conteudo_original = origem.get_contents()
        original = conteudo_original.get_data() if conteudo_original is not None else b""
        conteudo = DecodedStreamObject()
        conteudo.set_data(b"q\n" + original + b"\nQ\n" + moldura)
        nova[NameObject("/Contents")] = escritor._add_object(conteudo)
    nova.mediabox = ArrayObject([FloatObject(0), FloatObject(base), FloatObject(largura), FloatObject(topo)])
    nova.cropbox = nova.mediabox
    saida = io.BytesIO()
    escritor.write(saida)
    return saida.getvalue()


def folha_assinatura(*, fls, mov, arquivo, protocolo="26.613.666-8", assinantes=(), inserido_por="Maria Servidora da Silva",
                     inserido_em="21/09/2026 10:00", assinado_em="21/09/2026 13:18") -> bytes:
    """A folha "Na" que o eProtocolo acrescenta depois de um documento assinado.

    O texto começa pelo carimbo ("2a", "2") e por "Documento: arquivo.pdf.";
    o código de validação dessa folha só existe no QR code, não no texto.
    """
    largura, altura = 627, 842
    buffer, c = _canvas((largura, altura))
    c.setFont("Helvetica", 7)
    c.drawString(largura - 45, altura - 43, fls)
    c.drawString(largura - 40, altura - 54, mov)
    linhas = [f"Documento: {arquivo}."]
    for nome, cpf in assinantes:
        linhas.append(
            f"Assinatura Avançada realizada por: {nome} ({_cpf_meio(cpf, 'X')}) em {assinado_em} Local: DPC/ASCOM."
        )
    linhas += [
        f"Inserido ao protocolo {protocolo} por: {inserido_por} em: {inserido_em}.",
        "Documento assinado nos termos do Art. 38 do Decreto Estadual nº 7304/2021.",
        "A autenticidade deste documento pode ser validada no endereço:",
        "https://www.eprotocolo.pr.gov.br/spiweb/validarDocumento com o código:",
    ]
    _desenhar_linhas(c, linhas, x=20, topo=710, fonte=8, entrelinha=12)
    c.showPage()
    c.save()
    from pypdf import PdfReader
    from pypdf import PdfWriter
    from pypdf.generic import ArrayObject
    from pypdf.generic import FloatObject

    escritor = PdfWriter()
    escritor.add_page(PdfReader(io.BytesIO(buffer.getvalue())).pages[0])
    escritor.pages[0].mediabox = ArrayObject([FloatObject(0), FloatObject(-40), FloatObject(largura), FloatObject(altura)])
    saida = io.BytesIO()
    escritor.write(saida)
    return saida.getvalue()


def capa_eprotocolo(*, protocolo="26.613.666-8", numero_ano="12/2026", assunto="DIARIAS", cidade="CURITIBA / PR",
                    orgao="DPC", em="21/09/2026 10:00", palavras_chave="PRESTACAO DE CONTAS",
                    detalhamento="PRESTACAO DE CONTAS DE DIARIAS", interessados=("POLICIA CIVIL DO PARANA",)) -> bytes:
    """A capa ("ContraCapa") do volume, com os campos nas coordenadas da real.

    Rótulos em x=67 e valores em x=156 na mesma altura; "Cidade:" em x=384.
    A ordem de desenho imita a real, em que o texto extraído sai com o valor
    antes do rótulo ("12/2026Nº/Ano") — só a leitura por coordenadas acerta.
    """
    largura, altura = 637, 842
    buffer, c = _canvas((largura, altura))

    def escrever(x, y, texto, corpo=10):
        c.setFont("Helvetica", corpo)
        c.drawString(x, y, texto)

    escrever(95.5, 651.8, "ESTADO DO PARANÁ", 18)
    escrever(523, 760.9, "Folha 1")
    escrever(412, 628.6, "Protocolo:")
    escrever(413, 607.0, protocolo)
    escrever(67, 627.9, "Órgão Cadastro:")
    escrever(156, 628.9, orgao)
    escrever(67, 612.9, "Em:")
    escrever(156, 613.9, em)
    escrever(143.4, 473.1, "Para informações acesse: https://www.eprotocolo.pr.gov.br/spiweb/consultarProtocolo", 8)
    escrever(67, 487.4, "Código TTD:")
    escrever(131, 487.4, "-")
    escrever(424, 557.9, cidade)
    escrever(384, 557.9, "Cidade:")
    escrever(67, 557.9, "Assunto:")
    escrever(67, 521.6, "Detalhamento:")
    escrever(156, 533.9, numero_ano)
    escrever(67, 533.9, "Nº/Ano")
    escrever(156, 545.9, palavras_chave)
    escrever(67, 545.9, "Palavras-chave:")
    escrever(156, 557.9, assunto)
    escrever(156, 522.6, detalhamento)
    y = 583.9
    for posicao, interessado in enumerate(list(interessados) + [""], start=1):
        escrever(67, y, f"Interessado {posicao}:")
        if interessado:
            escrever(156, y + 0.7, interessado)
        y -= 13.5
    c.setFont("Helvetica", 7)
    c.drawString(593.8, 799.0, "1")
    c.drawString(596.8, 788.0, "1")
    c.showPage()
    c.save()
    from pypdf import PdfReader
    from pypdf import PdfWriter
    from pypdf.generic import ArrayObject
    from pypdf.generic import FloatObject

    escritor = PdfWriter()
    escritor.add_page(PdfReader(io.BytesIO(buffer.getvalue())).pages[0])
    escritor.pages[0].mediabox = ArrayObject([FloatObject(0), FloatObject(-40), FloatObject(largura), FloatObject(altura)])
    saida = io.BytesIO()
    escritor.write(saida)
    return saida.getvalue()


@dataclass
class Doc:
    """Um documento a pôr no processo.

    - `pdf`: o documento (uma ou mais páginas);
    - `arquivo`: nome do arquivo original (vira o marcador "N - arquivo" e
      o "Documento: arquivo." da folha de assinatura);
    - `assinantes`: [(nome, cpf)] — assinatura avançada no rodapé e folha "Na";
    - `embrulhar`: cada página vai num form com Y invertido (ver `emoldurar`);
    - `aninhado`: o documento já tinha passado pelo protocolo `protocolo_antigo`
      (moldura antiga dentro, base −80);
    - `inserido_por`: quem juntou (padrão: o do processo).
    """

    pdf: bytes
    arquivo: str = "documento.pdf"
    assinantes: list = field(default_factory=list)
    embrulhar: bool = False
    aninhado: bool = False
    protocolo_antigo: str = "24.740.746-4"
    inserido_por: str | None = None


def processo_eprotocolo(docs: list[Doc], *, protocolo="26.613.666-8", volume=1, capa=True, marcadores=True,
                        criador=True, codigos=True, inserido_por="Maria Servidora da Silva",
                        inserido_em="21/09/2026 10:00", numero_ano="12/2026", fls_inicial=None, mov_inicial=None,
                        **campos_capa) -> bytes:
    """Um volume do eProtocolo com a capa (Mov 1) e os `docs`, na ordem.

    Cada documento ganha o próximo Mov e cada página a próxima folha; o
    documento assinado ganha a folha "Na" logo depois. O código de
    validação é o mesmo em todas as páginas do documento. Com
    `marcadores`, há um marcador "N - arquivo" por documento; com
    `criador`, os metadados são os do eProtocolo (/Author com um CPF
    fictício, como o real traz o de quem baixou). Sem `codigos`, o rodapé
    sai sem código de validação (só o Mov separa os documentos). `volume`
    > 1 começa sem capa, na folha `fls_inicial` e no Mov `mov_inicial`.
    """
    from pypdf import PdfReader
    from pypdf import PdfWriter

    escritor = PdfWriter()
    inicios: list[tuple[int, str]] = []
    folha = fls_inicial or 1
    mov = mov_inicial or 1

    def acrescentar(dados):
        for pag in PdfReader(io.BytesIO(dados)).pages:
            escritor.add_page(pag)

    if capa and volume == 1:
        inicios.append((len(escritor.pages), "1 - ContraCapa.pdf"))
        acrescentar(capa_eprotocolo(protocolo=protocolo, numero_ano=numero_ano, em=inserido_em, **campos_capa))
        folha, mov = 2, 2
    for doc in docs:
        codigo = _codigo(protocolo, mov, doc.arquivo) if codigos else ""
        quem = doc.inserido_por or inserido_por
        inicios.append((len(escritor.pages), f"{mov} - {doc.arquivo}"))
        leitor = PdfReader(io.BytesIO(doc.pdf))
        for pag in leitor.pages:
            unica = PdfWriter()
            unica.add_page(pag)
            buffer = io.BytesIO()
            unica.write(buffer)
            dados = buffer.getvalue()
            if doc.aninhado:
                dados = emoldurar(dados, fls=f"{folha + 200}", mov="61", protocolo=doc.protocolo_antigo,
                                  inserido_por="Servidor Antigo", inserido_em="20/10/2025 16:13")
            dados = emoldurar(dados, fls=str(folha), mov=str(mov), protocolo=protocolo, codigo=codigo,
                              inserido_por=quem, inserido_em=inserido_em, assinantes=doc.assinantes,
                              embrulhar=doc.embrulhar)
            acrescentar(dados)
            ultima = folha
            folha += 1
        if doc.assinantes:
            acrescentar(folha_assinatura(fls=f"{ultima}a", mov=str(mov), arquivo=doc.arquivo, protocolo=protocolo,
                                         assinantes=doc.assinantes, inserido_por=quem, inserido_em=inserido_em))
        mov += 1
    if marcadores:
        for pagina_inicial, titulo in inicios:
            escritor.add_outline_item(titulo, pagina_inicial)
    if criador:
        escritor.add_metadata(
            {
                "/Creator": "Sistema eProtocolo",
                "/Producer": "OpenPDF 1.3.40",
                "/Subject": "Volume do protocolo",
                "/Author": "00000000191",
                "/Title": f"Processo_{protocolo}_{volume}.pdf",
            }
        )
    saida = io.BytesIO()
    escritor.write(saida)
    return saida.getvalue()


# ─────────────────────────────────────────────────────────────────
# Imagem
# ─────────────────────────────────────────────────────────────────

def imagem_da_pagina(pdf: bytes, indice: int = 0, *, largura: int | None = None, dpi: int = 100):
    """A página desenhada pelo pdfium como aparece na tela (com /Rotate), em tons de cinza (PIL)."""
    import pypdfium2 as pdfium

    documento = pdfium.PdfDocument(pdf)
    try:
        imagem = documento[indice].render(scale=dpi / 72, grayscale=True).to_pil().convert("L")
    finally:
        documento.close()
    if largura:
        imagem = imagem.resize((largura, max(1, round(imagem.height * largura / imagem.width))))
    return imagem


def semelhanca(a, b, tamanho=(80, 56)) -> float:
    """Correlação de Pearson entre duas imagens (1 = iguais; −1 = invertidas). Retrato × paisagem = −1."""
    if (a.width > a.height) != (b.width > b.height):
        return -1.0
    tamanho = tamanho if a.width > a.height else tamanho[::-1]
    va = list(a.convert("L").resize(tamanho).getdata())
    vb = list(b.convert("L").resize(tamanho).getdata())
    ma, mb = sum(va) / len(va), sum(vb) / len(vb)
    cov = sum((x - ma) * (y - mb) for x, y in zip(va, vb))
    da = sum((x - ma) ** 2 for x in va) ** 0.5
    db = sum((y - mb) ** 2 for y in vb) ** 0.5
    return cov / (da * db) if da and db else 0.0


def imagem_png(origem, *, girar: int = 0, dpi: int = 110) -> bytes:
    """PNG da primeira página de `origem` (PDF em bytes ou lista de linhas), girada `girar` graus no sentido horário."""
    pdf = origem if isinstance(origem, (bytes, bytearray)) else pagina(list(origem), fonte=14)
    imagem = imagem_da_pagina(bytes(pdf), dpi=dpi)
    if girar:
        imagem = imagem.rotate(-girar, expand=True, fillcolor=255)
    saida = io.BytesIO()
    imagem.save(saida, format="PNG", dpi=(dpi, dpi))
    return saida.getvalue()


def pagina_imagem(origem, *, girar: int = 0, dpi: int = 110) -> bytes:
    """Página só de imagem (sem nenhum texto), como uma digitalização.

    `origem` é um PDF (a primeira página vira a imagem) ou uma lista de
    linhas. `girar` gira a imagem no sentido horário antes de pôr na
    página, que fica do tamanho da imagem (um diário paisagem girado 90
    vira página retrato).
    """
    from PIL import Image

    png = imagem_png(origem, girar=girar, dpi=dpi)
    imagem = Image.open(io.BytesIO(png))
    largura, altura = imagem.width * 72 / dpi, imagem.height * 72 / dpi
    buffer, c = _canvas((largura, altura))
    c.drawImage(ImageReader(imagem.convert("RGB")), 0, 0, largura, altura)
    c.showPage()
    c.save()
    return buffer.getvalue()


# ─────────────────────────────────────────────────────────────────
# Documentos que o sistema imprime
# ─────────────────────────────────────────────────────────────────

_CABECALHO = ["SECRETARIA DE ESTADO DA SEGURANÇA PÚBLICA", "POLÍCIA CIVIL DO PARANÁ", "ASSESSORIA DE COMUNICAÇÃO SOCIAL", ""]


def oficio_viagens(*, numero=12, ano=2026, protocolo="26.613.666-8", servidores=(("FULANO DE TAL", "52998224725"),),
                   convalidacao=True, data="21/09/2026") -> bytes:
    """Ofício de Viagens como `templates/documentos/pdf/oficio.html` (tabelas, equipe com CPF, roteiro)."""
    rotulo = "(Convalidação)" if convalidacao else "(Autorização)"
    termo = "convalidação" if convalidacao else "autorização"
    linhas = list(_CABECALHO) + [
        f"Ofício Nº {numero:02d}/{ano} {rotulo}      Data: {data}",
        "Origem: ASCOM      Destino: GAB/DG",
        f"Protocolo Nº: {protocolo}      Assunto: Solicitação de {termo} e concessão de diárias.",
        "",
        f"Senhor Delegado, através deste, solicito {termo} e medidas para a concessão de diárias e recursos",
        "para combustível, conforme cronograma abaixo:",
        "Nome   CPF   Cargo   Nº solicitação (Central de Viagens)",
    ]
    for nome, cpf in servidores:
        linhas.append(f"{nome}   CPF: {formatar_cpf(cpf)}   AGENTE DE POLÍCIA JUDICIÁRIA")
    linhas += [
        "Destino da viagem: PONTA GROSSA/PR   Nº de diárias por servidor: 1 diárias   Valor total do ofício: R$ 580,00",
        "Roteiro de ida",
        "Saída: Curitiba/PR - 20/09/2026 07:00   Chegada: Ponta Grossa/PR - 20/09/2026 09:00",
        "Meio de transporte: Viatura oficial   Placa oficial: ABC1D23",
        "Motivo da viagem: cobertura do evento PCPR na Comunidade.",
        "Declaro que os servidores estão cientes da necessidade de estar na posse de cartão corporativo",
        "Respeitosamente,",
    ]
    return pagina(linhas)


def oficio_coffee_break(*, numero=123, ano=2026, pcpr="2026.050731.000", notas=("8952", "8954"),
                        contrato="0762/2024", data_extenso="21 de Setembro de 2026") -> bytes:
    """Ofício do Coffee Break como o do processo real (texto de `coffee_break/editor.py`)."""
    plural = len(notas) > 1
    notas_texto = " e ".join(notas)
    return pagina(list(_CABECALHO) + [
        f"OFÍCIO {numero}/{ano}",
        f"PCPR Protocolo n.º: {pcpr} Curitiba, {data_extenso}",
        "Excelentíssimo Senhor Delegado:",
        "Venho, por meio deste, informar e certificar que os serviços de Coffee Break foram",
        "devidamente entregues, conforme solicitado, para o seguinte evento:",
        "• Encerramento do Curso - Coffee Break para 80 (oitenta) pessoas.",
        f"Encaminho, em anexo, {'as Notas Fiscais' if plural else 'a Nota Fiscal'} n° {notas_texto}, devidamente atestada,",
        f"juntamente com os demais documentos necessários, do CONTRATO {contrato} – GMS 7339/2024.",
        "Atenciosamente,",
    ])


def despacho(*, protocolo="26.613.666-8", assunto="PRESTAÇÃO DE CONTAS DE DIÁRIAS - OFÍCIO 12/2026",
             interessado="POLÍCIA CIVIL DO PARANÁ", destino="GAF", data="21/09/2026 10:03") -> bytes:
    """Despacho criado dentro do eProtocolo: cabeçalho Protocolo/Assunto e "DESPACHO" no fim do texto.

    Como no real, o valor do interessado e da data sai antes do rótulo, e o
    título é desenhado por último (a extração o põe no fim).
    """
    buffer, c = _canvas(A4)
    _desenhar_linhas(c, ["DEPARTAMENTO DE POLICIA CIVIL", "ASSESSORIA DE COMUNICAÇÃO SOCIAL",
                         f"Protocolo: {protocolo}", f"Assunto: {assunto}"], topo=740)
    c.drawString(56, 680, interessado)
    c.drawString(400, 680, "Interessado:")
    c.drawString(56, 665, data)
    c.drawString(400, 665, "Data:")
    _desenhar_linhas(c, [f"Ao {destino},", "Encaminhamos o presente protocolado com as devidas informações para",
                         "a análise da prestação de contas."], topo=620)
    c.setFont("Helvetica-Bold", 16)
    c.drawString(250, 780, "DESPACHO")
    c.showPage()
    c.save()
    return buffer.getvalue()


def relatorio_tecnico(*, oficio="12/2026", nome="FULANO DE TAL", cpf="52998224725", diaria="R$ 580,00",
                      data_extenso="21 de setembro de 2026") -> bytes:
    """RT como `relatorio_tecnico.html`: "Ref. ao Ofício", título, tabela Nome/CPF, valores, relato."""
    return pagina([
        "SECRETARIA DE ESTADO DA SEGURANÇA PÚBLICA", "",
        f"Ref. ao Ofício {oficio}                                  Curitiba, {data_extenso}",
        ("Relatório técnico de viagem", 14, True),
        f"Nome   {nome}",
        f"CPF    {formatar_cpf(cpf)}",
        ("Valores utilizados na viagem:", 12, True),
        f"Diária: {diaria}", "Translado: -", "Combustível: Cartão Prime", "Passagem: -",
        "DESCRIÇÃO DO EVENTO", "PCPR na Comunidade em Ponta Grossa.",
        "OBJETIVO DA PARTICIPAÇÃO", "Cobertura fotográfica.",
        "Declaramos que o trabalho previsto na programação de viagem foi realizado",
        f"CPF {formatar_cpf(cpf)}",
    ])


def diario_bordo(*, oficio="12/2026", protocolo="26.613.666-8", placa="ABC1D23", motorista="BELTRANO MOTORISTA",
                 cpf_motorista="11144477735", trechos=6) -> bytes:
    """Diário de bordo como `diario_bordo.html`: A4 deitado (842 × 595), ficha do veículo e trechos."""
    linhas = [
        "SECRETARIA DE ESTADO DA SEGURANÇA PÚBLICA", "POLÍCIA CIVIL DO PARANÁ", "",
        f"Referente ao Ofício: {oficio}                         E-protocolo: {protocolo}",
        "Ficha individual do veículo (tipo): CARACTERIZADA      Combustível: GASOLINA",
        f"Placa oficial: {placa}                                  Placa reservada: -",
        "Saída                 Chegada               Origem        Destino       Necessidade de abastecimento",
        "Data   Hora   KM (inicial)   Data   Hora   KM (final)",
    ]
    for i in range(trechos):
        linhas.append(
            f"2{i % 9}/09/2026  0{7 + i % 3}:00  {10000 + i * 120}   2{i % 9}/09/2026  1{i % 9}:00  {10120 + i * 120}   "
            f"CURITIBA   PONTA GROSSA   NÃO"
        )
    linhas.append(f"Nome: {motorista}      CPF: {formatar_cpf(cpf_motorista)}      Assinatura:")
    return pagina(linhas, paisagem=True)


def termo_autorizacao(*, nome="FULANO DE TAL", cpf="52998224725", rg="12.345.678-9", lotacao="ASCOM",
                      destino="Ponta Grossa", data_evento="no dia 20 de setembro de 2026") -> bytes:
    """Termo de autorização como `termo_autorizacao_automatico.docx` (com RG e CPF)."""
    return pagina(list(_CABECALHO) + [
        ("TERMO DE AUTORIZAÇÃO PARA PARTICIPAÇÃO EM EVENTOS DA ASCOM", 12, True),
        f"Eu {nome}, RG: {rg}, CPF: {formatar_cpf(cpf)}, telefone (41) 99999-0000, lotado(a) na(o) {lotacao},",
        f"manifesto o interesse em participar do PCPR na Comunidade, {data_evento}, no município de {destino}",
        "para execução de atividades inerentes à Assessoria de Comunicação Social - ASCOM/PCPR.",
        "Declaro que estou ciente da necessidade de estar na posse de cartão corporativo vigente e apto para uso.",
        "Viatura: SPIN   Placa / Combustível: ABC1D23 / GASOLINA",
        "Assinatura servidor:", "Autorização da Chefia:",
    ])


def justificativa(*, texto="O ofício foi emitido após a viagem por falta de tempo hábil.",
                  data_extenso="21 de setembro de 2026") -> bytes:
    """Justificativa como `justificativa.html`: local e data, título "Justificativa", texto e assinante."""
    return pagina(list(_CABECALHO) + [f"Curitiba, {data_extenso}", ("Justificativa", 14, True), texto, "", "CHEFE DA ASCOM"])


def ordem_servico(*, numero=5, ano=2026) -> bytes:
    """Ordem de serviço como `ordem_servico.html` ("Ordem de Serviço N/AAAA - ASCOM", "Determino")."""
    return pagina(list(_CABECALHO) + [
        (f"Ordem de Serviço {numero:02d}/{ano} - ASCOM", 14, True), "Ref.: Diligências",
        "Eu, CHEFE DA ASCOM, Delegado de Polícia da Polícia Civil do Paraná, no uso das atribuições que me foram conferidas",
        "Determino", "O deslocamento dos servidores para o município de Ponta Grossa.",
    ])


def plano_trabalho(*, numero=3, ano=2026) -> bytes:
    """Plano de trabalho como `plano_trabalho.html` (capa + seções numeradas)."""
    return pagina(list(_CABECALHO) + [
        (f"Plano de Trabalho Nº {numero:02d}/{ano}", 14, True), "1. Breve contextualização",
        "O programa PCPR na Comunidade leva serviços à população.", "2. Atuação", "3. Metas estabelecidas",
    ])


def nota_fiscal(*, numero=8952, valor="1.600,00", emissao="18/09/2026", cnpj="35.014.719/0001-66", serie="001") -> bytes:
    """DANFE (NF-e) com número, série, emissão, valor total e chave de acesso de 44 dígitos."""
    chave = f"41260935014719000166550010000{numero:05d}0122512905"[:44].ljust(44, "0")
    chave_fmt = " ".join(chave[i:i + 4] for i in range(0, 44, 4))
    digitos = f"{numero:09d}"
    numero_fmt = f"{digitos[:3]}.{digitos[3:6]}.{digitos[6:]}"
    return pagina([
        "RECEBEMOS DE PADARIA EXEMPLO LTDA OS PRODUTOS / SERVIÇOS CONSTANTES DA NOTA FISCAL INDICADO AO LADO",
        "NF-e", f"Nº {numero_fmt}", f"SÉRIE {serie}",
        f"EMISSÃO: {emissao} - DEST. / REM.: SECRETARIA DE ESTADO DA SEGURANCA PUBLICA - VALOR TOTAL: R$ {valor}",
        "DANFE", "DOCUMENTO AUXILIAR DA", "NOTA FISCAL ELETRÔNICA", "CHAVE DE ACESSO", chave_fmt,
        "PADARIA EXEMPLO LTDA", cnpj, "DESTINATÁRIO / REMETENTE", "SECRETARIA DE ESTADO DA SEGURANCA PUBLICA",
        "76.416.932/0001-81", "VALOR TOTAL DA NOTA", valor,
    ], fonte=8)


def certifico(*, nota="8952", cnpj="35.014.719/0001-66", contrato="0762/2024") -> bytes:
    """Certifico digital do Coffee Break (`coffee_break/editor.py`, BLOCOS_CERTIFICO)."""
    return pagina(list(_CABECALHO) + [
        ("CERTIFICO DIGITAL", 14, True),
        f"Nota Fiscal nº {nota}, emitida pela empresa PADARIA EXEMPLO LTDA, inscrita no CNPJ nº {cnpj} (CONTRATO {contrato}).",
        "ATESTO que os serviços e/ou bens acima identificados foram devidamente executados/entregues.",
        "(assinado e datado digitalmente)", f"Fiscal do Contrato n° {contrato}",
    ])


_CERTIDOES = {
    "FEDERAL": ["MINISTÉRIO DA FAZENDA", "Secretaria da Receita Federal do Brasil",
                "CERTIDÃO NEGATIVA DE DÉBITOS RELATIVOS AOS TRIBUTOS FEDERAIS E À DÍVIDA ATIVA DA UNIÃO"],
    "ESTADUAL": ["Estado do Paraná", "Secretaria de Estado da Fazenda", "Receita Estadual do Paraná",
                 "Certidão Negativa de Débitos Tributários e de Dívida Ativa Estadual"],
    "MUNICIPAL": ["PREFEITURA MUNICIPAL DE CURITIBA", "CERTIDÃO NEGATIVA DE DÉBITOS MUNICIPAIS"],
    "TRABALHISTA": ["CERTIDÃO NEGATIVA DE DÉBITOS TRABALHISTAS"],
    "FGTS": ["Certificado de", "Regularidade do FGTS - CRF"],
}


def certidao(tipo="FEDERAL", *, validade="15/02/2027", cnpj="35.014.719/0001-66") -> bytes:
    """Certidão de regularidade do `tipo` (FEDERAL, ESTADUAL, MUNICIPAL, TRABALHISTA, FGTS)."""
    return pagina(list(_CERTIDOES[tipo]) + [
        "Nome: PADARIA EXEMPLO LTDA", f"CNPJ: {cnpj}", "Certifica-se que não constam pendências.",
        f"Válida até {validade}.",
    ])


def contrato(*, numero="0762/2024", protocolo="22.906.321-9", paginas_=2) -> bytes:
    """Contrato com cabeçalho repetido em toda página ("CONTRATO – Nº …"), Contratante/Contratado e cláusulas."""
    cabecalho = ["SECRETARIA DE ESTADO DA SEGURANÇA PÚBLICA", f"SETOR DE CONTRATOS E CONVÊNIOS – CONTRATO – Nº {numero} – GMS Nº 7339/2024"]
    primeira = cabecalho + [
        "CONTRATO PARA A PRESTAÇÃO DE SERVIÇOS CONTÍNUOS DE COFFEE BREAK", f"PROTOCOLO nº: {protocolo}",
        "CONTRATANTE: O ESTADO DO PARANÁ, através da SECRETARIA DE ESTADO DA SEGURANÇA PÚBLICA",
        "CONTRATADO(A): PADARIA EXEMPLO LTDA, CNPJ nº 35.014.719/0001-66", "CLÁUSULA PRIMEIRA - DO OBJETO",
    ]
    return paginas([primeira] + [cabecalho + [f"CLÁUSULA {n + 2}ª - DISPOSIÇÕES"] for n in range(paginas_ - 1)])


def aditivo(*, numero="0355/2025", contrato_="0762/2024", protocolo="24.740.746-4", paginas_=2) -> bytes:
    """Termo aditivo com o cabeçalho "TERMO ADITIVO Nº …" em toda página."""
    cabecalho = ["SECRETARIA DE ESTADO DA SEGURANÇA PÚBLICA", f"CENTRO DE CONTRATOS E CONVÊNIOS – TERMO ADITIVO Nº {numero}",
                 f"Protocolo nº {protocolo}–Contrato nº {contrato_}–GMS 7339/2024–1º Termo Aditivo"]
    primeira = cabecalho + [
        f"PRIMEIRO TERMO ADITIVO AO CONTRATO Nº {contrato_} – GMS Nº 7339/2024",
        "CONTRATANTE: O ESTADO DO PARANÁ", "CONTRATADO(A): PADARIA EXEMPLO LTDA", "CLÁUSULA PRIMEIRA - DO OBJETO",
    ]
    return paginas([primeira] + [cabecalho + ["CLÁUSULA QUARTA – DAS DESPESAS"] for _ in range(paginas_ - 1)])


def nota_empenho(*, numero="2026NE108096", valor="17.558,33", emissao="14/09/26") -> bytes:
    """Nota de empenho do SIAFIC-PR."""
    return pagina([
        "Governo do Estado do Paraná", "Nota de Empenho", "Identificação", "Unidade Gestora Documento Emissão",
        f"390000 - Secretaria de Estado da Segurança Pública {numero} {emissao}",
        "Credor 35014719000166 - PADARIA EXEMPLO LTDA", f"Valor {valor} (valor por extenso)",
        "SIAFIC-PR / SEFA-PR Página 1/1",
    ])


def nota_liquidacao(*, numero="2026NL105243", empenho="2026NE108096", emissao="21/09/26", valor="2.400,00",
                    protocolo="26.613.666-8", notas=(("8.952", "18/09/2026", "1.600,00"), ("8.954", "18/09/2026", "800,00"))) -> bytes:
    """Nota de liquidação do SIAFIC-PR com os documentos comprobatórios (NFs)."""
    linhas = [
        "Governo do Estado do Paraná", "Nota de Liquidação", "Identificação", "Unidade Gestora Documento Emissão",
        f"390000 - Secretaria de Estado da Segurança Pública {numero} {emissao}", "Valor Bruto Valor Líquido",
        f"{valor} {valor}", f"Nota de Empenho {empenho}", "Documentos Comprobatórios",
        "Tipo Número Processo Competência Data Valor",
    ]
    for nf, data, valor_nf in notas:
        linhas += ["Outros Documentos", f"Fiscais {nf} {protocolo} 09/2026 {data} {valor_nf}"]
    linhas.append(f"Total Documentos Comprobatórios {valor}")
    return pagina(linhas)


def email_impresso(*, assunto="Pedido de cobertura do evento", de="Fulano <fulano@exemplo.pr.gov.br>",
                   para="ascom@pc.pr.gov.br", enviado="segunda-feira, 21 de setembro de 2026 10:15",
                   corpo=("Bom dia,", "Solicitamos a cobertura do evento em Ponta Grossa.")) -> bytes:
    """E-mail impresso do Outlook (De/Enviado em/Para/Assunto)."""
    return pagina([f"De: {de}", f"Enviado em: {enviado}", f"Para: {para}", f"Assunto: {assunto}", "", *corpo])


# ─────────────────────────────────────────────────────────────────
# Comprovantes bancários
# ─────────────────────────────────────────────────────────────────

_MESES_ABREV = ["JAN", "FEV", "MAR", "ABR", "MAI", "JUN", "JUL", "AGO", "SET", "OUT", "NOV", "DEZ"]


def _modelos(nome, cpf, valor, data, hora, pagador):
    dia, mes, ano = data.split("/")
    data_nubank = f"{dia} {_MESES_ABREV[int(mes) - 1]} {ano}"
    return {
        "caixa_saque": [
            "CAIXA ECONOMICA FEDERAL", "COMPROVANTE DE SAQUE", "TERMINAL: 012345   AGENCIA: 1234",
            f"DATA: {data}   HORA: {hora}:15", "CONTA: 0001 / 00012345-6", f"NOME: {nome.upper()}",
            f"CPF: {_cpf_meio(cpf)}", f"VALOR: R$ {valor}", "NSU: 000123456",
        ],
        "bb_saque": [
            "BANCO DO BRASIL", "COMPROVANTE DE SAQUE", "AUTOATENDIMENTO", f"CLIENTE: {nome.upper()}",
            "AGENCIA: 1234-5   CONTA: 12.345-6", f"DATA {data}   HORA {hora}:15", f"VALOR DO SAQUE      R$ {valor}",
            "SALDO DISPONIVEL   R$ 12,34", "AUTENTICACAO SISBB: 1.2AB.3CD.4EF",
        ],
        "bb_pix": [
            "BANCO DO BRASIL", "Comprovante Pix", "Pix enviado", f"Data: {data} às {hora}", f"Valor: R$ {valor}",
            "Pagador", f"Nome: {pagador}", "Recebedor", f"Nome: {nome.title()}", f"CPF: {_cpf_meio(cpf)}",
            "Instituição: CAIXA ECONOMICA FEDERAL", "ID: E00000000202609211032abcdef",
        ],
        "itau_pix": [
            "Itaú", "comprovante de transferência", "Pix enviado", f"valor R$ {valor}",
            f"data da transferência {data} - {hora}", "de", f"nome {pagador}", "para", f"nome {nome.upper()}",
            f"CPF {_cpf_meio(cpf)}", "instituição CAIXA ECONOMICA FEDERAL", "autenticação 1A2B3C4D",
        ],
        "bradesco_transferencia": [
            "Bradesco", "Comprovante de Transação Bancária", "Transferência entre contas",
            f"Data da operação: {data} - {hora}", f"Valor: R$ {valor}", f"Favorecido: {nome.upper()}",
            f"CPF: {_cpf_pontas(cpf)}", "Agência: 1234   Conta: 12345-6", "Controle: 0012345678",
        ],
        "santander_pix": [
            "Santander", "Comprovante do Pix", "Valor pago", f"R$ {valor}", "Data e hora", f"{data} às {hora}",
            "Para", nome.upper(), f"CPF •••.{cpf[3:6]}.{cpf[6:9]}-••", "De", pagador,
        ],
        "nubank_pix": [
            "Comprovante de transferência", f"{data_nubank} - {hora}:15", "Valor", f"R$ {valor}",
            "Tipo de transferência", "Pix", "Destino", f"Nome {nome.title()}", f"CPF •••.{cpf[3:6]}.{cpf[6:9]}-••",
            "Instituição CAIXA ECONOMICA FEDERAL", "Origem", f"Nome {pagador}", "Instituição NU PAGAMENTOS - IP",
            "Nu Pagamentos S.A. - Instituição de Pagamento", "Ouvidoria: 0800 887 0463",
        ],
        "sicredi_ted": [
            "Sicredi", "Comprovante de TED", f"Data da Transação: {data}", f"Hora: {hora}", f"Valor: R$ {valor}",
            f"Favorecido: {nome.upper()}", f"CPF/CNPJ do Favorecido: {_cpf_meio(cpf)}",
            "Banco: 104 - CAIXA ECONOMICA FEDERAL",
        ],
        "inter_pix": [
            "Pix enviado", f"R$ {valor}", f"{data} às {hora}", "Quem recebeu", f"Nome {nome.title()}",
            f"CPF {_cpf_meio(cpf)}", "Instituição CAIXA ECONOMICA FEDERAL", "Quem pagou", f"Nome {pagador}",
            "Instituição BANCO INTER S.A.",
        ],
        "caixa_deposito": [
            "CAIXA", "COMPROVANTE DE DEPOSITO", f"DATA: {data}  HORA: {hora}", f"DEPOSITANTE: {pagador}",
            f"FAVORECIDO: {nome.upper()}", f"CPF: {_cpf_meio(cpf)}", f"VALOR: R$ {valor}",
        ],
    }


#: (operação, banco, formato do CPF mascarado — "" se o modelo não mostra CPF) de cada modelo.
MODELOS_COMPROVANTE = {
    "caixa_saque": ("saque", "Caixa", "meio"),
    "bb_saque": ("saque", "Banco do Brasil", ""),
    "bb_pix": ("pix", "Banco do Brasil", "meio"),
    "itau_pix": ("pix", "Itaú", "meio"),
    "bradesco_transferencia": ("transferencia", "Bradesco", "pontas"),
    "santander_pix": ("pix", "Santander", "meio"),
    "nubank_pix": ("pix", "Nubank", "meio"),
    "sicredi_ted": ("ted", "Sicredi", "meio"),
    "inter_pix": ("pix", "Inter", "meio"),
    "caixa_deposito": ("deposito", "Caixa", "meio"),
}


def linhas_comprovante(modelo="bb_saque", *, nome="FULANO DE TAL", cpf="52998224725", valor="580,00",
                       data="21/09/2026", hora="10:32", pagador="Beltrano Pagador Souza") -> list[str]:
    """As linhas do comprovante do `modelo` (ver `MODELOS_COMPROVANTE`)."""
    return _modelos(nome, cpf, valor, data, hora, pagador)[modelo]


def comprovante(modelo="bb_saque", **dados) -> bytes:
    """PDF de 1 página com o comprovante do `modelo` (mesmos argumentos de `linhas_comprovante`)."""
    return pagina(linhas_comprovante(modelo, **dados), fonte=11)


# ─────────────────────────────────────────────────────────────────
# Processos prontos
# ─────────────────────────────────────────────────────────────────

def processo_viagens(*, numero=12, ano=2026, protocolo="26.613.666-8", servidores=(("FULANO DE TAL", "52998224725"),),
                     convalidacao=True, chefe=("Chefe da Silva", "11144477735"), diario_deitado=90,
                     modelos_comprovante=("bb_saque",), comprovante_imagem=False, valor="580,00", **opcoes) -> bytes:
    """Processo de prestação de Viagens na ordem pedida pelo usuário.

    Capa → ofício (assinado pela chefia, página embrulhada) → despacho
    (assinado) → um RT por servidor (assinado por ele) → diário de bordo
    (deitado `diario_deitado` graus dentro da moldura retrato; 0 = em pé,
    paisagem) → um comprovante por servidor (modelo em `modelos_comprovante`,
    repetido se houver mais servidores; com `comprovante_imagem`, página só
    de imagem). `opcoes` vão para `processo_eprotocolo`.
    """
    numero_ano = f"{numero:02d}/{ano}"
    docs = [
        Doc(oficio_viagens(numero=numero, ano=ano, protocolo=protocolo, servidores=servidores, convalidacao=convalidacao),
            arquivo=f"Of.{numero}-{ano}.pdf", assinantes=[chefe], embrulhar=True),
        Doc(despacho(protocolo=protocolo, assunto=f"PRESTAÇÃO DE CONTAS DE DIÁRIAS - OFÍCIO {numero_ano}"),
            arquivo="DESPACHO_1.pdf", assinantes=[chefe]),
    ]
    for nome, cpf in servidores:
        docs.append(Doc(relatorio_tecnico(oficio=numero_ano, nome=nome, cpf=cpf, diaria=f"R$ {valor}"),
                        arquivo=f"RT_{nome.split()[0].lower()}.pdf", assinantes=[(nome.title(), cpf)]))
    diario = diario_bordo(oficio=numero_ano, protocolo=protocolo)
    docs.append(Doc(girar_conteudo(diario, diario_deitado) if diario_deitado else diario, arquivo="Diario_de_bordo.pdf",
                    embrulhar=True))
    for posicao, (nome, cpf) in enumerate(servidores):
        modelo = modelos_comprovante[posicao % len(modelos_comprovante)]
        documento = comprovante(modelo, nome=nome, cpf=cpf, valor=valor)
        if comprovante_imagem:
            documento = pagina_imagem(documento)
        docs.append(Doc(documento, arquivo=f"comprovante_{nome.split()[0].lower()}.pdf", inserido_por=nome.title()))
    return processo_eprotocolo(docs, protocolo=protocolo, numero_ano=numero_ano, **opcoes)


def processo_coffee_break(*, numero=123, ano=2026, protocolo="26.613.666-8", notas=((8952, "1.600,00"), (8954, "800,00")),
                          pcpr="2026.050731.000", contrato_="0762/2024", **opcoes) -> bytes:
    """Processo de pagamento do Coffee Break como os reais: ofício, NF + certifico por nota,
    cinco certidões, aditivo e contrato aninhados, despacho, empenho e liquidação."""
    fiscal = ("Fiscal do Contrato", "22233344405")
    docs = [Doc(oficio_coffee_break(numero=numero, ano=ano, pcpr=pcpr, notas=[str(n) for n, _ in notas], contrato=contrato_),
                arquivo=f"Of.{numero}coffeebreak.pdf", assinantes=[("Chefe da Silva", "11144477735")])]
    for numero_nf, valor_nf in notas:
        docs.append(Doc(nota_fiscal(numero=numero_nf, valor=valor_nf), arquivo=f"NF{numero_nf}.pdf", assinantes=[fiscal]))
        docs.append(Doc(certifico(nota=str(numero_nf), contrato=contrato_), arquivo=f"CERTIFICO{numero_nf}.pdf",
                        assinantes=[fiscal]))
    for tipo in ("FGTS", "TRABALHISTA", "MUNICIPAL", "ESTADUAL", "FEDERAL"):
        docs.append(Doc(certidao(tipo), arquivo=f"{tipo}.pdf"))
    docs += [
        Doc(aditivo(contrato_=contrato_), arquivo="CONTRATOTERMOADITIVO.pdf", aninhado=True, embrulhar=True),
        Doc(contrato(numero=contrato_), arquivo="CONTRATO.pdf", aninhado=True),
        Doc(despacho(protocolo=protocolo, assunto=f"CONTRATO {contrato_} - PAGAMENTO"), arquivo="DESPACHO_1.pdf"),
        Doc(nota_empenho(), arquivo="2026NE108096.pdf"),
        Doc(nota_liquidacao(protocolo=protocolo), arquivo="LIQ.pdf"),
    ]
    return processo_eprotocolo(docs, protocolo=protocolo, numero_ano=f"{numero}/{ano}", assunto="LICITACAO", **opcoes)
