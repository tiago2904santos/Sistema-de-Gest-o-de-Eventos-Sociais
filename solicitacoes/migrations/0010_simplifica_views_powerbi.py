"""Views do Power BI ajustadas ao fluxo enxuto.

Com o fim da etapa de análise (0009), os status ENVIADA/EM_ANALISE e os
marcos INICIO_ANALISE/ENCAMINHAMENTO_DESPACHO não ocorrem mais:

- vw_solicitacoes deixa de traduzir os status extintos;
- vw_tempos_workflow passa a ter só os marcos reais (criação, envio e
  decisão) e já entrega a métrica pronta `dias_envio_ate_decisao`.

Como a vw_tempos_workflow perde colunas, ela precisa ser dropada e
recriada — o que derruba o GRANT do powerbi_reader; o GRANT é refeito
aqui mesmo quando o role existir.
"""

from django.db import migrations

SQL_SIMPLIFICAR = """
CREATE OR REPLACE VIEW vw_solicitacoes AS
SELECT
    s.id AS solicitacao_id,
    s.status AS status_codigo,
    CASE s.status
        WHEN 'RASCUNHO' THEN 'Rascunho'
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

DROP VIEW IF EXISTS vw_tempos_workflow;

CREATE VIEW vw_tempos_workflow AS
SELECT
    t.solicitacao_id,
    t.criado_em,
    t.enviado_em,
    t.decidido_em,
    ROUND(
        (EXTRACT(EPOCH FROM (t.decidido_em - t.enviado_em)) / 86400.0)::numeric,
        2
    ) AS dias_envio_ate_decisao
FROM (
    SELECT
        h.solicitacao_id,
        MIN(CASE WHEN h.acao = 'CRIACAO' THEN h.criado_em END) AS criado_em,
        MIN(CASE WHEN h.acao = 'ENVIO' THEN h.criado_em END) AS enviado_em,
        MIN(CASE WHEN h.acao = 'DECISAO' THEN h.criado_em END) AS decidido_em
    FROM solicitacoes_historicosolicitacao h
    GROUP BY h.solicitacao_id
) t;

DO $$
BEGIN
    IF EXISTS (SELECT FROM pg_roles WHERE rolname = 'powerbi_reader') THEN
        GRANT SELECT ON vw_tempos_workflow TO powerbi_reader;
    END IF;
END $$;
"""

SQL_RESTAURAR = """
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

DROP VIEW IF EXISTS vw_tempos_workflow;

CREATE VIEW vw_tempos_workflow AS
SELECT
    h.solicitacao_id,
    MIN(CASE WHEN h.acao = 'CRIACAO' THEN h.criado_em END) AS criado_em,
    MIN(CASE WHEN h.acao = 'ENVIO' THEN h.criado_em END) AS enviado_em,
    MIN(CASE WHEN h.acao = 'INICIO_ANALISE' THEN h.criado_em END) AS analise_iniciada_em,
    MIN(CASE WHEN h.acao = 'ENCAMINHAMENTO_DESPACHO' THEN h.criado_em END) AS encaminhado_despacho_em,
    MIN(CASE WHEN h.acao = 'DECISAO' THEN h.criado_em END) AS decidido_em
FROM solicitacoes_historicosolicitacao h
GROUP BY h.solicitacao_id;

DO $$
BEGIN
    IF EXISTS (SELECT FROM pg_roles WHERE rolname = 'powerbi_reader') THEN
        GRANT SELECT ON vw_tempos_workflow TO powerbi_reader;
    END IF;
END $$;
"""


def simplificar(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    schema_editor.execute(SQL_SIMPLIFICAR)


def restaurar(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    schema_editor.execute(SQL_RESTAURAR)


class Migration(migrations.Migration):

    dependencies = [
        ("solicitacoes", "0009_migra_status_fluxo_enxuto"),
    ]

    operations = [
        migrations.RunPython(simplificar, restaurar),
    ]
