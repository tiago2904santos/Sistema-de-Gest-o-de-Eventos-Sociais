#!/usr/bin/env node
/**
 * Motor de auditoria — camada de runtime. Audita UMA página (ou fluxo curto) de ponta a ponta
 * e grava evidência + achados no formato comum (docs/agent/audit-finding.schema.json).
 *
 *   node tests/tools/audit-page.mjs --path /viagens/oficios/ --role viagensGestor [--label antes]
 *        [--viewports desktop,mobile] [--click "text=Filtros e ordem"] [--base http://127.0.0.1:8031]
 *
 * Saída em reports/audit/<slug>[-<label>]/:
 *   <viewport>.png           captura de página inteira por viewport
 *   axe.json                 violações (critical/serious/moderate/minor)
 *   layout.json              overflow, vazamentos, texto cortado, alvos pequenos por viewport
 *   console.json             erros de console, exceções JS, requisições falhas e 5xx
 *   perf.json                TTFB, LCP, CLS, bytes, requisições
 *   dom.json                 headings, landmarks, formulários, contagem de interativos
 *   findings.json            achados normalizados (categoria, severidade P0–P4, evidência, recomendação)
 *
 * Requer o servidor do laboratório (npm run agent:serve). Se não estiver no ar, sobe um.
 */
import { chromium } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import { mkdirSync, writeFileSync, readFileSync } from "node:fs";
import { spawn } from "node:child_process";
import path from "node:path";
import crypto from "node:crypto";

const args = Object.fromEntries(
  process.argv.slice(2).reduce((acc, a, i, arr) => (a.startsWith("--") ? [...acc, [a.slice(2), arr[i + 1]?.startsWith("--") || arr[i + 1] === undefined ? "1" : arr[i + 1]]] : acc), []),
);
const BASE = args.base ?? process.env.LAB_BASE_URL ?? `http://127.0.0.1:${process.env.LAB_PORT ?? 8031}`;
const ROLE = args.role ?? "admin";
const PATH = args.path ?? "/";
const VIEWPORTS = { desktop: { width: 1440, height: 900 }, laptop: { width: 1280, height: 800 }, tabletRetrato: { width: 1024, height: 1366 }, tablet: { width: 768, height: 1024 }, mobile: { width: 390, height: 844 }, mobilePequeno: { width: 360, height: 800 } };
const vps = (args.viewports ?? "desktop,mobile").split(",");
const slug = (PATH.replace(/[^\w]+/g, "-").replace(/^-|-$/g, "") || "home") + (args.label ? `-${args.label}` : "");
const OUT = path.join("reports", "audit", slug);
mkdirSync(OUT, { recursive: true });

async function servidorNoAr() {
  try { return (await fetch(`${BASE}/_lab/health/`)).ok; } catch { return false; }
}
async function garantirServidor() {
  if (await servidorNoAr()) return null;
  console.log("Subindo o servidor do laboratório…");
  const p = spawn(process.execPath, ["scripts/agent/run.mjs", "serve"], { stdio: "ignore", detached: false });
  for (let i = 0; i < 240; i++) { if (await servidorNoAr()) return p; await new Promise((r) => setTimeout(r, 1000)); }
  throw new Error("servidor do laboratório não subiu");
}

const achados = [];
const achado = (rule, category, severity, title, { detail = "", evidence = [], recommendation = "" } = {}) => {
  const id = "rt-" + crypto.createHash("sha1").update(`${rule}|${PATH}|${title}`).digest("hex").slice(0, 12);
  achados.push({ id, rule, source: "runtime", category, severity, title, detail, target: { type: "page", ref: PATH, role: ROLE }, evidence, recommendation });
};
const axeSev = { critical: "P1", serious: "P2", moderate: "P3", minor: "P4" };

const proc = await garantirServidor();
const browser = await chromium.launch();
try {
  const ctx = await browser.newContext({ baseURL: BASE, storageState: ROLE === "anon" ? undefined : `.lab/auth/${ROLE}.json`, locale: "pt-BR", timezoneId: "America/Sao_Paulo" });
  const page = await ctx.newPage();
  const sinais = { consoleErrors: [], pageErrors: [], failedRequests: [], serverErrors: [] };
  page.on("console", (m) => m.type() === "error" && sinais.consoleErrors.push(m.text()));
  page.on("pageerror", (e) => sinais.pageErrors.push(`${e.name}: ${e.message}`));
  page.on("requestfailed", (r) => !String(r.failure()?.errorText).includes("ABORTED") && sinais.failedRequests.push(`${r.method()} ${r.url()}`));
  page.on("response", (r) => r.status() >= 500 && sinais.serverErrors.push(`${r.status()} ${r.url()}`));

  await page.addInitScript(() => {
    window.__lab = { lcp: 0, cls: 0 };
    new PerformanceObserver((l) => { for (const e of l.getEntries()) window.__lab.lcp = e.startTime; }).observe({ type: "largest-contentful-paint", buffered: true });
    new PerformanceObserver((l) => { for (const e of l.getEntries()) if (!e.hadRecentInput) window.__lab.cls += e.value; }).observe({ type: "layout-shift", buffered: true });
  });
  const resp = await page.goto(PATH, { waitUntil: "load" });
  if (page.url().includes("/conta/entrar/") && !PATH.includes("/conta/entrar/")) {
    throw new Error(`Sessão do papel "${ROLE}" ausente/expirada: rode os testes uma vez (npm run test:smoke) para gerar .lab/auth/`);
  }
  const status = resp?.status() ?? 0;
  if (status >= 500) achado("http-5xx", "FUNCTIONAL", "P0", `Página responde ${status}`);
  else if (status >= 400) achado("http-4xx", "FUNCTIONAL", "P1", `Página responde ${status} para o papel ${ROLE}`);
  await page.waitForTimeout(600);
  if (args.click) { await page.locator(args.click).first().click(); await page.waitForTimeout(400); }

  // Desempenho
  const perf = await page.evaluate(() => {
    const nav = performance.getEntriesByType("navigation")[0];
    const res = performance.getEntriesByType("resource");
    return { ttfbMs: Math.round(nav.responseStart - nav.requestStart), lcpMs: Math.round(window.__lab.lcp), cls: +window.__lab.cls.toFixed(3), requests: res.length + 1, htmlKB: Math.round((nav.encodedBodySize || 0) / 1024) };
  });
  writeFileSync(path.join(OUT, "perf.json"), JSON.stringify(perf, null, 2));
  if (perf.lcpMs > 2500) achado("lcp", "PERFORMANCE", "P2", `LCP ${perf.lcpMs} ms (> 2.500)`, { evidence: [{ kind: "file", path: `${OUT}/perf.json` }] });
  if (perf.cls > 0.1) achado("cls", "PERFORMANCE", "P2", `CLS ${perf.cls} (> 0,1)`, { evidence: [{ kind: "file", path: `${OUT}/perf.json` }] });
  if (perf.htmlKB > 400) achado("html-pesado", "PERFORMANCE", "P3", `HTML de ${perf.htmlKB} KB`, { recommendation: "Pagine no servidor, remova menus/modais repetidos por linha, carregue detalhes sob demanda." });

  // DOM / semântica
  const dom = await page.evaluate(() => ({
    title: document.title,
    h1: [...document.querySelectorAll("h1")].map((h) => h.textContent.trim()),
    headings: [...document.querySelectorAll("h1,h2,h3")].map((h) => `${h.tagName}: ${h.textContent.trim().slice(0, 60)}`).slice(0, 40),
    landmarks: [...document.querySelectorAll("main,nav,header,footer,aside,[role=main],[role=navigation],[role=search]")].map((e) => e.tagName.toLowerCase() + (e.getAttribute("aria-label") ? `[${e.getAttribute("aria-label")}]` : "")),
    forms: document.forms.length,
    interactive: document.querySelectorAll("a[href],button,input,select,textarea,[tabindex]").length,
    domNodes: document.getElementsByTagName("*").length,
  }));
  writeFileSync(path.join(OUT, "dom.json"), JSON.stringify(dom, null, 2));
  if (dom.h1.length !== 1) achado("h1", "ACCESSIBILITY", "P3", `Página com ${dom.h1.length} <h1>`, { recommendation: "Exatamente um h1 por página." });
  if (dom.domNodes > 5000) achado("dom-grande", "PERFORMANCE", "P3", `${dom.domNodes} nós no DOM`, { recommendation: "Virtualize/pagine listas e evite menus duplicados por linha." });

  // Acessibilidade
  const axe = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa", "best-practice"]).analyze();
  writeFileSync(path.join(OUT, "axe.json"), JSON.stringify(axe.violations, null, 2));
  for (const v of axe.violations) {
    achado(`axe:${v.id}`, "ACCESSIBILITY", axeSev[v.impact] ?? "P4", `${v.help} (${v.nodes.length}×)`, {
      detail: v.nodes.slice(0, 3).map((n) => n.target.join(" ")).join(" | "), evidence: [{ kind: "file", path: `${OUT}/axe.json` }, { kind: "url", value: v.helpUrl }],
      recommendation: v.nodes[0]?.failureSummary?.split("\n").slice(0, 3).join(" ") ?? "",
    });
  }

  // Layout por viewport
  const { layoutIssuesSource } = await import("./layout-source.mjs");
  const layout = {};
  for (const vp of vps) {
    await page.setViewportSize(VIEWPORTS[vp]);
    await page.waitForTimeout(300);
    layout[vp] = await page.evaluate(layoutIssuesSource);
    writeFileSync(path.join(OUT, `${vp}.png`), await page.screenshot({ fullPage: true }));
    const ov = layout[vp].filter((i) => i.kind === "page-overflow-x");
    if (ov.length) achado("overflow-x", "RESPONSIVE", vp.startsWith("mobile") ? "P2" : "P2", `Rolagem horizontal da página em ${vp}`, { detail: ov[0].detail + "; culpados: " + layout[vp].filter((i) => i.kind === "element-overflow").map((i) => i.selector).slice(0, 5).join(", "), evidence: [{ kind: "screenshot", path: `${OUT}/${vp}.png` }] });
    const tiny = layout[vp].filter((i) => i.kind === "tiny-target");
    if (tiny.length) achado("alvo-pequeno", "ACCESSIBILITY", "P3", `${tiny.length} alvo(s) de toque < 24px em ${vp}`, { detail: tiny.slice(0, 5).map((t) => t.selector).join(", "), evidence: [{ kind: "screenshot", path: `${OUT}/${vp}.png` }] });
  }
  writeFileSync(path.join(OUT, "layout.json"), JSON.stringify(layout, null, 2));

  // Console / rede
  writeFileSync(path.join(OUT, "console.json"), JSON.stringify(sinais, null, 2));
  if (sinais.pageErrors.length) achado("js-excecao", "FUNCTIONAL", "P1", `${sinais.pageErrors.length} exceção(ões) JS não tratada(s)`, { detail: sinais.pageErrors.slice(0, 3).join(" | "), evidence: [{ kind: "file", path: `${OUT}/console.json` }] });
  if (sinais.serverErrors.length) achado("xhr-5xx", "FUNCTIONAL", "P1", "Requisição secundária com 5xx", { detail: sinais.serverErrors.slice(0, 3).join(" | ") });
  if (sinais.consoleErrors.length) achado("console-erro", "FUNCTIONAL", "P3", `${sinais.consoleErrors.length} erro(s) no console`, { detail: sinais.consoleErrors.slice(0, 3).join(" | ") });
  if (sinais.failedRequests.length) achado("req-falha", "FUNCTIONAL", "P2", `${sinais.failedRequests.length} requisição(ões) falharam`, { detail: sinais.failedRequests.slice(0, 3).join(" | ") });

  const ordem = { P0: 0, P1: 1, P2: 2, P3: 3, P4: 4 };
  achados.sort((a, b) => ordem[a.severity] - ordem[b.severity]);
  const resumo = { page: PATH, role: ROLE, status, generated_at: new Date().toISOString(), total: achados.length, by_severity: achados.reduce((m, a) => ({ ...m, [a.severity]: (m[a.severity] ?? 0) + 1 }), {}) };
  writeFileSync(path.join(OUT, "findings.json"), JSON.stringify({ summary: resumo, findings: achados }, null, 2));
  console.log(JSON.stringify(resumo, null, 2));
  console.log(`Evidências em ${OUT}/`);
} finally {
  await browser.close();
  proc?.kill();
}
