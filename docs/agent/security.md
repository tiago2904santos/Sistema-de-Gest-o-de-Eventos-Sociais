# Segurança — agente e ferramentas

Regras do agente: [`security-rules.md`](security-rules.md). Aqui, a camada de ferramentas.

| Controle | Ferramenta | Portão |
|---|---|---|
| Ambiente do banco | `agent_lab/environment.py` (LAB/DEV/STAGING/PRODUCTION por marca interna + DEBUG + host) | reset/seed só em LAB; PRODUCTION somente leitura |
| SQL do agente | `db_explain` (só SELECT/WITH, transação somente-leitura; ANALYZE só LAB/DEV) | recusa escrita/DDL |
| Rede no lab | integrações desligadas; `agent_api` bloqueia conexões externas durante a varredura | — |
| SAST Python | bandit com catraca (`tests/security/bandit-baseline.json`) | CI fast |
| Config de produção | `manage.py check --deploy` com ambiente de produção simulado | CI fast |
| Dependências | pip-audit, npm audit, Dependabot | nightly (informativo) |
| Segredos | gitleaks no histórico; `.claude/settings.json` nega `.env` | nightly |
| Revisão de mudança | skill `security-review`, `/code-review` | por PR |

Não instalados (justificativa em `tool-registry.json`): Semgrep/CodeQL (bandit + auditoria estática cobrem Python; CodeQL pode
ser ligado no GitHub sem custo), Trivy/Checkov (não há container/IaC).

Estado atual: `npm run agent:security` → bandit sem achado novo, `check --deploy` limpo, **weasyprint 69.0 vulnerável** (KP-13).
Achados antigos do bandit para triagem (na baseline): caractere bidi em `core/leitura/mensagem.py:2001` (B613), `autoescape`
desligado no Jinja do docxtpl (B701), MD5/SHA1 sem `usedforsecurity=False` (B324) — KP-15.
