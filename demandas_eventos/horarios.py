"""Horários escritos à mão na planilha ("14h", "10h00 às 15h00", "9:30").

A coluna "Data do evento e hora (período)" mistura data, horário e recado.
Daqui sai o horário de início e o de fim; o que não for horário fica como
texto, para ninguém perder o recado ("à definir", "manhã").
"""

import re
from datetime import time

_HORA = re.compile(r"\b(\d{1,2})\s*(?:hrs|hs|h|:)\s*(\d{2})?(?:\s*(?:hrs|hs|h|min))?\b", re.I)
# Entre dois horários, estes conectores dizem "de ... até ...".
_ATE = re.compile(r"^\s*(?:às|as|a|até|ate|-|–)\s*$", re.I)


def _hora(horas, minutos):
    h, m = int(horas), int(minutos or 0)
    if h > 23 or m > 59:
        return None
    return time(h, m)


def extrair_horarios(texto):
    """(início, fim, texto que sobrou) de um trecho de texto."""
    texto = (texto or "").strip()
    achados = [(m, _hora(m.group(1), m.group(2))) for m in _HORA.finditer(texto)]
    achados = [(m, h) for m, h in achados if h]
    if not achados:
        return None, None, texto
    inicio = achados[0][1]
    fim = None
    if len(achados) == 2 and _ATE.match(texto[achados[0][0].end():achados[1][0].start()]):
        fim = achados[1][1]
    usados = achados[:2] if fim else achados[:1]
    # O conector entre início e fim ("às", "-") sai junto com os horários:
    # senão "das 9h às 12h" sobrava "das às" e "10h às 15h à definir",
    # "às à definir".
    primeiro, ultimo = usados[0][0], usados[-1][0]
    sobra = texto[: primeiro.start()] + " " + texto[ultimo.end():]
    sobra = re.sub(r"\s+", " ", sobra).strip(" ,;:-–")
    if re.fullmatch(r"(?:às|as|a|até|ate|das|de|e)?", sobra, re.I):
        sobra = ""
    if len(achados) > len(usados) or re.search(r"\d", sobra):
        # Mais horários do que início e fim ("9h30 e 15h30"): o texto inteiro
        # fica, para o recado não se perder.
        sobra = texto
    return inicio, fim, sobra
