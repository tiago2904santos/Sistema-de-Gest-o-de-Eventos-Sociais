# Problemas conhecidos do produto (abertos)

Severidade: P0 quebrado · P1 crítico · P2 importante · P3 melhoria relevante · P4 refinamento.
Relatórios completos: `reports/audit/static-findings.md` (estático) e `docs/auditoria-pratica-2026-09-29.md` (manual).

| # | Sev. | Categoria | Problema | Evidência |
|---|---|---|---|---|
| KP-00 | **P1** | FUNCTIONAL (perda de dado) | Excluir um servidor pela tela (`POST /viagens/cadastros/servidores/<pk>/excluir/`) apaga em silêncio as prestações de contas dele: `PrestacaoServidor.servidor` é CASCADE e `_dependencias_protegidas` só considera PROTECT/RESTRICT. Reproduzido no lab (2 prestações → 0). | `agent_lab/test_known_bugs.py` (expectedFailure), `reports/data/db-audit.md` |
| KP-01 | P1 | ACCESSIBILITY | Agenda: 5 violações axe críticas (`aria-allowed-attr`) + 49 sérias | `reports/accessibility/agenda.json` |
| KP-02 | P2 | ACCESSIBILITY | Foco do teclado invisível (`:focus-visible{outline:none}` global em `ds-v32.css`) | `tests/regression/known-bugs.spec.ts` (test.fail) |
| KP-03 | P2 | ACCESSIBILITY | Contraste: `--n-400` (3,78:1) e `--rotulo` (4,29:1) em texto pequeno; ~3 violações `color-contrast` por página | `reports/design/contrast.md`, `reports/accessibility/summary.md` |
| KP-04 | P2 | RESPONSIVE | Navegação do módulo Viagens transborda: rolagem horizontal em 40 combinações página×viewport, inclusive 1440px | `tests/responsive/baseline.json` |
| KP-05 | P2 | VISUAL | `pdf-place.css` referencia 13 custom properties inexistentes | `ui-inventory/tokens.json → used_but_undefined` |
| KP-06 | P2 | SECURITY | `DEBUG` liga por padrão quando `DJANGO_DEBUG` não existe | `config/settings.py` |
| KP-13 | P2 | SECURITY | `weasyprint 69.0` tem vulnerabilidade conhecida (PYSEC-2026-3940), corrigida na 70.0; `requirements.txt` fixa `<70.0`. Avaliar a atualização com os goldens de PDF | `pip-audit -r requirements.txt` |
| KP-07 | P3 | PERFORMANCE | Lista de prestações: 656 KB de HTML, 7.394 nós, 52 violações de contraste, `landmark-unique` ×24 | `reports/audit/viagens-prestacoes/` |
| KP-08 | P3 | CONSISTENCY | DS sem escalas (115 font-sizes, 18 breakpoints, 12+ raios); 3 CSS concorrentes (design-system + ds-v32 + bridge) com 308 seletores duplicados | `ui-inventory/styles.json`, `duplication-report.json` |
| KP-09 | P3 | FUNCTIONAL | 14 testes falhando no `main` (12 de paginação desatualizados, 2 OCR sem tesseract) | `docs/agent/BOOTSTRAP-REPORT.md` |
| KP-10 | P3 | ARCHITECTURE | Ciclo de imports envolvendo 19 apps; `core` depende de apps de domínio | `reports/architecture/dependency-graph.json` |
| KP-11 | P3 | MAINTAINABILITY | 127 páginas sem estado de erro detectável e 130 sem estado vazio (heurística) | `ui-inventory/states.json` |
| KP-12 | P3 | UX | Linha de lista não clicável (UX-01 da auditoria manual) | `docs/auditoria-pratica-2026-09-29.md` |
