import { test, expect } from "../support/lab";
import { KEY_PAGES } from "../support/pages";

test("sonda do laboratório: banco ok, sem migração pendente, seed presente", async ({ request }) => {
  const r = await request.get("/_lab/health/");
  expect(r.status()).toBe(200);
  const body = await r.json();
  expect(body.db_ok).toBe(true);
  expect(body.pending_migrations).toEqual([]);
  expect(body.seed.lab_users).toBeGreaterThanOrEqual(9);
  expect(body.server_now?.startsWith("2026-09-15")).toBe(true);
});

test("login renderiza sem erro de console", async ({ page, signals }) => {
  await page.goto("/conta/entrar/");
  await expect(page.getByLabel("Usuário")).toBeVisible();
  expect(signals.pageErrors).toEqual([]);
  expect(signals.serverErrors).toEqual([]);
});

for (const p of KEY_PAGES.filter((k) => k.archetype !== "ERROR" && k.id !== "login")) {
  test(`página-chave abre: ${p.id} (${p.role})`, async ({ asRole }) => {
    const page = await asRole(p.role);
    const erros: string[] = [];
    page.on("pageerror", (e) => erros.push(e.message));
    const resp = await page.goto(p.path);
    expect(resp?.status(), `${p.path} respondeu ${resp?.status()}`).toBeLessThan(400);
    await expect(page.locator("h1").first()).toBeVisible();
    expect(erros, "exceção JS na página").toEqual([]);
  });
}
