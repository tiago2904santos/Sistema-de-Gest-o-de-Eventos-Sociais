"""O número da nota fiscal, lido do PDF que o fornecedor manda.

Na etapa 2 basta anexar a nota: o sistema tira o número dela. A nota do
processo 26.617.058-0 é um DANFE (NF-e), onde o número aparece como
"Nº 000.008.957" e dentro da chave de acesso de 44 dígitos (posições 26 a
34). Nota de serviço (NFS-e) traz "Número da NFS-e 123" ou parecido. Quando
nada disso aparece (PDF escaneado, sem texto), devolve "" e a tela pede o
número.
"""

from __future__ import annotations

import io
import re

# A chave de acesso da NF-e: 44 dígitos, em geral em grupos de 4.
_CHAVE = re.compile(r"(?<!\d)((?:\d[\s.]?){43}\d)(?!\d)")
# DANFE: "Nº 000.008.957" (com ou sem pontos).
_DANFE = re.compile(r"N[º°o]\.?\s*:?\s*(\d{3}\.\d{3}\.\d{3}|\d{9})(?!\d)")
# NFS-e e notas com o número por extenso no rótulo.
_ROTULOS = (
    re.compile(r"N[úu]mero\s+da\s+(?:NFS-?e|Nota(?:\s+Fiscal)?)\s*[:\-]?\s*(\d{1,15})", re.IGNORECASE),
    re.compile(r"NFS-?e\s*(?:N[º°o.]*|n[úu]mero)\s*[:\-]?\s*(\d{1,15})", re.IGNORECASE),
    re.compile(r"Nota\s+Fiscal[^\n\d]{0,40}?N[º°o.]+\s*[:\-]?\s*(\d{1,15})", re.IGNORECASE),
)


def _sem_zeros(numero):
    digitos = re.sub(r"\D", "", numero)
    return str(int(digitos)) if digitos else ""


def numero_no_texto(texto: str) -> str:
    """O número da nota num texto extraído do PDF; "" se não achar."""
    texto = texto or ""
    for achado in _CHAVE.finditer(texto):
        chave = re.sub(r"\D", "", achado.group(1))
        # Modelo 55 (NF-e) ou 65 (NFC-e) nas posições 21-22; número nas 26-34.
        if len(chave) == 44 and chave[20:22] in ("55", "65"):
            numero = _sem_zeros(chave[25:34])
            if numero and numero != "0":
                return numero
    achado = _DANFE.search(texto)
    if achado:
        numero = _sem_zeros(achado.group(1))
        if numero and numero != "0":
            return numero
    for padrao in _ROTULOS:
        achado = padrao.search(texto)
        if achado:
            numero = _sem_zeros(achado.group(1))
            if numero and numero != "0":
                return numero
    return ""


def _texto_do_pdf(dados: bytes, paginas: int = 3) -> str:
    try:
        from pypdf import PdfReader

        leitor = PdfReader(io.BytesIO(dados))
        return "\n".join((pagina.extract_text() or "") for pagina in leitor.pages[:paginas])
    except Exception:  # PDF quebrado ou protegido: a tela pede o número
        return ""


def numero_da_nota(dados: bytes, paginas: int = 3) -> str:
    """O número da nota no PDF (bytes); "" se não der para ler."""
    return numero_no_texto(_texto_do_pdf(dados, paginas))


# ---------------------------------------------------------------------------
# Conferência: emitente, valor e data de emissão
# ---------------------------------------------------------------------------

_DINHEIRO = r"(\d{1,3}(?:\.\d{3})*,\d{2}|\d+,\d{2})"
_VALOR_TOTAL = (
    # DANFE: "VALOR TOTAL DA NOTA 842,80".
    re.compile(r"VALOR\s+TOTAL\s+DA\s+NOTA[^\d]{0,40}?" + _DINHEIRO, re.IGNORECASE),
    # NFS-e: "Valor Total da NFS-e", "Valor Líquido da NFS-e", "Valor Total do Serviço".
    re.compile(
        r"VALOR\s+(?:TOTAL|L[ÍI]QUIDO)\s+D[AO]\s+(?:NFS-?e|NOTA(?:\s+FISCAL)?|SERVI[ÇC]OS?)[^\d]{0,40}?" + _DINHEIRO,
        re.IGNORECASE,
    ),
)
_EMISSAO = re.compile(
    r"(?:DATA\s+D[AE]\s+EMISS[ÃA]O|DATA\s+E\s+HORA\s+D[AE]\s+EMISS[ÃA]O|EMITIDA\s+EM)[^\d]{0,40}?(\d{2}/\d{2}/\d{4})",
    re.IGNORECASE,
)
_CNPJ_PRESTADOR = re.compile(
    r"PRESTADOR[\s\S]{0,300}?CNPJ[^\d]{0,20}(\d{2}\.?\d{3}\.?\d{3}/?\d{4}-?\d{2})", re.IGNORECASE
)


def _chave_de_acesso(texto: str) -> str:
    for achado in _CHAVE.finditer(texto or ""):
        chave = re.sub(r"\D", "", achado.group(1))
        if len(chave) == 44 and chave[20:22] in ("55", "65"):
            return chave
    return ""


def dados_no_texto(texto: str) -> dict:
    """O que a conferência usa, lido do texto da nota (cada item pode faltar):

    - ``cnpj``: o do emitente (da chave de acesso, posições 7 a 20; na NFS-e,
      o CNPJ do prestador);
    - ``ano_mes``: (ano, mês) da emissão, da chave de acesso (posições 3 a 6);
    - ``valor``: o valor total da nota (Decimal);
    - ``emissao``: a data de emissão (date).
    """
    from datetime import date
    from decimal import Decimal

    texto = texto or ""
    saida = {"numero": numero_no_texto(texto), "cnpj": "", "ano_mes": None, "valor": None, "emissao": None}
    chave = _chave_de_acesso(texto)
    if chave:
        saida["cnpj"] = chave[6:20]
        ano, mes = 2000 + int(chave[2:4]), int(chave[4:6])
        if 1 <= mes <= 12:
            saida["ano_mes"] = (ano, mes)
    else:
        achado = _CNPJ_PRESTADOR.search(texto)
        if achado:
            saida["cnpj"] = re.sub(r"\D", "", achado.group(1))
    for padrao in _VALOR_TOTAL:
        achado = padrao.search(texto)
        if achado:
            saida["valor"] = Decimal(achado.group(1).replace(".", "").replace(",", "."))
            break
    achado = _EMISSAO.search(texto)
    if achado:
        dia, mes, ano = (int(p) for p in achado.group(1).split("/"))
        try:
            saida["emissao"] = date(ano, mes, dia)
        except ValueError:
            pass
    return saida


def dados_da_nota(dados: bytes, paginas: int = 3) -> dict:
    """`dados_no_texto` do PDF (bytes); tudo vazio se não der para ler."""
    return dados_no_texto(_texto_do_pdf(dados, paginas))
