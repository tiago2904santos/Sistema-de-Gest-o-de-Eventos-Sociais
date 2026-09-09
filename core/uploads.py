from __future__ import annotations

from pathlib import Path
import re
import shlex
import subprocess
import tempfile
import unicodedata
import warnings

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import FileExtensionValidator


def validate_private_document_upload(uploaded_file):
    """Política central para anexos privados PDF/imagem."""
    max_bytes = getattr(settings, "PRIVATE_UPLOAD_MAX_BYTES", 10 * 1024 * 1024)
    if uploaded_file.size > max_bytes:
        raise ValidationError(
            f"O arquivo excede o limite de {max_bytes // (1024 * 1024)} MB.",
        )

    FileExtensionValidator(["pdf", "png", "jpg", "jpeg"])(uploaded_file)
    extension = Path(uploaded_file.name).suffix.lower()
    uploaded_file.name = normalize_upload_filename(uploaded_file.name)
    position = uploaded_file.tell() if hasattr(uploaded_file, "tell") else 0
    try:
        uploaded_file.seek(0)
        header = uploaded_file.read(16)
        if extension == ".pdf":
            if not header.startswith(b"%PDF-"):
                raise ValidationError("O conteúdo não corresponde a um PDF válido.")
            try:
                from pypdf import PdfReader
                uploaded_file.seek(0)
                reader = PdfReader(uploaded_file)
                if reader.is_encrypted and not reader.decrypt(""):
                    raise ValueError("PDF protegido por senha")
                if not len(reader.pages):
                    raise ValueError("PDF vazio")
            except Exception as exc:
                raise ValidationError("O conteúdo não corresponde a um PDF válido e legível.") from exc
        else:
            uploaded_file.seek(0)
            try:
                from PIL import Image
                from PIL import UnidentifiedImageError

                with warnings.catch_warnings():
                    warnings.simplefilter("error", Image.DecompressionBombWarning)
                    image = Image.open(uploaded_file)
                    esperado = "PNG" if extension == ".png" else "JPEG"
                    if image.format != esperado:
                        raise ValueError("Formato da imagem não corresponde à extensão")
                    image.verify()
            # `SyntaxError` entrou na lista por medição, não por precaução: um PNG com
            # CRC quebrado faz `Image.verify()` levantar `SyntaxError` de dentro do
            # `PngImagePlugin`, que não descende de `OSError` nem de `ValueError`. Sem
            # ele, arquivo corrompido virava 500 em vez de recusa com mensagem. O
            # caminho nunca havia sido exercitado porque a política não rodava (QA-04).
            except (
                UnidentifiedImageError,
                OSError,
                ValueError,
                SyntaxError,
                Image.DecompressionBombWarning,
            ) as exc:
                raise ValidationError("O conteúdo não corresponde a uma imagem válida.") from exc
    finally:
        uploaded_file.seek(position)

    if getattr(settings, "PRIVATE_UPLOAD_REQUIRE_ANTIVIRUS", False):
        _scan_with_clamav(uploaded_file)


def normalize_upload_filename(filename: str) -> str:
    path = Path(filename or "arquivo")
    extension = path.suffix.lower()
    stem = unicodedata.normalize("NFKD", path.stem)
    stem = stem.encode("ascii", "ignore").decode("ascii")
    stem = re.sub(r"[^A-Za-z0-9._-]+", "-", stem).strip("._-") or "arquivo"
    return f"{stem[:120]}{extension}"


def _scan_with_clamav(uploaded_file):
    # `shlex.split` em vez de tratar o ajuste como nome de binário: a invocação
    # correta do clamd precisa de flag, e sem isso o valor "clamdscan --fdpass"
    # viraria um executável inexistente (FileNotFoundError) — a falha se
    # disfarçaria de "antivírus indisponível".
    command = getattr(settings, "CLAMAV_SCAN_COMMAND", "") or "clamdscan --fdpass"
    argv = shlex.split(command)
    if not argv:
        raise ValidationError(
            "O serviço antivírus está indisponível; tente novamente mais tarde.",
        )
    position = uploaded_file.tell() if hasattr(uploaded_file, "tell") else 0
    try:
        uploaded_file.seek(0)
        with tempfile.NamedTemporaryFile(suffix=Path(uploaded_file.name).suffix) as temp:
            for chunk in uploaded_file.chunks():
                temp.write(chunk)
            temp.flush()
            try:
                # `--fdpass` não é preciosismo: o clamd roda como usuário
                # `clamav` e recebe só o caminho, mas o NamedTemporaryFile nasce
                # 0600 sob o usuário do gunicorn. Sem passar o descritor já
                # aberto, o daemon responde "Access denied" e sai com 2, e todo
                # anexo é recusado. Medido na VPS, não deduzido.
                result = subprocess.run(
                    [*argv, "--no-summary", temp.name],
                    capture_output=True,
                    text=True,
                    timeout=30,
                    check=False,
                )
            except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
                raise ValidationError(
                    "O serviço antivírus está indisponível; tente novamente mais tarde.",
                ) from exc
            if result.returncode == 1:
                raise ValidationError("O arquivo foi rejeitado pela verificação antivírus.")
            if result.returncode != 0:
                raise ValidationError(
                    "Não foi possível concluir a verificação antivírus.",
                )
    finally:
        uploaded_file.seek(position)
