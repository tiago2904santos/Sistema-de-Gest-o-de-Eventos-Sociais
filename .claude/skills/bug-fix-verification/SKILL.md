---
name: bug-fix-verification
description: Provar que a correção resolve e não quebra nada.
---

# bug-fix-verification

Provar que a correção resolve e não quebra nada.

## Antes

- `agent-discovery` se ainda não se orientou nesta sessão. Ferramentas: project-mcp (`.mcp.json`) ou CLI equivalente (`python scripts/agent/lab.py …`).

## Passos

1. O teste de reprodução passa (e falhava antes — mostre as duas execuções).
2. Testes do app afetado: `testing_run_django_tests {labels}`; se UI, `testing_run_e2e_tests` + `audit_page`.
3. Remover `expectedFailure`/`test.fail` correspondente; atualizar `known-problems.md`.
4. `superpowers:verification-before-completion` antes de afirmar 'corrigido'.

## Saída

Antes/depois dos testes citados no commit. Achados no formato `docs/agent/audit-finding.schema.json` (finding, severity, source, evidence, recommendation, verification).

## Exemplo

KP-00 corrigido → `agent_lab/test_known_bugs.py` passa sem o decorator.

## Se falhar

Algo quebrou → reverta para o checkpoint e reavalie a causa.

## Pronto quando

Evidência de antes/depois + suíte do app verde.
