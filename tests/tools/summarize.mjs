#!/usr/bin/env node
// Consolida as evidências gravadas pelos testes em resumos Markdown.
//   node tests/tools/summarize.mjs a11y [--update-baseline]
//   node tests/tools/summarize.mjs perf
//   node tests/tools/summarize.mjs responsive
import { existsSync, readdirSync, readFileSync, writeFileSync, mkdirSync, statSync } from "node:fs";
import path from "node:path";

const [, , alvo, ...flags] = process.argv;
const lerJson = (f) => JSON.parse(readFileSync(f, "utf-8"));
const jsons = (dir) => (existsSync(dir) ? readdirSync(dir).filter((f) => f.endsWith(".json")).sort().map((f) => path.join(dir, f)) : []);

function a11y() {
  const dir = "reports/accessibility";
  mkdirSync(dir, { recursive: true });
  const l = ["# Acessibilidade (axe) — páginas-chave", "", "| Página | critical | serious | moderate | minor | Regras |", "|---|---|---|---|---|---|"];
  const total = { critical: 0, serious: 0, moderate: 0, minor: 0 };
  const base = {};
  for (const f of jsons(dir)) {
    const r = lerJson(f);
    if (!r.counts) continue;
    const id = r.page?.id ?? path.basename(f, ".json");
    for (const k of Object.keys(total)) total[k] += r.counts[k];
    base[id] = { critical: r.counts.critical, serious: r.counts.serious };
    l.push(`| ${id} | ${r.counts.critical} | ${r.counts.serious} | ${r.counts.moderate} | ${r.counts.minor} | ${r.violations.map((v) => `${v.id}×${v.nodes}`).join(", ")} |`);
  }
  l.push(`| **Total** | ${total.critical} | ${total.serious} | ${total.moderate} | ${total.minor} | |`);
  writeFileSync(`${dir}/summary.md`, l.join("\n") + "\n");
  if (flags.includes("--update-baseline")) {
    const sorted = Object.fromEntries(Object.entries(base).sort(([a], [b]) => a.localeCompare(b)));
    writeFileSync("tests/a11y/baseline.json", JSON.stringify(sorted, null, 2) + "\n");
    console.log("baseline de acessibilidade atualizado");
  }
  console.log(`${dir}/summary.md`);
}

function perf() {
  const dir = "reports/performance";
  mkdirSync(dir, { recursive: true });
  const l = ["# Desempenho (laboratório) — páginas-chave", "", "| Página | TTFB ms | LCP ms | CLS | long tasks | req | HTML KB | JS KB | CSS KB | bloqueantes |", "|---|---|---|---|---|---|---|---|---|---|"];
  for (const f of jsons(dir)) {
    const { page, metrics: m } = lerJson(f);
    if (!m) continue;
    l.push(`| ${page} | ${m.ttfbMs} | ${m.lcpMs} | ${m.cls} | ${m.longTasks} | ${m.requests} | ${m.htmlKB} | ${m.jsKB} | ${m.cssKB} | ${m.blocking.length} |`);
  }
  writeFileSync(`${dir}/summary.md`, l.join("\n") + "\n");
  console.log(`${dir}/summary.md`);
}

function responsive() {
  const raiz = "reports/responsive";
  if (!existsSync(raiz)) return;
  const l = ["# Responsividade — achados de layout por página e viewport", "", "| Página | Viewport | overflow página | vazamentos | texto cortado | alvos < 24px |", "|---|---|---|---|---|---|"];
  for (const pg of readdirSync(raiz).sort()) {
    const d = path.join(raiz, pg);
    if (!statSync(d).isDirectory()) continue;
    for (const f of jsons(d)) {
      const r = lerJson(f);
      const c = (k) => r.issues.filter((i) => i.kind === k).length;
      l.push(`| ${pg} | ${path.basename(f, ".json")} | ${c("page-overflow-x") ? "⚠️" : "—"} | ${c("element-overflow")} | ${c("clipped-text")} | ${c("tiny-target")} |`);
    }
  }
  writeFileSync(`${raiz}/summary.md`, l.join("\n") + "\n");
  if (flags.includes("--update-baseline")) {
    const overflow = [];
    for (const pg of readdirSync(raiz).sort()) {
      const d = path.join(raiz, pg);
      if (!statSync(d).isDirectory()) continue;
      for (const f of jsons(d)) if (lerJson(f).issues.some((i) => i.kind === "page-overflow-x")) overflow.push(`${pg}@${path.basename(f, ".json")}`);
    }
    writeFileSync("tests/responsive/baseline.json", JSON.stringify({ overflow }, null, 2) + "\n");
    console.log(`baseline responsivo: ${overflow.length} combinação(ões) com overflow toleradas`);
  }
  console.log(`${raiz}/summary.md`);
}

mkdirSync("reports", { recursive: true });
const fn = { a11y, perf, responsive }[alvo];
if (fn) fn();
else {
  console.error("uso: summarize.mjs a11y|perf|responsive [--update-baseline]");
  process.exit(2);
}
