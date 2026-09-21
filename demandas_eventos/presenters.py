"""Como a palestra (ou evento) da ASCOM se apresenta na lista.

Composição das listas de Viagens: uma célula só, com o tipo de evento e o
município no título ao lado dos selos — o status e o quando do evento — e
as colunas da planilha que mais importam como fatos com ícone logo abaixo.
"""

from django.urls import reverse
from django.utils import timezone

from .models import StatusDemanda, TipoEventoPalestra

# Ícone de cada situação na trilha lateral.
ICONES_STATUS = {
    StatusDemanda.PENDENTE: "hourglass",
    StatusDemanda.EM_ANDAMENTO: "activity",
    StatusDemanda.AGUARDANDO_RETORNO: "clock",
    StatusDemanda.EVENTO_AGENDADO: "calendar",
    StatusDemanda.ATENDIDA: "check-circle",
    StatusDemanda.CANCELADA: "ban",
}

# Ícone de cada valor da coluna "Evento".
ICONES_EVENTO = {
    TipoEventoPalestra.PALESTRA: "users",
    TipoEventoPalestra.PCPR_NA_COMUNIDADE: "landmark",
    TipoEventoPalestra.EVENTO: "calendar",
}


def titulo_da_demanda(demanda):
    """O tipo de evento e onde ele acontece — o que identifica a linha."""
    tipo = demanda.get_evento_display()
    municipio = demanda.municipio_display
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


def _fato(icone, rotulo, texto, vazio):
    return {"icone": icone, "rotulo": rotulo, "texto": texto or vazio, "ausente": not texto}


def fatos_da_demanda(demanda):
    """As colunas da planilha que cabem na linha, como itens com ícone."""
    publico = demanda.quantidade_publico
    return [
        _fato("calendar", "Data do evento e hora", demanda.periodo_evento_display, "À definir"),
        _fato("checklist", "Tema", str(demanda.tema) if demanda.tema_id else "", "Sem tema"),
        _fato("user", "Solicitante", demanda.solicitante, "Sem solicitante"),
        _fato("users", "Servidor", demanda.servidor, "Sem servidor"),
        _fato("activity", "Quantidade de público", f"{publico} pessoas" if publico else "", "Público não informado"),
        _fato("clock", "Data da solicitação", f"Solicitada em {demanda.data_solicitacao:%d/%m/%Y}", ""),
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
        "cancelada": demanda.status == StatusDemanda.CANCELADA,
    }


def linha_do_cadastro(item, tipo):
    """A linha dos cadastros de apoio (palestrantes, temas, respostas).

    Os três cadastros moram na mesma tela e mudam só o que dizem de si.
    """
    if tipo == "respostas":
        titulo = item.tipo
        primeira = (item.mensagem or "").strip().splitlines()
        fatos = [_fato("mail", "Mensagem", primeira[0] if primeira else "", "Sem mensagem")]
    elif tipo == "palestrantes":
        titulo = item.nome
        municipio = str(item.municipio) if item.municipio_id else item.municipio_texto
        fatos = [
            _fato("landmark", "Divisão e lotação", " · ".join(x for x in (item.divisao, item.lotacao) if x), "Sem lotação"),
            _fato("map-pin", "Município", municipio, "Sem município"),
            _fato("mail", "Contato", item.contato, "Sem contato"),
            _fato("checklist", "Tema de abordagem", item.tema_abordagem, "Sem tema"),
        ]
    else:
        titulo = item.nome
        fatos = []
    return {
        "item": item,
        "titulo": titulo,
        "fatos": fatos,
        "url_editar": reverse("demandas_eventos:cadastro_editar", args=[tipo, item.pk]),
        "url_excluir": reverse("demandas_eventos:cadastro_excluir", args=[tipo, item.pk]),
        "cancelada": False,
    }
