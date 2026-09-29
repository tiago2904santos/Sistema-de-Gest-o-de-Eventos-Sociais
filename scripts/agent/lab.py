#!/usr/bin/env python3
"""CLI do laboratório do agente (multiplataforma, só biblioteca padrão).

    python scripts/agent/lab.py <comando> [opções]

Comandos:
    bootstrap   prepara tudo de forma idempotente e termina com o health check
    health      verifica runtime, deps, banco, app, navegador, testes → reports/agent-health.md
    serve       sobe o Django do laboratório (banco próprio, relógio ancorado, AGENT_LAB=1)
    reset       recria o banco do laboratório e semeia (--scenario)
    seed        semeia um cenário adicional (--scenario)
    inventory   regenera ui-inventory/*.json
    depgraph    regenera o mapa de dependências (reports/architecture/)
    audit       auditoria estática (templates/CSS/rotas) → reports/audit/static-*.json
    tokens      compila tokens/*.json → static/css/tokens.css (+ relatório de contraste)
    db-audit    auditoria do banco do laboratório → reports/data/db-audit.{json,md}
    env         mostra o ambiente que o laboratório usa (sem segredos)

O laboratório NUNCA usa o banco de desenvolvimento de quem programa: por padrão é
SQLite em ``.lab/lab.sqlite3``; com ``LAB_DATABASE=postgres`` usa ``<POSTGRES_DB>_lab``.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import platform
import shutil
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
LAB_DIR = RAIZ / ".lab"
REPORTS = RAIZ / "reports"
PORTA_PADRAO = int(os.environ.get("LAB_PORT", "8031"))
ANCORA = os.environ.get("AGENT_LAB_FREEZE_DEFAULT", "2026-09-15T10:00:00-03:00")
WIN = os.name == "nt"


# ---------------------------------------------------------------------------
# ambiente
# ---------------------------------------------------------------------------


def venv_python() -> Path:
    cand = RAIZ / ".venv" / ("Scripts/python.exe" if WIN else "bin/python")
    return cand


def python_exec() -> str:
    vp = venv_python()
    return str(vp) if vp.exists() else sys.executable


def ler_dotenv() -> dict:
    env = {}
    p = RAIZ / ".env"
    if p.exists():
        for linha in p.read_text(encoding="utf-8", errors="replace").splitlines():
            linha = linha.strip()
            if linha and not linha.startswith("#") and "=" in linha:
                k, v = linha.split("=", 1)
                env[k.strip()] = v.strip().strip('"').strip("'")
    return env


def lab_env(freeze: bool = True) -> dict:
    """Ambiente do servidor/comandos do laboratório. Nunca devolve segredos ao log."""
    env = dict(os.environ)
    dotenv = ler_dotenv()
    env.update(
        {
            "AGENT_LAB": "1",
            "DJANGO_DEBUG": "1",
            "ROTINAS_DIARIAS_AUTOMATICAS": "0",
            "EPROTOCOLO_AMBIENTE": "mock",
            "EPROTOCOLO_REAL_READONLY": "1",
            "GEOCODIFICAR_SOB_DEMANDA": "0",
            "OPENROUTESERVICE_API_KEY": "",
            "ANTHROPIC_API_KEY": "",
            "ASSISTENTE_LLM": "deterministico",
            "EMAIL_HOST": "",
            "WHATSAPP_APP_SECRET": "",
            "WHATSAPP_TOKEN": "",
            "WHATSAPP_VERIFY_TOKEN": "",
            "LEGADO_DB_NAME": "",
            "MEDIA_ROOT": str(LAB_DIR / "media"),
        "AGENT_LAB_OBS": os.environ.get("AGENT_LAB_OBS", "1"),
            "PYTHONIOENCODING": "utf-8",
            "PYTHONUTF8": "1",
        }
    )
    if freeze:
        env["AGENT_LAB_FREEZE"] = os.environ.get("AGENT_LAB_FREEZE", ANCORA)
    if os.environ.get("LAB_DATABASE", "sqlite") == "postgres":
        base = os.environ.get("POSTGRES_DB") or dotenv.get("POSTGRES_DB") or "eventos_sociais"
        env["POSTGRES_DB"] = base if base.endswith("_lab") else f"{base}_lab"
        for k in ("POSTGRES_USER", "POSTGRES_PASSWORD", "POSTGRES_HOST", "POSTGRES_PORT"):
            if k not in os.environ and k in dotenv:
                env[k] = dotenv[k]
    else:
        env["POSTGRES_DB"] = ""  # vazio vence o .env (load_dotenv não sobrescreve) → SQLite
        env["SQLITE_PATH"] = str(LAB_DIR / "lab.sqlite3")
    return env


def run(cmd, *, env=None, check=True, capture=False, timeout=None):
    r = subprocess.run(
        cmd, cwd=RAIZ, env=env, text=True, capture_output=capture, timeout=timeout, encoding="utf-8", errors="replace"
    )
    if check and r.returncode != 0:
        if capture:
            sys.stderr.write((r.stdout or "") + (r.stderr or ""))
        raise SystemExit(f"Falhou: {' '.join(map(str, cmd))} (código {r.returncode})")
    return r


def manage(*args, env=None, **kw):
    return run([python_exec(), "manage.py", *args], env=env or lab_env(), **kw)


def garantir_banco_postgres(env):
    if not env.get("POSTGRES_DB"):
        return
    codigo = (
        "import os,psycopg;"
        "c=psycopg.connect(dbname='postgres',user=os.environ.get('POSTGRES_USER','postgres'),"
        "password=os.environ.get('POSTGRES_PASSWORD',''),host=os.environ.get('POSTGRES_HOST','localhost'),"
        "port=os.environ.get('POSTGRES_PORT','5432'),autocommit=True);"
        "n=os.environ['POSTGRES_DB'];"
        "e=c.execute('select 1 from pg_database where datname=%s',(n,)).fetchone();"
        "e or c.execute(f'CREATE DATABASE \"{n}\"');print('db', n, 'ok')"
    )
    run([python_exec(), "-c", codigo], env=env)


# ---------------------------------------------------------------------------
# comandos
# ---------------------------------------------------------------------------


def cmd_env(_a):
    env = lab_env()
    visiveis = {
        k: env.get(k)
        for k in (
            "AGENT_LAB",
            "DJANGO_DEBUG",
            "AGENT_LAB_FREEZE",
            "POSTGRES_DB",
            "SQLITE_PATH",
            "MEDIA_ROOT",
            "EPROTOCOLO_AMBIENTE",
            "GEOCODIFICAR_SOB_DEMANDA",
        )
    }
    visiveis["python"] = python_exec()
    visiveis["port"] = PORTA_PADRAO
    print(json.dumps(visiveis, indent=2, ensure_ascii=False))


def cmd_reset(a):
    LAB_DIR.mkdir(exist_ok=True)
    env = lab_env()
    garantir_banco_postgres(env)
    manage("agent_reset", "--scenario", a.scenario, env=env)


def cmd_seed(a):
    manage("agent_seed", "--scenario", a.scenario)


def cmd_inventory(_a):
    manage("agent_inventory")


def cmd_depgraph(_a):
    manage("agent_depgraph")


def cmd_audit(_a):
    manage("agent_audit_static")


def cmd_tokens(_a):
    run([python_exec(), str(RAIZ / "scripts" / "agent" / "build_tokens.py")])


def cmd_db_audit(_a):
    manage("agent_db_audit", "--dados")


def porta_livre(porta):
    with socket.socket() as s:
        return s.connect_ex(("127.0.0.1", porta)) != 0


def cmd_serve(a):
    LAB_DIR.mkdir(exist_ok=True)
    env = lab_env()
    garantir_banco_postgres(env)
    manage("migrate", "--noinput", "-v", "0", env=env)
    precisa_seed = not (LAB_DIR / "seeded").exists() or a.reset
    if precisa_seed:
        manage("agent_reset", "--scenario", a.scenario, env=env)
        (LAB_DIR / "seeded").write_text(a.scenario, encoding="utf-8")
    print(f"UI Lab: http://127.0.0.1:{a.port}/_lab/  ·  saúde: http://127.0.0.1:{a.port}/_lab/health/", flush=True)
    cmd = [python_exec(), "manage.py", "runserver", f"127.0.0.1:{a.port}"] + ([] if a.reload else ["--noreload"])
    if WIN:
        sys.exit(subprocess.call(cmd, cwd=RAIZ, env=env))
    os.execve(cmd[0], cmd, env)


# ---------------------------------------------------------------------------
# health
# ---------------------------------------------------------------------------


def _versao(cmd):
    exe = shutil.which(cmd[0])
    if not exe:
        return None
    try:
        r = subprocess.run([exe, *cmd[1:]], capture_output=True, text=True, timeout=20)
        return (r.stdout or r.stderr).strip().splitlines()[0] if (r.stdout or r.stderr) else "?"
    except Exception:
        return None


def checar(nome, fn, critico=True):
    t0 = time.time()
    try:
        ok, detalhe = fn()
    except Exception as exc:  # health nunca cai: registra
        ok, detalhe = False, f"{type(exc).__name__}: {exc}"
    return {"check": nome, "ok": bool(ok), "critical": critico, "detail": detalhe, "ms": int((time.time() - t0) * 1000)}


def cmd_health(a):
    env = lab_env()
    resultados = []
    py = python_exec()

    def runtime():
        r = run(
            [py, "-c", "import sys,django;print(sys.version.split()[0], django.get_version())"],
            env=env,
            capture=True,
            check=False,
        )
        return r.returncode == 0, r.stdout.strip() or r.stderr.strip()[-300:]

    def deps():
        r = run([py, "-m", "pip", "check"], env=env, capture=True, check=False)
        if "No module named pip" in (r.stderr or ""):
            r = (
                run(["uv", "pip", "check", "--python", py], env=env, capture=True, check=False)
                if shutil.which("uv")
                else r
            )
        return r.returncode == 0, (r.stdout or r.stderr).strip()[-400:]

    def dj_check():
        r = manage("check", env=env, capture=True, check=False)
        return r.returncode == 0, (r.stdout + r.stderr).strip()[-400:]

    def migracoes():
        r = manage("makemigrations", "--check", "--dry-run", env=env, capture=True, check=False)
        return r.returncode == 0, (r.stdout + r.stderr).strip()[-300:]

    def banco():
        garantir_banco_postgres(env)
        r = manage("migrate", "--noinput", "-v", "0", env=env, capture=True, check=False)
        if r.returncode:
            return False, r.stderr[-400:]
        r = manage(
            "shell",
            "-v",
            "0",
            "-c",
            "from django.db import connection as c;c.ensure_connection();print(c.vendor, c.settings_dict['NAME'])",
            env=env,
            capture=True,
            check=False,
        )
        return r.returncode == 0, (r.stdout + r.stderr).strip()[-300:]

    def node():
        v = _versao(["node", "--version"])
        return bool(v), f"node {v}; npm {_versao(['npm', '--version'])}"

    def node_modules():
        ok = (RAIZ / "node_modules" / "@playwright" / "test").exists() and (
            RAIZ / "node_modules" / "@axe-core" / "playwright"
        ).exists()
        return ok, "node_modules com @playwright/test e @axe-core/playwright" if ok else "rode: npm ci"

    def navegador():
        r = run(
            [
                "node",
                "-e",
                "const {chromium}=require('@playwright/test');chromium.launch().then(b=>{console.log('chromium',b.version());return b.close()}).catch(e=>{console.error(e.message.split('\\n')[0]);process.exit(1)})",
            ],
            env=env,
            capture=True,
            check=False,
            timeout=90,
        )
        return r.returncode == 0, (r.stdout + r.stderr).strip()[-300:]

    def git():
        r = run(["git", "status", "--porcelain", "-b"], capture=True, check=False)
        linhas = r.stdout.splitlines()
        return r.returncode == 0, f"{linhas[0] if linhas else '?'}; {len(linhas) - 1} arquivo(s) alterado(s)"

    def dotenv():
        existe = (RAIZ / ".env").exists()
        rastreado = run(["git", "ls-files", "--error-unmatch", ".env"], capture=True, check=False).returncode == 0
        if rastreado:
            return False, ".env está versionado — remova do git!"
        return True, ".env presente (não versionado)" if existe else "sem .env (o laboratório não precisa dele)"

    def app():
        porta = PORTA_PADRAO
        proc = None
        if porta_livre(porta):
            proc = subprocess.Popen(
                [py, "manage.py", "runserver", f"127.0.0.1:{porta}", "--noreload"],
                cwd=RAIZ,
                env=env,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        try:
            for _ in range(60):
                try:
                    with urllib.request.urlopen(f"http://127.0.0.1:{porta}/_lab/health/", timeout=3) as resp:
                        corpo = json.loads(resp.read().decode())
                        return (
                            resp.status == 200,
                            f"HTTP {resp.status}; db={corpo.get('db_vendor')}; pendentes={len(corpo.get('pending_migrations', []))}",
                        )
                except urllib.error.HTTPError as e:
                    return False, f"HTTP {e.code}: {e.read().decode()[:200]}"
                except Exception:
                    time.sleep(1)
            return False, "servidor não respondeu em 60 s"
        finally:
            if proc:
                proc.terminate()

    def mcp():
        arq = RAIZ / ".mcp.json"
        if not arq.exists():
            return False, "sem .mcp.json"
        dados = json.loads(arq.read_text(encoding="utf-8"))
        return True, "servidores: " + ", ".join(sorted(dados.get("mcpServers", {})))

    def suite_rapida():
        if a.quick:
            return True, "pulado (--quick)"
        r = manage(
            "test",
            "agent_lab",
            "--noinput",
            env={**env, "AGENT_LAB_FREEZE": ""},
            capture=True,
            check=False,
            timeout=900,
        )
        return r.returncode == 0, (r.stderr or "").strip().splitlines()[-1] if r.stderr else "?"

    def playwright_smoke():
        if a.quick:
            return True, "pulado (--quick)"
        r = run(
            ["npx", "playwright", "test", "--project=smoke", "--reporter=line"],
            env=env,
            capture=True,
            check=False,
            timeout=900,
        )
        ultima = [ln for ln in (r.stdout or "").splitlines() if ln.strip()][-3:]
        return r.returncode == 0, " | ".join(ultima)

    for nome, fn, crit in [
        ("Python + Django", runtime, True),
        ("Dependências Python (pip check)", deps, False),
        ("manage.py check", dj_check, True),
        ("Migrações sem pendência", migracoes, True),
        ("Banco do laboratório", banco, True),
        ("Node/npm", node, True),
        ("node_modules", node_modules, True),
        ("Chromium (Playwright)", navegador, True),
        ("Git", git, False),
        (".env seguro", dotenv, True),
        ("Aplicação responde (/_lab/health/)", app, True),
        ("MCP configurado", mcp, False),
        ("Testes do agent_lab", suite_rapida, True),
        ("Playwright smoke", playwright_smoke, True),
    ]:
        res = checar(nome, fn, crit)
        resultados.append(res)
        print(f"{'✓' if res['ok'] else ('✗' if crit else '!')} {nome}: {res['detail'][:160]}", flush=True)

    REPORTS.mkdir(exist_ok=True)
    agora = dt.datetime.now().astimezone().isoformat(timespec="seconds")
    falhas = [r for r in resultados if not r["ok"] and r["critical"]]
    status = "READY" if not falhas else ("PARTIAL" if len(falhas) < 3 else "BLOCKED")
    linhas = [
        f"# Agent health — {status}",
        "",
        f"Gerado em {agora} · {platform.platform()} · python `{py}`",
        "",
        "| Check | Resultado | Crítico | Detalhe | ms |",
        "|---|---|---|---|---|",
    ]
    for r in resultados:
        det = r["detail"].replace("|", "\\|").replace("\n", " ")[:220]
        linhas.append(
            f"| {r['check']} | {'✅' if r['ok'] else '❌'} | {'sim' if r['critical'] else 'não'} | {det} | {r['ms']} |"
        )
    (REPORTS / "agent-health.md").write_text("\n".join(linhas) + "\n", encoding="utf-8")
    (REPORTS / "agent").mkdir(exist_ok=True)
    (REPORTS / "agent" / "health.json").write_text(
        json.dumps({"status": status, "generated_at": agora, "checks": resultados}, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    print(f"\nStatus: {status} → reports/agent-health.md")
    sys.exit(0 if not falhas else 1)


# ---------------------------------------------------------------------------
# bootstrap
# ---------------------------------------------------------------------------


def cmd_bootstrap(a):
    passos = []

    def passo(nome):
        print(f"\n▶ {nome}", flush=True)
        passos.append(nome)

    passo("Detectar stack")
    print(
        json.dumps(
            {
                "os": platform.platform(),
                "python_venv": str(venv_python()) if venv_python().exists() else None,
                "node": _versao(["node", "--version"]),
                "git": _versao(["git", "--version"]),
                "uv": _versao(["uv", "--version"]),
                "postgres_client": _versao(["psql", "--version"]),
            },
            indent=2,
        )
    )

    passo("Ambiente virtual Python")
    if not venv_python().exists():
        if shutil.which("uv"):
            run(["uv", "venv", "--python", "3.14", ".venv"])
        else:
            run([sys.executable, "-m", "venv", ".venv"])
    else:
        print("  .venv já existe")

    passo("Dependências Python (produção + dev)")
    reqs = ["-r", "requirements.txt", "-r", "requirements-dev.txt"]
    if shutil.which("uv"):
        run(["uv", "pip", "install", "--python", python_exec(), *reqs])
    else:
        run([python_exec(), "-m", "pip", "install", "-q", *reqs])

    passo("Dependências Node (Playwright, axe, TypeScript)")
    if shutil.which("npm"):
        lock = (RAIZ / "package-lock.json").exists()
        run(["npm", "ci" if lock else "install", "--no-audit", "--no-fund"], env=dict(os.environ), check=True) if not (
            RAIZ / "node_modules" / "@playwright"
        ).exists() or a.force else print("  node_modules já instalado")
        if not os.environ.get("PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD"):
            run(["npx", "playwright", "install", "chromium"], check=False)
    else:
        print("  npm ausente: instale Node 20+ para a camada de navegador")

    passo("Banco do laboratório (migrate + seed normal)")
    LAB_DIR.mkdir(exist_ok=True)
    if not (LAB_DIR / "seeded").exists() or a.force:
        cmd_reset(argparse.Namespace(scenario=a.scenario))
        (LAB_DIR / "seeded").write_text(a.scenario, encoding="utf-8")
    else:
        manage("migrate", "--noinput", "-v", "0")
        print(f"  já semeado ({(LAB_DIR / 'seeded').read_text(encoding='utf-8')}); use --force para recriar")

    passo("Inventário do produto e mapa de dependências")
    cmd_inventory(a)
    cmd_depgraph(a)

    passo("Health check")
    cmd_health(argparse.Namespace(quick=a.quick))


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("bootstrap")
    b.add_argument("--scenario", default="normal")
    b.add_argument("--force", action="store_true")
    b.add_argument("--quick", action="store_true")
    h = sub.add_parser("health")
    h.add_argument("--quick", action="store_true", help="pula suíte do lab e smoke do Playwright")
    s = sub.add_parser("serve")
    s.add_argument("--port", type=int, default=PORTA_PADRAO)
    s.add_argument("--scenario", default="normal")
    s.add_argument("--reset", action="store_true")
    s.add_argument("--reload", action="store_true", help="recarrega ao editar código Python")
    for nome in ("reset", "seed"):
        sp = sub.add_parser(nome)
        sp.add_argument("--scenario", default="normal")
    for nome in ("inventory", "depgraph", "audit", "db-audit", "tokens", "env"):
        sub.add_parser(nome)
    a = p.parse_args()
    {
        "bootstrap": cmd_bootstrap,
        "health": cmd_health,
        "serve": cmd_serve,
        "reset": cmd_reset,
        "seed": cmd_seed,
        "inventory": cmd_inventory,
        "depgraph": cmd_depgraph,
        "audit": cmd_audit,
        "db-audit": cmd_db_audit,
        "tokens": cmd_tokens,
        "env": cmd_env,
    }[a.cmd](a)


if __name__ == "__main__":
    main()
