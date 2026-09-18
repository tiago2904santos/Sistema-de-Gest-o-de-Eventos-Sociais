"""Como o plano se apresenta: na lista, nos cartões de evento e no painel da viagem."""

from django.urls import reverse

from viagens_roteiros.services.diarias import formatar_valor
from viagens_roteiros.services.valor_extenso import valor_por_extenso_ptbr

from .models import PlanoTrabalho
from .services import format_periodo_evento_extenso, montar_efetivo_evento_texto, montar_efetivo_texto

SEM_VALOR = {"—", "", "Destino não informado", "Período não informado"}


def selo_do_plano(plano):
    if plano.cancelado:
        return "Cancelado", "cancelada"
    if plano.status == PlanoTrabalho.STATUS_GERADO:
        return "Gerado", "atendido"
    return "Rascunho", "neutro"


def _agregado_multi(plano):
    """No plano de vários eventos os campos do plano são o rascunho: agrega dos eventos."""
    eventos = list(plano.eventos.all()) if plano.pk else []
    destinos = []
    for e in eventos:
        d = e.destino_display
        if d not in SEM_VALOR and d not in destinos:
            destinos.append(d)
    inicios = [e.data_evento_inicio for e in eventos if e.data_evento_inicio]
    fins = [e.data_evento_fim or e.data_evento_inicio for e in eventos if e.data_evento_inicio]
    if inicios:
        ini, fim = min(inicios), max(fins)
        periodo = ini.strftime("%d/%m/%Y") if ini == fim else f"{ini.strftime('%d/%m/%Y')} a {fim.strftime('%d/%m/%Y')}"
    else:
        periodo = ""
    n = len(eventos)
    return {
        "programa": f"{n} eventos" if n != 1 else "1 evento",
        "destino": ", ".join(destinos),
        "periodo": periodo,
        "efetivo_total": plano.total_efetivo_combinado,
        "valor_total": plano.diarias_combinada_valor_total,
    }


def resumo_do_plano(plano):
    if plano.is_multi_evento:
        return _agregado_multi(plano)
    return {
        "programa": plano.programa_display or "",
        "destino": "" if plano.destino_display in SEM_VALOR else plano.destino_display,
        "periodo": "" if plano.periodo_display in SEM_VALOR else plano.periodo_display,
        "efetivo_total": plano.total_efetivo,
        "valor_total": plano.diarias_valor_total,
    }


def fatos_do_plano(plano):
    """Os dados do cartão como itens separados, um ícone para cada; o vazio é nomeado."""
    r = resumo_do_plano(plano)
    coordenador, _ = plano.coordenador_nome_cargo("adm")
    fatos = [
        {"icone": "calendar", "rotulo": "Período", "texto": r["periodo"] or "Sem período", "ausente": not r["periodo"]},
        {"icone": "map-pin", "rotulo": "Destino", "texto": r["destino"] or "Sem destino", "ausente": not r["destino"]},
        {"icone": "landmark", "rotulo": "Programa", "texto": r["programa"] or "Sem programa", "ausente": not r["programa"]},
        {"icone": "user", "rotulo": "Coordenador", "texto": coordenador or "Sem coordenador", "ausente": not coordenador},
        {"icone": "users", "rotulo": "Efetivo", "texto": f"{r['efetivo_total']} no efetivo" if r["efetivo_total"] else "Sem efetivo", "ausente": not r["efetivo_total"]},
    ]
    if r["valor_total"] is not None:
        fatos.append({"icone": "landmark", "rotulo": "Diárias", "texto": f"R$ {formatar_valor(r['valor_total'])}", "ausente": False})
    if plano.viagem_id:
        fatos.append({"icone": "truck", "rotulo": "Viagem", "texto": str(plano.viagem), "ausente": False})
    return fatos


def linha_da_lista(plano):
    selo, tom = selo_do_plano(plano)
    return {
        "plano": plano,
        "titulo": f"Plano de Trabalho {plano.numero_formatado}",
        "selo": selo,
        "selo_tom": tom,
        "fatos": fatos_do_plano(plano),
        "url_editar": reverse("viagens_planos:editar", args=[plano.pk]),
        "url_visualizar": reverse("viagens_planos:gerar", args=[plano.pk, "pdf"]) + "?inline=1",
        "url_pdf": reverse("viagens_planos:gerar", args=[plano.pk, "pdf"]),
        "url_docx": reverse("viagens_planos:gerar", args=[plano.pk, "docx"]),
        "url_excluir": reverse("viagens_planos:acao", args=[plano.pk, "excluir"]),
        "url_cancelar": reverse("viagens_planos:acao", args=[plano.pk, "cancelar"]),
        "url_reativar": reverse("viagens_planos:acao", args=[plano.pk, "reativar"]),
    }


# ── Cartões de evento (plano de vários eventos) ──────────────────────────────


def _efetivo_itens(efetivos):
    itens = []
    for item in efetivos.select_related("cargo", "unidade").order_by("cargo__nome"):
        if not item.quantidade or not item.cargo_id:
            continue
        cargo_nome = (item.cargo.nome or "").strip()
        if not cargo_nome:
            continue
        unidade = ((item.unidade.sigla or "").strip() or (item.unidade.nome or "").strip()) if item.unidade_id else ""
        itens.append({"quantidade": int(item.quantidade), "cargo": cargo_nome, "unidade": unidade})
    return itens


def apresentar_evento_card(evento):
    nome_op, cargo_op = evento.coordenador_nome_cargo()
    atividades = list(evento.atividades_selecionadas.order_by("nome")) if evento.pk else []
    return {
        "id": evento.pk,
        "ordem": evento.ordem,
        "titulo": f"Evento {evento.ordem}",
        "programa": evento.programa_display or "—",
        "destino": evento.destino_display,
        "periodo": evento.periodo_display,
        "horario": (evento.horario_atendimento or "").strip() or "—",
        "coordenador_op": nome_op or "—",
        "coordenador_op_cargo": cargo_op or "",
        "efetivo_total": evento.total_efetivo,
        "efetivo_texto": montar_efetivo_evento_texto(evento),
        "valor_total_display": f"R$ {formatar_valor(evento.diarias_valor_total)}" if evento.diarias_valor_total is not None else "",
        "valor_unitario_display": f"R$ {formatar_valor(evento.diarias_valor_unitario)}" if evento.diarias_valor_unitario is not None else "",
        "diarias_composicao": (evento.diarias_composicao or "").strip(),
        "atividades": [a.nome for a in atividades],
        "atividades_count": len(atividades),
        "editar_url": reverse("viagens_planos:evento_editar", args=[evento.plano_id, evento.pk]),
        "excluir_url": reverse("viagens_planos:evento_remover", args=[evento.plano_id, evento.pk]),
    }


def apresentar_resumo_evento_card(evento):
    """O cartão de resumo de um evento gravado, como o da etapa 4 da origem."""
    card = apresentar_evento_card(evento)
    card["valor_total_display"] = card["valor_total_display"] or "—"
    card["valor_unitario_display"] = card["valor_unitario_display"] or "—"
    card["diarias_composicao"] = card["diarias_composicao"] or "—"
    card["coordenador_op_presente"] = card["coordenador_op"] != "—"
    card["data_evento_extenso"] = format_periodo_evento_extenso(evento.data_evento_inicio, evento.data_evento_fim) or "—"
    card["valor_extenso"] = valor_por_extenso_ptbr(evento.diarias_valor_total) if evento.diarias_valor_total is not None else "—"
    card["efetivo_itens"] = _efetivo_itens(evento.efetivos)
    return card


def apresentar_resumo_header(plano):
    nome_adm, cargo_adm = plano.coordenador_nome_cargo("adm")
    return {
        "numero": plano.numero_formatado,
        "coordenador_adm_nome": nome_adm or "—",
        "coordenador_adm_cargo": cargo_adm or "",
        "is_multi": plano.is_multi_evento,
    }


def resumo_do_plano_para_tela(plano):
    """O resumo do cartão 4 (destino, período, programa, horário, efetivo e valor)."""
    from .services import montar_texto_coordenacao, montar_valor_do_plano_texto

    return {
        "destino": plano.destino_display,
        "periodo": plano.periodo_display,
        "programa": plano.programa_display or "—",
        "horario": plano.horario_atendimento or "—",
        "efetivo": montar_efetivo_texto(plano) or "—",
        "valor_plano": montar_valor_do_plano_texto(plano) or "—",
        "coordenacao": (plano.coordenacao or "").strip() or (montar_texto_coordenacao(plano) if plano.coordenacao_auto else "") or "—",
    }
