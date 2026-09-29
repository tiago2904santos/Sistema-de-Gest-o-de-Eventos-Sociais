# Descobertas

- **2026-09-29 · O repositório é o "Sistema de Gestão de Eventos Sociais"**, base da unificação com o Central de Viagens 3
  (apps `viagens_*`). Plano: `docs/PLANO_MESTRE_UNIFICACAO.md`.
- **2026-09-29 · Tamanho**: 600 rotas (incl. admin), 201 templates de página, 40 componentes de template, 62 formulários,
  109 modelos, 207 custom properties CSS, 18 arquivos CSS (~9,8 mil linhas), ~14,9 mil linhas de JS. Evidência: `ui-inventory/summary.json`.
- **2026-09-29 · Suíte**: 3.054 testes em 7 min (PG, `--parallel 8`); 14 falhas pré-existentes no `main` @ 53dbf3f —
  12 de texto de paginação ("Mostrando 1 a 20 de 21 …") desatualizados em relação ao componente, 2 de OCR (exigem `tesseract`).
- **2026-09-29 · O banco defende o período**: `periodo_evento_valido` impede data final < inicial em `SolicitacaoEvento`
  (tentativa de semear dado inválido falhou no PG). Bom sinal — regras críticas estão no banco.
- **2026-09-29 · `GET /viagens/planos/criar/` não cria nada** (redireciona). Hipótese de GET com efeito colateral descartada após ler a view.
- **2026-09-29 · Autorização**: middleware `AutorizacaoPorModuloMiddleware` + decorator `acesso_ao_modulo` (163 views). Rotas sem
  guarda explícita na view são poucas e em geral públicas por desenho (webhook, diário de campo por token, login/reset).
- **2026-09-29 · Grafo de imports**: 19 apps formam um único componente fortemente conexo (ciclo), e `accounts ↔ viagens_cadastros`
  se referenciam por FK (User.servidor ↔ …). Evidência: `reports/architecture/dependency-graph.json`.
- **2026-09-29 · DS v3.2 sem escalas**: 115 `font-size` distintos, 12+ raios, sombras e z-index literais, 18 breakpoints;
  `--d-500` = `--d-600` e `--d-400` = `--d-550` (tokens duplicados). Dourado de acento `#bea45a` tem 2,33:1 sobre papel.
- **2026-09-29 · `pdf-place.css` usa tokens de um DS antigo** (`--space-*`, `--text-muted`, `--radius-field`, `--surface`…) que não existem mais.
- **2026-09-29 · Navegação do módulo Viagens transborda**: 12 itens em `div.nav-mod` geram rolagem horizontal da página até em 1440px
  (página com 1588px). Evidência: `reports/responsive/*/desktop.json`, captura `oficios-lista.png`.
- **2026-09-29 · Lista de prestações pesa 656 KB de HTML e 7.394 nós** com 25 ofícios (cenário normal).
- **2026-09-29 · Agenda tem 5 violações axe *critical*** (`aria-allowed-attr`) e 49 *serious*. Evidência: `reports/accessibility/agenda.json`.
- **2026-09-29 · Com DEBUG, 404/500 próprios não aparecem**; use `/_lab/erro/<código>/` para vê-los.
- **2026-09-29 · Exclusão de servidor cascateia prestações de contas** (KP-00). A auditoria de banco apontou 9 cascatas sensíveis; a hipótese foi confirmada pela view real no lab, dentro de transação revertida.
