"""As quatro situações da lista de ofícios.

Mesma régua de `core/documento_abas.py` da origem, já portada para os roteiros
na Meta 2 (`viagens_roteiros/abas.py`): os recortes são mutuamente exclusivos
e combináveis, e sem nenhum escolhido a lista mostra tudo. O ofício não tem
data própria — a viagem é a do roteiro vinculado, pela saída da sede ou, na
falta dela, pelo primeiro trecho com saída. "Finalizado" é o estado das
prestações de contas do ofício, e entra por subconsulta.
"""

from datetime import datetime, time

from django.db.models import DateTimeField, Exists, F, Min, OuterRef, Q, Subquery
from django.db.models.functions import Coalesce
from django.utils import timezone

from viagens_roteiros.abas import (  # noqa: F401 — mesmos rótulos e chaves da origem
    ABA_ATUAIS,
    ABA_CANCELADOS,
    ABA_FINALIZADOS,
    ABA_FUTURAS,
    ABA_ROTULOS,
    ABAS_VALIDAS,
    normalizar_abas,
)

CANCELADO_Q = Q(cancelado=True)
FINALIZADO_Q = Q(_tem_prestacao=True) & Q(_tem_prestacao_pendente=False)


def anotar_situacao(queryset):
    """Anota a saída da viagem e o estado das prestações de cada ofício.

    `_saida` é a saída da sede do roteiro ou, quando o editor gravou os
    horários só nos trechos, a primeira saída de trecho — a mesma regra de
    `get_primeira_saida_oficio`, expressa no banco para filtrar e ordenar.
    """
    from viagens_prestacoes.models import PrestacaoServidor
    from viagens_roteiros.models import RoteiroTrecho

    primeiro_trecho = (
        RoteiroTrecho.objects.filter(roteiro=OuterRef("roteiro_id"))
        .exclude(saida_dt=None)
        .values("roteiro")
        .annotate(primeira=Min("saida_dt"))
        .values("primeira")[:1]
    )
    prestacoes = PrestacaoServidor.objects.filter(prestacao__oficio=OuterRef("pk"))
    return queryset.annotate(
        _saida=Coalesce(
            F("roteiro__saida_dt"),
            Subquery(primeiro_trecho, output_field=DateTimeField()),
            output_field=DateTimeField(),
        ),
        _tem_prestacao=Exists(prestacoes),
        _tem_prestacao_pendente=Exists(prestacoes.filter(finalizada=False)),
    )


def _fim_de_hoje():
    hoje = timezone.localdate()
    return timezone.make_aware(datetime.combine(hoje, time.max), timezone.get_current_timezone())


def q_da_aba(aba):
    aba = aba if aba in ABAS_VALIDAS else ABA_FUTURAS
    if aba == ABA_CANCELADOS:
        return CANCELADO_Q
    ativo = ~CANCELADO_Q
    if aba == ABA_FINALIZADOS:
        return ativo & FINALIZADO_Q
    pendente = ativo & ~FINALIZADO_Q
    limite = _fim_de_hoje()
    if aba == ABA_FUTURAS:
        return pendente & Q(_saida__gt=limite)
    # Atuais: já começou, ou ainda sem data — o rascunho também precisa de atenção.
    return pendente & (Q(_saida__lte=limite) | Q(_saida__isnull=True))


def q_das_abas(abas):
    filtros = [q_da_aba(aba) for aba in normalizar_abas(abas)]
    if not filtros:
        return None
    combinado = filtros[0]
    for filtro in filtros[1:]:
        combinado |= filtro
    return combinado


def contar_por_aba(queryset):
    return {chave: queryset.filter(q_da_aba(chave)).count() for chave, _ in ABA_ROTULOS}


def opcoes_de_aba(queryset, escolhidas):
    """Opções do filtro de situação, com a contagem ao lado — como na origem."""
    contagem = contar_por_aba(queryset)
    marcadas = set(escolhidas or [])
    return [
        {
            "valor": chave,
            "rotulo": f"{rotulo} ({contagem.get(chave, 0)})",
            "selecionado": chave in marcadas,
        }
        for chave, rotulo in ABA_ROTULOS
    ]
