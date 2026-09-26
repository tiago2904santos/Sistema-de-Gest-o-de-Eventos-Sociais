"""O Plano de Trabalho de uma viagem que veio de solicitação já nasce preenchido.

A solicitação deferida já diz quais serviços o evento terá, qual é o programa
(o tipo de evento), se vai unidade móvel e quantos servidores de cada equipe.
Aqui isso vira o rascunho do plano: atividades marcadas (com metas, recursos
e o texto da unidade móvel regenerados a partir delas), programa escolhido e
efetivo previsto. A pessoa só revisa.

Serviço e atividade dizem a mesma coisa com grafias diferentes; a comparação
é a mesma do comando ``sincronizar_servicos_pt`` (sem acento, sem pontuação,
um nome contido no outro). O que não encontra correspondente fica de fora —
melhor uma atividade a marcar do que uma marcada errada.
"""

from __future__ import annotations

from collections import Counter

from cadastros.management.commands.sincronizar_servicos_pt import _combina, chave


def solicitacao_da_viagem(viagem):
    """A solicitação de evento que gerou a viagem, se houver."""
    if viagem is None or not viagem.pk:
        return None
    roteiro = (
        viagem.roteiros.filter(solicitacao__isnull=False, cancelado=False)
        .select_related("solicitacao__tipo_evento", "solicitacao__orgao_responsavel",
                        "solicitacao__unidade_movel_designada")
        .order_by("id")
        .first()
    )
    return roteiro.solicitacao if roteiro is not None else None


def _correspondente(nome, candidatos, *, rotulo=str):
    alvo = chave(nome)
    if not alvo:
        return None
    exato = next((c for c in candidatos if chave(rotulo(c)) == alvo), None)
    if exato is not None:
        return exato
    return next((c for c in candidatos if _combina(alvo, chave(rotulo(c)))), None)


def atividades_da_solicitacao(solicitacao):
    """As atividades do PT correspondentes aos serviços pedidos (e à unidade móvel)."""
    from .models import AtividadePlanoTrabalho
    from .services import CODIGO_UNIDADE_MOVEL

    catalogo = list(AtividadePlanoTrabalho.objects.all())
    escolhidas = []
    for servico in solicitacao.servicos.all():
        atividade = _correspondente(servico.nome, catalogo, rotulo=lambda a: a.nome)
        if atividade is not None and atividade not in escolhidas:
            escolhidas.append(atividade)
    if solicitacao.unidade_movel:
        movel = next((a for a in catalogo if a.codigo == CODIGO_UNIDADE_MOVEL), None)
        if movel is not None and movel not in escolhidas:
            escolhidas.append(movel)
    return escolhidas


def programa_da_solicitacao(solicitacao):
    """O programa solicitante pelo tipo de evento (ou pelo órgão responsável)."""
    from .models import ProgramaSolicitante

    programas = list(ProgramaSolicitante.objects.all())
    for nome in (
        solicitacao.tipo_evento.nome if solicitacao.tipo_evento_id else "",
        solicitacao.orgao_responsavel.nome if solicitacao.orgao_responsavel_id else "",
    ):
        programa = _correspondente(nome, programas, rotulo=lambda p: p.nome)
        if programa is not None:
            return programa
    return None


def _efetivo_previsto(plano, viagem):
    """[(unidade, cargo, quantidade)]: dos ofícios, senão das equipes designadas.

    Os servidores dos ofícios são a equipe de verdade. Sem ofício, a meta da
    DG vira linha só quando há um cargo padrão cadastrado — o efetivo do PT
    exige cargo, e inventar um seria pior que deixar a linha para a pessoa.
    """
    from viagens_cadastros.models import Cargo, Unidade
    from viagens_viagem.meta_equipe import nomes_combinam, servidores_em_oficios

    servidores = [s for s in servidores_em_oficios(viagem) if s.cargo_id]
    if servidores:
        contagem = Counter((s.unidade_id, s.cargo_id) for s in servidores)
        return [(unidade, cargo, n) for (unidade, cargo), n in contagem.items()]

    cargo = Cargo.objects.filter(is_padrao=True).first()
    if cargo is None:
        return []
    unidades = list(Unidade.objects.all())
    linhas = {}
    for prevista in viagem.equipes_previstas.select_related("equipe"):
        if not prevista.quantidade:
            continue
        unidade = next(
            (u for u in unidades if nomes_combinam(prevista.equipe.nome, u.nome, u.sigla)), None
        )
        chave_linha = (unidade.pk if unidade else None, cargo.pk)
        linhas[chave_linha] = linhas.get(chave_linha, 0) + prevista.quantidade
    return [(unidade, cargo_id, n) for (unidade, cargo_id), n in linhas.items()]


def semear_da_solicitacao(plano, viagem) -> bool:
    """Preenche o rascunho com o que a solicitação de origem sabe.

    Só completa o que está vazio: atividades, programa, efetivo. Devolve se
    havia solicitação para semear.
    """
    from .services import TEXTO_UNIDADE_MOVEL, sincronizar_atividades

    solicitacao = solicitacao_da_viagem(viagem)
    if solicitacao is None:
        return False

    if not plano.atividades_selecionadas.exists():
        atividades = atividades_da_solicitacao(solicitacao)
        if atividades:
            plano.atividades_selecionadas.set(atividades)
            sincronizar_atividades(plano, save=False)

    if solicitacao.unidade_movel:
        texto = plano.unidade_movel_texto or TEXTO_UNIDADE_MOVEL
        if solicitacao.unidade_movel_designada_id:
            texto = f"{texto} Unidade designada: {solicitacao.unidade_movel_designada}."
        plano.unidade_movel_texto = texto

    if not plano.programa_id:
        programa = programa_da_solicitacao(solicitacao)
        if programa is not None:
            plano.programa = programa
            plano.programa_outros = ""
        elif solicitacao.tipo_evento_id:
            # O título da viagem ("Município — data") não é programa; o tipo
            # de evento é o mais próximo que a solicitação tem.
            plano.programa_outros = solicitacao.tipo_evento.nome

    plano.save()

    if not plano.efetivos.exists():
        for unidade_id, cargo_id, quantidade in _efetivo_previsto(plano, viagem):
            plano.efetivos.create(unidade_id=unidade_id, cargo_id=cargo_id, quantidade=quantidade)
    return True
