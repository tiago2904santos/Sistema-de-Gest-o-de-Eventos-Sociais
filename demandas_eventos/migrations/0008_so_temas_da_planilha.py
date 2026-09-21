"""Só os temas da aba TEMAS da planilha.

- O "Tema de abordagem" do palestrante é uma coluna de texto da aba
  PALESTRANTES, não uma escolha entre temas: vira texto, com o que já estava
  marcado.
- Os temas que a migração 0006 semeou (o catálogo próprio, com subtemas) não
  estão na planilha e saem. A palestra que usava um deles guarda o nome em
  "Informações prévias" antes de o tema sair.

Os demais temas que não são da aba TEMAS saem na próxima importação da
planilha (`importar_planilha_ascom`), que passa a sincronizar a lista.
"""

import importlib

from django.db import migrations, models


def temas_de_abordagem_em_texto(apps, schema_editor):
    Palestrante = apps.get_model("demandas_eventos", "Palestrante")
    for palestrante in Palestrante.objects.prefetch_related("temas"):
        nomes = ", ".join(t.nome for t in palestrante.temas.all())
        if nomes:
            palestrante.tema_abordagem = nomes[:300]
            palestrante.save(update_fields=["tema_abordagem"])


def remove_temas_semeados(apps, schema_editor):
    semente = importlib.import_module("demandas_eventos.migrations.0006_seed_temas_e_subtemas_ascom")
    Tema = apps.get_model("demandas_eventos", "Tema")
    DemandaEvento = apps.get_model("demandas_eventos", "DemandaEvento")
    for tema in Tema.objects.filter(nome__in=list(semente.CATALOGO)):
        for demanda in DemandaEvento.objects.filter(tema=tema):
            demanda.informacoes_previas = "\n".join(
                parte for parte in [demanda.informacoes_previas.strip(), f"Tema: {tema.nome}"] if parte
            )
            demanda.tema = None
            demanda.save(update_fields=["informacoes_previas", "tema"])
        tema.delete()


class Migration(migrations.Migration):

    dependencies = [
        ("demandas_eventos", "0007_palestras_colunas_da_planilha"),
    ]

    operations = [
        migrations.AddField(
            model_name="palestrante",
            name="tema_abordagem",
            field=models.CharField(blank=True, max_length=300, verbose_name="tema de abordagem"),
        ),
        migrations.RunPython(temas_de_abordagem_em_texto, migrations.RunPython.noop),
        migrations.RemoveField(model_name="palestrante", name="temas"),
        migrations.RunPython(remove_temas_semeados, migrations.RunPython.noop),
    ]
