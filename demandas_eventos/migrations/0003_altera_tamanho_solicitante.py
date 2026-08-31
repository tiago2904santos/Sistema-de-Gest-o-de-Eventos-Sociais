from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("demandas_eventos", "0002_seed_modulo_ascom"),
    ]

    operations = [
        migrations.AlterField(
            model_name="demandaevento",
            name="solicitante",
            field=models.CharField(max_length=1000, verbose_name="solicitante"),
        ),
    ]
