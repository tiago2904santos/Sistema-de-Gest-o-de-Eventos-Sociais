"""O "Consultar andamento" das telas que guardam um número do eProtocolo.

Solicitações de evento e palestras chegam muitas vezes por protocolo. Aqui
fica o que as duas telas repetiriam: normalizar o número (00.000.000-0),
consultar a última movimentação pela integração — que responde em modo
simulado enquanto não houver credencial — e guardar o resultado na sessão
para a tela mostrar num cartão depois do redirecionamento.

Só leitura: consultar não grava nada no eProtocolo nem no banco.
"""

from __future__ import annotations

import re
from datetime import datetime

from django.utils import timezone

from . import services
from .exceptions import EProtocoloError

CHAVE_SESSAO = "andamento_eprotocolo"


def formatar_numero(texto) -> str | None:
    """"00.000.000-0" a partir do que foi digitado; "" se vazio; None se inválido."""
    digitos = re.sub(r"\D", "", texto or "")
    if not digitos:
        return ""
    if len(digitos) != 9:
        return None
    return f"{digitos[:2]}.{digitos[2:5]}.{digitos[5:8]}-{digitos[8]}"


def _data_legivel(valor) -> str:
    if not valor:
        return ""
    try:
        momento = datetime.fromisoformat(str(valor).replace("Z", "+00:00"))
    except ValueError:
        return str(valor)
    if timezone.is_aware(momento):
        momento = timezone.localtime(momento)
    return momento.strftime("%d/%m/%Y %H:%M")


def _situacao_legivel(valor) -> str:
    texto = str(valor or "").replace("_", " ").strip()
    return texto[:1].upper() + texto[1:].lower() if texto else ""


def consultar_andamento(numero: str) -> dict:
    """A última movimentação do protocolo, pronta para o cartão da tela.

    Levanta ``EProtocoloError`` quando o eProtocolo não responde — quem chama
    transforma em mensagem.
    """
    # Na URL da API vão só os dígitos; na tela, o número como no ofício.
    resultado = services.consultar_protocolo(re.sub(r"\D", "", numero))
    dados = resultado.dados or {}
    return {
        "numero": numero,
        "situacao": _situacao_legivel(dados.get("situacao")),
        "local": dados.get("nomeLocalAtual") or dados.get("codLocalAtual") or "",
        "ultima_movimentacao": _data_legivel(dados.get("ultimaMovimentacao")),
        "simulado": bool(resultado.mock),
        "consultado_em": timezone.localtime().strftime("%d/%m/%Y %H:%M"),
    }


def consultar_e_guardar(request, modulo: str, pk: int, numero: str) -> str:
    """Consulta e guarda o resultado para a próxima tela; devolve o erro, se houver."""
    try:
        andamento = consultar_andamento(numero)
    except EProtocoloError as erro:
        return f"Não foi possível consultar o eProtocolo agora: {erro}"
    request.session[CHAVE_SESSAO] = {"modulo": modulo, "pk": pk, **andamento}
    return ""


def andamento_guardado(request, modulo: str, pk: int) -> dict | None:
    """O resultado da consulta desta tela, lido uma vez só."""
    guardado = request.session.get(CHAVE_SESSAO)
    if not guardado or guardado.get("modulo") != modulo or guardado.get("pk") != pk:
        return None
    del request.session[CHAVE_SESSAO]
    return guardado
