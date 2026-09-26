"""Envia os lembretes diários das solicitações (sino e e-mail).

    python manage.py enviar_lembretes_solicitacoes [--simular] [--data AAAA-MM-DD]

Pode rodar quantas vezes quiser: cada lembrete sai uma vez só por
solicitação e data de referência. Agende uma vez por dia (cron ou timer do
servidor); veja `scripts/deploy/vps/README.md` e `solicitacoes/lembretes.py`.
"""

from datetime import date

from django.core.management.base import BaseCommand, CommandError

from solicitacoes.lembretes import enviar_lembretes
from solicitacoes.models import TipoLembrete


class Command(BaseCommand):
    help = (
        "Avisa o autor para confirmar o atendimento depois do evento, a DG dos "
        "pedidos com evento em até 7 dias e o autor da devolução parada há mais "
        "de 3 dias. Idempotente."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--simular",
            action="store_true",
            help="Só conta o que seria enviado, sem gravar nem avisar ninguém.",
        )
        parser.add_argument(
            "--data",
            help="Dia de referência (AAAA-MM-DD); padrão: hoje.",
        )

    def handle(self, *args, **opcoes):
        hoje = None
        if opcoes.get("data"):
            try:
                hoje = date.fromisoformat(opcoes["data"])
            except ValueError as erro:
                raise CommandError("Use a data no formato AAAA-MM-DD.") from erro
        enviados = enviar_lembretes(hoje=hoje, simular=opcoes["simular"])
        verbo = "seriam enviados" if opcoes["simular"] else "enviados"
        for tipo, quantidade in enviados.items():
            self.stdout.write(f"{TipoLembrete(tipo).label}: {quantidade} {verbo}")
        self.stdout.write(self.style.SUCCESS(f"Total: {sum(enviados.values())} {verbo}."))
