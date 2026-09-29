import { test, expect, stabilize, evidence } from "../support/lab";
import { layoutIssues } from "../support/layout";
import { KEY_PAGES } from "../support/pages";
import { VIEWPORTS, type ViewportName } from "../support/viewports";
import { existsSync, readFileSync } from "node:fs";

/**
 * Cada página-chave em cada viewport: captura + varredura de layout
 * (overflow horizontal, elemento vazando, texto cortado, alvo de toque < 24px).
 * Evidências em reports/responsive/<pagina>/<viewport>.{png,json}.
 *
 * Portão em catraca: overflow horizontal da página (o bug de layout mais caro no
 * celular) só é tolerado nas combinações página@viewport já registradas em
 * tests/responsive/baseline.json. Combinação nova com overflow = regressão.
 * Depois de corrigir: node tests/tools/summarize.mjs responsive --update-baseline
 */
const BASELINE: string[] = existsSync("tests/responsive/baseline.json")
  ? JSON.parse(readFileSync("tests/responsive/baseline.json", "utf-8")).overflow
  : [];
const PAGES = KEY_PAGES.filter((p) => !["erro-404"].includes(p.id));

for (const p of PAGES) {
  for (const vp of Object.keys(VIEWPORTS) as ViewportName[]) {
    test(`${p.id} @ ${vp}`, async ({ asRole }, testInfo) => {
      const page = await asRole(p.role);
      await page.setViewportSize(VIEWPORTS[vp]);
      await page.goto(p.path);
      await page.waitForLoadState("networkidle").catch(() => {});
      await stabilize(page);
      const issues = await layoutIssues(page);
      await evidence(testInfo, `responsive/${p.id}`, vp, { page: p.id, viewport: VIEWPORTS[vp], issues });
      await evidence(testInfo, `responsive/${p.id}`, vp, await page.screenshot({ fullPage: true }));
      const overflow = issues.filter((i) => i.kind === "page-overflow-x");
      const chave = `${p.id}@${vp}`;
      if (BASELINE.includes(chave)) {
        if (!overflow.length) testInfo.annotations.push({ type: "melhorou", description: `${chave} não transborda mais — aperte o baseline` });
      } else {
        expect.soft(overflow, `overflow horizontal novo em ${chave}`).toEqual([]);
      }
    });
  }
}
