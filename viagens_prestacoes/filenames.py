import re

_BARRA_RE = re.compile(r"[\\/]+")

_ESPACOS_RE = re.compile(r"\s+")

_NAO_ASCII_RE = re.compile(r"[^A-Za-z0-9 ._-]")

def nome_arquivo_ascii(value: str) -> str:
    """Sanea um nome de arquivo para download, sem acentos nem caracteres
    especiais — alguns sistemas externos (onde o usuário anexa o PDF depois
    de baixado) rejeitam nomes com acentuação. Diferente de
    ``sanitize_drive_name``: aquele mantém acentos porque o Drive aceita.
    """
    import unicodedata

    text = (value or "").strip()
    text = _BARRA_RE.sub("-", text)
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = _NAO_ASCII_RE.sub("", text)
    text = _ESPACOS_RE.sub(" ", text).strip()
    text = text.strip(" .")
    return text or "documento"

def primeiro_nome(servidor) -> str:
    nome = (getattr(servidor, "nome", "") or "").strip()
    if not nome:
        return ""
    return nome.split()[0].capitalize()
