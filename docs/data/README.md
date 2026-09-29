# Dados

- Modelo completo (109 entidades, campos, relações, constraints): `../../ui-inventory/entities.json`.
- Auditoria: `npm run agent:db-audit` → `reports/data/db-audit.{json,md}`.

## Achados estruturais (29/09/2026)

- **74 modelos com constraints declaradas** (períodos, não-negativos, unicidades) — invariantes no banco, bom.
- **Cascatas sensíveis (9)**: apagar um `Servidor` apaga `PrestacaoServidor` e `AssinaturaSubstituicao`; apagar um
  `Municipio` apaga `Feriado`, `OrdemServicoDestino` e `DistanciaMunicipios`. **Confirmado pela tela (KP-00, P1)**: a
  exclusão de servidor em `viagens_cadastros` só bloqueia vínculos PROTECT/RESTRICT, então apaga as prestações de contas
  do servidor. Correção sugerida: `on_delete=PROTECT` em `PrestacaoServidor.servidor` (migração) ou incluir CASCADE
  sensíveis na checagem. Teste que acusa a correção: `agent_lab/test_known_bugs.py`.
- **139 FKs anuláveis**, **106 campos `legado_*`** (rastreio da migração do GV — manter até a virada terminar),
  **15 modelos sem `ordering`** (paginação instável; o Django avisa `UnorderedObjectListWarning` em Coffee Break).
- Ciclo de FK `accounts ↔ viagens_cadastros`.

## Migração de dados

A migração do GV está em `migracao_legado/` (comandos `migrar_gv`/`desfazer_migracao_gv`, lotes, registros e vínculos
idempotentes). Uma eventual migração estrutural futura segue o mesmo padrão: estrutura → dados → estrutura, idempotente,
reversível, com testes pelo executor de migrações (ver F1 no Plano Mestre).
