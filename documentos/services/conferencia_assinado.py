"""Conferência do PDF "assinado" na hora de anexar (m112).

Até aqui entrava qualquer PDF: o mesmo documento sem assinatura, ou o de
outra viagem. Agora o sistema lê o arquivo, tudo local (pypdf e o leitor de
`core/leitura`), e diz o que encontrou:

- se há assinatura digital — pelos campos `/Sig` do PDF (ICP-Brasil,
  gov.br, Adobe) ou pelo carimbo desenhado na página (o do eProtocolo,
  "Assinado de forma digital por", "Documento assinado digitalmente");
- quem assinou e quando, do campo (`/Name`, `/M`), do certificado dentro do
  `/Contents` (o CN "NOME:CPF" da ICP-Brasil, lido sem validar a cadeia) ou
  do carimbo;
- se o PDF é do documento certo: o número (ofício, OS, plano), o protocolo e
  os nomes que o documento tem de trazer.

É aviso, não bloqueio: quem anexa decide se continua. O que se leu fica na
versão assinada (`DocumentoAssinaturaVersao`).
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from datetime import datetime
from io import BytesIO

from django.utils import timezone

logger = logging.getLogger(__name__)

RX_NUMERO_DOCUMENTO = re.compile(
    r"(?:Of[ií]cio|Ordem de Servi[çc]o|O\.?S\.?|Plano de Trabalho|Justificativa)\s*"
    r"(?:N|n)?[ºo°.]*\s*(\d{1,4})\s*/\s*(\d{4})",
    re.I,
)
# Data dos campos de assinatura do PDF: D:YYYYMMDDHHmmSS+HH'mm'
RX_DATA_PDF = re.compile(r"D:(\d{4})(\d{2})(\d{2})(\d{2})?(\d{2})?(\d{2})?([+\-Z])?(\d{2})?'?(\d{2})?")
# CN dentro do DER do certificado: OID 2.5.4.3 seguido de UTF8String (0x0C) ou PrintableString (0x13).
RX_CN_DER = re.compile(rb"\x06\x03\x55\x04\x03[\x0c\x13]([\x01-\x7f])")


@dataclass
class Assinante:
    nome: str
    quando: datetime | None = None
    origem: str = ""  # "campo", "certificado", "carimbo", "eprotocolo"

    def como_json(self) -> dict:
        return {"nome": self.nome, "quando": self.quando.isoformat() if self.quando else "", "origem": self.origem}


@dataclass
class Conferencia:
    assinado: bool = False
    assinantes: list[Assinante] = field(default_factory=list)
    avisos: list[str] = field(default_factory=list)
    sem_texto: bool = False

    @property
    def assinante(self) -> Assinante | None:
        # O do campo/certificado vale mais que o carimbo (que é só desenho).
        for origem in ("certificado", "campo", "eprotocolo", "carimbo"):
            for a in self.assinantes:
                if a.origem == origem and a.nome:
                    return a
        return self.assinantes[0] if self.assinantes else None

    def resumo(self) -> str:
        """"Assinado digitalmente por FULANO em 24/09/2026 10:30" ou o aviso de que não há assinatura."""
        if not self.assinado:
            return "Este PDF não tem assinatura digital reconhecível."
        quem = self.assinante
        if quem is None:
            return "PDF com assinatura digital."
        texto = f"Assinado digitalmente por {quem.nome}"
        if quem.quando:
            momento = timezone.localtime(quem.quando) if timezone.is_aware(quem.quando) else quem.quando
            texto += f" em {momento:%d/%m/%Y %H:%M}" if (momento.hour or momento.minute) else f" em {momento:%d/%m/%Y}"
        return texto + "."

    def como_json(self) -> dict:
        return {
            "assinado": self.assinado, "resumo": self.resumo(), "avisos": list(self.avisos), "sem_texto": self.sem_texto,
            "assinantes": [a.como_json() for a in self.assinantes],
        }


# ---- Leitura do PDF ---------------------------------------------------------


def _data_pdf(valor) -> datetime | None:
    m = RX_DATA_PDF.search(str(valor or ""))
    if not m:
        return None
    try:
        ano, mes, dia = int(m.group(1)), int(m.group(2)), int(m.group(3))
        hora, minuto, segundo = int(m.group(4) or 0), int(m.group(5) or 0), int(m.group(6) or 0)
        momento = datetime(ano, mes, dia, hora, minuto, segundo)
    except ValueError:
        return None
    sinal = m.group(7)
    if sinal in ("+", "-"):
        from datetime import timedelta, timezone as tz

        desvio = timedelta(hours=int(m.group(8) or 0), minutes=int(m.group(9) or 0))
        return momento.replace(tzinfo=tz(desvio if sinal == "+" else -desvio))
    if sinal == "Z":
        from datetime import timezone as tz

        return momento.replace(tzinfo=tz.utc)
    return timezone.make_aware(momento)


def _nome_do_certificado(contents) -> str:
    """O CN do certificado do assinante dentro do PKCS#7, sem validar nada:
    o da ICP-Brasil é "NOME:CPF" — fica o nome. Vazio quando não se acha."""
    try:
        dados = bytes(contents)
    except Exception:
        return ""
    candidatos = []
    for m in RX_CN_DER.finditer(dados):
        tamanho = m.group(1)[0]
        inicio = m.end()
        valor = dados[inicio:inicio + tamanho]
        try:
            texto = valor.decode("utf-8").strip()
        except UnicodeDecodeError:
            continue
        if texto:
            candidatos.append(texto)
    # A cadeia traz também as ACs ("AC Certisign...", "Autoridade Certificadora..."):
    # o assinante é o CN com CPF ou, na falta, o último que não é AC.
    for texto in candidatos:
        if re.search(r":\d{11}$", texto):
            return texto.rsplit(":", 1)[0].strip()
    for texto in reversed(candidatos):
        if not re.match(r"(?i)^(AC\b|Autoridade Certificadora|ICP-Brasil)", texto):
            return texto
    return ""


def _texto_pdf(valor) -> str:
    try:
        return str(valor or "").strip()
    except Exception:
        return ""


def _campos_de_assinatura(dados: bytes) -> list[Assinante]:
    """Os campos `/Sig` preenchidos do PDF, com nome e data quando os há."""
    from pypdf import PdfReader

    saida = []
    # O pypdf avisa no log sobre PDF malformado ("EOF marker not found"); aqui
    # isso é caso normal (arquivo que não se lê), não erro a registrar.
    registro_pypdf = logging.getLogger("pypdf")
    nivel = registro_pypdf.level
    registro_pypdf.setLevel(logging.ERROR)
    try:
        leitor = PdfReader(BytesIO(dados))
        campos = leitor.get_fields() or {}
    except Exception:
        return saida
    finally:
        registro_pypdf.setLevel(nivel)
    for campo in campos.values():
        try:
            if str(campo.get("/FT") or "") != "/Sig":
                continue
            valor = campo.get("/V")
            valor = valor.get_object() if hasattr(valor, "get_object") else valor
            if not valor:
                continue
            nome = _texto_pdf(valor.get("/Name")) or _nome_do_certificado(valor.get("/Contents") or b"")
            origem = "certificado" if not _texto_pdf(valor.get("/Name")) and nome else "campo"
            saida.append(Assinante(nome=nome, quando=_data_pdf(valor.get("/M")), origem=origem))
        except Exception:  # um campo estranho não derruba a conferência
            continue
    return saida


def _carimbos(texto: str) -> list[Assinante]:
    """Assinaturas escritas na página: o carimbo do eProtocolo e os da ICP/gov.br."""
    from core.leitura.eprotocolo import _assinaturas, _assinaturas_digitais

    saida = []
    for a in _assinaturas(texto):
        saida.append(Assinante(nome=a.nome, quando=a.quando if isinstance(a.quando, datetime) else None, origem="eprotocolo"))
    for a in _assinaturas_digitais(texto):
        saida.append(Assinante(nome=a.nome, quando=a.quando if isinstance(a.quando, datetime) else None, origem="carimbo"))
    return saida


def _numeros_no_texto(texto: str) -> set[str]:
    return {f"{int(n):03d}/{ano}" for n, ano in RX_NUMERO_DOCUMENTO.findall(texto)}


def _numero_normalizado(numero: str) -> str:
    m = re.search(r"(\d{1,4})\s*/\s*(\d{4})", str(numero or ""))
    return f"{int(m.group(1)):03d}/{m.group(2)}" if m else ""


def conferir_pdf_assinado(dados: bytes, *, numero: str = "", protocolo: str = "", nomes=(), rotulo: str = "documento") -> Conferencia:
    """Lê o PDF e diz se tem assinatura, quem assinou e se é o documento esperado.

    `numero` é o número do documento ("123/2026"), `protocolo` o do
    eProtocolo (com ou sem máscara), `nomes` os que o documento tem de
    trazer (o servidor do termo, do relatório), `rotulo` o nome do documento
    nos avisos ("ofício 125/2026").
    """
    from core.leitura.pdf import ArquivoIlegivel, ler_paginas
    from core.leitura.texto import achar_protocolos, normalizar

    conferencia = Conferencia()
    conferencia.assinantes.extend(_campos_de_assinatura(dados))
    try:
        paginas = ler_paginas(dados)
    except ArquivoIlegivel:
        conferencia.avisos.append("Não foi possível ler o PDF para conferir se é o documento certo.")
        paginas = []
    texto = "\n".join(p.texto or "" for p in paginas[:4])
    conferencia.assinantes.extend(_carimbos(texto))
    conferencia.assinado = bool(conferencia.assinantes)

    if paginas and not texto.strip():
        conferencia.sem_texto = True
        conferencia.avisos.append("O PDF é só imagem (digitalizado): não deu para conferir se é o documento certo.")
        return conferencia
    if not texto.strip():
        return conferencia

    esperado = _numero_normalizado(numero)
    achados = _numeros_no_texto(texto)
    if esperado and achados and esperado not in achados:
        lista = ", ".join(sorted(achados))
        conferencia.avisos.append(f"O número neste PDF é {lista}, mas você está anexando no {rotulo} {esperado}.")

    digitos = re.sub(r"\D", "", str(protocolo or ""))
    protocolos = achar_protocolos(texto)
    if digitos and protocolos and digitos not in protocolos:
        p = protocolos[0]
        conferencia.avisos.append(
            f"O protocolo neste PDF é {p[:2]}.{p[2:5]}.{p[5:8]}-{p[8:]}, mas o {rotulo} é do protocolo "
            f"{digitos[:2]}.{digitos[2:5]}.{digitos[5:8]}-{digitos[8:]}."
        )

    corrido = normalizar(" ".join(texto.split()))
    for nome in nomes:
        nome = str(nome or "").strip()
        if nome and normalizar(nome) not in corrido:
            conferencia.avisos.append(f"O nome {nome} não aparece neste PDF.")
    return conferencia


# ---- O que cada artefato espera ----------------------------------------------


def esperado_do_artefato(artefato) -> dict:
    """Número, protocolo, nomes e rótulo que o PDF assinado deste artefato tem de trazer."""
    esperado = {"numero": "", "protocolo": "", "nomes": [], "rotulo": "documento"}
    tipo = str(artefato.tipo or "")
    oficio = artefato.oficio if artefato.oficio_id else None
    if oficio is None and artefato.termo_id and getattr(artefato.termo, "oficio_id", None):
        oficio = artefato.termo.oficio
    if oficio is None and artefato.prestacao_id:
        oficio = artefato.prestacao.oficio
    if artefato.ordem_servico_id:
        ordem = artefato.ordem_servico
        esperado.update(numero=f"{ordem.numero}/{ordem.ano}" if ordem.numero and ordem.ano else "", rotulo="ordem de serviço")
    elif artefato.plano_trabalho_id:
        plano = artefato.plano_trabalho
        esperado.update(numero=f"{plano.numero}/{plano.ano}" if plano.numero and plano.ano else "", rotulo="plano de trabalho")
    elif oficio is not None:
        esperado.update(numero=oficio.numero_formatado if oficio.numero else "", protocolo=oficio.protocolo or "")
        esperado["rotulo"] = {"oficio": "ofício", "justificativa": "ofício", "termo_autorizacao": "termo do ofício",
                              "relatorio_tecnico": "relatório do ofício", "diario_bordo": "diário do ofício"}.get(tipo, "ofício")
    if artefato.servidor_id:
        esperado["nomes"] = [artefato.servidor.nome]
    return esperado


def conferir_artefato(artefato, dados: bytes) -> Conferencia:
    """A conferência do PDF assinado contra o que o artefato espera; nunca
    derruba o anexo — um erro de leitura vira aviso."""
    try:
        esperado = esperado_do_artefato(artefato)
        return conferir_pdf_assinado(dados, **esperado)
    except Exception:
        logger.exception("Falha ao conferir o PDF assinado do artefato %s", getattr(artefato, "pk", "?"))
        conferencia = Conferencia()
        conferencia.avisos.append("Não foi possível conferir o PDF assinado.")
        return conferencia


def mensagens_da_conferencia(conferencia) -> list[tuple[int, str]]:
    """As mensagens da tela depois de anexar: o resumo (sucesso ou aviso) e cada aviso."""
    from django.contrib import messages

    if conferencia is None:
        return []
    saida = [(messages.SUCCESS if conferencia.assinado else messages.WARNING, conferencia.resumo())]
    saida.extend((messages.WARNING, aviso) for aviso in conferencia.avisos)
    return saida
