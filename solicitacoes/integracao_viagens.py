"""A ponte entre o despacho da DG e o módulo de Viagens.

Quando a DG defere uma solicitação, o evento deixa de ser um pedido e passa a
ser trabalho a executar — e esse trabalho, quando há deslocamento, vive em
Viagens. Até aqui alguém relia a solicitação e redigitava tudo do outro lado:
município, datas, local, quantidade de servidores. Redigitar é onde o erro
entra, e o erro aqui vira documento oficial.

**A viagem nasce em rascunho, e só o que a solicitação sabe.** Ela não sabe
quem vai nominalmente (tem quantidade por equipe, não nomes), nem viatura, nem
motorista — e esses três é que decidem a diária. Inventar aqui seria pior que
deixar em branco: um número de diária errado atravessa a prestação de contas
inteira sem ninguém notar.

**A geração não derruba o despacho.** Se criar a viagem falhar, a decisão da
DG continua registrada: ela é o ato administrativo, e a viagem é consequência
dele. O contrário — despacho perdido porque o módulo vizinho estava com
problema — seria inaceitável.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

# Quantos servidores a solicitação previu, somando as equipes. Usado só para
# dimensionar o roteiro; a lista nominal é preenchida em Viagens.
def quantidade_prevista(solicitacao) -> int:
    direto = getattr(solicitacao, "quantidade_servidores", None)
    if direto:
        return int(direto)
    return sum(
        item.quantidade_servidores or 0
        for item in solicitacao.itens_equipe.all()
    )


def resumo_das_equipes(solicitacao) -> str:
    """"ASCOM: 2; Cerimonial (sem quantidade)" — o que a DG autorizou.

    Vai para as observações do roteiro porque é a informação que se perde no
    caminho: em Viagens só sobra o total, e quem monta a equipe precisa saber
    de que setores ela deveria vir.

    A equipe **sem quantidade aparece mesmo assim**. Nos dados reais quase
    toda solicitação tem equipe e quase nenhuma tem o número (98 de 101 contra
    6 de 101): filtrar pelo número esconderia justamente o caso comum, e quem
    fosse montar a viagem não saberia nem de que setor chamar.
    """
    partes = []
    for item in solicitacao.itens_equipe.select_related("equipe"):
        if item.quantidade_servidores:
            partes.append(f"{item.equipe}: {item.quantidade_servidores}")
        else:
            partes.append(f"{item.equipe} (sem quantidade)")
    return "; ".join(partes)


def viagem_da_solicitacao(solicitacao):
    """A viagem já gerada a partir desta solicitação, se houver."""
    from viagens_viagem.models import Viagem

    return Viagem.objects.filter(
        roteiros__solicitacao=solicitacao, cancelado=False
    ).order_by("id").first()


def pode_gerar(solicitacao) -> tuple[bool, str]:
    """Se cabe gerar viagem para esta solicitação, e por que não quando não cabe."""
    from solicitacoes.models import DecisaoDG, StatusSolicitacao

    if solicitacao.decisao_dg != DecisaoDG.ATENDER:
        return False, "A DG ainda não autorizou o atendimento desta solicitação."
    if solicitacao.status != StatusSolicitacao.DEFERIDA_EM_ANDAMENTO:
        return False, f"A solicitação está {solicitacao.get_status_display().lower()}."
    if not solicitacao.municipio_id:
        return False, "A solicitação não tem município definido."
    if not solicitacao.data_inicio_evento:
        return False, "A solicitação não tem data de início do evento."
    if viagem_da_solicitacao(solicitacao) is not None:
        return False, "Esta solicitação já tem viagem gerada."
    return True, ""


def o_que_falta(viagem) -> list[str]:
    """O que a solicitação não tinha e alguém precisa completar em Viagens.

    Devolvido em texto, para a tela listar. É a diferença entre uma viagem que
    parece pronta e uma que está pronta.
    """
    faltando = []
    roteiro = viagem.roteiros.order_by("id").first()

    if roteiro is None:
        faltando.append("Roteiro da viagem")
    else:
        if not roteiro.origem_municipio_id:
            faltando.append("Município de onde a equipe sai")
        if not roteiro.saida_dt:
            faltando.append("Data e hora da saída")

    oficios = list(viagem.oficios.filter(cancelado=False))
    if not oficios:
        faltando.append("Ofício de viagem (com a equipe nominal)")
    else:
        for oficio in oficios:
            if not oficio.servidores.exists():
                faltando.append(f"Servidores do ofício #{oficio.pk}")
            if not oficio.viatura_id and not oficio.transporte_placa_manual:
                faltando.append(f"Viatura do ofício #{oficio.pk}")
            if not oficio.motorista_id and not oficio.motorista_manual_nome:
                faltando.append(f"Motorista do ofício #{oficio.pk}")

    return faltando


def gerar_viagem(solicitacao, usuario):
    """Cria a viagem em rascunho a partir da solicitação deferida.

    Devolve a viagem criada. Levanta ``ValueError`` com o motivo quando não
    cabe gerar — quem chama decide se isso é erro ou só informação.
    """
    from django.db import transaction

    from viagens_roteiros.models import RoteiroDestino
    from viagens_viagem.models import Viagem

    cabe, motivo = pode_gerar(solicitacao)
    if not cabe:
        raise ValueError(motivo)

    municipio = solicitacao.municipio
    inicio = solicitacao.data_inicio_evento
    fim = solicitacao.data_fim_evento or inicio
    previstos = quantidade_prevista(solicitacao)

    # O motivo carrega a origem: seis meses depois, ninguém lembra de onde
    # veio uma viagem, e o número da solicitação é o fio que liga os dois.
    motivo = _motivo_da_solicitacao(solicitacao)

    with transaction.atomic():
        viagem = Viagem.objects.create(
            titulo=f"{municipio} — {inicio:%d/%m/%Y}",
            destino_municipio=municipio,
            destino_estado=municipio.estado,
            data_inicio=inicio,
            data_fim=fim,
            motivo=motivo,
            descricao=(solicitacao.descricao_complementar or "").strip(),
            status=Viagem.STATUS_EM_PREPARACAO,
        )

        from viagens_roteiros.models import Roteiro

        roteiro = Roteiro.objects.create(
            viagem=viagem,
            # A ligação que faltava: daqui para frente a solicitação e a
            # viagem se encontram pelo banco, não pela memória de alguém.
            solicitacao=solicitacao,
            quantidade_servidores=max(previstos, 1),
            observacoes=_observacoes_do_roteiro(solicitacao),
        )
        RoteiroDestino.objects.create(roteiro=roteiro, municipio=municipio, ordem=1)

    logger.info(
        "Viagem %s gerada a partir da solicitação %s por %s",
        viagem.pk, solicitacao.pk, getattr(usuario, "username", "?"),
    )
    return viagem


def _motivo_da_solicitacao(solicitacao) -> str:
    partes = []
    if solicitacao.tipo_evento_id:
        partes.append(str(solicitacao.tipo_evento))
    if solicitacao.local_evento:
        partes.append(solicitacao.local_evento)
    texto = " — ".join(partes) or "Atendimento de solicitação de evento"
    return f"{texto} (Solicitação #{solicitacao.pk})"


def _observacoes_do_roteiro(solicitacao) -> str:
    """O que a solicitação sabia e o roteiro não tem campo para guardar."""
    linhas = [f"Gerado a partir da Solicitação de Evento #{solicitacao.pk}."]
    equipes = resumo_das_equipes(solicitacao)
    if equipes:
        linhas.append(f"Equipes autorizadas pela DG — {equipes}.")
    if solicitacao.solicitante_nome:
        linhas.append(f"Solicitante: {solicitacao.solicitante_nome}.")
    if solicitacao.local_evento:
        linhas.append(f"Local: {solicitacao.local_evento}.")
    if solicitacao.quantidade_cin:
        linhas.append(f"CIN previstas: {solicitacao.quantidade_cin}.")
    if solicitacao.observacoes_dg:
        linhas.append(f"Observação da DG: {solicitacao.observacoes_dg}")
    return "\n".join(linhas)
