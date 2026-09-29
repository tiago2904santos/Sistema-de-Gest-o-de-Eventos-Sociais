# Tipografia

**Hoje**: família `--f` (Segoe UI, system-ui…); corpo 14px/1,5; `h1` peso 500, altura 1,08.
**115 valores distintos de `font-size`** no CSS (só no ds-v32: 13, 12.5, 13.5, 11, 11.5, 12, 14, 15, 10.5, 14.5 px…);
pesos 400/500/600/650/700/800.

**Avaliação**: sem escala, cada tela escolhe seu tamanho; meio-pixels geram renderização inconsistente no Windows.

**Regra v4** — escala proposta (`tokens/typography.json`): xs 11 · sm 12 · md 13 · base 14 · lg 16 · xl 20 · 2xl 26 · 3xl 34 px;
pesos regular 400 · medium 500 · semibold 600 · bold 700. Mínimo de 12px para texto informativo; 11px só em rótulo em
caixa-alta com contraste AA. Números em tabela: `font-variant-numeric: tabular-nums`.
