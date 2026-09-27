"""A situação real da viagem na Agenda — a mesma da lista de Viagens (m131).

``Viagem.status`` só muda em três momentos (criar, cancelar, reativar), então
lê-lo faz toda viagem parecer "Rascunho" ou "Em preparação" para sempre. A
lista de Viagens calcula a situação na hora (Cancelado, Finalizado, Pronto,
Rascunho) e o "quando" (faltam N dias, Em andamento, Realizado) a partir dos
documentos e das prestações. A Agenda usa exatamente as mesmas funções, com a
mesma anotação e o mesmo prefetch, para as duas telas nunca discordarem.
"""

from __future__ import annotations


def consulta_de_viagens(queryset):
    """A consulta anotada e com o prefetch que ``selo_situacao``/``selo_quando`` leem."""
    from viagens_viagem.abas import anotar_situacao

    return anotar_situacao(
        queryset.prefetch_related(
            "oficios__roteiro", "planos_trabalho", "ordens_servico", "documentos_solicitacao", "roteiros",
        )
    )


def situacao_da_viagem(viagem) -> tuple[str, str, str]:
    """(texto, slug, tom) da viagem, como a lista mostra.

    O texto junta o selo com o "quando" quando este diz algo de fato ("Pronto
    · Em andamento", "Rascunho · Realizado"); "faltam N dias" fica de fora do
    filtro, porque mudaria todo dia. O slug é o do selo (finalizado, pronto,
    rascunho, cancelado): é por ele que a tela agrupa o filtro "Situação".
    """
    from viagens_viagem.presenters import selo_quando, selo_situacao

    selo, tom = selo_situacao(viagem)
    quando = selo_quando(viagem)
    texto = selo
    if quando and quando[0] in ("Em andamento", "Realizado"):
        texto = f"{selo} · {quando[0]}"
    return texto, selo.lower(), tom
