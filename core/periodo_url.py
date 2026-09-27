"""Datas vindas da URL: "Criar aqui" da Agenda (m135).

Clicar num dia (ou arrastar sobre vários) no calendário abre a tela nova
do módulo com ``?inicio=AAAA-MM-DD&fim=AAAA-MM-DD``. Cada tela lê os dois
com `iniciais_do_periodo` e usa como valor inicial do formulário — nada é
gravado até a pessoa salvar. Datas inválidas ou fora de ordem são ignoradas
em silêncio: a tela abre em branco, como sempre abriu.
"""

from __future__ import annotations

import datetime as dt


def _data(valor) -> dt.date | None:
    try:
        return dt.date.fromisoformat((valor or "")[:10])
    except ValueError:
        return None


def datas_da_url(dados, inicio: str = "inicio", fim: str = "fim") -> tuple[dt.date | None, dt.date | None]:
    """(início, fim) lidos de um QueryDict; fim antes do início vira início."""
    d_inicio = _data(dados.get(inicio))
    if d_inicio is None:
        return None, None
    d_fim = _data(dados.get(fim)) or d_inicio
    if d_fim < d_inicio:
        d_fim = d_inicio
    return d_inicio, d_fim


def iniciais_do_periodo(dados, campo_inicio: str = "data_inicio_evento", campo_fim: str = "data_fim_evento") -> dict:
    """Os `initial` do formulário, ou {} quando a URL não traz período."""
    d_inicio, d_fim = datas_da_url(dados)
    if d_inicio is None:
        return {}
    return {campo_inicio: d_inicio, campo_fim: d_fim}
