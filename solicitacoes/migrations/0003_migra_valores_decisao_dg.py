"""Converte os valores antigos de decisão da DG para os novos códigos.

DEFERIDA → ATENDER e INDEFERIDA → NAO_ATENDER, preservando registros já
existentes. A operação reversa restaura os valores antigos.
"""

from django.db import migrations

MAPEAMENTO = {"DEFERIDA": "ATENDER", "INDEFERIDA": "NAO_ATENDER"}


def aplicar(apps, schema_editor):
    SolicitacaoEvento = apps.get_model("solicitacoes", "SolicitacaoEvento")
    for antigo, novo in MAPEAMENTO.items():
        SolicitacaoEvento.objects.filter(decisao_dg=antigo).update(decisao_dg=novo)


def reverter(apps, schema_editor):
    SolicitacaoEvento = apps.get_model("solicitacoes", "SolicitacaoEvento")
    for antigo, novo in MAPEAMENTO.items():
        SolicitacaoEvento.objects.filter(decisao_dg=novo).update(decisao_dg=antigo)


class Migration(migrations.Migration):

    dependencies = [
        ("solicitacoes", "0002_historicosolicitacao_solicitacaoevento_decidido_em_and_more"),
    ]

    operations = [
        migrations.RunPython(aplicar, reverter),
    ]
