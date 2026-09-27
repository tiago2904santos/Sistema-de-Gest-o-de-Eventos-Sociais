"""'Criar aqui': o que a pessoa pode abrir a partir de um dia do calendário (m135).

Cada atalho aponta para a tela nova de um módulo, e só entra na lista quem
pode usar aquele módulo — a mesma regra das fontes (`agenda.fontes`), mais
o perfil de operador no caso da viagem, porque criar viagem é POST de quem
edita. As datas escolhidas vão na query string (``?inicio=&fim=``) e as
telas novas as leem como valor inicial (`core.periodo_url`); a viagem é
criada por POST, então o atalho leva ``metodo="post"`` e o JS manda um
formulário com as duas datas.
"""

from __future__ import annotations

from django.urls import reverse


def atalhos_de_criacao(usuario) -> list[dict]:
    from accounts.modulos import usuario_tem_modulo
    from coffee_break.permissions import pode_acessar as pode_coffee
    from demandas_eventos.permissions import CODIGO_MODULO as MODULO_DEMANDAS
    from viagens_cadastros.permissions import pode_acessar as pode_viagens, pode_editar_cadastros

    atalhos = []
    if pode_viagens(usuario) and pode_editar_cadastros(usuario):
        atalhos.append({
            "slug": "viagem", "rotulo": "Nova viagem", "icone": "truck",
            "dica": "Abre a etapa 1 já com o período.",
            "url": reverse("viagens_viagem:criar"), "metodo": "post",
        })
    if usuario.is_authenticated:
        atalhos.append({
            "slug": "solicitacao", "rotulo": "Nova solicitação de evento", "icone": "calendar",
            "dica": "Evento social com as datas preenchidas.",
            "url": reverse("solicitacoes:nova"), "metodo": "get",
        })
    if pode_coffee(usuario):
        atalhos.append({
            "slug": "coffee", "rotulo": "Novo coffee break", "icone": "coffee",
            "dica": "Pedido ao fornecedor para o período.",
            "url": reverse("coffee_break:nova"), "metodo": "get",
        })
    if usuario_tem_modulo(usuario, MODULO_DEMANDAS):
        atalhos.append({
            "slug": "demanda", "rotulo": "Nova palestra ou evento", "icone": "users",
            "dica": "Demanda da ASCOM nas datas escolhidas.",
            "url": reverse("demandas_eventos:nova"), "metodo": "get",
        })
    return atalhos
