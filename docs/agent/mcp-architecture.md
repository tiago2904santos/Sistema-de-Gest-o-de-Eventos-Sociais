# Arquitetura MCP

Princípio: um servidor por capacidade, nenhum redundante. Onde uma CLI/biblioteca local faz o
trabalho de forma verificável (e versionada no repo), ela vence um MCP.

| Capacidade | Solução | Tipo | Configuração | Observação |
|---|---|---|---|---|
| Navegador exploratório | **Playwright MCP** (Microsoft) | MCP | plugin `playwright` + `.mcp.json` do projeto | Snapshot de acessibilidade, sem coordenadas; traces em `reports/mcp-playwright` |
| Navegador de teste | `@playwright/test` | biblioteca | `playwright.config.ts` | Repetível, em CI; é o que produz evidência oficial |
| Acessibilidade | `@axe-core/playwright` (+ Axe MCP opcional) | biblioteca / MCP | `tests/support/a11y.ts` | Axe MCP exige chave Deque (`AXE_API_KEY`) — opcional |
| GitHub | **GitHub MCP** oficial | MCP | plugin `github` | Issues/PRs; push depende de o repositório estar autorizado na sessão |
| Banco de dados | `manage.py dbshell/shell` + `psql` | CLI | `.env` / lab | O MCP oficial de Postgres foi arquivado; Django shell respeita modelos, routers e o banco legado somente-leitura |
| Documentação atual | WebSearch/WebFetch nativos | nativo | — | Docs Django/Playwright/WCAG |
| Design | Skills do plugin **Design** + `docs/design-import/` | skills | — | Sem Figma no projeto |
| Arquivos do usuário | `remote-devices` | nativo | pasta conectada | Entrega da branch |
| Observabilidade | `reports/` + logs Django | local | — | Sem Sentry; recomendação futura em `docs/engineering/observability.md` |

## Fluxo típico

```text
exploração  → Playwright MCP / Claude Browser (olhar, clicar, entender)
evidência   → @playwright/test + axe (reprodutível, entra no git como teste)
diagnóstico → ui-inventory + agent_lab (inventário, dependências, auditoria estática)
entrega     → git (branch + bundle) / GitHub MCP quando autorizado
```

## Segurança

MCPs recebem só o necessário: o Playwright MCP navega no servidor do laboratório (dados sintéticos),
nunca no banco real. Nenhum segredo vai em `.mcp.json` (variáveis por ambiente).
