# Cores

**Hoje** (`ds-v32.css :root`, espelhado em `tokens/colors.json`):

- Neutros `--n-950…--n-25` (16 tons), dourado `--d-900…--d-50` (11 tons), base `--branco`, `--papel`, `--grafite`.
- Estados: `ok` (sucesso), `wn` (aviso), `dg` (perigo), `in` (informação), `nt` (neutro), cada um com texto (`-t`), fundo (`-b`) e borda (`-r`).
- Semânticos: `--acento`, `--link`, `--foco`, `--sel-*`, `--hover-b`, `--rotulo`.
- 205 cores literais em `design-system.css`, 118 no bridge, 76 no ds-v32 (fora das definições de token).

**Contraste medido** (`reports/design/contrast.md`): `--n-400` 3,78:1 e `--n-450`/`--rotulo` 4,29:1 sobre papel —
**reprovam** texto pequeno; `--d-500` 2,33:1. Pares de status (texto sobre fundo) passam AA.
Duplicatas: `--d-500 = --d-600`, `--d-400 = --d-550`.

**Regra v4**
- Texto normal: `neutral.600` ou mais escuro. Rótulos de 11–12px: `neutral.600` (substitui 450/400).
- Link e acento em texto: `gold.700`. `gold.500` só para superfícies, bordas decorativas e ícones decorativos.
- Anel de foco: `color.semantic.focus-ring` (proposto: `gold.700`, ≥ 3:1).
- Status sempre em trio texto/fundo/borda do mesmo estado; nunca só cor — acompanhar ícone ou texto.
- Remover as duplicatas de dourado; toda cor nova nasce em `tokens/colors.json`.
