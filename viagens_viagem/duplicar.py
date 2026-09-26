"""Repetir uma viagem em outra data (m076).

Ações como "PCPR na Comunidade" e "Justiça no Bairro" se repetem com a mesma
equipe, viatura, roteiro e plano, mudando a data e, às vezes, a cidade. Aqui a
viagem é copiada com os documentos dela — roteiros, ofícios, planos de
trabalho, ordens de serviço e termos —, todos em rascunho e com as datas
deslocadas pela diferença entre a data nova e a antiga.

Nunca se copia o que identifica a edição anterior: números (ofício, plano e
OS recebem número novo pela numeração de cada um), protocolos, documentos
gerados e assinados, justificativas e prestações. Cancelados ficam de fora.

Com uma cidade nova, ela substitui o destino principal em todos os
documentos; o roteiro perde a rota calculada (as distâncias eram da cidade
antiga) e é recalculado ao abrir.
"""

from datetime import date, datetime, timedelta

from django.db import models, transaction

# Campos que são da edição anterior ou do próprio registro, nunca da cópia.
_SEMPRE_FORA = {
    "id", "criado_em", "atualizado_em", "cancelado", "motivo_cancelamento",
    "cancelado_em", "legado_origem", "legado_pk",
}
# Datas que não são do evento: não se deslocam (e as de cima nem são copiadas).
_DATAS_FIXAS = {"data_criacao", "protocolo_criado_em", "rota_calculada_em"}


class ViagemSemData(ValueError):
    """Sem data na viagem (nem no roteiro) não há como deslocar o calendário."""


class Repeticao:
    def __init__(self, deslocamento, cidade_antiga=None, cidade_nova=None):
        self.deslocamento = deslocamento
        self.municipios = {}
        self.estados = {}
        if cidade_nova is not None and cidade_antiga is not None and cidade_antiga.pk != cidade_nova.pk:
            self.municipios[cidade_antiga.pk] = cidade_nova.pk
            if cidade_antiga.estado_id != cidade_nova.estado_id:
                self.estados[cidade_antiga.estado_id] = cidade_nova.estado_id

    @property
    def trocou_cidade(self):
        return bool(self.municipios)

    def preencher(self, original, fora=(), **valores):
        """Cópia de `original` (sem gravar) com datas deslocadas e a cidade trocada."""
        from cadastros.models import Estado, Municipio

        copia = type(original)()
        for campo in original._meta.concrete_fields:
            if campo.primary_key or campo.name in _SEMPRE_FORA or campo.name in fora or campo.name in valores:
                continue
            valor = getattr(original, campo.attname)
            if valor is not None and campo.name not in _DATAS_FIXAS and isinstance(valor, (date, datetime)):
                valor = valor + self.deslocamento
            if isinstance(campo, models.ForeignKey) and valor is not None:
                if campo.related_model is Municipio:
                    valor = self.municipios.get(valor, valor)
                elif campo.related_model is Estado:
                    valor = self.estados.get(valor, valor)
            setattr(copia, campo.attname, valor)
        for nome, valor in valores.items():
            setattr(copia, nome, valor)
        return copia

    def copiar(self, original, fora=(), **valores):
        copia = self.preencher(original, fora, **valores)
        copia.save()
        return copia

    def municipio(self, pk):
        return self.municipios.get(pk, pk)


def _data_de_referencia(viagem):
    if viagem.data_inicio:
        return viagem.data_inicio
    from django.utils import timezone

    from .selectors import listar_roteiros_da_viagem

    saidas = [r.saida_dt for r in listar_roteiros_da_viagem(viagem) if r.saida_dt and not r.cancelado]
    if saidas:
        return timezone.localdate(min(saidas))
    raise ViagemSemData("A viagem não tem data para servir de base. Informe o período antes de repetir.")


def _copiar_roteiro(rep, roteiro, viagem):
    from viagens_roteiros.models import Roteiro

    extras = {"viagem": viagem, "solicitacao": None, "status": Roteiro.Status.RASCUNHO}
    fora = {"resumo_diarias", "valor_diarias", "valor_diarias_extenso"}
    if rep.trocou_cidade:
        fora |= {"rota_geojson", "rota_distancia_km", "rota_duracao_min", "rota_fonte", "rota_assinatura", "rota_calculada_em"}
        extras["rota_status"] = Roteiro.RotaStatus.PENDENTE
    novo = rep.copiar(roteiro, fora=fora, **extras)
    for destino in roteiro.destinos.all():
        rep.copiar(destino, roteiro=novo)
    trocados = {"distancia_km", "duracao_min", "tempo_viagem_min", "rota_fonte", "rota_calculada_em"} if rep.trocou_cidade else set()
    for trecho in roteiro.trechos.all():
        rep.copiar(trecho, fora=trocados, roteiro=novo)
    # As parcelas descrevem o cálculo antigo; o novo sai da tabela vigente.
    from viagens_roteiros.services.calculo import recalcular_diarias
    from viagens_roteiros.services.diarias import RoteiroIncalculavel, SemTabelaDeDiarias

    try:
        recalcular_diarias(novo)
    except (SemTabelaDeDiarias, RoteiroIncalculavel):
        pass
    return novo


def _copiar_oficio(rep, oficio, viagem, roteiros):
    from viagens_oficios.models import Oficio
    from viagens_oficios.services import reservar_numero_oficio

    novo = rep.copiar(
        oficio,
        fora={
            "numero", "ano", "data_criacao", "protocolo", "protocolo_origem", "protocolo_situacao",
            "protocolo_criado_em", "motorista_oficio_referencia", "motorista_protocolo_ref",
            "retificado_documento", "complementar_documento",
        },
        viagem=viagem,
        roteiro_id=roteiros.get(oficio.roteiro_id, oficio.roteiro_id),
        status=Oficio.STATUS_RASCUNHO,
    )
    novo.servidores.set(oficio.servidores.all())
    novo.servidores_termo_autorizacao.set(oficio.servidores_termo_autorizacao.all())
    return reservar_numero_oficio(novo, ano=novo.data_criacao.year if novo.data_criacao else None)


def _copiar_plano(rep, plano, viagem):
    from viagens_planos.models import PlanoTrabalho
    from viagens_planos.services import salvar_plano_numerado

    # Montado sem gravar: a numeração do plano grava junto com o número.
    novo = rep.preencher(
        plano, fora={"numero", "ano", "sufixo_numero", "data_criacao", "evento_em_edicao"},
        viagem=viagem, status=PlanoTrabalho.STATUS_RASCUNHO,
    )
    salvar_plano_numerado(novo)
    novo.atividades_selecionadas.set(plano.atividades_selecionadas.all())
    eventos = {}
    for evento in plano.eventos.all():
        copia = rep.copiar(evento, plano=novo)
        copia.atividades_selecionadas.set(evento.atividades_selecionadas.all())
        for efetivo in evento.efetivos.all():
            rep.copiar(efetivo, evento=copia)
        eventos[evento.pk] = copia
    for destino in plano.destinos.all():
        rep.copiar(destino, plano=novo, evento=eventos.get(destino.evento_id))
    for efetivo in plano.efetivos.all():
        rep.copiar(efetivo, plano=novo)
    return novo


def _copiar_ordem(rep, ordem, viagem, oficios):
    novo = rep.copiar(ordem, fora={"numero", "ano"}, viagem=viagem)
    novo.definir_destinos([rep.municipio(m.pk) for m in ordem.destinos_em_ordem()])
    novo.servidores.set(ordem.servidores.all())
    novo.oficios.set([oficios.get(o.pk, o) for o in ordem.oficios.all()])
    return novo


def _copiar_termo(rep, termo, viagem, oficios):
    novo_oficio = oficios.get(termo.oficio_id)
    novo = rep.copiar(
        termo, viagem=viagem,
        oficio=novo_oficio if novo_oficio is not None else (termo.oficio if termo.oficio_id else None),
    )
    novo.servidores.set(termo.servidores.all())
    return novo


@transaction.atomic
def repetir_viagem(viagem, nova_data, nova_cidade=None):
    """Cria a viagem repetida em `nova_data` (e `nova_cidade`, se mudar). Devolve a nova."""
    from .models import Viagem
    from .selectors import listar_roteiros_da_viagem, listar_termos_da_viagem

    referencia = _data_de_referencia(viagem)
    rep = Repeticao(nova_data - referencia, viagem.destino_municipio, nova_cidade)
    nova = rep.copiar(viagem, status=Viagem.STATUS_RASCUNHO)
    if nova_cidade is not None:
        # Também quando a original não tinha destino principal: a nova passa a ter.
        nova.destino_municipio = nova_cidade
        nova.destino_estado_id = nova_cidade.estado_id
        nova.save(update_fields=["destino_municipio", "destino_estado", "atualizado_em"])
    nova.tipos.set(viagem.tipos.all())

    roteiros = {}
    for roteiro in listar_roteiros_da_viagem(viagem):
        if not roteiro.cancelado:
            roteiros[roteiro.pk] = _copiar_roteiro(rep, roteiro, nova).pk
    oficios = {}
    for oficio in viagem.oficios.filter(cancelado=False).order_by("pk"):
        oficios[oficio.pk] = _copiar_oficio(rep, oficio, nova, roteiros)
    for plano in viagem.planos_trabalho.filter(cancelado=False).order_by("pk"):
        _copiar_plano(rep, plano, nova)
    for ordem in viagem.ordens_servico.filter(cancelado=False).order_by("pk"):
        _copiar_ordem(rep, ordem, nova, oficios)
    for termo in listar_termos_da_viagem(viagem):
        if not termo.cancelado:
            _copiar_termo(rep, termo, nova, oficios)
    return nova


def deslocamento_em_dias(viagem, nova_data):
    """Quantos dias a repetição anda — para a mensagem da tela."""
    return (nova_data - _data_de_referencia(viagem)) // timedelta(days=1)
