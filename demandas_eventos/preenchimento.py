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

A leitura genérica (datas, município, telefone, assinatura) vem de
`core.leitura` e de `core.preencher_por_email`. Nada aqui grava.
"""

from __future__ import annotations

import re

from django.core.exceptions import ValidationError
from django.core.validators import validate_email

from cadastros.models import Municipio
from core.leitura.casamento import cadastros_no_texto, quantidade_de_pessoas
from core.leitura.datas import dobrar, horarios_do_texto
from core.leitura.mensagem import Mensagem
from core.preencher_por_email import Sugestao, Sugestoes, data_do_email, municipio_do_pedido, protocolo_do_pedido, quando_do_pedido, quem_pede

from .models import CanalSolicitacao, Palestrante, Tema, TipoEventoPalestra

# O corpo inteiro vai para "Pedido/Contato"; texto maior que isto é cortado.
LIMITE_PEDIDO = 6000

_R_PCPR_NA_COMUNIDADE = re.compile(r"\b(?:pcpr|policia\s+civil)\s+na\s+comunidade\b")
_R_PALESTRA = re.compile(
    r"\b(?:palestras?|palestrante|bate[\s-]?papo|roda\s+de\s+conversa|conversa\s+com\s+(?:os|as)\s+"
    r"(?:alunos|alunas|estudantes|jovens)|orientac(?:ao|oes)\s+(?:aos|as|para\s+os|para\s+as)\s+"
    r"(?:alunos|alunas|estudantes|pais|jovens)|conscientizacao)\b"
)
_R_EVENTO = re.compile(
    r"\b(?:estandes?|stands?|feiras?|exposic(?:ao|oes)|desfiles?|solenidades?|formaturas?|gincanas?|"
    r"festas?|festival|blitz\s+educativa|acao\s+social|mutirao)\b"
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
CAMPOS_APRENDIDOS = ["evento", "estado", "municipio", "solicitante", "telefone", "canal_solicitacao", "temas", "palestrantes"]



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


def _raizes(texto: str) -> list[str]:
    palavras = re.findall(r"[a-z0-9]+", dobrar(texto))
    return [p[:5] for p in palavras if len(p) >= 4 and p not in _VAZIAS]


def _temas_pelas_palavras(texto: str, temas: list) -> list:
    """Os temas cujas palavras (pelo começo) aparecem todas numa mesma frase do texto."""
    frases = [set(_raizes(frase)) for frase in re.split(r"[\n.!?;]+", texto) if frase.strip()]
    achados = []
    for tema in temas:
        raizes = set(_raizes(tema.nome))
        if raizes and any(raizes <= frase for frase in frases):
            achados.append(tema)
    return achados


def _temas(corpo: str, assunto: str) -> Sugestao | None:
    """Os temas do cadastro citados no pedido.

    Pelo nome do cadastro ("crimes virtuais") preenche; só pelas palavras,
    todas na mesma frase ("crime virtual"; "violência contra a mulher no
    ambiente doméstico" para "Violência doméstica"), fica como sugestão.
    """
    texto = "\n".join(x for x in (assunto, corpo) if x)
    temas = list(Tema.objects.order_by("nome"))
    if not texto.strip() or not temas:
        return None
    achados = cadastros_no_texto(texto, temas)
    if achados:
        escolhidos = [a.valor for a in achados]
        trecho = " · ".join(dict.fromkeys(a.trecho for a in achados if a.trecho))
        return Sugestao(escolhidos, ", ".join(t.nome for t in escolhidos), "M", trecho)
    parecidos = _temas_pelas_palavras(texto, temas)
    if parecidos:
        return Sugestao(parecidos, ", ".join(t.nome for t in parecidos), "B", "Palavras do tema citadas no pedido.")
    return None


def _palavras_do_nome(nome: str) -> list[str]:
    return re.findall(r"[a-z0-9]{2,}", dobrar(nome))


def _palestrantes(corpo: str) -> Sugestao | None:
    """Palestrante só quando o nome inteiro (duas palavras ou mais) aparece no pedido.

    Fica como sugestão: na falta, a tela recomenda os palestrantes do tema.
    """
    opcoes = [p for p in Palestrante.objects.order_by("nome") if len(_palavras_do_nome(p.nome)) >= 2]
    if not corpo or not opcoes:
        return None
    achados = cadastros_no_texto(corpo, opcoes)
    if not achados:
        return None
    escolhidos = [a.valor for a in achados]
    trecho = " · ".join(dict.fromkeys(a.trecho for a in achados if a.trecho))
    return Sugestao(escolhidos, ", ".join(p.nome for p in escolhidos), "B", trecho)


# ---------------------------------------------------------------------------
# Quem pede, canal e o texto do pedido
# ---------------------------------------------------------------------------


def _solicitante(pessoa) -> Sugestao | None:
    """"Nome — Instituição", como a coluna Solicitante da planilha."""
    if pessoa is None or not (pessoa.nome or pessoa.unidade):
        return None
    complemento = pessoa.unidade or pessoa.cargo
    valor = " — ".join(x for x in (pessoa.nome, complemento) if x)[:1000]
    return Sugestao(valor, valor, "M", pessoa.trecho)


def _email(mensagem: Mensagem) -> Sugestao | None:
    endereco = (mensagem.remetente_email or "").strip().lower()
    if not endereco:
        return None
    try:
        validate_email(endereco)
    except ValidationError:
        return None
    return Sugestao(endereco, endereco, "A", mensagem.remetente)


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


def _datas(s: Sugestoes, quando) -> None:
    confianca = quando.confianca
    exibir = f"{quando.inicio:%d/%m/%Y}" + (f" a {quando.fim:%d/%m/%Y}" if quando.fim else "")
    s.por("data_inicio_evento", Sugestao(quando.inicio, exibir, confianca, quando.trecho))
    if quando.fim:
        s.por("data_fim_evento", Sugestao(quando.fim, f"{quando.fim:%d/%m/%Y}", confianca, quando.trecho))
    if quando.hora_inicio:
        s.por("hora_inicio", Sugestao(quando.hora_inicio, f"{quando.hora_inicio:%H:%M}", confianca, quando.trecho))


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
        _datas(s, quando)

    pessoa = quem_pede(mensagem)
    ddd = pessoa.telefone.detalhes.get("digitos", "")[:2] if pessoa and pessoa.telefone else ""
    municipios = Municipio.objects.filter(ativo=True, estado__ativo=True).select_related("estado")
    municipio = municipio_do_pedido(mensagem, municipios, ddd=ddd)
    if municipio is not None:
        estado = municipio.valor.estado
        s.por("estado", Sugestao(estado, estado.nome, "A", municipio.trecho))
        s.por("municipio", Sugestao.de_achado(municipio))

    s.por("quantidade_publico", Sugestao.de_achado(quantidade_de_pessoas(mensagem.corpo)))
    s.por("temas", _temas(mensagem.corpo, mensagem.assunto_limpo))
    s.por("palestrantes", _palestrantes(mensagem.corpo))
    s.por("descricao", _descricao(mensagem.corpo))

    s.por("solicitante", _solicitante(pessoa))
    if pessoa is not None and pessoa.telefone is not None:
        s.por("telefone", Sugestao.de_achado(pessoa.telefone))
    s.por("email", _email(mensagem))
    _canal_e_protocolo(s, mensagem)
    assunto = mensagem.assunto_limpo[:300]
    if assunto:
        s.por("assunto_email", Sugestao(assunto, assunto, "A", mensagem.assunto))
    s.por("pedido_contato", _pedido_contato(mensagem))
    s.por("informacoes_previas", _informacoes_previas(mensagem, quando))
    return s
