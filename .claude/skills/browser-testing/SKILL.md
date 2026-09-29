---
name: browser-testing
description: Navegar e inspecionar a aplicação no navegador (exploração).
---

# browser-testing

Navegar e inspecionar a aplicação no navegador (exploração).

## Antes

- Leia `CLAUDE.md`, `docs/agent/lab-guide.md` e `docs/agent/memory/known-problems.md`.
- Servidor do laboratório: `npm run agent:serve` (banco próprio, dados sintéticos, relógio ancorado).

## Passos

1. Subir o lab (`npm run agent:serve`).
2. Playwright MCP (plugin) ou Claude Browser para explorar; `read_page`/árvore de acessibilidade antes de captura.
3. Transformar o que foi verificado em spec (`tests/e2e`) para virar evidência repetível.

## Saída

notas + spec. Achados sempre no formato `docs/agent/audit-finding.schema.json` (severidade P0–P4 + evidência).

## Pronto quando

Tudo que foi concluído no navegador está num teste. Registrar decisões/descobertas em `docs/agent/memory/`.
