"""Cataloga o módulo ASCOM_COFFEE_BREAK e autoriza o setor ASCOM.

Seed idempotente de dados institucionais estáveis; os registros históricos
da planilha entram pelo comando `importar_coffee_break`.
"""

from django.db import migrations

CODIGO_MODULO = "ASCOM_COFFEE_BREAK"
NOME_MODULO = "Coffee Break (ASCOM)"
NOME_SETOR = "ASCOM"


def criar_modulo(apps, schema_editor):
    Setor = apps.get_model("accounts", "Setor")
    Modulo = apps.get_model("accounts", "Modulo")
    setor, _ = Setor.objects.get_or_create(
        nome=NOME_SETOR, defaults={"sigla": NOME_SETOR}
    )
    modulo, _ = Modulo.objects.get_or_create(
        codigo=CODIGO_MODULO, defaults={"nome": NOME_MODULO}
    )
    modulo.setores.add(setor)


def remover_modulo(apps, schema_editor):
    Modulo = apps.get_model("accounts", "Modulo")
    # O setor ASCOM fica: pode estar em uso por outros módulos.
    Modulo.objects.filter(codigo=CODIGO_MODULO).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("coffee_break", "0001_initial"),
        ("accounts", "0003_setor_modulo_user_setores"),
    ]

    operations = [
        migrations.RunPython(criar_modulo, remover_modulo),
    ]
