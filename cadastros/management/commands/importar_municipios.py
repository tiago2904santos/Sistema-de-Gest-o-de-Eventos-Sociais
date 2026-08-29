"""Importa municípios (com suas regiões) a partir de um CSV oficial.

Uso: python manage.py importar_municipios caminho/municipios_pr.csv

Formato esperado do CSV (UTF-8, separador ';', com cabeçalho):

    nome;regiao
    Curitiba;Metropolitana de Curitiba
    Londrina;Norte Central Paranaense

Fonte recomendada: lista oficial de municípios do Paraná do IBGE
(https://www.ibge.gov.br) ou o dataset institucional adotado pela PCPR,
mapeando cada município à região administrativa desejada. O comando é
idempotente: reexecutá-lo atualiza a região sem duplicar municípios.
"""

import csv
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from cadastros.models import Municipio, Regiao


class Command(BaseCommand):
    help = "Importa municípios e regiões de um CSV (colunas: nome;regiao)."

    def add_arguments(self, parser):
        parser.add_argument("arquivo", help="Caminho do CSV com colunas nome;regiao")
        parser.add_argument(
            "--separador", default=";", help="Separador de colunas (padrão ';')"
        )

    @transaction.atomic
    def handle(self, *args, **options):
        caminho = Path(options["arquivo"])
        if not caminho.exists():
            raise CommandError(f"Arquivo não encontrado: {caminho}")

        criados = atualizados = 0
        with caminho.open(encoding="utf-8-sig", newline="") as arquivo:
            leitor = csv.DictReader(arquivo, delimiter=options["separador"])
            if not leitor.fieldnames or {"nome", "regiao"} - set(
                nome.strip().lower() for nome in leitor.fieldnames
            ):
                raise CommandError("O CSV precisa das colunas 'nome' e 'regiao'.")
            for linha in leitor:
                linha = {chave.strip().lower(): (valor or "").strip() for chave, valor in linha.items()}
                if not linha.get("nome") or not linha.get("regiao"):
                    continue
                regiao, _ = Regiao.objects.get_or_create(nome=linha["regiao"])
                municipio, criado = Municipio.objects.update_or_create(
                    nome=linha["nome"], regiao=regiao, defaults={}
                )
                if criado:
                    criados += 1
                else:
                    atualizados += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"Importação concluída: {criados} criado(s), {atualizados} já existente(s)."
            )
        )
