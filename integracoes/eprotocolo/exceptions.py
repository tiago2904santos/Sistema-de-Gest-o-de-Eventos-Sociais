"""Hierarquia de erros da integração.

O ``client`` converte toda falha externa para uma destas classes: quem está
acima não precisa conhecer ``urllib`` nem status HTTP, e cada erro já traz a
frase que pode ir para a tela.
"""

from __future__ import annotations


class EProtocoloError(Exception):
    """Base de qualquer falha na conversa com o eProtocolo."""

    mensagem_usuario = "Falha na comunicação com o eProtocolo."

    def __init__(self, mensagem: str | None = None, *, status_code: int | None = None,
                 payload=None):
        self.status_code = status_code
        self.payload = payload
        super().__init__(mensagem or self.mensagem_usuario)


class EProtocoloAuthError(EProtocoloError):
    """Token inválido ou expirado — HTTP 401."""

    mensagem_usuario = "Não foi possível autenticar no eProtocolo (credenciais inválidas)."


class EProtocoloForbiddenError(EProtocoloError):
    """Acesso negado ao recurso — HTTP 403."""

    mensagem_usuario = "Acesso negado pelo eProtocolo para esta operação."


class EProtocoloNotFoundError(EProtocoloError):
    """Recurso inexistente — HTTP 404."""

    mensagem_usuario = "Protocolo ou recurso não encontrado no eProtocolo."


class EProtocoloValidationError(EProtocoloError):
    """Dados recusados — HTTP 400/422, ou reprovados antes de sair daqui."""

    mensagem_usuario = "O eProtocolo recusou os dados enviados (validação)."


class EProtocoloUnavailableError(EProtocoloError):
    """Serviço fora do ar — HTTP 5xx ou falha de conexão."""

    mensagem_usuario = "O serviço do eProtocolo está indisponível no momento."


class EProtocoloTimeoutError(EProtocoloUnavailableError):
    """Tempo limite excedido na chamada."""

    mensagem_usuario = "Tempo limite excedido ao chamar o eProtocolo."


class EProtocoloConfigError(EProtocoloError):
    """Configuração incompleta para o modo real.

    Ex.: falta ``BASE_URL``/``TOKEN_URL``/``CLIENT_ID``/``CLIENT_SECRET``/
    ``CONSUMER_ID``, ou a trava ``EPROTOCOLO_REAL_READONLY`` está fechada para
    uma operação que grava.
    """

    mensagem_usuario = "A integração do eProtocolo está com configuração incompleta."


class EProtocoloNaoConfiguradoError(EProtocoloConfigError):
    """Sem credencial, com o modo real exigido."""

    mensagem_usuario = "A integração real do eProtocolo ainda não está configurada."


def excecao_para_status(status_code: int, mensagem: str | None = None, payload=None) -> EProtocoloError:
    """Status HTTP → a exceção correspondente."""
    if status_code in (400, 422):
        return EProtocoloValidationError(mensagem, status_code=status_code, payload=payload)
    if status_code == 401:
        return EProtocoloAuthError(mensagem, status_code=status_code, payload=payload)
    if status_code == 403:
        return EProtocoloForbiddenError(mensagem, status_code=status_code, payload=payload)
    if status_code == 404:
        return EProtocoloNotFoundError(mensagem, status_code=status_code, payload=payload)
    if status_code >= 500:
        return EProtocoloUnavailableError(mensagem, status_code=status_code, payload=payload)
    return EProtocoloError(mensagem, status_code=status_code, payload=payload)
