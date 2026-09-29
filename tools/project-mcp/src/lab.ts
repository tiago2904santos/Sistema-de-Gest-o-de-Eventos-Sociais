/** lab_* — ciclo de vida do laboratório; testing_* — suítes; db_*, api_*, obs_* — dados e runtime. */
import { readFileSync, existsSync } from "node:fs";
import path from "node:path";
import { z } from "zod";
import type { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { BASE_URL, ROOT, ensureServer, evidenceDir, labHealth, manage, manageJson, ok, pythonExec, rel, run, safe, writeJson } from "./util.ts";

const PROJETOS = ["smoke", "e2e", "regression", "a11y", "visual", "responsive", "perf"] as const;

type PwStats = { expected: number; unexpected: number; flaky: number; skipped: number; duration: number };

/** Roda um projeto Playwright com reporter JSON e resume passes/falhas. */
export async function runPlaywright(project: string, grep?: string) {
  const args = ["playwright", "test", `--project=${project}`, "--reporter=json"];
  if (grep) args.push("-g", grep);
  const r = await run("npx", args, { timeoutMs: 1_200_000, env: { PLAYWRIGHT_JSON_OUTPUT_NAME: "" } });
  const ini = r.stdout.indexOf("{");
  if (ini < 0) return { project, ok: false, error: (r.stderr || r.stdout).slice(-2000) };
  const j = JSON.parse(r.stdout.slice(ini)) as { stats: PwStats; suites: unknown[]; errors?: { message?: string }[] };
  const falhas: { title: string; file: string; error: string }[] = [];
  const walk = (s: any) => {
    for (const sp of s.specs ?? []) for (const t of sp.tests ?? []) for (const res of t.results ?? [])
      if (res.status !== "passed" && res.status !== "skipped" && t.expectedStatus !== res.status)
        falhas.push({ title: sp.title, file: sp.file, error: String(res.errors?.[0]?.message ?? res.error?.message ?? "").replace(/\x1b\[[0-9;]*m/g, "").slice(0, 600) });
    for (const c of s.suites ?? []) walk(c);
  };
  for (const s of j.suites) walk(s);
  const erros = (j.errors ?? []).map((e) => String(e.message ?? "").replace(/\x1b\[[0-9;]*m/g, "").slice(0, 600));
  // "ok" exige que algo tenha rodado: 0 testes (ex.: globalSetup quebrado) é falha, não sucesso.
  return { project, ok: j.stats.unexpected === 0 && j.stats.expected + j.stats.flaky > 0 && erros.length === 0, stats: j.stats, errors: erros, failures: falhas.slice(0, 30) };
}

export function registerLab(server: McpServer) {
  const T = (name: string, description: string, shape: z.ZodRawShape, fn: (a: any) => Promise<ReturnType<typeof ok>>) =>
    server.registerTool(name, { description, inputSchema: shape }, safe(fn));

  // ---- laboratório
  T("lab_status", "Estado do laboratório: servidor no ar?, ambiente (LAB/DEV/…), migrações pendentes, relógio, usuários.", {}, async () => ok({ url: BASE_URL, health: await labHealth() }));
  T("lab_start", "Sobe o servidor do laboratório (se não estiver no ar) e devolve a sonda de saúde.", {}, async () => ok(await ensureServer()));
  T("lab_list_scenarios", "Cenários de seed disponíveis (embutidos e sob medida em tests/scenarios/).", {}, async () => {
    const r = await run(pythonExec(), [path.join(ROOT, "scripts/agent/lab.py"), "manage", "shell", "-v", "0", "-c", "import json;from agent_lab.seed import listar_cenarios;print(json.dumps(listar_cenarios()))"]);
    return ok({ scenarios: JSON.parse(r.stdout.trim().split("\n").at(-1) || "[]"), docs: "docs/testing/data-scenarios.md" });
  });
  T("lab_reset", "Recria o banco do LAB do zero e semeia um cenário (recusado fora de LAB — ver agent_lab/environment.py). Reinicie sessões de navegador depois.", { scenario: z.string().default("normal") }, async (a) => {
    const r = await manage(["agent_reset", "--scenario", a.scenario], 600_000);
    if (r.code !== 0) throw new Error((r.stderr || r.stdout).slice(-1500));
    return ok({ scenario: a.scenario, output: r.stdout.slice(-1500), health: await labHealth() });
  });
  T("lab_seed", "Semeia um cenário adicional no LAB (aditivo).", { scenario: z.string() }, async (a) => {
    const r = await manage(["agent_seed", "--scenario", a.scenario], 600_000);
    if (r.code !== 0) throw new Error((r.stderr || r.stdout).slice(-1500));
    return ok({ scenario: a.scenario, output: r.stdout.slice(-2000) });
  });
  T("lab_create_test_scenario", "Cria um cenário sob medida (tests/scenarios/<nome>.json, versionável). Depois use lab_reset/lab_seed com o nome.",
    { name: z.string().regex(/^[a-z0-9_-]{2,40}$/), volume: z.number().int().min(0).max(5000).default(10), long_text: z.boolean().default(false), missing_data: z.boolean().default(false), invalid_data: z.boolean().default(false), all_statuses: z.boolean().default(false), modules: z.array(z.enum(["eventos_sociais", "viagens_cadastros", "viagens_documentos", "ascom", "coffee_break"])).default([]), description: z.string().default("") },
    async (a) => {
      const code = `import json;from agent_lab.seed import criar_cenario;print(json.dumps(criar_cenario(${JSON.stringify(a.name)}, volume=${a.volume}, long_text=${a.long_text ? "True" : "False"}, missing_data=${a.missing_data ? "True" : "False"}, invalid_data=${a.invalid_data ? "True" : "False"}, all_statuses=${a.all_statuses ? "True" : "False"}, modules=${JSON.stringify(a.modules)}, descricao=${JSON.stringify(a.description)})))`;
      const r = await run(pythonExec(), [path.join(ROOT, "scripts/agent/lab.py"), "manage", "shell", "-v", "0", "-c", code]);
      if (r.code !== 0) throw new Error(r.stderr.slice(-1200));
      return ok({ created: `tests/scenarios/${a.name}.json`, scenario: JSON.parse(r.stdout.trim().split("\n").at(-1)!), next: `lab_reset {scenario:"${a.name}"}` });
    });

  // ---- testes
  for (const p of PROJETOS) {
    T(`testing_run_${p}_tests`, `Roda o projeto Playwright "${p}" e devolve estatísticas e falhas (reports/testing/…).`, { grep: z.string().optional() }, async (a) => ok(await runPlaywright(p, a.grep)));
  }
  T("testing_run_django_tests", "Roda testes Django (labels: apps/módulos/classes). Sem labels = só agent_lab (a suíte completa leva ~8 min).", { labels: z.array(z.string()).default(["agent_lab"]), parallel: z.number().default(4) }, async (a) => {
    const r = await run(pythonExec(), [path.join(ROOT, "scripts/agent/lab.py"), "manage", "test", ...a.labels, "--noinput", `--parallel=${a.parallel}`], { timeoutMs: 1_500_000, env: { AGENT_LAB_FREEZE: "" } });
    const linha = (r.stderr.match(/Ran \d+ tests? in [\d.]+s/) ?? [""])[0];
    const status = r.stderr.split(/\r?\n/).find((l) => /^(OK|FAILED)\b/.test(l)) ?? "?";
    return ok({ labels: a.labels, ok: r.code === 0, summary: `${linha} — ${status}`, failures: [...r.stderr.matchAll(/^(FAIL|ERROR): (.+)$/gm)].map((m) => m[2]).slice(0, 40), ms: r.ms });
  });
  T("testing_run_full_validation", "Validação completa: typecheck, ruff crítico, tokens, testes do agent_lab, Playwright (smoke, e2e, regression, a11y, responsive, visual). Relatório em reports/mcp/.", {}, async () => {
    const dir = evidenceDir("full_validation");
    const passos: Record<string, unknown> = {};
    const r1 = await run("npx", ["tsc", "--noEmit", "-p", "tsconfig.json"]); passos.typecheck = { ok: r1.code === 0, out: r1.stdout.slice(-800) };
    const ruff = path.join(ROOT, ".venv", process.platform === "win32" ? "Scripts/ruff.exe" : "bin/ruff");
    const r2 = await run(existsSync(ruff) ? ruff : "ruff", ["check", "--select", "E9,F63,F7,F82", "."]); passos.ruff_critical = { ok: r2.code === 0, out: r2.stdout.slice(-800) };
    const r3 = await run(pythonExec(), ["scripts/agent/build_tokens.py", "--check"]); passos.tokens = { ok: r3.code === 0, out: (r3.stdout + r3.stderr).trim() };
    const r4 = await run(pythonExec(), [path.join(ROOT, "scripts/agent/lab.py"), "manage", "test", "agent_lab", "--noinput"], { timeoutMs: 900_000, env: { AGENT_LAB_FREEZE: "" } }); passos.agent_lab_tests = { ok: r4.code === 0, out: r4.stderr.split("\n").slice(-4).join(" ") };
    for (const p of ["smoke", "e2e", "regression", "a11y", "responsive", "visual"]) passos[`playwright_${p}`] = await runPlaywright(p);
    const tudoOk = Object.values(passos).every((x) => (x as { ok: boolean }).ok);
    const ev = writeJson(path.join(dir, "validation.json"), { ok: tudoOk, steps: passos });
    return ok({ ok: tudoOk, steps: Object.fromEntries(Object.entries(passos).map(([k, v]) => [k, (v as { ok: boolean }).ok])), details: passos, evidence: [ev] });
  });

  // ---- banco
  T("db_environment", "Classificação do ambiente de banco (LAB/DEV/STAGING/PRODUCTION), sinais usados e capacidades (read/write/reset).", {}, async () => ok(await manageJson(["agent_env"])));
  T("db_explain", "EXPLAIN de um SELECT (somente leitura; ANALYZE só em LAB/DEV). Recusa escrita/DDL.", { sql: z.string(), analyze: z.boolean().default(false) }, async (a) => ok(await manageJson(["agent_db", "explain", a.sql, ...(a.analyze ? ["--analyze"] : [])])));
  T("db_validate_migrations", "Migrações: pendentes (com operações destrutivas/RunPython sinalizadas), modelos sem migração, conflitos.", {}, async () => ok(await manageJson(["agent_db", "migrations"])));
  T("db_find_anomalies", "Anomalias de dados: datas finais antes das iniciais, valores negativos, obrigatórios vazios.", {}, async () => ok(await manageJson(["agent_db", "anomalies"])));
  T("db_index_review", "Colunas de ordering sem índice e tabelas grandes afetadas.", {}, async () => ok(await manageJson(["agent_db", "indexes"])));
  T("db_audit", "Auditoria estrutural + dados: cascatas sensíveis, FKs anuláveis, legado, ordering, duplicidades.", {}, async () => {
    await manageJson(["agent_db_audit", "--dados"]);
    return ok({ report: readFileSync(path.join(ROOT, "reports/data/db-audit.md"), "utf-8"), evidence: ["reports/data/db-audit.json", "reports/data/db-audit.md"] });
  });

  // ---- API
  T("api_discover_endpoints", "Descobre endpoints JSON (GET sem parâmetro) no LAB, infere schema e gera docs/api/openapi.lab.json. Rede externa bloqueada durante a varredura.", {}, async () => ok(await manageJson(["agent_api"], 600_000)));
  T("api_check_contracts", "Compara as respostas atuais com docs/api/contracts.json (campos removidos/tipo mudado = quebra). Rode no cenário normal.", {}, async () => {
    const r = await manage(["agent_api", "--check"], 600_000);
    const ini = r.stdout.indexOf("{");
    return ok({ ok: r.code === 0, ...(ini >= 0 ? JSON.parse(r.stdout.slice(ini)) : { error: r.stderr.slice(-1000) }) });
  });

  // ---- observabilidade
  const lerJsonl = (nome: string, limite: number) => {
    const f = path.join(ROOT, ".lab", "observability", nome);
    if (!existsSync(f)) return [];
    return readFileSync(f, "utf-8").trim().split("\n").slice(-limite).filter(Boolean).map((l) => JSON.parse(l));
  };
  T("obs_get_requests", "Log de requisições do servidor do lab (duração, nº de SQL, tempo de banco, status). Filtro por substring do caminho.", { path: z.string().default(""), limit: z.number().default(50) }, async (a) =>
    ok({ source: ".lab/observability/requests.jsonl", requests: lerJsonl("requests.jsonl", 2000).filter((r) => r.path.includes(a.path)).slice(-a.limit) }));
  T("obs_get_slow_queries", "Consultas lentas e suspeitas de N+1 (SQL repetido ≥ 3× numa requisição).", { limit: z.number().default(20) }, async (a) => {
    const reqs = lerJsonl("requests.jsonl", 2000);
    return ok({ slow: reqs.flatMap((r) => r.slow_queries.map((q: object) => ({ path: r.path, ...q }))).slice(-a.limit), n_plus_one: reqs.filter((r) => r.repeated_queries.length).map((r) => ({ path: r.path, queries: r.queries, repeated: r.repeated_queries.slice(0, 2) })).slice(-a.limit), slowest_requests: [...reqs].sort((x, y) => y.duration_ms - x.duration_ms).slice(0, 10).map((r) => ({ path: r.path, ms: r.duration_ms, queries: r.queries, db_ms: r.db_ms })) });
  });
  T("obs_get_errors", "Exceções não tratadas capturadas pelo servidor do lab (com traceback).", { limit: z.number().default(10) }, async (a) => ok({ source: ".lab/observability/errors.jsonl", errors: lerJsonl("errors.jsonl", a.limit) }));
  T("obs_clear", "Zera os logs de observabilidade do lab (para medir um fluxo isolado).", {}, async () => {
    for (const n of ["requests.jsonl", "errors.jsonl"]) { const f = path.join(ROOT, ".lab", "observability", n); if (existsSync(f)) (await import("node:fs")).writeFileSync(f, ""); }
    return ok({ cleared: true });
  });
  void rel;
}
