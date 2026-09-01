"""Cálculo das diárias de um roteiro.

Portado da Central de Viagens 3, onde as regras abaixo foram estabelecidas
contra **demonstrativos do sistema oficial de solicitação de diárias** — o
documento com os valores que a administração efetivamente paga. Os testes de
caracterização em ``viagens_roteiros/tests_caracterizacao.py`` reproduzem esses
demonstrativos ao centavo, e são a régua desta implementação: mudança aqui que
os quebre é regressão de dinheiro, não ajuste de código.

As três regras que os demonstrativos revelam:

1. **Onde cada período começa e termina.** O período de um destino vai da
   *chegada* nele até a *chegada* no destino seguinte — não de uma saída à
   outra. O primeiro é a exceção: começa na saída da sede, porque a ida já é
   faturada no destino para onde se vai. Assim o tempo de estrada entre dois
   destinos é cobrado na tarifa de onde o servidor estava, em vez de cair no
   trecho de volta (que não carrega complemento) e sumir da conta.

2. **Trecho tarifário** é a sequência de períodos consecutivos da mesma faixa.
   O oficial fatura por trecho, não por destino: três capitais seguidas viram
   um trecho só, com um único complemento sobre a sobra somada; um interior no
   meio quebra a sequência e abre trecho novo.

3. **A escada do resto**, por duração — o calendário não entra::

       resto ≤ 6h        →   0%
       resto > 6h  ≤ 8h  →  15%
       resto > 8h  ≤ 12h →  30%
       resto > 12h       → 100%  (uma diária cheia)

Duas diferenças deliberadas em relação à origem:

- **Sem tabela histórica embutida no código.** Lá, quando não há vigência
  cadastrada, o cálculo cai numa tabela fixa no módulo. Aqui isso levanta
  ``SemTabelaDeDiarias``: valor de diária mora em ``TabelaDiaria`` (é o motivo
  de a tabela existir), e um valor de 2026 congelado no código envelhece em
  silêncio. Falhar de forma visível é melhor que cobrar por um valor que
  ninguém sabe de onde veio.
- **Capitais vêm de uma tabela única** neste módulo, com as 27 UFs. A origem
  cruza a base geográfica com um mapa de reserva e mantém um teste para os dois
  não divergirem; aqui não há duas fontes para divergir.
"""

import unicodedata
from dataclasses import dataclass
from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal

from django.utils import timezone

from .valor_extenso import valor_por_extenso_ptbr

CAPITAIS_POR_UF = {
    "AC": "RIO BRANCO",
    "AL": "MACEIO",
    "AP": "MACAPA",
    "AM": "MANAUS",
    "BA": "SALVADOR",
    "CE": "FORTALEZA",
    "DF": "BRASILIA",
    "ES": "VITORIA",
    "GO": "GOIANIA",
    "MA": "SAO LUIS",
    "MT": "CUIABA",
    "MS": "CAMPO GRANDE",
    "MG": "BELO HORIZONTE",
    "PA": "BELEM",
    "PB": "JOAO PESSOA",
    "PR": "CURITIBA",
    "PE": "RECIFE",
    "PI": "TERESINA",
    "RJ": "RIO DE JANEIRO",
    "RN": "NATAL",
    "RS": "PORTO ALEGRE",
    "RO": "PORTO VELHO",
    "RR": "BOA VISTA",
    "SC": "FLORIANOPOLIS",
    "SP": "SAO PAULO",
    "SE": "ARACAJU",
    "TO": "PALMAS",
}

FAIXA_INTERIOR = "INTERIOR"
FAIXA_CAPITAL = "CAPITAL"
FAIXA_BRASILIA = "BRASILIA"

CENTAVOS = Decimal("0.01")


class SemTabelaDeDiarias(Exception):
    """Não há vigência cadastrada para a data do roteiro."""


class RoteiroIncalculavel(ValueError):
    """Faltam datas, ou elas estão fora de ordem."""


@dataclass(frozen=True)
class Marcador:
    """Um destino do roteiro: quando se sai para ele e quando se chega nele.

    ``chegada`` é opcional porque nem todo chamador conhece as duas pontas.
    Quando falta, o único instante conhecido é tratado como a chegada ao
    destino: é a mesma regra com menos informação, não outra regra.
    """

    saida: datetime
    destino_cidade: str
    destino_uf: str
    chegada: datetime | None = None

    @property
    def instante_de_chegada(self):
        return self.chegada or self.saida


class ResultadoDiarias(dict):
    """Resultado em dict, com a composição por parcela ao lado.

    A composição alimenta ``RoteiroDiariaComponente``: é o que explica, linha a
    linha, de onde saiu o total — e o que permite conferir um pagamento anos
    depois, quando os valores vigentes já forem outros.
    """

    def __init__(self, *args, componentes=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.componentes = componentes or []


def _sem_acentos_maiusculo(valor):
    cru = unicodedata.normalize("NFKD", (valor or "").strip().upper())
    return "".join(c for c in cru if not unicodedata.combining(c))


def mesmo_lugar(cidade_a, uf_a, cidade_b, uf_b):
    return _sem_acentos_maiusculo(cidade_a) == _sem_acentos_maiusculo(cidade_b) and (
        uf_a or ""
    ).strip().upper() == (uf_b or "").strip().upper()


def classificar_faixa(cidade, uf):
    """Faixa tarifária do destino: Brasília, capital ou interior."""
    uf_norm = (uf or "").strip().upper()
    cidade_norm = _sem_acentos_maiusculo(cidade)
    if uf_norm == "DF" and cidade_norm == "BRASILIA":
        return FAIXA_BRASILIA
    if not uf_norm or not cidade_norm:
        return FAIXA_INTERIOR
    if CAPITAIS_POR_UF.get(uf_norm) == cidade_norm:
        return FAIXA_CAPITAL
    return FAIXA_INTERIOR


def _formatar_dt(momento):
    """Data e hora como o operador as digitou, no fuso do sistema.

    Com ``USE_TZ`` ligado, o que vem do banco está em UTC: formatar direto
    faria uma saída às 08:00 aparecer como 11:00 no documento. Datas ingênuas
    (as do cálculo isolado, sem banco) passam intactas.
    """
    if timezone.is_aware(momento):
        momento = timezone.localtime(momento)
    return momento.strftime("%d/%m/%Y"), momento.strftime("%H:%M")


def formatar_valor(valor):
    """Valor no padrão brasileiro: 1.234,56."""
    quantizado = Decimal(valor).quantize(CENTAVOS, rounding=ROUND_HALF_UP)
    return f"{quantizado:,.2f}".replace(",", "_").replace(".", ",").replace("_", ".")


def _tabelas_vigentes(data_referencia):
    """Valores das três faixas vigentes na data, com a identidade da linha.

    Guardar de qual linha da tabela veio cada valor é o que permite auditar um
    pagamento depois: sem isso, mudar a vigência apagaria a explicação do que
    já foi pago.
    """
    from viagens_cadastros.models import TabelaDiaria

    tabelas = {}
    faltando = []
    for faixa, _rotulo in TabelaDiaria.Faixa.choices:
        vigente = TabelaDiaria.vigente_em(faixa, data_referencia)
        if vigente is None:
            faltando.append(faixa)
            continue
        tabelas[faixa] = {
            "24h": vigente.valor_24h,
            "15": vigente.valor_15,
            "30": vigente.valor_30,
            "tabela_id": vigente.pk,
            "vigencia_inicio": vigente.vigencia_inicio,
        }
    if faltando:
        raise SemTabelaDeDiarias(
            "Não há valor de diária vigente em "
            f"{data_referencia:%d/%m/%Y} para: {', '.join(sorted(faltando))}. "
            "Cadastre a vigência antes de calcular."
        )
    return tabelas


def _decompor(inicio, fim):
    """Dias inteiros, percentual do resto, horas do resto e horas totais."""
    segundos = (fim - inicio).total_seconds()
    if segundos <= 0:
        raise RoteiroIncalculavel("Período inválido para cálculo de diárias.")

    dias_inteiros = int(segundos // (24 * 3600))
    resto = segundos - dias_inteiros * 24 * 3600

    if resto <= 6 * 3600:
        percentual = 0
    elif resto <= 8 * 3600:
        percentual = 15
    elif resto <= 12 * 3600:
        percentual = 30
    else:
        percentual = 100

    horas_resto = Decimal(str(resto / 3600)).quantize(CENTAVOS, rounding=ROUND_HALF_UP)
    horas_totais = Decimal(str(segundos / 3600)).quantize(
        CENTAVOS, rounding=ROUND_HALF_UP
    )
    return dias_inteiros, percentual, horas_resto, horas_totais


def _resumo_das_diarias(trechos):
    """Ex.: "2 x 100% + 1 x 30%".

    Resto acima de 12 horas vale uma diária cheia, então entra na contagem de
    100% — senão o resumo diria "0 x 100%" para uma viagem que paga uma inteira.
    """
    inteiras = sum(int(t.get("n_diarias", 0) or 0) for t in trechos)
    inteiras += sum(1 for t in trechos if t.get("percentual_adicional") == 100)
    p15 = sum(1 for t in trechos if t.get("percentual_adicional") == 15)
    p30 = sum(1 for t in trechos if t.get("percentual_adicional") == 30)
    partes = []
    if inteiras:
        partes.append(f"{inteiras} x 100%")
    if p15:
        partes.append(f"{p15} x 15%")
    if p30:
        partes.append(f"{p30} x 30%")
    return " + ".join(partes)


def montar_trechos(
    marcadores,
    chegada_final_sede,
    *,
    quantidade_servidores=1,
    sede_cidade=None,
    sede_uf=None,
):
    """Trechos tarifários do roteiro, já com o dinheiro de cada um."""
    if not marcadores or not chegada_final_sede:
        raise RoteiroIncalculavel("Preencha datas e horas para calcular.")

    # Uma resolução por cálculo: a vigência vale para o roteiro inteiro,
    # decidida pela saída mais antiga. Resolver por trecho abriria a porta para
    # um roteiro que atravessa a virada de vigência cobrar dois valores.
    ordenados = sorted(marcadores, key=lambda m: m.saida)
    tabelas = _tabelas_vigentes(min(m.saida for m in ordenados).date())
    servidores = max(0, int(quantidade_servidores or 0))

    periodos = []
    ultimo_indice = len(ordenados) - 1
    for indice, marcador in enumerate(ordenados):
        inicio = marcador.saida if indice == 0 else marcador.instante_de_chegada
        fim = (
            ordenados[indice + 1].instante_de_chegada
            if indice < ultimo_indice
            else chegada_final_sede
        )
        if fim < inicio:
            raise RoteiroIncalculavel("Preencha datas e horas para calcular.")
        if fim == inicio:
            # Parada instantânea (chegar e seguir viagem no mesmo horário): não
            # há permanência, então não gera diária — mas também não invalida
            # o roteiro.
            continue

        e_o_ultimo = indice == ultimo_indice
        volta_para_sede = bool(
            sede_cidade
            and sede_uf
            and mesmo_lugar(
                marcador.destino_cidade, marcador.destino_uf, sede_cidade, sede_uf
            )
        )
        # Passar pela sede no meio do roteiro não gera diária: o servidor está
        # em casa. Só o último marcador pode ser a volta, e ela prolonga o
        # destino anterior em vez de abrir trecho.
        if not e_o_ultimo and volta_para_sede:
            continue

        faixa = classificar_faixa(marcador.destino_cidade, marcador.destino_uf)
        data_saida, hora_saida = _formatar_dt(inicio)
        periodos.append(
            {
                "tipo": faixa,
                "data_saida": data_saida,
                "hora_saida": hora_saida,
                "valor_diaria": formatar_valor(tabelas[faixa]["24h"]),
                "_inicio": inicio,
                "_fim": fim,
                "_retorno_sede": bool(e_o_ultimo and volta_para_sede),
            }
        )

    if not periodos:
        raise RoteiroIncalculavel("Preencha datas e horas para calcular.")

    trechos = []
    for periodo in periodos:
        anterior = trechos[-1] if trechos else None
        if anterior is not None and anterior["_fim"] == periodo["_inicio"]:
            # A volta para a sede nunca abre trecho: prolonga o último destino.
            # Do contrário o dia da volta seria faturado na tarifa da própria
            # sede — numa sede capital, cobrando capital por estar indo embora.
            if periodo["_retorno_sede"]:
                anterior["_fim"] = periodo["_fim"]
                continue
            if anterior["tipo"] == periodo["tipo"]:
                anterior["_fim"] = periodo["_fim"]
                continue
        trechos.append(periodo)

    for trecho in trechos:
        inicio, fim = trecho["_inicio"], trecho["_fim"]
        dias, percentual, horas_resto, horas_totais = _decompor(inicio, fim)
        tabela = tabelas[trecho["tipo"]]

        if percentual == 15:
            valor_parcial = tabela["15"]
        elif percentual == 30:
            valor_parcial = tabela["30"]
        elif percentual == 100:
            # Resto acima de 12 horas vale uma diária cheia. No demonstrativo
            # oficial ela aparece decomposta em hospedagem 70% + alimentação
            # 30%; somar o valor de 24h dá o mesmo número e evita arredondar
            # duas vezes.
            valor_parcial = tabela["24h"]
        else:
            valor_parcial = Decimal("0.00")

        subtotal = (tabela["24h"] * dias + valor_parcial) * servidores
        data_chegada, hora_chegada = _formatar_dt(fim)
        trecho.update(
            {
                "data_chegada": data_chegada,
                "hora_chegada": hora_chegada,
                "n_diarias": dias,
                "horas_adicionais": float(horas_resto),
                "percentual_adicional": percentual,
                "total_horas_periodo": float(horas_totais),
                "subtotal": formatar_valor(subtotal),
                "subtotal_decimal": subtotal,
                "_tabela": tabela,
            }
        )
        trecho.pop("_retorno_sede", None)

    return trechos


def calcular_diarias(
    marcadores,
    chegada_final_sede,
    *,
    quantidade_servidores=1,
    sede_cidade=None,
    sede_uf=None,
):
    """Total do roteiro, os trechos que o compõem e a composição por parcela."""
    trechos = montar_trechos(
        marcadores,
        chegada_final_sede,
        quantidade_servidores=quantidade_servidores,
        sede_cidade=sede_cidade,
        sede_uf=sede_uf,
    )
    servidores = max(0, int(quantidade_servidores or 0))

    total = sum((t["subtotal_decimal"] for t in trechos), Decimal("0.00"))
    total_horas = sum(float(t.get("total_horas_periodo", 0) or 0) for t in trechos)
    resumo = _resumo_das_diarias(trechos)

    if servidores <= 0:
        por_servidor = Decimal("0.00")
    else:
        por_servidor = (total / Decimal(servidores)).quantize(
            CENTAVOS, rounding=ROUND_HALF_UP
        )

    unitarios = {t["valor_diaria"] for t in trechos if t.get("valor_diaria")}
    if len(unitarios) == 1:
        referencia = next(iter(unitarios))
    elif unitarios:
        referencia = f"{trechos[0]['valor_diaria']} (variável por trecho)"
    else:
        referencia = ""

    componentes = []
    for ordem, trecho in enumerate(trechos, start=1):
        tabela = trecho["_tabela"]
        base = {
            "tabela_diaria_id": tabela["tabela_id"],
            "tabela_vigencia_inicio": tabela["vigencia_inicio"],
            "faixa": trecho["tipo"],
            "periodo_inicio": trecho["_inicio"],
            "periodo_fim": trecho["_fim"],
        }
        if trecho["n_diarias"]:
            componentes.append(
                {
                    **base,
                    "percentual": 100,
                    "quantidade": trecho["n_diarias"],
                    "valor_unitario": tabela["24h"],
                    "subtotal": tabela["24h"] * trecho["n_diarias"] * servidores,
                }
            )
        percentual = trecho["percentual_adicional"]
        if percentual:
            chave = "24h" if percentual == 100 else str(percentual)
            componentes.append(
                {
                    **base,
                    "percentual": percentual,
                    "quantidade": 1,
                    "valor_unitario": tabela[chave],
                    "subtotal": tabela[chave] * servidores,
                }
            )

    publicos = []
    for trecho in trechos:
        linha = {
            chave: valor
            for chave, valor in trecho.items()
            if not chave.startswith("_")
            and chave not in ("subtotal_decimal", "total_horas_periodo")
        }
        publicos.append(linha)

    return ResultadoDiarias(
        {
            "trechos": publicos,
            "totais": {
                "resumo_diarias": resumo,
                "total_horas": round(total_horas, 2),
                "total_valor": formatar_valor(total),
                "total_valor_decimal": total,
                "valor_extenso": valor_por_extenso_ptbr(total),
                "quantidade_servidores": servidores,
                "valor_por_servidor": formatar_valor(por_servidor),
                "valor_por_servidor_decimal": por_servidor,
                "valor_unitario_referencia": referencia,
            },
        },
        componentes=componentes,
    )
