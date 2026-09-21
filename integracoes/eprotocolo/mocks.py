"""Respostas determinísticas do modo simulado.

Usadas quando não há credencial ou quando ``EPROTOCOLO_AMBIENTE=mock``. É o
que permite desenvolver, testar e rodar a suíte inteira sem nenhuma chamada
externa — e o que mantém o sistema utilizável na instalação que ainda não
recebeu as credenciais da Celepar.

O formato imita o da API real; quando a documentação oficial for confirmada,
ajusta-se o parse nos services e o contrato daqui continua valendo.
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone


def _agora_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def gerar_numero_mock(seed: str | int | None = None) -> str:
    """Número fictício no formato do eProtocolo/PR (``NN.NNN.NNN-D``).

    Estável por seed: o mesmo ofício simulado duas vezes recebe o mesmo
    número, o que torna os testes previsíveis.
    """
    base = hashlib.sha256(str(seed if seed is not None else _agora_iso()).encode("utf-8")).hexdigest()
    digitos = "".join(ch for ch in base if ch.isdigit()).ljust(9, "0")[:9]
    return f"{digitos[0:2]}.{digitos[2:5]}.{digitos[5:8]}-{digitos[8]}"


def criar_protocolo(payload: dict, *, seed=None) -> dict:
    numero = gerar_numero_mock(seed if seed is not None else payload.get("referenciaDocumento"))
    return {
        "numero": numero,
        "situacao": "CRIADO",
        "codOrgao": payload.get("codOrgao", ""),
        "codLocalAtual": payload.get("codLocalOrigem", ""),
        "nomeLocalAtual": payload.get("nomeOrgao", ""),
        "criadoEm": _agora_iso(),
        "_mock": True,
    }


def consultar_protocolo(numero: str) -> dict:
    return {
        "numero": numero,
        "situacao": "EM_TRAMITACAO",
        "codLocalAtual": "0001",
        "nomeLocalAtual": "Local de Trâmite (simulado)",
        "ultimaMovimentacao": _agora_iso(),
        "_mock": True,
    }


def autenticar() -> dict:
    """Simula a obtenção de token — sem expor nada, real ou falso."""
    return {"autenticado": True, "tokenType": "Bearer", "expiresIn": 300, "_mock": True}


def listar_orgaos() -> dict:
    return {"orgaos": [{"codigo": "0000", "nome": "Órgão (simulado)"}], "_mock": True}


def listar_locais(cod_orgao: str | None = None) -> dict:
    return {
        "codOrgao": cod_orgao or "",
        "locais": [{"codigo": "0001", "nome": "Local de Trâmite (simulado)"}],
        "_mock": True,
    }
