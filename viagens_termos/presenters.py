"""Como o termo se apresenta na lista.

O cartão da lista abandonou a linha corrida da origem (`termos/index`, que
juntava "Ofício: N/AAAA · servidores · AAA-1234 DUSTER" numa frase só) em
favor de fatos separados, cada um com o seu ícone, e do período fora do
título. O selo temporal ("Realizado", "Sem período", ...) continua colado ao
destino; ao lado dele entrou o andamento dos documentos ("3 de 5 assinados"),
que a origem não mostrava.
"""

import json

from django.urls import reverse
from django.utils import timezone

from documentos.services.types import DocumentoTipo
from viagens_oficios.presenters import iniciais


def destino_do_titulo(termo):
    destino = termo.destino_efetivo()
    return destino.upper() if destino else "—"


def periodo_do_titulo(termo):
    inicio, fim = termo.periodo_efetivo()
    if not inicio:
        return ""
    if not fim or fim == inicio:
        return f"{inicio:%d/%m/%Y}"
    return f"{inicio:%d/%m/%Y} a {fim:%d/%m/%Y}"


def titulo_do_termo(termo):
    """Destino e período numa linha só — o cabeçalho da prévia, não o da lista."""
    periodo = periodo_do_titulo(termo)
    destino = destino_do_titulo(termo)
    return f"{destino} · {periodo}" if periodo else destino


def selo_do_termo(termo):
    """"Realizado" e "Sem período" são da origem; os demais completam a régua."""
    if termo.cancelado:
        return "Cancelado", "cancelada"
    inicio, fim = termo.periodo_efetivo()
    if not inicio:
        return "Sem período", "neutro"
    hoje = timezone.localdate()
    fim = fim or inicio
    if fim < hoje:
        return "Realizado", "atendido"
    if inicio <= hoje:
        return "Em andamento", "em_andamento"
    return "Previsto", "aguardando"


def viatura_do_termo(termo):
    viatura = termo.viatura_efetiva()
    if viatura is None:
        return ""
    return " ".join(p for p in [viatura.placa_formatada, viatura.modelo] if p)


def fatos_do_termo(termo):
    """Os dados do cartão como itens separados, um ícone para cada.

    Substitui a linha corrida da origem. O que falta aparece assim mesmo, em
    tom apagado (`ausente`), para o cartão ter sempre a mesma altura e para o
    vazio ser uma informação, não um buraco.
    """
    periodo = periodo_do_titulo(termo)
    servidores = ", ".join(s.nome for s in termo.servidores_efetivos())
    viatura = viatura_do_termo(termo)
    fatos = [{"icone": "calendar", "rotulo": "Período", "texto": periodo or "Sem período", "ausente": not periodo}]
    # Sem ofício, não há o que dizer: o item só aparece quando há vínculo.
    if termo.oficio_id:
        fatos.append({"icone": "document", "rotulo": "Ofício", "texto": f"Ofício {termo.oficio.numero_formatado}", "ausente": False})
    fatos += [
        {"icone": "users", "rotulo": "Servidores", "texto": servidores or "Sem servidores", "ausente": not servidores},
        {"icone": "truck", "rotulo": "Viatura", "texto": viatura or "Sem viatura", "ausente": not viatura},
    ]
    return fatos


def herdados_do_termo(termo):
    """O que o termo herda do ofício por estar em branco: a regra dos valores efetivos."""
    return [h["campo"] for h in heranca_do_termo(termo)]


def heranca_do_termo(termo):
    """O mesmo que `herdados_do_termo`, com o valor que vem do ofício em cada campo.

    O formulário mostra o valor herdado junto do nome do campo: dizer só
    "herda o destino" obriga a abrir o ofício para saber qual é.
    """
    if not termo.oficio_id:
        return []
    heranca = []
    if not termo.destino_cidade_id and not termo.destino_estado_id and not termo.destinos_extras:
        heranca.append({"campo": "destino", "valor": termo.destino_efetivo()})
    if not termo.data_evento_inicio:
        heranca.append({"campo": "período", "valor": periodo_do_titulo(termo)})
    if termo.pk and not termo.servidores.exists():
        heranca.append({"campo": "servidores", "valor": ", ".join(s.nome for s in termo.servidores_efetivos())})
    if not termo.viatura_id:
        heranca.append({"campo": "viatura", "valor": viatura_do_termo(termo)})
    return heranca


def documentos_do_termo(termo, artefatos_pdf):
    """Os documentos que o termo emite, cada um com as suas ações e o seu estado.

    `artefatos_pdf` mapeia servidor_id (ou None, para o genérico) ao PDF já
    gerado — `{"pk": ..., "assinado": bool}` —, para "Visualizar" o que já
    existe, "Anexar assinado" e marcar quem já saiu e quem já voltou assinado.
    """
    def acoes(servidor_id):
        artefato = artefatos_pdf.get(servidor_id)
        return {
            "url_pdf": reverse("viagens_termos:gerar", args=[termo.pk, servidor_id or 0, "pdf"]),
            "url_docx": reverse("viagens_termos:gerar", args=[termo.pk, servidor_id or 0, "docx"]),
            "url_previa": reverse("viagens_termos:preview_servidor", args=[termo.pk, servidor_id]) if servidor_id else reverse("viagens_termos:preview", args=[termo.pk]),
            "url_assinado": reverse("viagens_oficios:assinatura_artefato", args=[artefato["pk"]]) if artefato else "",
            "tem_pdf": artefato is not None,
            "assinado": bool(artefato and artefato["assinado"]),
            **estado_do_documento(artefato),
        }

    servidores = [
        {"servidor": s, "iniciais": iniciais(s.nome), "descricao": " · ".join(p for p in [str(s.cargo) if s.cargo_id else "", (s.unidade.sigla or s.unidade.nome) if s.unidade_id else ""] if p), **acoes(s.pk)}
        for s in termo.servidores_efetivos()
    ]
    generico = acoes(None)
    # O modal "Baixar documentos" lista o termo vazio e um item por servidor.
    itens_baixar = [{"valor": "0", "nome": "Termo vazio", "detalhe": "Só destino e período, para preencher à mão", "estado": generico["estado"]}]
    itens_baixar += [{"valor": str(s["servidor"].pk), "nome": s["servidor"].nome, "detalhe": s["descricao"], "estado": s["estado"]} for s in servidores]
    return {
        "servidores": servidores,
        "generico": generico,
        "url_baixar": reverse("viagens_termos:baixar", args=[termo.pk]),
        "itens_baixar": json.dumps(itens_baixar, ensure_ascii=False),
        # O modal de anexar escolhe entre estes; sem PDF gerado, a opção vem apagada.
        "opcoes_anexar": json.dumps(
            [{"nome": "Termo vazio", "url": generico["url_assinado"], "atual": generico["assinado"]}]
            + [{"nome": s["servidor"].nome, "url": s["url_assinado"], "atual": s["assinado"]} for s in servidores],
            ensure_ascii=False,
        ),
        "algum_para_anexar": bool(generico["url_assinado"]) or any(s["url_assinado"] for s in servidores),
        "viatura": {
            "viatura": termo.viatura_efetiva(),
            "url_pdf": reverse("viagens_termos:gerar_viatura", args=[termo.pk, "pdf"]),
            "url_docx": reverse("viagens_termos:gerar_viatura", args=[termo.pk, "docx"]),
        },
        "url_todos_pdf": reverse("viagens_termos:todos_pdf", args=[termo.pk]),
        "url_lote_pdf": reverse("viagens_termos:lote", args=[termo.pk, "pdf"]),
        "url_lote_docx": reverse("viagens_termos:lote", args=[termo.pk, "docx"]),
    }


def estado_do_documento(artefato):
    """O selo de um documento só: onde ele está entre "nem saiu" e "voltou assinado"."""
    if artefato is None:
        return {"estado": "Sem PDF", "estado_tom": "neutro"}
    if artefato["assinado"]:
        return {"estado": "Assinado", "estado_tom": "atendido"}
    return {"estado": "PDF gerado", "estado_tom": "aguardando"}


def situacao_dos_documentos(termo, artefatos_pdf):
    """Quanto do termo já saiu em PDF e quanto já voltou assinado.

    Conta os servidores efetivos; num termo sem servidor o alvo é o termo
    genérico, que é o único documento que ele emite.
    """
    alvos = [s.pk for s in termo.servidores_efetivos()] or [None]
    gerados = [artefatos_pdf[a] for a in alvos if a in artefatos_pdf]
    assinados = [a for a in gerados if a["assinado"]]
    total, gerados, assinados = len(alvos), len(gerados), len(assinados)
    if not gerados:
        rotulo, tom = "Sem PDF gerado", "neutro"
    elif assinados == total:
        rotulo, tom = ("Assinado" if total == 1 else "Todos assinados"), "atendido"
    elif assinados:
        rotulo, tom = f"{assinados} de {total} assinados", "em_andamento"
    elif gerados == total:
        rotulo, tom = ("PDF gerado" if total == 1 else "Todos em PDF"), "aguardando"
    else:
        rotulo, tom = f"{gerados} de {total} em PDF", "aguardando"
    return {"total": total, "gerados": gerados, "assinados": assinados, "rotulo": rotulo, "tom": tom}


def linha_da_lista(termo, *, artefatos_pdf=None):
    selo, tom = selo_do_termo(termo)
    artefatos_pdf = artefatos_pdf or {}
    return {
        "termo": termo,
        "titulo": destino_do_titulo(termo),
        "selo": selo,
        "selo_tom": tom,
        "fatos": fatos_do_termo(termo),
        "situacao_documentos": situacao_dos_documentos(termo, artefatos_pdf),
        "herdados": herdados_do_termo(termo),
        "documentos": documentos_do_termo(termo, artefatos_pdf),
        "url_previa": reverse("viagens_termos:preview", args=[termo.pk]),
        "url_editar": reverse("viagens_termos:editar", args=[termo.pk]),
        "url_excluir": reverse("viagens_termos:acao", args=[termo.pk, "excluir"]),
        "url_cancelar": reverse("viagens_termos:acao", args=[termo.pk, "cancelar"]),
        "url_reativar": reverse("viagens_termos:acao", args=[termo.pk, "reativar"]),
    }


def artefatos_pdf_por_termo(termos):
    """(termo_id, servidor_id) → PDF de termo gerado e se já há versão assinada.

    O PDF apontado continua sendo o primeiro da ordem de criação, como antes —
    é o alvo de "Anexar assinado". Já `assinado` olha **todos** os PDFs
    daquele servidor: basta um assinado para o termo dele estar assinado.

    A assinatura sai do banco (`arquivo_assinado` preenchido ou versão viva em
    `versoes_assinadas`), não de `DocumentoArtefato.esta_assinado`: aquela
    propriedade bate no storage a cada artefato, o que numa lista paginada
    seria uma ida ao disco por linha.
    """
    from django.db.models import Exists, OuterRef
    from documentos.models import DocumentoArtefato, DocumentoAssinaturaVersao
    ids = [t.pk for t in termos]
    if not ids:
        return {}
    versao_viva = DocumentoAssinaturaVersao.objects.filter(artefato=OuterRef("pk"), revogada_em__isnull=True)
    consulta = (
        DocumentoArtefato.objects
        .filter(termo_id__in=ids, formato="pdf", tipo=DocumentoTipo.TERMO_AUTORIZACAO.value)
        .annotate(tem_versao=Exists(versao_viva))
        .order_by("criado_em")
        .values_list("termo_id", "servidor_id", "pk", "tem_versao", "arquivo_assinado")
    )
    mapa = {}
    for termo_id, servidor_id, pk, tem_versao, arquivo_assinado in consulta:
        por_servidor = mapa.setdefault(termo_id, {})
        entrada = por_servidor.setdefault(servidor_id, {"pk": pk, "assinado": False})
        entrada["assinado"] = entrada["assinado"] or bool(tem_versao) or bool(arquivo_assinado)
    return mapa
