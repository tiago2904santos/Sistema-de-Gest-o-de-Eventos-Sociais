"""Revalida e copia binários; simulação não cria diretórios ou arquivos."""

import hashlib
import os
import shutil
import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.files import File

from core.uploads import validate_private_document_upload


def sha256(caminho):
    with Path(caminho).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def caminho_contido(raiz, nome):
    raiz = Path(raiz).resolve()
    nome = str(nome).replace("\\", "/")
    partes = PurePosixPath(nome)
    if not nome or partes.is_absolute() or ".." in partes.parts or ":" in nome:
        raise ValidationError("Caminho de arquivo inválido.")
    caminho = (raiz / nome).resolve()
    if not caminho.is_relative_to(raiz) or caminho == raiz:
        raise ValidationError("Arquivo fora da pasta permitida.")
    return caminho


@dataclass(frozen=True)
class ArquivoPlanejado:
    origem: Path
    nome: str
    hash: str
    tamanho: int


def planejar_arquivo(raiz, nome, hash_esperado="", *, extensoes=None):
    origem = caminho_contido(raiz, nome)
    if not origem.is_file():
        raise ValidationError("Arquivo de origem não encontrado.")
    limite = getattr(settings, "PRIVATE_UPLOAD_MAX_BYTES", 10 * 1024 * 1024)
    tamanho = origem.stat().st_size
    if tamanho > limite:
        raise ValidationError(f"Arquivo excede o limite de {limite} bytes.")
    ext = origem.suffix.lower().lstrip(".")
    permitidas = set(extensoes or ["pdf", "png", "jpg", "jpeg", "docx", "xlsx"])
    if ext not in permitidas:
        raise ValidationError("Extensão não permitida para este campo.")
    if ext in {"docx", "xlsx"}:
        try:
            with zipfile.ZipFile(origem) as pacote:
                if sum(i.file_size for i in pacote.infolist()) > limite * 20:
                    raise ValidationError("Documento compactado excede o limite descompactado.")
                principal = "word/document.xml" if ext == "docx" else "xl/workbook.xml"
                if principal not in pacote.namelist() or "[Content_Types].xml" not in pacote.namelist() or pacote.testzip():
                    raise ValidationError("Documento Office inválido ou corrompido.")
        except (OSError, zipfile.BadZipFile, RuntimeError) as exc:
            raise ValidationError("Documento Office inválido ou ilegível.") from exc
    else:
        with origem.open("rb") as stream:
            validate_private_document_upload(File(stream, name=origem.name))
    digest = sha256(origem)
    if hash_esperado and digest != str(hash_esperado).lower():
        raise ValidationError("SHA-256 diverge do hash gravado na origem.")
    return ArquivoPlanejado(origem, f"legado/{digest[:2]}/{digest}.{ext}", digest, tamanho)


def copiar_arquivo(plano, raiz_destino):
    """Retorna (nome relativo, criou). Nunca substitui um binário diferente.

    O chamador registra o nome antes da transação e compensa a cópia se a
    gravação da linha falhar. O arquivo fica sob nome final apenas após conferir
    o hash; a criação exclusiva protege contra colisão concorrente.
    """
    destino = caminho_contido(raiz_destino, plano.nome)
    if destino.exists():
        if sha256(destino) != plano.hash:
            raise ValidationError("Arquivo de destino existe com conteúdo diferente.")
        return plano.nome, False
    destino.parent.mkdir(parents=True, exist_ok=True)
    criado = False
    try:
        with destino.open("xb") as stream, plano.origem.open("rb") as fonte:
            criado = True
            shutil.copyfileobj(fonte, stream)
            stream.flush()
            os.fsync(stream.fileno())
        if sha256(destino) != plano.hash:
            raise ValidationError("Arquivo mudou durante a cópia; linha não importada.")
    except FileExistsError:
        if sha256(destino) == plano.hash:
            return plano.nome, False
        raise ValidationError("Colisão de arquivo durante a cópia.")
    except Exception:
        if criado:
            destino.unlink(missing_ok=True)
        raise
    return plano.nome, True


def quarentenar(raiz_origem, nome, raiz_quarentena, *, commit=False):
    """Cópia de evidência, inclusive quando o arquivo não pode ser interpretado."""
    origem = caminho_contido(raiz_origem, nome)
    if not origem.is_file():
        return {"situacao": "ausente", "copiado": False}
    digest = sha256(origem)
    # Sem extensão executável e fora de MEDIA_ROOT: não pode ser servido como anexo.
    relativo = f"{digest[:2]}/{digest}.quarentena"
    if commit:
        copiar_arquivo(ArquivoPlanejado(origem, relativo, digest, origem.stat().st_size), raiz_quarentena)
    return {"situacao": "quarentena" if commit else "quarentena_prevista", "hash": digest, "arquivo": relativo, "copiado": commit}
