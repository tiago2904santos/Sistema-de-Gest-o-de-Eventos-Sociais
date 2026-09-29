# Acessibilidade

Meta: **WCAG 2.2 AA**. Medição automática: `npm run test:a11y` (axe em 21 páginas) + axe por componente no UI Lab.

**Hoje**: 5 críticas (agenda, `aria-allowed-attr`), 177 sérias (contraste em quase todas as páginas; `target-size` no
formulário de solicitação), 26 moderadas (`landmark-unique`). Foco invisível no casco (A11Y-01).

**Regras**
- Foco visível com `:focus-visible` e anel `focus-ring` (≥ 3:1). Nunca `outline:none` sem substituto.
- Contraste AA com os tokens aprovados (`colors.md`).
- Um `h1` por página; landmarks únicos ou nomeados (`aria-label`).
- Formulários: rótulo associado, erro com `aria-describedby`, `aria-invalid`.
- Diálogos: nativos, com nome, foco gerenciado.
- Alvos ≥ 24px (44px no celular).
- Catraca: `tests/a11y/baseline.json` só diminui.
