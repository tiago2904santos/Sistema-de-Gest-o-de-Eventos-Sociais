/**
 * audit_* — auditorias com achados no formato comum (finding, severity, source, evidence,
 * recommendation, verification). Também compare_screenshots / visual.
 */
import { copyFileSync, existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import path from "node:path";
import { PNG } from "pngjs";
import pixelmatch from "pixelmatch";
import { z } from "zod";
import type { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { ROLES, type Role } from "../../../tests/support/roles.ts";
import { KEY_PAGES } from "../../../tests/support/pages.ts";
import { VIEWPORTS, type ViewportName } from "../../../tests/support/viewports.ts";
import { axe, focusWalk, landmarks, layout, openSession, screenshot, stabilize } from "./browser.ts";
import { ROOT, evidenceDir, finding, manageJson, ok, readJson, rel, requireLab, run, safe, writeJson, type Finding } from "./util.ts";

const roleEnum = z.enum(Object.keys(ROLES) as [Role, ...Role[]]);
const AXE_SEV: Record<string, Finding["severity"]> = { critical: "P1", serious: "P2", moderate: "P3", minor: "P4" };

function resumo(fs: Finding[]) {
  const by: Record<string, number> = {};
  for (const f of fs) by[f.severity] = (by[f.severity] ?? 0) + 1;
  return { total: fs.length, by_severity: Object.fromEntries(Object.entries(by).sort()) };
}

function salvar(dir: string, target: string, fs: Finding[], extra: Record<string, unknown> = {}) {
  const ordem = { P0: 0, P1: 1, P2: 2, P3: 3, P4: 4 };
  fs.sort((a, b) => ordem[a.severity] - ordem[b.severity]);
  const data = { target, generated_at: new Date().toISOString(), summary: resumo(fs), findings: fs, ...extra };
  return { ...data, evidence_file: writeJson(path.join(dir, "findings.json"), data) };
}

export function compare(a: string, b: string, outDir: string, threshold = 0.1) {
  const A = PNG.sync.read(readFileSync(a)), B = PNG.sync.read(readFileSync(b));
  const w = Math.max(A.width, B.width), h = Math.max(A.height, B.height);
  const pad = (img: PNG) => { if (img.width === w && img.height === h) return img; const o = new PNG({ width: w, height: h }); o.data.fill(255); PNG.bitblt(img, o, 0, 0, img.width, img.height, 0, 0); return o; };
  const pa = pad(A), pb = pad(B), diff = new PNG({ width: w, height: h });
  const n = pixelmatch(pa.data, pb.data, diff.data, w, h, { threshold, includeAA: false });
  mkdirSync(outDir, { recursive: true });
  copyFileSync(a, path.join(outDir, "before.png"));
  copyFileSync(b, path.join(outDir, "after.png"));
  const diffFile = path.join(outDir, "diff.png");
  writeFileSync(diffFile, PNG.sync.write(diff));
  return { before: rel(path.join(outDir, "before.png")), after: rel(path.join(outDir, "after.png")), diff: rel(diffFile), size_before: [A.width, A.height], size_after: [B.width, B.height], diffPixels: n, diffRatio: +(n / (w * h)).toFixed(5), sizeChanged: A.width !== B.width || A.height !== B.height };
}

/** Baseline de uma página-chave, espécime ou chave livre (reports/visual-baselines). */
function baselineFor(key: string) {
  const kp = KEY_PAGES.find((p) => p.id === key || p.path === key);
  if (kp) return { file: path.join(ROOT, "tests/visual/snapshots/visual/pages.spec.ts", `${kp.id}.png`), kind: "playwright-page", keyPage: kp };
  const spec = path.join(ROOT, "tests/visual/snapshots/visual/components.spec.ts", `${key}.png`);
  if (existsSync(spec)) return { file: spec, kind: "playwright-specimen" };
  return { file: path.join(ROOT, "reports/visual-baselines", `${key.replace(/[^\w-]+/g, "_").replace(/^_|_$/g, "") || "home"}.png`), kind: "mcp" };
}

export async function auditAccessibilityRuntime(pathUrl: string, role: Role, dir: string) {
  const s = await openSession({ role });
  await s.page.goto(pathUrl, { waitUntil: "load" });
  await s.page.waitForLoadState("networkidle").catch(() => {});
  const r = await axe(s.page);
  const lm = await landmarks(s.page);
  const foco = await focusWalk(s.page, 12);
  await s.context.close();
  const ev = writeJson(path.join(dir, "axe.json"), { ...r, landmarks: lm, focus: foco });
  const fs: Finding[] = r.violations.map((v) => finding({
    rule: `axe:${v.id}`, category: "ACCESSIBILITY", severity: AXE_SEV[v.impact ?? "minor"] ?? "P4", title: `${v.help} (${v.nodes}×)`,
    detail: v.targets.join(" | "), target: { type: "page", ref: pathUrl, role }, evidence: [{ kind: "file", path: ev }, { kind: "url", value: v.helpUrl }],
    recommendation: (v.fix ?? "").split("\n").slice(0, 3).join(" "), verification: `audit_accessibility {path:"${pathUrl}", role:"${role}"} sem a regra ${v.id}`,
  }));
  if (lm.h1.length !== 1) fs.push(finding({ rule: "h1-unico", category: "ACCESSIBILITY", severity: "P3", title: `${lm.h1.length} <h1> na página`, target: { type: "page", ref: pathUrl, role }, evidence: [{ kind: "file", path: ev }], recommendation: "Exatamente um h1.", verification: "browser_inspect_landmarks" }));
  const semAnel = foco.filter((f) => !f.visibleRing && f.element !== "body");
  if (semAnel.length) fs.push(finding({ rule: "foco-invisivel", category: "ACCESSIBILITY", severity: "P2", title: `${semAnel.length}/${foco.length} paradas de Tab sem anel de foco visível`, detail: semAnel.slice(0, 5).map((f) => f.element).join(", "), target: { type: "page", ref: pathUrl, role }, evidence: [{ kind: "file", path: ev }], recommendation: ":focus-visible com anel de token (docs/design-system/accessibility.md).", verification: "browser_inspect_focus" }));
  return fs;
}

export function registerAudit(server: McpServer) {
  const T = (name: string, description: string, shape: z.ZodRawShape, fn: (a: any) => Promise<ReturnType<typeof ok>>) =>
    server.registerTool(name, { description, inputSchema: shape }, safe(fn));
  const pg = { path: z.string(), role: roleEnum.default("admin") };

  T("audit_page", "Auditoria completa de uma página (tests/tools/audit-page.mjs): status, JS, console, rede, axe, h1/landmarks/DOM, LCP/CLS/HTML, layout por viewport, capturas.",
    { ...pg, viewports: z.array(z.enum(Object.keys(VIEWPORTS) as [ViewportName, ...ViewportName[]])).default(["desktop", "mobile"]), label: z.string().optional() },
    async (a) => {
      const args = ["tests/tools/audit-page.mjs", "--path", a.path, "--role", a.role, "--viewports", a.viewports.join(",")];
      if (a.label) args.push("--label", a.label);
      const r = await run(process.execPath, args, { timeoutMs: 600_000 });
      const pasta = r.stdout.match(/Evidências em (.+)\//)?.[1];
      if (!pasta) throw new Error(`audit-page falhou: ${(r.stderr || r.stdout).slice(-1500)}`);
      const f = readJson<{ summary: unknown; findings: Finding[] }>(path.join(pasta, "findings.json"))!;
      return ok({ evidence_dir: pasta, summary: f.summary, findings: f.findings, verification: `node ${args.join(" ")}` });
    });

  T("audit_accessibility", "Axe (WCAG 2.2 AA + boas práticas) + landmarks + ordem/anel de foco de uma página.", pg, async (a) => {
    const dir = evidenceDir("audit_a11y");
    return ok(salvar(dir, a.path, await auditAccessibilityRuntime(a.path, a.role, dir)));
  });

  T("audit_responsive", "Layout em várias viewports: overflow horizontal (culpado por seletor), texto cortado, alvos pequenos; capturas.", { ...pg, viewports: z.array(z.string()).default(Object.keys(VIEWPORTS)) }, async (a) => {
    const dir = evidenceDir("audit_responsive");
    const s = await openSession({ role: a.role });
    await s.page.goto(a.path, { waitUntil: "load" });
    const fs: Finding[] = [];
    const porVp: Record<string, unknown> = {};
    for (const vp of a.viewports as ViewportName[]) {
      await s.page.setViewportSize(VIEWPORTS[vp]);
      await s.page.reload({ waitUntil: "load" });
      await stabilize(s.page);
      const issues = await layout(s.page);
      const shot = await screenshot(s.page, dir, vp, { fullPage: true });
      porVp[vp] = issues;
      const ov = issues.find((i) => i.kind === "page-overflow-x");
      if (ov) fs.push(finding({ rule: "overflow-x", category: "RESPONSIVE", severity: "P2", title: `Rolagem horizontal da página em ${vp}`, detail: `${ov.detail}; culpados: ${issues.filter((i) => i.kind === "element-overflow").map((i) => i.selector).slice(0, 5).join(", ")}`, target: { type: "page", ref: a.path, role: a.role }, evidence: [{ kind: "screenshot", path: shot.file }], recommendation: "Contêiner com rolagem própria, quebra de linha ou agrupamento (docs/design-system/responsive.md).", verification: `audit_responsive {path:"${a.path}"} sem overflow em ${vp}` }));
      const tiny = issues.filter((i) => i.kind === "tiny-target");
      if (tiny.length) fs.push(finding({ rule: "alvo-pequeno", category: "ACCESSIBILITY", severity: "P3", title: `${tiny.length} alvo(s) de toque < 24px em ${vp}`, detail: tiny.slice(0, 5).map((t) => t.selector).join(", "), target: { type: "page", ref: a.path, role: a.role }, evidence: [{ kind: "screenshot", path: shot.file }], recommendation: "Mínimo 24px (WCAG 2.5.8); 44px no celular.", verification: "audit_responsive" }));
    }
    await s.context.close();
    writeJson(path.join(dir, "layout.json"), porVp);
    return ok(salvar(dir, a.path, fs));
  });

  T("audit_performance", "Vitals de laboratório de uma página: TTFB, LCP, CLS, long tasks, bytes por tipo, requisições, Server-Timing (app/db/queries).", pg, async (a) => {
    const dir = evidenceDir("audit_perf");
    const s = await openSession({ role: a.role, clock: false });
    await s.page.addInitScript(() => {
      const w = window as unknown as { __lab: { lcp: number; cls: number; lt: number } };
      w.__lab = { lcp: 0, cls: 0, lt: 0 };
      new PerformanceObserver((l) => { for (const e of l.getEntries()) w.__lab.lcp = e.startTime; }).observe({ type: "largest-contentful-paint", buffered: true });
      new PerformanceObserver((l) => { for (const e of l.getEntries() as unknown as { value: number; hadRecentInput: boolean }[]) if (!e.hadRecentInput) w.__lab.cls += e.value; }).observe({ type: "layout-shift", buffered: true });
      try { new PerformanceObserver((l) => { w.__lab.lt += l.getEntries().length; }).observe({ type: "longtask", buffered: true }); } catch { /* sem suporte */ }
    });
    const resp = await s.page.goto(a.path, { waitUntil: "load" });
    await s.page.waitForTimeout(700);
    const m = await s.page.evaluate(() => {
      const nav = performance.getEntriesByType("navigation")[0] as PerformanceNavigationTiming;
      const res = performance.getEntriesByType("resource") as PerformanceResourceTiming[];
      const kb = (f: (r: PerformanceResourceTiming) => boolean) => Math.round(res.filter(f).reduce((t, r) => t + (r.encodedBodySize || 0), 0) / 1024);
      const lab = (window as unknown as { __lab: { lcp: number; cls: number; lt: number } }).__lab;
      return { ttfbMs: Math.round(nav.responseStart - nav.requestStart), loadMs: Math.round(nav.loadEventEnd), lcpMs: Math.round(lab.lcp), cls: +lab.cls.toFixed(3), longTasks: lab.lt, requests: res.length + 1, htmlKB: Math.round((nav.encodedBodySize || 0) / 1024), jsKB: kb((r) => r.name.endsWith(".js")), cssKB: kb((r) => r.name.endsWith(".css")), domNodes: document.getElementsByTagName("*").length };
    });
    const st = resp?.headers()["server-timing"] ?? null;
    await s.context.close();
    const ev = writeJson(path.join(dir, "metrics.json"), { path: a.path, serverTiming: st, ...m });
    const alvo = { type: "page" as const, ref: a.path, role: a.role };
    const fs: Finding[] = [];
    const add = (cond: boolean, rule: string, sev: Finding["severity"], title: string, rec: string) => cond && fs.push(finding({ rule, category: "PERFORMANCE", severity: sev, title, target: alvo, evidence: [{ kind: "metric", path: ev }], recommendation: rec, verification: `audit_performance {path:"${a.path}"}` }));
    add(m.lcpMs > 2500, "lcp", "P2", `LCP ${m.lcpMs} ms`, "Reduzir bloqueantes e o HTML acima da dobra.");
    add(m.cls > 0.1, "cls", "P2", `CLS ${m.cls}`, "Reservar espaço para conteúdo tardio.");
    add(m.htmlKB > 400, "html-pesado", "P3", `HTML de ${m.htmlKB} KB`, "Paginar no servidor; não repetir menus/modais por linha.");
    add(m.domNodes > 5000, "dom-grande", "P3", `${m.domNodes} nós no DOM`, "Paginar/virtualizar listas.");
    const q = st?.match(/desc="(\d+) queries"/)?.[1];
    add(!!q && Number(q) > 60, "queries-demais", "P2", `${q} consultas SQL numa requisição`, "Verificar N+1 com obs_get_slow_queries e select_related/prefetch_related.");
    return ok(salvar(dir, a.path, fs, { metrics: m, serverTiming: st }));
  });

  T("audit_visual", "Compara a página/espécime com o baseline (Playwright ou do MCP). Sem baseline e updateBaseline=true, cria.",
    { key: z.string().describe("id de página-chave (ex. oficios-lista), caminho, ou id de espécime do UI Lab"), role: roleEnum.optional(), updateBaseline: z.boolean().default(false), threshold: z.number().default(0.1) },
    async (a) => {
      const base = baselineFor(a.key);
      const kp = (base as { keyPage?: (typeof KEY_PAGES)[number] }).keyPage;
      const role = (a.role ?? kp?.role ?? "admin") as Role;
      const alvoPath = kp?.path ?? (a.key.startsWith("/") ? a.key : `/_lab/c/${a.key}/`);
      const dir = evidenceDir("audit_visual");
      const s = await openSession({ role });
      await s.page.goto(alvoPath, { waitUntil: "load" });
      await s.page.waitForLoadState("networkidle").catch(() => {});
      await stabilize(s.page);
      const atual = await screenshot(s.page, dir, "current", base.kind === "playwright-specimen" ? { selector: "#alvo" } : { fullPage: true });
      await s.context.close();
      if (!existsSync(base.file)) {
        if (!a.updateBaseline) return ok({ key: a.key, baseline: null, current: atual.file, note: "sem baseline; chame com updateBaseline=true para criar" }, [atual.buf]);
        mkdirSync(path.dirname(base.file), { recursive: true });
        copyFileSync(path.join(ROOT, atual.file), base.file);
        return ok({ key: a.key, created_baseline: rel(base.file) });
      }
      const cmp = compare(base.file, path.join(ROOT, atual.file), dir, a.threshold);
      const fs: Finding[] = [];
      if (cmp.diffRatio > 0.002 || cmp.sizeChanged) fs.push(finding({ rule: "diff-visual", category: "VISUAL", severity: "P3", title: `Diferença visual de ${(cmp.diffRatio * 100).toFixed(2)}%${cmp.sizeChanged ? " e mudança de tamanho" : ""}`, target: { type: kp ? "page" : "component", ref: a.key, role }, evidence: [{ kind: "diff", path: cmp.diff }, { kind: "screenshot", path: cmp.before }, { kind: "screenshot", path: cmp.after }], recommendation: "Revisar o diff: intencional → atualizar baseline; senão, corrigir.", verification: `audit_visual {key:"${a.key}"} com diffRatio ≤ 0,002` }));
      if (a.updateBaseline && base.kind === "mcp") copyFileSync(path.join(ROOT, atual.file), base.file);
      return ok(salvar(dir, a.key, fs, { comparison: cmp, baseline: rel(base.file), baselineKind: base.kind }), [PNG.sync.write(PNG.sync.read(readFileSync(path.join(ROOT, cmp.diff))))]);
    });

  T("compare_screenshots", "Compara dois PNG (caminhos do repositório) e gera before/after/diff.", { before: z.string(), after: z.string(), threshold: z.number().default(0.1) }, async (a) => {
    const dir = evidenceDir("compare");
    const r = compare(path.join(ROOT, a.before), path.join(ROOT, a.after), dir, a.threshold);
    return ok(r, [readFileSync(path.join(ROOT, r.diff))]);
  });

  T("audit_component", "Audita um espécime do UI Lab: renderiza, axe no componente, captura e compara com o baseline.", { specimen: z.string().describe("id do espécime, ex. button-primario (ver get_ui_inventory specimens)") }, async (a) => {
    const dir = evidenceDir("audit_component");
    const s = await openSession({ role: "admin" });
    const resp = await s.page.goto(`/_lab/c/${a.specimen}/`);
    if (resp?.status() !== 200) { await s.context.close(); throw new Error(`espécime ${a.specimen} não existe (status ${resp?.status()})`); }
    const erro = await s.page.locator("[data-error]").count();
    await stabilize(s.page);
    const r = await axe(s.page, "#alvo");
    const shot = await screenshot(s.page, dir, a.specimen, { selector: "#alvo" }).catch(() => null);
    await s.context.close();
    const alvo = { type: "component" as const, ref: a.specimen };
    const fs: Finding[] = r.violations.map((v) => finding({ rule: `axe:${v.id}`, category: "ACCESSIBILITY", severity: AXE_SEV[v.impact ?? "minor"] ?? "P4", title: v.help, detail: v.targets.join(" | "), target: alvo, evidence: [{ kind: "url", value: v.helpUrl }], recommendation: v.fix ?? "", verification: "audit_component" }));
    if (erro) fs.push(finding({ rule: "render", category: "FUNCTIONAL", severity: "P1", title: "Espécime não renderiza", target: alvo, evidence: [], recommendation: "Ver /_lab/ (fumaça).", verification: "audit_component" }));
    const base = baselineFor(a.specimen);
    const cmp = shot && existsSync(base.file) ? compare(base.file, path.join(ROOT, shot.file), dir) : null;
    if (cmp && cmp.diffRatio > 0.002) fs.push(finding({ rule: "diff-visual", category: "VISUAL", severity: "P3", title: `Diferença visual ${(cmp.diffRatio * 100).toFixed(2)}%`, target: alvo, evidence: [{ kind: "diff", path: cmp.diff }], recommendation: "Revisar diff.", verification: "npm run test:visual" }));
    return ok(salvar(dir, a.specimen, fs, { comparison: cmp, screenshot: shot?.file }), shot ? [shot.buf] : []);
  });

  T("audit_form", "Audita um formulário: rótulos, obrigatórios, envio vazio (validação do servidor), erros anunciados, foco no erro. Envia dados → só em LAB.",
    { ...pg, form: z.string().default("main form") }, async (a) => {
      await requireLab();
      const dir = evidenceDir("audit_form");
      const s = await openSession({ role: a.role });
      await s.page.goto(a.path, { waitUntil: "load" });
      const estrutura = await s.page.locator(a.form).first().evaluate((f) => {
        const campos = [...f.querySelectorAll("input,select,textarea")].filter((i) => !["hidden", "submit", "button"].includes((i as HTMLInputElement).type));
        return campos.map((c) => {
          const id = c.id;
          const label = (id && document.querySelector(`label[for="${id}"]`)) || c.closest("label");
          return { name: (c as HTMLInputElement).name, type: (c as HTMLInputElement).type || c.tagName.toLowerCase(), required: (c as HTMLInputElement).required, hasLabel: !!label || !!c.getAttribute("aria-label") || !!c.getAttribute("aria-labelledby"), describedBy: c.getAttribute("aria-describedby") };
        });
      });
      await s.page.locator(a.form).first().evaluate((f) => ((f as HTMLFormElement).noValidate = true));
      const antes = await screenshot(s.page, dir, "antes", { fullPage: true });
      await s.page.locator(a.form).first().evaluate((f) => (f as HTMLFormElement).requestSubmit());
      await s.page.waitForLoadState("domcontentloaded").catch(() => {});
      const depois = await s.page.evaluate(() => ({
        errors: [...document.querySelectorAll(".form-erro, .errorlist li")].map((e) => e.textContent?.trim()),
        invalid: [...document.querySelectorAll("[aria-invalid=true]")].length,
        errorsWithoutDescribedBy: [...document.querySelectorAll("[aria-invalid=true]")].filter((e) => !e.getAttribute("aria-describedby")).map((e) => (e as HTMLInputElement).name),
        summary: !!document.querySelector("[role=alert], .resumo-erros, .form-erros"),
        focused: document.activeElement?.getAttribute("name") ?? document.activeElement?.tagName,
      }));
      const shotDepois = await screenshot(s.page, dir, "depois-envio-vazio", { fullPage: true });
      await s.context.close();
      const alvo = { type: "page" as const, ref: `${a.path} ${a.form}`, role: a.role };
      const ev = writeJson(path.join(dir, "form.json"), { fields: estrutura, afterEmptySubmit: depois });
      const fs: Finding[] = [];
      const semLabel = estrutura.filter((c) => !c.hasLabel);
      if (semLabel.length) fs.push(finding({ rule: "campo-sem-rotulo", category: "ACCESSIBILITY", severity: "P2", title: `${semLabel.length} campo(s) sem rótulo associado`, detail: semLabel.map((c) => c.name).join(", "), target: alvo, evidence: [{ kind: "file", path: ev }], recommendation: "Usar components/input|select|textarea (label for=id).", verification: "audit_form" }));
      if (depois.invalid && depois.errorsWithoutDescribedBy.length) fs.push(finding({ rule: "erro-nao-anunciado", category: "ACCESSIBILITY", severity: "P2", title: "Campo inválido sem aria-describedby para a mensagem", detail: depois.errorsWithoutDescribedBy.join(", "), target: alvo, evidence: [{ kind: "screenshot", path: shotDepois.file }], recommendation: "aria-describedby apontando para o id do erro.", verification: "audit_form" }));
      if (depois.invalid && !depois.summary && estrutura.length > 10) fs.push(finding({ rule: "sem-resumo-erros", category: "UX", severity: "P3", title: "Formulário longo sem resumo de erros no topo", target: alvo, evidence: [{ kind: "screenshot", path: shotDepois.file }], recommendation: "Resumo com links para os campos (docs/design-system/forms.md).", verification: "audit_form" }));
      if (!depois.invalid && !depois.errors.length) fs.push(finding({ rule: "envio-vazio-aceito", category: "FUNCTIONAL", severity: "P3", title: "Envio vazio não mostrou erro algum (aceito ou redirecionou)", target: alvo, evidence: [{ kind: "screenshot", path: shotDepois.file }], recommendation: "Confirmar se é intencional (rascunho) ou falta validação.", verification: "audit_form" }));
      return ok(salvar(dir, alvo.ref, fs, { fields: estrutura.length, evidence: [antes.file, shotDepois.file, ev] }));
    });

  T("audit_table", "Audita tabelas/listas da página: cabeçalhos, scope, caption, linhas clicáveis, rolagem própria no celular, peso.", pg, async (a) => {
    const dir = evidenceDir("audit_table");
    const s = await openSession({ role: a.role });
    await s.page.goto(a.path, { waitUntil: "load" });
    const info = await s.page.evaluate(() => [...document.querySelectorAll("table")].map((t, i) => {
      const linhas = [...t.querySelectorAll("tbody tr")];
      let rolavel = false;
      for (let p = t.parentElement; p && p !== document.body; p = p.parentElement) { const o = getComputedStyle(p).overflowX; if (o === "auto" || o === "scroll") { rolavel = true; break; } }
      return { index: i, headers: [...t.querySelectorAll("th")].map((h) => h.textContent?.trim()), thWithScope: t.querySelectorAll("th[scope]").length, ths: t.querySelectorAll("th").length, caption: !!t.querySelector("caption") || !!t.getAttribute("aria-label"), rows: linhas.length, rowsWithLink: linhas.filter((r) => r.querySelector("a[href]")).length, scrollContainer: rolavel };
    }));
    await s.page.setViewportSize(VIEWPORTS.mobile);
    await s.page.reload({ waitUntil: "load" });
    const mobile = await layout(s.page);
    const shot = await screenshot(s.page, dir, "mobile", { fullPage: true });
    await s.context.close();
    const alvo = { type: "page" as const, ref: a.path, role: a.role };
    const ev = writeJson(path.join(dir, "tables.json"), { tables: info, mobileLayout: mobile });
    const fs: Finding[] = [];
    for (const t of info) {
      if (t.ths && t.thWithScope < t.ths) fs.push(finding({ rule: "th-sem-scope", category: "ACCESSIBILITY", severity: "P3", title: `Tabela ${t.index}: ${t.ths - t.thWithScope} <th> sem scope`, target: alvo, evidence: [{ kind: "file", path: ev }], recommendation: 'scope="col"/"row".', verification: "audit_table" }));
      if (!t.caption) fs.push(finding({ rule: "tabela-sem-nome", category: "ACCESSIBILITY", severity: "P4", title: `Tabela ${t.index} sem caption/aria-label`, target: alvo, evidence: [{ kind: "file", path: ev }], recommendation: "caption (pode ser sr-only).", verification: "audit_table" }));
      if (t.rows > 0 && t.rowsWithLink === 0) fs.push(finding({ rule: "linha-nao-clicavel", category: "UX", severity: "P3", title: `Tabela ${t.index}: nenhuma linha tem link para o registro`, target: alvo, evidence: [{ kind: "file", path: ev }], recommendation: "Título da linha como <a> (UX-01).", verification: "audit_table" }));
    }
    if (mobile.some((i) => i.kind === "page-overflow-x")) fs.push(finding({ rule: "tabela-transborda", category: "RESPONSIVE", severity: "P2", title: "No celular a página rola na horizontal", target: alvo, evidence: [{ kind: "screenshot", path: shot.file }], recommendation: "Contêiner com overflow-x:auto ou Data List.", verification: "audit_table" }));
    return ok(salvar(dir, a.path, fs, { tables: info }));
  });

  T("audit_modal", "Abre um diálogo pelo gatilho e verifica: abre, nome acessível, aria-modal/showModal, foco dentro, Esc fecha, foco volta ao gatilho.",
    { ...pg, trigger: z.string().describe("seletor CSS do botão que abre o diálogo") }, async (a) => {
      const dir = evidenceDir("audit_modal");
      const s = await openSession({ role: a.role });
      await s.page.goto(a.path, { waitUntil: "load" });
      await s.page.locator(a.trigger).first().focus();
      await s.page.keyboard.press("Enter");
      await s.page.waitForTimeout(300);
      const aberto = await s.page.evaluate(() => {
        const d = document.querySelector("dialog[open], [role=dialog]:not([hidden])") as HTMLElement | null;
        if (!d) return null;
        const nomeId = d.getAttribute("aria-labelledby");
        return { tag: d.tagName.toLowerCase(), id: d.id, name: d.getAttribute("aria-label") || (nomeId ? document.getElementById(nomeId)?.textContent?.trim() : null), modal: d.tagName === "DIALOG" ? (d as HTMLDialogElement).matches(":modal") : d.getAttribute("aria-modal") === "true", focusInside: d.contains(document.activeElement) };
      });
      const shot = await screenshot(s.page, dir, "aberto");
      let fechaEsc = false, focoVoltou = false;
      if (aberto) {
        await s.page.keyboard.press("Escape");
        await s.page.waitForTimeout(250);
        fechaEsc = (await s.page.locator("dialog[open], [role=dialog]:not([hidden])").count()) === 0;
        focoVoltou = await s.page.locator(a.trigger).first().evaluate((el) => el === document.activeElement);
      }
      await s.context.close();
      const alvo = { type: "component" as const, ref: `${a.path} ${a.trigger}`, role: a.role };
      const ev = writeJson(path.join(dir, "modal.json"), { opened: aberto, closesOnEsc: fechaEsc, focusReturns: focoVoltou });
      const fs: Finding[] = [];
      const add = (c: boolean, rule: string, sev: Finding["severity"], title: string, rec: string) => c && fs.push(finding({ rule, category: "ACCESSIBILITY", severity: sev, title, target: alvo, evidence: [{ kind: "file", path: ev }, { kind: "screenshot", path: shot.file }], recommendation: rec, verification: "audit_modal" }));
      add(!aberto, "nao-abre-teclado", "P2", "Diálogo não abriu com Enter no gatilho", "Gatilho deve ser <button>.");
      if (aberto) {
        add(!aberto.name, "sem-nome", "P2", "Diálogo sem nome acessível", "aria-labelledby no título.");
        add(!aberto.modal, "nao-modal", "P3", "Diálogo não é modal (showModal/aria-modal)", "dialog.showModal().");
        add(!aberto.focusInside, "foco-fora", "P2", "Foco não entrou no diálogo", "Foco no 1º controle ao abrir.");
        add(!fechaEsc, "esc", "P2", "Esc não fecha", "Tratar cancel/Esc.");
        add(fechaEsc && !focoVoltou, "foco-volta", "P3", "Foco não volta ao gatilho", "Devolver foco ao fechar.");
      }
      return ok(salvar(dir, alvo.ref, fs));
    });

  T("audit_navigation", "Audita a navegação da página: itens por barra, item ativo (aria-current), overflow por viewport.", pg, async (a) => {
    const dir = evidenceDir("audit_nav");
    const s = await openSession({ role: a.role });
    await s.page.goto(a.path, { waitUntil: "load" });
    const navs = await s.page.evaluate(() => [...document.querySelectorAll("nav")].map((n) => ({ label: n.getAttribute("aria-label"), items: n.querySelectorAll("a").length, current: [...n.querySelectorAll("[aria-current]")].map((c) => c.textContent?.trim()), cls: n.className })));
    const porVp: Record<string, boolean> = {};
    for (const vp of ["desktop", "laptop", "tablet", "mobile"] as ViewportName[]) {
      await s.page.setViewportSize(VIEWPORTS[vp]);
      await s.page.reload({ waitUntil: "load" });
      porVp[vp] = (await layout(s.page)).some((i) => i.kind === "page-overflow-x");
    }
    await s.context.close();
    const alvo = { type: "page" as const, ref: a.path, role: a.role };
    const ev = writeJson(path.join(dir, "nav.json"), { navs, overflowByViewport: porVp });
    const fs: Finding[] = [];
    for (const n of navs) {
      if (n.items > 9) fs.push(finding({ rule: "nav-itens-demais", category: "UX", severity: "P3", title: `Navegação "${n.label ?? n.cls}" com ${n.items} itens`, target: alvo, evidence: [{ kind: "file", path: ev }], recommendation: "≤ 7 visíveis; agrupar ou 'Mais' (docs/design-system/navigation.md).", verification: "audit_navigation" }));
      if (!n.label) fs.push(finding({ rule: "nav-sem-nome", category: "ACCESSIBILITY", severity: "P4", title: "<nav> sem aria-label", target: alvo, evidence: [{ kind: "file", path: ev }], recommendation: "Nomear navs quando houver mais de uma.", verification: "audit_navigation" }));
    }
    for (const [vp, ov] of Object.entries(porVp)) if (ov) fs.push(finding({ rule: "overflow-x", category: "RESPONSIVE", severity: "P2", title: `Rolagem horizontal em ${vp}`, target: alvo, evidence: [{ kind: "file", path: ev }], recommendation: "Ver KP-04.", verification: "audit_navigation" }));
    return ok(salvar(dir, a.path, fs, { navs }));
  });

  T("audit_static", "Auditoria estática (CSS, templates, código, rotas, duplicação) → achados no formato comum.", {}, async () => {
    const r = await manageJson(["agent_audit_static"]);
    const f = readJson<{ findings: Finding[] }>("reports/audit/static-findings.json");
    return ok({ summary: r, top: f?.findings.filter((x) => ["P0", "P1", "P2"].includes(x.severity)), evidence: ["reports/audit/static-findings.json", "reports/audit/static-findings.md"] });
  });
}
