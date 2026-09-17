"""As quatro situações da lista de planos de trabalho.

Mesma régua dos roteiros, ofícios e termos: recortes combináveis, e sem
nenhum marcado a lista mostra tudo. A data do plano é a inicial do evento
(ou, no plano de vários eventos, a do primeiro evento gravado). "Finalizado"
é o das prestações dos ofícios (não cancelados) da viagem do plano; plano
avulso nunca finaliza. Sem data o plano ainda não aconteceu: fica entre os
que vão acontecer.
"""

from django.db.models import DateField, Exists, F, Min, OuterRef, Q, Subquery
from django.db.models.functions import Coalesce
from django.utils import timezone

from viagens_roteiros.abas import ABA_ATUAIS, ABA_CANCELADOS, ABA_FINALIZADOS, ABA_FUTURAS, ABA_ROTULOS, ABAS_VALIDAS, normalizar_abas  # noqa: F401

CANCELADO_Q = Q(cancelado=True)
FINALIZADO_Q = Q(_tem_prestacao=True) & Q(_tem_prestacao_pendente=False)


def anotar_situacao(queryset):
    from viagens_prestacoes.models import PrestacaoServidor

    from .models import EventoPlano

    prestacoes = PrestacaoServidor.objects.filter(
        prestacao__oficio__viagem=OuterRef("viagem_id"), prestacao__oficio__cancelado=False,
    )
    primeiro_evento = (
        EventoPlano.objects.filter(plano=OuterRef("pk"), data_evento_inicio__isnull=False)
        .values("plano").annotate(primeira=Min("data_evento_inicio")).values("primeira")[:1]
    )
    return queryset.annotate(
        _inicio=Coalesce(F("data_evento_inicio"), Subquery(primeiro_evento, output_field=DateField()), output_field=DateField()),
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
