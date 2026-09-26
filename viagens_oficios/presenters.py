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


def tipo_do_oficio(oficio, *, prazo=None):
    """Autorização ou Convalidação, e por quê — a decisão que o documento toma.

    A regra é a de `assunto_oficio.resolver_assunto_oficio` (data do ofício
    contra a primeira saída do roteiro); a obrigatoriedade da justificativa
    segue `avaliar_justificativa_oficio` (antecedência até o prazo, ou saída
    antes do ofício). `prazo` evita reler a configuração em cada linha da lista.
    """
    from .assunto_oficio import resolver_assunto_oficio
    from .justificativas_services import get_prazo_justificativa_dias, get_primeira_saida_oficio

    assunto = resolver_assunto_oficio(oficio)
    autorizacao = assunto["assunto_termo"] == "autorização"
    marcador = assunto["assunto_rotulo"].strip("()") if assunto["assunto_rotulo"] in ("(Retificado)", "(Complementar)") else ""
    prazo = prazo if prazo is not None else get_prazo_justificativa_dias()
    data = oficio.data_criacao
    primeira = None
    saida_dt = get_primeira_saida_oficio(oficio)
    if saida_dt is not None:
        primeira = saida_dt.astimezone(timezone.get_current_timezone()).date()
    if primeira is None:
        motivo = "Sem data de saída no roteiro: por enquanto vale Autorização."
        justificativa = ""
        obrigatoria = False
        dias = None
    else:
        dias = (primeira - data).days
        if dias > 0:
            motivo = f"A viagem começa em {primeira:%d/%m/%Y}, depois da data do ofício ({data:%d/%m/%Y})."
        elif dias == 0:
            motivo = f"A viagem começa no mesmo dia do ofício ({data:%d/%m/%Y})."
        else:
            motivo = f"A viagem começou em {primeira:%d/%m/%Y}, antes da data do ofício ({data:%d/%m/%Y})."
        obrigatoria = dias <= prazo
        if dias < 0:
            justificativa = "Justificativa obrigatória: a saída é anterior ao ofício."
        elif obrigatoria:
            justificativa = (f"Justificativa obrigatória: {dias} dia{'s' if dias != 1 else ''} de antecedência, "
                             f"o prazo mínimo é de {prazo}.")
        else:
            justificativa = (f"Justificativa dispensada: {dias} dias de antecedência, "
                             f"acima do prazo mínimo de {prazo}.")
    rotulo = "Autorização" if autorizacao else "Convalidação"
    return {
        "rotulo": rotulo,
        "tom": "neutro" if autorizacao else "aguardando",
        "marcador": marcador,
        "motivo": motivo,
        "justificativa": justificativa,
        "justificativa_obrigatoria": obrigatoria,
        "dias_antecedencia": dias,
        "prazo_dias": prazo,
        "explicacao": " ".join(p for p in [motivo, justificativa] if p),
    }


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


def artefatos_pdf_por_oficio(oficios):
    """oficio_id → {(tipo, servidor_id): {"pk", "assinado"}} dos PDFs já gerados.

    Mesma regra de `viagens_termos.presenters.artefatos_pdf_por_termo`: o PDF
    apontado é o primeiro gerado (alvo de "Anexar assinado") e `assinado` vale
    se qualquer PDF daquele documento tiver versão assinada, lido do banco.
    """
    from django.db.models import Exists, OuterRef
    from documentos.models import DocumentoArtefato, DocumentoAssinaturaVersao
    ids = [o.pk for o in oficios]
    if not ids:
        return {}
    versao_viva = DocumentoAssinaturaVersao.objects.filter(artefato=OuterRef("pk"), revogada_em__isnull=True)
    consulta = (
        DocumentoArtefato.objects
        .filter(oficio_id__in=ids, termo_id__isnull=True, formato="pdf")
        .annotate(tem_versao=Exists(versao_viva))
        .order_by("criado_em")
        .values_list("oficio_id", "tipo", "servidor_id", "pk", "tem_versao", "arquivo_assinado")
    )
    mapa = {}
    for oficio_id, tipo, servidor_id, pk, tem_versao, arquivo_assinado in consulta:
        entrada = mapa.setdefault(oficio_id, {}).setdefault((tipo, servidor_id), {"pk": pk, "assinado": False})
        entrada["assinado"] = entrada["assinado"] or bool(tem_versao) or bool(arquivo_assinado)
    return mapa


def fatos_do_oficio(oficio):
    """Os dados da linha como itens com ícone; o que falta aparece apagado."""
    subtitulo = subtitulo_do_cartao(oficio)
    servidores = []
    for s in oficio.servidores.all():
        servidores.append(f"{s.nome} (motorista)" if oficio.motorista_id == s.pk else s.nome)
    transporte = transporte_do_cartao(oficio)
    viatura = " · ".join(p for p in [transporte["modelo"], transporte["placa"]] if p)
    diarias = diarias_do_cartao(oficio)
    valor = ""
    if diarias:
        valor = diarias["valor"] + (f" · {diarias['quantidade']}" if diarias["quantidade"] else "")
    # Data e destino moram no título; aqui só o aviso quando faltam.
    fatos = [] if subtitulo else [{"icone": "map-pin", "rotulo": "Viagem", "texto": "Sem roteiro", "ausente": True}]
    return fatos + [
        {"icone": "users", "rotulo": "Servidores", "texto": ", ".join(servidores) or "Sem servidores", "ausente": not servidores},
        {"icone": "truck", "rotulo": "Viatura", "texto": viatura or "Sem viatura", "ausente": not viatura},
        {"icone": "chart", "rotulo": "Diárias", "texto": valor or "Sem diárias", "ausente": not valor},
    ]


def documentos_do_oficio(oficio, artefatos_pdf):
    """O que o modal "Baixar documentos" e o de "Anexar assinado" oferecem:
    o ofício, a justificativa (quando há texto) e um termo por servidor."""
    import json

    from documentos.services.types import DocumentoTipo

    def estado(chave):
        artefato = artefatos_pdf.get(chave)
        if artefato is None:
            return {"estado": "Sem PDF", "assinado": False, "url_assinado": ""}
        return {"estado": "Assinado" if artefato["assinado"] else "PDF gerado", "assinado": artefato["assinado"],
                "url_assinado": reverse("viagens_oficios:assinatura_artefato", args=[artefato["pk"]])}

    documentos = [("oficio", "Ofício", f"Ofício {oficio.numero_formatado}", estado((DocumentoTipo.OFICIO.value, None)))]
    if justificativa_do_cartao(oficio)["preenchida"]:
        documentos.append(("justificativa", "Justificativa", "Justificativa de prazo",
                           estado((DocumentoTipo.JUSTIFICATIVA.value, None))))
    for s in oficio.servidores_termo_autorizacao.all():
        documentos.append((f"termo-{s.pk}", f"Termo · {s.nome}", _descricao_pessoa(s),
                           estado((DocumentoTipo.TERMO_AUTORIZACAO.value, s.pk))))
    return {
        "url_baixar": reverse("viagens_oficios:baixar", args=[oficio.pk]),
        "itens_baixar": json.dumps(
            [{"valor": v, "nome": n, "detalhe": d, "estado": e["estado"], "assinado": e["assinado"]} for v, n, d, e in documentos],
            ensure_ascii=False,
        ),
        "opcoes_anexar": json.dumps(
            [{"nome": n, "url": e["url_assinado"], "atual": e["assinado"]} for _, n, _, e in documentos],
            ensure_ascii=False,
        ),
        "algum_para_anexar": any(e["url_assinado"] for *_, e in documentos),
    }


def _destino_e_periodo(oficio):
    """"GUARAPUAVA/PR · 09/11 a 10/11/2026", na ordem do título das justificativas."""
    if oficio.roteiro_id is None:
        return ""
    periodo = periodo_curto(*periodo_roteiro(oficio.roteiro))
    return " · ".join(p for p in [destinos_resumidos(oficio.roteiro), periodo] if p and p != "—")


def linha_da_lista(oficio, *, artefatos_pdf=None, prazo=None):
    """Uma linha da lista de ofícios, no padrão das listas de termos e justificativas."""
    selo, tom = selo_do_cartao(oficio)
    justificativa = justificativa_do_cartao(oficio)
    return {
        "oficio": oficio,
        "titulo": " · ".join(p for p in [titulo_do_cartao(oficio), _destino_e_periodo(oficio)] if p),
        "selo": selo,
        "selo_tom": tom,
        "justificativa_preenchida": justificativa["preenchida"],
        "tipo": tipo_do_oficio(oficio, prazo=prazo),
        "fatos": fatos_do_oficio(oficio),
        "documentos": documentos_do_oficio(oficio, artefatos_pdf or {}),
        "url_editar": reverse("viagens_oficios:editar", args=[oficio.pk]),
    }
