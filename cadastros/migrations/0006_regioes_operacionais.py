"""Regiões passam a ser as operacionais da PCPR: Capital, Interior e Brasília.

O importador do IBGE gravava a macrorregião do país, o que colocava todos os
municípios do Paraná em "Sul" e deixava o campo inútil nas telas e nos
relatórios. A Diretoria-Geral organiza deslocamento por Capital / Interior /
Brasília — é essa a classificação que passa a valer.
"""

from django.db import migrations

CAPITAL = "Capital"
INTERIOR = "Interior"
BRASILIA = "Brasília"
NOVAS = [CAPITAL, INTERIOR, BRASILIA]


def aplicar(apps, schema_editor):
    Regiao = apps.get_model("cadastros", "Regiao")
    Municipio = apps.get_model("cadastros", "Municipio")
    Solicitacao = apps.get_model("solicitacoes", "SolicitacaoEvento")

    regioes = {nome: Regiao.objects.get_or_create(nome=nome)[0] for nome in NOVAS}

    # Curitiba/PR é a Capital; Brasília entra à parte; o resto é Interior.
    Municipio.objects.update(regiao=regioes[INTERIOR])
    Municipio.objects.filter(nome="Curitiba", estado__sigla="PR").update(
        regiao=regioes[CAPITAL]
    )
    Municipio.objects.filter(nome="Brasília").update(regiao=regioes[BRASILIA])

    # A solicitação guarda a região do município; realinha antes de limpar.
    for nome, regiao in regioes.items():
        Solicitacao.objects.filter(municipio__regiao=regiao).exclude(
            regiao=regiao
        ).update(regiao=regiao)
    Solicitacao.objects.filter(municipio__isnull=True).update(regiao=None)

    Regiao.objects.exclude(nome__in=NOVAS).delete()


def reverter(apps, schema_editor):
    """Sem volta possível: as mesorregiões antigas não são recuperáveis."""


class Migration(migrations.Migration):

    dependencies = [
        ("cadastros", "0005_unidademovel"),
        ("solicitacoes", "0015_remove_solicitacaoevento_veiculo_exposicao"),
    ]

    operations = [
        migrations.RunPython(aplicar, reverter),
    ]
