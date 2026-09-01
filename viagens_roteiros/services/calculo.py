"""Liga o roteiro gravado ao motor de cálculo das diárias.

O motor (``diarias.py``) é puro: recebe marcadores e devolve números. Aqui é
onde um ``Roteiro`` do banco vira marcadores e onde o resultado volta para o
banco — inclusive a composição parcela a parcela, que é o que explica o total.
"""

from django.db import transaction

from .diarias import Marcador, RoteiroIncalculavel, calcular_diarias


def marcadores_do_roteiro(roteiro):
    """Um marcador por trecho de ida com destino e horários preenchidos.

    O trecho de retorno não vira marcador: a chegada dele fecha o período do
    último destino, em vez de abrir um período faturado na tarifa da sede.
    """
    marcadores = []
    trechos = roteiro.trechos.select_related("destino_municipio__estado").order_by(
        "ordem", "pk"
    )
    for trecho in trechos:
        if trecho.sentido != trecho.Sentido.IDA:
            continue
        if not (trecho.saida_dt and trecho.destino_municipio_id):
            continue
        marcadores.append(
            Marcador(
                saida=trecho.saida_dt,
                chegada=trecho.chegada_dt,
                destino_cidade=trecho.destino_municipio.nome,
                destino_uf=trecho.destino_municipio.estado.sigla,
            )
        )
    return marcadores


def chegada_final(roteiro):
    """Quando o servidor volta para a sede."""
    if roteiro.retorno_chegada_dt:
        return roteiro.retorno_chegada_dt
    ultimo = roteiro.trechos.order_by("-ordem", "-pk").first()
    return ultimo.chegada_dt if ultimo else None


def previa_diarias(form, formset):
    """Roda o motor sobre o formulário como está, sem gravar nada.

    É a prévia da tela de montagem: o operador vê o valor enquanto preenche,
    como no editor de referência. Linhas com erro ou marcadas para remoção
    ficam de fora — a prévia mostra o que seria gravado, não o que está
    quebrado.
    """
    form.is_valid()
    formset.is_valid()
    dados_form = getattr(form, "cleaned_data", None) or {}
    sede = dados_form.get("origem_municipio")
    quantidade = dados_form.get("quantidade_servidores") or 1

    marcadores = []
    fim = None
    for form_trecho in formset.forms:
        if form_trecho.errors:
            continue
        dados = getattr(form_trecho, "cleaned_data", None) or {}
        if dados.get("DELETE"):
            continue
        saida = form_trecho.instance.saida_dt
        chegada = form_trecho.instance.chegada_dt
        destino = dados.get("destino_municipio")
        if chegada and (fim is None or chegada > fim):
            fim = chegada
        if not (saida and destino):
            continue
        marcadores.append(
            Marcador(
                saida=saida,
                chegada=chegada,
                destino_cidade=destino.nome,
                destino_uf=destino.estado.sigla,
            )
        )

    if not marcadores or not fim:
        raise RoteiroIncalculavel(
            "Preencha destino, saída e chegada dos trechos para ver a prévia."
        )
    return calcular_diarias(
        marcadores,
        fim,
        quantidade_servidores=quantidade,
        sede_cidade=sede.nome if sede else "",
        sede_uf=sede.estado.sigla if sede else "",
    )


@transaction.atomic
def recalcular_diarias(roteiro):
    """Recalcula o roteiro e grava o resultado com a composição que o explica.

    As parcelas anteriores são apagadas e regravadas: elas descrevem **este**
    cálculo. Editar uma parcela existente reescreveria a história de um valor
    que já pode ter sido pago — por isso o caminho é substituir o conjunto
    inteiro, dentro de uma transação.
    """
    marcadores = marcadores_do_roteiro(roteiro)
    fim = chegada_final(roteiro)
    if not marcadores or not fim:
        raise RoteiroIncalculavel(
            "Informe os trechos com destino, saída e chegada antes de calcular."
        )

    resultado = calcular_diarias(
        marcadores,
        fim,
        quantidade_servidores=roteiro.quantidade_servidores,
        sede_cidade=roteiro.sede_cidade,
        sede_uf=roteiro.sede_uf,
    )
    totais = resultado["totais"]

    roteiro.resumo_diarias = totais["resumo_diarias"]
    roteiro.valor_diarias = totais["total_valor_decimal"]
    roteiro.valor_diarias_extenso = totais["valor_extenso"]
    roteiro.save(
        update_fields=[
            "resumo_diarias",
            "valor_diarias",
            "valor_diarias_extenso",
            "atualizado_em",
        ]
    )

    roteiro.componentes_diarias.all().delete()
    componentes = [
        roteiro.componentes_diarias.model(
            roteiro=roteiro,
            ordem=ordem,
            tabela_diaria_id=dados["tabela_diaria_id"],
            tabela_vigencia_inicio=dados["tabela_vigencia_inicio"],
            faixa=dados["faixa"],
            percentual=dados["percentual"],
            quantidade=dados["quantidade"],
            valor_unitario=dados["valor_unitario"],
            subtotal=dados["subtotal"],
            periodo_inicio=dados["periodo_inicio"],
            periodo_fim=dados["periodo_fim"],
        )
        for ordem, dados in enumerate(resultado.componentes, start=1)
    ]
    roteiro.componentes_diarias.bulk_create(componentes)
    return resultado
