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


def numero_da_nota(dados: bytes, paginas: int = 3) -> str:
    """O número da nota no PDF (bytes); "" se não der para ler."""
    try:
        from pypdf import PdfReader

        leitor = PdfReader(io.BytesIO(dados))
        texto = "\n".join((pagina.extract_text() or "") for pagina in leitor.pages[:paginas])
    except Exception:  # PDF quebrado ou protegido: a tela pede o número
        return ""
    return numero_no_texto(texto)
