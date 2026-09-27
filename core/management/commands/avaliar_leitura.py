"""Roda a bateria do preenchimento automático e mostra o placar.

    python manage.py avaliar_leitura                     # todos os módulos
    python manage.py avaliar_leitura solicitacoes --erros
    python manage.py avaliar_leitura --caso sol-012 --erros

Nada fica gravado: os cadastros da bateria entram numa transação que é
desfeita no fim. Ver `core/leitura/tests/bateria/`.
"""

from django.core.management.base import BaseCommand
from django.db import transaction

from core.leitura.tests.bateria import avaliar as bateria


class _Desfazer(Exception):
    pass


class Command(BaseCommand):
    help = "Avalia o preenchimento automático contra a bateria de e-mails com gabarito."

    def add_arguments(self, parser):
        parser.add_argument("modulos", nargs="*", help="Módulos (padrão: todos).")
        parser.add_argument("--erros", action="store_true", help="Lista cada falha.")
        parser.add_argument("--caso", action="append", default=[], help="Só estes ids de caso.")

    def handle(self, *args, **opcoes):
        modulos = opcoes["modulos"] or bateria.MODULOS
        casos, cadastros = bateria.carregar(modulos)
        if opcoes["caso"]:
            casos = [c for c in casos if c.id in opcoes["caso"]]
        try:
            with transaction.atomic():
                bateria.preparar_banco(cadastros)
                relatorio = bateria.avaliar(casos)
                raise _Desfazer
        except _Desfazer:
            pass
        if opcoes["erros"]:
            for falha in relatorio.falhas:
                self.stdout.write(falha.linha())
        self.stdout.write(relatorio.resumo())
