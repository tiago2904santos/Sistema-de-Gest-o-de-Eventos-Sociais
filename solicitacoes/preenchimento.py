"""Sugestões para a solicitação nova a partir de um e-mail ("Preencher com um e-mail").

As regras do domínio do evento social: o tipo do evento por nome ou
sinônimo (curso é Capacitação, formatura é Inauguração/Solenidade), os
serviços por palavra-chave (sem os negados), a quantidade de CIN, o órgão e
a unidade móvel só como sugestão (são decisão interna). O local, quem pede
e a quantidade saem de `solicitacoes.leitura`; a leitura genérica (datas,
município, telefone, endereço) vem de `core.leitura` e de
`core.preencher_por_email`.

Nada aqui grava: a tela aplica as sugestões nos campos vazios e quem
preenche confere antes de salvar.
"""

from __future__ import annotations

import re

from django.utils import timezone

from cadastros.models import Municipio, OrgaoResponsavel, Servico, TipoEvento
from core.leitura.casamento import cadastros_no_texto, telefone_no_texto
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

from .leitura import (
    desquebrar,
    local_do_evento,
    quantidade_de_cin,
    sem_tratamento,
    solicitante_do_pedido,
    texto_do_pedido,
)

# Termo do e-mail -> nome do tipo de evento cadastrado. "*" casa o começo da palavra.
SINONIMOS_TIPO = {
    "curso*": "Capacitação",
    "treinamento*": "Capacitação",
    "oficina*": "Capacitação",
    "formatura*": "Inauguração/Solenidade",
    "posse": "Inauguração/Solenidade",
    "solenidade*": "Inauguração/Solenidade",
    "inauguração*": "Inauguração/Solenidade",
    "inaugurar": "Inauguração/Solenidade",
    "cerimônia*": "Inauguração/Solenidade",
    "reinauguração*": "Inauguração/Solenidade",
    "exposição": "Feira",
    "expo": "Feira",
    "bate-papo": "Palestra",
    "roda de conversa": "Palestra",
    "visita técnica": "Visita",
    "pcpr na comunidade": "PCPR na Comunidade",
    "polícia civil na comunidade": "PCPR na Comunidade",
}
# "Evento" é o genérico: não se casa pela palavra (todo e-mail fala em
# "evento"), só entra como sugestão quando nada mais casou.
TIPO_GENERICO = "Evento"

SINONIMOS_SERVICO = {
    "cin": "Emissão de CIN",
    "rg": "Emissão de CIN",
    "carteira de identidade": "Emissão de CIN",
    "carteiras de identidade": "Emissão de CIN",
    "identidade*": "Emissão de CIN",
    "digitais": "Coleta de digitais",
    # "tirar as digital": o singular coloquial (sozinho, "digital" é outra coisa).
    "as digital": "Coleta de digitais",
    "a digital": "Coleta de digitais",
    "biometria": "Coleta de digitais",
    "foto": "Fotografia para documento",
    "fotos": "Fotografia para documento",
    "fotografia*": "Fotografia para documento",
    "atendimento social": "Atendimento social",
    # "Assistência social" sozinha é quase sempre quem pede ("diretora de
    # assistência social", "Secretaria de Assistência Social"), não o serviço.
    "atendimento de assistência social": "Atendimento social",
    "jurídic*": "Orientação jurídica",
    "viatura*": "Exposição de viaturas antigas e modernas",
    "exposição de viaturas": "Exposição de viaturas antigas e modernas",
}

_R_IDENTIFICACAO = re.compile(r"\b(?:cin|rg|carteiras?\s+de\s+identidade|identidade|identificacao)\b")
# Unidade móvel só quando inequívoca: "ônibus" sozinho pode ser o da excursão.
_R_UNIDADE_MOVEL = re.compile(
    r"\bunidade\s+movel\b|\b(?:onibus|carreta|van|caminhao|micro-?onibus|veiculo)\s+(?:da|de|do)\s+"
    r"(?:identificacao|instituto|pcpr|policia|cin|rg|documentos?)\b"
)
# "quinta-feira": a "feira" do dia da semana não é o tipo Feira.
_R_DIA_DA_SEMANA = re.compile(r"\b(segunda|terca|quarta|quinta|sexta)(\s*-?\s*)feira\b")
# "eventos ao longo do ano (palestras, feiras, ações)": tipos listados no
# plural descrevem uma parceria, não o evento pedido.
_TIPOS_NO_PLURAL = r"(?:palestras|feiras|cursos|capacitacoes|oficinas|reunioes|visitas|solenidades|inauguracoes|formaturas)"
_R_LISTA_DE_TIPOS = re.compile(_TIPOS_NO_PLURAL + r"(?:\s*(?:,|\be\b)\s*" + _TIPOS_NO_PLURAL + r")+")
# "reunião de alinhamento do calendário do Paraná em Ação": o evento é a reunião.
_R_REUNIAO_SOBRE = re.compile(r"\breunia\w*\s+(?:de|sobre|para)\b[^.;\n]{0,80}$")

#: Campos que a memória guarda por remetente ao salvar (`core.aprendizado`):
#: o que o próximo e-mail da mesma origem provavelmente repete.
CAMPOS_APRENDIDOS = ["tipo_evento", "estado", "municipio", "local_evento", "endereco", "bairro", "cep", "solicitante_nome", "solicitante_cargo_unidade", "contato", "orgao_responsavel", "servicos", "unidade_movel", "tipo_operacao"]



def _sem_dia_da_semana(texto: str) -> str:
    """Troca a "feira" de "quinta-feira" por espaços (mantendo as posições)."""
    dobrado = dobrar(texto)
    partes, inicio = [], 0
    for m in _R_DIA_DA_SEMANA.finditer(dobrado):
        partes.append(texto[inicio:m.end(2)])
        partes.append(" " * len("feira"))
        inicio = m.end()
    partes.append(texto[inicio:])
    return "".join(partes)


def _sem_posicao(texto: str, regex: re.Pattern) -> str:
    """Troca por espaços o que o regex (no texto dobrado) casar, mantendo as posições."""
    saida = list(texto)
    for m in regex.finditer(dobrar(texto)):
        saida[m.start():m.end()] = " " * (m.end() - m.start())
    return "".join(saida)


def _tipo_do_evento(texto: str) -> Sugestao | None:
    tipos = list(TipoEvento.objects.filter(ativo=True).order_by("nome"))
    especificos = [t for t in tipos if t.nome.casefold() != TIPO_GENERICO.casefold()]
    texto = _sem_posicao(_sem_dia_da_semana(texto), _R_LISTA_DE_TIPOS)
    achados = cadastros_no_texto(texto, especificos, sinonimos=SINONIMOS_TIPO)
    if achados:
        achado = achados[0]
        reuniao = next((a for a in achados if a.valor.nome.casefold() == "reunião"), None)
        if reuniao is not None and reuniao is not achado:
            # A reunião "sobre o Paraná em Ação" é reunião: o outro tipo é o assunto.
            dobrado = dobrar(texto)
            for m in re.finditer(re.escape(dobrar(achado.valor.nome)), dobrado):
                if _R_REUNIAO_SOBRE.search(dobrado[max(0, m.start() - 120):m.start()]):
                    achado = reuniao
                    break
        return Sugestao.de_achado(achado)
    generico = next((t for t in tipos if t.nome.casefold() == TIPO_GENERICO.casefold()), None)
    if generico is None:
        return None
    return Sugestao(generico, generico.nome, "B", "Nenhum tipo específico citado no e-mail.")


def _servicos(texto: str) -> Sugestao | None:
    """Os serviços pedidos à PCPR: sem os negados, os de outro órgão e a CIN como tema."""
    achados = cadastros_no_texto(texto_do_pedido(texto), Servico.objects.filter(ativo=True), sinonimos=SINONIMOS_SERVICO)
    if not achados:
        return None
    servicos = [a.valor for a in achados]
    return Sugestao(
        servicos,
        ", ".join(s.nome for s in servicos),
        "M",
        " · ".join(dict.fromkeys(a.trecho for a in achados if a.trecho))[:300],
    )


def _orgao(texto: str) -> Sugestao | None:
    """Só com pedido de identificação: o Instituto de Identificação, como sugestão."""
    m = _R_IDENTIFICACAO.search(dobrar(texto))
    if not m:
        return None
    for orgao in OrgaoResponsavel.objects.filter(ativo=True):
        if "identificacao" in dobrar(orgao.nome):
            return Sugestao(orgao, orgao.nome, "B", texto[max(0, m.start() - 60):m.end() + 60].strip())
    return None


def sugestoes(mensagem: Mensagem, usuario=None) -> Sugestoes:
    """As sugestões para a tela "Nova solicitação", campo a campo, na ordem de aplicar."""
    s = Sugestoes()
    texto = mensagem.texto_para_busca

    s.por("data_solicitacao", data_do_email(mensagem))

    quando, avisos_da_data = quando_do_pedido(mensagem)
    for aviso in avisos_da_data:
        s.avisar(aviso)
    if quando is not None:
        confianca = quando.confianca
        fim = quando.fim or quando.inicio
        exibir = f"{quando.inicio:%d/%m/%Y}" + (f" a {fim:%d/%m/%Y}" if fim != quando.inicio else "")
        s.por("data_inicio_evento", Sugestao(quando.inicio, exibir, confianca, quando.trecho))
        s.por("data_fim_evento", Sugestao(fim, f"{fim:%d/%m/%Y}", confianca, quando.trecho))

    s.por("tipo_evento", _tipo_do_evento(texto))

    pessoa = quem_pede(mensagem)
    ddd = pessoa.telefone.detalhes.get("digitos", "")[:2] if pessoa and pessoa.telefone else ""
    municipios = Municipio.objects.filter(ativo=True, estado__ativo=True).select_related("estado")
    municipio = municipio_do_pedido(mensagem, municipios, ddd=ddd)
    if municipio is not None:
        estado = municipio.valor.estado
        s.por("estado", Sugestao(estado, estado.nome, "A", municipio.trecho))
        s.por("municipio", Sugestao.de_achado(municipio))

    s.por("local_evento", Sugestao.de_achado(local_do_evento(mensagem.corpo, remetente=mensagem.remetente_nome)))
    sugerir_endereco(s, mensagem)

    # O "Paraná em Ação" não fixa mais o solicitante (o modelo do tipo é
    # aplicado na tela, com um clique): aqui vai quem de fato pede.
    solicitante = solicitante_do_pedido(mensagem)
    if solicitante is not None:
        s.por("solicitante_nome", Sugestao(solicitante.nome, solicitante.nome, "M", solicitante.trecho))
        s.por("solicitante_cargo_unidade", Sugestao(solicitante.cargo, solicitante.cargo, "M", solicitante.trecho))
    elif pessoa is not None:
        nome = sem_tratamento(pessoa.nome)
        s.por("solicitante_nome", Sugestao(nome, nome, "M", pessoa.trecho))
        cargo = pessoa.cargo_e_unidade[:255]
        s.por("solicitante_cargo_unidade", Sugestao(cargo, cargo, "M", pessoa.trecho))
    telefone = (
        (solicitante.telefone if solicitante else None)
        or (pessoa.telefone if pessoa else None)
        # WhatsApp: o remetente é o próprio número de quem pede.
        or telefone_no_texto(mensagem.remetente_nome or "")
    )
    s.por("contato", Sugestao.de_achado(telefone))

    s.por("orgao_responsavel", _orgao(texto))
    # "O resto continua igual": sem serviço nem quantidade na resposta, valem os da conversa anterior.
    servicos = _servicos(texto) or _servicos(mensagem.citado or "")
    s.por("servicos", servicos)
    dias = len(quando.dias) if quando is not None and quando.dias else (
        ((quando.fim or quando.inicio) - quando.inicio).days + 1 if quando is not None else 1
    )
    quantidade = quantidade_de_cin(texto_do_pedido(mensagem.corpo), dias=dias)
    if quantidade is None and servicos is not None and (mensagem.citado or "").strip():
        quantidade = quantidade_de_cin(texto_do_pedido(mensagem.citado), dias=dias)
    s.por("quantidade_cin", Sugestao.de_achado(quantidade))

    movel = _R_UNIDADE_MOVEL.search(dobrar(texto_do_pedido(texto)))
    if movel:
        pedido = desquebrar(texto)
        trecho = pedido[max(0, movel.start() - 60):movel.end() + 60].strip()
        s.por("unidade_movel", Sugestao(True, "Sim", "B", trecho))

    s.por("descricao_complementar", _descricao(mensagem))
    return s


def _descricao(mensagem: Mensagem) -> Sugestao | None:
    """O corpo limpo (sem citações nem assinatura) e de onde veio."""
    corpo = (mensagem.corpo or "").strip()
    if not corpo:
        return None
    if len(corpo) > 4000:
        corpo = corpo[:4000].rstrip() + "…"
    enviado = timezone.localtime(mensagem.enviado_em) if mensagem.enviado_em and timezone.is_aware(mensagem.enviado_em) else mensagem.enviado_em
    origem = "Origem: e-mail"
    if mensagem.remetente:
        origem += f" de {mensagem.remetente}"
    if enviado:
        origem += f" em {enviado:%d/%m/%Y %H:%M}"
    texto = f"{corpo}\n\n{origem}."
    return Sugestao(texto, " ".join(corpo.split())[:120], "A", mensagem.assunto_limpo)
