import { test, expect, evidence } from "../support/lab";
import { KEY_PAGES } from "../support/pages";

/**
 * Desempenho de carregamento (laboratório, sem throttling): LCP, CLS, TTFB,
 * DOMContentLoaded, bytes por tipo, número de requisições, recursos bloqueantes.
 * Orçamentos iniciais generosos — servem para detectar regressão, não para certificar.
 * Métricas de campo (INP real) exigem RUM; aqui medimos o proxy "long tasks".
 */
const BUDGET = { lcpMs: 2500, cls: 0.1, requests: 60, jsKB: 900, cssKB: 400 };

for (const p of KEY_PAGES.filter((k) => k.archetype !== "ERROR")) {
  test(`vitals: ${p.id}`, async ({ asRole }, testInfo) => {
    const page = await asRole(p.role, { clock: false });
    await page.addInitScript(() => {
      const w = window as unknown as { __lab: { lcp: number; cls: number; longTasks: number } };
      w.__lab = { lcp: 0, cls: 0, longTasks: 0 };
      new PerformanceObserver((l) => { for (const e of l.getEntries()) w.__lab.lcp = e.startTime; }).observe({ type: "largest-contentful-paint", buffered: true });
      new PerformanceObserver((l) => { for (const e of l.getEntries() as unknown as { value: number; hadRecentInput: boolean }[]) if (!e.hadRecentInput) w.__lab.cls += e.value; }).observe({ type: "layout-shift", buffered: true });
      try { new PerformanceObserver((l) => { w.__lab.longTasks += l.getEntries().length; }).observe({ type: "longtask", buffered: true }); } catch {}
    });
    await page.goto(p.path, { waitUntil: "load" });
    await page.waitForTimeout(800);
    const m = await page.evaluate(() => {
      const nav = performance.getEntriesByType("navigation")[0] as PerformanceNavigationTiming;
      const res = performance.getEntriesByType("resource") as PerformanceResourceTiming[];
      const kb = (f: (r: PerformanceResourceTiming) => boolean) => Math.round(res.filter(f).reduce((s, r) => s + (r.encodedBodySize || r.transferSize || 0), 0) / 1024);
      const lab = (window as unknown as { __lab: { lcp: number; cls: number; longTasks: number } }).__lab;
      return {
        ttfbMs: Math.round(nav.responseStart - nav.requestStart),
        dclMs: Math.round(nav.domContentLoadedEventEnd),
        loadMs: Math.round(nav.loadEventEnd),
        lcpMs: Math.round(lab.lcp),
        cls: Number(lab.cls.toFixed(3)),
        longTasks: lab.longTasks,
        requests: res.length + 1,
        htmlKB: Math.round((nav.encodedBodySize || 0) / 1024),
        jsKB: kb((r) => r.initiatorType === "script" || r.name.endsWith(".js")),
        cssKB: kb((r) => r.initiatorType === "link" && r.name.includes(".css") || r.name.endsWith(".css")),
        imgKB: kb((r) => r.initiatorType === "img"),
        fontKB: kb((r) => /\.(woff2?|ttf|otf)(\?|$)/.test(r.name)),
        blocking: res.filter((r) => (r as unknown as { renderBlockingStatus?: string }).renderBlockingStatus === "blocking").map((r) => r.name.replace(location.origin, "")),
      };
    });
    await evidence(testInfo, "performance", p.id, { page: p.id, path: p.path, budget: BUDGET, metrics: m });
    expect.soft(m.lcpMs, "LCP").toBeLessThanOrEqual(BUDGET.lcpMs);
    expect.soft(m.cls, "CLS").toBeLessThanOrEqual(BUDGET.cls);
    expect.soft(m.requests, "requisições").toBeLessThanOrEqual(BUDGET.requests);
    expect.soft(m.jsKB, "JS KB").toBeLessThanOrEqual(BUDGET.jsKB);
  });
}
