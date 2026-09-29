---
name: rollback
description: Voltar a um estado conhecido com segurança.
---

# rollback

Voltar a um estado conhecido com segurança.

## Antes

- `agent-discovery` se ainda não se orientou nesta sessão. Ferramentas: project-mcp (`.mcp.json`) ou CLI equivalente (`python scripts/agent/lab.py …`).

## Passos

1. Identificar o ponto: `git_history`, tags `checkpoint/*`.
2. Preferir reversão não destrutiva: `git revert <commit>` ou nova branch a partir do checkpoint.
3. `git reset --hard` só com autorização explícita e sem trabalho não salvo.
4. Banco do LAB: `lab_reset`. Banco real: nunca pelo agente — só plano para o humano.
5. Reexecutar a validação (`testing_run_full_validation`).

## Saída

Estado restaurado + validação. Achados no formato `docs/agent/audit-finding.schema.json` (finding, severity, source, evidence, recommendation, verification).

## Exemplo

Refatoração quebrou o visual → `git revert` do commit, visual volta a bater.

## Se falhar

Conflitos no revert → pare e peça decisão.

## Pronto quando

Validação verde no estado restaurado.
