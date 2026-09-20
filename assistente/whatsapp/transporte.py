"""As duas chamadas que saem daqui para a Meta: responder e baixar áudio.

`urllib` da biblioteca padrão, como o cálculo de rota já faz — o projeto não
tem `requests` no `requirements.txt` e não é por este canal que ele vai
ganhar uma dependência.

O transporte é uma classe, e não funções soltas, para poder ser trocado por
um dublê nos testes sem `mock.patch` em caminho de módulo. Quem chama o
serviço passa o transporte; o padrão é o real.
"""

from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request

from . import config

logger = logging.getLogger(__name__)


class EnvioIndisponivel(Exception):
    """Falta credencial, ou a Meta recusou. A mensagem fica na fila."""


class Transporte:
    """Contrato mínimo do canal. Implementado de verdade abaixo."""

    def enviar(self, numero: str, texto: str) -> str:
        raise NotImplementedError

    def baixar_midia(self, media_id: str) -> tuple[bytes, str]:
        raise NotImplementedError


class TransporteCloudAPI(Transporte):
    def _pedir(self, url: str, *, dados: bytes | None = None, aceita_json: bool = True):
        token = config.token()
        if not token:
            raise EnvioIndisponivel(
                "WHATSAPP_TOKEN não configurado: o canal está desligado."
            )
        cabecalhos = {"Authorization": f"Bearer {token}"}
        if dados is not None:
            cabecalhos["Content-Type"] = "application/json; charset=utf-8"
        pedido = urllib.request.Request(
            url, data=dados, headers=cabecalhos, method="POST" if dados else "GET"
        )
        try:
            with urllib.request.urlopen(pedido, timeout=config.TIMEOUT_SEGUNDOS) as resposta:
                bruto = resposta.read()
                tipo = resposta.headers.get("Content-Type", "")
            return (json.loads(bruto) if aceita_json else bruto), tipo
        except urllib.error.HTTPError as erro:
            # O corpo do erro da Meta explica o motivo (janela fechada, token
            # vencido, número inválido); sem ele a fila só diria "HTTP 400".
            detalhe = ""
            try:
                detalhe = erro.read().decode("utf-8", "replace")[:500]
            except Exception:  # noqa: BLE001 - diagnóstico não pode falhar
                pass
            raise EnvioIndisponivel(f"HTTP {erro.code} da Meta: {detalhe}") from erro
        except urllib.error.URLError as erro:
            raise EnvioIndisponivel(f"Rede indisponível: {erro.reason}") from erro

    def enviar(self, numero: str, texto: str) -> str:
        if not config.envio_configurado():
            raise EnvioIndisponivel(
                "Canal sem credencial: defina WHATSAPP_TOKEN e "
                "WHATSAPP_PHONE_NUMBER_ID no .env do servidor."
            )
        corpo = json.dumps(
            {
                "messaging_product": "whatsapp",
                "recipient_type": "individual",
                "to": numero,
                "type": "text",
                # A Meta encurta link sozinha; a prévia atrapalha mais que ajuda
                # numa resposta curta de sistema.
                "text": {"preview_url": False, "body": texto},
            }
        ).encode("utf-8")
        url = f"{config.URL_GRAPH}/{config.phone_number_id()}/messages"
        resposta, _ = self._pedir(url, dados=corpo)
        mensagens = resposta.get("messages") or []
        return str(mensagens[0].get("id", "")) if mensagens else ""

    def baixar_midia(self, media_id: str) -> tuple[bytes, str]:
        """Duas etapas: a Meta dá uma URL assinada, e ela também exige o token."""
        metadados, _ = self._pedir(f"{config.URL_GRAPH}/{media_id}")
        url = metadados.get("url")
        if not url:
            raise EnvioIndisponivel(f"A Meta não devolveu URL para a mídia {media_id}.")
        conteudo, tipo = self._pedir(url, aceita_json=False)
        return conteudo, (metadados.get("mime_type") or tipo or "")


def obter_transporte() -> Transporte:
    return TransporteCloudAPI()
