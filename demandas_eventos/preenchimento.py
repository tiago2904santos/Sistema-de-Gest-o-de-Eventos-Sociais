"""Sugestões para a palestra nova a partir de um e-mail ("Preencher com um e-mail").

As regras do domínio das palestras (mapas/demandas.md §2.3):

- o canal é o do próprio pedido — E-mail (ou WhatsApp, na conversa colada);
  só um protocolo ancorado ("protocolo nº 26.613.666-8") muda o canal para
  Protocolo, como a planilha fazia com "E-MAIL E PROTOCOLO Nº …";
- o tipo do evento: PCPR na Comunidade pelo nome, Palestra por palestra,
  bate-papo ou roda de conversa; Evento só como sugestão (estande, feira,
  solenidade), porque "o evento será no auditório" também é palestra;
- os temas pelo nome do cadastro (preenche) ou pelas palavras do tema
  (sugere); o palestrante só quando o nome inteiro dele é citado, e mesmo
  assim como sugestão — na falta, a tela recomenda pelo tema;
- o que não tem campo (horário de término, turno, dias soltos, anexos)
  vai para "Informações prévias", para não se perder.

A leitura genérica (datas, município, telefone, assinatura, local e
endereço) vem de `core.leitura` e de `core.preencher_por_email`. Nada aqui
grava.
"""

from __future__ import annotations

import os
import re
from datetime import time

from django.core.exceptions import ValidationError
from django.core.validators import validate_email

from cadastros.models import Municipio
from core.leitura.casamento import cadastros_no_texto, telefone_no_texto
from core.leitura.datas import dobrar, horarios_do_texto
from core.leitura.mensagem import Mensagem
from core.preencher_por_email import (
    Sugestao,
    Sugestoes,
    data_do_email,
    municipio_do_pedido,
    protocolo_do_pedido,
    quando_do_pedido,
    quem_pede,
    sugerir_endereco,
)

from .local import local_do_pedido
from .publico import publico_no_texto
from .solicitante import (
    Instituicao,
    instituicao_da_assinatura,
    instituicao_na_linha,
    instituicoes_do_corpo,
    sem_nomes_de_instituicao,
    sigla_do_remetente,
)
from .models import CanalSolicitacao, Palestrante, Tema, TipoEventoPalestra

# O corpo inteiro vai para "Pedido/Contato"; texto maior que isto é cortado.
LIMITE_PEDIDO = 6000

_R_PCPR_NA_COMUNIDADE = re.compile(r"\b(?:pcpr|policia\s+civil)\s+na\s+comunidade\b")
_R_PALESTRA = re.compile(
    r"\b(?:palestras?|palestrante|bate[\s-]?papo|roda\s+de\s+conversa|conversa\s+com\s+(?:os|as)\s+"
    r"(?:alunos|alunas|estudantes|jovens)|orientac(?:ao|oes)\s+(?:aos|as|para\s+os|para\s+as)\s+"
    r"(?:alunos|alunas|estudantes|pais|jovens)|conscientizacao|"
    # A fala da PCPR com outro nome: "falar sobre golpes", "fala rápida", "mesa sobre crimes",
    # "capacitação para professores".
    r"falar?(?:\s+rapida)?\s+(?:\([^)]{1,20}\)\s+)?sobre|mesa(?:\s+de\s+debates?|\s+redonda)?\s+sobre|"
    r"capacitac(?:ao|oes)|treinamentos?|minicursos?|oficinas?\s+sobre)\b"
)
_R_EVENTO = re.compile(
    r"\b(?:estandes?|stands?|feiras?|exposic(?:ao|oes)|desfiles?|solenidades?|sessao\s+solene|formaturas?|"
    r"cerimonias?|homenage(?:m|ns)|inauguracao|gincanas?|festas?|festival|blitz\s+educativa|acao\s+social|mutirao)\b"
)
_R_TERMINO = re.compile(r"\b(?:termino|encerramento|fim|ate|terminar|encerrar)\b[^.\n]{0,25}$")
_R_SAUDACAO = re.compile(
    r"^\s*(?:bom\s+dia|boa\s+tarde|boa\s+noite|ola|oi|prezad[oa]s?|car[oa]s?|senhor(?:a|es)?|sr\.?|sra\.?|"
    r"ilustr[ií]ssim[oa]|excelent[ií]ssim[oa]|a\s+quem\s+possa|at\.?|a/c)\b"
)
# "Crimes virtuais" -> "crime", "virtu": as palavras de quatro letras ou mais,
# pelo começo, como a recomendação de palestrante do palestras-form.js.
_VAZIAS = frozenset({
    "para", "como", "sobre", "contra", "entre", "outros", "outras", "prevencao", "combate",
    "enfrentamento", "identificar", "importancia", "consequencias", "cuidados",
})

#: Campos que a memória guarda por remetente ao salvar (`core.aprendizado`):
#: o que o próximo e-mail da mesma origem provavelmente repete.
CAMPOS_APRENDIDOS = ["evento", "estado", "municipio", "local", "endereco", "bairro", "cep", "solicitante", "telefone", "canal_solicitacao", "temas", "palestrantes"]



def _trecho_de(texto: str, inicio: int, fim: int, margem: int = 70) -> str:
    """O texto em volta do achado (posições do texto dobrado valem no original), numa linha só."""
    return " ".join(texto[max(0, inicio - margem):min(len(texto), fim + margem)].split())


# ---------------------------------------------------------------------------
# Evento, temas e palestrantes
# ---------------------------------------------------------------------------


def _evento(texto: str) -> Sugestao | None:
    """PCPR na Comunidade e Palestra preenchem; Evento fica só como sugestão."""
    dobrado = dobrar(texto)
    rotulos = dict(TipoEventoPalestra.choices)
    for regex, valor, confianca in (
        (_R_PCPR_NA_COMUNIDADE, TipoEventoPalestra.PCPR_NA_COMUNIDADE, "M"),
        (_R_PALESTRA, TipoEventoPalestra.PALESTRA, "M"),
        (_R_EVENTO, TipoEventoPalestra.EVENTO, "B"),
    ):
        m = regex.search(dobrado)
        if m:
            return Sugestao(valor, rotulos[valor], confianca, _trecho_de(texto, m.start(), m.end()))
    return None


# O jeito comum de dizer a palavra do tema ("crimes na internet" são crimes
# cibernéticos; "abuso sexual das crianças", abuso sexual infantil).
_RAIZES_EQUIVALENTES = {
    "ciber": {"inter", "virtu", "onlin", "digit", "redes"},
    "infan": {"crian", "menor"},
}


def _parecidas(a: str, b: str) -> bool:
    """Uma letra a mais, a menos ou trocada ("bulling" por "bullying"), em palavra longa."""
    if a == b:
        return True
    if min(len(a), len(b)) < 6 or abs(len(a) - len(b)) > 1:
        return False
    if len(a) > len(b):
        a, b = b, a
    for i in range(len(b)):
        if a == b[:i] + b[i + 1:] or (len(a) == len(b) and a[:i] + a[i + 1:] == b[:i] + b[i + 1:]):
            return True
    return False


def _mesma_palavra(do_tema: str, do_texto: str) -> bool:
    """"golpe" é "golpes", "sexuais" é "sexual"; "transportes" não é "trânsito"."""
    comum = len(os.path.commonprefix([do_tema, do_texto]))
    return comum >= max(4, min(6, len(do_tema) - 1, len(do_texto) - 1)) or _parecidas(do_tema, do_texto)


def _palavras_do_tema(nome: str) -> list[str]:
    return [p for p in re.findall(r"[a-z0-9]+", dobrar(nome)) if len(p) >= 4 and p not in _VAZIAS]


def _nucleo_do_tema(nome: str) -> list[str]:
    """As palavras que dizem o tema: numa enumeração ("Golpes e fraudes", "Armas de fogo e
    desarmamento"), a primeira parte já basta."""
    return _palavras_do_tema(re.split(r"\s+e\s+", nome, maxsplit=1)[0])


def _temas_pelas_palavras(texto: str, temas: list, *, nome_inteiro: bool = False) -> list:
    """Os temas cujas palavras aparecem todas numa mesma frase do texto.

    A frase vai até o ponto (a quebra de linha no meio da frase não conta);
    vale o plural, o jeito comum de dizer a palavra ("internet" por
    "cibernético") e o erro de uma letra ("bulling"). Numa enumeração basta
    a primeira parte, a não ser com `nome_inteiro`.
    """
    frases = [re.findall(r"[a-z0-9]+", dobrar(f)) for f in re.split(r"[.!?;]+|\n\s*\n", texto) if f.strip()]
    achados = []
    for tema in temas:
        palavras = _palavras_do_tema(tema.nome) if nome_inteiro else _nucleo_do_tema(tema.nome)

        def tem(palavra, frase):
            equivalentes = _RAIZES_EQUIVALENTES.get(palavra[:5], set())
            return any(_mesma_palavra(palavra, p) or p[:5] in equivalentes for p in frase)

        if palavras and any(all(tem(p, frase) for p in palavras) for frase in frases):
            achados.append(tema)
    return achados


def _temas(corpo: str, assunto: str) -> Sugestao | None:
    """Os temas do cadastro citados no pedido.

    Pelo nome do cadastro ("crimes virtuais") preenche; só pelas palavras,
    todas na mesma frase ("crime virtual"; "violência contra a mulher no
    ambiente doméstico" para "Violência doméstica"), fica como sugestão —
    a não ser junto de um tema citado pelo nome ("bullying e crimes na
    internet"). O nome de instituição não é tema ("Secretaria de Trânsito").
    """
    texto = sem_nomes_de_instituicao("\n\n".join(x for x in (assunto, corpo) if x))
    temas = list(Tema.objects.order_by("nome"))
    if not texto.strip() or not temas:
        return None
    achados = cadastros_no_texto(texto, temas)
    escolhidos = [a.valor for a in achados]
    if escolhidos:
        # Junto do tema citado pelo nome, só o que tem o nome inteiro em outras palavras.
        todos = escolhidos + [t for t in _temas_pelas_palavras(texto, temas, nome_inteiro=True) if t not in escolhidos]
        trecho = " · ".join(dict.fromkeys(a.trecho for a in achados if a.trecho))
        return Sugestao(todos, ", ".join(t.nome for t in todos), "M", trecho)
    parecidos = _temas_pelas_palavras(texto, temas)
    if parecidos:
        return Sugestao(parecidos, ", ".join(t.nome for t in parecidos), "B", "Palavras do tema citadas no pedido.")
    return None


def _palavras_do_nome(nome: str) -> list[str]:
    return re.findall(r"[a-z0-9]{2,}", dobrar(nome))


# O cargo policial antes do primeiro nome: "o investigador Everton", "a Dra. Juliana".
_R_CARGO_POLICIAL = re.compile(
    r"\b(?:investigador(?:a)?|delegad[oa]|escriv(?:a|ao)|agente|papiloscopista|perit[oa]|policial|dra?\.?|doutor(?:a)?)\s+$"
)


def _palestrantes(corpo: str) -> Sugestao | None:
    """O palestrante pedido pelo nome, como sugestão (na falta, a tela recomenda pelo tema).

    Vale o nome inteiro, o nome abreviado (o primeiro e o último: "Dra.
    Juliana Mehl" para Juliana Bittencourt Mehl) e o primeiro nome sozinho
    depois do cargo ("o investigador Everton"), se só um palestrante do
    cadastro tem esse nome. Nome solto ("Oi Andréia") não é pedido.
    """
    opcoes = [p for p in Palestrante.objects.order_by("nome") if len(_palavras_do_nome(p.nome)) >= 2]
    if not corpo or not opcoes:
        return None
    abreviados = {}
    for p in opcoes:
        palavras = p.nome.split()
        if len(palavras) >= 3:
            abreviados[f"{palavras[0]} {palavras[-1]}"] = p
    achados = cadastros_no_texto(corpo, opcoes, sinonimos=abreviados)
    escolhidos = [a.valor for a in achados]
    trechos = [a.trecho for a in achados if a.trecho]
    primeiros = {}
    for p in opcoes:
        primeiros.setdefault(_palavras_do_nome(p.nome)[0], []).append(p)
    dobrado = dobrar(corpo)
    for primeiro, donos in primeiros.items():
        if len(donos) != 1 or donos[0] in escolhidos:
            continue
        for m in re.finditer(r"(?<![a-z0-9])" + re.escape(primeiro) + r"(?![a-z0-9])", dobrado):
            if _R_CARGO_POLICIAL.search(dobrado[max(0, m.start() - 20):m.start()]):
                escolhidos.append(donos[0])
                trechos.append(_trecho_de(corpo, m.start(), m.end()))
                break
    if not escolhidos:
        return None
    trecho = " · ".join(dict.fromkeys(trechos))
    return Sugestao(escolhidos, ", ".join(p.nome for p in escolhidos), "B", trecho)


# ---------------------------------------------------------------------------
# Quem pede, canal e o texto do pedido
# ---------------------------------------------------------------------------


def _instituicao(mensagem: Mensagem, fortes: list, fracas: list) -> Instituicao | None:
    """A instituição que pede, na ordem de `solicitante.py`."""
    if fortes:
        return fortes[0]
    nome = instituicao_da_assinatura(mensagem.assinatura)
    if nome:
        return Instituicao(nome, "Assinatura do e-mail.")
    if mensagem.origem != "eprotocolo":
        nome = instituicao_na_linha(mensagem.remetente_nome or "")
        if nome:
            return Instituicao(nome, mensagem.remetente or "")
    return fracas[0] if fracas else None


def _pessoa_de_contato(pessoa, instituicao: Instituicao | None) -> str:
    """O nome de gente ao lado da instituição; nunca o de quem só encaminha."""
    if pessoa is None or not pessoa.nome or (instituicao and instituicao.encaminhado):
        return ""
    dobrado = dobrar(pessoa.nome)
    # "Equipe Natal Solidário", "eProtocolo - Notificação": não é gente.
    if instituicao_na_linha(pessoa.nome) or re.search(r"\b(?:equipe|comissao|direcao|coordenacao|orientacao|marketing|eventos|setor|departamento|eprotocolo|notificacao)\b", dobrado):
        return ""
    return pessoa.nome


def _solicitante(mensagem: Mensagem, pessoa, instituicao: Instituicao | None) -> Sugestao | None:
    """"Nome — Instituição", como a coluna Solicitante da planilha."""
    if instituicao is None:
        if pessoa is None or not (pessoa.nome or pessoa.unidade):
            return None
        complemento = pessoa.unidade or pessoa.cargo
        valor = " — ".join(x for x in (pessoa.nome, complemento) if x)[:1000]
        return Sugestao(valor, valor, "M", pessoa.trecho)
    nome = instituicao.nome
    sigla = sigla_do_remetente(mensagem.remetente_nome or "", nome)
    if sigla:
        nome += f" ({sigla})"
    valor = " — ".join(x for x in (_pessoa_de_contato(pessoa, instituicao), nome) if x)[:1000]
    return Sugestao(valor, valor, "M", instituicao.trecho)


def _citado(mensagem: Mensagem) -> str:
    """O texto das mensagens citadas, sem os ">" (a resposta "confirmo" traz o pedido embaixo)."""
    return "\n".join(re.sub(r"^(?:\s*>)+\s?", "", linha) for linha in (mensagem.citado or "").split("\n"))


def _publico(mensagem: Mensagem):
    """O público do corpo; sem nenhum, o do pedido citado embaixo da resposta."""
    return publico_no_texto(mensagem.corpo) or publico_no_texto(_citado(mensagem))


# Quem só repassa o pedido: a própria PCPR (delegacia, Protocolo Geral) e os
# avisos automáticos ("naoresponda@", "noreply@"). O contato é o do pedido.
_R_REPASSE = re.compile(r"^(?:nao-?responda|no-?reply|nao-?responder|do-?not-?reply)@|[@.]pc\.pr\.gov\.br$")
_R_EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
# "Contato: …", "O contato da escola é …", "Contato do colégio: …" — até o fim do parágrafo.
_R_CONTATO = re.compile(r"\bcontato\b[^\n]{0,40}?(?:[:é]|\be\b)(?P<resto>[^\n]*(?:\n(?!\s*\n)[^\n]*)?)", re.IGNORECASE)


def _valido(endereco: str) -> bool:
    try:
        validate_email(endereco)
    except ValidationError:
        return False
    return True


def _so_repassa(mensagem: Mensagem, instituicao: Instituicao | None) -> bool:
    remetente = (mensagem.remetente_email or "").strip().lower()
    return (
        not remetente
        or mensagem.origem == "eprotocolo"
        or bool(_R_REPASSE.search(remetente))
        or bool(instituicao and instituicao.encaminhado)
    )


def _contato_no_corpo(corpo: str) -> str:
    """O trecho "Contato: …" do corpo (o da escola num pedido encaminhado)."""
    m = _R_CONTATO.search(corpo or "")
    return m.group("resto") if m else ""


def _email(mensagem: Mensagem, repassado: bool) -> Sugestao | None:
    """O e-mail de quem pede: o remetente; num repasse, o do pedido (o "Contato:" ou o timbre)."""
    remetente = (mensagem.remetente_email or "").strip().lower()
    if repassado:
        corpo = mensagem.corpo or ""
        candidatos = _R_EMAIL.findall(_contato_no_corpo(corpo)) + _R_EMAIL.findall(corpo)
        for endereco in candidatos:
            endereco = endereco.strip(".").lower()
            if _valido(endereco) and not _R_REPASSE.search(endereco):
                return Sugestao(endereco, endereco, "M", "E-mail de contato citado no pedido.")
    if not remetente or not _valido(remetente) or _R_REPASSE.search(remetente):
        return None
    return Sugestao(remetente, remetente, "A", mensagem.remetente)


def _telefone(mensagem: Mensagem, pessoa, repassado: bool):
    """O telefone de quem pede.

    Num repasse, o do "Contato:" do pedido (não o de quem encaminha). Na
    assinatura, o número marcado "plantão" não é o contato.
    """
    if repassado:
        contato = telefone_no_texto(_contato_no_corpo(mensagem.corpo).replace("\n", " "), preferir_celular=False)
        if contato is not None:
            return contato
    if pessoa is None or pessoa.telefone is None:
        return None
    sem_plantao = re.sub(r"(?i)plant[aã]o\s*:?\s*[+\d(][\d\s().-]{7,}", "", mensagem.assinatura or "")
    if sem_plantao != (mensagem.assinatura or ""):
        return telefone_no_texto(sem_plantao) or pessoa.telefone
    return pessoa.telefone


# O registro que a equipe escreve do pedido que não veio por escrito: o recado
# de telefone ("RECADO", "Ligou a diretora…") e o atendimento no balcão.
_R_TELEFONEMA = re.compile(r"^\W*(?:recado|ligacao|atendimento\s+telefonico|ligou\b|telefonou\b)")
_R_PRESENCIAL = re.compile(r"^\W*(?:atendimento\s+presencial|compareceu\b|esteve\s+(?:aqui|na\s+ascom|no\s+setor))")


def _registro_de_atendimento(mensagem: Mensagem):
    """(canal, motivo) quando o texto colado é o registro de um telefonema ou de uma visita."""
    if mensagem.origem not in ("texto", "txt") or mensagem.remetente_email:
        return None
    linhas = [dobrar(linha) for linha in (mensagem.corpo or "").split("\n") if linha.strip()][:3]
    for linha in linhas:
        if _R_TELEFONEMA.search(linha):
            return CanalSolicitacao.TELEFONE, "Recado de telefonema."
        if _R_PRESENCIAL.search(linha):
            return CanalSolicitacao.PRESENCIAL, "Registro de atendimento presencial."
    return None


def _canal_e_protocolo(s: Sugestoes, mensagem: Mensagem) -> None:
    """E-mail (ou WhatsApp) pela origem; Protocolo só com o número ancorado."""
    rotulos = dict(CanalSolicitacao.choices)
    protocolo = protocolo_do_pedido(mensagem)
    if protocolo is not None:
        do_processo = mensagem.origem == "eprotocolo"
        confianca = "A" if do_processo else "M"
        s.por("canal_solicitacao", Sugestao(CanalSolicitacao.PROTOCOLO, rotulos[CanalSolicitacao.PROTOCOLO], confianca, protocolo.trecho))
        s.por("protocolo", Sugestao.de_achado(protocolo, confianca=confianca))
        if not do_processo:
            s.avisar(
                f"O pedido cita o protocolo {protocolo.valor}: o canal ficou Protocolo. "
                "Se o pedido veio só por e-mail, troque para E-mail."
            )
        return
    registro = _registro_de_atendimento(mensagem)
    if registro is not None:
        canal, motivo = registro
        s.por("canal_solicitacao", Sugestao(canal, rotulos[canal], "M", motivo))
        return
    canal = CanalSolicitacao.WHATSAPP if mensagem.origem == "whatsapp" else CanalSolicitacao.EMAIL
    motivo = "Conversa do WhatsApp colada." if canal == CanalSolicitacao.WHATSAPP else "O pedido chegou por e-mail."
    s.por("canal_solicitacao", Sugestao(canal, rotulos[canal], "A", motivo))


def _pedido_contato(mensagem: Mensagem) -> Sugestao | None:
    """O pedido inteiro (sem citações) e a assinatura, que é o contato."""
    corpo = (mensagem.corpo or "").strip()
    if not corpo:
        return None
    texto = corpo
    if mensagem.assinatura.strip():
        texto += "\n\n" + mensagem.assinatura.strip()
    if len(texto) > LIMITE_PEDIDO:
        texto = texto[:LIMITE_PEDIDO].rstrip() + "…"
    return Sugestao(texto, " ".join(corpo.split())[:120], "A", mensagem.assunto_limpo)


def _descricao(corpo: str) -> Sugestao | None:
    """O primeiro parágrafo que diz algo (sem o "Bom dia"), como sugestão."""
    for paragrafo in re.split(r"\n\s*\n", corpo or ""):
        linhas = [linha for linha in paragrafo.strip().split("\n") if linha.strip()]
        while linhas and _R_SAUDACAO.match(dobrar(linhas[0])) and len(linhas[0]) <= 60:
            linhas.pop(0)
        texto = " ".join(" ".join(linhas).split())
        if len(texto) >= 40:
            texto = texto[:1000]
            return Sugestao(texto, texto[:120] + ("…" if len(texto) > 120 else ""), "B", "1º parágrafo do pedido.")
    return None


# ---------------------------------------------------------------------------
# Datas e o que sobra para "Informações prévias"
# ---------------------------------------------------------------------------


def _termino(quando) -> str:
    """O horário de término citado na frase da data ("término previsto às 16h")."""
    if quando.hora_fim:
        return f"{quando.hora_fim:%H:%M}"
    if not quando.hora_inicio:
        return ""
    trecho = quando.trecho
    dobrado = dobrar(trecho)
    for horario in horarios_do_texto(trecho):
        if horario.inicio > quando.hora_inicio and _R_TERMINO.search(dobrado[max(0, horario.inicio_pos - 40):horario.inicio_pos]):
            return f"{horario.inicio:%H:%M}"
    return ""


def _dias_soltos(dias) -> str:
    """"10/10, 12/10 e 14/10" quando os dias citados não são seguidos."""
    if len(dias) < 2 or (dias[-1] - dias[0]).days == len(dias) - 1:
        return ""
    datas = [f"{d:%d/%m}" for d in dias]
    return ", ".join(datas[:-1]) + " e " + datas[-1]


def _informacoes_previas(mensagem: Mensagem, quando) -> Sugestao | None:
    linhas = []
    if quando is not None:
        termino = _termino(quando)
        if termino:
            linhas.append(f"Término previsto: {termino}.")
        if quando.turno and not quando.hora_inicio:
            linhas.append(f"Período: {quando.turno}.")
        dias = _dias_soltos(quando.dias)
        if dias:
            linhas.append(f"Dias citados no pedido: {dias}.")
    nomes = [nome for nome, _ in mensagem.anexos] + list(mensagem.anexos_citados)
    if nomes:
        linhas.append("Anexos do e-mail: " + ", ".join(dict.fromkeys(nomes)) + ".")
    if not linhas:
        return None
    texto = "\n".join(linhas)
    return Sugestao(texto, " ".join(linhas), "M", "O que o pedido diz e não tem campo próprio.")


def _hora_da_opcao_escolhida(mensagem: Mensagem, dia):
    """A hora que a conversa deu junto do dia escolhido ("Pode ser a segunda opção, dia 20"
    responde a "dia 19/11 às 9h ou dia 20/11 às 14h": a hora é a do dia 20)."""
    data = rf"(?<!\d)0?{dia.day}/0?{dia.month}(?:/(?:\d{{2}})?\d{{2}})?(?!\d)"
    hora = r"\s*,?\s*(?:as|a\s+partir\s+das)\s+(?P<h>\d{1,2})\s*(?:h|:|horas)\s*(?P<m>\d{2})?"
    for texto in (mensagem.corpo, _citado(mensagem)):
        m = re.search(data + hora, dobrar(texto or ""))
        if m and int(m.group("h")) < 24 and int(m.group("m") or 0) < 60:
            return time(int(m.group("h")), int(m.group("m") or 0)), " ".join(m.group(0).split())
    return None


def _datas(s: Sugestoes, quando, mensagem: Mensagem) -> None:
    confianca = quando.confianca
    exibir = f"{quando.inicio:%d/%m/%Y}" + (f" a {quando.fim:%d/%m/%Y}" if quando.fim else "")
    s.por("data_inicio_evento", Sugestao(quando.inicio, exibir, confianca, quando.trecho))
    if quando.fim:
        s.por("data_fim_evento", Sugestao(quando.fim, f"{quando.fim:%d/%m/%Y}", confianca, quando.trecho))
    if quando.hora_inicio:
        s.por("hora_inicio", Sugestao(quando.hora_inicio, f"{quando.hora_inicio:%H:%M}", confianca, quando.trecho))
    elif (achada := _hora_da_opcao_escolhida(mensagem, quando.inicio)) is not None:
        hora, trecho = achada
        s.por("hora_inicio", Sugestao(hora, f"{hora:%H:%M}", "M", trecho))


# ---------------------------------------------------------------------------
# Todas as sugestões
# ---------------------------------------------------------------------------


def sugestoes(mensagem: Mensagem, usuario=None) -> Sugestoes:
    """As sugestões para a tela "Nova palestra", campo a campo, na ordem de aplicar.

    O estado vem antes do município (trocar o estado limpa o município) e o
    canal antes do protocolo (o número só aparece com o canal Protocolo).
    """
    s = Sugestoes()
    texto = mensagem.texto_para_busca

    s.por("data_solicitacao", data_do_email(mensagem))
    s.por("evento", _evento(texto))

    quando, avisos_da_data = quando_do_pedido(mensagem)
    for aviso in avisos_da_data:
        s.avisar(aviso)
    if quando is not None:
        _datas(s, quando, mensagem)

    pessoa = quem_pede(mensagem)
    ddd = pessoa.telefone.detalhes.get("digitos", "")[:2] if pessoa and pessoa.telefone else ""
    municipios = Municipio.objects.filter(ativo=True, estado__ativo=True).select_related("estado")
    municipio = municipio_do_pedido(mensagem, municipios, ddd=ddd)
    if municipio is not None:
        estado = municipio.valor.estado
        s.por("estado", Sugestao(estado, estado.nome, "A", municipio.trecho))
        s.por("municipio", Sugestao.de_achado(municipio))

    # O local é o nome do lugar; o endereço vai para os campos próprios.
    sugerir_endereco(s, mensagem)
    fortes, fracas = instituicoes_do_corpo(mensagem.corpo or "")
    instituicao = _instituicao(mensagem, fortes, fracas)
    s.por("local", Sugestao.de_achado(local_do_pedido(mensagem.corpo, _citado(mensagem), fortes, fracas, instituicao)))

    s.por("quantidade_publico", Sugestao.de_achado(_publico(mensagem)))
    s.por("temas", _temas(mensagem.corpo, mensagem.assunto_limpo))
    s.por("palestrantes", _palestrantes(mensagem.corpo))
    s.por("descricao", _descricao(mensagem.corpo))

    repassado = _so_repassa(mensagem, instituicao)
    s.por("solicitante", _solicitante(mensagem, pessoa, instituicao))
    s.por("telefone", Sugestao.de_achado(_telefone(mensagem, pessoa, repassado)))
    s.por("email", _email(mensagem, repassado))
    _canal_e_protocolo(s, mensagem)
    assunto = mensagem.assunto_limpo[:300]
    if assunto:
        s.por("assunto_email", Sugestao(assunto, assunto, "A", mensagem.assunto))
    s.por("pedido_contato", _pedido_contato(mensagem))
    s.por("informacoes_previas", _informacoes_previas(mensagem, quando))
    return s
