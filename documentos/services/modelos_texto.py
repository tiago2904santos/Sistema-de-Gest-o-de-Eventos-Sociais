"""Textos-base dos modelos de documento, editados pela administração (m057).

Cada tipo de documento tem os seus blocos do modelo (documentos/editor/
blocos.py): título, cabeçalho, parágrafos fixos. O texto que a administração
grava aqui vale no lugar do padrão do sistema para todos os documentos desse
tipo — o que o documento reescreveu só para si (`DocumentoBloco`) e a versão
editada inteira continuam valendo por cima.

O texto em vigor entra no payload por `document_blocks.conteudo_documental`:
muda a chave de cache, então o próximo PDF já sai com o texto novo. O que já
foi emitido fica guardado no artefato, e a via assinada nunca muda.
"""

from __future__ import annotations

import re

from documentos.editor.blocos import blocos_do_tipo

TAMANHO_MAXIMO = 20_000
MARCADOR = re.compile(r"\{(\w+)\}")

# Os campos que os textos do modelo aceitam. Os de viagem usam os rótulos de
# viagens_oficios/campos_modelo.py (os mesmos marcadores dos modelos de motivo
# e de justificativa).
_ROTULOS_PROPRIOS = {
    "assunto": "\"autorização\" ou \"convalidação\", conforme a data do ofício",
    "servidor": "nome do servidor do documento",
    "unidade": "unidade emissora",
}


def rotulos_dos_campos() -> dict[str, str]:
    from viagens_oficios.campos_modelo import CAMPOS

    return {**dict(CAMPOS), **_ROTULOS_PROPRIOS}


# O nome curto de cada campo, para a etiqueta que o representa no texto da
# tela de modelos ("Destino", "Período"); o rótulo acima vai na dica.
NOMES_CURTOS = {
    "destino": "Destino",
    "periodo": "Período",
    "data_saida": "Data de saída",
    "data_retorno": "Data de retorno",
    "dias_antecedencia": "Dias de antecedência",
    "prazo": "Prazo",
    "evento": "Evento",
    "servidores": "Servidores",
    "data_oficio": "Data do ofício",
    "numero_oficio": "Número do ofício",
    "assunto": "Assunto",
    "servidor": "Servidor",
    "unidade": "Unidade",
}


def campos_do_bloco(bloco) -> list[dict]:
    rotulos = rotulos_dos_campos()
    negrito = set(getattr(bloco, "destaque", ()))
    return [
        {"chave": c, "marcador": "{" + c + "}", "rotulo": rotulos.get(c, c),
         "nome": NOMES_CURTOS.get(c, c.replace("_", " ").capitalize()), "negrito": c in negrito}
        for c in getattr(bloco, "campos", ())
    ]


def _tipo(tipo) -> str:
    return str(getattr(tipo, "value", tipo))


def linhas(tipo, chave=None):
    from documentos.models import ModeloTextoDocumento

    consulta = ModeloTextoDocumento.objects.filter(tipo_documento=_tipo(tipo)).select_related("criado_por")
    if chave is not None:
        consulta = consulta.filter(chave=chave)
    return consulta.order_by("-criado_em", "-pk")


def textos_vigentes(tipo) -> dict[str, str]:
    """Chave → texto em vigor, só das chaves que a administração alterou."""
    vistos, textos = set(), {}
    for linha in linhas(tipo).select_related(None).only("chave", "texto", "padrao_sistema", "criado_em"):
        if linha.chave in vistos:
            continue
        vistos.add(linha.chave)
        if not linha.padrao_sistema:
            textos[linha.chave] = linha.texto
    return textos


def texto_vigente(tipo, chave) -> str | None:
    atual = linhas(tipo, chave).first()
    return None if atual is None or atual.padrao_sistema else atual.texto


def estado(tipo) -> str:
    """A marca do modelo para o controle de concorrência: a linha mais
    recente do tipo (qualquer bloco). Quem salva manda a que leu; se outra
    pessoa gravou no meio, a marca mudou."""
    atual = linhas(tipo).select_related(None).only("pk").first()
    return str(atual.pk) if atual else ""


def resumo(tipo) -> dict:
    """Para o cartão do tipo: quantos blocos estão personalizados e a última
    alteração (quando e quem)."""
    return {"personalizados": len(textos_vigentes(tipo)), "ultima": linhas(tipo).first()}


# O que o navegador manda é texto com marcadores: sem caracteres de controle
# (só a quebra de linha), invisíveis nem os de uso privado (as marcas da folha).
_INVISIVEIS = re.compile("[\x00-\x09\x0b-\x1f\x7f​-‍⁠﻿-]")


def limpar(texto) -> str:
    texto = str(texto or "").replace("\r\n", "\n").replace("\r", "\n").replace(" ", " ")
    texto = _INVISIVEIS.sub("", texto)
    return "\n".join(linha.rstrip() for linha in texto.split("\n")).strip()


def texto_em_vigor(tipo, chave) -> str:
    """O texto que o bloco tem hoje: o da administração ou o padrão."""
    vigente = texto_vigente(tipo, chave)
    bloco = blocos_do_tipo(tipo).get(chave)
    return vigente if vigente is not None else (bloco.padrao if bloco else "")


def salvar_blocos(tipo, textos, usuario) -> list[str]:
    """Grava, de uma vez, os textos que mudaram (chave → texto com os
    marcadores `{campo}`). Bloco fora do modelo ou campo que o bloco não
    aceita recusa tudo (ValueError com o motivo). Devolve as chaves gravadas."""
    from django.db import transaction

    blocos = blocos_do_tipo(tipo)
    if not isinstance(textos, dict):
        raise ValueError("Textos inválidos.")
    mudaram, erros = {}, []
    for chave, texto in textos.items():
        bloco = blocos.get(chave)
        if bloco is None or not isinstance(texto, str):
            raise ValueError("Bloco fora do modelo deste documento.")
        if len(texto) > TAMANHO_MAXIMO:
            raise ValueError(f"“{bloco.rotulo}”: texto grande demais.")
        texto = limpar(texto)
        fora = marcadores_desconhecidos(bloco, texto)
        if fora:
            aceitos = ", ".join(c["nome"] for c in campos_do_bloco(bloco)) or "nenhum"
            erros.append(f"“{bloco.rotulo}” não aceita o campo {', '.join('{' + m + '}' for m in fora)} (aceita: {aceitos}).")
            continue
        # Texto apagado volta ao padrão do sistema (como em `gravar`).
        if (texto or limpar(bloco.padrao)) != limpar(texto_em_vigor(tipo, chave)):
            mudaram[chave] = texto
    if erros:
        raise ValueError(" ".join(erros))
    with transaction.atomic():
        for chave, texto in mudaram.items():
            gravar(tipo, chave, texto, usuario)
    return list(mudaram)


def marcadores_desconhecidos(bloco, texto: str) -> list[str]:
    aceitos = set(getattr(bloco, "campos", ()))
    return sorted({m for m in MARCADOR.findall(texto or "") if m not in aceitos})


def gravar(tipo, chave, texto: str, usuario):
    """Grava o texto novo do bloco. Texto vazio ou igual ao do sistema volta
    ao padrão do sistema."""
    from documentos.models import ModeloTextoDocumento

    bloco = blocos_do_tipo(tipo).get(chave)
    if bloco is None:
        raise ValueError("Bloco fora do modelo deste documento.")
    texto = str(texto or "").replace("\r\n", "\n").strip()[:TAMANHO_MAXIMO]
    padrao_sistema = not texto or texto == bloco.padrao
    atual = linhas(tipo, chave).first()
    if atual is not None and atual.padrao_sistema == padrao_sistema and (padrao_sistema or atual.texto == texto):
        return atual  # nada mudou: não acumula linhas iguais
    if atual is None and padrao_sistema:
        return None
    return ModeloTextoDocumento.objects.create(
        tipo_documento=_tipo(tipo), chave=chave, texto="" if padrao_sistema else texto,
        padrao_sistema=padrao_sistema, criado_por=usuario if getattr(usuario, "is_authenticated", False) else None,
    )
