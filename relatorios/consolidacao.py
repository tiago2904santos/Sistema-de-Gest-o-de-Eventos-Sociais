"""O relatório consolidado: os números de todos os módulos numa página só.

Segue o desenho da planilha "PCPR NA COMUNIDADE - ASCOM", que a ASCOM
montava à mão juntando as outras planilhas — uma aba de Palestras (mês,
quantidade, pessoas atendidas), uma de Eventos em geral (data, tipo,
descrição, local) e uma do PCPR na Comunidade (mês, cidade, público, RGs) —
e acrescenta o que os outros módulos do sistema já registram: coffee break,
publicações, atendimento à imprensa e viagens.

Duas regras, as mesmas da agenda:

**A permissão é a de cada módulo, importada de lá.** Uma seção fora do
acesso de quem pede não é calculada nem aparece; as Solicitações passam pelo
``queryset_visivel`` delas (o dossiê é de quem criou).

**Conta o que aconteceu.** Palestras e eventos da ASCOM contam quando
atendidos; solicitações de evento, quando atendidas ou deferidas com a data
já passada; coffee break, viagens e ofícios, quando não cancelados.
"""

from __future__ import annotations

import datetime as dt
from collections import defaultdict

from django.utils import timezone

MESES = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"]
MESES_EXTENSO = [
    "Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho",
    "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro",
]
PRIMEIRO_ANO = 2022
ANO_MINIMO = 2000


# ---------------------------------------------------------------------------
# Período
# ---------------------------------------------------------------------------


class Periodo:
    """Um ano (colunas por mês) ou todos os anos (colunas por ano)."""

    def __init__(self, ano: int | None, hoje: dt.date):
        self.ano = ano
        self.hoje = hoje

    @property
    def rotulo(self):
        return str(self.ano) if self.ano else "Todos os anos"

    def chaves(self, anos_com_dados=()):
        if self.ano:
            return [(self.ano, mes) for mes in range(1, 13)]
        anos = set(anos_com_dados) | {self.hoje.year}
        return sorted(anos)

    def chave(self, data: dt.date):
        return (data.year, data.month) if self.ano else data.year

    def rotulo_da_chave(self, chave):
        if self.ano:
            return f"{MESES[chave[1] - 1]}/{str(chave[0])[2:]}"
        return str(chave)

    def contem(self, data: dt.date | None) -> bool:
        if not data:
            return False
        if self.ano:
            return data.year == self.ano
        # Datas digitadas erradas ("0202", "1905") não viram coluna de ano.
        return ANO_MINIMO <= data.year <= self.hoje.year + 1

    def filtrar(self, queryset, campo):
        if self.ano:
            return queryset.filter(**{f"{campo}__year": self.ano})
        return queryset.filter(
            **{f"{campo}__year__gte": ANO_MINIMO, f"{campo}__year__lte": self.hoje.year + 1}
        )


def anos_disponiveis(hoje):
    return list(range(hoje.year, PRIMEIRO_ANO - 1, -1))


# ---------------------------------------------------------------------------
# Quem vê o quê
# ---------------------------------------------------------------------------


def _pode_palestras(usuario):
    from accounts.modulos import usuario_tem_modulo
    from demandas_eventos.permissions import CODIGO_MODULO

    return usuario_tem_modulo(usuario, CODIGO_MODULO)


def _pode_coffee(usuario):
    from coffee_break.permissions import pode_acessar

    return pode_acessar(usuario)


def _pode_publicacoes(usuario):
    from publicacoes.permissions import pode_acessar

    return pode_acessar(usuario)


def _pode_imprensa(usuario):
    from atendimento_imprensa.permissions import pode_acessar

    return pode_acessar(usuario)


def _pode_viagens(usuario):
    from viagens_cadastros.permissions import pode_acessar

    return pode_acessar(usuario)


# ---------------------------------------------------------------------------
# De onde vêm as linhas
# ---------------------------------------------------------------------------


def _palestras_atendidas(usuario, periodo, evento):
    """Linhas da planilha de palestras atendidas, no mês do evento."""
    from demandas_eventos.models import DemandaEvento, StatusDemanda
    from demandas_eventos.permissions import queryset_visivel

    consulta = queryset_visivel(
        usuario,
        DemandaEvento.objects.filter(evento=evento, status=StatusDemanda.ATENDIDA),
    ).select_related("municipio", "tema")
    if periodo.ano:
        # O "Mês" da planilha é o do evento; sem data de evento, o da solicitação.
        from django.db.models import Q

        consulta = consulta.filter(
            Q(data_inicio_evento__year=periodo.ano)
            | Q(data_inicio_evento__isnull=True, data_solicitacao__year=periodo.ano)
        )
    return list(consulta.distinct())


def _solicitacoes_realizadas(usuario, periodo):
    from django.db.models import Q

    from solicitacoes.models import SolicitacaoEvento, StatusSolicitacao
    from solicitacoes.permissions import queryset_visivel

    consulta = queryset_visivel(usuario, SolicitacaoEvento.objects.all()).filter(
        Q(status=StatusSolicitacao.ATENDIDA)
        | Q(
            status=StatusSolicitacao.DEFERIDA_EM_ANDAMENTO,
            data_inicio_evento__lte=periodo.hoje,
        )
    )
    consulta = periodo.filtrar(consulta, "data_inicio_evento")
    return list(consulta.select_related("municipio", "tipo_evento").order_by("data_inicio_evento", "pk"))


def _eh_pcpr(solicitacao):
    nome = (solicitacao.tipo_evento.nome if solicitacao.tipo_evento_id else "").upper()
    return "COMUNIDADE" in nome


def _municipio(obj):
    if getattr(obj, "municipio_id", None):
        return obj.municipio.nome
    return getattr(obj, "municipio_texto", "") or ""


def _data_br(data):
    return f"{data:%d/%m/%Y}" if data else ""


# ---------------------------------------------------------------------------
# Seções
# ---------------------------------------------------------------------------


def _secao(slug, titulo, icone, colunas, linhas, totais=None, nota="", numericas=()):
    return {
        "slug": slug,
        "titulo": titulo,
        "icone": icone,
        "colunas": colunas,
        "linhas": linhas,
        "totais": totais,
        "nota": nota,
        # Índices das colunas numéricas: alinhadas à direita na tela.
        "numericas": set(numericas),
    }


def _por_mes(periodo, itens, data_de, valores_de, colunas_valor):
    """Soma itens por mês (ou por ano) nas colunas pedidas, com total."""
    baldes = defaultdict(lambda: [0] * len(colunas_valor))
    for item in itens:
        data = data_de(item)
        if not periodo.contem(data):
            continue
        for i, valor in enumerate(valores_de(item)):
            baldes[periodo.chave(data)][i] += valor or 0
    chaves = periodo.chaves({c for c in baldes} if not periodo.ano else ())
    linhas = [[periodo.rotulo_da_chave(c), *baldes.get(c, [0] * len(colunas_valor))] for c in chaves]
    totais = ["Total", *[sum(linha[i + 1] for linha in linhas) for i in range(len(colunas_valor))]]
    return linhas, totais


def secao_palestras(usuario, periodo):
    from demandas_eventos.models import TipoEventoPalestra

    itens = _palestras_atendidas(usuario, periodo, TipoEventoPalestra.PALESTRA)
    linhas, totais = _por_mes(
        periodo,
        itens,
        lambda d: d.mes_referencia,
        lambda d: (1, d.quantidade_publico),
        ["Qtd.", "Pessoas atendidas"],
    )
    return _secao(
        "palestras",
        "Palestras",
        "users",
        ["Mês/ano" if periodo.ano else "Ano", "Qtd.", "Pessoas atendidas"],
        linhas,
        totais,
        "Palestras com status Atendida no módulo Palestras e Eventos, no mês do evento.",
        numericas=(1, 2),
    )


def secao_pcpr(usuario, periodo, solicitacoes, pode_palestras):
    """O PCPR na Comunidade das duas fontes, sem contar a mesma edição duas vezes.

    A edição nasce como solicitação de evento (que traz a quantidade de CIN)
    e costuma estar também na planilha da ASCOM (que traz o público). Quando
    as duas falam do mesmo município no mesmo período, viram uma linha só.
    """
    from demandas_eventos.models import TipoEventoPalestra

    linhas = []
    for s in solicitacoes:
        if not _eh_pcpr(s):
            continue
        linhas.append({
            "data": s.data_inicio_evento,
            "fim": s.data_fim_evento or s.data_inicio_evento,
            "municipio_id": s.municipio_id,
            "cidade": _municipio(s),
            "publico": None,
            "cin": s.quantidade_cin,
            "origem": "Solicitação",
        })
    if pode_palestras:
        for d in _palestras_atendidas(usuario, periodo, TipoEventoPalestra.PCPR_NA_COMUNIDADE):
            data = d.data_inicio_evento
            par = next(
                (
                    linha for linha in linhas
                    if linha["origem"] == "Solicitação"
                    and linha["publico"] is None
                    and d.municipio_id and linha["municipio_id"] == d.municipio_id
                    and data and linha["data"] <= data <= linha["fim"]
                ),
                None,
            )
            if par:
                par["publico"] = d.quantidade_publico
                par["origem"] = "Solicitação + ASCOM"
                continue
            linhas.append({
                "data": d.mes_referencia,
                "fim": d.mes_referencia,
                "municipio_id": d.municipio_id,
                "cidade": _municipio(d),
                "publico": d.quantidade_publico,
                "cin": None,
                "origem": "ASCOM",
            })
    linhas.sort(key=lambda linha: (linha["data"], linha["cidade"]))
    tabela = [
        [
            f"{MESES[linha['data'].month - 1]}/{linha['data']:%y}",
            _data_br(linha["data"]),
            (linha["cidade"] or "Sem município").upper(),
            linha["publico"] if linha["publico"] is not None else "",
            linha["cin"] if linha["cin"] is not None else "",
            linha["origem"],
        ]
        for linha in linhas
    ]
    totais = [
        f"{len(linhas)} edições",
        "",
        "",
        sum(linha["publico"] or 0 for linha in linhas),
        sum(linha["cin"] or 0 for linha in linhas),
        "",
    ]
    return _secao(
        "pcpr",
        "PCPR na Comunidade",
        "landmark",
        ["Mês/ano", "Data", "Cidade", "Público", "Qtd. RGs (CIN)", "Origem"],
        tabela,
        totais,
        "Solicitações de evento do tipo PCPR na Comunidade (atendidas ou deferidas com data já passada), "
        "somadas às linhas atendidas da planilha de palestras. A mesma edição nas duas fontes vira uma linha só.",
        numericas=(3, 4),
    ), linhas


def secao_eventos(usuario, periodo, solicitacoes, pode_palestras):
    from demandas_eventos.models import TipoEventoPalestra

    linhas = []
    for s in solicitacoes:
        if _eh_pcpr(s):
            continue
        descricao = s.local_evento or (s.descricao_complementar or "").strip().split("\n")[0]
        linhas.append((s.data_inicio_evento, str(s.tipo_evento or "Evento"), descricao, _municipio(s), "Solicitação"))
    if pode_palestras:
        for d in _palestras_atendidas(usuario, periodo, TipoEventoPalestra.EVENTO):
            descricao = d.assunto_email or (d.descricao or "").strip().split("\n")[0] or str(d.tema or "")
            linhas.append((d.mes_referencia, "Evento (ASCOM)", descricao, _municipio(d), "ASCOM"))
    linhas.sort(key=lambda linha: (linha[0], linha[1]))
    return _secao(
        "eventos",
        "Eventos em geral",
        "calendar",
        ["Data", "Tipo", "Descrição", "Local", "Origem"],
        [[_data_br(data), tipo, descricao[:160], local, origem] for data, tipo, descricao, local, origem in linhas],
        [f"{len(linhas)} eventos", "", "", "", ""],
        "Solicitações de evento dos demais tipos (inaugurações, solenidades, ações…) e os eventos atendidos da planilha de palestras.",
    ), linhas


def secao_coffee(usuario, periodo):
    from django.db.models import Q

    from coffee_break.models import SolicitacaoCoffeeBreak

    consulta = SolicitacaoCoffeeBreak.objects.all()
    if periodo.ano:
        consulta = consulta.filter(
            Q(data_inicio_evento__year=periodo.ano)
            | Q(data_inicio_evento__isnull=True, data_solicitacao__year=periodo.ano)
        )
    itens = list(consulta.only("data_inicio_evento", "data_solicitacao", "quantidade", "cancelada"))
    linhas, totais = _por_mes(
        periodo,
        itens,
        lambda s: s.data_inicio_evento or s.data_solicitacao,
        lambda s: (0, 0, 1) if s.cancelada else (1, s.quantidade, 0),
        ["Solicitações", "Quantidade servida", "Canceladas"],
    )
    return _secao(
        "coffee",
        "Coffee break",
        "coffee",
        ["Mês/ano" if periodo.ano else "Ano", "Solicitações", "Quantidade servida", "Canceladas"],
        linhas,
        totais,
        "Solicitações de coffee break no mês do evento; a quantidade soma só as não canceladas.",
        numericas=(1, 2, 3),
    )


def secao_publicacoes(usuario, periodo):
    from publicacoes.models import Publicacao, StatusPublicacao

    itens = list(periodo.filtrar(Publicacao.objects.all(), "data").only("data", "status"))
    linhas, totais = _por_mes(
        periodo,
        itens,
        lambda p: p.data,
        lambda p: (1, int(p.status == StatusPublicacao.PUBLICADA)),
        ["Pautas", "Publicadas"],
    )
    return _secao(
        "publicacoes",
        "Publicações",
        "document",
        ["Mês/ano" if periodo.ano else "Ano", "Pautas", "Publicadas"],
        linhas,
        totais,
        "Pautas pela data da pauta.",
        numericas=(1, 2),
    )


def secao_imprensa(usuario, periodo):
    from atendimento_imprensa.models import Atendimento, SituacaoAtendimento

    itens = list(periodo.filtrar(Atendimento.objects.all(), "data").only("data", "situacao"))
    linhas, totais = _por_mes(
        periodo,
        itens,
        lambda a: a.data,
        lambda a: (1, int(a.situacao == SituacaoAtendimento.ATENDIDO)),
        ["Pedidos", "Atendidos"],
    )
    return _secao(
        "imprensa",
        "Atendimento à imprensa",
        "send",
        ["Mês/ano" if periodo.ano else "Ano", "Pedidos", "Atendidos"],
        linhas,
        totais,
        "Pedidos de jornalistas pela data do pedido.",
        numericas=(1, 2),
    )


def secao_viagens(usuario, periodo):
    from viagens_oficios.models import Oficio
    from viagens_viagem.models import Viagem

    viagens = list(
        periodo.filtrar(Viagem.objects.filter(cancelado=False), "data_inicio").only("data_inicio")
    )
    oficios = list(
        periodo.filtrar(Oficio.objects.filter(cancelado=False), "data_criacao").only("data_criacao")
    )
    itens = [("v", v.data_inicio) for v in viagens] + [("o", o.data_criacao) for o in oficios]
    linhas, totais = _por_mes(
        periodo,
        itens,
        lambda item: item[1],
        lambda item: (int(item[0] == "v"), int(item[0] == "o")),
        ["Viagens", "Ofícios"],
    )
    return _secao(
        "viagens",
        "Viagens",
        "truck",
        ["Mês/ano" if periodo.ano else "Ano", "Viagens", "Ofícios"],
        linhas,
        totais,
        "Viagens pela data de saída e ofícios pela data de criação, sem os cancelados.",
        numericas=(1, 2),
    )


# ---------------------------------------------------------------------------
# O relatório inteiro
# ---------------------------------------------------------------------------


def _coluna(secao, indice):
    """Os valores de uma coluna numérica das linhas de uma seção mensal."""
    return [linha[indice] for linha in secao["linhas"]]


def relatorio(usuario, ano=None, hoje=None):
    hoje = hoje or timezone.localdate()
    periodo = Periodo(ano, hoje)
    pode_palestras = _pode_palestras(usuario)
    solicitacoes = _solicitacoes_realizadas(usuario, periodo)

    secoes = []
    kpis = []
    # Linhas do quadro mês a mês: (módulo, contagem por chave do período).
    visao = []

    def por_chave(datas):
        contagem = defaultdict(int)
        for data in datas:
            if periodo.contem(data):
                contagem[periodo.chave(data)] += 1
        return contagem

    if pode_palestras:
        palestras = secao_palestras(usuario, periodo)
        secoes.append(palestras)
        kpis.append({"titulo": "Palestras", "valor": palestras["totais"][1], "icone": "users",
                     "detalhe": f"{palestras['totais'][2]} pessoas atendidas"})
        if periodo.ano:
            visao.append(("Palestras", dict(zip(periodo.chaves(), _coluna(palestras, 1)))))
        else:
            visao.append(("Palestras", {int(l[0]): l[1] for l in palestras["linhas"]}))

    pcpr, linhas_pcpr = secao_pcpr(usuario, periodo, solicitacoes, pode_palestras)
    secoes.append(pcpr)
    kpis.append({"titulo": "PCPR na Comunidade", "valor": len(linhas_pcpr), "icone": "landmark",
                 "detalhe": f"{pcpr['totais'][4]} CIN emitidas"})
    visao.append(("PCPR na Comunidade", por_chave(linha["data"] for linha in linhas_pcpr)))

    eventos, linhas_eventos = secao_eventos(usuario, periodo, solicitacoes, pode_palestras)
    secoes.append(eventos)
    kpis.append({"titulo": "Eventos em geral", "valor": len(linhas_eventos), "icone": "calendar", "detalhe": "inaugurações, solenidades e ações"})
    visao.append(("Eventos em geral", por_chave(linha[0] for linha in linhas_eventos)))

    mensais = [
        (_pode_coffee, secao_coffee, "Coffee break", 1, "coffee", 2, "unidades servidas"),
        (_pode_publicacoes, secao_publicacoes, "Publicações", 2, "document", 1, "pautas"),
        (_pode_imprensa, secao_imprensa, "Atendimento à imprensa", 1, "send", 2, "atendidos"),
        (_pode_viagens, secao_viagens, "Viagens", 1, "truck", 2, "ofícios"),
    ]
    for pode, montar, rotulo, coluna_kpi, icone, coluna_detalhe, detalhe in mensais:
        if not pode(usuario):
            continue
        secao = montar(usuario, periodo)
        secoes.append(secao)
        kpis.append({
            "titulo": rotulo,
            "valor": secao["totais"][coluna_kpi],
            "icone": icone,
            "detalhe": f"{secao['totais'][coluna_detalhe]} {detalhe}",
        })
        if periodo.ano:
            visao.append((rotulo, dict(zip(periodo.chaves(), _coluna(secao, coluna_kpi)))))
        else:
            visao.append((rotulo, {int(l[0]): l[coluna_kpi] for l in secao["linhas"]}))

    # O quadro geral: um módulo por linha, um mês (ou ano) por coluna.
    anos = set()
    for _, contagem in visao:
        anos |= {c for c in contagem if isinstance(c, int)}
    chaves = periodo.chaves(anos)
    quadro = _secao(
        "geral",
        "Visão geral por mês" if periodo.ano else "Visão geral por ano",
        "chart",
        ["Módulo", *[periodo.rotulo_da_chave(c) for c in chaves], "Total"],
        [
            [rotulo, *[contagem.get(c, 0) for c in chaves], sum(contagem.get(c, 0) for c in chaves)]
            for rotulo, contagem in visao
        ],
        nota="Palestras, PCPR e eventos contam o que aconteceu; coffee break, solicitações não canceladas; "
        "publicações, pautas publicadas; imprensa, pedidos recebidos; viagens, viagens não canceladas.",
        numericas=range(1, len(chaves) + 2),
    )
    return {
        "periodo": periodo,
        "kpis": kpis,
        "quadro": quadro,
        "secoes": secoes,
    }
