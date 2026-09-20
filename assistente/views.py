"""Telas do assistente — finas de propósito.

A view não decide nada: recebe o texto, entrega ao orquestrador e mostra o que
voltou. O mesmo caminho serve ao WhatsApp, que trocaria só a entrada e a
saída — é o motivo de a regra não morar aqui.

O envio é POST + redirect (PRG) e funciona sem JavaScript: recarregar a página
não reenvia a mensagem, e a conversa continua legível num navegador simples,
que é o que se encontra em máquina de repartição.
"""

from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from viagens_cadastros.permissions import acesso_ao_modulo

from .ferramentas import disponiveis
from .llm import obter_interpretador
from .models import Conversa
from .orquestrador import AJUDA, responder

SUGESTOES = [
    "O que está pendente?",
    "Quais viagens desta semana?",
    "Quem vai para Maringá em setembro?",
]


def _conversa_atual(request):
    pk = request.session.get("assistente_conversa")
    if pk:
        conversa = Conversa.objects.filter(pk=pk, usuario=request.user).first()
        if conversa:
            return conversa
    conversa = Conversa.objects.create(usuario=request.user)
    request.session["assistente_conversa"] = conversa.pk
    return conversa


@login_required
@acesso_ao_modulo
def painel(request):
    conversa = _conversa_atual(request)
    interpretador = obter_interpretador()
    return render(
        request,
        "pages/assistente/painel.html",
        {
            "conversa": conversa,
            "mensagens": conversa.mensagens.all(),
            "pendente": conversa.pendente,
            "sugestoes": SUGESTOES,
            "ajuda": AJUDA,
            "ferramentas": disponiveis(request.user),
            "interpretador": interpretador.nome,
            "interpretador_remoto": interpretador.remoto,
        },
    )


@login_required
@acesso_ao_modulo
@require_POST
def enviar(request):
    texto = (request.POST.get("texto") or "").strip()
    if texto:
        conversa = _conversa_atual(request)
        responder(request.user, texto, conversa=conversa)
    return redirect("assistente:painel")


@login_required
@acesso_ao_modulo
@require_POST
def nova_conversa(request):
    """Recomeça do zero — a conversa anterior fica gravada, não é apagada."""
    conversa = Conversa.objects.create(usuario=request.user)
    request.session["assistente_conversa"] = conversa.pk
    return redirect("assistente:painel")
