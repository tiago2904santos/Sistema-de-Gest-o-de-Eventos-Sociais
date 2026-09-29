# Agentes

23 subagentes em `.claude/agents/` (validados pelo `doctor`: frontmatter, ferramentas nativas conhecidas, cada
`mcp__project-mcp__*` existe, skills citadas existem). Lista viva: `agent_list_agents`.

| Área | Agentes |
|---|---|
| Plataforma | tooling-architect, research-agent, final-verifier, documentation-agent, release-agent, incident-agent |
| Produto/UX | product-discovery-agent, ux-research-agent, design-agent, design-system-agent |
| Engenharia | architecture-agent, frontend-architect, frontend-implementer, backend-architect, backend-implementer, database-agent, api-agent |
| Qualidade | qa-agent, accessibility-agent, performance-agent, security-agent, browser-agent, migration-agent |

Mudanças desta missão: `product-agent` → **product-discovery-agent**; `ux-agent` → **ux-research-agent**; `frontend-agent` →
**frontend-architect** + **frontend-implementer**; `backend-agent` → **backend-architect** + **backend-implementer**;
`visual-agent` e `responsive-agent` fundidos em **design-agent**; novos **tooling-architect**, **research-agent**, **api-agent**,
**incident-agent**. `architecture-agent` fica como papel de sistema (acima dos architects de camada).
