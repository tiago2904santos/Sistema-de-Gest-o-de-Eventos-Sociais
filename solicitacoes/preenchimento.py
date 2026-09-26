"""Sugestões para a solicitação nova a partir de um e-mail ("Preencher com um e-mail").

As regras do domínio do evento social: o tipo do evento por nome ou
sinônimo (curso é Capacitação, formatura é Inauguração/Solenidade), o
Paraná em Ação que fixa o solicitante, os serviços por palavra-chave, a
quantidade de CIN, o órgão e a unidade móvel só como sugestão (são decisão
interna). A leitura genérica (datas, município, telefone, assinatura, local)
vem de `core.leitura` e de `core.preencher_por_email`.

Nada aqui grava: a tela aplica as sugestões nos campos vazios e quem
preenche confere antes de salvar.
"""

from __future__ import annotations

import re

from django.utils import timezone

from cadastros.models import Municipio, OrgaoResponsavel, Servico, TipoEvento
from core.leitura.casamento import cadastro_no_texto, cadastros_no_texto, quantidade_no_texto
from core.leitura.datas import dobrar
from core.leitura.mensagem import Mensagem
from core.preencher_por_email import Sugestao, Sugestoes, data_do_email, local_no_texto, municipio_do_pedido, quando_do_pedido, quem_pede

PARANA_EM_ACAO = "Paraná em Ação"
# O que o formulário grava no solicitante quando o tipo é Paraná em Ação
# (SolicitacaoForm.clean e o app.js fazem o mesmo).
SOLICITANTE_PARANA_EM_ACAO = ("Paraná em Ação", "SEJU")

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
    "biometria": "Coleta de digitais",
    "foto": "Fotografia para documento",
    "fotos": "Fotografia para documento",
    "fotografia*": "Fotografia para documento",
    "atendimento social": "Atendimento social",
    "jurídic*": "Orientação jurídica",
    "viatura*": "Exposição de viaturas antigas e modernas",
    "exposição de viaturas": "Exposição de viaturas antigas e modernas",
}
# "Secretaria de Assistência Social" é quem pede, não o serviço pedido.
_R_ORGAO_SOCIAL = re.compile(r"\b(?:secretaria|departamento|diretoria|coordenacao)\s+(?:\w+\s+){0,2}(?:de\s+)?assistencia\s+social\b")
_R_ASSISTENCIA = re.compile(r"\bassistencia\s+social\b")

PALAVRAS_CIN = (
    "cin", "cins", "rg", "rgs", "carteiras", "carteira", "identidades", "atendimentos",
    "agendamentos", "documentos", "emissões", "emissoes",
)
_R_IDENTIFICACAO = re.compile(r"\b(?:cin|rg|carteiras?\s+de\s+identidade|identidade|identificacao)\b")
_R_UNIDADE_MOVEL = re.compile(r"\b(?:unidade\s+movel|onibus|carreta|van)\b")
# "quinta-feira": a "feira" do dia da semana não é o tipo Feira.
_R_DIA_DA_SEMANA = re.compile(r"\b(segunda|terca|quarta|quinta|sexta)(\s*-?\s*)feira\b")

#: Campos que a memória guarda por remetente ao salvar (`core.aprendizado`):
#: o que o próximo e-mail da mesma origem provavelmente repete.
CAMPOS_APRENDIDOS = ["tipo_evento", "estado", "municipio", "local_evento", "solicitante_nome", "solicitante_cargo_unidade", "contato", "orgao_responsavel", "servicos", "unidade_movel", "tipo_operacao"]



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


def _tipo_do_evento(texto: str) -> Sugestao | None:
    tipos = list(TipoEvento.objects.filter(ativo=True).order_by("nome"))
    especificos = [t for t in tipos if t.nome.casefold() != TIPO_GENERICO.casefold()]
    achado = cadastro_no_texto(_sem_dia_da_semana(texto), especificos, sinonimos=SINONIMOS_TIPO)
    if achado is not None:
        return Sugestao.de_achado(achado)
    generico = next((t for t in tipos if t.nome.casefold() == TIPO_GENERICO.casefold()), None)
    if generico is None:
        return None
    return Sugestao(generico, generico.nome, "B", "Nenhum tipo específico citado no e-mail.")


def _servicos(texto: str) -> Sugestao | None:
    dobrado = dobrar(texto)
    sinonimos = dict(SINONIMOS_SERVICO)
    if _R_ASSISTENCIA.search(_R_ORGAO_SOCIAL.sub(" ", dobrado)):
        sinonimos["assistência social"] = "Atendimento social"
    achados = cadastros_no_texto(texto, Servico.objects.filter(ativo=True), sinonimos=sinonimos)
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

    tipo = _tipo_do_evento(texto)
    s.por("tipo_evento", tipo)
    parana_em_acao = bool(tipo and tipo.confianca != "B" and tipo.valor.nome.casefold() == PARANA_EM_ACAO.casefold())

    pessoa = quem_pede(mensagem)
    ddd = pessoa.telefone.detalhes.get("digitos", "")[:2] if pessoa and pessoa.telefone else ""
    municipios = Municipio.objects.filter(ativo=True, estado__ativo=True).select_related("estado")
    municipio = municipio_do_pedido(mensagem, municipios, ddd=ddd)
    if municipio is not None:
        estado = municipio.valor.estado
        s.por("estado", Sugestao(estado, estado.nome, "A", municipio.trecho))
        s.por("municipio", Sugestao.de_achado(municipio))

    s.por("local_evento", Sugestao.de_achado(local_no_texto(mensagem.corpo)))

    if parana_em_acao:
        nome, unidade = SOLICITANTE_PARANA_EM_ACAO
        motivo = "Tipo do evento Paraná em Ação: o solicitante é sempre o programa."
        s.por("solicitante_nome", Sugestao(nome, nome, "A", motivo))
        s.por("solicitante_cargo_unidade", Sugestao(unidade, unidade, "A", motivo))
    elif pessoa is not None:
        s.por("solicitante_nome", Sugestao(pessoa.nome, pessoa.nome, "M", pessoa.trecho))
        cargo = pessoa.cargo_e_unidade[:255]
        s.por("solicitante_cargo_unidade", Sugestao(cargo, cargo, "M", pessoa.trecho))
    if pessoa is not None and pessoa.telefone is not None:
        s.por("contato", Sugestao.de_achado(pessoa.telefone))

    s.por("orgao_responsavel", _orgao(texto))
    s.por("servicos", _servicos(texto))
    s.por("quantidade_cin", Sugestao.de_achado(quantidade_no_texto(mensagem.corpo, PALAVRAS_CIN)))

    movel = _R_UNIDADE_MOVEL.search(dobrar(texto))
    if movel:
        trecho = texto[max(0, movel.start() - 60):movel.end() + 60].strip()
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
