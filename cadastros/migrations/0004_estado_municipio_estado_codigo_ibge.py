import django.db.models.deletion
from django.db import migrations, models


def definir_parana_nos_municipios_existentes(apps, schema_editor):
    Estado = apps.get_model("cadastros", "Estado")
    Municipio = apps.get_model("cadastros", "Municipio")
    parana, _ = Estado.objects.get_or_create(
        codigo_ibge=41,
        defaults={"nome": "Paraná", "sigla": "PR"},
    )
    Municipio.objects.filter(estado__isnull=True).update(estado=parana)


class Migration(migrations.Migration):

    dependencies = [
        ("cadastros", "0003_remove_servico_descricao"),
    ]

    operations = [
        migrations.CreateModel(
            name="Estado",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("nome", models.CharField(max_length=150, unique=True, verbose_name="nome")),
                ("ativo", models.BooleanField(default=True, verbose_name="ativo")),
                ("criado_em", models.DateTimeField(auto_now_add=True, verbose_name="criado em")),
                ("atualizado_em", models.DateTimeField(auto_now=True, verbose_name="atualizado em")),
                ("sigla", models.CharField(max_length=2, unique=True, verbose_name="sigla")),
                (
                    "codigo_ibge",
                    models.PositiveSmallIntegerField(unique=True, verbose_name="código IBGE"),
                ),
            ],
            options={
                "verbose_name": "estado",
                "verbose_name_plural": "estados",
                "ordering": ["nome"],
            },
        ),
        migrations.AddField(
            model_name="municipio",
            name="codigo_ibge",
            field=models.PositiveIntegerField(
                blank=True, null=True, unique=True, verbose_name="código IBGE"
            ),
        ),
        migrations.AddField(
            model_name="municipio",
            name="estado",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="municipios",
                to="cadastros.estado",
                verbose_name="estado",
            ),
        ),
        migrations.RunPython(
            definir_parana_nos_municipios_existentes,
            migrations.RunPython.noop,
        ),
        migrations.AlterField(
            model_name="municipio",
            name="estado",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name="municipios",
                to="cadastros.estado",
                verbose_name="estado",
            ),
        ),
        migrations.RemoveConstraint(
            model_name="municipio",
            name="municipio_unico_por_regiao",
        ),
        migrations.AddConstraint(
            model_name="municipio",
            constraint=models.UniqueConstraint(
                fields=("nome", "estado"),
                name="municipio_unico_por_estado",
            ),
        ),
    ]
