# Convenções de engenharia

- **Idioma**: código de domínio, mensagens e docs em português (padrão existente).
- **Camadas por app**: `models.py` (invariantes + constraints no banco), `services.py` (casos de uso, transações),
  `forms.py`, `views.py` (finas), `presenters` para listas; templates em `templates/pages/<app>/`.
- **Autorização**: registrar o namespace em `accounts.modulos` e usar `acesso_ao_modulo` nas views.
- **Componentes**: `{% include "components/…" with … %}` com contrato comentado no topo; novo componente ganha espécimes em `agent_lab/specimens.py`.
- **Regras de dinheiro/numeração/documentos**: teste de caracterização primeiro; goldens para documentos.
- **Migrações**: estrutura → dados → estrutura; `makemigrations --check` limpo no CI.
- **CSS novo**: só tokens (`--t-*` de `static/css/tokens.css` durante a migração); nada de cor/raio/sombra literal.
- **JS novo**: módulo ES, sem globais, `// @ts-check`.
- **Tipagem**: Python com type hints em código novo; testes Playwright em TypeScript strict (`npm run typecheck`).
