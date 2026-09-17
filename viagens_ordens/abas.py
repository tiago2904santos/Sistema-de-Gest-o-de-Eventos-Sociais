"""As quatro situações da lista de ordens de serviço.

Mesma régua dos roteiros, ofícios e termos (`core/documento_abas.py` da
origem): recortes combináveis, e sem nenhum escolhido a lista mostra tudo. A
data é a inicial do evento da própria OS; sem data ela ainda "vai acontecer".
"Finalizado" é o estado das prestações dos ofícios (não cancelados) vinculados
à OS, por subconsulta — OS sem ofício nunca finaliza.
"""

from django.db.models import Exists, F, OuterRef, Q
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
    from viagens_prestacoes.models import PrestacaoServidor

    prestacoes = PrestacaoServidor.objects.filter(
        prestacao__oficio__ordens_servico=OuterRef("pk"),
        prestacao__oficio__cancelado=False,
    )
    return queryset.annotate(
        _inicio=F("data_evento_inicio"),
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
        # Sem data ainda não aconteceu: o rascunho fica entre os que vão acontecer.
        return pendente & (Q(_inicio__gt=hoje) | Q(_inicio__isnull=True))
    return pendente & Q(_inicio__lte=hoje)


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
