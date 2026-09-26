"""Sugestões para a solicitação nova de coffee break a partir de um e-mail.

As regras do domínio: o município só do Paraná (é ele que decide o lote),
o lote e o saldo conferidos já na leitura (falta de saldo vira aviso antes
de salvar), uma data só por OS (um período vira aviso: uma OS por dia) e o
número da OS nunca sugerido — ele é da numeração única do sistema.

A leitura genérica (datas, município, telefone, assinatura, local) vem de
`core.leitura` e de `core.preencher_por_email`. Nada aqui grava.
"""

from __future__ import annotations

import re


from core.leitura.casamento import quantidade_de_pessoas
from core.leitura.datas import dobrar, horarios_do_texto
from core.leitura.mensagem import Mensagem
from core.preencher_por_email import Sugestao, Sugestoes, data_do_email, local_no_texto, municipio_do_pedido, quando_do_pedido, quem_pede

from . import services

# "Solicitação de coffee break – Ciclo de Palestras" -> "Ciclo de Palestras".
_R_PEDIDO_NO_ASSUNTO = re.compile(
    r"^\s*(?:(?:solicitacao|pedido|requisicao|reserva|solicitamos|solicito)\s+(?:de\s+|do\s+|para\s+)?)?"
    r"(?:(?:um|uma)\s+)?(?:coffee[\s-]?break|cof+e+|cafe(?:\s+da\s+manha)?|lanches?|kits?\s+(?:de\s+)?lanches?)"
    r"\s*(?:(?:para|p/)\s+(?:o|a|os|as)?\s*)?[-–:,/|]*\s*"
)
_R_ASSUNTO_GENERICO = re.compile(r"^(?:solicitacao|pedido|requisicao|urgente|importante|informacao|duvida)?\W*$")
_R_COFFEE = re.compile(r"\b(?:cof+e+(?:[\s-]?break)?|cafe|lanches?|intervalo|servir|servido|entrega|entregar)\b")
_R_PARA_QUANTOS = re.compile(
    r"\b(?:cof+e+(?:[\s-]?break)?|cafe|lanches?|kits?)\b[^.\n]{0,40}?\bpara\s+"
    r"(?:cerca\s+de\s+|aproximadamente\s+|aprox\.?\s+|uns\s+|umas\s+|ate\s+)?(?P<n>\d{1,4})\b"
    r"(?!\s*(?:h\b|hs\b|horas?|min|/|de\s+(?:jan|fev|mar|abr|mai|jun|jul|ago|set|out|nov|dez)))"
)
_R_COFFEE_NO_CORPO = re.compile(r"\b(?:cof+e+(?:[\s-]?break)?|lanches?|kits?\s+(?:de\s+)?lanches?)\b")
# "para o Encontro Regional", "do Ciclo de Palestras": palavras com inicial maiúscula.
_R_NOME_DO_EVENTO = re.compile(
    r"\b(?:para|do|da|no|na)\s+(?:o|a|os|as)\s+(?P<nome>[A-ZÀ-Ý][\wÀ-ÿ'ºª-]*"
    r"(?:\s+(?:(?:d[aeo]s?|e)\s+)?[A-ZÀ-Ý0-9][\wÀ-ÿ'ºª-]*){1,8})"
)
_R_RESPONSAVEL = re.compile(
    r"\b(?:respons[a]vel\s+(?:pelo\s+|pela\s+|por\s+)?(?:recebimento|receber|entrega)|"
    r"quem\s+(?:vai\s+)?receber(?:a)?|recebedor[a]?|contato\s+(?:no|do)\s+local|receber\s+no\s+local)"
    r"\s*(?:[:–-]|sera|e)?\s*(?P<valor>[^\n;]{3,150})"
)

#: Campos que a memória guarda por remetente ao salvar (`core.aprendizado`):
#: o que o próximo e-mail da mesma origem provavelmente repete.
CAMPOS_APRENDIDOS = ["municipio", "local_entrega", "responsavel_recebimento"]



def _nome_do_evento(corpo: str, municipio) -> Sugestao | None:
    """Sem assunto que sirva: o nome próprio do evento na frase do coffee, e o município.

    "coffee break para o Encontro Regional em Ponta Grossa" vira
    "Encontro Regional - Ponta Grossa" (no molde "Ciclo de Palestras - 1DP Curitiba").
    """
    dobrado = dobrar(corpo)
    for pedido in _R_COFFEE_NO_CORPO.finditer(dobrado):
        m = _R_NOME_DO_EVENTO.search(corpo, pedido.end(), min(len(corpo), pedido.end() + 120))
        if not m:
            continue
        nome = " ".join(m.group("nome").split())
        if municipio is not None and dobrar(municipio.nome) not in dobrar(nome):
            nome = f"{nome} - {municipio.nome}"
        return Sugestao(nome[:255], nome[:255], "M", corpo[pedido.start():m.end()].strip())
    return None


def _descricao_do_evento(mensagem: Mensagem, municipio=None) -> Sugestao | None:
    """O objeto da OS: o assunto sem "RES:"/"ENC:" e sem "Solicitação de coffee break –"."""
    assunto = mensagem.assunto_limpo
    if assunto:
        m = _R_PEDIDO_NO_ASSUNTO.match(dobrar(assunto))
        resto = assunto[m.end():] if m else assunto
        resto = " ".join(resto.split()).strip(" -–:,.")
        if len(resto) >= 4 and not _R_ASSUNTO_GENERICO.match(dobrar(resto)):
            resto = resto[:1].upper() + resto[1:]
            return Sugestao(resto[:255], resto[:255], "M", assunto)
    return _nome_do_evento(mensagem.corpo or "", municipio)


def _quantidade(corpo: str) -> Sugestao | None:
    achado = quantidade_de_pessoas(corpo)
    if achado is not None:
        return Sugestao.de_achado(achado)
    m = _R_PARA_QUANTOS.search(dobrar(corpo))
    if m and 0 < int(m.group("n")) <= 10000:
        valor = int(m.group("n"))
        return Sugestao(valor, str(valor), "M", corpo[m.start():m.end()].strip())
    return None


def _horario(texto: str, quando) -> Sugestao | None:
    """O horário do coffee ("coffee às 10h", "intervalo às 15h30"); senão, o início do evento."""
    dobrado = dobrar(texto)
    for horario in horarios_do_texto(texto):
        antes = dobrado[max(0, horario.inicio_pos - 60):horario.inicio_pos]
        frase = antes[max(antes.rfind("\n"), antes.rfind(". ")) + 1:]
        if _R_COFFEE.search(frase):
            trecho = texto[max(0, horario.inicio_pos - len(frase)):horario.fim_pos].strip()
            return Sugestao(horario.inicio, f"{horario.inicio:%H:%M}", "M", trecho)
    if quando is not None and quando.hora_inicio:
        return Sugestao(quando.hora_inicio, f"{quando.hora_inicio:%H:%M}", "M", quando.trecho)
    return None


def _responsavel(mensagem: Mensagem, pessoa) -> Sugestao | None:
    """Quem recebe no local: o que o e-mail disser; senão, nome e celular de quem pede."""
    corpo = mensagem.corpo or ""
    m = _R_RESPONSAVEL.search(dobrar(corpo))
    if m:
        valor = corpo[m.start("valor"):m.end("valor")]
        valor = re.split(r"\.\s|\.$", valor)[0]
        valor = " ".join(valor.split()).strip(" ,.;:-–")
        if len(valor) >= 3:
            return Sugestao(valor[:150], valor[:150], "M", corpo[m.start():m.end()].strip())
    if pessoa is None or not pessoa.nome:
        return None
    valor = pessoa.nome
    if pessoa.telefone is not None:
        valor = f"{valor} {pessoa.telefone.valor}"
    return Sugestao(valor[:150], valor[:150], "M", pessoa.trecho)


def _avisos_do_lote(s: Sugestoes, municipio, data, quantidade: int | None) -> None:
    """O lote sai do município: avisa já na leitura se não há lote ou se falta saldo."""
    lote, _distancia = services.escolher_lote(municipio, data)
    if lote is None:
        s.avisar(
            f"Nenhum lote ativo atende {municipio.nome}. Inclua o município na lista de um lote "
            "em Cadastros › Lotes antes de salvar."
        )
        return
    restante = getattr(lote, "restante", None)
    if restante is None:
        restante = lote.saldo_restante
    if quantidade and quantidade > restante:
        s.avisar(
            f"O {lote.rotulo_curto} ({lote.contrato.fornecedor.razao_social}), que atende "
            f"{municipio.nome}, tem saldo de {restante} unidade(s) e o pedido é de {quantidade}: "
            "a solicitação não poderá ser salva com essa quantidade."
        )


def sugestoes(mensagem: Mensagem, usuario=None) -> Sugestoes:
    """As sugestões para a tela "Nova solicitação" do coffee break, na ordem de aplicar.

    Não sugere o número da OS (numeração única do sistema) nem o período em
    texto: a OS tem uma data só.
    """
    from .forms import municipios_do_parana

    s = Sugestoes()
    texto = mensagem.texto_para_busca
    data_email = data_do_email(mensagem)
    s.por("data_solicitacao", data_email)

    pessoa = quem_pede(mensagem)
    ddd = pessoa.telefone.detalhes.get("digitos", "")[:2] if pessoa and pessoa.telefone else ""
    municipio = municipio_do_pedido(mensagem, municipios_do_parana().select_related("estado"), ddd=ddd)
    s.por("municipio", Sugestao.de_achado(municipio))

    s.por("descricao_evento", _descricao_do_evento(mensagem, municipio.valor if municipio else None))
    quantidade = _quantidade(mensagem.corpo)
    s.por("quantidade", quantidade)

    quando, avisos_da_data = quando_do_pedido(mensagem)
    for aviso in avisos_da_data:
        s.avisar(aviso)
    if quando is not None:
        confianca = quando.confianca
        if len(quando.dias) > 1 or (quando.fim and quando.fim != quando.inicio):
            fim = quando.fim or quando.dias[-1]
            confianca = "M"
            s.avisar(
                f"O pedido cita mais de um dia ({quando.inicio:%d/%m} a {fim:%d/%m}), e a OS tem uma data só: "
                f"preenchi o primeiro dia. Para os outros dias, registre uma solicitação por dia."
            )
        s.por("data_inicio_evento", Sugestao(quando.inicio, f"{quando.inicio:%d/%m/%Y}", confianca, quando.trecho))
    s.por("horario_evento", _horario(texto, quando))

    s.por("local_entrega", Sugestao.de_achado(local_no_texto(mensagem.corpo)))
    s.por("responsavel_recebimento", _responsavel(mensagem, pessoa))

    if municipio is not None:
        data = (quando.inicio if quando else None) or (data_email.valor if data_email else None)
        _avisos_do_lote(s, municipio.valor, data, int(quantidade.valor) if quantidade else None)
    return s
