"""
Payloads canônicos para o núcleo documental (templates DOCX/PDF).

Os modelos DOCX ``termo_autorizacao.docx`` e ``ordem_servico.docx``
usam placeholders **aninhados** (ex.: ``{{ oficio.numero_formatado }}``, ``{{ termo.participante.nome }}``).
Para esses tipos, a ``DocumentoFacade`` recebe o payload canónico diretamente (sem ``docxtpl_context`` plano).
O ofício e a justificativa legados usam chaves planas e ``oficios.docxtpl_context``.
"""

from __future__ import annotations

import re
from typing import Any

from viagens_cadastros.models import Servidor
from viagens_cadastros.selectors import build_configuracao_context
from core.utils.masks import format_placa
from core.utils.masks import format_protocolo

from viagens_oficios.models import Justificativa
from viagens_oficios.justificativas_services import oficio_exige_justificativa

from documentos.services.timing import measure_step
from documentos.services.types import DocumentoTipo

from .models import Oficio
from .roteiro_context import periodo_roteiro


_DEMO_PREFIX_RE = re.compile(r"^\s*\[\s*demo[^\]]*\]\s*", re.IGNORECASE)


def _document_text(value: object, default: str = "—") -> str:
    text = _DEMO_PREFIX_RE.sub("", str(value or "")).strip()
    return text or default


def _blank(value: object, default: str = "—") -> str:
    text = str(value or "").strip()
    return text or default


def _format_date(value) -> str:
    if not value:
        return "—"
    return value.strftime("%d/%m/%Y")


def _format_datetime(value) -> str:
    if not value:
        return "—"
    from django.utils import timezone

    if timezone.is_naive(value):
        value = timezone.make_aware(value, timezone.get_current_timezone())
    return value.astimezone(timezone.get_current_timezone()).strftime("%d/%m/%Y %H:%M")


_MESES = {
    1: "janeiro", 2: "fevereiro", 3: "março", 4: "abril",
    5: "maio", 6: "junho", 7: "julho", 8: "agosto",
    9: "setembro", 10: "outubro", 11: "novembro", 12: "dezembro",
}


def _to_local_date(value):
    if not value:
        return None
    from django.utils import timezone

    if timezone.is_naive(value):
        value = timezone.make_aware(value, timezone.get_current_timezone())
    return value.astimezone(timezone.get_current_timezone()).date()


def _fmt_data_extenso(d) -> str:
    return f"{d.day} de {_MESES[d.month]} de {d.year}"


def _periodo_extenso(saida, retorno) -> str:
    inicio = _to_local_date(saida)
    fim = _to_local_date(retorno)
    if not inicio and not fim:
        return "—"
    if not inicio:
        inicio = fim
    if not fim or fim == inicio:
        return f"no dia {_fmt_data_extenso(inicio)}"
    if inicio.month == fim.month and inicio.year == fim.year:
        return f"nos dias {inicio.day} até {fim.day} de {_MESES[inicio.month]} de {inicio.year}"
    if inicio.year == fim.year:
        return (
            f"nos dias {inicio.day} de {_MESES[inicio.month]} até "
            f"{fim.day} de {_MESES[fim.month]} de {fim.year}"
        )
    return f"nos dias {_fmt_data_extenso(inicio)} até {_fmt_data_extenso(fim)}"


def _format_brl(value) -> str:
    if value in (None, ""):
        return "—"
    from documentos.services.formatters import format_currency_br
    return format_currency_br(value)


def _roteiro_resumo(oficio: Oficio) -> dict[str, Any]:
    r = oficio.roteiro
    if not r:
        return {"resumo": "", "destinos_texto": "", "saida": ""}
    partes: list[str] = []
    qs = r.destinos.select_related("municipio__estado").order_by("ordem", "pk")[:20]
    for d in qs:
        sigla = d.municipio.estado.sigla if d.municipio.estado_id else ""
        nome_cidade = d.municipio.nome if d.municipio_id else ""
        partes.append(f"{nome_cidade} ({sigla})".strip())
    destinos = "; ".join(partes) if partes else ""
    saida = ""
    primeira, _ = periodo_roteiro(r)
    if primeira:
        saida = _format_datetime(primeira)
    return {
        "resumo": str(r),
        "destinos_texto": destinos,
        "saida": saida,
        "quantidade_diarias": r.resumo_diarias or "",
    }


def _justificativa_bloco(oficio: Oficio) -> dict[str, Any]:
    exigida = oficio_exige_justificativa(oficio)
    texto = ""
    j: Justificativa | None
    try:
        j = oficio.justificativa
    except Justificativa.DoesNotExist:
        j = None
    if j and j.texto:
        texto = j.texto.strip()
    return {
        "exigida": exigida,
        "texto": texto,
        "status": getattr(j, "status", "") if j else "",
    }


def build_canonical_document_payload(oficio: Oficio, tipo: DocumentoTipo) -> dict[str, Any]:
    """Monta o contexto usado pelos templates registrados em documentos.services.templates."""
    from .services import build_oficio_document_payload

    oid = getattr(oficio, "pk", None)
    with measure_step(
        "build_canonical_document_payload",
        {"oficio_id": oid, "tipo": tipo.value},
    ):
        base = build_oficio_document_payload(oficio)
        institucional = build_configuracao_context()
        oficio_bloco = {
            **base,
            "roteiro_detalhe": _roteiro_resumo(oficio),
        }
        payload: dict[str, Any] = {
            "institucional": institucional,
            "oficio": oficio_bloco,
            "justificativa": _justificativa_bloco(oficio),
        }

        if tipo == DocumentoTipo.TERMO_AUTORIZACAO:
            raise ValueError("Use build_termo_payload com participante e variante.")
        return payload


def build_justificativa_payload(oficio: Oficio) -> dict[str, Any]:
    return build_canonical_document_payload(oficio, DocumentoTipo.JUSTIFICATIVA)


class VarianteTermo:
    SEMIPREENCHIDO = "semipreenchido"
    COMPLETO_COM_VIATURA = "completo_com_viatura"
    COMPLETO_SEM_VIATURA = "completo_sem_viatura"


def _resolver_variante_padrao(oficio: Oficio) -> str:
    from .services import build_oficio_document_payload

    dados = build_oficio_document_payload(oficio)
    viatura = (dados.get("viatura") or "").strip()
    if viatura:
        return VarianteTermo.COMPLETO_COM_VIATURA
    return VarianteTermo.COMPLETO_SEM_VIATURA


def _roteiro_linhas(roteiro, tipo: str) -> list[str]:
    if not roteiro:
        return []
    linhas: list[str] = []
    qs = roteiro.trechos.select_related(
        "origem_municipio",
        "origem_municipio__estado",
        "destino_municipio",
        "destino_municipio__estado",
    ).filter(sentido=tipo).order_by("ordem", "pk")
    for trecho in qs:
        origem = trecho.origem_municipio or getattr(trecho.origem_municipio, "estado", None)
        destino = trecho.destino_municipio or getattr(trecho.destino_municipio, "estado", None)
        partes = [f"{_blank(origem)} para {_blank(destino)}"]
        if trecho.saida_dt:
            partes.append(f"saida em {_format_datetime(trecho.saida_dt)}")
        if trecho.chegada_dt:
            partes.append(f"chegada em {_format_datetime(trecho.chegada_dt)}")
        linhas.append(" - ".join(partes))
    return linhas


def _destinos_texto(roteiro) -> str:
    if not roteiro:
        return "—"
    destinos = []
    for destino in roteiro.destinos.select_related("municipio__estado").order_by("ordem", "pk"):
        cidade = destino.municipio.nome if destino.municipio_id else ""
        sigla = destino.municipio.estado.sigla if destino.municipio.estado_id else ""
        destinos.append(f"{cidade}/{sigla}" if cidade and sigla else _blank(cidade or sigla, ""))
    return "; ".join(d for d in destinos if d) or "—"


def _transporte_payload(oficio: Oficio) -> dict[str, Any]:
    if oficio.viatura_id:
        viatura = oficio.viatura
        placa = viatura.placa_formatada
        modelo = viatura.modelo
        tipo = viatura.get_tipo_display() if viatura.tipo else ""
        combustivel = str(viatura.combustivel) if viatura.combustivel_id else ""
    else:
        placa = format_placa(oficio.transporte_placa_manual)
        modelo = oficio.transporte_modelo_manual
        tipo = oficio.get_transporte_tipo_manual_display() if oficio.transporte_tipo_manual else ""
        combustivel = (
            str(oficio.transporte_combustivel_manual)
            if oficio.transporte_combustivel_manual_id
            else ""
        )

    if oficio.motorista_id:
        motorista = _document_text(oficio.motorista.nome)
    elif oficio.motorista_modo == Oficio.MOTORISTA_MODO_MANUAL:
        motorista = _document_text(oficio.motorista_manual_nome)
    else:
        motorista = ""

    return {
        "tem_viatura": bool((placa or "").strip()),
        "placa": _blank(placa),
        "modelo": _document_text(modelo),
        "tipo": _document_text(tipo),
        "combustivel": _document_text(combustivel),
        "motorista": _document_text(motorista),
        "porte_armas": "Sim" if oficio.porte_transporte_armas else "Nao",
        "unidade": _document_text(oficio.solicitante),
    }


def _viagem_payload(oficio: Oficio) -> dict[str, Any]:
    roteiro = oficio.roteiro
    saida, retorno = periodo_roteiro(roteiro)
    saida_txt = _format_datetime(saida)
    retorno_txt = _format_datetime(retorno)
    periodo = _periodo_extenso(saida, retorno)
    destino_principal = "—"
    if roteiro:
        destino = roteiro.destinos.select_related("municipio__estado").order_by("ordem", "pk").first()
        if destino:
            destino_principal = str(destino.municipio)
    roteiro_ida = _roteiro_linhas(roteiro, "IDA")
    roteiro_retorno = _roteiro_linhas(roteiro, "RETORNO")
    diarias = oficio.diarias_para_servidores()
    if diarias:
        quantidade_diarias = _blank(diarias["quantidade"])
        valor_diarias = _format_brl(diarias["valor_decimal"])
        valor_diarias_extenso = _document_text(diarias["valor_extenso"])
    else:
        quantidade_diarias = _blank(getattr(roteiro, "resumo_diarias", ""))
        valor_diarias = _format_brl(getattr(roteiro, "valor_diarias", None))
        valor_diarias_extenso = _document_text(getattr(roteiro, "valor_diarias_extenso", ""))
    return {
        "destino_principal": destino_principal,
        "destinos_texto": _destinos_texto(roteiro),
        "saida": saida_txt,
        "retorno": retorno_txt,
        "periodo": periodo,
        "roteiro_ida": roteiro_ida,
        "roteiro_ida_texto": "; ".join(roteiro_ida) or _destinos_texto(roteiro),
        "roteiro_retorno": roteiro_retorno,
        "roteiro_retorno_texto": "; ".join(roteiro_retorno) or "—",
        "quantidade_diarias": quantidade_diarias,
        "valor_diarias": valor_diarias,
        "valor_diarias_extenso": valor_diarias_extenso,
        "motivo": _document_text(oficio.motivo),
    }


def _oficio_termo_payload(oficio: Oficio) -> dict[str, Any]:
    return {
        "numero_formatado": oficio.numero_formatado,
        "protocolo_formatado": format_protocolo(oficio.protocolo) or "—",
        "data_criacao": _format_date(oficio.data_criacao),
        "assunto": _document_text(oficio.assunto),
        "origem": _document_text(oficio.solicitante),
        "destino": "Direcao/chefia competente",
    }


def build_termo_payload(
    oficio: Oficio,
    servidor: Servidor,
    *,
    variante: str | None = None,
    modo_semipreenchido: bool = False,
) -> dict[str, Any]:
    if modo_semipreenchido:
        var = VarianteTermo.SEMIPREENCHIDO
    else:
        var = variante or _resolver_variante_padrao(oficio)
    base_ctx = build_canonical_document_payload(oficio, DocumentoTipo.OFICIO)
    participante = {
        "id": servidor.pk,
        "nome": _document_text(servidor.nome),
        "cargo": _document_text(servidor.cargo.nome if servidor.cargo_id else ""),
        "rg_formatado": servidor.rg_formatado,
        "cpf": servidor.cpf or "",
        "cpf_formatado": servidor.cpf_formatado,
        "unidade": _document_text(servidor.unidade.nome if servidor.unidade_id else ""),
        "telefone_formatado": servidor.telefone_formatado,
        "email": "",
    }
    viagem = _viagem_payload(oficio)
    transporte = _transporte_payload(oficio)
    oficio_termo = _oficio_termo_payload(oficio)
    textos = {
        "titulo": "TERMO DE AUTORIZAÇÃO",
        "corpo_autorizacao": (
            "Autorizo o servidor acima identificado a realizar o deslocamento descrito neste "
            "termo, vinculado ao oficio indicado, observadas as normas administrativas "
            "aplicaveis ao servico publico e ao uso do transporte informado."
        ),
        "declaracao": (
            "O servidor declara ciencia das informacoes registradas, do periodo autorizado, "
            "do roteiro previsto e das responsabilidades funcionais decorrentes da viagem."
        ),
        "observacoes": _document_text(
            getattr(oficio.roteiro, "observacoes", "") if oficio.roteiro_id else "",
        ),
    }
    base_ctx["termo"] = {
        "variante": var,
        "participante": participante,
        "viagem": viagem,
        "transporte": transporte,
        "oficio": oficio_termo,
        "textos": textos,
    }
    return base_ctx
