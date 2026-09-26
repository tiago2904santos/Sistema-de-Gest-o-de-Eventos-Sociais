"""Grava na tabela de distâncias os pares dos trechos de roteiro já existentes (m078).

Não chama o serviço de rotas: aproveita só o que já foi calculado e gravado.
Pode ser rodado quantas vezes quiser; pares já guardados não mudam.
"""

from django.core.management.base import BaseCommand

from viagens_roteiros.services.distancias import carregar_dos_roteiros


class Command(BaseCommand):
    help = "Guarda as distâncias dos trechos de roteiro já gravados na tabela permanente."

    def handle(self, *args, **options):
        criados = carregar_dos_roteiros()
        self.stdout.write(self.style.SUCCESS(f"{criados} distância(s) nova(s) guardada(s)."))
