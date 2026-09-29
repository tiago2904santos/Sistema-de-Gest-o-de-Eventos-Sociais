---
name: git-checkpoint
description: Criar ponto de retorno antes de mudança arriscada.
---

# git-checkpoint

Criar ponto de retorno antes de mudança arriscada.

## Antes

- Leia `CLAUDE.md`, `docs/agent/lab-guide.md` e `docs/agent/memory/known-problems.md`.
- Servidor do laboratório: `npm run agent:serve` (banco próprio, dados sintéticos, relógio ancorado).

## Passos

1. `git status` limpo ou commit do WIP.
2. `git tag checkpoint/$(date +%Y%m%d-%H%M)-<assunto>`.
3. Registrar a tag no relatório da tarefa.

## Saída

tag. Achados sempre no formato `docs/agent/audit-finding.schema.json` (severidade P0–P4 + evidência).

## Pronto quando

Rollback possível com um comando. Registrar decisões/descobertas em `docs/agent/memory/`.
