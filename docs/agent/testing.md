# Testes do agente e do produto

Estratégia do produto: [`../testing/strategy.md`](../testing/strategy.md). Aqui, o que testa **a própria infraestrutura**:

| Teste | Comando | Cobre |
|---|---|---|
| Testes do `agent_lab` | `manage.py test agent_lab` (27 + 1 expectedFailure) | inventário, seed/ancoragem/cenários, ambiente, explain, contratos, consultas, UI Lab, auditoria |
| MCP sanity | `npm run mcp:sanity` | handshake + chamadas reais |
| Self-test | `npm run agent:self-test` | 19 passos ponta a ponta pelo protocolo MCP |
| Doctor | `npm run agent:doctor` | skills, agentes, pipelines, scripts, drift, mortos, banco, navegador |
| Health | `npm run agent:health` | 14 checagens do laboratório |
| Typecheck | `npm run typecheck` | testes + project-mcp em TS strict |
| Desempenho de páginas | `npm run test:perf` | vitals de laboratório das páginas-chave |

Todos entram no CI (`.github/workflows/agent-lab.yml`, trilhas fast/full/nightly).
