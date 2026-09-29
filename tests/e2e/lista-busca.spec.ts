import { test, expect } from "../support/lab";

/** Interação real numa lista: busca por texto e volta ao total. */
test("lista de ofícios: buscar filtra e limpar restaura", async ({ asRole }) => {
  const page = await asRole("viagensGestor");
  await page.goto("/viagens/oficios/");
  const busca = page.getByRole("searchbox").or(page.locator("input[name=q]")).first();
  await expect(busca).toBeVisible();
  const linhasAntes = await page.locator("table tbody tr, [data-lista] li, .lista-registros__item").count();
  await busca.fill("termo-que-nao-existe-xyz");
  await busca.press("Enter");
  await page.waitForLoadState("domcontentloaded");
  await expect(page.locator("body")).toContainText(/Nenhum|nenhum|não encontr/);
  await page.goto("/viagens/oficios/");
  const linhasDepois = await page.locator("table tbody tr, [data-lista] li, .lista-registros__item").count();
  expect(linhasDepois).toBe(linhasAntes);
});

test("estado de erro de rede: falha de XHR não derruba a página", async ({ asRole }) => {
  const page = await asRole("admin");
  const erros: string[] = [];
  page.on("pageerror", (e) => erros.push(e.message));
  await page.route(/\/api\/|\.json(\?|$)/, (r) => r.abort("failed"));
  const resp = await page.goto("/agenda/");
  expect(resp?.status()).toBe(200);
  await expect(page.locator("h1").first()).toBeVisible();
  expect(erros, "exceção não tratada com a rede fora").toEqual([]);
});
