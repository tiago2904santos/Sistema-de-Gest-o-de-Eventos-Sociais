"""Como o ofício se apresenta: no resumo documental e no cartão da lista.

O cartão reproduz o da origem (`partials/_oficio_card.html` do Gerenciador de
Viagens), com as mesmas palavras: "Nº 161/2026 · Protocolo 12.345.678-9", o
período com os destinos, o selo temporal do roteiro, a equipe com cargo e
unidade e a marca de motorista, placa e modelo, os trechos com horários, o
valor total por extenso, a quantidade de diárias e o bloco da justificativa.
"""

from django.urls import reverse
from django.utils import timezone
from django.utils.formats import number_format

from core.utils.masks import format_placa, format_protocolo
from viagens_roteiros.presenters import rotulo_cidade, selo_temporal

from .roteiro_context import periodo_roteiro
from .services import build_oficio_document_payload


def apresentar_oficio(oficio):
    resumo = build_oficio_document_payload(oficio)
    diarias = oficio.diarias_para_servidores()
    resumo['protocolo'] = format_protocolo(oficio.protocolo)
    resumo['diarias'] = diarias
    resumo['valor_diarias'] = number_format(diarias['valor_decimal'], 2, force_grouping=True) if diarias and diarias['valor_decimal'] is not None else '—'
    return resumo


def iniciais(nome):
    """"JP" para JANINE LACERDA DO PRADO: primeiro e último nome, como na origem."""
    partes = [p for p in (nome or "").split() if p]
    if not partes:
        return "—"
    if len(partes) == 1:
        return partes[0][:2].upper()
    return (partes[0][0] + partes[-1][0]).upper()


def _local(valor):
    if not valor:
        return None
    return timezone.localtime(valor) if timezone.is_aware(valor) else valor


def periodo_curto(inicio, fim):
    """"25/08 a 30/08/2026"; "25/08/2026" quando é um dia só."""
    inicio, fim = _local(inicio), _local(fim)
    if not inicio and not fim:
        return ""
    if not fim or (inicio and inicio.date() == fim.date()):
        return f"{(inicio or fim):%d/%m/%Y}"
    if not inicio:
        return f"até {fim:%d/%m/%Y}"
    if inicio.year == fim.year:
        return f"{inicio:%d/%m} a {fim:%d/%m/%Y}"
    return f"{inicio:%d/%m/%Y} a {fim:%d/%m/%Y}"


def destinos_resumidos(roteiro, maximo=2):
    """"ALMIRANTE TAMANDARÉ/PR, ANTONINA/PR +1": os primeiros, e quantos ficaram de fora."""
    if roteiro is None:
        return ""
    nomes = [rotulo_cidade(d.municipio).upper() for d in roteiro.destinos.all() if d.municipio_id]
    if not nomes:
        return ""
    texto = ", ".join(nomes[:maximo])
    if len(nomes) > maximo:
        texto += f" +{len(nomes) - maximo}"
    return texto


def titulo_do_cartao(oficio):
    titulo = f"Nº {oficio.numero_formatado}"
    if oficio.protocolo:
        titulo += f" · Protocolo {format_protocolo(oficio.protocolo)}"
    return titulo


def subtitulo_do_cartao(oficio):
    if oficio.roteiro_id is None:
        return ""
    periodo = periodo_curto(*periodo_roteiro(oficio.roteiro))
    destinos = destinos_resumidos(oficio.roteiro)
    return " · ".join(parte for parte in [periodo, destinos] if parte)


def selo_do_cartao(oficio):
    """Cancelado prevalece; depois o selo temporal do roteiro; sem data, a situação."""
    if oficio.cancelado:
        return "Cancelado", "cancelada"
    if oficio.roteiro_id:
        selo, tom = selo_temporal(oficio.roteiro)
        if selo:
            return selo, tom
    return oficio.get_status_display(), "rascunho" if oficio.status == oficio.STATUS_RASCUNHO else "neutro"


def _descricao_pessoa(servidor):
    cargo = str(servidor.cargo) if servidor.cargo_id else ""
    unidade = ""
    if servidor.unidade_id:
        unidade = servidor.unidade.sigla or servidor.unidade.nome
    return " · ".join(parte for parte in [cargo, unidade] if parte)


def equipe_do_cartao(oficio, artefatos_termo=None):
    """Viajantes na ordem do cadastro, com a marca de motorista e os endereços do termo."""
    artefatos_termo = artefatos_termo or {}
    com_termo = {s.pk for s in oficio.servidores_termo_autorizacao.all()}
    pessoas = []
    for servidor in oficio.servidores.all():
        pessoas.append({
            "pk": servidor.pk,
            "nome": servidor.nome,
            "iniciais": iniciais(servidor.nome),
            "descricao": _descricao_pessoa(servidor),
            "motorista": oficio.motorista_id == servidor.pk,
            "tem_termo": servidor.pk in com_termo,
            "url_termo_pdf": reverse("viagens_oficios:termo", args=[oficio.pk, servidor.pk, "pdf"]),
            "url_termo_docx": reverse("viagens_oficios:termo", args=[oficio.pk, servidor.pk, "docx"]),
            "url_termo_assinado": (
                reverse("viagens_oficios:assinatura_artefato", args=[artefatos_termo[servidor.pk]])
                if servidor.pk in artefatos_termo else ""
            ),
        })
    return pessoas


def transporte_do_cartao(oficio):
    if oficio.viatura_id:
        return {"placa": oficio.viatura.placa_formatada, "modelo": oficio.viatura.modelo or ""}
    return {
        "placa": format_placa(oficio.transporte_placa_manual) if oficio.transporte_placa_manual else "",
        "modelo": oficio.transporte_modelo_manual or "",
    }


def _horario(valor):
    valor = _local(valor)
    return f"{valor:%d/%m/%Y %H:%M}" if valor else "—"


def trechos_do_cartao(oficio):
    if oficio.roteiro_id is None:
        return []
    return [
        {
            "rota": f"{rotulo_cidade(t.origem_municipio).upper()} → {rotulo_cidade(t.destino_municipio).upper()}",
            "horario": f"{_horario(t.saida_dt)} → {_horario(t.chegada_dt)}",
        }
        for t in oficio.roteiro.trechos.all()
    ]


def diarias_do_cartao(oficio):
    try:
        diarias = oficio.diarias_para_servidores()
    except Exception:  # roteiro sem efetivo: o cartão não pode derrubar a lista
        diarias = None
    if not diarias or diarias.get("valor_decimal") is None:
        return None
    return {
        "valor": f"R$ {number_format(diarias['valor_decimal'], decimal_pos=2, force_grouping=True)}",
        "extenso": diarias.get("valor_extenso") or "",
        "quantidade": diarias.get("quantidade") or "",
    }


def justificativa_do_cartao(oficio):
    justificativa = getattr(oficio, "justificativa", None)
    texto = (justificativa.texto if justificativa else "") or ""
    return {
        "preenchida": bool(texto.strip()),
        "texto": texto.strip() or "Nenhuma justificativa informada.",
    }


def cartao_da_lista(oficio, *, editar_url, artefatos_termo=None, artefato_oficio_pdf=None, artefato_justificativa_pdf=None):
    """Tudo o que o cartão da lista mostra, resolvido de uma vez."""
    selo, tom = selo_do_cartao(oficio)
    return {
        "oficio": oficio,
        "titulo": titulo_do_cartao(oficio),
        "subtitulo": subtitulo_do_cartao(oficio),
        "selo": selo,
        "selo_tom": tom,
        "equipe": equipe_do_cartao(oficio, artefatos_termo),
        "transporte": transporte_do_cartao(oficio),
        "trechos": trechos_do_cartao(oficio),
        "diarias": diarias_do_cartao(oficio),
        "justificativa": justificativa_do_cartao(oficio),
        "editar_url": editar_url,
        "editar_justificativa_url": f"{editar_url}#justificativa",
        "artefato_oficio_pdf": artefato_oficio_pdf,
        "artefato_justificativa_pdf": artefato_justificativa_pdf,
    }
