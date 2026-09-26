"""Avisos da prestação de contas no sino (e por e-mail) da equipe de viagens (m085, m090).

O que vai para o sino, por servidor (a prestação é individual):

- **Diárias liberadas** — na hora, quando a data de liberação é preenchida;
- **Saque vence em N dias** e **Prazo de saque vencido** — sem comprovante anexado;
- **Prestação vencida** — passou dos 3 dias úteis depois do fim do saque (m094);
- **Documentos gerados** — diário e RT prontos, falta mandar ao servidor e o
  assinado voltar; e **Documentos assinados recebidos** — RT e diário assinados
  anexados.

E, da viagem (m096): **Amanhã sai a viagem** — lembrete de mandar ao motorista o
link do diário no celular — e **A equipe chegou** — hora de começar a prestação.

Os de prazo, de documentos e de viagem saem do comando `avisar_prazos_prestacao`
(cron/timer do deploy). Cada aviso sai uma vez só: o título leva o servidor, o
ofício e a data, e o que já está no sino não se repete.
"""

from __future__ import annotations

import datetime

from django.urls import reverse
from django.utils import timezone

from core.models import Notificacao
from core.notificacoes import LIMITE_TITULO
from core.notificacoes import _cabe
from core.notificacoes import notificar
from core.notificacoes import usuarios_do_grupo

GRUPO = "VIAGENS_OPERADOR"


def _link(ps) -> str:
    return reverse("viagens_prestacoes:documentos_servidor", args=[ps.pk])


def _avisar_uma_vez(ps, titulo, mensagem, *, exceto=None, link=None) -> bool:
    link = link or _link(ps)
    if Notificacao.objects.filter(titulo=_cabe(titulo, LIMITE_TITULO), link=link).exists():
        return False
    return bool(notificar(usuarios_do_grupo(GRUPO), titulo, mensagem, link=link, exceto=exceto))


def _quem(ps) -> str:
    return f"{ps.servidor.nome} (Ofício {ps.prestacao.oficio.numero_formatado})"


def avisar_diarias_liberadas(ps, *, autor=None) -> bool:
    """Diárias liberadas: sai quando a data de liberação é preenchida."""
    if not ps.data_liberacao_diarias:
        return False
    prazo = f" Prazo para saque: {ps.prazo_limite_saque:%d/%m/%Y}." if ps.prazo_limite_saque else ""
    return _avisar_uma_vez(
        ps,
        f"Diárias liberadas: {_quem(ps)} em {ps.data_liberacao_diarias:%d/%m}",
        f"Avise o servidor da liberação.{prazo}",
        exceto=autor,
    )


def avisar_prazos(hoje: datetime.date | None = None) -> int:
    """Os avisos diários de prazo e de documentos. Devolve quantos saíram."""
    from .completude import ASSINADO, GERADO, situacao_diario, situacao_rt
    from .models import PrestacaoDocumentoAnexo as Anexo
    from .models import PrestacaoServidor
    from .prazos import DIAS_AVISO_SAQUE, prazo_para_prestar

    hoje = hoje or timezone.localdate()
    enviados = 0
    servidores = (
        PrestacaoServidor.objects.filter(finalizada=False, arquivada=False, prestacao__oficio__cancelado=False)
        .select_related("servidor", "prestacao__oficio", "prestacao__diario_bordo", "prestacao__relatorio_tecnico")
        .prefetch_related("documentos_anexos", "prestacao__documentos_anexos", "prestacao__diario_bordo__trechos")
    )
    for ps in servidores:
        tem_comprovante = any(a.tipo == Anexo.TIPO_COMPROVANTE for a in ps.documentos_anexos.all())
        prazo = ps.prazo_limite_saque
        if prazo and not tem_comprovante:
            faltam = (prazo - hoje).days
            if faltam < 0:
                enviados += _avisar_uma_vez(ps, f"Prazo de saque vencido: {_quem(ps)} em {prazo:%d/%m}", "Não há comprovante de saque ou transferência anexado.")
            elif faltam <= DIAS_AVISO_SAQUE:
                quando = "hoje" if faltam == 0 else f"em {faltam} dia{'s' if faltam > 1 else ''}"
                enviados += _avisar_uma_vez(ps, f"Saque vence {quando}: {_quem(ps)} ({prazo:%d/%m})", "Lembre o servidor de sacar ou transferir as diárias.")
        limite = prazo_para_prestar(prazo)
        if limite and hoje > limite:
            enviados += _avisar_uma_vez(ps, f"Prestação vencida: {_quem(ps)} em {limite:%d/%m}", "Passaram os 3 dias úteis depois do fim do prazo de saque.")
        diario, rt = situacao_diario(ps.prestacao), situacao_rt(ps)
        if diario == ASSINADO and rt == ASSINADO:
            enviados += _avisar_uma_vez(ps, f"Documentos assinados recebidos: {_quem(ps)}", "Diário de bordo e relatório técnico assinados estão anexados.")
        elif diario and rt and GERADO in (diario, rt):
            enviados += _avisar_uma_vez(ps, f"Documentos gerados: {_quem(ps)}", "Diário e relatório técnico prontos: envie ao servidor para assinar.")
    return enviados


#: Até quantas horas depois da chegada de volta o aviso "a equipe chegou" ainda
#: sai: cobre o comando rodando uma vez por dia sem avisar viagens antigas na
#: primeira execução.
HORAS_AVISO_CHEGADA = 36


def _usa_viatura(oficio) -> bool:
    return bool(oficio.viatura_id or oficio.transporte_placa_manual or oficio.motorista_id or oficio.motorista_manual_nome)


def _prestacoes_com_roteiro(filtro_roteiro: dict):
    """Prestações ativas cujo roteiro efetivo (o ajustado, senão o do ofício) casa com o filtro."""
    from django.db.models import Q

    from .models import PrestacaoContas

    ajustado = Q(**{f"roteiro_ajustado__{campo}": valor for campo, valor in filtro_roteiro.items()})
    do_oficio = Q(roteiro_ajustado__isnull=True, **{f"oficio__roteiro__{campo}": valor for campo, valor in filtro_roteiro.items()})
    return (
        PrestacaoContas.objects.filter(oficio__cancelado=False)
        .filter(ajustado | do_oficio)
        .select_related("oficio", "roteiro_ajustado", "oficio__roteiro")
    )


def avisar_viagens(agora: datetime.datetime | None = None) -> int:
    """m096: "amanhã sai a viagem" (mande o link do diário) e "a equipe chegou"."""
    from .campo_services import datas_da_viagem, link_ativo
    from .diario_services import _local
    from .models import DiarioBordo

    agora = agora or timezone.now()
    amanha = timezone.localdate(agora) + datetime.timedelta(days=1)
    enviados = 0
    for prestacao in _prestacoes_com_roteiro({"saida_dt__date": amanha}):
        oficio = prestacao.oficio
        ps = prestacao.servidores_prestacao.order_by("pk").first()
        if ps is None or not _usa_viatura(oficio):
            continue
        saida, _retorno = datas_da_viagem(prestacao)
        saida = _local(saida)
        diario = DiarioBordo.objects.filter(prestacao=prestacao).first()
        ja_tem_link = diario is not None and link_ativo(diario) is not None
        mensagem = (
            "O link do diário já foi gerado: confirme que o motorista o recebeu e abriu com internet."
            if ja_tem_link
            else "Gere o link do diário no celular e envie ao motorista pelo WhatsApp: ele lança o km de cada trecho mesmo sem sinal."
        )
        link = reverse("viagens_prestacoes:diario_servidor", args=[ps.pk]) + "#celular"
        enviados += _avisar_uma_vez(
            ps,
            f"Amanhã sai a viagem do Ofício {oficio.numero_formatado} ({saida:%d/%m %H:%M}): envie o link do diário ao motorista",
            mensagem,
            link=link,
        )
    for prestacao in _prestacoes_com_roteiro({"retorno_chegada_dt__lte": agora, "retorno_chegada_dt__gte": agora - datetime.timedelta(hours=HORAS_AVISO_CHEGADA)}):
        ps = prestacao.servidores_prestacao.order_by("pk").first()
        if ps is None:
            continue
        _saida, retorno = datas_da_viagem(prestacao)
        retorno = _local(retorno)
        enviados += _avisar_uma_vez(
            ps,
            f"A equipe do Ofício {prestacao.oficio.numero_formatado} chegou de viagem ({retorno:%d/%m %H:%M})",
            "Hora de começar a prestação de contas: diário de bordo, relatório técnico e comprovantes.",
            link=reverse("viagens_prestacoes:diario_servidor", args=[ps.pk]),
        )
    return enviados
