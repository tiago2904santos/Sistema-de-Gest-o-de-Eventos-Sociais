"""Endereço brasileiro citado num e-mail: logradouro e número, complemento, bairro e CEP.

"Rua XV de Novembro, 1200, sala 2 - Centro - CEP 84010-000", "Av. Brasil
nº 45, bairro Jardim América", "PR-445, km 12", "Linha São Roque, s/n",
com ou sem acento, em maiúsculas ou em linhas próprias (o endereço depois
de "Local: Ginásio X", o CEP na linha de baixo).

O e-mail costuma ter dois endereços: o do evento (ou da entrega) e o de
quem escreve, na assinatura. Só interessa o primeiro — por isso o que só
aparece na assinatura é ignorado e o que vem perto de "local", "será
realizado", "no endereço", "entrega" ganha preferência.

Puro como o resto de `core.leitura`: recebe texto e devolve o que achou,
com o trecho de onde saiu para a tela mostrar ao conferir.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .datas import dobrar

__all__ = ["Endereco", "endereco_no_texto", "formatar_cep"]


@dataclass(frozen=True)
class Endereco:
    """O endereço achado, separado nos campos do formulário.

    `logradouro_numero` é "Rua X, 123" (ou "PR-445, km 12", "Rua Y, s/n");
    `cep` já vem no formato "00000-000"; `trecho`, a linha de onde saiu;
    `ancorado`, se havia uma palavra-âncora ("local", "será realizado",
    "entrega") perto — com ela, ou com CEP, a leitura é de confiança alta.
    """

    logradouro_numero: str = ""
    complemento: str = ""
    bairro: str = ""
    cep: str = ""
    trecho: str = ""
    ancorado: bool = False

    @property
    def endereco(self) -> str:
        """O campo "endereço" do formulário: logradouro, número e complemento."""
        return ", ".join(x for x in (self.logradouro_numero, self.complemento) if x)

    @property
    def confianca(self) -> str:
        return "A" if (self.cep or self.ancorado) else "M"


def formatar_cep(valor: str) -> str:
    """"84.010-000", "84010000" -> "84010-000"; sem oito dígitos, vazio."""
    digitos = re.sub(r"\D", "", valor or "")
    return f"{digitos[:5]}-{digitos[5:]}" if len(digitos) == 8 else ""


# ---------------------------------------------------------------------------
# Padrões (sempre sobre o texto dobrado: minúsculo e sem acento)
# ---------------------------------------------------------------------------

# O tipo do logradouro. "Praça", "Estrada", "Largo", "Servidão" e "Linha"
# também são palavras comuns ("na praça central", "em linha"): só valem com
# o nome próprio em maiúscula logo depois.
_R_TIPO = re.compile(
    r"(?<![\w.\-/])(?P<tipo>rua|r\.|avenida|av\.?|alameda|al\.|travessa|trav\.|tv\.|praca|pca\.?|"
    r"rodovia|rod\.|estrada|estr\.|largo|servidao|linha)(?=\s)"
)
_TIPOS_FRACOS = {"praca", "pca", "pca.", "estrada", "estr.", "largo", "servidao", "linha"}
# Rodovia sem a palavra "Rodovia": "PR-445, km 12", "BR 277 km 3" (só com o km).
_R_RODOVIA = re.compile(
    r"(?<![\w-])(?P<tipo>(?:br|pr|sc|sp|rs|ms|mg|rj|go|mt|to|ba|pe|ce|pa|am|ro|es|df)[\s-]?\d{3})"
    r"(?=\s*,?\s*km\b)"
)
_CONECTORES = {"de", "da", "do", "das", "dos", "e", "d'"}
# Abreviaturas que terminam em ponto sem terminar a frase.
_ABREVIATURAS = {
    "r", "av", "al", "tv", "trav", "pca", "rod", "estr", "jd", "vl", "pq", "b", "n", "no", "nro", "num",
    "sl", "bl", "ap", "apto", "ed", "dr", "dra", "prof", "profa", "gov", "sen", "dep", "pe", "sta", "sto",
    "s", "sr", "sra", "cel", "cap", "ten", "gal", "mal", "pres", "eng", "des", "min", "conj", "lt", "qd",
    "lj", "km", "cond", "res", "ch", "cmte", "vol", "sgt", "maj", "cb", "pref", "ver", "mons", "fr",
}
_PREPOSICOES = {"na", "no", "em", "a", "da", "do", "de", "e", "para", "pela", "pelo", "ate", "sera", "local"}
_R_TERMINO = re.compile(r"[;!?()]|\.(?=\s|$)")
# Linha seguinte que continua o endereço: bairro, CEP, complemento, cidade/UF.
_R_CONTINUA = re.compile(
    r"^[ \t]*(?:[-,][ \t]*)?(?:bairro\b|b\.\s|cep\b|\d{2}\.?\d{3}-?\d{3}\b|jardim\b|jd\.?\s|vila\b|vl\.\s|centro\b|"
    r"parque\b|conjunto\b|residencial\b|sala\b|bloco\b|andar\b|loja\b|[^\n]{2,40}[/-][ \t]*[a-z]{2}[ \t]*$)"
)
_R_SEPARADOR = re.compile(r"(?:[ \t]*(?:,|\n|[ \t]-[ \t]|/(?=[ \t]*[a-z]{2}\b)|\|)[ \t]*)+|[ \t]+")
# Onde termina um pedaço (bairro, complemento, cidade).
_R_FIM_PEDACO = re.compile(r",|\n|[ \t]-[ \t]|/(?=[ \t]*[a-z]{2}\b)|\||[ \t](?=cep\b)")
_R_CEP = re.compile(r"(?:cep\s*[:.]?\s*(?:n[o.]?\s*)?)?(?P<cep>\d{2}\.?\d{3}\s?-?\s?\d{3})(?!\d)")
_R_CEP_ROTULADO = re.compile(r"\bcep\s*[:.]?\s*(?:n[o.]?\s*)?(?P<cep>\d{2}\.?\d{3}\s?-?\s?\d{3})(?!\d)")
_R_NUMERO = re.compile(
    r"(?:(?:n\s*[o.]\s*\.?|nro\.?|num\.?|numero|n)\s*[:.]?\s*)?(?P<n>\d{1,5}(?:-?[a-gi-z](?![\w]))?)(?![\d.,:]?\d|\s*(?:h\b|hs\b|horas?\b|min\b|pessoas|participantes|de\s+(?:jan|fev|mar|abr|mai|jun|jul|ago|set|out|nov|dez)))"
)
_R_SEM_NUMERO = re.compile(r"(?:s\s*/\s*n(?:o|\.)?|sem\s+numero|sn)(?![\w])")
_R_KM = re.compile(r"km\.?\s*(?P<km>\d{1,4}(?:[.,]\d{1,3})?)(?!\d)")
_R_PREFIXO_NUMERO = re.compile(r"(?:n\s*[o.]\s*\.?|nro\.?|num\.?|numero)$")
_R_COMPLEMENTO = re.compile(
    r"(?:salas?|sl\.|bloco|bl\.|apto\.?|apartamento|ap\.|\d{1,2}\s*o?\s*andar|andar|loja|lj\.|conjunto\s+\d|"
    r"conj\.\s*\d|casa\s+\d|fundos|lote|lt\.|quadra\s+\w|qd\.|box|terreo|piso|anexo|edificio|ed\.|galpao|barracao)(?![\w])"
)
_R_BAIRRO_ROTULO = re.compile(r"(?:bairro|b\.)\s*:?\s*")
_R_BAIRRO_TIPO = re.compile(
    r"(?:jardim|jd\.?|vila|vl\.|parque|pq\.|conjunto|residencial|centro|nucleo|chacara|loteamento|distrito|"
    r"cidade\s+(?:industrial|nova|alta|jardim|universitaria)|portal|recanto|setor)(?![\w])"
)
_UFS = {
    "ac", "al", "ap", "am", "ba", "ce", "df", "es", "go", "ma", "mt", "ms", "mg", "pa", "pb", "pr", "pe",
    "pi", "rj", "rn", "rs", "ro", "rr", "sc", "sp", "se", "to", "parana", "santa catarina", "sao paulo",
}
_R_HORA_OU_DATA = re.compile(r"\d{1,2}\s*h|\d{1,2}:\d{2}|\d{1,2}/\d{1,2}")

# Âncoras: palavras que dizem que o endereço é do evento (ou da entrega).
_R_ANCORA = re.compile(
    r"\b(?:local|realizad[oa]s?|realizacao|sera|serao|no\s+endereco|endereco|entrega|entregar|entregue|"
    r"acontece(?:ra|r)?|ocorre(?:ra|r)?|sediad[oa]|situad[oa]|localizad[oa]|sito|onde)\b"
)
# E as que dizem que o endereço é de outra coisa (de quem escreve, de correspondência).
_R_CONTRA = re.compile(r"\b(?:residente|domiciliad[oa]|resid[ei]|mora|correspondencia|nosso\s+endereco|endereco\s+para\s+resposta)\b")
# O fecho do e-mail: dali para baixo é assinatura, mesmo quando ela não veio separada.
_R_FECHO = re.compile(
    r"(?m)^[ \t]*(?:att\.?|atte\.?|atenciosamente|cordialmente|respeitosamente|abracos|abs\.?|grat[oa]|"
    r"obrigad[oa]|--)[ \t,!.]*$"
)


# ---------------------------------------------------------------------------
# Leitura
# ---------------------------------------------------------------------------


def _eh_maiuscula(palavra: str) -> bool:
    return bool(palavra) and (palavra[0].isupper() or palavra[0].isdigit())


def _limpar(valor: str) -> str:
    return " ".join((valor or "").split()).strip(" ,.;:-–—/")


def _fim_da_regiao(texto: str, dobrado: str, inicio: int) -> int:
    """Até onde vai o endereço: o fim da frase ou da linha — mais as linhas que o continuam."""
    i = inicio
    while True:
        quebra = dobrado.find("\n", i)
        fim_linha = len(dobrado) if quebra == -1 else quebra
        for m in _R_TERMINO.finditer(dobrado, i, fim_linha):
            if m.group() == ".":
                antes = re.search(r"([a-z]+)$", dobrado[max(0, m.start() - 12):m.start()])
                if antes and (antes.group(1) in _ABREVIATURAS or len(antes.group(1)) == 1):
                    continue
            return m.start()
        if quebra == -1:
            return fim_linha
        proxima = quebra + 1
        fim_proxima = dobrado.find("\n", proxima)
        linha = dobrado[proxima:len(dobrado) if fim_proxima == -1 else fim_proxima]
        if not linha.strip() or not _R_CONTINUA.match(linha):
            return fim_linha
        i = proxima


_R_PALAVRA = re.compile(r"[ \t]*(?P<p>[^\s,;:()\[\]/|]+)")
_R_SIGLA_RODOVIA = re.compile(r"(?:br|pr|sc|sp|rs|ms|mg|rj|go|mt|to|ba|pe|ce|pa|am|ro|es|df)[ \t-]?\d{3}(?![\w])")


def _nome(texto: str, dobrado: str, pos: int, fim: int, minusculas: bool) -> tuple[int, bool]:
    """O fim do nome do logradouro que começa em `pos` e se ele tem palavra em maiúscula.

    O nome vai enquanto as palavras começam com maiúscula (ou são "de",
    "da", "dos"...). Um número encerra o nome — é o número do endereço —,
    salvo em "Rua 7 de Setembro". Texto todo em minúsculas vale até cinco
    palavras (`minusculas`: o próprio tipo veio em minúscula, "rua das
    flores"), mas aí só conta como endereço se tiver número ou CEP.
    """
    ultimo, maiuscula, palavras, atual = pos, False, 0, pos
    while True:
        m = _R_PALAVRA.match(texto, atual, fim)
        if not m:
            break
        sigla = _R_SIGLA_RODOVIA.match(dobrado, m.start("p"), fim)
        if sigla:
            # "PR-445", "BR 277": a sigla da rodovia é o nome inteiro.
            atual = ultimo = sigla.end()
            maiuscula = True
            palavras += 1
            continue
        bruta = m.group("p")
        palavra = bruta
        if bruta.endswith(".") and dobrar(bruta[:-1]) not in _ABREVIATURAS:
            palavra = bruta[:-1]
        dobrada = dobrado[m.start("p"):m.start("p") + len(palavra)]
        if not palavra or set(dobrada) <= {"-"}:
            break
        if dobrada in _CONECTORES:
            atual = m.end()
            continue
        if (_R_PREFIXO_NUMERO.fullmatch(dobrada) or re.match(r"km\b|km\d", dobrada)
                or _R_SEM_NUMERO.match(dobrado, m.start("p"))):
            break
        if palavra[0].isdigit():
            # "Rua 7 de Setembro": o número faz parte do nome quando segue "de Nome".
            seguinte = re.match(r"[ \t]+(?:de|da|do)[ \t]+(?P<p>\S+)", texto[m.end():fim])
            if re.fullmatch(r"\d{1,2}", palavra) and seguinte and _eh_maiuscula(seguinte.group("p")):
                atual = ultimo = m.end() + seguinte.end()
                palavras += 1
                maiuscula = True
                continue
            if palavras == 0 and re.fullmatch(r"\d{1,3}", dobrada):
                # "Rua 15, 300": nome numérico, só quando vem outro número depois.
                if re.match(r"[ \t]*,[ \t]*(?:n\s*[o.]\s*)?\d", dobrado[m.end():fim]):
                    atual = ultimo = m.end()
                    palavras += 1
                    maiuscula = True
                    continue
            break
        if _eh_maiuscula(palavra):
            maiuscula = True
        elif not minusculas or maiuscula or palavras >= 5 or not palavra.replace("'", "").isalpha():
            break
        palavras += 1
        atual = ultimo = m.start("p") + len(palavra)
        if palavra != bruta:
            break  # o ponto terminava a frase
    return ultimo, maiuscula


def _pedaco(dobrado: str, pos: int, fim: int) -> int:
    """O fim do pedaço (bairro, complemento, cidade) que começa em `pos`."""
    m = _R_FIM_PEDACO.search(dobrado, pos, fim)
    return m.start() if m else fim


@dataclass
class _Candidato:
    inicio: int
    fim: int
    endereco: Endereco
    pontos: int


def _ler_candidato(texto: str, dobrado: str, inicio: int, fim_tipo: int, fraco: bool) -> _Candidato | None:
    fim = _fim_da_regiao(texto, dobrado, fim_tipo)
    tipo = texto[inicio:fim_tipo]
    fim_nome, maiuscula = _nome(texto, dobrado, fim_tipo, fim, minusculas=bool(tipo) and tipo[0].islower())
    if fim_nome <= fim_tipo:
        return None
    if fraco:
        # "Praça", "Largo", "Linha" só como nome próprio, e não no meio de
        # outro nome ("Campo Largo", "Nova Linha").
        anterior = re.search(r"(\S+)[ \t]+$", texto[max(0, inicio - 40):inicio])
        if not (maiuscula and _eh_maiuscula(tipo)) or (
            anterior and anterior.group(1)[0].isupper() and anterior.group(1)[-1].isalpha()
            and dobrar(anterior.group(1)) not in _PREPOSICOES
        ):
            return None
    nome = _limpar(texto[inicio:fim_nome])
    numero, km = "", ""
    complementos: list[str] = []
    bairro, cep = "", ""
    pos = usado = fim_nome
    while pos < fim:
        sep = _R_SEPARADOR.match(dobrado, pos, fim)
        traco = False
        if sep:
            traco = "-" in sep.group() or "|" in sep.group()
            pos = sep.end()
        if pos >= fim:
            break
        m = _R_CEP.match(dobrado, pos, fim)
        if m and not cep:
            # Oito dígitos sem rótulo nem traço só depois do número ("Rua X, 10, 84010000").
            if dobrado.startswith("cep", pos) or re.search(r"[-.]", m.group("cep")) or numero or bairro or complementos:
                cep = formatar_cep(m.group("cep"))
                pos = usado = m.end()
                continue
        m = _R_KM.match(dobrado, pos, fim)
        if m and not km:
            km = "km " + texto[m.start("km"):m.end("km")]
            pos = usado = m.end()
            continue
        if not numero and not bairro:
            m = _R_SEM_NUMERO.match(dobrado, pos, fim)
            if m:
                numero = "s/n"
                pos = usado = m.end()
                continue
            m = _R_NUMERO.match(dobrado, pos, fim)
            if m:
                numero = texto[m.start("n"):m.end("n")].replace(" ", "").upper() if re.search(r"[a-z]$", m.group("n")) else m.group("n")
                pos = usado = m.end()
                continue
        m = _R_COMPLEMENTO.match(dobrado, pos, fim)
        if m and not bairro:
            fim_pedaco = _pedaco(dobrado, m.end(), fim)
            complementos.append(_limpar(texto[pos:fim_pedaco]))
            pos = usado = fim_pedaco
            continue
        m = _R_BAIRRO_ROTULO.match(dobrado, pos, fim)
        if m and not bairro and m.end() < fim and dobrado[m.end()].isalnum():
            fim_pedaco = _pedaco(dobrado, m.end(), fim)
            bairro = _limpar(texto[m.end():fim_pedaco])
            pos = usado = fim_pedaco
            continue
        m = _R_BAIRRO_TIPO.match(dobrado, pos, fim)
        if m and not bairro:
            fim_pedaco = _pedaco(dobrado, pos, fim)
            bairro = _limpar(texto[pos:fim_pedaco])
            pos = usado = fim_pedaco
            continue
        fim_pedaco = _pedaco(dobrado, pos, fim)
        pedaco = _limpar(dobrado[pos:fim_pedaco])
        if pedaco in _UFS:
            pos = usado = fim_pedaco
            continue
        original = _limpar(texto[pos:fim_pedaco])
        if not _eh_maiuscula(original) or _R_HORA_OU_DATA.search(pedaco) or len(original) > 60 or len(original.split()) > 6:
            break
        # Um nome solto: é a cidade quando vem seguido da UF ("Ponta Grossa/PR",
        # "Curitiba - PR"); é o bairro quando vem depois de um traço ou antes
        # de mais um pedaço ("123, Uvaranas, Ponta Grossa").
        depois = _R_SEPARADOR.match(dobrado, fim_pedaco, fim)
        resto = dobrado[depois.end():fim] if depois else ""
        seguinte = _limpar(resto[:_pedaco(resto, 0, len(resto))]) if resto else ""
        if seguinte in _UFS or bairro:
            pos = usado = fim_pedaco
            continue
        if traco or seguinte:
            bairro = original
            pos = usado = fim_pedaco
            continue
        break
    if not (maiuscula or numero or cep):
        return None
    if not (numero or km or cep or bairro) and fraco:
        # "Praça Central" sozinha é o nome de um lugar, não um endereço.
        return None
    partes = [nome] + [x for x in (km, numero) if x]
    endereco = Endereco(
        logradouro_numero=", ".join(partes)[:255],
        complemento=", ".join(complementos)[:120],
        bairro=bairro[:120],
        cep=cep,
    )
    pontos = 1 + bool(numero or km) + bool(cep) * 2 + bool(bairro)
    return _Candidato(inicio, max(usado, fim_nome), endereco, pontos)


def _cep_solto(m) -> _Candidato:
    """Só o CEP (com rótulo), sem logradouro reconhecível por perto."""
    endereco = Endereco(cep=formatar_cep(m.group("cep")))
    return _Candidato(m.start(), m.end(), endereco, 0)


def _trecho(texto: str, inicio: int, fim: int) -> str:
    comeco = max(texto.rfind("\n", 0, inicio) + 1, inicio - 80)
    fim_linha = texto.find("\n", fim)
    fim_linha = len(texto) if fim_linha == -1 else fim_linha
    return " ".join(texto[comeco:min(fim_linha, fim + 60)].split())[:300]


def _ancorado(dobrado: str, inicio: int) -> tuple[bool, bool]:
    """(tem âncora de evento/entrega, tem âncora contrária) logo antes do endereço."""
    paragrafo = dobrado.rfind("\n\n", 0, inicio)
    comeco = max(paragrafo + 2 if paragrafo != -1 else 0, inicio - 120)
    antes = dobrado[comeco:inicio]
    # A âncora contrária vale só colada ao endereço ("residente na Rua X"):
    # o mesmo e-mail pode citar a casa de alguém e, adiante, o local do evento.
    return bool(_R_ANCORA.search(antes)), bool(_R_CONTRA.search(dobrado[max(comeco, inicio - 40):inicio]))


def _trechos_da_assinatura(texto: str, dobrado: str, assinatura: str) -> list[tuple[int, int]]:
    """Onde a assinatura está dentro do texto (colada ou depois do fecho)."""
    trechos = []
    assinatura = (assinatura or "").strip()
    if assinatura:
        achou = texto.find(assinatura)
        if achou == -1:
            primeira = assinatura.split("\n", 1)[0].strip()
            achou = texto.rfind(primeira) if len(primeira) >= 8 else -1
        if achou != -1:
            trechos.append((achou, len(texto)))
    fechos = list(_R_FECHO.finditer(dobrado))
    if fechos:
        trechos.append((fechos[-1].start(), len(texto)))
    return trechos


def endereco_no_texto(texto: str, assinatura: str = "") -> Endereco | None:
    """O endereço do evento (ou da entrega) citado no texto, ou None.

    Com vários endereços, fica o que tem palavra-âncora antes ("local",
    "será realizado", "no endereço", "entrega"), depois o mais completo
    (número, CEP, bairro) e, empatando, o primeiro. O que está na
    `assinatura` (ou depois do fecho "Atenciosamente") é de quem escreve,
    não do evento: não conta.
    """
    texto = texto or ""
    if not texto.strip():
        return None
    dobrado = dobrar(texto)
    fora = _trechos_da_assinatura(texto, dobrado, assinatura)

    def na_assinatura(pos: int) -> bool:
        return any(a <= pos < b for a, b in fora)

    candidatos: list[_Candidato] = []
    ocupado_ate = -1
    achados = sorted(
        [(m.start(), m.end(), m.group("tipo").strip() in _TIPOS_FRACOS) for m in _R_TIPO.finditer(dobrado)]
        + [(m.start(), m.start(), False) for m in _R_RODOVIA.finditer(dobrado)]
    )
    for inicio, fim_tipo, fraco in achados:
        if inicio < ocupado_ate or na_assinatura(inicio):
            continue
        if fim_tipo == inicio:
            # Rodovia sem a palavra: o "tipo" é a própria sigla ("PR-445").
            candidato = _ler_candidato(texto, dobrado, inicio, inicio, False)
        else:
            candidato = _ler_candidato(texto, dobrado, inicio, fim_tipo, fraco)
        if candidato is not None:
            candidatos.append(candidato)
            ocupado_ate = candidato.fim
    for m in _R_CEP_ROTULADO.finditer(dobrado):
        if na_assinatura(m.start()) or any(c.inicio <= m.start() < c.fim for c in candidatos):
            continue
        candidatos.append(_cep_solto(m))
    if not candidatos:
        return None

    melhores = []
    for candidato in candidatos:
        ancora, contra = _ancorado(dobrado, candidato.inicio)
        pontos = candidato.pontos + (4 if ancora else 0) - (5 if contra else 0)
        melhores.append((pontos, -candidato.inicio, candidato, ancora))
    pontos, _, escolhido, ancora = max(melhores, key=lambda x: (x[0], x[1]))
    if pontos < 0:
        return None
    e = escolhido.endereco
    return Endereco(
        logradouro_numero=e.logradouro_numero,
        complemento=e.complemento,
        bairro=e.bairro,
        cep=e.cep,
        trecho=_trecho(texto, escolhido.inicio, escolhido.fim),
        ancorado=ancora,
    )

