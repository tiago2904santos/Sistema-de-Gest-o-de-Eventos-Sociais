# Fluxos de trabalho (orquestrador)

Pipelines em `docs/agent/pipelines/*.json` (consulta: `agent_get_pipeline`). Cada fase define **agente**, **skills**,
**ferramentas** e **critério de saída**. O `doctor` valida que todas as referências existem.

Cadeia completa (`full-chain`):

```text
DISCOVER → RESEARCH → PLAN → ARCHITECTURE → IMPLEMENT → TEST → VISUAL REVIEW → ACCESSIBILITY
        → SECURITY → PERFORMANCE → REGRESSION → VERIFY → DOCUMENT
```

| Pedido do usuário | Pipeline |
|---|---|
| "Audite este módulo." | `audit-module` |
| "Redesenhe esta página." | `redesign-page` |
| "Reescreva este componente." | `rewrite-component` |
| "Investigue este bug." | `investigate-bug` |
| "Migre este módulo." | `migrate-module` |
| "Reconstrua o sistema." | `rebuild-system` (começa ratificando o ADR 0001) |
| "Avalie a arquitetura." | `evaluate-architecture` |

## Delegação

- Um subagente por fase (`.claude/agents/<agente>.md`), com ferramentas mínimas (lista explícita de `mcp__project-mcp__*`).
- Fases independentes podem rodar em paralelo (skill `superpowers:dispatching-parallel-agents`); multiagente em escala só com pedido explícito (Workflow).
- O `final-verifier` reexecuta as evidências antes de qualquer "pronto".
- Ciclo de revisão de design dentro de IMPLEMENT/VISUAL REVIEW: [`design-review-loop.md`](design-review-loop.md).
