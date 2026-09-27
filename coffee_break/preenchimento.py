"""Sugestões para a solicitação nova de coffee break a partir de um e-mail.

As regras do domínio: o município só do Paraná (é ele que decide o lote),
o lote e o saldo conferidos já na leitura (falta de saldo vira aviso antes
de salvar), uma data só por OS (um período vira aviso: uma OS por dia) e o
número da OS nunca sugerido — ele é da numeração única do sistema.

A leitura genérica (datas, município, telefone, assinatura, local, endereço) vem de
`core.leitura` e de `core.preencher_por_email`. Nada aqui grava.
"""

from __future__ import annotations

import re


from core.leitura.datas import dobrar
from core.leitura.mensagem import Mensagem
from core.preencher_por_email import (
    Sugestao,
    Sugestoes,
    data_do_email,
    municipio_do_pedido,
    quando_do_pedido,
    quem_pede,
    sugerir_endereco,
)

from . import services
from .leitura_pedido import evento_do_texto, horario_do_texto, local_do_texto, quantidade_do_texto, quem_recebe_no_texto

# "Solicitação de coffee break – Ciclo de Palestras" -> "Ciclo de Palestras".
_R_PEDIDO_NO_ASSUNTO = re.compile(
    r"^\s*(?:(?:solicitacao|pedido|requisicao|reserva|solicitamos|solicito)\s+(?:de\s+|do\s+|para\s+)?)?"
    r"(?:(?:um|uma)\s+)?(?:coffee[\s-]?break|cof+e+|cafe(?:\s+da\s+manha)?|lanches?|kits?\s+(?:de\s+)?lanches?)"
    r"\s*(?:(?:para|p/)\s+(?:o|a|os|as)?\s*)?[-–:,/|]*\s*"
)
_R_ASSUNTO_GENERICO = re.compile(r"^(?:solicitacao|pedido|requisicao|urgente|importante|informacao|duvida)?\W*$")

# "De:/Enviado em:/Assunto:" do e-mail citado: o assunto abreviado não é o nome do evento.
_R_CABECALHO_CITADO = re.compile(
    r"(?im)^\s*(?:de|from|enviado\s+em|sent|date|data|para|to|cc|assunto|subject)\s*:.*$"
)

#: Campos que a memória guarda por remetente ao salvar (`core.aprendizado`):
#: o que o próximo e-mail da mesma origem provavelmente repete.
CAMPOS_APRENDIDOS = ["municipio", "local_entrega", "endereco", "bairro", "cep", "responsavel_recebimento"]



def _partes(mensagem: Mensagem) -> list[str]:
    """Onde procurar: o corpo e, se faltar, a conversa citada (a correção
    "serão 55, e não 40" vem no corpo; o resto do pedido, no e-mail citado)."""
    citado = _R_CABECALHO_CITADO.sub("", mensagem.citado or "")
    return [t for t in (mensagem.corpo or "", citado) if t.strip()]


def _com_municipio(nome: str, municipio) -> str:
    """No molde da OS, "Encontro Regional em Ponta Grossa" vira "Encontro Regional - Ponta Grossa"."""
    if municipio is None:
        return nome
    cidade = municipio.nome
    m = re.search(r"\s+(?:em|de)\s+" + re.escape(dobrar(cidade)) + r"$", dobrar(nome))
    if m:
        nome = nome[:m.start()]
    if dobrar(cidade) not in dobrar(nome):
        nome = f"{nome} - {cidade}"
    return nome


def _descricao_do_evento(mensagem: Mensagem, municipio=None) -> Sugestao | None:
    """O evento para o qual é o coffee: o nome dito no corpo (com o município); senão, o assunto limpo."""
    for texto in _partes(mensagem):
        evento = evento_do_texto(texto)
        if evento is not None:
            nome = _com_municipio(evento.nome, municipio)[:255]
            return Sugestao(nome, nome, evento.confianca, evento.trecho)
    assunto = mensagem.assunto_limpo
    if assunto:
        m = _R_PEDIDO_NO_ASSUNTO.match(dobrar(assunto))
        resto = assunto[m.end():] if m else assunto
        resto = " ".join(resto.split()).strip(" -–:,.")
        if len(resto) >= 4 and not _R_ASSUNTO_GENERICO.match(dobrar(resto)):
            resto = resto[:1].upper() + resto[1:]
            return Sugestao(resto[:255], resto[:255], "M", assunto)
    return None


def _quantidade(mensagem: Mensagem) -> Sugestao | None:
    for texto in _partes(mensagem):
        achado = quantidade_do_texto(texto)
        if achado is not None:
            return Sugestao(achado.valor, str(achado.valor), achado.confianca, achado.trecho)
    return None


def _horario(mensagem: Mensagem, quando) -> Sugestao | None:
    """O horário do coffee ("coffee às 10h", "intervalo às 15h30"); senão, o do evento."""
    achados = [h for h in (horario_do_texto(t) for t in _partes(mensagem)) if h is not None]
    for hora in achados:
        if hora.do_coffee:
            return Sugestao(hora.valor, f"{hora.valor:%H:%M}", "M", hora.trecho)
    # O 1º horário do texto (já sem "15h\n30 participantes" virar 15h30); senão, o do evento.
    if achados:
        hora = achados[0]
        return Sugestao(hora.valor, f"{hora.valor:%H:%M}", "M", hora.trecho)
    if quando is not None and quando.hora_inicio:
        return Sugestao(quando.hora_inicio, f"{quando.hora_inicio:%H:%M}", "M", quando.trecho)
    return None


def _local_entrega(mensagem: Mensagem) -> Sugestao | None:
    """O nome do lugar da entrega (o endereço vai nos campos próprios)."""
    for texto in _partes(mensagem):
        local = local_do_texto(texto)
        if local is not None:
            return Sugestao(local.nome[:255], local.nome[:255], local.confianca, local.trecho)
    return None


def _responsavel(mensagem: Mensagem, pessoa) -> Sugestao | None:
    """Quem recebe no local: o que o e-mail disser; senão (ou "eu recebo"), nome e celular de quem pede."""
    for texto in _partes(mensagem):
        quem = quem_recebe_no_texto(texto)
        if quem is not None and not quem.eh_quem_pede:
            return Sugestao(quem.nome, quem.nome, "M", quem.trecho)
        if quem is not None:
            break
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
    quantidade = _quantidade(mensagem)
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
    s.por("horario_evento", _horario(mensagem, quando))

    s.por("local_entrega", _local_entrega(mensagem))
    sugerir_endereco(s, mensagem)
    s.por("responsavel_recebimento", _responsavel(mensagem, pessoa))

    if municipio is not None:
        data = (quando.inicio if quando else None) or (data_email.valor if data_email else None)
        _avisos_do_lote(s, municipio.valor, data, int(quantidade.valor) if quantidade else None)
    return s
