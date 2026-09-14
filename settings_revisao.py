"""Configuração de teste para revisão paralela.

O Codex roda a suíte ao mesmo tempo neste repositório, e dois processos
disputando o mesmo banco de teste derrubam os dois. Aqui o banco de teste tem
nome próprio. Arquivo de rascunho: não entra em produção.
"""

from config.settings import *  # noqa: F401,F403
from config.settings import DATABASES

DATABASES["default"]["TEST"] = {"NAME": "test_eventos_sociais_revisao"}
