"""A via emitida de um documento (m113): o PDF que saiu, reimpresso igual.

Todo PDF era remontado na hora com os dados atuais: mudou o chefe que
assina, o destinatário ou o endereço da unidade, um ofício antigo
reimpresso saía com o nome e o cabeçalho novos. Agora a primeira emissão
do PDF de um documento (a geração que o tira do rascunho, o "Baixar PDF",
o iframe da conferência) fica registrada no artefato como **via emitida**,
versão 1, e todo pedido seguinte do PDF — visualizar, baixar, o ZIP, o PDF
único, o anexo do processo — entrega essa via, sem gerar de novo.

Para mudar o que foi emitido, a pessoa pede "Emitir nova versão": o PDF é
refeito com os dados de hoje e vira a versão seguinte (2, 3...). Se nada
mudou, a via continua a mesma e nenhum número novo é gasto. A via assinada
anexada continua valendo por cima de tudo, como antes.

O próprio documento alterado depois da via (m140) — os dados do ofício, do
plano, da OS…, um bloco reescrito no editor ou uma versão editada — também
faz a versão seguinte sozinho: quem mudou o documento e clica em baixar quer
o que está vendo, não a via de antes. O que continua congelado é a mudança
de fora (o chefe que assina, o endereço da unidade na configuração).

"Mesmo documento" é o recorte de `documentos.services.assinados`: o tipo,
os vínculos (ofício, termo, prestação, OS, plano, servidor) e a referência
de geração, que separa, por exemplo, o termo vazio do termo da viatura.
"""

from __future__ import annotations

import logging
from dataclasses import replace
from datetime import timedelta

from django.conf import settings
from django.core.files.base import ContentFile
from django.db import transaction
from django.utils import timezone

from documentos.services.types import DocumentoFormato

logger = logging.getLogger(__name__)


def _vinculos_do_artefato(artefato) -> dict:
    return {
        "oficio_id": artefato.oficio_id, "termo_id": artefato.termo_id,
        "prestacao_id": artefato.prestacao_id, "servidor_id": artefato.servidor_id,
        "ordem_servico_id": artefato.ordem_servico_id, "plano_trabalho_id": artefato.plano_trabalho_id,
    }


def vias_emitidas(tipo, *, reference=None, **vinculos):
    """As vias emitidas do documento, da mais recente à primeira."""
    from documentos.services.assinados import artefatos_do_documento

    return (
        artefatos_do_documento(tipo, reference=reference, **vinculos)
        .filter(versao_emitida__isnull=False)
        .order_by("-versao_emitida", "-criado_em")
    )


def via_emitida(tipo, *, reference=None, **vinculos):
    """A via emitida vigente (a de maior versão), ou None."""
    if not any(vinculos.values()):
        return None
    return vias_emitidas(tipo, reference=reference, **vinculos).first()


def documento_da_via(via, *, tipo, reference=None):
    """O `DocumentoGerado` com o conteúdo da via, ou None se o arquivo sumiu
    do storage (aí o documento é gerado de novo, e a via registrada de novo)."""
    from documentos.services.document_cache import documento_gerado_from_artifact

    try:
        if not via.arquivo or not via.arquivo.storage.exists(via.arquivo.name):
            return None
        return documento_gerado_from_artifact(via, tipo=tipo, formato=DocumentoFormato.PDF, reference=reference)
    except (FileNotFoundError, OSError, ValueError):
        logger.warning("Via emitida %s sem arquivo no storage; gerando o PDF de novo.", via.pk)
        return None


def _usuario_atual():
    from core.middleware import obter_requisicao_atual

    usuario = getattr(obter_requisicao_atual(), "user", None)
    return usuario if getattr(usuario, "is_authenticated", False) else None


def _copia(artefato):
    """Um artefato novo com o mesmo conteúdo, para a via de um documento que
    voltou a um estado já emitido antes (o cache devolveu uma via antiga)."""
    from documentos.models import DocumentoArtefato

    with artefato.arquivo.open("rb") as origem:
        conteudo = origem.read()
    copia = DocumentoArtefato(
        tipo=artefato.tipo, formato=artefato.formato, nome_exibicao=artefato.nome_exibicao,
        payload_snapshot=artefato.payload_snapshot, hash_sha256=artefato.hash_sha256,
        cache_key=artefato.cache_key, generator_version=artefato.generator_version, engine=artefato.engine,
        criado_por_id=artefato.criado_por_id, roteiro_id=artefato.roteiro_id, **_vinculos_do_artefato(artefato),
        arquivo=ContentFile(conteudo, name=artefato.nome_exibicao or "documento.pdf"),
    )
    copia.save()
    return copia


@transaction.atomic
def registrar_emissao(artefato, *, reference=None, usuario=None, nova_versao=False):
    """Marca o artefato como a via emitida do documento dele.

    Sem via: versão 1. Com via e `nova_versao`: a seguinte — a não ser que o
    conteúdo seja o mesmo da via vigente (nada mudou), e aí ela continua.
    Com via e sem `nova_versao`, nada muda: a via vigente é a que vale.
    Devolve o artefato que é a via vigente ao fim.
    """
    from documentos.models import DocumentoArtefato
    from documentos.services.types import DocumentoTipo

    if artefato is None or artefato.formato != DocumentoFormato.PDF.value:
        return artefato
    tipo = DocumentoTipo(artefato.tipo)
    vinculos = _vinculos_do_artefato(artefato)
    vigente = via_emitida(tipo, reference=reference, **vinculos)
    if vigente is not None:
        # "Nada mudou" é a mesma chave de cache (dados + modelo): os bytes do
        # PDF variam a cada geração (identificador e subconjuntos de fonte).
        mesma = vigente.pk == artefato.pk or vigente.hash_sha256 == artefato.hash_sha256 or (
            bool(vigente.cache_key) and vigente.cache_key == artefato.cache_key
        )
        if not nova_versao or mesma:
            return vigente
        if artefato.versao_emitida is not None:
            artefato = _copia(artefato)
        numero = (vigente.versao_emitida or 0) + 1
    else:
        numero = 1
    DocumentoArtefato.objects.filter(pk=artefato.pk).update(
        versao_emitida=numero, emitida_em=timezone.now(),
        emitida_por=usuario if usuario is not None else _usuario_atual(),
    )
    artefato.refresh_from_db(fields=["versao_emitida", "emitida_em", "emitida_por"])
    return artefato


FOLGA_DA_EMISSAO_S = 20

_VINCULOS_DO_DOCUMENTO = ("oficio_id", "termo_id", "prestacao_id", "ordem_servico_id", "plano_trabalho_id")


def documento_alterado_depois(via, **vinculos) -> bool:
    """O documento (o objeto, os blocos do editor ou a versão editada) mudou depois da via?"""
    from documentos.models import DocumentoArtefato, DocumentoBloco, DocumentoVersaoEditada

    quando = via.emitida_em or via.criado_em
    if quando is None:
        return False
    # A própria emissão mexe no documento logo depois (status "gerado", data
    # do documento): isso não é alteração de quem edita.
    quando = quando + timedelta(seconds=FOLGA_DA_EMISSAO_S)
    for campo in _VINCULOS_DO_DOCUMENTO:
        valor = vinculos.get(campo)
        if not valor:
            continue
        modelo = DocumentoArtefato._meta.get_field(campo[:-3]).related_model
        if any(f.name == "atualizado_em" for f in modelo._meta.get_fields()):
            if modelo.objects.filter(pk=valor, atualizado_em__gt=quando).exists():
                return True
        filtro = {campo: valor}
        if DocumentoBloco.objects.filter(atualizado_em__gt=quando, **filtro).exists():
            return True
        if DocumentoVersaoEditada.objects.filter(criado_em__gt=quando, **filtro).exists():
            return True
    return False


def emitir(tipo, formato, gerar, *, reference=None, usar_assinado=True, nova_versao=False, usuario=None, **vinculos):
    """O PDF do documento: a via assinada, se houver; senão a via emitida;
    senão o que `gerar()` produz, que passa a ser a via (versão 1, ou a
    seguinte com `nova_versao`). Outros formatos passam direto por `gerar`.
    """
    if formato != DocumentoFormato.PDF or not getattr(settings, "DOCUMENTOS_PERSIST_ARTEFATOS", True):
        return gerar()
    if usar_assinado:
        from documentos.services.assinados import documento_assinado

        assinado = documento_assinado(tipo, formato, reference=reference, **vinculos)
        if assinado is not None:
            return assinado
    if not nova_versao:
        via = via_emitida(tipo, reference=reference, **vinculos)
        if via is not None and documento_alterado_depois(via, **vinculos):
            # Mudou depois da via: refaz; conteúdo igual mantém a mesma via.
            nova_versao = True
        elif via is not None:
            pronto = documento_da_via(via, tipo=tipo, reference=reference)
            if pronto is not None:
                return pronto
    resultado = gerar()
    if resultado.artefato_id is None or resultado.pdf_engine_used == "assinado":
        return resultado
    from documentos.models import DocumentoArtefato

    artefato = DocumentoArtefato.objects.filter(pk=resultado.artefato_id).first()
    if artefato is None:
        return resultado
    via = registrar_emissao(artefato, reference=reference, usuario=usuario, nova_versao=nova_versao)
    if via.pk != artefato.pk:
        # O cache devolveu outra geração, mas a via vigente é a que vale.
        pronto = documento_da_via(via, tipo=tipo, reference=reference)
        if pronto is not None:
            return pronto
    return replace(resultado, artefato_id=via.pk)


def resumo_da_via(via) -> dict:
    """O que a tela diz da via: "Versão 2 emitida em 03/09/2026 por Fulana"."""
    if via is None:
        return {"versao": None, "emitida_em": None, "emitida_por": ""}
    return {
        "versao": via.versao_emitida,
        "emitida_em": via.emitida_em,
        "emitida_por": (str(via.emitida_por) if via.emitida_por_id else ""),
    }
