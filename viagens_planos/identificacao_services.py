"""Gravação da identificação do plano (cartão 1) numa transação só.

A contextualização nasce do destino e do programa, e o valor da diária do
período: gravar um sem o outro deixaria o documento contradizendo a si mesmo.
"""

from django.db import transaction

from .services import atualizar_snapshot_diarias, sincronizar_textos_padrao

#: Campo de texto → interruptor que diz se ele ainda está no modo automático.
FLAGS_AUTOMATICAS = {
    "contextualizacao": "contextualizacao_auto",
    "coordenacao": "coordenacao_auto",
    "consideracao_final": "consideracao_auto",
}


def flags_automaticas(post):
    """Os três interruptores de texto automático; ausente conta como ligado."""
    return {flag: (post.get(flag, "1") or "0").strip() != "0" for flag in FLAGS_AUTOMATICAS.values()}


@transaction.atomic
def salvar_identificacao(form, *, flags):
    plano = form.save()
    for flag, ligado in flags.items():
        setattr(plano, flag, ligado)
    campos_texto = sincronizar_textos_padrao(plano)
    plano.save(update_fields=[*{*campos_texto, *flags}, "atualizado_em"])
    if plano.saida_sede_data and plano.chegada_sede_data:
        atualizar_snapshot_diarias(plano)
    return plano
