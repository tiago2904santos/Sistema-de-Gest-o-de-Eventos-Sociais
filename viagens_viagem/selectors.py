"""Consultas de leitura da viagem — a lista e o que o painel mostra em cada etapa.

O `eventos/selectors.py` da origem, sem o recorte por área. Roteiros e termos
"da viagem" contam os ligados direto (`viagem`) e os que chegam por um ofício
dela: é o que a etapa 2 e a etapa 5 listam.
"""

from django.db.models import Case, IntegerField, Q, Value, When
from django.shortcuts import get_object_or_404

from .abas import anotar_situacao, q_das_abas
from .models import Viagem, ViagemDocumentoSolicitacao


def base_viagens():
    return anotar_situacao(
        Viagem.objects.select_related(
            "unidade_responsavel", "responsavel", "destino_municipio__estado", "destino_estado",
        ).prefetch_related(
            "tipos",
            "oficios__servidores", "oficios__motorista", "oficios__roteiro__origem_municipio",
            "oficios__roteiro__trechos__destino_municipio__estado",
            "roteiros__trechos", "planos_trabalho__programa", "planos_trabalho__destino_cidade__estado",
            "ordens_servico__destinos__estado", "documentos_solicitacao",
            # O contador de servidores da lista (m063).
            "equipes_previstas__equipe", "oficios__servidores__unidade",
            # O selo de coerência da lista (m071).
            "oficios__viatura", "ordens_servico__servidores", "planos_trabalho__destinos",
            "termos_autorizacao__servidores", "termos_autorizacao__oficio__viatura", "termos_autorizacao__viatura",
        )
    )


def _filtro_busca(q):
    """Título, descrição, motivo, destino, responsável ou unidade — a busca da
    origem — e, dos ofícios, servidor, motorista, placa, protocolo e número."""
    import re

    from viagens_cadastros.normalizacao import normalizar_digitos, normalizar_placa

    q = q.strip()
    filtro = (
        Q(titulo__icontains=q)
        | Q(descricao__icontains=q)
        | Q(motivo__icontains=q)
        | Q(destino_municipio__nome__icontains=q)
        | Q(destino_estado__sigla__iexact=q)
        | Q(responsavel__nome__icontains=q)
        | Q(unidade_responsavel__nome__icontains=q)
        | Q(tipos__nome__icontains=q)
        | Q(oficios__servidores__nome__icontains=q)
        | Q(oficios__motorista__nome__icontains=q)
        | Q(oficios__motorista_manual_nome__icontains=q)
    )
    # Placa em qualquer grafia ("abc-1d23"): a gravada não tem hífen.
    placa = normalizar_placa(q)
    if len(placa) >= 3 and re.search(r"\d", placa):
        filtro |= Q(oficios__viatura__placa__icontains=placa) | Q(oficios__transporte_placa_manual__icontains=placa)
    # Protocolo é gravado só com dígitos: "12.345.678-9" acha "123456789".
    digitos = normalizar_digitos(q)
    if len(digitos) >= 5:
        filtro |= Q(oficios__protocolo__contains=digitos)
    # Número do ofício: "15/2026" ou "15".
    numero_ano = re.fullmatch(r"(\d{1,5})\s*/\s*(\d{4})", q)
    if numero_ano:
        filtro |= Q(oficios__numero=int(numero_ano[1]), oficios__ano=int(numero_ano[2]))
    elif q.isdigit() and len(q) <= 5:
        filtro |= Q(oficios__numero=int(q))
    return filtro


def listar_viagens(q="", *, situacoes=None):
    qs = base_viagens()
    if q:
        qs = qs.filter(_filtro_busca(q)).distinct()
    filtro = q_das_abas(situacoes)
    if filtro is not None:
        qs = qs.filter(filtro)
    return qs.order_by("-criado_em", "-pk")


def get_viagem_by_id(pk):
    return get_object_or_404(base_viagens(), pk=pk)


def listar_oficios_da_viagem(viagem):
    from viagens_oficios.selectors import base_oficios

    return base_oficios().filter(viagem=viagem).order_by("-ano", "-numero", "-pk")


def listar_roteiros_da_viagem(viagem):
    """Roteiros ligados à viagem: direto (`roteiro.viagem`) ou por um ofício dela."""
    from viagens_roteiros.abas import anotar_finalizacao
    from viagens_roteiros.models import Roteiro

    return anotar_finalizacao(
        Roteiro.objects.filter(Q(viagem=viagem) | Q(oficios__viagem=viagem)).distinct()
        .select_related("origem_municipio__estado").prefetch_related("trechos__destino_municipio__estado")
    ).order_by("-criado_em", "-pk")


def listar_termos_da_viagem(viagem):
    """Todos os termos da viagem, diretos ou via ofício — os genéricos (sem ofício) primeiro."""
    from viagens_termos.selectors import base_termos

    return (
        base_termos().filter(Q(viagem=viagem) | Q(oficio__viagem=viagem)).distinct()
        .annotate(_generico=Case(When(oficio__isnull=True, then=Value(0)), default=Value(1), output_field=IntegerField()))
        .order_by("_generico", "-criado_em", "-pk")
    )


def existe_termo_da_viagem(viagem):
    from viagens_termos.models import TermoAutorizacao

    return TermoAutorizacao.objects.filter(Q(viagem=viagem) | Q(oficio__viagem=viagem)).exists()


def buscar_documento_solicitacao(viagem, pk):
    """Devolve `None` quando não existe — quem chama decide a mensagem."""
    return ViagemDocumentoSolicitacao.objects.filter(pk=pk, viagem=viagem).first()


def get_documento_solicitacao_by_id(viagem, pk):
    return get_object_or_404(ViagemDocumentoSolicitacao, pk=pk, viagem=viagem)
