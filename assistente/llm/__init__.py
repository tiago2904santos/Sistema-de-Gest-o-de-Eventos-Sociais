"""Escolha do interpretador — uma linha de configuração, nada mais.

A ordem é deliberada: se houver chave de API configurada, usa o adaptador
remoto; senão, o determinístico. O sistema **funciona nos dois casos**, com
menos conversa no segundo. Nenhuma tela, ferramenta ou teste depende de qual
está ativo, que é o ponto de a camada existir.

Configuração (``settings`` ou ``.env``):

- ``ANTHROPIC_API_KEY`` — sem ela, o assistente roda de graça e local.
- ``ASSISTENTE_LLM_MODELO`` — padrão ``claude-opus-5``.
- ``ASSISTENTE_LLM`` — ``deterministico`` força o modo gratuito mesmo com chave.
"""

from __future__ import annotations

import os

from django.conf import settings

from .base import AdaptadorLLM, Intencao
from .deterministico import InterpretadorDeterministico

__all__ = ["AdaptadorLLM", "Intencao", "InterpretadorDeterministico", "obter_interpretador"]


def _config(nome, padrao=""):
    return getattr(settings, nome, None) or os.environ.get(nome, padrao)


def obter_interpretador() -> AdaptadorLLM:
    if _config("ASSISTENTE_LLM") == "deterministico":
        return InterpretadorDeterministico()
    chave = _config("ANTHROPIC_API_KEY")
    if not chave:
        return InterpretadorDeterministico()
    try:
        from .api_anthropic import InterpretadorAnthropic

        return InterpretadorAnthropic(
            api_key=chave,
            modelo=_config("ASSISTENTE_LLM_MODELO", "claude-opus-5"),
        )
    except ImportError:
        # Chave configurada mas biblioteca ausente: seguir gratuito é melhor
        # que derrubar a tela do assistente.
        return InterpretadorDeterministico()
