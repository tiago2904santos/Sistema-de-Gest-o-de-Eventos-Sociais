# Ciclo de revisão de design

```text
AUDIT → FINDINGS → PLAN → IMPLEMENT → TEST → SCREENSHOT → COMPARE → FIX → VERIFY
```

1. **AUDIT** — `audit-page.mjs --label antes` nas páginas afetadas (todas as viewports relevantes).
2. **FINDINGS** — ler `findings.json`; separar o que a mudança resolve do que fica.
3. **PLAN** — mudanças mínimas, com tokens/componentes do DS; registrar decisão se houver trade-off.
4. **IMPLEMENT** — checkpoint git antes.
5. **TEST** — `manage.py test <apps>` + `npm run test:smoke test:e2e`.
6. **SCREENSHOT** — `audit-page.mjs --label depois`.
7. **COMPARE** — `visual-compare.mjs antes depois`; olhar os `diff.png`.
8. **FIX** — se qualquer métrica crítica piorou (novo P0/P1, mais axe critical/serious, overflow novo, LCP muito pior), corrigir **ou reverter**.
9. **VERIFY** — `npm run test:a11y test:responsive test:visual`; atualizar baseline só do que mudou de propósito; commit com evidência citada.
