"""Pacote do protocolo de pagamento no eProtocolo (etapa 3).

O eProtocolo que o sistema alcança hoje é o de treinamento/simulado
(``integracoes/eprotocolo``, ``EPROTOCOLO["AMBIENTE"]`` = mock): não abre
processo de verdade. Por isso o protocolo de pagamento se abre à mão, e o
sistema entrega tudo pronto para isso:

- os dados do cadastro para copiar (interessado, assunto, palavras-chave,
  Nº/ano, detalhamento) e o despacho ao GAF (documentos.textos_eprotocolo);
- a ordem dos documentos (os quatro arquivos do anexo, documentos.partes_do_anexo)
  e o modal "Baixar documentos" com o PDF único ou o ZIP;
- o passo a passo na tela;
- o registro do número aberto (00.000.000-0), que vira o protocolo do ofício
  e, com a nota, o do pagamento em todas as OS do mesmo pagamento, com
  histórico.

Integração real (futuro): quando houver credenciais da Celepar e o ambiente
de produção, ``payload_integracao`` já monta o que
``integracoes.eprotocolo.services.criar_protocolo`` recebe
(``integracoes.eprotocolo.mappers.mapear_pagamento_coffee``). O caminho seria:
``criar_protocolo(payload)`` → ``registrar_numero`` com o número devolvido →
incluir cada arquivo de ``documentos.partes_do_anexo`` pelo endpoint
``Endpoints.DOCUMENTOS`` (definido em integracoes/eprotocolo/schemas.py, ainda
sem cliente) → ``services.sincronizar_protocolo``. Até lá, nada aqui chama a
rede.
"""

import re

from django.core.exceptions import ValidationError

from core.utils.masks import format_protocolo, normalize_protocolo

from . import documentos, services
from .models import AcaoHistoricoCoffeeBreak

FORMATO_PROTOCOLO = re.compile(r"^\d{2}\.\d{3}\.\d{3}-\d$")


def validar_numero(texto):
    """O número do eProtocolo: 00.000.000-0 (nove dígitos; a máscara se põe
    sozinha quando vêm só os dígitos). Levanta ValidationError."""
    texto = " ".join((texto or "").split())
    if not texto:
        raise ValidationError("Informe o número do protocolo aberto no eProtocolo.")
    numero = format_protocolo(texto)
    if len(normalize_protocolo(texto)) != 9 or not FORMATO_PROTOCOLO.match(numero):
        raise ValidationError("O número do protocolo deve estar no formato 00.000.000-0.")
    return numero


def passos(solicitacao):
    """O passo a passo para abrir o protocolo à mão, na ordem do trabalho."""
    return [
        "No eProtocolo, abra um novo protocolo e informe o interessado (CNPJ e nome), "
        "o assunto, as palavras-chave e o Nº/ano do ofício — copie de \"Dados para o eProtocolo\".",
        "Cole o detalhamento.",
        "Baixe os documentos (\"Baixar documentos\": um PDF só, ou separados) e anexe na ordem "
        "da lista \"Anexo do protocolo\": OS, ofício, notas com os certificos, contrato com "
        "aditivos e certidões.",
        "Assine no eProtocolo o ofício e o certifico e despache ao GAF com o texto do despacho.",
        "Volte aqui e registre o número do protocolo aberto (00.000.000-0).",
    ]


def registrar_numero(solicitacao, texto, usuario):
    """Grava o número do protocolo aberto à mão: vira o "PCPR protocolo n.º"
    do ofício (em todas as OS do pagamento) e, com a nota, o protocolo de
    pagamento. Devolve (numero, virou_pagamento)."""
    if solicitacao.bloqueada_para_edicao:
        raise ValidationError("Solicitações canceladas ou concluídas ficam bloqueadas para edição.")
    numero = validar_numero(texto)
    anterior = solicitacao.protocolo_pcpr_oficio
    if anterior != numero:
        solicitacao.protocolo_pcpr_oficio = numero
        solicitacao.save(update_fields=["protocolo_pcpr_oficio", "atualizado_em"])
        services.espelhar(solicitacao, ["protocolo_pcpr_oficio"], usuario)
        services.registrar_historico(
            solicitacao, usuario, AcaoHistoricoCoffeeBreak.ATUALIZACAO,
            f"Protocolo aberto no eProtocolo registrado: {numero}"
            + (f" (antes: {anterior})." if anterior else "."),
        )
    services.sincronizar_protocolo(solicitacao, usuario)
    solicitacao.refresh_from_db(fields=["protocolo_pagamento"])
    return numero, solicitacao.protocolo_pagamento == numero


def payload_integracao(solicitacao):
    """O que a integração real mandaria ao eProtocolo (ver o topo do módulo).
    Não é chamado pela tela enquanto o eProtocolo for só de treinamento."""
    from integracoes.eprotocolo.mappers import mapear_pagamento_coffee

    return mapear_pagamento_coffee(
        textos=documentos.textos_eprotocolo(solicitacao),
        partes=documentos.partes_do_anexo(solicitacao),
        fornecedor=solicitacao.lote.contrato.fornecedor,
        numero_oficio=solicitacao.numero_oficio,
    )
