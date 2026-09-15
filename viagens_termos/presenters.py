"""Como o termo se apresenta na lista.

A linha da origem (`termos/index`): título "DESTINO/PR · 24/08/2026 a
30/08/2026" (ou só "PR" quando há apenas a unidade federativa), o selo
"Realizado" / "Sem período", e uma linha com "Ofício: N/AAAA", os servidores e
"AAA-1234 DUSTER", separados por " · ".
"""

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


def descricao_do_termo(termo):
    partes = []
    if termo.oficio_id:
        partes.append(f"Ofício: {termo.oficio.numero_formatado}")
    servidores = ", ".join(s.nome for s in termo.servidores_efetivos())
    if servidores:
        partes.append(servidores)
    viatura = termo.viatura_efetiva()
    if viatura is not None:
        partes.append(" ".join(p for p in [viatura.placa_formatada, viatura.modelo] if p))
    return " · ".join(partes)


def herdados_do_termo(termo):
    """O que o termo herda do ofício por estar em branco: a regra dos valores efetivos."""
    if not termo.oficio_id:
        return []
    herdados = []
    if not termo.destino_cidade_id and not termo.destino_estado_id and not termo.destinos_extras:
        herdados.append("destino")
    if not termo.data_evento_inicio:
        herdados.append("período")
    if termo.pk and not termo.servidores.exists():
        herdados.append("servidores")
    if not termo.viatura_id:
        herdados.append("viatura")
    return herdados


def documentos_do_termo(termo, artefatos_pdf):
    """Os documentos que o termo emite, cada um com as suas ações.

    `artefatos_pdf` mapeia servidor_id (ou None, para o genérico) ao último PDF
    gerado, para "Visualizar" o que já existe e "Anexar assinado".
    """
    def acoes(servidor_id):
        return {
            "url_pdf": reverse("viagens_termos:gerar", args=[termo.pk, servidor_id or 0, "pdf"]),
            "url_docx": reverse("viagens_termos:gerar", args=[termo.pk, servidor_id or 0, "docx"]),
            "url_previa": reverse("viagens_termos:preview_servidor", args=[termo.pk, servidor_id]) if servidor_id else reverse("viagens_termos:preview", args=[termo.pk]),
            "url_assinado": reverse("viagens_oficios:assinatura_artefato", args=[artefatos_pdf[servidor_id]]) if servidor_id in artefatos_pdf else "",
        }

    servidores = [
        {"servidor": s, "iniciais": iniciais(s.nome), "descricao": " · ".join(p for p in [str(s.cargo) if s.cargo_id else "", (s.unidade.sigla or s.unidade.nome) if s.unidade_id else ""] if p), **acoes(s.pk)}
        for s in termo.servidores_efetivos()
    ]
    return {
        "servidores": servidores,
        "generico": acoes(None),
        "viatura": {
            "viatura": termo.viatura_efetiva(),
            "url_pdf": reverse("viagens_termos:gerar_viatura", args=[termo.pk, "pdf"]),
            "url_docx": reverse("viagens_termos:gerar_viatura", args=[termo.pk, "docx"]),
        },
        "url_todos_pdf": reverse("viagens_termos:todos_pdf", args=[termo.pk]),
        "url_lote_pdf": reverse("viagens_termos:lote", args=[termo.pk, "pdf"]),
        "url_lote_docx": reverse("viagens_termos:lote", args=[termo.pk, "docx"]),
    }


def linha_da_lista(termo, *, artefatos_pdf=None):
    selo, tom = selo_do_termo(termo)
    return {
        "termo": termo,
        "titulo": titulo_do_termo(termo),
        "selo": selo,
        "selo_tom": tom,
        "descricao": descricao_do_termo(termo),
        "herdados": herdados_do_termo(termo),
        "documentos": documentos_do_termo(termo, artefatos_pdf or {}),
        "url_previa": reverse("viagens_termos:preview", args=[termo.pk]),
        "url_editar": reverse("viagens_termos:editar", args=[termo.pk]),
        "url_excluir": reverse("viagens_termos:acao", args=[termo.pk, "excluir"]),
        "url_cancelar": reverse("viagens_termos:acao", args=[termo.pk, "cancelar"]),
        "url_reativar": reverse("viagens_termos:acao", args=[termo.pk, "reativar"]),
    }


def artefatos_pdf_por_termo(termos):
    """(termo_id, servidor_id) → último PDF de termo gerado, numa consulta."""
    from documentos.models import DocumentoArtefato
    ids = [t.pk for t in termos]
    if not ids:
        return {}
    mapa = {}
    for termo_id, servidor_id, pk in DocumentoArtefato.objects.filter(termo_id__in=ids, formato="pdf", tipo=DocumentoTipo.TERMO_AUTORIZACAO.value).order_by("criado_em").values_list("termo_id", "servidor_id", "pk"):
        mapa.setdefault(termo_id, {})[servidor_id] = pk
    return mapa
