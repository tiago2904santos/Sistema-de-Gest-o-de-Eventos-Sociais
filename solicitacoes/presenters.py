"""Como a solicitação se apresenta na lista.

A listagem deixou de espalhar a solicitação por sete colunas (nº, status,
tipo, município, período, solicitante, data da solicitação) em favor da
composição das listas de Viagens: uma célula só, com o título ao lado dos
dois selos — a situação do registro e o quando do evento — e os fatos com
ícone logo abaixo.

Cada vazio tem o seu nome ("Sem período", "Local não informado") em tom
apagado: a linha fica sempre com a mesma altura e o que falta é informação,
não buraco.
"""

from django.urls import reverse
from django.utils import timezone

from .models import StatusSolicitacao


def periodo_do_evento(solicitacao):
    """"01/02/2026 a 03/02/2026", ou só a data quando o evento é de um dia."""
    inicio, fim = solicitacao.data_inicio_evento, solicitacao.data_fim_evento
    if not inicio:
        return ""
    if not fim or fim == inicio:
        return f"{inicio:%d/%m/%Y}"
    return f"{inicio:%d/%m/%Y} a {fim:%d/%m/%Y}"


def titulo_da_solicitacao(solicitacao):
    """O que identifica a solicitação numa linha: o tipo e onde acontece."""
    tipo = str(solicitacao.tipo_evento) if solicitacao.tipo_evento_id else "Evento"
    municipio = str(solicitacao.municipio) if solicitacao.municipio_id else ""
    return f"{tipo} · {municipio.upper()}" if municipio else tipo


def selo_da_solicitacao(solicitacao):
    """O status do fluxo, com o tom que o V3.2 já dá a cada um deles."""
    return solicitacao.get_status_display(), solicitacao.status.lower()


def selo_temporal(solicitacao):
    """Quando o evento acontece — a mesma régua dos termos e dos roteiros."""
    inicio = solicitacao.data_inicio_evento
    if not inicio:
        return "", ""
    fim = solicitacao.data_fim_evento or inicio
    hoje = timezone.localdate()
    if fim < hoje:
        return "Realizado", "atendido"
    if inicio <= hoje:
        return "Acontecendo", "em_andamento"
    return "Previsto", "aguardando"


def fatos_da_solicitacao(solicitacao):
    """Os dados que estavam nas colunas, agora como itens com ícone."""
    periodo = periodo_do_evento(solicitacao)
    solicitante = solicitacao.solicitante_nome
    if solicitante and solicitacao.solicitante_cargo_unidade:
        solicitante = f"{solicitante} — {solicitacao.solicitante_cargo_unidade}"
    fatos = [
        {
            "icone": "calendar",
            "rotulo": "Período do evento",
            "texto": periodo or "Sem período",
            "ausente": not periodo,
        },
        {
            "icone": "map-pin",
            "rotulo": "Local",
            "texto": solicitacao.local_evento or "Local não informado",
            "ausente": not solicitacao.local_evento,
        },
        {
            "icone": "user",
            "rotulo": "Solicitante",
            "texto": solicitante or "Sem solicitante",
            "ausente": not solicitante,
        },
    ]
    # A unidade móvel muda a operação do evento: quando há, é fato de lista.
    if solicitacao.unidade_movel:
        movel = (
            str(solicitacao.unidade_movel_designada)
            if solicitacao.unidade_movel_designada_id
            else "Unidade móvel a designar"
        )
        fatos.append(
            {
                "icone": "truck",
                "rotulo": "Unidade móvel",
                "texto": movel,
                "ausente": not solicitacao.unidade_movel_designada_id,
            }
        )
    fatos.append(
        {
            "icone": "clock",
            "rotulo": "Solicitada em",
            "texto": f"Solicitada em {solicitacao.data_solicitacao:%d/%m/%Y}",
            "ausente": False,
        }
    )
    return fatos


def acao_principal(solicitacao, acoes):
    """O próximo passo de quem abre a linha, no rótulo que a origem usava."""
    url = reverse("solicitacoes:editar", args=[solicitacao.pk])
    if acoes.get("despachar"):
        return {
            "rotulo": "Despachar",
            "ajuda": "Decidir o atendimento na Direção-Geral",
            "icone": "gavel",
            "url": f"{url}#despacho-dg",
        }
    if acoes.get("concluir"):
        return {
            "rotulo": "Confirmar atendimento",
            "ajuda": "Registrar o encerramento do evento",
            "icone": "check",
            "url": f"{url}#encerramento",
        }
    if acoes.get("enviar"):
        return {
            "rotulo": "Continuar",
            "ajuda": "Completar os dados e enviar para despacho",
            "icone": "pencil",
            "url": url,
        }
    return None


def linha_da_lista(solicitacao, acoes):
    """Tudo o que a linha da lista precisa, montado fora do template."""
    selo, selo_tom = selo_da_solicitacao(solicitacao)
    quando, quando_tom = selo_temporal(solicitacao)
    return {
        "solicitacao": solicitacao,
        "acoes": acoes,
        "titulo": titulo_da_solicitacao(solicitacao),
        "selo": selo,
        "selo_tom": selo_tom,
        "quando": quando,
        "quando_tom": quando_tom,
        "fatos": fatos_da_solicitacao(solicitacao),
        "principal": acao_principal(solicitacao, acoes),
        "url_editar": reverse("solicitacoes:editar", args=[solicitacao.pk]),
        "url_excluir": reverse("solicitacoes:excluir", args=[solicitacao.pk]),
        "cancelada": solicitacao.status == StatusSolicitacao.CANCELADA,
    }
