"""Leituras do e-mail próprias do evento social: local, quem pede, CIN.

`core.preencher_por_email` lê o que serve a todas as telas; aqui ficam as
regras que o pedido de evento social pede a mais:

- o local é o NOME do lugar ("Ginásio Municipal X"): o endereço tem campos
  próprios. O texto do e-mail vem quebrado a cada ~72 colunas, então as
  linhas de um parágrafo são juntadas antes de ler;
- quem pede é quem assina, mesmo quando a "assinatura" ficou no corpo
  (WhatsApp, "Fulano, secretário, 41 9999-0000"), sem o tratamento (Prof.,
  Dr., Frei, Cap. PM) e preferindo a autoridade ao assessor;
- a quantidade de CIN é a de carteiras/pessoas a documentar, nunca o
  público do evento, e "300 por dia" em 2 dias são 600.

Tudo puro: recebe texto, devolve `Achado` (ou None).
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from core.leitura.casamento import Achado, telefone_no_texto
from core.leitura.datas import dobrar

# ---------------------------------------------------------------------------
# Texto
# ---------------------------------------------------------------------------

# "Local: ", "Serviços: ", "Silvana Céu Azul: " — linha que começa um item novo.
_R_LINHA_ROTULADA = re.compile(r"^\s*[^\s:][^:\n]{0,39}:\s")
_R_FIM_DE_FRASE = re.compile(r"[.!?:;]\s*$")
_R_TERMINA_EM_LIGACAO = re.compile(r"\b(?:de|do|da|dos|das|no|na|nos|nas|em|e|a|o|ao|com|para|pelo|pela)\s*$")


def desquebrar(texto: str) -> str:
    """Junta as linhas de um parágrafo que o programa de e-mail quebrou.

    Só junta linha longa (quebra automática) sem pontuação no fim e seguida
    de texto que não começa um item novo ("Local: ..."). Mensagens curtas do
    WhatsApp e listas ficam como estão.
    """
    linhas = (texto or "").split("\n")
    partes = []
    for i, linha in enumerate(linhas):
        partes.append(linha.rstrip())
        if i == len(linhas) - 1:
            break
        seguinte = linhas[i + 1]
        # Linha que acaba em "do", "na", "e" continua na de baixo, mesmo que ela
        # pareça rótulo ("na sede do\nSindicato: Rua X").
        pela_metade = bool(_R_TERMINA_EM_LIGACAO.search(dobrar(linha)))
        juntar = (
            len(linha.strip()) >= 55
            and seguinte.strip()
            and not _R_FIM_DE_FRASE.search(linha)
            and (pela_metade or not _R_LINHA_ROTULADA.match(seguinte))
        )
        partes.append(" " if juntar else "\n")
    return "".join(partes)


def _frases(texto: str) -> list[tuple[int, int]]:
    """(início, fim) de cada frase: ponto final, "?", "!", ";" ou quebra de linha."""
    limites, inicio = [], 0
    for m in re.finditer(r"[.!?;]\s|\n", texto):
        antes = texto[max(0, m.start() - 5):m.start()].lower()
        if m.group(0)[0] == "." and re.search(r"(?:^|\W)(?:" + _ABREVIACOES + r")$", antes):
            continue  # "Cel. José", "Av. Brasil": abreviação, não fim de frase
        limites.append((inicio, m.start()))
        inicio = m.end()
    limites.append((inicio, len(texto)))
    return [(a, b) for a, b in limites if texto[a:b].strip()]


def _frase_de(texto: str, posicao: int) -> tuple[int, int]:
    for inicio, fim in _frases(texto):
        if inicio <= posicao <= fim:
            return inicio, fim
    return max(0, posicao - 100), min(len(texto), posicao + 100)


def _caixa(texto: str) -> str:
    """"mista" (texto normal), ou "sem" (tudo minúsculo ou tudo maiúsculo): aí a
    maiúscula não diz onde acaba um nome próprio."""
    letras = [c for c in texto if c.isalpha()]
    if not letras:
        return "sem"
    maiusculas = sum(1 for c in letras if c.isupper())
    palavras = re.findall(r"\b[^\W\d_]{3,}", texto)
    capitalizadas = sum(1 for p in palavras if p[0].isupper())
    if maiusculas / len(letras) > 0.8 or (palavras and capitalizadas / len(palavras) < 0.04):
        return "sem"
    return "mista"


def _nome_proprio(valor: str) -> str:
    """"SEBASTIAO DOS SANTOS"/"vanderlei grochoski" -> "Sebastiao dos Santos"."""
    if valor.isupper() or valor.islower():
        palavras = valor.lower().split()
        return " ".join(p if p in _CONECTORES_NOME else p[:1].upper() + p[1:] for p in palavras)
    return valor


# ---------------------------------------------------------------------------
# Local do evento (o nome do lugar)
# ---------------------------------------------------------------------------

_LUGARES = (
    "colegio", "escola", "ginasio", "praca", "centro", "salao", "igreja", "camara", "auditorio", "teatro",
    "parque", "associacao", "clube", "sede", "paroquia", "cras", "creas", "estadio", "espaco", "casa",
    "barracao", "pavilhao", "sala", "quadra", "biblioteca", "universidade", "faculdade", "instituto",
    "hospital", "delegacia", "batalhao", "shopping", "hotel", "restaurante", "cmei", "ubs", "terminal",
    "rodoviaria", "forum", "tribunal", "assembleia", "anfiteatro", "galpao", "complexo", "conjunto",
    "capela", "aldeia", "assentamento", "cooperativa", "sindicato", "patio", "apae", "posto", "unidade",
    "marco", "arena", "cemiterio", "museu", "calcadao", "rua da cidadania", "estacao",
)
# Sigla que sozinha já é o nome do lugar ("no CRAS mesmo").
_SIGLAS_DE_LUGAR = {"cras", "creas", "apae", "cmei", "ubs", "sesc", "sesi", "senai", "senac", "cejusc"}
# Onde o lugar costuma ser a própria instituição que pede ("A Escola X solicita").
_LUGARES_INSTITUICAO = {"colegio", "escola", "apae", "cras", "creas", "cmei", "ubs", "igreja", "paroquia",
                        "clube", "sindicato", "associacao", "hospital", "capela", "universidade", "faculdade"}
_R_LUGAR = re.compile(r"\b(?:" + "|".join(sorted(_LUGARES, key=len, reverse=True)) + r")\b")
_R_PREPOSICAO = re.compile(r"\b(?:no|na|nos|nas|em|ao|a|pelo|pela|a\s+partir\s+d[oa])\s+(?P<proprio>propri[oa]\s+)?$")
_R_CORRECAO = re.compile(r"\b(?:mudou|mudamos|mudar|passou|passa|transferid[oa]|alterad[oa]|trocad[oa])\s+(?:para|pra)\s+(?:o|a|os|as)?\s*$")
_R_ROTULO_LOCAL = re.compile(r"(?m)^[ \t*•-]*(?:local(?:\s+do\s+evento|\s+da\s+acao)?|onde)\s*[:–-]\s*")
_R_NA_RUA = re.compile(r"\b(?:no|na|pela|pelo)\s+(?P<valor>(?:av\.|avenida|rua|r\.|rodovia|estrada|travessa|alameda)\s)")
_R_ENDERECO_INICIO = re.compile(r"^(?:rua|r\.|av\.?|avenida|rodovia|estrada|travessa|alameda|rod\.)\s")
_ABREVIACOES = r"cel|dr|dra|pe|prof|profa|sto|sta|gen|gal|mal|cap|ten|maj|des|dep|sen|gov|pres|eng|av|r|n|s|jd|vl|pq|ver|sr|sra"
_R_CORTE = re.compile(r"[,;:()!?\n\"“”]|\s[-–—]\s|/(?!\w)|\.(?:\s|$)")
_CONECTORES_LUGAR = {"de", "da", "do", "das", "dos", "e", "ao", "a", "del"}
_ADJETIVOS_LUGAR = {
    "municipal", "estadual", "federal", "paroquial", "comunitario", "comunitaria", "rural", "central",
    "cultural", "ecologico", "esportivo", "esportiva", "social", "publico", "publica", "evangelica",
    "catolica", "multiuso", "poliesportivo", "de", "da", "do", "das", "dos",
}
_PARAR = {
    "aqui", "em", "que", "pra", "para", "com", "onde", "as", "no", "na", "nos", "nas", "ate", "desde", "pelo",
    "pela", "por", "entre", "junto", "sera", "vai", "localizado", "localizada", "mesmo", "mesma", "rua", "av",
    "avenida", "rodovia", "estrada", "travessa", "alameda", "bairro", "n", "nº", "precisa",
}


def _nome_do_lugar(texto: str, dobrado: str, inicio: int, caixa: str) -> tuple[str, int]:
    """O nome do lugar que começa em `inicio` e onde ele acaba ("", 0 se não for nome)."""
    corte = _R_CORTE.search(dobrado, inicio)
    while corte and corte.group(0).startswith(".") and re.search(
        r"(?:^|\W)(?:" + _ABREVIACOES + r")$", dobrado[max(inicio, corte.start() - 5):corte.start()]
    ):
        corte = _R_CORTE.search(dobrado, corte.end())
    fim_maximo = min(corte.start() if corte else len(texto), inicio + 150)
    tokens = [(m.group(0), m.start(), m.end()) for m in re.finditer(r"\S+", texto[inicio:fim_maximo])]
    aceitos: list[tuple[str, int]] = []
    pendentes: list[tuple[str, int]] = []
    # "na associação de moradores da vila", "no pátio da igreja": lugar escrito
    # em minúsculas segue sem depender de maiúscula (até umas poucas palavras).
    livre = caixa == "sem" or texto[inicio:inicio + 1].islower()
    for n, (palavra, _, fim) in enumerate(tokens):
        chave = dobrar(palavra).strip(".")
        if n == 0:
            aceitos.append((palavra, fim))
            continue
        if chave in _PARAR and not (chave in ("no", "na") and caixa == "mista" and palavra[:1].isupper()):
            break
        if livre and caixa == "mista" and palavra[:1].isupper():
            livre = False  # "salão da Igreja Nossa Senhora": daqui em diante vale a maiúscula
        if livre:
            if len(aceitos) + len(pendentes) >= 9:
                break
            if chave in _CONECTORES_LUGAR:
                pendentes.append((palavra, fim))
            else:
                aceitos.extend(pendentes + [(palavra, fim)])
                pendentes = []
            continue
        maiuscula = palavra[:1].isupper() or palavra[:1].isdigit() or re.fullmatch(r"[IVX]+", palavra)
        if maiuscula:
            aceitos.extend(pendentes + [(palavra, fim)])
            pendentes = []
        elif chave in _CONECTORES_LUGAR:
            pendentes.append((palavra, fim))
        elif chave in _ADJETIVOS_LUGAR and not pendentes and len(aceitos) == 1:
            aceitos.append((palavra, fim))
        elif pendentes and _R_LUGAR.fullmatch(chave):
            # "pátio da igreja": um lugar dentro do outro, mesmo em minúsculas.
            aceitos.extend(pendentes + [(palavra, fim)])
            pendentes = []
        else:
            break
    if not aceitos:
        return "", 0
    fim = inicio + aceitos[-1][1]
    valor = " ".join(p for p, _ in aceitos).strip(" .,-")
    return valor, fim


def _lugar_valido(valor: str) -> bool:
    palavras = valor.split()
    if len(palavras) >= 2:
        return not re.match(r"(?:unidade\s+movel|conjunto\s+com|centro\s+(?:de\s+)?(?:do|da)?\s*cidade)", dobrar(valor))
    return len(palavras) == 1 and dobrar(valor) in _SIGLAS_DE_LUGAR and valor.isupper()


@dataclass(frozen=True)
class _Candidato:
    valor: str
    inicio: int
    prioridade: int  # rótulo "Local:" 3, correção ("mudou para") 4, preposição 1
    qualidade: int  # 2 com nome próprio, 1 descrição em minúsculas
    confianca: str


def _qualidade(valor: str, caixa: str) -> int:
    if caixa == "sem":
        return 1
    return 2 if any(p[:1].isupper() for p in valor.split()) else 1


def _instituicao_citada(texto: str, dobrado: str, lugar: str, caixa: str) -> str:
    """"no próprio CRAS": o CRAS com nome citado antes ("do CRAS Jardim São Jorge")."""
    for m in re.finditer(r"\b" + re.escape(lugar) + r"\b", dobrado):
        valor, _ = _nome_do_lugar(texto, dobrado, m.start(), caixa)
        if len(valor.split()) >= 2 and _qualidade(valor, caixa) == 2:
            return valor
    return ""


def local_do_evento(corpo: str, *, remetente: str = "") -> Achado | None:
    """O nome do lugar do evento, sem o endereço.

    Com "Local:" é "A"; "no Ginásio X" é "M"; o lugar que é a própria
    instituição que pede ("A Escola X solicita a vinda da equipe") é só "B".
    Havendo vários, vale o corrigido ("o local mudou para a Praça Y"), depois
    o rotulado, depois o de nome próprio ("na igreja do bairro" perde para
    "no Centro da Juventude"), depois o primeiro.
    """
    texto = desquebrar(corpo or "")
    dobrado = dobrar(texto)
    caixa = _caixa(texto)
    candidatos: list[_Candidato] = []

    for m in _R_ROTULO_LOCAL.finditer(dobrado):
        if _R_ENDERECO_INICIO.match(dobrado[m.end():]):
            continue  # "Local: Rua X, 100" é endereço, não nome
        valor, _ = _nome_do_lugar(texto, dobrado, m.end(), "sem")
        if valor:
            candidatos.append(_Candidato(valor, m.start(), 3, 2, "A"))

    for m in _R_LUGAR.finditer(dobrado):
        if m.group(0) == "marco" and (texto[m.start()].islower() or re.match(r"marco\s+de\s+\d", dobrado[m.start():])):
            continue  # "em março de 2027": o mês, não o Marco das Três Fronteiras
        antes = dobrado[max(0, m.start() - 40):m.start()]
        correcao = _R_CORRECAO.search(antes)
        preposicao = _R_PREPOSICAO.search(antes)
        if not (correcao or preposicao):
            continue
        if preposicao and preposicao.group("proprio"):
            valor = _instituicao_citada(texto, dobrado, m.group(0), caixa)
            if not valor and remetente and _R_LUGAR.search(dobrar(remetente)):
                valor = remetente
            if not valor:
                valor = _primeira_instituicao(texto, dobrado, caixa)
            if valor:
                candidatos.append(_Candidato(valor, m.start(), 1, 2, "M"))
            continue
        valor, _ = _nome_do_lugar(texto, dobrado, m.start(), caixa)
        if not _lugar_valido(valor):
            continue
        # "a" só vale como "à" (craseado) ou depois de verbo de ir: "convida a Praça" não é lugar.
        if not correcao and preposicao.group(0).strip() == "a" and texto[m.start() - 2:m.start() - 1] != "à":
            if not re.search(r"\b(?:ir|vir|levar|visita\w*|ida|vinda)\s+a\s+$", antes):
                continue
        candidatos.append(_Candidato(valor, m.start(), 4 if correcao else 1, _qualidade(valor, caixa), "M"))

    if not candidatos:
        # Desfile na avenida: sem outro lugar, a rua sem número é o local ("na Av. Presidente Bernardes").
        for m in _R_NA_RUA.finditer(dobrado):
            valor, fim = _nome_do_lugar(texto, dobrado, m.start("valor"), "mista")
            if len(valor.split()) >= 2 and not re.match(r"\s*,?\s*(?:n[o.º]*\s*)?\d", dobrado[fim:fim + 8]):
                trecho = texto[slice(*_frase_de(texto, m.start()))].strip()[:300]
                return Achado(valor, valor, trecho, "M")
        valor = _primeira_instituicao(texto, dobrado, caixa, so_sujeito=True)
        if valor:
            inicio = dobrado.find(dobrar(valor))
            return Achado(valor, valor, texto[slice(*_frase_de(texto, max(inicio, 0)))].strip()[:300], "B")
        return None
    melhor = max(candidatos, key=lambda c: (c.prioridade, c.qualidade, -c.inicio))
    trecho = texto[slice(*_frase_de(texto, melhor.inicio))].strip()[:300]
    return Achado(melhor.valor[:255], melhor.valor[:255], trecho, melhor.confianca)


def _primeira_instituicao(texto: str, dobrado: str, caixa: str, *, so_sujeito: bool = False) -> str:
    """A instituição com nome citada no texto ("A APAE de Cambé tem 45 alunos...").

    `so_sujeito`: só a que abre a frase e pede ("A Escola X ... solicita"),
    quando o e-mail não diz outro lugar: a equipe vai até quem pede.
    """
    for inicio, fim in _frases(texto):
        frase = dobrado[inicio:fim]
        m = re.match(r"\s*(?:a|o)\s+(" + "|".join(sorted(_LUGARES_INSTITUICAO, key=len, reverse=True)) + r")\b", frase)
        if not m:
            if so_sujeito:
                continue
            m = re.search(r"\b(" + "|".join(sorted(_LUGARES_INSTITUICAO, key=len, reverse=True)) + r")\b", frase)
            if not m:
                continue
        if so_sujeito and not re.search(r"\b(?:solicit|ped[ei]|gostari|convid|precis)", frase):
            continue
        valor, _ = _nome_do_lugar(texto, dobrado, inicio + m.start(1), caixa)
        if len(valor.split()) >= 2 and _qualidade(valor, caixa) == 2:
            return valor
    return ""


# ---------------------------------------------------------------------------
# Quem pede
# ---------------------------------------------------------------------------

_CONECTORES_NOME = {"de", "da", "do", "das", "dos", "e", "di", "del", "van", "von"}
# Tratamento antes do nome: sai do nome; o que também é cargo vira cargo na falta de outro.
_R_TRATAMENTO = re.compile(
    r"^(?:(?P<cargo>investigador[a]?|escrivao|escriva|delegad[oa]|diretor[a]?|pastor[a]?|padre|"
    r"enfermeir[oa]|vereador[a]?|prefeit[oa]|paroco)\b\.?|"
    r"(?:prof[aª]?|professor[a]?|dr[a]?|doutor[a]?|sr[a]?|srta|dona|pr[a]?|pe|frei|ir|irma|irmao|enf|cel|coronel|"
    r"cap|capitao|ten|tenente|sgt|sargento|maj|major|pm|rr|companheir[oa]|sub|cb|sd)\b\.?)\s+"
)
_CARGOS = (
    r"diretor|diretora|coordenador|coordenadora|secretari[oa]|prefeit[oa]|assessor|assessora|chefe|"
    r"delegad[oa]|investigador|investigadora|escriva|escrivao|professor|professora|pedagog[oa]|presidente|"
    r"vice-presidente|vice|gerente|analista|tecnic[oa]|agente|supervisor|supervisora|orientador|orientadora|"
    r"vereador|vereadora|comandante|assistente|auxiliar|servidor|servidora|policial|papiloscopista|"
    r"perit[oa]|psicolog[oa]|responsavel|organizador|organizadora|pastor|padre|paroco|vigario|lider|"
    r"conselheir[oa]|voluntari[oa]|extensionista|administrador|administradora|enfermeir[oa]|tesoureir[oa]|"
    r"membro|integrante|representante|superintendente|articulador[a]?|educador[a]?|mobilizador[a]?"
)
_R_CARGO_NO_INICIO = re.compile(r"^(?:" + _CARGOS + r")\b")
_R_CARGO = re.compile(r"\b(?:" + _CARGOS + r")\b")
_NAO_NOME = {
    "prefeitura", "secretaria", "colegio", "escola", "departamento", "policia", "delegacia", "municipio",
    "governo", "camara", "associacao", "instituto", "universidade", "faculdade", "nucleo", "coordenacao",
    "diretoria", "divisao", "setor", "gabinete", "assessoria", "ministerio", "tribunal", "fundacao",
    "conselho", "centro", "batalhao", "comando", "companhia", "sindicato", "igreja", "paroquia", "cras",
    "creas", "ong", "ltda", "cerimonial", "equipe", "comissao", "pastoral", "clube", "club", "grupo",
    "bom", "boa", "dia", "tarde", "noite", "prezados", "prezadas", "prezado", "prezada", "senhor", "senhores",
    "obrigado", "obrigada", "atenciosamente", "cordialmente", "abracos", "att", "valeu", "civil", "social",
    "municipal", "estadual", "pcpr", "parana", "acao", "evento", "servicos", "local", "data", "horario",
    "rg", "cin", "carteira", "identidade", "pessoal", "vcs", "voces", "nos", "gente", "pedido", "solicitacao",
    "assistencia", "saude", "educacao", "emater", "rotary", "lions", "moto", "encontro",
}
_R_CONTATO = re.compile(
    r"@|https?://|www\.|\b(?:tel|fone|telefone|celular|cel|whats?app|ramal|e-?mail|fax)\b|\d{4}[-.\s]?\d{4}"
)
_R_ENDERECO = re.compile(r"^\s*(?:rua|r\.|av\.?|avenida|travessa|rodovia|alameda|praca|estrada)\s|\b\d{5}-?\d{3}\b|\d.*/[a-z]{2}\b")
_R_DESPEDIDA = re.compile(
    r"^\s*(?:att|atte|atenciosamente|cordialmente|respeitosamente|obrigad[oa]s?|abs|abracos?|grat[oa]|"
    r"com\s+carinho|valeu|um\s+abraco|sds|saudacoes|enviado\s+do\s+meu|sent\s+from)\b"
)
# "Enviado em nome do Prefeito por:" — daqui em diante é o assessor que mandou.
_R_EM_NOME_DE = re.compile(r"\b(?:em\s+nome\s+d[oa]|por\s+ordem\s+d[oa]|enviado\s+por|p/)\b")
_R_TELEFONE_SOLTO = re.compile(
    r"(?:\b(?:tel|fone|telefone|celular|cel|whats?app|contato)\b\.?\s*:?\s*)?"
    r"(?:\+\s?55\s?)?\(?\s*0?\d{2}\s*\)?\s*[-.]?\s*9?\s?\d{4}\s*[-.\s]?\s*\d{4}(?:\s*(?:ramal|r\.)\s*\d{1,5})?",
    re.IGNORECASE,
)
_R_ROTULO_PESSOA = re.compile(
    r"(?im)^[ \t*•-]*(?:respons[aá]vel(?:\s+pelo\s+(?:evento|pedido))?|solicitante|contato|requerente|"
    r"coordena[cç][aã]o|organiza[cç][aã]o)\s*:\s*(?P<valor>[^\n]+)$"
)
# "Sou voluntária do Natal Solidário", "sou servidor da Assistência Social".
_R_SOU_CARGO = re.compile(r"\bsou\s+(?:(?:o|a|um|uma)\s+)?(?P<cargo>(?:" + _CARGOS + r")\b[^\n.;!?,]{0,80})")
_R_APRESENTACAO = re.compile(
    r"\b(?:meu\s+nome\s+e|me\s+chamo|sou\s+(?:o|a)|aqui\s+e\s+(?:o|a))\s+(?P<resto>[^\n.;!?]{2,120})"
)


@dataclass(frozen=True)
class Solicitante:
    nome: str
    cargo: str
    telefone: Achado | None
    trecho: str


def _sem_tratamento(parte: str) -> tuple[str, str]:
    """("Prof. Marcelo Vendrame" -> "Marcelo Vendrame", ""), ("Diretora Kelly Anjos" -> (..., "Diretora"))."""
    cargo = ""
    for _ in range(4):
        m = _R_TRATAMENTO.match(dobrar(parte))
        if not m or len(parte[m.end():].split()) < 2:
            break
        if m.group("cargo") and not cargo:
            cargo = parte[:m.end()].strip(" .")
        parte = parte[m.end():]
    return parte.strip(), cargo


def _e_nome(valor: str, *, minusculas: bool = False) -> bool:
    palavras = valor.split()
    if not 2 <= len(palavras) <= 7 or any(c.isdigit() for c in valor) or "@" in valor:
        return False
    chaves = [dobrar(p).strip(".'") for p in palavras]
    if chaves[0] in _CONECTORES_NOME or chaves[-1] in _CONECTORES_NOME:
        return False
    if any(c in _NAO_NOME or _R_CARGO.fullmatch(c) for c in chaves):
        return False
    tudo_maiusculo = valor.isupper()
    for palavra, chave in zip(palavras, chaves):
        if chave in _CONECTORES_NOME:
            continue
        if not re.fullmatch(r"[^\W\d_][\w'.-]*", palavra):
            return False
        if tudo_maiusculo:
            continue
        if palavra.isupper() and len(palavra) > 1:
            return False  # "Ana Paula SEMAS": sigla no meio não é nome de gente
        if not palavra[0].isupper() and not (minusculas and valor.islower()):
            return False
    return True


def _sem_telefone(linha: str) -> str:
    return " ".join(_R_TELEFONE_SOLTO.sub(" ", linha).split()).strip(" ,.;-–—|")


def _ler_linha(linha: str, *, minusculas: bool = False) -> tuple[str, list[str], str] | None:
    """(nome, o resto da linha em partes, cargo do tratamento) de "Nome, cargo, telefone"."""
    linha = " ".join(linha.split()).strip(" -–—|•*_")
    for tentativa in (linha, re.sub(r"^[^:]{2,40}:\s*", "", linha)):
        tentativa = re.sub(r"\s*[\"“][^\"”]{1,25}[\"”]\s*", " ", _sem_telefone(tentativa)).strip()
        if not tentativa:
            continue
        tentativa, cargo_tratamento = _sem_tratamento(tentativa)
        partes = [p.strip(" .,-–—") for p in re.split(r"\s+[-–—|]\s+|,\s*|\.\s+|;\s*", tentativa)]
        partes = [p for p in partes if p]
        if not partes:
            continue
        nome = partes[0]
        if not _e_nome(nome, minusculas=minusculas):
            # "JOSE ROBERTO PANIAGO PRESIDENTE": o cargo colado no nome.
            m = _R_CARGO.search(dobrar(nome))
            if not m or not _e_nome(nome[:m.start()].strip(), minusculas=minusculas):
                continue
            partes[:1] = [nome[:m.start()].strip(), nome[m.start():].strip()]
            nome = partes[0]
        return _nome_proprio(nome), partes[1:], cargo_tratamento
    return None


def _linha_de_cargo(linha: str) -> bool:
    return bool(_R_CARGO_NO_INICIO.match(dobrar(linha.strip())))


def _linha_de_contato(linha: str) -> bool:
    dobrada = dobrar(linha)
    return bool(_R_CONTATO.search(dobrada) or _R_ENDERECO.search(dobrada))


def _ler_bloco(linhas: list[str], *, minusculas: bool = False, olhar_acima: bool = False) -> Solicitante | None:
    """Quem assina um bloco de linhas (assinatura, fim do corpo, "Responsável: ...")."""
    linhas = [" ".join(l.split()) for l in linhas]
    linhas = [l for l in linhas if l and not _R_DESPEDIDA.match(dobrar(l)) and not l.endswith(",")]
    for i, linha in enumerate(linhas):
        if _R_EM_NOME_DE.search(dobrar(linha)) and i > 0:
            break  # o que vem depois é quem mandou em nome de outro: fica o de cima
        seguinte = linhas[i + 1] if i + 1 < len(linhas) else ""
        # Nome em minúsculas só com a estrutura de assinatura (cargo ou telefone embaixo).
        aceita_minusculas = minusculas and bool(seguinte) and (_linha_de_cargo(seguinte) or _linha_de_contato(seguinte))
        lido = _ler_linha(linha, minusculas=aceita_minusculas)
        if lido is None:
            continue
        nome, resto, cargo_tratamento = lido
        extras = list(resto)
        bloco = [linha]
        for outra in linhas[i + 1:i + 4]:
            if _R_EM_NOME_DE.search(dobrar(outra)) or _ler_linha(outra) is not None and not _linha_de_cargo(outra):
                break
            bloco.append(outra)
            if len(extras) < 2 and not _linha_de_contato(outra):
                extras.append(outra.strip(" -–—|"))
        if not extras and olhar_acima:
            # Assinatura com o cargo em cima do nome ("Secretaria Executiva\nFulana").
            extras = [l for l in linhas[max(0, i - 2):i] if not _linha_de_contato(l)][-1:]
        if cargo_tratamento and not (extras and _linha_de_cargo(extras[0])):
            extras.insert(0, cargo_tratamento)
        extras = [e for e in extras if not re.fullmatch(r"[A-Z]{2,5}", e)]  # "OFM", ordem religiosa
        cargo = " / ".join(dict.fromkeys(extras))[:255]
        telefone = telefone_no_texto("\n".join(bloco))
        return Solicitante(nome[:150], cargo, telefone, " · ".join(bloco)[:300])
    return None


def _paragrafos(texto: str) -> list[list[str]]:
    blocos = [b for b in re.split(r"\n\s*\n", texto or "") if b.strip()]
    return [[l for l in b.split("\n") if l.strip()] for b in blocos]


def _apresentacao(corpo: str) -> tuple[str, str]:
    """(nome, cargo) de "Sou a Neide Vasconcelos do CRAS X", "meu nome é padre Fulano"."""
    texto = desquebrar(corpo)
    dobrado = dobrar(texto)
    nome, cargo = "", ""
    for m in _R_APRESENTACAO.finditer(dobrado):
        resto = texto[m.start("resto"):m.end("resto")]
        partes = re.split(r",\s*|\s+(?=d[aeo]s?\s)", resto, maxsplit=1)
        candidato, _ = _sem_tratamento(partes[0].strip())
        # O nome vai até a primeira palavra minúscula que não seja conector.
        palavras = []
        for palavra in candidato.split():
            if palavra[:1].isupper() or dobrar(palavra) in _CONECTORES_NOME and palavras:
                palavras.append(palavra)
            else:
                break
        while palavras and dobrar(palavras[-1]) in _CONECTORES_NOME:
            palavras.pop()
        if not nome and _e_nome(" ".join(palavras)):
            nome = " ".join(palavras)
        depois = re.search(r"\b(?:d[aeo]s?)\s+(?P<org>[^\n.;!?,]{3,80})", resto)
        if not cargo:
            primeira = dobrar(resto.split()[0]) if resto.split() else ""
            if _R_CARGO.fullmatch(primeira):
                cargo = re.split(r"\s+e\s+|,", resto)[0].strip()  # "Sou voluntária do Natal Solidário..."
            elif depois:
                cargo = depois.group("org").strip()
    m = _R_SOU_CARGO.search(dobrado)
    if m:
        cargo = texto[m.start("cargo"):m.end("cargo")].strip()
    return nome, cargo


def solicitante_do_pedido(mensagem) -> Solicitante | None:
    """Quem pede, pela ordem: "Responsável: ..." no corpo, a assinatura, a
    assinatura que ficou no fim do corpo, "sou a Fulana do CRAS". O cargo
    que faltar sai da apresentação ("Sou voluntária do ...")."""
    corpo = mensagem.corpo or ""
    achado: Solicitante | None = None
    for m in _R_ROTULO_PESSOA.finditer(corpo):
        seguintes = corpo[m.end():].split("\n\n", 1)[0].split("\n")
        achado = _ler_bloco([m.group("valor")] + seguintes[1:4])
        if achado:
            break
    if achado is None and (mensagem.assinatura or "").strip():
        achado = _ler_bloco(mensagem.assinatura.split("\n"), olhar_acima=True)
    if achado is None:
        paragrafos = _paragrafos(corpo)
        if paragrafos:
            ultimo = paragrafos[-1]
            achado = _ler_bloco(ultimo if len(ultimo) <= 5 else ultimo[-2:], minusculas=True)
    nome_apresentado, cargo_apresentado = _apresentacao(corpo)
    if achado is None and nome_apresentado:
        achado = Solicitante(nome_apresentado, "", None, "")
    if achado is not None and not achado.cargo and cargo_apresentado:
        achado = Solicitante(achado.nome, cargo_apresentado[:255], achado.telefone, achado.trecho)
    return achado


def sem_tratamento(nome: str) -> str:
    """O nome sem "Dr.", "Prof.", "Frei" na frente (para o nome que vem de outro leitor)."""
    return _sem_tratamento(nome)[0] if nome else nome


# ---------------------------------------------------------------------------
# Serviços: o que não é pedido à PCPR
# ---------------------------------------------------------------------------

# "Não precisamos de emissão de RG", "não haverá emissão", "não é necessário trazer a unidade móvel".
_R_NEGACAO = re.compile(
    r"\b(?:nao\s+(?:\w+\s+){0,2}?(?:havera|ha|precis\w*|necessari\w*|necessidade|queremos|quer\w*|pedimos|"
    r"solicit\w*|sera|vai|vamos)|sem\s+(?:necessidade|precisar)|dispensa\w*)\b"
)
# "A orientação jurídica ficará por conta da Defensoria": serviço de outro órgão.
_R_POR_CONTA_DE_OUTRO = re.compile(r"\b(?:por\s+conta\s+d[aeo]s?|a\s+cargo\s+d[aeo]s?|(?:feit|oferecid|prestad)[oa]s?\s+pel[oa]s?)\b")
# "oficina sobre ... a nova Carteira de Identidade Nacional": a CIN é o tema, não o serviço.
_R_TEMA = re.compile(r"\b(?:sobre|a\s+respeito\s+d[aeo]s?|tema)\b")
_R_VOLTA_AO_PEDIDO = re.compile(
    r"\b(?:e\s+tambem|alem\s+d[aeo]s?|e\s+(?:a|o|as|os)?\s*(?:emissao|coleta|confeccao|atendimento|exposicao))\b"
)
_R_ORACAO = re.compile(r"[^,;:.\n!?()]+")


def texto_do_pedido(texto: str) -> str:
    """O texto com as orações que não pedem nada à PCPR trocadas por espaços.

    Some a oração negada ("não precisamos de emissão de RG"), a do serviço
    de outro órgão ("por conta da Defensoria") e o tema ("capacitação sobre
    a nova CIN"). As posições do texto desquebrado não mudam.
    """
    texto = desquebrar(texto or "")
    dobrado = dobrar(texto)
    saida = list(texto)
    for m in _R_ORACAO.finditer(dobrado):
        oracao = m.group(0)
        corte = None
        negacao = _R_NEGACAO.search(oracao)
        if negacao:
            corte = negacao.start()
        elif _R_POR_CONTA_DE_OUTRO.search(oracao):
            corte = 0
        else:
            tema = _R_TEMA.search(oracao)
            if tema:
                corte = tema.start()
        if corte is not None:
            final = m.end()
            if corte and not negacao:
                volta = _R_VOLTA_AO_PEDIDO.search(oracao, corte)
                final = m.start() + volta.start() if volta else final
            for i in range(m.start() + corte, final):
                saida[i] = " "
    return "".join(saida)


# ---------------------------------------------------------------------------
# Quantidade de CIN
# ---------------------------------------------------------------------------

_NUMERO = (
    r"(?<![\d.,/])(?P<n>\d{1,3}(?:\.\d{3})+|\d{1,6})"
    r"(?![\d/]|[.,:]\d|\s*h\b|\s*(?:%|reais|anos|dias|horas|km|mil\b|o\b|a\b|º|ª))"
)
_PALAVRAS_CIN = r"cins?|rgs?|carteiras?|carteirinhas?|identidades?|atendimentos|agendamentos|documentos|emissoes|senhas"
_PALAVRAS_GENTE = (
    r"pessoas|idosos|idosas|alunos|alunas|estudantes|pacientes|moradores|familias|criancas|jovens|adolescentes|"
    r"trabalhadores|agricultores|inscritos|inscritas|agendados|agendadas|mulheres|homens|participantes|"
    r"beneficiarios|cidadaos|detentos|internos|presos|atendidos|atendidas"
)
_R_DIRETA = re.compile(_NUMERO + r"\s*(?:\([^)\n]{1,40}\)\s*)?(?:[a-z]{3,}\s+)?(?:" + _PALAVRAS_CIN + r")\b")
_R_GENTE = re.compile(_NUMERO + r"\s*(?:\([^)\n]{1,40}\)\s*)?(?:[a-z]{3,}\s+)?(?:" + _PALAVRAS_GENTE + r")\b")
# "120 vão precisar do documento", "130 alunos sem documento".
_R_PRECISAM = re.compile(_NUMERO + r"\s+(?:(?:" + _PALAVRAS_GENTE + r")\s+)?(?:vao|irao|precis\w*|agendad\w*|sem\s+(?:documento|carteira|rg))\b")
# "acho que uns 60." — número solto, mas estimado, numa frase sobre carteira.
_R_SOLTA = re.compile(r"\b(?:uns|umas|cerca\s+de|aproximadamente|em\s+torno\s+de)\s+" + _NUMERO + r"(?=\s*(?:[.,;!?]|$))")
_R_IDENTIFICACAO = re.compile(r"\b(?:carteir\w*|identidade|rg|cin|documento\w*|atendimento\w*|emiss\w+)\b")
# Público do evento não é quantidade de carteiras.
_R_PUBLICO = re.compile(r"\b(?:publico|visitantes|esperamos|expectativa|plateia)\b")
# Números de ações passadas: "foram emitidas 640 carteiras", "nas ações de 2025 foram 200".
_R_PASSADO = re.compile(
    r"\b(?:foram|foi|fizemos|tivemos|emitid[oa]s|atendemos|edicao\s+anterior|ano\s+passado|nas\s+acoes\s+de|na\s+edicao\s+de)\b"
)
_R_POR_DIA = re.compile(r"^\s*(?:[a-z]+\s+)?por\s+(?:dia|sabado|domingo|data|edicao|encontro|evento)\b")
_POR_EXTENSO = {"dois": 2, "duas": 2, "tres": 3, "quatro": 4, "cinco": 5, "seis": 6, "sete": 7}


def _vezes(dobrado: str, dias: int) -> int:
    """Em quantos dias/sábados/datas: "três sábados", "nos dois dias"; senão, os dias lidos."""
    m = re.search(r"\b(dois|duas|tres|quatro|cinco|seis|sete|[2-7])\s+(?:dias|sabados|domingos|datas|edicoes|encontros)\b", dobrado)
    if m:
        return _POR_EXTENSO.get(m.group(1)) or int(m.group(1))
    return max(dias, 1)


def quantidade_de_cin(texto: str, *, dias: int = 1) -> Achado | None:
    """Quantas carteiras o pedido estima.

    "300 carteiras", "150 atendimentos", "85 pessoas agendadas pra fazer a
    identidade", "acho que uns 60" (numa frase sobre RG). Não conta o público
    ("público estimado: 600 pessoas"), números de ações passadas nem gente
    em frase que não fala de documento. "300 por dia" vezes os dias do
    evento. Havendo vários, vale o maior.
    """
    texto = desquebrar(texto or "")
    dobrado = dobrar(texto)
    achados = []
    for inicio, fim in _frases(texto):
        frase = dobrado[inicio:fim]
        if _R_PASSADO.search(frase):
            continue
        sobre_documento = bool(_R_IDENTIFICACAO.search(frase))
        for regex, precisa_documento in ((_R_DIRETA, False), (_R_GENTE, True), (_R_PRECISAM, True), (_R_SOLTA, True)):
            if precisa_documento and not sobre_documento:
                continue
            for m in regex.finditer(frase):
                if regex is not _R_DIRETA and _R_PUBLICO.search(frase[max(0, m.start() - 40):m.start()]):
                    continue
                valor = int(m.group("n").replace(".", ""))
                if not 0 < valor <= 100000:
                    continue
                if _R_POR_DIA.match(frase[m.end():m.end() + 30]):
                    valor *= _vezes(dobrado, dias)
                achados.append((valor, inicio + m.start()))
    if not achados:
        return None
    valor, comeco = max(achados, key=lambda a: (a[0], -a[1]))
    trecho = texto[slice(*_frase_de(texto, comeco))].strip()[:300]
    return Achado(valor, str(valor), trecho, "M")
