"""O meio de campo: da caixa de entrada ao orquestrador, e de volta à de saída.

Nenhuma regra de negócio mora aqui. O que este módulo decide é só de canal:
quem pode falar, o que fazer com áudio, quando ainda dá para responder e o
que fazer quando não dá.

Por que gravar antes de processar: a Meta espera um 200 em segundos e
reentrega o que não confirmou. Se a transcrição de um áudio de trinta
segundos acontecesse dentro do webhook, ela estouraria o prazo, a Meta
reentregaria, e o mesmo áudio viraria duas viagens. Gravar primeiro dá
resposta rápida e idempotência (por `wa_message_id`) de uma vez só.
"""

from __future__ import annotations

import datetime as dt
import logging

from django.db import IntegrityError, transaction
from django.utils import timezone

from ..models import Conversa, MensagemEnviada, MensagemRecebida
from ..orquestrador import responder
from . import config
from .numeros import buscar_vinculo
from .transcricao import obter_transcritor
from .transporte import EnvioIndisponivel, obter_transporte

logger = logging.getLogger(__name__)

# Limite do corpo de texto da Cloud API.
LIMITE_CARACTERES = 4096

# Depois disso a fila para de tentar: o que falha cinco vezes seguidas não é
# instabilidade de rede, é configuração errada — e insistir só gasta cota.
MAX_TENTATIVAS = 5

SEM_TRANSCRICAO = (
    "Recebi seu áudio, mas a transcrição não está instalada neste servidor. "
    "Me manda por texto que eu resolvo."
)
TIPO_NAO_SUPORTADO = (
    "Por enquanto eu entendo texto e áudio. Me manda o pedido escrito ou falado."
)


def registrar_entradas(entradas) -> list[MensagemRecebida]:
    """Grava o que chegou, ignorando o que já tinha chegado antes.

    A unicidade de `wa_message_id` é quem garante a idempotência — e ela é
    checada pelo banco, não por um `exists()` antes do insert, que perderia a
    corrida entre duas reentregas simultâneas.
    """
    gravadas = []
    for entrada in entradas:
        try:
            with transaction.atomic():
                gravadas.append(
                    MensagemRecebida.objects.create(
                        wa_message_id=entrada.wa_message_id,
                        numero=entrada.numero,
                        tipo=entrada.tipo,
                        texto=entrada.texto,
                        media_id=entrada.media_id,
                    )
                )
        except IntegrityError:
            logger.info("Reentrega ignorada: %s", entrada.wa_message_id)
    return gravadas


def _conversa_do_numero(vinculo) -> Conversa:
    """Continua a conversa aberta, ou começa outra quando ela esfriou.

    Continuidade importa: é ela que faz "qual Silva?" → "1" funcionar pelo
    WhatsApp. Mas retomar uma conversa de semanas atrás faria uma pergunta
    antiga capturar uma resposta nova — então a janela de serviço, que já
    limita o canal, limita também a memória dele.
    """
    corte = timezone.now() - dt.timedelta(hours=config.JANELA_DE_SERVICO_HORAS)
    recente = (
        Conversa.objects.filter(
            usuario=vinculo.usuario,
            canal=Conversa.Canal.WHATSAPP,
            atualizado_em__gte=corte,
        )
        .order_by("-atualizado_em")
        .first()
    )
    return recente or Conversa.objects.create(
        usuario=vinculo.usuario, canal=Conversa.Canal.WHATSAPP
    )


def _texto_da_mensagem(mensagem, transporte, transcritor) -> str | None:
    """O que a pessoa disse, venha como vier. None quando não há o que fazer."""
    if mensagem.tipo == MensagemRecebida.Tipo.TEXTO:
        return mensagem.texto
    if mensagem.tipo == MensagemRecebida.Tipo.AUDIO:
        if transcritor is None:
            return None
        audio, mime = transporte.baixar_midia(mensagem.media_id)
        texto = transcritor.transcrever(audio, mime)
        if texto:
            # A transcrição fica gravada: é ela que explica, depois, por que o
            # assistente entendeu o que entendeu.
            mensagem.texto = texto
            mensagem.save(update_fields=["texto"])
        return texto
    return None


def processar_pendentes(*, transporte=None, transcritor=None, limite: int = 50) -> int:
    """Processa a caixa de entrada. Devolve quantas mensagens foram tratadas."""
    transporte = transporte or obter_transporte()
    if transcritor is None:
        transcritor = obter_transcritor()

    pendentes = MensagemRecebida.objects.filter(
        status=MensagemRecebida.Status.PENDENTE
    ).order_by("recebida_em", "pk")[:limite]

    tratadas = 0
    for mensagem in pendentes:
        try:
            _processar_uma(mensagem, transporte, transcritor)
        except Exception as erro:  # noqa: BLE001 - uma mensagem não derruba a fila
            logger.exception("Falha ao processar %s", mensagem.wa_message_id)
            mensagem.status = MensagemRecebida.Status.ERRO
            mensagem.erro = str(erro)[:2000]
            mensagem.processada_em = timezone.now()
            mensagem.save(update_fields=["status", "erro", "processada_em"])
        tratadas += 1
    return tratadas


def _processar_uma(mensagem, transporte, transcritor) -> None:
    vinculo = buscar_vinculo(mensagem.numero)
    if vinculo is None:
        # Silêncio deliberado: responder confirmaria que o número existe e
        # que há um sistema atrás dele, e ainda abriria conversa paga.
        logger.warning("Mensagem de número sem vínculo: %s", mensagem.numero)
        mensagem.status = MensagemRecebida.Status.IGNORADA
        mensagem.erro = "Número sem vínculo ativo."
        mensagem.processada_em = timezone.now()
        mensagem.save(update_fields=["status", "erro", "processada_em"])
        return

    vinculo.ultima_entrada_em = timezone.now()
    vinculo.save(update_fields=["ultima_entrada_em"])

    if mensagem.tipo == MensagemRecebida.Tipo.OUTRO:
        _enfileirar(mensagem, TIPO_NAO_SUPORTADO)
        _concluir(mensagem)
        return

    texto = _texto_da_mensagem(mensagem, transporte, transcritor)
    if not texto:
        vazio = (
            SEM_TRANSCRICAO
            if mensagem.tipo == MensagemRecebida.Tipo.AUDIO and transcritor is None
            else "Não consegui entender o que você mandou. Pode repetir?"
        )
        _enfileirar(mensagem, vazio)
        _concluir(mensagem)
        return

    conversa = _conversa_do_numero(vinculo)
    # É aqui que o canal acaba: daqui para dentro é o mesmo caminho do painel,
    # com a permissão do usuário vinculado e a confirmação antes de gravar.
    resposta = responder(vinculo.usuario, texto, conversa=conversa)
    mensagem.conversa = conversa
    _enfileirar(mensagem, resposta.texto)
    _concluir(mensagem, campos=["conversa"])


def _concluir(mensagem, campos=()):
    mensagem.status = MensagemRecebida.Status.PROCESSADA
    mensagem.processada_em = timezone.now()
    mensagem.save(update_fields=["status", "processada_em", *campos])


def _enfileirar(mensagem, texto: str) -> MensagemEnviada:
    if len(texto) > LIMITE_CARACTERES:
        corte = LIMITE_CARACTERES - 60
        texto = texto[:corte].rstrip() + "\n\n[…] Abra o sistema para ver a lista inteira."
    return MensagemEnviada.objects.create(
        numero=mensagem.numero, texto=texto, resposta_a=mensagem
    )


def _dentro_da_janela(numero: str) -> bool:
    """Se a conversa de serviço ainda está aberta para este número.

    Fora dela a Meta só aceita template aprovado, que é pago e precisa ter
    sido cadastrado antes. Como este canal é só de entrada, não há template:
    a resposta é recusada com um motivo legível em vez de um HTTP 400 seco.
    """
    vinculo = buscar_vinculo(numero)
    if vinculo is None or vinculo.ultima_entrada_em is None:
        return False
    limite = vinculo.ultima_entrada_em + dt.timedelta(
        hours=config.JANELA_DE_SERVICO_HORAS
    )
    return timezone.now() <= limite


def drenar_saida(*, transporte=None, limite: int = 50) -> int:
    """Envia o que está na fila. Devolve quantas saíram."""
    transporte = transporte or obter_transporte()
    pendentes = MensagemEnviada.objects.filter(
        status=MensagemEnviada.Status.PENDENTE, tentativas__lt=MAX_TENTATIVAS
    ).order_by("criada_em", "pk")[:limite]

    enviadas = 0
    for mensagem in pendentes:
        mensagem.tentativas += 1
        if not _dentro_da_janela(mensagem.numero):
            mensagem.status = MensagemEnviada.Status.ERRO
            mensagem.erro = (
                "Fora da janela de 24h: a Meta só aceitaria um template aprovado, "
                "e este canal não envia mensagem proativa."
            )
            mensagem.save(update_fields=["status", "erro", "tentativas"])
            continue
        try:
            mensagem.wa_message_id = transporte.enviar(mensagem.numero, mensagem.texto)
            mensagem.status = MensagemEnviada.Status.ENVIADA
            mensagem.enviada_em = timezone.now()
            mensagem.erro = ""
            enviadas += 1
        except EnvioIndisponivel as erro:
            # Continua PENDENTE até esgotar as tentativas: token vencido e rede
            # fora do ar se resolvem sozinhos, e a resposta ainda vale.
            mensagem.erro = str(erro)[:2000]
            if mensagem.tentativas >= MAX_TENTATIVAS:
                mensagem.status = MensagemEnviada.Status.ERRO
        mensagem.save(
            update_fields=["status", "erro", "tentativas", "wa_message_id", "enviada_em"]
        )
    return enviadas
