---
name: dependency-review
description: Revisar dependências: vulnerabilidades, necessidade, versões fixadas, licenças.
---

# dependency-review

Revisar dependências: vulnerabilidades, necessidade, versões fixadas, licenças.

## Antes

- `agent-discovery` se ainda não se orientou nesta sessão. Ferramentas: project-mcp (`.mcp.json`) ou CLI equivalente (`python scripts/agent/lab.py …`).

## Passos

1. `pip-audit -r requirements.txt` e `npm audit`.
2. Para dependência nova: é necessária? existe algo no projeto que já faz? mantida? licença?
3. Fixar versão; registrar em `docs/agent/tool-registry.json`/`tooling-inventory.md`.
4. Atualização com impacto (ex.: weasyprint 70) → rodar goldens de documento.

## Saída

Lista de vulnerabilidades + decisão por pacote. Achados no formato `docs/agent/audit-finding.schema.json` (finding, severity, source, evidence, recommendation, verification).

## Exemplo

weasyprint 69.0 (PYSEC-2026-3940) → atualizar para 70 com `documentos.tests.test_golden_templates`.

## Se falhar

Sem rede → registre que a checagem não rodou; não afirme 'sem vulnerabilidades'.

## Pronto quando

Nenhuma dependência sem motivo e versão registrados.
