# Arquitetura da infraestrutura do agente

```text
                ┌──────────── Claude (Cowork / Claude Code) ────────────┐
                │ skills (.claude/skills, 55) · agentes (.claude/agents, 23) │
                │ pipelines (docs/agent/pipelines, 8) · plugins (Superpowers, Design, code-review, Axe…) │
                └───────────────┬───────────────────────────────┬──────────┘
                                │ MCP (stdio)                   │ Bash
                     ┌──────────▼──────────┐          ┌─────────▼─────────┐
                     │ project-mcp (TS)     │          │ lab.py / doctor.py │
                     │ 106 ferramentas      │─────────▶│ npm run agent:*    │
                     └──┬──────┬──────┬────┘          └─────────┬─────────┘
          Playwright ◀──┘      │      └──▶ manage.py agent_*    │
          (sessões, axe,       │           (agent_lab)          │
           pixelmatch)         │                                │
                     ┌─────────▼────────────────────────────────▼─────────┐
                     │ Django do laboratório (:8031, AGENT_LAB=1)          │
                     │ banco LAB (.lab/lab.sqlite3, marca interna)         │
                     │ relógio ancorado · observabilidade · UI Lab /_lab/  │
                     └─────────────────────────────────────────────────────┘
      evidências: reports/ (não versionado) · conhecimento: docs/ + ui-inventory/ (versionados)
```

Princípios: **uma fonte de verdade por coisa** (ambiente em `lab.py::lab_env`, papéis em `tests/support/roles.ts`,
viewports em `viewports.ts`, varredura de layout em `layout-source.mjs` — o MCP importa os mesmos módulos dos testes);
**trabalho real e verificável** (nenhuma ferramenta simulada); **seguro por padrão** (ambiente classificado pelo banco);
**determinismo** (seed + relógio ancorados).
