import { test, expect } from "../support/lab";

test("anônimo é mandado ao login ao abrir módulo protegido", async ({ page }) => {
  await page.goto("/viagens/oficios/");
  await expect(page).toHaveURL(/\/conta\/entrar\//);
});

test("usuário sem o módulo recebe 403 próprio (PERMISSION_DENIED)", async ({ asRole }) => {
  const page = await asRole("semModulo");
  const resp = await page.goto("/viagens/oficios/");
  expect(resp?.status()).toBe(403);
  await expect(page.locator("body")).toContainText(/acesso|permiss/i);
});

test("leitor de viagens enxerga a lista de ofícios", async ({ asRole }) => {
  const page = await asRole("viagensLeitor");
  const resp = await page.goto("/viagens/oficios/");
  expect(resp?.status()).toBe(200);
});
