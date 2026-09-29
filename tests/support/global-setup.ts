import { chromium, type FullConfig } from "@playwright/test";
import { mkdirSync } from "node:fs";
import { ROLES, LAB_PASSWORD, storageStatePath, type Role } from "./roles";

/** Faz login real (pelo formulário) com cada papel e guarda a sessão. */
export default async function globalSetup(config: FullConfig) {
  const baseURL = config.projects[0].use.baseURL!;
  mkdirSync(".lab/auth", { recursive: true });
  const browser = await chromium.launch();
  for (const role of Object.keys(ROLES) as Role[]) {
    const ctx = await browser.newContext({ baseURL });
    const page = await ctx.newPage();
    await page.goto("/conta/entrar/");
    await page.getByLabel("Usuário").fill(ROLES[role]);
    await page.getByLabel("Senha", { exact: true }).fill(LAB_PASSWORD);
    await Promise.all([page.waitForLoadState("domcontentloaded"), page.locator("form button[type=submit]").click()]);
    if (page.url().includes("/conta/entrar/")) {
      throw new Error(`Login falhou para ${ROLES[role]} — o seed rodou? (node scripts/agent/run.mjs reset)`);
    }
    await ctx.storageState({ path: storageStatePath(role) });
    await ctx.close();
  }
  await browser.close();
}
