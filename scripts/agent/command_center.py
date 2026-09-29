#!/usr/bin/env python3
"""Consolida os relatórios do laboratório no contrato de dados do UI Command Center.

    python scripts/agent/command_center.py   → reports/agent/command-center.json

Só lê arquivos gerados (não roda nada): cada bloco diz de onde veio, quando foi
gerado e fica ``null`` com ``missing`` se a fonte ainda não existir. Contrato:
docs/agent/command-center.schema.json.
"""

from __future__ import annotations

import json
import re
import time
from collections import Counter
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
R = RAIZ / "reports"


def ler(p):
    p = RAIZ / p if not isinstance(p, Path) else p
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None


def bloco(fonte, dados):
    p = RAIZ / fonte
    return {
        "source": fonte,
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(p.stat().st_mtime)) if p.exists() else None,
        "missing": not p.exists(),
        "data": dados,
    }


def tabela(md, contem):
    txt = (RAIZ / md).read_text(encoding="utf-8").splitlines()
    linhas = [ln for ln in txt if ln.startswith("|")]
    cab = None
    out = []
    for ln in linhas:
        cel = [c.strip() for c in ln.strip("|").split("|")]
        if cab is None and any(contem in c for c in cel):
            cab = cel
            continue
        if cab and not set(ln) <= set("|-: "):
            out.append(dict(zip(cab, cel, strict=False)))
    return out


def main():
    health, doctor, selftest = (
        ler(R / "agent/health.json"),
        ler(R / "agent/doctor.json"),
        ler(R / "agent/self-test.json"),
    )
    a11y = [ler(p) for p in sorted((R / "accessibility").glob("*.json"))] if (R / "accessibility").exists() else []
    a11y = [x for x in a11y if x and x.get("counts")]
    resp = []
    if (R / "responsive").exists():
        for d in sorted(p for p in (R / "responsive").iterdir() if p.is_dir()):
            for f in d.glob("*.json"):
                j = ler(f)
                resp.append(
                    {
                        "page": d.name,
                        "viewport": f.stem,
                        "overflow": any(i["kind"] == "page-overflow-x" for i in j["issues"]),
                    }
                )
    perf = [ler(p) for p in sorted((R / "performance").glob("*.json"))] if (R / "performance").exists() else []
    static = ler(R / "audit/static-findings.json")
    sec = ler(R / "security/summary.json")
    pw = ler(R / "testing/playwright-results.json")
    inv = ler(RAIZ / "ui-inventory/summary.json")
    rotas = ler(RAIZ / "ui-inventory/routes.json")
    reg = ler(RAIZ / "docs/agent/tool-registry.json")
    kp = tabela("docs/agent/memory/known-problems.md", "Sev")
    mig = tabela("docs/architecture/migration-matrix.md", "Módulo")
    auditadas = {p.name for p in (R / "audit").iterdir() if p.is_dir()} if (R / "audit").exists() else set()
    paginas_rotas = [
        r["pattern"] for r in (rotas or {}).get("routes", []) if not r["params"] and not r["admin"] and r["templates"]
    ]
    nao_auditadas = [p for p in paginas_rotas if re.sub(r"[^\w]+", "-", p).strip("-") not in auditadas]
    cats = Counter(f["category"] for f in (static or {}).get("findings", []))
    dados = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "agent_health": bloco(
            "reports/agent/health.json",
            health and {"status": health["status"], "failed": [c["check"] for c in health["checks"] if not c["ok"]]},
        ),
        "tool_health": bloco(
            "reports/agent/doctor.json",
            doctor
            and {
                "status": doctor["status"],
                "critical_failures": doctor["critical_failures"],
                "warnings": doctor["warnings"],
                "versions": doctor["versions"],
            },
        ),
        "mcp_health": bloco(
            "reports/agent/self-test.json",
            selftest
            and {
                "ok": selftest["ok"],
                "tools": selftest["mcp_tools"],
                "steps_ok": sum(s["ok"] for s in selftest["steps"]),
                "steps": len(selftest["steps"]),
            },
        ),
        "plugin_health": bloco("docs/agent/tool-registry.json", reg and Counter(t["status"] for t in reg["tools"])),
        "test_health": bloco("reports/testing/playwright-results.json", pw and pw["stats"]),
        "page_coverage": bloco(
            "ui-inventory/routes.json",
            {
                "pages_with_route": len(paginas_rotas),
                "audited": len(paginas_rotas) - len(nao_auditadas),
                "not_audited_sample": nao_auditadas[:30],
            },
        ),
        "component_coverage": bloco(
            "ui-inventory/summary.json",
            inv
            and {
                "template_components": inv.get("template_components"),
                "specimens_in_lab": len(
                    list((RAIZ / "tests/visual/snapshots/visual/components.spec.ts").glob("*.png"))
                ),
            },
        ),
        "accessibility": bloco(
            "reports/accessibility",
            {
                "pages": len(a11y),
                "totals": {k: sum(x["counts"][k] for x in a11y) for k in ("critical", "serious", "moderate", "minor")},
                "baseline": ler(RAIZ / "tests/a11y/baseline.json"),
            },
        ),
        "visual_regression": bloco(
            "tests/visual/snapshots", {"baselines": len(list((RAIZ / "tests/visual/snapshots").rglob("*.png")))}
        ),
        "responsive": bloco(
            "reports/responsive",
            {"combinations": len(resp), "overflow": [f"{x['page']}@{x['viewport']}" for x in resp if x["overflow"]]},
        ),
        "performance": bloco(
            "reports/performance",
            [
                {"page": p["page"], **{k: p["metrics"][k] for k in ("ttfbMs", "lcpMs", "cls", "htmlKB", "requests")}}
                for p in perf
                if p and p.get("metrics")
            ],
        ),
        "security": bloco("reports/security/summary.json", sec),
        "ux_debt": bloco(
            "docs/agent/memory/known-problems.md",
            [k for k in kp if re.search(r"UX|VISUAL|ACCESSIBILITY|RESPONSIVE", k.get("Categoria", ""))],
        ),
        "technical_debt": bloco(
            "reports/audit/static-findings.json",
            static and {"by_category": dict(cats), "by_severity": static["summary"]["by_severity"]},
        ),
        "migration_status": bloco("docs/architecture/migration-matrix.md", mig),
        "known_problems": bloco("docs/agent/memory/known-problems.md", kp),
        "top_problems": bloco(
            "docs/agent/memory/known-problems.md", [k for k in kp if re.search(r"P0|P1|P2", k.get("Sev.", ""))]
        ),
    }
    saida = R / "agent" / "command-center.json"
    saida.parent.mkdir(parents=True, exist_ok=True)
    saida.write_text(json.dumps(dados, ensure_ascii=False, indent=2, default=dict), encoding="utf-8")
    faltando = [k for k, v in dados.items() if isinstance(v, dict) and v.get("missing")]
    print(
        json.dumps(
            {"written": str(saida.relative_to(RAIZ)), "blocks": len(dados) - 1, "missing_sources": faltando},
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
