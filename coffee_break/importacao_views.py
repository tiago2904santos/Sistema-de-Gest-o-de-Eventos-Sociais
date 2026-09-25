"""Telas de "Importar processo de pagamento" (ver `importacao_processo`).

- `importar_processo` (POST): recebe o PDF do processo — da lista de
  solicitações (o sistema descobre de quem é) ou da etapa 3 / do ⋮ de uma
  solicitação (`solicitacao`, a âncora) —, lê fora de transação e, se a
  identificação for segura, aplica na hora; senão guarda o arquivo para a
  conferência;
- `importacao_processo` (GET): a conferência (antes) ou o resultado (depois);
- `aplicar_importacao_processo` (POST): relê o processo com as escolhas da
  conferência e grava;
- `descartar_importacao_processo` (POST): desiste sem gravar.

Sem modelo novo: o PDF que espera a conferência fica numa pasta temporária do
servidor, apontado por um token na sessão (o padrão da importação de
planilha), e sai quando é aplicado, descartado ou esquecido por um dia. O
resultado fica na sessão para a tela; o registro permanente é o histórico de
cada solicitação.

Permissão: o módulo (`acesso_ao_modulo`) — a mesma de anexar a nota fiscal e
as certidões. Solicitação cancelada ou concluída não muda.
"""

from __future__ import annotations

import logging
import re
import tempfile
import time
import uuid
from pathlib import Path

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.shortcuts import redirect
from django.shortcuts import render
from django.urls import reverse
from django.views.decorators.http import require_POST

from core.errors import capture
from core.leitura.pdf import ArquivoIlegivel
from core.retorno import voltar_para

from . import importacao_processo as importacao
from .models import SolicitacaoCoffeeBreak
from .permissions import acesso_ao_modulo

__all__ = [
    "aplicar_importacao_processo",
    "descartar_importacao_processo",
    "importacao_processo",
    "importar_processo",
]

_CHAVE_SESSAO = "coffee_break_processos"
#: Quantas importações cada sessão guarda (a mais antiga sai, com o arquivo).
_MAX_NA_SESSAO = 5
#: Arquivo esperando conferência esquecido (tela fechada) some depois disto.
_VALIDADE_SEGUNDOS = 24 * 60 * 60
_R_TOKEN = re.compile(r"^[0-9a-f]{32}$")


# ─────────────────────────────────────────────────────────────────
# O que fica entre a leitura e a aplicação
# ─────────────────────────────────────────────────────────────────

def _pasta() -> Path:
    pasta = Path(tempfile.gettempdir()) / "coffee-break-processos"
    pasta.mkdir(exist_ok=True)
    return pasta


def _apagar_arquivo(entrada: dict) -> None:
    nome = (entrada or {}).get("arquivo") or ""
    if _R_TOKEN.match(nome.removesuffix(".pdf")):
        (_pasta() / nome).unlink(missing_ok=True)


def _limpar_esquecidos() -> None:
    limite = time.time() - _VALIDADE_SEGUNDOS
    for arquivo in _pasta().glob("*.pdf"):
        try:
            if arquivo.stat().st_mtime < limite:
                arquivo.unlink(missing_ok=True)
        except OSError:
            continue


def _guardar(request, *, nome, hash_sha256, ancora, tela, dados=None, resultado=None) -> str:
    """Guarda a importação na sessão (e o PDF, se ainda vai ser aplicado); devolve o token."""
    token = uuid.uuid4().hex
    entrada = {
        "nome": nome,
        "hash": hash_sha256,
        "ancora": ancora.pk if ancora is not None else None,
        "tela": tela,
        "resultado": resultado,
        "arquivo": "",
        "criado": time.time(),
    }
    if dados is not None:
        _limpar_esquecidos()
        entrada["arquivo"] = f"{token}.pdf"
        (_pasta() / entrada["arquivo"]).write_bytes(dados)
    pendentes = dict(request.session.get(_CHAVE_SESSAO) or {})
    pendentes[token] = entrada
    for velho in sorted(pendentes, key=lambda t: pendentes[t].get("criado", 0))[:-_MAX_NA_SESSAO]:
        _apagar_arquivo(pendentes.pop(velho))
    request.session[_CHAVE_SESSAO] = pendentes
    return token


def _entrada(request, token: str) -> dict | None:
    if not _R_TOKEN.match(token or ""):
        return None
    return (request.session.get(_CHAVE_SESSAO) or {}).get(token)


def _atualizar(request, token: str, **campos) -> None:
    pendentes = dict(request.session.get(_CHAVE_SESSAO) or {})
    if token in pendentes:
        pendentes[token] = {**pendentes[token], **campos}
        request.session[_CHAVE_SESSAO] = pendentes


def _caminho(entrada: dict) -> Path | None:
    """O PDF que espera a conferência, se ainda estiver na pasta temporária."""
    nome = entrada.get("arquivo") or ""
    if not _R_TOKEN.match(nome.removesuffix(".pdf")):
        return None
    caminho = _pasta() / nome
    return caminho if caminho.is_file() else None


def _dados_do_arquivo(entrada: dict) -> bytes | None:
    caminho = _caminho(entrada)
    return caminho.read_bytes() if caminho is not None else None


def _ancora(pk) -> SolicitacaoCoffeeBreak | None:
    try:
        return SolicitacaoCoffeeBreak.objects.select_related("lote__contrato__fornecedor").get(pk=int(pk))
    except (TypeError, ValueError, SolicitacaoCoffeeBreak.DoesNotExist):
        return None


def _mensagens_do_resultado(request, resultado: importacao.Resultado) -> None:
    messages.success(request, resultado.resumo)
    pendentes = resultado.pendencias or any(s["pendente"] for s in resultado.solicitacoes)
    if pendentes:
        messages.warning(request, "Há pontos para você conferir: veja “Ficou para você” abaixo.")


# ─────────────────────────────────────────────────────────────────
# Views
# ─────────────────────────────────────────────────────────────────

@acesso_ao_modulo
@require_POST
def importar_processo(request):
    """Recebe o PDF do processo; aplica sozinho quando a identificação é segura."""
    voltar = voltar_para(request, reverse("coffee_break:solicitacoes"))
    ancora = _ancora(request.POST.get("solicitacao")) if request.POST.get("solicitacao") else None
    arquivo = request.FILES.get("arquivo")
    if arquivo is None:
        messages.error(request, "Escolha o PDF do processo de pagamento.")
        return redirect(voltar)
    nome = Path(getattr(arquivo, "name", "") or "processo.pdf").name
    try:
        importacao.validar_arquivo(arquivo)
    except ValidationError as erro:
        messages.error(request, " ".join(erro.messages))
        return redirect(voltar)
    arquivo.seek(0)
    dados = arquivo.read()

    # A leitura roda fora de transação: só a gravação abre a sua.
    try:
        plano = importacao.analisar(dados, nome, ancora=ancora)
    except ArquivoIlegivel:
        messages.error(request, "Não foi possível abrir o PDF do processo.")
        return redirect(voltar)
    except Exception as exc:  # leitura nova quebrando não vira 500
        capture(exc, "coffee_break.importar_processo.analisar", level=logging.ERROR)
        messages.error(request, "Não foi possível ler o processo. Tente de novo ou anexe a nota pela etapa 2.")
        return redirect(voltar)
    if not plano.reconhecido:
        messages.error(
            request,
            "Este PDF não parece um processo de pagamento do Coffee Break: não achei o nº do processo, o ofício nem notas fiscais.",
        )
        return redirect(voltar)

    if plano.seguro:
        resultado = importacao.aplicar(plano, dados, request.user)
        token = _guardar(
            request, nome=nome, hash_sha256=plano.hash_sha256, ancora=ancora,
            tela=plano.para_tela(), resultado=resultado.para_json(),
        )
        _mensagens_do_resultado(request, resultado)
    else:
        token = _guardar(request, nome=nome, hash_sha256=plano.hash_sha256, ancora=ancora, tela=plano.para_tela(), dados=dados)
        messages.info(request, "Confira de quem é o processo e clique em Aplicar: nada foi gravado ainda.")
    return redirect("coffee_break:importacao_processo", token=token)


@acesso_ao_modulo
def importacao_processo(request, token):
    """A conferência (antes de aplicar) ou o resultado (depois), na mesma tela."""
    entrada = _entrada(request, token)
    if entrada is None:
        messages.warning(request, "Esta importação não está mais aberta. O que foi gravado está no histórico de cada solicitação.")
        return redirect("coffee_break:solicitacoes")
    tela = entrada.get("tela") or {}
    resultado = entrada.get("resultado")
    ancora = _ancora(entrada.get("ancora")) if entrada.get("ancora") else None
    candidatas = tela.get("candidatas") or []
    opcoes_nota = [{"valor": "0", "rotulo": "Não anexar"}] + [
        {"valor": str(c["pk"]), "rotulo": c["rotulo"]} for c in candidatas
    ]
    return render(
        request,
        "pages/coffee_break/importacao_processo.html",
        {
            "breadcrumb": [
                {"label": "Coffee Break", "url": reverse("coffee_break:painel")},
                {"label": "Solicitações", "url": reverse("coffee_break:solicitacoes")},
                {"label": "Importar processo de pagamento"},
            ],
            "token": token,
            "tela": tela,
            "resultado": resultado,
            "aplicada": bool(resultado),
            "arquivo_disponivel": _caminho(entrada) is not None,
            "opcoes_solicitacoes": [
                {
                    "valor": str(c["pk"]),
                    "rotulo": c["rotulo"],
                    "dica": " · ".join(p for p in [c.get("dica", ""), "; ".join(c.get("evidencias") or [])] if p),
                    "icone": "coffee",
                    "marcado": c.get("marcada"),
                }
                for c in candidatas
            ],
            "opcoes_nota": opcoes_nota,
            "ancora": ancora,
            "voltar_url": reverse("coffee_break:etapa_protocolo", args=[ancora.pk]) if ancora else reverse("coffee_break:solicitacoes"),
            "importacao_limite_mb": importacao.limite_de_bytes() // (1024 * 1024),
        },
    )


@acesso_ao_modulo
@require_POST
def aplicar_importacao_processo(request, token):
    """Grava com as escolhas da conferência (relê o processo com elas)."""
    entrada = _entrada(request, token)
    if entrada is None:
        messages.warning(request, "Esta importação não está mais aberta: envie o processo de novo.")
        return redirect("coffee_break:solicitacoes")
    if entrada.get("resultado"):
        return redirect("coffee_break:importacao_processo", token=token)
    dados = _dados_do_arquivo(entrada)
    if dados is None:
        messages.error(request, "O arquivo desta importação expirou: envie o processo de novo.")
        return redirect("coffee_break:solicitacoes")
    ancora = _ancora(entrada.get("ancora")) if entrada.get("ancora") else None
    escolhas = importacao.Escolhas.do_formulario(request.POST)
    try:
        plano = importacao.analisar(dados, entrada.get("nome") or "", ancora=ancora, escolhas=escolhas)
    except Exception as exc:
        capture(exc, "coffee_break.importar_processo.aplicar", level=logging.ERROR)
        messages.error(request, "Não foi possível ler o processo de novo. Envie o arquivo outra vez.")
        return redirect("coffee_break:importacao_processo", token=token)
    if not plano.solicitacoes:
        _atualizar(request, token, tela=plano.para_tela())
        messages.error(request, "Marque ao menos uma solicitação (ou informe o nº da OS) para aplicar.")
        return redirect("coffee_break:importacao_processo", token=token)
    resultado = importacao.aplicar(plano, dados, request.user)
    _apagar_arquivo(entrada)
    _atualizar(request, token, tela=plano.para_tela(), resultado=resultado.para_json(), arquivo="")
    _mensagens_do_resultado(request, resultado)
    return redirect("coffee_break:importacao_processo", token=token)


@acesso_ao_modulo
@require_POST
def descartar_importacao_processo(request, token):
    """Desiste da importação: nada é gravado e o arquivo sai do servidor."""
    pendentes = dict(request.session.get(_CHAVE_SESSAO) or {})
    entrada = pendentes.pop(token, None) if _R_TOKEN.match(token or "") else None
    if entrada is not None:
        _apagar_arquivo(entrada)
        request.session[_CHAVE_SESSAO] = pendentes
        if not entrada.get("resultado"):
            messages.info(request, "Importação descartada: nada foi gravado.")
    ancora = _ancora((entrada or {}).get("ancora")) if (entrada or {}).get("ancora") else None
    if ancora is not None:
        return redirect("coffee_break:etapa_protocolo", pk=ancora.pk)
    return redirect("coffee_break:solicitacoes")
