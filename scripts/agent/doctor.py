#!/usr/bin/env python3
"""agent:doctor — diagnóstico (e auto-recuperação segura) da infraestrutura do agente.

    python scripts/agent/doctor.py            # diagnóstico legível
    python scripts/agent/doctor.py --json     # JSON (usado pelo project-mcp: agent_doctor)
    python scripts/agent/doctor.py --fix      # detect → diagnose → repair → retest (só reparos seguros)
    python scripts/agent/doctor.py --quick    # pula checagens lentas (handshake MCP, typecheck)

Verifica: runtimes, dependências, navegador, MCP (handshake real), plugins, skills, agentes,
pipelines, scripts, banco do laboratório, testes (typecheck), configuração conflitante,
drift de documentação e ferramentas mortas. Grava reports/agent/doctor.{json,md} e versions.json.

Auto-recuperação NUNCA é destrutiva fora do laboratório: recria só o banco do LAB (.lab/),
reinstala node_modules/Chromium, regera inventário e tokens.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ / "scripts" / "agent"))
import lab  # noqa: E402  (reaproveita lab_env/python_exec)

NATIVAS = {
    "Read",
    "Edit",
    "Write",
    "Grep",
    "Glob",
    "Bash",
    "WebSearch",
    "WebFetch",
    "NotebookEdit",
    "Agent",
    "TodoWrite",
}
SECOES_SKILL = ("## Passos", "## Se falhar")
REPORTS = RAIZ / "reports" / "agent"


def sh(cmd, timeout=180, env=None):
    try:
        # Sem shell: no Windows npx/npm são .cmd — resolve o caminho completo.
        exe = shutil.which(cmd[0]) or cmd[0]
        r = subprocess.run(
            [exe, *cmd[1:]],
            cwd=RAIZ,
            capture_output=True,
            text=True,
            timeout=timeout,
            env=env or os.environ,
            encoding="utf-8",
            errors="replace",
        )
        return r.returncode, (r.stdout or "") + (r.stderr or "")
    except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
        return -1, str(exc)


def fm(texto):
    m = re.match(r"---\n(.*?)\n---", texto, re.S)
    if not m:
        return None
    return {k.strip(): v.strip() for k, v in (ln.split(":", 1) for ln in m.group(1).splitlines() if ":" in ln)}


class Doctor:
    def __init__(self, quick=False):
        self.quick = quick
        self.checks = []
        self.mcp_tools: set[str] = set()
        self.versions = {}

    def add(self, area, nome, ok, detalhe="", critico=True, recuperavel=None, fix=None):
        self.checks.append(
            {
                "area": area,
                "check": nome,
                "ok": bool(ok),
                "critical": critico,
                "detail": str(detalhe)[:600],
                "recoverable": recuperavel,
                "fix": fix,
            }
        )

    # ---------------------------------------------------------------- runtime
    def runtime(self):
        py = lab.python_exec()
        code, out = sh([py, "-c", "import sys,django;print(sys.version.split()[0], django.get_version())"])
        self.add("runtime", "Python + Django (.venv)", code == 0, out.strip(), recuperavel=True, fix="bootstrap")
        if code == 0:
            self.versions["python"], self.versions["django"] = out.split()[:2]
        for exe in ("node", "npm", "git"):
            v = shutil.which(exe)
            code, out = sh([exe, "--version"]) if v else (-1, "ausente")
            self.add("runtime", exe, code == 0, out.strip().splitlines()[0] if out else "", critico=exe != "git")
            if code == 0:
                self.versions[exe] = out.strip().splitlines()[0]

    def deps(self):
        pkg = json.loads((RAIZ / "package.json").read_text(encoding="utf-8"))
        faltando = [d for d in pkg.get("devDependencies", {}) if not (RAIZ / "node_modules" / d).exists()]
        self.add(
            "deps",
            "node_modules completo",
            not faltando,
            f"faltando: {faltando}" if faltando else "ok",
            recuperavel=True,
            fix="npm",
        )
        for d, v in pkg.get("devDependencies", {}).items():
            p = RAIZ / "node_modules" / d / "package.json"
            if p.exists():
                self.versions[f"npm:{d}"] = json.loads(p.read_text(encoding="utf-8")).get("version")
        req_dev = (RAIZ / "requirements-dev.txt").read_text(encoding="utf-8")
        bin_ = Path(lab.python_exec()).parent
        for ferramenta in ("ruff", "bandit", "pip-audit"):
            existe = (bin_ / ferramenta).exists() or (bin_ / f"{ferramenta}.exe").exists()
            self.add(
                "deps",
                f"{ferramenta} instalado e em requirements-dev",
                existe and ferramenta in req_dev,
                "ok" if existe else "rode bootstrap",
                critico=False,
                recuperavel=True,
                fix="pip",
            )
            if existe:
                c, o = sh([str(bin_ / ferramenta), "--version"])
                self.versions[ferramenta] = o.strip().splitlines()[0] if o else "?"
        # Versões que precisam casar
        pw = self.versions.get("npm:@playwright/test")
        core = (
            json.loads((RAIZ / "node_modules/playwright-core/package.json").read_text(encoding="utf-8"))["version"]
            if (RAIZ / "node_modules/playwright-core/package.json").exists()
            else None
        )
        self.add(
            "config", "@playwright/test = playwright-core (axe usa o mesmo core)", pw == core, f"test={pw} core={core}"
        )

    def browser(self):
        code, out = sh(
            [
                "node",
                "-e",
                "const {chromium}=require('@playwright/test');chromium.launch().then(b=>{console.log(b.version());return b.close()}).catch(e=>{console.error(e.message.split('\\n')[0]);process.exit(1)})",
            ],
            timeout=120,
        )
        self.add("browser", "Chromium do Playwright abre", code == 0, out.strip(), recuperavel=True, fix="chromium")
        if code == 0:
            self.versions["chromium"] = out.strip()

    # ---------------------------------------------------------------- MCP / plugins
    def mcp(self):
        arq = RAIZ / ".mcp.json"
        try:
            cfg = json.loads(arq.read_text(encoding="utf-8"))["mcpServers"]
        except Exception as exc:
            self.add("mcp", ".mcp.json válido", False, exc)
            return
        self.add("mcp", ".mcp.json válido", True, ", ".join(cfg))
        for nome, s in cfg.items():
            self.add(
                "mcp",
                f"comando do servidor '{nome}' existe",
                bool(shutil.which(s["command"]) or Path(s["command"]).exists()),
                s["command"],
            )
        if self.quick:
            return
        script = (
            "import {connect,call} from './tools/project-mcp/test/client.ts';"
            "const c=await connect();const t=await c.listTools();const r=await call(c,'project_inspect_project');"
            "console.log(JSON.stringify({tools:t.tools.map(x=>x.name),ok:r.ok,env:r.data?.environment?.environment}));await c.close();"
        )
        tmp = RAIZ / ".lab" / "doctor-mcp.mts"
        tmp.parent.mkdir(exist_ok=True)
        tmp.write_text(script.replace("./tools", "../tools"), encoding="utf-8")
        t0 = time.time()
        code, out = sh(["node", str(RAIZ / "node_modules/tsx/dist/cli.mjs"), str(tmp)], timeout=180)
        try:
            dados = json.loads(out.strip().splitlines()[-1])
            self.mcp_tools = set(dados["tools"])
            self.add(
                "mcp",
                "project-mcp: handshake + chamada real",
                dados["ok"],
                f"{len(self.mcp_tools)} ferramentas; ambiente {dados['env']}; {int((time.time() - t0) * 1000)} ms",
            )
            self.versions["project-mcp tools"] = len(self.mcp_tools)
        except Exception:
            self.add("mcp", "project-mcp: handshake + chamada real", False, out[-800:])

    def plugins(self):
        synced = list(Path.home().glob(".claude/plugins/synced/*/manifest.json"))
        if not synced:
            self.add(
                "plugins",
                "plugins do claude.ai visíveis neste ambiente",
                True,
                "sem manifesto local (ambiente sem Cowork/Claude Code) — ver docs/agent/manual-connections.md",
                critico=False,
            )
            return
        man = json.loads(synced[0].read_text(encoding="utf-8"))
        nomes = [p.get("description", p["name"])[:40] for p in man.get("plugins", [])]
        self.add("plugins", "plugins sincronizados", True, f"{len(nomes)}: " + "; ".join(nomes), critico=False)
        vazios = [d.name for d in synced[0].parent.iterdir() if d.is_dir() and not any(d.iterdir())]
        if vazios:
            self.add(
                "plugins",
                "plugins só-MCP sem servidor ativo nesta sessão",
                False,
                f"{len(vazios)} plugin(s) só com MCP remoto (ex.: playwright, github, context7, figma) não carregam aqui; use project-mcp ou conecte o conector no claude.ai",
                critico=False,
            )

    # ---------------------------------------------------------------- skills / agentes / pipelines
    def skills(self):
        pkg_scripts = set(json.loads((RAIZ / "package.json").read_text(encoding="utf-8"))["scripts"])
        d = RAIZ / ".claude" / "skills"
        nomes = sorted(p.name for p in d.iterdir() if p.is_dir())
        self.skill_names = set(nomes)
        ruins = []
        for n in nomes:
            f = d / n / "SKILL.md"
            if not f.exists():
                ruins.append(f"{n}: sem SKILL.md")
                continue
            t = f.read_text(encoding="utf-8")
            meta = fm(t)
            if not meta or meta.get("name") != n or not meta.get("description"):
                ruins.append(f"{n}: frontmatter inválido")
            falta = [s for s in SECOES_SKILL if s not in t]
            if falta:
                ruins.append(f"{n}: faltam seções {falta}")
            for cmd in re.findall(r"npm run ([\w:.-]*\w)(?![\w{*:])", t):
                if cmd not in pkg_scripts:
                    ruins.append(f"{n}: npm run {cmd} não existe")
            if self.mcp_tools:
                for tool in set(
                    re.findall(
                        r"`((?:project|inventory|lab|testing|browser|audit|compare|knowledge|git|report|db|api|obs|agent)_[a-z_]+)`",
                        t,
                    )
                ):
                    if tool not in self.mcp_tools:
                        ruins.append(f"{n}: ferramenta MCP {tool} não existe")
        self.add("skills", f"{len(nomes)} skills válidas", not ruins, "; ".join(ruins[:15]) or "ok")

    def agents(self):
        d = RAIZ / ".claude" / "agents"
        ruins, nomes = [], set()
        for f in sorted(d.glob("*.md")):
            meta = fm(f.read_text(encoding="utf-8"))
            if not meta or meta.get("name") != f.stem or not meta.get("description") or not meta.get("tools"):
                ruins.append(f"{f.stem}: frontmatter inválido")
                continue
            nomes.add(f.stem)
            for tool in [x.strip() for x in meta["tools"].split(",")]:
                if tool.startswith("mcp__project-mcp__"):
                    if self.mcp_tools and tool.removeprefix("mcp__project-mcp__") not in self.mcp_tools:
                        ruins.append(f"{f.stem}: {tool} não existe")
                elif tool not in NATIVAS:
                    ruins.append(f"{f.stem}: ferramenta desconhecida {tool}")
            for sk in (
                re.findall(r"`([a-z0-9-]+)`", f.read_text(encoding="utf-8").split("- Skills:")[-1].split("\n")[0])
                if "- Skills:" in f.read_text(encoding="utf-8")
                else []
            ):
                if sk not in self.skill_names:
                    ruins.append(f"{f.stem}: skill {sk} não existe")
        self.agent_names = nomes
        self.add("agents", f"{len(nomes)} agentes válidos", not ruins, "; ".join(ruins[:15]) or "ok")

    def pipelines(self):
        ruins = []
        refs_skills, refs_agents = set(), set()
        for f in sorted((RAIZ / "docs/agent/pipelines").glob("*.json")):
            for ph in json.loads(f.read_text(encoding="utf-8"))["phases"]:
                refs_agents.add(ph["agent"])
                if ph["agent"] not in self.agent_names:
                    ruins.append(f"{f.stem}/{ph['phase']}: agente {ph['agent']} não existe")
                for sk in ph["skills"]:
                    refs_skills.add(sk)
                    if ":" not in sk and sk not in self.skill_names:
                        ruins.append(f"{f.stem}: skill {sk} não existe")
                for t in ph["tools"]:
                    if t not in NATIVAS and self.mcp_tools and t not in self.mcp_tools:
                        ruins.append(f"{f.stem}: ferramenta {t} não existe")
        self.refs = (refs_skills, refs_agents)
        self.add("agents", "pipelines do orquestrador coerentes", not ruins, "; ".join(ruins[:15]) or "ok")

    # ---------------------------------------------------------------- scripts / config
    def scripts(self):
        pkg = json.loads((RAIZ / "package.json").read_text(encoding="utf-8"))["scripts"]
        ruins = []
        for nome, cmd in pkg.items():
            for arq in re.findall(r"(?:node|bash|python3?)\s+([\w./-]+\.(?:mjs|js|sh|py))", cmd):
                if not (RAIZ / arq).exists():
                    ruins.append(f"{nome}: {arq} não existe")
            m = re.search(r"run\.mjs (\S+)", cmd)
            if m and m.group(1) not in lab_subcomandos():
                ruins.append(f"{nome}: lab.py não tem '{m.group(1)}'")
        self.add("scripts", f"{len(pkg)} scripts npm apontam para algo que existe", not ruins, "; ".join(ruins) or "ok")
        wf = (RAIZ / ".github/workflows/agent-lab.yml").read_text(encoding="utf-8")
        falta = [
            t
            for t in ("ruff", "bandit", "pip-audit")
            if t in wf and t not in (RAIZ / "requirements-dev.txt").read_text(encoding="utf-8")
        ]
        self.add("config", "ferramentas usadas no CI estão em requirements-dev", not falta, falta or "ok")
        s = (RAIZ / "config/settings.py").read_text(encoding="utf-8")
        self.add(
            "config",
            "agent_lab só com AGENT_LAB (desligado em produção)",
            'os.environ.get("AGENT_LAB", "1" if DEBUG else "0")' in s,
            "config/settings.py",
        )

    def database(self):
        code, out = sh([lab.python_exec(), str(RAIZ / "scripts/agent/lab.py"), "manage", "agent_env"], timeout=120)
        try:
            env = json.loads(out[out.index("{") :])
            self.add(
                "database",
                "banco do laboratório é LAB (marca interna)",
                env["environment"] == "LAB",
                f"{env['environment']} · {env['database']['name']}",
                recuperavel=True,
                fix="reset",
            )
        except Exception:
            self.add("database", "banco do laboratório acessível", False, out[-500:], recuperavel=True, fix="reset")
        # Controle detetivo: o banco tem o volume do cenário semeado? (pegou o bug do reset
        # que não apagava o SQLite e acumulava seeds — ver memory/corrections.md)
        marca = RAIZ / ".lab" / "seeded"
        if marca.exists():
            cen = marca.read_text(encoding="utf-8").strip()
            vol = {
                "empty": 0,
                "small": 3,
                "normal": 25,
                "large": 300,
                "edge_case": 12,
                "long_text": 6,
                "missing_data": 6,
                "invalid_data": 6,
            }.get(cen)
            if vol is not None:
                code, out = sh(
                    [
                        lab.python_exec(),
                        str(RAIZ / "scripts/agent/lab.py"),
                        "manage",
                        "shell",
                        "-v",
                        "0",
                        "-c",
                        "from solicitacoes.models import SolicitacaoEvento as S;print(S.objects.count())",
                    ],
                    timeout=120,
                )
                n = out.strip().splitlines()[-1] if out.strip() else "?"
                self.add(
                    "database",
                    f"volume do cenário '{cen}' íntegro",
                    n == str(vol),
                    f"esperado {vol}, encontrado {n}",
                    recuperavel=True,
                    fix="reset",
                )
        code, out = sh(
            [lab.python_exec(), str(RAIZ / "scripts/agent/lab.py"), "manage", "agent_db", "migrations"], timeout=240
        )
        try:
            m = json.loads(out[out.index("{") :])
            self.add(
                "database",
                "sem migrações pendentes/faltando",
                not m["unapplied"] and not m["models_without_migration"],
                f"pendentes={len(m['unapplied'])} faltando={m['models_without_migration']}",
                recuperavel=True,
                fix="migrate",
            )
        except Exception:
            self.add("database", "validação de migrações", False, out[-500:])

    def tests(self):
        if self.quick:
            return
        code, out = sh(["npx", "tsc", "--noEmit", "-p", "tsconfig.json"], timeout=300)
        self.add("tests", "typecheck (TS strict: testes + project-mcp)", code == 0, out.strip()[-600:] or "ok")
        code, out = sh([lab.python_exec(), str(RAIZ / "scripts/agent/build_tokens.py"), "--check"])
        self.add(
            "config",
            "tokens.css em dia com tokens/*.json",
            code == 0,
            out.strip(),
            critico=False,
            recuperavel=True,
            fix="tokens",
        )

    def freshness(self):
        inv = RAIZ / "ui-inventory" / "summary.json"
        if not inv.exists():
            self.add("inventory", "inventário existe", False, "ausente", recuperavel=True, fix="inventory")
            return
        t_inv = inv.stat().st_mtime
        mais_novo = max(
            (
                p.stat().st_mtime
                for pad in ("templates/**/*.html", "*/urls.py", "*/models.py", "*/forms.py", "static/css/*.css")
                for p in RAIZ.glob(pad)
            ),
            default=0,
        )
        self.add(
            "inventory",
            "inventário atualizado em relação ao código",
            t_inv >= mais_novo - 1,
            "desatualizado" if t_inv < mais_novo - 1 else "ok",
            critico=False,
            recuperavel=True,
            fix="inventory",
        )

    # ---------------------------------------------------------------- drift / mortos
    def drift(self):
        pkg_scripts = set(json.loads((RAIZ / "package.json").read_text(encoding="utf-8"))["scripts"])
        comandos = {p.stem for p in (RAIZ / "agent_lab/management/commands").glob("agent_*.py")}
        docs = [
            RAIZ / "CLAUDE.md",
            RAIZ / "AGENTS.md",
            *(RAIZ / "docs/agent").rglob("*.md"),
            *(RAIZ / "docs/architecture").rglob("*.md"),
            *(RAIZ / "docs/testing").glob("*.md"),
            *(RAIZ / "docs/engineering").glob("*.md"),
            *(RAIZ / ".claude").rglob("*.md"),
        ]
        ruins = []
        for f in docs:
            t = f.read_text(encoding="utf-8")
            rel = f.relative_to(RAIZ).as_posix()
            for link in re.findall(r"\]\(([^)#\s]+)\)", t):
                if link.startswith(("http", "mailto")):
                    continue
                if not (f.parent / link).resolve().exists() and not (RAIZ / link).exists():
                    ruins.append(f"{rel}: link quebrado {link}")
            for cam in re.findall(r"`((?:docs|scripts|tests|agent_lab|tools|tokens|\.claude)/[\w./-]+\.\w+)`", t):
                if "*" in cam or "<" in cam:
                    continue
                if not (RAIZ / cam).exists():
                    ruins.append(f"{rel}: caminho inexistente {cam}")
            for cmd in re.findall(r"npm run ([\w:.-]*\w)(?![\w{*:])", t):
                if cmd not in pkg_scripts:
                    ruins.append(f"{rel}: npm run {cmd} não existe")
            for cmd in re.findall(r"manage\.py (agent_\w+)", t):
                if cmd not in comandos:
                    ruins.append(f"{rel}: manage.py {cmd} não existe")
        self.drift_list = ruins
        self.add(
            "docs",
            "sem drift de documentação",
            not ruins,
            f"{len(ruins)} problema(s): " + "; ".join(ruins[:12]) if ruins else "ok",
            critico=False,
        )

    def dead(self):
        refs_skills, refs_agents = getattr(self, "refs", (set(), set()))
        corpus = "\n".join(
            p.read_text(encoding="utf-8")
            for p in [
                *(RAIZ / "docs").rglob("*.md"),
                RAIZ / "CLAUDE.md",
                RAIZ / "AGENTS.md",
                *(RAIZ / ".claude/agents").glob("*.md"),
            ]
        )
        skills_orfas = sorted(
            s
            for s in getattr(self, "skill_names", set())
            if s not in refs_skills and f"`{s}`" not in corpus and s not in corpus
        )
        agentes_orfaos = sorted(
            a for a in getattr(self, "agent_names", set()) if a not in refs_agents and a not in corpus
        )
        pkg = json.loads((RAIZ / "package.json").read_text(encoding="utf-8"))
        codigo = "\n".join(
            p.read_text(encoding="utf-8", errors="ignore")
            for pad in ("tests/**/*.ts", "tests/**/*.mjs", "tools/**/*.ts", "scripts/**/*.mjs", "playwright.config.ts")
            for p in RAIZ.glob(pad)
            if p.is_file()
        )
        deps_mortas = [
            d
            for d in pkg["devDependencies"]
            if d not in codigo
            and d not in ("typescript", "@types/node", "@types/pngjs", "tsx")
            and d not in json.dumps(pkg["scripts"])
        ]
        scripts_mortos = [
            s
            for s in pkg["scripts"]
            if s not in corpus
            and not s.startswith("post")
            and f"npm run {s}" not in (RAIZ / ".github/workflows/agent-lab.yml").read_text(encoding="utf-8")
        ]
        self.dead_list = {
            "orphan_skills": skills_orfas,
            "orphan_agents": agentes_orfaos,
            "unused_dev_dependencies": deps_mortas,
            "undocumented_npm_scripts": scripts_mortos,
        }
        algo = any(self.dead_list.values())
        self.add(
            "dead",
            "sem ferramentas mortas/órfãs",
            not algo,
            json.dumps(self.dead_list, ensure_ascii=False)[:600],
            critico=False,
        )

    # ---------------------------------------------------------------- execução
    def run_all(self):
        for etapa in (
            self.runtime,
            self.deps,
            self.browser,
            self.mcp,
            self.plugins,
            self.skills,
            self.agents,
            self.pipelines,
            self.scripts,
            self.database,
            self.tests,
            self.freshness,
            self.drift,
            self.dead,
        ):
            try:
                etapa()
            except Exception as exc:  # o doctor nunca cai
                self.add("doctor", etapa.__name__, False, f"{type(exc).__name__}: {exc}")
        return self


def lab_subcomandos():
    t = (RAIZ / "scripts/agent/lab.py").read_text(encoding="utf-8")
    return set(re.findall(r'"([\w-]+)": cmd_', t))


REPAROS = {
    "npm": (["npm", "ci", "--no-audit", "--no-fund"], "reinstala node_modules a partir do lockfile"),
    "chromium": (["npx", "playwright", "install", "chromium"], "instala o Chromium da versão do Playwright"),
    "reset": (
        [lab.python_exec(), str(RAIZ / "scripts/agent/lab.py"), "reset", "--scenario", "normal"],
        "recria SÓ o banco do laboratório (.lab/) e semeia",
    ),
    "migrate": (
        [lab.python_exec(), str(RAIZ / "scripts/agent/lab.py"), "manage", "migrate", "--noinput"],
        "aplica migrações no banco do LAB",
    ),
    "inventory": ([lab.python_exec(), str(RAIZ / "scripts/agent/lab.py"), "inventory"], "regera ui-inventory/"),
    "tokens": ([lab.python_exec(), str(RAIZ / "scripts/agent/build_tokens.py")], "recompila tokens.css"),
    "pip": (
        [lab.python_exec(), "-m", "pip", "install", "-q", "-r", "requirements-dev.txt"],
        "instala ferramentas de dev",
    ),
    "bootstrap": (
        [lab.python_exec(), str(RAIZ / "scripts/agent/lab.py"), "bootstrap", "--quick"],
        "bootstrap idempotente",
    ),
}


def relatorio(doc, reparos):
    falhas = [c for c in doc.checks if not c["ok"] and c["critical"]]
    avisos = [c for c in doc.checks if not c["ok"] and not c["critical"]]
    status = "HEALTHY" if not falhas else "DEGRADED" if len(falhas) <= 2 else "BROKEN"
    dados = {
        "status": status,
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "critical_failures": len(falhas),
        "warnings": len(avisos),
        "checks": doc.checks,
        "repairs": reparos,
        "versions": doc.versions,
        "drift": getattr(doc, "drift_list", []),
        "dead": getattr(doc, "dead_list", {}),
    }
    REPORTS.mkdir(parents=True, exist_ok=True)
    (REPORTS / "doctor.json").write_text(json.dumps(dados, indent=2, ensure_ascii=False), encoding="utf-8")
    (REPORTS / "versions.json").write_text(json.dumps(doc.versions, indent=2, ensure_ascii=False), encoding="utf-8")
    md = [
        f"# agent:doctor — {status}",
        "",
        f"{dados['generated_at']} · {len(falhas)} falha(s) crítica(s), {len(avisos)} aviso(s)",
        "",
        "| Área | Check | OK | Crítico | Detalhe |",
        "|---|---|---|---|---|",
    ]
    md += [
        f"| {c['area']} | {c['check']} | {'✅' if c['ok'] else '❌'} | {'sim' if c['critical'] else 'não'} | {c['detail'][:180].replace('|', '/')} |"
        for c in doc.checks
    ]
    if reparos:
        md += ["", "## Reparos aplicados", ""] + [
            f"- {r['fix']}: {r['what']} → {'ok' if r['ok'] else 'falhou'}" for r in reparos
        ]
    (REPORTS / "doctor.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    return dados


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--fix", action="store_true")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--quick", action="store_true")
    a = ap.parse_args()
    doc = Doctor(quick=a.quick).run_all()
    reparos = []
    if a.fix:
        feitos = set()
        for c in doc.checks:
            if not c["ok"] and c["recoverable"] and c["fix"] in REPAROS and c["fix"] not in feitos:
                cmd, oque = REPAROS[c["fix"]]
                code, out = sh(cmd, timeout=900)
                reparos.append({"fix": c["fix"], "what": oque, "ok": code == 0, "output": out[-400:]})
                feitos.add(c["fix"])
        if reparos:  # retest
            doc = Doctor(quick=a.quick).run_all()
    dados = relatorio(doc, reparos)
    if a.json:
        print(json.dumps({k: v for k, v in dados.items()}, ensure_ascii=False))
    else:
        for c in doc.checks:
            print(
                f"{'✓' if c['ok'] else ('✗' if c['critical'] else '!')} [{c['area']}] {c['check']}: {c['detail'][:150]}"
            )
        for r in reparos:
            print(f"↻ reparo {r['fix']}: {'ok' if r['ok'] else 'falhou'}")
        print(f"\nStatus: {dados['status']} → reports/agent/doctor.md")
    sys.exit(0 if dados["status"] == "HEALTHY" else 1)


if __name__ == "__main__":
    main()
