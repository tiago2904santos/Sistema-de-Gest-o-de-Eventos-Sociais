# Política de seleção de ferramentas

Antes de executar uma tarefa:

1. **Nomeie a capacidade** necessária ("contraste de uma página", "por que a lista está lenta").
2. **Procure a ferramenta especializada** — `agent_select_tool {capability}` consulta `docs/agent/tool-registry.json`.
3. **Use a mais específica**, nesta ordem:
   1. ferramenta do **project-mcp** (conhece o projeto, respeita o ambiente, gera evidência);
   2. comando do **laboratório** (`python scripts/agent/lab.py …`, `manage.py agent_*`, `npm run …`);
   3. **skill/plugin** oficial (Design, Superpowers, code-review, Axe, Figma quando conectado);
   4. ferramenta genérica (Bash, WebFetch, navegador manual) — só se nada acima cobre.
4. **Evite redundância**: uma ferramenta por capacidade. Não confirme o resultado de `audit_accessibility` rodando outro scanner.
5. **Se estiver indisponível** (`UNAVAILABLE`/`REQUIRES_MANUAL_CONNECTION`), use a `replacement` do registro e registre a lacuna.
6. **Evidência**: toda conclusão cita a saída da ferramenta (arquivo em `reports/…` ou fonte `arquivo:linha`).

Exemplos: layout no celular → `audit_responsive` · "a view faz N+1?" → `obs_get_slow_queries` + `db_explain` ·
"onde esse componente é usado?" → `inventory_get_component_usage` · "qual a regra de diária?" → `knowledge_search_business_rules`.
