"""Regras de negócio do módulo de Coffee Break.

Concentra o que precisa ser testável fora das views: a derivação da
situação financeira e a validação transacional do saldo do lote.
"""

import re
from datetime import date

from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.utils import timezone

from .models import (
    AcaoHistoricoCoffeeBreak,
    HistoricoCoffeeBreak,
    LoteCoffeeBreak,
    SituacaoFinanceira,
)

# Situação -> sufixo dos status-badges já existentes no design system.
CSS_SITUACAO = {
    SituacaoFinanceira.AGUARDANDO_NOTA_FISCAL: "aguardando_despacho",
    SituacaoFinanceira.AGUARDANDO_PROTOCOLO: "aguardando_despacho",
    SituacaoFinanceira.AGUARDANDO_ATESTO: "aguardando_despacho",
    SituacaoFinanceira.AGUARDANDO_ORDEM_BANCARIA: "deferida_em_andamento",
    SituacaoFinanceira.AGUARDANDO_ENVIO_EMPRESA: "deferida_em_andamento",
    SituacaoFinanceira.CONCLUIDA: "atendida",
    SituacaoFinanceira.CANCELADA: "cancelada",
}


def situacao_financeira(solicitacao):
    """Deriva a situação do fluxo de pagamento a partir dos marcos.

    A planilha não tem coluna de status: a leitura é feita pelos campos
    preenchidos, na ordem do fluxo real — NF → protocolo → atesto →
    ordem bancária → envio à empresa.
    """
    if solicitacao.cancelada:
        return SituacaoFinanceira.CANCELADA
    if solicitacao.data_envio_empresa:
        return SituacaoFinanceira.CONCLUIDA
    if solicitacao.data_ordem_bancaria:
        return SituacaoFinanceira.AGUARDANDO_ENVIO_EMPRESA
    if solicitacao.data_atesto_gaf:
        return SituacaoFinanceira.AGUARDANDO_ORDEM_BANCARIA
    if solicitacao.protocolo_pagamento.strip():
        return SituacaoFinanceira.AGUARDANDO_ATESTO
    if solicitacao.numero_nota_fiscal.strip():
        return SituacaoFinanceira.AGUARDANDO_PROTOCOLO
    return SituacaoFinanceira.AGUARDANDO_NOTA_FISCAL


def validar_saldo(lote, quantidade, excluir_pk=None):
    """Garante que a quantidade cabe no saldo do lote.

    Deve rodar dentro de uma transação com o lote travado
    (``select_for_update``) para não haver corrida entre solicitações
    simultâneas — use :func:`salvar_com_saldo`.
    """
    consumo = lote.solicitacoes.filter(cancelada=False)
    if excluir_pk:
        consumo = consumo.exclude(pk=excluir_pk)
    consumido = consumo.aggregate(total=models.Sum("quantidade"))["total"] or 0
    restante = lote.quantidade_total - consumido
    if quantidade > restante:
        raise ValidationError(
            {
                "quantidade": (
                    f"Quantidade acima do saldo do lote: restam {restante} "
                    f"de {lote.quantidade_total} unidades."
                )
            }
        )


def salvar_com_saldo(solicitacao):
    """Salva a solicitação consumindo saldo com trava no lote.

    Trava a linha do lote, revalida o saldo já com concorrentes
    serializados e só então persiste — a validação e a escrita ficam na
    mesma transação.
    """
    with transaction.atomic():
        lote = LoteCoffeeBreak.objects.select_for_update().get(
            pk=solicitacao.lote_id
        )
        if not solicitacao.cancelada:
            validar_saldo(lote, solicitacao.quantidade, excluir_pk=solicitacao.pk)
        if not solicitacao.numero:
            # A numeração é uma só para todos os lotes: trava a configuração
            # (linha única) para dois pedidos simultâneos não pegarem o mesmo número.
            from .models import ConfiguracaoCoffeeBreak

            ConfiguracaoCoffeeBreak.objects.select_for_update().filter(pk=1).exists()
            solicitacao.numero = proximo_numero(solicitacao.data_solicitacao.year)
        solicitacao.save()
    return solicitacao


def registrar_historico(solicitacao, usuario, acao, descricao=""):
    return HistoricoCoffeeBreak.objects.create(
        solicitacao=solicitacao,
        usuario=usuario,
        acao=acao,
        descricao=(descricao or "").strip(),
    )


def cancelar(solicitacao, usuario, motivo=""):
    """Cancelamento auditável: sai do consumo, mas permanece no histórico."""
    if solicitacao.cancelada:
        raise ValidationError("A solicitação já está cancelada.")
    if solicitacao.concluida:
        raise ValidationError(
            "Solicitações com o fluxo financeiro concluído não podem ser canceladas."
        )
    motivo = (motivo or "").strip()
    if not motivo:
        raise ValidationError("Informe o motivo do cancelamento.")
    solicitacao.cancelada = True
    solicitacao.cancelada_em = timezone.now()
    solicitacao.cancelada_por = usuario
    solicitacao.motivo_cancelamento = motivo[:255]
    solicitacao.save(
        update_fields=[
            "cancelada",
            "cancelada_em",
            "cancelada_por",
            "motivo_cancelamento",
            "atualizado_em",
        ]
    )
    registrar_historico(
        solicitacao,
        usuario,
        AcaoHistoricoCoffeeBreak.CANCELAMENTO,
        motivo,
    )
    return solicitacao


def reativar(solicitacao, usuario=None):
    """Desfaz um cancelamento, revalidando o saldo do lote."""
    if not solicitacao.cancelada:
        raise ValidationError("A solicitação não está cancelada.")
    if (solicitacao.quantidade or 0) < 1:
        raise ValidationError(
            "Informe uma quantidade válida antes de reativar a solicitação."
        )
    with transaction.atomic():
        lote = LoteCoffeeBreak.objects.select_for_update().get(
            pk=solicitacao.lote_id
        )
        validar_saldo(lote, solicitacao.quantidade, excluir_pk=solicitacao.pk)
        solicitacao.cancelada = False
        solicitacao.cancelada_em = None
        solicitacao.cancelada_por = None
        solicitacao.motivo_cancelamento = ""
        solicitacao.save(
            update_fields=[
                "cancelada",
                "cancelada_em",
                "cancelada_por",
                "motivo_cancelamento",
                "atualizado_em",
            ]
        )
        registrar_historico(
            solicitacao,
            usuario,
            AcaoHistoricoCoffeeBreak.REATIVACAO,
            "Saldo revalidado e solicitação reativada.",
        )
    return solicitacao


# Percentual de saldo abaixo do qual o painel destaca o lote.
LIMIAR_ALERTA_SALDO = 15


def lotes_em_alerta(lotes_anotados):
    """Lotes ativos com saldo igual ou abaixo do limiar de alerta."""
    em_alerta = []
    for lote in lotes_anotados:
        if not lote.quantidade_total:
            continue
        percentual_restante = lote.restante * 100 / lote.quantidade_total
        if percentual_restante <= LIMIAR_ALERTA_SALDO:
            em_alerta.append(lote)
    return em_alerta


# ---------------------------------------------------------------------------
# Lote pelo município
# ---------------------------------------------------------------------------

def _distancia_km(a, b):
    """Distância em linha reta entre dois municípios com coordenadas."""
    from math import asin, cos, radians, sin, sqrt

    lat1, lon1, lat2, lon2 = map(
        lambda v: radians(float(v)), (a.latitude, a.longitude, b.latitude, b.longitude)
    )
    h = sin((lat2 - lat1) / 2) ** 2 + cos(lat1) * cos(lat2) * sin((lon2 - lon1) / 2) ** 2
    return 6371 * 2 * asin(sqrt(h))


def _tem_coordenadas(municipio):
    return municipio.latitude is not None and municipio.longitude is not None


class EscolhaDeLotes:
    """Escolhe o lote de cada município a partir dos lotes ativos.

    1. o lote que lista o município (se houver mais de um, o do exercício da
       data e, depois, o de maior saldo);
    2. senão, o lote cuja cidade listada estiver mais perto (precisa das
       coordenadas dos municípios).

    Carrega os lotes uma vez só, para servir a lista inteira de municípios do
    formulário.
    """

    def __init__(self, data=None, lotes=None):
        self.ano = str((data or timezone.localdate()).year)
        if lotes is None:
            lotes = (
                LoteCoffeeBreak.objects.filter(ativo=True)
                .com_consumo()
                .select_related("contrato__fornecedor")
                .prefetch_related("municipios")
            )
        self.lotes = list(lotes)
        self._por_municipio = {}
        for lote in self.lotes:
            for municipio in lote.municipios.all():
                self._por_municipio.setdefault(municipio.pk, []).append(lote)

    def _preferido(self, lotes):
        return max(
            lotes,
            key=lambda l: (l.exercicio == self.ano, getattr(l, "restante", 0)),
        )

    def escolher(self, municipio):
        """(lote, distância em km — 0 quando o lote lista o município) ou (None, None)."""
        if municipio is None:
            return None, None
        exatos = self._por_municipio.get(municipio.pk)
        if exatos:
            return self._preferido(exatos), 0
        if not _tem_coordenadas(municipio):
            return None, None
        melhor = None
        for lote in self.lotes:
            for sede in lote.municipios.all():
                if not _tem_coordenadas(sede):
                    continue
                distancia = _distancia_km(municipio, sede)
                chave = (round(distancia), lote.exercicio != self.ano)
                if melhor is None or chave < melhor[0]:
                    melhor = (chave, lote, distancia, sede)
        if melhor is None:
            return None, None
        _chave, lote, distancia, sede = melhor
        lote.sede_mais_proxima = sede
        return lote, round(distancia)


def escolher_lote(municipio, data=None):
    return EscolhaDeLotes(data).escolher(municipio)


# ---------------------------------------------------------------------------
# Numeração da solicitação / ordem de serviço
# ---------------------------------------------------------------------------

_NUMERO = re.compile(r"^\s*(\d+)\s*/\s*(\d{4})\s*$")


def partes_numero(numero):
    """(sequência, ano) de um "NN/AAAA"; None para texto em outro formato."""
    achado = _NUMERO.match(numero or "")
    return (int(achado.group(1)), int(achado.group(2))) if achado else None


def formatar_numero(sequencia, ano):
    return f"{sequencia:02d}/{ano}"


def proxima_sequencia(ano):
    """A próxima sequência da OS no ano: uma numeração só, de todos os lotes
    (1, 2, 3...). Vale a maior já usada + 1 — quem pula para 12 faz a
    seguinte ser 13."""
    from .models import SolicitacaoCoffeeBreak

    maior = 0
    for numero in SolicitacaoCoffeeBreak.objects.filter(numero__endswith=f"/{ano}").values_list("numero", flat=True):
        partes = partes_numero(numero)
        if partes and partes[1] == ano:
            maior = max(maior, partes[0])
    return maior + 1


def proximo_numero(ano):
    """"NN/AAAA": a próxima OS do ano, na numeração única."""
    return formatar_numero(proxima_sequencia(ano), ano)


def proxima_sequencia_oficio(ano):
    """O próximo ofício do Coffee Break no ano: o maior já usado + 1."""
    from .models import SolicitacaoCoffeeBreak

    maior = 0
    for numero in SolicitacaoCoffeeBreak.objects.filter(numero_oficio__endswith=f"/{ano}").values_list("numero_oficio", flat=True):
        partes = partes_numero(numero)
        if partes and partes[1] == ano:
            maior = max(maior, partes[0])
    return maior + 1


def oficio_em_uso(numero, excluir_pk=None):
    """A solicitação de fora do pagamento conjunto que já tem este número de
    ofício, ou None (as do mesmo pagamento dividem o ofício)."""
    from .models import SolicitacaoCoffeeBreak

    consulta = SolicitacaoCoffeeBreak.objects.filter(numero_oficio=numero)
    if excluir_pk:
        atual = SolicitacaoCoffeeBreak.objects.filter(pk=excluir_pk).first()
        grupo = [s.pk for s in atual.grupo_pagamento()] if atual else [excluir_pk]
        consulta = consulta.exclude(pk__in=grupo)
    return consulta.first()


# ---------------------------------------------------------------------------
# Pagamento conjunto: várias OS do mesmo lote num ofício e num protocolo
# ---------------------------------------------------------------------------

# O que é do pagamento (igual em todas as OS do grupo); a nota e o certifico
# são de cada uma.
CAMPOS_ESPELHADOS = (
    "numero_oficio", "data_oficio", "protocolo_pcpr_oficio",
    "protocolo_pagamento", "data_atesto_gaf", "data_ordem_bancaria", "data_envio_empresa",
)


def espelhar(solicitacao, campos=None):
    """Copia os campos do pagamento para as outras OS do mesmo pagamento."""
    from .models import SolicitacaoCoffeeBreak

    campos = [c for c in (campos or CAMPOS_ESPELHADOS) if c in CAMPOS_ESPELHADOS]
    outras = [s.pk for s in solicitacao.grupo_pagamento() if s.pk != solicitacao.pk]
    if not campos or not outras:
        return 0
    valores = {campo: getattr(solicitacao, campo) for campo in campos}
    return SolicitacaoCoffeeBreak.objects.filter(pk__in=outras).update(atualizado_em=timezone.now(), **valores)


def sincronizar_protocolo(solicitacao, usuario=None):
    """O protocolo de pagamento é o do ofício (etapa 2): com a nota
    registrada, o protocolo do ofício vira o do pagamento, em todas as OS do
    mesmo pagamento."""
    from .models import SolicitacaoCoffeeBreak

    from core.utils.masks import normalize_protocolo

    protocolo = (solicitacao.protocolo_pcpr_oficio or "").strip()
    if not protocolo or not solicitacao.numero_nota_fiscal.strip() or solicitacao.protocolo_pagamento == protocolo:
        return False
    # O "PCPR protocolo n.º" em outro formato (o número interno da PCPR,
    # "2026.050880.000") não é o do eProtocolo: não troca o protocolo de
    # pagamento já gravado (o do processo, vindo da importação).
    if solicitacao.protocolo_pagamento.strip() and len(normalize_protocolo(protocolo)) != 9:
        return False
    SolicitacaoCoffeeBreak.objects.filter(pk=solicitacao.pk).update(protocolo_pagamento=protocolo, atualizado_em=timezone.now())
    solicitacao.protocolo_pagamento = protocolo
    espelhar(solicitacao, ["protocolo_pagamento"])
    registrar_historico(solicitacao, usuario, AcaoHistoricoCoffeeBreak.ATUALIZACAO, f"Protocolo de pagamento: {protocolo} (o do ofício).")
    return True


def marcar_atesto(solicitacao, usuario=None, dia=None):
    """Atesto e envio ao GAF: o dia em que a etapa 3 se conclui — quando os
    arquivos do protocolo são baixados. Só com o protocolo registrado, e
    uma vez (a data da primeira vez fica)."""
    from .models import SolicitacaoCoffeeBreak

    if solicitacao.data_atesto_gaf or not solicitacao.protocolo_pagamento or solicitacao.cancelada:
        return False
    dia = dia or timezone.localdate()
    SolicitacaoCoffeeBreak.objects.filter(pk=solicitacao.pk).update(data_atesto_gaf=dia, atualizado_em=timezone.now())
    solicitacao.data_atesto_gaf = dia
    espelhar(solicitacao, ["data_atesto_gaf"])
    registrar_historico(solicitacao, usuario, AcaoHistoricoCoffeeBreak.ATUALIZACAO, f"Atesto e envio ao GAF: {dia:%d/%m/%Y} (arquivos do protocolo baixados).")
    return True


def candidatas_ao_pagamento(solicitacao):
    """As OS que podem ir no mesmo ofício: do mesmo lote, sem pagamento
    (sem protocolo, não pagas), não canceladas nem em outro pagamento."""
    from .models import SolicitacaoCoffeeBreak

    grupo = {s.pk for s in solicitacao.grupo_pagamento()}
    return (
        SolicitacaoCoffeeBreak.objects.filter(lote_id=solicitacao.lote_id, cancelada=False, data_envio_empresa__isnull=True)
        .filter(protocolo_pagamento="")
        .exclude(pk__in=grupo)
        .filter(pagamento_com__isnull=True, pagamento_junto__isnull=True)
        .order_by("numero")
    )


@transaction.atomic
def definir_pagamento_conjunto(solicitacao, outras_pks, usuario=None):
    """Deixa no mesmo pagamento de `solicitacao` exatamente as OS `outras_pks`.

    A principal continua a mesma quando fica no grupo; se sai, esta passa a
    ser a principal. Quem entra recebe o ofício, o protocolo e os marcos do
    pagamento; quem sai volta a ter o pagamento próprio (com os mesmos
    dados, para editar à parte).
    """
    from .models import SolicitacaoCoffeeBreak

    atual = solicitacao.grupo_pagamento()
    alvo = {solicitacao.pk} | {int(pk) for pk in outras_pks}
    antigos = {s.pk for s in atual}
    novos = alvo - antigos
    validas = set(candidatas_ao_pagamento(solicitacao).filter(pk__in=novos).values_list("pk", flat=True))
    if novos - validas:
        raise ValidationError("Só entram OS do mesmo lote, sem protocolo de pagamento e fora de outro pagamento conjunto.")
    principal_antigo = solicitacao.principal_do_pagamento
    principal = principal_antigo if principal_antigo.pk in alvo else solicitacao
    saem = antigos - alvo
    if saem:
        SolicitacaoCoffeeBreak.objects.filter(pk__in=saem).update(pagamento_com=None, atualizado_em=timezone.now())
    SolicitacaoCoffeeBreak.objects.filter(pk=principal.pk).update(pagamento_com=None)
    membros = alvo - {principal.pk}
    if membros:
        SolicitacaoCoffeeBreak.objects.filter(pk__in=membros).update(pagamento_com=principal, atualizado_em=timezone.now())
    principal.refresh_from_db()
    espelhar(principal)
    for pk in novos | saem:
        outra = SolicitacaoCoffeeBreak.objects.get(pk=pk)
        registrar_historico(
            outra, usuario, AcaoHistoricoCoffeeBreak.ATUALIZACAO,
            f"Pagamento junto com a OS {principal.numero} (mesmo ofício e protocolo)." if pk in novos
            else "Saiu do pagamento conjunto: ofício e protocolo próprios.",
        )
    return principal


def numero_em_uso(numero, excluir_pk=None):
    """A solicitação que já tem este número de OS (de qualquer lote), ou None."""
    from .models import SolicitacaoCoffeeBreak

    consulta = SolicitacaoCoffeeBreak.objects.filter(numero=numero)
    if excluir_pk:
        consulta = consulta.exclude(pk=excluir_pk)
    return consulta.first()


# ---------------------------------------------------------------------------
# Andamento: o próximo marco do fluxo, no desenho das Palestras
# ---------------------------------------------------------------------------

# Os marcos na ordem do fluxo real: (campo, etapa no stepper, rótulo do campo, tipo).
MARCOS = [
    ("numero_nota_fiscal", "Nota fiscal", "Número da nota fiscal", "text"),
    ("protocolo_pagamento", "Protocolo", "Protocolo de pagamento", "text"),
    ("data_atesto_gaf", "Atesto", "Atesto e envio ao GAF em", "date"),
    ("data_ordem_bancaria", "Ordem bancária", "Ordem bancária emitida em", "date"),
    ("data_envio_empresa", "Paga", "OB enviada à empresa em", "date"),
]


def _preenchido(solicitacao, campo):
    valor = getattr(solicitacao, campo)
    return bool(valor.strip()) if isinstance(valor, str) else valor is not None


def etapas(solicitacao):
    """O stepper: um marco conta como feito quando ele ou um posterior está preenchido.

    Registros da planilha não têm a data da OS, mas já andaram adiante: o
    marco pulado aparece concluído, como o resto do caminho.
    """
    feitos = [_preenchido(solicitacao, campo) for campo, *_ in MARCOS]
    ultimo = max((i for i, f in enumerate(feitos) if f), default=-1)
    saida = [{"titulo": "Pedido", "estado": "concluido"}]
    for i, (_campo, titulo, *_resto) in enumerate(MARCOS):
        if i <= ultimo:
            estado = "concluido"
        elif i == ultimo + 1 and not solicitacao.cancelada:
            estado = "atual"
        else:
            estado = "pendente"
        saida.append({"titulo": titulo, "estado": estado})
    return saida


def proximo_marco(solicitacao):
    """(campo, rótulo, tipo) do marco que falta, ou None quando acabou."""
    if solicitacao.cancelada:
        return None
    feitos = [_preenchido(solicitacao, campo) for campo, *_ in MARCOS]
    ultimo = max((i for i, f in enumerate(feitos) if f), default=-1)
    if ultimo + 1 >= len(MARCOS):
        return None
    campo, _titulo, rotulo, tipo = MARCOS[ultimo + 1]
    return {"campo": campo, "rotulo": rotulo, "tipo": tipo}


def ultima_anotacao(solicitacao):
    ultima = solicitacao.historico.filter(
        acao=AcaoHistoricoCoffeeBreak.ATUALIZACAO, descricao__contains=" — "
    ).order_by("-criado_em", "-pk").first()
    return ultima.descricao.split(" — ", 1)[1] if ultima else ""


@transaction.atomic
def registrar_marco(solicitacao, usuario, valor, anotacao=""):
    """Grava o próximo marco (com as regras de ordem do modelo) e o histórico."""
    marco = proximo_marco(solicitacao)
    if marco is None:
        raise ValidationError("Esta solicitação não tem marco a registrar.")
    valor = (valor or "").strip() if isinstance(valor, str) else valor
    if not valor:
        raise ValidationError(f"Informe: {marco['rotulo'].lower()}.")
    if marco["tipo"] == "date" and isinstance(valor, str):
        try:
            valor = date.fromisoformat(valor)
        except ValueError as exc:
            raise ValidationError("Data inválida.") from exc
    setattr(solicitacao, marco["campo"], valor)
    try:
        solicitacao.full_clean(exclude=["lote", "municipio", "criado_por"])
    except ValidationError as erro:
        raise ValidationError(
            [m for mensagens in erro.message_dict.values() for m in mensagens]
        ) from erro
    solicitacao.save()
    # Marco do pagamento vale para todas as OS do mesmo pagamento.
    espelhar(solicitacao, [marco["campo"]])
    texto = f"{marco['rotulo']}: {valor:%d/%m/%Y}" if marco["tipo"] == "date" else f"{marco['rotulo']}: {valor}"
    anotacao = (anotacao or "").strip()
    registrar_historico(
        solicitacao, usuario, AcaoHistoricoCoffeeBreak.ATUALIZACAO,
        f"{texto} — {anotacao}" if anotacao else texto,
    )
    return solicitacao
