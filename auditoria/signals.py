"""Auditoria automática por signals.

Todo CREATE/UPDATE/DELETE nos apps auditados vira um ``RegistroAuditoria``
com o delta dos campos, o usuário e o caminho da requisição corrente.
A escrita acontece em ``transaction.on_commit`` — uma transação abortada
nunca deixa rastro na trilha.
"""

from django.db import transaction
from django.db.models.signals import post_save, pre_delete, pre_save

from core.middleware import obter_requisicao_atual

APPS_AUDITADOS = {
    "accounts",
    "cadastros",
    "solicitacoes",
    "coffee_break",
    "demandas_eventos",
    # App novo entra aqui junto com o app, e não depois: a tabela de diárias é
    # dinheiro que vai para documento oficial, e alteração de valor sem rastro
    # é o tipo de coisa que só se descobre quando alguém contesta o pagamento.
    "viagens_cadastros",
}

# Modelos com trilha própria ou que só gerariam ruído.
MODELOS_EXCLUIDOS = {
    "auditoria.registroauditoria",
    "auditoria.logauditoria",
    "solicitacoes.historicosolicitacao",
    "core.notificacao",
}

# Nomes de campo que nunca entram em snapshot nem em delta.
CAMPOS_SENSIVEIS = {"password", "senha", "token", "access_token", "refresh_token"}

_ATRIBUTO_SNAPSHOT = "_auditoria_snapshot_anterior"


def _deve_auditar(sender):
    # Modelos históricos de migração não representam o estado real.
    if sender.__module__ == "__fake__":
        return False
    meta = sender._meta
    if meta.app_label not in APPS_AUDITADOS:
        return False
    return meta.label_lower not in MODELOS_EXCLUIDOS


def _serializar(valor):
    if valor is None or isinstance(valor, (bool, int, float, str)):
        return valor
    return str(valor)


def _snapshot(instancia):
    dados = {}
    for campo in instancia._meta.concrete_fields:
        if campo.name in CAMPOS_SENSIVEIS or campo.attname in CAMPOS_SENSIVEIS:
            continue
        dados[campo.name] = _serializar(campo.value_from_object(instancia))
    return dados


def _contexto_da_requisicao():
    requisicao = obter_requisicao_atual()
    if requisicao is None:
        return None, ""
    usuario = getattr(requisicao, "user", None)
    if usuario is not None and not usuario.is_authenticated:
        usuario = None
    return usuario, requisicao.path[:500]


def _agendar_registro(instancia, acao, alteracoes):
    from .models import RegistroAuditoria

    usuario, caminho = _contexto_da_requisicao()
    dados = {
        "usuario": usuario,
        "acao": acao,
        "modelo": instancia._meta.label_lower,
        "objeto_id": str(instancia.pk),
        "objeto_repr": str(instancia)[:255],
        "alteracoes": alteracoes,
        "caminho_requisicao": caminho,
    }
    transaction.on_commit(lambda: RegistroAuditoria.objects.create(**dados))


def _capturar_estado_anterior(sender, instance, **kwargs):
    if not _deve_auditar(sender):
        return
    anterior = None
    if instance.pk is not None:
        existente = sender._base_manager.filter(pk=instance.pk).first()
        if existente is not None:
            anterior = _snapshot(existente)
    setattr(instance, _ATRIBUTO_SNAPSHOT, anterior)


def _registrar_apos_salvar(sender, instance, created, **kwargs):
    if not _deve_auditar(sender):
        return
    from .models import RegistroAuditoria

    atual = _snapshot(instance)
    if created:
        _agendar_registro(instance, RegistroAuditoria.Acao.CRIACAO, {"novo": atual})
        return
    anterior = getattr(instance, _ATRIBUTO_SNAPSHOT, None)
    if anterior is None:
        # save() sem pre_save correspondente (ex.: pk forçado): trata como criação.
        _agendar_registro(instance, RegistroAuditoria.Acao.CRIACAO, {"novo": atual})
        return
    delta = {
        campo: {"antes": anterior.get(campo), "depois": valor}
        for campo, valor in atual.items()
        if anterior.get(campo) != valor
    }
    if not delta:
        return
    _agendar_registro(instance, RegistroAuditoria.Acao.ATUALIZACAO, delta)


def _registrar_antes_de_excluir(sender, instance, **kwargs):
    if not _deve_auditar(sender):
        return
    from .models import RegistroAuditoria

    _agendar_registro(
        instance, RegistroAuditoria.Acao.EXCLUSAO, {"antigo": _snapshot(instance)}
    )


def conectar_signals_de_auditoria():
    pre_save.connect(_capturar_estado_anterior, dispatch_uid="auditoria_pre_save")
    post_save.connect(_registrar_apos_salvar, dispatch_uid="auditoria_post_save")
    pre_delete.connect(_registrar_antes_de_excluir, dispatch_uid="auditoria_pre_delete")
