"""Gravação da identificação do plano (cartão 1) numa transação só.

A contextualização nasce do destino e do programa, e o valor da diária do
período: gravar um sem o outro deixaria o documento contradizendo a si mesmo.
"""

from django.db import transaction

from .services import atualizar_snapshot_diarias, sincronizar_textos_padrao

#: Os interruptores de texto automático. A tela do plano não os oferece — o
#: POST nunca os muda —; quem os desliga é o editor documental, quando alguém
#: reescreve o texto no documento, e é ele quem os religa (apagar o texto ou
#: voltar ao automático). A gravação da identificação refaz só os textos que
#: continuam automáticos: o escrito no documento fica.
FLAGS_AUTOMATICAS = ("contextualizacao_auto", "coordenacao_auto", "consideracao_auto")


@transaction.atomic
def salvar_identificacao(form):
    plano = form.save()
    campos_texto = sincronizar_textos_padrao(plano)
    plano.save(update_fields=[*campos_texto, "atualizado_em"])
    if plano.saida_sede_data and plano.chegada_sede_data:
        atualizar_snapshot_diarias(plano)
    return plano
