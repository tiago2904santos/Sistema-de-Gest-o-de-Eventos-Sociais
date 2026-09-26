"""Página pública (sem login) do link do fornecedor — ver link_fornecedor.py."""

from datetime import date

from django.core.exceptions import ValidationError
from django.shortcuts import redirect, render
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import csrf_protect
from django.views.decorators.http import require_http_methods

from core import limite

from . import link_fornecedor
from .models import TIPO_ENVIO_NOTA, TipoCertidao


def _invalido(request, status=404):
    """Mesmo aviso para token inexistente, expirado ou revogado: quem tenta
    adivinhar não aprende nada sobre qual é o caso."""
    return limite.cabecalhos_de_pagina_com_token(
        render(request, "pages/publico/fornecedor_invalido.html", status=status)
    )


@never_cache
@csrf_protect
@require_http_methods(["GET", "POST"])
def envio(request, token):
    ip = limite.ip_do_cliente(request)
    if limite.excedeu("fornecedor_invalidos", ip, link_fornecedor.limite_de_tokens_invalidos()):
        return _invalido(request, status=429)
    link = link_fornecedor.link_do_token(token)
    if link is None:
        limite.somar("fornecedor_invalidos", ip, link_fornecedor.JANELA_LIMITE)
        return _invalido(request)

    erro = ""
    if request.method == "POST":
        if limite.excedeu("fornecedor_envios", link.pk, link_fornecedor.limite_de_envios()) or limite.excedeu(
            "fornecedor_envios_ip", ip, link_fornecedor.limite_de_envios()
        ):
            return _invalido(request, status=429)
        limite.somar("fornecedor_envios", link.pk, link_fornecedor.JANELA_LIMITE)
        limite.somar("fornecedor_envios_ip", ip, link_fornecedor.JANELA_LIMITE)
        tipo = request.POST.get("tipo", "")
        arquivo = request.FILES.get("arquivo")
        try:
            if arquivo is None:
                raise ValidationError("Escolha o arquivo em PDF.")
            if tipo == TIPO_ENVIO_NOTA:
                recebido = link_fornecedor.receber_nota(link, arquivo)
            elif tipo in TipoCertidao.values:
                texto = (request.POST.get("validade") or "").strip()
                try:
                    informada = date.fromisoformat(texto) if texto else None
                except ValueError as exc:
                    raise ValidationError("Data de validade inválida.") from exc
                recebido = link_fornecedor.receber_certidao(link, tipo, arquivo, informada)
            else:
                raise ValidationError("Escolha o que está enviando.")
        except ValidationError as exc:
            erro = " ".join(exc.messages)
        else:
            request.session["fornecedor_recebido"] = {
                "o_que": recebido.get_tipo_display(),
                "avisos": recebido.lista_avisos,
            }
            return redirect(request.path)

    confirmacao = request.session.pop("fornecedor_recebido", None) if request.method == "GET" else None
    return limite.cabecalhos_de_pagina_com_token(
        render(
            request,
            "pages/publico/fornecedor_envio.html",
            {
                "resumo": link_fornecedor.resumo_publico(link),
                "tipos_certidao": TipoCertidao.choices,
                "tipo_nota": TIPO_ENVIO_NOTA,
                "erro": erro,
                "confirmacao": confirmacao,
            },
            status=400 if erro else 200,
        )
    )
