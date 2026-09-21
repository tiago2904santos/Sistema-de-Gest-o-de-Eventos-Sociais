"""Uma função por operação de negócio da integração.

Cada uma decide entre **modo simulado** (sem rede) e **modo real** (via
``client``) e devolve sempre um :class:`ResultadoOperacao` — quem chama sabe
de onde veio o número sem inspecionar credencial.

Abrir protocolo é gravação no sistema de origem e não tem desfazer fácil:
por isso ela exige, além de credencial, a trava ``EPROTOCOLO_REAL_READONLY``
aberta. Enquanto a instalação não tiver as credenciais da Celepar, tudo aqui
responde em modo simulado e nada sai para a rede.
"""

from __future__ import annotations

from . import mappers, mocks
from . import settings as cfg
from .client import get_client
from .exceptions import EProtocoloConfigError
from .schemas import Endpoints, ResultadoOperacao


def _simulado(dados: dict, mensagem: str = "") -> ResultadoOperacao:
    return ResultadoOperacao(sucesso=True, dados=dados, mock=True, mensagem=mensagem)


def _real(dados: dict, mensagem: str = "") -> ResultadoOperacao:
    return ResultadoOperacao(sucesso=True, dados=dados, mock=False, mensagem=mensagem)


# -- diagnóstico -----------------------------------------------------------
def testar_autenticacao() -> ResultadoOperacao:
    """Confirma que dá para obter um token. Nunca devolve o token."""
    if cfg.em_modo_mock():
        return _simulado(mocks.autenticar(), "Autenticação simulada (modo mock).")
    get_client().garantir_token()
    return _real({"autenticado": True}, "Autenticação no eProtocolo bem-sucedida.")


def testar_conexao() -> ResultadoOperacao:
    """Uma consulta simples (órgãos) para validar o acesso ao barramento."""
    if cfg.em_modo_mock():
        return _simulado(mocks.listar_orgaos(), "Conexão simulada (modo mock).")
    return _real(get_client().get(Endpoints.ORGAOS), "Conexão com o eProtocolo bem-sucedida.")


# -- protocolo -------------------------------------------------------------
def criar_protocolo(payload: dict, *, seed=None) -> ResultadoOperacao:
    """Abre um protocolo. Em modo simulado devolve um número fictício."""
    if cfg.em_modo_mock():
        return _simulado(
            mocks.criar_protocolo(payload, seed=seed),
            "Protocolo simulado — a integração real do eProtocolo não está configurada.",
        )
    if not cfg.mutacao_real_liberada():
        raise EProtocoloConfigError(
            "Abertura de protocolo bloqueada: defina EPROTOCOLO_REAL_READONLY=False "
            "para permitir gravação no eProtocolo."
        )
    dados = get_client().post(Endpoints.CRIAR_PROTOCOLO, json_body=payload)
    return _real(dados, "Protocolo aberto no eProtocolo.")


def criar_protocolo_de_oficio(oficio, *, seed=None) -> ResultadoOperacao:
    """Abre o protocolo de um ofício, traduzindo o model para o payload.

    Em modo simulado usa o mapper tolerante; no modo real, o validado — ali um
    campo faltando vira processo errado dentro do eProtocolo.
    """
    if cfg.em_modo_mock():
        payload = mappers.mapear_oficio_para_protocolo(oficio)
    else:
        payload = mappers.mapear_oficio_para_payload_eprotocolo(oficio)
    return criar_protocolo(payload, seed=seed if seed is not None else getattr(oficio, "pk", None))


def consultar_protocolo(numero: str) -> ResultadoOperacao:
    if cfg.em_modo_mock():
        return _simulado(mocks.consultar_protocolo(numero))
    return _real(get_client().get(Endpoints.CONSULTAR_PROTOCOLO.format(numero=numero)))
