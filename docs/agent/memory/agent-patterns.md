# Padrões do agente (o que funciona)

- **Descobrir antes de agir**: `agent-discovery` → `project_inspect_*`/`knowledge_search` → só então código.
- **Uma pipeline por tipo de missão** (`agent_get_pipeline`), com o `final-verifier` no fim.
- **Evidência como saída padrão**: toda ferramenta de auditoria grava `findings.json` com `verification` — o próximo agente reexecuta em vez de confiar.
- **Composição explícita** no MCP: relatórios compõem ferramentas existentes (`report_generate_page_report` = inspeção + `audit-page.mjs`) em vez de duplicar lógica.
- **Catracas + expectedFailure/test.fail** para dívida conhecida: CI verde e útil, e o teste avisa quando a dívida é paga.
- **Determinismo em camadas**: cenário fixo + seed ancorado + relógio do servidor + `clock.setFixedTime` no navegador + estabilização de animações.
- **Controles detetivos para bugs do próprio ferramental** (ex.: volume do cenário no doctor).
