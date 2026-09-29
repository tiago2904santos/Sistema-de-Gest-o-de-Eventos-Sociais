/**
 * agent:self-test — prova, pelo protocolo MCP real, que o agente consegue trabalhar sozinho.
 * Cada passo chama ferramentas do project-mcp e verifica o resultado (não só "não deu erro").
 * Relatório: reports/agent/self-test.{json,md}. Código de saída ≠ 0 se algum passo falhar.
 *
 *   npm run agent:self-test            (completo, ~4–6 min)
 *   npm run agent:self-test -- --quick (sem suítes Playwright)
 */
import { mkdirSync, writeFileSync } from "node:fs";
import path from "node:path";
import { call, connect, ROOT, type CallResult } from "./client.ts";

const quick = process.argv.includes("--quick");
const c = await connect();
type Step = { n: number; name: string; tools: string[]; ok: boolean; detail: string; ms: number; evidence: string[] };
const steps: Step[] = [];

async function step(name: string, fn: () => Promise<{ ok: boolean; detail: string; tools: string[]; evidence?: string[] }>) {
  const t0 = Date.now();
  let r: { ok: boolean; detail: string; tools: string[]; evidence?: string[] };
  try { r = await fn(); } catch (e) { r = { ok: false, detail: (e as Error).message.slice(0, 400), tools: [] }; }
  const s = { n: steps.length + 1, name, tools: r.tools, ok: r.ok, detail: r.detail, ms: Date.now() - t0, evidence: r.evidence ?? [] };
  steps.push(s);
  console.log(`${s.ok ? "✓" : "✗"} ${String(s.n).padStart(2)} ${name} (${s.ms} ms) — ${s.detail.slice(0, 140)}`);
}
const must = (r: CallResult, what: string) => { if (!r.ok) throw new Error(`${what}: ${JSON.stringify(r.data).slice(0, 300)}`); return r.data; };

const tools = (await c.listTools()).tools.map((t) => t.name);

await step("Descobrir uma página (rota → view → template → componentes)", async () => {
  const r = must(await call(c, "project_inspect_route", { route: "/viagens/oficios/" }), "rota");
  const p = must(await call(c, "project_inspect_page", { page: "/viagens/oficios/" }), "página");
  return { ok: r.view === "viagens_oficios.views.lista" && p.template === "pages/viagens_oficios/lista.html" && p.components.length > 3,
    detail: `${r.view} em ${r.file}:${r.line} → ${p.template} com ${p.components.length} componentes`, tools: ["project_inspect_route", "project_inspect_page"] };
});
await step("Iniciar o laboratório (LAB, sem migração pendente)", async () => {
  const h = must(await call(c, "lab_start"), "lab");
  return { ok: h.environment === "LAB" && Array.isArray(h.pending_migrations) && h.pending_migrations.length === 0, detail: `ambiente ${h.environment}, relógio ${h.server_now}`, tools: ["lab_start"] };
});
let sess = "";
await step("Abrir a página com Playwright como viagensGestor", async () => {
  const r = must(await call(c, "browser_open_page", { path: "/viagens/oficios/", role: "viagensGestor" }), "open");
  sess = r.session;
  return { ok: r.status === 200 && r.h1.includes("Ofícios") && r.evidence.length === 1, detail: `sessão ${r.session}, h1=${r.h1}`, tools: ["browser_open_page"], evidence: r.evidence };
});
await step("Capturar screenshot da página inteira", async () => {
  const r = await call(c, "browser_capture_full_page", { session: sess });
  const d = must(r, "full page");
  return { ok: r.images === 1 || d.evidence.length === 1, detail: `${d.evidence[0]} (imagem inline: ${r.images})`, tools: ["browser_capture_full_page"], evidence: d.evidence };
});
await step("Consultar a árvore de acessibilidade", async () => {
  const d = must(await call(c, "browser_inspect_accessibility_tree", { session: sess, selector: "main" }), "aria");
  return { ok: /heading "Ofícios"/.test(d.snapshot), detail: `${d.snapshot.split("\n").length} linhas; contém heading "Ofícios"`, tools: ["browser_inspect_accessibility_tree"], evidence: d.evidence };
});
await step("Executar Axe (auditoria de acessibilidade com achados P0–P4)", async () => {
  const d = must(await call(c, "audit_accessibility", { path: "/viagens/oficios/", role: "viagensGestor" }), "axe");
  const temContraste = d.findings.some((f: { rule: string }) => f.rule === "axe:color-contrast");
  return { ok: d.summary.total > 0 && temContraste && d.findings.every((f: any) => f.severity && f.evidence && f.recommendation !== undefined && f.verification),
    detail: `${d.summary.total} achados ${JSON.stringify(d.summary.by_severity)}; color-contrast presente (KP-03 confirmado)`, tools: ["audit_accessibility"], evidence: [d.evidence_file] };
});
await step("Consultar o DOM", async () => {
  const d = must(await call(c, "browser_inspect_dom", { session: sess }), "dom");
  return { ok: d.nodes > 500 && d.interactive > 20, detail: `${d.nodes} nós, ${d.interactive} interativos, ${d.forms.length} formulários`, tools: ["browser_inspect_dom"] };
});
await step("Teste de interação (fluxo com busca + trace)", async () => {
  const d = must(await call(c, "browser_run_page_flow", { role: "viagensGestor", steps: [
    { action: "goto", target: "/viagens/oficios/" },
    { action: "fill", target: "input[name=q]", value: "termo-inexistente-xyz" },
    { action: "press", value: "Enter" },
    { action: "expect_text", target: "main", value: "Nenhum" },
  ] }), "flow");
  return { ok: d.passed && !!d.trace, detail: `${d.steps.length} passos, trace ${d.trace}`, tools: ["browser_run_page_flow"], evidence: [d.trace, ...d.steps.map((s: any) => s.evidence)] };
});
await step("Comparar screenshot com o baseline", async () => {
  const d = must(await call(c, "audit_visual", { key: "oficios-lista" }), "visual");
  return { ok: typeof d.comparison?.diffRatio === "number" && !!d.comparison.diff, detail: `diff ${(d.comparison.diffRatio * 100).toFixed(3)}% vs ${d.baseline} (${d.summary.total} achado)`, tools: ["audit_visual"], evidence: [d.comparison.diff] };
});
await step("Consultar o inventário (resumo + uso de componente)", async () => {
  const s = must(await call(c, "inventory_get_ui_inventory", { section: "summary" }), "summary");
  const u = must(await call(c, "inventory_get_component_usage", { component: "page_header" }), "uso");
  return { ok: s.routes > 500 && u.used_by_count > 0, detail: `${s.routes} rotas, ${s.pages} páginas; page_header usado ${u.used_by_count}×`, tools: ["inventory_get_ui_inventory", "inventory_get_component_usage"] };
});
await step("Consultar o design system (tokens + conhecimento)", async () => {
  const t = must(await call(c, "inventory_get_design_tokens", { category: "color" }), "tokens");
  const k = must(await call(c, "knowledge_search_design_system", { query: "contraste rótulo cinza" }), "ks");
  return { ok: t.count > 50 && k.results.length > 0, detail: `${t.count} tokens de cor; 1º trecho: ${k.results[0].source}`, tools: ["inventory_get_design_tokens", "knowledge_search_design_system"] };
});
await step("Consultar a memória do projeto (problemas conhecidos)", async () => {
  const p = must(await call(c, "inventory_get_known_problems", { severity: "P1" }), "kp");
  const k = must(await call(c, "knowledge_search_known_problems", { query: "exclusão servidor prestações cascata" }), "k");
  const fonte = k.results.slice(0, 3).find((r: { source: string }) => r.source.includes("known-problems"));
  return { ok: p.count >= 2 && !!fonte, detail: `${p.count} problemas P1; busca → ${fonte?.source ?? k.results[0]?.source}`, tools: ["inventory_get_known_problems", "knowledge_search_known_problems"] };
});
await step(quick ? "Executar testes (agent_lab, Django)" : "Executar testes (smoke Playwright + agent_lab)", async () => {
  const dj = must(await call(c, "testing_run_django_tests", { labels: ["agent_lab"] }), "django");
  if (quick) return { ok: dj.ok, detail: dj.summary, tools: ["testing_run_django_tests"] };
  const sm = must(await call(c, "testing_run_smoke_tests", {}), "smoke");
  return { ok: dj.ok && sm.ok, detail: `django: ${dj.summary}; smoke: ${sm.stats?.expected} ok / ${sm.stats?.unexpected} falhas`, tools: ["testing_run_django_tests", "testing_run_smoke_tests"] };
});
await step("Gerar relatório (consolidar achados)", async () => {
  const achados = steps.flatMap((s) => s.evidence).filter((e) => e?.endsWith("findings.json"));
  const d = must(await call(c, "report_generate_audit_report", { findingsFiles: achados, title: "Self-test — ofícios" }), "report");
  return { ok: d.findings > 0 && !!d.report, detail: `${d.findings} achados em ${d.report}`, tools: ["report_generate_audit_report"], evidence: [d.report] };
});
await step("Verificar Git", async () => {
  const s = must(await call(c, "git_status"), "status");
  const h = must(await call(c, "git_history", { n: 3 }), "hist");
  return { ok: s.branch !== "main" && h.length === 3, detail: `branch ${s.branch}; último: ${h[0].subject.slice(0, 60)}`, tools: ["git_status", "git_history"] };
});
// Extras (capacidades novas da missão 2)
await step("Banco: ambiente + EXPLAIN somente leitura + recusa de escrita", async () => {
  const e = must(await call(c, "db_environment"), "env");
  const x = must(await call(c, "db_explain", { sql: "SELECT id FROM viagens_oficios_oficio WHERE protocolo = '1'" }), "explain");
  const recusa = await call(c, "db_explain", { sql: "DELETE FROM viagens_oficios_oficio" });
  return { ok: e.environment === "LAB" && x.plan.length > 0 && !recusa.ok, detail: `${e.environment}; plano: ${x.plan.slice(0, 60)}; DELETE recusado`, tools: ["db_environment", "db_explain"] };
});
await step("Observabilidade: requisições com nº de SQL e Server-Timing", async () => {
  const d = must(await call(c, "obs_get_requests", { path: "/viagens/oficios/", limit: 5 }), "obs");
  return { ok: d.requests.length > 0 && typeof d.requests.at(-1).queries === "number", detail: `${d.requests.length} registros; última: ${d.requests.at(-1)?.duration_ms} ms, ${d.requests.at(-1)?.queries} consultas`, tools: ["obs_get_requests"] };
});
await step("Seleção de ferramenta + pipeline do orquestrador", async () => {
  const s = must(await call(c, "agent_select_tool", { capability: "acessibilidade de uma página" }), "select");
  const p = must(await call(c, "agent_get_pipeline", { name: "audit-module" }), "pipeline");
  return { ok: !!s.best && p.phases.length >= 4, detail: `melhor: ${s.best?.name}; audit-module com ${p.phases.length} fases`, tools: ["agent_select_tool", "agent_get_pipeline"] };
});
await step("Contratos de API", async () => {
  const d = must(await call(c, "api_check_contracts"), "api");
  return { ok: d.ok && Array.isArray(d.breaking) && d.breaking.length === 0, detail: `${d.endpoints?.length} endpoints; quebras: ${d.breaking?.length}`, tools: ["api_check_contracts"] };
});
await c.callTool({ name: "browser_close", arguments: { all: true } }).catch(() => {});
await c.close();

const okTotal = steps.every((s) => s.ok);
const dir = path.join(ROOT, "reports", "agent");
mkdirSync(dir, { recursive: true });
const res = { ok: okTotal, generated_at: new Date().toISOString(), mcp_tools: tools.length, quick, steps };
writeFileSync(path.join(dir, "self-test.json"), JSON.stringify(res, null, 2));
writeFileSync(path.join(dir, "self-test.md"), [`# agent:self-test — ${okTotal ? "PASSOU" : "FALHOU"}`, "", `${res.generated_at} · project-mcp com ${tools.length} ferramentas`, "",
  "| # | Passo | Ferramentas | OK | ms | Detalhe |", "|---|---|---|---|---|---|",
  ...steps.map((s) => `| ${s.n} | ${s.name} | ${s.tools.map((t) => `\`${t}\``).join(" ")} | ${s.ok ? "✅" : "❌"} | ${s.ms} | ${s.detail.replace(/\|/g, "/").slice(0, 200)} |`)].join("\n") + "\n");
console.log(`\n${okTotal ? "PASSOU" : "FALHOU"} — ${steps.filter((s) => s.ok).length}/${steps.length} passos → reports/agent/self-test.md`);
process.exit(okTotal ? 0 : 1);
