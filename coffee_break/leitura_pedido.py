"""Leituras próprias do pedido de coffee break: quantidade, horário, evento, local e quem recebe.

O pedido de coffee tem jeito próprio de escrever ("2 turmas de 25", "coffee
às 15h30, a palestra começa às 14h", "Recebe: Escrivã X", "Entrega: Auditório
Y, Rua Z"), por isso estas regras moram no módulo e não em `core.leitura`.
Todas trabalham no texto dobrado (`dobrar`: minúsculo, sem acento e com o
mesmo comprimento), e as posições valem para o original.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import time

from core.leitura.datas import dobrar, horarios_do_texto

# ---------------------------------------------------------------------------
# Quantidade
# ---------------------------------------------------------------------------

_UNIDADES = {
    "um": 1, "uma": 1, "dois": 2, "duas": 2, "tres": 3, "quatro": 4, "cinco": 5, "seis": 6, "sete": 7,
    "oito": 8, "nove": 9, "dez": 10, "onze": 11, "doze": 12, "treze": 13, "quatorze": 14, "catorze": 14,
    "quinze": 15, "dezesseis": 16, "dezessete": 17, "dezoito": 18, "dezenove": 19,
}
_DEZENAS = {
    "vinte": 20, "trinta": 30, "quarenta": 40, "cinquenta": 50, "sessenta": 60,
    "setenta": 70, "oitenta": 80, "noventa": 90,
}
_CENTENAS = {
    "cem": 100, "cento": 100, "duzentos": 200, "duzentas": 200, "trezentos": 300, "trezentas": 300,
    "quatrocentos": 400, "quinhentos": 500,
}
_PALAVRAS_NUMERO = {**_UNIDADES, **_DEZENAS, **_CENTENAS}
_R_EXTENSO = re.compile(
    r"\b(?:" + "|".join(sorted(_PALAVRAS_NUMERO, key=len, reverse=True)) + r")"
    r"(?:\s+e\s+(?:" + "|".join(sorted(_PALAVRAS_NUMERO, key=len, reverse=True)) + r"))*\b"
)


def _extenso_para_numero(dobrado: str) -> str:
    """"quarenta pessoas" -> "40 pessoas", "vinte e cinco" -> "25".

    "um"/"uma" sozinhos ficam como estão ("um coffee" não é quantidade).
    """

    def trocar(m):
        partes = re.split(r"\s+e\s+", m.group(0))
        if len(partes) == 1 and partes[0] in ("um", "uma"):
            return m.group(0)
        return str(sum(_PALAVRAS_NUMERO[p] for p in partes))

    return _R_EXTENSO.sub(trocar, dobrado)


_PESSOAS = (
    r"(?:pessoas?|pesoas?|pessoal|participantes|alunos|alunas|convidados|servidores|policiais|kits?|"
    r"integrantes|inscritos|agentes|delegados|estudantes|lanches|unidades|pax)"
)
# Número que não é gente: hora, data, ordinal, km, andar, ramal.
_NAO_QUANTIDADE = r"(?!\s*(?:h\b|hs\b|horas?|min|:|/|\.\d|º|ª|o\b|a\b|km|andar))"
# "30 alunos + 10 instrutores": a soma.
_R_SOMA = re.compile(r"\b(?P<a>\d{1,4})\s+[a-z]+\s*\+\s*(?P<b>\d{1,4})\s+[a-z]+")
# "2 turmas de 25": o produto.
_R_TURMAS = re.compile(r"\b(?P<a>\d{1,2})\s+turmas?\s+de\s+(?P<b>\d{1,4})\b")
# "40 pessoas", "80 kits de lanche", "80 (80) convidados", "efetivo de 35 policiais".
_R_COM_UNIDADE = re.compile(r"\b(?P<n>\d{1,4})\s*(?:\([^)]{1,30}\)\s*)?" + _PESSOAS + r"\b")
# "Quantidade: 25", "Pessoas: 45".
_R_ROTULO = re.compile(r"\b(?:quantidade|pessoas|participantes|publico(?:\s+estimado)?|efetivo)\s*[:=]\s*(?P<n>\d{1,4})\b")
# "coffee para 30", "kits pra 30", "coffee p 20", "mandar coffee para 50".
_R_PARA_N = re.compile(
    r"\b(?:cof+e+(?:[\s-]?break)?|cafe|lanches?|kits?)\b[^.\n]{0,40}?\b(?:para|pra|p/?|p\.)\s+"
    r"(?:cerca\s+de\s+|aproximadamente\s+|aprox\.?\s+|uns\s+|umas\s+|ate\s+)?(?P<n>\d{1,4})\b" + _NAO_QUANTIDADE
)
# "uns 40", "cerca de 60" soltos.
_R_CERCA = re.compile(r"\b(?:uns|umas|cerca\s+de|aproximadamente|efetivo\s+de)\s+(?P<n>\d{1,4})\b" + _NAO_QUANTIDADE)
# "entre 40 e 50 pessoas": faixa, vale só se nada mais firme aparecer.
_R_FAIXA = re.compile(r"\bentre\s+\d{1,4}\s+e\s+(?P<n>\d{1,4})\b")
# O que veio antes e foi desfeito: "(dia 14/10, 20 pessoas)" depois de
# "desconsiderar o pedido anterior", "(que foi para 25 pessoas)", "e não 40".
_R_PARENTESE = re.compile(r"\([^()]*\)")
_R_ANTERIOR = re.compile(r"\b(?:anterior|desconsider\w*|foi|foram|era|eram)\b")
_R_E_NAO = re.compile(r"\be\s+nao\s+\d{1,4}\b[^.\n]*")
# Correção: vale o que vem depois ("corrigindo, serão 36").
_R_CORRECAO = re.compile(r"\b(?:corrig\w*|correcao|retific\w*|desconsider\w*|na\s+verdade|o\s+novo\s+pedido)\b")


@dataclass
class Quantidade:
    valor: int
    trecho: str
    confianca: str = "M"


def _apagar(texto: str, inicio: int, fim: int) -> str:
    return texto[:inicio] + " " * (fim - inicio) + texto[fim:]


def quantidade_do_texto(texto: str) -> Quantidade | None:
    """Quantas pessoas (ou kits) o coffee atende.

    Soma e produto quando o e-mail os dá ("2 turmas de 25" = 50, "30 alunos
    + 10 instrutores" = 40); com correção ("corrigindo, serão 36"), vale a
    última; com dois lotes ("50 hoje e outro para 20"), vale o primeiro.
    """
    if not texto:
        return None
    dobrado = _extenso_para_numero(dobrar(texto))
    # Tira o que foi desfeito, mantendo as posições.
    limpo = dobrado
    for m in _R_PARENTESE.finditer(dobrado):
        antes = dobrado[max(0, m.start() - 40):m.start()]
        if _R_ANTERIOR.search(m.group(0)) or _R_ANTERIOR.search(antes):
            limpo = _apagar(limpo, m.start(), m.end())
    for m in _R_E_NAO.finditer(limpo):
        limpo = _apagar(limpo, m.start(), m.end())

    achados: list[tuple[int, int, bool, str]] = []  # (posição, valor, fraco, trecho)
    tomados: list[tuple[int, int]] = []

    def livre(inicio, fim):
        return all(fim <= a or inicio >= b for a, b in tomados)

    for regex, conta in ((_R_TURMAS, lambda a, b: a * b), (_R_SOMA, lambda a, b: a + b)):
        for m in regex.finditer(limpo):
            achados.append((m.start(), conta(int(m.group("a")), int(m.group("b"))), False, dobrado[m.start():m.end()]))
            tomados.append((m.start(), m.end()))
    for m in _R_FAIXA.finditer(limpo):
        achados.append((m.start(), int(m.group("n")), True, dobrado[m.start():m.end()]))
        tomados.append((m.start(), m.end() + 12))
    for regex in (_R_ROTULO, _R_COM_UNIDADE, _R_PARA_N, _R_CERCA):
        for m in regex.finditer(limpo):
            if livre(m.start("n"), m.end("n")):
                achados.append((m.start("n"), int(m.group("n")), False, dobrado[m.start():m.end()]))
    achados = [a for a in achados if 0 < a[1] <= 10000]
    if not achados:
        return None
    firmes = [a for a in achados if not a[2]] or achados
    correcao = None
    for m in _R_CORRECAO.finditer(limpo):
        correcao = m
    if correcao is not None:
        depois = [a for a in firmes if a[0] >= correcao.start()]
        if depois:
            firmes = depois
    escolhido = min(firmes, key=lambda a: a[0])
    return Quantidade(escolhido[1], escolhido[3].strip())


# ---------------------------------------------------------------------------
# Horário
# ---------------------------------------------------------------------------

R_COFFEE = re.compile(r"\b(?:cof+e+(?:[\s-]?break)?|cafe|lanches?|kits?|intervalo|servir|servido|servirmos|entrega|entregar)\b")
_R_DEPOIS_COFFEE = re.compile(r"^\s*[-–—:]\s*(?:cof+e+|cafe|lanche|intervalo)")


@dataclass
class Hora:
    valor: time
    trecho: str
    do_coffee: bool


def _hora_certa(texto: str, dobrado: str, horario) -> time:
    """Conserta o que o leitor geral junta demais: "15h\\n30 participantes" é 15h; "8 e meia" é 8h30."""
    hora = horario.inicio
    trecho = texto[horario.inicio_pos:horario.fim_pos]
    if "\n" in trecho and hora.minute:
        hora = time(hora.hour, 0)
    if hora.minute == 0 and re.match(r"\s+e\s+meia\b", dobrado[horario.fim_pos:]):
        hora = time(hora.hour, 30)
    return hora


def horario_do_texto(texto: str) -> Hora | None:
    """O horário do coffee ("coffee às 15h30", "10h – coffee break"); senão, o primeiro citado."""
    if not texto:
        return None
    dobrado = dobrar(texto)
    horarios = horarios_do_texto(texto)
    for horario in horarios:
        antes = dobrado[max(0, horario.inicio_pos - 60):horario.inicio_pos]
        frase = antes[max(antes.rfind("\n"), antes.rfind(". ")) + 1:]
        depois = dobrado[horario.fim_pos:horario.fim_pos + 20]
        if R_COFFEE.search(frase) or _R_DEPOIS_COFFEE.match(depois):
            trecho = texto[max(0, horario.inicio_pos - len(frase)):horario.fim_pos].strip()
            return Hora(_hora_certa(texto, dobrado, horario), trecho, True)
    if horarios:
        horario = horarios[0]
        return Hora(_hora_certa(texto, dobrado, horario), texto[horario.inicio_pos:horario.fim_pos].strip(), False)
    return None


# ---------------------------------------------------------------------------
# Texto corrido: junta as linhas quebradas no meio da frase
# ---------------------------------------------------------------------------

_ENDERECO = r"(?:rua|r\.|av\.?|avenida|rodovia|rod\.|travessa|alameda|estrada|praca|br-\d|pr-\d)"
_R_LINHA_NOVA = re.compile(r"^\s*(?:" + _ENDERECO + r"|[^\n:]{1,40}:|\[|-{2,}|cep\b)")


def corrido(texto: str) -> str:
    """As quebras de linha que só cortam a frase viram espaço (mesmo comprimento).

    A quebra fica quando a linha seguinte começa um endereço ("Rua ...", "Av."),
    um rótulo ("Recebe: ...") ou quando há linha em branco.
    """
    saida = list(texto)
    dobrado = dobrar(texto)
    for m in re.finditer(r"\n", texto):
        i = m.start()
        anterior = texto[:i].rsplit("\n", 1)[-1]
        seguinte = dobrado[i + 1:].split("\n", 1)[0]
        # Linha que termina em ponto fecha a frase; a seguinte começa outra.
        if not anterior.strip() or anterior.rstrip().endswith(".") or not seguinte.strip() or _R_LINHA_NOVA.match(seguinte):
            continue
        saida[i] = " "
    return "".join(saida)


# ---------------------------------------------------------------------------
# Descrição do evento
# ---------------------------------------------------------------------------

_EVENTOS = (
    r"curso|reuniao|palestra|seminario|encontro|formatura|solenidade|treinamento|capacitacao|workshop|"
    r"oficina|jornada|forum|confraternizacao|operacao|roda\s+de\s+conversa|aula|semana\s+d[aeo]|cerimonia|"
    r"conferencia|congresso|simposio|audiencia\s+publica|posse"
)
_R_EVENTO = re.compile(r"\b(?:" + _EVENTOS + r")\b")
_R_ROTULO_EVENTO = re.compile(r"\bevento\s*:\s*")
# Onde o nome do evento acaba: pontuação, data, hora, lugar, verbo.
_R_FIM_EVENTO = re.compile(
    r"\s*[,;.!?(\n]|\s+[-–—]\s+(?=" + _ENDERECO + r")|"
    r"\s+(?:dia|as\s+\d|a\s+realizar|aqui|que|sera|serao|vamos|vou|teremos|faremos|precisa\w*|solicit\w*|"
    r"com\s+(?:coffee|entrega)|eu|agora|hoje|amanha)\b"
)


_R_PREPOSICAO_FORA = re.compile(r"\s+(?:na|no|nos|nas|em)\s+(?=[a-zà-ÿ0-9])")


@dataclass
class Evento:
    nome: str
    trecho: str
    confianca: str = "M"


def evento_do_texto(texto: str) -> Evento | None:
    """O evento para o qual é o coffee: "Evento: X" ou o 1º "Curso/Reunião/Palestra ..." do texto."""
    if not texto:
        return None
    texto = corrido(texto)
    dobrado = dobrar(texto)
    m = _R_ROTULO_EVENTO.search(dobrado)
    inicio = m.end() if m else None
    confianca = "A" if m else "M"
    if inicio is None:
        m = _R_EVENTO.search(dobrado)
        if not m:
            return None
        inicio = m.start()
    # O fim só conta depois da 1ª palavra ("Palestra" "no Trânsito" é nome).
    primeira = re.match(r"[\w'-]+(?:\s+de\s+conversa)?", dobrado[inicio:])
    busca_de = inicio + (primeira.end() if primeira else 0)
    fim_m = _R_FIM_EVENTO.search(dobrado, busca_de)
    fim = fim_m.start() if fim_m else len(texto)
    # "na quinta", "no dia", "em Campo Mourão" fecham; "no Trânsito", "em Crises" são do nome.
    prep = _R_PREPOSICAO_FORA.search(texto, busca_de, fim)
    if prep:
        fim = prep.start()
    fim = min(fim, inicio + 150)
    nome = " ".join(texto[inicio:fim].split()).strip(" -–—:\"'“”")
    nome = nome.replace('"', "").replace("“", "").replace("”", "")
    if len(nome) < 4:
        return None
    nome = nome[:1].upper() + nome[1:]
    comeco = max(texto.rfind("\n", 0, inicio) + 1, inicio - 60)
    return Evento(nome, texto[comeco:fim].strip(), confianca)


# ---------------------------------------------------------------------------
# Local de entrega (o nome do lugar; o endereço tem campos próprios)
# ---------------------------------------------------------------------------

_R_ROTULO_LOCAL = re.compile(
    r"(?<![\w])(?<!no )(?<!do )(?:local\s+de\s+entrega|endereco\s+de\s+entrega|local|entrega)\s*:\s*|"
    r"\bentrega\s+(?:no|na|em)\s+(?=[a-z0-9])"
)
_LUGARES = (
    r"auditorio|sala|salao|sede|delegacia|camara|prefeitura|centro|colegio|escola|ginasio|clube|hotel|"
    r"parque|patio|stand|estande|base|laboratorio|distrito|canil|gabinete|subdivisao|associacao|igreja|"
    r"paroquia|teatro|biblioteca|quartel|batalhao|nucleo|estadio|espaco|plenario|anfiteatro|"
    r"\d{1,2}[ªa]\s*(?:sdp|dp|sdp\b)?"
)
_R_NO_LUGAR = re.compile(r"\b(?:no|na|nos|nas)\s+(?P<valor>(?:" + _LUGARES + r"))\b")
# Linha (ou frase) que começa pelo lugar: "Auditório do Centro de Estudos".
_R_LINHA_LUGAR = re.compile(r"(?m)(?:^|\.\s+)\s*(?P<valor>(?:" + _LUGARES + r"))\b")
_R_FIM_LOCAL = re.compile(
    r"\s*[,;(\n]|\.(?:\s|$)|\s+[-–—|]\s|\s+(?:na|no|em)\s+(?=" + _ENDERECO + r")|\s+(?=" + _ENDERECO + r"\s)|"
    r"\s+(?:e\s+pra|e\s+para|para|pra|as|dia|reuniao)\b"
)


@dataclass
class Local:
    nome: str
    trecho: str
    confianca: str


def _nome_do_local(texto: str, dobrado: str, inicio: int) -> str:
    # Pula o que sobrou do rótulo até o nome (espaços, quebra de linha).
    while inicio < len(texto) and texto[inicio] in " \t\n":
        inicio += 1
    fim_m = _R_FIM_LOCAL.search(dobrado, inicio + 1)
    fim = fim_m.start() if fim_m else len(texto)
    return " ".join(texto[inicio:min(fim, inicio + 150)].split()).strip(" -–—:.")


def local_do_texto(texto: str) -> Local | None:
    """O lugar da entrega: "Local:"/"Entrega:" ou "no Auditório X", sem o endereço."""
    if not texto:
        return None
    texto = corrido(texto)
    dobrado = dobrar(texto)
    m = _R_ROTULO_LOCAL.search(dobrado)
    if m:
        nome = _nome_do_local(texto, dobrado, m.end())
        # "Local: Rua X, 100" é endereço, não nome de lugar.
        if len(nome) >= 3 and not re.match(_ENDERECO + r"\s", dobrar(nome)):
            return Local(nome, texto[m.start():m.end() + len(nome) + 2].strip(), "A")
    candidatos = []
    for regex in (_R_NO_LUGAR, _R_LINHA_LUGAR):
        for m in regex.finditer(dobrado):
            candidatos.append(m.start("valor"))
    for inicio in sorted(candidatos):
        nome = _nome_do_local(texto, dobrado, inicio)
        if len(nome) >= 3:
            comeco = max(texto.rfind("\n", 0, inicio) + 1, inicio - 40)
            return Local(nome, texto[comeco:inicio + len(nome)].strip(), "M")
    return None


# ---------------------------------------------------------------------------
# Quem recebe
# ---------------------------------------------------------------------------

_R_QUEM_RECEBE = re.compile(
    r"\b(?:respons[a]vel(?:\s+(?:pelo|pela|por)\s+(?:recebimento|receber|entrega))?(?:\s+no\s+local)?|"
    r"recebimento|quem\s+(?:vai\s+)?recebe(?:r|ra)?|recebedor[a]?|contato\s+(?:no|do)\s+local|"
    r"recebe(?:r)?(?:\s+com)?(?:\s+no\s+local)?)(?!\w)"
    r"(?:\s*[:–-]|\s+(?:sera|e)\b)?\s*"
)
_TITULOS = (
    r"(?:sr|sra|dr|dra|inv|esc|del|ag|agt|investigador[a]?|escriva|escrivao|agente|delegad[oa]|"
    r"secretari[oa]|instrutor[a]?|coordenador[a]?)"
)
_R_ENTREGAR_PARA = re.compile(
    r"\bentregar\b[^.\n]{0,40}?\b(?:para|pra|p/|ao|a)\s+(?:o\s+|a\s+)?(?=" + _TITULOS + r"\b)"
)
_R_EU_RECEBO = re.compile(r"\beu\s+(?:mesm[oa]\s+)?recebo\b|\bentregar\s+(?:para|pra)\s+mim\b|\bfala\s+(?:cmg|comigo)\b")
_ABREVIADOS = {"sr", "sra", "dr", "dra", "inv", "esc", "del", "ag", "agt", "cel", "prof", "profa", "invest"}


def _ate_o_fim_da_frase(texto: str, inicio: int) -> str:
    fim = len(texto)
    for m in re.finditer(r"[\n;]|\.(?=\s|$)", texto[inicio:]):
        if m.group(0) == ".":
            palavra = re.search(r"(\w+)$", texto[inicio:inicio + m.start()])
            if palavra and dobrar(palavra.group(1)) in _ABREVIADOS:
                continue
        fim = inicio + m.start()
        break
    return texto[inicio:fim]


def _limpar_pessoa(valor: str) -> str:
    valor = " ".join(valor.split()).strip(" ,.;:-–")
    # "com o Investigador X", "a própria escrivã Márcia", "o plantão, inv. Cristiano".
    valor = re.sub(r"^(?:com\s+)?(?:o|a)\s+(?=\S)", "", valor, flags=re.IGNORECASE)
    valor = re.sub(r"^própri[oa]\s+", "", valor, flags=re.IGNORECASE)
    return valor.strip(" ,.;:-–")


@dataclass
class QuemRecebe:
    nome: str
    trecho: str
    eh_quem_pede: bool = False


def quem_recebe_no_texto(texto: str) -> QuemRecebe | None:
    """Quem recebe no local, quando o e-mail diz ("Recebe: X", "entregar para o sr. X").

    "eu recebo"/"entregar para mim" devolve `eh_quem_pede`: é o remetente.
    """
    if not texto:
        return None
    texto = corrido(texto)
    dobrado = dobrar(texto)
    for m in _R_QUEM_RECEBE.finditer(dobrado):
        valor = _limpar_pessoa(_ate_o_fim_da_frase(texto, m.end()))
        if len(valor) >= 3:
            return QuemRecebe(valor[:150], texto[m.start():m.end() + len(valor) + 2].strip())
    m = _R_ENTREGAR_PARA.search(dobrado)
    if m:
        valor = _limpar_pessoa(_ate_o_fim_da_frase(texto, m.end()))
        if len(valor) >= 3:
            return QuemRecebe(valor[:150], texto[m.start():m.end() + len(valor)].strip())
    m = _R_EU_RECEBO.search(dobrado)
    if m:
        return QuemRecebe("", texto[m.start():m.end()], eh_quem_pede=True)
    return None
