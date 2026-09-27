"""Sugestões para o atendimento novo a partir do e-mail do jornalista.

As regras do domínio da imprensa (mapas/demandas.md §2.4):

- data e horário do pedido são os do e-mail (a tela traz "agora" como padrão);
- o jornalista preenche quando o nome já está no histórico de atendimentos
  (mantém a grafia usada); nome novo fica como sugestão, para conferir. O
  nome do contato do WhatsApp ("Juliano Gazeta") cede à apresentação
  ("Juliano Ferraz aqui"); produção/chefia/assessoria que escreve "em nome
  da repórter X" → jornalista e contato são os de X; "Redação" não é nome;
- o veículo é sempre só sugestão: o pelo qual se pede, no texto (apresentação,
  assunto, corpo — não o citado como fonte da matéria), na assinatura, no
  nome do contato e, por último, no domínio do remetente (aprendido dos
  atendimentos anteriores ou colado no nome: @tvparanasul); se não houver no
  cadastro, o nome lido vai como sugestão para "Outro veículo" — que cria o
  cadastro ao salvar, então só a pessoa decide;
- o prazo ("até às 17h de hoje", "vai ao ar amanhã") vira o deadline, e a
  hora dele, que não tem campo, entra no texto do pedido;
- o responsável é quem está registrando, quando o nome casa com a equipe.

Fontes, resposta e horários de resposta não se extraem: são o que acontece
depois do pedido. Nada aqui grava.
"""

from __future__ import annotations

import re

from django.db.models import Count
from django.utils import timezone

from core.equipe import integrante_do_usuario
from core.leitura.casamento import telefone_no_texto
from core.leitura.datas import dobrar, prazo_do_texto
from core.leitura.mensagem import Mensagem
from core.preencher_por_email import Sugestao, Sugestoes, data_do_email, quem_pede

from .models import Atendimento, Responsavel, Veiculo

LIMITE_PEDIDO = 6000

# Provedores de e-mail pessoal: o domínio não diz o veículo.
DOMINIOS_GENERICOS = frozenset({
    "gmail.com", "googlemail.com", "hotmail.com", "hotmail.com.br", "outlook.com", "outlook.com.br",
    "live.com", "msn.com", "yahoo.com", "yahoo.com.br", "icloud.com", "me.com", "uol.com.br",
    "bol.com.br", "terra.com.br", "ig.com.br", "protonmail.com", "proton.me",
})
# Linha do cargo na assinatura: "Repórter | RPC Curitiba", "Produtora - Banda B".
_R_CARGO_IMPRENSA = re.compile(
    r"^(?:reporter|produtor[a]?|producao|jornalista|editor[a]?(?:[\s-]+chefe)?|pauteir[oa]|"
    r"chefe\s+de\s+reportagem|apresentador[a]?|redator[a]?|redacao|correspondente|colunista|"
    r"assistente\s+de\s+producao|rep\.)\b"
)
# O que liga o cargo ao veículo: "Repórter | RPC", "Repórter da RPC", "Produtora na Banda B".
_R_LIGACAO = re.compile(r"^(?:\s*[|/,:·•–—-]\s*|\s+(?:d[aeo]s?|n[ao]s?|em)\s+)", re.IGNORECASE)
_R_CONTATO = re.compile(r"@|https?://|www\.|\d{4}[-.\s]?\d{4}|\b(?:tel|fone|telefone|celular|cel|whats?app|ramal)\b")

#: Campos que a memória guarda por remetente ao salvar (`core.aprendizado`):
#: o que o próximo e-mail da mesma origem provavelmente repete.
CAMPOS_APRENDIDOS = ["veiculo", "jornalista", "contato", "responsavel"]



def _chave(texto: str) -> str:
    return " ".join(re.findall(r"[a-z0-9]+", dobrar(texto or "")))


# ---------------------------------------------------------------------------
# Quem escreve: apresentação no corpo e repórter em nome de quem se pede
# ---------------------------------------------------------------------------

# Palavra que abre nome de veículo: separa "Everton Zanella" de "do Jornal…".
_MIDIA = r"(?:R[aá]dio|TV|Jornal|Portal|Revista|Ag[eê]ncia|Folha|Gazeta|Tribuna|Di[aá]rio|Blog|Site|Canal|Programa|Podcast)"
_PALAVRA_NOME = r"[A-ZÀ-Ý][a-zà-ÿ]+(?:-[A-ZÀ-Ý]?[a-zà-ÿ]+)?"
# Nome de gente numa linha só (sem atravessar a quebra: a linha de baixo é outra coisa).
_NOME = rf"{_PALAVRA_NOME}(?:[ \t]+(?:d[aeo]s?[ \t]+)?(?!{_MIDIA}\b){_PALAVRA_NOME}){{0,4}}"
_SAUDACAO = r"(?i:(?:bom[ \t]+dia|boa[ \t]+tarde|boa[ \t]+noite|oi|ol[aá]|opa|prezad[oa]s?|pessoal)\w*[ \t,!.]*)*"
# "aqui é o Rafael Monteiro", "sou Leonardo Paixão", "meu nome é…", ". É o Sérgio Mazur".
_R_APRESENTA = re.compile(
    rf"(?:(?i:\baqui[ \t]+(?:[eé]|quem[ \t]+fala[ \t]+[eé])|\bsou|\bmeu[ \t]+nome[ \t]+[eé])[ \t]+(?i:[oa][ \t]+)?"
    rf"|(?:^|(?<=[,.!?])[ \t]*)(?i:[eé])[ \t]+(?i:[oa])[ \t]+)(?P<nome>{_NOME})",
    re.MULTILINE,
)
# "Juliano Ferraz aqui, Gazeta dos Campos".
_R_NOME_AQUI = re.compile(rf"^{_SAUDACAO}(?P<nome>{_NOME})[ \t]+aqui\b", re.MULTILINE)
# "Bom dia! Fabiano Teles, da Rádio Cidade FM", "Bia - Radio Cidade FM".
_R_NOME_DO_VEICULO = re.compile(
    rf"^{_SAUDACAO}(?P<nome>{_NOME})(?:[ \t]*,[ \t]*(?:d[aeo][ \t]+)?|[ \t]+d[aeo][ \t]+|[ \t]+[-–—|][ \t]+)(?={_MIDIA}\b)",
    re.MULTILINE,
)
# Produção/chefia/assessoria do veículo pedindo pelo repórter: "Em nome da repórter Luana Brandt".
_R_REPORTER_CITADO = re.compile(rf"(?i:\brep[oó]rter)[ \t]+(?P<nome>{_PALAVRA_NOME}(?:[ \t]+{_PALAVRA_NOME}){{1,3}})")
# Remetente que não é gente: "Produção Jornalismo TV Iguaçu", "Redação", "Chefia de Reportagem".
_R_NAO_E_PESSOA = re.compile(r"\b(?:redacao|producao|jornalismo|chefia|assessoria|reportagem|pauta|imprensa|comercial|contato)\b")
_PALAVRAS_QUE_NAO_SAO_NOME = frozenset({"bom", "boa", "oi", "ola", "preciso", "gostaria", "estou", "somos", "tudo", "equipe", "pessoal"})


def _apresentacao(corpo: str) -> tuple[str, str, int]:
    """(nome, trecho, fim do nome) de quem se apresenta no corpo; o primeiro que aparece."""
    achados = []
    for regex in (_R_APRESENTA, _R_NOME_AQUI, _R_NOME_DO_VEICULO):
        for m in regex.finditer(corpo):
            nome = m.group("nome")
            if dobrar(nome.split()[0]) in _PALAVRAS_QUE_NAO_SAO_NOME:
                continue
            achados.append((m.start("nome"), nome, m.end("nome")))
            break
    if not achados:
        return "", "", -1
    inicio, nome, fim = min(achados)
    linha_inicio = corpo.rfind("\n", 0, inicio) + 1
    linha_fim = corpo.find("\n", fim)
    return nome, corpo[linha_inicio:linha_fim if linha_fim >= 0 else None].strip(), fim


def _reporter_citado(mensagem: Mensagem) -> tuple[str, str]:
    """(nome, trecho) do repórter por quem a produção/chefia/assessoria escreve."""
    for texto in (mensagem.corpo or "", mensagem.assunto_limpo or ""):
        m = _R_REPORTER_CITADO.search(texto)
        if m:
            return m.group("nome"), " ".join(texto[max(0, m.start() - 20):m.end() + 20].split())
    return "", ""


def _so_telefone(texto: str) -> bool:
    return bool(texto) and not re.search(r"[A-Za-zÀ-ÿ]", texto) and len(re.sub(r"\D", "", texto)) >= 10


# ---------------------------------------------------------------------------
# Quem pede numa conversa do WhatsApp
# ---------------------------------------------------------------------------

# A própria assessoria na conversa: "Ascom PCPR", "Paula Ascom" (grupo interno que repassa).
_R_DA_CASA = re.compile(r"\b(?:ascom|assessoria|pcpr)\b")
# Nome completo escrito no texto (duas palavras ou mais): "Kátia Gonçalves", "Osvaldo Júnior Tanaka".
_R_NOME_COMPLETO = re.compile(
    rf"(?<![\wÀ-ÿ])(?!{_MIDIA}\b)(?P<nome>{_PALAVRA_NOME}(?:[ \t]+(?:d[aeo]s?[ \t]+)?(?!{_MIDIA}\b){_PALAVRA_NOME}){{1,4}})"
)
_CARGO_DE_IMPRENSA = r"(?:rep[oó]rter|produtor[a]?|editor[a]?|jornalista|apresentador[a]?|colunista|redator[a]?|pauteir[oa])"
# Depois do nome, o veículo: "Fulana, TV X", "Fulana – Jornal X", "Fulana, da Rádio X", "Fulana, editor do blog X".
_R_LIGA_AO_VEICULO = re.compile(
    rf"[ \t]*(?:,|[-–—|])?[ \t]*(?:(?:d[aeo]|n[ao])[ \t]+)?(?:{_CARGO_DE_IMPRENSA}[ \t]+(?:d[aeo][ \t]+)?)?",
    re.IGNORECASE,
)
# A assinatura em linhas: "Beatriz Almeida Souza" / "Repórter | TV Norte Paranaense".
_R_LINHA_DE_CARGO = re.compile(rf"[ \t]*\n[ \t]*{_CARGO_DE_IMPRENSA}\b", re.IGNORECASE)
# "produzido pela jornalista Fulana", "a produtora Fulana".
_R_CARGO_E_NOME = re.compile(rf"(?i:\b{_CARGO_DE_IMPRENSA})[ \t]+(?P<nome>{_PALAVRA_NOME}(?:[ \t]+{_PALAVRA_NOME}){{1,3}})")


_NAO_ABRE_NOME = _PALAVRAS_QUE_NAO_SAO_NOME | frozenset(
    "sou somos aqui att atenciosamente abraco abs obrigado obrigada ola meu minha e o a".split()
)


def _quem_fala(mensagem: Mensagem) -> tuple[bool, str]:
    """(é conversa, nome do contato de quem pede): o primeiro de fora da assessoria
    na última conversa (depois da última pausa de mais de 12 horas).

    Vazio quando só a assessoria fala (grupo interno repassando a ligação).
    """
    falas = [f for f in (mensagem.extras or {}).get("falas") or [] if f.get("nome")]
    if not falas:
        return False, ""
    inicio, anterior = 0, None
    for i, fala in enumerate(falas):
        quando = fala.get("enviado_em")
        if quando is not None and anterior is not None and (quando - anterior).total_seconds() > 12 * 3600:
            inicio = i
        anterior = quando or anterior
    for fala in falas[inicio:] + falas[:inicio]:
        if not _R_DA_CASA.search(dobrar(fala["nome"])):
            return True, " ".join(fala["nome"].split())
    return True, ""


def _palavras_de_veiculo(veiculos) -> set[str]:
    return {p for v in veiculos for p in _chave(v.nome).split() if p not in _PARTICULAS and len(p) >= 3}


def _nomes_no_texto(corpo: str, veiculos) -> list[tuple[int, int, str]]:
    """(início, fim, nome) de cada nome completo no texto, sem o veículo que vem colado
    ("Kátia Gonçalves da Educadora" → "Kátia Gonçalves")."""
    do_veiculo = _palavras_de_veiculo(veiculos)
    achados = []
    for m in _R_NOME_COMPLETO.finditer(corpo or ""):
        palavras = list(re.finditer(r"\S+", m.group("nome")))
        fim = len(palavras)
        for i in range(1, len(palavras)):
            palavra = dobrar(palavras[i].group(0))
            anterior = dobrar(palavras[i - 1].group(0))
            # "da Educadora": a partícula liga ao veículo, não ao sobrenome.
            if palavra in do_veiculo and (anterior in _PARTICULAS or i == len(palavras) - 1 and i >= 2):
                fim = i - 1 if anterior in _PARTICULAS else i
                break
        # "Sou Diego Anhaia", "Att Débora…": a palavra do começo da frase não é nome.
        comeco = 0
        while comeco < fim and dobrar(palavras[comeco].group(0)) in _NAO_ABRE_NOME:
            comeco += 1
        nomes = [p for p in palavras[comeco:fim] if dobrar(p.group(0)) not in _PARTICULAS]
        if len(nomes) < 2:
            continue
        inicio = m.start("nome") + palavras[comeco].start()
        final = m.start("nome") + palavras[fim - 1].end()
        achados.append((inicio, final, corpo[inicio:final]))
    return achados


def _se_identifica(corpo: str, veiculos, nomes) -> tuple[str, str]:
    """(nome, trecho) de quem se identifica com o veículo no texto: a apresentação,
    "Fulana, TV X", "Att, Fulana – Jornal X", a assinatura em linhas ("Fulana" /
    "Repórter | TV X"), "produzido pela jornalista Fulana"."""
    achados = []
    apresentado, trecho, fim = _apresentacao(corpo)
    if apresentado:
        achados.append((fim - len(apresentado), apresentado, trecho))
    for inicio, fim, nome in nomes:
        liga = _R_LIGA_AO_VEICULO.match(corpo, fim)
        depois = corpo[liga.end():liga.end() + 80] if liga else ""
        veiculo_logo_depois = re.match(rf"(?i:{_MIDIA}|podcast)\b", depois) or any(
            i == 0 for i, _, _ in _mencoes(depois, veiculos))
        if (liga and liga.end() > fim and veiculo_logo_depois) or _R_LINHA_DE_CARGO.match(corpo, fim):
            achados.append((inicio, nome, " ".join(corpo[inicio:fim + 60].split())))
    for m in _R_CARGO_E_NOME.finditer(corpo):
        achados.append((m.start("nome"), m.group("nome"), " ".join(m.group(0).split())))
    if not achados:
        return "", ""
    _inicio, nome, trecho = min(achados, key=lambda a: a[0])
    return nome, trecho


def _jornalista_na_conversa(mensagem: Mensagem, veiculos) -> tuple[str, str]:
    """(nome, trecho) de quem pede numa conversa do WhatsApp; vazio quando a conversa não diz.

    O contato salvo é apelido ("Ju Gazeta", "Fernanda Litoral", "Kátia 📻
    Educadora AM"): vale o nome completo do texto com o mesmo nome. Contato
    que não é gente (número, "Tribuna PG - Redação", "Podcast…", a própria
    assessoria repassando a ligação) ou só um apelido ("Bia TV Norte",
    "Juninho Rádio Vale", "Beto Plantão"): vale quem se identifica no texto;
    sem ninguém que se identifique, o contato com nome e sobrenome. A assessoria
    que abre a conversa nunca é o jornalista.
    """
    conversa, quem = _quem_fala(mensagem)
    if not conversa:
        return "", ""
    corpo = mensagem.corpo or ""
    nomes = _nomes_no_texto(corpo, veiculos)
    # O contato sem o veículo: "Thiago Rádio Cidade" → "Thiago"; "Everton Blog Fronteira" → "Everton".
    contato = re.split(rf"(?i:\b(?:{_MIDIA}|podcast)\b)", quem)[0] if not _so_telefone(quem) else ""
    contato = _sem_veiculo(contato, veiculos)
    do_veiculo = _palavras_de_veiculo(veiculos)
    palavras = [p for p in _chave(contato).split() if len(p) >= 3 and p not in do_veiculo]
    if _R_NAO_E_PESSOA.search(dobrar(quem)):
        palavras = []
    for _inicio, _fim, nome in nomes:
        if set(palavras) & set(_chave(nome).split()):
            return nome, f"{quem} · {nome}"
    # O contato não aparece no texto: quem se identifica nele vale mais ("Beto Plantão" → "Aqui é o Roberto…").
    nome, trecho = _se_identifica(corpo, veiculos, nomes)
    if nome:
        return nome, trecho
    if len(palavras) >= 2:
        return " ".join(contato.split()).strip(" -–—|,"), quem
    return "", ""


# ---------------------------------------------------------------------------
# Jornalista
# ---------------------------------------------------------------------------


def _jornalista(pessoa, mensagem: Mensagem, veiculos) -> tuple[Sugestao | None, bool]:
    """(o nome de quem pede, na grafia do histórico; se veio de "repórter X" citado).

    Ordem: o repórter por quem a produção/chefia escreve; a apresentação no
    corpo quando o remetente não é um e-mail (o nome do contato do WhatsApp
    é apelido: "Juliano Gazeta"); a assinatura/remetente; a apresentação.
    Casou com um jornalista já atendido: preenche. Nome novo: sugestão.
    """
    remetente = (pessoa.nome if pessoa else "") or mensagem.remetente_nome
    remetente = " ".join((remetente or "").split())
    if _so_telefone(remetente) or _R_NAO_E_PESSOA.search(dobrar(remetente)):
        remetente = ""
    elif remetente and not mensagem.remetente_email:
        # Contato do WhatsApp "Bruna Salvatti TV Paraná Sul": o veículo não é nome.
        remetente = _sem_veiculo(remetente, veiculos)
    apresentado, trecho_apresentado, _ = _apresentacao(mensagem.corpo or "")
    reporter, trecho_reporter = _reporter_citado(mensagem)
    trecho_remetente = pessoa.trecho if pessoa else mensagem.remetente
    na_conversa, trecho_conversa = _jornalista_na_conversa(mensagem, veiculos) if mensagem.origem == "whatsapp" else ("", "")
    if reporter and _chave(reporter).split()[:1] != _chave(remetente).split()[:1]:
        nome, trecho = reporter, trecho_reporter
    elif na_conversa:
        nome, trecho = na_conversa, trecho_conversa
    elif apresentado and (not mensagem.remetente_email or not remetente):
        nome, trecho = apresentado, trecho_apresentado
    elif remetente:
        nome, trecho = remetente, trecho_remetente
    else:
        nome, trecho = apresentado, trecho_apresentado
    nome = nome[:150]
    chave = _chave(nome)
    if not chave:
        return None, False
    citado = nome == reporter
    palavras = chave.split()
    curto = f"{palavras[0]} {palavras[-1]}" if len(palavras) > 2 else ""
    conhecidos = Atendimento.objects.order_by("jornalista").values_list("jornalista", flat=True).distinct()
    for conhecido in conhecidos:
        if _chave(conhecido) in (chave, curto):
            return Sugestao(conhecido, conhecido, "M", f"Já atendido antes · {trecho}"), citado
    return Sugestao(nome, nome, "B", f"Jornalista ainda não atendido · {trecho}"), citado


# ---------------------------------------------------------------------------
# Veículo
# ---------------------------------------------------------------------------

_TIPOS_DE_VEICULO = frozenset({"jornal", "radio", "tv", "portal", "revista", "agencia", "site", "blog"})
_PARTICULAS = frozenset({"de", "da", "do", "das", "dos", "em", "e"})
# Veículo citado como fonte da matéria ou só como o e-mail antigo: não é por ele que se pede.
_R_CITADO_COMO_FONTE = re.compile(
    r"(?:(?:materia|reportagem|noticia|publicacao|post|entrevista)\s+(?:d[aeo]|n[ao])"
    r"|segundo\s+(?:[ao]\s+)?|conforme\s+(?:[ao]\s+)?|(?:publicad|veiculad|divulgad|noticiad)[ao]s?\s+(?:pel[ao]|n[ao])"
    r"|e-?mail\s+(?:\w+\s+)?d[ao])\s*$"
)
# O que liga quem escreve ao veículo no corpo: "sou do Portal X", "trabalho no Jornal X",
# "editora da Revista X", "colaboradora da Revista X", "assino uma coluna no Portal X".
_R_VINCULO = re.compile(
    r"\b(?:sou|somos|trabalho|escrevo|assino|coluna|colaborador[a]?|reporter|produtor[a]?|jornalista|editor[a]?|"
    r"pauteir[oa]|apresentador[a]?|redator[a]?|colunista|correspondente)\b[^.\n]{0,25}?"
    r"\b(?:d[aeo]s?|n[ao]s?|pel[ao])\s+"
)
_R_ESCRITO = re.compile(r"[A-ZÀ-Ý0-9][\wÀ-ÿ&'.-]*(?:[ \t]+(?:d[aeo]s?[ \t]+|em[ \t]+)?[A-ZÀ-Ý0-9][\wÀ-ÿ&'.-]*){0,5}")
# Depois do nome apresentado: ", da Rádio X", " do Jornal X", " - Radio X", ", editora da Revista X".
_R_DEPOIS_DO_NOME = re.compile(
    r"[ \t]*(?:,[ \t]*)?(?:(?:rep[oó]rter|produtor[a]?|editor[a]?|jornalista|apresentador[a]?|colunista|redator[a]?)[ \t]+)?"
    r"(?:d[aeo]s?[ \t]+|n[ao]s?[ \t]+|[-–—|][ \t]*)?",
    re.IGNORECASE,
)


def _apelidos(nome: str) -> list[str]:
    """As formas curtas com que o veículo aparece: "Diário do Oeste", "Rádio Cidade", "Notícias Já".

    Só com duas palavras ou mais: "Cidade" sozinha não é a Rádio Cidade FM.
    """
    palavras = _chave(nome).split()
    formas = {" ".join(palavras)}
    variantes = [palavras]
    if len(palavras) > 2 and palavras[0] in _TIPOS_DE_VEICULO:
        variantes.append(palavras[1:])
    for base in list(variantes):
        if len(base) > 2 and base[-1] in ("fm", "am"):
            variantes.append(base[:-1])
        if len(base) > 3 and base[-2:] == ["de", "noticias"]:
            variantes.append(base[:-2])
    for variante in variantes:
        if len(variante) >= 2 and variante[-1] not in _PARTICULAS:
            formas.add(" ".join(variante))
    return sorted((f for f in formas if f), key=len, reverse=True)


def _mencoes(texto: str, veiculos) -> list[tuple[int, int, Veiculo]]:
    """(início, fim, veículo) de cada citação de veículo do cadastro, na ordem do texto."""
    dobrado = dobrar(texto or "")
    padroes = sorted(((forma, v) for v in veiculos for forma in _apelidos(v.nome)), key=lambda p: -len(p[0]))
    achados, ocupado = [], [False] * len(dobrado)
    for forma, veiculo in padroes:
        regex = r"(?<![a-z0-9])" + r"[^a-z0-9]+".join(map(re.escape, forma.split())) + r"(?![a-z0-9])"
        for m in re.finditer(regex, dobrado):
            if any(ocupado[m.start():m.end()]):
                continue
            ocupado[m.start():m.end()] = [True] * (m.end() - m.start())
            achados.append((m.start(), m.end(), veiculo))
    return sorted(achados, key=lambda a: a[0])


def _mencao_do_pedido(texto: str, veiculos):
    """A 1ª citação que não é fonte da matéria (nem o e-mail antigo): (veículo, trecho)."""
    dobrado = dobrar(texto or "")
    for inicio, fim, veiculo in _mencoes(texto, veiculos):
        if _R_CITADO_COMO_FONTE.search(dobrado[max(0, inicio - 40):inicio]):
            continue
        return veiculo, " ".join(texto[max(0, inicio - 30):fim + 10].split())
    return None, ""


def _sem_veiculo(nome: str, veiculos) -> str:
    """O nome do contato sem o veículo que vem junto ("Bruna Salvatti TV Paraná Sul")."""
    mencoes = _mencoes(nome, veiculos)
    if mencoes:
        nome = nome[:mencoes[0][0]]
    return nome.strip(" -–—|,()") or ""


def _escrito_em(texto: str, pos: int) -> str:
    """O nome de veículo escrito a partir de `pos` ("blog Plantão Policial" → "Plantão Policial")."""
    trecho = texto[pos:pos + 150]
    m = _R_ESCRITO.match(trecho)
    if not m:
        # Tipo em minúscula antes do nome: "blog Plantão Policial Guarapuava".
        tipo = re.match(r"(?:blog|site|portal|jornal|programa|revista|r[aá]dio|tv)[ \t]+", trecho, re.IGNORECASE)
        m = _R_ESCRITO.match(trecho, tipo.end()) if tipo else None
    if not m:
        return ""
    nome = m.group(0).strip(" .,")
    palavras = nome.split()
    # Uma palavra só precisa ser de veículo ("Gazeta"); senão pode ser cidade, região…
    if len(palavras) < 2 and not re.match(rf"{_MIDIA}\b", nome):
        return ""
    return nome[:150]


def _veiculo_no_corpo(corpo: str, fim_do_nome: int) -> tuple[str, str]:
    """(nome escrito, trecho) do veículo pelo qual quem escreve se apresenta no corpo."""
    candidatos = []
    if fim_do_nome >= 0:
        m = _R_DEPOIS_DO_NOME.match(corpo, fim_do_nome)
        if m and m.end() > fim_do_nome:
            escrito = _escrito_em(corpo, m.end())
            if escrito:
                candidatos.append((m.end(), escrito))
    for m in _R_VINCULO.finditer(dobrar(corpo)):
        escrito = _escrito_em(corpo, m.end())
        if escrito:
            candidatos.append((m.end(), escrito))
            break
    if not candidatos:
        return "", ""
    pos, escrito = min(candidatos)
    return escrito, " ".join(corpo[max(0, pos - 40):pos + len(escrito)].split())


def _texto_do_veiculo(mensagem: Mensagem) -> tuple[str, str]:
    """(nome do veículo como escrito, trecho) pela linha do cargo na assinatura."""
    linhas = [" ".join(linha.split()).strip(" -–—|•*_") for linha in (mensagem.assinatura or "").split("\n")]
    linhas = [linha for linha in linhas if linha]
    for i, linha in enumerate(linhas):
        m = _R_CARGO_IMPRENSA.match(dobrar(linha))
        if not m:
            continue
        resto = _R_LIGACAO.sub("", linha[m.end():]).strip(" |-–—/,:·•")
        if resto and not _R_CONTATO.search(dobrar(resto)):
            return resto[:150], linha
        seguinte = linhas[i + 1] if i + 1 < len(linhas) else ""
        if seguinte and not _R_CONTATO.search(dobrar(seguinte)) and len(seguinte) <= 80:
            return seguinte[:150], f"{linha} · {seguinte}"
    # "Nome / Veículo": a 2ª linha, quando não é contato nem cargo.
    if len(linhas) >= 2 and not _R_CONTATO.search(dobrar(linhas[1])) and len(linhas[1]) <= 80:
        escrito = _escrito_em(linhas[1], 0)
        if escrito:
            return escrito, f"{linhas[0]} · {linhas[1]}"
    return "", ""


def _raiz_do_dominio(email: str) -> str:
    dominio = (email or "").rpartition("@")[2].strip().lower()
    if not dominio or dominio in DOMINIOS_GENERICOS:
        return ""
    return dominio.split(".")[0]


def _veiculo_pelo_dominio(email: str, veiculos) -> Veiculo | None:
    """O veículo do domínio: o dos atendimentos anteriores; senão, o nome colado ("@tvparanasul")."""
    dominio = (email or "").rpartition("@")[2].strip().lower()
    raiz = _raiz_do_dominio(email)
    if not raiz:
        return None
    linha = (
        Atendimento.objects.filter(contato__icontains=f"@{dominio}", veiculo__isnull=False)
        .values("veiculo")
        .annotate(total=Count("pk"))
        .order_by("-total", "veiculo")
        .first()
    )
    if linha:
        return Veiculo.objects.filter(pk=linha["veiculo"]).first()
    for veiculo in veiculos:
        palavras = _chave(veiculo.nome).split()
        colados = {"".join(palavras), "".join(p for p in palavras if p not in _PARTICULAS)}
        for colado in colados:
            # Igual, ou um é começo do outro com folga ("agenciapinhao" ~ "agenciapinhaodenoticias").
            if raiz == colado or (min(len(raiz), len(colado)) >= 8 and (colado.startswith(raiz) or raiz.startswith(colado))):
                return veiculo
    return None


def _veiculo(s: Sugestoes, mensagem: Mensagem, veiculos, fim_do_nome: int) -> None:
    """O veículo, sempre como sugestão: do cadastro, ou o nome lido para "Outro veículo".

    Vale o veículo pelo qual se pede, na ordem: o da apresentação no corpo
    ("Fulana, da Rádio X", "escrevo como colaboradora da Revista Y"), o do
    assunto, o citado no corpo (menos o citado como fonte da matéria), o da
    assinatura, o do nome do contato no WhatsApp; depois o domínio do
    e-mail (o texto manda: frila e colaborador escrevem do e-mail de outro).
    """
    corpo = mensagem.corpo or ""
    escrito, trecho_escrito = _veiculo_no_corpo(corpo, fim_do_nome)
    fontes = [(escrito, trecho_escrito)] if escrito else []
    fontes += [(mensagem.assunto, ""), (corpo, ""), (mensagem.assinatura, ""), (mensagem.remetente_nome, "")]
    for texto, trecho in fontes:
        veiculo, achado = _mencao_do_pedido(texto, veiculos)
        if veiculo is not None:
            s.por("veiculo", Sugestao(veiculo, veiculo.nome, "B", trecho or achado))
            return
    # Fora do cadastro: o nome da apresentação no corpo vale mais que o domínio.
    if escrito:
        s.por("veiculo_novo", Sugestao(escrito, escrito, "B", trecho_escrito))
        return
    pelo_dominio = _veiculo_pelo_dominio(mensagem.remetente_email, veiculos)
    if pelo_dominio is not None:
        dominio = mensagem.remetente_email.rpartition("@")[2]
        s.por("veiculo", Sugestao(pelo_dominio, pelo_dominio.nome, "B", f"Atendimentos anteriores / domínio @{dominio}"))
        return
    escrito, trecho_escrito = _texto_do_veiculo(mensagem)
    if escrito:
        s.por("veiculo_novo", Sugestao(escrito, escrito, "B", trecho_escrito))


# ---------------------------------------------------------------------------
# Contato, pedido e prazo
# ---------------------------------------------------------------------------

_R_EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
# Endereço da própria casa (a ASCOM) nunca é o contato do jornalista.
DOMINIOS_DA_CASA = ("pc.pr.gov.br",)


def _emails_em(texto: str) -> list[str]:
    return [e.lower().rstrip(".") for e in _R_EMAIL.findall(texto or "") if not e.lower().rstrip(".").endswith(DOMINIOS_DA_CASA)]


def _telefone_colado(texto: str) -> str:
    """Telefone do remetente do WhatsApp, com +55 ou sem separadores: "(41) 99734-5521"."""
    achado = telefone_no_texto(texto or "")
    if achado is not None:
        return achado.valor
    digitos = re.sub(r"\D", "", texto or "")
    if len(digitos) in (12, 13) and digitos.startswith("55"):
        digitos = digitos[2:]
    if len(digitos) in (10, 11) and _so_telefone(texto):
        return f"({digitos[:2]}) {digitos[2:-4]}-{digitos[-4:]}"
    return ""


def _contato_do_reporter(nome: str, mensagem: Mensagem) -> Sugestao | None:
    """Contato do repórter citado pela produção: o e-mail com o nome dele (corpo ou cópia)
    e o telefone da linha que fala dele. O da produção/chefia não serve."""
    partes = [dobrar(p) for p in nome.split() if len(p) >= 3]
    copia = getattr(mensagem, "copia", "") or getattr(mensagem, "cc", "") or ""
    if isinstance(copia, (list, tuple)):
        copia = ", ".join(map(str, copia))
    emails = [e for e in _emails_em(f"{mensagem.corpo}\n{copia}") if any(p in dobrar(e.split("@")[0]) for p in partes)]
    telefone = ""
    primeiro = partes[0] if partes else ""
    linhas = (mensagem.corpo or "").split("\n")
    for i, linha in enumerate(linhas):
        if primeiro and (primeiro in dobrar(linha) or re.search(r"\bdel[ae]\b", dobrar(linha))):
            achado = telefone_no_texto(linha)
            if achado is not None:
                telefone = achado.valor
                break
            # Cartão de contato do WhatsApp: "Contato: Fulano TV X" e o número na linha de baixo.
            seguinte = linhas[i + 1] if i + 1 < len(linhas) else ""
            if re.match(r"\s*contato\b", dobrar(linha)) and not re.search(r"[A-Za-zÀ-ÿ]", seguinte):
                telefone = _telefone_colado(seguinte)
                if telefone:
                    break
    valor = " / ".join(p for p in (emails[0] if emails else "", telefone) if p)[:150]
    if not valor:
        return None
    return Sugestao(valor, valor, "M", f"Contato do repórter {nome}")


def _contato(pessoa, mensagem: Mensagem) -> Sugestao | None:
    """"e-mail / telefone" de quem pediu."""
    email = (mensagem.remetente_email or "").strip().lower()
    trecho = pessoa.trecho if pessoa else mensagem.remetente
    if not email:
        # Texto colado: o e-mail que a pessoa deixou no corpo ("Contato: fulana@…").
        emails = _emails_em(mensagem.corpo)
        email = emails[0] if emails else ""
    partes = [email]
    if pessoa is not None and pessoa.telefone is not None:
        partes.append(pessoa.telefone.valor)
    elif not mensagem.remetente_email:
        # WhatsApp de número sem nome na agenda: o número é o contato.
        partes.append(_telefone_colado(mensagem.remetente_nome))
    valor = " / ".join(p for p in partes if p)[:150]
    if not valor:
        return None
    return Sugestao(valor, valor, "A", trecho)


def _pedido(mensagem: Mensagem, prazo) -> Sugestao | None:
    """O assunto e o corpo limpo; a hora do prazo, que não tem campo, no fim."""
    corpo = (mensagem.corpo or "").strip()
    assunto = mensagem.assunto_limpo
    if not corpo and not assunto:
        return None
    partes = []
    if assunto:
        partes.append(f"Assunto: {assunto}")
    if corpo:
        partes.append(corpo)
    if prazo is not None and prazo.hora:
        partes.append(f"Prazo pedido: até {prazo.hora:%H:%M} de {prazo.data:%d/%m/%Y}.")
    texto = "\n\n".join(partes)
    if len(texto) > LIMITE_PEDIDO:
        texto = texto[:LIMITE_PEDIDO].rstrip() + "…"
    exibir = " ".join((corpo or assunto).split())[:120]
    return Sugestao(texto, exibir, "A", assunto or mensagem.remetente)


def _deadline(mensagem: Mensagem, prazo) -> Sugestao | None:
    if prazo is None:
        return None
    confianca = "A" if mensagem.data_referencia else "M"
    exibir = f"{prazo.data:%d/%m/%Y}" + (f" até {prazo.hora:%H:%M}" if prazo.hora else "")
    return Sugestao(prazo.data, exibir, confianca, prazo.trecho)


def _horario_do_email(mensagem: Mensagem) -> Sugestao | None:
    # Numa conversa, a hora da fala que pede (não a do "bom dia").
    enviado = mensagem.pedido_em or mensagem.enviado_em
    if enviado is None:
        return None
    if timezone.is_aware(enviado):
        enviado = timezone.localtime(enviado)
    hora = enviado.time().replace(second=0, microsecond=0)
    return Sugestao(hora, f"{hora:%H:%M}", "A", f"Enviado em {enviado:%d/%m/%Y %H:%M}")


# ---------------------------------------------------------------------------
# Todas as sugestões
# ---------------------------------------------------------------------------


def sugestoes(mensagem: Mensagem, usuario=None) -> Sugestoes:
    """As sugestões para a tela "Novo atendimento", campo a campo."""
    s = Sugestoes()
    referencia = mensagem.data_referencia or timezone.localdate()
    pessoa = quem_pede(mensagem)
    prazo = prazo_do_texto(mensagem.texto_para_busca, referencia)

    s.por("data", data_do_email(mensagem))
    s.por("horario", _horario_do_email(mensagem))
    veiculos = list(Veiculo.objects.order_by("nome"))
    jornalista, citado = _jornalista(pessoa, mensagem, veiculos)
    s.por("jornalista", jornalista)
    _veiculo(s, mensagem, veiculos, _apresentacao(mensagem.corpo or "")[2])
    # Repórter citado pela produção/chefia: o contato é o dele, nunca o de quem escreveu.
    s.por("contato", _contato_do_reporter(jornalista.valor, mensagem) if citado else _contato(pessoa, mensagem))
    s.por("pedido", _pedido(mensagem, prazo))
    s.por("deadline", _deadline(mensagem, prazo))
    s.por("responsavel", Sugestao.de_achado(integrante_do_usuario(usuario, Responsavel.objects.order_by("nome"))))
    if prazo is not None and prazo.data < timezone.localdate():
        s.avisar(f"O prazo pedido ({prazo.data:%d/%m/%Y}) já passou: confira.")
    return s
