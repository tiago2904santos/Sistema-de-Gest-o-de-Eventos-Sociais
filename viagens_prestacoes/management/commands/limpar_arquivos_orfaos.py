from __future__ import annotations

from collections.abc import Iterator

from django.apps import apps
from django.core.files.storage import default_storage
from django.core.management.base import BaseCommand
from django.db import models


PREFIXO_PRESTACOES = "viagens_prestacoes"


def _listar_arquivos(prefixo: str) -> Iterator[str]:
    """Percorre o storage sem presumir que ele seja um filesystem local."""
    try:
        diretorios, arquivos = default_storage.listdir(prefixo)
    except FileNotFoundError:
        return

    for nome in arquivos:
        yield f"{prefixo}/{nome}"
    for diretorio in diretorios:
        yield from _listar_arquivos(f"{prefixo}/{diretorio}")


def _arquivos_referenciados(prefixo: str) -> set[str]:
    """Inclui todo FileField vivo para não confundir outro documento com órfão."""
    inicio = f"{prefixo}/"
    referenciados: set[str] = set()
    for model in apps.get_models():
        for field in model._meta.concrete_fields:
            if not isinstance(field, models.FileField):
                continue
            valores = (
                model._base_manager.exclude(**{field.name: ""})
                .values_list(field.name, flat=True)
                .iterator()
            )
            referenciados.update(
                nome for nome in valores if nome and str(nome).startswith(inicio)
            )
    return referenciados


class Command(BaseCommand):
    help = (
        "Lista arquivos órfãos no storage privado de prestações; "
        "só os remove quando --apagar é informado."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--apagar",
            action="store_true",
            help="Remove do storage os arquivos sem referência no banco.",
        )

    def handle(self, *args, **options):
        referenciados = _arquivos_referenciados(PREFIXO_PRESTACOES)
        orfaos = sorted(set(_listar_arquivos(PREFIXO_PRESTACOES)) - referenciados)

        if not orfaos:
            self.stdout.write(self.style.SUCCESS("Nenhum arquivo órfão encontrado."))
            return

        for nome in orfaos:
            self.stdout.write(f"Arquivo órfão: {nome}")

        if not options["apagar"]:
            self.stdout.write(
                self.style.WARNING(
                    f"Diagnóstico: {len(orfaos)} arquivo(s); nada foi apagado. "
                    "Use --apagar para remover."
                )
            )
            return

        for nome in orfaos:
            default_storage.delete(nome)
        self.stdout.write(
            self.style.SUCCESS(f"Removidos {len(orfaos)} arquivo(s) órfão(s).")
        )
