"""As quatro situações da lista de viagens.

A mesma régua dos roteiros, ofícios e termos (`core/documento_abas.py` da
origem): recortes mutuamente exclusivos e combináveis, e sem nenhum marcado a
lista mostra tudo. A data da viagem é a `data_inicio` do cadastro; sem ela a
viagem ainda não aconteceu e fica entre as que vão acontecer. "Finalizado" é
o das prestações dos ofícios não cancelados da viagem — todas encerradas —,
e por isso a terceira aba se chama "Contas prestadas", como na lista de
ofícios.
"""

from django.db.models import Exists, OuterRef, Q
from django.utils import timezone

from viagens_roteiros.abas import ABA_ATUAIS, ABA_CANCELADOS, ABA_FINALIZADOS, ABA_FUTURAS, ABAS_VALIDAS, normalizar_abas  # noqa: F401

ABA_ROTULOS = [
    (ABA_FUTURAS, "Que vão acontecer"),
    (ABA_ATUAIS, "Em andamento e realizados"),
    (ABA_FINALIZADOS, "Contas prestadas"),
    (ABA_CANCELADOS, "Cancelados"),
]

CANCELADO_Q = Q(cancelado=True)
FINALIZADO_Q = Q(_tem_prestacao=True) & Q(_tem_prestacao_pendente=False)


def anotar_situacao(queryset):
    from viagens_prestacoes.models import PrestacaoServidor

    prestacoes = PrestacaoServidor.objects.filter(
        prestacao__oficio__viagem=OuterRef("pk"), prestacao__oficio__cancelado=False,
    )
    return queryset.annotate(
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
        # Sem data ainda não aconteceu: o rascunho fica entre as que vão acontecer.
        return pendente & (Q(data_inicio__gt=hoje) | Q(data_inicio__isnull=True))
    return pendente & Q(data_inicio__lte=hoje)


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
