"""Sugestões para a pauta nova a partir de um e-mail (o release, o pedido de divulgação).

As regras do domínio das publicações (mapas/demandas.md §2.5):

- data e início da pauta são os do e-mail;
- o título é o do release: o sugerido ("Sugestão de título: …"), a linha
  em CAIXA ALTA que abre o texto, o assunto sem "RES:", "Release -", "Para
  divulgação:"; se nada disso diz o fato, a primeira frase do texto;
- a unidade é sempre só sugestão: a de quem manda a pauta (assinatura,
  contato, assunto, "segue release da…", o sujeito do release), nunca a
  parceira que "deu apoio" (ver `unidades.py`); sem cadastro, o nome lido
  vai como sugestão para "Outra unidade" — que cria o cadastro ao salvar,
  então só a pessoa decide;
- a fonte é quem assina ("Del. Fulano"); se o remetente é a caixa da
  unidade ("DP Ortigueira"), quem assina o texto ("Inv. Fulano",
  "Informações: escrivão Fulano"). O jornalista responsável é quem está
  registrando, quando o nome casa com a equipe;
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
from core.preencher_por_email import Sugestao, Sugestoes, data_do_email, quem_pede

from . import unidades as leitura_unidades
from .models import Responsavel, Unidade

# Rótulos de envio no começo do assunto ou da linha: "Release - Prisão em Colombo",
# "Para divulgação: …", "Material p/ divulgação - DHPP", "Pedido de publicação - …".
_ROTULO = (
    r"(?:(?:novo\s+|segue\s+(?:o\s+)?)?release|press\s*release|nota(?:\s+(?:oficial|para\s+(?:a\s+)?imprensa|a\s+imprensa))?|"
    r"sugestao\s+de\s+pauta|pauta|(?:pedido|solicitacao)\s+de\s+(?:divulgacao|publicacao|release)|"
    r"(?:segue\s+)?material(?:\s+(?:p/|para)\s+(?:divulgacao|publicacao))?|(?:para|p/)\s+(?:a\s+)?(?:divulgacao|publicacao)|"
    r"divulgacao|publicacao|informac(?:ao|oes)|materia|urgente|importante)"
)
_R_PREFIXO_TITULO = re.compile(
    r"^\s*" + _ROTULO + r"(?:\s+(?:para\s+(?:a\s+)?divulgacao|pcpr|da\s+pcpr))?\s*(?:[-–:|/]+\s*|$)"
)
# "… - para divulgação", "… – fotos" no fim do assunto.
_R_SUFIXO_TITULO = re.compile(
    r"\s*(?:[-–:|/(]+\s*)(?:para\s+|p/\s+)?(?:divulgacao|publicacao|fotos?|release|divulgar|publicar)\)?\s*$"
)
_R_SAUDACAO = re.compile(
    r"^\s*(?:bom\s+dia|boa\s+tarde|boa\s+noite|ola|oi|prezad[oa]s?|car[oa]s?|pessoal|equipe|senhor(?:a|es)?)\b"
    r"[^.!?\n]{0,40}?(?:[.!?,]+|\s*$)\s*"
)
# "Segue release para divulgação:", "Favor publicar.", "segue material para divulgação".
_R_ENVIO = re.compile(
    r"^\s*(?:segue(?:m)?|encaminh[oa]\w*|envi[oa]\w*|solicit[oa]\w*|pedimos|peco|favor|por\s+gentileza|"
    r"material|release|mais\s+uma|para\s+divulgacao|pra\s+divulgar)\b[^.:!?\n]{0,80}?(?:[.:!?]+|\s*$)\s*"
)
# "Sugestão de título: …", "Título sugestão: …", "Título: …".
_R_TITULO_SUGERIDO = re.compile(r"\b(?:sugestao\s+de\s+titulo|titulo(?:\s+sugerido|\s+sugestao)?)\s*:\s*")
# Linhas em CAIXA ALTA que são só rótulo ("PARA DIVULGAÇÃO"), não a manchete.
_R_SO_ROTULO = re.compile(r"^\s*" + _ROTULO + r"[\s:.!-]*$")
_MINUSCULAS = frozenset(
    "a o as os e de da do das dos em na no nas nos por pela pelo pelas pelos com para pra sem sob sobre "
    "um uma uns umas que ao aos à às ou se".split()
)
_SIGLAS_FIXAS = frozenset({"PCPR", "PC", "PM", "PMPR", "PRF", "PF", "BR", "PR", "SC", "MP", "MPPR", "TJ", "CPF", "CNH"})

_CARGOS_FONTE = (
    (re.compile(r"^(?:delegad[oa]\b|del\b)"), "Del."),
    (re.compile(r"^investigador[a]?\b"), ""),
    (re.compile(r"^escriv(?:ao|a)\b"), ""),
)
_CARGO = (r"(?P<cargo>(?i:del\.|dra?\.|inv\.|invest\.|esc\.|delegad[oa](?:\s+de\s+pol[ií]cia)?|investigador[a]?|"
          r"escriv[ãa]o?|agente|papiloscopista))")
_NOME = r"(?P<nome>[A-ZÀ-Ý][\wÀ-ÿ'-]+(?:[ \t]+(?:d[aeo]s?[ \t]+)?[A-ZÀ-Ý][\wÀ-ÿ'-]+){1,4})"
# "o delegado Fulano de Tal", "Del. Fulano": o cargo em qualquer caixa, o nome com maiúsculas.
_R_FONTE_NO_TEXTO = re.compile(
    r"\b(?P<cargo>(?i:del\.|delegad[oa](?:\s+de\s+pol[ií]cia)?|investigador[a]?|escriv[ãa]o?))\s+" + _NOME
)
# A linha de quem assina o texto: "Inv. Alessandro Pilati", "Informações: escrivão Fulano".
_R_FONTE_NA_LINHA = re.compile(
    r"^\s*(?:(?i:informa[cç](?:ão|oes|ões)|mais\s+informa[cç]ões\s+com|fonte|contato)\s*:?\s*)?"
    r"(?:(?:o|a)\s+)?" + _CARGO + r"\s+" + _NOME, re.M
)
# O remetente que é a caixa da unidade, não gente: "DP Ortigueira", "COPE - Setor de Operações".
_R_INSTITUCIONAL = re.compile(
    r"^(?:setor|gabinete|cartorio|assessoria|ascom|imprensa|comunicacao|delegacia|divisao|nucleo|centro|"
    r"subdivisao|secretaria|policia|pcpr|plantao|protocolo|equipe|grupo|departamento)\b"
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


def _eh_caixa_alta(linha: str) -> bool:
    letras = [c for c in linha if c.isalpha()]
    return len(letras) >= 15 and sum(c.isupper() for c in letras) >= 0.85 * len(letras)


def _manchete(texto: str) -> str:
    """A linha em CAIXA ALTA que abre o release ("PCPR PRENDE HOMEM POR…"), sem os rótulos."""
    for linha in (texto or "").split("\n"):
        linha = " ".join(linha.split())
        if len(linha.split()) < 4 or not _eh_caixa_alta(linha) or _R_SO_ROTULO.match(dobrar(linha)):
            continue
        return linha.strip(" -–:")
    return ""


def _formas_no_texto(contexto: str, leitor: leitura_unidades.Leitor) -> dict[str, dict[str, int]]:
    """Como cada palavra aparece escrita no meio da frase: {"palmas": {"Palmas": 2}}.

    O nome das unidades não conta ("Divisão de Homicídios" não faz de
    "homicídios" nome próprio), mas a cidade dele sim ("9ª SDP de Foz").
    """
    for mencao in leitor.mencoes(contexto):
        fim = mencao.fim
        if mencao.cidade:
            achada = dobrar(contexto).rfind(dobrar(mencao.cidade), mencao.inicio, mencao.fim)
            fim = achada if achada >= 0 else fim
        contexto = contexto[: mencao.inicio] + " " * (fim - mencao.inicio) + contexto[fim:]
    formas: dict[str, dict[str, int]] = {}
    for linha in contexto.split("\n"):
        if _eh_caixa_alta(linha):
            continue
        for m in re.finditer(r"[\wÀ-ÿ'-]+", linha):
            antes = linha[: m.start()].rstrip()
            if not antes or antes[-1] in ".!?:\"“(–-":
                continue  # começo de frase: a maiúscula não diz nada
            palavra = m.group(0)
            contagem = formas.setdefault(dobrar(palavra), {})
            contagem[palavra] = contagem.get(palavra, 0) + 1
    return formas


def _em_caixa_normal(manchete: str, contexto: str, leitor: leitura_unidades.Leitor) -> str:
    """ "PCPR PRENDE HOMEM EM PALMAS" -> "PCPR prende homem em Palmas".

    Cada palavra fica como o resto do e-mail a escreve no meio da frase
    ("Palmas", "DHPP", "tráfico"); a que não aparece fora da manchete fica
    em minúscula, menos siglas conhecidas, o que tem número ("BR-277"), o
    nome das unidades ("SDP de Ponta Grossa") e o dos municípios.
    """
    formas = _formas_no_texto(contexto, leitor)
    siglas = _SIGLAS_FIXAS | set(leitura_unidades.SIGLAS)
    dobrada = dobrar(manchete)

    def palavra_normal(palavra: str) -> str:
        chave = dobrar(palavra)
        contagem = formas.get(chave, {})
        if any(c.isdigit() for c in palavra) or palavra.isupper() and palavra in siglas:
            return palavra
        if chave in _MINUSCULAS or not contagem:
            return palavra.lower()
        maiusculas = sum(n for f, n in contagem.items() if f != f.lower())
        if maiusculas <= sum(n for f, n in contagem.items() if f == f.lower()):
            return palavra.lower()  # empate: a palavra comum ("roubos") vence
        return max(((f, n) for f, n in contagem.items() if f != f.lower()), key=lambda x: x[1])[0]

    def titulo(trecho: str) -> str:
        return re.sub(
            r"[\wÀ-ÿ'-]+",
            lambda m: m.group(0) if m.group(0) in siglas or any(c.isdigit() for c in m.group(0))
            else m.group(0).lower() if dobrar(m.group(0)) in _MINUSCULAS else m.group(0).capitalize(),
            trecho,
        )

    # Trechos com grafia certa: unidade, município, "Polícia Civil".
    fixos: dict[int, tuple[int, str]] = {}
    for mencao in leitor.mencoes(manchete):
        fixos[mencao.inicio] = (mencao.fim, titulo(manchete[mencao.inicio:mencao.fim]))
    for m in re.finditer(r"\bpolicia\s+(?:civil|militar|federal|rodoviaria\s+federal|cientifica)\b|\bparana\b", dobrada):
        fixos.setdefault(m.start(), (m.end(), titulo(manchete[m.start():m.end()])))
    for m in re.finditer(r"[\wÀ-ÿ'-]+", manchete):
        if any(a <= m.start() < b for a, (b, _) in fixos.items()):
            continue
        cidade, fim = leitor.cidade_em(manchete, m.start(), abreviacao=False)
        # Nome de uma palavra só ("Palmas", mas também "Floresta", "Reserva") só depois de "em".
        if cidade and (" " in cidade or re.search(r"\bem\s+$", dobrada[: m.start()])):
            fixos[m.start()] = (fim, cidade)
    saida, pos = [], 0
    for m in re.finditer(r"[\wÀ-ÿ'-]+", manchete):
        if m.start() < pos:
            continue
        saida.append(manchete[pos:m.start()])
        if m.start() in fixos:
            pos, forma = fixos[m.start()]
            saida.append(forma)
            continue
        saida.append(palavra_normal(m.group(0)))
        pos = m.end()
    saida.append(manchete[pos:])
    texto = "".join(saida)
    return texto[:1].upper() + texto[1:]


def _sem_rotulos(texto: str) -> str:
    """O assunto sem "Release -", "Para divulgação:" no começo e "- divulgação", "- fotos" no fim."""
    resto = texto
    for _ in range(3):
        m = _R_PREFIXO_TITULO.match(dobrar(resto))
        if not m or not m.end():
            break
        resto = resto[m.end():]
    for _ in range(2):
        m = _R_SUFIXO_TITULO.search(dobrar(resto))
        if not m:
            break
        resto = resto[: m.start()]
    return " ".join(resto.split()).strip(" -–:|/.")


def _diz_o_fato(assunto: str, leitor: leitura_unidades.Leitor) -> bool:
    """ "Divulgação Rio Negro", "Material para divulgação - DHPP": só a unidade ou a cidade, sem o fato."""
    resto = assunto
    for mencao in sorted(leitor.mencoes(assunto, solto=True), key=lambda x: -x.inicio):
        resto = resto[: mencao.inicio] + " " + resto[mencao.fim:]
    palavras = [p for p in re.findall(r"[\wÀ-ÿ'-]+", resto) if dobrar(p) not in _MINUSCULAS]
    chave = _chave(" ".join(palavras))
    if chave in leitor.municipios or leitura_unidades.ABREVIACOES_CIDADE.get(chave):
        return False
    return len(palavras) >= 2 and len(resto.strip()) >= 8


def _limpar_abertura(linha: str) -> str:
    """Tira da linha a saudação e a frase de envio: "Boa tarde. Para divulgação: PCPR prende…"."""
    for _ in range(4):
        dobrada = dobrar(linha)
        m = _R_SAUDACAO.match(dobrada) or _R_ENVIO.match(dobrada)
        if not m or not m.end():
            break
        linha = linha[m.end():]
    return linha.strip()


def _primeira_frase(corpo: str) -> str:
    for paragrafo in re.split(r"\n\s*\n", corpo or ""):
        linhas = [linha for linha in paragrafo.strip().split("\n") if linha.strip()]
        while linhas:
            limpa = _limpar_abertura(linhas[0])
            if limpa:
                linhas[0] = limpa
                break
            linhas.pop(0)
        texto = " ".join(" ".join(linhas).split())
        if len(texto) < 20:
            continue
        # Ponto final seguido de espaço e maiúscula: "(PCPR) prendeu… Curitiba. A ação…".
        fim = re.search(r"[.!?](?=\s+[A-ZÀ-Ý0-9]|\s*$)", texto)
        frase = texto[: fim.start()] if fim else texto
        return frase[:1].upper() + frase[1:]
    return ""


def _titulo(mensagem: Mensagem, leitor: leitura_unidades.Leitor) -> Sugestao | None:
    """O título sugerido, a manchete do release, o assunto sem rótulos ou a primeira frase."""
    corpo = mensagem.corpo or ""
    m = _R_TITULO_SUGERIDO.search(dobrar(corpo))
    if m:
        linha = corpo[m.end():].split("\n")[0].strip()
        if len(linha) >= 12:
            return Sugestao(linha[:300], linha[:300], "M", corpo[m.start():m.end()] + linha)
    assunto = mensagem.assunto_limpo
    manchete = _manchete(corpo) or (assunto if len(assunto.split()) >= 4 and _eh_caixa_alta(assunto) else "")
    if manchete:
        titulo = _em_caixa_normal(manchete, f"{assunto}\n{corpo}\n{mensagem.assinatura}", leitor)[:300]
        return Sugestao(titulo, titulo, "M", manchete)
    resto = _sem_rotulos(assunto)
    if resto and _diz_o_fato(resto, leitor):
        resto = resto[:1].upper() + resto[1:]
        return Sugestao(resto[:300], resto[:300], "M", assunto)
    frase = _primeira_frase(corpo)
    if frase:
        titulo = frase[:300]
        return Sugestao(titulo, titulo, "M", "1ª frase do texto (o assunto não diz o fato).")
    return None


# ---------------------------------------------------------------------------
# Unidade e fonte
# ---------------------------------------------------------------------------


def _assinatura_no_corpo(corpo: str) -> tuple[str, str]:
    """(corpo, assinatura) quando a assinatura ficou colada no fim do texto:
    o último parágrafo só de linhas curtas ("Inv. Fulano / COPE – Curitiba")."""
    paragrafos = re.split(r"\n\s*\n", (corpo or "").rstrip())
    ultimo = paragrafos[-1].strip() if paragrafos else ""
    linhas = [linha for linha in ultimo.split("\n") if linha.strip()]
    if len(paragrafos) > 1 and 0 < len(linhas) <= 6 and all(len(linha) <= 70 for linha in linhas):
        return "\n\n".join(paragrafos[:-1]), ultimo
    return corpo or "", ""


def _leitor() -> leitura_unidades.Leitor:
    from cadastros.models import Municipio

    return leitura_unidades.Leitor(Municipio.objects.values_list("nome", flat=True))


def _unidade(s: Sugestoes, mensagem: Mensagem, leitor: leitura_unidades.Leitor) -> None:
    """A unidade de quem manda, sempre como sugestão: a do cadastro, ou o nome lido para "Outra unidade"."""
    unidades = list(Unidade.objects.order_by("nome"))
    cadastros = leitura_unidades.ler_cadastros(unidades, leitor)
    corpo, assinatura_colada = _assinatura_no_corpo(mensagem.corpo)
    assinatura = "\n".join(x for x in (mensagem.assinatura, assinatura_colada) if x)
    leitor.aprender(mensagem.assunto_limpo, mensagem.corpo, mensagem.assinatura)
    mencoes = (
        leitor.pontuadas(assinatura, "assinatura", solto=True, linha=True)
        + leitor.pontuadas(mensagem.remetente_nome, "contato", solto=True, linha=True)
        + leitor.pontuadas(mensagem.assunto_limpo, "assunto", solto=True)
        + leitor.pontuadas(corpo, "texto")
    )
    # Mais pontos primeiro; no mesmo lugar, a SDP perde para a unidade que ela
    # abrange ("Delegacia da Mulher – 15ª SDP"), e vale a ordem de leitura.
    ordem = sorted(range(len(mencoes)), key=lambda i: (-mencoes[i].pontos, mencoes[i].tipo == "SDP", i))
    for i in ordem:
        mencao = mencoes[i]
        unidade = leitura_unidades.no_cadastro(mencao, cadastros)
        if unidade is not None:
            s.por("unidade", Sugestao(unidade, unidade.nome, "B", mencao.trecho))
            return
        if mencao.determinada:
            nome = mencao.nome()[:150]
            s.por("unidade_nova", Sugestao(nome, nome, "B", f"Unidade citada no e-mail e ainda sem cadastro: {mencao.trecho}"))
            return
    # Cadastro que o leitor não reconhece como unidade ("Gabinete…"): pelo nome.
    if not mencoes:
        for texto in (assinatura, mensagem.assunto_limpo, corpo):
            achados = cadastros_no_texto(texto, unidades)
            if achados:
                s.por("unidade", Sugestao(achados[0].valor, achados[0].exibir, "B", achados[0].trecho))
                return


def _institucional(nome: str, leitor: leitura_unidades.Leitor) -> bool:
    """O "nome" é a caixa da unidade ("DP Ortigueira", "Nucria Curitiba"), não uma pessoa."""
    if _R_INSTITUCIONAL.match(dobrar(nome)):
        return True
    return any(m.inicio == 0 for m in leitor.mencoes(nome, solto=True))


def _nome_do_contato(nome: str, leitor: leitura_unidades.Leitor) -> tuple[str, str]:
    """(nome, cargo) do contato do WhatsApp: "Carla Bento DM Cascavel" -> "Carla Bento";
    "Henrique Vasconi - Delegado Palmas" e "Gustavo Menegatti Del." -> delegado."""
    cargo = ""
    m = re.match(r"^(?P<nome>.+?)\s+(?:[-–|/]\s+)?(?P<cargo>del\.?|delegad[oa]|inv\.|investigador[a]?|esc\.|escriv(?:ao|a))(?:\s.*)?$",
                 dobrar(nome))
    if m and len(m.group("nome").split()) >= 2:
        nome, cargo = nome[: m.end("nome")], m.group("cargo")
    for mencao in leitor.mencoes(nome, solto=True):
        antes = nome[: mencao.inicio].rstrip(" -–|/")
        if len(antes.split()) >= 2:
            return antes, cargo
    return nome.rstrip(" -–|/"), cargo


def _fonte(mensagem: Mensagem, pessoa, leitor: leitura_unidades.Leitor) -> Sugestao | None:
    """Quem passou a informação: "Del. Fulano" pela assinatura, ou quem assina o texto."""
    if pessoa is not None and pessoa.nome and not _institucional(pessoa.nome, leitor):
        nome, cargo_no_nome = _nome_do_contato(pessoa.nome, leitor)
        cargo = dobrar(pessoa.cargo) or cargo_no_nome
        if not re.match(r"^(?:del|dr|dra)\.?\s", dobrar(nome)):
            for regex, abreviacao in _CARGOS_FONTE:
                if regex.match(cargo):
                    nome = f"{abreviacao} {nome}" if abreviacao else f"{nome} ({pessoa.cargo})" if pessoa.cargo else nome
                    break
        return Sugestao(nome[:200], nome[:200], "M", pessoa.trecho)
    # Remetente é a caixa da unidade: quem assina a linha ("Inv. Fulano"), depois quem o texto cita.
    texto = "\n".join(x for x in (mensagem.corpo, mensagem.assinatura) if x)
    m = _R_FONTE_NA_LINHA.search(texto) or _R_FONTE_NO_TEXTO.search(mensagem.corpo or "")
    if m:
        cargo = " ".join(m.group("cargo").split())
        valor = f"Del. {m.group('nome')}" if dobrar(cargo).startswith("del") else f"{cargo} {m.group('nome')}"
        valor = " ".join(valor.split())[:200]
        return Sugestao(valor, valor, "M", " ".join(m.group(0).split()))
    nome = mensagem.remetente_nome or (pessoa.nome if pessoa is not None else "")
    if nome:
        return Sugestao(nome[:200], nome[:200], "M", mensagem.remetente or nome)
    return None


# ---------------------------------------------------------------------------
# Todas as sugestões
# ---------------------------------------------------------------------------


def _chegada(mensagem: Mensagem):
    """Quando a pauta chegou à assessoria.

    E-mail encaminhado: o encaminhamento que chegou (`recebido_em`), não o
    original. Conversa do WhatsApp: a primeira fala depois da última pausa
    longa (mais de 12 horas) — o "obrigada" de três dias antes é outra conversa.
    """
    falas = [f["enviado_em"] for f in (mensagem.extras or {}).get("falas") or [] if f.get("enviado_em")]
    if falas:
        inicio = anterior = None
        for quando in falas:
            if anterior is None or (quando - anterior).total_seconds() > 12 * 3600:
                inicio = quando
            anterior = quando
        return inicio
    return mensagem.recebido_em or mensagem.enviado_em


def _data_da_pauta(mensagem: Mensagem) -> Sugestao | None:
    chegada = _chegada(mensagem)
    if chegada is None:
        return None
    if timezone.is_aware(chegada):
        chegada = timezone.localtime(chegada)
    return Sugestao(chegada.date(), f"{chegada:%d/%m/%Y}", "A", f"Chegou em {chegada:%d/%m/%Y %H:%M}")


def _inicio_da_pauta(mensagem: Mensagem) -> Sugestao | None:
    """A hora em que a pauta chegou à assessoria (ver `_chegada`)."""
    enviado = _chegada(mensagem)
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
    leitor = _leitor()
    s.por("data", _data_da_pauta(mensagem))
    s.por("titulo", _titulo(mensagem, leitor))
    s.por("jornalista", Sugestao.de_achado(integrante_do_usuario(usuario, Responsavel.objects.order_by("nome"))))
    _unidade(s, mensagem, leitor)
    s.por("fonte", _fonte(mensagem, pessoa, leitor))
    s.por("inicio_pauta", _inicio_da_pauta(mensagem))
    _aviso_de_fotos(s, mensagem)
    return s
