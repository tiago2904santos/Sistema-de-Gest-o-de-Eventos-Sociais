"""Camada de serviço do workflow de solicitações.

Fluxo enxuto: o solicitante cria/revisa e envia direto para a DG; a DG
despacha. Todas as mudanças de status passam por aqui: as views nunca alteram
o campo `status` diretamente, e transições inválidas levantam
`TransicaoInvalida`.
"""

import logging

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.urls import reverse
from django.utils import timezone

from core.notificacoes import notificar, usuarios_do_grupo

from .models import (
    AcaoHistorico,
    DecisaoDG,
    HistoricoSolicitacao,
    SolicitacaoEvento,
    StatusSolicitacao,
)

logger = logging.getLogger(__name__)


class TransicaoInvalida(ValidationError):
    """Transição de status não permitida pelo workflow."""


TRANSICOES_VALIDAS = {
    StatusSolicitacao.RASCUNHO: {StatusSolicitacao.AGUARDANDO_DESPACHO},
    StatusSolicitacao.AGUARDANDO_DESPACHO: {
        StatusSolicitacao.DEFERIDA_EM_ANDAMENTO,
        StatusSolicitacao.NAO_ATENDIDA,
        StatusSolicitacao.CANCELADA,
        StatusSolicitacao.DEVOLVIDA,
    },
    StatusSolicitacao.DEVOLVIDA: {
        StatusSolicitacao.AGUARDANDO_DESPACHO,
        StatusSolicitacao.CANCELADA,
    },
    # Deferida: o evento acontece e o solicitante confirma o atendimento —
    # ou o evento é cancelado no caminho.
    StatusSolicitacao.DEFERIDA_EM_ANDAMENTO: {
        StatusSolicitacao.ATENDIDA,
        StatusSolicitacao.CANCELADA,
    },
}

STATUS_EDITAVEIS = {StatusSolicitacao.RASCUNHO, StatusSolicitacao.DEVOLVIDA}

STATUS_POR_DECISAO = {
    DecisaoDG.ATENDER: StatusSolicitacao.DEFERIDA_EM_ANDAMENTO,
    DecisaoDG.NAO_ATENDER: StatusSolicitacao.NAO_ATENDIDA,
    DecisaoDG.CANCELADO: StatusSolicitacao.CANCELADA,
}

DECISOES_COM_OBSERVACAO_OBRIGATORIA = {DecisaoDG.NAO_ATENDER, DecisaoDG.CANCELADO}

CAMPOS_OBRIGATORIOS_ENVIO = {
    "data_solicitacao": "Data da solicitação",
    "data_inicio_evento": "Início do evento",
    "data_fim_evento": "Fim do evento",
    "tipo_evento": "Tipo do evento",
    "municipio": "Município",
    "solicitante_nome": "Solicitante",
    "solicitante_cargo_unidade": "Cargo / unidade",
    "orgao_responsavel": "Órgão responsável",
}


def registrar_historico(
    solicitacao,
    usuario,
    acao,
    status_anterior="",
    status_novo="",
    observacao="",
    alteracoes=None,
):
    return HistoricoSolicitacao.objects.create(
        solicitacao=solicitacao,
        usuario=usuario,
        acao=acao,
        status_anterior=status_anterior,
        status_novo=status_novo,
        observacao=observacao,
        alteracoes=alteracoes or [],
    )


# ---------------------------------------------------------------------------
# O que mudou: fotografia antes e depois de salvar, campo a campo
# ---------------------------------------------------------------------------

# Campo do modelo -> rótulo no histórico, na ordem da tela.
CAMPOS_FOTOGRAFIA = [
    ("data_solicitacao", "Data da solicitação"),
    ("data_inicio_evento", "Início do evento"),
    ("data_fim_evento", "Fim do evento"),
    ("municipio", "Município"),
    ("solicitante_nome", "Solicitante"),
    ("contato", "Contato"),
    ("solicitante_cargo_unidade", "Cargo / unidade"),
    ("orgao_responsavel", "Órgão responsável"),
    ("tipo_evento", "Tipo do evento"),
    ("local_evento", "Local do evento"),
    ("protocolo", "Protocolo (eProtocolo)"),
    ("tipo_operacao", "Tipo de operação"),
    ("quantidade_cin", "CIN agendadas"),
    ("descricao_complementar", "Descrição complementar"),
    ("unidade_movel", "Unidade móvel"),
    ("unidade_movel_designada", "Qual unidade móvel"),
    ("motorista", "Motorista"),
]


def _texto(valor):
    if valor is None or valor == "":
        return ""
    if isinstance(valor, bool):
        return "Sim" if valor else "Não"
    if hasattr(valor, "strftime"):
        return valor.strftime("%d/%m/%Y")
    return str(valor)


def fotografia(solicitacao):
    """Os valores legíveis do pedido, para comparar antes e depois."""
    foto = {}
    for campo, rotulo in CAMPOS_FOTOGRAFIA:
        if campo == "tipo_operacao":
            valor = solicitacao.get_tipo_operacao_display() if solicitacao.tipo_operacao else ""
        else:
            valor = getattr(solicitacao, campo)
        foto[rotulo] = _texto(valor)
    if solicitacao.pk:
        foto["Serviços"] = ", ".join(
            # filter(): consulta nova, sem o cache do prefetch da tela.
            sorted(str(servico) for servico in solicitacao.servicos.filter())
        )
        for item in solicitacao.itens_equipe.select_related("equipe"):
            foto[f"Servidores — {item.equipe}"] = _texto(item.quantidade_servidores)
    return foto


def diferencas(antes, depois):
    """[{campo, antes, depois}] do que mudou entre duas fotografias."""
    alteracoes = []
    for campo in list(antes) + [c for c in depois if c not in antes]:
        valor_antes, valor_depois = antes.get(campo, ""), depois.get(campo, "")
        if valor_antes != valor_depois:
            campo_rotulo = campo
            if campo.startswith("Servidores — ") and campo not in antes:
                campo_rotulo = campo.replace("Servidores — ", "Equipe incluída — ")
            elif campo.startswith("Servidores — ") and campo not in depois:
                campo_rotulo = campo.replace("Servidores — ", "Equipe retirada — ")
            alteracoes.append(
                {"campo": campo_rotulo, "antes": valor_antes, "depois": valor_depois}
            )
    return alteracoes


def _transicionar(solicitacao, novo_status):
    permitidos = TRANSICOES_VALIDAS.get(solicitacao.status, set())
    if novo_status not in permitidos:
        raise TransicaoInvalida(
            f"Transição de {solicitacao.get_status_display()} para "
            f"{StatusSolicitacao(novo_status).label} não é permitida."
        )
    anterior = solicitacao.status
    solicitacao.status = novo_status
    return anterior


def pendencias_para_envio(solicitacao):
    """Pendências para enviar à DG: dados, serviços e planejamento mínimo."""
    faltas = [
        rotulo
        for campo, rotulo in CAMPOS_OBRIGATORIOS_ENVIO.items()
        if not getattr(solicitacao, campo)
    ]
    if solicitacao.pk:
        if not solicitacao.itens_servico.exists():
            faltas.append("Ao menos um serviço solicitado")
        if not solicitacao.itens_equipe.exists():
            faltas.append("Ao menos uma equipe designada")
        elif solicitacao.itens_equipe.exclude(quantidade_servidores__gt=0).exists():
            faltas.append("Quantidade de servidores de cada equipe")
    if not solicitacao.tipo_operacao:
        faltas.append("Tipo de operação")
    if solicitacao.unidade_movel and not solicitacao.unidade_movel_designada_id:
        faltas.append("Qual unidade móvel vai ao evento")
    return faltas


@transaction.atomic
def enviar(solicitacao, usuario):
    """Envia a solicitação revisada (nova ou devolvida) para o despacho da DG."""
    if solicitacao.status not in STATUS_EDITAVEIS:
        raise TransicaoInvalida(
            "Apenas rascunhos ou solicitações devolvidas podem ser enviados."
        )
    faltas = pendencias_para_envio(solicitacao)
    if faltas:
        raise ValidationError(
            "Preencha os campos obrigatórios antes de enviar: " + ", ".join(faltas) + "."
        )
    anterior = _transicionar(solicitacao, StatusSolicitacao.AGUARDANDO_DESPACHO)
    solicitacao.save()
    registrar_historico(
        solicitacao,
        usuario,
        AcaoHistorico.ENVIO,
        status_anterior=anterior,
        status_novo=solicitacao.status,
    )
    link_registro = reverse("solicitacoes:editar", args=[solicitacao.pk])
    notificar(
        usuarios_do_grupo("GESTOR_DG"),
        f"Solicitação #{solicitacao.pk} aguardando despacho",
        f"{solicitacao.municipio or 'Município a definir'} — "
        f"{solicitacao.tipo_evento or 'tipo a definir'}.",
        link=f"{link_registro}#despacho-dg",
        solicitacao=solicitacao,
        exceto=usuario,
    )
    return solicitacao


@transaction.atomic
def devolver(solicitacao, usuario, observacao):
    """A DG devolve para o criador ajustar e reenviar, com o motivo."""
    if solicitacao.status != StatusSolicitacao.AGUARDANDO_DESPACHO:
        raise TransicaoInvalida(
            "Somente solicitações aguardando despacho podem ser devolvidas."
        )
    observacao = (observacao or "").strip()
    if not observacao:
        raise ValidationError(
            "Informe o motivo da devolução para o solicitante ajustar."
        )
    anterior = _transicionar(solicitacao, StatusSolicitacao.DEVOLVIDA)
    solicitacao.save()
    registrar_historico(
        solicitacao,
        usuario,
        AcaoHistorico.DEVOLUCAO,
        status_anterior=anterior,
        status_novo=solicitacao.status,
        observacao=observacao,
    )
    notificar(
        [solicitacao.criado_por],
        f"Solicitação #{solicitacao.pk} enviada para correção",
        observacao,
        link=reverse("solicitacoes:editar", args=[solicitacao.pk]),
        solicitacao=solicitacao,
        exceto=usuario,
    )
    return solicitacao


def ajustar_quantidades_dg(solicitacao, usuario, quantidades):
    """A DG aceita ou altera a quantidade de servidores de cada equipe.

    `quantidades` mapeia equipe_id -> nova quantidade (int >= 1). Alterações
    são aplicadas e registradas no histórico; valores iguais são ignorados.
    """
    itens = {item.equipe_id: item for item in solicitacao.itens_equipe.select_related("equipe")}
    mudancas = []
    alteracoes = []
    for equipe_id, quantidade in (quantidades or {}).items():
        item = itens.get(equipe_id)
        if item is None:
            continue
        if not isinstance(quantidade, int) or quantidade < 1:
            raise ValidationError(
                f"Informe uma quantidade válida de servidores para {item.equipe}."
            )
        if item.quantidade_servidores != quantidade:
            mudancas.append(
                f"{item.equipe}: {item.quantidade_servidores or 0} → {quantidade}"
            )
            alteracoes.append({
                "campo": f"Servidores — {item.equipe}",
                "antes": _texto(item.quantidade_servidores),
                "depois": str(quantidade),
            })
            item.quantidade_servidores = quantidade
            item.save(update_fields=["quantidade_servidores"])
    if mudancas:
        solicitacao.recalcular_quantidade_servidores()
        # A solicitação mudou, ainda que só nos itens: quem estiver com o
        # "Editar" aberto precisa recarregar antes de salvar por cima.
        solicitacao.atualizado_em = timezone.now()
        type(solicitacao).objects.filter(pk=solicitacao.pk).update(
            atualizado_em=solicitacao.atualizado_em
        )
        registrar_historico(
            solicitacao,
            usuario,
            AcaoHistorico.AJUSTE_DG,
            alteracoes=alteracoes,
        )
    return mudancas


@transaction.atomic
def salvar_ajustes_dg(solicitacao, usuario, quantidades):
    """A DG salva ajustes de quantidade sem registrar a decisão ainda."""
    if solicitacao.status != StatusSolicitacao.AGUARDANDO_DESPACHO:
        raise TransicaoInvalida(
            "Somente solicitações aguardando despacho podem ser ajustadas pela DG."
        )
    return ajustar_quantidades_dg(solicitacao, usuario, quantidades)


@transaction.atomic
def despachar(solicitacao, usuario, decisao, observacao="", quantidades=None):
    if solicitacao.finalizada:
        raise TransicaoInvalida("A solicitação já foi finalizada e não aceita novo despacho.")
    if solicitacao.status != StatusSolicitacao.AGUARDANDO_DESPACHO:
        raise TransicaoInvalida(
            "Somente solicitações aguardando despacho podem receber decisão da DG."
        )
    if decisao not in STATUS_POR_DECISAO:
        raise ValidationError("Decisão inválida.")
    observacao = (observacao or "").strip()
    if decisao in DECISOES_COM_OBSERVACAO_OBRIGATORIA and not observacao:
        raise ValidationError(
            "A observação da DG é obrigatória para decisões de não atendimento ou cancelamento."
        )
    # A DG pode aceitar as quantidades propostas ou ajustá-las ao decidir.
    ajustar_quantidades_dg(solicitacao, usuario, quantidades)
    anterior = _transicionar(solicitacao, STATUS_POR_DECISAO[decisao])
    solicitacao.decisao_dg = decisao
    solicitacao.observacoes_dg = observacao
    solicitacao.decidido_por = usuario
    solicitacao.decidido_em = timezone.now()
    solicitacao.save()
    registrar_historico(
        solicitacao,
        usuario,
        AcaoHistorico.DECISAO,
        status_anterior=anterior,
        status_novo=solicitacao.status,
        observacao=observacao,
    )
    notificar(
        [solicitacao.criado_por],
        f"Solicitação #{solicitacao.pk}: {solicitacao.get_status_display().lower()}",
        observacao or "A Diretoria-Geral registrou a decisão.",
        link=reverse("solicitacoes:editar", args=[solicitacao.pk]),
        solicitacao=solicitacao,
        exceto=usuario,
    )
    _agendar_acompanhamento_da_viagem(solicitacao, usuario, observacao)
    return solicitacao


def _agendar_acompanhamento_da_viagem(solicitacao, usuario, observacao="") -> None:
    """Mexe na viagem só **depois** que a decisão estiver gravada."""
    transaction.on_commit(
        lambda: _acompanhar_viagem(solicitacao, usuario, observacao)
    )


def _acompanhar_viagem(solicitacao, usuario, observacao="") -> None:
    """A viagem segue a solicitação: nasce, se atualiza ou é cancelada.

    Deferiu com atendimento? A viagem nasce em rascunho — ou, se já existia
    de um despacho anterior, é atualizada com o que foi deferido agora. Não
    atendida ou cancelada? A viagem gerada é cancelada (ou o operador de
    Viagens é avisado, se ela já tem documentos).

    Roda depois da transação do despacho e engole o próprio erro de
    propósito: a decisão da DG é o ato administrativo e não pode se perder
    porque o módulo de Viagens teve um problema. Se falhar, fica no log,
    quem despachou é avisado e a geração pode ser repetida pela tela da
    solicitação.
    """
    from solicitacoes import integracao_viagens

    try:
        with transaction.atomic():
            if solicitacao.status == StatusSolicitacao.DEFERIDA_EM_ANDAMENTO:
                if integracao_viagens.viagem_da_solicitacao(solicitacao) is not None:
                    integracao_viagens.sincronizar_viagem(solicitacao, usuario)
                elif integracao_viagens.pode_gerar(solicitacao)[0]:
                    integracao_viagens.gerar_viagens(solicitacao, usuario)
            elif solicitacao.status in {
                StatusSolicitacao.NAO_ATENDIDA,
                StatusSolicitacao.CANCELADA,
            }:
                integracao_viagens.encerrar_viagem(solicitacao, usuario, observacao)
    except Exception:  # noqa: BLE001 - o despacho não depende disto
        logger.exception(
            "Falha ao atualizar a viagem da solicitação %s; o despacho foi mantido.",
            solicitacao.pk,
        )
        # A falha não pode ficar só no registro técnico: quem despachou sabe.
        notificar(
            [usuario],
            f"Solicitação #{solicitacao.pk}: a viagem não foi atualizada",
            "A decisão foi registrada, mas a viagem em Viagens não pôde ser "
            "gerada ou atualizada. Use \"Tentar de novo\" no cartão Viagem da solicitação ou "
            "confira a viagem pelo módulo de Viagens.",
            link=reverse("solicitacoes:editar", args=[solicitacao.pk]) + "#viagem",
            solicitacao=solicitacao,
        )


@transaction.atomic
def concluir_atendimento(solicitacao, usuario):
    """O solicitante confirma que o evento aconteceu e foi atendido."""
    if solicitacao.status != StatusSolicitacao.DEFERIDA_EM_ANDAMENTO:
        raise TransicaoInvalida(
            "Somente solicitações deferidas em andamento podem ser confirmadas."
        )
    if not solicitacao.evento_encerrado:
        ultimo = solicitacao.ultimo_dia_evento
        raise ValidationError(
            "A solicitação só pode ser marcada como atendida depois que o evento terminar"
            + (f" (após {ultimo:%d/%m/%Y})." if ultimo else ".")
        )
    anterior = _transicionar(solicitacao, StatusSolicitacao.ATENDIDA)
    solicitacao.save()
    registrar_historico(
        solicitacao,
        usuario,
        AcaoHistorico.CONCLUSAO,
        status_anterior=anterior,
        status_novo=solicitacao.status,
    )
    notificar(
        usuarios_do_grupo("GESTOR_DG", exceto=usuario),
        f"Solicitação #{solicitacao.pk}: atendimento confirmado",
        f"{solicitacao.municipio or 'Município a definir'} — o solicitante "
        "confirmou que o evento foi atendido.",
        link=reverse("solicitacoes:editar", args=[solicitacao.pk]),
        solicitacao=solicitacao,
        exceto=usuario,
    )
    return solicitacao


@transaction.atomic
def cancelar_evento(solicitacao, usuario, observacao):
    """Registra cancelamento apenas para autoria ou alçada autorizada."""
    from .permissions import STATUS_CANCELAVEIS, pode_cancelar

    if solicitacao.status not in STATUS_CANCELAVEIS:
        raise TransicaoInvalida(
            "Apenas solicitações em andamento podem ser canceladas."
        )
    if not pode_cancelar(usuario, solicitacao):
        raise PermissionDenied("Você não pode cancelar esta solicitação.")
    observacao = (observacao or "").strip()
    if not observacao:
        raise ValidationError("Informe o motivo do cancelamento do evento.")
    anterior = _transicionar(solicitacao, StatusSolicitacao.CANCELADA)
    solicitacao.save()
    registrar_historico(
        solicitacao,
        usuario,
        AcaoHistorico.CANCELAMENTO,
        status_anterior=anterior,
        status_novo=solicitacao.status,
        observacao=observacao,
    )
    interessados = set(usuarios_do_grupo("GESTOR_DG"))
    interessados.add(solicitacao.criado_por)
    interessados.discard(usuario)
    notificar(
        list(interessados),
        f"Solicitação #{solicitacao.pk}: evento cancelado",
        observacao,
        link=reverse("solicitacoes:editar", args=[solicitacao.pk]),
        solicitacao=solicitacao,
        exceto=usuario,
    )
    # Evento cancelado depois do deferimento: a viagem gerada não vai acontecer.
    _agendar_acompanhamento_da_viagem(solicitacao, usuario, observacao)
    return solicitacao


@transaction.atomic
def transferir(solicitacao, usuario, novo_responsavel, motivo=""):
    """Passa a solicitação para outro responsável, com histórico e aviso.

    O responsável é quem a criou (`criado_por`): é ele quem edita, envia,
    reenvia e confirma o atendimento. O rascunho original continua no
    histórico ("Rascunho criado" por quem criou).
    """
    from .permissions import pode_transferir

    if not pode_transferir(usuario, solicitacao):
        raise PermissionDenied("Você não pode transferir esta solicitação.")
    if novo_responsavel is None or not novo_responsavel.is_active:
        raise ValidationError("Escolha um usuário ativo para ser o novo responsável.")
    anterior = solicitacao.criado_por
    if novo_responsavel.pk == anterior.pk:
        raise ValidationError("Essa pessoa já é a responsável pela solicitação.")
    motivo = (motivo or "").strip()
    solicitacao.criado_por = novo_responsavel
    solicitacao.save(update_fields=["criado_por", "atualizado_em"])
    # De quem e para quem nas alterações; por quem no usuário; o motivo no texto.
    registrar_historico(
        solicitacao,
        usuario,
        AcaoHistorico.TRANSFERENCIA,
        observacao=f"Motivo: {motivo}" if motivo else "",
        alteracoes=[
            {"campo": "Responsável", "antes": str(anterior), "depois": str(novo_responsavel)}
        ],
    )
    link = reverse("solicitacoes:editar", args=[solicitacao.pk])
    notificar(
        [novo_responsavel],
        f"Solicitação #{solicitacao.pk} transferida para você",
        f"{usuario} passou a solicitação para você"
        + (f": {motivo}" if motivo else ".")
        + " Agora é você quem edita, envia e confirma o atendimento.",
        link=link,
        solicitacao=solicitacao,
        exceto=usuario,
    )
    notificar(
        [anterior],
        f"Solicitação #{solicitacao.pk} transferida para {novo_responsavel}",
        motivo or f"{usuario} registrou a transferência.",
        link=link,
        solicitacao=solicitacao,
        exceto=usuario,
    )
    return solicitacao


# O que a cópia leva: o evento que se repete, sem datas, protocolo, decisão
# nem anexos (esses são de cada pedido).
CAMPOS_DUPLICADOS = [
    "municipio", "tipo_evento", "local_evento", "solicitante_nome",
    "solicitante_cargo_unidade", "contato", "orgao_responsavel", "unidade_movel",
    "unidade_movel_designada", "descricao_complementar", "tipo_operacao",
    "quantidade_cin", "motorista",
]


@transaction.atomic
def duplicar(solicitacao, usuario):
    """Rascunho novo com os dados, serviços e equipes de uma solicitação.

    Para eventos que se repetem: falta só ajustar as datas e enviar.
    """
    nova = SolicitacaoEvento(
        criado_por=usuario,
        **{campo: getattr(solicitacao, campo) for campo in CAMPOS_DUPLICADOS},
    )
    nova.save()
    for item in solicitacao.itens_servico.all():
        nova.itens_servico.create(servico_id=item.servico_id, observacao=item.observacao)
    equipes = [
        nova.itens_equipe.model(
            solicitacao=nova,
            equipe_id=item.equipe_id,
            quantidade_servidores=item.quantidade_servidores,
            observacao=item.observacao,
        )
        for item in solicitacao.itens_equipe.all()
    ]
    nova.itens_equipe.model.objects.bulk_create(equipes)
    nova.recalcular_quantidade_servidores()
    registrar_historico(
        nova,
        usuario,
        AcaoHistorico.CRIACAO,
        status_novo=nova.status,
        observacao=f"Copiada da #{solicitacao.pk}",
    )
    return nova


STATUS_REABRIVEIS = {
    StatusSolicitacao.AGUARDANDO_DESPACHO,
    StatusSolicitacao.DEFERIDA_EM_ANDAMENTO,
}


@transaction.atomic
def reenviar_apos_edicao(solicitacao, usuario, alteracoes):
    """Depois do envio, o pedido só muda pelo "Editar" — e volta para a DG.

    O despacho vale para o que estava escrito quando ele foi dado: mudou o
    evento, os serviços ou as equipes, a DG precisa despachar de novo — e até
    lá a solicitação não pode ser marcada como atendida.
    """
    if solicitacao.status not in STATUS_REABRIVEIS:
        raise TransicaoInvalida(
            "Somente solicitações enviadas e ainda em andamento podem ser editadas."
        )
    faltas = pendencias_para_envio(solicitacao)
    if faltas:
        raise ValidationError(
            "Preencha os campos obrigatórios antes de enviar: " + ", ".join(faltas) + "."
        )
    anterior = solicitacao.status
    solicitacao.status = StatusSolicitacao.AGUARDANDO_DESPACHO
    solicitacao.decisao_dg = DecisaoDG.PENDENTE
    solicitacao.observacoes_dg = ""
    solicitacao.decidido_em = None
    solicitacao.decidido_por = None
    solicitacao.save(
        update_fields=[
            "status", "decisao_dg", "observacoes_dg", "decidido_em",
            "decidido_por", "atualizado_em",
        ]
    )
    registrar_historico(
        solicitacao,
        usuario,
        AcaoHistorico.REENVIO,
        status_anterior=anterior,
        status_novo=solicitacao.status,
        observacao=(
            "Alterada depois do despacho: aguarda novo despacho da DG."
            if anterior == StatusSolicitacao.DEFERIDA_EM_ANDAMENTO
            else ""
        ),
        alteracoes=alteracoes,
    )
    notificar(
        usuarios_do_grupo("GESTOR_DG"),
        f"Solicitação #{solicitacao.pk} alterada: aguarda novo despacho",
        # O sino corta no limite dele; a lista inteira fica no histórico.
        "; ".join(a["campo"] for a in alteracoes),
        link=reverse("solicitacoes:editar", args=[solicitacao.pk]) + "#despacho-dg",
        solicitacao=solicitacao,
        exceto=usuario,
    )
    return solicitacao


def montar_timeline(solicitacao=None):
    """Etapas da timeline lateral a partir do status e histórico reais.

    Cada etapa vencida traz quem fez, quando e a observação do histórico —
    o mesmo rastro do processo que a tela de cadastro registra. Sem
    solicitação (tela de criação), devolve o estado inicial de rascunho.
    """

    def registro_de(*acoes):
        """O registro **mais recente** destas ações: depois de um reenvio ou
        de um novo despacho, a etapa mostra o último, não o primeiro."""
        if not solicitacao or not solicitacao.pk:
            return None
        return next(
            (h for h in reversed(list(solicitacao.historico.all())) if h.acao in acoes),
            None,
        )

    def detalhes(registro):
        """Data/hora, autor e observação de um registro do histórico."""
        if registro is None:
            return {}
        return {
            "quando": timezone.localtime(registro.criado_em).strftime(
                "%d/%m/%Y %H:%M"
            ),
            "usuario": str(registro.usuario) if registro.usuario else "",
            "observacao": registro.observacao,
        }

    status = solicitacao.status if solicitacao else StatusSolicitacao.RASCUNHO
    rascunho = status == StatusSolicitacao.RASCUNHO
    devolvida = status == StatusSolicitacao.DEVOLVIDA
    aguardando = status == StatusSolicitacao.AGUARDANDO_DESPACHO
    deferida = status == StatusSolicitacao.DEFERIDA_EM_ANDAMENTO
    finalizada = bool(solicitacao) and solicitacao.finalizada

    # Origem da etapa de envio, em ordem de preferência: o envio (ou o
    # reenvio depois de alterada); nas importadas da planilha, a importação;
    # só na falta dos dois, a criação do rascunho.
    registro_envio = (
        registro_de(AcaoHistorico.ENVIO, AcaoHistorico.REENVIO)
        or registro_de(AcaoHistorico.IMPORTACAO)
        or registro_de(AcaoHistorico.CRIACAO)
    )
    registro_decisao = registro_de(AcaoHistorico.DECISAO)
    # O que encerrou: a confirmação do atendimento, o cancelamento do evento
    # ou a própria decisão — o que veio por último.
    registro_final = registro_de(
        AcaoHistorico.CONCLUSAO, AcaoHistorico.CANCELAMENTO, AcaoHistorico.DECISAO
    )

    # As quatro etapas existem sempre, desde o rascunho: quem abre a tela vê o
    # caminho inteiro e onde o pedido está. O que muda é o estado de cada uma.
    if devolvida:
        subtitulo_envio = "Enviada para correção — ajuste e reenvie"
    elif rascunho:
        subtitulo_envio = "Aguardando preenchimento"
    else:
        subtitulo_envio = "Concluída"

    # A etapa do deferimento só se acende quando a DG deferiu de fato: pedido
    # não atendido não passou por ela.
    deferiu = bool(solicitacao) and (
        deferida
        or status == StatusSolicitacao.ATENDIDA
        or solicitacao.decisao_dg == DecisaoDG.ATENDER
    )

    rotulos_finais = {
        StatusSolicitacao.ATENDIDA: "Atendida",
        StatusSolicitacao.NAO_ATENDIDA: "Não atendida",
        StatusSolicitacao.CANCELADA: "Cancelada",
    }

    etapas = [
        {
            "titulo": "Enviar para a DG",
            "subtitulo": subtitulo_envio,
            "estado": "atual" if rascunho or devolvida else "concluido",
            **(detalhes(registro_envio) if not (rascunho or devolvida) else {}),
        },
        {
            "titulo": "Aguardando despacho DG",
            "subtitulo": "Concluída" if deferida or finalizada else "Pendente",
            "estado": (
                "concluido"
                if deferida or finalizada
                else ("atual" if aguardando else "pendente")
            ),
            **(detalhes(registro_envio) if aguardando else {}),
        },
        {
            "titulo": "Deferida — em andamento",
            "subtitulo": (
                "Deferida pela DG" if deferiu else "Depende do despacho da DG"
            ),
            "estado": (
                "atual" if deferida else ("concluido" if deferiu else "pendente")
            ),
            **(detalhes(registro_decisao) if deferiu else {}),
        },
        {
            "titulo": (
                rotulos_finais[status] if finalizada else "Atendimento do evento"
            ),
            "subtitulo": (
                "Encerrada" if finalizada else "Confirme após o evento acontecer"
            ),
            "estado": "concluido" if finalizada else "pendente",
            **(detalhes(registro_final) if finalizada else {}),
        },
    ]
    return etapas
