"""Serviço de notificações: registro interno (sino) + e-mail opcional.

O registro interno sempre acontece. O e-mail é enviado apenas para usuários
com e-mail cadastrado, após o commit da transação, e nunca derruba a
operação que o originou (fail_silently).
"""

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.mail import send_mail
from django.db import transaction

from .models import Notificacao


def usuarios_do_grupo(nome_grupo, exceto=None):
    """Usuários ativos de um grupo de perfil, opcionalmente excluindo um."""
    queryset = get_user_model().objects.filter(
        is_active=True, groups__name=nome_grupo
    )
    if exceto is not None:
        queryset = queryset.exclude(pk=exceto.pk)
    return queryset


def usuarios_ativos(exceto=None):
    """Todos os usuários ativos, opcionalmente excluindo um deles."""
    queryset = get_user_model().objects.filter(is_active=True)
    if exceto is not None:
        queryset = queryset.exclude(pk=exceto.pk)
    return queryset


def notificar(usuarios, titulo, mensagem="", link="", solicitacao=None, exceto=None):
    """Cria notificações internas e agenda os e-mails correspondentes.

    `exceto` retira o autor da ação da lista: ninguém precisa ser avisado do
    que acabou de fazer. `solicitacao` vincula a notificação à origem, para
    que ela desapareça junto quando a solicitação é excluída.
    """
    destinatarios = {
        usuario.pk: usuario
        for usuario in usuarios
        if usuario and usuario.is_active and usuario != exceto
    }.values()
    if not destinatarios:
        return []

    notificacoes = Notificacao.objects.bulk_create(
        Notificacao(
            usuario=usuario,
            solicitacao=solicitacao,
            titulo=titulo,
            mensagem=mensagem,
            link=link,
        )
        for usuario in destinatarios
    )

    emails = sorted({u.email for u in destinatarios if u.email})
    if emails:
        corpo = mensagem or titulo
        if link:
            corpo = f"{corpo}\n\nAcesse: {link}"

        def enviar_emails():
            send_mail(
                subject=f"[Eventos Sociais] {titulo}",
                message=corpo,
                from_email=getattr(settings, "DEFAULT_FROM_EMAIL", None),
                recipient_list=emails,
                fail_silently=True,
            )

        transaction.on_commit(enviar_emails)

    return notificacoes
