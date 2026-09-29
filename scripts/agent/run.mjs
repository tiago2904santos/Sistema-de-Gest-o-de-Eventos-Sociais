#!/usr/bin/env node
// Lançador multiplataforma: acha o Python do .venv (Windows ou Linux/macOS)
// e executa scripts/agent/lab.py com os argumentos recebidos.
import { spawnSync } from "node:child_process";
import { existsSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const raiz = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..", "..");
const candidatos = [
  process.env.LAB_PYTHON,
  path.join(raiz, ".venv", "Scripts", "python.exe"),
  path.join(raiz, ".venv", "bin", "python"),
  process.platform === "win32" ? "python" : "python3",
].filter(Boolean);
const python = candidatos.find((c) => !c.includes(path.sep) || existsSync(c));
const r = spawnSync(python, [path.join(raiz, "scripts", "agent", "lab.py"), ...process.argv.slice(2)], {
  stdio: "inherit",
  cwd: raiz,
});
process.exit(r.status ?? 1);
