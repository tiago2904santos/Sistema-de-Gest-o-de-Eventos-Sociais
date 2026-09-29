"""Classificação do ambiente de banco: LAB, DEV, STAGING ou PRODUCTION.

Nenhum sinal isolado decide. Em especial, **o nome de uma variável ou do banco
nunca basta** para liberar escrita destrutiva:

* **LAB** exige a *marca dentro do próprio banco* (tabela ``agent_lab_marcador``,
  gravada pelo ``agent_reset``) **e** DEBUG ligado **e** banco local. Um banco de
  produção nunca tem essa tabela, então apontar o laboratório para ele por engano
  não o transforma em LAB.
* **DEV**: DEBUG ligado e banco local, sem a marca.
* **STAGING**: declarado (``APP_ENVIRONMENT=staging``) e DEBUG desligado.
* **PRODUCTION**: DEBUG desligado, banco remoto, host público, ou declaração
  explícita — e também o padrão quando os sinais se contradizem (falha segura).

Capacidades por ambiente::

    LAB         read, write, reset
    DEV         read, write            (reset só de banco NOVO/vazio com cara de lab)
    STAGING     read, write controlada (exige --confirmar-staging)
    PRODUCTION  read                   (somente leitura)
"""

from __future__ import annotations

import os
from pathlib import Path

from django.conf import settings
from django.db import connection

TABELA_MARCA = "agent_lab_marcador"
HOSTS_LOCAIS = {"", "localhost", "127.0.0.1", "::1"}
CAPACIDADES = {
    "LAB": {"read": True, "write": True, "reset": True},
    "DEV": {"read": True, "write": True, "reset": False},
    "STAGING": {"read": True, "write": "controlada", "reset": False},
    "PRODUCTION": {"read": True, "write": False, "reset": False},
}
ORDEM_RISCO = ["LAB", "DEV", "STAGING", "PRODUCTION"]


class AmbienteRecusado(Exception):
    pass


def _banco():
    cfg = connection.settings_dict
    return {
        "vendor": connection.vendor,
        "name": str(cfg.get("NAME", "")),
        "host": str(cfg.get("HOST", "") or ""),
    }


def _banco_local(b):
    if b["vendor"] == "sqlite":
        return True
    return b["host"] in HOSTS_LOCAIS


def _sqlite_no_lab(b):
    if b["vendor"] != "sqlite":
        return False
    try:
        lab = (Path(settings.BASE_DIR) / ".lab").resolve()
        return (
            Path(b["name"]).resolve().is_relative_to(lab)
            or b["name"].startswith("file:memorydb")
            or b["name"] == ":memory:"
        )
    except OSError, ValueError:
        return False


def ler_marca():
    """Lê a marca de laboratório gravada dentro do banco (None se não houver)."""
    try:
        with connection.cursor() as c:
            tabelas = connection.introspection.table_names(c)
            if TABELA_MARCA not in tabelas:
                return None
            c.execute(f"SELECT chave, valor FROM {TABELA_MARCA}")
            return dict(c.fetchall())
    except Exception:
        return None


def gravar_marca():
    from django.utils import timezone

    with connection.cursor() as c:
        c.execute(f"CREATE TABLE IF NOT EXISTS {TABELA_MARCA} (chave VARCHAR(50) PRIMARY KEY, valor VARCHAR(200))")
        c.execute(f"DELETE FROM {TABELA_MARCA}")
        for chave, valor in (("ambiente", "LAB"), ("criado_em", timezone.now().isoformat())):
            c.execute(f"INSERT INTO {TABELA_MARCA} (chave, valor) VALUES (%s, %s)", [chave, valor])


def banco_vazio():
    """Sem nenhuma tabela de aplicação com dados (banco recém-criado)."""
    try:
        with connection.cursor() as c:
            tabelas = connection.introspection.table_names(c)
        if not tabelas:
            return True
        from django.contrib.auth import get_user_model

        return not get_user_model().objects.exists()
    except Exception:
        return True


def detectar():
    b = _banco()
    sinais = []
    declarado = (os.environ.get("APP_ENVIRONMENT") or "").strip().upper() or None
    if declarado:
        sinais.append(f"declarado APP_ENVIRONMENT={declarado}")
    sinais.append(f"DEBUG={settings.DEBUG}")
    local = _banco_local(b)
    sinais.append(f"banco {b['vendor']} {'local' if local else 'REMOTO'} ({b['name']})")
    hosts_publicos = [h for h in settings.ALLOWED_HOSTS if h not in HOSTS_LOCAIS and h not in ("testserver",)]
    if hosts_publicos:
        sinais.append(f"ALLOWED_HOSTS públicos: {hosts_publicos}")
    marca = ler_marca()
    if marca:
        sinais.append(f"marca de laboratório no banco ({marca.get('criado_em', '?')})")

    if declarado == "PRODUCTION" or not settings.DEBUG and declarado != "STAGING" or not local:
        amb = "PRODUCTION"
    elif declarado == "STAGING" and not settings.DEBUG:
        amb = "STAGING"
    elif marca and marca.get("ambiente") == "LAB" and settings.DEBUG and local:
        amb = "LAB"
    elif settings.DEBUG and local:
        amb = "DEV"
    else:
        amb = "PRODUCTION"
    # Declaração só pode AUMENTAR o risco, nunca diminuir.
    if declarado in ORDEM_RISCO and ORDEM_RISCO.index(declarado) > ORDEM_RISCO.index(amb):
        amb = declarado
    return {
        "environment": amb,
        "capabilities": CAPACIDADES[amb],
        "signals": sinais,
        "database": b,
        "lab_path": _sqlite_no_lab(b),
    }


def exigir(capacidade, *, permitir_banco_novo_de_lab=False, confirmar_staging=False):
    """Levanta AmbienteRecusado se o ambiente atual não permite a capacidade."""
    info = detectar()
    amb, cap = info["environment"], info["capabilities"].get(capacidade)
    if cap is True:
        return info
    if capacidade == "reset" and amb == "DEV" and permitir_banco_novo_de_lab:
        b = info["database"]
        cara_de_lab = (
            info["lab_path"]
            or b["name"].lower().endswith(("_lab", "_test", "_ci"))
            or os.environ.get("AGENT_LAB_ALLOW_RESET") == "1"
        )
        # O arquivo em .lab/ é do laboratório por construção; um PG "<nome>_lab" sem marca
        # só é aceito vazio (primeira criação) ou com liberação explícita.
        if info["lab_path"] or (cara_de_lab and (banco_vazio() or os.environ.get("AGENT_LAB_ALLOW_RESET") == "1")):
            return info
        raise AmbienteRecusado(
            f"Recusado: banco DEV '{b['name']}' não é do laboratório (sem marca interna). "
            "Reset só em banco do lab (.lab/…sqlite3 ou <nome>_lab) vazio ou já marcado. "
            "Se for mesmo descartável: AGENT_LAB_ALLOW_RESET=1."
        )
    if cap == "controlada" and confirmar_staging:
        return info
    raise AmbienteRecusado(f"Recusado: '{capacidade}' não é permitido em {amb}. Sinais: {'; '.join(info['signals'])}")
