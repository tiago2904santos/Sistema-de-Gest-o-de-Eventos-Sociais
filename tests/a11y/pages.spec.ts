import { test, expect, evidence } from "../support/lab";
import { runAxe } from "../support/a11y";
import { KEY_PAGES } from "../support/pages";
import { existsSync, readFileSync } from "node:fs";

/**
 * Axe em cada página-chave. Relatório por página em reports/accessibility/<id>.json
 * e resumo em reports/accessibility/summary.md (gerado no afterAll).
 *
 * Portão em catraca: a dívida registrada em tests/a11y/baseline.json é tolerada,
 * mas nenhuma página pode PIORAR (mais violações critical/serious que o baseline).
 * Página nova, sem baseline, precisa nascer sem critical. Quando uma correção
 * reduzir a dívida, aperte a catraca: npm run test:a11y && node tests/tools/summarize.mjs a11y --update-baseline
 */
const BASELINE_FILE = "tests/a11y/baseline.json";
const baseline: Record<string, { critical: number; serious: number }> = existsSync(BASELINE_FILE)
  ? JSON.parse(readFileSync(BASELINE_FILE, "utf-8"))
  : {};

for (const p of KEY_PAGES) {
  test(`axe: ${p.id}`, async ({ asRole }, testInfo) => {
    const page = await asRole(p.role);
    await page.goto(p.path);
    await page.waitForLoadState("networkidle").catch(() => {});
    const r = await runAxe(page);
    await evidence(testInfo, "accessibility", p.id, { page: p, ...r });
    const teto = baseline[p.id] ?? { critical: 0, serious: Number.POSITIVE_INFINITY };
    const regras = (imp: string) => r.violations.filter((v) => v.impact === imp).map((v) => v.id).join(", ");
    expect.soft(r.counts.critical, `critical em ${p.id} acima do baseline (${teto.critical}): ${regras("critical")}`).toBeLessThanOrEqual(teto.critical);
    expect.soft(r.counts.serious, `serious em ${p.id} acima do baseline (${teto.serious}): ${regras("serious")}`).toBeLessThanOrEqual(teto.serious);
  });
}
