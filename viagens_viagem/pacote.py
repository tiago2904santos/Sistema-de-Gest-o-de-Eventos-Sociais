"""Gerar os documentos da viagem de uma vez (m064).

Depois do roteiro, cada documento era criado um por um, e em cada um se
escolhiam de novo equipe, viatura e motorista. Aqui a pessoa monta os
ofícios da viagem numa tela só — cada ofício com a SUA equipe, o seu
motorista e a sua viatura ("servidor 1 dirigindo a VTR 1 no ofício 1;
servidores 2, 3 e 4, com o 4 dirigindo a VTR 2, no ofício 2") — e o sistema
cria, em rascunho e já vinculados:

- um ofício por equipe, numerado, com o roteiro da viagem, o motivo e a
  unidade responsável como solicitante;
- os termos de autorização de cada servidor, no próprio ofício (a mesma
  regra da tela do ofício: todos, menos quem é da unidade emissora);
- uma ordem de serviço com toda a equipe e os ofícios vinculados, se a
  viagem ainda não tiver;
- o plano de trabalho, se a viagem ainda não tiver (o rascunho semeado pela
  viagem, como no "Novo plano").

Nada é finalizado nem protocolado: a pessoa revisa cada documento e
finaliza no módulo dele. Documento que já existe não é mexido.
"""

from dataclasses import dataclass, field

from django.db import transaction


@dataclass
class EquipeDoOficio:
    servidores: list
    motorista: object = None
    viatura: object = None


@dataclass
class ResultadoDoPacote:
    oficios: list = field(default_factory=list)
    ordem: object = None
    plano: object = None
    avisos: list = field(default_factory=list)


class PacoteInvalido(ValueError):
    """As equipes não fecham: servidor em dois ofícios, ofício sem ninguém..."""

    def __init__(self, erros):
        super().__init__("; ".join(erros))
        self.erros = erros


def servidores_ja_em_oficios(viagem):
    """{servidor_pk: ofício} dos ofícios ativos que a viagem já tem."""
    ocupados = {}
    for oficio in viagem.oficios.filter(cancelado=False).prefetch_related("servidores").order_by("pk"):
        for servidor in oficio.servidores.all():
            ocupados.setdefault(servidor.pk, oficio)
    return ocupados


def completar_com_motoristas(viagem, equipes):
    """O motorista que não viaja em nenhum outro ofício entra na equipe do seu.

    É o caso comum ("servidor 1 (motorista)"). Quem já está em outra equipe,
    deste pacote ou de um ofício que a viagem já tem, fica de fora: é o
    motorista "de outro ofício", e aquele ofício vira a referência dele.
    """
    nas_equipes = {s.pk for e in equipes for s in e.servidores}
    ja_em_oficios = servidores_ja_em_oficios(viagem)
    for equipe in equipes:
        motorista = equipe.motorista
        if motorista is not None and motorista.pk not in nas_equipes and motorista.pk not in ja_em_oficios:
            equipe.servidores = [*equipe.servidores, motorista]
            nas_equipes.add(motorista.pk)
    return equipes


def conferir_equipes(viagem, equipes):
    """Os erros que impedem gerar; lista vazia quando dá para seguir."""
    erros = []
    if not equipes:
        return ["Monte ao menos um ofício com a equipe."]
    ja_em_oficios = servidores_ja_em_oficios(viagem)
    vistos, viaturas = {}, {}
    for n, equipe in enumerate(equipes, 1):
        if not equipe.servidores:
            erros.append(f"Ofício {n}: escolha ao menos um servidor.")
        for servidor in equipe.servidores:
            if servidor.pk in vistos:
                erros.append(f"{servidor.nome} está nos ofícios {vistos[servidor.pk]} e {n}: cada servidor vai em um ofício só.")
            vistos.setdefault(servidor.pk, n)
            if servidor.pk in ja_em_oficios:
                erros.append(f"{servidor.nome} já está no ofício {ja_em_oficios[servidor.pk].numero_formatado} desta viagem.")
        if equipe.viatura is not None:
            if equipe.viatura.pk in viaturas:
                erros.append(f"A viatura {equipe.viatura} está nos ofícios {viaturas[equipe.viatura.pk]} e {n}.")
            viaturas.setdefault(equipe.viatura.pk, n)
    return erros


def _roteiro_da_viagem(viagem):
    return viagem.roteiros.filter(cancelado=False).order_by("-atualizado_em", "-pk").first()


def _criar_oficio(viagem, equipe, roteiro, *, com_termos, unidade_emissora):
    from viagens_oficios.services import criar_oficio_rascunho

    oficio = criar_oficio_rascunho(viagem)
    oficio.roteiro = roteiro
    oficio.viatura = equipe.viatura
    oficio.motorista = equipe.motorista
    # O mesmo retrato do efetivo que a tela do ofício guarda para as diárias.
    oficio.diarias_quantidade_servidores = len(equipe.servidores)
    oficio.save()
    oficio.servidores.set(equipe.servidores)
    if com_termos:
        oficio.servidores_termo_autorizacao.set(
            [s for s in equipe.servidores if not (unidade_emissora and s.unidade_id == unidade_emissora)]
        )
    return oficio


def _referenciar_motorista_de_outro_oficio(viagem, oficios, equipes):
    """Motorista que viaja em outro ofício: o número e o protocolo dele viram a referência."""
    onde = dict(servidores_ja_em_oficios(viagem))
    for oficio, equipe in zip(oficios, equipes):
        for servidor in equipe.servidores:
            onde[servidor.pk] = oficio
    for oficio, equipe in zip(oficios, equipes):
        motorista = equipe.motorista
        if motorista is None or motorista in equipe.servidores:
            continue
        origem = onde.get(motorista.pk)
        if origem is not None and origem.numero and origem.ano:
            oficio.motorista_oficio_referencia = f"{origem.numero}/{origem.ano}"
            oficio.motorista_protocolo_ref = origem.protocolo or ""
            oficio.save(update_fields=["motorista_oficio_referencia", "motorista_protocolo_ref", "atualizado_em"])


def _criar_ordem(viagem, oficios, equipes):
    from viagens_ordens.models import OrdemServico

    from .services import semente_de_documentos

    semente = semente_de_documentos(viagem)
    motoristas = [e.motorista for e in equipes if e.motorista is not None]
    ordem = OrdemServico(
        viagem=viagem,
        data_evento_inicio=semente["data_inicio"],
        data_evento_fim=semente["data_fim"] or semente["data_inicio"],
        motivo=semente["motivo"] or "",
        motorista_equipe=motoristas[0] if motoristas else None,
    )
    ordem.save()
    ordem.definir_destinos([cidade.pk for cidade, _ in semente["destinos"] if cidade is not None])
    servidores = []
    for equipe in equipes:
        for servidor in equipe.servidores:
            if servidor not in servidores:
                servidores.append(servidor)
    ordem.servidores.set(servidores)
    ordem.oficios.set(oficios)
    return ordem


@transaction.atomic
def gerar_pacote(viagem, equipes, *, gerar_ordem=True, gerar_plano=True, gerar_termos=True, unidade_emissora=None):
    """Cria os documentos da viagem a partir das equipes. `PacoteInvalido` se não fecham."""
    from viagens_planos.services import criar_plano_rascunho

    from .models import Viagem

    equipes = completar_com_motoristas(viagem, equipes)
    erros = conferir_equipes(viagem, equipes)
    if erros:
        raise PacoteInvalido(erros)
    resultado = ResultadoDoPacote()
    roteiro = _roteiro_da_viagem(viagem)
    if roteiro is None:
        resultado.avisos.append("A viagem ainda não tem roteiro: os ofícios saíram sem roteiro e sem diárias.")
    for equipe in equipes:
        resultado.oficios.append(
            _criar_oficio(viagem, equipe, roteiro, com_termos=gerar_termos, unidade_emissora=unidade_emissora)
        )
    _referenciar_motorista_de_outro_oficio(viagem, resultado.oficios, equipes)

    if gerar_ordem:
        existente = viagem.ordens_servico.filter(cancelado=False).first()
        if existente is None:
            resultado.ordem = _criar_ordem(viagem, resultado.oficios, equipes)
        else:
            resultado.avisos.append(f"A viagem já tinha a {existente.numero_formatado}; ela não foi alterada.")
    if gerar_plano:
        existente = viagem.planos_trabalho.filter(cancelado=False).first()
        if existente is None:
            resultado.plano = criar_plano_rascunho(viagem)
        else:
            resultado.avisos.append(f"A viagem já tinha o Plano de Trabalho {existente.numero_formatado}; ele não foi alterado.")

    if viagem.status in (Viagem.STATUS_RASCUNHO, Viagem.STATUS_EM_PREPARACAO):
        viagem.status = Viagem.STATUS_DOCUMENTOS_GERADOS
        viagem.save(update_fields=["status", "atualizado_em"])
    return resultado
