# Responsividade

**Hoje**: 18 breakpoints distintos em `@media` (560–1400px; mais usados 900, 760, 720, 680, 1000). Listas viram Data List no celular.

**Medido** (`reports/responsive/summary.md`, 20 páginas × 6 viewports): overflow horizontal em 40 combinações
(navegação de Viagens; agenda, dashboard e prestações no celular).

**Regra v4**: breakpoints `sm 640 · md 768 · lg 1024 · xl 1280 · 2xl 1440`; mobile-first; nenhuma página com rolagem
horizontal (tabelas rolam dentro do próprio contêiner); viewports de teste em `tests/support/viewports.ts`
(1440×900, 1280×800, 1024×1366, 768×1024, 390×844, 360×800).
