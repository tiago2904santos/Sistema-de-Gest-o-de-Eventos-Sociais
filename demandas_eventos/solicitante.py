"""Quem pede a palestra: a instituição (escola, igreja, empresa, conselho…).

Na planilha o "Solicitante" é a instituição, com a pessoa de contato ao
lado ("Maria — Colégio Estadual X"). A assinatura quase nunca diz a
instituição ("Diretora", "Analista de RH"); quem diz é o próprio pedido:
"Sou pedagoga do Colégio X", "A Associação Y solicita", "o pedido do
Rotary Club de Z". A ordem de preferência:

1. no corpo, a instituição que se apresenta ("sou/somos/aqui é da X",
   "diretora Regiane, do Colégio X", "coordeno o Clube X", "pedido do X",
   "Interessado: X", "na sede da X") ou que pede ("A X, de Cidade,
   solicita/convida/gostaria…");
2. a linha de instituição da assinatura ("Vara da Infância…");
3. o nome do remetente, quando é de instituição ("EEB Santo Antônio");
4. a primeira instituição citada no corpo (o timbre do ofício, "para os
   alunos da Escola X").

Quem só encaminha (a delegacia, o gabinete, o eProtocolo) não é o
solicitante: a PCPR e a ASCOM nunca são candidatas.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from core.leitura.datas import dobrar

# Palavras que fazem de um nome próprio uma instituição (pelo começo da palavra).
_CHAVES = (
    "colegio", "escola", "eeb", "cmei", "creche", "apae", "apmf", "cras", "creas", "secretaria",
    "prefeitura", "camara", "conselho", "associacao", "assoc", "instituto", "universidade",
    "faculdade", "centro", "clube", "club", "rotary", "lions", "igreja", "paroquia", "comunidade",
    "congregacao", "grupo", "cooperativa", "industria", "empresa", "sindicato", "federacao",
    "fundacao", "oab", "ordem", "subsecao", "vara", "comarca", "tribunal", "ministerio",
    "defensoria", "promotoria", "uniao", "movimento", "pastoral", "nucleo", "departamento",
    "curso", "sesc", "senai", "sesi", "senac", "hospital", "abrigo", "asilo", "loja", "rede", "congresso",
)
_CHAVES_SET = frozenset(_CHAVES)
# Sozinhas não dizem qual instituição ("DIRECAO ESCOLA", "na escola estadual").
_GENERICAS = frozenset(_CHAVES) | {
    "estadual", "municipal", "federal", "direcao", "coordenacao", "equipe", "comissao", "sede",
    "pedagogica", "escolar", "publica", "de", "da", "do", "das", "dos", "e", "d", "rh",
}
# A PCPR é quem recebe o pedido; delegacias e gabinetes só encaminham.
_R_NAO_E_SOLICITANTE = re.compile(
    r"\b(?:policia\s+civil|pcpr|ascom|assessoria\s+de\s+comunicacao|subdivisao\s+policial|delegacia|"
    r"gabinete|eprotocolo|protocolo\s+geral)\b"
)
_CONECTORES = {"de", "da", "do", "das", "dos", "e", "d'"}
# Onde o nome da instituição acaba: o endereço e os rótulos do pedido.
_PARADAS = {
    "rua", "r", "av", "avenida", "rodovia", "travessa", "alameda", "estrada", "endereco", "local",
    "data", "horario", "publico", "contato", "fone", "tel", "telefone", "cep", "bairro", "dia",
}
# Nas linhas todas minúsculas (ou maiúsculas) o nome vai até a preposição de lugar/assunto.
_PARADAS_PLANAS = _PARADAS | {
    "em", "para", "pra", "pro", "pros", "pras", "sobre", "no", "na", "nos", "nas", "aqui", "as",
    "com", "que", "precisamos", "queremos", "gostaria", "gostariamos", "solicita", "solicito",
    "palestra", "sou", "somos", "dia", "ta", "pq", "porque",
}
_R_ABREVIACAO = re.compile(r"^(?:Dr|Dra|Pe|Sr|Sra|Prof|Profa|Profª|Sto|Sta|Ltda|Ev|Pr|Jd|Vl|Cel|Dep|Ver|Mons|Irm|[A-Z]\.[A-Z])\.$")
_R_MAIUSCULA = re.compile(r"^[A-ZÀ-Ý]")

# Antes do nome: quem se apresenta, o cargo de quem pede, o pedido encaminhado.
_R_APRESENTACAO = re.compile(
    r"\b(?:sou|somos|aqui\s+e|me\s+chamo|coordeno|trabalho|falo|represento|interessad[oa]|pedido|"
    r"sede|diretor|diretora|pedagog[oa]|professor|professora|secretari[oa]|presidente|pastor|lider|"
    r"coordenador|coordenadora|conselheir[oa]|orientador|orientadora|vice-diretor[a]?|responsavel|"
    r"assistente\s+social|tecnic[oa])\b"
)
_R_ENCAMINHAMENTO = re.compile(r"\b(?:pedido|encaminh\w*|interessad[oa])\b")
# Logo antes do nome: "da", "do", "o" (de "coordeno o"), "Interessado:".
_R_LIGACAO = re.compile(r"(?:\b(?:d[aeo]s?|[oa])|:)\s*$")
# Depois do nome: o verbo do pedido, com um aposto opcional (", de Toledo,").
_R_VERBO = re.compile(
    r"^\s*(?P<sigla>\([^)\n]{1,40}\)\s*)?(?:[-–]\s*[^,.\n]{1,30})?(?:,(?P<aposto>[^.;!?]{1,110}),\s*)?(?:gostaria|gostariamos|solicita|solicitam|convida|"
    r"convidam|realiza|realizara|realizarao|promove|promovera|pede|pedem|vem|deseja|desejam|esta|organiza|"
    r"organizara|fara|necessita|precisa|agradece|tem\s+o\s+prazer)\b"
)
_R_ARTIGO_ANTES = re.compile(r"(?:[.:;!?\n,]|\b(?:que|e|mas))\s*[ao]s?\s+$")
# Só a ligação "da/do" põe um nome sem palavra de instituição na conta ("Sou do RH da Autopeças
# Kreutz"); "Sou a Rosângela" é a pessoa.
_R_LIGACAO_DA = re.compile(r"\bd[ao]s?\s*$")
# Palavras que abrem a frase com maiúscula e não fazem parte do nome.
_FUNCAO = frozenset({
    "o", "a", "os", "as", "na", "no", "nas", "nos", "em", "para", "pela", "pelo", "sou", "somos", "aqui",
    "e", "de", "da", "do", "das", "dos", "com", "se", "um", "uma", "ao", "ola", "oi", "bom", "boa", "prezados",
    "prezadas", "prezado", "prezada", "senhores", "ligou", "compareceu", "encaminho", "encaminhamos",
})
_R_FIM_DE_FRASE = re.compile(r"[.!?]\s|\n\s*\n")


@dataclass(frozen=True)
class Instituicao:
    nome: str
    trecho: str
    encaminhado: bool = False
    #: Onde o nome aparece no corpo (-1: fora do corpo).
    inicio: int = -1


def _palavras(texto: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", dobrar(texto))


def _e_chave(palavra: str) -> bool:
    """"escola", "escolas", "igrejas" — mas não "escolar" (de "violência escolar")."""
    palavra = palavra.lower().rstrip(".")
    return palavra in _CHAVES_SET or palavra.rstrip("s") in _CHAVES_SET or palavra[:-2] in _CHAVES_SET and palavra.endswith("es")


def _tem_chave(texto: str) -> bool:
    return any(_e_chave(p) for p in _palavras(texto))


def _diz_qual(texto: str) -> bool:
    """Tem ao menos uma palavra além das genéricas ("Colégio Estadual X", não "Direção Escola")."""
    return any(p not in _GENERICAS and not _e_chave(p) for p in _palavras(texto) if len(p) > 1)


def _limpar(nome: str) -> str:
    nome = " ".join(nome.split()).strip(" ,.;:-–—")
    # Conector solto no fim ("Colégio Estadual de").
    while nome and nome.split()[-1].lower() in _CONECTORES:
        nome = nome.rsplit(" ", 1)[0] if " " in nome else ""
    return nome[:200]


def _linha_plana(linha: str) -> bool:
    letras = [c for c in linha if c.isalpha()]
    return len(letras) >= 8 and (all(c.islower() for c in letras) or all(c.isupper() for c in letras))


def _nomes_no_texto(texto: str):
    """Os nomes próprios do texto (sequências capitalizadas), como (início, fim).

    Numa linha toda minúscula ou maiúscula ("sou da escola estadual pe
    anchieta de ivai") o nome começa na palavra de instituição e vai até a
    preposição de lugar ou assunto.
    """
    corrida: list[list] = []  # [início, fim, palavra] da sequência aberta

    def fechar():
        while corrida and corrida[-1][2].lower() in _CONECTORES:
            corrida.pop()
        if corrida:
            yield corrida[0][0], corrida[-1][1]
        corrida.clear()

    pos = 0
    for linha in texto.split("\n"):
        if _linha_plana(linha):
            yield from fechar()
            yield from ((pos + i, pos + f) for i, f in _nomes_na_linha_plana(linha))
            pos += len(linha) + 1
            continue
        for m in re.finditer(r"\S+", linha):
            bruto = m.group()
            if bruto in ("-", "–", "—", "|", "·", "/", "•"):
                yield from fechar()
                continue
            if bruto[0] in "([\"“'":
                yield from fechar()
            nucleo = bruto.strip("([\"“”')],;:!?")
            inicio = pos + m.start() + bruto.find(nucleo[:1]) if nucleo else pos + m.start()
            # Abreviação ("Dr.", "Pe.", "Ltda.", "S.A.") não fecha o nome; ponto final fecha.
            abreviacao = bool(_R_ABREVIACAO.search(nucleo))
            fim_de_frase = nucleo.endswith(".") and not abreviacao
            if not abreviacao:
                nucleo = nucleo.rstrip(".")
            dobrada = dobrar(nucleo).rstrip(".")
            if nucleo and _R_MAIUSCULA.match(nucleo) and dobrada not in _PARADAS:
                corrida.append([inicio, inicio + len(nucleo), nucleo])
            elif corrida and nucleo.lower() in _CONECTORES and bruto == nucleo:
                corrida.append([inicio, inicio + len(nucleo), nucleo])
            else:
                yield from fechar()
                continue
            if fim_de_frase or bruto[-1] in ",;:!?)]\"”":
                yield from fechar()
        # A quebra de linha no meio da frase não fecha ("Escola Estadual\nMonsenhor Pedro Lech").
        if not linha.strip() or linha.rstrip()[-1] in ".:;!?":
            yield from fechar()
        pos += len(linha) + 1
    yield from fechar()


def _nomes_na_linha_plana(linha: str):
    palavras = list(re.finditer(r"[^\s,;:!?()]+", linha))
    i = 0
    while i < len(palavras):
        if not _e_chave(dobrar(palavras[i].group())):
            i += 1
            continue
        j = i + 1
        while j < len(palavras) and j - i < 9:
            if linha[palavras[j - 1].end():palavras[j].start()].strip():
                break  # vírgula, parêntese
            bruto = palavras[j].group()
            if dobrar(bruto).strip(".").lower() in _PARADAS_PLANAS or bruto[0].isdigit():
                break
            j += 1
        yield palavras[i].start(), palavras[j - 1].end()
        i = j


def _prefixo_minusculo(dobrado: str, inicio: int) -> int:
    """"a cooperativa de crédito Cresol": a palavra de instituição minúscula antes do nome."""
    antes = dobrado[max(0, inicio - 40):inicio]
    # Só com artigo antes ("a cooperativa", "o grupo"): "secretária da APAE" é o cargo.
    m = re.search(r"\b(?:[ao]s?|um|uma|d[ao]s?|n[ao]s?)\s+((?:" + "|".join(_CHAVES) + r")(?:e?s)?\b(?:\s+d[aeo]s?\s+[a-z]+)?\s+)$", antes)
    return inicio - len(antes) + m.start(1) if m else inicio


def instituicoes_do_corpo(corpo: str) -> tuple[list[Instituicao], list[Instituicao]]:
    """(as que se apresentam ou pedem, as outras citadas) — na ordem do texto."""
    dobrado = dobrar(corpo)
    fortes, fracas = [], []
    for inicio, fim in _nomes_no_texto(corpo):
        # "O Colégio X", "Sou do RH da Y": as palavras de abrir a frase ficam de fora.
        while True:
            m = re.match(r"\s*([^\s]+)\s+", corpo[inicio:fim])
            if not m or dobrar(m.group(1)).lower() not in _FUNCAO:
                break
            inicio += m.end()
        inicio = _prefixo_minusculo(dobrado, inicio)
        nome = _limpar(corpo[inicio:fim])
        if not nome or _R_NAO_E_SOLICITANTE.search(dobrar(nome)) or not _diz_qual(nome):
            continue
        # A frase até o nome: onde o texto se apresenta ("Sou pedagoga do …").
        antes = dobrado[max(0, inicio - 90):inicio]
        corte = list(_R_FIM_DE_FRASE.finditer(antes))
        frase = antes[corte[-1].end():] if corte else antes
        chave = _tem_chave(nome)
        ligacao = _R_LIGACAO if chave else _R_LIGACAO_DA
        apresenta = bool(_R_APRESENTACAO.search(frase) and ligacao.search(frase))
        artigo = _R_ARTIGO_ANTES.search(antes if inicio >= 90 else "\n" + antes)
        verbo = _R_VERBO.match(dobrado[fim:fim + 160]) if artigo else None
        pede = verbo is not None
        if verbo:
            # "por meio do CRAS X": a unidade que pede.
            aposto = re.search(r"\bpor\s+meio\s+d[ao]s?\s+(.+)", verbo.group("aposto") or "")
            if aposto:
                comeco = fim + verbo.start("aposto") + aposto.start(1)
                nome = _limpar(corpo[comeco:fim + verbo.end("aposto")]) + " / " + nome
        # "(UniNoroeste)", "(CONDIRE 2026)": a sigla logo depois vem junto.
        sigla = re.match(r"\s*\(([^)\n]{2,40})\)", corpo[fim:])
        if sigla and re.fullmatch(r"\s*[A-ZÀ-Ý][\wÀ-ÿ-]*[A-Z][\wÀ-ÿ-]*(?:\s+\d{4})?\s*", sigla.group(1)):
            nome += f" ({sigla.group(1).strip()})"
        trecho = " ".join(corpo[max(0, inicio - 60):fim + 60].split())
        if apresenta or pede:
            fortes.append(Instituicao(nome, trecho, bool(_R_ENCAMINHAMENTO.search(frase)), inicio))
        elif chave:
            fracas.append(Instituicao(nome, trecho, inicio=inicio))
    return fortes, fracas


def instituicao_na_linha(linha: str) -> str:
    linha = " ".join(linha.split()).strip(" -–—|•*_")
    dobrada = dobrar(linha)
    if (not linha or len(linha) > 120 or "@" in linha or re.search(r"\d{4}[-.\s]?\d{4}|^\s*(?:rua|av)", dobrada)
            or _R_NAO_E_SOLICITANTE.search(dobrada)):
        return ""
    if not (_tem_chave(linha) and _diz_qual(linha)):
        return ""
    return _limpar(linha)


def instituicao_da_assinatura(assinatura: str) -> str:
    for linha in (assinatura or "").split("\n"):
        # "Endereço da Secretaria: Rua …" é endereço, não instituição.
        if ":" in linha:
            continue
        nome = instituicao_na_linha(linha)
        if nome:
            return nome
    return ""


def sigla_do_remetente(remetente: str, nome: str) -> str:
    """A sigla que o remetente usa e o nome escrito por extenso não mostra ("OAB")."""
    iniciais = "".join(p[0] for p in re.findall(r"[A-ZÀ-Ý][\wÀ-ÿ]*", nome)).upper()
    for sigla in re.findall(r"\b[A-Z]{3,6}\b", remetente or ""):
        if sigla in ("SESMT", "CIPA", "SIPAT") or sigla in dobrar(nome).upper() or dobrar(sigla).upper() in dobrar(iniciais).upper():
            continue
        return sigla
    return ""


def sem_nomes_de_instituicao(texto: str) -> str:
    """O texto com os nomes de instituição apagados (trocados por espaços, as posições ficam).

    "Secretaria Municipal de Segurança e Trânsito" não é pedido de palestra
    sobre trânsito, nem "Conselho da Mulher" de segurança da mulher.
    """
    texto = texto or ""
    partes = list(texto)
    for inicio, fim in _nomes_no_texto(texto):
        if _tem_chave(texto[inicio:fim]):
            partes[inicio:fim] = [c if c == "\n" else " " for c in texto[inicio:fim]]
    return "".join(partes)
