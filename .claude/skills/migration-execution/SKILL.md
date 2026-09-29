---
name: migration-execution
description: Executar a migração de uma página/módulo.
---

# migration-execution

Executar a migração de uma página/módulo.

## Antes

- Leia `CLAUDE.md`, `docs/agent/lab-guide.md` e `docs/agent/memory/known-problems.md`.
- Servidor do laboratório: `npm run agent:serve` (banco próprio, dados sintéticos, relógio ancorado).

## Passos

1. Checkpoint git.
2. Capturas `--label antes`.
3. Migrar uma página por commit.
4. Paridade (dados, permissões, cálculos, documentos, UX).
5. Atualizar matriz (status) e memória.

## Saída

commits por página. Achados sempre no formato `docs/agent/audit-finding.schema.json` (severidade P0–P4 + evidência).

## Pronto quando

Paridade aprovada; catracas iguais ou melhores. Registrar decisões/descobertas em `docs/agent/memory/`.
