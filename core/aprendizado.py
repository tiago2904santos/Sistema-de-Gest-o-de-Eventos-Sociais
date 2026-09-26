"""A memória do sistema: cada pedido salvo a partir de um e-mail ensina o próximo.

Quando um formulário criado por "Preencher com um e-mail" (ou pela triagem
da página inicial) é salvo, `aprender` guarda em `core.MemoriaLeitura`:

- para onde foi o pedido deste remetente, do domínio dele e das palavras
  do assunto (a triagem passa a acertar o módulo de quem já pediu antes:
  a escola que pede palestra, a delegacia que pede coffee break);
- o que ficou em cada campo escolhido do formulário (município, solicitante,
  local, tipo do evento, temas…): da próxima vez, o que o texto do e-mail
  não disser vem daqui como sugestão ("aprendido de 3 pedidos anteriores
  deste remetente").

Tudo o que se grava já está no próprio registro salvo; nada do texto do
e-mail vai para a memória nem para o log. Aprender nunca derruba o salvar:
qualquer falha vira um aviso no log e o registro fica como está.
"""

from __future__ import annotations

import logging
import re
from collections import defaultdict
from datetime import date, datetime, time
from typing import Any, Iterable

from django.db import IntegrityError, transaction
from django.db.models import F, Model
from django.utils import timezone

from core.leitura.datas import dobrar

logger = logging.getLogger(__name__)

__all__ = [
    "DOMINIOS_GENERICOS",
    "aprender",
    "aprender_do_formulario",
    "pesos_de_triagem",
    "sugestoes_aprendidas",
]

#: Domínios de e-mail que não dizem nada sobre quem pede (todo mundo os usa);
#: o da própria PCPR também: coffee break, pauta e evento chegam todos dele.
DOMINIOS_GENERICOS = frozenset({
    "gmail.com", "hotmail.com", "outlook.com", "outlook.com.br", "yahoo.com", "yahoo.com.br",
    "live.com", "icloud.com", "uol.com.br", "bol.com.br", "terra.com.br", "globo.com", "msn.com",
    "pc.pr.gov.br", "policiacivil.pr.gov.br",
})
_PALAVRAS_VAZIAS = frozenset({
    "solicitacao", "solicitacoes", "pedido", "pedidos", "para", "sobre", "como", "este", "esta",
    "esse", "essa", "pela", "pelo", "com", "sem", "dos", "das", "nos", "nas", "que", "uma", "umas",
    "uns", "confirmacao", "informacao", "informacoes", "urgente", "importante", "agendamento",
    "fwd", "enc", "res", "re", "encaminhamento", "resposta", "assunto", "email", "e-mail",
})
_MAX_PALAVRAS = 12
_MAX_VEZES_CONTADAS = 50


def _dominio(email: str) -> str:
    email = (email or "").strip().lower()
    return email.rsplit("@", 1)[1] if "@" in email else ""


def _palavras(assunto: str) -> list[str]:
    """As palavras do assunto que valem como sinal (4+ letras, sem as vazias), sem repetir."""
    vistas: list[str] = []
    for palavra in re.findall(r"[a-z0-9-]{4,}", dobrar(assunto or "")):
        if palavra in _PALAVRAS_VAZIAS or palavra.isdigit() or palavra in vistas:
            continue
        vistas.append(palavra)
        if len(vistas) >= _MAX_PALAVRAS:
            break
    return vistas


def _chaves(remetente_email: str, assunto: str) -> list[tuple[str, str]]:
    """(tipo, chave) de tudo o que identifica este pedido para a memória."""
    from core.models import MemoriaLeitura as M

    chaves: list[tuple[str, str]] = []
    email = (remetente_email or "").strip().lower()
    if email and "@" in email:
        chaves.append((M.TIPO_REMETENTE, email[:200]))
        dominio = _dominio(email)
        if dominio and dominio not in DOMINIOS_GENERICOS:
            chaves.append((M.TIPO_DOMINIO, dominio[:200]))
    chaves.extend((M.TIPO_PALAVRA, palavra) for palavra in _palavras(assunto))
    return chaves


def _para_texto(valor: Any) -> tuple[str, str]:
    """(valor como o campo da tela espera, como mostrar) de um valor do formulário."""
    if valor is None or valor == "" or valor is False:
        return "", ""
    if valor is True:
        return "1", "Sim"
    if isinstance(valor, Model):
        return str(valor.pk), str(valor)
    if isinstance(valor, datetime):
        valor = timezone.localtime(valor) if timezone.is_aware(valor) else valor
        return valor.date().isoformat(), f"{valor:%d/%m/%Y}"
    if isinstance(valor, date):
        return valor.isoformat(), f"{valor:%d/%m/%Y}"
    if isinstance(valor, time):
        return valor.strftime("%H:%M"), valor.strftime("%H:%M")
    if hasattr(valor, "__iter__") and not isinstance(valor, str):
        itens = [_para_texto(item) for item in valor]
        itens = [item for item in itens if item[0]]
        if not itens:
            return "", ""
        return ",".join(v for v, _ in itens), ", ".join(e for _, e in itens)
    texto = " ".join(str(valor).split())
    return texto[:500], texto[:300]


def _contar(tipo: str, chave: str, modulo: str, campo: str = "", valor: str = "", exibir: str = "") -> None:
    from core.models import MemoriaLeitura as M

    atualizados = M.objects.filter(tipo=tipo, chave=chave, modulo=modulo, campo=campo, valor=valor).update(
        vezes=F("vezes") + 1, exibir=exibir or F("exibir"), atualizado_em=timezone.now()
    )
    if atualizados:
        return
    try:
        with transaction.atomic():
            M.objects.create(tipo=tipo, chave=chave, modulo=modulo, campo=campo, valor=valor, exibir=exibir)
    except IntegrityError:  # duas gravações no mesmo instante
        M.objects.filter(tipo=tipo, chave=chave, modulo=modulo, campo=campo, valor=valor).update(vezes=F("vezes") + 1)


def aprender(remetente_email: str, assunto: str, modulo: str, campos: dict[str, Any] | None = None) -> int:
    """Registra que um pedido de `remetente_email` (com este `assunto`) virou registro
    em `modulo`, com os valores dos `campos` {nome: valor do formulário}.

    Devolve quantas linhas da memória foram tocadas. Nunca levanta exceção.
    """
    try:
        chaves = _chaves(remetente_email, assunto)
        if not chaves or not modulo:
            return 0
        valores = {}
        for campo, bruto in (campos or {}).items():
            valor, exibir = _para_texto(bruto)
            if valor:
                valores[campo[:60]] = (valor, exibir)
        tocadas = 0
        for tipo, chave in chaves:
            _contar(tipo, chave, modulo)
            tocadas += 1
            if tipo == "palavra":
                continue  # palavra do assunto só aponta o módulo, não os campos
            for campo, (valor, exibir) in valores.items():
                _contar(tipo, chave, modulo, campo, valor, exibir)
                tocadas += 1
        logger.info("Memória de leitura: %d linha(s) em %s.", tocadas, modulo)
        return tocadas
    except Exception:  # aprender é um extra: nunca derruba o salvar
        logger.exception("Falha ao registrar a memória de leitura em %s.", modulo)
        return 0


def aprender_do_formulario(origem, modulo: str, form, campos: Iterable[str]) -> int:
    """`aprender` com o e-mail de origem (`core.preencher_por_email.Origem`) e o
    formulário válido salvo: pega de `cleaned_data` só os `campos` pedidos."""
    if origem is None or form is None:
        return 0
    dados = getattr(form, "cleaned_data", None) or {}
    valores = {campo: dados.get(campo) for campo in campos if campo in dados}
    return aprender(getattr(origem, "remetente_email", ""), getattr(origem, "assunto", ""), modulo, valores)


def _plural(n: int, um: str, varios: str) -> str:
    return f"{n} {um if n == 1 else varios}"


def pesos_de_triagem(mensagem) -> dict[str, list[tuple[float, str]]]:
    """{modulo: [(pontos, sinal)]} pelo que a memória sabe deste e-mail.

    O remetente pesa mais (2 por pedido anterior, até 6), o domínio menos
    (1,5 por pedido, até 4) e as palavras do assunto menos ainda (0,5 por
    pedido com a mesma palavra, até 3 no total).
    """
    from core.models import MemoriaLeitura as M

    pesos: dict[str, list[tuple[float, str]]] = defaultdict(list)
    try:
        chaves = _chaves(getattr(mensagem, "remetente_email", ""), getattr(mensagem, "assunto_limpo", ""))
        if not chaves:
            return {}
        linhas = M.objects.filter(campo="", valor="")
        # Uma consulta por tipo: chaves de tipos diferentes têm pesos diferentes.
        por_tipo: dict[str, dict[str, dict[str, int]]] = defaultdict(lambda: defaultdict(dict))
        for tipo in {t for t, _ in chaves}:
            valores = [c for t, c in chaves if t == tipo]
            for linha in linhas.filter(tipo=tipo, chave__in=valores).values("chave", "modulo", "vezes"):
                por_tipo[tipo][linha["modulo"]][linha["chave"]] = min(linha["vezes"], _MAX_VEZES_CONTADAS)
        for modulo, contagens in por_tipo.get(M.TIPO_REMETENTE, {}).items():
            vezes = sum(contagens.values())
            pesos[modulo].append((min(6.0, 2.0 * vezes), _plural(vezes, "pedido anterior deste remetente", "pedidos anteriores deste remetente")))
        for modulo, contagens in por_tipo.get(M.TIPO_DOMINIO, {}).items():
            vezes = sum(contagens.values())
            pesos[modulo].append((min(4.0, 1.5 * vezes), _plural(vezes, "pedido anterior deste domínio", "pedidos anteriores deste domínio")))
        for modulo, contagens in por_tipo.get(M.TIPO_PALAVRA, {}).items():
            vezes = sum(contagens.values())
            palavras = ", ".join(sorted(contagens, key=lambda p: -contagens[p])[:3])
            pesos[modulo].append((min(3.0, 0.5 * vezes), f"palavras do assunto já vistas aqui: {palavras}"))
    except Exception:
        logger.exception("Falha ao consultar a memória de leitura para a triagem.")
        return {}
    return dict(pesos)


def sugestoes_aprendidas(mensagem, modulo: str, ja_sugeridos: Iterable[str] = ()) -> dict[str, dict]:
    """{campo: {valor, exibir, confianca, trecho}} do que a memória sabe deste
    remetente para o módulo — só os campos fora de `ja_sugeridos`.

    O remetente exato manda; sem ele, o domínio (uma prefeitura, uma escola
    com vários e-mails). "M" quando o mesmo valor apareceu em 2+ pedidos do
    remetente; senão "B", só como sugestão.
    """
    from core.models import MemoriaLeitura as M

    ignorar = set(ja_sugeridos)
    saida: dict[str, dict] = {}
    try:
        email = (getattr(mensagem, "remetente_email", "") or "").strip().lower()
        if not email or "@" not in email:
            return {}
        fontes = [(M.TIPO_REMETENTE, email[:200], "deste remetente")]
        dominio = _dominio(email)
        if dominio and dominio not in DOMINIOS_GENERICOS:
            fontes.append((M.TIPO_DOMINIO, dominio[:200], f"de @{dominio}"))
        for tipo, chave, quem in fontes:
            linhas = (
                M.objects.filter(tipo=tipo, chave=chave, modulo=modulo)
                .exclude(campo="")
                .order_by("campo", "-vezes", "-atualizado_em")
            )
            for linha in linhas:
                if linha.campo in ignorar or linha.campo in saida:
                    continue
                if tipo == M.TIPO_DOMINIO and linha.vezes < 2:
                    continue  # um pedido só do domínio não faz sugestão
                confianca = "M" if tipo == M.TIPO_REMETENTE and linha.vezes >= 2 else "B"
                quando = timezone.localtime(linha.atualizado_em)
                saida[linha.campo] = {
                    "valor": linha.valor,
                    "exibir": linha.exibir or linha.valor,
                    "confianca": confianca,
                    "trecho": f"Aprendido de {_plural(linha.vezes, 'pedido anterior', 'pedidos anteriores')} {quem} "
                              f"(último em {quando:%d/%m/%Y}).",
                }
    except Exception:
        logger.exception("Falha ao consultar a memória de leitura para as sugestões.")
        return {}
    return saida
