"""Multieventos: vários eventos na mesma cidade, uma viagem só.

Caso típico: o mesmo evento em três escolas de Antonina — dia 06, dia 07 e
de 08 a 09. A mesma equipe atende os três; o que muda é só o Plano de
Trabalho, que vira multieventos (um evento por escola). Antes cada
solicitação gerava a sua viagem, com três roteiros, três ofícios por
servidor e três planos.

Agora, no deferimento, a solicitação cuja cidade e cujos dias encostam numa
viagem já gerada (mesma cidade, mesmo ambiente, até `FOLGA_DIAS` de
intervalo) entra nessa viagem: o período se estende, o roteiro é refeito
para o período todo, as equipes previstas ficam com a maior quantidade (são
as mesmas pessoas) e o plano sai multieventos. Só junta enquanto a viagem
não tem ofício, ordem de serviço nem plano: documento emitido não é mexido.

Antes do deferimento, a tela da solicitação já avisa quais eventos vizinhos
vão virar uma viagem só (`eventos_vizinhos`).
"""

from datetime import timedelta

#: Dias de intervalo entre dois eventos que ainda contam como a mesma viagem
#: (06/10 e 07/10 encostam; 06/10 e 08/10 têm um dia livre no meio).
FOLGA_DIAS = 1

#: Até quantos dias de distância se procuram vizinhos de uma solicitação.
JANELA_DIAS = 30


def _periodo(inicio, fim):
    return inicio, fim or inicio


def encostam(periodo_a, periodo_b, folga=FOLGA_DIAS):
    """Os dois períodos se sobrepõem ou ficam a até `folga` dias um do outro."""
    (ia, fa), (ib, fb) = periodo_a, periodo_b
    if not (ia and ib):
        return False
    alcance = timedelta(days=folga + 1)
    return ia <= fb + alcance and ib <= fa + alcance


def solicitacoes_da_viagem(viagem):
    """A de origem (a do roteiro) e as juntadas, por data do evento."""
    from solicitacoes.models import SolicitacaoEvento

    if viagem is None or not viagem.pk:
        return []
    ids = set(viagem.roteiros.filter(solicitacao__isnull=False).values_list("solicitacao_id", flat=True))
    ids |= set(viagem.solicitacoes_juntadas.values_list("pk", flat=True))
    return list(
        SolicitacaoEvento.objects.filter(pk__in=ids)
        .select_related("municipio__estado", "tipo_evento", "orgao_responsavel", "unidade_movel_designada")
        .order_by("data_inicio_evento", "pk")
    )


def documentos_que_impedem(viagem):
    """Os documentos que já saíram: com eles, a viagem não recebe outro evento sozinha."""
    impedem = []
    if viagem.oficios.filter(cancelado=False).exists():
        impedem.append("ofício")
    if viagem.ordens_servico.filter(cancelado=False).exists():
        impedem.append("ordem de serviço")
    if viagem.planos_trabalho.filter(cancelado=False).exists():
        impedem.append("plano de trabalho")
    return impedem


def viagem_para_juntar(solicitacao, setor):
    """(viagem, pode_juntar) da viagem vizinha no mesmo ambiente, ou (None, False).

    Vizinha: veio de solicitação, está ativa, vai à mesma cidade e o período
    encosta no do evento. `pode_juntar` é falso quando ela já tem documento.
    """
    from viagens_viagem.models import Viagem

    if not solicitacao.municipio_id or not solicitacao.data_inicio_evento:
        return None, False
    periodo = _periodo(solicitacao.data_inicio_evento, solicitacao.data_fim_evento)
    candidatas = (
        Viagem.objects.filter(cancelado=False, destino_municipio_id=solicitacao.municipio_id,
                              data_inicio__isnull=False, roteiros__solicitacao__isnull=False)
        .exclude(roteiros__solicitacao=solicitacao).exclude(solicitacoes_juntadas=solicitacao)
        .distinct().order_by("data_inicio", "pk")
    )
    candidatas = candidatas.filter(setor=setor) if setor is not None else candidatas.filter(setor__isnull=True)
    for viagem in candidatas:
        if encostam(periodo, _periodo(viagem.data_inicio, viagem.data_fim)):
            return viagem, not documentos_que_impedem(viagem)
    return None, False


def eventos_vizinhos(solicitacao):
    """As outras solicitações da mesma cidade em dias encostados, em cadeia.

    06, 07 e 08–09: a de 06 encosta na de 07, que encosta na de 08 — as três
    são um bloco só, mesmo que 06 e 08 não encostem entre si.
    """
    from solicitacoes.models import DecisaoDG, SolicitacaoEvento, StatusSolicitacao

    if not solicitacao.municipio_id or not solicitacao.data_inicio_evento:
        return []
    inicio, fim = _periodo(solicitacao.data_inicio_evento, solicitacao.data_fim_evento)
    candidatas = list(
        SolicitacaoEvento.objects.filter(
            municipio_id=solicitacao.municipio_id, data_inicio_evento__isnull=False,
            data_inicio_evento__gte=inicio - timedelta(days=JANELA_DIAS),
            data_inicio_evento__lte=fim + timedelta(days=JANELA_DIAS),
        )
        .exclude(pk=solicitacao.pk)
        .exclude(status__in=[StatusSolicitacao.NAO_ATENDIDA, StatusSolicitacao.CANCELADA, StatusSolicitacao.RASCUNHO])
        .exclude(decisao_dg__in=[DecisaoDG.NAO_ATENDER, DecisaoDG.CANCELADO])
        .order_by("data_inicio_evento", "pk")
    )
    bloco = [_periodo(inicio, fim)]
    vizinhos, mudou = [], True
    while mudou:
        mudou = False
        for outra in list(candidatas):
            periodo = _periodo(outra.data_inicio_evento, outra.data_fim_evento)
            if any(encostam(periodo, p) for p in bloco):
                bloco.append(periodo)
                vizinhos.append(outra)
                candidatas.remove(outra)
                mudou = True
    return sorted(vizinhos, key=lambda s: (s.data_inicio_evento, s.pk))
