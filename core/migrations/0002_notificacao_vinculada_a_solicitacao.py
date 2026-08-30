"""Vincula a notificação à solicitação que a originou.

Antes o elo era só o texto do link: apagar a solicitação deixava a
notificação viva apontando para uma página 404. Esta migração cria a chave
estrangeira, religa as notificações existentes pelo link e descarta as que
ficaram órfãs.
"""

import re

import django.db.models.deletion
from django.db import migrations, models

LINK_SOLICITACAO = re.compile(r"^/solicitacoes/(\d+)/")


def religar_e_limpar(apps, schema_editor):
    Notificacao = apps.get_model("core", "Notificacao")
    Solicitacao = apps.get_model("solicitacoes", "SolicitacaoEvento")

    existentes = set(Solicitacao.objects.values_list("pk", flat=True))
    orfas = []
    for notificacao in Notificacao.objects.all():
        encontrado = LINK_SOLICITACAO.match(notificacao.link or "")
        if not encontrado:
            continue
        pk = int(encontrado.group(1))
        if pk in existentes:
            notificacao.solicitacao_id = pk
            notificacao.save(update_fields=["solicitacao"])
        else:
            orfas.append(notificacao.pk)
    Notificacao.objects.filter(pk__in=orfas).delete()


def desfazer(apps, schema_editor):
    """Nada a fazer: remover a coluna já desfaz o vínculo."""


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0001_initial'),
        ('solicitacoes', '0015_remove_solicitacaoevento_veiculo_exposicao'),
    ]

    operations = [
        migrations.AddField(
            model_name='notificacao',
            name='solicitacao',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='notificacoes', to='solicitacoes.solicitacaoevento', verbose_name='solicitação'),
        ),
        migrations.RunPython(religar_e_limpar, desfazer),
    ]
