"""Sugestões da tela da solicitação — mostradas, nunca aplicadas sozinhas.

- `sugestao_do_tipo`: serviços, equipes (com a quantidade) e solicitante que
  costumam acompanhar um tipo de evento. Vem do modelo do tipo (Cadastros ›
  Tipos de evento › Modelo da solicitação); o que o modelo não diz sai das
  últimas solicitações do mesmo tipo.
"""

from collections import Counter

from cadastros.models import TipoEvento

from .models import SolicitacaoEvento, StatusSolicitacao

# Quantas solicitações recentes do tipo servem de base, e em que fração delas
# um serviço ou equipe precisa aparecer para ser sugerido.
HISTORICO_BASE = 20
FRACAO_MINIMA = 0.5


def _do_historico(tipo):
    """Serviços e equipes mais usados nas últimas solicitações do tipo."""
    recentes = list(
        SolicitacaoEvento.objects.filter(tipo_evento=tipo)
        .exclude(status=StatusSolicitacao.RASCUNHO)
        .order_by("-data_solicitacao", "-pk")
        .prefetch_related("itens_servico__servico", "itens_equipe__equipe")[:HISTORICO_BASE]
    )
    if not recentes:
        return [], [], 0
    minimo = max(1, round(len(recentes) * FRACAO_MINIMA))
    servicos, nomes_servico = Counter(), {}
    equipes, nomes_equipe, quantidades = Counter(), {}, {}
    for solicitacao in recentes:
        for item in solicitacao.itens_servico.all():
            if item.servico.ativo:
                servicos[item.servico_id] += 1
                nomes_servico[item.servico_id] = item.servico.nome
        for item in solicitacao.itens_equipe.all():
            if item.equipe.ativo:
                equipes[item.equipe_id] += 1
                nomes_equipe[item.equipe_id] = item.equipe.nome
                if item.quantidade_servidores:
                    quantidades.setdefault(item.equipe_id, Counter())[item.quantidade_servidores] += 1
    lista_servicos = [
        {"id": pk, "nome": nomes_servico[pk]}
        for pk, vezes in servicos.most_common()
        if vezes >= minimo
    ]
    lista_equipes = [
        {
            "id": pk,
            "nome": nomes_equipe[pk],
            # A quantidade mais usada; no empate, a maior.
            "quantidade": max(
                quantidades[pk].items(), key=lambda par: (par[1], par[0])
            )[0]
            if pk in quantidades
            else None,
        }
        for pk, vezes in equipes.most_common()
        if vezes >= minimo
    ]
    return lista_servicos, lista_equipes, len(recentes)


def sugestao_do_tipo(tipo):
    """O que sugerir ao escolher o tipo de evento (dict pronto para JSON)."""
    if not isinstance(tipo, TipoEvento):
        tipo = TipoEvento.objects.filter(pk=tipo).first()
    vazio = {"tipo": "", "origem": [], "servicos": [], "equipes": [], "solicitante": None}
    if tipo is None:
        return vazio

    servicos = [
        {"id": s.pk, "nome": s.nome} for s in tipo.servicos_sugeridos.filter(ativo=True)
    ]
    equipes = [
        {"id": item.equipe_id, "nome": item.equipe.nome, "quantidade": item.quantidade}
        for item in tipo.equipes_sugeridas.select_related("equipe").filter(equipe__ativo=True)
    ]
    origem = []
    if servicos or equipes:
        origem.append("o modelo do tipo")
    else:
        servicos, equipes, base = _do_historico(tipo)
        if servicos or equipes:
            origem.append(
                f"as últimas {base} solicitações deste tipo" if base > 1
                else "a última solicitação deste tipo"
            )

    solicitante = None
    if tipo.solicitante_padrao or tipo.cargo_padrao or tipo.orgao_padrao_id:
        orgao = tipo.orgao_padrao if tipo.orgao_padrao_id and tipo.orgao_padrao.ativo else None
        solicitante = {
            "nome": tipo.solicitante_padrao,
            "cargo": tipo.cargo_padrao,
            "orgao": {"id": orgao.pk, "nome": orgao.nome} if orgao else None,
        }
        if "o modelo do tipo" not in origem:
            origem.insert(0, "o modelo do tipo")

    return {
        "tipo": tipo.nome,
        "origem": origem,
        "servicos": servicos,
        "equipes": equipes,
        "solicitante": solicitante,
    }


# ---------------------------------------------------------------------------
# Solicitantes que já pediram antes (m009)
# ---------------------------------------------------------------------------

LIMITE_SOLICITANTES = 8
# Quantas linhas recentes o agrupamento lê: o bastante para achar os nomes
# sem varrer o histórico inteiro a cada tecla.
LINHAS_LIDAS = 300


def ultimos_por_nome(queryset, campo_nome, termo, campos, ordem, limite=LIMITE_SOLICITANTES):
    """Os nomes que contêm `termo`, cada um com os dados do pedido mais recente.

    `campos` mapeia o nome do campo no formulário -> caminho no banco; devolve
    [{"nome", "campos": {campo: valor}, "pedidos": n}], dos mais recentes aos
    mais antigos. Nomes iguais sem diferença de maiúsculas/espaços se juntam.
    """
    termo = (termo or "").strip()
    if len(termo) < 2:
        return []
    linhas = (
        queryset.filter(**{f"{campo_nome}__icontains": termo})
        .order_by(*ordem)
        .values(campo_nome, *campos.values())[:LINHAS_LIDAS]
    )
    achados = {}
    for linha in linhas:
        nome = " ".join(str(linha[campo_nome] or "").split())
        if not nome:
            continue
        chave = nome.casefold()
        if chave in achados:
            achados[chave]["pedidos"] += 1
            continue
        if len(achados) >= limite:
            continue
        achados[chave] = {
            "nome": nome,
            "campos": {
                campo: "" if linha[caminho] is None else str(linha[caminho])
                for campo, caminho in campos.items()
            },
            "pedidos": 1,
        }
    return list(achados.values())


def solicitantes_anteriores(usuario, termo):
    """Quem já pediu evento (entre as solicitações que o usuário enxerga)."""
    from cadastros.models import OrgaoResponsavel

    from .permissions import queryset_visivel

    achados = ultimos_por_nome(
        queryset_visivel(usuario, SolicitacaoEvento.objects.all()),
        "solicitante_nome",
        termo,
        {
            "solicitante_cargo_unidade": "solicitante_cargo_unidade",
            "contato": "contato",
            "orgao_responsavel": "orgao_responsavel_id",
        },
        ordem=["-data_solicitacao", "-pk"],
    )
    ids_orgaos = [a["campos"]["orgao_responsavel"] for a in achados if a["campos"]["orgao_responsavel"]]
    orgaos = {
        str(pk): nome
        for pk, nome in OrgaoResponsavel.objects.filter(pk__in=ids_orgaos).values_list("pk", "nome")
    }
    for achado in achados:
        campos = achado["campos"]
        achado["detalhe"] = " · ".join(
            parte
            for parte in (
                campos["solicitante_cargo_unidade"],
                campos["contato"],
                orgaos.get(campos["orgao_responsavel"], ""),
            )
            if parte
        )
    return achados
