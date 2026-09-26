"""Troca o "ate" sem acento gravado no horário de atendimento (m077).

O Plano criado a partir de uma viagem gravava "09:00 ate 17:00", que ia para o
documento e não batia com o catálogo ("09:00 até 17:00"). A volta não
reescreve: o texto com acento é o correto.
"""

from django.db import migrations
from django.db.models import Value
from django.db.models.functions import Replace


def acentuar(apps, schema_editor):
    for nome in ("PlanoTrabalho", "EventoPlano"):
        modelo = apps.get_model("viagens_planos", nome)
        modelo.objects.filter(horario_atendimento__contains=" ate ").update(
            horario_atendimento=Replace("horario_atendimento", Value(" ate "), Value(" até "))
        )


class Migration(migrations.Migration):

    dependencies = [
        ("viagens_planos", "0004_numero_lacuna"),
    ]

    operations = [
        migrations.RunPython(acentuar, migrations.RunPython.noop),
    ]
