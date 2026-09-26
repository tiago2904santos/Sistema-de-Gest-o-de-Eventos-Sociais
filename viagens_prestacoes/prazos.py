"""Os prazos de cada servidor na prestação: o do saque e o de prestar contas.

- **Saque** (m085): `prazo_limite_saque` é digitado na lista. Sem comprovante e
  com o prazo perto (ou já passado), o servidor precisa de um lembrete.
- **Prestar contas** (m094): 3 dias úteis depois do FIM DO PRAZO DE SAQUE — e não
  do retorno —, pulando fins de semana e feriados (`core.feriados`: nacionais
  calculados e os locais cadastrados no admin).

Os dois são por servidor, porque a prestação é individual: um pode nem ter
recebido e outro já estar finalizado.
"""

from __future__ import annotations

import datetime
from dataclasses import dataclass

from django.conf import settings
from django.utils import timezone

from core.feriados import dias_uteis_entre
from core.feriados import somar_dias_uteis

#: Dias úteis, depois do fim do prazo de saque, para prestar contas.
DIAS_UTEIS_PARA_PRESTAR = getattr(settings, "PRESTACAO_DIAS_UTEIS_PARA_PRESTAR", 3)
#: A partir de quantos dias antes do fim do saque o lembrete aparece.
DIAS_AVISO_SAQUE = getattr(settings, "PRESTACAO_DIAS_AVISO_SAQUE", 3)


def prazo_para_prestar(prazo_limite_saque: datetime.date | None) -> datetime.date | None:
    """A data limite para prestar contas, ou `None` sem prazo de saque."""
    if not prazo_limite_saque:
        return None
    return somar_dias_uteis(prazo_limite_saque, DIAS_UTEIS_PARA_PRESTAR)


def ultimo_saque_com_prestacao_vencida(hoje: datetime.date | None = None) -> datetime.date:
    """O maior prazo de saque cuja prestação já venceu (para filtrar no banco).

    `prazo_para_prestar` só cresce com o prazo de saque, então basta recuar a partir
    de hoje até a primeira data que já estourou.
    """
    hoje = hoje or timezone.localdate()
    candidato = hoje - datetime.timedelta(days=1)
    while prazo_para_prestar(candidato) >= hoje:
        candidato -= datetime.timedelta(days=1)
    return candidato


def _plural(n: int, singular: str, plural: str) -> str:
    return f"{n} {singular if n == 1 else plural}"


@dataclass(frozen=True)
class Selo:
    texto: str
    tom: str  # "alerta" | "vencido" | "ok"
    detalhe: str = ""


def selo_do_saque(ps, *, tem_comprovante: bool, hoje=None) -> Selo | None:
    """"Saque vence em 3 dias" / "Prazo de saque vencido", só para quem não tem comprovante."""
    if ps.finalizada or tem_comprovante or not ps.prazo_limite_saque:
        return None
    hoje = hoje or timezone.localdate()
    faltam = (ps.prazo_limite_saque - hoje).days
    if faltam < 0:
        return Selo("Prazo de saque vencido", "vencido", f"Venceu em {ps.prazo_limite_saque:%d/%m/%Y}, sem comprovante.")
    if faltam == 0:
        return Selo("Saque vence hoje", "alerta", "Sem comprovante anexado.")
    if faltam <= DIAS_AVISO_SAQUE:
        return Selo(f"Saque vence em {_plural(faltam, 'dia', 'dias')}", "alerta", f"Prazo: {ps.prazo_limite_saque:%d/%m/%Y}.")
    return None


def saque_depois_do_prazo(ps, comprovantes) -> bool:
    """Algum comprovante com data da operação depois do prazo limite de saque."""
    if not ps.prazo_limite_saque:
        return False
    return any(a.data_operacao and a.data_operacao > ps.prazo_limite_saque for a in comprovantes)


def selo_da_prestacao(ps, *, hoje=None) -> Selo | None:
    """"Prestar contas até 12/09 — faltam 2 dias úteis", com destaque quando vence."""
    if ps.finalizada:
        return None
    limite = prazo_para_prestar(ps.prazo_limite_saque)
    if limite is None:
        return None
    hoje = hoje or timezone.localdate()
    if hoje > limite:
        atraso = dias_uteis_entre(limite, hoje)
        return Selo(f"Prestação vencida em {limite:%d/%m}", "vencido", f"Há {_plural(atraso, 'dia útil', 'dias úteis')}.")
    faltam = dias_uteis_entre(hoje, limite)
    if faltam == 0:
        return Selo(f"Prestar contas hoje ({limite:%d/%m})", "alerta")
    tom = "alerta" if faltam <= 1 else "ok"
    return Selo(f"Prestar contas até {limite:%d/%m} — {'falta' if faltam == 1 else 'faltam'} {_plural(faltam, 'dia útil', 'dias úteis')}", tom)
