"""Gera a viagem de cada solicitação deferida que ainda não tem uma.

    python manage.py gerar_viagens_pendentes

Roda também nas rotinas diárias e no deploy. Só pega evento que ainda não
terminou; a que já tem viagem fica como está.
"""

from django.core.management.base import BaseCommand

from solicitacoes.integracao_viagens import gerar_viagens_pendentes


class Command(BaseCommand):
    help = "Gera as viagens das solicitações deferidas que ainda não têm viagem."

    def handle(self, *args, **opcoes):
        geradas = gerar_viagens_pendentes()
        self.stdout.write(f"{geradas} solicitação(ões) ganharam viagem.")
