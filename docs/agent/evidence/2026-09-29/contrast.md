# Contraste dos tokens de cor (WCAG 2.x)

Texto normal exige 4,5:1; texto grande (≥ 18,66px negrito ou 24px) e componentes de interface, 3:1.

| Token | Cor | sobre papel | sobre branco | AA texto |
|---|---|---|---|---|
| `color.base.graphite` | `#333333` | 12.10 | 12.63 | ✅ |
| `color.base.paper` | `#fafafa` | 1.00 | 1.04 | ❌ |
| `color.base.white` | `#fff` | 1.04 | 1.00 | ❌ |
| `color.gold.100` | `#f5eed9` | 1.11 | 1.16 | ❌ |
| `color.gold.200` | `#ebe0c4` | 1.26 | 1.31 | ❌ |
| `color.gold.300` | `#ddd0ab` | 1.47 | 1.53 | ❌ |
| `color.gold.400` | `#c9b06d` | 2.03 | 2.12 | ❌ |
| `color.gold.50` | `#faf7ef` | 1.03 | 1.07 | ❌ |
| `color.gold.500` | `#bea45a` | 2.33 | 2.43 | ❌ |
| `color.gold.550` | `#c9b06d` | 2.03 | 2.12 | ❌ |
| `color.gold.600` | `#bea45a` | 2.33 | 2.43 | ❌ |
| `color.gold.700` | `#7d6626` | 5.29 | 5.53 | ✅ |
| `color.gold.800` | `#6d5926` | 6.48 | 6.76 | ✅ |
| `color.gold.900` | `#5c4a1c` | 8.21 | 8.57 | ✅ |
| `color.neutral.100` | `#eff0f0` | 1.09 | 1.14 | ❌ |
| `color.neutral.150` | `#e9eaeb` | 1.15 | 1.20 | ❌ |
| `color.neutral.200` | `#e1e2e3` | 1.24 | 1.30 | ❌ |
| `color.neutral.25` | `#fbfbfb` | 1.01 | 1.03 | ❌ |
| `color.neutral.250` | `#d1d3d4` | 1.44 | 1.50 | ❌ |
| `color.neutral.300` | `#a6a8aa` | 2.29 | 2.39 | ❌ |
| `color.neutral.400` | `#808080` | 3.78 | 3.95 | ⚠️ só grande/UI |
| `color.neutral.450` | `#777777` | 4.29 | 4.48 | ⚠️ só grande/UI |
| `color.neutral.50` | `#f7f8f8` | 1.02 | 1.06 | ❌ |
| `color.neutral.500` | `#6e6e6e` | 4.89 | 5.10 | ✅ |
| `color.neutral.600` | `#5e5e5e` | 6.21 | 6.48 | ✅ |
| `color.neutral.700` | `#4d4d4d` | 8.10 | 8.45 | ✅ |
| `color.neutral.75` | `#f3f4f4` | 1.06 | 1.10 | ❌ |
| `color.neutral.800` | `#3f3f3f` | 10.09 | 10.53 | ✅ |
| `color.neutral.900` | `#333333` | 12.10 | 12.63 | ✅ |
| `color.neutral.950` | `#262626` | 14.50 | 15.13 | ✅ |
| `color.semantic.accent` | `#bea45a` | 2.33 | 2.43 | ❌ |
| `color.semantic.focus-bg` | `#f5eed9` | 1.11 | 1.16 | ❌ |
| `color.semantic.focus-ring` | `#7d6626` | 5.29 | 5.53 | ✅ |
| `color.semantic.hover-bg` | `#eff0f0` | 1.09 | 1.14 | ❌ |
| `color.semantic.label` | `#777777` | 4.29 | 4.48 | ⚠️ só grande/UI |
| `color.semantic.link` | `#7d6626` | 5.29 | 5.53 | ✅ |
| `color.semantic.selected-bg` | `#faf7ef` | 1.03 | 1.07 | ❌ |
| `color.semantic.selected-border` | `#c9b06d` | 2.03 | 2.12 | ❌ |
| `color.semantic.text` | `#4d4d4d` | 8.10 | 8.45 | ✅ |
| `color.semantic.text-muted` | `#5e5e5e` | 6.21 | 6.48 | ✅ |
| `color.semantic.text-strong` | `#333333` | 12.10 | 12.63 | ✅ |
| `color.status.danger.text` | `#a32b22` | 6.88 | 7.18 | ✅ |
| `color.status.info.text` | `#17548a` | 7.53 | 7.86 | ✅ |
| `color.status.neutral.text` | `#5e5e5e` | 6.21 | 6.48 | ✅ |
| `color.status.success.text` | `#1c7040` | 5.85 | 6.10 | ✅ |
| `color.status.warning.text` | `#7d5a00` | 6.03 | 6.30 | ✅ |
| `status.success.text` sobre `status.success.bg` | `#1c7040`/`#e9f2ec` | 5.34 | — | ✅ |
| `status.warning.text` sobre `status.warning.bg` | `#7d5a00`/`#fdf3dd` | 5.71 | — | ✅ |
| `status.danger.text` sobre `status.danger.bg` | `#a32b22`/`#fdeeec` | 6.36 | — | ✅ |
| `status.info.text` sobre `status.info.bg` | `#17548a`/`#eaf1f8` | 6.90 | — | ✅ |
| `status.neutral.text` sobre `status.neutral.bg` | `#5e5e5e`/`#eff0f0` | 5.68 | — | ✅ |
