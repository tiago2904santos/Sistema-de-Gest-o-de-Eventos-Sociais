"""A via emitida e a via assinada da OS, do ofício e do certifico.

Cada PDF que sai (visualizar, baixar, o e-mail ao fornecedor, os arquivos do
protocolo) fica guardado como `DocumentoArtefato`, com a data e quem emitiu —
o registro do que exatamente foi à empresa e ao GAF. Um PDF igual ao último
guardado (a mesma folha) não gera outra via: devolve-se o guardado.

A via assinada anexada (`DocumentoAssinaturaVersao`, o mesmo fluxo de Viagens)
passa a valer no lugar da gerada em todo pedido do documento — visualizar,
baixar, e-mail, arquivos do protocolo e pagamento conjunto — até ser removida.

O ofício é do pagamento: as vias dele moram na OS principal
(`principal_do_pagamento`), como os textos reescritos no editor.
"""

from __future__ import annotations

import hashlib
import logging

from django.conf import settings
from django.core.files.base import ContentFile

from .editor import TipoCoffee

logger = logging.getLogger(__name__)

# O nome curto (na URL) de cada documento.
TIPOS = {
    "os": TipoCoffee.ORDEM_SERVICO,
    "oficio": TipoCoffee.OFICIO,
    "certifico": TipoCoffee.CERTIFICO,
}
ROTULOS = {
    TipoCoffee.ORDEM_SERVICO: "Ordem de servico",
    TipoCoffee.OFICIO: "Oficio",
    TipoCoffee.CERTIFICO: "Certifico",
}


def dono(tipo, solicitacao):
    """A solicitação que guarda as vias do documento."""
    return solicitacao.principal_do_pagamento if TipoCoffee(tipo) == TipoCoffee.OFICIO else solicitacao


def _vias(tipo, solicitacao):
    from documentos.models import DocumentoArtefato

    return DocumentoArtefato.objects.filter(
        tipo=TipoCoffee(tipo).value, formato="pdf", coffee_break_solicitacao=dono(tipo, solicitacao)
    )


def vias(tipo, solicitacao):
    """As vias guardadas, da mais recente à mais antiga."""
    return _vias(tipo, solicitacao).select_related("criado_por").order_by("-criado_em")


def ultima_via(tipo, solicitacao):
    return vias(tipo, solicitacao).first()


def assinada(tipo, solicitacao):
    """A versão assinada que vale para o documento (a viva mais recente), ou None."""
    from documentos.models import DocumentoAssinaturaVersao

    return (
        DocumentoAssinaturaVersao.objects.filter(artefato__in=_vias(tipo, solicitacao), revogada_em__isnull=True)
        .select_related("criado_por", "artefato")
        .order_by("-criado_em")
        .first()
    )


def _ler(arquivo):
    try:
        with arquivo.open("rb") as aberto:
            return aberto.read()
    except (FileNotFoundError, OSError, ValueError):
        logger.warning("Via do Coffee Break sem arquivo no storage (%s).", getattr(arquivo, "name", "?"))
        return None


def conteudo_assinado(tipo, solicitacao):
    versao = assinada(tipo, solicitacao)
    return _ler(versao.arquivo) if versao is not None else None


def _usuario_atual():
    from core.middleware import obter_requisicao_atual

    usuario = getattr(obter_requisicao_atual(), "user", None)
    return usuario if getattr(usuario, "is_authenticated", False) else None


def emitir(tipo, solicitacao, html, gerar_pdf):
    """O PDF do documento: a via assinada, se houver; senão a folha `html` em
    PDF (`gerar_pdf(html)`), guardada como via emitida.

    A mesma folha do último PDF guardado devolve o guardado, sem gerar de novo
    nem acumular vias iguais.
    """
    from documentos.models import DocumentoArtefato

    assinado = conteudo_assinado(tipo, solicitacao)
    if assinado is not None:
        return assinado
    persistir = getattr(settings, "DOCUMENTOS_PERSIST_ARTEFATOS", True) and solicitacao.pk
    marca = hashlib.sha256(html.encode("utf-8")).hexdigest()
    if persistir:
        ultima = _vias(tipo, solicitacao).order_by("-criado_em").first()
        if ultima is not None and ultima.cache_key == marca:
            guardado = _ler(ultima.arquivo)
            if guardado is not None:
                return guardado
    conteudo = gerar_pdf(html)
    if not persistir:
        return conteudo
    from documentos.services.filenames import slugify_filename_part

    responsavel = dono(tipo, solicitacao)
    referencia = slugify_filename_part(
        (responsavel.numero_oficio if TipoCoffee(tipo) == TipoCoffee.OFICIO else responsavel.numero) or str(responsavel.pk)
    )
    nome = f"{TipoCoffee(tipo).value}_{referencia}_{responsavel.pk}.pdf"
    artefato = DocumentoArtefato(
        tipo=TipoCoffee(tipo).value,
        formato="pdf",
        coffee_break_solicitacao=responsavel,
        criado_por=_usuario_atual(),
        nome_exibicao=nome,
        hash_sha256=hashlib.sha256(conteudo).hexdigest(),
        cache_key=marca,
        engine="weasyprint",
        arquivo=ContentFile(conteudo, name=nome),
    )
    try:
        artefato.save()
    except Exception:
        if artefato.arquivo and artefato.arquivo._committed:
            artefato.arquivo.storage.delete(artefato.arquivo.name)
        raise
    return conteudo


def resumo(tipo, solicitacao):
    """O que a tela mostra do documento: a última via emitida e a assinada."""
    versao = assinada(tipo, solicitacao)
    ultima = ultima_via(tipo, solicitacao)
    return {
        "assinado": versao is not None,
        "assinada_em": versao.criado_em if versao else None,
        "assinada_por": versao.criado_por if versao else None,
        "emitida_em": ultima.criado_em if ultima else None,
        "emitida_por": ultima.criado_por if ultima else None,
        "vias": _vias(tipo, solicitacao).count(),
    }
