r"""Gera os seis arquivos da F3 usando apenas banco e mídia descartáveis.

Execute da raiz com .venv\Scripts\python.exe scripts/documentos/verificar_fase3.py.
O PostgreSQL de desenvolvimento nunca é conectado por este script.
"""

import argparse
import hashlib
import io
import json
import os
from pathlib import Path
import sys
import tempfile


def main():
    root = Path(__file__).resolve().parents[2]
    sys.path.insert(0, str(root))
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--engine", default="auto")
    args = parser.parse_args()
    (root / "logs").mkdir(exist_ok=True)
    output = Path(tempfile.mkdtemp(prefix="fase3_", dir=root / "logs"))
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

    from django.conf import settings

    settings.DATABASES = {"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": ":memory:"}}
    settings.MEDIA_ROOT = output / "artefatos"
    settings.DOCUMENTOS_DEFAULT_PDF_ENGINE = args.engine
    settings.DOCUMENTOS_SIMPLE_PDF_FALLBACK = True

    import django

    django.setup()
    from django.core.management import call_command
    from docxtpl import DocxTemplate
    from pypdf import PdfReader
    from documentos.models import DocumentoArtefato
    from documentos.services.facade import DocumentoFacade
    from documentos.services.resources_paths import resolve_resource_docx
    from documentos.services.types import DocumentoTipo, DocumentoFormato

    call_command("migrate", verbosity=0, interactive=False)
    payload = {
        "institucional": {"nome_orgao": "PCPR", "unidade": "Teste F3"},
        "oficio": {"numero_formatado": "F3/2026", "assunto": "Teste F3", "roteiro": "Curitiba"},
        "justificativa": {"exigida": True, "texto": "Teste F3"},
        "termo": {"participante": {"nome": "Teste F3"}},
    }
    facade = DocumentoFacade()
    results = []
    for tipo in DocumentoTipo:
        template = resolve_resource_docx(f"{tipo.value}.docx")
        variables = DocxTemplate(str(template)).get_undeclared_template_variables()
        context = dict.fromkeys(variables, "Teste F3")
        for formato in DocumentoFormato:
            doc = facade.gerar(
                tipo=tipo, formato=formato, payload=payload,
                docxtpl_context=context, reference="prova-f3",
            )
            art = DocumentoArtefato.objects.get(pk=doc.artefato_id)
            assert art.hash_sha256 == hashlib.sha256(doc.conteudo).hexdigest()
            repeated = facade.gerar(
                tipo=tipo, formato=formato, payload=payload,
                docxtpl_context=context, reference="prova-f3",
            )
            assert repeated.cache_hit and repeated.artefato_id == art.pk
            path = output / f"{tipo.value}.{formato.value}"
            path.write_bytes(doc.conteudo)
            record = dict(arquivo=str(path), motor=art.engine, sha256=art.hash_sha256,
                          artefato_id=str(art.pk), cache_hit=repeated.cache_hit)
            if formato == DocumentoFormato.PDF:
                pdf = PdfReader(io.BytesIO(doc.conteudo))
                record["paginas"] = len(pdf.pages)
                assert record["paginas"] > 0
                assert "F3" in " ".join(page.extract_text() for page in pdf.pages)
            results.append(record)
    assert DocumentoArtefato.objects.count() == 6
    manifest = output / "manifesto.json"
    manifest.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Seis documentos e seis artefatos verificados: {manifest}")


if __name__ == "__main__":
    main()
