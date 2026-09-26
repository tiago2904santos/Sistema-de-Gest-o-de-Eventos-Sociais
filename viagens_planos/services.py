"""Regras do plano de trabalho: textos padrão, efetivo, diárias, atividades,
eventos do plano de vários eventos, pendências, numeração e documento.

Portado inteiro do Gerenciador de Viagens. O que mudou é o motor das diárias
(o da casa, `viagens_roteiros.services.diarias`), a sede (da configuração do
setor de quem pede) e os catálogos, que aqui são alfabéticos e sem "ativo".
"""

from __future__ import annotations

import re
from datetime import date, datetime, time, timedelta
from decimal import Decimal

from django.db import transaction
from django.db.models import Max
from django.utils import timezone

from core.deletion import excluir_com_protecao
from core.numeracao import NAMESPACE_PLANO_TRABALHO, reservar_numero
from documentos.services.facade import DocumentoFacade
from documentos.services.formatters import format_city_uf, format_document_display
from documentos.services.types import DocumentoFormato, DocumentoTipo
from viagens_cadastros.models import ConfiguracaoSistema
from viagens_roteiros.services.diarias import Marcador, RoteiroIncalculavel, SemTabelaDeDiarias, calcular_diarias, formatar_valor
from viagens_roteiros.services.valor_extenso import valor_por_extenso_ptbr

from .models import (
    CONSTRAINT_NUMERO_PLANO_TRABALHO,
    HORARIO_ATENDIMENTO_PADRAO,
    AtividadePlanoTrabalho,
    EfetivoEvento,
    EfetivoPlano,
    EventoPlano,
    PlanoDestino,
    PlanoTrabalho,
    PresetAtividadesPlanoTrabalho,
)


@transaction.atomic
def excluir_plano(plano):
    """Exclui o plano e libera o número para o próximo do ano, como no ofício."""
    from .models import PlanoTrabalhoNumeroLacuna

    numero, ano = plano.numero, plano.ano
    excluir_com_protecao(plano)
    if numero and ano:
        PlanoTrabalhoNumeroLacuna.objects.get_or_create(ano=ano, numero=numero)


_MESES_PT = (
    "", "janeiro", "fevereiro", "março", "abril", "maio", "junho",
    "julho", "agosto", "setembro", "outubro", "novembro", "dezembro",
)

TEXTO_PADRAO_CONTEXTUALIZACAO = (
    "A Assessoria de Comunicação Social da Polícia Civil do Paraná (PCPR), no âmbito do "
    'programa "PCPR na Comunidade", promoverá ação itinerante no município de {municipio}.\n\n'
    "A iniciativa visa atender à solicitação formulada pelo {programa} (Ofício em anexo), "
    "levando serviços essenciais de polícia judiciária às populações urbanas, rurais e "
    "ribeirinhas, especialmente em localidades de difícil acesso.\n\n"
    "A ação tem como foco principal garantir o acesso à documentação básica e prestar "
    "orientações de polícia judiciária, promovendo cidadania e fortalecendo a aproximação "
    "institucional com a comunidade."
)

TEXTO_PADRAO_CONSIDERACAO_FINAL = (
    "A realização da ação no município de {municipio} reforça o compromisso institucional "
    "da Polícia Civil do Paraná com a promoção da cidadania e com a ampliação do acesso a "
    "serviços públicos essenciais, especialmente em regiões com limitações de deslocamento "
    "e maior vulnerabilidade social."
)

TEXTO_COORDENADOR_ADM = (
    "Fica {designado} como {coordenador_administrativo} do Plano {artigo} {cargo_nome}, "
    "{artigo} qual ficará responsável pelo acompanhamento da execução administrativa do presente "
    "Plano de Trabalho, organização das escalas de servidores, controle de materiais e "
    "equipamentos, consolidação de dados estatísticos, elaboração de relatório final e demais "
    "providências necessárias ao regular cumprimento da ação."
)

TEXTO_COORDENADOR_OP = (
    "Fica {designado} como {coordenador_operacional} {artigo} {cargo_nome}, "
    "{artigo} qual ficará responsável pela execução operacional da ação no local do evento, "
    "acompanhamento das equipes e suporte às demandas surgidas durante o atendimento."
)

_MUNICIPIO_PLACEHOLDER = "________"


# ── Textos padrão ────────────────────────────────────────────────────────────


def _cidade_uf(cidade):
    return format_city_uf(f"{cidade.nome}/{cidade.estado.sigla}")


def _municipio_display(plano):
    rotulos = []
    if plano.pk:
        for destino in plano.destinos_rascunho():
            if destino.cidade_id:
                rotulos.append(_cidade_uf(destino.cidade))
    if not rotulos and plano.destino_cidade_id:
        rotulos.append(_cidade_uf(plano.destino_cidade))
    unicos = list(dict.fromkeys(r for r in rotulos if r))
    return ", ".join(unicos) if unicos else _MUNICIPIO_PLACEHOLDER


def _programa_display(plano):
    if plano.is_multi_evento and plano.pk:
        nomes = [format_document_display(e.programa_display) for e in plano.eventos_ordenados if e.programa_display]
        nomes = list(dict.fromkeys(nomes))
        return ", ".join(nomes) if nomes else "________"
    texto = plano.programa_display
    return format_document_display(texto) if texto else "________"


def texto_padrao_contextualizacao(plano):
    return TEXTO_PADRAO_CONTEXTUALIZACAO.format(municipio=_municipio_display(plano), programa=_programa_display(plano))


def texto_padrao_consideracao_final(plano):
    return TEXTO_PADRAO_CONSIDERACAO_FINAL.format(municipio=_municipio_display(plano))


def texto_padrao_coordenacao(plano):
    return montar_texto_coordenacao(plano)


def sincronizar_textos_padrao(plano):
    """Regenera os textos cujo `*_auto` está ligado; devolve os campos alterados."""
    alterados = []
    if plano.contextualizacao_auto:
        plano.contextualizacao = texto_padrao_contextualizacao(plano)
        alterados.append("contextualizacao")
    if plano.coordenacao_auto:
        plano.coordenacao = texto_padrao_coordenacao(plano)
        alterados.append("coordenacao")
    if plano.consideracao_auto:
        plano.consideracao_final = texto_padrao_consideracao_final(plano)
        alterados.append("consideracao_final")
    return alterados


def aplicar_textos_padrao(plano):
    """Preenche só o que está vazio; devolve os campos alterados."""
    alterados = []
    if not (plano.contextualizacao or "").strip():
        plano.contextualizacao = texto_padrao_contextualizacao(plano)
        alterados.append("contextualizacao")
    if not (plano.coordenacao or "").strip():
        texto = texto_padrao_coordenacao(plano)
        if texto:
            plano.coordenacao = texto
            alterados.append("coordenacao")
    if not (plano.consideracao_final or "").strip():
        plano.consideracao_final = texto_padrao_consideracao_final(plano)
        alterados.append("consideracao_final")
    return alterados


def _termos_genero_coordenador(genero):
    feminino = genero == PlanoTrabalho.COORDENADOR_GENERO_FEMININO
    return {
        "designado": "designada" if feminino else "designado",
        "artigo": "a" if feminino else "o",
        "coordenador_administrativo": "Coordenadora Administrativa" if feminino else "Coordenador Administrativo",
        "coordenador_operacional": "Coordenadora Operacional do Evento" if feminino else "Coordenador Operacional do Evento",
    }


def _cargo_nome(cargo, nome):
    return " ".join(p for p in (format_document_display(cargo), format_document_display(nome)) if p)


def montar_texto_coordenacao(plano):
    """Parágrafos de designação: o administrativo sempre; o operacional quando há."""
    paragrafos = []
    nome_adm, cargo_adm = plano.coordenador_nome_cargo("adm")
    if nome_adm:
        paragrafos.append(TEXTO_COORDENADOR_ADM.format(
            cargo_nome=_cargo_nome(cargo_adm, nome_adm), **_termos_genero_coordenador(plano.coordenador_genero("adm")),
        ))
    # No plano de vários eventos o operacional varia por evento: o documento só designa o administrativo.
    if plano.is_multi_evento:
        return "\n\n".join(paragrafos)
    nome_op, cargo_op = plano.coordenador_nome_cargo("op")
    if nome_op:
        paragrafos.append(TEXTO_COORDENADOR_OP.format(
            cargo_nome=_cargo_nome(cargo_op, nome_op), **_termos_genero_coordenador(plano.coordenador_genero("op")),
        ))
    return "\n\n".join(paragrafos)


# ── Períodos e efetivo ───────────────────────────────────────────────────────


def format_data_extenso(valor):
    return f"{valor.day} de {_MESES_PT[valor.month]} de {valor.year}"


def format_periodo_evento_extenso(data_inicio, data_fim):
    """'25 a 27 de junho de 2026', '30 de junho a 02 de julho de 2026'…"""
    if not data_inicio:
        return ""
    if not data_fim or data_fim == data_inicio:
        return format_data_extenso(data_inicio)
    d1, d2 = f"{data_inicio.day:02d}", f"{data_fim.day:02d}"
    m1, m2 = _MESES_PT[data_inicio.month], _MESES_PT[data_fim.month]
    if data_inicio.year == data_fim.year and data_inicio.month == data_fim.month:
        return f"{d1} a {d2} de {m1} de {data_inicio.year}"
    if data_inicio.year == data_fim.year:
        return f"{d1} de {m1} a {d2} de {m2} de {data_inicio.year}"
    return f"{d1} de {m1} de {data_inicio.year} a {d2} de {m2} de {data_fim.year}"


_CONECTORES_PT = {"de", "da", "do", "das", "dos", "e"}
_VOGAIS_PT = "aeiouáéíóúàâêîôûãõ"


def _is_sigla(palavra):
    # Cargos vêm em maiúsculas, então o caso não distingue sigla; só palavras curtas contam.
    limpa = "".join(c for c in palavra if c.isalpha())
    return bool(limpa) and limpa.isascii() and limpa.isupper() and len(limpa) <= 3


def _pluralizar_palavra_pt(palavra):
    if not palavra:
        return palavra
    if palavra.endswith("ão"):
        return palavra[:-2] + "ões"
    if palavra.endswith("il"):
        return palavra[:-2] + "is"
    ultima = palavra[-1]
    if ultima in _VOGAIS_PT:
        return palavra + "s"
    if ultima == "l" and len(palavra) >= 2:
        return palavra[:-1] + "is"
    if ultima in ("r", "z", "n"):
        return palavra + "es"
    if ultima == "m":
        return palavra[:-1] + "ns"
    if ultima == "s":
        return palavra
    return palavra + "s"


def _cargo_rotulo(nome, *, plural):
    """'POLICIAL CIVIL' → 'Policiais Civis' (plural) ou 'Policial Civil'."""
    partes = []
    for token in (nome or "").split():
        if _is_sigla(token):
            partes.append(token)
            continue
        baixo = token.lower()
        if plural and baixo not in _CONECTORES_PT:
            baixo = _pluralizar_palavra_pt(baixo)
        partes.append(baixo)
    return format_document_display(" ".join(partes))


def _efetivo_unidade_rotulo(unidade):
    if unidade is None:
        return ""
    return (unidade.sigla or "").strip() or (unidade.nome or "").strip()


def _efetivo_linha(cargo_nome, unidade_nome, quantidade):
    """'2 Agentes de Polícia Judiciária (ASCOM)' — a unidade só entra quando informada."""
    rotulo = _cargo_rotulo(cargo_nome, plural=quantidade > 1)
    sufixo = f" ({unidade_nome})" if unidade_nome else ""
    return f"{quantidade} {rotulo}{sufixo}"


def _montar_efetivo_linhas(itens):
    linhas = []
    for item in itens:
        if not item.quantidade or not item.cargo_id:
            continue
        cargo_nome = (item.cargo.nome or "").strip()
        if not cargo_nome:
            continue
        linhas.append(_efetivo_linha(cargo_nome, _efetivo_unidade_rotulo(item.unidade if item.unidade_id else None), int(item.quantidade)))
    return "\n".join(linhas)


def montar_efetivo_texto(plano):
    """Uma linha por cargo/unidade; no plano de vários eventos soma o de todos."""
    if plano.is_multi_evento and plano.pk:
        agregados = {}
        for evento in plano.eventos.all():
            for item in evento.efetivos.select_related("cargo", "unidade"):
                if not item.quantidade or not item.cargo_id:
                    continue
                cargo_nome = (item.cargo.nome or "").strip()
                if not cargo_nome:
                    continue
                unidade_nome = _efetivo_unidade_rotulo(item.unidade if item.unidade_id else None)
                chave = (item.cargo_id, item.unidade_id)
                _c, _u, anterior = agregados.get(chave, (cargo_nome, unidade_nome, 0))
                agregados[chave] = (cargo_nome, unidade_nome, anterior + int(item.quantidade))
        return "\n".join(
            _efetivo_linha(c, u, q) for c, u, q in sorted(agregados.values(), key=lambda v: (v[1], v[0]))
        )
    return _montar_efetivo_linhas(plano.efetivos.select_related("cargo", "unidade").order_by("unidade__nome", "cargo__nome"))


def montar_efetivo_evento_texto(evento):
    return _montar_efetivo_linhas(evento.efetivos.select_related("cargo", "unidade").order_by("unidade__nome", "cargo__nome"))


# ── Diárias ──────────────────────────────────────────────────────────────────


def _sede_cidade_uf():
    config = ConfiguracaoSistema.atual()
    cidade = config.cidade_sede_padrao
    if cidade is not None:
        return cidade.nome or "", cidade.estado.sigla or ""
    return config.cidade_endereco or "", config.uf or ""


def _resultado_diarias(marcadores, chegada, quantidade_servidores):
    """O motor da casa, com o resultado no formato que a tela e o documento leem."""
    sede_cidade, sede_uf = _sede_cidade_uf()
    resultado = calcular_diarias(
        marcadores, chegada, quantidade_servidores=quantidade_servidores,
        sede_cidade=sede_cidade or None, sede_uf=sede_uf or None,
    )
    totais = resultado["totais"]
    valor_unitario = totais["valor_por_servidor_decimal"]
    valor_total = totais["total_valor_decimal"]
    return {
        "ok": True,
        "erros": [],
        "composicao": totais["resumo_diarias"],
        "valor_unitario": valor_unitario,
        "valor_total": valor_total,
        "valor_unitario_display": formatar_valor(valor_unitario),
        "valor_total_display": formatar_valor(valor_total),
        "valor_unitario_extenso": valor_por_extenso_ptbr(valor_unitario),
        "valor_total_extenso": valor_por_extenso_ptbr(valor_total),
        "quantidade_servidores": quantidade_servidores,
        "periodos": resultado["trechos"],
    }


def _erro_de_calculo(exc):
    return {"ok": False, "erros": [str(exc)]}


def calcular_diarias_plano(plano, total_efetivo=None):
    """Um período só: sede → destino (saída) … chegada na sede.

    `total_efetivo` permite calcular com o efetivo ainda não gravado (a prévia ao vivo).
    Devolve {ok, erros[], composicao, valor_unitario, valor_total, displays e extensos}.
    """
    erros = []
    if not (plano.saida_sede_data and plano.saida_sede_hora):
        erros.append("Informe data e hora de saída da sede.")
    if not (plano.chegada_sede_data and plano.chegada_sede_hora):
        erros.append("Informe data e hora de chegada na sede.")
    if not plano.destino_cidade_id:
        erros.append("Informe o destino na identificação.")
    if total_efetivo is None:
        total_efetivo = plano.total_efetivo
    if total_efetivo <= 0:
        erros.append("Informe o efetivo (cargo e quantidade).")
    if erros:
        return {"ok": False, "erros": erros}

    saida = datetime.combine(plano.saida_sede_data, plano.saida_sede_hora)
    chegada = datetime.combine(plano.chegada_sede_data, plano.chegada_sede_hora)
    if chegada <= saida:
        return {"ok": False, "erros": ["A chegada na sede deve ser depois da saída."]}

    marcador = Marcador(saida=saida, destino_cidade=plano.destino_cidade.nome, destino_uf=plano.destino_cidade.estado.sigla)
    try:
        return _resultado_diarias([marcador], chegada, total_efetivo)
    except (RoteiroIncalculavel, SemTabelaDeDiarias, ValueError) as exc:
        return _erro_de_calculo(exc)


def atualizar_snapshot_diarias(plano, *, save=True):
    """Recalcula e grava a composição e os valores das diárias no plano."""
    resultado = calcular_diarias_plano(plano)
    if resultado["ok"]:
        plano.diarias_composicao = resultado["composicao"]
        plano.diarias_valor_unitario = resultado["valor_unitario"]
        plano.diarias_valor_total = resultado["valor_total"]
    else:
        plano.diarias_composicao = ""
        plano.diarias_valor_unitario = None
        plano.diarias_valor_total = None
    if save:
        plano.save(update_fields=["diarias_composicao", "diarias_valor_unitario", "diarias_valor_total", "atualizado_em"])
    return resultado


def montar_valor_do_plano_texto(plano):
    """O bloco do placeholder {{valor_do_plano}}; no plano de vários eventos, o combinado."""
    if plano.is_multi_evento:
        composicao = plano.diarias_combinada_composicao
        unitario_val, total_val = plano.diarias_combinada_valor_unitario, plano.diarias_combinada_valor_total
    else:
        composicao = plano.diarias_composicao
        unitario_val, total_val = plano.diarias_valor_unitario, plano.diarias_valor_total
    if total_val is None or unitario_val is None:
        return ""
    total, unitario = Decimal(total_val), Decimal(unitario_val)
    return (
        f"Valor total: R${formatar_valor(total)} ({valor_por_extenso_ptbr(total)}). "
        f"Valor correspondente a {composicao}, por servidor, no valor unitário "
        f"de R${formatar_valor(unitario)} ({valor_por_extenso_ptbr(unitario)})."
    )


# ── Textos por evento (documento de vários eventos) ──────────────────────────


def _evento_data_header(evento):
    """'Dia 17 de junho de 2026' ou 'Dias 18 a 21 de junho de 2026'."""
    inicio = evento.data_evento_inicio
    fim = evento.data_evento_fim or inicio
    periodo = format_periodo_evento_extenso(inicio, fim)
    if not periodo:
        return ""
    dia_unico = (not fim) or (fim == inicio)
    return ("Dia " if dia_unico else "Dias ") + periodo


def _evento_data_curta(evento):
    """('17/06/2026', True) para dia único; ('18 a 21/06/2026', False) para período."""
    inicio = evento.data_evento_inicio
    fim = evento.data_evento_fim or inicio
    if not inicio:
        return "", True
    if not fim or fim == inicio:
        return inicio.strftime("%d/%m/%Y"), True
    if inicio.month == fim.month and inicio.year == fim.year:
        return f"{inicio.day:02d} a {fim.strftime('%d/%m/%Y')}", False
    return f"{inicio.strftime('%d/%m/%Y')} a {fim.strftime('%d/%m/%Y')}", False


def _valor_bloco_texto(rotulo, composicao, unitario_val, total_val):
    if total_val is None or unitario_val is None:
        return ""
    total, unitario = Decimal(total_val), Decimal(unitario_val)
    return (
        f"{rotulo}: R${formatar_valor(total)} ({valor_por_extenso_ptbr(total)}).\n"
        f"Valor correspondente a {composicao}, por servidor, no valor unitário "
        f"de R${formatar_valor(unitario)} ({valor_por_extenso_ptbr(unitario)})."
    )


def montar_valor_multi_texto(plano):
    blocos = []
    for evento in plano.eventos_ordenados:
        curta, dia_unico = _evento_data_curta(evento)
        bloco = _valor_bloco_texto(
            f"Valor do evento {'dia' if dia_unico else 'dias'}: {curta}",
            evento.diarias_composicao, evento.diarias_valor_unitario, evento.diarias_valor_total,
        )
        if bloco:
            blocos.append(bloco)
    total = _valor_bloco_texto(
        "Valor total", plano.diarias_combinada_composicao, plano.diarias_combinada_valor_unitario, plano.diarias_combinada_valor_total,
    )
    if total:
        blocos.append(total)
    return "\n\n".join(blocos)


# ── Diárias de vários eventos ────────────────────────────────────────────────


def _destino_principal_evento(evento):
    destino = evento.destino_principal
    if destino and destino.cidade_id:
        return destino.cidade.nome or "", destino.cidade.estado.sigla or ""
    if evento.plano_id and evento.plano.destino_cidade_id:
        return evento.plano.destino_cidade.nome or "", evento.plano.destino_cidade.estado.sigla or ""
    return None


def calcular_diarias_evento(plano, evento, total_efetivo=None):
    """Só este evento: sede → evento → sede."""
    erros = []
    if not (plano.saida_sede_data and plano.saida_sede_hora):
        erros.append("Informe data e hora de saída da sede.")
    if not (plano.chegada_sede_data and plano.chegada_sede_hora):
        erros.append("Informe data e hora de chegada na sede.")
    destino = _destino_principal_evento(evento)
    if destino is None:
        erros.append("Informe o destino do evento.")
    if total_efetivo is None:
        total_efetivo = evento.total_efetivo
    if total_efetivo <= 0:
        erros.append("Informe o efetivo do evento.")
    if erros:
        return {"ok": False, "erros": erros}

    saida = datetime.combine(plano.saida_sede_data, plano.saida_sede_hora)
    chegada = datetime.combine(plano.chegada_sede_data, plano.chegada_sede_hora)
    if chegada <= saida:
        return {"ok": False, "erros": ["A chegada na sede deve ser depois da saída."]}
    cidade, uf = destino
    try:
        return _resultado_diarias([Marcador(saida=saida, destino_cidade=cidade, destino_uf=uf)], chegada, total_efetivo)
    except (RoteiroIncalculavel, SemTabelaDeDiarias, ValueError) as exc:
        return _erro_de_calculo(exc)


def _parse_hora_inicio(horario):
    """A hora de início de um texto como '09:00 até 17:00' ou '18h às 02h'."""
    if not horario:
        return time(9, 0)
    match = re.search(r"(\d{1,2})\s*[:hH]?\s*(\d{0,2})", horario)
    if not match:
        return time(9, 0)
    h = int(match.group(1))
    m = int(match.group(2)) if match.group(2) else 0
    if 0 <= h < 24 and 0 <= m < 60:
        return time(h, m)
    return time(9, 0)


def calcular_diarias_combinadas(plano):
    """Sede → todos os eventos (na ordem das datas) → sede."""
    erros = []
    if not (plano.saida_sede_data and plano.saida_sede_hora):
        erros.append("Informe data e hora de saída da sede.")
    if not (plano.chegada_sede_data and plano.chegada_sede_hora):
        erros.append("Informe data e hora de chegada na sede.")
    eventos = list(plano.eventos.order_by("data_evento_inicio", "ordem", "pk")) if plano.pk else []
    if not eventos:
        erros.append("Adicione ao menos um evento ao plano.")

    marcadores = []
    for evento in eventos:
        destino = _destino_principal_evento(evento)
        if destino is None:
            erros.append(f"Informe o destino do evento {evento.ordem}.")
            continue
        if not evento.data_evento_inicio:
            erros.append(f"Informe a data de início do evento {evento.ordem}.")
            continue
        # A saída de cada trecho é o início do evento, na hora do atendimento.
        saida_evento = datetime.combine(evento.data_evento_inicio, _parse_hora_inicio(evento.horario_atendimento))
        cidade, uf = destino
        marcadores.append(Marcador(saida=saida_evento, destino_cidade=cidade, destino_uf=uf))
    if erros:
        return {"ok": False, "erros": erros}

    chegada = datetime.combine(plano.chegada_sede_data, plano.chegada_sede_hora)
    saida_sede = datetime.combine(plano.saida_sede_data, plano.saida_sede_hora)
    # O primeiro marcador parte da sede na hora da saída, quando ela vem antes.
    if marcadores and saida_sede < marcadores[0].saida:
        marcadores[0] = Marcador(saida=saida_sede, destino_cidade=marcadores[0].destino_cidade, destino_uf=marcadores[0].destino_uf)
    if chegada <= marcadores[0].saida:
        return {"ok": False, "erros": ["A chegada na sede deve ser depois da saída."]}
    total = plano.total_efetivo_combinado
    if total <= 0:
        return {"ok": False, "erros": ["Informe o efetivo dos eventos."]}
    try:
        return _resultado_diarias(marcadores, chegada, total)
    except (RoteiroIncalculavel, SemTabelaDeDiarias, ValueError) as exc:
        return _erro_de_calculo(exc)


def atualizar_snapshot_diarias_evento(evento, *, save=True):
    resultado = calcular_diarias_evento(evento.plano, evento)
    if resultado["ok"]:
        evento.diarias_composicao = resultado["composicao"]
        evento.diarias_valor_unitario = resultado["valor_unitario"]
        evento.diarias_valor_total = resultado["valor_total"]
    else:
        evento.diarias_composicao = ""
        evento.diarias_valor_unitario = None
        evento.diarias_valor_total = None
    if save:
        evento.save(update_fields=["diarias_composicao", "diarias_valor_unitario", "diarias_valor_total", "atualizado_em"])
    return resultado


def atualizar_snapshot_diarias_combinadas(plano, *, save=True):
    resultado = calcular_diarias_combinadas(plano)
    if resultado["ok"]:
        plano.diarias_combinada_composicao = resultado["composicao"]
        plano.diarias_combinada_valor_unitario = resultado["valor_unitario"]
        plano.diarias_combinada_valor_total = resultado["valor_total"]
    else:
        plano.diarias_combinada_composicao = ""
        plano.diarias_combinada_valor_unitario = None
        plano.diarias_combinada_valor_total = None
    if save:
        plano.save(update_fields=[
            "diarias_combinada_composicao", "diarias_combinada_valor_unitario", "diarias_combinada_valor_total", "atualizado_em",
        ])
    return resultado


# ── Atividades, metas e recursos ─────────────────────────────────────────────


CODIGO_UNIDADE_MOVEL = "UNIDADE_MOVEL"

TEXTO_UNIDADE_MOVEL = "Estrutura: Unidade móvel da PCPR equipada para atendimento e confecção de documentos."


def atividades_catalogo():
    return list(AtividadePlanoTrabalho.objects.order_by("nome"))


def presets_atividades():
    return list(PresetAtividadesPlanoTrabalho.objects.prefetch_related("atividades").order_by("nome"))


def preset_padrao():
    return PresetAtividadesPlanoTrabalho.objects.filter(is_padrao=True).prefetch_related("atividades").first()


def _atividades_selecionadas_ordenadas(plano):
    if not plano.pk:
        return []
    return list(plano.atividades_selecionadas.order_by("nome"))


def montar_atividades_texto(itens):
    return "\n".join(f"• {item.nome}" for item in itens)


def montar_metas_texto(itens):
    metas = []
    for item in itens:
        meta = (item.meta or "").strip()
        if meta and meta not in metas:
            metas.append(meta)
    return "\n".join(f"• {m}" for m in metas)


def montar_recursos_texto(itens):
    if not itens:
        return ""
    recursos = []
    for item in itens:
        recurso = (item.recurso_necessario or "").strip()
        if recurso and recurso not in recursos:
            recursos.append(recurso)
    linhas = [f"• {r}" for r in recursos]
    if any(item.codigo == CODIGO_UNIDADE_MOVEL for item in itens):
        linhas.append("• Prever unidade móvel institucional e o suporte operacional associado.")
    return "\n".join(linhas)


def montar_unidade_movel_texto(itens):
    if any(item.codigo == CODIGO_UNIDADE_MOVEL for item in itens):
        return TEXTO_UNIDADE_MOVEL
    return ""


def sincronizar_atividades(plano, *, save=True):
    """Regenera os textos da seção 3 a partir das atividades marcadas (depois do M2M)."""
    itens = _atividades_combinadas_multi(plano) if plano.is_multi_evento and plano.pk else _atividades_selecionadas_ordenadas(plano)
    plano.atividades = montar_atividades_texto(itens)
    plano.metas = montar_metas_texto(itens)
    plano.recursos_necessarios = montar_recursos_texto(itens)
    plano.unidade_movel_texto = montar_unidade_movel_texto(itens)
    campos = ["atividades", "metas", "recursos_necessarios", "unidade_movel_texto"]
    if save:
        plano.save(update_fields=[*campos, "atualizado_em"])
    return campos


def _atividades_evento_ordenadas(evento):
    if not evento.pk:
        return []
    return list(evento.atividades_selecionadas.order_by("nome"))


def _atividades_combinadas_multi(plano):
    """União (na ordem do catálogo) das atividades de todos os eventos."""
    if not plano.pk:
        return []
    codigos = {a.codigo for evento in plano.eventos.all() for a in evento.atividades_selecionadas.all()}
    if not codigos:
        return []
    return list(AtividadePlanoTrabalho.objects.filter(codigo__in=codigos).order_by("nome"))


def sincronizar_atividades_evento(evento, *, save=True):
    itens = _atividades_evento_ordenadas(evento)
    evento.atividades_texto = montar_atividades_texto(itens)
    evento.metas = montar_metas_texto(itens)
    evento.recursos_necessarios = montar_recursos_texto(itens)
    evento.unidade_movel_texto = montar_unidade_movel_texto(itens)
    campos = ["atividades_texto", "metas", "recursos_necessarios", "unidade_movel_texto"]
    if save:
        evento.save(update_fields=[*campos, "atualizado_em"])
    return campos


# ── Vários eventos: rascunho ↔ EventoPlano ───────────────────────────────────
#
# As seções 1 a 3 sempre editam os campos do próprio plano (o "rascunho do
# evento atual"). "Adicionar evento ao plano" copia o rascunho para um
# EventoPlano e o limpa para o próximo; editar um cartão recarrega aquele
# evento no rascunho. Destinos e efetivo são copiados, nunca movidos.

_SCRATCHPAD_CAMPOS = [
    ("programa_id", "programa_id"),
    ("programa_outros", "programa_outros"),
    ("data_evento_inicio", "data_evento_inicio"),
    ("data_evento_fim", "data_evento_fim"),
    ("horario_atendimento", "horario_atendimento"),
    ("coordenador_op_modo", "coordenador_op_modo"),
    ("coordenador_op_id", "coordenador_op_id"),
    ("coordenador_op_nome_manual", "coordenador_op_nome_manual"),
    ("coordenador_op_cargo_manual", "coordenador_op_cargo_manual"),
    ("coordenador_op_genero", "coordenador_op_genero"),
    ("metas", "metas"),
    ("atividades", "atividades_texto"),
    ("recursos_necessarios", "recursos_necessarios"),
    ("unidade_movel_texto", "unidade_movel_texto"),
    ("diarias_composicao", "diarias_composicao"),
    ("diarias_valor_unitario", "diarias_valor_unitario"),
    ("diarias_valor_total", "diarias_valor_total"),
]


def scratchpad_tem_conteudo(plano):
    if not plano.pk:
        return False
    return bool(
        plano.programa_id
        or (plano.programa_outros or "").strip()
        or plano.destino_cidade_id
        or plano.data_evento_inicio
        or plano.atividades_selecionadas.exists()
        or plano.efetivos.exists()
        or plano.destinos.filter(evento__isnull=True).exists()
    )


def commit_scratchpad_para_evento(plano):
    """Cria ou atualiza o EventoPlano que o rascunho representa; None se não há nada."""
    evento = plano.evento_em_edicao
    if evento is None:
        if not scratchpad_tem_conteudo(plano):
            return None
        ordem = (plano.eventos.aggregate(maxo=Max("ordem"))["maxo"] or 0) + 1
        evento = EventoPlano(plano=plano, ordem=ordem)
    for origem, destino in _SCRATCHPAD_CAMPOS:
        setattr(evento, destino, getattr(plano, origem))
    evento.save()

    evento.atividades_selecionadas.set(plano.atividades_selecionadas.all())

    evento.efetivos.all().delete()
    for ef in plano.efetivos.all():
        EfetivoEvento.objects.create(evento=evento, unidade_id=ef.unidade_id, cargo_id=ef.cargo_id, quantidade=ef.quantidade)

    PlanoDestino.objects.filter(evento=evento).delete()
    rascunho = list(plano.destinos.filter(evento__isnull=True).order_by("ordem", "pk"))
    for d in rascunho:
        PlanoDestino.objects.create(plano=plano, evento=evento, estado_id=d.estado_id, cidade_id=d.cidade_id, ordem=d.ordem)
    if not rascunho and plano.destino_cidade_id:
        estado_id = plano.destino_estado_id or plano.destino_cidade.estado_id
        PlanoDestino.objects.create(plano=plano, evento=evento, estado_id=estado_id, cidade_id=plano.destino_cidade_id, ordem=1)
    return evento


def limpar_scratchpad(plano):
    """Zera os campos de evento do rascunho (coordenador adm, contextualização e sede ficam)."""
    plano.programa = None
    plano.programa_outros = ""
    plano.destino_estado = None
    plano.destino_cidade = None
    plano.data_evento_inicio = None
    plano.data_evento_fim = None
    plano.horario_atendimento = HORARIO_ATENDIMENTO_PADRAO
    plano.coordenador_op_modo = PlanoTrabalho.COORDENADOR_MODO_SERVIDOR
    plano.coordenador_op = None
    plano.coordenador_op_nome_manual = ""
    plano.coordenador_op_cargo_manual = ""
    plano.coordenador_op_genero = PlanoTrabalho.COORDENADOR_GENERO_MASCULINO
    plano.metas = ""
    plano.atividades = ""
    plano.recursos_necessarios = ""
    plano.unidade_movel_texto = ""
    plano.diarias_composicao = ""
    plano.diarias_valor_unitario = None
    plano.diarias_valor_total = None
    plano.save()
    plano.atividades_selecionadas.clear()
    plano.efetivos.all().delete()
    plano.destinos.filter(evento__isnull=True).delete()


def carregar_evento_no_scratchpad(plano, evento):
    """Copia um evento gravado de volta para o rascunho e o marca em edição."""
    for origem, destino in _SCRATCHPAD_CAMPOS:
        setattr(plano, origem, getattr(evento, destino))
    primeiro = evento.destinos.order_by("ordem", "pk").first() if evento.pk else None
    if primeiro:
        plano.destino_estado_id = primeiro.estado_id
        plano.destino_cidade_id = primeiro.cidade_id
    else:
        plano.destino_estado = None
        plano.destino_cidade = None
    plano.evento_em_edicao = evento
    plano.save()

    plano.atividades_selecionadas.set(evento.atividades_selecionadas.all())
    plano.efetivos.all().delete()
    for ef in evento.efetivos.all():
        EfetivoPlano.objects.create(plano=plano, unidade_id=ef.unidade_id, cargo_id=ef.cargo_id, quantidade=ef.quantidade)
    plano.destinos.filter(evento__isnull=True).delete()
    for d in evento.destinos.order_by("ordem", "pk"):
        PlanoDestino.objects.create(plano=plano, evento=None, estado_id=d.estado_id, cidade_id=d.cidade_id, ordem=d.ordem)


@transaction.atomic
def adicionar_evento_ao_plano(plano):
    """Grava o rascunho como evento, limpa o rascunho e devolve o evento (ou None)."""
    evento = commit_scratchpad_para_evento(plano)
    if evento is None:
        return None
    plano.is_multi_evento = True
    plano.evento_em_edicao = None
    limpar_scratchpad(plano)
    atualizar_snapshot_diarias_combinadas(plano)
    return evento


@transaction.atomic
def editar_evento_no_scratchpad(plano, evento):
    """Guarda o rascunho em andamento e carrega o evento escolhido para edição."""
    commit_scratchpad_para_evento(plano)
    plano.evento_em_edicao = None
    limpar_scratchpad(plano)
    carregar_evento_no_scratchpad(plano, evento)
    atualizar_snapshot_diarias_combinadas(plano)


@transaction.atomic
def remover_evento(plano, evento):
    era_em_edicao = plano.evento_em_edicao_id == evento.pk
    evento.delete()
    if era_em_edicao:
        plano.evento_em_edicao = None
        limpar_scratchpad(plano)
    if plano.eventos.count() == 0:
        plano.is_multi_evento = False
        plano.evento_em_edicao = None
        plano.save(update_fields=["is_multi_evento", "evento_em_edicao", "atualizado_em"])
    else:
        atualizar_snapshot_diarias_combinadas(plano)


def sincronizar_scratchpad(plano):
    """Reflete o rascunho atual como EventoPlano sem limpá-lo (resumo e finalização)."""
    if not plano.is_multi_evento:
        return None
    evento = commit_scratchpad_para_evento(plano)
    if evento is not None and plano.evento_em_edicao_id != evento.pk:
        plano.evento_em_edicao = evento
        plano.save(update_fields=["evento_em_edicao", "atualizado_em"])
    atualizar_snapshot_diarias_combinadas(plano)
    return evento


def eventos_para_cards(plano):
    """Os eventos gravados que viram cartão (fora o que está no rascunho)."""
    if not plano.pk or not plano.is_multi_evento:
        return []
    qs = plano.eventos.order_by("ordem", "data_evento_inicio", "pk")
    if plano.evento_em_edicao_id:
        qs = qs.exclude(pk=plano.evento_em_edicao_id)
    return list(qs)


# ── Pendências ───────────────────────────────────────────────────────────────


def avaliar_pendencias_documento(plano):
    pendencias = []
    nome_adm, _ = plano.coordenador_nome_cargo("adm")
    if not nome_adm:
        pendencias.append("Informe o coordenador administrativo na identificação.")
    if plano.is_multi_evento:
        eventos = list(plano.eventos.all()) if plano.pk else []
        if not eventos:
            pendencias.append("Adicione ao menos um evento ao plano.")
        for evento in eventos:
            if _destino_principal_evento(evento) is None:
                pendencias.append(f"Informe o destino do evento {evento.ordem}.")
            if not evento.data_evento_inicio:
                pendencias.append(f"Informe a data do evento {evento.ordem}.")
            if evento.total_efetivo <= 0:
                pendencias.append(f"Informe o efetivo do evento {evento.ordem}.")
        if plano.diarias_combinada_valor_total is None:
            pendencias.append("Calcule as diárias combinadas em efetivo e diárias.")
    else:
        if not plano.destino_cidade_id:
            pendencias.append("Informe o destino (cidade/UF) na identificação.")
        if not plano.data_evento_inicio:
            pendencias.append("Informe a data do evento na identificação.")
        if plano.total_efetivo <= 0:
            pendencias.append("Informe o efetivo (cargo e quantidade) em efetivo e diárias.")
        if plano.diarias_valor_total is None:
            pendencias.append("Calcule as diárias em efetivo e diárias.")
    return pendencias


# ── Documento ────────────────────────────────────────────────────────────────


def referencia_do_plano(plano):
    return f"{plano.numero:02d}-{plano.ano}" if plano.numero and plano.ano else f"plano-{plano.pk}"


def gerar_plano_documento(plano, formato, *, usar_assinado=True):
    """O DOCX ou o PDF do plano pela fachada documental (que também o persiste)."""
    from viagens_cadastros.selectors import build_configuracao_context

    from .docxtpl_context import build_plano_docxtpl_context

    contexto = build_plano_docxtpl_context(plano)
    from documentos.services.document_blocks import conteudo_documental

    # Os títulos reescritos no editor entram no PDF e na chave do cache.
    payload = {"institucional": build_configuracao_context(), "plano": contexto,
               "documento": conteudo_documental(DocumentoTipo.PLANO_TRABALHO, plano)}
    # O plano de vários eventos tem modelo próprio, com os laços por evento.
    docx_template = "plano_trabalho_multievento.docx" if plano.is_multi_evento else None
    return DocumentoFacade().gerar(
        tipo=DocumentoTipo.PLANO_TRABALHO, formato=formato, payload=payload,
        reference=referencia_do_plano(plano), docxtpl_context=contexto, docx_template_path=docx_template,
        plano_trabalho_id=plano.pk, usar_assinado=usar_assinado,
    )


def marcar_plano_gerado(plano):
    if plano.status != PlanoTrabalho.STATUS_GERADO:
        plano.status = PlanoTrabalho.STATUS_GERADO
        plano.save(update_fields=["status", "atualizado_em"])


# ── Numeração e criação ──────────────────────────────────────────────────────


@transaction.atomic
def salvar_plano_numerado(plano):
    """Reserva e grava o número com a mecânica comum e a política do número de ofício."""
    if plano.numero and plano.ano:
        plano.save()
        return plano

    ano = timezone.localdate().year
    original_pk = plano.pk
    original_adding = plano._state.adding
    escolha = {}

    def escolher():
        numero, ano_escolhido, sufixo = type(plano).proximo_numero()
        escolha["ano"], escolha["sufixo"] = ano_escolhido, sufixo
        return numero

    def gravar(numero):
        plano.numero = numero
        plano.ano = escolha["ano"]
        plano.sufixo_numero = escolha["sufixo"]
        plano.save()

    def limpar():
        plano.numero = None
        plano.ano = None
        plano.sufixo_numero = ""
        if original_adding:
            plano.pk = original_pk
            plano._state.adding = True

    def numero_ocupado(numero):
        return PlanoTrabalho.objects.filter(ano=ano, numero=numero).exclude(pk=plano.pk).exists()

    reservar_numero(
        namespace=NAMESPACE_PLANO_TRABALHO, ano=ano, modelo=PlanoTrabalho, constraint=CONSTRAINT_NUMERO_PLANO_TRABALHO,
        escolher=escolher, gravar=gravar, ja_ocupado=numero_ocupado, apos_colisao=limpar,
    )
    return plano


# Um rascunho aberto e abandonado não pode prender um número: o próximo
# "Novo plano" o reaproveita. A folga evita entregar a outra pessoa o rascunho
# que alguém acabou de abrir e ainda vai preencher.
FOLGA_RASCUNHO_VAZIO = timedelta(minutes=30)


def rascunho_vazio_disponivel():
    """O rascunho numerado que ninguém preencheu e ninguém está preenchendo."""
    limite = timezone.now() - FOLGA_RASCUNHO_VAZIO
    return (
        PlanoTrabalho.objects.filter(
            status=PlanoTrabalho.STATUS_RASCUNHO, cancelado=False, numero__isnull=False,
            legado_pk__isnull=True, viagem__isnull=True, programa__isnull=True,
            destino_cidade__isnull=True, data_evento_inicio__isnull=True,
            programa_outros="", coordenador_adm__isnull=True, coordenador_adm_nome_manual="",
            saida_sede_data__isnull=True, atualizado_em__lt=limite,
        )
        .exclude(efetivos__isnull=False)
        .exclude(atividades_selecionadas__isnull=False)
        .exclude(eventos__isnull=False)
        .exclude(artefatos__isnull=False)
        .order_by("ano", "numero")
        .first()
    )


@transaction.atomic
def criar_plano_rascunho(viagem=None):
    """O rascunho numerado que "Novo plano" abre, semeado pela viagem quando há uma."""
    from viagens_viagem.services import semente_de_documentos

    semente = semente_de_documentos(viagem) or {}
    vazio = rascunho_vazio_disponivel()
    plano = vazio if vazio is not None else PlanoTrabalho()
    plano.data_criacao = timezone.localdate()
    plano.viagem = viagem
    config = ConfiguracaoSistema.get_singleton()
    if config.coordenador_adm_plano_trabalho_id:
        plano.coordenador_adm = config.coordenador_adm_plano_trabalho
    elif getattr(viagem, "responsavel_id", None):
        plano.coordenador_adm = viagem.responsavel
    if getattr(viagem, "responsavel_id", None):
        plano.coordenador_op = viagem.responsavel
    cidade, estado = semente.get("cidade"), semente.get("estado")
    if cidade is not None:
        plano.destino_cidade = cidade
        plano.destino_estado = cidade.estado
    elif estado is not None:
        plano.destino_estado = estado
    plano.data_evento_inicio = semente.get("data_inicio")
    plano.data_evento_fim = semente.get("data_fim") or semente.get("data_inicio")
    if viagem is not None:
        plano.programa_outros = viagem.titulo or ""
        if viagem.horario_inicio and viagem.horario_fim:
            plano.horario_atendimento = f"{viagem.horario_inicio:%H:%M} até {viagem.horario_fim:%H:%M}"
    # A contextualização NÃO herda o motivo da viagem: é texto curto de agenda,
    # não o parágrafo de abertura. Fica automática até alguém editar à mão.
    plano = salvar_plano_numerado(plano)
    _semear_destinos_da_viagem(plano, semente)
    return plano


def _semear_destinos_da_viagem(plano, semente):
    """Todos os destinos da viagem viram linhas do rascunho, quando são dois ou mais.

    Um destino só já está nos campos `destino_*`; não vale criar linha para
    repetir o que o formulário monta sozinho.
    """
    from viagens_viagem.services import destinos_para_formulario

    destinos = destinos_para_formulario(semente) if semente else []
    if len(destinos) < 2:
        return
    PlanoDestino.objects.filter(plano=plano, evento__isnull=True).delete()
    PlanoDestino.objects.bulk_create([
        PlanoDestino(plano=plano, estado_id=estado_id, cidade_id=cidade_id, ordem=ordem)
        for ordem, (estado_id, cidade_id) in enumerate(destinos, 1)
    ])
