---
name: table-audit
description: Auditar tabelas/listas.
---

# table-audit

Auditar tabelas/listas.

## Antes

- Leia `CLAUDE.md`, `docs/agent/lab-guide.md` e `docs/agent/memory/known-problems.md`.
- Servidor do laboratório: `npm run agent:serve` (banco próprio, dados sintéticos, relógio ancorado).

## Passos

1. `ui-inventory/tables.json` (cabeçalhos, scope, wrapper).
2. Cenários `empty`, `large`, `long_text`.
3. Linha clicável, ordenação/paginação preservando filtros, contêiner com rolagem própria no celular, peso do HTML.

## Saída

achados. Achados sempre no formato `docs/agent/audit-finding.schema.json` (severidade P0–P4 + evidência).

## Pronto quando

Lista testada vazia, cheia e com texto longo. Registrar decisões/descobertas em `docs/agent/memory/`.
