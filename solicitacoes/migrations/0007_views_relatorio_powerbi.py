"""Views SQL de relatório para consumo pelo Power BI.

Criadas apenas em PostgreSQL (no-op em SQLite, usado como fallback de
desenvolvimento/CI). O Power BI conecta com o usuário somente-leitura
`powerbi_reader` (ver scripts/powerbi/criar_usuario_powerbi.sql) e enxerga
apenas estas views, com códigos já traduzidos para rótulos em português.
"""

from django.db import migrations

VIEWS = ["vw_solicitacoes", "vw_solicitacao_servicos", "vw_solicitacao_equipes", "vw_tempos_workflow"]

SQL_CRIAR = """
CREATE OR REPLACE VIEW vw_solicitacoes AS
SELECT
    s.id AS solicitacao_id,
    s.status AS status_codigo,
    CASE s.status
        WHEN 'RASCUNHO' THEN 'Rascunho'
        WHEN 'ENVIADA' THEN 'Enviada'
        WHEN 'EM_ANALISE' THEN 'Em análise'
        WHEN 'AGUARDANDO_DESPACHO' THEN 'Aguardando despacho'
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
    s.veiculo_exposicao,
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

CREATE OR REPLACE VIEW vw_solicitacao_servicos AS
SELECT
    ss.solicitacao_id,
    sv.nome AS servico
FROM solicitacoes_solicitacaoeventoservico ss
JOIN cadastros_servico sv ON sv.id = ss.servico_id;

CREATE OR REPLACE VIEW vw_solicitacao_equipes AS
SELECT
    se.solicitacao_id,
    eq.nome AS equipe,
    se.quantidade_servidores
FROM solicitacoes_solicitacaoeventoequipe se
JOIN cadastros_equipe eq ON eq.id = se.equipe_id;

CREATE OR REPLACE VIEW vw_tempos_workflow AS
SELECT
    h.solicitacao_id,
    MIN(CASE WHEN h.acao = 'CRIACAO' THEN h.criado_em END) AS criado_em,
    MIN(CASE WHEN h.acao = 'ENVIO' THEN h.criado_em END) AS enviado_em,
    MIN(CASE WHEN h.acao = 'INICIO_ANALISE' THEN h.criado_em END) AS analise_iniciada_em,
    MIN(CASE WHEN h.acao = 'ENCAMINHAMENTO_DESPACHO' THEN h.criado_em END) AS encaminhado_despacho_em,
    MIN(CASE WHEN h.acao = 'DECISAO' THEN h.criado_em END) AS decidido_em
FROM solicitacoes_historicosolicitacao h
GROUP BY h.solicitacao_id;
"""


def criar_views(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    schema_editor.execute(SQL_CRIAR)


def remover_views(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    for view in VIEWS:
        schema_editor.execute(f"DROP VIEW IF EXISTS {view}")


class Migration(migrations.Migration):

    dependencies = [
        ("solicitacoes", "0006_quantidade_servidores_por_equipe"),
        # As views juntam tabelas de cadastros; garante que elas existem.
        ("cadastros", "0004_estado_municipio_estado_codigo_ibge"),
    ]

    operations = [
        migrations.RunPython(criar_views, remover_views),
    ]
