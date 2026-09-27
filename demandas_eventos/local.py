"""Onde a palestra acontece: o nome do lugar (o endereço vai para os campos próprios).

A leitura genérica (`core.preencher_por_email.local_no_texto`) acha o
"Local:" rotulado e o "no Ginásio X" numa linha só. Na palestra o lugar
costuma ser a própria instituição que pede, dito de passagem:

- "no auditório do colégio", "na sede do CRAS", "aqui no colégio", "na
  própria escola": o colégio/o CRAS é o citado no pedido — o local ganha o
  nome dele ("auditório do Colégio Estadual X");
- "no nosso pátio coberto": o lugar é da instituição que pede;
- o nome do lugar que quebra a linha ("no Plenário\\nda Câmara");
- sem lugar dito, a escola dos alunos ("para os alunos da Escola X") ou a
  própria instituição que pede, quando é escola, igreja, CRAS…
"""

from __future__ import annotations

import re

from core.leitura.casamento import Achado
from core.leitura.datas import dobrar

from .solicitante import Instituicao

_LUGARES = (
    "colegio", "escola", "ginasio", "praca", "centro", "salao", "igreja", "camara", "prefeitura", "auditorio",
    "teatro", "parque", "associacao", "clube", "sede", "paroquia", "cras", "creas", "estadio", "espaco", "casa",
    "barracao", "pavilhao", "sala", "quadra", "biblioteca", "universidade", "faculdade", "instituto", "hospital",
    "batalhao", "shopping", "hotel", "restaurante", "cmei", "ubs", "terminal", "rodoviaria", "forum", "tribunal",
    "assembleia", "academia", "anfiteatro", "galpao", "complexo", "capela", "aldeia", "assentamento",
    "cooperativa", "sindicato", "secretaria", "templo", "patio", "refeitorio", "plenario", "campus", "apae",
    "museu", "arena", "matriz", "unidade", "fabrica", "cinema", "laboratorio",
)
# O lugar que é da instituição citada ("do colégio", "da escola", "do CRAS").
_REFERENCIAS = frozenset({
    "colegio", "escola", "cras", "creas", "apae", "igreja", "paroquia", "clube", "associacao", "sindicato",
    "cooperativa", "empresa", "faculdade", "universidade", "camara", "cmei", "creche", "instituto", "sede",
    "comunidade", "fabrica", "subsecao",
})
# Lugares onde "escola"/"colégio" costumam ser o local (para os alunos da Escola X).
_ESCOLAS = ("escola", "colegio", "eeb", "cmei", "creche", "apae", "centro de educacao")
_R_LUGAR = re.compile(
    r"\b(?P<prep>no|na|nos|nas|em)\s+(?P<posse>(?:(?:nosso|nossa|nossos|nossas|proprio|propria|seu|sua)\s+)?)"
    r"(?P<nucleo>(?:" + "|".join(_LUGARES) + r")(?:e?s)?)\b"
)
_PARA_ANTES_DO_LUGAR = frozenset({
    "para", "pra", "com", "sobre", "as", "a", "dia", "em", "que", "onde", "no", "na", "nos", "nas", "rua", "r",
    "av", "avenida", "rodovia", "travessa", "alameda", "estrada", "endereco", "cep", "bairro", "tel", "fone",
    "telefone", "contato", "durante", "entre", "ate", "desde", "sera", "sendo", "pois", "porque", "mas", "e",
})
_ABREVIACOES = re.compile(r"^(?:Dr|Dra|Pe|Sr|Sra|Prof|Profa|Profª|Sto|Sta|Ltda|Jd|Vl|Cel|Dep|Ver|Mons|[A-Z]\.[A-Z])\.$")
_R_ROTULO = re.compile(r"(?im)^[ \t*•-]*(?:local(?:\s+do\s+evento)?|onde)\s*[:–-]\s*(?P<valor>[^\n]{3,255})$")
_R_ENDERECO = re.compile(r"(?i)\s*(?:[-–,]\s*)?\b(?:rua|r\.|av\.?|avenida|rodovia|travessa|alameda|estrada|br-\d)\s.*$")


def _estender(texto: str, fim: int, *, maximo: int = 10) -> int:
    """Junta as palavras do nome do lugar até a vírgula, o parêntese, o traço ou o fim da frase.

    A quebra de linha no meio do nome não o corta ("no Plenário\nda Câmara").
    """
    pos = fim
    for _ in range(maximo):
        m = re.match(r"(\s*)(\S+)", texto[pos:])
        if not m or m.group(1).count("\n") > 1:
            break
        bruto = m.group(2)
        # Depois da quebra de linha, só se o nome continua ("no Plenário\nda Câmara").
        if "\n" in m.group(1) and not (bruto[0].isupper() or (
                dobrar(bruto).lower() in ("de", "da", "do", "das", "dos") and _proxima_maiuscula(texto, pos + m.end()))):
            break
        if bruto[0] in "([\"“-–—|/,.;:!?" or bruto[0].isdigit():
            break
        nucleo = bruto.rstrip(",.;:!?)\"”")
        dobrada = dobrar(nucleo).lower()
        if not nucleo or re.match(r"^\d", dobrada):
            break
        if dobrada in _PARA_ANTES_DO_LUGAR and not (dobrada == "e" and _proxima_maiuscula(texto, pos + m.end())):
            break
        if bruto == nucleo or _ABREVIACOES.match(bruto):
            pos += m.end()
            continue
        return pos + m.start(2) + len(nucleo)  # a pontuação fecha o nome
    return pos


def _proxima_maiuscula(texto: str, pos: int) -> bool:
    m = re.match(r"\s*(\S)", texto[pos:])
    return bool(m and m.group(1).isupper())


def _limpar(valor: str) -> str:
    valor = " ".join(valor.split()).strip(" ,.;:-–—")
    while valor and dobrar(valor.split()[-1]).lower() in ("de", "da", "do", "das", "dos", "e"):
        valor = valor.rsplit(" ", 1)[0] if " " in valor else ""
    return valor[:255]


def _singular(palavra: str) -> str:
    """"escolas" → "escola"; "cras" fica "cras"."""
    palavra = dobrar(palavra).lower()
    if palavra not in _REFERENCIAS and palavra.endswith("s") and palavra[:-1] in _REFERENCIAS:
        return palavra[:-1]
    return palavra


def _instituicao_citada(referencia: str, posicao: int, instituicoes: list[Instituicao], quem_pede: Instituicao | None) -> str:
    """O nome a que "o colégio"/"o CRAS" se refere: o citado antes, o mais perto; senão, quem pede.

    Do nome, a parte que começa pela referência: "o colégio" da "APMF do
    Colégio Estadual X" é o "Colégio Estadual X".
    """
    alvo = _singular(referencia)

    def parte(inst):
        palavras = inst.nome.split()
        for i, p in enumerate(palavras):
            if _singular(p.strip("(),")) == alvo:
                return " ".join(palavras[i:])
        return ""

    antes = [i for i in instituicoes if parte(i) and 0 <= i.inicio < posicao]
    if antes:
        return parte(max(antes, key=lambda i: i.inicio))
    if quem_pede is not None and (parte(quem_pede) or alvo == "sede"):
        return parte(quem_pede) or quem_pede.nome
    return next((parte(i) for i in instituicoes if parte(i)), "")


def _resolver(valor: str, posse: bool, posicao: int, instituicoes, quem_pede) -> str:
    """Troca "o colégio" pelo nome dele; o lugar "nosso" ganha o nome de quem pede."""
    palavras = valor.split()
    # Só a referência: "colégio", "própria escola", "nossa sede".
    if len(palavras) == 1 and _singular(palavras[0]) in _REFERENCIAS:
        return _instituicao_citada(palavras[0], posicao, instituicoes, quem_pede)
    # "auditório do colégio", "sede do CRAS": o dono é a instituição citada. Dono com nome
    # próprio ("Auditório da Unespar", "Ginásio do Guaraituba") já diz qual é.
    if len(palavras) >= 3 and dobrar(palavras[-2]).lower() in ("do", "da", "dos", "das"):
        dono = palavras[-1]
        if _singular(dono) in _REFERENCIAS and (dono.islower() or dono.isupper()):
            nome = _instituicao_citada(dono, posicao, instituicoes, quem_pede)
            if nome and dobrar(nome).lower() != dobrar(dono).lower():
                return " ".join(palavras[:-1] + [nome])
    if posse and quem_pede is not None and dobrar(quem_pede.nome).lower() not in dobrar(valor).lower():
        return f"{valor} — {quem_pede.nome}"
    return valor


def _lugar_no_texto(texto: str, instituicoes, quem_pede) -> Achado | None:
    dobrado = dobrar(texto).lower()
    for m in _R_LUGAR.finditer(dobrado):
        fim = _estender(texto, m.end("nucleo"))
        valor = _limpar(texto[m.start("nucleo"):fim])
        posse = bool(m.group("posse").strip())
        palavras = valor.split()
        referencia = len(palavras) == 1 and _singular(palavras[0]) in _REFERENCIAS
        # "no centro", "na sala": o tipo do lugar sem nome não diz onde é.
        if len(palavras) < 2 and not (referencia or posse):
            continue
        resolvido = _resolver(valor, posse, m.start(), instituicoes, quem_pede)
        if not resolvido:
            continue
        trecho = " ".join(texto[max(0, m.start() - 50):fim + 20].split())
        return Achado(resolvido, resolvido, trecho, "M")
    return None


def _rotulado(texto: str, instituicoes, quem_pede) -> Achado | None:
    """"Local: Auditório Principal - Rua Chile, 1800" → "Auditório Principal"."""
    m = _R_ROTULO.search(texto)
    if not m:
        return None
    valor = _R_ENDERECO.sub("", m.group("valor"))
    valor = re.split(r"\s+[-–—]\s+|\s*\(|,", valor)[0]
    valor = _limpar(re.sub(r"(?i)^(?:aqui\s+)?(?:n[oa]s?|em)\s+(?:(?:nosso|nossa|propri[oa])\s+)?", "", valor))
    if not valor or re.match(r"^\d", valor):
        return None
    posse = bool(re.search(r"(?i)\b(?:nosso|nossa|propri[oa]|aqui)\b", m.group("valor")))
    resolvido = _resolver(valor, posse, m.start(), instituicoes, quem_pede)
    if not resolvido:
        return None
    return Achado(resolvido, resolvido, m.group(0).strip(), "A")


def _municipios_e_estados() -> frozenset:
    from cadastros.models import Estado, Municipio

    nomes = list(Municipio.objects.values_list("nome", flat=True)) + list(Estado.objects.values_list("nome", flat=True))
    return frozenset(dobrar(n).lower() for n in nomes)


def _nome_proprio_no_texto(texto: str) -> Achado | None:
    """"ocorrerá … no Centreventos de Itajaí": o lugar pelo nome próprio (que não é cidade nem estado)."""
    cidades = None
    for m in re.finditer(r"\b(?:no|na)\s+(?P<nome>[A-ZÀ-Ý][\wÀ-ÿ'-]+(?:\s+(?:d[aeo]s?\s+)?[A-ZÀ-Ý][\wÀ-ÿ'-]+)*)", texto):
        nome = m.group("nome")
        dobrado = dobrar(nome).lower()
        primeira = dobrado.split()[0]
        if re.search(r"\b(?:policia|pcpr|ascom|nucleo|comunidade|dia|semana|mes|janeiro|fevereiro|marco|abril|maio|junho|"
                     r"julho|agosto|setembro|outubro|novembro|dezembro|segunda|terca|quarta|quinta|sexta|sabado|domingo)\b",
                     dobrado):
            continue
        if cidades is None:
            cidades = _municipios_e_estados()
        if dobrado in cidades or primeira in cidades:
            continue
        valor = _limpar(nome)
        # Precisa de um sinal de evento na frase ("ocorrerá", "será", "realizado").
        frase = dobrar(texto[max(0, m.start() - 120):m.start()]).lower()
        if not re.search(r"\b(?:ocorrera|acontecera|sera|realizad[oa]|realizara|evento)\b", frase):
            continue
        trecho = " ".join(texto[max(0, m.start() - 50):m.end() + 20].split())
        return Achado(valor, valor, trecho, "M")
    return None


def local_do_pedido(corpo: str, citado: str, fortes: list[Instituicao], fracas: list[Instituicao],
                    quem_pede: Instituicao | None) -> Achado | None:
    """O local, na ordem: "Local:", "no/na <lugar>" (no corpo; senão no pedido citado),
    o nome próprio do lugar, a escola dos alunos, a instituição que pede."""
    instituicoes = sorted(fortes + fracas, key=lambda i: i.inicio)
    for texto in (corpo, citado):
        if not (texto or "").strip():
            continue
        achado = _rotulado(texto, instituicoes, quem_pede) or _lugar_no_texto(texto, instituicoes, quem_pede)
        if achado is None and texto is corpo:
            achado = _nome_proprio_no_texto(texto)
        if achado is not None:
            return achado
    for inst in fracas:
        if dobrar(inst.nome).lower().startswith(_ESCOLAS):
            return Achado(inst.nome, inst.nome, inst.trecho, "M")
    if quem_pede is not None and dobrar(quem_pede.nome).lower().startswith(_ESCOLAS + ("igreja", "paroquia", "cras", "creas", "camara", "clube", "associacao")):
        return Achado(quem_pede.nome, quem_pede.nome, "A instituição que pede (sem outro lugar citado).", "M")
    return None
