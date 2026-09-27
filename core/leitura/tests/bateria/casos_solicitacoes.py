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
    # ------------------------------------------------------------------ 011
    Caso(
        id="sol-011",
        modulo="solicitacoes",
        formato="eml",
        agora="2026-09-29 09:10",
        texto=_eml(
            "Conselho Municipal dos Direitos da Mulher <cmdm@cascavel.pr.gov.br>",
            _PCPR,
            "Capacitação - rede de enfrentamento à violência contra a mulher",
            "2026-09-28 15:31",
            """
Prezados,

O Conselho Municipal dos Direitos da Mulher de Cascavel está organizando um
curso de capacitação para a rede de atendimento (CRAS, CREAS, saúde e
conselhos tutelares) e gostaria de contar com uma delegada ou investigadora
da Polícia Civil como instrutora.

O curso será nos dias 20, 21 e 22 de outubro, das 8h às 12h, no Auditório da
ACIC - Av. Carlos Gomes, 1650, Centro, CEP 85801-020.

Serão cerca de 80 participantes.

Grata,

Patrícia Lorenzetti Andrade
Presidente do CMDM Cascavel
(45) 3902-1377 | (45) 99941-2200
""",
            html=True,
        ),
        esperado={
            "tipo_evento": "Capacitação",
            "estado": "PR",
            "municipio": "Cascavel",
            "local_evento": Contem("Auditório da ACIC"),
            "endereco": Contem("Av. Carlos Gomes, 1650"),
            "bairro": "Centro",
            "cep": "85801-020",
            "data_inicio_evento": "2026-10-20",
            "data_fim_evento": "2026-10-22",
            "data_solicitacao": "2026-09-28",
            "servicos": [],
            "quantidade_cin": AUSENTE,
            "solicitante_nome": "Patrícia Lorenzetti Andrade",
            "solicitante_cargo_unidade": Contem("Presidente do CMDM"),
            "contato": UmDe(Contem("3902-1377"), Contem("99941-2200")),
        },
        nota="Multipart com HTML; '20, 21 e 22 de outubro' = três dias; 80 participantes não é CIN; CEP no endereço.",
    ),
    # ------------------------------------------------------------------ 012
    Caso(
        id="sol-012",
        modulo="solicitacoes",
        formato="texto",
        agora="2026-10-26 13:45",
        texto="""De: Vanderlei Grochoski
Enviado em: domingo, 25 de outubro de 2026 21:14
Para: eventos.sociais@pc.pr.gov.br
Assunto: MUTIRAO DA CIDADANIA SAO JOSE DOS PINHAIS

boa noite

a associacao de moradores do borda do campo vai fazer um mutirao da cidadania
aqui em sao jose dos pinhais no sabado, dia 7, e queriamos pedir a equipe da
policia civil p fazer rg e dar orientacao juridica pro pessoal

vai ser na escola municipal papa joao paulo I, rua joinville 2300, bairro borda do campo
comeca as 8h ate umas 14h

vanderlei grochoski
presidente da associacao
41 99187-6620
""",
        esperado={
            "estado": "PR",
            "municipio": "São José dos Pinhais",
            "local_evento": Contem("Papa João Paulo"),
            "endereco": Contem("Rua Joinville 2300"),
            "bairro": "Borda do Campo",
            "data_inicio_evento": "2026-11-07",
            "data_fim_evento": "2026-11-07",
            "data_solicitacao": "2026-10-25",
            "servicos": [_CIN, _JUR],
            "solicitante_nome": "Vanderlei Grochoski",
            "solicitante_cargo_unidade": Contem("Presidente da Associação"),
            "contato": Contem("99187-6620"),
        },
        nota="Sem acento e em minúsculas; 'Rua Joinville' não é o município (SC); 'sábado, dia 7' deduz novembro pelo agora.",
    ),
    # ------------------------------------------------------------------ 013
    Caso(
        id="sol-013",
        modulo="solicitacoes",
        formato="texto",
        agora="2026-10-14 15:00",
        texto="""[14/10/2026 11:02] Kátia Bandeirantes CREAS: Boa tarde, delegado! Tudo bem?
[14/10/2026 11:03] Kátia Bandeirantes CREAS: Aqui em Bandeirantes a gente quer fazer uma roda de conversa com as mulheres atendidas pelo CREAS sobre violência doméstica e medida protetiva
[14/10/2026 11:04] Kátia Bandeirantes CREAS: Pode ser semana que vem na quarta, às 14h?
[14/10/2026 11:05] Kátia Bandeirantes CREAS: Local: CREAS, Rua Frei Rafael Proner, 1100 - Centro
[14/10/2026 11:05] Kátia Bandeirantes CREAS: Deve dar umas 30 mulheres
[14/10/2026 11:07] Kátia Bandeirantes CREAS: Kátia Regina Moraes - coordenadora do CREAS - 43 3542-9010
""",
        esperado={
            "tipo_evento": "Palestra",
            "estado": "PR",
            "municipio": "Bandeirantes",
            "local_evento": Contem("CREAS"),
            "endereco": Contem("Rua Frei Rafael Proner, 1100"),
            "bairro": "Centro",
            "data_inicio_evento": "2026-10-21",
            "data_fim_evento": "2026-10-21",
            "data_solicitacao": "2026-10-14",
            "servicos": [],
            "quantidade_cin": AUSENTE,
            "solicitante_nome": "Kátia Regina Moraes",
            "solicitante_cargo_unidade": Contem("coordenadora do CREAS"),
            "contato": Contem("3542-9010"),
        },
        nota="'Semana que vem na quarta' a partir de quarta 14/10 = 21/10; roda de conversa = palestra; 30 mulheres não é CIN.",
    ),
    # ------------------------------------------------------------------ 014
    Caso(
        id="sol-014",
        modulo="solicitacoes",
        formato="eml",
        agora="2026-09-10 10:30",
        texto=_eml(
            "Organização Expo Segurança Sul <contato@exposegurancasul.com.br>",
            _PCPR,
            _q("Convite expositor – Expo Segurança Sul 2026 – Joinville/SC"),
            "2026-09-09 10:02",
            """
Prezados senhores,

Temos a satisfação de convidar a Polícia Civil do Paraná a participar como
expositora da Expo Segurança Sul 2026, feira de segurança pública e privada
que acontece de 12 a 14 de novembro de 2026 no Complexo Expoville,
Rua XV de Novembro, 4315 - Glória, Joinville/SC.

Reservamos à PCPR uma área externa de 300 m² para exposição de viaturas
antigas e modernas. Público esperado: 15 mil visitantes.

Favor confirmar até 15/10.

Atenciosamente,
Ricardo Hoffmann Schütz
Diretor Comercial - Expo Segurança Sul
+55 47 3433-2020
""",
        ),
        esperado={
            "tipo_evento": "Feira",
            "estado": "SC",
            "municipio": "Joinville",
            "local_evento": Contem("Expoville"),
            "endereco": Contem("Rua XV de Novembro, 4315"),
            "bairro": "Glória",
            "data_inicio_evento": "2026-11-12",
            "data_fim_evento": "2026-11-14",
            "data_solicitacao": "2026-09-09",
            "servicos": [_VTR],
            "quantidade_cin": AUSENTE,
            "solicitante_nome": "Ricardo Hoffmann Schütz",
            "solicitante_cargo_unidade": Contem("Diretor Comercial"),
            "contato": Contem("3433-2020"),
        },
        nota="Evento em SC; 'Rua XV de Novembro' não é data; prazo 15/10 não é evento; 15 mil visitantes não é CIN.",
    ),
    # ------------------------------------------------------------------ 015
    Caso(
        id="sol-015",
        modulo="solicitacoes",
        formato="texto",
        agora="2026-09-30 08:15",
        texto="""SOLICITACAO DE RG ITINERANTE - MUNICIPIO DE MARILUZ

SOLICITAMOS A EQUIPE DE IDENTIFICACAO DA POLICIA CIVIL PARA ATENDIMENTO NO DIA
20-10-2026 NO GINASIO MUNICIPAL DE ESPORTES (R. DAS FLORES, S/N, VILA NOVA),
DAS 8:00 AS 16:00. PREVISAO DE 200 CARTEIRAS. COLETA DE DIGITAIS E FOTO NO LOCAL.

RESPONSAVEL: SEBASTIAO APARECIDO DOS SANTOS
SECRETARIO MUNICIPAL DE ADMINISTRACAO
FONE (44) 3531-1122
""",
        esperado={
            "estado": "PR",
            "municipio": "Mariluz",
            "local_evento": Contem("Ginásio Municipal de Esportes"),
            "endereco": Contem("R. das Flores, s/n"),
            "bairro": "Vila Nova",
            "data_inicio_evento": "2026-10-20",
            "data_fim_evento": "2026-10-20",
            "servicos": [_CIN, _DIG, _FOTO],
            "quantidade_cin": 200,
            "solicitante_nome": "Sebastião Aparecido dos Santos",
            "solicitante_cargo_unidade": Contem("Secretário Municipal de Administração"),
            "contato": Contem("3531-1122"),
        },
        nota="Tudo em CAIXA ALTA sem acento; data com hífen 'dd-mm-aaaa'; endereço entre parênteses com s/n.",
    ),
    # ------------------------------------------------------------------ 016
    Caso(
        id="sol-016",
        modulo="solicitacoes",
        formato="eml",
        agora="2026-10-02 11:20",
        texto=_eml(
            "=?utf-8?q?Coordena=C3=A7=C3=A3o_Paran=C3=A1_em_A=C3=A7=C3=A3o?= <paranaemacao@seju.pr.gov.br>",
            _PCPR,
            _q("Paraná em Ação – Francisco Beltrão – 13 e 14/11"),
            "2026-10-01 18:02",
            """
Prezada equipe da PCPR,

Encaminhamos a programação da próxima edição do Paraná em Ação, que será
realizada em Francisco Beltrão nos dias 13 e 14 de novembro, no Parque de
Exposições Jaime Canet Júnior (Rodovia PR-180, km 5).

Contamos com a unidade móvel do Instituto de Identificação para emissão de
CIN e fotos, com previsão de 800 atendimentos nos dois dias.

Lembramos que na edição de Dois Vizinhos (18 e 19/09) foram emitidas 640
carteiras.

Atenciosamente,

Fernanda Scheffer Guimarães
Coordenadora Executiva - Paraná em Ação
Secretaria de Estado da Justiça e Cidadania
Rua Jacy Loureiro de Campos, s/n - Palácio das Araucárias - Curitiba/PR
(41) 3221-7300
""",
        ),
        esperado={
            "tipo_evento": "Paraná em Ação",
            "estado": "PR",
            "municipio": "Francisco Beltrão",
            "local_evento": Contem("Parque de Exposições Jaime Canet"),
            "endereco": Contem("Rodovia PR-180, km 5"),
            "data_inicio_evento": "2026-11-13",
            "data_fim_evento": "2026-11-14",
            "data_solicitacao": "2026-10-01",
            "servicos": [_CIN, _FOTO],
            "quantidade_cin": 800,
            "unidade_movel": True,
            "solicitante_nome": "Fernanda Scheffer Guimarães",
            "solicitante_cargo_unidade": Contem("Coordenadora Executiva"),
            "contato": Contem("3221-7300"),
        },
        nota="Edição anterior em Dois Vizinhos (18 e 19/09, 640 carteiras) é armadilha; endereço da assinatura é Curitiba; endereço do evento é rodovia com km.",
    ),
    # ------------------------------------------------------------------ 017
    Caso(
        id="sol-017",
        modulo="solicitacoes",
        formato="texto",
        agora="2026-12-10 10:00",
        texto="""---------- Forwarded message ---------
De: Secretaria de Turismo de Guaratuba <turismo@guaratuba.pr.gov.br>
Date: qua., 9 de dez. de 2026 às 16:48
Subject: Unidade móvel na temporada - virada do ano
To: Gabinete DG <gabinete.dg@pc.pr.gov.br>


Senhores,

Solicitamos a permanência da unidade móvel de identificação da PCPR na
Praça dos Namorados, Av. Atlântica, Centro de Guaratuba, no período de
28 de dezembro a 3 de janeiro, para emissão de carteiras de identidade aos
veranistas e moradores, no horário das 10h às 18h.

Atenciosamente,
Márcio Luiz Pacheco Filho
Secretário Municipal de Turismo
(41) 3472-8500
""",
        esperado={
            "estado": "PR",
            "municipio": "Guaratuba",
            "local_evento": Contem("Praça dos Namorados"),
            "endereco": Contem("Av. Atlântica"),
            "bairro": "Centro",
            "data_inicio_evento": "2026-12-28",
            "data_fim_evento": "2027-01-03",
            "data_solicitacao": "2026-12-09",
            "servicos": [_CIN],
            "unidade_movel": True,
            "solicitante_nome": "Márcio Luiz Pacheco Filho",
            "solicitante_cargo_unidade": Contem("Secretário Municipal de Turismo"),
            "contato": Contem("3472-8500"),
        },
        nota="Período que vira o ano: 3 de janeiro é 2027; encaminhado pelo Gmail.",
    ),
    # ------------------------------------------------------------------ 018
    Caso(
        id="sol-018",
        modulo="solicitacoes",
        formato="eml",
        agora="2026-10-02 16:00",
        texto=_eml(
            "Guarda Municipal Pato Branco <gm@patobranco.pr.gov.br>",
            _PCPR,
            "Curso preservação de local de crime - GM Pato Branco",
            "2026-10-02 14:37",
            """
Senhor Delegado,

Solicitamos instrutor da Polícia Civil para ministrar capacitação sobre
preservação de local de crime aos guardas municipais, na data de 20.10.26,
das 13h30 às 17h30, no auditório da UTFPR (Via do Conhecimento, km 1,
Fraron).

Turma de 45 guardas.

Insp. Gilmar Roberto Zanella
Comandante da Guarda Municipal de Pato Branco
46 3220-1000
""",
        ),
        esperado={
            "tipo_evento": "Capacitação",
            "estado": "PR",
            "municipio": "Pato Branco",
            "local_evento": Contem("UTFPR"),
            "endereco": Contem("Via do Conhecimento, km 1"),
            "bairro": "Fraron",
            "data_inicio_evento": "2026-10-20",
            "data_fim_evento": "2026-10-20",
            "data_solicitacao": "2026-10-02",
            "servicos": [],
            "quantidade_cin": AUSENTE,
            "solicitante_nome": "Gilmar Roberto Zanella",
            "solicitante_cargo_unidade": Contem("Comandante da Guarda Municipal"),
            "contato": Contem("3220-1000"),
        },
        nota="Data 'dd.mm.aa' (20.10.26); horário 13h30 não é data; 45 guardas não é CIN.",
    ),
    # ------------------------------------------------------------------ 019
    Caso(
        id="sol-019",
        modulo="solicitacoes",
        formato="eml",
        agora="2026-10-06 09:00",
        texto=_eml(
            "Associação Amigos do Bem <contato@amigosdobem-pr.org.br>",
            _PCPR,
            "Pedido de apoio - Domingo Solidário",
            "2026-10-05 20:30",
            """
Olá!

Somos uma associação beneficente e vamos realizar o Domingo Solidário no
Parque Municipal de Quatro Barras, dia 8 de nov., das 9h às 15h, com
distribuição de agasalhos, corte de cabelo e serviços de cidadania.

Gostaríamos muito de ter a emissão de RG e o atendimento social da Polícia Civil.

Um abraço,

Beatriz Ogliari Campos
Voluntária - Associação Amigos do Bem
Sede: Rua Marechal Deodoro, 500, sala 12 - Centro - Curitiba/PR - CEP 80010-010
(41) 3014-2525
""",
        ),
        esperado={
            "estado": "PR",
            "municipio": "Quatro Barras",
            "local_evento": Contem("Parque Municipal"),
            "endereco": AUSENTE,
            "bairro": AUSENTE,
            "cep": AUSENTE,
            "data_inicio_evento": "2026-11-08",
            "data_fim_evento": "2026-11-08",
            "data_solicitacao": "2026-10-05",
            "servicos": [_CIN, _SOCIAL],
            "solicitante_nome": "Beatriz Ogliari Campos",
            "solicitante_cargo_unidade": Contem("Associação Amigos do Bem"),
            "contato": Contem("3014-2525"),
        },
        nota="Endereço, bairro e CEP só da sede (Curitiba) na assinatura: não são do evento; 'dia 8 de nov.' abreviado.",
    ),
    # ------------------------------------------------------------------ 020
    Caso(
        id="sol-020",
        modulo="solicitacoes",
        formato="texto",
        agora="2026-08-11 10:00",
        texto="""De: Gabinete - Prefeitura de Fazenda Rio Grande <gabinete@fazendariogrande.pr.gov.br>
Enviado em: segunda-feira, 10 de agosto de 2026 17:02
Para: Protocolo PCPR
Assunto: Ofício 088/2026 - Solicitação de unidade móvel

Fazenda Rio Grande, 7 de agosto de 2026.

OFÍCIO Nº 088/2026

Senhor Delegado-Geral,

Vimos solicitar a disponibilização da unidade móvel de identificação para
atendimento à população de Fazenda Rio Grande, em data a ser definida em
conjunto com essa instituição, preferencialmente no segundo semestre.

Solicitamos resposta até 20/08/2026.

Respeitosamente,

ANTÔNIO CARLOS VIDAL
Prefeito Municipal
""",
        esperado={
            "estado": "PR",
            "municipio": "Fazenda Rio Grande",
            "data_inicio_evento": AUSENTE,
            "data_fim_evento": AUSENTE,
            "data_solicitacao": UmDe("2026-08-07", "2026-08-10"),
            "unidade_movel": True,
            "solicitante_nome": "Antônio Carlos Vidal",
            "solicitante_cargo_unidade": Contem("Prefeito"),
            "local_evento": AUSENTE,
        },
        nota="Nenhuma data de evento: data do ofício, do envio e prazo 20/08 são armadilhas; município composto com 'Rio Grande'.",
    ),
    # ------------------------------------------------------------------ 021
    Caso(
        id="sol-021",
        modulo="solicitacoes",
        formato="eml",
        agora="2026-09-20 18:00",
        texto=_eml(
            "Secretaria da Criança de Maringá <semcri@maringa.pr.gov.br>",
            _PCPR,
            "Festa das Crianças - Conjunto Requião - apoio PCPR",
            "2026-09-18 10:44",
            """
Bom dia!

A Secretaria Municipal da Criança de Maringá vai realizar a Festa das
Crianças do Conjunto Requião no dia 12 de outubro, segunda-feira, feriado,
na Praça do Conjunto Requião (Rua Pioneiro Antônio Ruiz Saldanha, s/n).

Gostaríamos da exposição de viaturas antigas e modernas e, se possível, da
emissão da carteira de identidade para as crianças - estimamos cerca de 100
carteiras infantis.

Abraços,
Juliana Tanaka Belotto
Gerente de Eventos
Secretaria Municipal da Criança
(44) 3221-6400 / (44) 99722-1188
""",
            html=True,
        ),
        esperado={
            "estado": "PR",
            "municipio": "Maringá",
            "local_evento": Contem("Praça do Conjunto Requião"),
            "endereco": Contem("Rua Pioneiro Antônio Ruiz Saldanha, s/n"),
            "data_inicio_evento": "2026-10-12",
            "data_fim_evento": "2026-10-12",
            "data_solicitacao": "2026-09-18",
            "servicos": [_VTR, _CIN],
            "quantidade_cin": 100,
            "solicitante_nome": "Juliana Tanaka Belotto",
            "solicitante_cargo_unidade": Contem("Gerente de Eventos"),
            "contato": UmDe(Contem("3221-6400"), Contem("99722-1188")),
        },
        nota="Data por extenso sem ano com dia da semana; tipo genérico (festa) fica fora; 'Conjunto Requião' é bairro, não cidade.",
    ),
    # ------------------------------------------------------------------ 022
    Caso(
        id="sol-022",
        modulo="solicitacoes",
        formato="texto",
        agora="2026-10-15 17:00",
        texto="""[15/10/2026 16:38] Dona Lurdes Assoc. Guaíra: boa tarde doutor desculpa incomodar
[15/10/2026 16:39] Dona Lurdes Assoc. Guaíra: amanhã tem a ação social aqui no bairro Guaíra em Curitiba e o pessoal da prefeitura falou pra pedir pra vcs
[15/10/2026 16:40] Dona Lurdes Assoc. Guaíra: é na associação de moradores da vila guaíra, rua brigadeiro franco 3800
[15/10/2026 16:40] Dona Lurdes Assoc. Guaíra: é pra fazer RG e tirar foto
[15/10/2026 16:41] Dona Lurdes Assoc. Guaíra: das 9 as 13
[15/10/2026 16:44] Dona Lurdes Assoc. Guaíra: Maria de Lourdes Pscheidt, presidente da associação. 41 98845-2031
""",
        esperado={
            "estado": "PR",
            "municipio": "Curitiba",
            "local_evento": Contem("Associação de Moradores da Vila Guaíra"),
            "endereco": Contem("Rua Brigadeiro Franco 3800"),
            "bairro": "Guaíra",
            "data_inicio_evento": "2026-10-16",
            "data_fim_evento": "2026-10-16",
            "data_solicitacao": "2026-10-15",
            "servicos": [_CIN, _FOTO],
            "solicitante_nome": "Maria de Lourdes Pscheidt",
            "solicitante_cargo_unidade": Contem("presidente da associação"),
            "contato": Contem("98845-2031"),
        },
        nota="Bairro 'Guaíra' tem nome de município do PR: o evento é em Curitiba; 'amanhã' a partir do agora; 'das 9 as 13' é horário.",
    ),
    # ------------------------------------------------------------------ 023
    Caso(
        id="sol-023",
        modulo="solicitacoes",
        formato="eml",
        agora="2026-10-21 10:00",
        texto=_eml(
            "SMAS Campo Largo <smas@campolargo.pr.gov.br>",
            _PCPR,
            "OFICIO 331/2026 - SMAS - Campo Largo Cidadã",
            "2026-10-20 15:12",
            """
Segue o ofício abaixo, o original vai anexo assinado.

---------------------------------------------------------------
PREFEITURA MUNICIPAL DE CAMPO LARGO
SECRETARIA MUNICIPAL DE ASSISTÊNCIA SOCIAL

Campo Largo, 19 de outubro de 2026.

Ofício nº 331/2026 - SMAS

Assunto: ação "Campo Largo Cidadã"

Senhor Diretor,

Solicitamos a participação do Instituto de Identificação na ação
"Campo Largo Cidadã", com data marcada para 14 11 2026, das 8h às 17h, na
Escola Municipal Antonio Kaminski - Rua Rui Barbosa, 1300 - Vila Bancária.

Serviços solicitados: emissão de carteira de identidade (CIN), coleta de
digitais, fotografia e atendimento social.

A ação deve reunir aproximadamente 1.000 pessoas de diversos bairros.

Atenciosamente,

Rosimeri Aparecida Kloster
Secretária Municipal de Assistência Social
Fone: (41) 3291-5150
---------------------------------------------------------------
""",
        ),
        esperado={
            "estado": "PR",
            "municipio": "Campo Largo",
            "local_evento": Contem("Escola Municipal Antonio Kaminski"),
            "endereco": Contem("Rua Rui Barbosa, 1300"),
            "bairro": "Vila Bancária",
            "data_inicio_evento": "2026-11-14",
            "data_fim_evento": "2026-11-14",
            "data_solicitacao": UmDe("2026-10-19", "2026-10-20"),
            "servicos": [_CIN, _DIG, _FOTO, _SOCIAL],
            "quantidade_cin": AUSENTE,
            "solicitante_nome": "Rosimeri Aparecida Kloster",
            "solicitante_cargo_unidade": Contem("Secretária Municipal de Assistência Social"),
            "contato": Contem("3291-5150"),
        },
        nota="Data com espaços '14 11 2026'; ofício colado com data no topo; 1.000 pessoas é público; quatro serviços.",
    ),
    # ------------------------------------------------------------------ 024
    Caso(
        id="sol-024",
        modulo="solicitacoes",
        formato="eml",
        agora="2026-10-15 09:30",
        texto=_eml(
            "Comissão Expovale <comissao@expovale.com.br>",
            _PCPR,
            "Feira Expovale 2026 - União da Vitória",
            "2026-10-14 16:20",
            """
Prezados,

A Comissão Organizadora da Expovale 2026 - feira de negócios do Vale do
Iguaçu - convida a Polícia Civil do Paraná para participar do evento, de
3 a 5/12, no Pavilhão de Eventos da Beira-Rio, Av. Manoel Ribas, 120 - Centro,
em União da Vitória.

Gostaríamos de um estande com emissão de carteira de identidade e a exposição
de viaturas antigas e modernas.

Atenciosamente,

Rodrigo Wiecheteck
Presidente da Comissão Organizadora
Rua Marechal Deodoro, 44 - Centro - Porto União/SC
(42) 3522-9090
""",
        ),
        esperado={
            "tipo_evento": "Feira",
            "estado": "PR",
            "municipio": "União da Vitória",
            "local_evento": Contem("Pavilhão de Eventos da Beira-Rio"),
            "endereco": Contem("Av. Manoel Ribas, 120"),
            "bairro": "Centro",
            "data_inicio_evento": "2026-12-03",
            "data_fim_evento": "2026-12-05",
            "data_solicitacao": "2026-10-14",
            "servicos": [_CIN, _VTR],
            "solicitante_nome": "Rodrigo Wiecheteck",
            "solicitante_cargo_unidade": Contem("Presidente da Comissão Organizadora"),
            "contato": Contem("3522-9090"),
        },
        nota="Assinatura em Porto União/SC (cidade gêmea); o evento é em União da Vitória/PR; intervalo 'de 3 a 5/12'.",
    ),
    # ------------------------------------------------------------------ 025
    Caso(
        id="sol-025",
        modulo="solicitacoes",
        formato="texto",
        agora="2026-10-08 14:00",
        texto="""oi bom dia, aqui é da paroquia sao jose de rio negro, a gente vai fazer uma
acao social no dia 30 no pavilhao da paroquia (rua dr vicente machado 120) e queria
saber se a policia civil pode vir fazer carteira de identidade pros idosos, acho q
uns 60. meu nome é padre Leocádio Wisniewski, telefone 47 3645-1020
obrigado e fiquem com Deus
""",
        esperado={
            "estado": "PR",
            "municipio": "Rio Negro",
            "local_evento": Contem("Pavilhão da Paróquia"),
            "endereco": Contem("Vicente Machado 120"),
            "data_inicio_evento": "2026-10-30",
            "data_fim_evento": "2026-10-30",
            "servicos": [_CIN],
            "quantidade_cin": 60,
            "solicitante_nome": Contem("Leocádio Wisniewski"),
            "contato": Contem("3645-1020"),
        },
        nota="Texto corrido sem pontuação; 'dia 30' só com o dia (outubro pelo agora); DDD 47 não faz o evento ser em SC.",
    ),
    # ------------------------------------------------------------------ 026
    Caso(
        id="sol-026",
        modulo="solicitacoes",
        formato="eml",
        agora="2026-10-19 11:00",
        texto=_eml(
            "Cerimonial - Prefeitura de Toledo <cerimonial@toledo.pr.gov.br>",
            _PCPR,
            _q("Convite – Inauguração da Casa da Mulher Toledana"),
            "2026-10-16 09:15",
            """
O Prefeito Municipal de Toledo/PR tem a honra de convidar Vossa Senhoria
para a solenidade de inauguração da Casa da Mulher Toledana, que contará
com sala da Delegacia da Mulher.

Data: sexta-feira, 6 de novembro de 2026
Horário: 10h
Local: Casa da Mulher Toledana
Rua Barão do Rio Branco, 2020 - Jardim La Salle

Solicitamos, se possível, a presença de representante da Polícia Civil
para compor a mesa de autoridades.

Confirmação de presença até 30/10 pelo telefone (45) 3055-8801, com Sílvia.

Cerimonial - Gabinete do Prefeito
Sílvia Bortolini Heck - Chefe do Cerimonial
""",
        ),
        esperado={
            "tipo_evento": "Inauguração/Solenidade",
            "estado": "PR",
            "municipio": "Toledo",
            "local_evento": Contem("Casa da Mulher Toledana"),
            "endereco": Contem("Rua Barão do Rio Branco, 2020"),
            "bairro": "Jardim La Salle",
            "data_inicio_evento": "2026-11-06",
            "data_fim_evento": "2026-11-06",
            "data_solicitacao": "2026-10-16",
            "servicos": [],
            "solicitante_nome": "Sílvia Bortolini Heck",
            "solicitante_cargo_unidade": Contem("Chefe do Cerimonial"),
            "contato": Contem("3055-8801"),
        },
        nota="'Toledo/PR' colado com a UF; confirmação até 30/10 é prazo; convite de solenidade sem serviços.",
    ),
    # ------------------------------------------------------------------ 027
    Caso(
        id="sol-027",
        modulo="solicitacoes",
        formato="texto",
        agora="2026-10-27 10:40",
        texto="""De: Direção EM Mário de Andrade <em.mariodeandrade@apucarana.pr.gov.br>
Enviado em: terça-feira, 27 de outubro de 2026 07:58
Para: eventos.sociais@pc.pr.gov.br
Cc: nucleo.educacao@apucarana.pr.gov.br
Assunto: Palestra prevenção às drogas - 5º ano

Bom dia,

Solicitamos uma palestra sobre prevenção ao uso de drogas para as turmas de
5º ano da Escola Municipal Mário de Andrade, na terça-feira, 17 de novembro
de 2026, das 9h às 11h.

Endereço: Av. Minas Gerais, 1234 - Jardim Ponta Grossa - Apucarana/PR.

Att.,
Rosana Ferreira Lima
Diretora
(43) 3162-4400

AVISO DE CONFIDENCIALIDADE: Esta mensagem e seus anexos são destinados
exclusivamente ao(s) destinatário(s) e podem conter informações confidenciais
protegidas por lei. Se você a recebeu por engano, notifique o remetente e
apague-a. Prefeitura Municipal de Apucarana - Rua Ponta Grossa, 2100 - Centro.
""",
        esperado={
            "tipo_evento": "Palestra",
            "estado": "PR",
            "municipio": "Apucarana",
            "local_evento": Contem("Escola Municipal Mário de Andrade"),
            "endereco": Contem("Av. Minas Gerais, 1234"),
            "bairro": "Jardim Ponta Grossa",
            "data_inicio_evento": "2026-11-17",
            "data_fim_evento": "2026-11-17",
            "data_solicitacao": "2026-10-27",
            "servicos": [],
            "solicitante_nome": "Rosana Ferreira Lima",
            "solicitante_cargo_unidade": Contem("Diretora"),
            "contato": Contem("3162-4400"),
        },
        nota="Bairro 'Jardim Ponta Grossa' e 'Rua Ponta Grossa' no rodapé: o município é Apucarana; aviso de confidencialidade longo.",
    ),
    # ------------------------------------------------------------------ 028
    Caso(
        id="sol-028",
        modulo="solicitacoes",
        formato="eml",
        agora="2026-10-28 09:00",
        texto=_eml(
            "Justiça no Bairro <justicanobairro@tjpr.jus.br>",
            _PCPR,
            "Justiça no Bairro Tatuquara - 20 e 21 de novembro",
            "2026-10-27 14:00",
            """
Prezados parceiros,

A próxima edição do Justiça no Bairro será no Tatuquara, em Curitiba, nos
dias 20 e 21 de novembro (sexta e sábado), na Rua da Cidadania do Tatuquara,
Rua Olívio Carlos Pinto, 1350.

Pedimos à PCPR a emissão da carteira de identidade, com coleta de digitais e
foto, estimando 500 carteiras. A orientação jurídica ficará por conta da
Defensoria Pública.

Obrigada,
Heloísa Brandalise Tomczak
Assessora - Coordenadoria do Justiça no Bairro - TJPR
(41) 3200-5871
""",
        ),
        esperado={
            "tipo_evento": "Justiça no Bairro",
            "estado": "PR",
            "municipio": "Curitiba",
            "local_evento": Contem("Rua da Cidadania do Tatuquara"),
            "endereco": Contem("Rua Olívio Carlos Pinto, 1350"),
            "bairro": "Tatuquara",
            "data_inicio_evento": "2026-11-20",
            "data_fim_evento": "2026-11-21",
            "data_solicitacao": "2026-10-27",
            "servicos": [_CIN, _DIG, _FOTO],
            "quantidade_cin": 500,
            "solicitante_nome": "Heloísa Brandalise Tomczak",
            "solicitante_cargo_unidade": Contem("Justiça no Bairro"),
            "contato": Contem("3200-5871"),
        },
        nota="Orientação jurídica citada é da Defensoria, não pedida à PCPR; 'Rua da Cidadania' é o nome do lugar e também começa com 'Rua'.",
    ),
    # ------------------------------------------------------------------ 029
    Caso(
        id="sol-029",
        modulo="solicitacoes",
        formato="eml",
        agora="2026-09-18 16:00",
        texto=_eml(
            "Encontro Sul-Brasileiro de Identificação <organizacao@esbi2026.org.br>",
            _PCPR,
            _q("Convite para palestra – Encontro Sul-Brasileiro de Identificação – Itajaí"),
            "2026-09-17 11:11",
            """
Prezado(a) Diretor(a),

Convidamos o Instituto de Identificação do Paraná a proferir palestra sobre
a implantação da Carteira de Identidade Nacional no Paraná durante o
IV Encontro Sul-Brasileiro de Identificação, que ocorrerá nos dias 26 e 27
de novembro de 2026 no Centreventos de Itajaí (Rua Heitor Liberato, 1000 -
Vila Operária, Itajaí - SC).

A palestra teria 40 minutos, no dia 26, às 15h.

Cordialmente,
Prof. Dr. Anselmo Duarte Krieger
Coordenador Científico
(47) 3348-7711
""",
            html=True,
        ),
        esperado={
            "tipo_evento": "Palestra",
            "estado": "SC",
            "municipio": "Itajaí",
            "local_evento": Contem("Centreventos"),
            "endereco": Contem("Rua Heitor Liberato, 1000"),
            "bairro": "Vila Operária",
            "data_inicio_evento": "2026-11-26",
            "data_fim_evento": UmDe("2026-11-26", "2026-11-27"),
            "data_solicitacao": "2026-09-17",
            "servicos": [],
            "quantidade_cin": AUSENTE,
            "solicitante_nome": "Anselmo Duarte Krieger",
            "solicitante_cargo_unidade": Contem("Coordenador Científico"),
            "contato": Contem("3348-7711"),
        },
        nota="SC; 'Carteira de Identidade Nacional' é o tema da palestra, não serviço pedido; palestra só no dia 26 de um encontro de dois dias.",
    ),
    # ------------------------------------------------------------------ 030
    Caso(
        id="sol-030",
        modulo="solicitacoes",
        formato="texto",
        agora="2026-11-10 09:30",
        texto="""Prezados da Polícia Civil,

Venho mais uma vez, em nome da Comissão de Moradores do Jardim Cachoeira, em
Almirante Tamandaré, pedir o apoio de vocês. Para quem não conhece o nosso
histórico: começamos o projeto "Cachoeira Cidadã" em março de 2025, com uma
primeira ação na igreja do bairro, que teve apenas atendimento de saúde. Em
10/04/2026 fizemos a segunda edição, já com a presença da unidade móvel da
PCPR, e foram feitas 94 carteiras de identidade, o que foi um marco para a
comunidade, porque muitos moradores nunca tinham tido documento. Depois disso
a prefeitura cedeu o espaço do Centro da Juventude, que é maior e coberto.

A terceira edição será no dia 5 de dezembro, sábado, das 9h às 16h, no Centro
da Juventude do Cachoeira, na Rua Tenente Tito Teixeira de Castro, 900.
Queremos de novo a unidade móvel com emissão de RG, e desta vez também o
atendimento social, porque tem muita família precisando de encaminhamento.
Esperamos em torno de 150 carteiras.

Agradeço desde já.

Edvaldo Nunes Prestes
Coordenador da Comissão de Moradores do Jardim Cachoeira
Telefone/WhatsApp: 41988887777
""",
        esperado={
            "estado": "PR",
            "municipio": "Almirante Tamandaré",
            "local_evento": Contem("Centro da Juventude"),
            "endereco": Contem("Rua Tenente Tito Teixeira de Castro, 900"),
            "bairro": UmDe("Cachoeira", "Jardim Cachoeira"),
            "data_inicio_evento": "2026-12-05",
            "data_fim_evento": "2026-12-05",
            "servicos": [_CIN, _SOCIAL],
            "quantidade_cin": 150,
            "unidade_movel": True,
            "solicitante_nome": "Edvaldo Nunes Prestes",
            "solicitante_cargo_unidade": Contem("Coordenador da Comissão de Moradores"),
            "contato": UmDe(Contem("41988887777"), Contem("98888-7777")),
        },
        nota="Histórico longo com edições anteriores (março/2025, 10/04/2026, 94 carteiras); 'Castro' no nome da rua não é o município; telefone sem separadores.",
    ),
    # ------------------------------------------------------------------ 031
    Caso(
        id="sol-031",
        modulo="solicitacoes",
        formato="eml",
        agora="2026-09-22 14:00",
        texto=_eml(
            "Sindicato Trabalhadores Alimentação Chapecó <secretaria@sintiachapeco.org.br>",
            _PCPR,
            "Mutirão de documentos para trabalhadores paranaenses",
            "2026-09-21 10:10",
            """
Senhores,

Grande parte dos trabalhadores dos frigoríficos da região de Chapecó são
paranaenses e estão com a identidade vencida ou danificada. O Sindicato
gostaria de saber se a Polícia Civil do Paraná pode realizar um mutirão de
emissão da CIN aqui em Chapecó (SC), no dia 20 de outubro, na sede do
Sindicato: Rua Marechal Floriano Peixoto, 555-E, Centro.

Previsão de 150 carteiras.

Atenciosamente,
Neusa Maria Dal Pizzol
Secretária-Geral
(49) 3322-4040
""",
        ),
        esperado={
            "estado": "SC",
            "municipio": "Chapecó",
            "local_evento": Contem("Sindicato"),
            "endereco": Contem("Rua Marechal Floriano Peixoto, 555-E"),
            "bairro": "Centro",
            "data_inicio_evento": "2026-10-20",
            "data_fim_evento": "2026-10-20",
            "data_solicitacao": "2026-09-21",
            "servicos": [_CIN],
            "quantidade_cin": 150,
            "solicitante_nome": "Neusa Maria Dal Pizzol",
            "solicitante_cargo_unidade": Contem("Secretária-Geral"),
            "contato": Contem("3322-4040"),
        },
        nota="Evento em SC pedido à PCPR; 'paranaenses' não faz o estado ser PR; número de endereço com letra (555-E).",
    ),
    # ------------------------------------------------------------------ 032
    Caso(
        id="sol-032",
        modulo="solicitacoes",
        formato="texto",
        agora="2026-09-16 10:00",
        texto="""---------- Forwarded message ---------
De: Delegacia de Irati <dp.irati@pc.pr.gov.br>
Date: ter., 15 de set. de 2026 às 17:30
Subject: Fwd: Semana do Idoso - pedido de identificação
To: Eventos Sociais <eventos.sociais@pc.pr.gov.br>


Encaminho para providências. Delegado Evandro.

---------- Forwarded message ---------
De: Conselho Municipal do Idoso <cmi@irati.pr.gov.br>
Date: seg., 14 de set. de 2026 às 09:02
Subject: Semana do Idoso - pedido de identificação
To: <dp.irati@pc.pr.gov.br>


Prezado Delegado,

Na Semana do Idoso, o Conselho Municipal do Idoso de Irati/PR vai realizar um
dia de cidadania em 01/10/2026 (quinta-feira), no Centro de Convivência do
Idoso, Rua Coronel Emílio Gomes, 318 - Centro. Solicitamos a emissão de
carteira de identidade e atendimento social para os idosos.

Atenciosamente,
Lindamir Gembarowski
Presidente do Conselho Municipal do Idoso
(42) 3907-3120
""",
        esperado={
            "estado": "PR",
            "municipio": "Irati",
            "local_evento": Contem("Centro de Convivência do Idoso"),
            "endereco": Contem("Rua Coronel Emílio Gomes, 318"),
            "bairro": "Centro",
            "data_inicio_evento": "2026-10-01",
            "data_fim_evento": "2026-10-01",
            "data_solicitacao": UmDe("2026-09-14", "2026-09-15"),
            "servicos": [_CIN, _SOCIAL],
            "solicitante_nome": "Lindamir Gembarowski",
            "solicitante_cargo_unidade": Contem("Presidente do Conselho Municipal do Idoso"),
            "contato": Contem("3907-3120"),
        },
        nota="Encaminhado duas vezes: o solicitante é o Conselho, não o delegado que encaminhou; Irati existe no PR e em SC ('Irati/PR').",
    ),
    # ------------------------------------------------------------------ 033
    Caso(
        id="sol-033",
        modulo="solicitacoes",
        formato="eml",
        agora="2026-11-10 15:00",
        texto=_eml(
            "Centro Acadêmico de Direito <cadireito.cm@unespar.edu.br>",
            _PCPR,
            "Palestra - Semana Jurídica",
            "2026-11-10 12:47",
            """
Boa tarde!

O Centro Acadêmico de Direito da Unespar - Campus de Campo Mourão gostaria de
convidar um delegado da Polícia Civil para a palestra de encerramento da
Semana Jurídica, na próxima sexta-feira, às 19h30, no Auditório da Unespar
(Av. Comendador Norberto Marcondes, 733 - Centro).

Tema sugerido: investigação de crimes cibernéticos.

Obrigado!
Lucas Henrique Vieira Sato
Presidente do CA de Direito
44 99130-5577
""",
        ),
        esperado={
            "tipo_evento": "Palestra",
            "estado": "PR",
            "municipio": "Campo Mourão",
            "local_evento": Contem("Auditório da Unespar"),
            "endereco": Contem("Av. Comendador Norberto Marcondes, 733"),
            "bairro": "Centro",
            "data_inicio_evento": UmDe("2026-11-13", "2026-11-20"),
            "data_fim_evento": UmDe("2026-11-13", "2026-11-20"),
            "data_solicitacao": "2026-11-10",
            "servicos": [],
            "solicitante_nome": "Lucas Henrique Vieira Sato",
            "solicitante_cargo_unidade": Contem("Presidente do CA de Direito"),
            "contato": Contem("99130-5577"),
        },
        nota="'Próxima sexta-feira' escrita numa terça: 13/11 (a que vem) ou 20/11 — as duas leituras valem; 19h30 é horário.",
    ),
    # ------------------------------------------------------------------ 034
    Caso(
        id="sol-034",
        modulo="solicitacoes",
        formato="texto",
        agora="2026-10-30 10:00",
        texto="""[29/10/2026 14:02] Ana Paula SEMAS Paranaguá: Pessoal, a ação de cidadania na Ilha dos Valadares vai ser dia 14/11
[29/10/2026 14:05] Ana Paula SEMAS Paranaguá: no Ginásio da Ilha, Rua Principal, 800
[29/10/2026 14:30] Jorge Coord. SEMAS: Ana, mudou! A secretária pediu pra passar pro dia 21/11 por causa da maré e da balsa
[29/10/2026 14:31] Ana Paula SEMAS Paranaguá: Ah ok, então fica 21/11 mesmo, sábado
[29/10/2026 14:33] Ana Paula SEMAS Paranaguá: Polícia Civil, conseguem levar a emissão de RG e as fotos? Umas 180 carteiras
[29/10/2026 14:35] Ana Paula SEMAS Paranaguá: Ana Paula Mendes Cordeiro, assistente social, 41 3420-2900
""",
        esperado={
            "estado": "PR",
            "municipio": "Paranaguá",
            "local_evento": Contem("Ginásio da Ilha"),
            "endereco": Contem("Rua Principal, 800"),
            "bairro": "Ilha dos Valadares",
            "data_inicio_evento": "2026-11-21",
            "data_fim_evento": "2026-11-21",
            "data_solicitacao": "2026-10-29",
            "servicos": [_CIN, _FOTO],
            "quantidade_cin": 180,
            "solicitante_nome": "Ana Paula Mendes Cordeiro",
            "solicitante_cargo_unidade": Contem("assistente social"),
            "contato": Contem("3420-2900"),
        },
        nota="Data corrigida no meio da conversa: vale 21/11, não 14/11; dois participantes no grupo.",
    ),
    # ------------------------------------------------------------------ 035
    Caso(
        id="sol-035",
        modulo="solicitacoes",
        formato="eml",
        agora="2026-10-22 09:00",
        texto=_eml(
            "Coordenação Tecnólogo em Segurança <seguranca@unipar-umuarama.edu.br>",
            _PCPR,
            "Visita técnica ao Instituto de Identificação",
            "2026-10-21 19:40",
            """
Prezados,

O curso de Tecnologia em Segurança Pública, de Umuarama, gostaria de agendar
uma visita técnica dos alunos do 4º período ao Instituto de Identificação do
Paraná, em Curitiba, no dia 3 de dezembro (quinta-feira), no período da manhã.
Seremos 35 alunos e 2 professores, viajando de ônibus.

Atenciosamente,

Prof. Marcelo Augusto Vendrame
Coordenador do Curso
Praça Mascarenhas de Moraes, 4282 - Zona III - Umuarama/PR
(44) 3621-2828
""",
        ),
        esperado={
            "tipo_evento": "Visita",
            "estado": "PR",
            "municipio": "Curitiba",
            "local_evento": Contem("Instituto de Identificação"),
            "endereco": AUSENTE,
            "bairro": AUSENTE,
            "data_inicio_evento": "2026-12-03",
            "data_fim_evento": "2026-12-03",
            "data_solicitacao": "2026-10-21",
            "servicos": [],
            "quantidade_cin": AUSENTE,
            "solicitante_nome": "Marcelo Augusto Vendrame",
            "solicitante_cargo_unidade": Contem("Coordenador do Curso"),
            "contato": Contem("3621-2828"),
        },
        nota="Quem pede é de Umuarama, mas a visita é em Curitiba; endereço da assinatura (Zona III) não é o local; 'ônibus' não é unidade móvel.",
    ),
    # ------------------------------------------------------------------ 036
    Caso(
        id="sol-036",
        modulo="solicitacoes",
        formato="eml",
        agora="2026-10-05 10:15",
        texto=_eml(
            "Secretaria de Governo - Colombo <governo@colombo.pr.gov.br>",
            _PCPR,
            _q("PCPR na Comunidade – Colombo – 31/10/2026"),
            "2026-10-05 08:03",
            """
Bom dia!

Confirmamos o interesse do Município de Colombo em receber o programa
PCPR na Comunidade no dia 31/10/2026, sábado, das 9h às 16h, no Parque
Municipal da Uva - Rodovia da Uva, 2600 - Roça Grande.

Pedimos a unidade móvel com emissão de CIN, coleta de digitais e fotografia,
além da exposição de viaturas para as famílias. Previsão de 350 atendimentos.

Atenciosamente,

Everton Luís Ceccon
Diretor de Relações Institucionais
Secretaria Municipal de Governo
(41) 3656-8000 ramal 8012
(41) 99640-7123
""",
            html=True,
        ),
        esperado={
            "tipo_evento": "PCPR na Comunidade",
            "estado": "PR",
            "municipio": "Colombo",
            "local_evento": Contem("Parque Municipal da Uva"),
            "endereco": Contem("Rodovia da Uva, 2600"),
            "bairro": "Roça Grande",
            "data_inicio_evento": "2026-10-31",
            "data_fim_evento": "2026-10-31",
            "data_solicitacao": "2026-10-05",
            "servicos": [_CIN, _DIG, _FOTO, _VTR],
            "quantidade_cin": 350,
            "unidade_movel": True,
            "solicitante_nome": "Everton Luís Ceccon",
            "solicitante_cargo_unidade": Contem("Diretor de Relações Institucionais"),
            "contato": UmDe(Contem("3656-8000"), Contem("99640-7123")),
        },
        nota="Assunto codificado em =?utf-8?; quatro serviços; 'Rodovia da Uva' sem PR-; ramal no telefone.",
    ),
    # ------------------------------------------------------------------ 037
    Caso(
        id="sol-037",
        modulo="solicitacoes",
        formato="texto",
        agora="2026-10-13 09:00",
        texto="""De: Assessoria Gabinete Pinhais
Enviado em: segunda-feira, 12 de outubro de 2026 18:25
Para: eventos.sociais@pc.pr.gov.br
Assunto: Pedido do Prefeito - ação no Weissópolis

Senhores,

A pedido do Prefeito de Pinhais, Sr. Osmar Kruger Bittencourt, solicito a
participação da Polícia Civil na ação social do Jardim Weissópolis, no
sábado (24/10), das 8h às 13h, no Ginásio Poliesportivo do Weissópolis -
Rua Rio Grande do Norte, 150.

Serviços: emissão de RG e atendimento social.

Qualquer dúvida estou à disposição.

Karina Alessi Moro
Assessora Especial do Gabinete do Prefeito
(41) 3912-5000 | 41 99812-0404
""",
        esperado={
            "estado": "PR",
            "municipio": "Pinhais",
            "local_evento": Contem("Ginásio Poliesportivo do Weissópolis"),
            "endereco": Contem("Rua Rio Grande do Norte, 150"),
            "bairro": UmDe("Jardim Weissópolis", "Weissópolis"),
            "data_inicio_evento": "2026-10-24",
            "data_fim_evento": "2026-10-24",
            "data_solicitacao": "2026-10-12",
            "servicos": [_CIN, _SOCIAL],
            "solicitante_nome": UmDe("Karina Alessi Moro", "Osmar Kruger Bittencourt"),
            "solicitante_cargo_unidade": UmDe(Contem("Assessora Especial"), Contem("Prefeito")),
            "contato": UmDe(Contem("3912-5000"), Contem("99812-0404")),
        },
        nota="Assessora pede em nome do prefeito; 'Rua Rio Grande do Norte' não é estado nem município; 'sábado (24/10)'.",
    ),
    # ------------------------------------------------------------------ 038
    Caso(
        id="sol-038",
        modulo="solicitacoes",
        formato="eml",
        agora="2026-10-26 10:00",
        texto=_eml(
            "Paraná em Ação <paranaemacao@seju.pr.gov.br>",
            _PCPR,
            "Paraná em Ação Arapongas - confirmação de serviços",
            "2026-10-23 16:30",
            """
Prezados,

Segue a confirmação da edição do Paraná em Ação em Arapongas, nos dias
2 e 3 de dezembro, no Colégio Estadual Marquês de Caravelas, Rua Maringá,
1500 - Centro.

Serviços da PCPR: emissão de CIN e coleta de digitais, com a unidade móvel.
Estimamos cerca de 300 atendimentos por dia.

Atenciosamente,
Fernanda Scheffer Guimarães
Coordenadora Executiva - Paraná em Ação
(41) 3221-7300
""",
        ),
        esperado={
            "tipo_evento": "Paraná em Ação",
            "estado": "PR",
            "municipio": "Arapongas",
            "local_evento": Contem("Colégio Estadual Marquês de Caravelas"),
            "endereco": Contem("Rua Maringá, 1500"),
            "bairro": "Centro",
            "data_inicio_evento": "2026-12-02",
            "data_fim_evento": "2026-12-03",
            "data_solicitacao": "2026-10-23",
            "servicos": [_CIN, _DIG],
            "quantidade_cin": 600,
            "unidade_movel": True,
            "solicitante_nome": "Fernanda Scheffer Guimarães",
            "solicitante_cargo_unidade": Contem("Coordenadora Executiva"),
            "contato": Contem("3221-7300"),
        },
        nota="'Rua Maringá' não é o município; '300 atendimentos por dia' em dois dias = 600.",
    ),
    # ------------------------------------------------------------------ 039
    Caso(
        id="sol-039",
        modulo="solicitacoes",
        formato="texto",
        agora="2026-09-25 11:00",
        texto="""Prezados, boa tarde.

Aqui no nosso município vamos realizar no dia 20 de outubro uma grande ação
de cidadania no Ginásio de Esportes Tio Beto (Rua XV de Novembro, 845, Centro),
e gostaríamos de contar com a Polícia Civil para emissão de carteira de
identidade. Serão aproximadamente 250 atendimentos.

Atenciosamente,

Jucimara Taques Pedroso
Secretária de Assistência Social
Prefeitura Municipal de Imbituva
(42) 3436-8100
""",
        esperado={
            "estado": "PR",
            "municipio": "Imbituva",
            "local_evento": Contem("Ginásio de Esportes Tio Beto"),
            "endereco": Contem("Rua XV de Novembro, 845"),
            "bairro": "Centro",
            "data_inicio_evento": "2026-10-20",
            "data_fim_evento": "2026-10-20",
            "servicos": [_CIN],
            "quantidade_cin": 250,
            "solicitante_nome": "Jucimara Taques Pedroso",
            "solicitante_cargo_unidade": Contem("Secretária de Assistência Social"),
            "contato": Contem("3436-8100"),
        },
        nota="O município só aparece na assinatura, mas o evento é 'aqui no nosso município': vale Imbituva; 'XV de Novembro' não é data.",
    ),
    # ------------------------------------------------------------------ 040
    Caso(
        id="sol-040",
        modulo="solicitacoes",
        formato="eml",
        agora="2026-09-30 09:00",
        texto=_eml(
            "3ª Regional de Saúde <3rs@sesa.pr.gov.br>",
            _PCPR,
            "Ação intersetorial em Tibagi",
            "2026-09-29 13:02",
            """
Prezados,

A 3ª Regional de Saúde de Ponta Grossa organiza, com a Prefeitura de Tibagi,
uma ação intersetorial de 16 a 18/10 no Distrito de Alto do Amparo, em Tibagi,
na Escola Rural Municipal Alto do Amparo.

Pedimos a participação da PCPR com emissão de carteiras de identidade e
coleta de digitais. Estimativa: 220 carteiras.

Atenciosamente,

Giovana Hilgemberg Martins
Chefe da Divisão de Atenção à Saúde
3ª Regional de Saúde - Ponta Grossa
Rua Balduíno Taques, 1500 - Centro - Ponta Grossa/PR
(42) 3219-9800
""",
        ),
        esperado={
            "estado": "PR",
            "municipio": "Tibagi",
            "local_evento": Contem("Escola Rural Municipal Alto do Amparo"),
            "endereco": AUSENTE,
            "data_inicio_evento": "2026-10-16",
            "data_fim_evento": "2026-10-18",
            "data_solicitacao": "2026-09-29",
            "servicos": [_CIN, _DIG],
            "quantidade_cin": 220,
            "solicitante_nome": "Giovana Hilgemberg Martins",
            "solicitante_cargo_unidade": Contem("Chefe da Divisão de Atenção à Saúde"),
            "contato": Contem("3219-9800"),
        },
        nota="Regional de Ponta Grossa (sede e endereço na assinatura) pede evento em Tibagi; o endereço da assinatura não é do evento.",
    ),
    # ------------------------------------------------------------------ 041
    Caso(
        id="sol-041",
        modulo="solicitacoes",
        formato="eml",
        agora="2026-10-01 10:00",
        texto=_eml(
            "Secretaria de Agricultura - Palmeira <agricultura@palmeira.pr.gov.br>",
            _PCPR,
            _q("Semana do Agricultor – Palmeira (PR) – solicitação de estande"),
            "2026-09-30 17:48",
            """
Prezados,

A Prefeitura de Palmeira (PR) realiza a 12ª Semana do Agricultor, feira
agropecuária do município, e gostaria de convidar a Polícia Civil para montar
um estande de emissão de carteira de identidade na sexta, 23 de outubro, das
8h às 18h, no Parque de Exposições Dr. Pedro Nolasco Pizzatto, Rodovia PR-151,
km 3.

Contato: Ademir José Kutz - Secretário Municipal de Agricultura
(42) 3252-1144 / (42) 98831-7070
""",
        ),
        esperado={
            "tipo_evento": "Feira",
            "estado": "PR",
            "municipio": "Palmeira",
            "local_evento": Contem("Parque de Exposições"),
            "endereco": Contem("Rodovia PR-151, km 3"),
            "data_inicio_evento": "2026-10-23",
            "data_fim_evento": "2026-10-23",
            "data_solicitacao": "2026-09-30",
            "servicos": [_CIN],
            "solicitante_nome": "Ademir José Kutz",
            "solicitante_cargo_unidade": Contem("Secretário Municipal de Agricultura"),
            "contato": UmDe(Contem("3252-1144"), Contem("98831-7070")),
        },
        nota="Palmeira existe no PR e em SC: '(PR)' decide; 'Semana do Agricultor' dura mais, mas o pedido é só para sexta 23/10; rodovia com km.",
    ),
    # ------------------------------------------------------------------ 042
    Caso(
        id="sol-042",
        modulo="solicitacoes",
        formato="texto",
        agora="2026-10-22 16:00",
        texto="""---------- Forwarded message ---------
From: Núcleo de Polícia Comunitária PG <npc.pontagrossa@pc.pr.gov.br>
Date: Thu, Oct 22, 2026 at 11:40 AM
Subject: Fwd: PCPR na Comunidade Uvaranas
To: eventos.sociais@pc.pr.gov.br


segue pedido da associação

---------- Forwarded message ---------
From: Associação de Moradores de Uvaranas <amuvaranas@gmail.com>
Date: Tue, Oct 20, 2026 at 8:15 PM
Subject: PCPR na Comunidade Uvaranas
To: npc.pontagrossa@pc.pr.gov.br


Boa noite,

Queremos solicitar o PCPR na Comunidade em Uvaranas no próximo dia 10/11 (terça),
das 13h às 18h, no Salão Comunitário São Judas Tadeu, Rua Carlos Cavalcanti,
4480 - Uvaranas, Ponta Grossa. Emissão de RG e orientação jurídica.

Clodoaldo Sviercoski
Presidente da AMU
(42) 99911-2233
""",
        esperado={
            "tipo_evento": "PCPR na Comunidade",
            "estado": "PR",
            "municipio": "Ponta Grossa",
            "local_evento": Contem("Salão Comunitário São Judas Tadeu"),
            "endereco": Contem("Rua Carlos Cavalcanti, 4480"),
            "bairro": "Uvaranas",
            "data_inicio_evento": "2026-11-10",
            "data_fim_evento": "2026-11-10",
            "data_solicitacao": UmDe("2026-10-20", "2026-10-22"),
            "servicos": [_CIN, _JUR],
            "solicitante_nome": "Clodoaldo Sviercoski",
            "solicitante_cargo_unidade": Contem("Presidente da AMU"),
            "contato": Contem("99911-2233"),
        },
        nota="Encaminhamento do Gmail em inglês (Date: Thu, Oct 22) aninhado; solicitante é a associação, não o núcleo que encaminhou.",
    ),
    # ------------------------------------------------------------------ 043
    Caso(
        id="sol-043",
        modulo="solicitacoes",
        formato="eml",
        agora="2026-10-10 09:00",
        texto=_eml(
            "Secretaria de Assistência Social <sas@cianorte.pr.gov.br>",
            _PCPR,
            "Pedido de carteiras de identidade - 07/11",
            "2026-10-09 11:26",
            """
Bom dia!

A Secretaria de Assistência Social de Cianorte solicita atendimento para
emissão da carteira de identidade no dia 07/11/2026, com previsão de 130
carteiras. O local ainda está a definir (provavelmente em um dos CRAS) e
informaremos assim que confirmado.

Atenciosamente,
Regiane Beraldo Fonseca
Gerente de Proteção Social
(44) 3619-6200
""",
        ),
        esperado={
            "estado": "PR",
            "municipio": "Cianorte",
            "local_evento": AUSENTE,
            "endereco": AUSENTE,
            "data_inicio_evento": "2026-11-07",
            "data_fim_evento": "2026-11-07",
            "data_solicitacao": "2026-10-09",
            "servicos": [_CIN],
            "quantidade_cin": 130,
            "solicitante_nome": "Regiane Beraldo Fonseca",
            "solicitante_cargo_unidade": Contem("Gerente de Proteção Social"),
            "contato": Contem("3619-6200"),
        },
        nota="Local 'a definir' ('provavelmente em um dos CRAS') não pode virar local do evento; data no assunto igual à do corpo.",
    ),
    # ------------------------------------------------------------------ 044
    Caso(
        id="sol-044",
        modulo="solicitacoes",
        formato="texto",
        agora="2026-10-19 08:30",
        texto="""[16/10/2026 19:10] Pr. Wellington: Paz do Senhor irmãos
[16/10/2026 19:11] Pr. Wellington: A igreja vai fazer a Feira de Cidadania dia 21/11 aqui em Telêmaco Borba, no pátio da igreja, Av. Chanceler Horácio Lafer, 1900, Centro
[16/10/2026 19:12] Irmã Cida: Pastor o senhor já pediu o RG pra polícia civil?
[16/10/2026 19:12] Pr. Wellington: Vou pedir agora. Polícia Civil, é possível vir fazer a carteira de identidade e as digitais?
[16/10/2026 19:14] Irmã Cida: Meu número pra quem quiser se inscrever é 42 99102-5566
[16/10/2026 19:20] Pr. Wellington: Pastor Wellington Siqueira Ramos, Igreja Evangélica Nova Aliança, 42 99977-3030
""",
        esperado={
            "tipo_evento": "Feira",
            "estado": "PR",
            "municipio": "Telêmaco Borba",
            "local_evento": Contem("Igreja"),
            "endereco": Contem("Av. Chanceler Horácio Lafer, 1900"),
            "bairro": "Centro",
            "data_inicio_evento": "2026-11-21",
            "data_fim_evento": "2026-11-21",
            "data_solicitacao": "2026-10-16",
            "servicos": [_CIN, _DIG],
            "solicitante_nome": "Wellington Siqueira Ramos",
            "solicitante_cargo_unidade": Contem("Igreja Evangélica Nova Aliança"),
            "contato": Contem("99977-3030"),
        },
        nota="Grupo com várias pessoas: o telefone da Irmã Cida (inscrições) não é o contato do solicitante.",
    ),
    # ------------------------------------------------------------------ 045
    Caso(
        id="sol-045",
        modulo="solicitacoes",
        formato="eml",
        agora="2026-11-16 10:00",
        texto=_eml(
            "APAE de Cambé <apae.cambe@apaepr.org.br>",
            _PCPR,
            "Carteira de identidade para alunos da APAE",
            "2026-11-16 08:55",
            """
Bom dia,

A APAE de Cambé tem 45 alunos que ainda não possuem carteira de identidade e
que têm grande dificuldade de locomoção. Solicitamos, se possível, o
atendimento na própria escola, no dia 4/12 (sexta-feira), no período da manhã.

Endereço: Rua Bahia, 750, Jardim Ana Rosa, Cambé.

Atenciosamente,
Silmara Nogueira Pires
Diretora da Escola de Educação Especial
(43) 3254-1616
""",
        ),
        esperado={
            "estado": "PR",
            "municipio": "Cambé",
            "local_evento": Contem("APAE"),
            "endereco": Contem("Rua Bahia, 750"),
            "bairro": "Jardim Ana Rosa",
            "data_inicio_evento": "2026-12-04",
            "data_fim_evento": "2026-12-04",
            "data_solicitacao": "2026-11-16",
            "servicos": [_CIN],
            "quantidade_cin": 45,
            "solicitante_nome": "Silmara Nogueira Pires",
            "solicitante_cargo_unidade": Contem("Diretora"),
            "contato": Contem("3254-1616"),
        },
        nota="45 alunos sem carteira = 45 CIN; 'Rua Bahia' não é estado; endereço em linha separada.",
    ),
    # ------------------------------------------------------------------ 046
    Caso(
        id="sol-046",
        modulo="solicitacoes",
        formato="eml",
        agora="2026-10-01 09:40",
        texto=_eml(
            "Cultura Lapa <cultura@lapa.pr.gov.br>",
            _PCPR,
            "Festa do Tropeiro - viaturas antigas",
            "2026-09-30 16:15",
            """
Olá, boa tarde

Na Festa do Tropeiro deste ano, dia 20 de out., gostaríamos de ter a exposição
das viaturas antigas e modernas da Polícia Civil na Praça General Carneiro,
no Centro Histórico da Lapa, das 10h às 18h.

O evento de 2025 (18/10/2025) teve público de 8 mil pessoas.

Abraço,
Otávio Correia Staben
Diretor de Cultura
(41) 3622-1230
""",
        ),
        esperado={
            "estado": "PR",
            "municipio": "Lapa",
            "local_evento": Contem("Praça General Carneiro"),
            "endereco": Contem("Praça General Carneiro"),
            "bairro": "Centro Histórico",
            "data_inicio_evento": "2026-10-20",
            "data_fim_evento": "2026-10-20",
            "data_solicitacao": "2026-09-30",
            "servicos": [_VTR],
            "quantidade_cin": AUSENTE,
            "solicitante_nome": "Otávio Correia Staben",
            "solicitante_cargo_unidade": Contem("Diretor de Cultura"),
            "contato": Contem("3622-1230"),
        },
        nota="'dia 20 de out.' abreviado; edição de 18/10/2025 e 8 mil pessoas são do ano anterior; festa sem tipo claro.",
    ),
    # ------------------------------------------------------------------ 047
    Caso(
        id="sol-047",
        modulo="solicitacoes",
        formato="texto",
        agora="2026-09-14 15:00",
        texto="""De: Gabinete SESP <gabinete@sesp.pr.gov.br>
Enviado em: sexta-feira, 11 de setembro de 2026 16:40
Para: Gabinete DG PCPR
Assunto: Ofício 1.207/2026-GS - Mutirão de cidadania em Laranjeiras do Sul

Curitiba, 10 de setembro de 2026.

Ofício nº 1.207/2026-GS

Senhor Delegado-Geral,

Encaminho pedido do Município de Laranjeiras do Sul para realização de
mutirão de cidadania nos dias 24 e 25 de outubro de 2026, no Centro de Eventos
Municipal, Av. 7 de Setembro, 2155 - Centro, com emissão da Carteira de
Identidade Nacional, coleta de digitais e fotografia. O município estima
400 atendimentos.

Respeitosamente,

Cel. Hamilton Pereira Duarte
Chefe de Gabinete - Secretaria de Estado da Segurança Pública
Rua Deputado Mário de Barros, 1290 - Centro Cívico - Curitiba/PR
""",
        esperado={
            "estado": "PR",
            "municipio": "Laranjeiras do Sul",
            "local_evento": Contem("Centro de Eventos Municipal"),
            "endereco": Contem("Av. 7 de Setembro, 2155"),
            "bairro": "Centro",
            "data_inicio_evento": "2026-10-24",
            "data_fim_evento": "2026-10-25",
            "data_solicitacao": UmDe("2026-09-10", "2026-09-11"),
            "servicos": [_CIN, _DIG, _FOTO],
            "quantidade_cin": 400,
            "solicitante_nome": "Hamilton Pereira Duarte",
            "solicitante_cargo_unidade": Contem("Chefe de Gabinete"),
        },
        nota="Ofício datado de Curitiba (sede da SESP) para evento no interior; 'Av. 7 de Setembro' não é data; Centro Cívico da assinatura não é o bairro.",
    ),
    # ------------------------------------------------------------------ 048
    Caso(
        id="sol-048",
        modulo="solicitacoes",
        formato="eml",
        agora="2026-12-15 10:00",
        texto=_eml(
            "Prefeitura de Pontal do Paraná <eventos@pontaldoparana.pr.gov.br>",
            _PCPR,
            "PCPR na Comunidade - Festival de Verão de Pontal",
            "2026-12-14 17:10",
            """
Prezados,

Para a programação do Festival de Verão, gostaríamos de receber o programa
PCPR na Comunidade nos dias 6 e 7 de fevereiro, na Praça de Eventos de Pontal
do Sul (Av. Beira-Mar, s/n, Pontal do Sul), com emissão de RG e exposição de
viaturas.

Atenciosamente,
Diego Morais Kawano
Diretor de Eventos
(41) 3455-8400
""",
        ),
        esperado={
            "tipo_evento": "PCPR na Comunidade",
            "estado": "PR",
            "municipio": "Pontal do Paraná",
            "local_evento": Contem("Praça de Eventos de Pontal do Sul"),
            "endereco": Contem("Av. Beira-Mar, s/n"),
            "bairro": "Pontal do Sul",
            "data_inicio_evento": "2027-02-06",
            "data_fim_evento": "2027-02-07",
            "data_solicitacao": "2026-12-14",
            "servicos": [_CIN, _VTR],
            "solicitante_nome": "Diego Morais Kawano",
            "solicitante_cargo_unidade": Contem("Diretor de Eventos"),
            "contato": Contem("3455-8400"),
        },
        nota="Mês sem ano lido em dezembro: fevereiro é do ano seguinte (2027); 'Pontal do Paraná' contém 'Paraná'.",
    ),
    # ------------------------------------------------------------------ 049
    Caso(
        id="sol-049",
        modulo="solicitacoes",
        formato="eml",
        agora="2026-10-30 14:00",
        texto=_eml(
            "Justiça no Bairro <justicanobairro@tjpr.jus.br>",
            _PCPR,
            _q("Justiça no Bairro – Londrina – Cinco Conjuntos"),
            "2026-10-30 10:30",
            """
Prezados parceiros,

O Justiça no Bairro estará em Londrina de 23 a 25/11/2026, na região dos
Cinco Conjuntos, no Centro Esportivo e Cultural Norte - Av. Saul Elkind, 2200
- Cinco Conjuntos, CEP 86082-000.

Solicitamos à PCPR a emissão de carteiras de identidade e as fotos, com
previsão de 900 carteiras nos três dias, e a unidade móvel.

Atenciosamente,
Rafael Tokarski Nunes
Analista Judiciário - Coordenadoria do Justiça no Bairro
(41) 3200-5890
""",
            html=True,
        ),
        esperado={
            "tipo_evento": "Justiça no Bairro",
            "estado": "PR",
            "municipio": "Londrina",
            "local_evento": Contem("Centro Esportivo e Cultural Norte"),
            "endereco": Contem("Av. Saul Elkind, 2200"),
            "bairro": "Cinco Conjuntos",
            "cep": "86082-000",
            "data_inicio_evento": "2026-11-23",
            "data_fim_evento": "2026-11-25",
            "data_solicitacao": "2026-10-30",
            "servicos": [_CIN, _FOTO],
            "quantidade_cin": 900,
            "unidade_movel": True,
            "solicitante_nome": "Rafael Tokarski Nunes",
            "solicitante_cargo_unidade": Contem("Analista Judiciário"),
            "contato": Contem("3200-5890"),
        },
        nota="Intervalo 'de 23 a 25/11/2026'; CEP depois do bairro; multipart.",
    ),
    # ------------------------------------------------------------------ 050
    Caso(
        id="sol-050",
        modulo="solicitacoes",
        formato="texto",
        agora="2026-08-20 10:00",
        texto="""Bom dia, sou o Ivan da Secretaria de Educação de Rolândia. Para o desfile
cívico de 7 de setembro na Av. Presidente Bernardes gostaríamos de contar com
as viaturas antigas da Polícia Civil desfilando ou expostas no final do
percurso. Concentração às 8h.
Ivan Carlos Mazzotti - Chefe de Divisão de Eventos Escolares - (43) 3255-8321
""",
        esperado={
            "estado": "PR",
            "municipio": "Rolândia",
            "local_evento": Contem("Presidente Bernardes"),
            "endereco": Contem("Av. Presidente Bernardes"),
            "data_inicio_evento": "2026-09-07",
            "data_fim_evento": "2026-09-07",
            "servicos": [_VTR],
            "solicitante_nome": "Ivan Carlos Mazzotti",
            "solicitante_cargo_unidade": Contem("Chefe de Divisão de Eventos Escolares"),
            "contato": Contem("3255-8321"),
        },
        nota="Aqui '7 de setembro' É a data do evento (desfile), sem ano; texto puro sem cabeçalho.",
    ),
    # ------------------------------------------------------------------ 051
    Caso(
        id="sol-051",
        modulo="solicitacoes",
        formato="eml",
        agora="2026-10-30 11:00",
        texto=_eml(
            "Conselho Tutelar Carambeí <ct@carambei.pr.gov.br>",
            _PCPR,
            "Solicitação de capacitação para conselheiros tutelares",
            "2026-10-29 09:37",
            """
Prezados,

Os Conselhos Tutelares da região dos Campos Gerais solicitam capacitação sobre
escuta especializada e depoimento especial, a ser realizada em Carambeí na
quarta e quinta, dias 18 e 19/11, das 8h às 17h, na Câmara Municipal de
Carambeí - Av. dos Pioneiros, 2150 - Centro.

Público: 60 conselheiros de 12 municípios.

Andreia Van der Neut
Conselheira Tutelar - Coordenadora
42 3231-9025
""",
        ),
        esperado={
            "tipo_evento": "Capacitação",
            "estado": "PR",
            "municipio": "Carambeí",
            "local_evento": Contem("Câmara Municipal de Carambeí"),
            "endereco": Contem("Av. dos Pioneiros, 2150"),
            "bairro": "Centro",
            "data_inicio_evento": "2026-11-18",
            "data_fim_evento": "2026-11-19",
            "data_solicitacao": "2026-10-29",
            "servicos": [],
            "quantidade_cin": AUSENTE,
            "solicitante_nome": "Andreia Van der Neut",
            "solicitante_cargo_unidade": Contem("Conselheira Tutelar"),
            "contato": Contem("3231-9025"),
        },
        nota="'quarta e quinta, dias 18 e 19/11'; '12 municípios' e 'Campos Gerais' não são o município; 60 conselheiros não é CIN.",
    ),
    # ------------------------------------------------------------------ 052
    Caso(
        id="sol-052",
        modulo="solicitacoes",
        formato="texto",
        agora="2026-10-08 10:00",
        texto="""De: 29ª DRP - Dois Vizinhos
Enviado em: quarta-feira, 7 de outubro de 2026 15:20
Para: Eventos Sociais
Assunto: RES: Feira Agropecuária de Dois Vizinhos - unidade móvel

Prezados colegas,

Reforço o pedido do Sindicato Rural: a Feira Agropecuária de Dois Vizinhos
acontece de 27 a 29 de novembro, no Parque de Exposições Arlindo Chiarello,
Estrada Municipal Linha São Braz, s/n. Pedem a unidade móvel para emissão da
CIN durante os três dias. Expectativa do sindicato: 25 mil visitantes.

Dr. Fabiano Ruschel Kemmerich
Delegado de Polícia - 29ª DRP
(46) 3536-1616

________________________________
De: Sindicato Rural de Dois Vizinhos
Enviado: segunda-feira, 5 de outubro de 2026 10:11
Assunto: Feira Agropecuária de Dois Vizinhos - unidade móvel

Delegado, conforme conversamos, segue o pedido formal. Maristela Fontana - secretária do Sindicato - (46) 3536-4040
""",
        esperado={
            "tipo_evento": "Feira",
            "estado": "PR",
            "municipio": "Dois Vizinhos",
            "local_evento": Contem("Parque de Exposições Arlindo Chiarello"),
            "endereco": Contem("Estrada Municipal Linha São Braz, s/n"),
            "data_inicio_evento": "2026-11-27",
            "data_fim_evento": "2026-11-29",
            "data_solicitacao": UmDe("2026-10-05", "2026-10-07"),
            "servicos": [_CIN],
            "quantidade_cin": AUSENTE,
            "unidade_movel": True,
            "solicitante_nome": UmDe("Fabiano Ruschel Kemmerich", "Maristela Fontana"),
            "contato": UmDe(Contem("3536-1616"), Contem("3536-4040")),
        },
        nota="Delegado reforça pedido do sindicato (mensagem citada embaixo com outra data); 25 mil visitantes não é CIN; endereço em estrada rural.",
    ),
    # ------------------------------------------------------------------ 053
    Caso(
        id="sol-053",
        modulo="solicitacoes",
        formato="eml",
        agora="2026-10-06 09:00",
        texto=_eml(
            "Coordenação Paraná em Ação <paranaemacao@seju.pr.gov.br>",
            "Parceiros Paraná em Ação <parceiros-pea@seju.pr.gov.br>",
            "Reunião de alinhamento - calendário 2027",
            "2026-10-05 18:20",
            """
Prezados parceiros,

Convocamos para reunião de alinhamento do calendário 2027 do Paraná em Ação,
na terça-feira, 13/10, às 14h, na Sala de Reuniões da SEJU - Palácio das
Araucárias, Rua Jacy Loureiro de Campos, s/n - Centro Cívico, Curitiba.

Solicitamos a presença de um representante da PCPR (Instituto de
Identificação).

Pauta: balanço das edições de 2026 (Dois Vizinhos, Francisco Beltrão e
Arapongas) e proposta de 10 edições para 2027.

Atenciosamente,
Fernanda Scheffer Guimarães
Coordenadora Executiva
(41) 3221-7300
""",
        ),
        esperado={
            "tipo_evento": "Reunião",
            "estado": "PR",
            "municipio": "Curitiba",
            "local_evento": Contem("Sala de Reuniões da SEJU"),
            "endereco": Contem("Rua Jacy Loureiro de Campos, s/n"),
            "bairro": "Centro Cívico",
            "data_inicio_evento": "2026-10-13",
            "data_fim_evento": "2026-10-13",
            "data_solicitacao": "2026-10-05",
            "servicos": [],
            "solicitante_nome": "Fernanda Scheffer Guimarães",
            "solicitante_cargo_unidade": Contem("Coordenadora Executiva"),
            "contato": Contem("3221-7300"),
        },
        nota="É uma reunião sobre o Paraná em Ação, não uma edição do programa; municípios da pauta (Dois Vizinhos...) não são o local.",
    ),
    # ------------------------------------------------------------------ 054
    Caso(
        id="sol-054",
        modulo="solicitacoes",
        formato="texto",
        agora="2026-10-07 18:00",
        texto="""[07/10/2026 15:21] Tânia Mandaguari: Boa tarde
[07/10/2026 15:21] Tânia Mandaguari: <Mídia oculta>
[07/10/2026 15:22] Tânia Mandaguari: Mandei o ofício aí em cima. Resumindo: queremos o PCPR na Comunidade aqui em Mandaguari no sábado 17/10
[07/10/2026 15:23] Tânia Mandaguari: Na Escola Estadual Vera Cruz, Rua Paraná, 400, Jardim Esperança
[07/10/2026 15:23] Tânia Mandaguari: RG, digitais e foto. E se der as viaturas antigas pras crianças verem 😍
[07/10/2026 15:25] Tânia Mandaguari: Tânia Bertoldo Marchi, diretora de assistência social, 44 3233-5011
""",
        esperado={
            "tipo_evento": "PCPR na Comunidade",
            "estado": "PR",
            "municipio": "Mandaguari",
            "local_evento": Contem("Escola Estadual Vera Cruz"),
            "endereco": Contem("Rua Paraná, 400"),
            "bairro": "Jardim Esperança",
            "data_inicio_evento": "2026-10-17",
            "data_fim_evento": "2026-10-17",
            "data_solicitacao": "2026-10-07",
            "servicos": [_CIN, _DIG, _FOTO, _VTR],
            "solicitante_nome": "Tânia Bertoldo Marchi",
            "solicitante_cargo_unidade": Contem("diretora de assistência social"),
            "contato": Contem("3233-5011"),
        },
        nota="WhatsApp com '<Mídia oculta>' e emoji; 'Rua Paraná' não é estado nem município; 'Vera Cruz' é nome de escola.",
    ),
    # ------------------------------------------------------------------ 055
    Caso(
        id="sol-055",
        modulo="solicitacoes",
        formato="eml",
        agora="2026-11-04 09:00",
        texto=_eml(
            "SALA DO EMPREENDEDOR <empreendedor@saomateusdosul.pr.gov.br>",
            _PCPR,
            "FEIRA DA MULHER EMPREENDEDORA - SAO MATEUS DO SUL",
            "2026-11-03 16:02",
            """
PREZADOS,

A SALA DO EMPREENDEDOR DE SAO MATEUS DO SUL REALIZA NO DIA 28/11 A FEIRA DA
MULHER EMPREENDEDORA, NA PRACA CEL. JOSE AUGUSTO DA SILVA, CENTRO, E CONVIDA A
POLICIA CIVIL PARA EMITIR CARTEIRAS DE IDENTIDADE NO LOCAL.

ATT
ELIANE KRAWCZYK
AGENTE DE DESENVOLVIMENTO
(42) 3520-1500
""",
        ),
        esperado={
            "tipo_evento": "Feira",
            "estado": "PR",
            "municipio": "São Mateus do Sul",
            "local_evento": Contem("Praça Cel. José Augusto da Silva"),
            "endereco": Contem("Praça Cel. José Augusto da Silva"),
            "bairro": "Centro",
            "data_inicio_evento": "2026-11-28",
            "data_fim_evento": "2026-11-28",
            "data_solicitacao": "2026-11-03",
            "servicos": [_CIN],
            "solicitante_nome": "Eliane Krawczyk",
            "solicitante_cargo_unidade": Contem("Agente de Desenvolvimento"),
            "contato": Contem("3520-1500"),
        },
        nota="Tudo em CAIXA ALTA sem acento, inclusive município e nome; data sem ano.",
    ),
    # ------------------------------------------------------------------ 056
    Caso(
        id="sol-056",
        modulo="solicitacoes",
        formato="eml",
        agora="2026-11-20 08:00",
        texto=_eml(
            "Débora Lemos <deboralemos.araucaria@gmail.com>",
            _PCPR,
            "Natal Solidário Costeira",
            "2026-11-19 22:48",
            """
Oi! Tudo bem? Sou voluntária do Natal Solidário do bairro Costeira, em
Araucária. Vai ser no sábado, 12 de dezembro, no Salão da Capela Santa Rita
(Rua Irmã Elizabeth Werka, 55, Costeira).

Vocês conseguiriam mandar uma equipe para fazer RG e atendimento social?
A gente estima umas 70 carteiras.

Débora Lemos
+55 41 99123-4567

Enviado do meu iPhone
""",
            html=True,
        ),
        esperado={
            "estado": "PR",
            "municipio": "Araucária",
            "local_evento": Contem("Capela Santa Rita"),
            "endereco": Contem("Rua Irmã Elizabeth Werka, 55"),
            "bairro": "Costeira",
            "data_inicio_evento": "2026-12-12",
            "data_fim_evento": "2026-12-12",
            "data_solicitacao": "2026-11-19",
            "servicos": [_CIN, _SOCIAL],
            "quantidade_cin": 70,
            "solicitante_nome": "Débora Lemos",
            "solicitante_cargo_unidade": Contem("voluntária"),
            "contato": Contem("99123-4567"),
        },
        nota="Telefone com +55; 'Enviado do meu iPhone' depois do nome; e-mail enviado à noite (-03:00) mantém a data local 19/11.",
    ),
    # ------------------------------------------------------------------ 057
    Caso(
        id="sol-057",
        modulo="solicitacoes",
        formato="eml",
        agora="2026-10-09 10:00",
        texto=_eml(
            "Rotary Club Jacarezinho <rotary.jacarezinho@gmail.com>",
            _PCPR,
            _q("Ação Comunitária do Rotary – 24/10 – Jacarezinho"),
            "2026-10-08 21:15",
            """
Caros amigos da Polícia Civil,

O Rotary Club de Jacarezinho promove a sua tradicional Ação Comunitária no
dia 24/10, sábado, das 8h às 14h, na Praça Rui Barbosa, centro.

Solicitamos a emissão de carteira de identidade, com coleta de digitais e
fotos para documento. Previsão de 200 atendimentos.

Companheiro Rubens Aoki Menegazzo
Presidente 2026-27 - Rotary Club de Jacarezinho
(43) 3525-0909
""",
        ),
        esperado={
            "tipo_evento": "Ação Comunitária",
            "estado": "PR",
            "municipio": "Jacarezinho",
            "local_evento": Contem("Praça Rui Barbosa"),
            "endereco": Contem("Praça Rui Barbosa"),
            "bairro": "Centro",
            "data_inicio_evento": "2026-10-24",
            "data_fim_evento": "2026-10-24",
            "data_solicitacao": "2026-10-08",
            "servicos": [_CIN, _DIG, _FOTO],
            "quantidade_cin": 200,
            "solicitante_nome": "Rubens Aoki Menegazzo",
            "solicitante_cargo_unidade": Contem("Presidente"),
            "contato": Contem("3525-0909"),
        },
        nota="'centro' em minúscula vira bairro Centro; 'Presidente 2026-27' não é data; tratamento 'Companheiro' não faz parte do nome.",
    ),
    # ------------------------------------------------------------------ 058
    Caso(
        id="sol-058",
        modulo="solicitacoes",
        formato="texto",
        agora="2026-11-12 09:00",
        texto="""Solicitação - Wenceslau Braz

Pedimos atendimento de emissão de carteira de identidade no CRAS Central
(Rua Coronel Pinto, 55 - Centro) em três sábados: dias 5, 12 e 19 de dezembro,
das 8h às 12h. Previsão de 50 carteiras por sábado.

Atenciosamente,
Gislaine Pedroso Bueno
Coordenadora do CRAS - Wenceslau Braz/PR
(43) 3528-1133
""",
        esperado={
            "estado": "PR",
            "municipio": "Wenceslau Braz",
            "local_evento": Contem("CRAS Central"),
            "endereco": Contem("Rua Coronel Pinto, 55"),
            "bairro": "Centro",
            "data_inicio_evento": "2026-12-05",
            "data_fim_evento": "2026-12-19",
            "servicos": [_CIN],
            "quantidade_cin": 150,
            "solicitante_nome": "Gislaine Pedroso Bueno",
            "solicitante_cargo_unidade": Contem("Coordenadora do CRAS"),
            "contato": Contem("3528-1133"),
        },
        nota="Três sábados separados (5, 12 e 19/12): início no primeiro, fim no último; 50 por sábado = 150.",
    ),
    # ------------------------------------------------------------------ 059
    Caso(
        id="sol-059",
        modulo="solicitacoes",
        formato="eml",
        agora="2026-10-16 10:00",
        texto=_eml(
            "Protocolo Geral PCPR <protocolo@pc.pr.gov.br>",
            _PCPR,
            "ENC: Solicitação - Ação Cidadania Campo Magro",
            "2026-10-16 08:05",
            """
Encaminho para conhecimento e providências.

Protocolo Geral - PCPR

-----Mensagem original-----
De: Secretaria de Desenvolvimento Social de Campo Magro <sds@campomagro.pr.gov.br>
Enviada em: quarta-feira, 14 de outubro de 2026 13:45
Para: protocolo@pc.pr.gov.br
Assunto: Solicitação - Ação Cidadania Campo Magro

Prezados,

Solicitamos a presença da Polícia Civil na Ação Cidadania que acontecerá no
dia 14 de novembro de 2026, no Centro Comunitário do Jardim Boa Vista -
Rua Pedro Stall, 300 - Jardim Boa Vista, com emissão de CIN e orientação
jurídica.

Atenciosamente,
Juliano Cordeiro Stall
Secretário de Desenvolvimento Social
(41) 3677-4000
""",
        ),
        esperado={
            "estado": "PR",
            "municipio": "Campo Magro",
            "local_evento": Contem("Centro Comunitário do Jardim Boa Vista"),
            "endereco": Contem("Rua Pedro Stall, 300"),
            "bairro": "Jardim Boa Vista",
            "data_inicio_evento": "2026-11-14",
            "data_fim_evento": "2026-11-14",
            "data_solicitacao": UmDe("2026-10-14", "2026-10-16"),
            "servicos": [_CIN, _JUR],
            "solicitante_nome": "Juliano Cordeiro Stall",
            "solicitante_cargo_unidade": Contem("Secretário de Desenvolvimento Social"),
            "contato": Contem("3677-4000"),
        },
        nota="'ENC:' do Outlook: o remetente do .eml é o protocolo interno; o solicitante está na mensagem original; 'dia 14' de outubro (envio) e de novembro (evento).",
    ),
    # ------------------------------------------------------------------ 060
    Caso(
        id="sol-060",
        modulo="solicitacoes",
        formato="eml",
        agora="2026-10-07 11:00",
        texto=_eml(
            "Emater Ivaiporã <ivaipora@emater.pr.gov.br>",
            _PCPR,
            "Dia de campo com cidadania - neste sábado",
            "2026-10-07 09:31",
            """
Bom dia,

Sei que o prazo é curto, mas gostaríamos de saber se é possível a equipe de
identificação comparecer neste sábado, no Dia de Campo das famílias da Vila
Rural, em Ivaiporã, na Quadra da Vila Rural (Estrada do Guarapuavinha, km 4).
Seria para emissão de carteira de identidade a umas 40 pessoas.

Obrigado,
Everaldo Sguario
Extensionista Rural - IDR-Paraná/Emater
(43) 3472-2021
""",
        ),
        esperado={
            "estado": "PR",
            "municipio": "Ivaiporã",
            "local_evento": Contem("Quadra da Vila Rural"),
            "endereco": Contem("Estrada do Guarapuavinha, km 4"),
            "data_inicio_evento": "2026-10-10",
            "data_fim_evento": "2026-10-10",
            "data_solicitacao": "2026-10-07",
            "servicos": [_CIN],
            "quantidade_cin": 40,
            "solicitante_nome": "Everaldo Sguario",
            "solicitante_cargo_unidade": Contem("Extensionista Rural"),
            "contato": Contem("3472-2021"),
        },
        nota="'neste sábado' a partir de quarta 07/10 = 10/10; 'Guarapuavinha' não é Guarapuava; '40 pessoas' para emissão = 40 carteiras.",
    ),
    # ------------------------------------------------------------------ 061
    Caso(
        id="sol-061",
        modulo="solicitacoes",
        formato="texto",
        agora="2026-10-21 09:00",
        texto="""---------- Forwarded message ---------
De: Leandro Gaio <leandro.gaio@uniaodavitoria.pr.gov.br>
Date: ter., 20 de out. de 2026 às 16:02
Subject: Semana da Pessoa Idosa - Porto União
To: <eventos.sociais@pc.pr.gov.br>


Boa tarde,

Sou servidor da Assistência Social de União da Vitória e estou ajudando a
organizar, junto com os colegas do lado catarinense, a Semana da Pessoa Idosa
de Porto União (SC). O dia de cidadania será em 03/11, no Clube 7 de Setembro,
Rua Padre Anchieta, 250 - Centro, Porto União. Muitos idosos moram de um lado
e são registrados do outro, por isso pedimos a emissão da CIN do Paraná.

Leandro Gaio
Técnico Social - SMAS União da Vitória/PR
(42) 3521-1200
""",
        esperado={
            "estado": "SC",
            "municipio": "Porto União",
            "local_evento": Contem("Clube 7 de Setembro"),
            "endereco": Contem("Rua Padre Anchieta, 250"),
            "bairro": "Centro",
            "data_inicio_evento": "2026-11-03",
            "data_fim_evento": "2026-11-03",
            "data_solicitacao": "2026-10-20",
            "servicos": [_CIN],
            "solicitante_nome": "Leandro Gaio",
            "solicitante_cargo_unidade": Contem("Técnico Social"),
            "contato": Contem("3521-1200"),
        },
        nota="Inverso do sol-024: quem pede é de União da Vitória/PR, o evento é em Porto União/SC; 'Clube 7 de Setembro' não é data; 'CIN do Paraná' não faz estado PR.",
    ),
    # ------------------------------------------------------------------ 062
    Caso(
        id="sol-062",
        modulo="solicitacoes",
        formato="eml",
        agora="2026-10-26 10:00",
        texto=_eml(
            "Sindicato dos Bancários de Curitiba <formacao@bancariosctba.org.br>",
            _PCPR,
            "Oficina: identificação de documentos falsos",
            "2026-10-26 09:02",
            """
Prezados,

O Sindicato dos Bancários solicita uma oficina de capacitação sobre
identificação de documentos falsos e a nova Carteira de Identidade Nacional,
para 120 bancários, na quinta-feira, 19 de novembro, das 18h30 às 21h30, no
Auditório da FIEP - Av. Cândido de Abreu, 200 - Centro Cívico, Curitiba.

Grata pela atenção,
Luciane Mikosz Farias
Secretária de Formação
+55 41 9 9765-4321
""",
        ),
        esperado={
            "tipo_evento": "Capacitação",
            "estado": "PR",
            "municipio": "Curitiba",
            "local_evento": Contem("Auditório da FIEP"),
            "endereco": Contem("Av. Cândido de Abreu, 200"),
            "bairro": "Centro Cívico",
            "data_inicio_evento": "2026-11-19",
            "data_fim_evento": "2026-11-19",
            "data_solicitacao": "2026-10-26",
            "servicos": [],
            "quantidade_cin": AUSENTE,
            "solicitante_nome": "Luciane Mikosz Farias",
            "solicitante_cargo_unidade": Contem("Secretária de Formação"),
            "contato": Contem("9765-4321"),
        },
        nota="CIN é tema da oficina, não serviço; 120 bancários não é CIN; telefone '+55 41 9 9765-4321'.",
    ),
    # ------------------------------------------------------------------ 063
    Caso(
        id="sol-063",
        modulo="solicitacoes",
        formato="texto",
        agora="2026-09-18 14:00",
        texto="""De: Secretaria de Assistência Social de Clevelândia
Enviado em: quinta-feira, 17 de setembro de 2026 10:20
Para: eventos.sociais@pc.pr.gov.br
Assunto: pedido de RG itinerante

Prezados,

Como no ano passado, em 12/05/2025, quando a unidade móvel esteve aqui e
atendeu 210 pessoas, gostaríamos de solicitar novamente a vinda da equipe de
identificação a Clevelândia. Estamos fechando o calendário e aguardamos a
disponibilidade de vocês para marcar a data.

Por favor responder até 30/09.

Att,
Solange Terezinha Bortoli
Secretária de Assistência Social
(46) 3252-8200
""",
        esperado={
            "estado": "PR",
            "municipio": "Clevelândia",
            "data_inicio_evento": AUSENTE,
            "data_fim_evento": AUSENTE,
            "data_solicitacao": "2026-09-17",
            "local_evento": AUSENTE,
            "servicos": [_CIN],
            "quantidade_cin": AUSENTE,
            "unidade_movel": True,
            "solicitante_nome": "Solange Terezinha Bortoli",
            "solicitante_cargo_unidade": Contem("Secretária de Assistência Social"),
            "contato": Contem("3252-8200"),
        },
        nota="Só datas-armadilha: evento anterior (12/05/2025), prazo (30/09) e envio; 210 pessoas do ano passado não é quantidade.",
    ),
    # ------------------------------------------------------------------ 064
    Caso(
        id="sol-064",
        modulo="solicitacoes",
        formato="eml",
        agora="2026-09-24 16:00",
        texto=_eml(
            "Câmara Municipal de Guaíra <camara@guaira.pr.leg.br>",
            _PCPR,
            "Palestra - violência contra a pessoa idosa",
            "2026-09-24 14:10",
            """
Senhores,

A Câmara Municipal de Guaíra/PR, por iniciativa da Comissão de Direitos
Humanos, convida a Polícia Civil para proferir palestra sobre violência
contra a pessoa idosa, no dia 9 de outubro, sexta-feira, às 8h30, no Plenário
da Câmara, Rua Otávio Tosta, 126, Centro.

Atenciosamente,
Vereadora Marlene Hoffmeister Arce
Presidente da Comissão de Direitos Humanos
(44) 3642-1340
""",
        ),
        esperado={
            "tipo_evento": "Palestra",
            "estado": "PR",
            "municipio": "Guaíra",
            "local_evento": Contem("Plenário da Câmara"),
            "endereco": Contem("Rua Otávio Tosta, 126"),
            "bairro": "Centro",
            "data_inicio_evento": "2026-10-09",
            "data_fim_evento": "2026-10-09",
            "data_solicitacao": "2026-09-24",
            "servicos": [],
            "solicitante_nome": "Marlene Hoffmeister Arce",
            "solicitante_cargo_unidade": Contem("Presidente da Comissão de Direitos Humanos"),
            "contato": Contem("3642-1340"),
        },
        nota="Agora 'Guaíra' é o município (em sol-022 era bairro de Curitiba); '8h30' é horário; 'Vereadora' é tratamento.",
    ),
    # ------------------------------------------------------------------ 065
    Caso(
        id="sol-065",
        modulo="solicitacoes",
        formato="texto",
        agora="2026-11-04 08:00",
        texto="""[03/11/2026 20:05] +55 44 99876-5432: Boa noite, desculpe o horário
[03/11/2026 20:06] +55 44 99876-5432: Sou a Neide Vasconcelos do CRAS Jardim São Jorge de Paranavaí
[03/11/2026 20:06] +55 44 99876-5432: Queria agendar o pessoal do RG pra fazer carteira aqui no sábado 14/11
[03/11/2026 20:07] +55 44 99876-5432: é no próprio CRAS, rua Antônio Felipe, 1520, Jardim São Jorge
[03/11/2026 20:08] +55 44 99876-5432: acho que umas 80 carteiras
""",
        esperado={
            "estado": "PR",
            "municipio": "Paranavaí",
            "local_evento": Contem("CRAS Jardim São Jorge"),
            "endereco": Contem("Antônio Felipe, 1520"),
            "bairro": "Jardim São Jorge",
            "data_inicio_evento": "2026-11-14",
            "data_fim_evento": "2026-11-14",
            "data_solicitacao": "2026-11-03",
            "servicos": [_CIN],
            "quantidade_cin": 80,
            "solicitante_nome": "Neide Vasconcelos",
            "solicitante_cargo_unidade": Contem("CRAS"),
            "contato": Contem("99876-5432"),
        },
        nota="Remetente do WhatsApp é só o número; o nome está no texto; município no meio da frase depois do nome do CRAS.",
    ),
    # ------------------------------------------------------------------ 066
    Caso(
        id="sol-066",
        modulo="solicitacoes",
        formato="eml",
        agora="2026-09-25 13:30",
        texto=_eml(
            "Expo Medianeira <contato@expomedianeira.com.br>",
            _PCPR,
            "Expo Medianeira 2026 - participação PCPR",
            "2026-09-25 11:48",
            """
Prezados,

A Expo Medianeira 2026 acontece de 20 a 22/10 no Parque de Exposições Ney
Braga, Av. Brasília, 3500, Jardim Irene, Medianeira. Convidamos a PCPR a
levar a exposição de viaturas antigas e modernas, que foi o sucesso da
edição de 2024.

Atenciosamente,
Cristiane Dalla Costa Weber
Coordenadora da Expo Medianeira
(45) 3264-7878
""",
        ),
        esperado={
            "tipo_evento": "Feira",
            "estado": "PR",
            "municipio": "Medianeira",
            "local_evento": Contem("Parque de Exposições Ney Braga"),
            "endereco": Contem("Av. Brasília, 3500"),
            "bairro": "Jardim Irene",
            "data_inicio_evento": "2026-10-20",
            "data_fim_evento": "2026-10-22",
            "data_solicitacao": "2026-09-25",
            "servicos": [_VTR],
            "solicitante_nome": "Cristiane Dalla Costa Weber",
            "solicitante_cargo_unidade": Contem("Coordenadora"),
            "contato": Contem("3264-7878"),
        },
        nota="'de 20 a 22/10'; 'Av. Brasília' não é cidade; edição de 2024 citada.",
    ),
    # ------------------------------------------------------------------ 067
    Caso(
        id="sol-067",
        modulo="solicitacoes",
        formato="eml",
        agora="2026-10-20 10:00",
        texto=_eml(
            "Núcleo de Polícia Comunitária de Cascavel <npc.cascavel@pc.pr.gov.br>",
            _PCPR,
            _q("PCPR na Comunidade – bairro Cataratas – Cascavel"),
            "2026-10-19 15:25",
            """
Prezados,

Solicitamos a inclusão no calendário do PCPR na Comunidade de uma edição no
bairro Cataratas, em Cascavel, no dia 07/11, sábado, das 9h às 15h, na Escola
Municipal Aníbal Lopes da Silva, Rua Foz do Iguaçu, 1800 - Cataratas.

Serviços: emissão de CIN, fotos e orientação jurídica. Previsão de
atendimento: cerca de 300 pessoas.

Investigadora Carla Beatriz Nascimento
Núcleo de Polícia Comunitária - 15ª SDP Cascavel
(45) 3218-3300
""",
        ),
        esperado={
            "tipo_evento": "PCPR na Comunidade",
            "estado": "PR",
            "municipio": "Cascavel",
            "local_evento": Contem("Escola Municipal Aníbal Lopes da Silva"),
            "endereco": Contem("Rua Foz do Iguaçu, 1800"),
            "bairro": "Cataratas",
            "data_inicio_evento": "2026-11-07",
            "data_fim_evento": "2026-11-07",
            "data_solicitacao": "2026-10-19",
            "servicos": [_CIN, _FOTO, _JUR],
            "quantidade_cin": 300,
            "solicitante_nome": "Carla Beatriz Nascimento",
            "solicitante_cargo_unidade": Contem("Núcleo de Polícia Comunitária"),
            "contato": Contem("3218-3300"),
        },
        nota="'Rua Foz do Iguaçu' e bairro 'Cataratas' puxam para Foz: o município é Cascavel; 'atendimento de cerca de 300 pessoas' = atendimentos.",
    ),
    # ------------------------------------------------------------------ 068
    Caso(
        id="sol-068",
        modulo="solicitacoes",
        formato="texto",
        agora="2026-10-23 09:00",
        texto="""bom dia pcpr aqui é do sindicato dos trabalhadores rurais de loanda nos queremos
fazer um dia de documentacao pros trabalhadores rurais dia 14 de novembro na sede
do sindicato rua sao paulo 612 centro precisa fazer rg de umas 100 pessoas e tirar
as digital tambem
ATT JOSE ROBERTO PANIAGO PRESIDENTE 44 3425-1717
""",
        esperado={
            "estado": "PR",
            "municipio": "Loanda",
            "local_evento": Contem("Sindicato"),
            "endereco": Contem("Rua São Paulo 612"),
            "bairro": "Centro",
            "data_inicio_evento": "2026-11-14",
            "data_fim_evento": "2026-11-14",
            "servicos": [_CIN, _DIG],
            "quantidade_cin": 100,
            "solicitante_nome": "José Roberto Paniago",
            "solicitante_cargo_unidade": Contem("Presidente"),
            "contato": Contem("3425-1717"),
        },
        nota="Sem pontuação nem acento; 'rua sao paulo' não é município; 'rg de umas 100 pessoas' = 100 carteiras.",
    ),
    # ------------------------------------------------------------------ 069
    Caso(
        id="sol-069",
        modulo="solicitacoes",
        formato="eml",
        agora="2026-11-05 10:00",
        texto=_eml(
            "Paraná em Ação <paranaemacao@seju.pr.gov.br>",
            _PCPR,
            _q("Paraná em Ação – Goioerê – programação e serviços"),
            "2026-11-04 17:40",
            """
PARANÁ EM AÇÃO - GOIOERÊ

Datas: 4 e 5 de dezembro de 2026
Horário: 8h às 17h
Local: Ginásio de Esportes Rubens Moreira, Rua Rio Grande do Sul, 1270 - Centro
CEP: 87360-000

Serviços solicitados à Polícia Civil do Paraná:
- Emissão da Carteira de Identidade Nacional (CIN)
- Coleta de digitais
- Fotografia para documento

Previsão: 500 CINs.

Outros parceiros: Sanepar, Copel, Detran, Defensoria Pública.

Fernanda Scheffer Guimarães
Coordenadora Executiva - Paraná em Ação
(41) 3221-7300
""",
            html=True,
        ),
        esperado={
            "tipo_evento": "Paraná em Ação",
            "estado": "PR",
            "municipio": "Goioerê",
            "local_evento": Contem("Ginásio de Esportes Rubens Moreira"),
            "endereco": Contem("Rua Rio Grande do Sul, 1270"),
            "bairro": "Centro",
            "cep": "87360-000",
            "data_inicio_evento": "2026-12-04",
            "data_fim_evento": "2026-12-05",
            "data_solicitacao": "2026-11-04",
            "servicos": [_CIN, _DIG, _FOTO],
            "quantidade_cin": 500,
            "solicitante_nome": "Fernanda Scheffer Guimarães",
            "solicitante_cargo_unidade": Contem("Coordenadora Executiva"),
            "contato": Contem("3221-7300"),
        },
        nota="Formato de ficha em tópicos; CEP em linha separada; parceiros (Defensoria) não viram serviço de orientação jurídica da PCPR.",
    ),
    # ------------------------------------------------------------------ 070
    Caso(
        id="sol-070",
        modulo="solicitacoes",
        formato="eml",
        agora="2026-10-22 15:00",
        texto=_eml(
            "CREAS Pitanga <creas@pitanga.pr.gov.br>",
            _PCPR,
            "roda de conversa lei maria da penha",
            "2026-10-22 11:20",
            """
Olá,

Gostaríamos de uma roda de conversa sobre a Lei Maria da Penha com as mulheres
do grupo de fortalecimento de vínculos do CREAS, na terça-feira, dia 3, às 14h,
aqui no CREAS de Pitanga (Rua Dr. Afonso Camargo, 88).

Obrigada
Tatiane Lustosa Ribeiro - psicóloga do CREAS
42 3646-2255
""",
        ),
        esperado={
            "tipo_evento": "Palestra",
            "estado": "PR",
            "municipio": "Pitanga",
            "local_evento": Contem("CREAS"),
            "endereco": Contem("Rua Dr. Afonso Camargo, 88"),
            "data_inicio_evento": "2026-11-03",
            "data_fim_evento": "2026-11-03",
            "data_solicitacao": "2026-10-22",
            "servicos": [],
            "solicitante_nome": "Tatiane Lustosa Ribeiro",
            "solicitante_cargo_unidade": Contem("psicóloga"),
            "contato": Contem("3646-2255"),
        },
        nota="'terça-feira, dia 3' lido em 22/10: é 03/11 (o dia 3 de outubro já passou e era sábado).",
    ),
    # ------------------------------------------------------------------ 071
    Caso(
        id="sol-071",
        modulo="solicitacoes",
        formato="texto",
        agora="2026-11-06 09:00",
        texto="""De: Assistência Social Prudentópolis <social@prudentopolis.pr.gov.br>
Enviado em: quinta-feira, 5 de novembro de 2026 14:12
Para: Eventos Sociais PCPR
Assunto: RES: RES: Ação de cidadania - Prudentópolis

Bom dia! Só uma alteração: por causa da reforma do ginásio, a ação do dia
19/11 vai ser no Salão Paroquial São Josafat (Rua Visconde de Guarapuava,
1150 - Centro). O resto continua igual.

Irene Kotviski Hul
Diretora de Assistência Social
(42) 3446-8030

________________________________
De: Eventos Sociais PCPR
Enviado: terça-feira, 3 de novembro de 2026 10:00
Assunto: RES: Ação de cidadania - Prudentópolis

Irene, confirmamos a emissão de CIN no dia 19/11. Por favor, confirme o local.

________________________________
De: Assistência Social Prudentópolis
Enviado: sexta-feira, 30 de outubro de 2026 16:45
Assunto: Ação de cidadania - Prudentópolis

Solicitamos a emissão de carteiras de identidade na ação de cidadania do dia
19/11, no Ginásio Municipal Pedro Siqueira, Rua São Josafat, 2000.
Previsão de 160 carteiras.
""",
        esperado={
            "estado": "PR",
            "municipio": "Prudentópolis",
            "local_evento": Contem("Salão Paroquial São Josafat"),
            "endereco": Contem("Rua Visconde de Guarapuava, 1150"),
            "bairro": "Centro",
            "data_inicio_evento": "2026-11-19",
            "data_fim_evento": "2026-11-19",
            "data_solicitacao": UmDe("2026-10-30", "2026-11-05"),
            "servicos": [_CIN],
            "quantidade_cin": 160,
            "solicitante_nome": "Irene Kotviski Hul",
            "solicitante_cargo_unidade": Contem("Diretora de Assistência Social"),
            "contato": Contem("3446-8030"),
        },
        nota="Local mudou na resposta mais nova (Salão Paroquial), o ginásio da mensagem citada não vale; 'Rua Visconde de Guarapuava' não é o município.",
    ),
    # ------------------------------------------------------------------ 072
    Caso(
        id="sol-072",
        modulo="solicitacoes",
        formato="eml",
        agora="2026-11-09 10:00",
        texto=_eml(
            "Colégio de Diretores de Identificação <secretaria@codiid.org.br>",
            "Diretores de Identificação <diretores@codiid.org.br>",
            _q("Convocação – Reunião Ordinária – Florianópolis/SC – 10 e 11/12"),
            "2026-11-06 12:00",
            """
Senhores Diretores,

Convocamos para a Reunião Ordinária do Colégio de Diretores de Identificação,
nos dias 10 e 11 de dezembro de 2026, no Hotel Majestic, Av. Jornalista Rubens
de Arruda Ramos, 2746 - Centro, Florianópolis/SC.

Pedimos a presença do Diretor do Instituto de Identificação do Paraná ou de
representante indicado.

Secretaria Executiva
Ana Cristina Beck Sell
(48) 3665-1010
""",
        ),
        esperado={
            "tipo_evento": "Reunião",
            "estado": "SC",
            "municipio": "Florianópolis",
            "local_evento": Contem("Hotel Majestic"),
            "endereco": Contem("Av. Jornalista Rubens de Arruda Ramos, 2746"),
            "bairro": "Centro",
            "data_inicio_evento": "2026-12-10",
            "data_fim_evento": "2026-12-11",
            "data_solicitacao": "2026-11-06",
            "servicos": [],
            "solicitante_nome": "Ana Cristina Beck Sell",
            "solicitante_cargo_unidade": Contem("Secretaria Executiva"),
            "contato": Contem("3665-1010"),
        },
        nota="Reunião em SC; 'Instituto de Identificação do Paraná' é o convidado, não faz o estado ser PR.",
    ),
    # ------------------------------------------------------------------ 073
    Caso(
        id="sol-073",
        modulo="solicitacoes",
        formato="texto",
        agora="2026-11-18 20:00",
        texto="""[18/11/2026 19:40] Vilmar Cambará: boa noite
[18/11/2026 19:41] Vilmar Cambará: dia 5/12 tem o Natal no Parque aqui em Cambará, no Parque Ecológico Municipal, Av. Brasil nº 45, bairro Jardim América
[18/11/2026 19:41] Vilmar Cambará: dá pra levar a van da identificação pra fazer RG?
[18/11/2026 19:43] Vilmar Cambará: Vilmar Pedro Stocco, secretário de esporte e lazer
""",
        esperado={
            "estado": "PR",
            "municipio": "Cambará",
            "local_evento": Contem("Parque Ecológico Municipal"),
            "endereco": Contem("Av. Brasil nº 45"),
            "bairro": "Jardim América",
            "data_inicio_evento": "2026-12-05",
            "data_fim_evento": "2026-12-05",
            "data_solicitacao": "2026-11-18",
            "servicos": [_CIN],
            "unidade_movel": True,
            "solicitante_nome": "Vilmar Pedro Stocco",
            "solicitante_cargo_unidade": Contem("secretário de esporte e lazer"),
        },
        nota="'Natal no Parque' não é data de Natal; 'van da identificação' = unidade móvel; sem telefone escrito (só o do WhatsApp, que não aparece).",
    ),
    # ------------------------------------------------------------------ 074
    Caso(
        id="sol-074",
        modulo="solicitacoes",
        formato="eml",
        agora="2026-10-23 08:00",
        texto=_eml(
            "CRAS Sarandi <cras.sarandi@sarandi.pr.gov.br>",
            _PCPR,
            "URGENTE - ação amanhã",
            "2026-10-22 17:10",
            """
Boa tarde, desculpe a urgência!

A equipe que viria amanhã (sexta) para a ação no CRAS Jardim Independência
(Rua Tamoios, 850) ainda não confirmou. Continua de pé? São 60 pessoas
agendadas para fazer a carteira de identidade.

Rosely Gimenes Tavares
Coordenadora do CRAS - Sarandi
(44) 3264-0101
""",
        ),
        esperado={
            "estado": "PR",
            "municipio": "Sarandi",
            "local_evento": Contem("CRAS Jardim Independência"),
            "endereco": Contem("Rua Tamoios, 850"),
            "data_inicio_evento": "2026-10-23",
            "data_fim_evento": "2026-10-23",
            "data_solicitacao": "2026-10-22",
            "servicos": [_CIN],
            "quantidade_cin": 60,
            "solicitante_nome": "Rosely Gimenes Tavares",
            "solicitante_cargo_unidade": Contem("Coordenadora do CRAS"),
            "contato": Contem("3264-0101"),
        },
        nota="'amanhã (sexta)' é relativo ao envio (quinta 22/10), não ao agora (sexta 23/10): o evento é 23/10.",
    ),
    # ------------------------------------------------------------------ 075
    Caso(
        id="sol-075",
        modulo="solicitacoes",
        formato="eml",
        agora="2026-10-14 10:00",
        texto=_eml(
            "Prefeitura de Assaí <gabinete@assai.pr.gov.br>",
            _PCPR,
            "Solicitação de unidade móvel",
            "2026-10-13 15:55",
            """
Prezados,

O Município de Assaí solicita a unidade móvel da Polícia Civil nos dias
20/11/2026 e 21/11/2026, na Praça da Bíblia (Av. Rio de Janeiro, s/n - Centro),
durante o Festival Nipo-Brasileiro.

Atenciosamente,
Hiroshi Yamaguchi Neto
Chefe de Gabinete
(43) 3262-1122
""",
        ),
        esperado={
            "estado": "PR",
            "municipio": "Assaí",
            "local_evento": Contem("Praça da Bíblia"),
            "endereco": Contem("Av. Rio de Janeiro, s/n"),
            "bairro": "Centro",
            "data_inicio_evento": "2026-11-20",
            "data_fim_evento": "2026-11-21",
            "data_solicitacao": "2026-10-13",
            "unidade_movel": True,
            "solicitante_nome": "Hiroshi Yamaguchi Neto",
            "solicitante_cargo_unidade": Contem("Chefe de Gabinete"),
            "contato": Contem("3262-1122"),
        },
        nota="Só 'unidade móvel', sem dizer quais serviços (fica fora); 'Av. Rio de Janeiro' não é município; datas completas com ano.",
    ),
    # ------------------------------------------------------------------ 076
    Caso(
        id="sol-076",
        modulo="solicitacoes",
        formato="eml",
        agora="2026-10-28 11:00",
        texto=_eml(
            "=?utf-8?b?Q29uc2VsaG8gZGEgTXVsaGVyIGRlIFJlYWxlemE=?= <cmm@realeza.pr.gov.br>",
            _PCPR,
            _q("1º Encontro Regional de Mulheres – pedido de apoio"),
            "2026-10-27 10:30",
            """
Prezadas e prezados,

No 1º Encontro Regional de Mulheres do Sudoeste, no sábado, 21 de novembro de
2026, no Salão da Comunidade Evangélica de Realeza (Rua Belém, 1300 - Centro),
gostaríamos de ter uma palestra de uma delegada sobre medidas protetivas e
também a emissão de carteira de identidade para as participantes que
precisarem, com fotografia no local.

Esperamos cerca de 400 mulheres de 15 municípios.

Com carinho,
Vera Lúcia Rigo Dalmolin
Presidente do Conselho Municipal dos Direitos da Mulher
(46) 3543-1234
""",
        ),
        esperado={
            "estado": "PR",
            "municipio": "Realeza",
            "local_evento": Contem("Salão da Comunidade Evangélica"),
            "endereco": Contem("Rua Belém, 1300"),
            "bairro": "Centro",
            "data_inicio_evento": "2026-11-21",
            "data_fim_evento": "2026-11-21",
            "data_solicitacao": "2026-10-27",
            "servicos": [_CIN, _FOTO],
            "quantidade_cin": AUSENTE,
            "solicitante_nome": "Vera Lúcia Rigo Dalmolin",
            "solicitante_cargo_unidade": Contem("Presidente do Conselho Municipal dos Direitos da Mulher"),
            "contato": Contem("3543-1234"),
        },
        nota="Remetente codificado em base64; pedido misto (palestra + CIN) sem tipo inequívoco; 400 mulheres é público, não CIN; 'Rua Belém' não é cidade.",
    ),
    # ------------------------------------------------------------------ 077
    Caso(
        id="sol-077",
        modulo="solicitacoes",
        formato="texto",
        agora="2026-11-02 10:00",
        texto="""Prezados,

A Escola Municipal Maria Marli Piovesan, no Boqueirão, em Curitiba, solicita a
vinda da equipe de identificação para fazer a carteira de identidade dos
alunos do 1º ao 5º ano. Pode ser semana que vem na quarta, das 8h às 11h30.
Previsão de 150 carteiras.

Endereço: Rua Bley Zornig, 3000 - Boqueirão.

Diretora Kelly Cristina Anjos
(41) 3316-0808
""",
        esperado={
            "estado": "PR",
            "municipio": "Curitiba",
            "local_evento": Contem("Escola Municipal Maria Marli Piovesan"),
            "endereco": Contem("Rua Bley Zornig, 3000"),
            "bairro": "Boqueirão",
            "data_inicio_evento": "2026-11-11",
            "data_fim_evento": "2026-11-11",
            "servicos": [_CIN],
            "quantidade_cin": 150,
            "solicitante_nome": "Kelly Cristina Anjos",
            "solicitante_cargo_unidade": Contem("Diretora"),
            "contato": Contem("3316-0808"),
        },
        nota="Texto puro sem data de envio: 'semana que vem na quarta' pelo agora (segunda 02/11) = 11/11; horário 11h30.",
    ),
    # ------------------------------------------------------------------ 078
    Caso(
        id="sol-078",
        modulo="solicitacoes",
        formato="eml",
        agora="2026-11-24 09:00",
        texto=_eml(
            "Gabinete - Sertanópolis <gabinete@sertanopolis.pr.gov.br>",
            _PCPR,
            "Ofício 145/2026 - Inauguração do Posto de Identificação",
            "2026-11-23 10:10",
            """
Sertanópolis, 20 de novembro de 2026.

Ofício nº 145/2026 - GAB

Excelentíssimo Senhor Delegado-Geral,

Temos a honra de convidar Vossa Excelência para a solenidade de inauguração do
Posto de Identificação de Sertanópolis, fruto do convênio firmado com a Polícia
Civil do Paraná em 15/06/2026, a realizar-se em 15/12/2026, às 10h, no Posto de
Atendimento ao Cidadão, Rua Tiradentes, 330, Centro.

Respeitosamente,

LUIZ FERNANDO BASSO
Prefeito Municipal
(43) 3232-1300
""",
        ),
        esperado={
            "tipo_evento": "Inauguração/Solenidade",
            "estado": "PR",
            "municipio": "Sertanópolis",
            "local_evento": Contem("Posto de Atendimento ao Cidadão"),
            "endereco": Contem("Rua Tiradentes, 330"),
            "bairro": "Centro",
            "data_inicio_evento": "2026-12-15",
            "data_fim_evento": "2026-12-15",
            "data_solicitacao": UmDe("2026-11-20", "2026-11-23"),
            "servicos": [],
            "solicitante_nome": "Luiz Fernando Basso",
            "solicitante_cargo_unidade": Contem("Prefeito"),
            "contato": Contem("3232-1300"),
        },
        nota="Três datas: ofício (20/11), convênio (15/06) e solenidade (15/12); nome em CAIXA ALTA; 'Rua Tiradentes' não é data.",
    ),
    # ------------------------------------------------------------------ 079
    Caso(
        id="sol-079",
        modulo="solicitacoes",
        formato="eml",
        agora="2026-10-26 09:30",
        texto=_eml(
            "Assistência Social Colorado <social@colorado.pr.gov.br>",
            _PCPR,
            "Colorado Cidadão - 21/11",
            "2026-10-26 08:44",
            """
Bom dia,

Segue o cronograma do "Colorado Cidadão":

- Inscrições das famílias: até 10/11
- Reunião preparatória com os parceiros: 13/11, às 9h, na Prefeitura
- Dia da ação: 21/11 (sábado), das 8h às 16h

Local da ação: Centro de Convivência, Av. Brasil nº 45, bairro Jardim América,
Colorado/PR.

Pedimos a emissão de RG, coleta de digitais e fotos. Hoje já temos 190
famílias inscritas, com previsão de 260 carteiras.

Atenciosamente,
Neiva Cardoso Lanzoni
Secretária de Assistência Social
(44) 3323-1414
""",
            html=True,
        ),
        esperado={
            "estado": "PR",
            "municipio": "Colorado",
            "local_evento": Contem("Centro de Convivência"),
            "endereco": Contem("Av. Brasil nº 45"),
            "bairro": "Jardim América",
            "data_inicio_evento": "2026-11-21",
            "data_fim_evento": "2026-11-21",
            "data_solicitacao": "2026-10-26",
            "servicos": [_CIN, _DIG, _FOTO],
            "quantidade_cin": 260,
            "solicitante_nome": "Neiva Cardoso Lanzoni",
            "solicitante_cargo_unidade": Contem("Secretária de Assistência Social"),
            "contato": Contem("3323-1414"),
        },
        nota="Cronograma com várias datas (inscrições, reunião preparatória): só o dia da ação vale; 190 famílias ≠ 260 carteiras.",
    ),
    # ------------------------------------------------------------------ 080
    Caso(
        id="sol-080",
        modulo="solicitacoes",
        formato="texto",
        agora="2026-10-09 14:00",
        texto="""De: Coordenação Paraná em Ação
Enviado em: quinta-feira, 8 de outubro de 2026 17:33
Para: 'Eventos Sociais PCPR'
Assunto: Paraná em Ação Bituruna

Senhores,

Informamos que o Paraná em Ação de Bituruna foi confirmado para 27 e 28 de
novembro, no Ginásio Municipal Tancredo Neves (Rua Padre Pedro Bortolini, 250
- Centro). Solicitamos a unidade móvel com emissão de CIN, previsão de 350
atendimentos, e a exposição de viaturas no sábado.

Fernanda Scheffer Guimarães
Coordenadora Executiva
""",
        esperado={
            "tipo_evento": "Paraná em Ação",
            "estado": "PR",
            "municipio": "Bituruna",
            "local_evento": Contem("Ginásio Municipal Tancredo Neves"),
            "endereco": Contem("Rua Padre Pedro Bortolini, 250"),
            "bairro": "Centro",
            "data_inicio_evento": "2026-11-27",
            "data_fim_evento": "2026-11-28",
            "data_solicitacao": "2026-10-08",
            "servicos": [_CIN, _VTR],
            "quantidade_cin": 350,
            "unidade_movel": True,
            "solicitante_nome": "Fernanda Scheffer Guimarães",
            "solicitante_cargo_unidade": Contem("Coordenadora Executiva"),
        },
        nota="Outlook sem e-mail do remetente e sem telefone; 'Tancredo Neves' é nome do ginásio.",
    ),
