# Observabilidade do agente

O que cada execução deixa registrado (sem segredos):

| Registro | Onde |
|---|---|
| Saúde do ambiente | `reports/agent-health.md`, `reports/agent/health.json` |
| Testes de navegador | `reports/testing/playwright-results.json`, `reports/testing/playwright-html/`, traces em `reports/testing/artifacts/` |
| Acessibilidade / responsivo / desempenho | `reports/{accessibility,responsive,performance}/` (+ `summary.md`) |
| Auditorias | `reports/audit/`, `reports/data/`, `reports/architecture/` |
| Decisões, descobertas, correções | `docs/agent/memory/` (versionado) |
| Mudanças | histórico git (mensagens descrevem evidência) |

`reports/` não é versionado (evidência regenerável); o que precisa sobreviver vai resumido para
`docs/agent/memory/` ou para o relatório da tarefa. Snapshot desta missão: `docs/agent/evidence/2026-09-29/`.
