/** git_*, report_*, agent_* — git somente-leitura + checkpoint, relatórios e meta-ferramentas do agente. */
import { existsSync, readFileSync, readdirSync } from "node:fs";
import path from "node:path";
import { z } from "zod";
import type { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { ROOT, evidenceDir, gitSync, manageJson, ok, pythonExec, readJson, rel, run, safe, writeJson, type Finding } from "./util.ts";
import { runPlaywright } from "./lab.ts";

function frontmatter(txt: string) {
  const m = txt.match(/^---\n([\s\S]*?)\n---/);
  if (!m) return null;
  return Object.fromEntries(m[1].split("\n").filter((l) => l.includes(":")).map((l) => [l.slice(0, l.indexOf(":")).trim(), l.slice(l.indexOf(":") + 1).trim()]));
}

export function registerAgentOps(server: McpServer) {
  const T = (name: string, description: string, shape: z.ZodRawShape, fn: (a: any) => Promise<ReturnType<typeof ok>>) =>
    server.registerTool(name, { description, inputSchema: shape }, safe(fn));

  // ---- git (leitura + checkpoint; nada destrutivo)
  T("git_status", "Branch, commits à frente do remoto, arquivos alterados.", {}, async () => ok({ branch: gitSync(["branch", "--show-current"]), status: gitSync(["status", "--porcelain=v1", "-b"]).split("\n").slice(0, 200), lastCommit: gitSync(["log", "-1", "--format=%h %s (%ar)"]) }));
  T("git_diff", "Diff do working tree (ou staged, ou contra uma ref) — estatística e patch truncado.", { ref: z.string().default(""), staged: z.boolean().default(false), path: z.string().default(""), maxChars: z.number().default(20000) }, async (a) => {
    const base = ["diff", ...(a.staged ? ["--cached"] : []), ...(a.ref ? [a.ref] : [])];
    const alvo = a.path ? ["--", a.path] : [];
    const patch = gitSync([...base, ...alvo]);
    return ok({ stat: gitSync([...base, "--stat", ...alvo]), patch: patch.slice(0, a.maxChars), truncated: patch.length > a.maxChars });
  });
  T("git_history", "Histórico recente (opcionalmente de um caminho).", { n: z.number().default(15), path: z.string().default("") }, async (a) => ok(gitSync(["log", `-${a.n}`, "--format=%h|%ad|%an|%s", "--date=short", ...(a.path ? ["--", a.path] : [])]).split("\n").map((l) => { const [h, d, au, s] = l.split("|"); return { hash: h, date: d, author: au, subject: s }; })));
  T("git_create_checkpoint", "Cria uma tag de checkpoint (checkpoint/AAAAMMDD-HHMM-<assunto>) no HEAD. Recusa se houver alterações não commitadas, a menos que allowDirty.", { subject: z.string().regex(/^[a-z0-9-]{2,40}$/), allowDirty: z.boolean().default(false) }, async (a) => {
    const sujo = gitSync(["status", "--porcelain"]);
    if (sujo && !a.allowDirty) throw new Error("há alterações não commitadas — commite antes ou use allowDirty (a tag aponta para o HEAD, não inclui o WIP)");
    const agora = new Date().toISOString().replace(/[-:T]/g, "").slice(0, 12);
    const tag = `checkpoint/${agora.slice(0, 8)}-${agora.slice(8, 12)}-${a.subject}`;
    const out = gitSync(["tag", tag]);
    return ok({ tag, head: gitSync(["rev-parse", "--short", "HEAD"]), output: out, rollback: `git checkout ${tag}  # ou: git reset --hard ${tag} (destrutivo)` });
  });

  // ---- relatórios
  T("report_generate_audit_report", "Consolida arquivos findings.json (das auditorias) num relatório Markdown priorizado.", { findingsFiles: z.array(z.string()).describe("caminhos findings.json (de audit_*)"), title: z.string().default("Relatório de auditoria") }, async (a) => {
    const todos: Finding[] = [];
    for (const f of a.findingsFiles) todos.push(...(readJson<{ findings: Finding[] }>(f)?.findings ?? []));
    const vistos = new Set<string>();
    const unicos = todos.filter((f) => !vistos.has(f.id) && vistos.add(f.id));
    const ordem = { P0: 0, P1: 1, P2: 2, P3: 3, P4: 4 };
    unicos.sort((x, y) => ordem[x.severity] - ordem[y.severity]);
    const md = [`# ${a.title}`, "", `Gerado em ${new Date().toISOString()} a partir de ${a.findingsFiles.length} arquivo(s).`, "", "| Sev. | Categoria | Achado | Alvo | Evidência | Como verificar |", "|---|---|---|---|---|---|",
      ...unicos.map((f) => `| ${f.severity} | ${f.category} | ${f.title.replace(/\|/g, "/")} | \`${f.target.ref}\` | ${f.evidence.map((e) => e.path ?? e.value).filter(Boolean).slice(0, 2).join("<br>")} | ${f.verification ?? ""} |`),
      "", "## Recomendações", "", ...unicos.map((f) => `- **${f.severity} ${f.title}** — ${f.recommendation}`)];
    const dir = evidenceDir("audit_report");
    const file = path.join(dir, "report.md");
    (await import("node:fs")).writeFileSync(file, md.join("\n") + "\n");
    return ok({ report: rel(file), findings: unicos.length, by_severity: unicos.reduce((m, f) => ({ ...m, [f.severity]: (m[f.severity as keyof typeof m] ?? 0) + 1 }), {} as Record<string, number>) });
  });
  T("report_generate_regression_report", "Roda regression + a11y + responsive + visual e compara com as catracas/baselines: o que piorou, o que melhorou.", {}, async () => {
    const res: Record<string, unknown> = {};
    for (const p of ["regression", "a11y", "responsive", "visual"]) res[p] = await runPlaywright(p);
    const a11yBase = readJson<Record<string, { critical: number; serious: number }>>("tests/a11y/baseline.json") ?? {};
    const melhorias: string[] = [];
    for (const f of existsSync(path.join(ROOT, "reports/accessibility")) ? readdirSync(path.join(ROOT, "reports/accessibility")).filter((x) => x.endsWith(".json")) : []) {
      const r = readJson<{ page?: { id: string }; counts: { critical: number; serious: number } }>(`reports/accessibility/${f}`);
      const id = r?.page?.id; const b = id ? a11yBase[id] : undefined;
      if (r && b && (r.counts.critical < b.critical || r.counts.serious < b.serious)) melhorias.push(`${id}: a11y ${b.critical}/${b.serious} → ${r.counts.critical}/${r.counts.serious} (aperte a catraca)`);
    }
    const dir = evidenceDir("regression_report");
    const ev = writeJson(path.join(dir, "regression.json"), { results: res, improvements: melhorias });
    return ok({ ok: Object.values(res).every((r) => (r as { ok: boolean }).ok), results: res, improvements: melhorias, evidence: [ev] });
  });
  T("report_generate_health_report", "Health check do laboratório (14 checagens) → reports/agent-health.md.", { quick: z.boolean().default(true) }, async (a) => {
    const r = await run(pythonExec(), [path.join(ROOT, "scripts/agent/lab.py"), "health", ...(a.quick ? ["--quick"] : [])], { timeoutMs: 1_200_000 });
    return ok({ ok: r.code === 0, output: r.stdout.slice(-3000), report: "reports/agent-health.md", json: readJson("reports/agent/health.json") });
  });
  T("report_generate_page_report", "Relatório completo de uma página: inspeção (rota/template/componentes/estados) + auditoria de runtime (audit-page.mjs) → Markdown.", { path: z.string(), role: z.string().default("admin"), viewports: z.string().default("desktop,tablet,mobile") }, async (a) => {
    const insp: Record<string, any> = await manageJson<Record<string, any>>(["agent_query", "page", a.path]).catch((e) => ({ error: String(e) }));
    const r = await run(process.execPath, ["tests/tools/audit-page.mjs", "--path", a.path, "--role", a.role, "--viewports", a.viewports], { timeoutMs: 600_000 });
    const pasta = r.stdout.match(/Evidências em (.+)\//)?.[1];
    if (!pasta) throw new Error(`audit-page falhou: ${(r.stderr || r.stdout).slice(-1200)}`);
    const f = readJson<{ summary: Record<string, unknown>; findings: Finding[] }>(path.join(pasta, "findings.json"))!;
    const md = [`# Página ${a.path} (${a.role})`, "", "## Estrutura", "", `- Template: \`${insp.template ?? "?"}\` (${insp.lines ?? "?"} linhas) · layout: ${(insp.extends ?? []).join(", ")}`,
      `- Componentes: ${(insp.components ?? []).map((c: string) => `\`${c}\``).join(", ")}`, `- Estados detectados: ${insp.states ? Object.entries(insp.states).filter(([k, v]) => k !== "template" && v).map(([k]) => k).join(", ") : "?"}`,
      `- Arquétipo: ${insp.key_page?.archetype ?? "não é página-chave"}`, "", "## Achados", "", `Resumo: ${JSON.stringify(f.summary.by_severity ?? {})}`, "",
      ...f.findings.map((x) => `- **${x.severity} · ${x.category}** — ${x.title}${x.detail ? ` — ${String(x.detail).slice(0, 160)}` : ""}\n  - Recomendação: ${x.recommendation}`),
      "", "## Evidências", "", `Pasta: \`${pasta}/\` (capturas por viewport, axe.json, layout.json, console.json, perf.json, dom.json).`];
    const file = path.join(ROOT, pasta, "REPORT.md");
    (await import("node:fs")).writeFileSync(file, md.join("\n") + "\n");
    return ok({ report: rel(file), summary: f.summary, findings: f.findings.length, inspection: { template: insp.template, components: insp.components } });
  });

  T("report_command_center", "Consolida saúde, testes, a11y, responsivo, desempenho, segurança, dívidas, migração e problemas no contrato do Command Center (reports/agent/command-center.json).", {}, async () => {
    const r = await run(pythonExec(), [path.join(ROOT, "scripts/agent/command_center.py")]);
    if (r.code !== 0) throw new Error(r.stderr.slice(-1000));
    return ok({ ...JSON.parse(r.stdout.trim().split("\n").at(-1)!), data: readJson("reports/agent/command-center.json") });
  });

  // ---- meta do agente
  T("agent_list_skills", "Skills do projeto (.claude/skills) com descrição.", {}, async () => {
    const d = path.join(ROOT, ".claude/skills");
    return ok(readdirSync(d).filter((n) => existsSync(path.join(d, n, "SKILL.md"))).map((n) => ({ name: n, description: frontmatter(readFileSync(path.join(d, n, "SKILL.md"), "utf-8"))?.description })));
  });
  T("agent_list_agents", "Subagentes do projeto (.claude/agents) com descrição e ferramentas.", {}, async () => {
    const d = path.join(ROOT, ".claude/agents");
    return ok(readdirSync(d).filter((n) => n.endsWith(".md")).map((n) => { const fm = frontmatter(readFileSync(path.join(d, n), "utf-8")); return { name: fm?.name, description: fm?.description, tools: fm?.tools }; }));
  });
  T("agent_get_pipeline", "Pipeline do orquestrador (fases → agente → skills → ferramentas → critério de saída). Sem nome: lista.", { name: z.string().default("") }, async (a) => {
    const d = path.join(ROOT, "docs/agent/pipelines");
    if (!a.name) return ok(readdirSync(d).filter((n) => n.endsWith(".json")).map((n) => ({ name: n.replace(".json", ""), description: readJson<{ description: string }>(path.join(d, n))?.description })));
    const p = readJson(path.join(d, `${a.name}.json`));
    if (!p) throw new Error(`pipeline ${a.name} não existe`);
    return ok(p);
  });
  T("agent_select_tool", "Política de seleção: dada uma capacidade (ex. 'acessibilidade de página'), devolve a ferramenta mais específica do registro e as alternativas.", { capability: z.string() }, async (a) => {
    const reg = readJson<{ tools: { name: string; category: string; purpose: string; status: string; replacement?: string | null }[] }>("docs/agent/tool-registry.json");
    if (!reg) throw new Error("docs/agent/tool-registry.json ausente");
    const q = a.capability.normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLowerCase().split(/\W+/).filter((x: string) => x.length > 2);
    const pont = reg.tools.map((t) => {
      const alvo = `${t.name} ${t.category} ${t.purpose}`.normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLowerCase();
      return { t, s: q.filter((w: string) => alvo.includes(w)).length + (t.status === "READY" ? 0.5 : 0) };
    }).filter((x) => x.s >= 1).sort((x, y) => y.s - x.s);
    return ok({ capability: a.capability, best: pont[0]?.t ?? null, alternatives: pont.slice(1, 5).map((x) => x.t), policy: "docs/agent/tool-selection-policy.md" });
  });
  T("agent_doctor", "Diagnóstico do agente (dependências, navegador, MCP, skills, agentes, scripts, banco, docs). fix=true tenta auto-recuperar o que for seguro.", { fix: z.boolean().default(false) }, async (a) => {
    const r = await run(pythonExec(), [path.join(ROOT, "scripts/agent/doctor.py"), "--json", ...(a.fix ? ["--fix"] : [])], { timeoutMs: 900_000 });
    const ini = r.stdout.indexOf("{");
    if (ini < 0) throw new Error((r.stderr || r.stdout).slice(-1500));
    return ok(JSON.parse(r.stdout.slice(ini)));
  });
}
