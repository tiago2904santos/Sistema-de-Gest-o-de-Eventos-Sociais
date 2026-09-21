"""Histórico das palestras e eventos da ASCOM.

O status é uma coluna do formulário, como na planilha; o que o sistema
acrescenta é o rastro: quem mudou o quê, e quando.
"""

from .models import HistoricoDemanda


def registrar_historico(
    demanda,
    usuario,
    acao,
    descricao="",
    status_anterior="",
    status_novo="",
):
    return HistoricoDemanda.objects.create(
        demanda=demanda,
        usuario=usuario,
        acao=acao,
        descricao=(descricao or "").strip(),
        status_anterior=status_anterior,
        status_novo=status_novo,
    )
