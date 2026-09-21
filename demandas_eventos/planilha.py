"""Leitura das colunas de texto livre da planilha: canal e servidor."""

import re
import unicodedata

from .models import CanalSolicitacao


def chave(texto):
    texto = unicodedata.normalize("NFKD", str(texto or "")).encode("ascii", "ignore").decode()
    return re.sub(r"[^A-Z0-9]+", " ", texto.upper()).strip()


def canal_e_protocolo(texto):
    """(canal, protocolo, sobra) do "Foi solicitado via" escrito à mão.

    "E-MAIL E PROTOCOLO Nº 25.166.989-9" vira Protocolo 25.166.989-9;
    "WPP", "Via wwp" e "WHATSAPP" viram WhatsApp. O que não se reconhece
    fica como Outro, e o texto volta em `sobra` para não se perder.
    """
    c = chave(texto)
    if not c:
        return "", "", ""
    digitos = re.search(r"(\d{2})\D?(\d{3})\D?(\d{3})\D?(\d)", str(texto))
    if "PROTOCOLO" in c or "EPROT" in c or digitos:
        numero = (
            f"{digitos.group(1)}.{digitos.group(2)}.{digitos.group(3)}-{digitos.group(4)}"
            if digitos
            else ""
        )
        return CanalSolicitacao.PROTOCOLO, numero, ""
    if "MAIL" in c:
        return CanalSolicitacao.EMAIL, "", ""
    if "WPP" in c or "WHATS" in c or "WWP" in c:
        return CanalSolicitacao.WHATSAPP, "", ""
    if "TELEFONE" in c or "LIGAC" in c:
        return CanalSolicitacao.TELEFONE, "", ""
    if "PRESENCIAL" in c:
        return CanalSolicitacao.PRESENCIAL, "", ""
    return CanalSolicitacao.OUTRO, "", str(texto).strip()


def palestrantes_do_texto(texto, por_nome):
    """Os palestrantes citados no "Servidor", se todos forem reconhecidos.

    `por_nome` é {chave(nome): palestrante}. Se algum nome não casar, nada é
    vinculado e o texto fica como estava — melhor do que vínculo pela metade.
    """
    partes = [chave(x) for x in re.split(r"[/,;]|\be\b", texto or "") if x.strip()]
    achados = [por_nome[c] for c in partes if c in por_nome]
    return achados if partes and len(achados) == len(partes) else []


_EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")


def formatar_telefone(digitos):
    """(41) 99999-0000 ou (41) 3333-0000, a mesma máscara da tela."""
    if len(digitos) == 11:
        return f"({digitos[:2]}) {digitos[2:7]}-{digitos[7:]}"
    if len(digitos) == 10:
        return f"({digitos[:2]}) {digitos[2:6]}-{digitos[6:]}"
    return ""


def telefone_e_email(texto):
    """(telefone, e-mail, sobra) do "Contato" escrito à mão.

    "45 9 9122-1333 / escritorio@x.com" vira (45) 99122-1333 e o e-mail.
    Só vale telefone com DDD (10 ou 11 dígitos). O que não for telefone nem
    e-mail — outro número, um nome — volta em `sobra`.
    """
    texto = str(texto or "").strip()
    emails = _EMAIL.findall(texto)
    resto = _EMAIL.sub(" ", texto)
    telefone = ""
    for trecho in re.split(r"[/;,]|\s{2,}|\bou\b", resto):
        digitos = re.sub(r"\D", "", trecho)
        if digitos.startswith("55") and len(digitos) in (12, 13):
            digitos = digitos[2:]
        if not telefone and formatar_telefone(digitos):
            telefone = formatar_telefone(digitos)
            # Só o número sai; um nome no mesmo trecho ("(Silmara)") fica.
            resto = resto.replace(trecho, re.sub(r"[\d()+\-.\s]{8,}", " ", trecho), 1)
    sobra = re.sub(r"[\s/;,\-]+", " ", resto).strip()
    if len(emails) > 1 or re.search(r"\d{4}", sobra) or re.search(r"[a-zA-Z]{3}", sobra):
        sobra = texto
    else:
        sobra = ""
    return telefone, (emails[0].lower() if emails else ""), sobra
