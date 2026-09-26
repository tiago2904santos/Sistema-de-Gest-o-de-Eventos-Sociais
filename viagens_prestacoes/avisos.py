"""Avisos da prestação de contas no sino (e por e-mail) da equipe de viagens (m085, m090).

O que vai para o sino, por servidor (a prestação é individual):

- **Diárias liberadas** — na hora, quando a data de liberação é preenchida;
- **Saque vence em N dias** e **Prazo de saque vencido** — sem comprovante anexado;
- **Prestação vencida** — passou dos 3 dias úteis depois do fim do saque (m094);
- **Documentos gerados** — diário e RT prontos, falta mandar ao servidor e o
  assinado voltar; e **Documentos assinados recebidos** — RT e diário assinados
  anexados.

Os de prazo e de documentos saem do comando diário `avisar_prazos_prestacao`
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


def _avisar_uma_vez(ps, titulo, mensagem, *, exceto=None) -> bool:
    link = _link(ps)
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
