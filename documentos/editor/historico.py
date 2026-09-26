"""O histórico do documento em linguagem do documento (m116).

A trilha de auditoria guarda, por registro, o nome técnico de cada campo e
o antes e o depois. Aqui ela vira o que o painel "Histórico" do editor
mostra: o rótulo que o documento usa (o do `CampoEditavel` ou do
`BlocoDocumental`, senão o `verbose_name` do campo), "de X para Y" resumido,
e o que é preciso para "Voltar a este valor" — a espécie, a chave, a parte e
o valor de antes, que o `documento-editor.js` regrava pelo mesmo PATCH da
edição (mesma validação, mesma trilha).

Como o editor grava a cada pausa da digitação, um parágrafo vira vários
registros seguidos: os do mesmo usuário, mesmo registro e mesmos campos,
dentro de uma janela curta, formam uma entrada só, do primeiro "antes" ao
último "depois".
"""

from __future__ import annotations

import json
from datetime import date, datetime, timedelta

from django.apps import apps

from .blocos import blocos_do_tipo, quebras_do_tipo
from .campos import campos_do_tipo

JANELA_AGRUPAMENTO = timedelta(minutes=2)
TAMANHO_RESUMO = 90
LIMITE_ENTRADAS = 25

# Campos do bloco documental que não são conteúdo: acompanham o override e
# não dizem nada a quem lê.
_ACESSORIOS_DO_BLOCO = {"editado_por", "editado_em", "editado_manualmente", "atualizado_em", "ordem", "criado_em"}
_FORA = {"atualizado_em", "criado_em", "novo", "antigo"}


def _partes_do_vinculo(vinculo) -> dict:
    """Nome do campo do model → (campo do editor, parte). Um nome que aparece
    em mais de um campo (o modo do motorista, no transporte e no motorista)
    fica com o primeiro."""
    partes = {}
    for campo in campos_do_tipo(vinculo.chave).values():
        for parte in campo.partes:
            partes.setdefault(parte.nome, (campo, parte))
    return partes


def _modelo(rotulo):
    try:
        return apps.get_model(rotulo)
    except (LookupError, ValueError):
        return None


def _formatar_data(texto):
    for formato in ("%Y-%m-%d", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M:%S.%f"):
        try:
            momento = datetime.strptime(str(texto)[:26], formato)
        except ValueError:
            continue
        return momento.strftime("%d/%m/%Y") if formato == "%Y-%m-%d" else momento.strftime("%d/%m/%Y %H:%M")
    return str(texto)


def _legivel(modelo, nome, valor) -> str:
    """O valor como o documento o mostraria: o registro ligado pelo nome, a
    escolha pelo rótulo, sim/não, datas no formato do país."""
    if valor in (None, "", []):
        return "—"
    if isinstance(valor, bool):
        return "Sim" if valor else "Não"
    if isinstance(valor, list):
        return ", ".join(str(v) for v in valor)
    campo = None
    if modelo is not None:
        try:
            campo = modelo._meta.get_field(nome)
        except Exception:  # noqa: BLE001 — campo que já não existe no model
            campo = None
    if campo is not None:
        if getattr(campo, "remote_field", None) is not None and getattr(campo, "related_model", None) is not None:
            ligado = campo.related_model._base_manager.filter(pk=valor).first()
            if ligado is not None:
                return str(ligado)
        if getattr(campo, "flatchoices", None):
            rotulos = {str(chave): str(rotulo) for chave, rotulo in campo.flatchoices}
            if str(valor) in rotulos:
                return rotulos[str(valor)]
        interno = campo.get_internal_type()
        if interno in ("DateField", "DateTimeField") or isinstance(valor, (date, datetime)):
            return _formatar_data(valor)
        if interno == "BooleanField":
            return "Sim" if str(valor).lower() in ("true", "1") else "Não"
    return str(valor)


def _resumo(texto: str) -> str:
    texto = " ".join(str(texto).split())
    return texto if len(texto) <= TAMANHO_RESUMO else texto[: TAMANHO_RESUMO - 1].rstrip() + "…"


def _verbose(modelo, nome) -> str:
    if modelo is not None:
        try:
            return str(modelo._meta.get_field(nome).verbose_name).capitalize()
        except Exception:  # noqa: BLE001
            pass
    return nome.replace("_", " ").capitalize()


def _blocos_do_historico(registros):
    """Chave e tipo de cada bloco documental citado, pelo id (o delta de uma
    atualização não traz a chave)."""
    from documentos.models import DocumentoBloco

    ids = {r.objeto_id for r in registros if r.modelo == "documentos.documentobloco"}
    blocos = {}
    if ids:
        for pk, chave, tipo in DocumentoBloco.objects.filter(pk__in=[int(i) for i in ids if str(i).isdigit()]).values_list("pk", "chave", "tipo"):
            blocos[str(pk)] = (chave, tipo)
    for r in registros:
        if r.modelo == "documentos.documentobloco" and r.objeto_id not in blocos:
            # Bloco apagado (quebra removida): a chave está no snapshot.
            dados = r.alteracoes.get("antigo") or r.alteracoes.get("novo") or {}
            if dados.get("chave"):
                blocos[r.objeto_id] = (dados.get("chave"), dados.get("tipo") or "")
    return blocos


def _mudancas_do_bloco(vinculo, registro, blocos_por_id) -> list[dict]:
    chave, tipo = blocos_por_id.get(registro.objeto_id, ("", ""))
    if tipo == "quebra_pagina" or (not tipo and chave in quebras_do_tipo(vinculo.tipo)):
        ponto = quebras_do_tipo(vinculo.tipo).get(chave)
        rotulo = f"Quebra de página · {ponto.rotulo.lower()}" if ponto else "Quebra de página"
        # Criar a quebra é ligá-la; apagar o registro é desligá-la.
        ativa = registro.acao != "EXCLUSAO"
        return [{
            "rotulo": rotulo, "antes": "Não" if ativa else "Sim", "depois": "Sim" if ativa else "Não",
            "voltar": {"especie": "quebra", "chave": chave, "valores": {"ativa": not ativa}} if chave else None,
        }]
    definicao = blocos_do_tipo(vinculo.tipo).get(chave)
    rotulo = definicao.rotulo if definicao else (chave or "Parágrafo do modelo")
    delta = registro.alteracoes
    if registro.acao == "CRIACAO":
        novo = delta.get("novo") or {}
        if not novo.get("editado_manualmente"):
            return []
        antes, depois = novo.get("conteudo_original", ""), novo.get("conteudo_atual", "")
    elif "conteudo_atual" in delta:
        antes, depois = delta["conteudo_atual"].get("antes", ""), delta["conteudo_atual"].get("depois", "")
    else:
        return []
    return [{
        "rotulo": rotulo, "antes": _resumo(antes), "depois": _resumo(depois),
        "voltar": {"especie": "bloco", "chave": chave, "valores": {"conteudo": antes}} if chave else None,
    }]


def _mudancas_do_campo(vinculo, registro, partes) -> list[dict]:
    modelo = _modelo(registro.modelo)
    delta = registro.alteracoes
    if registro.acao == "CRIACAO":
        return [{"rotulo": "Registro criado", "antes": "", "depois": "", "voltar": None}]
    if registro.acao == "EXCLUSAO":
        return [{"rotulo": "Registro excluído", "antes": "", "depois": "", "voltar": None}]
    mudancas = []
    for nome in sorted(delta):
        if nome in _FORA:
            continue
        valor = delta[nome]
        campo_parte = partes.get(nome)
        rotulo = campo_parte[0].rotulo if campo_parte else _verbose(modelo, nome)
        if campo_parte and len(campo_parte[0].partes) > 1 and campo_parte[1].rotulo != campo_parte[0].rotulo:
            rotulo = f"{campo_parte[0].rotulo} · {campo_parte[1].rotulo.lower()}"
        if not isinstance(valor, dict):
            mudancas.append({"rotulo": rotulo, "antes": "", "depois": _resumo(_legivel(modelo, nome, valor)), "voltar": None})
            continue
        if "operacao" in valor:
            # Relação de muitos (os viajantes): a operação e quantos.
            ids = valor.get("ids") or []
            mudancas.append({"rotulo": rotulo, "antes": "", "depois": f"{valor['operacao']}: {len(ids)} registro{'s' if len(ids) != 1 else ''}", "voltar": None})
            continue
        antes, depois = valor.get("antes"), valor.get("depois")
        voltar = None
        if campo_parte and campo_parte[1].tipo != "escolha_multipla":
            campo, parte = campo_parte
            voltar = {
                "especie": "campo", "chave": campo.chave, "origem": campo.origem,
                "valores": {parte.nome: "" if antes is None else antes},
            }
        mudancas.append({
            "rotulo": rotulo, "antes": _resumo(_legivel(modelo, nome, antes)), "depois": _resumo(_legivel(modelo, nome, depois)),
            "voltar": voltar,
        })
    return mudancas


def _mesma_digitacao(entrada, registro, chaves) -> bool:
    if entrada["usuario_id"] != registro.usuario_id or entrada["modelo"] != registro.modelo or entrada["objeto_id"] != registro.objeto_id:
        return False
    if entrada["acao_codigo"] != registro.acao or entrada["chaves"] != chaves:
        return False
    return entrada["ultimo_em"] - registro.criado_em <= JANELA_AGRUPAMENTO


def historico_legivel(vinculo, registros, *, pode_editar=False) -> list[dict]:
    """As entradas do painel a partir dos registros da trilha (do mais novo
    para o mais antigo). Sem permissão de edição, não há "Voltar"."""
    partes = _partes_do_vinculo(vinculo)
    blocos_por_id = _blocos_do_historico(registros)
    entradas: list[dict] = []
    for registro in registros:
        if registro.modelo == "documentos.documentobloco":
            mudancas = _mudancas_do_bloco(vinculo, registro, blocos_por_id)
            chaves = tuple(sorted(k for k in registro.alteracoes if k not in _FORA and k not in _ACESSORIOS_DO_BLOCO))
        else:
            mudancas = _mudancas_do_campo(vinculo, registro, partes)
            chaves = tuple(sorted(k for k in registro.alteracoes if k not in _FORA))
        if not mudancas:
            continue
        if not pode_editar:
            for m in mudancas:
                m["voltar"] = None
        # Registros vêm do mais novo para o mais antigo: a entrada aberta é a
        # mais nova do grupo; um registro mais antigo da mesma digitação só
        # empurra o "antes" (e o valor a que se volta) para trás.
        anterior = entradas[-1] if entradas else None
        if anterior is not None and _mesma_digitacao(anterior, registro, chaves):
            for atual, velho in zip(anterior["mudancas"], mudancas):
                atual["antes"] = velho["antes"]
                if atual["voltar"] and velho["voltar"]:
                    atual["voltar"]["valores"] = velho["voltar"]["valores"]
                    atual["voltar_json"] = json.dumps(atual["voltar"], ensure_ascii=False)
            anterior["ultimo_em"] = registro.criado_em
            anterior["agrupados"] += 1
            continue
        for m in mudancas:
            if m["voltar"] is not None and m["antes"] == m["depois"]:
                m["voltar"] = None
            m["voltar_json"] = json.dumps(m["voltar"], ensure_ascii=False) if m["voltar"] else ""
        entradas.append({
            "quando": registro.criado_em,
            "ultimo_em": registro.criado_em,
            "usuario": registro.usuario,
            "usuario_id": registro.usuario_id,
            "origem": registro.get_origem_display(),
            "acao": registro.get_acao_display(),
            "acao_codigo": registro.acao,
            "modelo": registro.modelo,
            "objeto_id": registro.objeto_id,
            "sobre_bloco": registro.modelo == "documentos.documentobloco",
            "chaves": chaves,
            "mudancas": mudancas,
            "agrupados": 1,
        })
        if len(entradas) >= LIMITE_ENTRADAS:
            break
    return entradas
