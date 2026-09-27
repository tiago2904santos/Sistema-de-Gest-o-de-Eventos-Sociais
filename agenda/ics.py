"""O feed iCalendar da agenda: o calendário da pessoa fora do sistema.

Colado no Outlook, no Google Agenda ou no celular, o link pessoal
(`agenda:ics`, com o token de `accounts.AssinaturaAgenda`) faz os
compromissos aparecerem sozinhos e acompanharem as mudanças de data — o
programa de calendário volta a buscar o arquivo de tempos em tempos.

O texto segue a RFC 5545 e é montado à mão: são meia dúzia de regras
(linhas terminadas em CRLF, dobradas a 75 octetos, vírgula e ponto e vírgula
escapados) e nenhuma biblioteca precisa entrar no projeto por isso.

O que vai no feed é de propósito menos do que a tela mostra. O arquivo sai
do servidor e fica no calendário da pessoa — e no de quem ela compartilhar
o calendário. Por isso leva só título, período, local, situação e o link de
volta ao sistema; nunca CPF, RG, telefone ou nome de solicitante. Quem quer
o dossiê clica no link e entra com a senha.
"""

from __future__ import annotations

import datetime as dt

from django.utils import timezone

from .fontes import FONTES, eventos_de

#: Janela do feed: o passado recente, para o histórico do calendário não
#: sumir de um dia para o outro, e um ano à frente.
DIAS_PARA_TRAS = 60
DIAS_PARA_FRENTE = 365

PRODID = "-//PCPR//Sistema de Gestão de Eventos Sociais//PT"

_ROTULOS = {f.slug: f.rotulo for f in FONTES}


def _escapar(texto: str) -> str:
    """Texto livre no formato do iCalendar (RFC 5545, 3.3.11)."""
    return (
        str(texto or "")
        .replace("\\", "\\\\")
        .replace(";", "\\;")
        .replace(",", "\\,")
        .replace("\r\n", "\\n")
        .replace("\n", "\\n")
    )


def _dobrar(linha: str) -> list[str]:
    """Linhas de até 75 octetos; a continuação começa com um espaço.

    O corte é por bytes, não por caracteres, e nunca no meio de um caractere
    UTF-8 — "São José" cortado no "ã" vira lixo no Outlook.
    """
    dados = linha.encode("utf-8")
    if len(dados) <= 75:
        return [linha]
    partes, inicio, limite = [], 0, 75
    while inicio < len(dados):
        fim = min(inicio + limite, len(dados))
        while fim < len(dados) and (dados[fim] & 0xC0) == 0x80:
            fim -= 1
        partes.append(("" if inicio == 0 else " ") + dados[inicio:fim].decode("utf-8"))
        inicio, limite = fim, 74
    return partes


def _vevent(evento: dict, *, dominio: str, base_url: str, agora: str) -> list[str]:
    props = evento.get("extendedProps") or {}
    inicio = evento["start"].replace("-", "")
    fim = evento["end"].replace("-", "")
    fonte = _ROTULOS.get(props.get("fonte"), props.get("fonte", ""))
    situacao = props.get("situacao") or ""
    link = base_url + props.get("url", "")
    descricao = " · ".join(p for p in (fonte, situacao) if p)
    if props.get("encerrado"):
        descricao = f"{descricao} (encerrado)"
    linhas = [
        "BEGIN:VEVENT",
        f"UID:{evento['id']}@{dominio}",
        f"DTSTAMP:{agora}",
        f"DTSTART;VALUE=DATE:{inicio}",
        f"DTEND;VALUE=DATE:{fim}",
        f"SUMMARY:{_escapar(evento['title'])}",
        f"DESCRIPTION:{_escapar(descricao + chr(10) + link)}",
        f"URL:{link}",
        f"CATEGORIES:{_escapar(fonte)}",
        "STATUS:CANCELLED" if props.get("encerrado") else "STATUS:CONFIRMED",
    ]
    if props.get("municipio"):
        linhas.append(f"LOCATION:{_escapar(props['municipio'])}")
    if not props.get("encerrado"):
        # Lembrete às 9h da véspera: o dia inteiro começa à meia-noite.
        linhas += [
            "BEGIN:VALARM",
            "ACTION:DISPLAY",
            f"DESCRIPTION:{_escapar(evento['title'])}",
            "TRIGGER:-PT15H",
            "END:VALARM",
        ]
    linhas.append("END:VEVENT")
    return linhas


def calendario(eventos: list[dict], *, nome: str, dominio: str, base_url: str) -> str:
    """O VCALENDAR inteiro, pronto para a resposta (CRLF, linhas dobradas)."""
    agora = timezone.now().strftime("%Y%m%dT%H%M%SZ")
    linhas = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        f"PRODID:{PRODID}",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        f"X-WR-CALNAME:{_escapar(nome)}",
        "X-PUBLISHED-TTL:PT1H",
        "REFRESH-INTERVAL;VALUE=DURATION:PT1H",
    ]
    for evento in eventos:
        linhas += _vevent(evento, dominio=dominio, base_url=base_url, agora=agora)
    linhas.append("END:VCALENDAR")
    saida = []
    for linha in linhas:
        saida += _dobrar(linha)
    return "\r\n".join(saida) + "\r\n"


def feed(usuario, *, slugs=None, so_meus=False, dominio: str, base_url: str, hoje: dt.date | None = None) -> str:
    """O feed da pessoa: as fontes que ela pode ver, na janela do feed.

    ``slugs`` restringe às fontes pedidas (uma fora do acesso é ignorada,
    como em `eventos_de`); ``so_meus`` deixa só o que a agenda marca como
    "meu" — o que a pessoa criou ou onde está escalada.
    """
    hoje = hoje or timezone.localdate()
    inicio = hoje - dt.timedelta(days=DIAS_PARA_TRAS)
    fim = hoje + dt.timedelta(days=DIAS_PARA_FRENTE)
    eventos = eventos_de(usuario, inicio, fim, slugs)
    if so_meus:
        eventos = [e for e in eventos if e["extendedProps"].get("meu")]
    nome = f"Agenda — {usuario.get_full_name() or usuario.get_username()}"
    return calendario(eventos, nome=nome, dominio=dominio, base_url=base_url)
