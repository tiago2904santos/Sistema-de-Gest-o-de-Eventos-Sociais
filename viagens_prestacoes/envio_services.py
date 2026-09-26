"""Envio ao financeiro, aprovação e devolução da prestação de cada servidor (m093).

Os estados `enviada`, `aprovada` e `reprovada` (exibida como "Devolvida") já
existiam no modelo, mas nada os atribuía. A prestação é individual: cada
servidor é enviado, aprovado ou devolvido por si — o envio pode valer para a
equipe inteira de uma vez, mas só para quem já está finalizado.

- **Enviar** exige a prestação finalizada; guarda a data e o protocolo/e-mail.
- **Aprovar** exige ter sido enviada.
- **Devolver** exige ter sido enviada (ou aprovada), pede o motivo, REABRE a
  prestação (volta a ser editável) e avisa a equipe de viagens no sino.
"""

from __future__ import annotations

from dataclasses import dataclass

from django.db import transaction
from django.urls import reverse
from django.utils import timezone

from .models import PrestacaoServidor


@dataclass(frozen=True)
class ResultadoEnvio:
    erro: str = ""
    afetados: int = 0


@transaction.atomic
def registrar_envio(servidores, *, data=None, protocolo="") -> ResultadoEnvio:
    """Marca como enviada quem está finalizado; devolve quantos."""
    prontos = [ps for ps in servidores if ps.finalizada]
    if not prontos:
        return ResultadoEnvio(erro="Finalize a prestação antes de registrar o envio.")
    for ps in prontos:
        ps.status = PrestacaoServidor.STATUS_ENVIADA
        ps.enviada_em = data or timezone.localdate()
        ps.protocolo_envio = (protocolo or "").strip()[:120]
        ps.decidida_em = None
        ps.save(update_fields=["status", "enviada_em", "protocolo_envio", "decidida_em", "atualizado_em"])
    return ResultadoEnvio(afetados=len(prontos))


@transaction.atomic
def registrar_aprovacao(ps) -> ResultadoEnvio:
    if ps.status != PrestacaoServidor.STATUS_ENVIADA:
        return ResultadoEnvio(erro="Só a prestação enviada pode ser aprovada.")
    ps.status = PrestacaoServidor.STATUS_APROVADA
    ps.decidida_em = timezone.now()
    ps.motivo_devolucao = ""
    ps.save(update_fields=["status", "decidida_em", "motivo_devolucao", "atualizado_em"])
    return ResultadoEnvio(afetados=1)


@transaction.atomic
def registrar_devolucao(ps, *, motivo, autor=None) -> ResultadoEnvio:
    motivo = (motivo or "").strip()
    if ps.status not in (PrestacaoServidor.STATUS_ENVIADA, PrestacaoServidor.STATUS_APROVADA):
        return ResultadoEnvio(erro="Só a prestação enviada pode ser devolvida.")
    if not motivo:
        return ResultadoEnvio(erro="Escreva o motivo da devolução.")
    ps.status = PrestacaoServidor.STATUS_REPROVADA
    ps.decidida_em = timezone.now()
    ps.motivo_devolucao = motivo
    ps.save(update_fields=["status", "decidida_em", "motivo_devolucao", "atualizado_em"])
    # Devolvida volta a ser editável: é para corrigir.
    ps.definir_finalizada(False)

    from core.notificacoes import notificar, usuarios_do_grupo

    notificar(
        usuarios_do_grupo("VIAGENS_OPERADOR"),
        f"Prestação devolvida: {ps.servidor.nome} (Ofício {ps.prestacao.oficio.numero_formatado})",
        motivo,
        link=reverse("viagens_prestacoes:documentos_servidor", args=[ps.pk]),
        exceto=autor,
    )
    return ResultadoEnvio(afetados=1)
