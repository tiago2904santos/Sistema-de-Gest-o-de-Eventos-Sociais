"""Views do laboratório: UI Lab (componentes isolados) e sonda de saúde."""

from __future__ import annotations

import platform
import sys
from collections import OrderedDict

import django
from django.conf import settings
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.http import Http404, JsonResponse
from django.shortcuts import render
from django.template.loader import render_to_string
from django.utils import timezone

from .inventory import templates_projeto
from .specimens import ESTADOS, all_specimens, by_id


def _liberado(request):
    # Instalado só com AGENT_LAB; ainda assim, fora do DEBUG exige superusuário.
    if not (settings.DEBUG or (request.user.is_authenticated and request.user.is_superuser)):
        raise Http404


def _render(spec, request):
    try:
        return render_to_string(spec.component, spec.context, request=request), None
    except Exception as exc:  # o lab mostra o erro em vez de cair
        return "", f"{type(exc).__name__}: {exc}"


def index(request):
    _liberado(request)
    grupos = OrderedDict()
    for spec in all_specimens():
        html, erro = _render(spec, request)
        grupos.setdefault(spec.component, []).append({"spec": spec, "html": html, "erro": erro})
    # Fumaça: todo componente de template precisa ao menos renderizar sem contexto.
    fumaca = []
    for nome, _ in templates_projeto():
        if nome.startswith("components/"):
            try:
                render_to_string(nome, {}, request=request)
                fumaca.append({"template": nome, "ok": True})
            except Exception as exc:
                fumaca.append({"template": nome, "ok": False, "erro": f"{type(exc).__name__}: {exc}"})
    return render(request, "agent_lab/index.html", {"grupos": grupos, "fumaca": fumaca, "estados": ESTADOS})


def specimen(request, spec_id):
    _liberado(request)
    spec = by_id().get(spec_id)
    if not spec:
        raise Http404
    html, erro = _render(spec, request)
    return render(request, "agent_lab/specimen.html", {"spec": spec, "html": html, "erro": erro})


def specimens_json(request):
    _liberado(request)
    return JsonResponse(
        {
            "specimens": [
                {"id": s.id, "component": s.component, "state": s.state, "interact": s.interact, "note": s.note}
                for s in all_specimens()
            ]
        }
    )


def health(request):
    _liberado(request)
    dados = {
        "python": sys.version.split()[0],
        "django": django.get_version(),
        "platform": platform.platform(),
        "debug": settings.DEBUG,
        "db_vendor": connection.vendor,
        # Com AGENT_LAB_FREEZE, o relógio do servidor parte da âncora do seed.
        "server_now": timezone.localtime().isoformat(),
    }
    try:
        with connection.cursor() as c:
            c.execute("SELECT 1")
        executor = MigrationExecutor(connection)
        pendentes = executor.migration_plan(executor.loader.graph.leaf_nodes())
        dados["db_ok"] = True
        dados["pending_migrations"] = [f"{m.app_label}.{m.name}" for m, _ in pendentes]
    except Exception as exc:
        dados["db_ok"] = False
        dados["db_error"] = f"{type(exc).__name__}: {exc}"
    try:
        from .seed import estado_atual

        dados["seed"] = estado_atual()
    except Exception as exc:
        dados["seed"] = {"error": repr(exc)}
    status = 200 if dados.get("db_ok") and not dados.get("pending_migrations") else 503
    return JsonResponse(dados, status=status)


def error_preview(request, code):
    """Mostra as páginas de erro próprias mesmo com DEBUG ligado (o Django
    troca 404/500 pelas páginas técnicas em desenvolvimento)."""
    _liberado(request)
    from django.views import defaults

    if code == 404:
        return defaults.page_not_found(request, Http404("prévia do laboratório"))
    if code == 403:
        from django.core.exceptions import PermissionDenied

        return defaults.permission_denied(request, PermissionDenied("prévia do laboratório"))
    if code == 500:
        return defaults.server_error(request)
    raise Http404
