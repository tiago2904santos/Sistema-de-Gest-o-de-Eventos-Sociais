import { test, expect } from "../support/lab";
import { readFileSync, existsSync } from "node:fs";

/**
 * Varredura de todas as rotas GET sem parâmetro do inventário (ui-inventory/routes.json),
 * como superusuário. Critério: nenhuma resposta 5xx. 3xx/4xx são registrados (rotas só-POST,
 * downloads que exigem contexto etc.) mas não reprovam.
 */
type Route = { name: string | null; pattern: string; params: string[]; admin: boolean; decorators: string[]; methods_hint: string[] };

const inv = "ui-inventory/routes.json";
const rotas: Route[] = existsSync(inv) ? JSON.parse(readFileSync(inv, "utf-8")).routes : [];
const alvo = rotas.filter(
  (r) => r.params.length === 0 && !r.admin && !r.pattern.includes("(") && !r.decorators.includes("require_POST")
    && !/\/(sair|logout|webhook|sw\.js|manifest)/.test(r.pattern),
);

test("varredura de rotas GET sem parâmetro não devolve 5xx", async ({ asRole }, testInfo) => {
  test.skip(alvo.length === 0, "Rode `npm run agent:inventory` antes");
  test.setTimeout(10 * 60_000);
  const page = await asRole("admin");
  const resultado: { path: string; status: number | null }[] = [];
  for (const r of alvo) {
    const resp = await page.request.get(r.pattern, { maxRedirects: 0 }).catch(() => null);
    resultado.push({ path: r.pattern, status: resp?.status() ?? null });
  }
  await testInfo.attach("rotas.json", { body: JSON.stringify(resultado, null, 2), contentType: "application/json" });
  const quebradas = resultado.filter((x) => x.status === null || x.status >= 500);
  expect(quebradas, `${quebradas.length} rota(s) com erro`).toEqual([]);
});
