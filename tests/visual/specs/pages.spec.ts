import { test, expect, stabilize } from "../../support/lab";
import { KEY_PAGES } from "../../support/pages";

/**
 * Regressão visual de páginas inteiras, com o seed `normal` e o relógio ancorado.
 * Máscaras cobrem o que muda sozinho (token CSRF não aparece; horários "agora" sim).
 */
for (const p of KEY_PAGES) {
  test(`página: ${p.id}`, async ({ asRole }) => {
    const page = await asRole(p.role);
    await page.goto(p.path);
    await page.waitForLoadState("networkidle").catch(() => {});
    await stabilize(page);
    await expect.soft(page).toHaveScreenshot(`${p.id}.png`, {
      fullPage: true,
      mask: [page.locator("[data-agora], time[data-relativo], .fc-timegrid-now-indicator-line")],
    });
  });
}
