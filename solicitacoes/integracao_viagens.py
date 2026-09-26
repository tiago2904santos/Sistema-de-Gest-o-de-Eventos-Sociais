"""A ponte entre o despacho da DG e o módulo de Viagens.

Quando a DG defere uma solicitação, o evento deixa de ser um pedido e passa a
ser trabalho a executar — e esse trabalho, quando há deslocamento, vive em
Viagens. Até aqui alguém relia a solicitação e redigitava tudo do outro lado:
município, datas, local, quantidade de servidores. Redigitar é onde o erro
entra, e o erro aqui vira documento oficial.

**A viagem nasce sozinha no deferimento, com tudo o que a solicitação sabe.**
Sede e percurso de ida e volta (pela configuração do setor), datas, destino,
motivo, tipo, equipes e quantidades, unidade móvel, motorista designado e os
anexos do pedido. O que ela não sabe — quem vai nominalmente e em que viatura
— fica para o ofício; inventar aqui seria pior que deixar em branco.

**Uma viagem por ambiente.** Cada equipe designada que é um setor de Viagens
("ASCOM: 2") ganha a viagem no ambiente dela, com a meta de servidores. O
contador (``viagens_viagem.meta_equipe``) mostra quantos faltam até os
ofícios somarem o que a DG designou.

**A geração não derruba o despacho.** Se criar a viagem falhar, a decisão da
DG continua registrada: ela é o ato administrativo, e a viagem é consequência
dele. O contrário — despacho perdido porque o módulo vizinho estava com
problema — seria inaceitável. A tela da solicitação oferece tentar de novo.
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


def viagens_da_solicitacao(solicitacao):
    """As viagens geradas a partir desta solicitação — uma por ambiente."""
    from viagens_viagem.models import Viagem

    return list(
        Viagem.objects.filter(roteiros__solicitacao=solicitacao, cancelado=False)
        .select_related("setor")
        .distinct()
        .order_by("id")
    )


def viagem_da_solicitacao(solicitacao):
    """A primeira viagem gerada a partir desta solicitação, se houver."""
    viagens = viagens_da_solicitacao(solicitacao)
    return viagens[0] if viagens else None


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
    from viagens_viagem.meta_equipe import contador_de_servidores

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
        contador = contador_de_servidores(viagem)
        if contador and contador["faltam"]:
            faltando.append(contador["texto"])

    return faltando


# ---------------------------------------------------------------------------
# Ambientes: cada equipe designada vai para a viagem do seu setor
# ---------------------------------------------------------------------------


def _setores_de_viagens():
    from accounts.models import Setor

    return list(
        Setor.objects.filter(ativo=True, modulos__codigo="VIAGENS", modulos__ativo=True)
        .distinct()
        .order_by("nome")
    )


def ambiente_da_equipe(equipe, setores=None):
    """O setor de Viagens que corresponde à equipe ("ASCOM" → setor ASCOM).

    Pelo nome ou pela sigla, sem acento nem caixa. Equipe que não é setor de
    Viagens (ex.: "Cerimonial") não tem ambiente próprio.
    """
    from viagens_viagem.meta_equipe import nomes_combinam

    for setor in setores if setores is not None else _setores_de_viagens():
        if nomes_combinam(equipe.nome, setor.nome, setor.sigla):
            return setor
    return None


def grupos_por_ambiente(solicitacao) -> list[tuple]:
    """[(setor ou None, [itens de equipe])]: uma viagem para cada grupo.

    A equipe com setor de Viagens correspondente ganha a viagem no ambiente
    dela; as que não têm setor vão juntas numa viagem sem ambiente. Sem
    equipe nenhuma, uma viagem só, como antes.
    """
    setores = _setores_de_viagens()
    grupos: dict = {}
    for item in solicitacao.itens_equipe.select_related("equipe").order_by("equipe__nome"):
        setor = ambiente_da_equipe(item.equipe, setores)
        grupos.setdefault(setor.pk if setor else None, (setor, []))[1].append(item)
    if not grupos:
        return [(None, [])]
    com_setor = sorted(
        (grupo for chave, grupo in grupos.items() if chave is not None),
        key=lambda grupo: grupo[0].nome,
    )
    sem_setor = [grupos[None]] if None in grupos else []
    return com_setor + sem_setor


def configuracao_do_ambiente(setor):
    """A configuração de Viagens do setor, sem criar nada; senão a global."""
    from viagens_cadastros.models import ConfiguracaoSistema

    if setor is not None:
        propria = ConfiguracaoSistema.objects.filter(setor=setor).first()
        if propria is not None:
            return propria
    return ConfiguracaoSistema.objects.filter(setor__isnull=True).first()


def _unidade_do_ambiente(setor, itens, config):
    """A unidade responsável: a lotação com o nome do setor ou da equipe."""
    from viagens_cadastros.models import Unidade
    from viagens_viagem.meta_equipe import nomes_combinam

    nomes = []
    if setor is not None:
        nomes += [setor.sigla, setor.nome]
    if len(itens) == 1:
        nomes.append(itens[0].equipe.nome)
    nomes = [n for n in nomes if n]
    if nomes:
        for unidade in Unidade.objects.all():
            if any(nomes_combinam(n, unidade.nome, unidade.sigla) for n in nomes):
                return unidade
    if setor is not None and config is not None and config.setor_id == setor.pk:
        return config.unidade
    return None


def _rotulo_do_ambiente(setor):
    return (setor.sigla or setor.nome) if setor is not None else ""


def _titulo(solicitacao, setor=None):
    municipio, inicio = solicitacao.municipio, solicitacao.data_inicio_evento
    titulo = f"{municipio} — {inicio:%d/%m/%Y}"
    rotulo = _rotulo_do_ambiente(setor)
    return f"{titulo} ({rotulo})" if rotulo else titulo


def _quantidade_do_grupo(solicitacao, itens, unico) -> int:
    soma = sum(item.quantidade_servidores or 0 for item in itens)
    if not soma and unico:
        soma = quantidade_prevista(solicitacao)
    return max(soma, 1)


def _tipos_da_viagem(solicitacao):
    """O tipo de viagem com o nome do tipo de evento, quando existe um."""
    from viagens_viagem.meta_equipe import chave_de_nome
    from viagens_viagem.models import TipoViagem

    if not solicitacao.tipo_evento_id:
        return []
    alvo = chave_de_nome(solicitacao.tipo_evento.nome)
    return [t for t in TipoViagem.objects.all() if chave_de_nome(t.nome) == alvo]


def gerar_viagem(solicitacao, usuario):
    """Cria as viagens em rascunho e devolve a primeira."""
    return gerar_viagens(solicitacao, usuario)[0]


def gerar_viagens(solicitacao, usuario):
    """Cria a viagem de cada ambiente a partir da solicitação deferida.

    Devolve as viagens criadas. Levanta ``ValueError`` com o motivo quando não
    cabe gerar — quem chama decide se isso é erro ou só informação.
    """
    from django.db import transaction

    cabe, motivo = pode_gerar(solicitacao)
    if not cabe:
        raise ValueError(motivo)

    grupos = grupos_por_ambiente(solicitacao)
    with transaction.atomic():
        viagens = [
            _criar_viagem_do_grupo(solicitacao, setor, itens, unico=len(grupos) == 1)
            for setor, itens in grupos
        ]

    logger.info(
        "Viagens %s geradas a partir da solicitação %s por %s",
        [v.pk for v in viagens], solicitacao.pk, getattr(usuario, "username", "?"),
    )
    return viagens


def _criar_viagem_do_grupo(solicitacao, setor, itens, *, unico):
    from viagens_roteiros.models import Roteiro, RoteiroDestino
    from viagens_viagem.models import EquipePrevista, Viagem

    municipio = solicitacao.municipio
    inicio = solicitacao.data_inicio_evento
    fim = solicitacao.data_fim_evento or inicio
    config = configuracao_do_ambiente(setor)
    sede = config.cidade_sede_padrao if config is not None else None

    viagem = Viagem.objects.create(
        titulo=_titulo(solicitacao, setor),
        destino_municipio=municipio,
        destino_estado=municipio.estado,
        data_inicio=inicio,
        data_fim=fim,
        # O motivo carrega a origem: seis meses depois, ninguém lembra de onde
        # veio uma viagem, e o número da solicitação é o fio que liga os dois.
        motivo=_motivo_da_solicitacao(solicitacao),
        descricao=(solicitacao.descricao_complementar or "").strip(),
        status=Viagem.STATUS_EM_PREPARACAO,
        setor=setor,
        unidade_responsavel=_unidade_do_ambiente(setor, itens, config),
    )
    tipos = _tipos_da_viagem(solicitacao)
    if tipos:
        viagem.tipos.set(tipos)
    EquipePrevista.objects.bulk_create([
        EquipePrevista(viagem=viagem, equipe=item.equipe, quantidade=item.quantidade_servidores)
        for item in itens
    ])

    roteiro = Roteiro.objects.create(
        viagem=viagem,
        # A ligação que faltava: daqui para frente a solicitação e a
        # viagem se encontram pelo banco, não pela memória de alguém.
        solicitacao=solicitacao,
        tipo=Roteiro.Tipo.EVENTO,
        origem_municipio=sede,
        quantidade_servidores=_quantidade_do_grupo(solicitacao, itens, unico),
        observacoes=_observacoes_do_roteiro(solicitacao),
    )
    RoteiroDestino.objects.create(roteiro=roteiro, municipio=municipio, ordem=1)
    _montar_trechos(roteiro, sede, municipio, inicio, fim)
    _copiar_anexos(solicitacao, viagem)
    return viagem


def _montar_trechos(roteiro, sede, municipio, inicio, fim):
    """Ida no primeiro dia às 08:00 e volta no último às 16:00, como o editor.

    A distância e o tempo vêm do serviço de rotas quando ele responde; sem
    ele os trechos ficam só com a saída e o operador completa a chegada. As
    diárias só são calculadas com o percurso inteiro datado.
    """
    from datetime import datetime, time, timedelta

    from django.utils import timezone

    from viagens_roteiros.models import RoteiroTrecho

    if sede is None or sede.pk == municipio.pk:
        return
    pernas = [
        (RoteiroTrecho.Sentido.IDA, sede, municipio, datetime.combine(inicio, time(8, 0))),
        (RoteiroTrecho.Sentido.RETORNO, municipio, sede, datetime.combine(fim, time(16, 0))),
    ]
    completo = True
    for ordem, (sentido, origem, destino, saida) in enumerate(pernas, 1):
        saida = timezone.make_aware(saida)
        trecho = RoteiroTrecho(
            roteiro=roteiro, ordem=ordem, sentido=sentido,
            origem_municipio=origem, destino_municipio=destino, saida_dt=saida,
        )
        estimativa = _estimar(origem, destino)
        if estimativa:
            viagem_min = estimativa.get("tempo_viagem_min") or 0
            adicional = estimativa.get("tempo_adicional_sugerido_min") or 0
            trecho.distancia_km = estimativa.get("distancia_km")
            trecho.tempo_viagem_min = viagem_min
            trecho.tempo_adicional_min = adicional
            trecho.duracao_min = viagem_min + adicional
            trecho.rota_fonte = estimativa.get("fonte", "")
            trecho.rota_calculada_em = timezone.now()
            trecho.chegada_dt = saida + timedelta(minutes=viagem_min + adicional)
        else:
            completo = False
        trecho.save()
    roteiro.sincronizar_periodo()
    if completo:
        try:
            from viagens_roteiros.services.calculo import recalcular_diarias

            recalcular_diarias(roteiro)
        except Exception:  # noqa: BLE001 - a diária fica para a tela do roteiro
            logger.info("Diárias do roteiro %s não calculadas na geração.", roteiro.pk)


def _estimar(origem, destino):
    try:
        from viagens_roteiros.services.rota import estimar_trecho

        return estimar_trecho(origem, destino)
    except Exception:  # noqa: BLE001 - sem rota, o trecho nasce só com a saída
        return None


EXTENSOES_COPIAVEIS = {".pdf", ".png", ".jpg", ".jpeg"}


def _copiar_anexos(solicitacao, viagem):
    """Ofício solicitante, convite e fotos vão para os documentos da viagem.

    Uma cópia do arquivo, não o mesmo caminho: apagar o anexo na solicitação
    não pode levar junto o documento da viagem. Imagem vira PDF; o que não
    abre é pulado sem derrubar a geração.
    """
    from pathlib import Path

    from django.core.files.base import ContentFile

    from viagens_viagem.models import ViagemDocumentoSolicitacao
    from viagens_viagem.services import converter_para_pdf_se_necessario

    for anexo in solicitacao.anexos.all():
        nome = Path(anexo.nome_original or anexo.arquivo.name).name
        if Path(nome).suffix.lower() not in EXTENSOES_COPIAVEIS:
            continue
        try:
            with anexo.arquivo.open("rb") as origem:
                conteudo = ContentFile(origem.read(), name=nome)
            arquivo = converter_para_pdf_se_necessario(conteudo)
            ViagemDocumentoSolicitacao.objects.create(
                viagem=viagem, arquivo=arquivo, nome_original=Path(arquivo.name).name
            )
        except Exception:  # noqa: BLE001 - um anexo ruim não impede a viagem
            logger.warning("Anexo %s não copiado para a viagem %s.", anexo.pk, viagem.pk)


def data_limite_sem_justificativa(viagem):
    """Último dia para criar o ofício sem precisar de justificativa.

    A justificativa é exigida com antecedência igual ou menor que o prazo do
    setor; a data-limite é a saída menos (prazo + 1) dias.
    """
    from datetime import timedelta

    from django.utils import timezone

    roteiro = viagem.roteiros.filter(cancelado=False).order_by("id").first()
    saida = None
    if roteiro is not None and roteiro.saida_dt:
        saida = timezone.localdate(roteiro.saida_dt)
    saida = saida or viagem.data_inicio
    if saida is None:
        return None
    config = configuracao_do_ambiente(viagem.setor)
    prazo = config.prazo_justificativa_dias if config is not None else 10
    return saida - timedelta(days=prazo + 1)


def resumo_da_viagem(viagem, user=None):
    """O que a solicitação e o painel mostram de cada viagem gerada."""
    from django.urls import reverse
    from django.utils import timezone

    from viagens_cadastros.permissions import pode_acessar
    from viagens_viagem.meta_equipe import contador_de_servidores

    limite = data_limite_sem_justificativa(viagem)
    return {
        "viagem": viagem,
        "ambiente": _rotulo_do_ambiente(viagem.setor),
        # Quem não tem o módulo vê a situação, mas não o link.
        "url": reverse("viagens_viagem:painel", args=[viagem.pk])
        if user is None or pode_acessar(user)
        else "",
        "falta": o_que_falta(viagem),
        "contador": contador_de_servidores(viagem),
        "data_limite": limite,
        "limite_vencido": bool(limite and limite < timezone.localdate()),
    }


# ---------------------------------------------------------------------------
# Depois de gerada: a viagem acompanha a solicitação
# ---------------------------------------------------------------------------

# Documentos oficiais da viagem. O roteiro fica de fora: é o planejamento que
# nasceu com ela, não um documento emitido.
DOCUMENTOS_EMITIDOS = ("oficios", "ordens_servico", "planos_trabalho", "termos_autorizacao")


def documentos_emitidos(viagem) -> bool:
    """A viagem já tem ofício, OS, plano ou termo ativo — ou passou dessa fase.

    Com documento emitido, a viagem não é mais só rascunho: mexer nela ou
    cancelá-la sozinho desfaria papel oficial. Aí quem decide é o operador
    de Viagens, que recebe o aviso.
    """
    from viagens_viagem.models import Viagem

    if viagem.status in {
        Viagem.STATUS_DOCUMENTOS_GERADOS,
        Viagem.STATUS_EM_EXECUCAO,
        Viagem.STATUS_FINALIZADO,
    }:
        return True
    return any(
        getattr(viagem, relacao).filter(cancelado=False).exists()
        for relacao in DOCUMENTOS_EMITIDOS
    )


def _avisar_operadores(viagem, titulo, mensagem, usuario):
    """Sino para gestores e operadores de Viagens, com o link do painel."""
    from django.urls import reverse

    from core.notificacoes import notificar, usuarios_do_grupo
    from viagens_cadastros.permissions import GRUPO_GESTOR, GRUPO_OPERADOR

    destinatarios = list(usuarios_do_grupo(GRUPO_GESTOR)) + list(
        usuarios_do_grupo(GRUPO_OPERADOR)
    )
    notificar(
        destinatarios,
        titulo,
        mensagem,
        link=reverse("viagens_viagem:painel", args=[viagem.pk]),
        exceto=usuario,
    )


def encerrar_viagem(solicitacao, usuario, motivo="") -> str:
    """A solicitação não vai mais acontecer (não atendida ou cancelada).

    Sem documento emitido, cada viagem é cancelada junto — e com ela o
    roteiro. Com documento, ela fica como está e o operador de Viagens é
    avisado. Devolve "cancelada", "avisada" ou "" (não havia viagem); com
    várias viagens, "avisada" prevalece.
    """
    viagens = viagens_da_solicitacao(solicitacao)
    if not viagens:
        return ""
    situacao = solicitacao.get_status_display().lower()
    texto = f"Solicitação #{solicitacao.pk} {situacao}"
    if motivo:
        texto = f"{texto}: {motivo}"
    resultado = "cancelada"
    for viagem in viagens:
        if not documentos_emitidos(viagem):
            viagem.cancelar(texto)
            continue
        _avisar_operadores(
            viagem,
            f"Viagem #{viagem.pk}: solicitação {situacao}",
            f"{texto}. A viagem já tem documentos emitidos e não foi cancelada; "
            "confira e cancele pelo painel se for o caso.",
            usuario,
        )
        resultado = "avisada"
    return resultado


def sincronizar_viagem(solicitacao, usuario) -> str:
    """Novo deferimento de uma solicitação que já tinha viagem.

    O pedido pode ter mudado de local, datas, município ou equipes entre um
    despacho e outro. A meta de servidores de cada viagem sempre acompanha o
    que a DG acabou de deferir (é contagem, não documento). Sem documento
    emitido, a viagem e o roteiro são atualizados; com documento, o operador
    de Viagens é avisado para conferir. Um ambiente novo ganha a sua viagem.
    Devolve "atualizada", "avisada" ou "" (não havia viagem).
    """
    from django.db import transaction

    viagens = viagens_da_solicitacao(solicitacao)
    if not viagens:
        return ""

    grupos = grupos_por_ambiente(solicitacao)
    por_setor = {(setor.pk if setor else None): itens for setor, itens in grupos}
    unico = len(grupos) == 1
    resultado = "atualizada"
    with transaction.atomic():
        vistos = set()
        for viagem in viagens:
            chave = viagem.setor_id
            if chave not in por_setor and len(viagens) == 1:
                # A viagem única segue a solicitação mesmo que o ambiente mude.
                chave = next(iter(por_setor))
            if chave not in por_setor:
                # A DG tirou a equipe deste ambiente: sem documento, a viagem
                # dele sai de cena; com documento, o operador decide.
                if documentos_emitidos(viagem):
                    _avisar_operadores(
                        viagem,
                        f"Viagem #{viagem.pk}: equipe retirada da solicitação #{solicitacao.pk}",
                        "A DG deferiu de novo sem a equipe deste ambiente, mas a viagem "
                        "já tem documentos emitidos. Confira e cancele pelo painel se for o caso.",
                        usuario,
                    )
                    resultado = "avisada"
                else:
                    viagem.cancelar(
                        f"Equipe retirada pela DG na Solicitação #{solicitacao.pk}"
                    )
                continue
            itens = por_setor[chave]
            vistos.add(chave)
            _sincronizar_equipes(viagem, itens)
            if documentos_emitidos(viagem):
                _avisar_operadores(
                    viagem,
                    f"Viagem #{viagem.pk}: solicitação #{solicitacao.pk} alterada",
                    "A solicitação foi alterada e deferida de novo pela DG, mas a viagem "
                    "já tem documentos emitidos. Confira datas, local e equipe.",
                    usuario,
                )
                resultado = "avisada"
                continue
            _atualizar_viagem(solicitacao, viagem, itens, unico)
        for setor, itens in grupos:
            if (setor.pk if setor else None) not in vistos:
                _criar_viagem_do_grupo(solicitacao, setor, itens, unico=unico)
    return resultado


def _sincronizar_equipes(viagem, itens):
    from viagens_viagem.models import EquipePrevista

    desejadas = {item.equipe_id: item.quantidade_servidores for item in itens}
    viagem.equipes_previstas.exclude(equipe_id__in=desejadas).delete()
    for equipe_id, quantidade in desejadas.items():
        EquipePrevista.objects.update_or_create(
            viagem=viagem, equipe_id=equipe_id, defaults={"quantidade": quantidade}
        )


def _atualizar_viagem(solicitacao, viagem, itens, unico):
    municipio = solicitacao.municipio
    inicio = solicitacao.data_inicio_evento
    viagem.titulo = _titulo(solicitacao, viagem.setor)
    viagem.destino_municipio = municipio
    viagem.destino_estado = municipio.estado
    viagem.data_inicio = inicio
    viagem.data_fim = solicitacao.data_fim_evento or inicio
    viagem.motivo = _motivo_da_solicitacao(solicitacao)
    viagem.descricao = (solicitacao.descricao_complementar or "").strip()
    viagem.save()

    for roteiro in viagem.roteiros.filter(solicitacao=solicitacao, cancelado=False):
        roteiro.tipo = roteiro.Tipo.EVENTO
        roteiro.quantidade_servidores = _quantidade_do_grupo(solicitacao, itens, unico)
        roteiro.observacoes = _observacoes_do_roteiro(solicitacao)
        campos = ["tipo", "quantidade_servidores", "observacoes", "atualizado_em"]
        destino = roteiro.destinos.order_by("ordem", "pk").first()
        if destino is not None and destino.municipio_id != municipio.pk:
            destino.municipio = municipio
            destino.save(update_fields=["municipio", "atualizado_em"])
            # O percurso mudou: a rota calculada deixa de valer.
            if roteiro.rota_status == roteiro.RotaStatus.CALCULADA:
                roteiro.rota_status = roteiro.RotaStatus.DESATUALIZADA
                campos.append("rota_status")
        roteiro.save(update_fields=campos)


def aviso_para_o_painel(viagem):
    """O que o painel da viagem precisa dizer sobre a solicitação de origem.

    Devolve {solicitacao, url, aviso, alteracoes, resumo} ou None quando a
    viagem não veio de solicitação. `aviso` fica vazio quando as duas estão
    em dia; `resumo` traz o contador de servidores e a data-limite do ofício.
    """
    from django.urls import reverse

    from solicitacoes.models import AcaoHistorico, StatusSolicitacao

    roteiro = (
        viagem.roteiros.filter(solicitacao__isnull=False)
        .select_related("solicitacao")
        .order_by("id")
        .first()
    )
    if roteiro is None:
        return None
    solicitacao = roteiro.solicitacao
    reenvios = list(
        solicitacao.historico.filter(
            acao=AcaoHistorico.REENVIO, criado_em__gt=viagem.criado_em
        ).order_by("criado_em", "pk")
    )
    aviso = ""
    alteracoes = []
    if not viagem.cancelado and solicitacao.status in {
        StatusSolicitacao.NAO_ATENDIDA,
        StatusSolicitacao.CANCELADA,
    }:
        aviso = (
            f"A solicitação está {solicitacao.get_status_display().lower()}, mas a "
            "viagem tem documentos emitidos e não foi cancelada automaticamente."
        )
    elif reenvios and solicitacao.status == StatusSolicitacao.AGUARDANDO_DESPACHO:
        aviso = (
            "Viagem desatualizada: a solicitação foi alterada e aguarda novo "
            "despacho da DG."
        )
    elif reenvios and documentos_emitidos(viagem):
        aviso = (
            "A solicitação foi alterada depois que a viagem teve documentos "
            "emitidos. Confira o que mudou."
        )
    if aviso:
        for registro in reenvios:
            alteracoes.extend(registro.alteracoes or [])
    return {
        "solicitacao": solicitacao,
        "url": reverse("solicitacoes:editar", args=[solicitacao.pk]),
        "aviso": aviso,
        "alteracoes": alteracoes,
        "resumo": resumo_da_viagem(viagem),
    }


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
    if solicitacao.unidade_movel:
        if solicitacao.unidade_movel_designada_id:
            linhas.append(f"Unidade móvel designada: {solicitacao.unidade_movel_designada}.")
        else:
            linhas.append("Com unidade móvel (ainda não designada).")
    if solicitacao.motorista_id:
        linhas.append(f"Motorista designado: {solicitacao.motorista.nome}.")
    if solicitacao.quantidade_cin:
        linhas.append(f"CIN previstas: {solicitacao.quantidade_cin}.")
    if solicitacao.observacoes_dg:
        linhas.append(f"Observação da DG: {solicitacao.observacoes_dg}")
    return "\n".join(linhas)
