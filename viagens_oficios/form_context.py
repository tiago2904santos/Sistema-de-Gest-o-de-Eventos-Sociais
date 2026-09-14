"""Contexto do formulário do ofício, bloco a bloco.

O wizard da origem tem seis etapas (dados e viajantes, transporte, roteiro,
justificativa, resumo, documentos), cada uma com blocos próprios. Aqui elas
viram seções de um formulário longo com a lateral de etapas do V3.2 — mesmos
campos, mesmos rótulos, mesma ordem e mesmas regras de habilitação; o que muda
é a pele. Nada aqui é renderizado por laço genérico sobre a lista de campos.
"""

from django.urls import reverse
from django.utils.formats import number_format

from viagens_cadastros.models import Combustivel, Servidor, Unidade, Viatura
from viagens_roteiros.presenters import periodo_display, titulo_da_rota, trechos_display

from .models import Oficio
from .picker import pks_ja_escolhidos
from .presenters import iniciais


def _valor(form, nome):
    valor = form[nome].value()
    if valor is None:
        return ""
    return str(getattr(valor, "pk", valor))


def _erros(form, nome):
    return form.errors.get(nome)


def _opcoes_servidores(form):
    """Servidores ativos com cargo e unidade, como a origem lista a equipe."""
    queryset = form.fields["servidores"].queryset.select_related("cargo", "unidade")
    opcoes = []
    for servidor in queryset:
        detalhes = []
        if servidor.cargo_id:
            detalhes.append(str(servidor.cargo))
        if servidor.unidade_id:
            detalhes.append(servidor.unidade.sigla or servidor.unidade.nome)
        opcoes.append({
            "valor": str(servidor.pk),
            "rotulo": servidor.nome,
            "iniciais": iniciais(servidor.nome),
            "detalhes": " · ".join(detalhes),
        })
    return opcoes


def _opcoes_viaturas(form):
    return [
        {"valor": str(v.pk), "rotulo": f"{v.placa_formatada} — {v.modelo}" if v.modelo else v.placa_formatada}
        for v in form.fields["viatura"].queryset
    ]


def _opcoes_roteiros(form):
    """Cada roteiro leva o próprio resumo: o bloco "Resumo da rota" lê daqui."""
    opcoes, resumos = [], {}
    for roteiro in form.fields["roteiro"].queryset.select_related("origem_municipio__estado").prefetch_related("trechos__destino_municipio__estado", "destinos__municipio__estado"):
        titulo = titulo_da_rota(roteiro)
        periodo = periodo_display(roteiro)
        opcoes.append({"valor": str(roteiro.pk), "rotulo": f"{titulo} · {periodo}" if periodo != "—" else titulo})
        resumos[str(roteiro.pk)] = {
            "sede": str(roteiro.origem_municipio) if roteiro.origem_municipio_id else "—",
            "rota": titulo,
            "destinos": [str(d.municipio) for d in roteiro.destinos.all() if d.municipio_id],
            "periodo": periodo,
            "trechos": trechos_display(roteiro),
            "servidores": roteiro.quantidade_servidores,
            "valor": f"R$ {number_format(roteiro.valor_diarias, decimal_pos=2, force_grouping=True)}" if roteiro.valor_diarias is not None else "—",
            "resumo_diarias": roteiro.resumo_diarias or "—",
            "extenso": roteiro.valor_diarias_extenso or "",
            "url_editar": reverse("viagens_roteiros:editar", args=[roteiro.pk]),
        }
    return opcoes, resumos


def _choices(campo, form):
    return [{"valor": str(chave), "rotulo": str(rotulo)} for chave, rotulo in form.fields[campo].choices if chave != ""]


def etapas_do_oficio(oficio, avaliacao, regra):
    """As seis etapas do wizard da origem, com o estado de cada uma."""
    checks = (avaliacao or {}).get("checks", {})

    def estado(chave):
        return {"complete": "concluida", "incomplete": "pendente"}.get(checks.get(chave, "not_started"), "pendente")

    transporte = "concluida" if checks.get("transporte") == "complete" and checks.get("motorista_documento") == "complete" else "pendente"
    # A etapa da justificativa segue a régua da origem: sem data de saída não
    # há como avaliar (pendente); prazo folgado dispensa (opcional); no prazo
    # curto, só fecha com o texto.
    if regra is None or regra.get("status") == "unknown":
        justificativa = "pendente"
    elif regra.get("status") == "not_applicable":
        justificativa = "opcional"
    else:
        justificativa = estado("justificativa")
    documentos = "concluida" if oficio.pk and oficio.artefatos.exists() else "pendente"
    return [
        {"id": "dados", "numero": 1, "titulo": "Dados e viajantes", "estado": estado("dados_viajantes") if oficio.pk else "pendente"},
        {"id": "transporte", "numero": 2, "titulo": "Transporte", "estado": transporte if oficio.pk else "pendente"},
        {"id": "roteiro", "numero": 3, "titulo": "Roteiro", "estado": estado("roteiro") if oficio.pk else "pendente"},
        {"id": "justificativa", "numero": 4, "titulo": "Justificativa", "estado": justificativa if oficio.pk else "pendente"},
        {"id": "resumo", "numero": 5, "titulo": "Resumo", "estado": "concluida" if (avaliacao or {}).get("status") == "complete" else "pendente"},
        {"id": "documentos", "numero": 6, "titulo": "Documentos", "estado": documentos},
    ]


def contexto_form_oficio(form, jform, oficio, *, avaliacao=None, regra=None):
    opcoes_roteiros, resumos_roteiros = _opcoes_roteiros(form)
    viajantes = pks_ja_escolhidos(form, "servidores")
    com_termo = set(pks_ja_escolhidos(form, "servidores_termo_autorizacao"))
    servidores = _opcoes_servidores(form)
    for opcao in servidores:
        opcao["selecionado"] = opcao["valor"] in viajantes
        opcao["termo"] = opcao["valor"] in com_termo
    modo_viatura = "manual" if (not _valor(form, "viatura") and (_valor(form, "transporte_placa_manual") or _valor(form, "transporte_modelo_manual"))) else "cadastrada"
    return {
        "valores": {nome: _valor(form, nome) for nome in form.fields},
        "erros": {nome: _erros(form, nome) for nome in form.fields},
        "justificativa": {
            "modelo": _valor(jform, "modelo"), "texto": _valor(jform, "texto"),
            "erros_modelo": _erros(jform, "modelo"), "erros_texto": _erros(jform, "texto"),
            "opcoes_modelo": [{"valor": str(m.pk), "rotulo": m.nome} for m in jform.fields["modelo"].queryset],
        },
        "opcoes_unidades": [{"valor": str(u.pk), "rotulo": u.sigla or u.nome, "detalhes": u.nome} for u in form.fields["solicitante"].queryset],
        "opcoes_motivos": [{"valor": str(m.pk), "rotulo": m.nome} for m in form.fields["modelo_motivo"].queryset],
        "opcoes_custeio": _choices("custeio", form),
        "opcoes_servidores": servidores,
        "opcoes_viaturas": _opcoes_viaturas(form),
        "opcoes_combustiveis": [{"valor": str(c.pk), "rotulo": c.nome} for c in form.fields["transporte_combustivel_manual"].queryset],
        "opcoes_tipos_viatura": _choices("transporte_tipo_manual", form),
        "opcoes_motorista_modo": _choices("motorista_modo", form),
        "opcoes_roteiros": opcoes_roteiros,
        "resumos_roteiros": resumos_roteiros,
        "modo_viatura": modo_viatura,
        "motorista_modo": _valor(form, "motorista_modo") or Oficio.MOTORISTA_MODO_SERVIDOR,
        "porte_armas": bool(form["porte_transporte_armas"].value()),
        "etapas": etapas_do_oficio(oficio, avaliacao, regra),
        "avaliacao": avaliacao,
        "regra": regra,
    }
