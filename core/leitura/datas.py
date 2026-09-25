"""Datas e horários escritos em português, como chegam num e-mail.

"dia 15/10 às 14h", "de 20 a 22 de novembro, das 9h às 12h", "próxima terça
pela manhã", "amanhã 10:00". O que é relativo ("amanhã", "próxima terça") e
a data sem ano ("12/03") se resolvem contra a data do e-mail, nunca contra
hoje: um pedido lido semanas depois continua apontando para o dia certo.

Sem ano vale a regra dos 60 dias do importador da ASCOM: se a data ficaria
mais de 60 dias antes da referência, é do ano seguinte.

Tudo aqui é puro: recebe texto e devolve o que achou, com o trecho de onde
saiu (para a tela mostrar ao conferir). Não há banco nem rede.
"""

from __future__ import annotations

import bisect
import re
import unicodedata
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from email.utils import parsedate_to_datetime

__all__ = [
    "DataAchada",
    "Horario",
    "Prazo",
    "Quando",
    "data_hora_de_cabecalho",
    "datas_do_texto",
    "dobrar",
    "horarios_do_texto",
    "prazo_do_texto",
    "quando_do_evento",
    "turno_do_texto",
]

MESES = {
    "janeiro": 1, "fevereiro": 2, "marco": 3, "abril": 4, "maio": 5, "junho": 6,
    "julho": 7, "agosto": 8, "setembro": 9, "outubro": 10, "novembro": 11, "dezembro": 12,
}
_MESES_ABREVIADOS = {
    "jan": 1, "fev": 2, "mar": 3, "abr": 4, "mai": 5, "jun": 6,
    "jul": 7, "ago": 8, "set": 9, "out": 10, "nov": 11, "dez": 12,
}
# Só para cabeçalhos ("Sent: Thursday, September 24, 2026 2:32 PM").
_MESES_INGLES = {
    "january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6,
    "july": 7, "august": 8, "september": 9, "october": 10, "november": 11, "december": 12,
    "feb": 2, "apr": 4, "aug": 8, "sep": 9, "sept": 9, "oct": 10, "dec": 12,
}
DIAS_DA_SEMANA = {
    "segunda": 0, "terca": 1, "quarta": 2, "quinta": 3, "sexta": 4, "sabado": 5, "domingo": 6,
}
_TURNOS = {"manha": "manhã", "matutino": "manhã", "tarde": "tarde", "vespertino": "tarde",
           "noite": "noite", "noturno": "noite"}
# Sem ano: mais de 60 dias antes da referência é do ano seguinte.
_JANELA_ANO_SEGUINTE = timedelta(days=60)
# Período maior que isso não é "de X a Y" de um evento.
_PERIODO_MAXIMO = timedelta(days=62)


# ---------------------------------------------------------------------------
# Texto dobrado: minúsculas e sem acento, posição a posição
# ---------------------------------------------------------------------------

_TROCAS = {
    "º": "o", "°": "o", "ª": "a", "–": "-", "—": "-", "‐": "-", "‑": "-", "−": "-",
    " ": " ", " ": " ", " ": " ", "’": "'", "‘": "'", "´": "'", "`": "'",
    "“": '"', "”": '"',
}
_DOBRA_CACHE: dict[str, str] = {}


def dobrar(texto: str) -> str:
    """Minúsculas e sem acento, com o mesmo comprimento do original.

    Cada caractere vira exatamente um. Assim a posição achada no texto
    dobrado aponta para o mesmo trecho no original, que é o que a tela mostra
    ("de onde saiu esta data").
    """
    texto = texto or ""
    if texto.isascii():
        return texto.lower()
    saida = []
    for caractere in texto:
        trocado = _DOBRA_CACHE.get(caractere)
        if trocado is None:
            trocado = _TROCAS.get(caractere)
            if trocado is None:
                base = unicodedata.normalize("NFKD", caractere)
                base = "".join(c for c in base if not unicodedata.combining(c)) or caractere
                trocado = base.lower()[:1] or caractere
            _DOBRA_CACHE[caractere] = trocado
        saida.append(trocado)
    return "".join(saida)


def _referencia(referencia) -> date:
    """A data de referência (a do e-mail), aceitando date ou datetime."""
    if isinstance(referencia, datetime):
        if referencia.tzinfo is not None:
            try:
                from django.utils import timezone

                return timezone.localtime(referencia).date()
            except Exception:  # sem Django configurado: vale o fuso do próprio valor
                return referencia.date()
        return referencia.date()
    if isinstance(referencia, date):
        return referencia
    raise TypeError("A referência precisa ser uma data.")


def _com_ano(dia: int, mes: int, ano: str | None, referencia: date) -> date | None:
    try:
        if ano:
            numero = int(ano)
            return date(numero + 2000 if numero < 100 else numero, mes, dia)
        candidata = date(referencia.year, mes, dia)
    except ValueError:
        return None
    if candidata < referencia - _JANELA_ANO_SEGUINTE:
        try:
            return date(referencia.year + 1, mes, dia)
        except ValueError:
            return None
    return candidata


# ---------------------------------------------------------------------------
# Datas
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class DataAchada:
    """Uma data (ou período) citada no texto.

    `tipo`: "data", "periodo" ("de 20 a 22"), "lista" ("20, 21 e 22"),
    "relativa" ("amanhã") ou "dia_semana" ("próxima terça"). `dias` são os
    dias do evento (todos, no período). `trecho` é o texto original.
    """

    inicio: date
    fim: date | None
    dias: tuple[date, ...]
    tipo: str
    trecho: str
    inicio_pos: int
    fim_pos: int

    @property
    def absoluta(self) -> bool:
        return self.tipo in ("data", "periodo", "lista")


_ANTES_NUMERO = r"(?<![\d.,/])"
_MES_COMPLETO = "|".join(sorted(MESES, key=len, reverse=True))
_MES_ABREVIADO = "|".join(_MESES_ABREVIADOS)
# "de outubro", "/out", "-out.", " outubro"; abreviação exige separador.
_MES = (
    r"(?:\s*(?:de\s+|[/.-]\s*)?(?P<mes>" + _MES_COMPLETO + r")\b"
    r"|\s*(?:de\s+|[/.-]\s*)(?P<abrev>" + _MES_ABREVIADO + r")\b\.?)"
)
_ANO_POR_EXTENSO = r"(?:\s*(?:,|de|/|-)?\s*(?P<ano>20\d{2})(?!\d))?"
_CONECTORES = r"(?P<meio>(?:\s*(?:,|\be\b|\ba\b|\bate\b|-)\s*\d{1,2}o?){1,10})"

_R_LISTA_EXTENSO = re.compile(_ANTES_NUMERO + r"(?P<dia>\d{1,2})o?" + _CONECTORES + _MES + _ANO_POR_EXTENSO)
_R_LISTA_NUMERO = re.compile(
    _ANTES_NUMERO + r"(?P<dia>\d{1,2})" + _CONECTORES
    + r"\s*/\s*(?P<num>\d{1,2})(?:\s*/\s*(?P<ano>\d{2}|20\d{2}))?(?![\d/])"
)
_R_EXTENSO = re.compile(_ANTES_NUMERO + r"(?P<dia>\d{1,2})o?" + _MES + _ANO_POR_EXTENSO)
_R_BARRA = re.compile(
    _ANTES_NUMERO + r"(?P<dia>\d{1,2})/(?P<num>\d{1,2})(?:/(?P<ano>\d{2}|20\d{2}))?(?![\d/])"
)
# "05.01.27", "15.10": dois dígitos de cada lado (não confunde com valor ou versão).
_R_PONTO = re.compile(
    _ANTES_NUMERO + r"(?P<dia>\d{2})\.(?P<num>\d{2})(?:\.(?P<ano>\d{2}|20\d{2}))?(?!\.?\d)(?!\s*h)"
)
_R_HIFEN = re.compile(r"(?<![\d.,/-])(?P<dia>\d{1,2})-(?P<num>\d{1,2})-(?P<ano>20\d{2})(?!\d)")
_R_RELATIVA = re.compile(r"\b(depois de amanha|amanha|hoje)\b(?!\s+em\s+dia)")
_SEMANA = "|".join(DIAS_DA_SEMANA)
_R_DIA_SEMANA = re.compile(
    r"\b(?:(?P<prefixo>proxim[oa]|nest[ea]|est[ea]|n[ao]|dia)\s+)?"
    r"(?P<dia>" + _SEMANA + r")(?P<feira>\s*-?\s*feira)?\b"
    r"(?P<sufixo>\s*,?\s*(?:d?a\s+)?(?:que\s+vem|semana\s+que\s+vem|proxima\s+semana)\b)?"
)
_R_SEMANA_QUE_VEM_ANTES = re.compile(r"(?:semana\s+que\s+vem|proxima\s+semana)\s*,?\s*(?:n[ao]\s+)?$")
# "na segunda etapa", "a quinta edição": ordinal, não dia da semana.
_R_ORDINAL_DEPOIS = re.compile(
    r"^\s+(?:etapa|edicao|via|turma|fase|parte|vez|serie|chamada|opcao|quinzena|metade|"
    r"reuniao|rodada|sessao|aula|semana|colocad[oa]|lugar|ano)\b"
)
_R_FAIXA_SEMANA = re.compile(r"^\s*(?:-?\s*feira)?\s*(?:a|ate|e|-)\s*(?:a\s+)?(?:" + _SEMANA + r")")
_R_RECORRENTE_ANTES = re.compile(r"\b(?:toda|todas\s+as|todo|todos\s+os|de|entre)\s+$")
# Número de documento, não data: "Ofício nº 05/10", "Lei 13.709/18".
_R_DOCUMENTO_ANTES = re.compile(
    r"\b(?:oficio|of\.|memorando|memo\.?|lei|decreto|portaria|resolucao|processo|protocolo|"
    r"n\.?o|numero|sei|edital|contrato|pregao|rg|cpf)\s*(?:n\.?o\.?|no\.?)?\s*[:.-]?\s*$"
)


def _mes_do(m) -> int:
    grupos = m.groupdict()
    if grupos.get("mes"):
        return MESES[grupos["mes"]]
    if grupos.get("abrev"):
        return _MESES_ABREVIADOS[grupos["abrev"]]
    return int(grupos["num"])


class _Ocupados:
    """Trechos do texto já usados, sem sobreposição, com consulta em log n.

    Texto grande (300 mil caracteres) pode ter milhares de números: comparar
    cada achado com todos os anteriores ficaria quadrático.
    """

    def __init__(self, trechos=()):
        self.inicios: list[int] = []
        self.fins: list[int] = []
        for inicio, fim in sorted(trechos):
            if self.fins and inicio < self.fins[-1]:
                self.fins[-1] = max(self.fins[-1], fim)
            else:
                self.inicios.append(inicio)
                self.fins.append(fim)

    def livre(self, inicio: int, fim: int) -> bool:
        i = bisect.bisect_right(self.inicios, inicio)
        if i > 0 and self.fins[i - 1] > inicio:
            return False
        return not (i < len(self.inicios) and self.inicios[i] < fim)

    def marcar(self, inicio: int, fim: int) -> None:
        i = bisect.bisect_right(self.inicios, inicio)
        self.inicios.insert(i, inicio)
        self.fins.insert(i, fim)


def _todos_os_dias(inicio: date, fim: date) -> tuple[date, ...]:
    return tuple(inicio + timedelta(days=n) for n in range((fim - inicio).days + 1))


def _eh_documento(dobrado: str, inicio: int) -> bool:
    return bool(_R_DOCUMENTO_ANTES.search(dobrado[max(0, inicio - 25):inicio]))


def _listas(texto, dobrado, referencia, ocupados):
    achadas = []
    for regex in (_R_LISTA_EXTENSO, _R_LISTA_NUMERO):
        for m in regex.finditer(dobrado):
            if not ocupados.livre(m.start(), m.end()) or _eh_documento(dobrado, m.start()):
                continue
            meio = m.group("meio")
            numeros = [int(m.group("dia"))] + [int(n) for n in re.findall(r"\d{1,2}", meio)]
            conectores = set(re.findall(r",|\be\b|\ba\b|\bate\b|-", meio))
            if any(b <= a for a, b in zip(numeros, numeros[1:])) and len(numeros) > 2:
                continue
            mes = _mes_do(m)
            ano = m.group("ano")
            entre = bool(re.search(r"\bentre\s+(?:os\s+)?(?:dias\s+)?$", dobrado[max(0, m.start() - 20):m.start()]))
            periodo = len(numeros) == 2 and (conectores & {"a", "ate", "-"} or (entre and "e" in conectores))
            if periodo:
                fim = _com_ano(numeros[1], mes, ano, referencia)
                inicio = _com_ano(numeros[0], mes, ano, referencia)
                if fim and numeros[0] > numeros[1]:
                    # "30 a 2/11": o primeiro dia é do mês anterior.
                    anterior = fim.replace(day=1) - timedelta(days=1)
                    inicio = _com_ano(numeros[0], anterior.month, str(anterior.year), referencia)
                if not inicio or not fim or fim < inicio or fim - inicio > _PERIODO_MAXIMO:
                    continue
                dias = _todos_os_dias(inicio, fim)
                tipo = "periodo"
            else:
                dias = tuple(d for d in (_com_ano(n, mes, ano, referencia) for n in numeros) if d)
                if len(dias) != len(numeros):
                    continue
                inicio, fim, tipo = min(dias), max(dias), "lista"
            achadas.append(DataAchada(inicio, fim, dias, tipo, texto[m.start():m.end()], m.start(), m.end()))
            ocupados.marcar(m.start(), m.end())
    return achadas


def _unicas(texto, dobrado, referencia, ocupados):
    achadas = []
    for regex in (_R_EXTENSO, _R_BARRA, _R_PONTO, _R_HIFEN):
        for m in regex.finditer(dobrado):
            if not ocupados.livre(m.start(), m.end()) or _eh_documento(dobrado, m.start()):
                continue
            dia = _com_ano(int(m.group("dia")), _mes_do(m), m.group("ano"), referencia)
            if not dia:
                continue
            achadas.append(DataAchada(dia, None, (dia,), "data", texto[m.start():m.end()], m.start(), m.end()))
            ocupados.marcar(m.start(), m.end())
    return achadas


def _juntar_periodos(texto, dobrado, achadas):
    """"de 30/10 a 02/11", "entre 20/11 e 22/11", "20/11, 21/11 e 22/11"."""
    achadas = sorted(achadas, key=lambda a: a.inicio_pos)
    resultado = []
    for atual in achadas:
        anterior = resultado[-1] if resultado else None
        if anterior is None or atual.tipo != "data" or anterior.tipo not in ("data", "lista"):
            resultado.append(atual)
            continue
        vao = dobrado[anterior.fim_pos:atual.inicio_pos]
        conector = re.fullmatch(r"\s*(,|e|a|ate|-)\s*(?:o\s+)?(?:dia\s+)?", vao)
        ultimo = anterior.fim or anterior.inicio
        if not conector or atual.inicio <= ultimo or atual.inicio - anterior.inicio > _PERIODO_MAXIMO:
            resultado.append(atual)
            continue
        ligacao = conector.group(1)
        entre = bool(re.search(r"\bentre\s+(?:os\s+)?(?:dias\s+)?$", dobrado[max(0, anterior.inicio_pos - 20):anterior.inicio_pos]))
        trecho = texto[anterior.inicio_pos:atual.fim_pos]
        if anterior.tipo == "data" and (ligacao in ("a", "ate", "-") or (ligacao == "e" and entre)):
            dias = _todos_os_dias(anterior.inicio, atual.inicio)
            juntada = DataAchada(anterior.inicio, atual.inicio, dias, "periodo", trecho, anterior.inicio_pos, atual.fim_pos)
        elif ligacao in (",", "e"):
            dias = anterior.dias + (atual.inicio,)
            juntada = DataAchada(anterior.inicio, atual.inicio, dias, "lista", trecho, anterior.inicio_pos, atual.fim_pos)
        else:
            resultado.append(atual)
            continue
        resultado[-1] = juntada
    return resultado


def _relativas(texto, dobrado, referencia, ocupados):
    deslocamento = {"hoje": 0, "amanha": 1, "depois de amanha": 2}
    achadas = []
    for m in _R_RELATIVA.finditer(dobrado):
        if not ocupados.livre(m.start(), m.end()):
            continue
        dia = referencia + timedelta(days=deslocamento[m.group(1)])
        achadas.append(DataAchada(dia, None, (dia,), "relativa", texto[m.start():m.end()], m.start(), m.end()))
    return achadas


def _primeiro_a_partir(itens, posicoes, inicio):
    """O primeiro item cuja posição é >= inicio (posicoes em ordem)."""
    i = bisect.bisect_left(posicoes, inicio)
    return itens[i] if i < len(itens) else None


def _dias_da_semana(texto, dobrado, referencia, absolutas):
    achadas = []
    descartar_proximo = False
    absolutas = sorted(absolutas, key=lambda a: a.inicio_pos)
    inicios = [a.inicio_pos for a in absolutas]
    por_fim = sorted(absolutas, key=lambda a: a.fim_pos)
    fins = [a.fim_pos for a in por_fim]
    for m in _R_DIA_SEMANA.finditer(dobrado):
        if descartar_proximo:
            descartar_proximo = False
            continue
        antes = dobrado[max(0, m.start() - 40):m.start()]
        depois = dobrado[m.end():m.end() + 40]
        # "de segunda a sexta", "segunda e quarta": expediente, não uma data.
        if _R_FAIXA_SEMANA.match(dobrado[m.end():m.end() + 30]):
            descartar_proximo = True
            continue
        if _R_RECORRENTE_ANTES.search(antes):
            continue
        prefixo = m.group("prefixo") or ""
        semana_que_vem = bool(m.group("sufixo")) or bool(_R_SEMANA_QUE_VEM_ANTES.search(antes))
        explicito = bool(m.group("feira")) or prefixo.startswith(("proxim", "nest", "est")) or semana_que_vem
        if not explicito:
            if prefixo not in ("na", "no", "dia") or _R_ORDINAL_DEPOIS.match(depois):
                continue
        # Dia da semana colado a uma data absoluta é só rótulo dela:
        # "quinta-feira, 24 de setembro", "25/09 (sexta)".
        depois_dela = _primeiro_a_partir(absolutas, inicios, m.end())
        antes_dela = por_fim[bisect.bisect_right(fins, m.start()) - 1] if bisect.bisect_right(fins, m.start()) else None
        if depois_dela and depois_dela.inicio_pos - m.end() <= 10 and re.fullmatch(
            r"[\s,(\-]*(?:dia\s+)?", dobrado[m.end():depois_dela.inicio_pos]
        ):
            continue
        if antes_dela and m.start() - antes_dela.fim_pos <= 4 and re.fullmatch(
            r"[\s,(\-]*", dobrado[antes_dela.fim_pos:m.start()]
        ):
            continue
        alvo = DIAS_DA_SEMANA[m.group("dia")]
        if semana_que_vem:
            segunda_seguinte = referencia + timedelta(days=7 - referencia.weekday())
            dia = segunda_seguinte + timedelta(days=alvo)
        else:
            dia = referencia + timedelta(days=(alvo - referencia.weekday()) % 7 or 7)
        achadas.append(DataAchada(dia, None, (dia,), "dia_semana", texto[m.start():m.end()], m.start(), m.end()))
    return achadas


def datas_do_texto(texto: str, referencia) -> list[DataAchada]:
    """Todas as datas citadas no texto, na ordem em que aparecem.

    `referencia` é a data do e-mail (date ou datetime): resolve "amanhã",
    "próxima terça" e o ano das datas sem ano. Números de documento
    ("Ofício nº 05/10", "Lei 13.709/18") não viram data, e o dia da semana
    colado a uma data ("quinta-feira, 24 de setembro") é só rótulo dela.
    """
    texto = texto or ""
    referencia = _referencia(referencia)
    dobrado = dobrar(texto)
    ocupados = _Ocupados()
    absolutas = _listas(texto, dobrado, referencia, ocupados)
    absolutas += _unicas(texto, dobrado, referencia, ocupados)
    absolutas = _juntar_periodos(texto, dobrado, absolutas)
    ocupados = _Ocupados((a.inicio_pos, a.fim_pos) for a in absolutas)
    relativas = _relativas(texto, dobrado, referencia, ocupados)
    semana = _dias_da_semana(texto, dobrado, referencia, absolutas)
    return sorted(absolutas + relativas + semana, key=lambda a: a.inicio_pos)


# ---------------------------------------------------------------------------
# Horários
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Horario:
    """Um horário ("14h") ou uma faixa ("das 9h às 12h") citada no texto."""

    inicio: time
    fim: time | None
    trecho: str
    inicio_pos: int
    fim_pos: int


_R_HORA_MARCADA = re.compile(
    r"(?<![\d/.,:])(?P<h>\d{1,2})\s*(?:"
    r"(?P<unidade>h|hs|hrs|hr|horas?)(?:\s*(?P<m1>\d{2})(?:\s*(?:min|mins|minutos?))?)?"
    r"|:\s?(?P<m2>\d{2})(?:\s*(?:h|hs|hrs|horas?)\b)?"
    r")(?![\d/])(?!\w)"
)
_PREFIXO_HORA = r"(?:as|das|pelas|a\s+partir\s+das|por\s+volta\s+das|ate\s+as|inicio\s+as)"
_R_HORA_NUA = re.compile(
    r"\b(?P<prefixo>" + _PREFIXO_HORA + r")\s+(?P<h>\d{1,2})(?![\d/]|[.,:]\d)"
    r"(?=\s*(?:$|[,.;:)\n]|e\s|a\s|as\s|ate\s|-|da\s+(?:manha|tarde|noite)|horas?\b|h\b))"
)
_R_MEIO_DIA = re.compile(
    r"(?:\b(?:ao|as|a|das|do|ate\s+o|ate|partir\s+do)\s+)?\bmei[oa]\s*(?P<hifen>-)?\s*(?P<qual>dia|noite)\b(?P<meia>\s+e\s+meia)?"
)
_R_DURACAO_ANTES = re.compile(
    r"\b(?:por|durante|duracao(?:\s+de)?|carga\s+horaria(?:\s+de)?|cerca\s+de|aproximadamente|aprox\.?|"
    r"mais\s+de|menos\s+de|em|com|de\s+ate)\s*$"
)
_R_DURACAO_DEPOIS = re.compile(r"^\s*(?:de\s+)?(?:duracao|cada|por\s+dia|semanais|diarias|de\s+palestra|de\s+atividade)")
_R_CONTEXTO_HORA = re.compile(r"\b(?:" + _PREFIXO_HORA + r"|horario|hora|inicio|comeca|comecando|comecar)\s*:?\s*$")
# "2h da tarde" é 14h; o turno entra no trecho.
_R_TURNO_DEPOIS = re.compile(r"^\s*(?:da|de)\s+(manha|tarde|noite)\b")


@dataclass
class _Ficha:
    hora: time
    inicio: int
    fim: int
    prefixo: str


def _com_turno(h: int, dobrado: str, fim: int) -> tuple[int, int]:
    turno = _R_TURNO_DEPOIS.match(dobrado[fim:fim + 20])
    if not turno:
        return h, fim
    if turno.group(1) in ("tarde", "noite") and h < 12:
        h += 12
    return h, fim + turno.end()


def _fichas_de_hora(dobrado: str) -> list[_Ficha]:
    fichas: list[_Ficha] = []
    ocupados = _Ocupados()
    for m in _R_MEIO_DIA.finditer(dobrado):
        tem_prefixo = bool(re.match(r"\s*(?:ao|as|a|das|do|ate|partir)\b", dobrado[m.start():m.start("qual")]))
        if not m.group("hifen") and not tem_prefixo:
            continue  # "meio dia" solto pode ser "meio período"
        hora = time(12 if m.group("qual") == "dia" else 0, 30 if m.group("meia") else 0)
        fichas.append(_Ficha(hora, m.start(), m.end(), "ao" if tem_prefixo else ""))
        ocupados.marcar(m.start(), m.end())
    for m in _R_HORA_MARCADA.finditer(dobrado):
        h, minutos = int(m.group("h")), int(m.group("m1") or m.group("m2") or 0)
        if h > 23 or minutos > 59:
            continue
        antes = dobrado[max(0, m.start() - 30):m.start()]
        depois = dobrado[m.end():m.end() + 30]
        if _R_DURACAO_ANTES.search(antes) or _R_DURACAO_DEPOIS.match(depois):
            continue
        unidade = m.group("unidade") or ""
        if unidade.startswith("hora") and not m.group("m1"):
            # "10 horas" só é horário com "às"/"das" antes ou "da manhã" depois;
            # sem isso é duração ("palestra de 2 horas").
            if not (_R_CONTEXTO_HORA.search(antes) or _R_TURNO_DEPOIS.match(depois)):
                continue
        h, fim = _com_turno(h, dobrado, m.end())
        fichas.append(_Ficha(time(h, minutos), m.start(), fim, ""))
        ocupados.marcar(m.start(), m.end())
    for m in _R_HORA_NUA.finditer(dobrado):
        if not ocupados.livre(m.start("h"), m.end("h")):
            continue
        h = int(m.group("h"))
        if h > 23 or re.match(r"^\s*(?:de\s+)?(?:" + _MES_COMPLETO + r")\b", dobrado[m.end():m.end() + 30]):
            continue
        h, fim = _com_turno(h, dobrado, m.end())
        fichas.append(_Ficha(time(h, 0), m.start(), fim, re.sub(r"\s+", " ", m.group("prefixo"))))
    return sorted(fichas, key=lambda f: f.inicio)


def horarios_do_texto(texto: str) -> list[Horario]:
    """Os horários citados no texto, com as faixas ("das 9h às 12h") juntas.

    Reconhece "14h", "14h30", "14:30", "às 10 horas", "às 10", "meio-dia",
    "2h da tarde". Duração não é horário ("palestra de 2 horas", "por 1h").
    """
    texto = texto or ""
    dobrado = dobrar(texto)
    fichas = _fichas_de_hora(dobrado)
    horarios: list[Horario] = []
    i = 0
    while i < len(fichas):
        atual = fichas[i]
        seguinte = fichas[i + 1] if i + 1 < len(fichas) else None
        if seguinte is not None:
            vao = dobrado[atual.fim:seguinte.inicio]
            conector = vao.strip()
            entre = re.search(r"\bentre\s+$", dobrado[max(0, atual.inicio - 10):atual.inicio])
            faixa = (
                re.fullmatch(r"(?:as|a|ate|ate as|-|ao)?", conector) is not None
                and (conector or seguinte.prefixo in ("as", "ate as", "ao"))
            ) or (conector == "e" and entre)
            if faixa and len(vao) <= 12 and seguinte.hora > atual.hora:
                inicio = atual.inicio
                antes = dobrado[max(0, inicio - 4):inicio]
                if re.search(r"\b(?:das|de)\s$", antes):
                    inicio -= len(re.search(r"(?:das|de)\s$", antes).group(0))
                horarios.append(Horario(atual.hora, seguinte.hora, texto[inicio:seguinte.fim], inicio, seguinte.fim))
                i += 2
                continue
        horarios.append(Horario(atual.hora, None, texto[atual.inicio:atual.fim], atual.inicio, atual.fim))
        i += 1
    return horarios


_R_TURNO = re.compile(r"\b(manha|tarde|noite|matutino|vespertino|noturno)\b")
_R_TURNO_FALSO_ANTES = re.compile(r"\b(?:boa|bom|uma\s+boa|otima|otimo|mais)\s+$")


def turno_do_texto(texto: str) -> str:
    """"manhã", "tarde" ou "noite" citado como período do evento ("" se não houver).

    Cumprimento não conta ("Boa tarde"), nem "mais tarde".
    """
    dobrado = dobrar(texto or "")
    achados = []
    for m in _R_TURNO.finditer(dobrado):
        if _R_TURNO_FALSO_ANTES.search(dobrado[max(0, m.start() - 12):m.start()]):
            continue
        if re.match(r"\s+demais\b", dobrado[m.end():m.end() + 8]):
            continue
        achados.append(_TURNOS[m.group(1)])
    return achados[0] if achados else ""


# ---------------------------------------------------------------------------
# A data do evento
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Quando:
    """Quando é o evento, pelo que o texto diz.

    `fim` é None num dia só. `turno` fica só como texto ("manhã"): não vira
    horário. `confianca`: "A" com âncora ("no dia", "será realizada"),
    "M" sem âncora (preencher e destacar para conferência).
    """

    inicio: date
    fim: date | None
    dias: tuple[date, ...]
    hora_inicio: time | None
    hora_fim: time | None
    turno: str
    trecho: str
    confianca: str


_R_ANCORA_DATA_ANTES = re.compile(
    r"(?:\b(?:dia|dias|data|datas|quando|periodo|previst[oa]\s+para|agendad[oa]\s+para|marcad[oa]\s+para)\b"
    r"[^.\n]{0,14}|\b(?:em|no|nos|para\s+o|para\s+os)\s+)$"
)
_R_EVENTO_NA_FRASE = re.compile(
    r"\b(?:realiz|sera\b|serao\b|ocorre|acontec|evento|palestra|encontro|reuniao|agend|program|previst|"
    r"solenidade|cerimonia|inaugura|formatura|curso|treinamento|capacita|acao\b|mutirao|feira|visita|"
    r"apresenta|comemora|coffee|lanche|entrega|atendimento)"
)
_R_NEGATIVO_ANTES = re.compile(
    r"\b(?:prazo|ate|enviad[oa]|recebid[oa]|datad[oa]|nascid[oa]|nascimento|validade|vencimento|vence|"
    r"emitid[oa]|emissao|publicad[oa]|desde|oficio|lei|decreto|portaria|escreveu)\b[^.\n]{0,20}$"
)


_JANELA_DA_FRASE = 400


def _frase(dobrado: str, inicio: int, fim: int) -> tuple[int, int]:
    """Início e fim da frase (ou linha) que contém o trecho.

    Olha no máximo 400 caracteres para cada lado: frase maior que isso não
    ajuda a decidir nada, e texto grande não fica quadrático.
    """
    base = max(0, inicio - _JANELA_DA_FRASE)
    comeco = base
    for m in re.finditer(r"[\n!?;]|\.\s", dobrado[base:inicio]):
        comeco = base + m.end()
    final = re.search(r"[\n!?;]|\.\s|\.$", dobrado[fim:fim + _JANELA_DA_FRASE])
    return comeco, (fim + final.start() if final else min(len(dobrado), fim + _JANELA_DA_FRASE))


def _pontos_da_data(item: DataAchada, dobrado: str, referencia: date) -> tuple[int, bool]:
    base = {"periodo": 2, "lista": 2, "data": 1, "relativa": 0, "dia_semana": 0}[item.tipo]
    comeco, final = _frase(dobrado, item.inicio_pos, item.fim_pos)
    antes = dobrado[max(comeco, item.inicio_pos - 40):item.inicio_pos]
    frase = dobrado[comeco:final]
    ancorada = bool(_R_ANCORA_DATA_ANTES.search(antes)) or bool(re.match(r"\s*data\b", frase))
    evento = bool(_R_EVENTO_NA_FRASE.search(frase))
    negativo = bool(_R_NEGATIVO_ANTES.search(antes))
    pontos = base + (3 if ancorada else 0) + (2 if evento else 0) - (5 if negativo else 0)
    if (item.fim or item.inicio) < referencia:
        pontos -= 3
    return pontos, (ancorada or evento) and not negativo


def quando_do_evento(texto: str, referencia) -> Quando | None:
    """A data (ou período) do evento, com horário e turno, se o texto disser.

    Entre várias datas, vale a que tem âncora ("no dia", "data do evento",
    "será realizada") e verbo de evento na mesma frase; prazo ("até o dia"),
    data de documento e data passada perdem. O horário vem da mesma frase da
    data; se não houver, de um horário ancorado no resto do texto ("às 14h").
    """
    texto = texto or ""
    referencia = _referencia(referencia)
    itens = datas_do_texto(texto, referencia)
    if not itens:
        return None
    dobrado = dobrar(texto)
    avaliados = [(item, *_pontos_da_data(item, dobrado, referencia)) for item in itens]
    melhor, pontos, ancorada = max(avaliados, key=lambda a: (a[1], -a[0].inicio_pos))
    comeco, final = _frase(dobrado, melhor.inicio_pos, melhor.fim_pos)
    spans_datas = [(i.inicio_pos, i.fim_pos) for i in itens]
    ocupados = _Ocupados(spans_datas)
    horarios = [h for h in horarios_do_texto(texto) if ocupados.livre(h.inicio_pos, h.fim_pos)]
    na_frase = [h for h in horarios if comeco <= h.inicio_pos < final]
    escolhido = None
    if na_frase:
        escolhido = next((h for h in na_frase if h.fim), na_frase[0])
    else:
        for h in horarios:
            antes = dobrado[max(0, h.inicio_pos - 25):h.inicio_pos]
            if _R_NEGATIVO_ANTES.search(antes) or re.match(r"ate\b", dobrado[h.inicio_pos:h.inicio_pos + 4]):
                continue
            if h.fim or _R_CONTEXTO_HORA.search(antes) or re.match(r"(?:as|das|pelas)\b", dobrado[h.inicio_pos:]):
                escolhido = h
                break
    turno = turno_do_texto(texto[comeco:final]) or turno_do_texto(texto)
    fim = melhor.fim if melhor.fim and melhor.fim != melhor.inicio else None
    trecho = texto[comeco:final].strip() or melhor.trecho
    return Quando(
        inicio=melhor.inicio,
        fim=fim,
        dias=melhor.dias,
        hora_inicio=escolhido.inicio if escolhido else None,
        hora_fim=escolhido.fim if escolhido else None,
        turno=turno,
        trecho=trecho[:300],
        confianca="A" if ancorada and pontos >= 3 else "M",
    )


# ---------------------------------------------------------------------------
# Prazo ("até às 17h de hoje")
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Prazo:
    """Prazo pedido no texto (imprensa: "até às 17h de hoje", "deadline amanhã")."""

    data: date
    hora: time | None
    trecho: str


_R_PRAZO = re.compile(
    r"\b(?:prazo|deadline|fechamento|vai\s+ao\s+ar|retorno\s+ate|resposta\s+ate|responder\s+ate|"
    r"ate\s+as|ate\s+o\s+dia|ate\s+dia|ate\s+hoje|ate\s+amanha|ate\s+o\s+(?:final|fim)\s+d[oa])\b"
)


def prazo_do_texto(texto: str, referencia) -> Prazo | None:
    """O prazo pedido ("até às 17h de hoje", "prazo: 30/09"), se houver.

    Só hora, sem dia: vale o dia da referência. Prazo antes da referência
    não serve (é outra coisa).
    """
    texto = texto or ""
    referencia = _referencia(referencia)
    dobrado = dobrar(texto)
    datas = datas_do_texto(texto, referencia)
    posicoes_datas = [d.inicio_pos for d in datas]
    horarios = horarios_do_texto(texto)
    posicoes_horas = [h.inicio_pos for h in horarios]
    for m in _R_PRAZO.finditer(dobrado):
        _comeco, final = _frase(dobrado, m.start(), m.end())
        janela_fim = min(final, m.end() + 80)
        dia = _primeiro_a_partir(datas, posicoes_datas, m.start())
        dia = dia if dia and dia.inicio_pos < janela_fim else None
        hora = _primeiro_a_partir(horarios, posicoes_horas, m.start())
        hora = hora if hora and hora.inicio_pos < janela_fim else None
        if dia is None and hora is None:
            continue
        data = dia.inicio if dia else referencia
        if data < referencia:
            continue
        fim_trecho = max([m.end()] + [x.fim_pos for x in (dia, hora) if x])
        return Prazo(data, hora.fim or hora.inicio if hora else None, texto[m.start():fim_trecho].strip())
    return None


# ---------------------------------------------------------------------------
# Data e hora de cabeçalho ("Enviado em:", "Sent:", Gmail)
# ---------------------------------------------------------------------------

_MESES_CABECALHO = {**_MESES_INGLES, **_MESES_ABREVIADOS, **MESES}
_MES_CABECALHO = "|".join(sorted(_MESES_CABECALHO, key=len, reverse=True))
_HORA_CABECALHO = r"(?:\D{0,8}?(?P<h>\d{1,2}):(?P<mi>\d{2})(?::\d{2})?\s*(?P<ampm>[ap]\.?\s?m\.?)?)?"
_R_CABECALHO = [
    # "24 de setembro de 2026 14:32", "qui., 24 de set. de 2026 às 14:32", "24 September 2026"
    re.compile(r"(?P<d>\d{1,2})\s*(?:de\s+)?(?P<mes>" + _MES_CABECALHO + r")\.?,?\s*(?:de\s+)?(?P<a>\d{4})" + _HORA_CABECALHO),
    # "September 24, 2026 2:32 PM", "Sep 24, 2026 at 2:32 PM"
    re.compile(r"(?P<mes>" + _MES_CABECALHO + r")\.?\s+(?P<d>\d{1,2}),?\s+(?P<a>\d{4})" + _HORA_CABECALHO),
    # "24/09/2026 14:32", "24/09/26, 14:32"
    re.compile(r"(?P<d>\d{1,2})/(?P<num>\d{1,2})/(?P<a>\d{4}|\d{2})\b" + _HORA_CABECALHO),
]


def data_hora_de_cabecalho(valor: str) -> datetime | None:
    """A data e hora de um cabeçalho de e-mail em texto (sem fuso).

    Aceita o formato do protocolo ("Thu, 24 Sep 2026 14:32:00 -0300", aí com
    fuso), o do Outlook em português ("quinta-feira, 24 de setembro de 2026
    14:32") e em inglês ("Thursday, September 24, 2026 2:32 PM", com AM/PM),
    e o do Gmail ("qui., 24 de set. de 2026 às 14:32").
    """
    valor = (valor or "").strip()
    if not valor:
        return None
    if re.match(r"^(?:[A-Za-z]{3},\s*)?\d{1,2}\s+[A-Za-z]{3}\s+\d{4}\s+\d{1,2}:\d{2}", valor):
        try:
            return parsedate_to_datetime(valor)
        except (TypeError, ValueError, IndexError):
            pass
    dobrado = dobrar(valor)
    for regex in _R_CABECALHO:
        m = regex.search(dobrado)
        if not m:
            continue
        grupos = m.groupdict()
        mes = _MESES_CABECALHO[grupos["mes"]] if grupos.get("mes") else int(grupos["num"])
        ano = int(grupos["a"])
        ano += 2000 if ano < 100 else 0
        hora, minuto = int(grupos["h"] or 0), int(grupos["mi"] or 0)
        ampm = (grupos.get("ampm") or "").replace(".", "").replace(" ", "")
        if ampm == "pm" and hora < 12:
            hora += 12
        elif ampm == "am" and hora == 12:
            hora = 0
        try:
            return datetime(ano, mes, int(grupos["d"]), hora, minuto)
        except ValueError:
            continue
    return None
