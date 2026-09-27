"""Bateria do módulo `solicitacoes` (Evento social).

Pedidos para a PCPR participar de eventos com unidade móvel e serviços de
identificação (CIN, digitais, fotos, atendimento social, orientação
jurídica, exposição de viaturas). Todos os nomes, telefones, e-mails e
endereços são inventados.

Convenções do gabarito deste módulo:

- ``data_solicitacao`` é a data em que o pedido foi feito (data do e-mail
  ou do ofício). Quando as duas existem e diferem, as duas valem (`UmDe`).
  Em texto colado sem data nenhuma do pedido, fica fora do gabarito.
- ``quantidade_cin`` só quando o e-mail estima atendimentos/carteiras;
  público estimado do evento (pessoas) não é quantidade de CIN.
- ``_endereco`` / ``_bairro``: o endereço do LOCAL do evento, que precisa
  aparecer no local sugerido. Endereço da assinatura não é local do evento.
"""

from datetime import datetime, timedelta, timezone
from email.header import Header
from email.utils import format_datetime
from html import escape

from . import AUSENTE, Caso, Contem, UmDe

_BRT = timezone(timedelta(hours=-3))


def _q(assunto):
    """Assunto codificado como os clientes de e-mail mandam (=?utf-8?b?...?=)."""
    return Header(assunto, "utf-8").encode()


def _eml(de, para, assunto, enviado, corpo, *, html=False, cc=None):
    """Monta um .eml (RFC 822). `enviado`: "2026-09-24 09:12" (Brasília)."""
    dt = datetime.strptime(enviado, "%Y-%m-%d %H:%M").replace(tzinfo=_BRT)
    cab = [
        f"From: {de}",
        f"To: {para}",
    ]
    if cc:
        cab.append(f"Cc: {cc}")
    cab += [
        f"Subject: {assunto}",
        f"Date: {format_datetime(dt)}",
        f"Message-ID: <{dt:%Y%m%d%H%M}.{abs(hash(assunto)) % 10**8}@mail.exemplo.test>",
        "MIME-Version: 1.0",
    ]
    corpo = corpo.strip("\n") + "\n"
    if not html:
        cab += [
            "Content-Type: text/plain; charset=utf-8",
            "Content-Transfer-Encoding: 8bit",
        ]
        return "\n".join(cab) + "\n\n" + corpo
    fronteira = "----=_Parte_000_01D9_" + f"{dt:%Y%m%d%H%M}"
    paragrafos = "".join(
        f"<p>{escape(p).replace(chr(10), '<br>')}</p>" for p in corpo.split("\n\n")
    )
    cab.append(f'Content-Type: multipart/alternative; boundary="{fronteira}"')
    partes = [
        "This is a multi-part message in MIME format.",
        "",
        f"--{fronteira}",
        "Content-Type: text/plain; charset=utf-8",
        "Content-Transfer-Encoding: 8bit",
        "",
        corpo,
        f"--{fronteira}",
        "Content-Type: text/html; charset=utf-8",
        "Content-Transfer-Encoding: 8bit",
        "",
        f'<html><head><meta charset="utf-8"></head><body style="font-family:Calibri">{paragrafos}</body></html>',
        "",
        f"--{fronteira}--",
        "",
    ]
    return "\n".join(cab) + "\n\n" + "\n".join(partes)


_CIN = "Emissão de CIN"
_DIG = "Coleta de digitais"
_FOTO = "Fotografia para documento"
_SOCIAL = "Atendimento social"
_JUR = "Orientação jurídica"
_VTR = "Exposição de viaturas antigas e modernas"

_PCPR = "Polícia Civil do Paraná <eventos.sociais@pc.pr.gov.br>"

CADASTROS = {
    "orgao": [
        "Instituto de Identificação do Paraná",
        "Secretaria de Estado da Justiça e Cidadania",
        "Secretaria de Estado da Segurança Pública",
        "Divisão de Polícia Comunitária",
        "Gabinete do Delegado-Geral",
        "Departamento da Polícia Civil do Interior",
    ],
}

CASOS = [
    # ------------------------------------------------------------------ 001
    Caso(
        id="sol-001",
        modulo="solicitacoes",
        formato="eml",
        agora="2026-09-24 10:00",
        texto=_eml(
            "Mariana Kowalski Ribas <protecao.basica@guarapuava.pr.gov.br>",
            _PCPR,
            "Solicitação de atendimento - Ação Social Morro Alto",
            "2026-09-23 16:40",
            """
Bom dia,

A Secretaria Municipal de Assistência Social de Guarapuava vem, por meio deste,
solicitar a participação da Polícia Civil na Ação Social do bairro Morro Alto,
que será realizada no dia 17/10, das 9h às 16h, no CRAS Morro Alto
(Rua Pedro Alves, 1540 - Morro Alto).

Gostaríamos de contar com a emissão de carteira de identidade e fotos para
documento. Estimamos cerca de 250 atendimentos.

Atenciosamente,

Mariana Kowalski Ribas
Coordenadora de Proteção Social Básica
Secretaria Municipal de Assistência Social - Guarapuava/PR
(42) 3630-2211
""",
        ),
        esperado={
            "estado": "PR",
            "municipio": "Guarapuava",
            "local_evento": Contem("CRAS Morro Alto"),
            "endereco": Contem("Rua Pedro Alves, 1540"),
            "bairro": "Morro Alto",
            "data_inicio_evento": "2026-10-17",
            "data_fim_evento": "2026-10-17",
            "data_solicitacao": "2026-09-23",
            "servicos": [_CIN, _FOTO],
            "quantidade_cin": 250,
            "solicitante_nome": "Mariana Kowalski Ribas",
            "solicitante_cargo_unidade": Contem("Coordenadora de Proteção Social Básica"),
            "contato": Contem("3630-2211"),
        },
        nota="Caso-base: data 'dd/mm' sem ano, horário 'das 9h às 16h' não é data; Secretaria de Assistência Social pede, não é serviço.",
    ),
    # ------------------------------------------------------------------ 002
    Caso(
        id="sol-002",
        modulo="solicitacoes",
        formato="eml",
        agora="2026-09-15 14:30",
        texto=_eml(
            "Gabinete do Prefeito <gabinete@palmas.pr.gov.br>",
            _PCPR,
            _q("Ofício nº 214/2026 – Paraná em Ação em Palmas"),
            "2026-09-14 11:05",
            """
Palmas, 10 de setembro de 2026.

Ofício nº 214/2026 - GP

Ao Senhor Delegado-Geral da Polícia Civil do Paraná

Assunto: Participação no programa Paraná em Ação

Senhor Delegado-Geral,

Cumprimentando-o cordialmente, o Município de Palmas solicita a participação
da Polícia Civil do Paraná, com a unidade móvel de identificação, no
PARANÁ EM AÇÃO que acontecerá nos dias 20 e 21 de outubro de 2026, no
Colégio Estadual Dom Carlos, Av. Coronel José Osório, 890, Centro.

Solicitamos a emissão da Carteira de Identidade Nacional (CIN), com
previsão de 400 carteiras nos dois dias.

Solicitamos resposta até 30/09.

Atenciosamente,

JOÃO BATISTA FERRAREZI
Prefeito Municipal

Enviado em nome do Prefeito por:
Luana Petrycoski - Assessora de Gabinete
(46) 3263-7000 / (46) 99912-4410
""",
        ),
        esperado={
            "tipo_evento": "Paraná em Ação",
            "estado": "PR",
            "municipio": "Palmas",
            "local_evento": Contem("Colégio Estadual Dom Carlos"),
            "endereco": Contem("Av. Coronel José Osório, 890"),
            "bairro": "Centro",
            "data_inicio_evento": "2026-10-20",
            "data_fim_evento": "2026-10-21",
            "data_solicitacao": UmDe("2026-09-10", "2026-09-14"),
            "servicos": [_CIN],
            "quantidade_cin": 400,
            "unidade_movel": True,
            "solicitante_nome": UmDe("João Batista Ferrarezi", "Luana Petrycoski"),
            "contato": UmDe(Contem("3263-7000"), Contem("99912-4410")),
        },
        nota="Data do ofício no topo e prazo de resposta 30/09 não são o evento; 'Palmas' é município e palavra comum; enviado por assessora em nome do prefeito.",
    ),
    # ------------------------------------------------------------------ 003
    Caso(
        id="sol-003",
        modulo="solicitacoes",
        formato="texto",
        agora="2026-10-05 09:20",
        texto="""De: Cláudia Zanetti <claudia.zanetti@castro.pr.gov.br>
Enviado em: segunda-feira, 5 de outubro de 2026 08:47
Para: Eventos Sociais PCPR <eventos.sociais@pc.pr.gov.br>
Assunto: Feira da Saúde e Cidadania - pedido de RG

Prezados,

O município de Castro realizará a 3ª Feira da Saúde e Cidadania no dia
14 de novembro, sábado, na Praça Manoel Ribas, centro, das 8h30 às 17h.

Pedimos, se possível, a presença da equipe para emissão de RG e coleta de
digitais. No ano passado, em 12/05/2025, atendemos 180 pessoas com vocês e
foi um sucesso.

Att.,
Cláudia Zanetti
Diretora do Departamento de Cidadania
Prefeitura Municipal de Castro
42 3233-8800
""",
        esperado={
            "tipo_evento": "Feira",
            "estado": "PR",
            "municipio": "Castro",
            "local_evento": Contem("Praça Manoel Ribas"),
            "endereco": Contem("Praça Manoel Ribas"),
            "bairro": "Centro",
            "data_inicio_evento": "2026-11-14",
            "data_fim_evento": "2026-11-14",
            "data_solicitacao": "2026-10-05",
            "servicos": [_CIN, _DIG],
            "quantidade_cin": AUSENTE,
            "solicitante_nome": "Cláudia Zanetti",
            "solicitante_cargo_unidade": Contem("Diretora do Departamento de Cidadania"),
            "contato": Contem("3233-8800"),
        },
        nota="Cabeçalho Outlook; data de evento anterior (12/05/2025) e 180 atendimentos do ano passado não valem para este; 'Castro' é sobrenome comum.",
    ),
    # ------------------------------------------------------------------ 004
    Caso(
        id="sol-004",
        modulo="solicitacoes",
        formato="texto",
        agora="2026-09-28 11:00",
        texto="""[28/09/2026 09:12] Rosangela CRAS Pinhão: Bom dia! Aqui é a Rosângela do CRAS de Pinhão
[28/09/2026 09:13] Rosangela CRAS Pinhão: a gente vai fazer uma ação comunitária no distrito de Faxinal do Céu dia 10/10
[28/09/2026 09:13] Rosangela CRAS Pinhão: vcs conseguem mandar o onibus da identificação? p fazer RG
[28/09/2026 09:15] Rosangela CRAS Pinhão: vai ser na escola municipal Rui Barbosa, rua das Araucárias 77
[28/09/2026 09:16] Rosangela CRAS Pinhão: umas 120 carteiras mais ou menos
[28/09/2026 09:20] Rosangela CRAS Pinhão: meu cel 42 99801-3344
""",
        esperado={
            "tipo_evento": "Ação Comunitária",
            "estado": "PR",
            "municipio": "Pinhão",
            "local_evento": Contem("Escola Municipal Rui Barbosa"),
            "endereco": Contem("Rua das Araucárias 77"),
            "data_inicio_evento": "2026-10-10",
            "data_fim_evento": "2026-10-10",
            "data_solicitacao": "2026-09-28",
            "servicos": [_CIN],
            "quantidade_cin": 120,
            "unidade_movel": True,
            "solicitante_nome": Contem("Rosângela"),
            "contato": Contem("99801-3344"),
        },
        nota="WhatsApp exportado em várias linhas; 'Faxinal do Céu' é distrito (não é Céu Azul); 'ônibus da identificação' = unidade móvel.",
    ),
    # ------------------------------------------------------------------ 005
    Caso(
        id="sol-005",
        modulo="solicitacoes",
        formato="eml",
        agora="2026-10-01 15:00",
        texto=_eml(
            "Escola Estadual Presidente Kennedy <direcao.kennedy@escola.pr.gov.br>",
            _PCPR,
            "palestra sobre golpes digitais",
            "2026-10-01 13:22",
            """
boa tarde

somos do Colegio Estadual Presidente Kennedy de Ponta Grossa e gostariamos
de uma palestra sobre golpes pela internet e crimes virtuais para os alunos
do ensino medio, dia 22 de outubro as 19h, no auditorio do colegio
(rua Balduino Taques 2100, bairro Jardim Carvalho)

obrigada
Profª Denise Wolski
Pedagoga
(42) 3222-4561
""",
        ),
        esperado={
            "tipo_evento": "Palestra",
            "estado": "PR",
            "municipio": "Ponta Grossa",
            "local_evento": Contem("Presidente Kennedy"),
            "endereco": Contem("Balduino Taques 2100"),
            "bairro": "Jardim Carvalho",
            "data_inicio_evento": "2026-10-22",
            "data_fim_evento": "2026-10-22",
            "data_solicitacao": "2026-10-01",
            "servicos": [],
            "quantidade_cin": AUSENTE,
            "solicitante_nome": "Denise Wolski",
            "solicitante_cargo_unidade": Contem("Pedagoga"),
            "contato": Contem("3222-4561"),
        },
        nota="Tudo minúsculo e sem acento; palestra não pede nenhum serviço de identificação; 19h não é data.",
    ),
    # ------------------------------------------------------------------ 006
    Caso(
        id="sol-006",
        modulo="solicitacoes",
        formato="eml",
        agora="2026-10-20 08:30",
        texto=_eml(
            "Coordenação Justiça no Bairro <justicanobairro@tjpr.jus.br>",
            _PCPR,
            _q("Justiça no Bairro – Foz do Iguaçu – 05 a 07/11"),
            "2026-10-19 17:55",
            """
Senhores,

Informamos que a próxima edição do Projeto Justiça no Bairro ocorrerá em
Foz do Iguaçu, de 05 a 07/11/2026, das 9:00 às 17:00, no Ginásio de Esportes
do Jardim São Paulo (Rua Tarobá, 1550 - Jardim São Paulo).

Solicitamos, como nas edições anteriores, o apoio do Instituto de
Identificação com emissão de carteiras de identidade, fotos e coleta de
digitais. A expectativa é de aproximadamente 1.200 pessoas circulando pelo
evento, com previsão de 600 carteiras de identidade.

Cordialmente,

Heloísa Brandalise Tomczak
Assessora da Coordenadoria do Projeto Justiça no Bairro
Tribunal de Justiça do Estado do Paraná
Praça Nossa Senhora da Salete, s/n - Centro Cívico - Curitiba/PR
(41) 3200-5871
""",
        ),
        esperado={
            "tipo_evento": "Justiça no Bairro",
            "estado": "PR",
            "municipio": "Foz do Iguaçu",
            "local_evento": Contem("Ginásio de Esportes do Jardim São Paulo"),
            "endereco": Contem("Rua Tarobá, 1550"),
            "bairro": "Jardim São Paulo",
            "data_inicio_evento": "2026-11-05",
            "data_fim_evento": "2026-11-07",
            "data_solicitacao": "2026-10-19",
            "servicos": [_CIN, _FOTO, _DIG],
            "quantidade_cin": 600,
            "solicitante_nome": "Heloísa Brandalise Tomczak",
            "solicitante_cargo_unidade": Contem("Justiça no Bairro"),
            "contato": Contem("3200-5871"),
        },
        nota="Intervalo 'de 05 a 07/11'; 1.200 pessoas é público, 600 carteiras é a quantidade; endereço da assinatura é em Curitiba (Centro Cívico).",
    ),
    # ------------------------------------------------------------------ 007
    Caso(
        id="sol-007",
        modulo="solicitacoes",
        formato="texto",
        agora="2026-11-03 16:10",
        texto="""---------- Forwarded message ---------
De: Assessoria Vereador Paulo Nishimura <gab.nishimura@cmlondrina.pr.gov.br>
Date: seg., 2 de nov. de 2026 às 18:21
Subject: PCPR na Comunidade - Jardim Bandeirantes
To: <eventos.sociais@pc.pr.gov.br>

Boa noite.

Em nome do vereador Paulo Nishimura, solicitamos a vinda do PCPR na Comunidade
ao Jardim Bandeirantes, em Londrina, no dia 28/11/2026 (sábado), das 9h às 15h.
Local: Centro Comunitário do Jardim Bandeirantes - Rua Guilherme de Almeida, 455.

Serviços desejados: emissão da CIN, fotos 3x4 e, se possível, orientação
jurídica para as famílias. Público estimado: 500 moradores.

Atenciosamente,
Thiago Ramires Okuda
Chefe de Gabinete
(43) 99654-0098
""",
        esperado={
            "tipo_evento": "PCPR na Comunidade",
            "estado": "PR",
            "municipio": "Londrina",
            "local_evento": Contem("Centro Comunitário do Jardim Bandeirantes"),
            "endereco": Contem("Rua Guilherme de Almeida, 455"),
            "bairro": "Jardim Bandeirantes",
            "data_inicio_evento": "2026-11-28",
            "data_fim_evento": "2026-11-28",
            "data_solicitacao": "2026-11-02",
            "servicos": [_CIN, _FOTO, _JUR],
            "quantidade_cin": AUSENTE,
            "solicitante_nome": "Thiago Ramires Okuda",
            "solicitante_cargo_unidade": Contem("Chefe de Gabinete"),
            "contato": Contem("99654-0098"),
        },
        nota="Bairro 'Jardim Bandeirantes' com nome de município: o município é Londrina; 500 moradores é público, não carteiras.",
    ),
    # ------------------------------------------------------------------ 008
    Caso(
        id="sol-008",
        modulo="solicitacoes",
        formato="eml",
        agora="2026-09-02 10:00",
        texto=_eml(
            "Secretaria de Educação <educacao@mcr.pr.gov.br>",
            _PCPR,
            "Convite - Formatura PROERD",
            "2026-09-01 09:40",
            """
Prezados(as),

A Secretaria Municipal de Educação de Marechal Cândido Rondon convida a
Polícia Civil para a formatura das turmas do programa Polícia Civil nas Escolas,
que acontecerá no dia 25 de setembro de 2026, às 14h, no Centro de Eventos
Werner Wanderer, Rua Espírito Santo, 777, Centro.

Gostaríamos, se possível, da exposição de viaturas antigas e modernas para
as crianças.

Atenciosamente,
Ivone Schwertner Kliemann
Secretária Municipal de Educação
(45) 3284-8800
""",
        ),
        esperado={
            "tipo_evento": UmDe("Evento", "Inauguração/Solenidade"),
            "estado": "PR",
            "municipio": "Marechal Cândido Rondon",
            "local_evento": Contem("Centro de Eventos Werner Wanderer"),
            "endereco": Contem("Rua Espírito Santo, 777"),
            "bairro": "Centro",
            "data_inicio_evento": "2026-09-25",
            "data_fim_evento": "2026-09-25",
            "data_solicitacao": "2026-09-01",
            "servicos": [_VTR],
            "solicitante_nome": "Ivone Schwertner Kliemann",
            "solicitante_cargo_unidade": Contem("Secretária Municipal de Educação"),
            "contato": Contem("3284-8800"),
        },
        nota="Formatura = tipo genérico 'Evento'; município com nome de pessoa (Marechal Cândido Rondon); só exposição de viaturas.",
    ),
    # ------------------------------------------------------------------ 009
    Caso(
        id="sol-009",
        modulo="solicitacoes",
        formato="eml",
        agora="2026-10-13 09:00",
        texto=_eml(
            '"Assistência Social - Cruz Machado" <cras@cruzmachado.pr.gov.br>',
            _PCPR,
            "Re: Re: Fwd: pedido carteira identidade",
            "2026-10-13 08:12",
            """
Bom dia Sr. Adriano,

Conforme conversamos por telefone, confirmo a data: será na próxima
quarta-feira, dia 21, no salão da Igreja Nossa Senhora do Rocio, na
Linha Vitória (interior de Cruz Machado). Estimamos 90 pessoas para fazer a
carteira de identidade, a maioria idosos e agricultores.

Obrigada!

Elaine Terezinha Kuchla
Assistente Social - CRAS Cruz Machado
42 3554-1180 ramal 22

Em sex., 9 de out. de 2026 às 14:03, Adriano Moletta <adriano.moletta@pc.pr.gov.br> escreveu:
> Boa tarde Elaine, a data de 14/10 não será possível. Pode ser dia 21/10?
>
> Em qui., 8 de out. de 2026 às 10:30, CRAS Cruz Machado escreveu:
>> Bom dia, gostaríamos de solicitar o atendimento para confecção de RG no
>> dia 14/10 no interior do município.
""",
        ),
        esperado={
            "estado": "PR",
            "municipio": "Cruz Machado",
            "local_evento": Contem("Igreja Nossa Senhora do Rocio"),
            "data_inicio_evento": "2026-10-21",
            "data_fim_evento": "2026-10-21",
            "data_solicitacao": UmDe("2026-10-08", "2026-10-13"),
            "servicos": [_CIN],
            "quantidade_cin": 90,
            "solicitante_nome": "Elaine Terezinha Kuchla",
            "solicitante_cargo_unidade": Contem("Assistente Social"),
            "contato": Contem("3554-1180"),
        },
        nota="Mensagem citada tem a data antiga (14/10) recusada; vale a nova (quarta, dia 21); 'Cruz Machado' parece nome de pessoa.",
    ),
    # ------------------------------------------------------------------ 010
    Caso(
        id="sol-010",
        modulo="solicitacoes",
        formato="texto",
        agora="2026-09-24 10:00",
        texto="""Bom dia. Gostaria de saber como faço para solicitar a unidade móvel da Polícia Civil
para um evento aqui em Céu Azul. Ainda não temos data definida, estamos
vendo com a prefeitura se vai ser em outubro ou novembro. Seria para fazer
RG das pessoas do interior.

Enviado do meu iPhone
""",
        esperado={
            "estado": "PR",
            "municipio": "Céu Azul",
            "data_inicio_evento": AUSENTE,
            "data_fim_evento": AUSENTE,
            "servicos": [_CIN],
            "unidade_movel": True,
            "solicitante_nome": AUSENTE,
        },
        nota="Sem data definida ('outubro ou novembro') e sem assinatura; 'Enviado do meu iPhone' não é nome; 'Céu Azul' é município.",
    ),
