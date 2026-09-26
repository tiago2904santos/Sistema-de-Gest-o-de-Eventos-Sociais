"""Triagem do e-mail na página inicial: soltar o pedido e cair na tela certa.

A pessoa solta o e-mail (ou o processo do eProtocolo em PDF) na faixa da
Central de módulos. `ler` lê a mensagem (`core.leitura.mensagem`), guarda o
original na pasta temporária sob o módulo "triagem" e responde com os
módulos candidatos (`core.preencher_por_email.candidatos_de_triagem`, que
soma os sinais do texto e a memória dos pedidos anteriores). Com um
candidato claro, o navegador vai direto para a tela nova daquele módulo com
`?email_origem=<token>`; a tela lê o e-mail sozinha ao abrir
(`origem_da_tela` + `data-pe-auto`) e oferece os outros módulos. Sem
candidato claro, a faixa mostra as opções para a pessoa escolher.

`encaminhar` é o clique numa opção: confere que o token é desta sessão e
manda para a tela nova do módulo escolhido.

Nada é gravado: o e-mail só vira registro quando o formulário é salvo, e o
que se aprende dele (`core.aprendizado`) é registrado nesse momento.
"""

from __future__ import annotations

import logging

from django.contrib.auth.decorators import login_required
from django.http import HttpResponseBadRequest, JsonResponse
from django.shortcuts import redirect
from django.utils import timezone
from django.views.decorators.http import require_POST

from core import preencher_por_email as pe
from core.leitura.mensagem import Mensagem

logger = logging.getLogger(__name__)

#: Confiança a partir da qual a página inicial abre a tela sem perguntar.
CONFIANCA_PARA_DECIDIR = 0.55


def _resumo(mensagem: Mensagem) -> dict:
    """O que a faixa mostra sobre o e-mail lido, antes de abrir a tela."""
    enviado = mensagem.enviado_em
    if enviado is not None and timezone.is_aware(enviado):
        enviado = timezone.localtime(enviado)
    quando, avisos = pe.quando_do_pedido(mensagem)
    pessoa = pe.quem_pede(mensagem)
    return {
        "assunto": mensagem.assunto_limpo[:200],
        "remetente": (mensagem.remetente or "")[:150],
        "enviado_em": f"{enviado:%d/%m/%Y %H:%M}" if enviado else "",
        "quando": f"{quando.inicio:%d/%m/%Y}" if quando else "",
        "quem": (pessoa.nome if pessoa else "")[:150],
        "avisos": [a for a in list(mensagem.avisos) + avisos if a][:4],
        "origem": mensagem.origem,
    }


@login_required
@require_POST
def ler(request):
    """Lê o e-mail solto na página inicial e diz para qual módulo ele parece ir."""
    try:
        mensagem, nome, dados = pe.ler_do_pedido(request)
    except pe.EmailRecusado as erro:
        return JsonResponse({"erro": str(erro)}, status=400)
    token = pe._guardar(request, pe.MODULO_TRIAGEM, nome, dados, mensagem)
    # Os candidatos com sinal e, depois, os outros módulos da pessoa (sem sinal, ela escolhe).
    opcoes = pe.opcoes_de_triagem(mensagem, request.user, token)
    sugerido = opcoes[0] if opcoes and opcoes[0]["confianca"] else None
    decidir = bool(sugerido) and sugerido["confianca"] >= CONFIANCA_PARA_DECIDIR
    logger.info(
        "Triagem de e-mail: origem=%s, %d opção(ões), sugerido=%s, decidir=%s.",
        mensagem.origem, len(opcoes), sugerido["modulo"] if sugerido else "-", decidir,
    )
    return JsonResponse({
        "token": token,
        "arquivo": nome,
        "resumo": _resumo(mensagem),
        "candidatos": opcoes,
        "sugerido": sugerido["modulo"] if sugerido else "",
        "decidir": decidir,
    })


@login_required
def encaminhar(request):
    """Abre a tela nova do módulo escolhido com o e-mail lido na página inicial."""
    token = (request.GET.get("token") or "").strip().lower()
    modulo = (request.GET.get("modulo") or "").strip()
    if modulo not in pe.MODULOS_TRIAGEM or modulo not in pe.modulos_de_triagem(request.user):
        return HttpResponseBadRequest("Módulo inválido.")
    if not pe.reencaminhar(request, token, modulo):
        return redirect("core:home")
    return redirect(f"{pe.url_da_tela_nova(modulo)}?email_origem={token}")
