"""Destinos da OS com ordem (m069).

O M2M simples vira um modelo intermediário sobre a MESMA tabela: o estado
ganha ``OrdemServicoDestino`` e o banco só ganha a coluna ``ordem``. Os
registros atuais recebem a ordem que as telas já mostravam (alfabética), então
nada muda para quem abre uma OS antiga.
"""

import django.db.models.deletion
from django.db import migrations, models


def numerar_pelo_nome(apps, schema_editor):
    Destino = apps.get_model("viagens_ordens", "OrdemServicoDestino")
    atual, posicao = None, 0
    for destino in Destino.objects.order_by("ordemservico_id", "municipio__nome", "pk").iterator():
        if destino.ordemservico_id != atual:
            atual, posicao = destino.ordemservico_id, 0
        posicao += 1
        if destino.ordem != posicao:
            Destino.objects.filter(pk=destino.pk).update(ordem=posicao)


class Migration(migrations.Migration):

    dependencies = [
        ("cadastros", "0011_tipos_de_evento_enxutos"),
        ("viagens_ordens", "0002_initial"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.CreateModel(
                    name="OrdemServicoDestino",
                    fields=[
                        ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                        ("ordemservico", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to="viagens_ordens.ordemservico")),
                        ("municipio", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to="cadastros.municipio")),
                    ],
                    options={
                        "verbose_name": "Destino da Ordem de Serviço",
                        "verbose_name_plural": "Destinos da Ordem de Serviço",
                        "db_table": "viagens_ordens_ordemservico_destinos",
                        "unique_together": {("ordemservico", "municipio")},
                    },
                ),
                migrations.AlterField(
                    model_name="ordemservico",
                    name="destinos",
                    field=models.ManyToManyField(blank=True, related_name="ordens_servico", through="viagens_ordens.OrdemServicoDestino", to="cadastros.municipio", verbose_name="Destinos"),
                ),
            ],
            database_operations=[],
        ),
        # Fora do SeparateDatabaseAndState: a coluna nasce no banco e no estado.
        migrations.AddField(
            model_name="ordemservicodestino",
            name="ordem",
            field=models.PositiveIntegerField(default=0, verbose_name="ordem"),
        ),
        migrations.AlterModelOptions(
            name="ordemservicodestino",
            options={"ordering": ["ordem", "pk"], "verbose_name": "Destino da Ordem de Serviço", "verbose_name_plural": "Destinos da Ordem de Serviço"},
        ),
        migrations.RunPython(numerar_pelo_nome, migrations.RunPython.noop),
    ]
