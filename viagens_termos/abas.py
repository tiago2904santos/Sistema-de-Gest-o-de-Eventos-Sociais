"""As quatro situações da lista de termos.

Mesma régua dos roteiros e dos ofícios (`core/documento_abas.py` da origem):
combináveis, e sem nenhuma marcada a lista mostra tudo. A data do termo é a
data inicial do evento ou, quando ele herda do ofício, a saída do roteiro.
"Finalizado" é o das prestações do ofício vinculado; termo avulso nunca
finaliza.
"""

from django.db.models import DateField, Exists, F, OuterRef, Q
from django.db.models.functions import Coalesce, TruncDate
from django.utils import timezone

from viagens_roteiros.abas import ABA_ATUAIS, ABA_CANCELADOS, ABA_FINALIZADOS, ABA_FUTURAS, ABA_ROTULOS, ABAS_VALIDAS, normalizar_abas  # noqa: F401

CANCELADO_Q = Q(cancelado=True)
FINALIZADO_Q = Q(_tem_prestacao=True) & Q(_tem_prestacao_pendente=False)


def anotar_situacao(queryset):
    from viagens_prestacoes.models import PrestacaoServidor

    prestacoes = PrestacaoServidor.objects.filter(prestacao__oficio=OuterRef("oficio_id"))
    return queryset.annotate(
        _inicio=Coalesce(F("data_evento_inicio"), TruncDate("oficio__roteiro__saida_dt"), output_field=DateField()),
        _tem_prestacao=Exists(prestacoes),
        _tem_prestacao_pendente=Exists(prestacoes.filter(finalizada=False)),
    )


def q_da_aba(aba):
    aba = aba if aba in ABAS_VALIDAS else ABA_FUTURAS
    if aba == ABA_CANCELADOS:
        return CANCELADO_Q
    ativo = ~CANCELADO_Q
    if aba == ABA_FINALIZADOS:
        return ativo & FINALIZADO_Q
    pendente = ativo & ~FINALIZADO_Q
    hoje = timezone.localdate()
    if aba == ABA_FUTURAS:
        return pendente & Q(_inicio__gt=hoje)
    return pendente & (Q(_inicio__lte=hoje) | Q(_inicio__isnull=True))


def q_das_abas(abas):
    filtros = [q_da_aba(aba) for aba in normalizar_abas(abas)]
    if not filtros:
        return None
    combinado = filtros[0]
    for filtro in filtros[1:]:
        combinado |= filtro
    return combinado


def opcoes_de_aba(queryset, escolhidas):
    marcadas = set(escolhidas or [])
    return [
        {"valor": chave, "rotulo": f"{rotulo} ({queryset.filter(q_da_aba(chave)).count()})", "selecionado": chave in marcadas}
        for chave, rotulo in ABA_ROTULOS
    ]
