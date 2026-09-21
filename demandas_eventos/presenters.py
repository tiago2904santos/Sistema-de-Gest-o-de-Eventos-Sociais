"""Como a demanda da ASCOM se apresenta na lista.

A listagem deixou de espalhar a demanda por sete colunas (solicitação, tipo
e tema, evento, município, solicitante, status, ações) em favor da
composição das listas de Viagens: uma célula só, com o tipo e o município no
título ao lado dos selos — a situação e o quando do evento — e os fatos com
ícone logo abaixo.
"""

from django.urls import reverse
from django.utils import timezone

from .models import StatusDemanda

# Ícone de cada situação na trilha lateral.
ICONES_STATUS = {
    StatusDemanda.PENDENTE: "hourglass",
    StatusDemanda.AGUARDANDO_RETORNO: "clock",
    StatusDemanda.EM_ANDAMENTO: "activity",
    StatusDemanda.EVENTO_AGENDADO: "calendar",
    StatusDemanda.ATENDIDA: "check-circle",
    StatusDemanda.NAO_ATENDER: "x",
    StatusDemanda.CANCELADA: "ban",
}


def titulo_da_demanda(demanda):
    """O tipo de evento e onde ele acontece — o que identifica a demanda."""
    tipo = str(demanda.tipo_evento) if demanda.tipo_evento_id else "Demanda"
    municipio = (
        str(demanda.municipio) if demanda.municipio_id else demanda.municipio_texto
    )
    return f"{tipo} · {municipio.upper()}" if municipio else tipo


def selo_temporal(demanda, hoje=None):
    """Quando o evento acontece — a mesma régua dos termos e dos roteiros."""
    inicio = demanda.data_inicio_evento
    if not inicio:
        return "", ""
    fim = demanda.data_fim_evento or inicio
    hoje = hoje or timezone.localdate()
    if fim < hoje:
        return "Realizado", "atendido"
    if inicio <= hoje:
        return "Acontecendo", "em_andamento"
    return "Previsto", "aguardando"


def fatos_da_demanda(demanda):
    """Os dados que estavam nas colunas, agora como itens com ícone."""
    periodo = demanda.periodo_evento_display
    tema = str(demanda.tema) if demanda.tema_id else ""
    if tema and demanda.subtema_id:
        tema = f"{tema} · {demanda.subtema.nome}"
    responsavel = (
        str(demanda.responsavel_atendimento)
        if demanda.responsavel_atendimento_id
        else ""
    )
    return [
        {
            "icone": "calendar",
            "rotulo": "Período do evento",
            "texto": periodo or "Sem período",
            "ausente": not periodo,
        },
        {
            "icone": "checklist",
            "rotulo": "Tema",
            "texto": tema or "Sem tema",
            "ausente": not tema,
        },
        {
            "icone": "user",
            "rotulo": "Solicitante",
            "texto": demanda.solicitante or "Sem solicitante",
            "ausente": not demanda.solicitante,
        },
        {
            "icone": "users",
            "rotulo": "Responsável",
            "texto": responsavel or "Sem responsável",
            "ausente": not responsavel,
        },
        {
            "icone": "clock",
            "rotulo": "Solicitada em",
            "texto": f"Solicitada em {demanda.data_solicitacao:%d/%m/%Y}",
            "ausente": False,
        },
    ]


def linha_da_lista(demanda, hoje=None):
    """Tudo o que a linha da lista precisa, montado fora do template."""
    quando, quando_tom = selo_temporal(demanda, hoje)
    return {
        "demanda": demanda,
        "titulo": titulo_da_demanda(demanda),
        "selo": demanda.get_status_display(),
        "selo_tom": demanda.status.lower(),
        "quando": quando,
        "quando_tom": quando_tom,
        "fatos": fatos_da_demanda(demanda),
        "url_editar": reverse("demandas_eventos:editar", args=[demanda.pk]),
        "cancelada": demanda.status
        in (StatusDemanda.CANCELADA, StatusDemanda.NAO_ATENDER),
    }


def linha_do_cadastro(item, tipo):
    """A linha dos cadastros de apoio das demandas (palestrante, tema…).

    Os quatro cadastros moram na mesma tela e mudam só o que dizem de si.
    """
    if tipo == "respostas":
        titulo = item.tipo
        fatos = [
            {"icone": "mail", "rotulo": "Resposta padrão", "texto": "Texto pronto de resposta", "ausente": False},
        ]
    elif tipo == "palestrantes":
        titulo = item.nome
        fatos = [
            {"icone": "landmark", "rotulo": "Lotação", "texto": item.lotacao or "Sem lotação", "ausente": not item.lotacao},
        ]
    elif tipo == "subtemas":
        titulo = item.nome
        fatos = [
            {"icone": "document", "rotulo": "Tema", "texto": str(item.tema), "ausente": False},
            {"icone": "checklist", "rotulo": "Escopo", "texto": item.escopo or "Sem escopo", "ausente": not item.escopo},
        ]
    else:
        titulo = item.nome
        fatos = [
            {"icone": "document", "rotulo": "Tema", "texto": "Tema das demandas", "ausente": False},
        ]
    return {
        "item": item,
        "titulo": titulo,
        "selo": "Ativo" if item.ativo else "Inativo",
        "selo_tom": "ativo" if item.ativo else "inativo",
        "fatos": fatos,
        "url_editar": reverse("demandas_eventos:cadastro_editar", args=[tipo, item.pk]),
        "cancelada": not item.ativo,
    }
