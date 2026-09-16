from datetime import date

from django.db.models import F, Q
from django.shortcuts import get_object_or_404

from core.utils.masks import normalize_protocolo

from .abas import anotar_situacao, q_das_abas
from .models import Oficio, ModeloMotivoOficio

# As seis ordenações da lista da origem, na ordem do menu de lá. A chave é o
# valor de `?sort=` (visto na URL da origem: `sort=numero_asc`).
ORDENACOES = {
    "numero_desc": ("Número: maior", ["-ano", "-numero", "-pk"]),
    "numero_asc": ("Número: menor", ["ano", "numero", "pk"]),
    "criacao_desc": ("Criação: mais recente", ["-data_criacao", "-criado_em"]),
    "criacao_asc": ("Criação: mais antiga", ["data_criacao", "criado_em"]),
    "viagem_asc": ("Viagem: mais próxima", [F("_saida").asc(nulls_last=True), "pk"]),
    "viagem_desc": ("Viagem: mais distante", [F("_saida").desc(nulls_last=True), "-pk"]),
}
ORDENACAO_PADRAO = "numero_desc"


def opcoes_de_ordenacao():
    return [{"valor": chave, "rotulo": rotulo} for chave, (rotulo, _) in ORDENACOES.items()]


def normalizar_ordenacao(pedido):
    return pedido if pedido in ORDENACOES else ORDENACAO_PADRAO


def _data(valor):
    """Data ISO vinda do calendário do sistema; qualquer outra coisa é ignorada."""
    try:
        return date.fromisoformat(str(valor)) if valor else None
    except ValueError:
        return None


def _filtro_busca(q):
    """Número, protocolo, motivo ou destino — o que o placeholder da origem promete."""
    q = q.strip()
    filtro = (
        Q(motivo__icontains=q)
        | Q(roteiro__destinos__municipio__nome__icontains=q)
        | Q(roteiro__trechos__destino_municipio__nome__icontains=q)
        | Q(servidores__nome__icontains=q)
    )
    digitos = normalize_protocolo(q)
    if digitos:
        filtro |= Q(protocolo__icontains=digitos)
    if q.isdigit():
        filtro |= Q(numero=int(q))
    elif "/" in q:
        numero, _, ano = q.partition("/")
        if numero.strip().isdigit() and ano.strip().isdigit():
            filtro |= Q(numero=int(numero), ano=int(ano))
    return filtro


def base_oficios():
    return anotar_situacao(
        Oficio.objects.select_related(
            "roteiro__origem_municipio__estado", "solicitante", "viatura", "motorista", "justificativa"
        ).prefetch_related(
            "servidores__cargo", "servidores__unidade", "servidores_termo_autorizacao",
            "roteiro__destinos__municipio__estado",
            "roteiro__trechos__origem_municipio__estado", "roteiro__trechos__destino_municipio__estado",
        )
    )


def listar_oficios(q="", status="", ano="", fila="", *, situacoes=None, viagem_de="", viagem_ate="",
                   criacao_de="", criacao_ate="", sort=""):
    """Lista filtrada como a origem: busca, situações combináveis, dois períodos e ordenação.

    `status`, `ano` e `fila` são o contrato anterior desta função e continuam
    valendo para quem os chama (`get_oficio_by_id` usa `fila="todos"`).
    """
    qs = base_oficios()
    if q:
        qs = qs.filter(_filtro_busca(q)).distinct()
    if status in dict(Oficio.STATUS_CHOICES):
        qs = qs.filter(status=status)
    if str(ano).isdigit():
        qs = qs.filter(ano=int(ano))
    if fila == "cancelados":
        qs = qs.filter(cancelado=True)
    elif fila == "ativos":
        qs = qs.filter(cancelado=False)
    if _data(viagem_de):
        qs = qs.filter(_saida__date__gte=_data(viagem_de))
    if _data(viagem_ate):
        qs = qs.filter(_saida__date__lte=_data(viagem_ate))
    if _data(criacao_de):
        qs = qs.filter(data_criacao__gte=_data(criacao_de))
    if _data(criacao_ate):
        qs = qs.filter(data_criacao__lte=_data(criacao_ate))
    filtro = q_das_abas(situacoes)
    if filtro is not None:
        qs = qs.filter(filtro)
    if sort:
        qs = qs.order_by(*ORDENACOES[normalizar_ordenacao(sort)][1])
    return qs


def get_oficio_by_id(pk):
    return get_object_or_404(listar_oficios(fila="todos"), pk=pk)


def listar_modelos_motivo_ativos():
    return ModeloMotivoOficio.objects.order_by('nome')
