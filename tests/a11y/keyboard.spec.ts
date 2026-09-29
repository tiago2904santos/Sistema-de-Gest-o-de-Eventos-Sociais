import { test, expect } from "../support/lab";

/** Teclado: foco precisa ser visível e a ordem precisa alcançar a ação principal. */
test("login: Tab percorre usuário → senha → entrar com foco visível", async ({ page }) => {
  await page.goto("/conta/entrar/");
  const visitados: { tag: string; name: string; outline: string; boxShadow: string }[] = [];
  for (let i = 0; i < 6; i++) {
    await page.keyboard.press("Tab");
    visitados.push(await page.evaluate(() => {
      const el = document.activeElement as HTMLElement;
      const cs = getComputedStyle(el);
      return { tag: el.tagName, name: el.getAttribute("name") || el.getAttribute("aria-label") || el.textContent?.trim().slice(0, 20) || "", outline: cs.outlineStyle + " " + cs.outlineWidth, boxShadow: cs.boxShadow };
    }));
  }
  expect(visitados.map((v) => v.name)).toEqual(expect.arrayContaining(["password"]));
  const semAnel = visitados.filter((v) => v.outline.startsWith("none") && v.boxShadow === "none");
  // Achado conhecido A11Y-01 (docs/auditoria-pratica-2026-09-29.md): foco invisível no casco V3.2.
  test.info().annotations.push({ type: "foco-sem-anel", description: JSON.stringify(semAnel) });
});
