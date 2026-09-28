"""Mostra o que o planejamento aprendeu com as viagens já feitas.

    python manage.py estudar_viagens

Para cada cidade com viagem feita: quantos roteiros, a saída e a volta que
uma viagem nova para lá receberia. Só lê o banco; nada é gravado.
"""

from collections import Counter
from datetime import date

from django.core.management.base import BaseCommand

from viagens_viagem.planejamento import amostras_de_roteiros, modelo_de_justificativa, planejar_horarios


class Command(BaseCommand):
    help = "Resume os horários de roteiro e o modelo de justificativa que o histórico de viagens ensina."

    def handle(self, *args, **opcoes):
        from cadastros.models import Municipio
        from viagens_cadastros.models import ConfiguracaoSistema

        amostras = amostras_de_roteiros()
        sede = ConfiguracaoSistema.get_singleton().cidade_sede_padrao
        self.stdout.write(f"{len(amostras)} roteiros de viagens feitas. Sede: {sede or '—'}.")
        por_cidade = Counter(m for a in amostras for m in a.destinos)
        referencia = date.today()
        for municipio in Municipio.objects.filter(pk__in=por_cidade).order_by("nome"):
            plano = planejar_horarios(sede, municipio, referencia, referencia, amostras=amostras)
            self.stdout.write(f"- {municipio.nome}: {plano.explicacao}")
        modelo = modelo_de_justificativa()
        self.stdout.write(f"Justificativa: modelo {modelo.nome}." if modelo else "Justificativa: nenhum modelo cadastrado.")
