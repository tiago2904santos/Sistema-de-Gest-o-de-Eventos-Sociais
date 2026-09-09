"""
Diagnóstico de ambiente para geração DOCX/PDF (read-only).
"""

from __future__ import annotations

import json
import sys
from contextlib import redirect_stdout
from dataclasses import asdict

from django.core.management.base import BaseCommand

from documentos.services.environment import build_document_environment_report


class Command(BaseCommand):
    help = "Verifica se o ambiente consegue gerar DOCX e PDF (motores instalados)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--json",
            action="store_true",
            help="Saída em JSON (stdout).",
        )
        parser.add_argument(
            "--verbose",
            action="store_true",
            help="Inclui detalhe por motor.",
        )

    def handle(self, *args, **options):
        # Bibliotecas opcionais podem imprimir avisos durante o import.
        # Reserve stdout para o JSON consumido pelo diagnóstico operacional.
        with redirect_stdout(self.stderr):
            report = build_document_environment_report()
        use_json: bool = options["json"]
        verbose: bool = options["verbose"]

        if use_json:
            payload = asdict(report)
            self.stdout.write(json.dumps(payload, indent=2, ensure_ascii=False))
        else:
            self.stdout.write(f"Sistema operacional: {report.os_name}")
            self.stdout.write(f"Python: {report.python_version}")
            self.stdout.write(f"DOCX: {'OK' if report.docx_available else 'INDISPONÍVEL'}")
            if report.docx_missing_packages:
                self.stdout.write(f"  Pacotes em falta: {', '.join(report.docx_missing_packages)}")
            self.stdout.write(f"PDF: {'OK' if report.pdf_available else 'INDISPONÍVEL'}")
            self.stdout.write(f"  Motor recomendado: {report.preferred_pdf_engine or '—'}")
            self.stdout.write(f"  Motores disponíveis: {', '.join(report.available_pdf_engines) or '—'}")
            self.stdout.write(f"  Motores indisponíveis: {', '.join(report.missing_pdf_engines) or '—'}")
            if report.libreoffice_binary:
                self.stdout.write(f"  LibreOffice: {report.libreoffice_binary}")
            self.stdout.write(f"  Word COM: {'OK' if report.microsoft_word_available else 'não disponível'}")
            self.stdout.write(f"  WeasyPrint (import): {'OK' if report.weasyprint_available else 'não disponível'}")
            self.stdout.write(
                f"  PDF simples (fpdf2 + fallback): {'OK' if report.simple_fallback_available else 'não disponível'}",
            )
            if verbose:
                self.stdout.write("  Detalhe por motor:")
                for d in report.engine_details:
                    self.stdout.write(f"    - {d.name}: {'OK' if d.available else 'falhou'} — {d.detail}")
            if report.install_hints:
                self.stdout.write("Instalação / próximos passos:")
                for h in report.install_hints:
                    self.stdout.write(f"  {h}")

        code = 0
        if not report.docx_available:
            code = 2
        elif not report.pdf_available:
            code = 1
        sys.exit(code)
