---
name: page-audit
description: Auditar UMA página de ponta a ponta com evidência.
---

# page-audit

Auditar UMA página de ponta a ponta com evidência.

## Antes

- Leia `CLAUDE.md`, `docs/agent/lab-guide.md` e `docs/agent/memory/known-problems.md`.
- Servidor do laboratório: `npm run agent:serve` (banco próprio, dados sintéticos, relógio ancorado).

## Passos

1. Garantir servidor do lab (`npm run agent:serve`) e sessões (`npm run test:smoke` uma vez).
2. `node tests/tools/audit-page.mjs --path <rota> --role <papel> --viewports desktop,tablet,mobile`.
3. Abrir as capturas e `findings.json`; repetir com `--scenario edge_case`/`empty` quando estados importarem.
4. Checklist de `docs/ux/README.md`.

## Saída

`reports/audit/<pagina>/`. Achados sempre no formato `docs/agent/audit-finding.schema.json` (severidade P0–P4 + evidência).

## Pronto quando

Achados com severidade + capturas; estados vazio/erro verificados. Registrar decisões/descobertas em `docs/agent/memory/`.
