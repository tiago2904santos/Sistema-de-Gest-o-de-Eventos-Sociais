from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("cadastros", "0002_remove_orgaoresponsavel_sigla"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="servico",
            name="descricao",
        ),
    ]
