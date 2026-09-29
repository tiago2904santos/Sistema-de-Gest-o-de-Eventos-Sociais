# Padrões rejeitados

- **Reescrever em SPA (React/Next) agora** — custo de reimplementar 600 rotas/62 formulários/regras sem ganho medido. Ver ADR 0001. Reavaliar pelos gatilhos do ADR.
- **Projeto greenfield paralelo** — duplicaria o domínio e os testes; a migração é "estranguladora" dentro do monólito, página a página.
- **Storybook** — exige React/Vue/Web Components; o equivalente é o UI Lab em Django (renderiza os templates reais).
- **Portão binário de a11y (zero violações) no dia 1** — deixaria o CI vermelho permanentemente e seria ignorado. Substituído por catraca.
- **Reformatar todo o código com ruff** — diff gigante, conflito com trabalho em andamento de outros agentes.
- **Semear dado "inválido" que o banco recusa** — o seed `invalid_data` só grava o que o banco aceita (dados que o formulário recusaria).
- **Lighthouse como dependência** — pesado; as métricas de laboratório vêm do próprio Playwright (LCP, CLS, long tasks, bytes). Lighthouse fica opcional (`npx lighthouse`).
- **MCP de Postgres** — o oficial foi arquivado; `manage.py shell/dbshell` respeita modelos, routers e o banco legado somente-leitura.
