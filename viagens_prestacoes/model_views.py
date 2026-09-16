"""Modelos de texto do relatório técnico.

A tela própria saiu: os modelos são um catálogo no padrão dos cadastros
(`viagens_cadastros:lista` com o slug `modelos-texto-rt`, na seção Modelos).
As rotas antigas continuam respondendo e levam para lá.
"""

from urllib.parse import urlencode

from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.views.decorators.http import require_POST

from core.retorno import next_valido, voltar_para
from viagens_cadastros.permissions import acesso_ao_modulo

from .models import ModeloTextoRelatorioTecnico
from .services import excluir_modelo_texto

SLUG = "modelos-texto-rt"


def _lista(request):
    url = reverse("viagens_cadastros:lista", args=[SLUG])
    retorno = next_valido(request)
    return f"{url}?{urlencode({'next': retorno})}" if retorno else url


@acesso_ao_modulo
def modelos_index(request):
    return redirect(_lista(request))


@acesso_ao_modulo
def modelo_editar(request, pk):
    get_object_or_404(ModeloTextoRelatorioTecnico, pk=pk)
    return redirect(reverse("viagens_cadastros:editar", args=[SLUG, pk]))


@acesso_ao_modulo
@require_POST
def modelo_excluir(request, pk):
    modelo = get_object_or_404(ModeloTextoRelatorioTecnico, pk=pk)
    excluir_modelo_texto(modelo)
    messages.success(request, "Modelo excluído.")
    return redirect(voltar_para(request, reverse("viagens_cadastros:lista", args=[SLUG])))
