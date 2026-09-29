# Integração com o Superpowers

Plugin **Superpowers** (obra, parceiro revisado, v6.4.1) instalado pelo usuário nesta missão. Traz 15 skills de processo e um
hook `SessionStart`. Skills vistas nesta sessão: brainstorming, writing-plans, executing-plans, subagent-driven-development,
dispatching-parallel-agents, test-driven-development, systematic-debugging, verification-before-completion,
requesting-code-review, receiving-code-review, using-git-worktrees, finishing-a-development-branch, writing-skills,
using-superpowers, diagnosing-superpowers.

## Como se encaixa (sem duplicar)

| Superpowers | Projeto | Regra |
|---|---|---|
| writing-plans / brainstorming | `plan-feature`, `plan-architecture` | As do projeto dizem **o que** planejar aqui (lab, evidência, catracas); as do Superpowers, **como** conduzir o planejamento. Usar juntas. |
| test-driven-development | `testing-strategy`, `bug-fix-verification` | TDD para código novo; caracterização primeiro para regra de dinheiro/documento (regra do Plano Mestre). |
| systematic-debugging | `bug-reproduction`, `regression-analysis` | Referenciada no pipeline `investigate-bug`. |
| verification-before-completion | `final-verifier`, `release-validation` | Obrigatória antes de afirmar "pronto/corrigido". |
| requesting/receiving-code-review | plugin `code-review` (`/code-review`) | Revisão de PR multiagente continua pelo `code-review`. |
| using-git-worktrees / finishing-a-development-branch | `git-checkpoint`, `rollback`, AGENTS.md | Worktree é bem-vindo; a regra "nunca na main" e o bundle de entrega continuam valendo. |
| dispatching-parallel-agents / subagent-driven-development | `.claude/agents` + pipelines | Os 23 agentes do projeto são os papéis; o Superpowers dá o método de despacho. |

## Conflitos avaliados

- **Hook SessionStart** do Superpowers carrega `using-superpowers`, que pede invocar skills antes de responder. Não conflita
  com `CLAUDE.md`; ambos pedem descoberta antes de agir.
- Nenhuma skill do projeto foi removida por sobreposição: as do projeto são específicas do domínio/lab; as do Superpowers são
  de processo genérico.
