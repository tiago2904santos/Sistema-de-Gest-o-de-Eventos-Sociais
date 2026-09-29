import { test, expect } from "../support/lab";

/**
 * Regressões: um teste por bug corrigido (nunca volta) e, para bugs conhecidos
 * ainda abertos, `test.fail()` — o teste documenta o defeito e passa a acusar
 * quando alguém o corrigir (aí troca-se fail → teste normal).
 * Fonte dos achados: docs/auditoria-pratica-2026-09-29.md.
 */

test("BUG-03: 404 próprio, com identidade e caminho de volta", async ({ asRole }) => {
  const page = await asRole("admin");
  // Com DEBUG o Django mostra a página técnica; a prévia do lab usa o handler real.
  const resp = await page.goto("/_lab/erro/404/");
  expect(resp?.status()).toBe(404);
  await expect(page.locator("a[href='/']").first()).toBeVisible();
  const r500 = await page.goto("/_lab/erro/500/");
  expect(r500?.status()).toBe(500);
  await expect(page.locator("body")).not.toContainText("Traceback");
});

test("A11Y-01: foco do teclado visível nos links do casco", async ({ asRole }) => {
  test.fail(true, "Aberto: ds-v32.css zera :focus-visible globalmente (auditoria 29/09, A11Y-01).");
  const page = await asRole("admin");
  await page.goto("/");
  await page.keyboard.press("Tab");
  const anel = await page.evaluate(() => {
    const cs = getComputedStyle(document.activeElement as Element);
    return cs.outlineStyle !== "none" || cs.boxShadow !== "none";
  });
  expect(anel).toBe(true);
});

test("tokens: pdf-place.css não usa custom properties inexistentes", async ({ asRole }) => {
  test.fail(true, "Aberto: pdf-place.css referencia --space-*, --text-muted, --radius-field… de um DS antigo (auditoria estática).");
  const page = await asRole("admin");
  await page.goto("/_lab/");
  const indefinidos = await page.evaluate(() => {
    const nomes = ["--space-1", "--text-muted", "--radius-field", "--surface", "--shadow-soft"];
    const cs = getComputedStyle(document.documentElement);
    return nomes.filter((n) => !cs.getPropertyValue(n).trim());
  });
  expect(indefinidos).toEqual([]);
});
