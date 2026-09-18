"""Gravação da identificação do plano (cartão 1) numa transação só.

A contextualização nasce do destino e do programa, e o valor da diária do
período: gravar um sem o outro deixaria o documento contradizendo a si mesmo.
"""

from django.db import transaction

from .services import atualizar_snapshot_diarias, sincronizar_textos_padrao

#: Os interruptores de texto automático. A tela não os oferece mais — os três
#: textos são sempre derivados do programa, do destino e dos coordenadores —,
#: então a gravação os religa em vez de ler o que veio no POST: um pedido
#: forjado (ou guardado de uma versão antiga da tela) congelaria o texto num
#: plano que já não tem tela para descongelá-lo.
FLAGS_AUTOMATICAS = ("contextualizacao_auto", "coordenacao_auto", "consideracao_auto")


@transaction.atomic
def salvar_identificacao(form):
    plano = form.save()
    for flag in FLAGS_AUTOMATICAS:
        setattr(plano, flag, True)
    campos_texto = sincronizar_textos_padrao(plano)
    plano.save(update_fields=[*{*campos_texto, *FLAGS_AUTOMATICAS}, "atualizado_em"])
    if plano.saida_sede_data and plano.chegada_sede_data:
        atualizar_snapshot_diarias(plano)
    return plano
