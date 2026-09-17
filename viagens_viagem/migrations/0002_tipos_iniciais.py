"""Tipos de viagem iniciais, os mesmos tipos de evento do Gerenciador de Viagens."""

from django.db import migrations

TIPOS = ["PCPR na Comunidade", "Operação Policial", "Paraná em Ação", "Expo", "Justiça no Bairro"]


def criar(apps, schema_editor):
    Tipo = apps.get_model("viagens_viagem", "TipoViagem")
    for nome in TIPOS:
        Tipo.objects.get_or_create(nome=nome)


def remover(apps, schema_editor):
    pass


class Migration(migrations.Migration):
    dependencies = [("viagens_viagem", "0001_initial")]
    operations = [migrations.RunPython(criar, remover)]
