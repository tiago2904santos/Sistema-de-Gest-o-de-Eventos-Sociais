"""Para onde o usuário volta depois de salvar (`NOVO-15`).

O sistema já sabe fazer a coisa certa em alguns lugares: você está montando um
ofício, precisa de um servidor que não existe, clica em "novo servidor", salva, e
**volta para o ofício que estava fazendo**. O mecanismo é um `?next=` na URL do
formulário, que a view honra no redirect pós-salvamento.

O problema é que isso estava reimplementado em **8 helpers espalhados por 5
arquivos** — `cadastros/views.py` tinha três — e só **14 dos 128** redirects de
view honravam o `next`. Nos outros o usuário era jogado numa lista fixa e tinha
que se reencontrar.

Este módulo é o dono único. Nesta primeira entrega ele **não muda comportamento
nenhum**: é a mesma função que já existia, cinco vezes byte a byte igual.

## O que este módulo deliberadamente não faz

Não trata passo de wizard. Um wizard salva e vai para o **passo seguinte**, não
para trás — são duas perguntas diferentes, e confundi-las quebraria o fluxo de
ofícios, plano de trabalho e prestações. O wizard simplesmente não usa isto.

## Segurança

`?next=` é entrada do usuário que vira `Location:` de um redirect. Sem validação
é *open redirect*: um link `?next=https://sitemalicioso/` levaria a vítima para
fora carregando a credibilidade do domínio. Todo caminho aqui passa por
`url_has_allowed_host_and_scheme`, restrito ao host da requisição e respeitando
HTTPS — igual às cópias que este módulo substitui.
"""

from __future__ import annotations

from urllib.parse import urlencode

from django.http import HttpRequest
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme


def _e_interno(request: HttpRequest, url: str) -> bool:
    return bool(url) and url_has_allowed_host_and_scheme(
        url,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    )


def voltar_para(request: HttpRequest, fallback: str) -> str:
    """A URL para onde o usuário deve voltar depois de salvar.

    Lê o `?next=` do POST primeiro — o formulário o reenvia num campo oculto — e
    do GET depois, que é como a tela foi aberta. Sem `next`, ou com `next`
    apontando para fora do host, devolve o `fallback`.
    """
    candidato = request.POST.get("next") or request.GET.get("next") or ""
    return candidato if _e_interno(request, candidato) else fallback


def next_valido(request: HttpRequest) -> str:
    """O `?next=` validado, ou string vazia.

    Sem fallback, ao contrário de `voltar_para`: serve para os casos em que "não
    tem retorno" precisa ser distinguível de "retorna para a lista" — é como
    `cadastros` decide se exibe o botão de voltar.
    """
    return voltar_para(request, "")


def com_next(url: str, next_url: str) -> str:
    """Anexa `?next=` a uma URL, quando há retorno a preservar."""
    if not next_url:
        return url
    separador = "&" if "?" in url else "?"
    return f"{url}{separador}{urlencode({'next': next_url})}"


def url_de_cadastro(url_name: str, next_url: str, *args) -> str:
    """URL de um formulário de cadastro que deve voltar para `next_url`.

    É o que faz o "novo servidor" dentro do ofício levar o usuário de volta ao
    ofício depois de salvar.
    """
    base = reverse(url_name, args=args) if args else reverse(url_name)
    return com_next(base, next_url)


def daqui(request: HttpRequest) -> str:
    """A tela atual, para passar como `next` ao formulário que vai se abrir.

    Usa `get_full_path`, que preserva a querystring: sem ela, voltar para uma
    lista filtrada perderia o filtro.
    """
    return request.get_full_path()
