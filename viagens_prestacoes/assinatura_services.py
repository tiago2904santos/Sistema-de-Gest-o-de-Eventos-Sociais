"""Assinatura eletrônica de RT e Diário de Bordo.

Fluxo: a partir da tela do documento gera-se um link para o operador compartilhar
com o signatário. O signatário confirma identidade (5 primeiros dígitos do CPF +
nome) e envia uma assinatura (nome em fonte manuscrita OU desenho à mão) renderizada
como PNG transparente no navegador. O servidor apenas **carimba** esse PNG sobre o
snapshot do PDF (``arquivo_origem``) e guarda o resultado em ``arquivo_assinado``.

O carimbo é puro Python (reportlab + pypdf) e independe do motor de geração de PDF.
"""

from __future__ import annotations

import hashlib
import math
from django.db import transaction
from django.utils.crypto import constant_time_compare, salted_hmac
from .arquivos import atomico_com_arquivos
import secrets
from datetime import timedelta
from io import BytesIO

from django.core.files.base import ContentFile
from django.utils import timezone

from core.errors import capture
from documentos.services.pdf_overlay import PdfOverlayError
from documentos.services.pdf_overlay import desenhar_overlay

from .models import AssinaturaDocumento
from .models import DiarioBordo
from .models import RelatorioTecnico


class AssinaturaError(Exception):
    """Erro amigável exibido ao usuário (ex.: signatário sem CPF, link expirado)."""


# ─────────────────────────────────────────────────────────────────
# Resolução do signatário
# ─────────────────────────────────────────────────────────────────

def signer_rt(servidor_prestacao):
    """Servidor que assina o Relatório Técnico (é o próprio servidor da linha)."""
    return getattr(servidor_prestacao, "servidor", None) if servidor_prestacao else None


def signer_db(prestacao):
    diario = getattr(prestacao, "diario_bordo", None)
    if diario and diario.motorista_modo == DiarioBordo.MOTORISTA_MODO_SERVIDOR:
        return diario.motorista_servidor
    if diario and diario.motorista_modo == DiarioBordo.MOTORISTA_MODO_OUTRO:
        return None
    return getattr(prestacao.oficio, "motorista", None)


def _cpf_valido(servidor) -> bool:
    cpf = (getattr(servidor, "cpf", "") or "").strip()
    return len(cpf) == 11 and cpf.isdigit()


# ─────────────────────────────────────────────────────────────────
# Geração do snapshot (PDF não assinado)
# ─────────────────────────────────────────────────────────────────

def _origem_rt_bytes(prestacao, servidor_prestacao) -> bytes:
    from .services import gerar_relatorio_tecnico_pdf

    relatorio, _ = RelatorioTecnico.objects.get_or_create(prestacao=prestacao)
    return gerar_relatorio_tecnico_pdf(relatorio, servidor_prestacao)


def _origem_db_bytes(prestacao) -> bytes:
    from .diario_services import gerar_diario_bordo_pdf

    diario, _ = DiarioBordo.objects.get_or_create(prestacao=prestacao)
    return gerar_diario_bordo_pdf(diario)


# ─────────────────────────────────────────────────────────────────
# Emissão / consulta de link
# ─────────────────────────────────────────────────────────────────

def _preparar_doc(doc, signer, origem_bytes, token, agora, expira, forcar=False):
    if doc.arquivo_origem:
        raise AssinaturaError("O documento de origem desta emissão é imutável.")
    try:
        valido = bool(origem_bytes) and _total_de_paginas(origem_bytes) > 0
    except Exception as exc:
        raise AssinaturaError("O documento de origem não é um PDF válido.") from exc
    if not valido:
        raise AssinaturaError("O documento de origem não é um PDF válido.")
    doc.nome_esperado = signer.nome
    doc.link_token_hash = hashlib.sha256(token.encode()).hexdigest()
    doc.cpf_prefixo_hash = _hash_prefixo(signer.cpf[:5])
    doc.link_criado_em = agora
    doc.link_expira_em = expira
    doc.hash_documento = hashlib.sha256(origem_bytes).hexdigest()
    doc.arquivo_origem.save(f"{doc.tipo}_origem.pdf", ContentFile(origem_bytes), save=False)
    doc.save()
    return doc


@atomico_com_arquivos
def emitir_link_rt(servidor_prestacao, dias=7, forcar=False):
    return _emitir(servidor_prestacao.prestacao, AssinaturaDocumento.TIPO_RT, signer_rt(servidor_prestacao), servidor_prestacao, dias, forcar)


@atomico_com_arquivos
def emitir_link_db(prestacao, dias=7, forcar=False):
    return _emitir(prestacao, AssinaturaDocumento.TIPO_DB, signer_db(prestacao), None, dias, forcar)


def documentos_do_link(token: str):
    """Documentos válidos (token confere e link não expirado), em ordem RT→DB."""
    if not token or len(token) > 128:
        return []
    import hashlib

    token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
    docs = list(
        AssinaturaDocumento.objects.select_related(
            "prestacao__oficio", "servidor_prestacao__servidor", "signer"
        ).filter(link_token_hash=token_hash).exclude(status=AssinaturaDocumento.STATUS_CANCELADA)
    )
    validos = [d for d in docs if not d.link_expirado]
    ordem = {AssinaturaDocumento.TIPO_RT: 0, AssinaturaDocumento.TIPO_DB: 1}
    validos.sort(key=lambda d: ordem.get(d.tipo, 9))
    return validos


def documento_do_link(token: str, tipo: str):
    for doc in documentos_do_link(token):
        if doc.tipo == tipo:
            return doc
    return None


def proximo_pendente(token: str):
    for doc in documentos_do_link(token):
        if doc.status != AssinaturaDocumento.STATUS_ASSINADA:
            return doc
    return None


# ─────────────────────────────────────────────────────────────────
# Identidade
# ─────────────────────────────────────────────────────────────────

@transaction.atomic
def validar_identidade(doc, cpf):
    atual = AssinaturaDocumento.objects.select_for_update().get(pk=doc.pk)
    if not atual.link_ativo or (atual.bloqueada_ate and atual.bloqueada_ate > timezone.now()):
        return False
    digitos = str(cpf or "").strip()
    if len(digitos) != 5 or not digitos.isascii() or not digitos.isdigit():
        return False
    if not constant_time_compare(_hash_prefixo(digitos), atual.cpf_prefixo_hash):
        return False
    atual.identidade_confirmada_em = timezone.now()
    atual.tentativas_identidade = 0
    atual.bloqueada_ate = None
    atual.save(update_fields=["identidade_confirmada_em", "tentativas_identidade", "bloqueada_ate", "atualizado_em"])
    doc.identidade_confirmada_em = atual.identidade_confirmada_em
    return True


# ─────────────────────────────────────────────────────────────────
# Carimbo da assinatura
# ─────────────────────────────────────────────────────────────────

def _limpar_assinatura(doc):
    """Revoga preservando snapshot, PNG, PDF e código para a trilha probatória."""
    doc.status = AssinaturaDocumento.STATUS_CANCELADA
    doc.revogada_em = timezone.now()
    doc.save(update_fields=["status", "revogada_em", "atualizado_em"])


def _carimbar_pdf(origem_bytes, png_bytes, *, pagina, x, y, w, h, nome, codigo) -> bytes:
    """Funde o PNG da assinatura na página escolhida pelo signatário.

    A manipulação do PDF em volta do desenho — decifrar, normalizar rotação, medir e
    fundir — mora em `documentos.services.pdf_overlay`, compartilhada com o carimbo do
    número de solicitação. Aqui fica só o que é da assinatura: a imagem e a legenda.
    """
    from reportlab.lib.utils import ImageReader

    total = _total_de_paginas(origem_bytes)
    if total == 0:
        raise AssinaturaError("O documento não possui páginas para assinar.")
    idx = max(0, min(int(pagina or 0), total - 1))

    def desenhar(c, medidas):
        # Frações vêm do navegador com origem no topo-esquerdo; PDF tem origem embaixo.
        box_w = max(1.0, float(w) * medidas.largura)
        box_h = max(1.0, float(h) * medidas.altura)
        box_x = medidas.x_pdf(x)
        box_y_bottom = medidas.y_pdf(y, box_h)

        c.drawImage(
            ImageReader(BytesIO(png_bytes)),
            box_x,
            box_y_bottom,
            width=box_w,
            height=box_h,
            mask="auto",
            preserveAspectRatio=True,
            anchor="sw",
        )
        from reportlab.lib.utils import simpleSplit
        legenda = f"Assinado eletronicamente por {nome}"
        c.setFont("Helvetica", 6)
        c.setFillColorRGB(0.30, 0.36, 0.43)
        largura_legenda = min(max(box_w, 300), medidas.largura - 12)
        centro = max(largura_legenda / 2 + 6, min(medidas.largura - largura_legenda / 2 - 6, box_x + box_w / 2))
        linhas = simpleSplit(legenda, "Helvetica", 6, largura_legenda)
        linhas.append(f"{timezone.localtime().strftime('%d/%m/%Y %H:%M')} — Código {codigo}")
        cap_y = max(7 * len(linhas), box_y_bottom - 8)
        for linha in linhas:
            c.drawCentredString(centro, cap_y, linha)
            cap_y -= 7

    try:
        return desenhar_overlay(origem_bytes, {idx: desenhar})
    except PdfOverlayError as exc:
        raise AssinaturaError(str(exc)) from exc


def _total_de_paginas(origem_bytes) -> int:
    from pypdf import PdfReader

    reader = PdfReader(BytesIO(origem_bytes))
    if getattr(reader, "is_encrypted", False):
        try:
            reader.decrypt("")
        except Exception as exc:
            capture(exc, "prestacoes.assinatura.decrypt_pdf")
    return len(reader.pages)


@atomico_com_arquivos
def aplicar_assinatura(doc, *, png_bytes, modo, fonte, pagina, x, y, w, h, ip=""):
    """Valida e carimba uma única vez o snapshot exibido ao signatário."""
    atual = AssinaturaDocumento.objects.select_for_update().get(pk=doc.pk)
    if not atual.link_ativo or not atual.identidade_confirmada_em:
        raise AssinaturaError("Este documento não está disponível para assinatura.")
    if modo not in dict(AssinaturaDocumento.MODO_CHOICES):
        raise AssinaturaError("Escolha como criar sua assinatura.")
    png_bytes = _validar_png(png_bytes)
    if not atual.arquivo_origem:
        raise AssinaturaError("Não há documento de origem para assinar.")
    with atual.arquivo_origem.open("rb") as f:
        origem = f.read()
    if not constant_time_compare(hashlib.sha256(origem).hexdigest(), atual.hash_documento):
        raise AssinaturaError("O documento de origem foi alterado. Solicite uma nova emissão.")
    coords = (x, y, w, h)
    if not all(isinstance(v, (float, int)) and math.isfinite(v) for v in coords):
        raise AssinaturaError("Posição de assinatura inválida.")
    if not (0 <= x < 1 and 0 <= y < 1 and 0 < w <= 1 and 0 < h <= 1 and x+w <= 1.00001 and y+h <= 1.00001):
        raise AssinaturaError("A assinatura precisa ficar dentro da página.")
    if not isinstance(pagina, int) or not 0 <= pagina < _total_de_paginas(origem):
        raise AssinaturaError("Página de assinatura inválida.")
    codigo = secrets.token_hex(6).upper()
    assinado = _carimbar_pdf(origem, png_bytes, pagina=pagina, x=x, y=y, w=w, h=h, nome=atual.nome_esperado, codigo=codigo)
    atual.modo = modo; atual.fonte = str(fonte or "")[:60]
    atual.pagina = pagina
    atual.pos_x, atual.pos_y, atual.largura, atual.altura = coords
    atual.assinatura_png.save("assinatura.png", ContentFile(png_bytes), save=False)
    atual.arquivo_assinado.save(f"{atual.tipo}_assinado.pdf", ContentFile(assinado), save=False)
    atual.assinado_em = timezone.now(); atual.assinado_ip = str(ip or "")[:64]
    atual.hash_assinado = hashlib.sha256(assinado).hexdigest()
    atual.codigo_verificacao = codigo; atual.status = AssinaturaDocumento.STATUS_ASSINADA
    atual.save()
    doc.refresh_from_db()


@transaction.atomic
def _cancelar_doc(doc):
    if doc:
        atual = AssinaturaDocumento.objects.select_for_update().get(pk=doc.pk)
        _limpar_assinatura(atual)


def cancelar_assinatura_rt(servidor_prestacao) -> None:
    _cancelar_doc(assinatura_rt(servidor_prestacao))


def cancelar_assinatura_db(prestacao) -> None:
    _cancelar_doc(assinatura_db(prestacao))


# ─────────────────────────────────────────────────────────────────
# Integração: usar o arquivo assinado quando existir
# ─────────────────────────────────────────────────────────────────

def assinatura_rt(servidor_prestacao):
    """Assinatura do RT de um servidor (qualquer status), ou ``None``."""
    if not servidor_prestacao:
        return None
    return (
        AssinaturaDocumento.objects.select_related("signer")
        .filter(servidor_prestacao=servidor_prestacao, tipo=AssinaturaDocumento.TIPO_RT).exclude(status=AssinaturaDocumento.STATUS_CANCELADA)
        .first()
    )


def assinatura_db(prestacao):
    """Assinatura do Diário de Bordo (qualquer status), ou ``None``."""
    return (
        AssinaturaDocumento.objects.select_related("signer")
        .filter(
            prestacao=prestacao,
            tipo=AssinaturaDocumento.TIPO_DB,
            servidor_prestacao__isnull=True,
        ).exclude(status=AssinaturaDocumento.STATUS_CANCELADA)
        .first()
    )


def _bytes_assinado(doc) -> bytes | None:
    if doc and doc.status == AssinaturaDocumento.STATUS_ASSINADA and doc.arquivo_assinado:
        with doc.arquivo_assinado.open("rb") as f:
            return f.read()
    return None


def pdf_rt_assinado_ou_gerado(servidor_prestacao) -> bytes:
    conteudo = _bytes_assinado(assinatura_rt(servidor_prestacao))
    if conteudo is not None:
        return conteudo
    from .services import gerar_relatorio_tecnico_pdf

    relatorio, _ = RelatorioTecnico.objects.get_or_create(prestacao=servidor_prestacao.prestacao)
    return gerar_relatorio_tecnico_pdf(relatorio, servidor_prestacao)


def pdf_db_assinado_ou_gerado(prestacao) -> bytes:
    conteudo = _bytes_assinado(assinatura_db(prestacao))
    if conteudo is not None:
        return conteudo
    from .diario_services import gerar_diario_bordo_pdf

    diario, _ = DiarioBordo.objects.get_or_create(prestacao=prestacao)
    return gerar_diario_bordo_pdf(diario)


def _hash_prefixo(prefixo):
    return salted_hmac("viagens_prestacoes.cpf_prefixo", prefixo, algorithm="sha256").hexdigest()


def _emitir(prestacao, tipo, signer, ps, dias, forcar):
    if signer is None:
        raise AssinaturaError("Defina um servidor cadastrado como signatário do documento.")
    if not _cpf_valido(signer):
        raise AssinaturaError(f'O signatário "{signer}" não tem CPF cadastrado; atualize seu cadastro.')
    # Serializa emissões do mesmo documento, inclusive quando ainda não existe link.
    type(prestacao).objects.select_for_update().get(pk=prestacao.pk)
    vigente = (AssinaturaDocumento.objects.select_for_update().filter(prestacao=prestacao, tipo=tipo, servidor_prestacao=ps).exclude(status=AssinaturaDocumento.STATUS_CANCELADA).first())
    if vigente and vigente.assinada and not forcar:
        raise AssinaturaError("Este documento já está assinado.")
    origem = _origem_rt_bytes(prestacao, ps) if tipo == AssinaturaDocumento.TIPO_RT else _origem_db_bytes(prestacao)
    agora = timezone.now()
    try:
        expira = agora + timedelta(days=max(1, int(dias)))
    except (ValueError, TypeError, OverflowError) as exc:
        raise AssinaturaError("Prazo de assinatura inválido.") from exc
    if vigente:
        _limpar_assinatura(vigente)
    doc = AssinaturaDocumento(prestacao=prestacao, servidor_prestacao=ps, tipo=tipo, signer=signer)
    token = secrets.token_urlsafe(32)
    return token, [_preparar_doc(doc, signer, origem, token, agora, expira)]


def _validar_png(png):
    from PIL import Image
    if not png or len(png) > 2 * 1024 * 1024:
        raise AssinaturaError("Envie uma assinatura PNG de até 2 MB.")
    try:
        with Image.open(BytesIO(png)) as img:
            if img.format != "PNG" or img.width * img.height > 8_000_000:
                raise ValueError("imagem inválida")
            img.verify()
        with Image.open(BytesIO(png)) as img:
            rgba = img.convert("RGBA")
            minimo, maximo = rgba.getchannel("A").getextrema()
            if maximo == 0 or minimo == 255:
                raise ValueError("assinatura vazia ou sem transparência")
            buf = BytesIO(); rgba.save(buf, format="PNG")
            return buf.getvalue()
    except Exception as exc:
        raise AssinaturaError("A assinatura deve ser um PNG transparente com traços visíveis.") from exc


@transaction.atomic
def registrar_tentativa_incorreta(doc):
    atual = AssinaturaDocumento.objects.select_for_update().get(pk=doc.pk)
    agora = timezone.now()
    if atual.bloqueada_ate and atual.bloqueada_ate <= agora:
        atual.tentativas_identidade = 0; atual.bloqueada_ate = None
    atual.tentativas_identidade += 1
    if atual.tentativas_identidade >= 5:
        atual.bloqueada_ate = agora + timedelta(minutes=15)
    atual.save(update_fields=["tentativas_identidade", "bloqueada_ate", "atualizado_em"])
    return atual.tentativas_identidade
