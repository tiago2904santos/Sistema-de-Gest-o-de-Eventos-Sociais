"""Inteligência de API: descoberta de endpoints JSON, schema inferido, contrato e OpenAPI.

O sistema não tem API formal; tem ~dezenas de endpoints JSON usados pelo próprio
front (buscas remotas de select, listas de ofícios para vincular, etc.). Esta
camada os descobre executando as rotas GET sem parâmetro no LAB (cliente de
teste do Django, logado como ``lab.admin``), infere um JSON Schema da resposta e:

* grava ``docs/api/contracts.json`` (``--update``) — o contrato versionado;
* compara a resposta atual com o contrato (``--check``) — campos que sumiram
  ou mudaram de tipo quebram o front sem nenhum teste de backend perceber;
* gera ``docs/api/openapi.lab.json`` (OpenAPI 3.1) a partir do que viu.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from django.conf import settings

from . import inventory as inv

BASE = Path(settings.BASE_DIR)
CONTRATOS = BASE / "docs" / "api" / "contracts.json"
OPENAPI = BASE / "docs" / "api" / "openapi.lab.json"


def inferir(valor, prof=0):
    if prof > 6:
        return {}
    if isinstance(valor, bool):
        return {"type": "boolean"}
    if isinstance(valor, int):
        return {"type": "integer"}
    if isinstance(valor, float):
        return {"type": "number"}
    if isinstance(valor, str):
        return {"type": "string"}
    if valor is None:
        return {"type": "null"}
    if isinstance(valor, list):
        itens = [inferir(v, prof + 1) for v in valor[:20]]
        return {"type": "array", "items": _unir(itens) if itens else {}}
    if isinstance(valor, dict):
        return {"type": "object", "properties": {k: inferir(v, prof + 1) for k, v in sorted(valor.items())}}
    return {}


def _unir(esquemas):
    """União simples de schemas de itens de lista (propriedades somadas; tipos em anyOf se divergirem)."""
    tipos = {json.dumps(e, sort_keys=True) for e in esquemas}
    if len(tipos) == 1:
        return esquemas[0]
    objetos = [e for e in esquemas if e.get("type") == "object"]
    if len(objetos) == len(esquemas):
        props = {}
        for e in objetos:
            for k, v in e["properties"].items():
                props.setdefault(k, v)
        return {"type": "object", "properties": props}
    return {"anyOf": [json.loads(t) for t in sorted(tipos)]}


class _SemRede:
    """Bloqueia conexões de saída durante a descoberta (views que consultam serviços externos)."""

    def __enter__(self):
        import socket

        self._orig = socket.create_connection

        def recusar(endereco, *a, **k):
            host = endereco[0] if isinstance(endereco, tuple) else str(endereco)
            if host in ("127.0.0.1", "localhost", "::1"):
                return self._orig(endereco, *a, **k)
            raise OSError(f"rede bloqueada pelo laboratório: {host}")

        socket.create_connection = recusar
        return self

    def __exit__(self, *exc):
        import socket

        socket.create_connection = self._orig


def descobrir(usuario="lab.admin"):
    with _SemRede():
        return _descobrir(usuario)


def _descobrir(usuario):
    from django.contrib.auth import get_user_model
    from django.test import Client

    cliente = Client(HTTP_HOST="127.0.0.1")
    cliente.force_login(get_user_model().objects.get(username=usuario))
    rotas = inv.coletar_rotas()["routes"]
    candidatas = [
        r
        for r in rotas
        if not r["params"]
        and not r["admin"]
        and "require_POST" not in r["decorators"]
        and not r["pattern"].startswith("/_lab/")
        and not re.search(r"(sair|logout|webhook|exportar|\.xlsx|\.csv|\.pdf|baixar|sw\.js|manifest|ics)", r["pattern"])
    ]
    endpoints = {}
    for r in candidatas:
        try:
            resp = cliente.get(r["pattern"])
        except Exception as exc:  # rota que quebra no lab também é informação
            endpoints[r["pattern"]] = {"name": r["name"], "error": f"{type(exc).__name__}: {exc}"}
            continue
        tipo = resp.get("Content-Type", "")
        if "json" not in tipo:
            continue
        try:
            corpo = json.loads(resp.content or b"null")
        except ValueError:
            corpo = None
        endpoints[r["pattern"]] = {
            "name": r["name"],
            "view": r["view"],
            "module_code": r["module_code"],
            "status": resp.status_code,
            "content_type": tipo,
            "schema": inferir(corpo),
        }
    return endpoints


def _campos(schema, prefixo=""):
    out = {}
    if schema.get("type") == "object":
        for k, v in schema.get("properties", {}).items():
            out[prefixo + k] = v.get("type", "anyOf")
            out.update(_campos(v, prefixo + k + "."))
    elif schema.get("type") == "array":
        out.update(_campos(schema.get("items", {}), prefixo + "[]."))
    return out


def comparar(atual, contrato):
    quebras, novidades = [], []
    for caminho, antes in contrato.items():
        agora = atual.get(caminho)
        if agora is None:
            quebras.append({"endpoint": caminho, "problem": "endpoint não responde mais JSON"})
            continue
        ca, cn = _campos(antes.get("schema", {})), _campos(agora.get("schema", {}))
        for campo, tipo in ca.items():
            if campo not in cn:
                quebras.append({"endpoint": caminho, "problem": f"campo removido: {campo}"})
            elif cn[campo] != tipo and "null" not in (cn[campo], tipo):
                quebras.append({"endpoint": caminho, "problem": f"tipo mudou em {campo}: {tipo} → {cn[campo]}"})
        for campo in cn.keys() - ca.keys():
            novidades.append({"endpoint": caminho, "change": f"campo novo: {campo}"})
    for caminho in atual.keys() - contrato.keys():
        novidades.append({"endpoint": caminho, "change": "endpoint JSON novo (sem contrato)"})
    return quebras, novidades


def openapi(endpoints):
    paths = {}
    for caminho, e in sorted(endpoints.items()):
        if "schema" not in e:
            continue
        paths[caminho] = {
            "get": {
                "operationId": (e["name"] or caminho).replace(":", "_"),
                "tags": [e["name"].split(":")[0] if e["name"] else "outros"],
                "x-view": e["view"],
                "x-module-code": e["module_code"],
                "responses": {
                    str(e["status"]): {
                        "description": "Resposta observada no laboratório",
                        "content": {"application/json": {"schema": e["schema"]}},
                    }
                },
            }
        }
    return {
        "openapi": "3.1.0",
        "info": {"title": "Endpoints JSON internos (inferidos no laboratório)", "version": "lab"},
        "servers": [{"url": "http://127.0.0.1:8031"}],
        "paths": paths,
        "x-note": "Gerado por agent_lab/api_intel.py — descreve o que o front consome; não é uma API pública.",
    }


def executar(*, atualizar=False, checar=False):
    endpoints = descobrir()
    resultado = {
        "discovered": len([e for e in endpoints.values() if "schema" in e]),
        "errors": {k: v["error"] for k, v in endpoints.items() if "error" in v},
    }
    OPENAPI.parent.mkdir(parents=True, exist_ok=True)
    OPENAPI.write_text(json.dumps(openapi(endpoints), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    atuais = {k: v for k, v in endpoints.items() if "schema" in v}
    if atualizar or not CONTRATOS.exists():
        CONTRATOS.write_text(json.dumps(atuais, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        resultado["contracts"] = "gravados"
    if checar:
        contrato = json.loads(CONTRATOS.read_text(encoding="utf-8"))
        quebras, novidades = comparar(atuais, contrato)
        resultado["breaking"] = quebras
        resultado["non_breaking"] = novidades
    resultado["endpoints"] = sorted(atuais)
    return resultado
