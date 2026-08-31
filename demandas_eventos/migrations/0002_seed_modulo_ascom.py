"""Cataloga Demandas ASCOM e autoriza o setor ASCOM."""

from django.db import migrations


CODIGO_MODULO = "ASCOM_DEMANDAS_EVENTOS"


def criar_modulo(apps, schema_editor):
    Modulo = apps.get_model("accounts", "Modulo")
    Setor = apps.get_model("accounts", "Setor")

    setor, _ = Setor.objects.get_or_create(
        nome="ASCOM",
        defaults={"sigla": "ASCOM", "ativo": True},
    )
    if setor.sigla != "ASCOM" or not setor.ativo:
        setor.sigla = "ASCOM"
        setor.ativo = True
        setor.save(update_fields=["sigla", "ativo"])

    modulo, _ = Modulo.objects.update_or_create(
        codigo=CODIGO_MODULO,
        defaults={"nome": "ASCOM — Demandas de eventos", "ativo": True},
    )
    modulo.setores.add(setor)


def remover_modulo(apps, schema_editor):
    Modulo = apps.get_model("accounts", "Modulo")
    Modulo.objects.filter(codigo=CODIGO_MODULO).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("demandas_eventos", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(criar_modulo, remover_modulo),
    ]
