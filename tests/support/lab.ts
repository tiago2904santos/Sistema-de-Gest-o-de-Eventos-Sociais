import { test as base, expect, type Page, type TestInfo } from "@playwright/test";
import { mkdirSync, writeFileSync } from "node:fs";
import path from "node:path";
import { storageStatePath, type Role } from "./roles";

/** Âncora do seed (agent_lab/seed.py → ANCORA) e do servidor (AGENT_LAB_FREEZE). */
export const ANCHOR = new Date("2026-09-15T10:00:00-03:00");

export type PageSignals = { consoleErrors: string[]; pageErrors: string[]; failedRequests: string[]; serverErrors: string[] };

/** Liga os coletores de sinais de erro a uma página. */
export function watchSignals(page: Page): PageSignals {
  const s: PageSignals = { consoleErrors: [], pageErrors: [], failedRequests: [], serverErrors: [] };
  page.on("console", (m) => {
    if (m.type() === "error") s.consoleErrors.push(m.text());
  });
  page.on("pageerror", (e) => s.pageErrors.push(`${e.name}: ${e.message}`));
  page.on("requestfailed", (r) => {
    const erro = r.failure()?.errorText ?? "";
    if (!erro.includes("ERR_ABORTED")) s.failedRequests.push(`${r.method()} ${r.url()} — ${erro}`);
  });
  page.on("response", (r) => {
    if (r.status() >= 500) s.serverErrors.push(`${r.status()} ${r.request().method()} ${r.url()}`);
  });
  return s;
}

/** Grava evidência (JSON ou PNG) em reports/<área>/… e anexa ao teste. */
export async function evidence(testInfo: TestInfo, area: string, name: string, data: unknown | Buffer) {
  const dir = path.join("reports", area);
  mkdirSync(dir, { recursive: true });
  const isBuf = Buffer.isBuffer(data);
  const file = path.join(dir, `${name}${isBuf ? ".png" : ".json"}`);
  writeFileSync(file, isBuf ? (data as Buffer) : JSON.stringify(data, null, 2));
  await testInfo.attach(name, { path: file, contentType: isBuf ? "image/png" : "application/json" });
  return file;
}

/** Deixa a página estável para captura: relógio fixo, sem animações, fontes carregadas. */
export async function stabilize(page: Page) {
  await page.addStyleTag({ content: "*,*::before,*::after{transition:none!important;animation:none!important;caret-color:transparent!important}" }).catch(() => {});
  await page.evaluate(() => document.fonts?.ready).catch(() => {});
}

type Fixtures = {
  signals: PageSignals;
  /** Página autenticada no papel. `clock: false` mantém o relógio real (necessário para métricas de desempenho). */
  asRole: (role: Role, opts?: { clock?: boolean }) => Promise<Page>;
};

export const test = base.extend<Fixtures>({
  signals: async ({ page }, use) => {
    await use(watchSignals(page));
  },
  asRole: async ({ browser }, use, testInfo) => {
    const abertas: { close: () => Promise<void> }[] = [];
    await use(async (role: Role, opts: { clock?: boolean } = {}) => {
      const ctx = await browser.newContext({
        ...testInfo.project.use,
        storageState: storageStatePath(role),
      });
      if (opts.clock !== false) await ctx.clock.setFixedTime(ANCHOR).catch(() => {});
      abertas.push(ctx);
      return ctx.newPage();
    });
    for (const c of abertas) await c.close();
  },
});

export { expect };
