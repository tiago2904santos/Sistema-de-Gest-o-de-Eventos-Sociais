from django.db import migrations, models


def normalizar_tipo_operacao(apps, schema_editor):
    SolicitacaoEvento = apps.get_model("solicitacoes", "SolicitacaoEvento")
    SolicitacaoEvento.objects.exclude(tipo_operacao="EXTRAJORNADA").update(
        tipo_operacao="DIARIA"
    )


def reverter_tipo_operacao(apps, schema_editor):
    SolicitacaoEvento = apps.get_model("solicitacoes", "SolicitacaoEvento")
    SolicitacaoEvento.objects.filter(tipo_operacao="DIARIA").update(
        tipo_operacao="ORDINARIA"
    )
    SolicitacaoEvento.objects.filter(tipo_operacao="EXTRAJORNADA").update(
        tipo_operacao="ESPECIAL"
    )


class Migration(migrations.Migration):

    dependencies = [
        ("solicitacoes", "0004_unifica_cargo_unidade_solicitante"),
    ]

    operations = [
        migrations.RunPython(normalizar_tipo_operacao, reverter_tipo_operacao),
        migrations.AlterField(
            model_name="solicitacaoevento",
            name="tipo_operacao",
            field=models.CharField(
                choices=[
                    ("DIARIA", "Diária"),
                    ("EXTRAJORNADA", "Extrajornada"),
                ],
                blank=True,
                default="DIARIA",
                max_length=20,
                verbose_name="tipo de operação",
            ),
        ),
    ]
