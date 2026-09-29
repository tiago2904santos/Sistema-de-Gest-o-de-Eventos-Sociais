---
name: form-audit
description: Auditar formulário: campos, validação, erros, acessibilidade, estados.
---

# form-audit

Auditar formulário: campos, validação, erros, acessibilidade, estados.

## Antes

- Leia `CLAUDE.md`, `docs/agent/lab-guide.md` e `docs/agent/memory/known-problems.md`.
- Servidor do laboratório: `npm run agent:serve` (banco próprio, dados sintéticos, relógio ancorado).

## Passos

1. Campos em `ui-inventory/forms.json`; template da página.
2. Enviar vazio, inválido, válido; checar mensagens, `aria-invalid`, foco no erro.
3. Conferir uso dos componentes `input/select/textarea` (nada montado à mão).
4. Celular: teclado virtual certo (`inputmode`).

## Saída

achados + spec. Achados sempre no formato `docs/agent/audit-finding.schema.json` (severidade P0–P4 + evidência).

## Pronto quando

Todo campo obrigatório tem erro anunciado. Registrar decisões/descobertas em `docs/agent/memory/`.

## Ferramentas MCP (project-mcp)

`audit_form`, `project_inspect_form`, `browser_submit` — ver `docs/agent/mcp.md`.

## Exemplo

`audit_form {path:'/solicitacoes/nova/', role:'solicitante'}`.

## Se falhar

Ferramenta MCP indisponível → use o equivalente de CLI (`python scripts/agent/lab.py …`, `manage.py agent_query …`, `npx playwright test …`). Lab fora do ar → `lab_start`/`npm run agent:serve`. Resultado inesperado → `agent-self-diagnosis`. Nunca conclua sem evidência.
