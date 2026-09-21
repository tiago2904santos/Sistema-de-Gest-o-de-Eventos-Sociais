"""O módulo de demandas vira o formulário de palestras: um campo por coluna.

Antes de apagar os campos que não são colunas da aba do ano da planilha,
o conteúdo deles vai para "Informações prévias" — nada que já foi digitado
se perde. O tipo de evento, que era um cadastro, vira a coluna "Evento"
(Palestra, PCPR na Comunidade ou Evento), e "Não atender" vira "Cancelada",
como a planilha registra.
"""

import unicodedata

from django.db import migrations, models


def _chave(texto):
    texto = unicodedata.normalize("NFKD", texto or "").encode("ascii", "ignore").decode()
    return texto.upper()


def para_colunas_da_planilha(apps, schema_editor):
    DemandaEvento = apps.get_model("demandas_eventos", "DemandaEvento")
    for demanda in DemandaEvento.objects.select_related(
        "tipo_evento", "subtema", "responsavel_atendimento"
    ).prefetch_related("palestrantes"):
        tipo = _chave(demanda.tipo_evento.nome if demanda.tipo_evento_id else "")
        if "PALESTRA" in tipo:
            demanda.evento = "PALESTRA"
        elif "COMUNIDADE" in tipo:
            demanda.evento = "PCPR_NA_COMUNIDADE"
        else:
            demanda.evento = "EVENTO"
        if demanda.status == "NAO_ATENDER":
            demanda.status = "CANCELADA"

        palestrantes = ", ".join(p.nome for p in demanda.palestrantes.all())
        demanda.servidor = demanda.servidor_texto or palestrantes

        responsavel = demanda.responsavel_atendimento_texto
        if demanda.responsavel_atendimento_id:
            usuario = demanda.responsavel_atendimento
            responsavel = (f"{usuario.first_name} {usuario.last_name}".strip() or usuario.username)
        sobras = [
            ("Tipo de evento", demanda.tipo_evento.nome if demanda.tipo_evento_id and demanda.evento == "EVENTO" else ""),
            ("Subtema", demanda.subtema.nome if demanda.subtema_id else ""),
            ("Responsável pela organização", demanda.responsavel_organizacao),
            ("Responsável pelo atendimento", responsavel),
            ("Palestrantes", palestrantes if demanda.servidor_texto else ""),
            ("Unidade", demanda.unidade),
            ("Briefing", demanda.briefing),
            ("Matéria no site", demanda.materia_site),
        ]
        linhas = [f"{rotulo}: {valor.strip()}" for rotulo, valor in sobras if (valor or "").strip()]
        if linhas:
            demanda.informacoes_previas = "\n".join(
                parte for parte in [demanda.informacoes_previas.strip(), *linhas] if parte
            )
        demanda.save()


class Migration(migrations.Migration):

    dependencies = [
        ("demandas_eventos", "0006_seed_temas_e_subtemas_ascom"),
    ]

    operations = [
        migrations.AddField(
            model_name="demandaevento",
            name="evento",
            field=models.CharField(choices=[("PALESTRA", "Palestra"), ("PCPR_NA_COMUNIDADE", "PCPR na Comunidade"), ("EVENTO", "Evento")], default="PALESTRA", max_length=25, verbose_name="evento"),
        ),
        migrations.AddField(
            model_name="demandaevento",
            name="servidor",
            field=models.CharField(blank=True, max_length=300, verbose_name="servidor"),
        ),
        migrations.RunPython(para_colunas_da_planilha, migrations.RunPython.noop),
        migrations.RemoveField(model_name="demandaevento", name="subtema"),
        migrations.RemoveField(model_name="demandaevento", name="briefing"),
        migrations.RemoveField(model_name="demandaevento", name="materia_site"),
        migrations.RemoveField(model_name="demandaevento", name="palestrantes"),
        migrations.RemoveField(model_name="demandaevento", name="responsavel_atendimento"),
        migrations.RemoveField(model_name="demandaevento", name="responsavel_atendimento_texto"),
        migrations.RemoveField(model_name="demandaevento", name="responsavel_organizacao"),
        migrations.RemoveField(model_name="demandaevento", name="servidor_texto"),
        migrations.RemoveField(model_name="demandaevento", name="tipo_evento"),
        migrations.RemoveField(model_name="demandaevento", name="unidade"),
        migrations.RemoveField(model_name="palestrante", name="ativo"),
        migrations.RemoveField(model_name="respostapadrao", name="ativo"),
        migrations.RemoveField(model_name="tema", name="ativo"),
        migrations.DeleteModel(name="Subtema"),
        migrations.AlterModelOptions(
            name="demandaevento",
            options={"ordering": ["-data_solicitacao", "-pk"], "verbose_name": "palestra ou evento", "verbose_name_plural": "palestras e eventos"},
        ),
        migrations.AlterModelOptions(
            name="historicodemanda",
            options={"ordering": ["criado_em", "pk"], "verbose_name": "histórico de palestra ou evento", "verbose_name_plural": "históricos de palestras e eventos"},
        ),
        migrations.AlterField(
            model_name="demandaevento",
            name="assunto_email",
            field=models.CharField(blank=True, max_length=300, verbose_name="assunto e-mail"),
        ),
        migrations.AlterField(
            model_name="demandaevento",
            name="canal_solicitacao",
            field=models.CharField(blank=True, max_length=150, verbose_name="foi solicitado via"),
        ),
        migrations.AlterField(
            model_name="demandaevento",
            name="data_inicio_evento",
            field=models.DateField(blank=True, null=True, verbose_name="data do evento"),
        ),
        migrations.AlterField(
            model_name="demandaevento",
            name="pedido_contato",
            field=models.TextField(blank=True, verbose_name="pedido/contato"),
        ),
        migrations.AlterField(
            model_name="demandaevento",
            name="periodo_evento_texto",
            field=models.CharField(blank=True, max_length=200, verbose_name="hora (período)"),
        ),
        migrations.AlterField(
            model_name="demandaevento",
            name="status",
            field=models.CharField(choices=[("PENDENTE", "Pendente"), ("EM_ANDAMENTO", "Em andamento"), ("AGUARDANDO_RETORNO", "Aguardando retorno"), ("EVENTO_AGENDADO", "Agendada"), ("ATENDIDA", "Atendida"), ("CANCELADA", "Cancelada")], default="PENDENTE", max_length=25, verbose_name="status da demanda"),
        ),
        migrations.AlterField(
            model_name="historicodemanda",
            name="acao",
            field=models.CharField(choices=[("CRIACAO", "Registro criado"), ("ATUALIZACAO", "Registro atualizado"), ("TRANSICAO", "Status alterado")], max_length=20, verbose_name="ação"),
        ),
        migrations.AlterField(
            model_name="palestrante",
            name="nome",
            field=models.CharField(max_length=200, verbose_name="servidor"),
        ),
        migrations.AlterField(
            model_name="palestrante",
            name="temas",
            field=models.ManyToManyField(blank=True, related_name="palestrantes", to="demandas_eventos.tema", verbose_name="tema de abordagem"),
        ),
    ]
