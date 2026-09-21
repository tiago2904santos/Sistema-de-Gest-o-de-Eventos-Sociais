"""Tema múltiplo, servidor escolhido entre os palestrantes e canal como escolha.

- "Tema" passa a aceitar mais de um tema da aba TEMAS: o tema que a linha
  tinha vira o primeiro da lista.
- "Servidor" passa a ser a escolha de palestrantes do cadastro. O texto da
  planilha que casa com o nome de um palestrante vira o vínculo; o que não
  casa continua guardado em `servidor`, para ninguém perder o nome.
- "Foi solicitado via" vira uma escolha (E-mail, WhatsApp, Protocolo…) e o
  número do protocolo, que vinha no meio do texto, ganha campo próprio.
"""

import re
import unicodedata

from django.db import migrations, models


def _chave(texto):
    texto = unicodedata.normalize("NFKD", texto or "").encode("ascii", "ignore").decode()
    return re.sub(r"[^A-Z0-9]+", " ", texto.upper()).strip()


def canal_e_protocolo(texto):
    """(canal, protocolo, sobra) a partir do texto livre da planilha."""
    chave = _chave(texto)
    if not chave:
        return "", "", ""
    digitos = re.search(r"(\d{2})\D?(\d{3})\D?(\d{3})\D?(\d)", texto or "")
    if "PROTOCOLO" in chave or "EPROT" in chave or digitos:
        numero = f"{digitos.group(1)}.{digitos.group(2)}.{digitos.group(3)}-{digitos.group(4)}" if digitos else ""
        return "PROTOCOLO", numero, ""
    if "MAIL" in chave:
        return "EMAIL", "", ""
    if "WPP" in chave or "WHATS" in chave or "WWP" in chave:
        return "WHATSAPP", "", ""
    if "TELEFONE" in chave or "LIGAC" in chave:
        return "TELEFONE", "", ""
    if "PRESENCIAL" in chave:
        return "PRESENCIAL", "", ""
    return "OUTRO", "", (texto or "").strip()


def converter(apps, schema_editor):
    DemandaEvento = apps.get_model("demandas_eventos", "DemandaEvento")
    Palestrante = apps.get_model("demandas_eventos", "Palestrante")
    por_nome = {}
    for p in Palestrante.objects.all():
        por_nome.setdefault(_chave(p.nome), p)
    for demanda in DemandaEvento.objects.all():
        if demanda.tema_id:
            demanda.temas.add(demanda.tema_id)
        if demanda.servidor:
            partes = [_chave(x) for x in re.split(r"[/,;]|\be\b", demanda.servidor) if x.strip()]
            achados = [por_nome[c] for c in partes if c in por_nome]
            if achados and len(achados) == len(partes):
                demanda.palestrantes.add(*achados)
                demanda.servidor = ""
        canal, protocolo, sobra = canal_e_protocolo(demanda.canal_solicitacao)
        demanda.canal_solicitacao = canal
        demanda.protocolo = protocolo
        if sobra:
            demanda.informacoes_previas = "\n".join(
                x for x in [demanda.informacoes_previas.strip(), f"Foi solicitado via: {sobra}"] if x
            )
        demanda.save(update_fields=["servidor", "canal_solicitacao", "protocolo", "informacoes_previas"])


class Migration(migrations.Migration):

    dependencies = [
        ("demandas_eventos", "0009_horario_do_evento"),
    ]

    operations = [
        migrations.AddField(
            model_name="demandaevento",
            name="palestrantes",
            field=models.ManyToManyField(blank=True, related_name="demandas", to="demandas_eventos.palestrante", verbose_name="servidor"),
        ),
        migrations.AddField(
            model_name="demandaevento",
            name="protocolo",
            field=models.CharField(blank=True, max_length=20, verbose_name="nº do protocolo"),
        ),
        migrations.AddField(
            model_name="demandaevento",
            name="temas",
            field=models.ManyToManyField(blank=True, related_name="demandas", to="demandas_eventos.tema", verbose_name="tema"),
        ),
        migrations.RunPython(converter, migrations.RunPython.noop),
        migrations.RemoveField(model_name="demandaevento", name="tema"),
        migrations.AlterField(
            model_name="demandaevento",
            name="canal_solicitacao",
            field=models.CharField(blank=True, choices=[("EMAIL", "E-mail"), ("WHATSAPP", "WhatsApp"), ("PROTOCOLO", "Protocolo"), ("TELEFONE", "Telefone"), ("PRESENCIAL", "Presencial"), ("OUTRO", "Outro")], max_length=20, verbose_name="foi solicitado via"),
        ),
        migrations.AlterField(
            model_name="demandaevento",
            name="servidor",
            field=models.CharField(blank=True, max_length=300, verbose_name="servidor (texto da planilha)"),
        ),
    ]
