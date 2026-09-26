# Inventário de valores CSS (Fase 0, 26/09/2026)

Levantamento feito antes de qualquer mudança, com um parser próprio sobre
`static/css/*.css`. Contagens por declaração; `padding:10px 14px` conta 2.
Cores normalizadas (`#fff`, `#ffffff` e `white` contam como uma).

## 0. Achados que pedem atenção primeiro

1. **Seletor quebrado no bridge, linhas 62–63.** `.fc[data-ativo] ` seguido de
   quebra de linha e `.chips-v32{…}` vira `.fc[data-ativo] .chips-v32`, uma
   regra morta. `.chips-v32` não aparece em nenhum template.
2. **Os tokens de `pdf-place.css` não existem** (`--space-1/2/3`, `--text-muted`,
   `--font-size-sm`, `--surface-rail`, `--radius-field`, `--paper`,
   `--shadow-soft`, `--accent`, `--paper-ink`, `--surface(-contrast)`,
   `--text-strong`), sem valor reserva. O arquivo é carregado em
   `viagens_prestacoes/carimbo_ajustar.html`.
3. **Contradição sobre o foco.** Bridge 1685: `*:focus,*:focus-visible{outline:none}`
   ("Nada de foco em lugar nenhum"). Mesmo assim 7 regras desenham
   `outline:2px solid var(--foco…)` (1938, 2048, 2157, 2330, 2355, 2368, 2901) e
   3 anéis `box-shadow:0 0 0 3px var(--d-200)` (2679, 2687, 2732). Como `--foco`
   é `--d-100`, esse contorno fica quase invisível.
4. **`#96762f` não existe em CSS nenhum** (só num comentário). Dourados escuros
   crus ainda existem: 7 em `ds-v32`, 4 no bridge, 1 em `design-system`. O bridge
   usa 30 vezes os tokens de dourado escuro (`--d-700`, `--d-800`, `--link`,
   `--marcado`).
5. **Valores reserva do bridge não batem com os tokens**: `var(--d-400,#bea45a)`
   (real #c9b06d), `var(--n-300,#cfccc5)` (real #a6a8aa), `var(--foco,#2d6fd6)`
   (azul!), `var(--n-900,#111)`, `var(--n-950,#1a1917)`.
6. **`--erro-t`, `--n-0`, `--av-t`, `--av-b` não existem**; caem nos reservas crus
   #b3261e, #fff, #6b4e10/#b7791f, #fdf3dc. Equivalentes: `--dg-t`, `--branco`,
   `--wn-t`, `--wn-b`.

## A. `ds-v32-bridge.css` — 2914 linhas, ~2412 blocos, 6607 declarações

### A1. Tokens
- **Sem `:root`.** Só 14 propriedades locais: `--reg-py`/`--reg-px` (1483–1485,
  1590, 1598 — a 1598 usa 18px em vez de 20px) e `--rotulo-fundo` (1882, 1883,
  2118, 2119).
- Usados sem definição: `--av-b`, `--av-t`, `--erro-t`, `--n-0`. (Definidos por
  JS/template e corretos: `--colunas`, `--equipes`, `--w/--x/--y/--h`.)
- Tokens mais usados: `--n-500` 115, `--n-900` 104, `--branco` 90, `--n-150` 82,
  `--n-200` 72, `--n-600` 58, `--n-800` 54, `--n-50` 41, `--n-450` 39, `--n-700` 37,
  `--n-100` 35, `--ok-t`/`--dg-t` 32, `--motion` 26, `--n-25` 26, `--n-400` 24,
  `--grafite` 21.
- A escala `--s*` quase não é usada: `--s1` 1, `--s2` 5, `--s3` 4, `--s4` 9,
  `--s5` 3, `--s6` 3.

### A2. Cores cruas — 111 ocorrências, 59 valores (48 como reserva em `var()`)
| Valor | Qtd | Onde | Observação |
|---|---|---|---|
| #fff | 15 | 165, 397, 418, 1025, 1134, 1275, 1811, 2617, 2630, 2902, 2914 | → `--branco` |
| #e3e1dc | 5 | reserva de `--n-200` | real #e1e2e3 |
| #7a776f | 5 | reserva de `--n-500` | real #6e6e6e |
| #faf9f7 | 4 | reserva de `--n-50` | |
| #6b4e10 | 3 | reserva de `--av-t` (2288, 2761, 2793) | dourado escuro |
| #bea45a | 3 | reserva de `--d-400` (2470, 2471) | |
| #b3261e | 2 | reserva de `--erro-t` (1790, 1794) | → `--dg-t` |
| #f4f4f4 | 2 | `.marca__sigla`, `.marca__titulo` (2302, 2305) | sem token |
| #f7d9d4 / #8a2d1f | 2+2 | `.cb-st--vencida` (2622, 2623) | ≈ `--dg-r`/`--dg-t` |
| #cfcfcf | 1 | `.marca__sub` 2306 | |
| #4d3703 | 1 | `.pc-pendencias li` 1332 | dourado escuro cru |
| #000 | 4 | máscaras SVG (796, 1398) | ok |
| rgba(26,25,23,α) | 23 | sombras e véus, 17 opacidades | sem token |
| rgba(0,0,0,α) | 6 | 2617, 2630, 2774, 2914 | |
| rgba(20,24,30,.72), rgba(10,14,20,.7) | 1+1 | `.pc-imp__lupa`, `.pc-zoom::backdrop` | preto azulado |

Dourado escuro por token: `--d-700` 12 usos, `--d-800` 6, `--link` 8, `--marcado` 5.

### A3. `border-radius` — 218 declarações, 20 valores
8px 38 · 9px 27 · 10px 26 · 12px 20 · 7px 16 · 99px 14 · 4px 14 · 6px 13 · 0 13 ·
5px 11 · 50% 8 · 999px 5 · 3px 4 · `11px 11px 0 0` 3 · 14px 1 (`.an-dialogo`) ·
20px 1 (interruptor) · outros 1.
Círculos em três grafias (99px, 999px, 50%). Botões e campos oscilam entre
5, 6, 7 e 8px. Modais em 10, 12 e 14px.

### A4. `box-shadow` — 62 declarações, 36 valores
Menus e listas suspensas com 5 sombras diferentes (175, 193, 1539, 1540, 1943,
1981, 379). Modais: `.an-dialogo` 0 24px 60px -12px .35; `.catalogo-paridade__dialog`
0 16px 48px #0003; agenda 0 24px 64px .28. Foco: 0 0 0 3px `--d-200` ×3.
Toast: 0 12px 30px rgba(0,0,0,.25).

### A5. Espaçamento
- padding: 605 valores, 36 distintos. Fora da escala de 4: 2, 3, 5, 6, 7, 9, 10,
  11, 13, 14, 15, 18, 22, 30, 34, 38, 42px.
- margin: 691 valores, 31 distintos (inclui −30, −20, −16, −12, −8, −6, −4, −2).
- gap: 438 valores, 19 distintos; 8px 86, 10px 69, 6px 67, 12px 67.
- Tokens: 49 usos contra ~1650 valores crus. A prática real é uma grade de 2px.

### A6. Tipografia
- font-size: 370 declarações, 24 valores; 12.5px 74, 13px 68, 12px 59, 11px 35,
  11.5px 31, 13.5px 31, 10.5px 16, 14px 9, 15px 9, 10px 6, 16px 5, 26px 5, 22px 4,
  20px 3, 28px 3; 1× 8px, 9px, 18px, 21px, 64px. 168 declarações em meio pixel.
- font-weight: 600 106, 700 28, 500 25, 400 17, **650** 1 (2305), **800** 1 (1039).
- line-height: 17 valores (1.5 11, 1.6 10, 1.45 7, 1 6, 1.3 5, 1.4 5…).

### A7–A8. Alturas e z-index
- `.btn-primaria` 44→36 (1458); `.form-controle` 38 (120); cabeçalho numerado
  min-height 56 repetido 3× (1486, 1591, 1599); `.app-v32 .ident__in` 88/68.
- z-index: 0 mapa/trilho · 1–5 sticky, ícones, arraste · 20 `.reg` com lista
  aberta · 30 `.btn-flutuante` · 40 ações fixas · 60 select/calendário/gaveta/toast
  · 61–63 select aberto · 500/600 mapa · 900/950 calendário múltiplo.

### A9. `!important` — 25 em 22 linhas
Necessários: 204 `.coluna-oculta`, 1366/1367 arraste, 1956 e 2675 `[hidden]`,
2344/2377 reduced-motion, 125 estado de erro (justificável), 308/730 esconder no
celular (plausível). Dispensáveis com especificidade: 69, 74, 89, 90, 946, 1202,
1203, 1376, 1377, 1994, 2423.

### A10. Breakpoints
`@container 680` 37 · `900` 17 · `1100` 7 · `560` 4 · `760` 1 · min 681/901/1101
1 cada · `@media 680` 4 · `720` 2 · 1000/900/760/600 1 cada · reduced-motion 8.

### A11. Organização
Cronológica e por pedido (Metas 2–6, datas, C1–C3, E2), não por componente.
`custom-select` volta em 6 pontos; `custom-date` em 7; `.btn-primaria` em 3;
cabeçalho numerado em 4.

## B. `ds-v32.css` — 1025 linhas (não editar)
- `:root` (6–27): neutros `--n-950…--n-25`, `--branco`, `--papel`, `--grafite`;
  dourados `--d-900…--d-50`; estados `--ok/--wn/--dg/--in/--nt` (t/b/r); `--f`;
  espaço `--s1…--s10`; `--pad` 48, `--linha-y` 13, `--cabeca-y` 28, `--larg` 1440,
  `--ctrl-h` 44; semânticos `--acento`, `--acento-num`, `--foco`, `--sel-b/r/f`,
  `--hover-b`, `--link`, `--marcado`, `--rotulo`; `--motion`.
- Iguais: `--d-600`=`--d-500`, `--d-550`=`--d-400`, `--grafite`=`--n-900`,
  `--nt-*`=`--n-600/100/250`, `--link`=`--marcado`. Nunca usados: `--d-550`, `--s8`.
- 76 cores cruas; dourados escuros crus: #a8822a ×2, #3d3009, #6b4d05, #5c4204,
  #4d3703, #8a6a1c, #8a7434. `.m-seletor` (427) crava "Segoe UI".
- Raios: `.btn-primaria` 8, `.btn--secundaria` 7, `.btn--quieta` 5, `.fc`/`.busca`/`.ib`
  8, `.ctrl` 7, `.reg`/`.mo` 12, `.painel`/`.fpanel` 10, `.chip` 6, `.st` 5, `.dd__c` 8.
- z-index: 1 · 20 `.gr__t` · 40 `.dd__c` · 50 `.frm-flut` · 60 tip/drawer · 100 véus
  · 101 sheet · 110 toast · 120 `.m-seletor`.

## C. `design-system.css` — 4130 linhas (legado)
- Tokens `--cor-*`, `--esp-*`, `--texto-*`, `--raio-*`, `--sombra-*`. Conflitos com
  o V3.2 (erro #b3261e vs #a32b22; sucesso #1e7e46 vs #1c7040; info #175d9c vs
  #17548a). 204 cores cruas, 91 distintas. 29 breakpoints, 15 larguras.
- **Só `layouts/auth.html` e as 5 páginas de autenticação carregam o arquivo**
  (`alterar_senha.html` já é V3.2). Classes usadas por elas: `auth-shell*`,
  `top-header*`, `menu-usuario*`, `auth-card*`, `auth-alerta*`, `alerta`, `btn`,
  `btn--bloco`, `btn--dourado`, `btn--secundario`, `form-campo`, `form-label`,
  `form-controle`, `form-erro`, `form-check`, `campo-com-icone*`, `campo-senha*`,
  `ui-icon`. **~107 regras (11,5%) servem a algo; ~821 (88,5%) estão mortas.**

## D. Arquivos de módulo
| Arquivo | Linhas | Observação |
|---|---|---|
| viagens-cadastros | 322 | usa **só tokens do legado** (`--cor-*`, `--esp-*`, `--texto-*`: 118 usos), que não existem no shell V3.2 |
| viagens-planos | 154 | tokens V3.2; 1 `!important` necessário |
| viagens-viagem | 74 | tokens V3.2; `.vg-fab` z 30 |
| viagens-ordens | 62 | tokens V3.2 |
| viagens-documentos | 11 | `--surface`/`--border` inexistentes |
| viagens-prestacoes | 2 | `--cor-primaria` do legado |
| agenda | 200 | `:root` próprio com `--ag-*` e `--fc-*`; font-size em rem (17 valores) |
| pdf-place | 113 | 17 tokens inexistentes; Helvetica/Arial |
| pages/viagens-documento | 189 | fora do levantamento inicial |
| pages/viagens-configuracoes | 17 | fora do levantamento inicial |

## E. Consolidado
- **Três vocabulários de token**: V3.2 (`--n/--d/--s`), legado (`--cor/--esp/--texto/--raio`)
  e um inexistente (`--space/--surface/--text/--paper`).
- **Cores da paleta cruas**: #fff 84×, #bea45a 32×, #d1d3d4 5×, #333 3×.
  rgba(26,25,23,α) 41× em 21 opacidades, sem token.
- **Raios por função**: botão 8→7; campo 7/8/9; cartão 8/9/10/12; modal 10/12/14;
  círculo 50%/99px/999px.
- **Sombra**: nenhum token no V3.2; 5 variantes de menu, 3 de modal, 2 de toast.
- **Alturas por função** (E7): botão primário 36/38/40/44/46; secundário
  36/38/40/44/46 (na mesma barra `.v32-barra`, primário 36 e secundário 38);
  botão de ícone 28/32/34/38/44; botão de limpar 22/24/26; campo
  26/30/32/34/36/38/44/46; stepper 28/36/40; linha de lista 46/47/48/52/56;
  cabeçalho de cartão 34/38/46/56; calendário botões 30/34.
- **Breakpoints**: 680 (44×) e 900 (23×) dominam; 1100 10×; 760 9×; e uma cauda
  de 720, 1000, 560, 640, 767, 600, 700, 820, 980, 1024, 1080, 1180, 1400.
- **`!important`**: 33 no total; ~12 necessários, ~10 dispensáveis no bridge.
- **Pilha de z-index** consolidada: 0 mapa · 1–5 detalhes · 20 cartão com lista
  aberta · 30 flutuante · 40 menus `.dd__c` · 50 `.frm-flut` · 60 select/calendário
  · 61–63 select aberto · 100–101 véus · 110 toast · 120 `.m-seletor` · 500/600
  mapa (contido por `isolation`) · 900/950 calendário múltiplo. Sem cabeçalho fixo.
