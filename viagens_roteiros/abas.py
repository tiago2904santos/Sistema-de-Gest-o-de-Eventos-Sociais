"""As quatro situações da lista de roteiros.

Portadas do Gerenciador de Viagens (`core/documento_abas.py`) na Meta 2. Os
recortes são mutuamente exclusivos e combináveis: sem nenhum escolhido, a lista
mostra tudo. "Finalizado" não é campo do roteiro — é o estado das prestações
dos ofícios que o usam, e por isso entra por subconsulta.
"""

from django.db.models import DateTimeField, Exists, OuterRef, Q, Subquery
from django.db.models.functions import Coalesce, TruncDate
from django.utils import timezone

ABA_FUTURAS = "futuras"
ABA_ATUAIS = "atuais"
ABA_FINALIZADOS = "finalizados"
ABA_CANCELADOS = "cancelados"

ABA_ROTULOS = [
    (ABA_FUTURAS, "Que vão acontecer"),
    (ABA_ATUAIS, "Em andamento e realizados"),
    (ABA_FINALIZADOS, "Finalizados"),
    (ABA_CANCELADOS, "Cancelados"),
]

ABAS_VALIDAS = {chave for chave, _ in ABA_ROTULOS}

# Finalizado: tem prestação e nenhuma delas está pendente.
FINALIZADO_Q = Q(_tem_prestacao=True) & Q(_tem_prestacao_pendente=False)

# Data de início anotada em `anotar_finalizacao`: a do roteiro ou, sem ela, a
# primeira saída dos trechos (é onde o editor grava as datas).
CAMPO_DATA = "_inicio"
CANCELADO_Q = Q(cancelado=True)


def normalizar_abas(valores):
    """Mantém a ordem dos rótulos e descarta o que não é aba."""
    escolhidas = {str(valor).strip().lower() for valor in valores or []}
    return [chave for chave, _ in ABA_ROTULOS if chave in escolhidas]


def anotar_finalizacao(queryset):
    """Anota se o roteiro tem prestação e se alguma continua pendente, e a data
    de início usada pelas abas temporais.

    `Exists` em vez de contagem: evita agrupamento e deixa a negação correta.
    """
    from viagens_prestacoes.models import PrestacaoServidor

    from .models import RoteiroTrecho

    todas = PrestacaoServidor.objects.filter(
        prestacao__oficio__roteiro=OuterRef("pk"),
        prestacao__oficio__cancelado=False,
    )
    primeira_saida = (
        RoteiroTrecho.objects.filter(roteiro=OuterRef("pk"), saida_dt__isnull=False)
        .order_by("saida_dt")
        .values("saida_dt")[:1]
    )
    return queryset.annotate(
        _tem_prestacao=Exists(todas),
        _tem_prestacao_pendente=Exists(todas.filter(finalizada=False)),
        _inicio=TruncDate(
            Coalesce("saida_dt", Subquery(primeira_saida, output_field=DateTimeField()))
        ),
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
        return pendente & Q(**{f"{CAMPO_DATA}__gt": hoje})
    # Atuais: já começou, ou ainda sem data — o que também precisa de atenção.
    return pendente & (
        Q(**{f"{CAMPO_DATA}__lte": hoje}) | Q(**{f"{CAMPO_DATA}__isnull": True})
    )


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


def opcoes_de_aba(queryset, escolhidas, contagem=None):
    """Opções do filtro, com a contagem ao lado — como na origem."""
    contagem = contagem or contar_por_aba(queryset)
    marcadas = set(escolhidas or [])
    return [
        {
            "valor": chave,
            "rotulo": f"{rotulo} ({contagem.get(chave, 0)})",
            "selecionado": chave in marcadas,
        }
        for chave, rotulo in ABA_ROTULOS
    ]
