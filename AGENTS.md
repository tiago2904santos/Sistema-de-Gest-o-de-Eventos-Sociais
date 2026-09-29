# AGENTS.md — regras para agentes de IA (Claude, Codex, Copilot…)

Este repositório é trabalhado por humanos e por vários agentes ao mesmo tempo. Estas regras
valem para todos. Detalhes específicos do Claude estão em `CLAUDE.md`.

## Fonte da verdade

- Documentação: `docs/` (índice em `docs/README.md`). Não duplique conteúdo — linke.
- Estado do produto medido por máquina: `ui-inventory/*.json` (regerar: `npm run agent:inventory`).
- Memória de engenharia: `docs/agent/memory/*.md`.
- Achados de auditoria: formato único em `docs/agent/audit-finding.schema.json`.

## Fluxo de trabalho

1. Entender (ler docs + inventário + código) → 2. Planejar → 3. Checkpoint git →
4. Implementar em passos pequenos → 5. Testar (Django + Playwright) → 6. Evidência
(captura, diff, axe, trace) → 7. Registrar decisão/descoberta → 8. Commit.

## Proibido

- Commitar `.env`, dumps, `media/`, `.lab/`, `node_modules/`, `reports/`.
- Rodar comandos destrutivos em banco que não seja do laboratório.
- Rodar `git` na cópia de trabalho Windows a partir da VM do Cowork sem necessidade; quando inevitável, só com
  `-c core.autocrlf=true -c gc.auto=0 -c maintenance.auto=false` e conferindo travas órfãs no fim
  (`.git/*.lock`, `.git/gc.pid` — ver `docs/agent/memory/corrections.md`).
- Instalar dependência sem registrar em `requirements*.txt`/`package.json` e em `docs/agent/tooling-inventory.md`.
- Atualizar baseline visual/a11y/responsivo para "fazer o teste passar" sem revisar a diferença.
- Alterar regra de negócio (cálculo de diárias, numeração, documentos oficiais) sem teste de caracterização antes.

## Convenções

- Código, mensagens e documentação em **português**; identificadores seguem o que o app já usa.
- Commits: `tipo(escopo): resumo` com tipos `feat`, `fix`, `refactor`, `chore`, `migration`, `design`, `docs`, `test`.
- Ferramentas de qualidade: `ruff` (config em `pyproject.toml`), `tsc` para os testes, Playwright + axe.
