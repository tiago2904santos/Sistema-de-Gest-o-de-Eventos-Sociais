"""Transporte HTTP do eProtocolo: token, cabeçalhos, timeout e nada mais.

Escrito em ``urllib`` da biblioteca padrão, como o cálculo de rota e o canal
do WhatsApp — o projeto não tem ``requests`` no ``requirements.txt``.

Duas responsabilidades e só:

* **autenticar** (OAuth2 *client credentials*), guardando o token em memória
  até pouco antes de expirar — cada cadastro de ofício não vai pedir um token
  novo;
* **converter status HTTP em exceção própria**, para que nenhuma camada acima
  precise ler código de erro.

O client é uma classe, e não funções soltas, para poder ser trocado por um
dublê nos testes sem ``mock.patch`` em caminho de módulo.

Nada sensível vai para o log: ``mascarar_dados`` apaga token, secret e CPF
antes de qualquer registro.
"""

from __future__ import annotations

import json
import logging
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

from . import settings as cfg
from .exceptions import (
    EProtocoloError,
    EProtocoloNaoConfiguradoError,
    EProtocoloTimeoutError,
    EProtocoloUnavailableError,
    excecao_para_status,
)

logger = logging.getLogger("integracoes.eprotocolo")

# Cabeçalhos/campos que jamais podem aparecer em log.
_CAMPOS_SENSIVEIS = {
    "authorization", "client_secret", "clientsecret", "client_id",
    "consumerid", "consumer_id", "access_token", "token", "senha", "password",
}


def mascarar_dados(valor):
    """Oculta token, secret e CPF antes de logar ou persistir."""
    if isinstance(valor, dict):
        limpo = {}
        for chave, item in valor.items():
            normalizada = str(chave).strip().lower()
            if normalizada in _CAMPOS_SENSIVEIS:
                limpo[chave] = "***"
            elif "cpf" in normalizada:
                limpo[chave] = _mascarar_cpf(item)
            else:
                limpo[chave] = mascarar_dados(item)
        return limpo
    if isinstance(valor, (list, tuple)):
        return [mascarar_dados(item) for item in valor]
    return valor


def _mascarar_cpf(valor):
    digitos = "".join(ch for ch in str(valor or "") if ch.isdigit())
    if len(digitos) != 11:
        return "***"
    return f"{digitos[0:3]}.***.***-{digitos[9:11]}"


class _TokenCache:
    """Token em memória, com validade e trava — o servidor tem mais de um worker."""

    def __init__(self):
        self._lock = threading.Lock()
        self._token = None
        self._expira_em = 0.0

    def get(self):
        with self._lock:
            if self._token and time.monotonic() < self._expira_em:
                return self._token
            return None

    def set(self, token: str, expira_em_segundos: int):
        with self._lock:
            self._token = token
            # 30s de margem: um token que vence no meio do caminho volta 401.
            self._expira_em = time.monotonic() + max(0, expira_em_segundos - 30)

    def clear(self):
        with self._lock:
            self._token = None
            self._expira_em = 0.0


class EProtocoloClient:
    """Transporte isolado. Recebe a configuração; o padrão é a do projeto."""

    def __init__(self, config: dict | None = None):
        self.config = config or cfg.get_config()
        self._token_cache = _TokenCache()

    # -- rede -------------------------------------------------------------
    def _abrir(self, pedido: urllib.request.Request):
        """Uma requisição, com timeout e os erros já traduzidos."""
        contexto = None
        if not self.config.get("VERIFY_SSL", True):
            # Só para o barramento de treinamento, que às vezes usa certificado
            # interno. Em produção a verificação fica ligada.
            import ssl

            contexto = ssl._create_unverified_context()
        timeout = self.config.get("TIMEOUT", 30)
        try:
            with urllib.request.urlopen(pedido, timeout=timeout, context=contexto) as resposta:
                return resposta.status, resposta.read()
        except urllib.error.HTTPError as erro:
            corpo = b""
            try:
                corpo = erro.read()
            except Exception:  # noqa: BLE001 - diagnóstico não pode falhar
                pass
            return erro.code, corpo
        except TimeoutError as erro:
            raise EProtocoloTimeoutError() from erro
        except urllib.error.URLError as erro:
            if isinstance(erro.reason, TimeoutError):
                raise EProtocoloTimeoutError() from erro
            raise EProtocoloUnavailableError(str(erro.reason)) from erro

    # -- autenticação ------------------------------------------------------
    def _obter_token(self) -> str:
        token = self._token_cache.get()
        if token:
            return token

        token_url = (self.config.get("TOKEN_URL") or "").strip()
        client_id = (self.config.get("CLIENT_ID") or "").strip()
        client_secret = (self.config.get("CLIENT_SECRET") or "").strip()
        if not (token_url and client_id and client_secret):
            raise EProtocoloNaoConfiguradoError()

        logger.info("eProtocolo: solicitando token de acesso (client_credentials).")
        corpo = urllib.parse.urlencode({
            "grant_type": "client_credentials",
            "client_id": client_id,
            "client_secret": client_secret,
        }).encode("utf-8")
        pedido = urllib.request.Request(
            token_url,
            data=corpo,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            method="POST",
        )
        status, bruto = self._abrir(pedido)
        if status >= 400:
            raise excecao_para_status(status, "Falha ao obter token de acesso.")

        dados = _json_seguro(bruto)
        token = dados.get("access_token")
        if not token:
            raise EProtocoloError("Resposta de token sem 'access_token'.")
        self._token_cache.set(token, int(dados.get("expires_in", 300) or 300))
        return token

    def garantir_token(self) -> bool:
        """Confirma que dá para autenticar. NUNCA devolve o token em si."""
        self._obter_token()
        return True

    def _headers(self, *, json_body: bool) -> dict:
        headers = {
            "Authorization": f"Bearer {self._obter_token()}",
            "consumerId": (self.config.get("CONSUMER_ID") or "").strip(),
            "Accept": "application/json",
        }
        if json_body:
            headers["Content-Type"] = "application/json; charset=utf-8"
        return headers

    # -- requisição base ---------------------------------------------------
    def _url(self, path: str, params: dict | None = None) -> str:
        base = (self.config.get("BASE_URL") or "").strip().rstrip("/")
        if not base:
            raise EProtocoloNaoConfiguradoError()
        url = f"{base}/{path.lstrip('/')}"
        if params:
            url = f"{url}?{urllib.parse.urlencode(params)}"
        return url

    def request(self, metodo: str, path: str, *, params=None, json_body=None):
        url = self._url(path, params)
        corpo = json.dumps(json_body).encode("utf-8") if json_body is not None else None
        pedido = urllib.request.Request(
            url,
            data=corpo,
            headers=self._headers(json_body=corpo is not None),
            method=metodo.upper(),
        )
        inicio = time.monotonic()
        status, bruto = self._abrir(pedido)
        duracao_ms = int((time.monotonic() - inicio) * 1000)
        logger.info(
            "eProtocolo %s %s → %s (%sms) req=%s",
            metodo.upper(), path, status, duracao_ms, mascarar_dados(json_body or {}),
        )

        dados = _json_seguro(bruto)
        if status >= 400:
            raise excecao_para_status(
                status,
                f"eProtocolo respondeu {status} em {metodo.upper()} {path}.",
                payload=dados,
            )
        return dados

    def get(self, path, params=None):
        return self.request("GET", path, params=params)

    def post(self, path, json_body=None):
        return self.request("POST", path, json_body=json_body if json_body is not None else {})


def _json_seguro(bruto: bytes) -> dict:
    """Corpo que não é JSON não derruba a chamada — vira ``_raw``."""
    texto = (bruto or b"").decode("utf-8", "replace")
    if not texto.strip():
        return {}
    try:
        dados = json.loads(texto)
    except ValueError:
        return {"_raw": texto[:1000]}
    return dados if isinstance(dados, dict) else {"_raw": dados}


def get_client(config: dict | None = None) -> EProtocoloClient:
    """Fábrica do client — o ponto de troca nos testes."""
    return EProtocoloClient(config=config)
