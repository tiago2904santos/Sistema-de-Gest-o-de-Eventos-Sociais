-- Usuário somente-leitura para o Power BI.
--
-- Execute UMA VEZ, conectado ao banco `eventos_sociais` com um usuário
-- administrador (ex.: postgres), depois de rodar as migrations:
--
--   psql -U postgres -h localhost -d eventos_sociais -f scripts/powerbi/criar_usuario_powerbi.sql
--
-- IMPORTANTE: troque a senha abaixo antes de executar.

CREATE ROLE powerbi_reader LOGIN PASSWORD 'TROQUE_ESTA_SENHA';

GRANT CONNECT ON DATABASE eventos_sociais TO powerbi_reader;
GRANT USAGE ON SCHEMA public TO powerbi_reader;

-- Acesso apenas às views de relatório — nunca às tabelas.
GRANT SELECT ON vw_solicitacoes TO powerbi_reader;
GRANT SELECT ON vw_solicitacao_servicos TO powerbi_reader;
GRANT SELECT ON vw_solicitacao_equipes TO powerbi_reader;
GRANT SELECT ON vw_tempos_workflow TO powerbi_reader;
