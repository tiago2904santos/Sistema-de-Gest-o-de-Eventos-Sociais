"""Comparar números de telefone do jeito que o Brasil exige.

O nono dígito é o problema real deste módulo. Números móveis brasileiros
ganharam um "9" na frente do assinante, mas o `wa_id` que a Meta entrega
aparece das duas formas conforme a idade do cadastro e a origem do contato:
``5544999998888`` (13 dígitos, com o 9) e ``554499998888`` (12, sem).

Guardar uma forma e comparar com a outra faz o vínculo não casar, e a
mensagem ser ignorada como se o número fosse desconhecido — uma falha
silenciosa que só aparece quando alguém reclama que "o assistente não
responde pra mim". Por isso a busca tenta as duas variações.

Fora do Brasil não há o que adivinhar: o número é comparado como veio.
"""

from __future__ import annotations

import re

BRASIL = "55"
# 55 + DDD (2) + 9 + 8 dígitos
COM_NONO = re.compile(r"^55(\d{2})9(\d{8})$")
# 55 + DDD (2) + 8 dígitos
SEM_NONO = re.compile(r"^55(\d{2})(\d{8})$")


def normalizar(numero: str) -> str:
    """Só os dígitos: é assim que a Meta entrega e como o vínculo é guardado."""
    return re.sub(r"\D", "", numero or "")


def variantes(numero: str) -> list[str]:
    """As formas equivalentes do mesmo número, a mais provável primeiro."""
    limpo = normalizar(numero)
    if not limpo:
        return []
    formas = [limpo]
    if limpo.startswith(BRASIL):
        com = COM_NONO.match(limpo)
        if com:
            formas.append(f"{BRASIL}{com.group(1)}{com.group(2)}")
        else:
            sem = SEM_NONO.match(limpo)
            if sem:
                formas.append(f"{BRASIL}{sem.group(1)}9{sem.group(2)}")
    return formas


def buscar_vinculo(numero: str):
    """O vínculo ativo do número, tentando as variações antes de desistir."""
    from ..models import VinculoWhatsApp

    formas = variantes(numero)
    if not formas:
        return None
    vinculos = {
        v.numero: v
        for v in VinculoWhatsApp.objects.select_related("usuario").filter(
            numero__in=formas, ativo=True
        )
    }
    for forma in formas:
        if forma in vinculos:
            return vinculos[forma]
    return None
