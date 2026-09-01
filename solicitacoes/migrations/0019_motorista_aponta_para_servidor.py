"""Aposenta a coluna antiga e devolve o nome ``motorista`` ao campo novo.

Terceiro e último passo da conversão. Só esquema — os dados já foram
convertidos e confirmados em `0018`, pelo motivo explicado em `0017`.
"""

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("solicitacoes", "0018_migrar_motoristas_para_servidores"),
    ]

    operations = [
        migrations.RemoveField(model_name="solicitacaoevento", name="motorista"),
        migrations.RenameField(
            model_name="solicitacaoevento",
            old_name="motorista_servidor",
            new_name="motorista",
        ),
    ]
