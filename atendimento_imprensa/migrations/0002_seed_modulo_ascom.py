"""Cataloga o módulo ASCOM_ATENDIMENTO_IMPRENSA e autoriza o setor ASCOM.

Seed idempotente; o histórico da planilha entra pelo comando
`importar_atendimentos`.
"""

from django.db import migrations

CODIGO_MODULO = "ASCOM_ATENDIMENTO_IMPRENSA"
NOME_MODULO = "Atendimento à Imprensa (ASCOM)"
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
    Modulo.objects.filter(codigo=CODIGO_MODULO).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("atendimento_imprensa", "0001_initial"),
        ("accounts", "0003_setor_modulo_user_setores"),
    ]

    operations = [
        migrations.RunPython(criar_modulo, remover_modulo),
    ]
