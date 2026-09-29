"""Observabilidade local do laboratório: requisições, consultas SQL e erros.

Ligada só com ``AGENT_LAB_OBS=1`` (o ``lab.py serve`` liga). Desligada, o
middleware é um repasse sem custo. Grava JSON Lines em ``.lab/observability/``:

* ``requests.jsonl`` — método, caminho, status, duração, nº de consultas, tempo
  de banco, consultas lentas (≥ ``AGENT_LAB_SLOW_MS``, padrão 50 ms) e SQL
  repetido (≥ 3× na mesma requisição → provável N+1);
* ``errors.jsonl`` — exceções não tratadas com traceback.

Também devolve ``Server-Timing`` (``app``, ``db``) para o navegador/Playwright
enxergarem o tempo do servidor. Nada disso vai para produção: o app só existe
com ``AGENT_LAB``.
"""

from __future__ import annotations

import json
import os
import re
import time
import traceback
from collections import Counter
from pathlib import Path

from django.conf import settings
from django.db import connection

LIMITE_ARQUIVO = 5 * 1024 * 1024


def ligado():
    return os.environ.get("AGENT_LAB_OBS") == "1"


def pasta():
    return Path(os.environ.get("AGENT_LAB_OBS_DIR") or Path(settings.BASE_DIR) / ".lab" / "observability")


def _gravar(nome, registro):
    d = pasta()
    d.mkdir(parents=True, exist_ok=True)
    arq = d / nome
    if arq.exists() and arq.stat().st_size > LIMITE_ARQUIVO:
        arq.replace(d / f"{nome}.1")
    with arq.open("a", encoding="utf-8") as f:
        f.write(json.dumps(registro, ensure_ascii=False, default=str) + "\n")


def _normalizar(sql):
    return re.sub(r"\b\d+\b|'[^']*'|%s", "?", sql)[:500]


class _Coletor:
    def __init__(self):
        self.consultas = []

    def __call__(self, execute, sql, params, many, context):
        t0 = time.perf_counter()
        try:
            return execute(sql, params, many, context)
        finally:
            self.consultas.append((sql, (time.perf_counter() - t0) * 1000))


class ObservabilidadeMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if not ligado() or request.path.startswith(("/static/", "/_lab/obs")):
            return self.get_response(request)
        coletor = _Coletor()
        t0 = time.perf_counter()
        with connection.execute_wrapper(coletor):
            response = self.get_response(request)
        total = (time.perf_counter() - t0) * 1000
        db_ms = sum(ms for _, ms in coletor.consultas)
        lento = float(os.environ.get("AGENT_LAB_SLOW_MS", "50"))
        repetidas = Counter(_normalizar(s) for s, _ in coletor.consultas)
        _gravar(
            "requests.jsonl",
            {
                "ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
                "method": request.method,
                "path": request.get_full_path()[:300],
                "status": response.status_code,
                "user": getattr(getattr(request, "user", None), "username", None),
                "duration_ms": round(total, 1),
                "db_ms": round(db_ms, 1),
                "queries": len(coletor.consultas),
                "slow_queries": [{"ms": round(ms, 1), "sql": s[:1000]} for s, ms in coletor.consultas if ms >= lento][
                    :10
                ],
                "repeated_queries": [{"count": n, "sql": s} for s, n in repetidas.most_common(5) if n >= 3],
            },
        )
        response["Server-Timing"] = f'app;dur={total:.1f}, db;dur={db_ms:.1f};desc="{len(coletor.consultas)} queries"'
        return response

    def process_exception(self, request, exception):
        if ligado():
            _gravar(
                "errors.jsonl",
                {
                    "ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
                    "method": request.method,
                    "path": request.get_full_path()[:300],
                    "error": f"{type(exception).__name__}: {exception}",
                    "traceback": traceback.format_exc()[-4000:],
                },
            )
        return None


def ler(nome, limite=200):
    arq = pasta() / nome
    if not arq.exists():
        return []
    linhas = arq.read_text(encoding="utf-8").splitlines()[-limite:]
    return [json.loads(x) for x in linhas if x.strip()]


def resumo(limite=500):
    reqs = ler("requests.jsonl", limite)
    lentas = sorted(reqs, key=lambda r: r["duration_ms"], reverse=True)[:10]
    n1 = [r for r in reqs if r["repeated_queries"]]
    return {
        "requests": len(reqs),
        "errors": len(ler("errors.jsonl", limite)),
        "slowest": [{k: r[k] for k in ("path", "status", "duration_ms", "db_ms", "queries")} for r in lentas],
        "n_plus_one_suspects": [{"path": r["path"], "repeated": r["repeated_queries"][:2]} for r in n1[:10]],
        "server_errors": [r for r in reqs if r["status"] >= 500][:10],
    }
