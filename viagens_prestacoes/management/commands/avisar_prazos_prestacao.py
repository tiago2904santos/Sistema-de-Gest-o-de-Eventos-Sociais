"""Avisos diários da prestação de contas no sino da equipe de viagens (m085, m090).

Rodar uma vez por dia no deploy (cron ou timer do systemd), por exemplo:

    15 7 * * *  cd /srv/app && .venv/bin/python manage.py avisar_prazos_prestacao

Cada aviso sai uma vez só; rodar de novo no mesmo dia não repete nada. Por isso
pode rodar de hora em hora (`0 * * * *`): o aviso "a equipe chegou de viagem"
(m096) sai mais perto da chegada, e os outros não se repetem.
"""

from django.core.management.base import BaseCommand

from viagens_prestacoes.avisos import avisar_prazos
from viagens_prestacoes.avisos import avisar_viagens


class Command(BaseCommand):
    help = "Avisa no sino os prazos de saque e de prestação, os documentos gerados/assinados e as saídas e chegadas de viagem."

    def handle(self, *args, **options):
        total = avisar_prazos() + avisar_viagens()
        self.stdout.write(self.style.SUCCESS(f"{total} aviso(s) enviado(s)."))
