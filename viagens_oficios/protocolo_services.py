"""O protocolo do ofício, aberto pelo sistema enquanto o ofício é feito.

O campo `protocolo` era digitado à mão a partir do número que a pessoa abria
no eProtocolo em outra aba. Aqui o caminho se inverte: ao gravar o ofício, o
sistema abre o protocolo e traz o número de volta.

Três regras sustentam o resto:

**Nunca por cima do que foi digitado.** Protocolo preenchido — por um ofício
antigo, por migração ou pela própria pessoa — é dado do usuário. A abertura
automática só acontece com o campo vazio; para trocar, apague e grave, ou
peça a reabertura explícita (`forcar=True`).

**Nunca derruba a gravação.** eProtocolo fora do ar, credencial vencida,
código institucional faltando: o ofício é salvo do mesmo jeito e a falha vira
aviso na tela. A conferência já cobra "Informe o protocolo." antes de
finalizar — é ela que impede o documento sair sem número, não uma exceção no
meio do cadastro.

**Nunca promete o que não fez.** Sem credencial, o número é simulado e a
origem gravada diz isso (`SIMULADO`), na ficha e no banco. Só o que veio do
barramento é marcado como `EPROTOCOLO`.

Chamado do formulário (a cada gravação, inclusive "Salvar rascunho"), e não
na criação do rascunho: o rascunho nasce vazio e é reaproveitado quando
abandonado — abrir um processo lá dentro seria abrir processo para ofício que
nunca existiu.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from django.contrib import messages
from django.utils import timezone

from core.errors import capture
from core.utils.masks import format_protocolo, normalize_protocolo
from integracoes.eprotocolo import services as epro
from integracoes.eprotocolo import settings as cfg
from integracoes.eprotocolo.exceptions import EProtocoloError, EProtocoloValidationError

from .models import Oficio

#: Tentativas de reseed quando o número simulado cai em cima de outro ofício.
#: Só o modo simulado repete: número vindo do eProtocolo é o que vale, mesmo
#: repetido (e o formulário já avisa sobre protocolo duplicado).
TENTATIVAS_NUMERO_SIMULADO = 5


@dataclass
class ResultadoProtocolo:
    """O que aconteceu na tentativa de abrir o protocolo."""

    numero: str = ""
    criado: bool = False
    simulado: bool = False
    #: O número vale como protocolo oficial? Só em produção: treinamento e
    #: homologação abrem processo de verdade num barramento de teste.
    oficial: bool = False
    #: O ambiente que respondeu, para a frase da tela dizer qual foi.
    ambiente: str = ""
    #: O ofício ainda não tem o que o eProtocolo exige (assunto, motivo,
    #: códigos institucionais). Não é erro de rascunho — é cedo demais.
    incompleto: bool = False
    erro: str = ""
    detalhes: dict = field(default_factory=dict)

    @property
    def numero_formatado(self) -> str:
        return format_protocolo(self.numero) or self.numero


def pode_abrir_protocolo(oficio: Oficio, *, forcar: bool = False) -> bool:
    """O ofício está em condição de receber um protocolo automático?"""
    if not cfg.auto_protocolo_oficio() and not forcar:
        return False
    if getattr(oficio, "cancelado", False):
        return False
    if (oficio.protocolo or "").strip() and not forcar:
        return False
    return True


def abrir_protocolo_do_oficio(oficio: Oficio, *, forcar: bool = False) -> ResultadoProtocolo:
    """Abre o protocolo e grava o número no ofício. Nunca levanta exceção."""
    if not pode_abrir_protocolo(oficio, forcar=forcar):
        return ResultadoProtocolo(numero=oficio.protocolo or "")

    try:
        resultado = _abrir(oficio)
    except EProtocoloValidationError as exc:
        # Falta dado no ofício (ou código no .env): cedo demais, não é falha.
        return ResultadoProtocolo(incompleto=True, erro=str(exc))
    except EProtocoloError as exc:
        # `str` já traz a frase de usuário quando a exceção não recebeu texto
        # próprio — e o texto próprio (qual variável falta, qual trava está
        # fechada) é exatamente o que ajuda quem está na tela.
        capture(exc, "viagens_oficios.protocolo.abrir", oficio_id=oficio.pk)
        return ResultadoProtocolo(erro=str(exc))
    except Exception as exc:  # noqa: BLE001 - gravar o ofício vem antes de tudo
        capture(exc, "viagens_oficios.protocolo.abrir", oficio_id=oficio.pk)
        return ResultadoProtocolo(erro="Falha inesperada ao abrir o protocolo.")

    numero = normalize_protocolo(resultado.dados.get("numero") or "")
    if not numero:
        return ResultadoProtocolo(
            erro="O eProtocolo respondeu sem número de protocolo.",
            detalhes=dict(resultado.dados or {}),
        )

    oficio.protocolo = numero
    oficio.protocolo_origem = _origem_do_numero(resultado)
    oficio.protocolo_situacao = str(resultado.dados.get("situacao") or "")[:40]
    oficio.protocolo_criado_em = timezone.now()
    oficio.save(update_fields=[
        "protocolo", "protocolo_origem", "protocolo_situacao", "protocolo_criado_em",
        "atualizado_em",
    ])
    return ResultadoProtocolo(
        numero=numero, criado=True, simulado=resultado.mock,
        oficial=cfg.numero_e_oficial(),
        ambiente=cfg.ambiente(),
        detalhes=dict(resultado.dados or {}),
    )


def _origem_do_numero(resultado) -> str:
    """Três destinos possíveis, e a diferença entre eles é a que importa:
    simulado (não saiu daqui), treinamento/homologação (existe, mas não vale
    para protocolar) e produção (vale)."""
    if resultado.mock:
        return Oficio.PROTOCOLO_ORIGEM_SIMULADO
    if not cfg.numero_e_oficial():
        return Oficio.PROTOCOLO_ORIGEM_TREINAMENTO
    return Oficio.PROTOCOLO_ORIGEM_EPROTOCOLO


def _abrir(oficio: Oficio):
    """A chamada em si, com o desempate dos números simulados."""
    resultado = epro.criar_protocolo_de_oficio(oficio)
    if not resultado.mock:
        return resultado

    for tentativa in range(TENTATIVAS_NUMERO_SIMULADO):
        numero = normalize_protocolo(resultado.dados.get("numero") or "")
        if not numero or not _numero_ocupado(numero, oficio):
            return resultado
        resultado = epro.criar_protocolo_de_oficio(
            oficio, seed=f"{oficio.pk}:{oficio.numero}:{oficio.ano}:{tentativa}"
        )
    return resultado


def _numero_ocupado(numero: str, oficio: Oficio) -> bool:
    return Oficio.objects.filter(protocolo=numero).exclude(pk=oficio.pk).exists()


def mensagens_do_protocolo(resultado: ResultadoProtocolo, *, finalizar: bool = False):
    """Traduz o resultado em mensagens para a tela, no formato (nível, texto).

    Em rascunho, ofício incompleto não rende mensagem: a pessoa ainda está
    preenchendo. Ao finalizar, rende — ali o número faz falta.
    """
    if resultado.criado and resultado.simulado:
        return [(messages.WARNING,
                 f"Protocolo {resultado.numero_formatado} gerado em modo simulado — "
                 "a integração com o eProtocolo ainda não está configurada. "
                 "Confirme o número real antes de protocolar.")]
    if resultado.criado and not resultado.oficial:
        # Processo aberto de verdade, mas no barramento de teste: dizer
        # "aberto no eProtocolo" e pronto faria o número passar por oficial.
        return [(messages.WARNING,
                 f"Protocolo {resultado.numero_formatado} aberto no eProtocolo de "
                 f"{resultado.ambiente or 'treinamento'} — é um processo de teste e "
                 "NÃO vale como protocolo oficial.")]
    if resultado.criado:
        return [(messages.SUCCESS,
                 f"Protocolo {resultado.numero_formatado} aberto no eProtocolo.")]
    if resultado.incompleto:
        if not finalizar:
            return []
        return [(messages.WARNING,
                 f"O protocolo não foi aberto automaticamente: {resultado.erro}")]
    if resultado.erro:
        return [(messages.WARNING,
                 f"Não foi possível abrir o protocolo no eProtocolo: {resultado.erro} "
                 "O ofício foi salvo; informe o protocolo manualmente ou tente de novo.")]
    return []
