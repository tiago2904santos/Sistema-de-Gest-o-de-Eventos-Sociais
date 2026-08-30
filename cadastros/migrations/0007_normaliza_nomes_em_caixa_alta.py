"""Nomes de cadastro deixam de ser gravados em CAIXA ALTA.

Gritar era decisão de apresentação embutida no dado: o nome aparecia em
maiúsculas no formulário, no resumo, no CSV exportado e no Power BI, sem que
ninguém pudesse mudar isso pelo CSS. As siglas continuam em maiúsculas.
"""

import re

from django.db import migrations

# Siglas que continuam em maiúsculas mesmo no meio da frase.
SIGLAS = {
    "CIN", "NOC", "PCPR", "IIPR", "DG", "RG", "BO", "CNH", "OAB",
    "TJPR", "SEJU", "SESP", "APAE", "CPF", "PR",
}

def _palavra(token, primeira):
    """Caixa de frase: só a primeira palavra sobe, siglas ficam como estão."""
    nucleo = token.strip("()[].,;:/")
    if nucleo.upper() in SIGLAS:
        return token
    minusculo = token.lower()
    if not primeira:
        return minusculo
    # Preserva pontuação de abertura ao capitalizar ("(texto" -> "(Texto").
    for indice, caractere in enumerate(minusculo):
        if caractere.isalnum():
            return minusculo[:indice] + caractere.upper() + minusculo[indice + 1:]
    return minusculo


def humanizar(nome):
    """"EXPOSIÇÃO DE MATERIAL TÁTICO" -> "Exposição de material tático"."""
    if nome != nome.upper():
        return nome  # Já foi escrito com caixa mista: respeita o que existe.
    tokens = re.split(r"(\s+)", nome.strip())
    resultado = []
    primeira = True
    for token in tokens:
        if not token.strip():
            resultado.append(token)
            continue
        resultado.append(_palavra(token, primeira))
        primeira = False
    return "".join(resultado)


def aplicar(apps, schema_editor):
    for rotulo in ("Servico", "TipoEvento", "Equipe", "OrgaoResponsavel"):
        modelo = apps.get_model("cadastros", rotulo)
        for registro in modelo.objects.all():
            novo = humanizar(registro.nome)
            if novo != registro.nome:
                registro.nome = novo
                registro.save(update_fields=["nome"])


def reverter(apps, schema_editor):
    """Sem volta: a caixa alta original não carregava informação."""


class Migration(migrations.Migration):

    dependencies = [
        ("cadastros", "0006_regioes_operacionais"),
    ]

    operations = [
        migrations.RunPython(aplicar, reverter),
    ]
