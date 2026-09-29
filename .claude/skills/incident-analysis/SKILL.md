---
name: incident-analysis
description: Analisar um incidente (erro em produção relatado, falha grave) sem acesso destrutivo: linha do tempo, causa, impacto, ações.
---

# incident-analysis

Analisar um incidente (erro em produção relatado, falha grave) sem acesso destrutivo: linha do tempo, causa, impacto, ações.

## Antes

- `agent-discovery` se ainda não se orientou nesta sessão. Ferramentas: project-mcp (`.mcp.json`) ou CLI equivalente (`python scripts/agent/lab.py …`).

## Passos

1. Coletar: relato, horário, logs fornecidos, versão (`git_history`).
2. Reproduzir no lab (`bug-reproduction`).
3. Causa raiz (5 porquês) com arquivo:linha; impacto em dados (somente leitura).
4. Relatório: linha do tempo, causa, impacto, correção, prevenção (teste/monitoramento) em `docs/agent/memory/`.

## Saída

Pós-mortem sem culpados. Achados no formato `docs/agent/audit-finding.schema.json` (finding, severity, source, evidence, recommendation, verification).

## Exemplo

"sumiram prestações" → KP-00 (cascata ao excluir servidor) como hipótese a confirmar nos logs de auditoria.

## Se falhar

Sem reprodução → documente hipóteses e o que falta para confirmá-las.

## Pronto quando

Causa confirmada e prevenção definida.
