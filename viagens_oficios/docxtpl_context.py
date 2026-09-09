"""
Contexto plano (flat) para templates DOCX legados (docxtpl), alinhado a
`oficio_model.docx` e `modelo_justificativa.docx` do Central de Viagens 2.0.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any
from typing import Mapping

from django.utils import timezone

from core.normalizers import normalize_upper
from core.errors import capture
from viagens_cadastros.selectors import build_configuracao_context
from documentos.services.timing import measure_step
from documentos.services.formatters import format_city_uf
from documentos.services.formatters import format_currency_br
from documentos.services.formatters import format_document_display
from documentos.services.formatters import format_institucional_rodape_linha
from documentos.services.formatters import format_valor_extenso_display

from viagens_oficios.models import Justificativa

from viagens_roteiros.models import RoteiroTrecho

from .assunto_oficio import resolver_assunto_oficio
from .models import Oficio

DESTINO_FORA_PARANA = "SESP"
DESTINO_DENTRO_PARANA = "Gabinete do Delegado Geral Adjunto"

_MESES_PTBR = {
    1: "janeiro",
    2: "fevereiro",
    3: "março",
    4: "abril",
    5: "maio",
    6: "junho",
    7: "julho",
    8: "agosto",
    9: "setembro",
    10: "outubro",
    11: "novembro",
    12: "dezembro",
}

# Chaves extraídas dos .docx legados (garantir todas presentes no dict).
OFICIO_DOCXTPL_KEYS = frozenset(
    {
        "oficio",
        "data_do_oficio",
        "protocolo",
        "nome_chefia",
        "cargo_chefia",
        "nome_destinatario",
        "cargo_destinatario",
        "unidade",
        "unidade_cabecalho",
        "orgao_destino",
        "placa",
        "viatura",
        "combustivel",
        "tipo_viatura",
        "motorista_formatado",
        "custo",
        "diarias_x",
        "diaria",
        "valor_total_oficio",
        "destinos_bloco",
        "col_servidor",
        "col_rgcpf",
        "col_cargo",
        "col_ida_saida",
        "col_ida_chegada",
        "col_volta_saida",
        "col_volta_chegada",
        "col_solicitacao",
        "assunto_linha",
        "assunto_oficio",
        "assunto_termo",
        "armamento",
        "motivo",
        "divisao",
        "divisao_cabecalho",
        "email",
        "endereco",
        "nome_orgao",
        "nome_orgao_cabecalho",
        "telefone",
        "unidade_rodape",
    },
)

JUSTIFICATIVA_DOCXTPL_KEYS = frozenset(
    {
        "sede",
        "data_extenso",
        "justificativa",
        "assinante_justificativa",
        "cargo_assinante_justificativa",
        "divisao",
        "unidade",
        "unidade_rodape",
        "endereco",
        "email",
        "telefone",
    },
)


def _txt(v: object) -> str:
    return str(v or "").strip()


def _hdr(v: object) -> str:
    t = _txt(v)
    return normalize_upper(t) if t else ""


def _fmt_date(d: date | datetime | None) -> str:
    if not d:
        return ""
    if isinstance(d, datetime):
        from django.utils import timezone as tz
        if tz.is_aware(d):
            d = tz.localtime(d)
        d = d.date()
    return d.strftime("%d/%m/%Y")


def _fmt_time(dt: datetime | None) -> str:
    if not dt:
        return ""
    from django.utils import timezone as tz
    if tz.is_aware(dt):
        dt = tz.localtime(dt)
    return dt.strftime("%H:%M")


def _build_endereco(inst: dict[str, Any]) -> str:
    """Endereço institucional em uma linha legível (separador ` - `, cidade/UF normalizada)."""
    log = _txt(inst.get("logradouro"))
    log_fmt = format_document_display(log) if log else ""
    num = _txt(inst.get("numero"))
    bai = _txt(inst.get("bairro"))
    bai_fmt = format_document_display(bai) if bai else ""
    linha1 = " - ".join([p for p in (log_fmt, num, bai_fmt) if p])

    cidade = _txt(inst.get("cidade_endereco"))
    uf = _txt(inst.get("uf")).upper()
    cidade_uf = ""
    if cidade and uf:
        cidade_uf = format_city_uf(f"{cidade}/{uf}")
    elif cidade:
        cidade_uf = format_document_display(cidade)
    elif uf:
        cidade_uf = uf

    cep = _txt(inst.get("cep_formatado") or inst.get("cep"))
    cep_part = f"CEP {cep}" if cep else ""

    return " - ".join(x for x in (linha1, cidade_uf, cep_part) if x)


def _build_sede(inst: dict[str, Any]) -> str:
    cidade = _txt(inst.get("cidade_endereco"))
    uf = _txt(inst.get("uf")).upper()
    if cidade and uf:
        return format_city_uf(f"{cidade}/{uf}")
    if cidade:
        return format_document_display(cidade)
    return format_document_display(_txt(inst.get("sede"))) if _txt(inst.get("sede")) else ""


def _assinatura_nome_cargo(
    inst: dict[str, Any],
    tipo: str | None = None,
    *,
    fallback_geral: bool = True,
) -> tuple[str, str]:
    ass = inst.get("assinaturas") or {}
    rows: list[dict[str, Any]] = []
    if isinstance(ass, dict):
        if tipo is not None:
            lst = ass.get(tipo) or []
            if isinstance(lst, list):
                for row in lst:
                    if isinstance(row, dict) and (_txt(row.get("nome")) or row.get("servidor")):
                        rows.append(row)
        else:
            for _tipo_key, lst in ass.items():
                if not isinstance(lst, list):
                    continue
                for row in lst:
                    if isinstance(row, dict) and (_txt(row.get("nome")) or row.get("servidor")):
                        rows.append(row)
    rows.sort(key=lambda r: int(r.get("ordem") or 0))
    if not rows:
        if fallback_geral:
            return _txt(inst.get("nome_chefia")), _txt(inst.get("cargo_chefia"))
        return "", ""
    row = rows[0]
    srv = row.get("servidor")
    nome = _txt(row.get("nome") or (getattr(srv, "nome", "") if srv else ""))
    cargo = ""
    if srv is not None and getattr(srv, "cargo_id", None):
        cargo = _txt(srv.cargo.nome)
    return nome, cargo


def _orgao_destino(oficio: Oficio, inst: Mapping[str, Any]) -> str:
    destino_padrao = _txt(inst.get("destinatario_oficio_unidade")) or DESTINO_DENTRO_PARANA
    r = getattr(oficio, "roteiro", None)
    if not r:
        raw = destino_padrao
    else:
        raw = destino_padrao
        for d in r.destinos.select_related("municipio__estado"):
            if d.municipio.estado_id and d.municipio.estado.sigla != "PR":
                raw = DESTINO_FORA_PARANA
                break
        else:
            for t in r.trechos.select_related("destino_municipio__estado"):
                if getattr(t.destino_municipio, "estado_id", None) and getattr(t.destino_municipio, "estado", None).sigla != "PR":
                    raw = DESTINO_FORA_PARANA
                    break
    return format_document_display(raw)


def _destinatario_nome_cargo(inst: Mapping[str, Any]) -> tuple[str, str]:
    return _txt(inst.get("destinatario_oficio_nome")), _txt(inst.get("destinatario_oficio_cargo"))


def _build_column_lines(items: list[str], blank_lines: int = 1) -> str:
    lines: list[str] = []
    cleaned = [str(x).strip() for x in items if str(x or "").strip()]
    for index, item in enumerate(cleaned):
        lines.append(item)
        if index < len(cleaned) - 1:
            lines.extend([""] * blank_lines)
    return "\n".join(lines)


def _build_optional_column_lines(items: list[str], blank_lines: int = 1) -> str:
    cleaned = [str(x or "").strip() for x in items]
    if not any(cleaned):
        return ""
    lines: list[str] = []
    for index, item in enumerate(cleaned):
        lines.append(item)
        if index < len(cleaned) - 1:
            lines.extend([""] * blank_lines)
    return "\n".join(lines)


def _viajantes(oficio: Oficio) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for s in oficio.servidores.select_related("cargo").order_by("nome"):
        nm = _txt(s.nome)
        cg = _txt(s.cargo.nome if s.cargo_id else "")
        out.append(
            {
                "id": s.pk,
                "nome": format_document_display(nm) if nm else "",
                "cargo": format_document_display(cg) if cg else "",
                "rg": _txt(s.rg_formatado),
                "cpf": _txt(s.cpf_formatado),
            },
        )
    return out


def _col_rgcpf(viajantes: list[dict[str, str]]) -> str:
    linhas: list[str] = []
    for index, v in enumerate(viajantes):
        linhas.append(f"RG: {v.get('rg') or '-'}")
        linhas.append(f"CPF: {v.get('cpf') or '-'}")
        if index < len(viajantes) - 1:
            linhas.append("")
    return "\n".join(linhas)


def _trecho_label(t: RoteiroTrecho) -> tuple[str, str]:
    def cidade_sigla(c, e):
        if c and e:
            return format_city_uf(f"{c.nome}/{e.sigla}")
        if c:
            return format_document_display(c.nome)
        if e:
            return _txt(e.sigla).upper()
        return ""

    orig = cidade_sigla(t.origem_municipio, getattr(t.origem_municipio, "estado", None))
    dest = cidade_sigla(t.destino_municipio, getattr(t.destino_municipio, "estado", None))
    return orig or "—", dest or "—"


def _route_columns(trechos: list[RoteiroTrecho]) -> tuple[str, str]:
    saida_lines: list[str] = []
    chegada_lines: list[str] = []
    for idx, trecho in enumerate(trechos):
        orig, dest = _trecho_label(trecho)
        sd = _fmt_date(trecho.saida_dt) if trecho.saida_dt else ""
        st = _fmt_time(trecho.saida_dt) if trecho.saida_dt else ""
        cd = _fmt_date(trecho.chegada_dt) if trecho.chegada_dt else ""
        ct = _fmt_time(trecho.chegada_dt) if trecho.chegada_dt else ""
        saida_lines.append(f"Saída {orig}: {sd} {st}".strip())
        chegada_lines.append(f"Chegada {dest}: {cd} {ct}".strip())
        if idx < len(trechos) - 1:
            saida_lines.append("")
            chegada_lines.append("")
    return "\n".join(saida_lines), "\n".join(chegada_lines)


def _retorno_from_roteiro_header(r, ida: list[RoteiroTrecho]) -> RoteiroTrecho:
    trecho = RoteiroTrecho(
        roteiro=r,
        sentido=RoteiroTrecho.Sentido.RETORNO,
        saida_dt=r.retorno_saida_dt,
        chegada_dt=r.retorno_chegada_dt,
    )
    origem = ida[-1] if ida else None
    if origem:
        trecho.origem_municipio = origem.destino_municipio
    else:
        destino = r.destinos.select_related("municipio__estado").order_by("ordem", "pk").first()
        if destino:
            trecho.origem_municipio = destino.municipio
    trecho.destino_municipio = r.origem_municipio
    return trecho


def _bate_volta_ida_volta(
    r, qs: list[RoteiroTrecho]
) -> tuple[list[RoteiroTrecho], list[RoteiroTrecho]] | None:
    """Reagrupa os trechos por direção no modo bate-volta diário.

    Nesse modo os trechos são gravados como pares alternados
    ``sede → destino`` (ordem par) e ``destino → sede`` (ordem ímpar), e apenas
    o último recebe ``tipo=RETORNO``. Dividir por ``tipo`` jogaria as voltas
    intermediárias no ROTEIRO DE IDA. Aqui todas as idas vão para o bloco de
    ida e todas as voltas para o de retorno.

    Retorna ``(ida, volta)`` quando o padrão bate-volta é reconhecido; caso
    contrário ``None`` (roteiro comum, split por ``tipo``).
    """
    sede = (getattr(r.origem_municipio, "estado_id", None), r.origem_municipio_id)
    if not sede[1] or len(qs) < 2 or len(qs) % 2 != 0:
        return None
    away = None
    for idx, t in enumerate(qs):
        origem = (getattr(t.origem_municipio, "estado_id", None), t.origem_municipio_id)
        destino = (getattr(t.destino_municipio, "estado_id", None), t.destino_municipio_id)
        if idx % 2 == 0:  # perna de ida: sede → destino
            if origem != sede:
                return None
            if away is None:
                away = destino
            if destino != away:
                return None
        else:  # perna de volta: destino → sede
            if away is None or origem != away or destino != sede:
                return None
    if not away or away == sede:
        return None
    return qs[0::2], qs[1::2]


def _roteiro_trechos(oficio: Oficio) -> tuple[list[RoteiroTrecho], list[RoteiroTrecho]]:
    r = oficio.roteiro
    if not r:
        return [], []
    qs = list(r.trechos.select_related("origem_municipio", "origem_municipio__estado", "destino_municipio", "destino_municipio__estado").order_by("ordem", "pk"))
    bate_volta = _bate_volta_ida_volta(r, qs)
    if bate_volta is not None:
        return bate_volta
    ida = [t for t in qs if t.sentido == RoteiroTrecho.Sentido.IDA]
    volta = [t for t in qs if t.sentido == RoteiroTrecho.Sentido.RETORNO]
    if not volta and (r.retorno_saida_dt or r.retorno_chegada_dt):
        volta = [_retorno_from_roteiro_header(r, ida)]
    return ida, volta


def _destinos_bloco(oficio: Oficio) -> str:
    r = oficio.roteiro
    if not r:
        return ""
    partes: list[str] = []
    for d in r.destinos.select_related("municipio__estado").order_by("ordem", "pk"):
        if d.municipio_id and d.municipio.estado_id:
            partes.append(format_city_uf(f"{d.municipio.nome}/{d.municipio.estado.sigla}"))
    return "\n".join(partes) if partes else ""


def _custeio_text(oficio: Oficio) -> str:
    labels = {
        Oficio.CUSTEIO_UNIDADE_DPC: "UNIDADE - DPC (diárias e combustível custeados pela DPC).",
        Oficio.CUSTEIO_OUTRA_INSTITUICAO: "OUTRA INSTITUIÇÃO",
        Oficio.CUSTEIO_ONUS_LIMITADO: "ÔNUS LIMITADOS AOS PRÓPRIOS VENCIMENTOS",
    }
    linhas: list[str] = []
    for choice in (
        Oficio.CUSTEIO_UNIDADE_DPC,
        Oficio.CUSTEIO_OUTRA_INSTITUICAO,
        Oficio.CUSTEIO_ONUS_LIMITADO,
    ):
        marcador = "( X )" if oficio.custeio == choice else "(   )"
        label = labels.get(choice, choice)
        if choice == Oficio.CUSTEIO_OUTRA_INSTITUICAO and oficio.custeio == choice and oficio.custeio_observacao:
            label = f"{label}: {oficio.custeio_observacao}"
        linhas.append(f"{marcador} {label}")
    return "\n".join(linhas)


def _motorista_formatado(oficio: Oficio) -> str:
    from core.utils.masks import format_protocolo

    def _append_refs(linhas: list[str]) -> str:
        ref = _txt(oficio.motorista_oficio_referencia)
        if ref:
            linhas.append(f"Ofício do Motorista: {ref}")
        prot = _txt(oficio.motorista_protocolo_ref)
        if prot:
            prot_fmt = format_protocolo(prot) or prot
            linhas.append(f"Protocolo do Motorista: {prot_fmt}")
        return "\n".join(linhas)

    if oficio.motorista_id:
        nome = _txt(oficio.motorista.nome)
        nome_fmt = format_document_display(nome) if nome else ""
        if not nome_fmt:
            return ""
        na_equipe = oficio.servidores.filter(pk=oficio.motorista_id).exists()
        if na_equipe:
            return nome_fmt
        linhas = [nome_fmt]
        if _txt(oficio.motorista_oficio_referencia) or _txt(oficio.motorista_protocolo_ref):
            return _append_refs(linhas)
        return nome_fmt

    if oficio.motorista_modo == Oficio.MOTORISTA_MODO_MANUAL:
        nome = _txt(oficio.motorista_manual_nome)
        if not nome:
            return ""
        linhas = [format_document_display(nome)]
        return _append_refs(linhas)

    return ""


def _veiculo_bloco(oficio: Oficio) -> dict[str, str]:
    placa = ""
    modelo = ""
    comb = ""
    tipo_v = ""
    if oficio.viatura_id:
        v = oficio.viatura
        placa = _txt(v.placa_formatada)
        modelo = _txt(v.modelo)
        comb = _txt(v.combustivel.nome if v.combustivel_id else "")
        tipo_v = _txt(v.get_tipo_display())
    else:
        from core.utils.masks import format_placa

        placa = format_placa(oficio.transporte_placa_manual) if oficio.transporte_placa_manual else ""
        modelo = _txt(oficio.transporte_modelo_manual)
        if oficio.transporte_combustivel_manual_id:
            comb = _txt(oficio.transporte_combustivel_manual.nome)
        tipo_v = _txt(oficio.get_transporte_tipo_manual_display() if oficio.transporte_tipo_manual else "")
    modelo_d = format_document_display(modelo) if modelo else ""
    comb_d = format_document_display(comb) if comb else ""
    tipo_d = format_document_display(tipo_v) if tipo_v else ""
    viatura_disp = modelo_d or placa or "—"
    return {
        "placa": placa,
        "viatura": viatura_disp,
        "combustivel": comb_d,
        "tipo_viatura": tipo_d,
    }


def _diarias(oficio: Oficio) -> tuple[str, str]:
    r = oficio.roteiro
    if not r:
        return "", ""
    diarias = oficio.diarias_para_servidores()
    if not diarias:
        return _txt(r.resumo_diarias), ""
    q = _txt(diarias["quantidade"])
    valor_fmt = format_currency_br(diarias["valor_decimal"])
    extenso = _txt(diarias["valor_extenso"])
    if extenso:
        valor = f"{valor_fmt} ({format_valor_extenso_display(extenso)})"
    else:
        valor = valor_fmt
    return q, valor


def _solicitacoes_por_servidor(oficio):
    from viagens_prestacoes.models import PrestacaoServidor
    return dict(PrestacaoServidor.objects.filter(prestacao__oficio=oficio).exclude(numero_solicitacao="").values_list("servidor_id", "numero_solicitacao"))



def build_oficio_docxtpl_context(
    oficio: Oficio,
    *,
    solicitacoes_por_servidor: Mapping[int, str] | None = None,
) -> dict[str, Any]:
    oid = getattr(oficio, "pk", None)
    with measure_step("build_oficio_docxtpl_context", {"oficio_id": oid}):
        return _build_oficio_docxtpl_context_impl(
            oficio,
            solicitacoes_por_servidor=solicitacoes_por_servidor,
        )


def _build_oficio_docxtpl_context_impl(
    oficio: Oficio,
    *,
    solicitacoes_por_servidor: Mapping[int, str] | None = None,
) -> dict[str, Any]:
    inst = build_configuracao_context()
    nome_chefia, cargo_chefia = _assinatura_nome_cargo(
        inst,
        "OFICIO",
        fallback_geral=False,
    )
    nome_destinatario, cargo_destinatario = _destinatario_nome_cargo(inst)
    nome_orgao_raw = _txt(inst.get("nome_orgao"))
    unidade_campo_raw = _txt(inst.get("unidade"))
    sigla_raw = _txt(inst.get("sigla_orgao"))
    unidade_raw = unidade_campo_raw or nome_orgao_raw or sigla_raw
    unidade = format_document_display(unidade_raw) if unidade_raw else ""
    viajantes = _viajantes(oficio)
    ida, volta = _roteiro_trechos(oficio)
    ida_saida, ida_chegada = _route_columns(ida)
    volta_saida, volta_chegada = _route_columns(volta)
    v = _veiculo_bloco(oficio)
    diarias_x, diaria = _diarias(oficio)
    data_of = _fmt_date(oficio.data_criacao)
    from core.utils.masks import format_protocolo

    protocolo = format_protocolo(oficio.protocolo)
    assunto_doc = resolver_assunto_oficio(oficio)
    solicitacoes = solicitacoes_por_servidor
    if solicitacoes is None:
        solicitacoes = _solicitacoes_por_servidor(oficio)

    ctx: dict[str, Any] = {
        "oficio": oficio.numero_formatado if oficio.numero and oficio.ano else "—",
        "data_do_oficio": data_of,
        "protocolo": protocolo,
        "nome_chefia": format_document_display(nome_chefia) if nome_chefia else "",
        "cargo_chefia": format_document_display(cargo_chefia) if cargo_chefia else "",
        "nome_destinatario": format_document_display(nome_destinatario) if nome_destinatario else "",
        "cargo_destinatario": format_document_display(cargo_destinatario) if cargo_destinatario else "",
        "nome_orgao": format_document_display(nome_orgao_raw) if nome_orgao_raw else "",
        "nome_orgao_cabecalho": _hdr(nome_orgao_raw),
        "unidade": unidade,
        "unidade_cabecalho": _hdr(unidade_campo_raw),
        "orgao_destino": _orgao_destino(oficio, inst),
        "placa": v["placa"],
        "viatura": v["viatura"],
        "combustivel": v["combustivel"],
        "tipo_viatura": v["tipo_viatura"],
        "motorista_formatado": _motorista_formatado(oficio),
        "custo": _custeio_text(oficio),
        "diarias_x": diarias_x,
        "diaria": diaria,
        # Alias para templates que evoluam o placeholder; mantém o mesmo texto que `diaria`.
        "valor_total_oficio": diaria,
        "destinos_bloco": _destinos_bloco(oficio),
        "col_servidor": _build_column_lines([v["nome"] for v in viajantes], blank_lines=2),
        "col_rgcpf": _col_rgcpf(viajantes),
        "col_cargo": _build_column_lines([v["cargo"] for v in viajantes], blank_lines=2),
        "col_ida_saida": ida_saida,
        "col_ida_chegada": ida_chegada,
        "col_volta_saida": volta_saida,
        "col_volta_chegada": volta_chegada,
        "col_solicitacao": _build_optional_column_lines(
            [_txt(solicitacoes.get(v["id"], "")) for v in viajantes],
            blank_lines=2,
        ),
        "assunto_linha": assunto_doc["assunto_linha"],
        "assunto_oficio": assunto_doc["assunto_oficio"],
        "assunto_termo": assunto_doc["assunto_termo"],
        "armamento": "Sim" if oficio.porte_transporte_armas else "Não",
        "motivo": format_document_display(_txt(oficio.motivo)) if _txt(oficio.motivo) else "",
        "divisao": _hdr(inst.get("divisao")),
        "divisao_cabecalho": _hdr(inst.get("divisao")),
        "email": (_txt(inst.get("email")) or "").lower(),
        "endereco": _build_endereco(inst),
        "telefone": _txt(inst.get("telefone_formatado") or inst.get("telefone")),
        "unidade_rodape": unidade,
    }
    for key in OFICIO_DOCXTPL_KEYS:
        ctx.setdefault(key, "")
    return ctx


def _format_data_extenso(d: date) -> str:
    mes = _MESES_PTBR.get(d.month, str(d.month))
    return f"{d.day} de {mes} de {d.year}"


def build_justificativa_docxtpl_context(oficio: Oficio) -> dict[str, Any]:
    oid = getattr(oficio, "pk", None)
    with measure_step("build_justificativa_docxtpl_context", {"oficio_id": oid}):
        return _build_justificativa_docxtpl_context_impl(oficio)


def _build_justificativa_docxtpl_context_impl(oficio: Oficio) -> dict[str, Any]:
    inst = build_configuracao_context()
    nome_a, cargo_a = _assinatura_nome_cargo(inst, "JUSTIFICATIVA", fallback_geral=False)
    unidade = _txt(inst.get("unidade")) or _txt(inst.get("nome_orgao")) or _txt(inst.get("sigla_orgao"))
    texto = ""
    try:
        j = oficio.justificativa
        texto = _txt(j.texto)
    except Justificativa.DoesNotExist:
        pass

    ctx: dict[str, Any] = {
        "sede": _build_sede(inst),
        "data_extenso": _format_data_extenso(timezone.localdate()),
        "justificativa": texto,
        "assinante_justificativa": format_document_display(nome_a) if nome_a else "",
        "cargo_assinante_justificativa": format_document_display(cargo_a) if cargo_a else "",
        "divisao": _hdr(inst.get("divisao")),
        "unidade": _hdr(unidade),
        "unidade_rodape": format_institucional_rodape_linha(inst),
        "endereco": _build_endereco(inst),
        "email": (_txt(inst.get("email")) or "").lower(),
        "telefone": _txt(inst.get("telefone_formatado") or inst.get("telefone")),
    }
    for key in JUSTIFICATIVA_DOCXTPL_KEYS:
        ctx.setdefault(key, "")
    return ctx
