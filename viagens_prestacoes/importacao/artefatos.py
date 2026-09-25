"""Os documentos do processo que voltam para o documento gerado pelo sistema.

O ofício, a justificativa, os termos de autorização (um por servidor) e a ordem
de serviço saem do sistema em PDF (`DocumentoArtefato`) e voltam assinados no
processo do eProtocolo. O lugar deles é a versão assinada do próprio documento
(`documentos.services.persistence.anexar_arquivo_assinado`) — a mesma que o
"Anexar assinado" das listas de Ofícios, Termos e OS grava, e que passa a valer
no "Visualizar" e no "Baixar documentos".

**Onde anexar.** Cada documento tem os seus PDFs gerados (mesmo tipo, mesmos
vínculos, mesma referência de geração: é por eles que a geração acha a versão
assinada depois). A versão vai no mais recente. Sem PDF gerado — o termo de um
servidor que nunca foi baixado —, o PDF é gerado agora, pelo serviço de sempre,
e o assinado vai nele.

**Termo de um servidor** pode ter dois donos: o termo tirado do ofício (lista de
Ofícios, servidores marcados para termo) e o termo do cadastro (lista de Termos),
avulso ou preso ao ofício. O papel assinado é um só, então ele entra em todos os
que existem para aquele servidor naquela viagem.

Nada aqui abre transação própria para a leitura: quem chama (a aplicação do
plano) já está dentro de `transacao_de_arquivos`, e tudo o que é gravado aqui —
o PDF gerado e a versão assinada — fica registrado para compensação.
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from dataclasses import dataclass

from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile

from documentos.services.types import DocumentoFormato
from documentos.services.types import DocumentoTipo

from ..arquivos import transacao_de_arquivos

__all__ = [
    "Alvo",
    "DocumentoSemPDF",
    "alvos_da_justificativa",
    "alvos_da_ordem",
    "alvos_do_oficio",
    "alvos_do_termo",
    "anexar_nos_alvos",
    "servidores_com_termo",
    "termos_do_oficio",
]


class DocumentoSemPDF(Exception):
    """Não há PDF gerado do documento e não deu para gerar agora (mensagem para a tela)."""


@dataclass
class Alvo:
    """Um documento gerado pelo sistema que recebe a versão assinada.

    `vinculos` e `referencia` são os da geração (é por eles que se acham os PDFs
    gerados, e a geração acha a versão assinada); `gerar` produz o PDF quando
    ainda não há nenhum, sem a versão assinada no lugar.
    """

    tipo: DocumentoTipo
    rotulo: str
    referencia: str
    vinculos: dict
    gerar: Callable
    #: Para a tela: a página do documento, onde se confere o que foi anexado.
    url_pagina: str = ""


def _vinculos(**vinculos) -> dict:
    base = {"oficio_id": None, "termo_id": None, "prestacao_id": None, "servidor_id": None,
            "ordem_servico_id": None, "plano_trabalho_id": None}
    base.update(vinculos)
    return base


# ─────────────────────────────────────────────────────────────────
# Quais documentos recebem o assinado
# ─────────────────────────────────────────────────────────────────

def alvos_do_oficio(oficio) -> list[Alvo]:
    from django.urls import reverse

    from viagens_oficios.document_generation import gerar_documento
    from viagens_oficios.document_generation import referencia_do_oficio

    return [Alvo(
        tipo=DocumentoTipo.OFICIO,
        rotulo=f"Ofício {oficio.numero_formatado}",
        referencia=referencia_do_oficio(oficio),
        vinculos=_vinculos(oficio_id=oficio.pk),
        gerar=lambda: gerar_documento(oficio, DocumentoFormato.PDF, DocumentoTipo.OFICIO, usar_assinado=False),
        url_pagina=reverse("viagens_oficios:editar", args=[oficio.pk]),
    )]


def alvos_da_justificativa(oficio) -> list[Alvo]:
    from django.urls import reverse

    from viagens_oficios.document_generation import gerar_documento
    from viagens_oficios.document_generation import referencia_do_oficio

    return [Alvo(
        tipo=DocumentoTipo.JUSTIFICATIVA,
        rotulo=f"Justificativa do Ofício {oficio.numero_formatado}",
        referencia=referencia_do_oficio(oficio),
        vinculos=_vinculos(oficio_id=oficio.pk),
        gerar=lambda: gerar_documento(oficio, DocumentoFormato.PDF, DocumentoTipo.JUSTIFICATIVA, usar_assinado=False),
        url_pagina=reverse("viagens_oficios:editar", args=[oficio.pk]),
    )]


def termos_do_oficio(oficio, *, alem_de=None) -> list:
    """Os termos do cadastro (lista de Termos) presos ao ofício, sem os cancelados."""
    if oficio is None:
        return [alem_de] if alem_de is not None and not alem_de.cancelado else []
    from viagens_termos.models import TermoAutorizacao

    termos = list(TermoAutorizacao.objects.filter(oficio=oficio, cancelado=False).select_related("oficio").order_by("pk"))
    if alem_de is not None and not alem_de.cancelado and all(t.pk != alem_de.pk for t in termos):
        termos.insert(0, alem_de)
    return termos


def servidores_com_termo(oficio, termo=None) -> list:
    """Quem pode ter termo nesta viagem: os marcados para termo no ofício e os do(s) termo(s) do cadastro.

    Na ordem em que o sistema gera os termos (por nome), sem repetir.
    """
    vistos: dict[int, object] = {}
    if oficio is not None:
        for servidor in oficio.servidores_termo_autorizacao.order_by("nome"):
            vistos.setdefault(servidor.pk, servidor)
    for cadastro in termos_do_oficio(oficio, alem_de=termo):
        for servidor in cadastro.servidores_efetivos():
            vistos.setdefault(servidor.pk, servidor)
    return sorted(vistos.values(), key=lambda s: (s.nome, s.pk))


def alvos_do_termo(servidor, *, oficio=None, termo=None) -> list[Alvo]:
    """O termo tirado do ofício (se o servidor está marcado para termo) e os do cadastro que o incluem."""
    from django.urls import reverse

    from viagens_termos.services import gerar_termo_cadastro_um
    from viagens_termos.services import gerar_termo_um
    from viagens_termos.services import referencia_termo_do_cadastro
    from viagens_termos.services import referencia_termo_do_oficio

    alvos: list[Alvo] = []
    if oficio is not None and not oficio.cancelado and oficio.servidores_termo_autorizacao.filter(pk=servidor.pk).exists():
        alvos.append(Alvo(
            tipo=DocumentoTipo.TERMO_AUTORIZACAO,
            rotulo=f"Termo de {servidor.nome} · Ofício {oficio.numero_formatado}",
            referencia=referencia_termo_do_oficio(oficio, servidor),
            vinculos=_vinculos(oficio_id=oficio.pk, servidor_id=servidor.pk),
            gerar=lambda: gerar_termo_um(oficio, servidor, DocumentoFormato.PDF, usar_assinado=False),
            url_pagina=reverse("viagens_oficios:editar", args=[oficio.pk]),
        ))
    for cadastro in termos_do_oficio(oficio, alem_de=termo):
        if not cadastro.servidores_efetivos().filter(pk=servidor.pk).exists():
            continue
        alvos.append(Alvo(
            tipo=DocumentoTipo.TERMO_AUTORIZACAO,
            rotulo=f"Termo #{cadastro.pk} de {servidor.nome}",
            referencia=referencia_termo_do_cadastro(cadastro, servidor),
            vinculos=_vinculos(oficio_id=cadastro.oficio_id, termo_id=cadastro.pk, servidor_id=servidor.pk),
            gerar=(lambda cadastro=cadastro: gerar_termo_cadastro_um(cadastro, servidor, DocumentoFormato.PDF, usar_assinado=False)),
            url_pagina=reverse("viagens_termos:editar", args=[cadastro.pk]),
        ))
    return alvos


def alvos_da_ordem(ordem) -> list[Alvo]:
    from django.urls import reverse

    from viagens_ordens.services import gerar_ordem_servico
    from viagens_ordens.services import referencia_da_ordem

    numero = f"{ordem.numero:02d}/{ordem.ano}" if ordem.numero and ordem.ano else f"#{ordem.pk}"
    return [Alvo(
        tipo=DocumentoTipo.ORDEM_SERVICO,
        rotulo=f"Ordem de Serviço {numero}",
        referencia=referencia_da_ordem(ordem),
        vinculos=_vinculos(ordem_servico_id=ordem.pk),
        gerar=lambda: gerar_ordem_servico(ordem, DocumentoFormato.PDF, usar_assinado=False),
        url_pagina=reverse("viagens_ordens:editar", args=[ordem.pk]),
    )]


# ─────────────────────────────────────────────────────────────────
# Anexar
# ─────────────────────────────────────────────────────────────────

def _mensagem(exc) -> str:
    if isinstance(exc, ValidationError):
        return "; ".join(exc.messages)
    return str(exc) or exc.__class__.__name__


def _artefato_para_assinar(alvo: Alvo):
    """O PDF gerado mais recente do documento; sem nenhum, gera agora (num savepoint)."""
    from documentos.models import DocumentoArtefato
    from documentos.services.assinados import artefatos_do_documento
    from documentos.services.exceptions import DocumentError

    artefato = artefatos_do_documento(alvo.tipo, reference=alvo.referencia, **alvo.vinculos).order_by("-criado_em").first()
    if artefato is not None:
        return artefato, False
    try:
        with transacao_de_arquivos():
            gerado = alvo.gerar()
    except (ValidationError, DocumentError, ValueError) as exc:
        raise DocumentoSemPDF(
            f"{alvo.rotulo}: o assinado não foi anexado ao documento — não há PDF gerado, e não deu para gerar agora "
            f"({_mensagem(exc)})."
        ) from exc
    if not getattr(gerado, "artefato_id", None):
        raise DocumentoSemPDF(
            f"{alvo.rotulo}: o assinado não foi anexado ao documento — os PDFs gerados não são guardados neste servidor."
        )
    return DocumentoArtefato.objects.get(pk=gerado.artefato_id), True


def _ja_anexado(alvo: Alvo, sha256: str) -> bool:
    """A versão assinada que vale hoje é este mesmo arquivo (importar de novo não repete a versão)."""
    from documentos.models import DocumentoAssinaturaVersao
    from documentos.services.assinados import artefatos_do_documento

    vigente = (
        DocumentoAssinaturaVersao.objects
        .filter(artefato__in=artefatos_do_documento(alvo.tipo, reference=alvo.referencia, **alvo.vinculos),
                revogada_em__isnull=True)
        .order_by("-criado_em")
        .first()
    )
    return vigente is not None and vigente.hash_sha256 == sha256


@dataclass
class Anexado:
    """O que aconteceu com um alvo: anexado (com ou sem geração do PDF antes) ou já estava lá."""

    alvo: Alvo
    artefato_id: str = ""
    gerado: bool = False
    repetido: bool = False


def anexar_nos_alvos(alvos: list[Alvo], pdf: bytes, nome_arquivo: str) -> tuple[list[Anexado], list[str]]:
    """Anexa `pdf` como versão assinada de cada alvo. Devolve (anexados, avisos).

    O alvo sem PDF que não pôde ser gerado vira aviso e fica de fora; qualquer
    outra falha sobe e desfaz a importação inteira (quem chama está na transação).
    """
    from documentos.services.persistence import anexar_arquivo_assinado

    sha256 = hashlib.sha256(pdf).hexdigest()
    nome = nome_arquivo if nome_arquivo.lower().endswith(".pdf") else f"{nome_arquivo}.pdf"
    anexados: list[Anexado] = []
    avisos: list[str] = []
    for alvo in alvos:
        if _ja_anexado(alvo, sha256):
            anexados.append(Anexado(alvo=alvo, repetido=True))
            continue
        try:
            artefato, gerado = _artefato_para_assinar(alvo)
        except DocumentoSemPDF as exc:
            avisos.append(str(exc))
            continue
        anexar_arquivo_assinado(artefato, SimpleUploadedFile(nome[:255], pdf, content_type="application/pdf"))
        anexados.append(Anexado(alvo=alvo, artefato_id=str(artefato.pk), gerado=gerado))
    return anexados, avisos
