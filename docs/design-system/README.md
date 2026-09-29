# Design System

Documenta **o que existe** (DS V3.2 em `static/css/ds-v32.css` + `ds-v32-bridge.css`, V2 em `design-system.css`)
e **o que deve valer** no DS v4 (tokens em `tokens/*.json`). A paleta atual não é tratada como definitiva.

Cada página tem três partes: **Hoje** (medido), **Avaliação** e **Regra v4**.

| Fundamentos | Componentes | Padrões |
|---|---|---|
| [principles](principles.md) · [visual-language](visual-language.md) · [colors](colors.md) · [typography](typography.md) · [spacing](spacing.md) · [sizing](sizing.md) · [radius](radius.md) · [shadows](shadows.md) · [elevation](elevation.md) · [motion](motion.md) · [icons](icons.md) | [buttons](buttons.md) · [forms](forms.md) · [tables](tables.md) · [dialogs](dialogs.md) · [navigation](navigation.md) · [filters](filters.md) · [status](status.md) | [page-archetypes](page-archetypes.md) · [responsive](responsive.md) · [accessibility](accessibility.md) · [anti-patterns](anti-patterns.md) |

Ferramentas: UI Lab em `/_lab/` · `npm run agent:inventory` (tokens/estilos/duplicação) ·
`python scripts/agent/build_tokens.py` (tokens → CSS + contraste em `reports/design/contrast.md`).
Referência histórica aprovada pelo usuário: `docs/design-import/` (pilotos HTML do V3.x).
