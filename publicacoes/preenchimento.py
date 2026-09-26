"""Sugestões para a pauta nova a partir de um e-mail (o release, o pedido de divulgação).

As regras do domínio das publicações (mapas/demandas.md §2.5):

- data e início da pauta são os do e-mail;
- o título é o assunto sem "RES:", "Release -", "Para divulgação:"; se o
  assunto não diz nada ("Release"), a primeira frase do texto;
- a unidade é sempre só sugestão: a do cadastro citada na assinatura ou no
  texto ("10ª DP", "DHPP"), com a grafia padronizada de `canonizar_unidade`;
  sem cadastro, o nome lido vai como sugestão para "Outra unidade" — que
  cria o cadastro ao salvar, então só a pessoa decide;
- a fonte é quem assina ("Del. Fulano"), e o jornalista responsável é quem
  está registrando, quando o nome casa com a equipe;
- as fotos do e-mail não têm onde ficar na pauta: viram aviso.

Nada aqui grava.
"""

from __future__ import annotations

import re
from pathlib import PurePath

from django.utils import timezone

from core.equipe import integrante_do_usuario
from core.leitura.casamento import cadastros_no_texto
from core.leitura.datas import dobrar
from core.leitura.mensagem import Mensagem
from core.planilhas import canonizar_unidade
from core.preencher_por_email import Sugestao, Sugestoes, data_do_email, quem_pede

from .models import Responsavel, Unidade

# "Release - Prisão em Colombo", "Para divulgação: …", "Sugestão de pauta – …".
_R_PREFIXO_TITULO = re.compile(
    r"^\s*(?:(?:novo\s+|segue\s+(?:o\s+)?)?release|press\s*release|nota(?:\s+(?:oficial|para\s+(?:a\s+)?imprensa|a\s+imprensa))?|"
    r"sugestao\s+de\s+pauta|pauta|para\s+(?:a\s+)?divulgacao|divulgacao|informac(?:ao|oes)|materia|urgente|importante)"
    r"(?:\s+(?:para\s+(?:a\s+)?divulgacao|pcpr|da\s+pcpr))?\s*(?:[-–:|/]+\s*|$)"
)
_R_ABERTURA_DO_TEXTO = re.compile(
    r"^\s*(?:segue(?:m)?\s+(?:o\s+|a\s+)?(?:release|texto|nota|materia|informac(?:ao|oes))[^:.\n]{0,40}[:.-]\s*)"
)
_R_SAUDACAO = re.compile(
    r"^\s*(?:bom\s+dia|boa\s+tarde|boa\s+noite|ola|oi|prezad[oa]s?|car[oa]s?|pessoal|equipe|senhor(?:a|es)?)\b[^\n]{0,40}$"
)
# "10ª Delegacia de Polícia de Curitiba", "10 DP", "3ª SDP de Londrina".
# O tipo em qualquer caixa; o nome da cidade depois, só com inicial maiúscula
# ("10ª DP de Curitiba", mas não "10ª DP de forma integrada").
_R_UNIDADE_NUMERADA = re.compile(
    r"\b(?P<numero>\d{1,3})\s*(?:[ªºo°]|a\.?)?\s*"
    r"(?P<tipo>(?i:DP|SDP|DH|DRP|Delegacia\s+de\s+Pol[ií]cia|Subdivis[ãa]o\s+Policial|"
    r"Delegacia\s+Regional(?:\s+de\s+Pol[ií]cia)?))\b"
    r"(?P<resto>(?:\s+(?:de|do|da)\s+[A-ZÀ-Ý][\wÀ-ÿ'-]*(?:\s+(?:d[aeo]s?\s+)?[A-ZÀ-Ý][\wÀ-ÿ'-]*){0,3})?)"
)
# A instituição inteira não é unidade: "Polícia Civil do Paraná", "Governo do Estado".
_R_ORGAO_GERAL = re.compile(r"^(?:policia\s+civil|pcpr|governo|secretaria|estado\s+do)\b")
_TIPOS_UNIDADE = {"delegacia de policia": "DP", "subdivisao policial": "SDP", "delegacia regional": "DRP",
                  "delegacia regional de policia": "DRP"}
_CARGOS_FONTE = (
    (re.compile(r"^delegad[oa]\b"), "Del."),
    (re.compile(r"^investigador[a]?\b"), ""),
    (re.compile(r"^escriv(?:ao|a)\b"), ""),
)
# "o delegado Fulano de Tal", "Del. Fulano": o cargo em qualquer caixa, o nome com maiúsculas.
_R_FONTE_NO_TEXTO = re.compile(
    r"\b(?i:del\.|delegad[oa](?:\s+de\s+pol[ií]cia)?|investigador[a]?|escriv[ãa]o?)\s+"
    r"(?P<nome>[A-ZÀ-Ý][\wÀ-ÿ'-]+(?:\s+(?:d[aeo]s?\s+)?[A-ZÀ-Ý][\wÀ-ÿ'-]+){1,4})"
)
_EXTENSOES_FOTO = frozenset({".jpg", ".jpeg", ".png", ".gif", ".heic", ".heif", ".webp", ".bmp", ".tif", ".tiff"})

#: Campos que a memória guarda por remetente ao salvar (`core.aprendizado`):
#: o que o próximo e-mail da mesma origem provavelmente repete.
CAMPOS_APRENDIDOS = ["unidade", "fonte", "jornalista"]



def _chave(texto: str) -> str:
    return " ".join(re.findall(r"[a-z0-9]+", dobrar(texto or "")))


# ---------------------------------------------------------------------------
# Título
# ---------------------------------------------------------------------------


def _primeira_frase(corpo: str) -> str:
    for paragrafo in re.split(r"\n\s*\n", corpo or ""):
        linhas = [linha for linha in paragrafo.strip().split("\n") if linha.strip()]
        while linhas and _R_SAUDACAO.match(dobrar(linhas[0])):
            linhas.pop(0)
        texto = " ".join(" ".join(linhas).split())
        m = _R_ABERTURA_DO_TEXTO.match(dobrar(texto))
        if m:
            texto = texto[m.end():].strip()
        if len(texto) < 20:
            continue
        # Ponto final seguido de espaço e maiúscula: "(PCPR) prendeu… Curitiba. A ação…".
        fim = re.search(r"[.!?](?=\s+[A-ZÀ-Ý]|\s*$)", texto)
        frase = texto[: fim.start()] if fim else texto
        return frase[:1].upper() + frase[1:]
    return ""


def _titulo(mensagem: Mensagem) -> Sugestao | None:
    """O assunto sem os rótulos de envio; se não sobrar nada, a primeira frase do texto."""
    assunto = mensagem.assunto_limpo
    resto = assunto
    for _ in range(3):
        m = _R_PREFIXO_TITULO.match(dobrar(resto))
        if not m or not m.end():
            break
        resto = resto[m.end():]
    resto = " ".join(resto.split()).strip(" -–:|/.")
    if len(resto) >= 12:
        resto = resto[:1].upper() + resto[1:]
        return Sugestao(resto[:300], resto[:300], "M", assunto)
    frase = _primeira_frase(mensagem.corpo)
    if frase:
        titulo = frase[:300]
        return Sugestao(titulo, titulo, "M", "1ª frase do texto (o assunto não diz o fato).")
    return None


# ---------------------------------------------------------------------------
# Unidade e fonte
# ---------------------------------------------------------------------------


def _unidades_numeradas(texto: str) -> list[tuple[str, str]]:
    """(nome padronizado, trecho) das unidades numeradas citadas ("10ª DP de Curitiba")."""
    achados = []
    for m in _R_UNIDADE_NUMERADA.finditer(texto or ""):
        tipo = m.group("tipo")
        sigla = _TIPOS_UNIDADE.get(_chave(tipo), tipo.upper())
        nome = canonizar_unidade(f"{m.group('numero')} {sigla}{m.group('resto')}")
        achados.append((nome, m.group(0).strip()))
    return achados


def _unidade(s: Sugestoes, mensagem: Mensagem, pessoa) -> None:
    """A unidade, sempre como sugestão: a do cadastro, ou o nome lido para "Outra unidade"."""
    unidades = list(Unidade.objects.order_by("nome"))
    por_chave = {_chave(u.nome): u for u in unidades}
    fontes = [x for x in (mensagem.assinatura, mensagem.assunto_limpo, mensagem.corpo) if x]
    lido = ""
    for texto in fontes:
        for nome, trecho in _unidades_numeradas(texto):
            # "10ª DP de Curitiba" no texto e "10ª DP" (ou o inverso) no cadastro.
            chave = _chave(nome)
            base = _chave(re.sub(r"\s+(?:de|do|da)\s+.*$", "", nome))
            unidade = por_chave.get(chave) or por_chave.get(base) or next(
                (u for c, u in por_chave.items() if c.startswith(chave + " ")), None
            )
            if unidade is not None:
                s.por("unidade", Sugestao(unidade, unidade.nome, "B", trecho))
                return
            lido = lido or nome
        achados = cadastros_no_texto(texto, unidades)
        if achados:
            s.por("unidade", Sugestao(achados[0].valor, achados[0].exibir, "B", achados[0].trecho))
            return
    if lido:
        s.por("unidade_nova", Sugestao(lido[:150], lido[:150], "B", "Unidade citada no e-mail e ainda sem cadastro."))
    elif pessoa is not None and pessoa.unidade and not _R_ORGAO_GERAL.match(dobrar(pessoa.unidade)):
        nome = canonizar_unidade(pessoa.unidade)[:150]
        s.por("unidade_nova", Sugestao(nome, nome, "B", pessoa.trecho))


def _fonte(mensagem: Mensagem, pessoa) -> Sugestao | None:
    """Quem passou a informação: "Del. Fulano" pela assinatura, ou citado no texto."""
    if pessoa is not None and pessoa.nome:
        nome = pessoa.nome
        cargo = dobrar(pessoa.cargo)
        if not re.match(r"^(?:del|dr|dra)\.?\s", dobrar(nome)):
            for regex, abreviacao in _CARGOS_FONTE:
                if regex.match(cargo):
                    nome = f"{abreviacao} {nome}" if abreviacao else f"{nome} ({pessoa.cargo})"
                    break
        return Sugestao(nome[:200], nome[:200], "M", pessoa.trecho)
    m = _R_FONTE_NO_TEXTO.search(mensagem.corpo or "")
    if m:
        valor = f"Del. {m.group('nome')}" if dobrar(m.group(0)).startswith("del") else m.group(0)
        valor = " ".join(valor.split())[:200]
        return Sugestao(valor, valor, "M", m.group(0))
    if mensagem.remetente_nome:
        return Sugestao(mensagem.remetente_nome[:200], mensagem.remetente_nome[:200], "M", mensagem.remetente)
    return None


# ---------------------------------------------------------------------------
# Todas as sugestões
# ---------------------------------------------------------------------------


def _inicio_da_pauta(mensagem: Mensagem) -> Sugestao | None:
    """A hora do e-mail: é quando a pauta chegou à assessoria."""
    enviado = mensagem.enviado_em
    if enviado is None:
        return None
    if timezone.is_aware(enviado):
        enviado = timezone.localtime(enviado)
    hora = enviado.time().replace(second=0, microsecond=0)
    return Sugestao(hora, f"{hora:%H:%M}", "A", f"Enviado em {enviado:%d/%m/%Y %H:%M}")


def _aviso_de_fotos(s: Sugestoes, mensagem: Mensagem) -> None:
    fotos = [nome for nome, _ in mensagem.anexos if PurePath(nome).suffix.lower() in _EXTENSOES_FOTO]
    if fotos:
        lista = ", ".join(fotos[:4]) + ("…" if len(fotos) > 4 else "")
        s.avisar(
            f"O e-mail traz {len(fotos)} foto(s) ({lista}). A pauta não guarda anexos: "
            "salve as fotos onde a equipe guarda as imagens das matérias."
        )


def sugestoes(mensagem: Mensagem, usuario=None) -> Sugestoes:
    """As sugestões para a tela "Nova pauta", campo a campo."""
    s = Sugestoes()
    pessoa = quem_pede(mensagem)
    s.por("data", data_do_email(mensagem))
    s.por("titulo", _titulo(mensagem))
    s.por("jornalista", Sugestao.de_achado(integrante_do_usuario(usuario, Responsavel.objects.order_by("nome"))))
    _unidade(s, mensagem, pessoa)
    s.por("fonte", _fonte(mensagem, pessoa))
    s.por("inicio_pauta", _inicio_da_pauta(mensagem))
    _aviso_de_fotos(s, mensagem)
    return s
