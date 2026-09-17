"""Gravação do efetivo e das diárias do plano (cartão 2).

A ordem importa: o efetivo é reconciliado primeiro e a diária recalculada
depois, porque o valor é função do total do efetivo.
"""

from dataclasses import dataclass

from django.db import transaction

from viagens_cadastros.models import Cargo, Unidade

from .services import atualizar_snapshot_diarias, atualizar_snapshot_diarias_combinadas


@dataclass(frozen=True)
class ResultadoEfetivo:
    efetivo: list
    diarias: dict | None


def _inteiro(valor):
    if valor in (None, ""):
        return None
    try:
        return int(valor)
    except (TypeError, ValueError):
        return None


@transaction.atomic
def reconciliar_efetivo(plano, rows):
    """Reconcilia o efetivo com as linhas da tela, por id.

    Linha com cargo e quantidade válidos é criada ou atualizada; incompleta é
    ignorada; (unidade, cargo) repetido fica só na primeira; id que não veio
    é apagado.
    """
    existentes = {e.pk: e for e in plano.efetivos.all()}
    mantidos = set()
    saida = []
    vistos = set()
    for indice, row in enumerate(rows or []):
        if not isinstance(row, dict):
            continue
        cargo_id, quantidade, unidade_id = _inteiro(row.get("cargo")), _inteiro(row.get("quantidade")), _inteiro(row.get("unidade"))
        if not cargo_id or not quantidade or quantidade <= 0:
            continue
        if not Cargo.objects.filter(pk=cargo_id).exists():
            continue
        if unidade_id and not Unidade.objects.filter(pk=unidade_id).exists():
            unidade_id = None
        chave = (unidade_id, cargo_id)
        if chave in vistos:
            continue
        vistos.add(chave)
        row_id = _inteiro(row.get("id"))
        if row_id and row_id in existentes:
            efetivo = existentes[row_id]
            efetivo.unidade_id, efetivo.cargo_id, efetivo.quantidade = unidade_id, cargo_id, quantidade
            efetivo.save(update_fields=["unidade", "cargo", "quantidade", "atualizado_em"])
            mantidos.add(row_id)
        else:
            efetivo = plano.efetivos.create(unidade_id=unidade_id, cargo_id=cargo_id, quantidade=quantidade)
            mantidos.add(efetivo.pk)
        saida.append({"idx": _inteiro(row.get("idx")) if _inteiro(row.get("idx")) is not None else indice, "id": efetivo.pk})
    remover = [pk for pk in existentes if pk not in mantidos]
    if remover:
        plano.efetivos.filter(pk__in=remover).delete()
    return saida


def recalcular_diarias(plano):
    resultado = atualizar_snapshot_diarias(plano)
    if plano.is_multi_evento:
        atualizar_snapshot_diarias_combinadas(plano)
    return resultado


@transaction.atomic
def salvar_efetivo_e_diarias(plano, *, rows, diarias_form):
    efetivo = reconciliar_efetivo(plano, rows)
    plano = diarias_form.save()
    return ResultadoEfetivo(efetivo=efetivo, diarias=recalcular_diarias(plano))


def linhas_do_formset(formset):
    """As linhas do formset de efetivo no formato de `reconciliar_efetivo`."""
    rows = []
    for indice, form in enumerate(formset.forms):
        cleaned = getattr(form, "cleaned_data", None)
        if not cleaned or cleaned.get("DELETE"):
            continue
        unidade, cargo = cleaned.get("unidade"), cleaned.get("cargo")
        rows.append({
            "idx": indice,
            "id": form.instance.pk or _inteiro(form.data.get(form.add_prefix("id"))),
            "unidade": unidade.pk if unidade else None,
            "cargo": cargo.pk if cargo else None,
            "quantidade": cleaned.get("quantidade"),
        })
    return rows
