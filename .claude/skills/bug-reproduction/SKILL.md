---
name: bug-reproduction
description: Reproduzir um bug de forma determinística antes de corrigir.
---

# bug-reproduction

Reproduzir um bug de forma determinística antes de corrigir.

## Antes

- `agent-discovery` se ainda não se orientou nesta sessão. Ferramentas: project-mcp (`.mcp.json`) ou CLI equivalente (`python scripts/agent/lab.py …`).

## Passos

1. Cenário: `lab_reset {scenario}` ou `lab_create_test_scenario` com os dados mínimos.
2. Passos: `browser_run_page_flow` (trace ligado) ou teste Django/Playwright que falha.
3. Sinais: `obs_get_errors`, `browser_inspect_console`, `obs_get_requests`.
4. Registrar passos + evidência (trace, captura).

## Saída

Teste que falha + evidência. Achados no formato `docs/agent/audit-finding.schema.json` (finding, severity, source, evidence, recommendation, verification).

## Exemplo

KP-00: POST de exclusão do servidor com prestação → prestações somem (teste expectedFailure).

## Se falhar

Não reproduz → varie papel, viewport, cenário (`edge_case`), relógio; registre as tentativas.

## Pronto quando

Reprodução repetível 3×.
