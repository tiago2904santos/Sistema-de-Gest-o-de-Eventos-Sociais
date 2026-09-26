"""Como o pedido da imprensa se apresenta na lista.

A listagem deixou de espalhar o atendimento por sete colunas (data,
situação, jornalista, veículo, pedido, responsável, deadline) em favor da
composição das listas de Viagens: uma célula só, com o jornalista e o
veículo no título, ao lado dos selos — a situação e o deadline — e os fatos
com ícone logo abaixo, o pedido entre eles.
"""

from django.urls import reverse
from django.utils import timezone

from .models import SituacaoAtendimento


def selo_do_deadline(atendimento, hoje=None):
    """O deadline como selo temporal: vencido, hoje, ou a data que vem."""
    if not atendimento.deadline or atendimento.atendido:
        return "", ""
    hoje = hoje or timezone.localdate()
    if atendimento.deadline < hoje:
        return f"Deadline vencido em {atendimento.deadline:%d/%m}", "perigo"
    if atendimento.deadline == hoje:
        return "Deadline hoje", "aguardando"
    return f"Deadline {atendimento.deadline:%d/%m/%Y}", "neutro"


def titulo_do_atendimento(atendimento):
    """Quem pediu e por qual veículo — o que identifica o atendimento."""
    veiculo = str(atendimento.veiculo) if atendimento.veiculo_id else ""
    return f"{atendimento.jornalista} · {veiculo.upper()}" if veiculo else atendimento.jornalista


def fatos_do_atendimento(atendimento):
    """Os dados que estavam nas colunas, agora como itens com ícone."""
    entrada = f"{atendimento.data:%d/%m/%Y}"
    if atendimento.horario:
        entrada += f" às {atendimento.horario:%H:%M}"
    responsavel = str(atendimento.responsavel) if atendimento.responsavel_id else ""
    fatos = [
        {"icone": "calendar", "rotulo": "Entrada do pedido", "texto": entrada, "ausente": False},
        {
            "icone": "user",
            "rotulo": "Responsável",
            "texto": responsavel or "Sem responsável",
            "ausente": not responsavel,
        },
    ]
    if atendimento.contato:
        fatos.append(
            {"icone": "mail", "rotulo": "Contato", "texto": atendimento.contato, "ausente": False}
        )
    # O pedido é o último fato e toma o resto da linha, cortando no fim.
    fatos.append(
        {
            "icone": "document",
            "rotulo": "Pedido",
            "texto": atendimento.pedido_resumo or "Sem descrição",
            "ausente": not atendimento.pedido_resumo,
        }
    )
    return fatos


def linha_da_lista(atendimento, hoje=None):
    """Tudo o que a linha da lista precisa, montado fora do template."""
    quando, quando_tom = selo_do_deadline(atendimento, hoje)
    return {
        "atendimento": atendimento,
        "titulo": titulo_do_atendimento(atendimento),
        "selo": atendimento.get_situacao_display(),
        "selo_tom": atendimento.situacao_css,
        "quando": quando,
        "quando_tom": quando_tom,
        "fatos": fatos_do_atendimento(atendimento),
        "url_editar": reverse("atendimento_imprensa:editar", args=[atendimento.pk]),
        "url_andamento": reverse("atendimento_imprensa:andamento", args=[atendimento.pk]),
        "cancelada": atendimento.situacao == SituacaoAtendimento.NAO_RESPONDER,
    }
