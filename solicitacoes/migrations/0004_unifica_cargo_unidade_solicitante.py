from django.db import migrations, models


def unificar_cargo_unidade(apps, schema_editor):
    SolicitacaoEvento = apps.get_model("solicitacoes", "SolicitacaoEvento")
    for solicitacao in SolicitacaoEvento.objects.all().iterator():
        partes = [
            valor.strip()
            for valor in (solicitacao.solicitante_cargo, solicitacao.solicitante_unidade)
            if valor and valor.strip()
        ]
        solicitacao.solicitante_cargo_unidade = " / ".join(partes)
        solicitacao.save(update_fields=["solicitante_cargo_unidade"])


def separar_cargo_unidade(apps, schema_editor):
    SolicitacaoEvento = apps.get_model("solicitacoes", "SolicitacaoEvento")
    for solicitacao in SolicitacaoEvento.objects.all().iterator():
        valor = (solicitacao.solicitante_cargo_unidade or "").strip()
        cargo, separador, unidade = valor.partition(" / ")
        solicitacao.solicitante_cargo = cargo
        solicitacao.solicitante_unidade = unidade if separador else ""
        solicitacao.save(update_fields=["solicitante_cargo", "solicitante_unidade"])


class Migration(migrations.Migration):

    dependencies = [
        ("solicitacoes", "0003_migra_valores_decisao_dg"),
    ]

    operations = [
        migrations.AddField(
            model_name="solicitacaoevento",
            name="solicitante_cargo_unidade",
            field=models.CharField(
                blank=True,
                max_length=255,
                verbose_name="cargo / unidade do solicitante",
            ),
        ),
        migrations.RunPython(unificar_cargo_unidade, separar_cargo_unidade),
        migrations.RemoveField(
            model_name="solicitacaoevento",
            name="solicitante_cargo",
        ),
        migrations.RemoveField(
            model_name="solicitacaoevento",
            name="solicitante_unidade",
        ),
    ]
