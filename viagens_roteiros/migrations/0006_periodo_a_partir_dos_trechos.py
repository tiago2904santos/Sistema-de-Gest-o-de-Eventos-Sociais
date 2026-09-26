"""Preenche as datas do cabeçalho dos roteiros gravados só com trechos.

Só toca roteiros com as quatro datas vazias: os migrados do legado podem ter o
cabeçalho próprio, e esse vale. A regra é a de ``Roteiro.periodo_dos_trechos``,
repetida aqui porque a migração não enxerga métodos do modelo. A volta não
desfaz nada: as datas preenchidas continuam coerentes com os trechos.
"""

from django.db import migrations

CAMPOS = ("saida_dt", "chegada_dt", "retorno_saida_dt", "retorno_chegada_dt")


def preencher(apps, schema_editor):
    Roteiro = apps.get_model("viagens_roteiros", "Roteiro")
    vazios = Roteiro.objects.filter(**{f"{campo}__isnull": True for campo in CAMPOS})
    for roteiro in vazios.filter(trechos__isnull=False).distinct().iterator():
        trechos = list(roteiro.trechos.order_by("ordem", "pk"))
        ida = [t for t in trechos if t.sentido != "RETORNO"]
        volta = [t for t in trechos if t.sentido == "RETORNO"]
        saidas = [t.saida_dt for t in trechos if t.saida_dt]
        chegadas_ida = [t.chegada_dt for t in ida if t.chegada_dt]
        datas = [
            saidas[0] if saidas else None,
            chegadas_ida[-1] if chegadas_ida else None,
            volta[-1].saida_dt if volta else None,
            volta[-1].chegada_dt if volta else None,
        ]
        anterior = None
        for indice, valor in enumerate(datas):
            if valor is None:
                continue
            if anterior is not None and valor < anterior:
                datas[indice] = None
                continue
            anterior = valor
        if any(datas):
            Roteiro.objects.filter(pk=roteiro.pk).update(**dict(zip(CAMPOS, datas)))


class Migration(migrations.Migration):
    dependencies = [
        ("viagens_roteiros", "0005_roteiro_viagem"),
    ]

    operations = [
        migrations.RunPython(preencher, migrations.RunPython.noop),
    ]
