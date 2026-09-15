from django.db.models.signals import m2m_changed
from django.db.models.signals import post_save
from django.dispatch import receiver

def _sincronizar_prestacao_servidores(oficio):
    """Reconcilia os ``PrestacaoServidor`` do ofício com a equipe atual.

    A prestação (uma por ofício) passa a refletir exatamente ``oficio.servidores``:
    cria uma linha para cada servidor que ainda não tem e — crucialmente — remove
    as linhas de servidores que saíram do ofício. Sem essa remoção, servidores
    apenas "semeados" no wizard de um novo ofício (que herda a equipe do ofício
    anterior do mesmo evento) e depois retirados continuariam aparecendo na
    prestação, misturando equipes entre ofícios.

    ``DB-06``: "remover" aqui deixou de significar ``DELETE``. Quem sai levando
    trabalho junto — comprovante de saque, número da solicitação — é apenas marcado (``PrestacaoServidor.sair_da_equipe``), some
    das telas e volta inteiro se o servidor voltar para a equipe. Quem não tem
    nada coletado continua sendo apagado, senão a prestação voltaria a exibir a
    equipe de outro ofício, que é o defeito que este sinal resolve.
    """
    from .models import PrestacaoContas
    from .models import PrestacaoServidor
    if oficio.cancelado:
        return
    prestacao, _ = PrestacaoContas.objects.get_or_create(oficio=oficio)
    ids_atuais = set(oficio.servidores.values_list('pk', flat=True))
    saindo = PrestacaoServidor.todos.filter(prestacao=prestacao, removida_em__isnull=True).exclude(servidor_id__in=ids_atuais)
    for servidor_prestacao in saindo:
        servidor_prestacao.sair_da_equipe()
    for servidor_id in sorted(ids_atuais):
        servidor_prestacao, criada = PrestacaoServidor.todos.get_or_create(prestacao=prestacao, servidor_id=servidor_id)
        if not criada:
            servidor_prestacao.voltar_para_equipe()

def connect_signals():
    from viagens_oficios.models import Oficio

    @receiver(post_save, sender=Oficio, dispatch_uid='prestacoes_contas.criar_ao_gerar_oficio', weak=False)
    def criar_prestacoes_para_oficio_gerado(sender, instance, **kwargs):
        _sincronizar_prestacao_servidores(instance)

    @receiver(m2m_changed, sender=Oficio.servidores.through, dispatch_uid='prestacoes_contas.sincronizar_ao_alterar_servidores', weak=False)
    def sincronizar_prestacoes_ao_alterar_servidores(sender, instance, action, reverse=False, pk_set=None, **kwargs):
        if reverse:
            if action == 'pre_clear':
                instance._prestacoes_oficios_antes_clear = list(Oficio.objects.filter(servidores=instance).values_list('pk', flat=True))
            if action in ('post_add', 'post_remove', 'post_clear'):
                ids = pk_set if action != 'post_clear' else getattr(instance, '_prestacoes_oficios_antes_clear', [])
                for oficio in Oficio.objects.filter(pk__in=ids or []):
                    _sincronizar_prestacao_servidores(oficio)
        elif action in ('post_add', 'post_remove', 'post_clear'):
            _sincronizar_prestacao_servidores(instance)
