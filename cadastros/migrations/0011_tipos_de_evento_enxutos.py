"""Enxuga a lista de tipos de evento.

A lista veio da planilha com 26 itens e só 6 apareciam em solicitações; o
resto era repetição do mesmo assunto (Inauguração, Solenidade,
Reinauguração) ou nome de edição específica (EXPO - Palotina, EXPOARA). Num
campo de escolha isso é ruído: quem preenche rola uma lista de 26 para achar
o de sempre.

Ficam os que estão em uso e os genéricos que a ASCOM atende. Tipo em uso
nunca é apagado, mesmo que esteja fora da lista — o registro antigo continua
legível, e o que sobrou é relatado no log da migração.
"""

from django.db import migrations

MANTER = [
    "PCPR na Comunidade",
    "Justiça no Bairro",
    "Paraná em Ação",
    "Demafe",
    "Inauguração/Solenidade",
    "Evento",
    "Palestra",
    "Reunião",
    "Visita",
    "Capacitação",
    "Feira",
]


def enxugar(apps, schema_editor):
    TipoEvento = apps.get_model("cadastros", "TipoEvento")
    for nome in MANTER:
        TipoEvento.objects.get_or_create(nome=nome)
    # `solicitacoes` é PROTECT: o filtro evita a exceção e preserva histórico.
    TipoEvento.objects.exclude(nome__in=MANTER).filter(solicitacoes__isnull=True).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("cadastros", "0010_origem_legado"),
        ("solicitacoes", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(enxugar, migrations.RunPython.noop),
    ]
