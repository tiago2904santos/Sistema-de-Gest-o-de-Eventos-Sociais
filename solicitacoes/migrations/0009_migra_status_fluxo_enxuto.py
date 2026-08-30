"""Fluxo enxuto: solicitações em análise passam a aguardar despacho.

Os status ENVIADA e EM_ANALISE deixaram de existir — quem estava neles
segue direto para a fila da DG (AGUARDANDO_DESPACHO). O histórico preserva
os valores antigos apenas como registro.
"""

from django.db import migrations

STATUS_EXTINTOS = ["ENVIADA", "EM_ANALISE"]


def aplicar(apps, schema_editor):
    SolicitacaoEvento = apps.get_model("solicitacoes", "SolicitacaoEvento")
    SolicitacaoEvento.objects.filter(status__in=STATUS_EXTINTOS).update(
        status="AGUARDANDO_DESPACHO"
    )


class Migration(migrations.Migration):

    dependencies = [
        ("solicitacoes", "0008_alter_historicosolicitacao_status_anterior_and_more"),
    ]

    operations = [
        # Irreversível de propósito: não há como saber quem estava em análise.
        migrations.RunPython(aplicar, migrations.RunPython.noop),
    ]
