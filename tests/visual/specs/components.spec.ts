import { test, expect, stabilize } from "../../support/lab";

/**
 * Regressão visual por componente: cada espécime do UI Lab (/_lab/specimens.json)
 * vira uma captura. Estados de interação (hover/focus/active) são aplicados aqui.
 * Baselines em tests/visual/snapshots/; diffs em reports/testing/artifacts/.
 * Atualizar baseline (depois de revisar a mudança!): npm run test:visual:update
 */
type Spec = { id: string; state: string; interact: string };

test("catálogo de espécimes responde", async ({ request }) => {
  const r = await request.get("/_lab/specimens.json");
  expect(r.ok()).toBeTruthy();
  expect((await r.json()).specimens.length).toBeGreaterThan(20);
});

test.describe("espécimes", () => {
  test("todos os espécimes renderizam e batem com o baseline", async ({ page, request }) => {
    test.setTimeout(5 * 60_000);
    const { specimens } = (await (await request.get("/_lab/specimens.json")).json()) as { specimens: Spec[] };
    for (const s of specimens.filter((x) => !x.id.startsWith("icon-"))) {
      await page.goto(`/_lab/c/${s.id}/`);
      await expect(page.locator("[data-error]"), `espécime ${s.id} quebrou`).toHaveCount(0);
      await stabilize(page);
      const alvo = page.locator("#alvo");
      if (await alvo.evaluate((e) => !e.innerHTML.trim())) {
        // Componente que não renderiza nada neste estado (ex.: paginação de uma página só).
        expect.soft(s.state, `${s.id} saiu vazio fora do estado "empty"`).toBe("empty");
        continue;
      }
      if (s.interact) {
        const el = alvo.locator(s.interact).first();
        if (s.state === "hover") await el.hover();
        if (s.state === "focus") { await page.keyboard.press("Tab"); await el.focus(); }
      }
      await expect.soft(alvo).toHaveScreenshot(`${s.id}.png`);
    }
  });

  test("ícones (grade)", async ({ page }) => {
    await page.goto("/_lab/");
    await stabilize(page);
    await expect.soft(page.locator(".lab-icons")).toHaveScreenshot("icons-grid.png");
  });
});
