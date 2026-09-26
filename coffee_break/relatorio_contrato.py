"""Relatório do contrato: o que justifica um aditivo, um reforço de empenho
ou as quantidades da próxima licitação.

Consumo por mês e por município, o ritmo médio, a previsão de quando o
saldo acaba (comparada com o fim da vigência), o valor gasto e pago, o
tempo médio entre a nota e o pagamento e o histórico das entregas — tudo com
os dados do próprio sistema (OS não canceladas; o mês é o do evento, ou o
do pedido quando o evento não tem data).
"""

from collections import OrderedDict
from decimal import Decimal

from django.utils import timezone

from . import services
from .models import OcorrenciaEntrega, SolicitacaoCoffeeBreak

MESES_ABREV = ("jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez")


def _mes(dia):
    return f"{MESES_ABREV[dia.month - 1]}/{dia.year}"


def _soma(valores):
    return sum((v for v in valores if v is not None), Decimal("0.00"))


def montar(contrato, hoje=None):
    hoje = hoje or timezone.localdate()
    solicitacoes = list(
        SolicitacaoCoffeeBreak.objects.filter(lote__contrato=contrato, cancelada=False)
        .select_related("lote__contrato", "municipio")
        .order_by("data_inicio_evento", "data_solicitacao", "pk")
    )
    lotes = list(contrato.lotes.com_consumo().order_by("-exercicio", "numero"))

    # Consumo por mês (na ordem do calendário).
    por_mes = OrderedDict()
    for s in sorted(solicitacoes, key=services._data_de_referencia):
        dia = services._data_de_referencia(s)
        chave = (dia.year, dia.month)
        item = por_mes.setdefault(chave, {"mes": _mes(dia), "os": 0, "quantidade": 0, "valor": Decimal("0.00")})
        item["os"] += 1
        item["quantidade"] += s.quantidade_efetiva
        item["valor"] += s.valor or Decimal("0.00")
    maior = max((m["quantidade"] for m in por_mes.values()), default=0)
    for item in por_mes.values():
        item["barra"] = round(item["quantidade"] * 100 / maior) if maior else 0
        item["valor_fmt"] = services.formatar_reais(item["valor"])

    # Consumo por município.
    por_municipio = {}
    for s in solicitacoes:
        nome = s.municipio.nome if s.municipio_id else "Sem município"
        item = por_municipio.setdefault(nome, {"municipio": nome, "os": 0, "quantidade": 0})
        item["os"] += 1
        item["quantidade"] += s.quantidade_efetiva
    municipios = sorted(por_municipio.values(), key=lambda i: (-i["quantidade"], i["municipio"]))

    # Saldo e projeção: os lotes vigentes do contrato.
    ativos = [lote for lote in lotes if lote.ativo]
    capacidade = sum(lote.quantidade_total for lote in ativos)
    restante = sum(lote.restante for lote in ativos)
    ids_ativos = {lote.pk for lote in ativos}
    ritmo = services.ritmo_mensal([s for s in solicitacoes if s.lote_id in ids_ativos], hoje)
    fim = services.fim_da_vigencia(contrato)
    projecao = services.projecao_do_saldo(restante, ritmo, fim, hoje)
    meses_com_consumo = len(por_mes)
    total_quantidade = sum(s.quantidade_efetiva for s in solicitacoes)

    # Valores: comprometido (OS não canceladas), pago (com OB) e o empenho.
    gasto = _soma(s.valor for s in solicitacoes)
    pago = _soma(s.valor for s in solicitacoes if s.data_ordem_bancaria)
    empenhos = [lote.valor_empenho for lote in ativos if lote.valor_empenho is not None]
    empenhado = _soma(empenhos) if empenhos else None
    comprometido_ativos = _soma(s.valor for s in solicitacoes if s.lote_id in ids_ativos)

    # Tempo entre a nota (emissão lida do PDF, senão o ofício) e a ordem bancária.
    prazos = []
    for s in solicitacoes:
        inicio = s.data_emissao_nf or s.data_oficio
        if inicio and s.data_ordem_bancaria and s.data_ordem_bancaria >= inicio:
            prazos.append((s.data_ordem_bancaria - inicio).days)

    entregas = services.resumo_de_entregas(
        OcorrenciaEntrega.objects.filter(solicitacao__lote__contrato=contrato)
    )
    saldo_empenho = empenhado - comprometido_ativos if empenhado is not None else None
    return {
        "reais": {
            "gasto": services.formatar_reais(gasto),
            "pago": services.formatar_reais(pago),
            "empenhado": services.formatar_reais(empenhado),
            "saldo_empenho": services.formatar_reais(saldo_empenho),
        },
        "contrato": contrato,
        "fornecedor": contrato.fornecedor,
        "hoje": hoje,
        "fim_vigencia": fim,
        "lotes": [
            {
                "lote": lote,
                "percentual": round(lote.consumido * 100 / lote.quantidade_total) if lote.quantidade_total else 0,
            }
            for lote in lotes
        ],
        "capacidade": capacidade,
        "restante": restante,
        "consumido": capacidade - restante,
        "por_mes": list(por_mes.values()),
        "por_municipio": municipios,
        "total_os": len(solicitacoes),
        "total_quantidade": total_quantidade,
        "media_geral": round(total_quantidade / meses_com_consumo, 1) if meses_com_consumo else 0,
        "meses_do_ritmo": services.MESES_DO_RITMO,
        "projecao": projecao,
        "gasto": gasto,
        "pago": pago,
        "empenhado": empenhado,
        "saldo_empenho": saldo_empenho,
        "prazo_medio_pagamento": round(sum(prazos) / len(prazos)) if prazos else None,
        "pagamentos_medidos": len(prazos),
        "entregas": entregas,
        "entregas_texto": services.texto_do_resumo(entregas),
    }


def linhas_csv(dados):
    """A planilha do relatório: um bloco por seção, separado por linha vazia."""
    reais = lambda v: "" if v is None else f"{v:.2f}".replace(".", ",")  # noqa: E731
    contrato = dados["contrato"]
    projecao = dados["projecao"]
    yield ["Relatório do contrato", contrato.numero, contrato.fornecedor.razao_social]
    yield ["Gerado em", f"{dados['hoje']:%d/%m/%Y}"]
    yield ["Fim da vigência", f"{dados['fim_vigencia']:%d/%m/%Y}" if dados["fim_vigencia"] else ""]
    yield ["Capacidade dos lotes vigentes", dados["capacidade"]]
    yield ["Saldo restante", dados["restante"]]
    yield [f"Ritmo (média dos últimos {dados['meses_do_ritmo']} meses)", str(projecao["ritmo"]).replace(".", ",")]
    yield ["Saldo acaba em", f"{projecao['acaba_em']:%d/%m/%Y}" if projecao["acaba_em"] else ""]
    yield ["Sobra (falta) no fim da vigência", "" if projecao["sobra"] is None else projecao["sobra"]]
    yield ["Valor gasto", reais(dados["gasto"])]
    yield ["Valor pago", reais(dados["pago"])]
    yield ["Empenhado (lotes vigentes)", reais(dados["empenhado"])]
    yield ["Saldo do empenho", reais(dados["saldo_empenho"])]
    yield ["Prazo médio nota → ordem bancária (dias)", "" if dados["prazo_medio_pagamento"] is None else dados["prazo_medio_pagamento"]]
    yield ["Entregas", dados["entregas_texto"]]
    yield []
    yield ["Mês", "OS", "Quantidade", "Valor"]
    for item in dados["por_mes"]:
        yield [item["mes"], item["os"], item["quantidade"], reais(item["valor"])]
    yield []
    yield ["Município", "OS", "Quantidade"]
    for item in dados["por_municipio"]:
        yield [item["municipio"], item["os"], item["quantidade"]]
    yield []
    yield ["Lote", "Exercício", "Vigente", "Capacidade", "Consumido", "Restante", "Empenho", "Valor do empenho"]
    for item in dados["lotes"]:
        lote = item["lote"]
        yield [
            lote.numero, lote.exercicio, "Sim" if lote.ativo else "Não", lote.quantidade_total,
            lote.consumido, lote.restante, lote.empenho, reais(lote.valor_empenho),
        ]
