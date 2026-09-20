"""Áudio vira texto sem sair da rede, quando houver como.

`faster-whisper` roda no próprio servidor. A escolha não é só de custo: o
áudio de um servidor dizendo para onde a equipe vai é dado operacional, e
mandá-lo a um serviço de transcrição na nuvem seria mais um lugar por onde
ele passa. Local, só o texto segue adiante — e nem ele precisa sair, porque o
interpretador padrão também é local.

Não é dependência do projeto: sem a biblioteca instalada, o canal continua
funcionando e responde pedindo o texto. Áudio silenciosamente ignorado seria
a pior versão disso.

O formato do WhatsApp é OGG/Opus. Não há conversão aqui de propósito: o
`faster-whisper` decodifica pelo PyAV que ele mesmo traz, então o `ffmpeg`
não vira pré-requisito de instalação no servidor.
"""

from __future__ import annotations

import logging
import os
import tempfile

logger = logging.getLogger(__name__)

# `small` é o ponto em que o português fica utilizável sem GPU; `base` erra
# nome próprio demais para um sistema que decide por nome próprio.
MODELO_PADRAO = "small"


class Transcritor:
    def transcrever(self, audio: bytes, mime: str = "") -> str:
        raise NotImplementedError


class WhisperLocal(Transcritor):
    def __init__(self, modelo: str = MODELO_PADRAO):
        from faster_whisper import WhisperModel

        # int8 na CPU: é o que torna viável um servidor sem GPU, que é o caso.
        self._modelo = WhisperModel(modelo, device="cpu", compute_type="int8")

    def transcrever(self, audio: bytes, mime: str = "") -> str:
        with tempfile.NamedTemporaryFile(suffix=".ogg", delete=False) as arquivo:
            arquivo.write(audio)
            caminho = arquivo.name
        try:
            segmentos, _ = self._modelo.transcribe(caminho, language="pt")
            return " ".join(s.text.strip() for s in segmentos).strip()
        finally:
            os.unlink(caminho)


def obter_transcritor() -> Transcritor | None:
    """O transcritor local, ou None quando a biblioteca não está instalada."""
    try:
        return WhisperLocal()
    except ImportError:
        return None
    except Exception:  # noqa: BLE001 - modelo ausente, disco cheio, sem rede
        # Carregar o modelo baixa arquivos na primeira vez; falhar aqui não
        # pode derrubar o canal inteiro, só o áudio.
        logger.warning("Transcrição local indisponível", exc_info=True)
        return None
