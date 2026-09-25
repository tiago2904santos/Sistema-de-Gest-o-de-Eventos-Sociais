"""Leitura de um volume do eProtocolo (ou de um PDF avulso) em documentos.

O PDF que o eProtocolo gera ("Processo_26.613.666-8_1.pdf") tem tudo o que
é preciso para separar os documentos sem adivinhar:

1. **marcadores** (outline), um por documento, "N - arquivo original.pdf",
   apontando para a primeira página — são os limites exatos;
2. **código de validação** no rodapé de cada página ("… validarDocumento
   com o código: <hex>"), igual em todas as páginas do mesmo documento;
3. **carimbo Fls./Mov.** no canto: cada Mov é um documento, e a folha "Na"
   (2a, 3a…) é a folha de assinatura dele, que vai junto.

Usa-se o primeiro que existir, nessa ordem. Documento que já tinha passado
por outro protocolo ("aninhado") traz carimbos e rodapés antigos no meio
do texto; vale sempre a ÚLTIMA ocorrência, que é a do protocolo atual.

A capa (folha 1) é lida por coordenadas: no texto extraído o valor sai
antes do rótulo ("123/2026Nº/Ano").

PDF que não é do eProtocolo (e-mail, digitalização, comprovante solto) e
imagem PNG/JPG viram documentos por tipo: páginas seguidas do mesmo tipo
formam um documento quando o tipo repete o cabeçalho em toda página
(diário, NF, contrato); nos outros, cada título abre um documento novo.

Página só de imagem é lida pelo OCR, se houver tesseract (até
`OCR_MAX_PAGINAS` por processo), e o texto lido serve para classificar e
extrair. Sem OCR, a página fica marcada `sem_texto` e o documento vai
para conferência.

LGPD: o /Author do PDF do eProtocolo é o CPF de quem baixou — não é lido.
Nomes e CPFs parciais do rodapé ficam só no resultado (servem para achar o
servidor); nada é registrado em log.
"""

from __future__ import annotations

import logging
import re
from collections import Counter
from dataclasses import dataclass
from dataclasses import field
from datetime import datetime

from core.errors import capture

from . import classificacao as tipos
from . import ocr
from .classificacao import classificar
from .extracao import dados_do_documento
from .extracao import data_hora
from .pdf import PROTOCOLO
from .pdf import RX_CARIMBO
from .pdf import RX_CODIGO
from .pdf import RX_FOLHA_ASSINATURA
from .pdf import Pagina
from .pdf import _abrir
from .pdf import como_pdf
from .pdf import ler_paginas
from .texto import achar_cpfs_mascarados
from .texto import achar_protocolos
from .texto import normalizar

__all__ = ["Assinatura", "Documento", "Processo", "ler_processo"]

CRIADOR_EPROTOCOLO = "Sistema eProtocolo"

_DATA_HORA = r"(\d{2}/\d{2}/\d{4})\s+(\d{2}:\d{2})"
RX_INSERIDO = re.compile(rf"Inserido ao protocolo\s*({PROTOCOLO})\s*por:?\s*(.+?)\s*em:?\s*{_DATA_HORA}", re.I)
RX_ASSINATURA = re.compile(
    r"Assinatura (Avan[çc]ada|Qualificada(?: Externa)?) realizada por:?\s*(.+?)"
    r"(?=\s*(?:Inserido ao protocolo|Documento assinado|Demais assinaturas|Assinatura (?:Avan|Qualif)|"
    r"A autenticidade)|$)",
    re.I,
)
RX_ASSINANTE = re.compile(
    r"\s*([^,()]+?)\s*(?:\(([\dXx*]{3}\.[\dXx*]{3}\.[\dXx*]{3}-[\dXx*]{2})\))?\s*em\s*"
    + _DATA_HORA
    + r"(?:\s*Local:\s*([^.,]+))?",
    re.I,
)
# Assinatura digital fora do eProtocolo: ICP ("Assinado de forma digital por
# NOME:CPF") e gov.br ("Documento assinado digitalmente / NOME / Data: …").
RX_ASSINADO_ICP = re.compile(
    r"Assinado (?:de forma )?digital(?:mente)? por:?\s*([A-ZÀ-Ý][A-ZÀ-Ý .'-]+?)\s*(?::\s*((?:\d\s?){11}))?\s*"
    r"(?:Dados|Data|DN|Raz[aã]o|$)\s*:?\s*(\d{4}\.\d{2}\.\d{2})?\s*(\d{2}:\d{2})?",
    re.I,
)
RX_ASSINADO_GOVBR = re.compile(
    r"Documento assinado digitalmente\s+([A-ZÀ-Ý][A-ZÀ-Ý .'-]+?)\s+Data:\s*" + _DATA_HORA, re.I
)
RX_TITULO_VOLUME = re.compile(r"Processo_(\d{2}\.?\d{3}\.?\d{3}-?\d)_(\d+)", re.I)
RX_MARCADOR = re.compile(r"^\s*(\d+)\s*-\s*(.+?)\s*$")
RX_PAGINACAO = re.compile(r"\bP[AÁ]G(?:INA|\.)?\s*(\d{1,3})\s*(?:DE|/)\s*(\d{1,3})\b|\bFL\.?\s*(\d{1,3})\s*/\s*(\d{1,3})\b", re.I)

_TIPOS_ASSINATURA = {"AVANCADA": "Avançada", "QUALIFICADA": "Qualificada", "QUALIFICADA EXTERNA": "Qualificada Externa"}


@dataclass
class Assinatura:
    """Quem assinou: `tipo` ("Avançada", "Qualificada", "Qualificada Externa",
    ou "Digital"/"gov.br" fora do eProtocolo), `nome` como está no documento,
    `cpf_meio` (os 6 dígitos que o eProtocolo deixa visíveis, `cpf[3:9]`) e
    `quando` (com fuso)."""

    tipo: str
    nome: str
    cpf_meio: str
    quando: datetime | None
    local: str = ""


@dataclass
class Documento:
    """Um documento do processo.

    - `ordem`: posição no processo, a partir de 1.
    - `paginas`: índices das páginas no PDF (a partir de 0), na ordem,
      incluindo a(s) folha(s) de assinatura.
    - `titulo`: nome do arquivo original (marcador ou "Documento: X.pdf").
    - `codigo`: código de validação do eProtocolo.
    - `inserido_por`/`inserido_em`: quem juntou o documento ao protocolo.
    - `folhas_assinatura`: índices das folhas "Na".
    - `aninhado`: o documento já tinha passado por outro protocolo.
    - `tipo`, `confianca`, `evidencias`: da classificação.
    - `dados`: o que se extraiu (ver `extracao.dados_do_documento`).
    """

    ordem: int
    paginas: list[int]
    titulo: str
    codigo: str
    assinaturas: list[Assinatura]
    inserido_por: str
    inserido_em: datetime | None
    folhas_assinatura: list[int]
    aninhado: bool
    tipo: str = ""
    confianca: float = 0.0
    dados: dict = field(default_factory=dict)
    evidencias: list[str] = field(default_factory=list)

    @property
    def paginas_de_conteudo(self) -> list[int]:
        """As páginas sem as folhas de assinatura."""
        return [p for p in self.paginas if p not in self.folhas_assinatura]


@dataclass
class Processo:
    """O PDF lido: `protocolo` (9 dígitos, "" se não achou), `volume` (1, 2…),
    `eh_eprotocolo`, `capa` (campos da folha 1), `documentos`, `paginas` e
    `avisos` (frases para a tela)."""

    protocolo: str
    volume: int | None
    eh_eprotocolo: bool
    capa: dict
    documentos: list[Documento]
    paginas: list[Pagina]
    avisos: list[str]


# ─────────────────────────────────────────────────────────────────
# Moldura de cada página
# ─────────────────────────────────────────────────────────────────

@dataclass
class _Moldura:
    fls: str = ""
    mov: str = ""
    protocolo: str = ""
    inserido_por: str = ""
    inserido_em: datetime | None = None
    codigo: str = ""
    assinaturas: list = field(default_factory=list)
    folha_assinatura: bool = False
    arquivo: str = ""
    capa: bool = False

    @property
    def tem_moldura(self) -> bool:
        return bool(self.mov or self.codigo or self.protocolo)


def _espacos(texto: str) -> str:
    return " ".join((texto or "").split())


def _assinaturas(trecho: str) -> list[Assinatura]:
    saida = []
    for tipo, quem in RX_ASSINATURA.findall(_espacos(trecho)):
        for nome, cpf, dia, hora, local in RX_ASSINANTE.findall(quem):
            mascarados = achar_cpfs_mascarados(cpf) if cpf else []
            meio = next((d for f, d in mascarados if f == "meio"), "")
            if not meio and cpf and re.fullmatch(r"[\d.-]{14}", cpf):
                meio = re.sub(r"\D", "", cpf)[3:9]
            saida.append(
                Assinatura(
                    tipo=_TIPOS_ASSINATURA.get(normalizar(tipo), tipo),
                    nome=nome.strip(),
                    cpf_meio=meio,
                    quando=data_hora(dia, hora),
                    local=(local or "").strip(),
                )
            )
    return saida


def _assinaturas_digitais(texto: str) -> list[Assinatura]:
    """Assinaturas ICP e gov.br desenhadas no próprio PDF (fora do eProtocolo)."""
    corrido = _espacos(texto)
    saida = []
    for m in RX_ASSINADO_ICP.finditer(corrido):
        quando = None
        if m.group(3):
            ano, mes, dia = m.group(3).split(".")
            quando = data_hora(f"{dia}/{mes}/{ano}", m.group(4) or "")
        cpf = re.sub(r"\D", "", m.group(2) or "")
        saida.append(Assinatura("Digital", m.group(1).strip(), cpf[3:9] if len(cpf) == 11 else "", quando))
    for m in RX_ASSINADO_GOVBR.finditer(corrido):
        saida.append(Assinatura("gov.br", m.group(1).strip(), "", data_hora(m.group(2), m.group(3))))
    return saida


def _ler_moldura(pagina: Pagina) -> _Moldura:
    texto = pagina.texto or ""
    moldura = _Moldura()
    carimbos = list(RX_CARIMBO.finditer(texto))
    if carimbos:
        ultimo = carimbos[-1]
        moldura.fls, moldura.mov = ultimo.group(1).lower(), ultimo.group(2)
        rodape = texto[ultimo.start():]
    else:
        folha = RX_FOLHA_ASSINATURA.match(texto)
        if folha:
            moldura.folha_assinatura = True
            moldura.fls, moldura.mov = folha.group(1).lower(), folha.group(2)
            moldura.arquivo = folha.group(3).strip()
        rodape = texto if folha else ""
    if pagina.indice == 0 and _parece_capa(texto):
        moldura.capa = True
        moldura.fls = moldura.fls or "1"
        moldura.mov = moldura.mov or "1"
        protocolos = achar_protocolos(texto)
        moldura.protocolo = protocolos[0] if protocolos else ""
        return moldura
    if not rodape:
        return moldura
    rodape_espacado = _espacos(rodape)
    inseridos = list(RX_INSERIDO.finditer(rodape_espacado))
    if inseridos:
        m = inseridos[-1]
        moldura.protocolo = re.sub(r"\D", "", m.group(1))
        moldura.inserido_por = m.group(2).strip()
        moldura.inserido_em = data_hora(m.group(3), m.group(4))
    codigos = RX_CODIGO.findall(rodape_espacado)
    moldura.codigo = codigos[-1].lower() if codigos else ""
    moldura.assinaturas = _assinaturas(rodape)
    return moldura


def _parece_capa(texto: str) -> bool:
    plano = normalizar(texto)
    return "ORGAO CADASTRO" in plano and ("FOLHA 1" in plano or "PROTOCOLO:" in plano)


# ─────────────────────────────────────────────────────────────────
# Capa por coordenadas
# ─────────────────────────────────────────────────────────────────

_CAMPOS_CAPA = {
    "PROTOCOLO": "protocolo",
    "ORGAO CADASTRO": "orgao_cadastro",
    "EM": "em",
    "CIDADE": "cidade",
    "ASSUNTO": "assunto",
    "DETALHAMENTO": "detalhamento",
    "NO/ANO": "numero_ano",
    "N°/ANO": "numero_ano",
    "PALAVRAS-CHAVE": "palavras_chave",
    "CODIGO TTD": "codigo_ttd",
}


def _rotulo_da_capa(texto: str) -> tuple[str, str] | None:
    """(campo, valor que veio junto) se o trecho é um rótulo da capa ("Assunto:", "Nº/Ano", "Em: 21/09/2026")."""
    plano = normalizar(texto)
    for rotulo, campo in _CAMPOS_CAPA.items():
        if plano == rotulo or plano == rotulo + ":":
            return campo, ""
        if plano.startswith(rotulo + ":"):
            return campo, texto.split(":", 1)[1].strip()
    m = re.fullmatch(r"INTERESSADO\s*(\d+):?(.*)", plano)
    if m:
        return f"interessado_{m.group(1)}", texto.split(":", 1)[1].strip() if ":" in texto else ""
    return None


def _capa_por_coordenadas(pagina_pdf) -> dict:
    """Campos da capa pelo lugar: rótulo à esquerda, valor à direita na mesma linha (±3 pt)."""
    trechos = []

    def visitante(texto, cm, tm, _fonte, _corpo):
        limpo = str(texto or "").strip()
        if not limpo:
            return
        for parte in limpo.split("\n"):
            parte = parte.strip()
            if parte:
                x = cm[0] * tm[4] + cm[2] * tm[5] + cm[4]
                y = cm[1] * tm[4] + cm[3] * tm[5] + cm[5]
                trechos.append((x, y, parte))

    try:
        pagina_pdf.extract_text(visitor_text=visitante)
    except Exception as exc:
        capture(exc, "leitura.eprotocolo.capa", level=logging.WARNING)
        return {}
    rotulos = []
    valores = []
    for x, y, parte in trechos:
        achado = _rotulo_da_capa(parte)
        if achado:
            rotulos.append((x, y, achado[0], achado[1]))
        else:
            valores.append((x, y, parte))

    campos: dict[str, str] = {}
    for x, y, campo, junto in rotulos:
        if junto:
            campos[campo] = junto
            continue
        # Até onde vai o valor: o próximo rótulo à direita na mesma linha e o
        # próximo rótulo abaixo na mesma coluna.
        direita = min((rx for rx, ry, *_ in rotulos if abs(ry - y) <= 3 and rx > x + 5), default=10_000)
        abaixo = max((ry for rx, ry, *_ in rotulos if abs(rx - x) <= 10 and ry < y - 3), default=y - 15)
        partes = [
            (vx, vy, v) for vx, vy, v in valores
            if x + 15 <= vx < direita and abaixo + 3 < vy <= y + 3
        ]
        if not partes:  # "Protocolo:" tem o número embaixo, na mesma coluna
            partes = [(vx, vy, v) for vx, vy, v in valores if abs(vx - x) <= 20 and y - 30 <= vy < y - 3]
        if partes:
            partes.sort(key=lambda item: (-round(item[1]), item[0]))
            campos[campo] = " ".join(v for _, _, v in partes).strip()
    return campos


def _ler_capa(leitor, pagina: Pagina) -> dict:
    campos = _capa_por_coordenadas(leitor.pages[pagina.indice])
    capa: dict = {}
    for chave in ("orgao_cadastro", "cidade", "assunto", "detalhamento", "palavras_chave", "numero_ano", "codigo_ttd"):
        valor = (campos.get(chave) or "").strip()
        if valor and valor != "-":
            capa[chave] = valor
    protocolos = achar_protocolos(campos.get("protocolo", "")) or achar_protocolos(pagina.texto)
    if protocolos:
        capa["protocolo"] = protocolos[0]
    m = re.search(_DATA_HORA, campos.get("em", ""))
    if m:
        capa["em"] = data_hora(m.group(1), m.group(2))
    interessados = [
        campos[chave].strip()
        for chave in sorted((c for c in campos if c.startswith("interessado_")), key=lambda c: int(c.split("_")[1]))
        if campos[chave].strip()
    ]
    if interessados:
        capa["interessados"] = interessados
    # Plano B pelo texto (capa desenhada de outro jeito).
    for chave, valor in dados_do_documento(tipos.CAPA, pagina.texto).items():
        capa.setdefault(chave, valor)
    return capa


# ─────────────────────────────────────────────────────────────────
# Segmentação
# ─────────────────────────────────────────────────────────────────

def _marcadores(leitor, total: int) -> list[tuple[int, str]]:
    """(página inicial, título) de cada marcador de 1º nível, se formarem uma sequência válida."""
    try:
        itens = leitor.outline
    except Exception:
        return []
    saida = []
    for item in itens or []:
        if isinstance(item, list):
            continue
        try:
            pagina = leitor.get_destination_page_number(item)
        except Exception:
            continue
        if pagina is None or not 0 <= pagina < total:
            continue
        saida.append((int(pagina), str(getattr(item, "title", "") or "").strip()))
    inicios = [p for p, _ in saida]
    if not saida or inicios != sorted(set(inicios)):
        return []
    return saida


def _grupos_por_marcadores(marcadores, total) -> list[tuple[list[int], str]]:
    grupos = []
    if marcadores[0][0] > 0:
        grupos.append((list(range(0, marcadores[0][0])), ""))
    for posicao, (inicio, titulo) in enumerate(marcadores):
        fim = marcadores[posicao + 1][0] if posicao + 1 < len(marcadores) else total
        m = RX_MARCADOR.match(titulo)
        grupos.append((list(range(inicio, fim)), m.group(2) if m else titulo))
    return grupos


def _grupos_por_moldura(molduras: list[_Moldura]) -> list[tuple[list[int], str]]:
    """Mesmo código de validação (ou, sem ele, mesmo Mov) = mesmo documento; a folha "Na" fecha o documento."""
    grupos: list[dict] = []
    for indice, moldura in enumerate(molduras):
        atual = grupos[-1] if grupos else None
        if moldura.capa:
            grupos.append({"paginas": [indice], "mov": "1", "codigo": "", "capa": True, "fechado": True})
            continue
        if moldura.folha_assinatura:
            if atual and not atual["capa"] and atual["mov"] == moldura.mov:
                atual["paginas"].append(indice)
                atual["fechado"] = True
            else:
                grupos.append({"paginas": [indice], "mov": moldura.mov, "codigo": "", "capa": False, "fechado": True})
            continue
        mesmo = bool(
            atual
            and not atual["capa"]
            and not atual["fechado"]
            and (
                (moldura.codigo and moldura.codigo == atual["codigo"])
                or (moldura.mov and moldura.mov == atual["mov"] and not (moldura.codigo and atual["codigo"]))
            )
        )
        if mesmo:
            atual["paginas"].append(indice)
            atual["codigo"] = atual["codigo"] or moldura.codigo
        else:
            grupos.append(
                {"paginas": [indice], "mov": moldura.mov, "codigo": moldura.codigo, "capa": False, "fechado": False}
            )
    return [(g["paginas"], "") for g in grupos]


def _paginacao(texto: str) -> tuple[int, int] | None:
    m = RX_PAGINACAO.search(texto or "")
    if not m:
        return None
    k, n = (m.group(1), m.group(2)) if m.group(1) else (m.group(3), m.group(4))
    k, n = int(k), int(n)
    return (k, n) if 1 <= k <= n else None


def _chave_de_continuacao(tipo: str, texto: str) -> str:
    """O que precisa bater para duas páginas do mesmo tipo contínuo serem o mesmo documento."""
    if tipo == tipos.NOTA_FISCAL:
        from coffee_break.nota_fiscal import numero_no_texto

        return numero_no_texto(texto)
    return ""


def _grupos_avulsos(paginas: list[Pagina], nome_arquivo: str) -> list[tuple[list[int], str]]:
    grupos: list[dict] = []
    for pagina in paginas:
        atual = grupos[-1] if grupos else None
        if pagina.sem_texto and not pagina.ocr:
            grupos.append({"paginas": [pagina.indice], "tipo": tipos.DESCONHECIDO, "imagem": True, "pag": None, "chave": ""})
            continue
        # Sem o nome do arquivo: "comprovantes.pdf" puxaria toda página de
        # continuação para "comprovante". O nome só entra no documento inteiro.
        tipo, _, _ = classificar(pagina.corpo)
        paginacao = _paginacao(pagina.corpo)
        chave = _chave_de_continuacao(tipo, pagina.corpo)
        continua = False
        if atual and not atual["imagem"]:
            anterior = atual["pag"]
            if paginacao and paginacao[0] > 1 and anterior and anterior == (paginacao[0] - 1, paginacao[1]):
                continua = True
            elif paginacao and paginacao[0] == 1:
                continua = False
            elif tipo == tipos.DESCONHECIDO:
                continua = True
            elif tipo == atual["tipo"] and tipo in tipos.TIPOS_CONTINUOS:
                continua = not (chave and atual["chave"] and chave != atual["chave"])
        if continua:
            atual["paginas"].append(pagina.indice)
            atual["pag"] = paginacao or atual["pag"]
            atual["chave"] = atual["chave"] or chave
        else:
            grupos.append({"paginas": [pagina.indice], "tipo": tipo, "imagem": False, "pag": paginacao, "chave": chave})
    titulo = nome_arquivo if len(grupos) == 1 else ""
    return [(g["paginas"], titulo) for g in grupos]


# ─────────────────────────────────────────────────────────────────
# OCR das páginas sem texto
# ─────────────────────────────────────────────────────────────────

def _aplicar_ocr(pdf: bytes, paginas: list[Pagina], ordem: list[int]) -> tuple[int, int]:
    """Lê pelo OCR as páginas sem texto, na ordem de prioridade dada; devolve (lidas, sem texto)."""
    sem_texto = [i for i in ordem if paginas[i].sem_texto]
    if not sem_texto or not ocr.disponivel():
        return 0, len(sem_texto)
    orcamento = ocr.max_paginas()
    lidas = 0
    for indice in sem_texto[:orcamento]:
        leitura = ocr.analisar_pagina(pdf, indice)
        pagina = paginas[indice]
        # Página só de imagem: o pouco texto que ela tenha (um nº de página, um
        # cabeçalho de navegador) não decide o sentido da imagem; o OCR decide.
        if leitura.rotacao is not None:
            pagina.angulo_texto = leitura.rotacao
        if leitura.texto.strip():
            pagina.corpo = leitura.texto
            pagina.ocr = True
            lidas += 1
    return lidas, len(sem_texto)


# ─────────────────────────────────────────────────────────────────
# Documento
# ─────────────────────────────────────────────────────────────────

def _montar_documento(ordem, indices, titulo, paginas, molduras, capa) -> Documento:
    folhas = [i for i in indices if molduras[i].folha_assinatura]
    conteudo = [i for i in indices if i not in folhas] or list(indices)
    primeira = conteudo[0]
    moldura = molduras[primeira]
    titulo = titulo or next((molduras[i].arquivo for i in folhas if molduras[i].arquivo), "")
    assinaturas: list[Assinatura] = []
    vistas = set()
    for i in indices:
        # A do eProtocolo (rodapé ou folha "Na") e a digital desenhada no corpo (ICP, gov.br).
        encontradas = molduras[i].assinaturas + _assinaturas_digitais(paginas[i].corpo)
        for assinatura in encontradas:
            chave = (assinatura.tipo, normalizar(assinatura.nome), assinatura.quando)
            if chave not in vistas:
                vistas.add(chave)
                assinaturas.append(assinatura)
    inserido = next((molduras[i] for i in indices if molduras[i].inserido_por), None)
    aninhado = any(
        paginas[i].base <= -79 or RX_INSERIDO.search(_espacos(paginas[i].corpo)) for i in conteudo
    )
    documento = Documento(
        ordem=ordem,
        paginas=list(indices),
        titulo=titulo,
        codigo=next((molduras[i].codigo for i in conteudo if molduras[i].codigo), ""),
        assinaturas=assinaturas,
        inserido_por=inserido.inserido_por if inserido else "",
        inserido_em=inserido.inserido_em if inserido else None,
        folhas_assinatura=folhas,
        aninhado=bool(aninhado),
    )
    if moldura.capa:
        documento.tipo, documento.confianca = tipos.CAPA, 1.0
        documento.evidencias = ["folha 1 do volume do eProtocolo"]
        documento.dados = dict(capa)
        return documento

    tipo, confianca, evidencias = classificar(paginas[primeira].corpo, titulo)
    if tipo == tipos.DESCONHECIDO and len(conteudo) > 1:
        tipo, confianca, evidencias = classificar("\n".join(paginas[i].corpo for i in conteudo[:3]), titulo)
    documento.tipo, documento.confianca, documento.evidencias = tipo, confianca, evidencias
    if any(paginas[i].ocr for i in conteudo):
        documento.evidencias = documento.evidencias + ["texto lido por OCR"]
        documento.confianca = round(documento.confianca * 0.9, 2)
    texto = "\n".join(paginas[i].corpo for i in conteudo)
    try:
        documento.dados = dados_do_documento(tipo, texto)
    except Exception as exc:  # regra nova quebrando não derruba a leitura inteira
        capture(exc, "leitura.eprotocolo.extrair", level=logging.WARNING, tipo=tipo)
        documento.dados = {}
    return documento


# ─────────────────────────────────────────────────────────────────
# Avisos
# ─────────────────────────────────────────────────────────────────

def _numero_da_folha(fls: str) -> tuple[int, str] | None:
    m = re.fullmatch(r"(\d+)([a-z]?)", fls or "")
    return (int(m.group(1)), m.group(2)) if m else None


def _aviso_de_folhas(molduras: list[_Moldura], volume: int | None) -> str:
    folhas = [f for f in (_numero_da_folha(m.fls) for m in molduras) if f]
    if not folhas:
        return ""
    faltando = []
    # Volume 1 começa na folha 1; volume seguinte ou documento baixado avulso, onde começar.
    esperado = 1 if volume == 1 else folhas[0][0]
    for numero, sufixo in folhas:
        if sufixo:
            continue
        if numero > esperado:
            faltando.append((esperado, numero - 1))
        esperado = max(esperado, numero + 1)
    if not faltando:
        return ""
    trechos = ", ".join(f"{a}" if a == b else f"{a} a {b}" for a, b in faltando[:5])
    return f"Faltam folhas no volume ({trechos}): o arquivo pode estar incompleto ou ser só parte do processo."


# ─────────────────────────────────────────────────────────────────
# Entrada
# ─────────────────────────────────────────────────────────────────

def _volume_e_protocolo(*nomes: str) -> tuple[str, int | None]:
    for nome in nomes:
        m = RX_TITULO_VOLUME.search(nome or "")
        if m:
            return re.sub(r"\D", "", m.group(1)), int(m.group(2))
    return "", None


def ler_processo(dados: bytes, nome_arquivo: str = "") -> Processo:
    """Lê o PDF do eProtocolo (ou PDF avulso, ou imagem PNG/JPG) e devolve os documentos.

    Não grava nada. Levanta `pdf.ArquivoIlegivel` se o arquivo não abrir.
    """
    pdf = como_pdf(dados)
    leitor = _abrir(pdf)
    paginas = ler_paginas(pdf)
    total = len(paginas)
    avisos: list[str] = []

    try:
        metadados = leitor.metadata or {}
        criador = str(metadados.get("/Creator") or "")
        titulo_pdf = str(metadados.get("/Title") or "")
    except Exception:
        criador, titulo_pdf = "", ""

    molduras = [_ler_moldura(pagina) for pagina in paginas]
    com_rodape = sum(1 for m in molduras if m.protocolo and not m.capa)
    eh_eprotocolo = criador.strip() == CRIADOR_EPROTOCOLO or (total > 0 and com_rodape * 2 >= total)

    protocolo_titulo, volume = _volume_e_protocolo(titulo_pdf, nome_arquivo)
    contagem = Counter(m.protocolo for m in molduras if m.protocolo and not m.capa)
    protocolo = contagem.most_common(1)[0][0] if contagem else ""
    if protocolo and protocolo_titulo and protocolo != protocolo_titulo:
        avisos.append("O número no nome do arquivo não é o mesmo do rodapé das páginas; vale o do rodapé.")
    capa: dict = {}
    if molduras and molduras[0].capa:
        capa = _ler_capa(leitor, paginas[0])
    protocolo = protocolo or protocolo_titulo or capa.get("protocolo", "")

    if eh_eprotocolo:
        marcadores = _marcadores(leitor, total)
        if marcadores:
            grupos = _grupos_por_marcadores(marcadores, total)
            if marcadores[0][0] > 0:
                avisos.append("As primeiras páginas não têm marcador: devem ser a continuação do volume anterior.")
        else:
            grupos = _grupos_por_moldura(molduras)
        # OCR: primeiro a primeira página de conteúdo de cada documento (é a que classifica).
        primeiras = [next((i for i in g if not molduras[i].folha_assinatura), g[0]) for g, _ in grupos]
        prioridade = primeiras + [i for g, _ in grupos for i in g if i not in primeiras]
        lidas, sem_texto = _aplicar_ocr(pdf, paginas, prioridade)
    else:
        lidas, sem_texto = _aplicar_ocr(pdf, paginas, list(range(total)))
        grupos = _grupos_avulsos(paginas, nome_arquivo)

    documentos = [
        _montar_documento(ordem, indices, titulo, paginas, molduras, capa)
        for ordem, (indices, titulo) in enumerate(grupos, start=1)
        if indices
    ]

    if eh_eprotocolo:
        aviso = _aviso_de_folhas(molduras, volume)
        if aviso:
            avisos.append(aviso)
    if sem_texto:
        if lidas:
            avisos.append(f"{sem_texto} página(s) só de imagem; o OCR leu {lidas}. Confira os dados dessas páginas.")
        else:
            avisos.append(f"{sem_texto} página(s) só de imagem, sem leitura do texto: confira na tela e informe os dados.")
    return Processo(
        protocolo=protocolo,
        volume=volume,
        eh_eprotocolo=eh_eprotocolo,
        capa=capa,
        documentos=documentos,
        paginas=paginas,
        avisos=avisos,
    )
