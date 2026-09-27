"""As unidades da PCPR citadas num release: qual manda a pauta e qual só apoiou.

O release cita várias unidades ("a DP de Irati, com apoio do COPE…"); a da
pauta é a de quem manda. Por isso cada citação vira uma `Mencao` com o que
identifica a unidade (tipo, número, cidade) e ganha pontos pelo lugar onde
aparece: assinatura e nome do contato valem mais que o assunto, que vale
mais que o texto; parceira ("com apoio da", "em ação conjunta com",
"vinculada à", "procurado pela", "origem do BO") não conta.

O cadastro é lido do mesmo jeito, então "13 SDP", "13ª Subdivisão Policial"
e "SDP de Ponta Grossa" casam com "13ª Subdivisão Policial de Ponta Grossa";
"Divisão Estadual de Narcóticos" casa com "DENARC".
"""

from __future__ import annotations

import re
from dataclasses import dataclass, replace

from core.leitura.datas import dobrar
from core.planilhas import canonizar_unidade


@dataclass(frozen=True)
class Tipo:
    chave: str
    nome: str  # como vai para "Outra unidade"
    extenso: str  # regex no texto dobrado (minúsculas, sem acento)
    siglas: tuple = ()
    por_cidade: bool = False  # há uma em cada cidade (DP, Delegacia da Mulher…)
    numerada: bool = False  # "13ª SDP", "10ª DP"
    solto: str = ""  # forma sem "Delegacia", só no contato/assinatura/assunto ("Furtos e Roubos")


# Do mais longo ao mais curto: "Delegacia de Furtos e Roubos de Veículos" antes
# de "Delegacia de Furtos e Roubos".
TIPOS = (
    Tipo("SDP", "Subdivisão Policial", r"subdivisao policial", ("SDP",), True, True),
    Tipo("DRP", "Delegacia Regional de Polícia", r"delegacia regional(?: de policia)?", ("DRP",), True, True),
    Tipo("DM", "Delegacia da Mulher",
         r"delegacia (?:especializada )?(?:da mulher|de (?:atendimento|defesa|protecao) (?:a|da) mulher)",
         ("DM", "DEAM", "DDM"), True),
    Tipo("DHPP", "Divisão de Homicídios e Proteção à Pessoa", r"divisao de homicidios e protecao a pessoa", ("DHPP",)),
    Tipo("DH", "Delegacia de Homicídios", r"delegacia de homicidios", ("DH",), True, True, r"homicidios"),
    Tipo("DENARC", "Divisão Estadual de Narcóticos", r"divisao estadual de narcoticos", ("DENARC",)),
    Tipo("NUCRIA", "Núcleo de Proteção à Criança e ao Adolescente Vítimas de Crimes",
         r"nucleo de protecao a crianca e ao adolescente(?: vitimas de crimes)?", ("NUCRIA",), True),
    Tipo("NUCIBER", "Núcleo de Combate aos Cibercrimes", r"nucleo de combate aos? ciber ?crimes", ("NUCIBER",)),
    Tipo("COPE", "Centro de Operações Policiais Especiais", r"centro de operacoes policiais especiais", ("COPE",)),
    Tipo("DFRV", "Delegacia de Furtos e Roubos de Veículos", r"delegacia de furtos e roubos de veiculos", ("DFRV",),
         solto=r"furtos e roubos de veiculos"),
    Tipo("DFR", "Delegacia de Furtos e Roubos", r"delegacia de furtos e roubos", ("DFR",), solto=r"furtos e roubos"),
    Tipo("DEDC", "Delegacia de Estelionato e Desvio de Cargas", r"delegacia de estelionato(?: e desvio de cargas)?",
         solto=r"estelionato"),
    Tipo("DP", "Delegacia de Polícia", r"delegacia de policia(?: civil)?", ("DP",), True, True),
)
_POR_CHAVE = {t.chave: t for t in TIPOS}
SIGLAS = {s: t for t in TIPOS for s in t.siglas}

# Abreviações de cidade que as delegacias usam na assinatura ("DM PG").
ABREVIACOES_CIDADE = {
    "pg": "Ponta Grossa", "foz": "Foz do Iguaçu", "cwb": "Curitiba", "sjp": "São José dos Pinhais",
    "uva": "União da Vitória",
}

# O número colado na unidade, na mesma linha: "13ª SDP", "13 SDP" (não o "BR-277" da linha de cima).
_NUMERO = r"(?:(?<![\d.,/-])(?P<numero>\d{1,3})[ \t]*(?:[ªºo°]|a\.?)?[ \t]*)?"
_R_EXTENSO = re.compile(
    r"(?<![a-z0-9])" + _NUMERO + r"(?P<tipo>" + "|".join(f"(?P<{t.chave}>{t.extenso})" for t in TIPOS) + r")(?![a-z0-9])"
)
_R_SOLTO = re.compile(
    r"(?<![a-z0-9])(?P<tipo>" + "|".join(f"(?P<{t.chave}>{t.solto})" for t in TIPOS if t.solto) + r")(?![a-z0-9])"
)
# Siglas no texto original: as de 2–3 letras só em maiúsculas ("DP", não "dp");
# as maiores em qualquer caixa ("Nucria", "Nuciber").
_R_SIGLA = re.compile(r"(?<![\wÀ-ÿ])" + _NUMERO + r"(?P<sigla>[A-Za-z]{2,8})(?![\wÀ-ÿ])")
# "Delegacia de Tibagi", "Delegacia de Explosivos, Armas e Munições": o resto em maiúscula.
_R_DELEGACIA_DE = re.compile(
    r"\bDelegacia\s+(?:de|do|da|dos|das)\s+"
    r"(?P<resto>[A-ZÀ-Ý][\wÀ-ÿ'-]*(?:(?:[ \t]*,[ \t]*|[ \t]+(?:e|de|do|da|dos|das)[ \t]+|[ \t]+)[A-ZÀ-Ý][\wÀ-ÿ'-]*)*)"
)
# "Sigla (definição)": "Delegacia de Explosivos, Armas e Munições (DEAM)" diz o que é a DEAM neste texto.
_R_PARENTESE = re.compile(r"\s*\(\s*(?P<sigla>[A-Za-zÀ-ÿ]{2,10})\s*\)")

_CONECTIVOS = r"(?:d[aeo]s?|n[ao]s?|pel[ao]s?|com|a|o|as|os|à|ao|aos|e|de|um|uma|equipes?|policiais|agentes|UNIDADE)"
# Parceira: quem apoiou, colaborou, procurava o preso ou registrou o BO.
_R_PARCEIRA_ANTES = re.compile(
    r"(?:(?:coordenad[ao]|integrad[ao]|conjunt[ao]|junto|parceria)\s+com|apoio|ajuda|auxilio|vinculad[ao]|"
    r"subordinad[ao]|procurad[ao]|informac(?:ao|oes)|inteligencia|boletim|ocorrencia|origem|registrou|registrad[ao])"
    r"(?:\s+" + _CONECTIVOS + r"){0,5}\s*$"
)
_R_PARCEIRA_DEPOIS = re.compile(
    r"^\s*,?\s*(?:que\s+)?(?:colaborou|compartilhou|cedeu|apoiou|auxiliou|deu apoio|participou|forneceu|ajudou|"
    r"contribuiu|repassou)"
)
# Quem manda: "Segue release da DFRV", "Aqui é da Delegacia de…", "material da 13 SDP".
_R_REMETENTE_ANTES = re.compile(
    r"(?:segue|seguem|encaminh\w*|envi\w*|material|release|texto|nota|materia|aqui e|sou|somos|divulga\w*|"
    r"publica\w*|mais uma)\b[^.!?\n]{0,40}?\b(?:d[aoe]s?|pel[ao])\s*$"
)
# Sujeito do release: "A DHPP prendeu", "por meio da DP de…", "presos pela SDP…".
_R_AGENTE_ANTES = re.compile(
    r"(?:(?:^|[.!?:\n]\s*)(?:a|o|as|os)?|por meio d[aoe]s?|atraves d[aoe]s?|pel[ao]s?|"
    r"(?:policiais|investigadores|agentes|equipes?)(?: civis)? d[aoe]s?)\s*$"
)

PONTOS = {"assinatura": 100, "contato": 90, "remetente": 80, "assunto": 70, "agente": 60, "texto": 30}


@dataclass(frozen=True)
class Mencao:
    tipo: str  # chave de `TIPOS` ou "ESP" (delegacia especializada fora da lista)
    numero: int | None
    cidade: str | None
    especialidade: str  # só para "ESP": "Explosivos, Armas e Munições"
    inicio: int
    fim: int
    trecho: str
    pontos: int = 0

    @property
    def determinada(self) -> bool:
        """Dá para saber qual é? "a DP" sozinha não diz qual delegacia."""
        tipo = _POR_CHAVE.get(self.tipo)
        return tipo is None or not tipo.por_cidade or bool(self.cidade or self.numero)

    def nome(self) -> str:
        """O nome para "Outra unidade"."""
        if self.tipo == "ESP":
            base = f"Delegacia de {self.especialidade}"
            return f"{base} de {self.cidade}" if self.cidade else base
        tipo = _POR_CHAVE[self.tipo]
        if self.numero:
            # Grafia do cadastro para as numeradas: "10ª DP de Curitiba".
            nome = canonizar_unidade(f"{self.numero} {tipo.siglas[0]}")
        else:
            nome = tipo.nome
        return f"{nome} de {self.cidade}" if self.cidade else nome


def _chave(texto: str) -> str:
    return " ".join(re.findall(r"[a-z0-9]+", dobrar(texto or "")))


class Leitor:
    """Acha unidades num texto; `municipios` são os nomes do cadastro (para "DP Irati")."""

    def __init__(self, municipios=()):
        self.municipios = {_chave(m): m for m in municipios if m}
        self.maior = max((len(c.split()) for c in self.municipios), default=1)
        # Siglas definidas no próprio e-mail ("… Munições (DEAM)"), valem para o assunto também.
        self.definicoes: dict[str, Mencao] = {}

    def aprender(self, *textos: str) -> None:
        """Lê as definições de sigla de todos os textos antes de pontuar."""
        for texto in textos:
            self.mencoes(texto)

    # -- cidade -------------------------------------------------------------

    def cidade_em(self, texto: str, pos: int, abreviacao: bool = True) -> tuple[str | None, int]:
        """O município que começa em `pos` ("Foz do Iguaçu/PR"), pela lista ou pela abreviação."""
        palavras = [(m.group(0), m.end()) for m in re.finditer(r"[\wÀ-ÿ'-]+", texto[pos:pos + 80])]
        # Só palavras seguidas de espaço entram no mesmo nome ("Ponta Grossa/PR" para no "/").
        seguidas = []
        for i, (palavra, fim) in enumerate(palavras[: self.maior]):
            if i and not re.fullmatch(r"\s+", texto[pos + palavras[i - 1][1]: pos + fim - len(palavra)]):
                break
            seguidas.append((palavra, fim))
        if not seguidas:
            return None, pos
        for n in range(len(seguidas), 0, -1):
            chave = _chave(" ".join(p for p, _ in seguidas[:n]))
            if chave in self.municipios:
                return self.municipios[chave], pos + seguidas[n - 1][1]
        abreviada = abreviacao and ABREVIACOES_CIDADE.get(_chave(seguidas[0][0]))
        if abreviada:
            return abreviada, pos + seguidas[0][1]
        return None, pos

    def _cidade_depois(self, texto: str, fim: int) -> tuple[str | None, int]:
        """A cidade logo depois da unidade: "de Palmas", " Irati", " – Ponta Grossa", "(Nucria) de Curitiba"."""
        m = _R_PARENTESE.match(texto, fim)
        pos = m.end() if m else fim
        m = re.match(r"\s*(?:(?P<de>de|do|da|em)\s+|[-–—,/:]\s*)?", texto[pos:])
        inicio = pos + m.end()
        cidade, fim_cidade = self.cidade_em(texto, inicio)
        if cidade:
            return cidade, fim_cidade
        # Sem a lista de municípios, "de" + nome próprio ainda é a cidade ("10ª DP de Curitiba").
        if m.group("de"):
            nome = re.match(r"[A-ZÀ-Ý][\wÀ-ÿ'-]*(?:\s+(?:d[aeo]s?\s+)?[A-ZÀ-Ý][\wÀ-ÿ'-]*){0,3}", texto[inicio:])
            if nome and not self.municipios:
                return nome.group(0), inicio + nome.end()
        return None, fim

    def _cidade_na_linha(self, texto: str, fim: int) -> str | None:
        """Assinatura "Delegacia da Mulher – 15ª SDP – Cascavel/PR": a cidade mais adiante na linha."""
        fim_linha = texto.find("\n", fim)
        fim_linha = len(texto) if fim_linha < 0 else fim_linha
        for m in re.finditer(r"[\wÀ-ÿ'-]+", texto[fim:fim_linha]):
            cidade, _ = self.cidade_em(texto, fim + m.start())
            if cidade:
                return cidade
        return None

    # -- menções ------------------------------------------------------------

    def mencoes(self, texto: str, *, solto: bool = False, linha: bool = False) -> list[Mencao]:
        """As unidades citadas em `texto`, na ordem. `solto` aceita "Furtos e Roubos" sem
        "Delegacia" (nome de contato, assinatura); `linha` procura a cidade no resto da linha."""
        texto = texto or ""
        dobrado = dobrar(texto)
        achadas: list[Mencao] = []
        ocupado: list[tuple[int, int]] = []
        definicoes = self.definicoes

        def livre(a, b):
            return all(b <= x or a >= y for x, y in ocupado)

        def nova(tipo, numero, especialidade, inicio, fim):
            cidade, fim_cidade = (None, fim)
            if tipo == "ESP" or _POR_CHAVE[tipo].por_cidade:
                cidade, fim_cidade = self._cidade_depois(texto, fim)
                if cidade is None and linha:
                    cidade = self._cidade_na_linha(texto, fim)
            mencao = Mencao(tipo, int(numero) if numero else None, cidade, especialidade, inicio, max(fim, fim_cidade),
                            " ".join(texto[inicio:max(fim, fim_cidade)].split()))
            achadas.append(mencao)
            ocupado.append((inicio, max(fim, fim_cidade)))
            definicao = _R_PARENTESE.match(texto, fim)
            if definicao:
                definicoes[definicao.group("sigla").upper()] = mencao
                ocupado.append((definicao.start("sigla"), definicao.end("sigla")))
            return mencao

        for m in _R_EXTENSO.finditer(dobrado):
            tipo = next(t for t in TIPOS if m.group(t.chave))
            numero = m.group("numero") if tipo.numerada else None
            inicio = m.start() if numero else m.start("tipo")
            if livre(inicio, m.end()):
                nova(tipo.chave, numero, "", inicio, m.end())
        for m in _R_DELEGACIA_DE.finditer(texto):
            if not livre(m.start(), m.end()):
                continue
            resto = m.group("resto")
            cidade, fim_cidade = self.cidade_em(texto, m.start("resto"))
            if cidade and fim_cidade >= m.end("resto") - 1:
                # "Delegacia de Pato Branco": a delegacia da cidade.
                achadas.append(Mencao("DP", None, cidade, "", m.start(), fim_cidade, texto[m.start():fim_cidade]))
                ocupado.append((m.start(), fim_cidade))
                continue
            # "Delegacia de X de Cidade": a especialidade e a cidade.
            partes = re.match(r"(?P<esp>.+?)\s+(?:de|do|da)\s+(?P<cid>[^,]+)$", resto)
            if partes:
                cidade, fim_cidade = self.cidade_em(texto, m.start("resto") + partes.start("cid"))
                if cidade:
                    fim = m.start("resto") + partes.end("esp")
                    nova("ESP", None, partes.group("esp"), m.start(), fim)
                    continue
            nova("ESP", None, resto, m.start(), m.end())
        if solto:
            for m in _R_SOLTO.finditer(dobrado):
                tipo = next(t.chave for t in TIPOS if t.solto and m.group(t.chave))
                if not livre(m.start(), m.end()):
                    continue
                # "Homicídios" solto só com a cidade ao lado ("Homicídios Londrina").
                if _POR_CHAVE[tipo].por_cidade and not self._cidade_depois(texto, m.end())[0]:
                    continue
                nova(tipo, None, "", m.start(), m.end())
        for m in _R_SIGLA.finditer(texto):
            sigla = m.group("sigla")
            maiuscula = sigla.upper()
            if not livre(m.start("sigla"), m.end("sigla")):
                continue
            if len(sigla) <= 3 and sigla != maiuscula:
                continue
            definida = definicoes.get(maiuscula)
            if definida is not None:
                achadas.append(replace(definida, inicio=m.start(), fim=m.end(), trecho=m.group(0).strip()))
                ocupado.append((m.start(), m.end()))
                continue
            tipo = SIGLAS.get(maiuscula)
            if tipo is None:
                continue
            inicio = m.start() if m.group("numero") else m.start("sigla")
            nova(tipo.chave, m.group("numero") if tipo.numerada else None, "", inicio, m.end())
        achadas.sort(key=lambda x: x.inicio)
        return _completar_cidade(achadas)

    # -- pontos -------------------------------------------------------------

    def pontuadas(self, texto: str, fonte: str, **opcoes) -> list[Mencao]:
        """As menções de `texto` com os pontos pelo lugar; parceiras ficam de fora."""
        mencoes = self.mencoes(texto, **opcoes)
        dobrado = dobrar(texto or "")
        saida = []
        for mencao in mencoes:
            base = max(0, mencao.inicio - 90)
            antes = dobrado[base:mencao.inicio]
            # "apoio do COPE e da PM": a 2ª também é parceira. Da direita para a
            # esquerda, para as posições das outras não mudarem.
            for outra in sorted(mencoes, key=lambda x: -x.inicio):
                if outra is not mencao and base <= outra.inicio and outra.fim <= mencao.inicio:
                    antes = antes[: outra.inicio - base] + "UNIDADE" + antes[outra.fim - base:]
            pedacos = re.split(r"[;!?\n]|\.\s", antes)
            # Janela cortada no meio da frase: o começo dela não é o começo da frase.
            antes = pedacos[-1] if len(pedacos) > 1 or mencao.inicio <= 90 else "… " + antes
            depois = dobrado[mencao.fim:mencao.fim + 40]
            if _R_PARCEIRA_ANTES.search(antes) or _R_PARCEIRA_DEPOIS.match(depois):
                continue
            pontos = PONTOS[fonte]
            if fonte == "texto":
                if _R_REMETENTE_ANTES.search(antes):
                    pontos = PONTOS["remetente"]
                elif _R_AGENTE_ANTES.search(antes):
                    pontos = PONTOS["agente"]
            saida.append(replace(mencao, pontos=pontos))
        return saida


def _completar_cidade(mencoes: list[Mencao]) -> list[Mencao]:
    """"Nucria" sem cidade e "Nucria de Curitiba" no mesmo texto: a mesma unidade."""
    saida = []
    for mencao in mencoes:
        if mencao.cidade is None and mencao.numero is None:
            irma = next((m for m in mencoes if m.tipo == mencao.tipo and m.cidade
                         and m.especialidade == mencao.especialidade), None)
            if irma is not None:
                mencao = replace(mencao, cidade=irma.cidade, numero=irma.numero)
        saida.append(mencao)
    return saida


# ---------------------------------------------------------------------------
# Cadastro
# ---------------------------------------------------------------------------


def _mesma(mencao: Mencao, cadastro: Mencao) -> int:
    """Quanto a menção casa com o cadastro: 0 não casa; mais é melhor."""
    if mencao.tipo != cadastro.tipo:
        return 0
    if mencao.tipo == "ESP":
        a, b = _chave(mencao.especialidade), _chave(cadastro.especialidade)
        if not (a == b or b.startswith(a + " ")):
            return 0
    pontos = 1
    for campo in ("numero", "cidade"):
        x, y = getattr(mencao, campo), getattr(cadastro, campo)
        if x and y:
            if _chave(str(x)) != _chave(str(y)):
                return 0
            pontos += 2
    # "DP de Palmeira" não é um cadastro "DP" sem cidade: a cidade dita tem que bater.
    if mencao.cidade and not cadastro.cidade and pontos == 1:
        return 0
    return pontos


def no_cadastro(mencao: Mencao, cadastros: list[tuple[object, Mencao]]):
    """O cadastro desta menção, se um só casa (ou um casa melhor que os outros)."""
    notas = sorted(((_mesma(mencao, lida), unidade) for unidade, lida in cadastros), key=lambda x: -x[0])
    notas = [(n, u) for n, u in notas if n]
    if not notas:
        return None
    if len(notas) > 1 and notas[0][0] == notas[1][0]:
        return None
    melhor, unidade = notas[0]
    # "a DP" sem cidade nem número só serve se há uma única DP no cadastro.
    if melhor == 1 and _POR_CHAVE.get(mencao.tipo, None) and _POR_CHAVE[mencao.tipo].por_cidade and len(notas) > 1:
        return None
    return unidade


def ler_cadastros(unidades, leitor: Leitor) -> list[tuple[object, Mencao]]:
    """Cada unidade do cadastro com a menção que o próprio nome faz ("DHPP", "13ª Subdivisão…")."""
    lidas = []
    for unidade in unidades:
        mencoes = leitor.mencoes(unidade.nome, solto=True)
        if mencoes:
            lidas.append((unidade, mencoes[0]))
    return lidas
