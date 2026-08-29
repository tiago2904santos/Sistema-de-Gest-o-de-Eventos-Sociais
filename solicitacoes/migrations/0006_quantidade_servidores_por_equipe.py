from django.db import migrations, models


def migrar_quantidade_da_equipe_unica(apps, schema_editor):
    SolicitacaoEvento = apps.get_model("solicitacoes", "SolicitacaoEvento")
    for solicitacao in SolicitacaoEvento.objects.exclude(
        quantidade_servidores__isnull=True
    ).iterator():
        itens = list(solicitacao.itens_equipe.all()[:2])
        if len(itens) == 1:
            itens[0].quantidade_servidores = solicitacao.quantidade_servidores
            itens[0].save(update_fields=["quantidade_servidores"])


class Migration(migrations.Migration):

    dependencies = [
        ("solicitacoes", "0005_tipo_operacao_diaria_extrajornada"),
    ]

    operations = [
        migrations.AddField(
            model_name="solicitacaoeventoequipe",
            name="quantidade_servidores",
            field=models.PositiveIntegerField(
                blank=True,
                null=True,
                verbose_name="quantidade de servidores",
            ),
        ),
        migrations.RunPython(
            migrar_quantidade_da_equipe_unica,
            migrations.RunPython.noop,
        ),
    ]
