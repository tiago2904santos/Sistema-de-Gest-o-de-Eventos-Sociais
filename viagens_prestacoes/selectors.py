from django.db.models import Prefetch
from django.shortcuts import get_object_or_404
from django.db.models import Q
from core.normalizers import remove_accents
from viagens_oficios.models import Oficio
from viagens_roteiros.models import RoteiroDestino
from viagens_roteiros.models import RoteiroTrecho
from .models import PrestacaoServidor
_SORT_MAP = {'criacao_desc': ['-prestacao__criado_em', 'prestacao_id', 'pk'], 'criacao_asc': ['prestacao__criado_em', 'prestacao_id', 'pk'], 'viagem_asc': ['prestacao__oficio__roteiro__saida_dt', '-prestacao__criado_em', 'prestacao_id', 'pk'], 'viagem_desc': ['-prestacao__oficio__roteiro__saida_dt', '-prestacao__criado_em', 'prestacao_id', 'pk'], 'oficio_asc': ['prestacao__oficio__ano', 'prestacao__oficio__numero', 'prestacao_id', 'pk'], 'oficio_desc': ['-prestacao__oficio__ano', '-prestacao__oficio__numero', 'prestacao_id', 'pk']}
ABA_NAO_LIBERADAS = 'nao_liberadas'
ABA_LIBERADAS = 'liberadas'
ABA_ARQUIVADOS = 'arquivados'
ABA_FINALIZADOS = 'finalizados'
#: m093: devolvida pelo financeiro para correção.
ABA_DEVOLVIDAS = 'devolvidas'
#: m094: prazo para prestar contas vencido. Diferente das de estado, cruza com elas.
ABA_PRESTACAO_VENCIDA = 'prestacao_vencida'
#: m085: prazo de saque vencendo (ou vencido) sem comprovante. Também cruza.
ABA_SAQUE_VENCENDO = 'saque_vencendo'
ABA_PADRAO = ABA_NAO_LIBERADAS
ABAS_VALIDAS = {ABA_NAO_LIBERADAS, ABA_LIBERADAS, ABA_DEVOLVIDAS, ABA_ARQUIVADOS, ABA_FINALIZADOS, ABA_SAQUE_VENCENDO, ABA_PRESTACAO_VENCIDA}
ORDEM_ABAS = (ABA_NAO_LIBERADAS, ABA_LIBERADAS, ABA_DEVOLVIDAS, ABA_ARQUIVADOS, ABA_FINALIZADOS, ABA_SAQUE_VENCENDO, ABA_PRESTACAO_VENCIDA)

def normalizar_aba(aba: str | None) -> str:
    aba = (aba or '').strip()
    return aba if aba in ABAS_VALIDAS else ABA_PADRAO

def normalizar_abas(valores) -> list[str]:
    """Normaliza uma seleção múltipla preservando a ordem visual canônica.

    Espelha `core.documento_abas.normalizar_abas`. As abas daqui são de ESTADO
    da prestação, não de período, mas o contrato da faixa de filtros é o mesmo
    em toda lista do sistema desde 2026-08-21.
    """
    if isinstance(valores, str):
        valores = [valores]
    escolhidas = {(valor or '').strip() for valor in valores or []}
    normalizadas = [chave for chave in ORDEM_ABAS if chave in escolhidas]
    return normalizadas or [ABA_PADRAO]

def _q_das_abas(abas) -> Q:
    """Combina por OR os recortes escolhidos. As abas são mutuamente exclusivas."""
    filtros = [_q_da_aba(aba) for aba in normalizar_abas(abas)]
    combinado = filtros[0]
    for filtro in filtros[1:]:
        combinado |= filtro
    return combinado

def _q_da_aba(aba: str) -> Q:
    """Filtro que define quais servidores pertencem a cada aba (as de estado são mutuamente exclusivas)."""
    if aba == ABA_SAQUE_VENCENDO:
        import datetime
        from django.db.models import Exists, OuterRef
        from django.utils import timezone
        from .models import PrestacaoDocumentoAnexo
        from .prazos import DIAS_AVISO_SAQUE
        comprovante = PrestacaoDocumentoAnexo.objects.filter(servidor_prestacao=OuterRef('pk'), tipo=PrestacaoDocumentoAnexo.TIPO_COMPROVANTE)
        limite = timezone.localdate() + datetime.timedelta(days=DIAS_AVISO_SAQUE)
        return Q(finalizada=False, arquivada=False, prazo_limite_saque__lte=limite) & ~Q(Exists(comprovante))
    if aba == ABA_PRESTACAO_VENCIDA:
        from .prazos import ultimo_saque_com_prestacao_vencida
        return Q(finalizada=False, arquivada=False, prazo_limite_saque__lte=ultimo_saque_com_prestacao_vencida())
    # m093: a prestação é individual, mas só vai para "Finalizados" quando a equipe
    # INTEIRA está finalizada; até lá, quem já finalizou continua junto dos colegas.
    from django.db.models import Exists, OuterRef
    em_aberto = Exists(PrestacaoServidor.objects.filter(prestacao=OuterRef('prestacao'), finalizada=False))
    if aba == ABA_FINALIZADOS:
        return Q(~em_aberto)
    if aba == ABA_ARQUIVADOS:
        return Q(arquivada=True) & Q(em_aberto)
    ativa = Q(arquivada=False) & Q(em_aberto)
    devolvida = Q(status=PrestacaoServidor.STATUS_REPROVADA, finalizada=False)
    if aba == ABA_DEVOLVIDAS:
        return ativa & devolvida
    if aba == ABA_LIBERADAS:
        return ativa & Q(data_liberacao_diarias__isnull=False) & ~devolvida
    return ativa & Q(data_liberacao_diarias__isnull=True) & ~devolvida

def servidores_removidos_da_equipe(prestacao):
    """Servidores que saíram da equipe do ofício mas cujos dados foram preservados (`DB-06`).

    Único ponto de leitura que usa `todos` de propósito: em todo o resto do
    sistema `objects` esconde estas linhas, e é isso que se quer. Aqui elas
    precisam aparecer — preservar comprovante e solicitação sem lugar nenhum de
    encontrá-los seria trocar "apagou em silêncio" por "sumiu em silêncio".

    A lista só não é vazia quando havia dado coletado: linha sem nada some de vez
    no próprio sinal, então o bloco da tela é autolimitado — aparece exatamente
    quando importa.
    """
    return PrestacaoServidor.todos.filter(prestacao=prestacao, removida_em__isnull=False).select_related('servidor', 'servidor__cargo', 'servidor__unidade').order_by('removida_em', 'pk')

def get_servidor_prestacao_by_id(pk):
    """Um `PrestacaoServidor` da área ativa, ou 404 (`PF-04`).

    Este domínio não tinha um selector de registro único — a lista sempre pediu
    página inteira. O endpoint de menus precisa de um, e escrever o filtro de área
    à mão aqui seria repetir a regra que o `BE-09` centralizou. Por isso reusa
    `_filter_servidores_by_area`, o mesmo que `_base_servidores` usa: `objects`
    aqui é `PrestacaoServidorAtivosManager`, que filtra removidos mas **não**
    recorta por área.

    O `select_related` acompanha o que o presenter do card toca, para o fragmento
    não virar um festival de consultas — ver `NOVO-38`.
    """
    queryset = PrestacaoServidor.objects.select_related('servidor', 'servidor__cargo', 'servidor__unidade', 'prestacao', 'prestacao__oficio', 'prestacao__oficio__roteiro', 'prestacao__oficio__roteiro__origem_municipio', 'prestacao__oficio__roteiro__origem_municipio__estado', 'prestacao__oficio__viatura', 'prestacao__oficio__motorista').prefetch_related(Prefetch('prestacao__oficio__roteiro__trechos', queryset=RoteiroTrecho.objects.select_related('origem_municipio', 'origem_municipio__estado', 'destino_municipio', 'destino_municipio__estado').order_by('ordem')), Prefetch('prestacao__oficio__roteiro__destinos', queryset=RoteiroDestino.objects.select_related('municipio', 'municipio__estado').order_by('ordem')))
    return get_object_or_404(queryset, pk=pk)

def _base_servidores(q: str | None=None, status: str | None=None, viagem_de: str | None=None, viagem_ate: str | None=None, sort: str | None=None):
    """Queryset com filtros de busca/ordenação, sem o recorte por aba."""
    order_fields = _SORT_MAP.get(sort or 'criacao_desc', _SORT_MAP['criacao_desc'])
    queryset = PrestacaoServidor.objects.select_related('servidor', 'servidor__cargo', 'servidor__unidade', 'prestacao', 'prestacao__oficio', 'prestacao__oficio__roteiro', 'prestacao__oficio__roteiro__origem_municipio', 'prestacao__oficio__roteiro__origem_municipio__estado', 'prestacao__oficio__viatura', 'prestacao__oficio__motorista').prefetch_related(Prefetch('prestacao__oficio__roteiro__trechos', queryset=RoteiroTrecho.objects.select_related('origem_municipio', 'origem_municipio__estado', 'destino_municipio', 'destino_municipio__estado').order_by('ordem')), Prefetch('prestacao__oficio__roteiro__destinos', queryset=RoteiroDestino.objects.select_related('municipio', 'municipio__estado').order_by('ordem')), Prefetch('prestacao__servidores_prestacao', queryset=PrestacaoServidor.objects.select_related('servidor', 'servidor__cargo', 'servidor__unidade').order_by('pk')), 'documentos_anexos', 'prestacao__documentos_anexos', 'prestacao__relatorio_tecnico', 'prestacao__diario_bordo', 'prestacao__diario_bordo__trechos').filter(prestacao__oficio__cancelado=False).order_by(*order_fields)
    if status:
        queryset = queryset.filter(status=status)
    if q:
        # Mesma busca sem acentos nos dois bancos; não exige extensão PostgreSQL.
        busca = remove_accents(q.strip()).casefold()
        ids = [pk for pk, nome, cargo, protocolo, numero, ano, solicitacao in queryset.values_list("pk", "servidor__nome", "servidor__cargo__nome", "prestacao__oficio__protocolo", "prestacao__oficio__numero", "prestacao__oficio__ano", "numero_solicitacao") if any(busca in remove_accents(str(v or "")).casefold() for v in (nome,cargo,protocolo,solicitacao)) or busca in (str(numero),str(ano))]
        queryset = queryset.filter(pk__in=ids)

    if viagem_de:
        queryset = queryset.filter(prestacao__oficio__roteiro__isnull=False, prestacao__oficio__roteiro__saida_dt__date__gte=viagem_de)
    if viagem_ate:
        queryset = queryset.filter(prestacao__oficio__roteiro__isnull=False, prestacao__oficio__roteiro__saida_dt__date__lte=viagem_ate)
    return queryset

def listar_prestacoes(q: str | None=None, status: str | None=None, aba=None, viagem_de: str | None=None, viagem_ate: str | None=None, sort: str | None=None):
    """Servidores, com os filtros aplicados.

    `aba` aceita uma situação, uma LISTA delas, ou nada. Nada significa **sem
    recorte**: a lista abre inteira, que é o contrato da faixa de filtros em
    todo o sistema desde 2026-08-21. Antes, `aba=None` era normalizado para a
    aba padrão e a tela abria filtrada sem dizer.

    Uma string continua aceita porque os testes de recorte pedem uma aba por
    vez, e é a forma natural de perguntar "quem está nesta situação".
    """
    base = _base_servidores(q=q, status=status, viagem_de=viagem_de, viagem_ate=viagem_ate, sort=sort)
    if not aba:
        return base
    return base.filter(_q_das_abas(aba))

def contar_por_aba(q: str | None=None, status: str | None=None, viagem_de: str | None=None, viagem_ate: str | None=None) -> dict:
    """Total de servidores em cada aba, respeitando os filtros de busca ativos."""
    base = _base_servidores(q=q, status=status, viagem_de=viagem_de, viagem_ate=viagem_ate)
    return {aba: base.filter(_q_da_aba(aba)).count() for aba in ORDEM_ABAS}
LIMITE_OFICIOS_PREFILL = 200

def oficios_para_prefill_de_motorista(oficio_atual):
    """Ofícios da área que podem emprestar motorista/viatura ao diário desta prestação.

    Consulta pura — vem para cá porque era o último acesso de manager que sobrava em
    `diario_views.py` depois da extração da gravação (`P-01`).
    """
    return Oficio.objects.select_related('viatura', 'viatura__combustivel', 'motorista', 'transporte_combustivel_manual').exclude(pk=oficio_atual.pk).filter(numero__isnull=False).order_by('-ano', '-numero')[:LIMITE_OFICIOS_PREFILL]
