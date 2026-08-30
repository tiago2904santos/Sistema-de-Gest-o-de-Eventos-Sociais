from django.db import migrations


NOME_SERVICO_VIATURAS = "EXPOSIÇÃO DE VIATURAS ANTIGAS E MODERNAS"

SQL_VIEW_SEM_CAMPO = """
CREATE VIEW vw_solicitacoes AS
SELECT
    s.id AS solicitacao_id,
    s.status AS status_codigo,
    CASE s.status
        WHEN 'RASCUNHO' THEN 'Rascunho'
        WHEN 'AGUARDANDO_DESPACHO' THEN 'Aguardando despacho'
        WHEN 'DEVOLVIDA' THEN 'Devolvida para ajuste'
        WHEN 'DEFERIDA_EM_ANDAMENTO' THEN 'Deferida — em andamento'
        WHEN 'ATENDIDA' THEN 'Atendida'
        WHEN 'NAO_ATENDIDA' THEN 'Não atendida'
        WHEN 'CANCELADA' THEN 'Cancelada'
        ELSE s.status
    END AS status,
    s.decisao_dg AS decisao_codigo,
    CASE s.decisao_dg
        WHEN 'PENDENTE' THEN 'Pendente'
        WHEN 'ATENDER' THEN 'Atender'
        WHEN 'NAO_ATENDER' THEN 'Não atender'
        WHEN 'CANCELADO' THEN 'Evento cancelado'
        ELSE s.decisao_dg
    END AS decisao,
    s.data_solicitacao,
    s.data_inicio_evento,
    s.data_fim_evento,
    EXTRACT(YEAR FROM s.data_inicio_evento)::int AS ano_evento,
    EXTRACT(MONTH FROM s.data_inicio_evento)::int AS mes_evento,
    s.local_evento,
    m.nome AS municipio,
    r.nome AS regiao,
    e.nome AS estado,
    e.sigla AS estado_sigla,
    t.nome AS tipo_evento,
    o.nome AS orgao_responsavel,
    s.tipo_operacao AS tipo_operacao_codigo,
    CASE s.tipo_operacao
        WHEN 'DIARIA' THEN 'Diária'
        WHEN 'EXTRAJORNADA' THEN 'Extrajornada'
        ELSE s.tipo_operacao
    END AS tipo_operacao,
    s.unidade_movel,
    s.quantidade_servidores,
    s.quantidade_cin,
    s.solicitante_nome,
    s.solicitante_cargo_unidade,
    s.criado_em,
    s.atualizado_em,
    s.decidido_em
FROM solicitacoes_solicitacaoevento s
LEFT JOIN cadastros_municipio m ON m.id = s.municipio_id
LEFT JOIN cadastros_regiao r ON r.id = s.regiao_id
LEFT JOIN cadastros_estado e ON e.id = m.estado_id
LEFT JOIN cadastros_tipoevento t ON t.id = s.tipo_evento_id
LEFT JOIN cadastros_orgaoresponsavel o ON o.id = s.orgao_responsavel_id;
"""

SQL_VIEW_COM_CAMPO = SQL_VIEW_SEM_CAMPO.replace(
    "    s.unidade_movel,\n",
    "    s.unidade_movel,\n    s.veiculo_exposicao,\n",
)

SQL_REAPLICAR_GRANT = """
DO $$
BEGIN
    IF EXISTS (SELECT FROM pg_roles WHERE rolname = 'powerbi_reader') THEN
        GRANT SELECT ON vw_solicitacoes TO powerbi_reader;
    END IF;
END $$;
"""


def remover_view(apps, schema_editor):
    if schema_editor.connection.vendor == "postgresql":
        schema_editor.execute("DROP VIEW IF EXISTS vw_solicitacoes;")


def _criar_view(schema_editor, sql):
    if schema_editor.connection.vendor == "postgresql":
        schema_editor.execute(sql)
        schema_editor.execute(SQL_REAPLICAR_GRANT)


def criar_view_sem_campo(apps, schema_editor):
    _criar_view(schema_editor, SQL_VIEW_SEM_CAMPO)


def criar_view_com_campo(apps, schema_editor):
    _criar_view(schema_editor, SQL_VIEW_COM_CAMPO)


def converter_marcacoes_em_servico(apps, schema_editor):
    Solicitacao = apps.get_model("solicitacoes", "SolicitacaoEvento")
    ItemServico = apps.get_model("solicitacoes", "SolicitacaoEventoServico")
    Servico = apps.get_model("cadastros", "Servico")

    servico = Servico.objects.filter(nome__iexact=NOME_SERVICO_VIATURAS).first()
    if servico is None:
        servico = Servico.objects.create(nome=NOME_SERVICO_VIATURAS)

    ids_existentes = set(
        ItemServico.objects.filter(servico_id=servico.pk).values_list(
            "solicitacao_id", flat=True
        )
    )
    itens = [
        ItemServico(solicitacao_id=pk, servico_id=servico.pk)
        for pk in Solicitacao.objects.filter(veiculo_exposicao=True).values_list(
            "pk", flat=True
        )
        if pk not in ids_existentes
    ]
    ItemServico.objects.bulk_create(itens)


def restaurar_marcacoes_do_servico(apps, schema_editor):
    Solicitacao = apps.get_model("solicitacoes", "SolicitacaoEvento")
    ItemServico = apps.get_model("solicitacoes", "SolicitacaoEventoServico")
    Servico = apps.get_model("cadastros", "Servico")

    servico = Servico.objects.filter(nome__iexact=NOME_SERVICO_VIATURAS).first()
    if servico is None:
        return
    ids = ItemServico.objects.filter(servico_id=servico.pk).values_list(
        "solicitacao_id", flat=True
    )
    Solicitacao.objects.filter(pk__in=ids).update(veiculo_exposicao=True)


class Migration(migrations.Migration):

    dependencies = [
        ("solicitacoes", "0014_alter_historicosolicitacao_acao_and_more"),
    ]

    operations = [
        migrations.RunPython(remover_view, criar_view_com_campo),
        migrations.RunPython(
            converter_marcacoes_em_servico,
            restaurar_marcacoes_do_servico,
        ),
        migrations.RemoveField(
            model_name="solicitacaoevento",
            name="veiculo_exposicao",
        ),
        migrations.RunPython(criar_view_sem_campo, remover_view),
    ]
