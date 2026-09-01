"""Cataloga o módulo VIAGENS e cria os grupos que escrevem nele.

Seed idempotente de dados institucionais estáveis. Nenhum setor é vinculado
aqui: quem opera viagens varia por instalação, e vincular a ASCOM por padrão
daria acesso a quem talvez não deva ter. O administrador liga o setor ao
módulo pela tela de usuários.
"""

from django.db import migrations

CODIGO_MODULO = "VIAGENS"
NOME_MODULO = "Viagens"
GRUPOS = ["VIAGENS_GESTOR", "VIAGENS_OPERADOR"]


def criar(apps, schema_editor):
    Modulo = apps.get_model("accounts", "Modulo")
    Group = apps.get_model("auth", "Group")
    Modulo.objects.get_or_create(codigo=CODIGO_MODULO, defaults={"nome": NOME_MODULO})
    for nome in GRUPOS:
        Group.objects.get_or_create(name=nome)


def remover(apps, schema_editor):
    Modulo = apps.get_model("accounts", "Modulo")
    Group = apps.get_model("auth", "Group")
    Modulo.objects.filter(codigo=CODIGO_MODULO).delete()
    Group.objects.filter(name__in=GRUPOS).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("viagens_cadastros", "0001_initial"),
        ("accounts", "0003_setor_modulo_user_setores"),
        ("auth", "0012_alter_user_first_name_max_length"),
    ]

    operations = [
        migrations.RunPython(criar, remover),
    ]
