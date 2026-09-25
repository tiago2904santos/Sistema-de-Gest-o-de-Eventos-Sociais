"""A chegada do processo: validar o upload, reconhecer repetido, registrar e reanalisar.

O processo inteiro do eProtocolo passa fácil do limite geral de anexo (10 MB):
aqui o limite é `IMPORTACAO_MAX_BYTES` (padrão 25 MiB, o mesmo do nginx), e o
resto da política é a central (`core.uploads.validate_private_document_upload`:
tipo real pelo conteúdo, PDF que abre, imagem íntegra, antivírus se ligado).
"""

from __future__ import annotations

import hashlib
from decimal import Decimal
from pathlib import Path

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile

from core.uploads import normalize_upload_filename
from core.uploads import validate_private_document_upload

from ..arquivos import atomico_com_arquivos
from ..models import ImportacaoProcesso
from .analise import analisar
from .plano import DESTINOS
from .plano import DESTINOS_DOCUMENTO
from .plano import IGNORAR
from .plano import Plano

__all__ = [
    "limite_de_bytes",
    "validar_arquivo_do_processo",
    "hash_do_arquivo",
    "importacao_do_mesmo_arquivo",
    "registrar_importacao",
    "reanalisar",
    "descartar",
    "aplicar_escolhas",
]

_MIB = 1024 * 1024
_CENTAVO = Decimal("0.01")


def limite_de_bytes() -> int:
    """Tamanho máximo do processo enviado (`IMPORTACAO_MAX_BYTES`, padrão 25 MiB)."""
    try:
        return int(getattr(settings, "IMPORTACAO_MAX_BYTES", 25 * _MIB))
    except (TypeError, ValueError):
        return 25 * _MIB


def validar_arquivo_do_processo(arquivo) -> None:
    """A política central de anexo privado, com o limite de tamanho do importador.

    A função central só conhece o limite geral (`PRIVATE_UPLOAD_MAX_BYTES`). O
    tamanho é conferido aqui, contra o limite do importador, e ela confere o resto
    vendo o arquivo com tamanho zero — assim nenhuma das outras regras (tipo real,
    PDF legível, bomba de descompressão, antivírus) deixa de valer.
    """
    limite = limite_de_bytes()
    tamanho = int(getattr(arquivo, "size", 0) or 0)
    if tamanho > limite:
        raise ValidationError(f"O arquivo passa do limite de {limite // _MIB} MB para importar um processo.")
    try:
        arquivo.size = 0
        validate_private_document_upload(arquivo)
    finally:
        arquivo.size = tamanho


def hash_do_arquivo(dados: bytes) -> str:
    return hashlib.sha256(dados).hexdigest()


def importacao_do_mesmo_arquivo(hash_sha256: str) -> ImportacaoProcesso | None:
    """A importação anterior do mesmo arquivo (a descartada não conta)."""
    return (
        ImportacaoProcesso.objects.filter(hash_sha256=hash_sha256)
        .exclude(situacao=ImportacaoProcesso.SITUACAO_DESCARTADA)
        .select_related("prestacao__oficio")
        .order_by("-criado_em", "-pk")
        .first()
    )


@atomico_com_arquivos
def registrar_importacao(dados: bytes, nome_arquivo: str, plano: Plano, *, usuario=None) -> ImportacaoProcesso:
    """Guarda o processo como veio e o plano da análise (situação "analisada")."""
    nome = normalize_upload_filename(Path(nome_arquivo or "processo.pdf").name)
    importacao = ImportacaoProcesso(
        nome_original=Path(nome_arquivo or nome).name[:255],
        hash_sha256=hash_do_arquivo(dados),
        protocolo=plano.protocolo,
        oficio_id=plano.oficio_id,
        prestacao_id=plano.prestacao_id,
        plano=plano.para_json(),
        criado_por=usuario if getattr(usuario, "is_authenticated", False) else None,
    )
    importacao.arquivo.save(nome, ContentFile(dados), save=False)
    importacao.save()
    return importacao


def _bytes(importacao) -> bytes:
    importacao.arquivo.open("rb")
    try:
        return importacao.arquivo.read()
    finally:
        importacao.arquivo.close()


def reanalisar(importacao: ImportacaoProcesso, prestacao, *, termo=None) -> Plano:
    """Lê de novo o processo com a prestação (ou o termo avulso) escolhida na conferência e guarda o plano novo.

    A leitura roda fora de transação; só a gravação do plano é atômica. A lista de
    origem (a volta, o que a tela pergunta) continua a do envio.
    """
    origem = Plano.de_json(importacao.plano).origem
    plano = analisar(_bytes(importacao), importacao.nome_original, prestacao=prestacao, termo=termo, origem=origem)
    importacao.plano = plano.para_json()
    importacao.prestacao_id = plano.prestacao_id
    importacao.oficio_id = plano.oficio_id
    importacao.save(update_fields=["plano", "prestacao", "oficio"])
    return plano


def descartar(importacao: ImportacaoProcesso) -> None:
    """Marca como descartada. O arquivo fica (auditoria); os anexos já gravados, também."""
    importacao.situacao = ImportacaoProcesso.SITUACAO_DESCARTADA
    importacao.save(update_fields=["situacao"])


def _valor_digitado(texto):
    """"R$ 1.580,00", "580,5" ou "580.00" → Decimal; None se não for número."""
    from .plano import _decimal

    limpo = str(texto or "").replace("R$", "").replace(" ", "").strip()
    if "," in limpo:
        limpo = limpo.replace(".", "").replace(",", ".")
    numero = _decimal(limpo)
    return numero.quantize(_CENTAVO) if numero is not None else None


def _giro(valor) -> int:
    try:
        return (int(valor) // 90 * 90) % 360
    except (TypeError, ValueError):
        return 0


def _id_permitido(valor, permitidos) -> int | None:
    try:
        escolhido = int(valor)
    except (TypeError, ValueError):
        return None
    return escolhido if escolhido in permitidos else None


def aplicar_escolhas(
    plano: Plano, dados, *, equipe_ids: set[int], servidores_termo_ids: set[int] = frozenset(),
    ordens_ids: set[int] = frozenset(),
) -> Plano:
    """As escolhas da conferência sobre o plano (recebe o `QueryDict`, não o request).

    Campos por documento `N` (a ordem no processo): `doc-N-destino`,
    `doc-N-servidor` (RT e comprovante: servidor da prestação), `doc-N-termo_servidor`
    (termo: servidor do cadastro), `doc-N-os` (ordem de serviço), `doc-N-valor`,
    `doc-N-data`, `doc-N-operacao`, `doc-N-giro`. Os ids só valem dentro do
    permitido (`equipe_ids`, `servidores_termo_ids`, `ordens_ids`). Campo ausente
    não mexe no que a leitura propôs. O que o operador decide deixa de precisar
    de conferência: a lista `conferir` do documento é esvaziada.
    """
    from ..models import OPERACAO_CHOICES
    from .plano import _data

    operacoes = {valor for valor, _ in OPERACAO_CHOICES}
    for item in plano.itens:
        prefixo = f"doc-{item.ordem}-"
        if not any(chave.startswith(prefixo) for chave in dados.keys()):
            continue
        destino = dados.get(prefixo + "destino")
        if destino is not None:
            item.destino = destino if destino in DESTINOS or destino in DESTINOS_DOCUMENTO or destino == IGNORAR else ""
        servidor = dados.get(prefixo + "servidor")
        if servidor is not None:
            item.servidor_prestacao_id = _id_permitido(servidor, equipe_ids)
        servidor_termo = dados.get(prefixo + "termo_servidor")
        if servidor_termo is not None:
            escolhido = _id_permitido(servidor_termo, servidores_termo_ids)
            if escolhido != item.servidor_id:
                item.evidencias = []  # o que a leitura disse era de outro servidor
            item.servidor_id = escolhido
        ordem = dados.get(prefixo + "os")
        if ordem is not None:
            item.ordem_servico_id = _id_permitido(ordem, ordens_ids)
        valor = dados.get(prefixo + "valor")
        if valor is not None:
            numero = _valor_digitado(valor)
            item.valor = str(numero) if numero is not None and numero > 0 else ""
        data = dados.get(prefixo + "data")
        if data is not None:
            dia = _data(data)
            item.data = dia.isoformat() if dia else ""
        operacao = dados.get(prefixo + "operacao")
        if operacao is not None:
            item.operacao = operacao if operacao in operacoes else ""
        giro = dados.get(prefixo + "giro")
        if giro is not None:
            item.giro = _giro(giro)
        item.conferir = []
    return plano
