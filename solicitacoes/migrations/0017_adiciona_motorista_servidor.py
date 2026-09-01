"""Abre o campo que vai receber o motorista como servidor de viagens.

Primeiro de três passos (0017 estrutura, 0018 dados, 0019 estrutura). A
separação não é estilo: o PostgreSQL recusa ``ALTER TABLE`` numa tabela com
eventos de gatilho pendentes, e é exatamente o que acontece quando a inserção
dos servidores e a alteração da coluna dividem a mesma transação — o
``migrate`` aborta no meio, com o banco já modificado. Cada migração tem sua
própria transação, então os dados são gravados e confirmados antes do passo
que mexe no esquema.
"""

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("solicitacoes", "0016_acao_historico_importacao"),
        ("viagens_cadastros", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="solicitacaoevento",
            name="motorista_servidor",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="solicitacoes_como_motorista",
                to="viagens_cadastros.servidor",
                verbose_name="motorista",
            ),
        ),
    ]
