"""Regras de obrigatoriedade de justificativa por prazo (Ofício)."""

from __future__ import annotations

from datetime import date
from typing import Any

from django.utils import timezone

from django.db import transaction

from core.deletion import excluir_com_protecao
from core.errors import capture

from viagens_cadastros.models import ConfiguracaoSistema

from .models import Justificativa
from .models import ModeloJustificativa
from .justificativas_selectors import get_or_none_justificativa_by_oficio


def get_prazo_justificativa_dias() -> int:
    """Prazo mínimo em dias corridos; do setor de quem gera, com fallback 10."""
    try:
        return int(ConfiguracaoSistema.atual().prazo_justificativa_dias)
    except Exception as exc:
        capture(exc, "justificativas.get_prazo_justificativa_dias")
        return 10


def get_primeira_saida_oficio(oficio):
    """
    Primeira saída do roteiro vinculado: `Roteiro.saida_dt`, senão primeiro trecho com `saida_dt`.
    Retorna datetime timezone-aware ou None.
    """
    roteiro = getattr(oficio, "roteiro", None)
    if roteiro is None:
        return None

    if roteiro.saida_dt:
        dt = roteiro.saida_dt
        if timezone.is_naive(dt):
            dt = timezone.make_aware(dt, timezone.get_current_timezone())
        return dt

    for trecho in roteiro.trechos.order_by("ordem", "pk"):
        if trecho.saida_dt:
            dt = trecho.saida_dt
            if timezone.is_naive(dt):
                dt = timezone.make_aware(dt, timezone.get_current_timezone())
            return dt
    return None


def calcular_dias_antecedencia_justificativa(oficio):
    """Dias entre a data da primeira saída e data_criacao do ofício; None se não avaliável."""
    primeira = get_primeira_saida_oficio(oficio)
    if primeira is None:
        return None
    d0 = oficio.data_criacao
    if not isinstance(d0, date):
        d0 = d0.date() if hasattr(d0, "date") else d0
    s_local = primeira.astimezone(timezone.get_current_timezone()).date()
    return (s_local - d0).days


def oficio_exige_justificativa(oficio) -> bool:
    return bool(avaliar_justificativa_oficio(oficio).get("obrigatoria"))


def avaliar_justificativa_oficio(oficio) -> dict[str, Any]:
    """
    Avalia se a justificativa é obrigatória pela regra de antecedência.

    status:
      - unknown — sem roteiro ou sem data de saída utilizável
      - required — obrigatória (antecedência <= prazo ou saída antes da criação)
      - not_applicable — regra avaliada e não obrigatória (antecedência > prazo)
    """
    prazo = get_prazo_justificativa_dias()
    d0 = oficio.data_criacao
    if isinstance(d0, date):
        d0_date = d0
    else:
        d0_date = d0.date()

    primeira = get_primeira_saida_oficio(oficio)
    if primeira is None:
        return {
            "obrigatoria": False,
            "primeira_saida": None,
            "data_criacao": d0_date,
            "dias_antecedencia": None,
            "prazo_dias": prazo,
            "status": "unknown",
            "motivo_regra": "Sem roteiro ou sem data de saída definida.",
        }

    s_local = primeira.astimezone(timezone.get_current_timezone()).date()
    dias = (s_local - d0_date).days

    if dias < 0:
        return {
            "obrigatoria": True,
            "primeira_saida": primeira,
            "data_criacao": d0_date,
            "dias_antecedencia": dias,
            "prazo_dias": prazo,
            "status": "required",
            "motivo_regra": "Saída anterior à data de criação do ofício.",
        }

    if dias <= prazo:
        return {
            "obrigatoria": True,
            "primeira_saida": primeira,
            "data_criacao": d0_date,
            "dias_antecedencia": dias,
            "prazo_dias": prazo,
            "status": "required",
            "motivo_regra": (
                f"Antecedência ({dias} dias) igual ou inferior ao prazo mínimo ({prazo} dias)."
            ),
        }

    return {
        "obrigatoria": False,
        "primeira_saida": primeira,
        "data_criacao": d0_date,
        "dias_antecedencia": dias,
        "prazo_dias": prazo,
        "status": "not_applicable",
        "motivo_regra": (
            f"Antecedência ({dias} dias) superior ao prazo mínimo ({prazo} dias)."
        ),
    }


@transaction.atomic
def get_or_create_justificativa_oficio(oficio):
    """Garante registro de Justificativa com snapshots da regra de prazo."""
    ev = avaliar_justificativa_oficio(oficio)
    defaults = {
        "obrigatoria": ev["obrigatoria"],
        "dias_antecedencia": ev["dias_antecedencia"],
        "prazo_dias": ev["prazo_dias"],
        "primeira_saida_dt": ev["primeira_saida"],
        "texto": "",
        "status": Justificativa.STATUS_RASCUNHO,
    }
    j, created = Justificativa.objects.get_or_create(oficio=oficio, defaults=defaults)
    if not created:
        j.obrigatoria = ev["obrigatoria"]
        j.dias_antecedencia = ev["dias_antecedencia"]
        j.prazo_dias = ev["prazo_dias"]
        j.primeira_saida_dt = ev["primeira_saida"]
        j.save(
            update_fields=[
                "obrigatoria",
                "dias_antecedencia",
                "prazo_dias",
                "primeira_saida_dt",
                "atualizado_em",
            ]
        )
    return j


@transaction.atomic
def atualizar_justificativa_oficio(oficio, form, action="save_draft"):
    """
    Persiste modelo/texto e atualiza snapshots. action: save_draft | save_continue.
    """
    if not getattr(form, "is_bound", False) or not form.is_valid():
        raise ValueError("Formulario de justificativa invalido.")

    j = get_or_create_justificativa_oficio(oficio)
    cd = form.cleaned_data
    j.modelo = cd.get("modelo")
    j.texto = cd.get("texto") or ""

    ev = avaliar_justificativa_oficio(oficio)
    j.obrigatoria = ev["obrigatoria"]
    j.dias_antecedencia = ev["dias_antecedencia"]
    j.prazo_dias = ev["prazo_dias"]
    j.primeira_saida_dt = ev["primeira_saida"]

    if action == "save_continue":
        j.status = Justificativa.STATUS_FINALIZADA
    else:
        j.status = Justificativa.STATUS_RASCUNHO

    j.save()
    return j


@transaction.atomic
def salvar_justificativa(oficio, modelo, texto):
    """Grava modelo e texto da justificativa do ofício, com a regra de prazo atualizada."""
    j = get_or_create_justificativa_oficio(oficio)
    j.modelo = modelo
    j.texto = texto or ""
    ev = avaliar_justificativa_oficio(oficio)
    j.obrigatoria = ev["obrigatoria"]
    j.dias_antecedencia = ev["dias_antecedencia"]
    j.prazo_dias = ev["prazo_dias"]
    j.primeira_saida_dt = ev["primeira_saida"]
    j.status = Justificativa.STATUS_FINALIZADA
    j.save()
    return j


def justificativa_oficio_esta_completa(oficio) -> bool:
    ev = avaliar_justificativa_oficio(oficio)
    if not ev["obrigatoria"]:
        return True
    j = get_or_none_justificativa_by_oficio(oficio)
    return bool(j and (j.texto or "").strip())


def avaliar_etapa_justificativa_oficio(oficio) -> dict[str, Any]:
    """Estado da etapa para wizard e templates."""
    ev = avaliar_justificativa_oficio(oficio)
    j = get_or_none_justificativa_by_oficio(oficio)
    pendencias = []
    primeira = ev["primeira_saida"]

    if ev["status"] == "unknown":
        pendencias.append("Defina data de saída no roteiro para avaliar a justificativa.")
        return {
            "obrigatoria": False,
            "status": "not_started",
            "pendencias": pendencias,
            "dias_antecedencia": ev["dias_antecedencia"],
            "prazo_dias": ev["prazo_dias"],
            "primeira_saida": primeira,
            "justificativa": j,
            "regra": ev,
        }

    if not ev["obrigatoria"]:
        return {
            "obrigatoria": False,
            "status": "not_required",
            "pendencias": [],
            "dias_antecedencia": ev["dias_antecedencia"],
            "prazo_dias": ev["prazo_dias"],
            "primeira_saida": primeira,
            "justificativa": j,
            "regra": ev,
        }

    texto_ok = bool(j and (j.texto or "").strip())
    if not texto_ok:
        pendencias.append("Informe o texto da justificativa.")
        status_etapa = "incomplete"
    else:
        status_etapa = "complete"

    return {
        "obrigatoria": True,
        "status": status_etapa,
        "pendencias": pendencias,
        "dias_antecedencia": ev["dias_antecedencia"],
        "prazo_dias": ev["prazo_dias"],
        "primeira_saida": primeira,
        "justificativa": j,
        "regra": ev,
    }


