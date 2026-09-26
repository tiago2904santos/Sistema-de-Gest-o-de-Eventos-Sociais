"""Duas pessoas no mesmo documento (m125): conflito só no mesmo campo, e
quem mais está editando.

A versão que o editor compara é a do registro inteiro (`atualizado_em` do
ofício, do termo...). Sozinha, ela acusava conflito sempre que outra pessoa
gravava qualquer campo — mesmo outro —, e quem digitava perdia o que tinha
escrito. Aqui fica a memória curta do que mudou: a cada gravação pelo
editor, o registro do alvo ganha uma entrada (versão anterior → nova, quais
campos, quem) no cache compartilhado. Uma gravação com versão antiga passa
se a cadeia de mudanças desde a versão lida existir inteira e nenhuma delas
tocar os campos pedidos; se a cadeia se perdeu (cache reiniciado) ou o
mesmo campo mudou, é conflito — e a mensagem diz quem mexeu.

A presença é uma chave por documento com quem o abriu e quando foi visto
pela última vez; o navegador avisa a cada 30 s, e quem não avisa há 60 s
some. Nada disso é banco: é aviso, não registro.
"""

from __future__ import annotations

from django.core.cache import cache
from django.utils import timezone

#: Por quanto tempo a memória de mudanças de um registro fica no cache.
VALIDADE_MUDANCAS = 60 * 60
#: Quantas mudanças recentes se guardam por registro.
LIMITE_MUDANCAS = 50
#: Quem não avisou presença há tantos segundos deixou o documento.
VALIDADE_PRESENCA = 60


def _nome(usuario) -> str:
    if usuario is None or not getattr(usuario, "is_authenticated", False):
        return ""
    return (usuario.get_full_name() or usuario.get_username()).strip()


def _chave_mudancas(alvo) -> str:
    return f"editor:mudancas:{alvo._meta.label_lower}:{alvo.pk}"


def registrar_mudanca(alvo, versao_anterior, versao_nova, nomes, usuario) -> None:
    """Guarda que `nomes` do alvo mudaram da versão anterior para a nova."""
    if not alvo or getattr(alvo, "pk", None) is None or not versao_nova or versao_nova == versao_anterior:
        return
    chave = _chave_mudancas(alvo)
    mudancas = list(cache.get(chave) or [])
    mudancas.append({
        "anterior": versao_anterior or "", "versao": versao_nova, "campos": sorted(set(nomes)),
        "usuario": _nome(usuario), "quando": timezone.now().isoformat(),
    })
    cache.set(chave, mudancas[-LIMITE_MUDANCAS:], VALIDADE_MUDANCAS)


def mudancas_desde(alvo, versao_lida, versao_atual) -> list[dict] | None:
    """A cadeia de mudanças da versão lida até a atual, ou None se ela não
    está inteira no cache (aí não se sabe o que mudou)."""
    if not versao_lida or getattr(alvo, "pk", None) is None:
        return None
    por_anterior = {}
    for mudanca in cache.get(_chave_mudancas(alvo)) or []:
        por_anterior[mudanca["anterior"]] = mudanca
    cadeia = []
    versao = versao_lida
    while versao != versao_atual:
        mudanca = por_anterior.get(versao)
        if mudanca is None or len(cadeia) >= LIMITE_MUDANCAS:
            return None
        cadeia.append(mudanca)
        versao = mudanca["versao"]
    return cadeia


def conflito(alvo, versao_lida, versao_atual, nomes) -> dict | None:
    """None quando a gravação pode seguir; senão o que dizer a quem edita:
    `mesmo_campo` (o campo pedido mudou) e `quem` (o último a mexer)."""
    if versao_lida == versao_atual:
        return None
    cadeia = mudancas_desde(alvo, versao_lida, versao_atual)
    if cadeia is None:
        return {"mesmo_campo": True, "quem": ""}
    pedidos = set(nomes)
    tocadas = [m for m in cadeia if pedidos & set(m["campos"])]
    if not tocadas:
        return None
    return {"mesmo_campo": True, "quem": tocadas[-1]["usuario"]}


def mensagem_do_conflito(detalhe: dict, rotulo: str = "") -> str:
    quem = detalhe.get("quem") or "outra pessoa"
    trecho = f" ({rotulo})" if rotulo else ""
    return f"{quem.capitalize() if quem == 'outra pessoa' else quem} alterou este mesmo trecho{trecho} desde que você o abriu. Recarregue para ver o valor atual."


# ---- Presença --------------------------------------------------------------


def _chave_presenca(tipo, pk, variante="") -> str:
    return f"editor:presenca:{tipo}:{pk}:{variante or ''}"


def marcar_presenca(tipo, pk, usuario, *, variante="", sair=False) -> list[str]:
    """Registra (ou retira) quem está no documento; devolve os nomes dos
    outros que ainda estão nele."""
    chave = _chave_presenca(tipo, pk, variante)
    agora = timezone.now()
    presentes = {}
    for uid, dados in (cache.get(chave) or {}).items():
        try:
            visto = timezone.datetime.fromisoformat(dados["visto"])
        except (KeyError, TypeError, ValueError):
            continue
        if (agora - visto).total_seconds() <= VALIDADE_PRESENCA:
            presentes[uid] = dados
    meu = str(getattr(usuario, "pk", "") or "")
    if sair:
        presentes.pop(meu, None)
    elif meu:
        presentes[meu] = {"nome": _nome(usuario), "visto": agora.isoformat()}
    cache.set(chave, presentes, VALIDADE_PRESENCA * 2)
    return sorted(dados["nome"] for uid, dados in presentes.items() if uid != meu and dados.get("nome"))
