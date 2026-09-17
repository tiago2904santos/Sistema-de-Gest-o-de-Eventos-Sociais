"""Contexto plano (placeholders) dos modelos plano_trabalho.docx e plano_trabalho_multievento.docx."""

from __future__ import annotations

from decimal import Decimal

from django.utils import timezone

from documentos.services.formatters import format_city_uf, format_document_display
from viagens_cadastros.selectors import build_configuracao_context
from viagens_oficios.docxtpl_context import _assinatura_nome_cargo, _build_endereco, _build_sede
from viagens_roteiros.services.diarias import formatar_valor
from viagens_roteiros.services.valor_extenso import valor_por_extenso_ptbr

from . import services


def _txt(valor):
    return str(valor or "").strip()


def _destinos_unicos(plano):
    """Os destinos do plano e dos eventos, sem repetir."""
    rotulos = []
    if plano.pk:
        for d in plano.destinos.select_related("cidade__estado").order_by("ordem", "pk"):
            if d.cidade_id:
                rotulo = format_city_uf(f"{d.cidade.nome}/{d.cidade.estado.sigla}")
                if rotulo and rotulo not in rotulos:
                    rotulos.append(rotulo)
    if not rotulos and plano.destino_cidade_id:
        rotulos.append(format_city_uf(f"{plano.destino_cidade.nome}/{plano.destino_cidade.estado.sigla}"))
    return ", ".join(rotulos)


def _build_valor_multi_richtext(plano):
    """Os blocos de valor, com "Valor do evento dia/dias:" e "Valor total:" em negrito."""
    from docxtpl import RichText

    def bloco(rt, rotulo, sufixo, composicao, unitario_val, total_val, *, primeiro):
        if total_val is None or unitario_val is None:
            return primeiro
        total, unitario = Decimal(total_val), Decimal(unitario_val)
        if not primeiro:
            rt.add("\n\n")
        rt.add(rotulo, bold=True)
        rt.add(
            f"{sufixo}: R${formatar_valor(total)} ({valor_por_extenso_ptbr(total)}).\n"
            f"Valor correspondente a {composicao}, por servidor, no valor unitário "
            f"de R${formatar_valor(unitario)} ({valor_por_extenso_ptbr(unitario)})."
        )
        return False

    rt = RichText()
    primeiro = True
    for evento in plano.eventos_ordenados:
        curta, dia_unico = services._evento_data_curta(evento)
        primeiro = bloco(
            rt, f"Valor do evento {'dia' if dia_unico else 'dias'}:", f" {curta}" if curta else "",
            evento.diarias_composicao, evento.diarias_valor_unitario, evento.diarias_valor_total, primeiro=primeiro,
        )
    bloco(
        rt, "Valor total:", "", plano.diarias_combinada_composicao,
        plano.diarias_combinada_valor_unitario, plano.diarias_combinada_valor_total, primeiro=primeiro,
    )
    return rt


def _build_eventos_doc(plano):
    """Um item por evento para os laços `{% for ev in eventos %}` do modelo de vários eventos."""
    linhas = []
    for evento in plano.eventos_ordenados:
        itens = services._atividades_evento_ordenadas(evento)
        cabecalho = services._evento_data_header(evento)
        programa = _txt(evento.programa_display)
        linhas.append({
            "data_header": cabecalho,
            "titulo": f"{cabecalho} - {programa}" if programa else cabecalho,
            "local": format_city_uf(evento.destino_display),
            "horario": _txt(evento.horario_atendimento),
            "efetivo": services.montar_efetivo_evento_texto(evento),
            "unidade_movel": services.montar_unidade_movel_texto(itens),
            "metas": services.montar_metas_texto(itens),
            "atividades": services.montar_atividades_texto(itens),
            "recursos": services.montar_recursos_texto(itens),
        })
    return linhas


def _data_evento_agregada(plano):
    if plano.is_multi_evento and plano.pk:
        eventos = list(plano.eventos.exclude(data_evento_inicio__isnull=True))
        if not eventos:
            return ""
        inicio = min(e.data_evento_inicio for e in eventos)
        fim = max((e.data_evento_fim or e.data_evento_inicio) for e in eventos)
        return services.format_periodo_evento_extenso(inicio, fim)
    return services.format_periodo_evento_extenso(plano.data_evento_inicio, plano.data_evento_fim)


def build_plano_docxtpl_context(plano):
    multi = bool(plano.is_multi_evento and plano.pk)
    if multi:
        # Metas, atividades, atuação e recursos saem do laço `eventos` do modelo.
        itens = services._atividades_combinadas_multi(plano)
        metas_txt = atividades_txt = recursos_txt = ""
        valor_txt = _build_valor_multi_richtext(plano)
    else:
        itens = services._atividades_selecionadas_ordenadas(plano)
        metas_txt = services.montar_metas_texto(itens)
        atividades_txt = _txt(plano.atividades) or services.montar_atividades_texto(itens)
        recursos_txt = services.montar_recursos_texto(itens)
        valor_txt = services.montar_valor_do_plano_texto(plano)

    inst = build_configuracao_context()
    nome_chefia, cargo_chefia = _assinatura_nome_cargo(inst, "PLANO_TRABALHO", fallback_geral=False)
    if plano.is_multi_evento:
        destinos = _destinos_unicos(plano)
    else:
        destinos = format_city_uf(plano.destino_display) if plano.destino_cidade_id else ""

    return {
        "numero_plano_trabalho": plano.numero_formatado if plano.numero else "—",
        "unidade": _txt(inst.get("unidade")) or _txt(inst.get("nome_orgao")),
        "contextualizacao": _txt(plano.contextualizacao),
        "metas": metas_txt,
        "atividades": atividades_txt,
        "data_evento": _data_evento_agregada(plano),
        "destinos": destinos,
        "horario_de_atendimento": _txt(plano.horario_atendimento),
        "efetivos": services.montar_efetivo_texto(plano),
        "unidade_movel": services.montar_unidade_movel_texto(itens),
        "valor_do_plano": valor_txt,
        "recursos_necessarios": recursos_txt,
        # Automático regenera (e garante só o administrativo no de vários eventos); editado à mão vale o gravado.
        "coordenacao": services.montar_texto_coordenacao(plano) if plano.coordenacao_auto else _txt(plano.coordenacao),
        "consideracao_final": _txt(plano.consideracao_final),
        "divisao": _txt(inst.get("divisao")).upper(),
        "unidade_rodape": format_document_display(_txt(inst.get("divisao") or inst.get("unidade") or inst.get("nome_orgao"))),
        "endereco": _build_endereco(inst),
        "telefone": _txt(inst.get("telefone_formatado") or inst.get("telefone")),
        "email": (_txt(inst.get("email")) or "").lower(),
        "sede": _build_sede(inst),
        "data_extenso": services.format_data_extenso(timezone.localdate()),
        "nome_chefia": format_document_display(nome_chefia) if nome_chefia else "",
        "cargo_chefia": format_document_display(cargo_chefia) if cargo_chefia else "",
        "is_multi_evento": multi,
        "eventos": _build_eventos_doc(plano) if multi else [],
    }
