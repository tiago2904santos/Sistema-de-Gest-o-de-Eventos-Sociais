/**
 * Utilidades comuns do project-mcp: raiz do repositório, execução de processos,
 * servidor do laboratório, evidências e formato padrão de resposta.
 */
import { spawn, spawnSync, type SpawnOptions } from "node:child_process";
import { existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

export const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..", "..", "..");
export const PORT = Number(process.env.LAB_PORT ?? 8031);
export const BASE_URL = process.env.LAB_BASE_URL ?? `http://127.0.0.1:${PORT}`;
const WIN = process.platform === "win32";

export function pythonExec(): string {
  const cands = [process.env.LAB_PYTHON, path.join(ROOT, ".venv", "Scripts", "python.exe"), path.join(ROOT, ".venv", "bin", "python")];
  return cands.find((c) => c && existsSync(c)) ?? (WIN ? "python" : "python3");
}

export type RunResult = { code: number; stdout: string; stderr: string; ms: number; command: string };

/** Executa um processo e devolve saída completa. Nunca lança por código ≠ 0. */
export function run(cmd: string, args: string[], opts: { timeoutMs?: number; env?: NodeJS.ProcessEnv; input?: string } = {}): Promise<RunResult> {
  return new Promise((resolve) => {
    const t0 = Date.now();
    const p = spawn(cmd, args, { cwd: ROOT, env: { ...process.env, ...opts.env, PYTHONUTF8: "1", FORCE_COLOR: "0", NO_COLOR: "1", DJANGO_COLORS: "nocolor" }, shell: WIN && cmd === "npx" } as SpawnOptions);
    let stdout = "";
    let stderr = "";
    p.stdout?.on("data", (d) => (stdout += d));
    p.stderr?.on("data", (d) => (stderr += d));
    const timer = setTimeout(() => p.kill("SIGKILL"), opts.timeoutMs ?? 300_000);
    if (opts.input) p.stdin?.end(opts.input);
    p.on("close", (code) => {
      clearTimeout(timer);
      const semCor = (x: string) => x.replace(/\x1b\[[0-9;]*m/g, "");
      resolve({ code: code ?? -1, stdout: semCor(stdout), stderr: semCor(stderr), ms: Date.now() - t0, command: [cmd, ...args].join(" ") });
    });
    p.on("error", (e) => {
      clearTimeout(timer);
      resolve({ code: -1, stdout, stderr: String(e), ms: Date.now() - t0, command: [cmd, ...args].join(" ") });
    });
  });
}

/** manage.py com o ambiente do laboratório (scripts/agent/lab.py manage …). */
export async function manage(args: string[], timeoutMs = 300_000): Promise<RunResult> {
  return run(pythonExec(), [path.join(ROOT, "scripts", "agent", "lab.py"), "manage", ...args], { timeoutMs });
}

/** manage.py … que imprime JSON: devolve o objeto ou lança com a mensagem de erro. */
export async function manageJson<T = unknown>(args: string[], timeoutMs = 300_000): Promise<T> {
  const r = await manage(args, timeoutMs);
  const ini = r.stdout.indexOf("{");
  if (r.code !== 0 || ini < 0) {
    throw new Error(`manage.py ${args.join(" ")} falhou (código ${r.code}): ${(r.stderr || r.stdout).trim().slice(-1500)}`);
  }
  return JSON.parse(r.stdout.slice(ini)) as T;
}

export async function labHealth(): Promise<Record<string, unknown> | null> {
  try {
    const r = await fetch(`${BASE_URL}/_lab/health/`, { signal: AbortSignal.timeout(4000) });
    return (await r.json()) as Record<string, unknown>;
  } catch {
    return null;
  }
}

let serverStarting: Promise<void> | null = null;

/** Garante o servidor do laboratório no ar (sobe um se preciso). */
export async function ensureServer(): Promise<Record<string, unknown>> {
  const h = await labHealth();
  if (h) return h;
  if (!serverStarting) {
    serverStarting = (async () => {
      const p = spawn(process.execPath, [path.join(ROOT, "scripts", "agent", "run.mjs"), "serve", "--port", String(PORT)], {
        cwd: ROOT, detached: !WIN, stdio: "ignore", env: { ...process.env },
      });
      p.unref();
      for (let i = 0; i < 240; i++) {
        if (await labHealth()) return;
        await new Promise((r) => setTimeout(r, 1000));
      }
      throw new Error("servidor do laboratório não subiu em 240 s (veja node scripts/agent/run.mjs serve)");
    })().finally(() => (serverStarting = null));
  }
  await serverStarting;
  return (await labHealth())!;
}

/** Exige que o servidor em uso seja LAB antes de ações que escrevem dados. */
export async function requireLab(): Promise<void> {
  const h = await ensureServer();
  if (h.environment !== "LAB") throw new Error(`Ação recusada: o servidor não está em ambiente LAB (atual: ${h.environment}).`);
}

let seq = 0;
/** Pasta de evidências desta chamada: reports/mcp/<AAAA-MM-DD>/<hora>-<n>-<ferramenta>/ */
export function evidenceDir(tool: string): string {
  const now = new Date();
  const dia = now.toISOString().slice(0, 10);
  const hora = now.toISOString().slice(11, 19).replace(/:/g, "");
  const d = path.join(ROOT, "reports", "mcp", dia, `${hora}-${String(++seq).padStart(3, "0")}-${tool}`);
  mkdirSync(d, { recursive: true });
  return d;
}

export const rel = (p: string) => path.relative(ROOT, p).split(path.sep).join("/");

export function writeJson(file: string, data: unknown) {
  mkdirSync(path.dirname(file), { recursive: true });
  writeFileSync(file, JSON.stringify(data, null, 2));
  return rel(file);
}

export function readJson<T = unknown>(file: string): T | null {
  const p = path.isAbsolute(file) ? file : path.join(ROOT, file);
  return existsSync(p) ? (JSON.parse(readFileSync(p, "utf-8")) as T) : null;
}

type Content = { type: "text"; text: string } | { type: "image"; data: string; mimeType: string };

/** Resposta padrão: JSON legível (+ imagens opcionais). */
export function ok(data: unknown, images: Buffer[] = []) {
  const content: Content[] = [{ type: "text", text: typeof data === "string" ? data : JSON.stringify(data, null, 2) }];
  for (const img of images) {
    if (img.length < 1_500_000) content.push({ type: "image", data: img.toString("base64"), mimeType: "image/png" });
  }
  return { content };
}

export function fail(message: string, extra: Record<string, unknown> = {}) {
  return { isError: true, content: [{ type: "text" as const, text: JSON.stringify({ error: message, ...extra }, null, 2) }] };
}

/** Envolve um handler: erros viram resposta de erro estruturada (o servidor nunca cai). */
export function safe<A>(fn: (a: A) => Promise<ReturnType<typeof ok>>) {
  return async (a: A) => {
    try {
      return await fn(a);
    } catch (e) {
      return fail(e instanceof Error ? e.message : String(e));
    }
  };
}

export function gitSync(args: string[]): string {
  const r = spawnSync("git", args, { cwd: ROOT, encoding: "utf-8" });
  return (r.stdout || r.stderr || "").trim();
}

/** Achado no formato docs/agent/audit-finding.schema.json. */
export type Finding = {
  id: string; rule: string; source: "runtime" | "static" | "manual"; category: string; severity: "P0" | "P1" | "P2" | "P3" | "P4";
  title: string; detail?: string; target: { type: "page" | "component" | "flow" | "module"; ref: string; role?: string };
  evidence: { kind: string; path?: string; value?: unknown }[]; recommendation: string; verification?: string;
};

import { createHash } from "node:crypto";
export function finding(f: Omit<Finding, "id" | "source"> & { source?: Finding["source"] }): Finding {
  const id = "mcp-" + createHash("sha1").update(`${f.rule}|${f.target.ref}|${f.title}`).digest("hex").slice(0, 12);
  return { source: "runtime", ...f, id };
}
