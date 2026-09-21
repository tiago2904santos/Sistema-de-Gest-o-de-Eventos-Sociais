"""Como a pauta se apresenta na lista.

A listagem deixou de espalhar a pauta por seis colunas (data, status,
título, unidade, jornalista, publicada em) em favor da composição das listas
de Viagens: uma célula só, com o título ao lado dos selos — a situação da
pauta e, quando já saiu, o quando da publicação — e os fatos com ícone logo
abaixo.

Cada vazio tem o seu nome ("Sem unidade", "Ainda não publicada") em tom
apagado: a linha fica sempre com a mesma altura.
"""

from django.urls import reverse

from .models import StatusPublicacao


def quando_publicada(publicacao):
    """"Publicada em 03/02/2026 às 14h30", ou vazio enquanto não sai."""
    if not publicacao.data_publicacao:
        return ""
    texto = f"Publicada em {publicacao.data_publicacao:%d/%m/%Y}"
    if publicacao.horario_publicacao:
        texto += f" às {publicacao.horario_publicacao:%H:%M}"
    return texto


def fatos_da_publicacao(publicacao):
    """Os dados que estavam nas colunas, agora como itens com ícone."""
    entrada = f"{publicacao.data:%d/%m/%Y}"
    if publicacao.inicio_pauta:
        entrada += f" às {publicacao.inicio_pauta:%H:%M}"
    unidade = str(publicacao.unidade) if publicacao.unidade_id else ""
    fatos = [
        {"icone": "calendar", "rotulo": "Entrada da pauta", "texto": entrada, "ausente": False},
        {
            "icone": "landmark",
            "rotulo": "Unidade",
            "texto": unidade or "Sem unidade",
            "ausente": not unidade,
        },
        {
            "icone": "user",
            "rotulo": "Jornalista",
            "texto": str(publicacao.jornalista) if publicacao.jornalista_id else "Sem jornalista",
            "ausente": not publicacao.jornalista_id,
        },
    ]
    if publicacao.fonte:
        fatos.append(
            {"icone": "info", "rotulo": "Fonte", "texto": publicacao.fonte, "ausente": False}
        )
    if publicacao.andamento and not publicacao.encerrada:
        fatos.append(
            {"icone": "activity", "rotulo": "Andamento", "texto": publicacao.andamento, "ausente": False}
        )
    return fatos


def linha_da_lista(publicacao):
    """Tudo o que a linha da lista precisa, montado fora do template."""
    quando = quando_publicada(publicacao)
    return {
        "publicacao": publicacao,
        "titulo": publicacao.titulo,
        "selo": publicacao.get_status_display(),
        "selo_tom": publicacao.status_css,
        "quando": quando,
        # O selo do quando só existe quando a pauta saiu: verde de concluído.
        "quando_tom": "publicada",
        "fatos": fatos_da_publicacao(publicacao),
        "url_editar": reverse("publicacoes:editar", args=[publicacao.pk]),
        "cancelada": publicacao.status == StatusPublicacao.CANCELADA,
    }
