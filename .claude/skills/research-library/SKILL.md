---
name: research-library
description: Aprender a API de uma biblioteca específica na versão instalada antes de usá-la (Context7 ou código-fonte local).
---

# research-library

Aprender a API de uma biblioteca específica na versão instalada antes de usá-la (Context7 ou código-fonte local).

## Antes

- `agent-discovery` se ainda não se orientou nesta sessão. Ferramentas: project-mcp (`.mcp.json`) ou CLI equivalente (`python scripts/agent/lab.py …`).

## Passos

1. Versão: `pip show <pkg>` / `npm ls <pkg>`.
2. Context7 (`resolve-library-id` → `query-docs`) quando o conector estiver disponível.
3. Sem Context7: tipos (`node_modules/<pkg>/**/*.d.ts`), docstrings (`python -c "import pkg; help(pkg.X)"`), exemplos nos testes do próprio pacote.
4. Escreva um teste mínimo que exercite a API antes de usá-la no projeto.

## Saída

Trecho de uso comprovado (teste ou execução) + versão. Achados no formato `docs/agent/audit-finding.schema.json` (finding, severity, source, evidence, recommendation, verification).

## Exemplo

`@modelcontextprotocol/sdk` 1.31: `registerTool` substitui `tool()` (lido em `dist/esm/server/mcp.d.ts`).

## Se falhar

API diverge da documentação → a do código instalado vence; registre em tooling-lessons.

## Pronto quando

Uso validado na versão do projeto.
