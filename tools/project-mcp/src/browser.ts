/**
 * browser_* — navegador orientado a evidências (Playwright), com sessões persistentes.
 * Cada ação devolve o que aconteceu + arquivos de evidência (capturas, DOM, console, rede, trace).
 */
import { chromium, type Browser, type BrowserContext, type Page } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import { existsSync, mkdirSync } from "node:fs";
import path from "node:path";
import { z } from "zod";
import type { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { ROLES, LAB_PASSWORD, storageStatePath, type Role } from "../../../tests/support/roles.ts";
import { VIEWPORTS, type ViewportName } from "../../../tests/support/viewports.ts";
import { layoutIssuesSource } from "../../../tests/tools/layout-source.mjs";
import { BASE_URL, ROOT, ensureServer, evidenceDir, ok, rel, safe, writeJson } from "./util.ts";

export const ANCHOR = new Date("2026-09-15T10:00:00-03:00");
const roleEnum = z.enum(Object.keys(ROLES) as [Role, ...Role[]]);
const vpEnum = z.enum(Object.keys(VIEWPORTS) as [ViewportName, ...ViewportName[]]);

type Signals = { console: { type: string; text: string }[]; pageErrors: string[]; requests: { method: string; url: string; status?: number; ms?: number; failed?: string; type: string }[] };
type Session = { id: string; role: Role | "anon"; context: BrowserContext; page: Page; signals: Signals; tracing: boolean; opened: string };

let browser: Browser | null = null;
const sessions = new Map<string, Session>();
let n = 0;

async function getBrowser() {
  if (!browser || !browser.isConnected()) browser = await chromium.launch();
  return browser;
}

/** Sessão autenticada do papel: reaproveita .lab/auth/<papel>.json ou faz login real. */
export async function ensureAuth(role: Role, force = false) {
  const file = path.join(ROOT, storageStatePath(role));
  if (existsSync(file) && !force) return file;
  mkdirSync(path.dirname(file), { recursive: true });
  const b = await getBrowser();
  const ctx = await b.newContext({ baseURL: BASE_URL });
  const page = await ctx.newPage();
  await page.goto("/conta/entrar/");
  await page.getByLabel("Usuário").fill(ROLES[role]);
  await page.getByLabel("Senha", { exact: true }).fill(LAB_PASSWORD);
  await page.locator("form button[type=submit]").click();
  await page.waitForLoadState("domcontentloaded");
  if (page.url().includes("/conta/entrar/")) throw new Error(`login falhou para ${ROLES[role]} — rode reset_lab`);
  await ctx.storageState({ path: file });
  await ctx.close();
  return file;
}

export async function openSession(opts: { role?: Role | "anon"; viewport?: ViewportName; clock?: boolean; trace?: boolean }): Promise<Session> {
  await ensureServer();
  const role = opts.role ?? "admin";
  const b = await getBrowser();
  const novoContexto = async (forcarLogin = false) => b.newContext({
    baseURL: BASE_URL, locale: "pt-BR", timezoneId: "America/Sao_Paulo",
    viewport: VIEWPORTS[opts.viewport ?? "desktop"],
    storageState: role === "anon" ? undefined : await ensureAuth(role, forcarLogin),
  });
  let context = await novoContexto();
  if (role !== "anon") {
    // Sessão salva pode ter expirado (ex.: lab_reset recriou o banco): confere e refaz o login.
    const r = await context.request.get("/", { maxRedirects: 5 });
    if (r.url().includes("/conta/entrar/")) {
      await context.close();
      context = await novoContexto(true);
    }
  }
  if (opts.clock !== false) await context.clock.setFixedTime(ANCHOR).catch(() => {});
  if (opts.trace) await context.tracing.start({ screenshots: true, snapshots: true });
  const page = await context.newPage();
  const signals: Signals = { console: [], pageErrors: [], requests: [] };
  page.on("console", (m) => signals.console.push({ type: m.type(), text: m.text() }));
  page.on("pageerror", (e) => signals.pageErrors.push(`${e.name}: ${e.message}`));
  const t0 = new Map<unknown, number>();
  page.on("request", (r) => t0.set(r, Date.now()));
  page.on("requestfinished", async (r) => {
    const resp = await r.response().catch(() => null);
    signals.requests.push({ method: r.method(), url: r.url().replace(BASE_URL, ""), status: resp?.status(), ms: Date.now() - (t0.get(r) ?? Date.now()), type: r.resourceType() });
  });
  page.on("requestfailed", (r) => signals.requests.push({ method: r.method(), url: r.url().replace(BASE_URL, ""), failed: r.failure()?.errorText, type: r.resourceType() }));
  const id = `p${++n}`;
  const s: Session = { id, role, context, page, signals, tracing: !!opts.trace, opened: new Date().toISOString() };
  sessions.set(id, s);
  return s;
}

export function getSession(id?: string): Session {
  const s = id ? sessions.get(id) : [...sessions.values()].at(-1);
  if (!s) throw new Error(`sessão ${id ?? "(última)"} não existe — use browser_open_page primeiro`);
  return s;
}

export async function screenshot(page: Page, dir: string, name: string, opts: { fullPage?: boolean; selector?: string } = {}) {
  const file = path.join(dir, `${name}.png`);
  const buf = opts.selector ? await page.locator(opts.selector).first().screenshot({ path: file }) : await page.screenshot({ path: file, fullPage: !!opts.fullPage });
  return { file: rel(file), buf };
}

export async function stabilize(page: Page) {
  await page.addStyleTag({ content: "*,*::before,*::after{transition:none!important;animation:none!important;caret-color:transparent!important}" }).catch(() => {});
  await page.evaluate(() => document.fonts?.ready).catch(() => {});
}

export async function landmarks(page: Page) {
  return page.evaluate(() => ({
    title: document.title,
    h1: [...document.querySelectorAll("h1")].map((h) => h.textContent?.trim()),
    headings: [...document.querySelectorAll("h1,h2,h3,h4")].map((h) => `${h.tagName} ${h.textContent?.trim().slice(0, 70)}`).slice(0, 60),
    landmarks: [...document.querySelectorAll("header,nav,main,aside,footer,form[aria-label],section[aria-label],[role=banner],[role=navigation],[role=main],[role=search],[role=contentinfo],[role=complementary]")]
      .map((e) => `${e.getAttribute("role") ?? e.tagName.toLowerCase()}${e.getAttribute("aria-label") ? ` "${e.getAttribute("aria-label")}"` : ""}`),
    skipLink: !!document.querySelector('a[href^="#"][class*="pular"], a[href="#conteudo"], a[href="#main"]'),
    lang: document.documentElement.lang,
  }));
}

export async function focusWalk(page: Page, steps = 15) {
  const out: { step: number; element: string; name: string; visibleRing: boolean }[] = [];
  await page.locator("body").click({ position: { x: 1, y: 1 } }).catch(() => {});
  for (let i = 1; i <= steps; i++) {
    await page.keyboard.press("Tab");
    out.push(await page.evaluate((i) => {
      const el = document.activeElement as HTMLElement | null;
      if (!el || el === document.body) return { step: i, element: "body", name: "", visibleRing: false };
      const cs = getComputedStyle(el);
      const ring = (cs.outlineStyle !== "none" && parseFloat(cs.outlineWidth) > 0) || (cs.boxShadow !== "none" && cs.boxShadow !== "");
      const cls = (el.getAttribute("class") || "").split(/\s+/).slice(0, 2).join(".");
      return { step: i, element: `${el.tagName.toLowerCase()}${el.id ? "#" + el.id : ""}${cls ? "." + cls : ""}`,
        name: (el.getAttribute("aria-label") || el.textContent || (el as HTMLInputElement).name || "").trim().slice(0, 50), visibleRing: ring };
    }, i));
  }
  return out;
}

export async function axe(page: Page, include?: string) {
  let b = new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa", "best-practice"]);
  if (include) b = b.include(include);
  const r = await b.analyze();
  const counts = { critical: 0, serious: 0, moderate: 0, minor: 0 } as Record<string, number>;
  for (const v of r.violations) counts[v.impact ?? "minor"] += v.nodes.length;
  return { counts, violations: r.violations.map((v) => ({ id: v.id, impact: v.impact, help: v.help, helpUrl: v.helpUrl, nodes: v.nodes.length, targets: v.nodes.slice(0, 5).map((x) => x.target.join(" ")), fix: v.nodes[0]?.failureSummary })) };
}

export async function layout(page: Page) {
  return page.evaluate(layoutIssuesSource) as Promise<{ kind: string; detail: string; selector?: string }[]>;
}

/** Localiza por seletor CSS ou, se começar com "role=", por papel+nome ("role=button[name=Salvar]"), ou "text=…"/"label=…". */
function locate(page: Page, target: string) {
  const m = target.match(/^role=(\w+)(?:\[name=(.+)\])?$/);
  if (m) return page.getByRole(m[1] as Parameters<Page["getByRole"]>[0], m[2] ? { name: m[2] } : undefined).first();
  if (target.startsWith("label=")) return page.getByLabel(target.slice(6)).first();
  if (target.startsWith("text=")) return page.getByText(target.slice(5)).first();
  return page.locator(target).first();
}

export function registerBrowser(server: McpServer) {
  const T = (name: string, description: string, shape: z.ZodRawShape, fn: (a: any) => Promise<ReturnType<typeof ok>>) =>
    server.registerTool(name, { description, inputSchema: shape }, safe(fn));
  const sid = { session: z.string().optional().describe("id da sessão (padrão: a última aberta)") };

  T("browser_open_page", "Abre uma página do laboratório como um papel (sessão autenticada real), com relógio ancorado. Devolve id da sessão, status, título, h1 e captura.",
    { path: z.string().describe("caminho, ex. /viagens/oficios/"), role: z.union([roleEnum, z.literal("anon")]).default("admin"), viewport: vpEnum.default("desktop"), trace: z.boolean().default(false), clock: z.boolean().default(true) },
    async (a) => {
      const s = await openSession(a);
      const resp = await s.page.goto(a.path, { waitUntil: "load" });
      await s.page.waitForLoadState("networkidle").catch(() => {});
      const dir = evidenceDir("open_page");
      const shot = await screenshot(s.page, dir, "viewport");
      return ok({ session: s.id, role: a.role, url: s.page.url(), status: resp?.status(), title: await s.page.title(), h1: await s.page.locator("h1").allInnerTexts(), evidence: [shot.file] }, [shot.buf]);
    });

  T("browser_navigate", "Navega a sessão para outro caminho.", { ...sid, path: z.string() }, async (a) => {
    const s = getSession(a.session);
    const resp = await s.page.goto(a.path, { waitUntil: "load" });
    return ok({ session: s.id, url: s.page.url(), status: resp?.status(), title: await s.page.title() });
  });

  T("browser_click", "Clica num elemento (CSS, role=botão[name=…], label=…, text=…) e relata navegação/erros.", { ...sid, target: z.string() }, async (a) => {
    const s = getSession(a.session);
    const antes = s.page.url();
    const erros = s.signals.pageErrors.length;
    await locate(s.page, a.target).click();
    await s.page.waitForLoadState("domcontentloaded").catch(() => {});
    return ok({ session: s.id, clicked: a.target, navigated: s.page.url() !== antes, url: s.page.url(), newPageErrors: s.signals.pageErrors.slice(erros) });
  });

  T("browser_fill", "Preenche um campo (CSS, label=…, role=…).", { ...sid, target: z.string(), value: z.string() }, async (a) => {
    const s = getSession(a.session);
    await locate(s.page, a.target).fill(a.value);
    return ok({ session: s.id, filled: a.target });
  });

  T("browser_select", "Seleciona opção num <select> nativo (pelo rótulo ou valor).", { ...sid, target: z.string(), option: z.string() }, async (a) => {
    const s = getSession(a.session);
    const r = await locate(s.page, a.target).selectOption({ label: a.option }).catch(() => locate(s.page, a.target).selectOption(a.option));
    return ok({ session: s.id, selected: r });
  });

  T("browser_submit", "Envia um formulário (padrão: o primeiro da página) e relata resultado: URL, mensagens, campos inválidos. Só em LAB.",
    { ...sid, form: z.string().default("main form"), noValidate: z.boolean().default(false).describe("desliga a validação HTML5 para testar a do servidor") }, async (a) => {
      const s = getSession(a.session);
      const f = s.page.locator(a.form).first();
      if (a.noValidate) await f.evaluate((el) => ((el as HTMLFormElement).noValidate = true));
      const antes = s.page.url();
      await f.evaluate((el) => (el as HTMLFormElement).requestSubmit());
      await s.page.waitForLoadState("domcontentloaded").catch(() => {});
      const estado = await s.page.evaluate(() => ({
        errors: [...document.querySelectorAll(".form-erro, .errorlist li, [role=alert]")].map((e) => e.textContent?.trim()).filter(Boolean).slice(0, 30),
        invalid: [...document.querySelectorAll("[aria-invalid=true]")].map((e) => (e as HTMLInputElement).name || e.id),
        messages: [...document.querySelectorAll(".mensagens li, .aviso, .alert, .toast")].map((e) => e.textContent?.trim()).filter(Boolean).slice(0, 10),
        focused: document.activeElement?.getAttribute("name") || document.activeElement?.tagName,
      }));
      return ok({ session: s.id, from: antes, to: s.page.url(), navigated: s.page.url() !== antes, ...estado });
    });

  T("browser_inspect_dom", "Resumo estruturado do DOM (ou de um seletor): título, headings, formulários, tabelas, interativos, contagem de nós; e o HTML externo do seletor (truncado).",
    { ...sid, selector: z.string().optional(), maxHtml: z.number().default(4000) }, async (a) => {
      const s = getSession(a.session);
      const resumo = await s.page.evaluate((sel) => {
        const raiz = sel ? document.querySelector(sel) : document.body;
        if (!raiz) return { error: `seletor não encontrado: ${sel}` };
        return {
          nodes: raiz.getElementsByTagName("*").length,
          forms: [...raiz.querySelectorAll("form")].map((f) => ({ action: f.getAttribute("action"), method: f.method, fields: [...f.querySelectorAll("input,select,textarea")].filter((i) => (i as HTMLInputElement).type !== "hidden").map((i) => (i as HTMLInputElement).name).slice(0, 60) })),
          tables: [...raiz.querySelectorAll("table")].map((t) => ({ headers: [...t.querySelectorAll("th")].map((h) => h.textContent?.trim()), rows: t.querySelectorAll("tbody tr").length })),
          interactive: raiz.querySelectorAll("a[href],button,input,select,textarea,[tabindex]").length,
          dialogs: [...raiz.querySelectorAll("dialog,[role=dialog]")].map((d) => d.id || d.getAttribute("aria-labelledby")),
        };
      }, a.selector);
      const html = a.selector ? (await s.page.locator(a.selector).first().evaluate((e) => e.outerHTML).catch(() => "")).slice(0, a.maxHtml) : undefined;
      return ok({ session: s.id, url: s.page.url(), ...resumo, html });
    });

  T("browser_inspect_accessibility_tree", "Árvore de acessibilidade (snapshot ARIA em YAML) da página ou de um seletor.", { ...sid, selector: z.string().default("body") }, async (a) => {
    const s = getSession(a.session);
    const snap = await s.page.locator(a.selector).first().ariaSnapshot();
    const dir = evidenceDir("aria");
    const file = path.join(dir, "aria.yml");
    (await import("node:fs")).writeFileSync(file, snap);
    return ok({ session: s.id, evidence: [rel(file)], snapshot: snap.length > 12000 ? snap.slice(0, 12000) + "\n… (truncado; ver evidência)" : snap });
  });

  T("browser_inspect_landmarks", "Landmarks, headings, h1, idioma e skip-link da página.", { ...sid }, async (a) => ok({ session: getSession(a.session).id, ...(await landmarks(getSession(a.session).page)) }));

  T("browser_inspect_focus", "Percorre a página com Tab e relata cada elemento focado e se o anel de foco é visível.", { ...sid, steps: z.number().default(15) }, async (a) => {
    const s = getSession(a.session);
    const passos = await focusWalk(s.page, a.steps);
    return ok({ session: s.id, steps: passos, withoutVisibleRing: passos.filter((p) => !p.visibleRing && p.element !== "body").length });
  });

  T("browser_inspect_console", "Mensagens de console e exceções JS acumuladas na sessão.", { ...sid, onlyErrors: z.boolean().default(true) }, async (a) => {
    const s = getSession(a.session);
    return ok({ session: s.id, pageErrors: s.signals.pageErrors, console: s.signals.console.filter((c) => !a.onlyErrors || c.type === "error" || c.type === "warning") });
  });

  T("browser_inspect_network", "Requisições da sessão (método, URL, status, ms); filtra falhas/5xx/lentas.", { ...sid, filter: z.enum(["all", "failed", "slow", "xhr"]).default("all"), slowMs: z.number().default(500) }, async (a) => {
    const s = getSession(a.session);
    let r = s.signals.requests;
    if (a.filter === "failed") r = r.filter((x) => x.failed || (x.status ?? 0) >= 400);
    if (a.filter === "slow") r = r.filter((x) => (x.ms ?? 0) >= a.slowMs);
    if (a.filter === "xhr") r = r.filter((x) => x.type === "xhr" || x.type === "fetch");
    return ok({ session: s.id, total: s.signals.requests.length, shown: r.length, requests: r.slice(-200) });
  });

  T("browser_inspect_layout", "Varredura de layout: overflow horizontal, elementos vazando, texto cortado, alvos < 24px.", { ...sid }, async (a) => {
    const s = getSession(a.session);
    return ok({ session: s.id, viewport: s.page.viewportSize(), issues: await layout(s.page) });
  });

  T("browser_capture_screenshot", "Captura a área visível.", { ...sid }, async (a) => {
    const s = getSession(a.session);
    const shot = await screenshot(s.page, evidenceDir("screenshot"), "viewport");
    return ok({ session: s.id, evidence: [shot.file] }, [shot.buf]);
  });

  T("browser_capture_full_page", "Captura a página inteira (estável: sem animações).", { ...sid }, async (a) => {
    const s = getSession(a.session);
    await stabilize(s.page);
    const shot = await screenshot(s.page, evidenceDir("full_page"), "full", { fullPage: true });
    return ok({ session: s.id, evidence: [shot.file] }, [shot.buf]);
  });

  T("browser_capture_element", "Captura um elemento.", { ...sid, selector: z.string() }, async (a) => {
    const s = getSession(a.session);
    const shot = await screenshot(s.page, evidenceDir("element"), "element", { selector: a.selector });
    return ok({ session: s.id, evidence: [shot.file] }, [shot.buf]);
  });

  T("browser_test_viewport", "Recarrega a página em cada viewport e devolve problemas de layout + capturas.", { ...sid, viewports: z.array(vpEnum).default(["desktop", "tablet", "mobile"]) }, async (a) => {
    const s = getSession(a.session);
    const dir = evidenceDir("viewports");
    const res: Record<string, unknown> = {};
    for (const vp of a.viewports as ViewportName[]) {
      await s.page.setViewportSize(VIEWPORTS[vp]);
      await s.page.reload({ waitUntil: "load" });
      await stabilize(s.page);
      const issues = await layout(s.page);
      const shot = await screenshot(s.page, dir, vp, { fullPage: true });
      res[vp] = { overflowX: issues.some((i) => i.kind === "page-overflow-x"), issues: issues.slice(0, 20), evidence: shot.file };
    }
    return ok({ session: s.id, results: res, evidence: [writeJson(path.join(dir, "viewports.json"), res)] });
  });

  T("browser_test_keyboard", "Teste de teclado: ordem de Tab, anel de foco, e (opcional) Enter/Esc num alvo.", { ...sid, steps: z.number().default(12), pressOn: z.string().optional(), key: z.enum(["Enter", "Escape", "Space", "ArrowDown"]).optional() }, async (a) => {
    const s = getSession(a.session);
    const passos = await focusWalk(s.page, a.steps);
    let acao: unknown = null;
    if (a.pressOn && a.key) {
      await locate(s.page, a.pressOn).focus();
      await s.page.keyboard.press(a.key);
      acao = { key: a.key, on: a.pressOn, url: s.page.url(), dialogOpen: await s.page.locator("dialog[open]").count() };
    }
    return ok({ session: s.id, tabOrder: passos, withoutVisibleRing: passos.filter((p) => !p.visibleRing && p.element !== "body").map((p) => p.element), action: acao });
  });

  T("browser_run_page_flow", "Executa um fluxo de passos (goto/click/fill/select/press/expect_text/expect_url/screenshot) numa sessão nova e grava evidência de cada passo.",
    {
      role: z.union([roleEnum, z.literal("anon")]).default("admin"), viewport: vpEnum.default("desktop"), trace: z.boolean().default(true),
      steps: z.array(z.object({ action: z.enum(["goto", "click", "fill", "select", "press", "expect_text", "expect_url", "screenshot", "wait"]), target: z.string().optional(), value: z.string().optional() })),
    },
    async (a) => {
      const s = await openSession({ role: a.role, viewport: a.viewport, trace: a.trace });
      const dir = evidenceDir("flow");
      const log: Record<string, unknown>[] = [];
      let falhou: string | null = null;
      for (const [i, st] of (a.steps as { action: string; target?: string; value?: string }[]).entries()) {
        try {
          if (st.action === "goto") await s.page.goto(st.target!, { waitUntil: "load" });
          if (st.action === "click") await locate(s.page, st.target!).click();
          if (st.action === "fill") await locate(s.page, st.target!).fill(st.value ?? "");
          if (st.action === "select") await locate(s.page, st.target!).selectOption({ label: st.value ?? "" });
          if (st.action === "press") await s.page.keyboard.press(st.value ?? "Enter");
          if (st.action === "wait") await s.page.waitForTimeout(Number(st.value ?? 300));
          if (st.action === "expect_text") { const txt = await s.page.locator(st.target ?? "body").first().innerText(); if (!txt.includes(st.value ?? "")) throw new Error(`texto "${st.value}" não encontrado`); }
          if (st.action === "expect_url") { if (!s.page.url().includes(st.value ?? "")) throw new Error(`URL ${s.page.url()} não contém ${st.value}`); }
          await s.page.waitForLoadState("domcontentloaded").catch(() => {});
          const shot = await screenshot(s.page, dir, `${String(i + 1).padStart(2, "0")}-${st.action}`);
          log.push({ step: i + 1, ...st, ok: true, url: s.page.url(), evidence: shot.file });
        } catch (e) {
          falhou = `passo ${i + 1} (${st.action} ${st.target ?? ""}): ${(e as Error).message.split("\n")[0]}`;
          const shot = await screenshot(s.page, dir, `${String(i + 1).padStart(2, "0")}-FALHA`).catch(() => null);
          log.push({ step: i + 1, ...st, ok: false, error: falhou, evidence: shot?.file });
          break;
        }
      }
      let trace: string | undefined;
      if (a.trace) { trace = rel(path.join(dir, "trace.zip")); await s.context.tracing.stop({ path: path.join(ROOT, trace) }); s.tracing = false; }
      const res = { session: s.id, passed: !falhou, failure: falhou, steps: log, pageErrors: s.signals.pageErrors, trace, verification: trace ? `npx playwright show-trace ${trace}` : undefined };
      writeJson(path.join(dir, "flow.json"), res);
      return ok(res);
    });

  T("browser_get_trace", "Para o trace da sessão (aberta com trace=true) e devolve o arquivo .zip.", { ...sid }, async (a) => {
    const s = getSession(a.session);
    if (!s.tracing) throw new Error("sessão sem trace ativo (abra com trace=true)");
    const file = path.join(evidenceDir("trace"), "trace.zip");
    await s.context.tracing.stop({ path: file });
    s.tracing = false;
    return ok({ session: s.id, trace: rel(file), open: `npx playwright show-trace ${rel(file)}` });
  });

  T("browser_close", "Fecha uma sessão (ou todas).", { session: z.string().optional(), all: z.boolean().default(false) }, async (a) => {
    const alvo = a.all ? [...sessions.values()] : [getSession(a.session)];
    for (const s of alvo) { await s.context.close().catch(() => {}); sessions.delete(s.id); }
    return ok({ closed: alvo.map((s) => s.id), open: [...sessions.keys()] });
  });

  T("browser_list_sessions", "Sessões abertas.", {}, async () =>
    ok([...sessions.values()].map((s) => ({ id: s.id, role: s.role, url: s.page.url(), opened: s.opened, tracing: s.tracing }))));
}

export async function shutdownBrowser() {
  for (const s of sessions.values()) await s.context.close().catch(() => {});
  sessions.clear();
  await browser?.close().catch(() => {});
}
