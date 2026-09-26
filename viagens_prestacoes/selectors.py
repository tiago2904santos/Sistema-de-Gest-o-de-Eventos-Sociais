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
#: m100: contadores de pendência para trabalhar em lote. Cruzam com as de estado,
#: e só contam prestações em aberto (nem finalizadas, nem arquivadas) — menos a
#: última, que é o número do mês para a chefia.
ABA_SEM_SOLICITACAO = 'sem_solicitacao'
ABA_SEM_DESPACHO = 'sem_despacho'
ABA_SEM_COMPROVANTE = 'sem_comprovante'
ABA_COMPROVANTE_DIVERGENTE = 'comprovante_divergente'
ABA_FINALIZADAS_MES = 'finalizadas_mes'
ABAS_PENDENCIA = (ABA_SEM_SOLICITACAO, ABA_SEM_DESPACHO, ABA_SEM_COMPROVANTE, ABA_COMPROVANTE_DIVERGENTE, ABA_FINALIZADAS_MES)
ABA_PADRAO = ABA_NAO_LIBERADAS
ORDEM_ABAS = (ABA_NAO_LIBERADAS, ABA_LIBERADAS, ABA_DEVOLVIDAS, ABA_ARQUIVADOS, ABA_FINALIZADOS, ABA_SAQUE_VENCENDO, ABA_PRESTACAO_VENCIDA, *ABAS_PENDENCIA)
ABAS_VALIDAS = set(ORDEM_ABAS)

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
    if aba in ABAS_PENDENCIA:
        return _q_da_pendencia(aba)
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

def _q_da_pendencia(aba: str) -> Q:
    """m100: o recorte de cada contador de pendência."""
    from django.db.models import Exists, OuterRef
    from django.utils import timezone
    from .models import PrestacaoDocumentoAnexo as Anexo
    em_aberto = Q(finalizada=False, arquivada=False)
    if aba == ABA_SEM_SOLICITACAO:
        return em_aberto & Q(numero_solicitacao='')
    if aba == ABA_SEM_DESPACHO:
        despacho = Anexo.objects.filter(prestacao=OuterRef('prestacao'), tipo=Anexo.TIPO_DESPACHO)
        legado = Q(prestacao__despacho_assinado='') | Q(prestacao__despacho_assinado__isnull=True)
        return em_aberto & ~Q(Exists(despacho)) & legado
    if aba == ABA_SEM_COMPROVANTE:
        # Só quem já teve a diária liberada: antes disso não há o que sacar.
        comprovante = Anexo.objects.filter(servidor_prestacao=OuterRef('pk'), tipo=Anexo.TIPO_COMPROVANTE)
        return em_aberto & Q(data_liberacao_diarias__isnull=False) & ~Q(Exists(comprovante))
    if aba == ABA_COMPROVANTE_DIVERGENTE:
        return Q(pk__in=_ids_comprovante_divergente())
    hoje = timezone.localdate()
    return Q(finalizada=True, finalizada_em__date__gte=hoje.replace(day=1), finalizada_em__date__lte=hoje)

def _ids_comprovante_divergente() -> list[int]:
    """Prestações em aberto cuja soma dos comprovantes não bate com a diária.

    A diária esperada sai do roteiro efetivo (ajustado ou do ofício) com o mesmo
    arredondamento do documento — conta que não cabe numa consulta; aqui percorre
    só quem tem comprovante, com os anexos e o roteiro já carregados.
    """
    from django.db.models import Exists, OuterRef
    from .models import PrestacaoDocumentoAnexo as Anexo
    from .services import divergencia_dos_comprovantes
    comprovante = Anexo.objects.filter(servidor_prestacao=OuterRef('pk'), tipo=Anexo.TIPO_COMPROVANTE)
    candidatos = PrestacaoServidor.objects.filter(finalizada=False, arquivada=False).filter(Exists(comprovante)).select_related('prestacao__oficio__roteiro', 'prestacao__roteiro_ajustado').prefetch_related('documentos_anexos')
    return [ps.pk for ps in candidatos if divergencia_dos_comprovantes(ps) is not None]

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
    from django.db.models import Count
    base = _base_servidores(q=q, status=status, viagem_de=viagem_de, viagem_ate=viagem_ate)
    # m100: uma consulta só, com uma contagem condicional por aba.
    return base.order_by().aggregate(**{aba: Count('pk', filter=_q_da_aba(aba), distinct=True) for aba in ORDEM_ABAS})
LIMITE_OFICIOS_PREFILL = 200

def oficios_para_prefill_de_motorista(oficio_atual):
    """Ofícios da área que podem emprestar motorista/viatura ao diário desta prestação.

    Consulta pura — vem para cá porque era o último acesso de manager que sobrava em
    `diario_views.py` depois da extração da gravação (`P-01`).
    """
    return Oficio.objects.select_related('viatura', 'viatura__combustivel', 'motorista', 'transporte_combustivel_manual').exclude(pk=oficio_atual.pk).filter(numero__isnull=False).order_by('-ano', '-numero')[:LIMITE_OFICIOS_PREFILL]
