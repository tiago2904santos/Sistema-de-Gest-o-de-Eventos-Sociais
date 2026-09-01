"""Remove o cadastro de motoristas, já convertido em servidores de viagens."""

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("cadastros", "0007_normaliza_nomes_em_caixa_alta"),
        # Declarada à mão: o Django não infere esta ordem, e sem ela a tabela
        # pode ser apagada antes de `solicitacoes.0018` copiar os motoristas
        # para servidores — a conversão leria uma tabela vazia e os vínculos
        # das solicitações se perderiam em silêncio.
        ("solicitacoes", "0019_motorista_aponta_para_servidor"),
    ]

    operations = [
        migrations.DeleteModel(
            name="Motorista",
        ),
    ]
