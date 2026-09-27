"""Feriados e dias úteis.

Os nacionais (fixos e móveis) são calculados aqui, sem cadastro: não mudam de ano
para ano, e depender de alguém digitá-los todo janeiro seria esquecer algum. Os
estaduais e municipais (e os pontos facultativos da casa) são cadastrados pelo
admin em `core.models.Feriado`, datados ou repetidos todo ano.

Carnaval (segunda e terça) e Corpus Christi são ponto facultativo nacional, não
feriado de lei, mas o expediente público costuma não abrir: contam como não úteis.
Para prazo, errar para mais um dia é o lado seguro.
"""

from __future__ import annotations

import datetime
from functools import lru_cache

#: (mês, dia) dos feriados nacionais fixos.
_NACIONAIS_FIXOS = {
    (1, 1): "Confraternização Universal",
    (4, 21): "Tiradentes",
    (5, 1): "Dia do Trabalho",
    (9, 7): "Independência do Brasil",
    (10, 12): "Nossa Senhora Aparecida",
    (11, 2): "Finados",
    (11, 15): "Proclamação da República",
    (11, 20): "Dia Nacional de Zumbi e da Consciência Negra",
    (12, 25): "Natal",
}


def pascoa(ano: int) -> datetime.date:
    """Domingo de Páscoa (algoritmo de Meeus/Jones/Butcher, calendário gregoriano)."""
    a = ano % 19
    b, c = divmod(ano, 100)
    d, e = divmod(b, 4)
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = divmod(c, 4)
    l_ = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l_) // 451
    mes, dia = divmod(h + l_ - 7 * m + 114, 31)
    return datetime.date(ano, mes, dia + 1)


@lru_cache(maxsize=64)
def feriados_nacionais(ano: int) -> dict[datetime.date, str]:
    """Os feriados nacionais do ano, fixos e móveis."""
    feriados = {datetime.date(ano, mes, dia): nome for (mes, dia), nome in _NACIONAIS_FIXOS.items()}
    domingo = pascoa(ano)
    feriados[domingo - datetime.timedelta(days=48)] = "Carnaval (segunda-feira)"
    feriados[domingo - datetime.timedelta(days=47)] = "Carnaval (terça-feira)"
    feriados[domingo - datetime.timedelta(days=2)] = "Sexta-feira Santa"
    feriados[domingo + datetime.timedelta(days=60)] = "Corpus Christi"
    return feriados


#: O cadastro é pequeno e muda raramente: lido uma vez e guardado por pouco tempo,
#: para a lista (um selo de prazo por servidor) não consultar o banco a cada cartão.
#: `Feriado.save`/`delete` limpam na hora.
_CACHE: dict = {}
_CACHE_SEGUNDOS = 300


def limpar_cache(**_kwargs) -> None:
    _CACHE.clear()


# Cada requisição começa relendo o cadastro: o cache vale dentro dela (os cartões
# da lista), nunca entre processos que não viram a mudança.
from django.core.signals import request_started  # noqa: E402

request_started.connect(limpar_cache, dispatch_uid="core.feriados.limpar_cache")


def _cadastro() -> tuple[list[datetime.date], list[datetime.date]]:
    import time

    from .models import Feriado

    agora = time.monotonic()
    if _CACHE.get("ate", 0) < agora:
        # Só os gerais: feriado municipal (m138) vale para a cidade, não para o
        # expediente da casa nem para os prazos.
        linhas = list(Feriado.objects.filter(municipio__isnull=True).values_list("data", "anual"))
        _CACHE["anuais"] = [data for data, anual in linhas if anual]
        _CACHE["datados"] = [data for data, anual in linhas if not anual]
        _CACHE["ate"] = agora + _CACHE_SEGUNDOS
    return _CACHE["anuais"], _CACHE["datados"]


def _cadastrados(inicio: datetime.date, fim: datetime.date) -> set[datetime.date]:
    """Os feriados do cadastro entre `inicio` e `fim` (os anuais projetados nos anos do intervalo)."""
    anuais, datados = _cadastro()
    datas = {data for data in datados if inicio <= data <= fim}
    for data in anuais:
        for ano in range(inicio.year, fim.year + 1):
            try:
                projetada = data.replace(year=ano)
            except ValueError:  # 29/02 em ano não bissexto
                continue
            if inicio <= projetada <= fim:
                datas.add(projetada)
    return datas


class Calendario:
    """Dias úteis num intervalo, com uma consulta só ao cadastro de feriados."""

    def __init__(self, inicio: datetime.date, fim: datetime.date):
        self.inicio, self.fim = inicio, fim
        self.feriados = set(_cadastrados(inicio, fim))
        for ano in range(inicio.year, fim.year + 1):
            self.feriados.update(feriados_nacionais(ano))

    def eh_dia_util(self, data: datetime.date) -> bool:
        return data.weekday() < 5 and data not in self.feriados


def _calendario_para(data: datetime.date, folga_dias: int) -> Calendario:
    return Calendario(data - datetime.timedelta(days=folga_dias), data + datetime.timedelta(days=folga_dias))


def eh_dia_util(data: datetime.date) -> bool:
    return _calendario_para(data, 0).eh_dia_util(data)


def somar_dias_uteis(data: datetime.date, quantidade: int) -> datetime.date:
    """O `quantidade`-ésimo dia útil depois de `data` (sem contar `data`)."""
    # Folga larga o bastante para qualquer sequência de feriados e fins de semana.
    calendario = _calendario_para(data, quantidade * 3 + 20)
    atual, restantes = data, quantidade
    while restantes > 0:
        atual += datetime.timedelta(days=1)
        if calendario.eh_dia_util(atual):
            restantes -= 1
    return atual


def _projetar(data: datetime.date, inicio: datetime.date, fim: datetime.date, anual: bool):
    """As ocorrências de um feriado cadastrado dentro de [inicio, fim]."""
    if not anual:
        return [data] if inicio <= data <= fim else []
    saida = []
    for ano in range(inicio.year, fim.year + 1):
        try:
            projetada = data.replace(year=ano)
        except ValueError:  # 29/02 em ano não bissexto
            continue
        if inicio <= projetada <= fim:
            saida.append(projetada)
    return saida


def feriados_no_periodo(inicio: datetime.date, fim: datetime.date, municipios=()) -> list[dict]:
    """Os feriados de [inicio, fim] para mostrar: nacionais, os gerais do cadastro
    e os municipais das cidades pedidas (m138).

    Cada item é ``{"data", "nome", "municipio"}`` — ``municipio`` é o nome da
    cidade num feriado municipal, ou "" nos demais. Ordem: data, depois nome.
    """
    from .models import Feriado

    saida = []
    for ano in range(inicio.year, fim.year + 1):
        for data, nome in feriados_nacionais(ano).items():
            if inicio <= data <= fim:
                saida.append({"data": data, "nome": nome, "municipio": ""})
    pks = {int(getattr(m, "pk", m)) for m in municipios or () if m}
    cadastrados = Feriado.objects.filter(municipio__isnull=True)
    if pks:
        from django.db.models import Q

        cadastrados = Feriado.objects.filter(Q(municipio__isnull=True) | Q(municipio_id__in=pks))
    for f in cadastrados.select_related("municipio"):
        for data in _projetar(f.data, inicio, fim, f.anual):
            saida.append({"data": data, "nome": f.nome, "municipio": f.municipio.nome if f.municipio_id else ""})
    saida.sort(key=lambda x: (x["data"], x["municipio"], x["nome"]))
    return saida


def dias_uteis_entre(inicio: datetime.date, fim: datetime.date) -> int:
    """Dias úteis em (inicio, fim]; negativo quando `fim` vem antes de `inicio`."""
    if fim == inicio:
        return 0
    sinal = 1 if fim > inicio else -1
    menor, maior = (inicio, fim) if sinal > 0 else (fim, inicio)
    calendario = Calendario(menor, maior)
    total, atual = 0, menor
    while atual < maior:
        atual += datetime.timedelta(days=1)
        if calendario.eh_dia_util(atual):
            total += 1
    return sinal * total
