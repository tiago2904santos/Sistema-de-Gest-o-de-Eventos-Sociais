"""Bateria do módulo `coffee_break` (Solicitação de coffee break).

Unidades da PCPR (delegacias, SDPs, divisões, Escola Superior de Polícia
Civil) pedem à ASCOM kits de lanche/coffee break para cursos, reuniões,
formaturas e operações. Todos os nomes, telefones, e-mails e endereços são
inventados.

Convenções do gabarito deste módulo:

- ``data_solicitacao``: a data em que o pedido foi feito (data do e-mail,
  do "Enviado em:", da mensagem do WhatsApp ou do ofício). Quando duas
  existem e diferem (ofício x e-mail, original x encaminhado), as duas
  valem (`UmDe`). Texto colado sem data do pedido: fora do gabarito.
- ``data_inicio_evento`` / ``horario_evento``: o dia e a hora do coffee
  (da entrega). Horário do curso/da abertura não é o do coffee.
- ``quantidade``: pessoas ou kits. Com dois lotes ("50 hoje e 20 amanhã"),
  vale o primeiro (anotado na `nota`).
- ``endereco`` / ``bairro`` / ``cep``: do LOCAL DE ENTREGA. Endereço da
  assinatura do remetente não é local de entrega (AUSENTE).
- ``municipio``: onde o coffee é entregue, nunca a cidade da assinatura, do
  cabeçalho do ofício ou de um nome de rua.
"""

from datetime import datetime, timedelta, timezone
from email.charset import QP, Charset
from email.header import Header
from email.utils import format_datetime
from html import escape

from . import AUSENTE, Caso, Contem, UmDe

_BRT = timezone(timedelta(hours=-3))


def _q(assunto):
    """Assunto codificado em quoted-printable (=?utf-8?q?...?=)."""
    cs = Charset("utf-8")
    cs.header_encoding = QP
    return Header(assunto, cs).encode()


def _eml(de, para, assunto, enviado, corpo, *, html=False, cc=None):
    """Monta um .eml (RFC 822). `enviado`: "2026-09-24 09:12" (Brasília)."""
    dt = datetime.strptime(enviado, "%Y-%m-%d %H:%M").replace(tzinfo=_BRT)
    cab = [f"From: {de}", f"To: {para}"]
    if cc:
        cab.append(f"Cc: {cc}")
    cab += [
        f"Subject: {assunto}",
        f"Date: {format_datetime(dt)}",
        f"Message-ID: <{dt:%Y%m%d%H%M}.{sum(map(ord, corpo)) % 10**8}@mail.exemplo.test>",
        "MIME-Version: 1.0",
    ]
    corpo = corpo.strip("\n") + "\n"
    if not html:
        cab += ["Content-Type: text/plain; charset=utf-8", "Content-Transfer-Encoding: 8bit"]
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


_ASCOM = "ASCOM PCPR <ascom.coffee@pc.pr.gov.br>"

_SIGILO = (
    "AVISO DE CONFIDENCIALIDADE: Esta mensagem e seus anexos são de uso exclusivo "
    "do destinatário e podem conter informações sigilosas, protegidas pela Lei "
    "13.709/2018. Se você a recebeu por engano, apague-a e avise o remetente."
)

CADASTROS = {}

CASOS = [
    Caso(
        id="cof-001",
        modulo="coffee_break",
        formato="eml",
        agora="2026-09-14 10:00",
        texto=_eml(
            "Dr. Ricardo Albuquerque Menezes – 7ª SDP <ricardo.menezes@pc.pr.gov.br>",
            _ASCOM,
            "Solicitação de coffee break - Curso de Atualização em Inquéritos",
            "2026-09-14 09:20",
            """
Prezados, bom dia.

Solicito, por gentileza, coffee break para 40 pessoas, referente ao Curso de
Atualização em Inquéritos, no dia 22/10 às 15h.

Local de entrega: Auditório da 7ª SDP – Rua Doutor Muricy, 1150 - Centro,
Ponta Grossa.
Responsável pelo recebimento: Escrivã Juliana Prado, (42) 3222-1100.

Atenciosamente,

Ricardo Albuquerque Menezes
Delegado de Polícia – 7ª SDP
""",
        ),
        esperado={
            "descricao_evento": Contem("Curso de Atualização em Inquéritos"),
            "data_inicio_evento": "2026-10-22",
            "horario_evento": "15:00",
            "quantidade": 40,
            "municipio": "Ponta Grossa",
            "local_entrega": Contem("Auditório da 7ª SDP"),
            "responsavel_recebimento": Contem("Juliana Prado"),
            "endereco": Contem("Rua Doutor Muricy, 1150"),
            "bairro": "Centro",
            "data_solicitacao": "2026-09-14",
        },
        nota="Caso-base, tudo explícito; ano do evento vem do agora.",
    ),
    Caso(
        id="cof-002",
        modulo="coffee_break",
        formato="eml",
        agora="2026-10-01 08:30",
        texto=_eml(
            "Coordenação de Ensino ESPC <ensino.espc@pc.pr.gov.br>",
            _ASCOM,
            _q("Pedido de coffee – Formatura Turma Investigadores"),
            "2026-09-30 16:48",
            """
Boa tarde!

A Escola Superior de Polícia Civil solicita coffee break para a Formatura da
Turma de Investigadores, que ocorrerá dia 20 de outubro, das 8h às 12h.
Serão 2 turmas de 25 alunos. O coffee deve ser servido no intervalo das 10h.

Entrega: Escola Superior de Polícia Civil, Rua Professor Algacyr Munhoz Mader,
2800 – Cidade Industrial, Curitiba – CEP 81350-010.
Quem recebe: Investigador Paulo Henrique Sautchuk.

Coordenação de Ensino – ESPC
Ramal 4402
""",
        ),
        esperado={
            "descricao_evento": Contem("Formatura"),
            "data_inicio_evento": "2026-10-20",
            "horario_evento": "10:00",
            "quantidade": 50,
            "municipio": "Curitiba",
            "local_entrega": Contem("Escola Superior de Polícia Civil"),
            "responsavel_recebimento": Contem("Paulo Henrique Sautchuk"),
            "endereco": Contem("Rua Professor Algacyr Munhoz Mader, 2800"),
            "bairro": "Cidade Industrial",
            "cep": "81350-010",
            "data_solicitacao": "2026-09-30",
        },
        nota="Assunto QP; 2 turmas de 25 = 50; horário do coffee (10h), não do início do curso (8h).",
    ),
    Caso(
        id="cof-003",
        modulo="coffee_break",
        formato="texto",
        agora="2026-10-05 15:00",
        texto="""
De: Escrivã Márcia Kloster <marcia.kloster@pc.pr.gov.br>
Enviado em: segunda-feira, 5 de outubro de 2026 14:12
Para: ASCOM Coffee
Assunto: coffee reunião delegados regionais

Boa tarde,

Vamos realizar a Reunião dos Delegados Regionais do Oeste na quinta-feira,
15/10, às 9h30. Precisamos de coffee break para cerca de 60 pessoas.

Local: sede da 15ª SDP em Cascavel, Rua Paraná, 3056 - Centro.
Receber com a própria escrivã Márcia (45) 3218-7700.

Obrigada
Márcia Kloster
Escrivã de Polícia – 15ª SDP
""",
        esperado={
            "descricao_evento": Contem("Reunião dos Delegados Regionais"),
            "data_inicio_evento": "2026-10-15",
            "horario_evento": "09:30",
            "quantidade": 60,
            "municipio": "Cascavel",
            "local_entrega": Contem("15ª SDP"),
            "responsavel_recebimento": Contem("Márcia"),
            "endereco": Contem("Rua Paraná, 3056"),
            "bairro": "Centro",
            "data_solicitacao": "2026-10-05",
        },
        nota="Outlook colado; 'cerca de 60' = 60; data de envio (05/10) ≠ evento.",
    ),
    Caso(
        id="cof-004",
        modulo="coffee_break",
        formato="texto",
        agora="2026-09-08 11:00",
        texto="""
[08/09/2026 10:41] Investigador Rogério Bach: bom dia pessoal da ascom
[08/09/2026 10:42] Investigador Rogério Bach: precisamos de coffee p amanhã, kits para 30, é o treinamento de tiro aqui no stand de tiro da 4ª SDP em Guarapuava
[08/09/2026 10:42] Investigador Rogério Bach: entregar 14h, eu mesmo recebo
""",
        esperado={
            "descricao_evento": Contem("treinamento de tiro"),
            "data_inicio_evento": "2026-09-09",
            "horario_evento": "14:00",
            "quantidade": 30,
            "municipio": "Guarapuava",
            "local_entrega": Contem("stand de tiro"),
            "responsavel_recebimento": Contem("Rogério"),
            "data_solicitacao": "2026-09-08",
        },
        nota="WhatsApp; 'amanhã' relativo à mensagem; 'kits para 30'.",
    ),
    Caso(
        id="cof-005",
        modulo="coffee_break",
        formato="eml",
        agora="2026-10-19 17:00",
        texto=_eml(
            "Delegada Fernanda Ribas <fernanda.ribas@pc.pr.gov.br>",
            _ASCOM,
            "Coffee break - Palestra Lei Maria da Penha",
            "2026-10-19 15:22",
            """
Prezados,

Solicito coffee break para quarenta pessoas na Palestra "Violência Doméstica e
Lei Maria da Penha", no dia 03 de novembro. A palestra começa às 14h e o coffee
será servido às 15h30.

Local de entrega: Delegacia da Mulher de Londrina
Av. Duque de Caxias, 1000 - Centro, Londrina-PR, CEP 86020-000

Recebimento: Agente Cláudia Moretti (43) 3322-4545.

Fernanda Ribas
Delegada de Polícia – Delegacia da Mulher de Londrina
Ramal 213
""",
            html=True,
        ),
        esperado={
            "descricao_evento": Contem("Lei Maria da Penha"),
            "data_inicio_evento": "2026-11-03",
            "horario_evento": "15:30",
            "quantidade": 40,
            "municipio": "Londrina",
            "local_entrega": Contem("Delegacia da Mulher"),
            "responsavel_recebimento": Contem("Cláudia Moretti"),
            "endereco": Contem("Av. Duque de Caxias, 1000"),
            "bairro": "Centro",
            "cep": "86020-000",
            "data_solicitacao": "2026-10-19",
        },
        nota="HTML; 'quarenta' por extenso; coffee 15h30, palestra 14h; 'Londrina-PR'.",
    ),
    Caso(
        id="cof-006",
        modulo="coffee_break",
        formato="eml",
        agora="2026-09-03 14:00",
        texto=_eml(
            "Gabinete 20ª SDP <gabinete.20sdp@pc.pr.gov.br>",
            _ASCOM,
            "Ofício 145/2026 - solicitação de coffee break",
            "2026-09-03 11:05",
            """
OFÍCIO Nº 145/2026 – 20ª SDP
Toledo, 02 de setembro de 2026.

Senhor Assessor,

Solicito a Vossa Senhoria o fornecimento de coffee break para o Encontro de
Integração da 20ª SDP, a realizar-se no dia 18/09, às 16h, para efetivo de 35
policiais.

Local: Auditório da 20ª SDP, Rua Guarani, 1500 - Centro, Toledo.
Responsável: Investigador Alceu Dambrós.

Respeitosamente,
Delegado Chefe da 20ª SDP
""",
        ),
        esperado={
            "descricao_evento": Contem("Encontro de Integração"),
            "data_inicio_evento": "2026-09-18",
            "horario_evento": "16:00",
            "quantidade": 35,
            "municipio": "Toledo",
            "local_entrega": Contem("Auditório da 20ª SDP"),
            "responsavel_recebimento": Contem("Alceu Dambrós"),
            "endereco": Contem("Rua Guarani, 1500"),
            "bairro": "Centro",
            "data_solicitacao": UmDe("2026-09-02", "2026-09-03"),
        },
        nota="Data do ofício (02/09) e do e-mail (03/09) ≠ evento; 'efetivo de 35 policiais'.",
    ),
    Caso(
        id="cof-007",
        modulo="coffee_break",
        formato="texto",
        agora="2026-10-20 13:40",
        texto="""
boa tarde preciso d coffe pra 25 pesoas dia 12/11 as 8 e meia da manha no auditorio da delegacia de castro, e pra entregar pra investigadora ana lucia. evento palestra prevenção ao suicidio
""",
        esperado={
            "descricao_evento": Contem("prevenção ao suicidio"),
            "data_inicio_evento": "2026-11-12",
            "horario_evento": "08:30",
            "quantidade": 25,
            "municipio": "Castro",
            "local_entrega": Contem("auditorio da delegacia"),
            "responsavel_recebimento": Contem("ana lucia"),
        },
        nota="Mal escrito, sem pontuação; '8 e meia da manha'; município em minúsculas.",
    ),
    Caso(
        id="cof-008",
        modulo="coffee_break",
        formato="eml",
        agora="2026-10-26 09:00",
        texto=_eml(
            "Investigadora Tatiane Gasparin – 9ª SDP <tatiane.gasparin@pc.pr.gov.br>",
            _ASCOM,
            "Coffee - Seminário de Investigação Criminal (Maringá)",
            "2026-10-23 17:31",
            """
Olá, equipe da ASCOM.

Para o Seminário de Investigação Criminal vamos precisar de 1 coffee para 50
pessoas no dia 10/11 às 10h e outro para 20 no dia seguinte, no mesmo horário.

Entrega no Centro de Convenções Municipal de Maringá
Av. XV de Novembro, 701 - Zona 01

Quem recebe: Tatiane (44) 3220-9090.

Att.
Tatiane Gasparin
Investigadora – 9ª SDP
""",
        ),
        esperado={
            "descricao_evento": Contem("Seminário de Investigação Criminal"),
            "data_inicio_evento": "2026-11-10",
            "horario_evento": "10:00",
            "quantidade": 50,
            "municipio": "Maringá",
            "local_entrega": Contem("Centro de Convenções"),
            "responsavel_recebimento": Contem("Tatiane"),
            "endereco": Contem("Av. XV de Novembro, 701"),
            "bairro": "Zona 01",
            "data_solicitacao": "2026-10-23",
        },
        nota="Dois lotes (50 em 10/11 e 20 em 11/11): vale o primeiro.",
    ),
    Caso(
        id="cof-009",
        modulo="coffee_break",
        formato="eml",
        agora="2026-09-22 16:00",
        texto=_eml(
            "Escrivão Diego Ferraz <diego.ferraz@pc.pr.gov.br>",
            _ASCOM,
            "Re: prazo pedidos de coffee - Delegacia de Foz",
            "2026-09-22 14:10",
            """
Prezados,

Conforme orientação, o pedido deve ser enviado até 25/09, então já adianto.

Evento: Capacitação em Atendimento ao Turista Vítima de Crime
Data: dia 06/10 (terça), às 15h
30 participantes
Local de entrega: Delegacia de Polícia de Foz do Iguaçu (sede) — Av. Juscelino
Kubitschek, 1800 - Centro
Receber com o Escrivão Diego Ferraz.

Diego Ferraz
Escrivão de Polícia
""",
        ),
        esperado={
            "descricao_evento": Contem("Atendimento ao Turista"),
            "data_inicio_evento": "2026-10-06",
            "horario_evento": "15:00",
            "quantidade": 30,
            "municipio": "Foz do Iguaçu",
            "local_entrega": Contem("Delegacia de Polícia de Foz do Iguaçu"),
            "responsavel_recebimento": Contem("Diego Ferraz"),
            "bairro": "Centro",
            "data_solicitacao": "2026-09-22",
        },
        nota="'Enviado até 25/09' é prazo do pedido, não o evento; endereço quebrado em duas linhas (fora do gabarito).",
    ),
    Caso(
        id="cof-010",
        modulo="coffee_break",
        formato="texto",
        agora="2026-09-17 09:10",
        texto="""
---------- Forwarded message ---------
De: Delegado Marcos Tavares <marcos.tavares@pc.pr.gov.br>
Date: qua., 16 de set. de 2026 às 17:05
Subject: Coffee break - Workshop Crimes Cibernéticos
To: <gabinete.5sdp@pc.pr.gov.br>

Prezada,

Favor encaminhar à ASCOM: precisaremos de coffee break para o Workshop sobre
Crimes Cibernéticos na próxima segunda-feira (21/09), pela manhã (9h), para 45
pessoas.

Local: Sala de Reuniões da 5ª SDP, Rua Tocantins, 2050, bairro Centro, Pato
Branco.
Recebimento: Investigadora Sílvia Zanella.

Marcos Tavares
Delegado Chefe – 5ª SDP
""",
        esperado={
            "descricao_evento": Contem("Crimes Cibernéticos"),
            "data_inicio_evento": "2026-09-21",
            "horario_evento": "09:00",
            "quantidade": 45,
            "municipio": "Pato Branco",
            "local_entrega": Contem("Sala de Reuniões da 5ª SDP"),
            "responsavel_recebimento": Contem("Sílvia Zanella"),
            "endereco": Contem("Rua Tocantins, 2050"),
            "bairro": "Centro",
            "data_solicitacao": "2026-09-16",
        },
        nota="Gmail encaminhado; 'pela manhã (9h)'; data do pedido é a da mensagem original.",
    ),
    Caso(
        id="cof-011",
        modulo="coffee_break",
        formato="eml",
        agora="2026-10-21 10:00",
        texto=_eml(
            "Divisão de Polícia do Interior <dpi.eventos@pc.pr.gov.br>",
            _ASCOM,
            "Coffee - Reunião do Conselho Comunitário de Segurança de Palmas",
            "2026-10-20 18:02",
            """
Senhores,

Solicitamos coffee break para 20 pessoas na Reunião do Conselho Comunitário de
Segurança de Palmas, dia 5 de novembro, 13h30, no Auditório do Fórum de Palmas.
O responsável no local será o Investigador Gilmar Kuhn.

Cordialmente,

Assessoria da Divisão de Polícia do Interior
Rua José Loureiro, 376 - Centro - Curitiba - CEP 80010-000
Tel. (41) 3235-0000
""",
        ),
        esperado={
            "descricao_evento": Contem("Conselho Comunitário de Segurança"),
            "data_inicio_evento": "2026-11-05",
            "horario_evento": "13:30",
            "quantidade": 20,
            "municipio": "Palmas",
            "local_entrega": Contem("Fórum de Palmas"),
            "responsavel_recebimento": Contem("Gilmar Kuhn"),
            "endereco": AUSENTE,
            "bairro": AUSENTE,
            "cep": AUSENTE,
            "data_solicitacao": "2026-10-20",
        },
        nota="Endereço/CEP/Curitiba só na assinatura: endereço AUSENTE, município Palmas.",
    ),
    Caso(
        id="cof-012",
        modulo="coffee_break",
        formato="eml",
        agora="2026-10-28 09:00",
        texto=_eml(
            "Patrícia Wosniak <patricia.wosniak@pc.pr.gov.br>",
            _ASCOM,
            "Solicitação coffee break – Curso de Formação de Delegados",
            "2026-10-27 13:15",
            """
Boa tarde,

Solicito coffee break para 80 alunos do Curso de Formação de Delegados, na
segunda-feira, 16 de novembro. O coffee será às 15h30, no intervalo.

Local de entrega:
Escola Superior de Polícia Civil
Rua Tenente Francisco Ferreira de Souza, 2600
Hauer – Curitiba/PR
CEP 81630-010

Responsável pelo recebimento: Coordenadora Patrícia Wosniak, ramal 4410.

Patrícia Wosniak
Coordenação Pedagógica – ESPC
""",
        ),
        esperado={
            "descricao_evento": Contem("Curso de Formação de Delegados"),
            "data_inicio_evento": "2026-11-16",
            "horario_evento": "15:30",
            "quantidade": 80,
            "municipio": "Curitiba",
            "local_entrega": Contem("Escola Superior de Polícia Civil"),
            "responsavel_recebimento": Contem("Patrícia Wosniak"),
            "endereco": Contem("Rua Tenente Francisco Ferreira de Souza, 2600"),
            "bairro": "Hauer",
            "cep": "81630-010",
            "data_solicitacao": "2026-10-27",
        },
        nota="Endereço em linhas separadas; ramal 4410 não é quantidade nem horário.",
    ),
    Caso(
        id="cof-013",
        modulo="coffee_break",
        formato="texto",
        agora="2026-10-22 08:00",
        texto="""
[21/10/2026 18:02] Esc. Débora Lunardi: Oi, boa noite
[21/10/2026 18:03] Esc. Débora Lunardi: vamos precisar de coffee p a formatura dos estagiarios dia 30/10
[21/10/2026 18:05] Esc. Débora Lunardi: 70 pessoas, 17h, no salão de eventos da 7ª SDP em Umuarama, Av. Paraná, 4800 - Zona I
[21/10/2026 18:05] Esc. Débora Lunardi: eu recebo
""",
        esperado={
            "descricao_evento": Contem("formatura dos estagiarios"),
            "data_inicio_evento": "2026-10-30",
            "horario_evento": "17:00",
            "quantidade": 70,
            "municipio": "Umuarama",
            "local_entrega": Contem("salão de eventos"),
            "responsavel_recebimento": Contem("Débora"),
            "endereco": Contem("Av. Paraná, 4800"),
            "bairro": "Zona I",
            "data_solicitacao": "2026-10-21",
        },
        nota="WhatsApp em várias mensagens; 'Av. Paraná' não é o município.",
    ),
    Caso(
        id="cof-014",
        modulo="coffee_break",
        formato="eml",
        agora="2026-10-06 22:30",
        texto=_eml(
            "Del. Otávio Scheffer <otavio.scheffer@pc.pr.gov.br>",
            _ASCOM,
            _q("Coffee amanhã – reunião DHPP"),
            "2026-10-06 22:14",
            """
Preciso coffee pra 15 pessoas amanhã 10h, reunião de alinhamento na sede da
DHPP (Curitiba). Quem recebe é o inv. Toledo.

Enviado do meu iPhone
""",
        ),
        esperado={
            "descricao_evento": Contem("reunião"),
            "data_inicio_evento": "2026-10-07",
            "horario_evento": "10:00",
            "quantidade": 15,
            "municipio": "Curitiba",
            "local_entrega": Contem("DHPP"),
            "responsavel_recebimento": Contem("Toledo"),
            "data_solicitacao": "2026-10-06",
        },
        nota="'Inv. Toledo' é pessoa, não o município de Toledo; 'amanhã' do e-mail da noite.",
    ),
    Caso(
        id="cof-015",
        modulo="coffee_break",
        formato="eml",
        agora="2026-10-16 11:00",
        texto=_eml(
            "Investigador Rui Bortolini <rui.bortolini@pc.pr.gov.br>",
            _ASCOM,
            "RES: RES: coffee break solenidade viaturas",
            "2026-10-16 10:12",
            """
Corrigindo: serão 55 pessoas, e não 40 como falei antes. O resto continua igual.

Rui

De: Investigador Rui Bortolini
Enviado em: quarta-feira, 14 de outubro de 2026 16:30
Para: ASCOM PCPR
Assunto: coffee break solenidade viaturas

Boa tarde. Solicito coffee break para 40 pessoas na Solenidade de Entrega de
Viaturas, dia 29/10 às 10h, no pátio da 19ª SDP, Rua Tenente Camargo, 2200 -
Centro, Francisco Beltrão. Recebe: Investigador Rui Bortolini.
""",
        ),
        esperado={
            "descricao_evento": Contem("Entrega de Viaturas"),
            "data_inicio_evento": "2026-10-29",
            "horario_evento": "10:00",
            "quantidade": 55,
            "municipio": "Francisco Beltrão",
            "local_entrega": Contem("pátio da 19ª SDP"),
            "responsavel_recebimento": Contem("Rui Bortolini"),
            "endereco": Contem("Rua Tenente Camargo, 2200"),
            "bairro": "Centro",
            "data_solicitacao": UmDe("2026-10-14", "2026-10-16"),
        },
        nota="Resposta corrige a quantidade (55, não 40 do e-mail citado).",
    ),
    Caso(
        id="cof-016",
        modulo="coffee_break",
        formato="texto",
        agora="2026-10-26 14:00",
        texto="""
Solicito coffee break p/ dia 14 11 às 14h, Seminário Regional de Polícia Judiciária,
em Campo Mourão. Local: Auditório da Câmara Municipal de Campo Mourão, Rua Brasil, 1487 - Centro.
100 pessoas. Receber: Escrivão Leandro Sipriano (44) 3523-1000.
""",
        esperado={
            "descricao_evento": Contem("Seminário Regional de Polícia Judiciária"),
            "data_inicio_evento": "2026-11-14",
            "horario_evento": "14:00",
            "quantidade": 100,
            "municipio": "Campo Mourão",
            "local_entrega": Contem("Câmara Municipal"),
            "responsavel_recebimento": Contem("Leandro Sipriano"),
            "endereco": Contem("Rua Brasil, 1487"),
            "bairro": "Centro",
        },
        nota="Data '14 11' sem barra; texto puro sem data do pedido.",
    ),
    Caso(
        id="cof-017",
        modulo="coffee_break",
        formato="eml",
        agora="2026-11-18 09:00",
        texto=_eml(
            "Assessoria DPI <assessoria.dpi@pc.pr.gov.br>",
            _ASCOM,
            "Solicitação de coffee break - Operação Verão",
            "2026-11-17 15:40",
            """
Prezados,

Por ordem do Delegado-Chefe da Divisão de Polícia do Interior, Dr. Anselmo
Kuster, solicito coffee break para a Reunião de Planejamento Operacional da
Operação Verão, no dia 04 de dezembro, às 9h, para 60 pessoas.

Local de entrega: Auditório da Delegacia de Paranaguá, Rua Faria Sobrinho,
350 - Centro, Paranaguá.
Responsável pelo recebimento: Investigadora Helena Parolin.

Atenciosamente,
Lucas Menegat
Assessor – Divisão de Polícia do Interior
Av. Visconde de Guarapuava, 2764 - Centro, Curitiba
""",
        ),
        esperado={
            "descricao_evento": Contem("Operação Verão"),
            "data_inicio_evento": "2026-12-04",
            "horario_evento": "09:00",
            "quantidade": 60,
            "municipio": "Paranaguá",
            "local_entrega": Contem("Delegacia de Paranaguá"),
            "responsavel_recebimento": Contem("Helena Parolin"),
            "endereco": Contem("Rua Faria Sobrinho, 350"),
            "bairro": "Centro",
            "data_solicitacao": "2026-11-17",
        },
        nota="Assessor em nome do chefe; assinatura em Curitiba (Visconde de Guarapuava) ≠ entrega.",
    ),
    Caso(
        id="cof-018",
        modulo="coffee_break",
        formato="eml",
        agora="2026-11-04 08:30",
        texto=_eml(
            "Investigador Sérgio Maldaner <sergio.maldaner@pc.pr.gov.br>",
            _ASCOM,
            "Coffee - abertura do Curso de Abordagem Policial",
            "2026-11-03 17:55",
            """
Senhores,

Encaminho solicitação para o Curso de Abordagem Policial, que ocorrerá nos dias
23 a 27 de novembro. O coffee será apenas na abertura (23/11), às 8h, para 30
alunos.

Entrega: Delegacia de Telêmaco Borba, Av. Chanceler Horácio Lafer, 800 - Centro.
Recebe: Investigador Sérgio Maldaner.

Sérgio Maldaner
Investigador de Polícia

"""
            + _SIGILO,
        ),
        esperado={
            "descricao_evento": Contem("Curso de Abordagem Policial"),
            "data_inicio_evento": "2026-11-23",
            "horario_evento": "08:00",
            "quantidade": 30,
            "municipio": "Telêmaco Borba",
            "local_entrega": Contem("Delegacia de Telêmaco Borba"),
            "responsavel_recebimento": Contem("Sérgio Maldaner"),
            "endereco": Contem("Av. Chanceler Horácio Lafer, 800"),
            "bairro": "Centro",
            "data_solicitacao": "2026-11-03",
        },
        nota="Curso de 5 dias, coffee só na abertura; aviso de confidencialidade com número de lei.",
    ),
    Caso(
        id="cof-019",
        modulo="coffee_break",
        formato="texto",
        agora="2026-10-13 12:00",
        texto="""
De: Investigadora Rosana Gembarowski <rosana.gembarowski@pc.pr.gov.br>
Enviado em: terça-feira, 13 de outubro de 2026 11:47
Para: ASCOM PCPR
Assunto: coffee treinamento BO

Olá!

Pedimos coffee break para o Treinamento sobre o Novo Sistema de BO na próxima
segunda, às 10h, para 22 pessoas, na Sala de Treinamento da Delegacia de Irati,
Rua Coronel Pires, 555 - Centro.
Quem recebe: Rosana, ramal 208.

Rosana Gembarowski
Investigadora – Delegacia de Irati
""",
        esperado={
            "descricao_evento": Contem("Novo Sistema de BO"),
            "data_inicio_evento": "2026-10-19",
            "horario_evento": "10:00",
            "quantidade": 22,
            "municipio": "Irati",
            "local_entrega": Contem("Sala de Treinamento"),
            "responsavel_recebimento": Contem("Rosana"),
            "endereco": Contem("Rua Coronel Pires, 555"),
            "bairro": "Centro",
            "data_solicitacao": "2026-10-13",
        },
        nota="'próxima segunda' a partir de terça 13/10 = 19/10.",
    ),
    Caso(
        id="cof-020",
        modulo="coffee_break",
        formato="eml",
        agora="2026-10-09 15:00",
        texto=_eml(
            "Delegado Henrique Sallum <henrique.sallum@pc.pr.gov.br>",
            _ASCOM,
            "Coffee - Operação integrada BR-277",
            "2026-10-09 13:20",
            """
Prezados,

Para a Operação Integrada Rota Segura teremos efetivo de 35 policiais. Solicito
kits de lanche para o sábado, 17/10, com entrega às 6h da manhã.

Local: Base de apoio na Rodovia BR-277, km 80, Campo Largo.
Recebimento: Investigador Nilton Grabowski (41) 99999-1234.

Henrique Sallum
Delegado de Polícia
""",
        ),
        esperado={
            "descricao_evento": Contem("Rota Segura"),
            "data_inicio_evento": "2026-10-17",
            "horario_evento": "06:00",
            "quantidade": 35,
            "municipio": "Campo Largo",
            "local_entrega": Contem("Base de apoio"),
            "responsavel_recebimento": Contem("Nilton Grabowski"),
            "endereco": Contem("BR-277, km 80"),
            "data_solicitacao": "2026-10-09",
        },
        nota="Endereço em rodovia (km 80) não é número; 'efetivo de 35 policiais'; 6h da manhã.",
    ),
    Caso(
        id="cof-021",
        modulo="coffee_break",
        formato="texto",
        agora="2026-12-03 09:30",
        texto="""
[03/12/2026 09:15] Del. Ramon – 11ª SDP: pessoal ASCOM, coffe p/ sexta agora, 40 pessoas, confraternizaçao de fim de ano, 16h, na delegacia de Jacarezinho rua paraná, 820. quem recebe é a escrivã Vera
""",
        esperado={
            "descricao_evento": Contem("confraterniza"),
            "data_inicio_evento": "2026-12-04",
            "horario_evento": "16:00",
            "quantidade": 40,
            "municipio": "Jacarezinho",
            "local_entrega": Contem("delegacia de Jacarezinho"),
            "responsavel_recebimento": Contem("Vera"),
            "endereco": Contem("rua paraná, 820"),
            "data_solicitacao": "2026-12-03",
        },
        nota="'sexta agora' de quinta 03/12 = 04/12; 'rua paraná' não é estado nem município.",
    ),
    Caso(
        id="cof-022",
        modulo="coffee_break",
        formato="eml",
        agora="2026-11-05 10:00",
        texto=_eml(
            "Cerimonial DPC <cerimonial.dpc@pc.pr.gov.br>",
            _ASCOM,
            "Coffee break – Solenidade de Homenagem aos Policiais Aposentados",
            "2026-11-04 16:00",
            """
Prezados,

O Cerimonial solicita coffee break para 120 pessoas na Solenidade de Homenagem
aos Policiais Aposentados, no dia 25/11, às 18h.

Local: Auditório do Departamento da Polícia Civil
Av. Visconde de Guarapuava, 2764 - Centro, Curitiba – CEP 80010-100

Recebimento: Agente Simone Taborda, ramal 3010.

Cerimonial – Departamento da Polícia Civil
""",
            html=True,
        ),
        esperado={
            "descricao_evento": Contem("Policiais Aposentados"),
            "data_inicio_evento": "2026-11-25",
            "horario_evento": "18:00",
            "quantidade": 120,
            "municipio": "Curitiba",
            "local_entrega": Contem("Auditório do Departamento da Polícia Civil"),
            "responsavel_recebimento": Contem("Simone Taborda"),
            "endereco": Contem("Av. Visconde de Guarapuava, 2764"),
            "bairro": "Centro",
            "cep": "80010-100",
            "data_solicitacao": "2026-11-04",
        },
        nota="HTML; 'Visconde de Guarapuava' é rua, município é Curitiba.",
    ),
    Caso(
        id="cof-023",
        modulo="coffee_break",
        formato="eml",
        agora="2026-09-01 09:00",
        texto=_eml(
            "Escrivã Luana Pietrobelli <luana.pietrobelli@pc.pr.gov.br>",
            _ASCOM,
            _q("Solicitação de lanche – curso entrevista e interrogatório"),
            "2026-08-31 18:20",
            """
Boa noite,

Solicito coffee break para o Curso de Técnicas de Entrevista e Interrogatório,
dia 17 de setembro, 28 participantes. O curso é das 13h às 17h30 e o coffee
deverá ser servido às 15h.

Auditório da 15ª SDP – Rua Souza Naves, 3983 – Centro – Cascavel/PR – CEP 85810-070

Receber: Escrivã Luana.

Luana Pietrobelli
""",
        ),
        esperado={
            "descricao_evento": Contem("Técnicas de Entrevista e Interrogatório"),
            "data_inicio_evento": "2026-09-17",
            "horario_evento": "15:00",
            "quantidade": 28,
            "municipio": "Cascavel",
            "local_entrega": Contem("Auditório da 15ª SDP"),
            "responsavel_recebimento": Contem("Luana"),
            "endereco": Contem("Rua Souza Naves, 3983"),
            "bairro": "Centro",
            "cep": "85810-070",
            "data_solicitacao": "2026-08-31",
        },
        nota="Assunto QP; mês por extenso sem ano; curso 13h–17h30, coffee 15h.",
    ),
    Caso(
        id="cof-024",
        modulo="coffee_break",
        formato="texto",
        agora="2026-09-10 10:00",
        texto="""
Bom dia. A Delegacia de Guarapuava vai realizar a Palestra sobre Segurança Escolar
para diretores das escolas estaduais, data ainda a definir (provavelmente em
outubro). Gostaria de já deixar reservado coffee para 50 pessoas. Assim que
tivermos a data e o horário, informo.
Local: Auditório do Núcleo Regional de Educação de Guarapuava.
Investigador Evandro Kloss
""",
        esperado={
            "descricao_evento": Contem("Segurança Escolar"),
            "data_inicio_evento": AUSENTE,
            "horario_evento": AUSENTE,
            "quantidade": 50,
            "municipio": "Guarapuava",
            "local_entrega": Contem("Núcleo Regional de Educação"),
        },
        nota="Data e horário a definir: AUSENTES (não inventar 'outubro').",
    ),
    Caso(
        id="cof-025",
        modulo="coffee_break",
        formato="eml",
        agora="2026-10-08 11:00",
        texto=_eml(
            "Delegacia do Adolescente de Maringá <dadolescente.mga@pc.pr.gov.br>",
            _ASCOM,
            "Pedido coffee - roda de conversa",
            "2026-10-08 10:31",
            """
Bom dia,

Pedimos kits para 30 pessoas para a Roda de Conversa com o Conselho Tutelar,
dia 20/10 às 15h.
Local de entrega: Delegacia do Adolescente de Maringá, Av. Tiradentes, 1120 -
Zona 03, Maringá.
Responsável: Agente Priscila Hoffmann.

Obrigado.
""",
        ),
        esperado={
            "descricao_evento": Contem("Roda de Conversa"),
            "data_inicio_evento": "2026-10-20",
            "horario_evento": "15:00",
            "quantidade": 30,
            "municipio": "Maringá",
            "local_entrega": Contem("Delegacia do Adolescente"),
            "responsavel_recebimento": Contem("Priscila Hoffmann"),
            "endereco": Contem("Av. Tiradentes, 1120"),
            "bairro": "Zona 03",
            "data_solicitacao": "2026-10-08",
        },
        nota="'kits para 30'; 'dia 20/10 às 15h'.",
    ),
    Caso(
        id="cof-026",
        modulo="coffee_break",
        formato="eml",
        agora="2026-10-14 15:00",
        texto=_eml(
            "Gabinete 6ª SDP <gabinete.6sdp@pc.pr.gov.br>",
            _ASCOM,
            "Memorando nº 18/11-6ªSDP - coffee break",
            "2026-10-14 14:02",
            """
MEMORANDO Nº 18/11-6ªSDP

Solicitamos coffee break para 45 pessoas no Encontro de Chefes de Cartório, no
dia 27 de outubro, às 14h30.

Local: Auditório da 6ª SDP, Rua Osvaldo Cruz, 510 - Centro, Apucarana.
Recebimento: Escrivão Fábio Rossetto.

Delegado Chefe da 6ª SDP
""",
        ),
        esperado={
            "descricao_evento": Contem("Chefes de Cartório"),
            "data_inicio_evento": "2026-10-27",
            "horario_evento": "14:30",
            "quantidade": 45,
            "municipio": "Apucarana",
            "local_entrega": Contem("Auditório da 6ª SDP"),
            "responsavel_recebimento": Contem("Fábio Rossetto"),
            "endereco": Contem("Rua Osvaldo Cruz, 510"),
            "bairro": "Centro",
            "data_solicitacao": "2026-10-14",
        },
        nota="'Memorando nº 18/11' parece data (18/11) mas é número do documento.",
    ),
    Caso(
        id="cof-027",
        modulo="coffee_break",
        formato="texto",
        agora="2026-11-04 16:00",
        texto="""
De: Anderson Pacheco <anderson.pacheco@pc.pr.gov.br>
Enviado em: quarta-feira, 4 de novembro de 2026 15:21
Para: ASCOM PCPR
Assunto: Coffee - reunião com prefeitos

Boa tarde,

A pedido do Dr. Cláudio Weber, delegado titular, solicito coffee para 25 pessoas
na Reunião com Prefeitos da Região da Cantuquiriguaçu, dia 18/11 às 9h, na Câmara
Municipal de Laranjeiras do Sul.
Quem recebe: Anderson (42) 3635-1122.

Anderson Pacheco
Agente de Polícia Judiciária – assessor do Gabinete
""",
        esperado={
            "descricao_evento": Contem("Reunião com Prefeitos"),
            "data_inicio_evento": "2026-11-18",
            "horario_evento": "09:00",
            "quantidade": 25,
            "municipio": "Laranjeiras do Sul",
            "local_entrega": Contem("Câmara Municipal"),
            "responsavel_recebimento": Contem("Anderson"),
            "data_solicitacao": "2026-11-04",
        },
        nota="Assessor pedindo em nome do delegado; sem endereço.",
    ),
    Caso(
        id="cof-028",
        modulo="coffee_break",
        formato="eml",
        agora="2026-11-03 09:00",
        texto=_eml(
            "Investigadora Kelly Sanches <kelly.sanches@pc.pr.gov.br>",
            _ASCOM,
            "coffee reuniao rolandia",
            "2026-11-02 19:44",
            """
Oi, boa noite.

Vou precisar de coffee para 18 pessoas na quarta, 11/11, 14h, para a Reunião de
Integração com a Guarda Municipal, que será na Delegacia de Rolândia (Rua Dom
Pedro II, 300 - Centro). Pode entregar para mim.

Kelly Sanches
Investigadora – 10ª SDP – Londrina
Rua Pernambuco, 1000 - Centro - Londrina/PR - CEP 86020-120
""",
        ),
        esperado={
            "descricao_evento": Contem("Guarda Municipal"),
            "data_inicio_evento": "2026-11-11",
            "horario_evento": "14:00",
            "quantidade": 18,
            "municipio": "Rolândia",
            "local_entrega": Contem("Delegacia de Rolândia"),
            "responsavel_recebimento": Contem("Kelly"),
            "endereco": Contem("Rua Dom Pedro II, 300"),
            "bairro": "Centro",
            "cep": AUSENTE,
            "data_solicitacao": "2026-11-02",
        },
        nota="Assinatura em Londrina com CEP; entrega em Rolândia (CEP AUSENTE).",
    ),
    Caso(
        id="cof-029",
        modulo="coffee_break",
        formato="eml",
        agora="2026-11-09 10:00",
        texto=_eml(
            "Delegado Vinícius Marcondes <vinicius.marcondes@pc.pr.gov.br>",
            _ASCOM,
            "Coffee break Capacitação em Lavratura de Flagrantes",
            "2026-11-09 08:15",
            """
Prezados,

Solicito coffee break para a Capacitação em Lavratura de Flagrantes, em
24/11/2026, para 35 servidores. Horário do coffee: 15:30.

Local de entrega: Salão Paroquial São Sebastião, Rua Getúlio Vargas, 1234 -
Centro, Paranavaí.
Responsável: Escrivã Rita Cavalcanti, (44) 3423-5566.

Vinícius Marcondes
Delegado de Polícia – 8ª SDP
""",
        ),
        esperado={
            "descricao_evento": Contem("Lavratura de Flagrantes"),
            "data_inicio_evento": "2026-11-24",
            "horario_evento": "15:30",
            "quantidade": 35,
            "municipio": "Paranavaí",
            "local_entrega": Contem("Salão Paroquial São Sebastião"),
            "responsavel_recebimento": Contem("Rita Cavalcanti"),
            "endereco": Contem("Rua Getúlio Vargas, 1234"),
            "bairro": "Centro",
            "data_solicitacao": "2026-11-09",
        },
        nota="Hora '15:30'; '24/11/2026' com ano; bairro na linha seguinte.",
    ),
    Caso(
        id="cof-030",
        modulo="coffee_break",
        formato="texto",
        agora="2026-10-30 09:00",
        texto="""
Prezados, bom dia.

Solicito coffee break para a Reunião Mensal de Coordenação da Divisão de Homicídios,
terça-feira, 10 de novembro de 2026, às 9h, cerca de 60 pessoas.

Local: Auditório da Divisão de Homicídios
Rua Barão do Rio Branco, 1200 - Centro - Curitiba - CEP 80.060-000

Receber com o Investigador Tiago Ramalho.
""",
        esperado={
            "descricao_evento": Contem("Reunião Mensal de Coordenação"),
            "data_inicio_evento": "2026-11-10",
            "horario_evento": "09:00",
            "quantidade": 60,
            "municipio": "Curitiba",
            "local_entrega": Contem("Auditório da Divisão de Homicídios"),
            "responsavel_recebimento": Contem("Tiago Ramalho"),
            "endereco": Contem("Rua Barão do Rio Branco, 1200"),
            "bairro": "Centro",
            "cep": "80060-000",
        },
        nota="CEP com ponto (80.060-000) normalizado; 'cerca de 60'.",
    ),
    Caso(
        id="cof-031",
        modulo="coffee_break",
        formato="eml",
        agora="2026-11-20 14:00",
        texto=_eml(
            "Cerimonial ESPC <cerimonial.espc@pc.pr.gov.br>",
            _ASCOM,
            "Coffee break – Formatura do Curso de Formação de Agentes",
            "2026-11-20 11:30",
            """
Senhores,

Solicitamos coffee break para a Formatura do Curso de Formação de Agentes de
Polícia Judiciária, na sexta-feira, 11 de dezembro, às 19h, para 150 convidados.

Observação: haverá ensaio geral na quinta, 10/12, às 14h (sem coffee).

Local de entrega: Centro de Eventos da Escola Superior de Polícia Civil, Rua
Professor Algacyr Munhoz Mader, 2800 - Cidade Industrial, Curitiba.
Recebimento: Investigador Maurício Tozetto.

Cerimonial – ESPC
""",
            html=True,
        ),
        esperado={
            "descricao_evento": Contem("Formatura do Curso de Formação de Agentes"),
            "data_inicio_evento": "2026-12-11",
            "horario_evento": "19:00",
            "quantidade": 150,
            "municipio": "Curitiba",
            "local_entrega": Contem("Centro de Eventos"),
            "responsavel_recebimento": Contem("Maurício Tozetto"),
            "bairro": "Cidade Industrial",
            "data_solicitacao": "2026-11-20",
        },
        nota="Ensaio 10/12 14h sem coffee: não é a data/horário do pedido.",
    ),
    Caso(
        id="cof-032",
        modulo="coffee_break",
        formato="texto",
        agora="2026-11-16 17:00",
        texto="""
[16/11/2026 16:20] Inv. Juarez: ascom boa tarde
[16/11/2026 16:21] Inv. Juarez: manda coffee p quarta, 25 pessoal, as 3 da tarde
[16/11/2026 16:21] Inv. Juarez: reunião com a guarda municipal aqui na delegacia de pinhais
[16/11/2026 16:22] Inv. Juarez: qualquer coisa fala cmg
""",
        esperado={
            "descricao_evento": Contem("guarda municipal"),
            "data_inicio_evento": "2026-11-18",
            "horario_evento": "15:00",
            "quantidade": 25,
            "municipio": "Pinhais",
            "local_entrega": Contem("delegacia de pinhais"),
            "responsavel_recebimento": Contem("Juarez"),
            "data_solicitacao": "2026-11-16",
        },
        nota="'quarta' a partir de segunda 16/11; '3 da tarde' = 15:00.",
    ),
    Caso(
        id="cof-033",
        modulo="coffee_break",
        formato="eml",
        agora="2026-09-28 15:00",
        texto=_eml(
            "Instrutor Cleverson Andrade <cleverson.andrade@pc.pr.gov.br>",
            _ASCOM,
            "Coffee - Curso de Uso Progressivo da Força",
            "2026-09-28 13:07",
            """
Boa tarde,

Solicito coffee break para o Curso de Uso Progressivo da Força, 2 turmas de 20
alunos, no dia 9 de outubro às 10h.

Local: 10ª SDP, Rua Pernambuco, 1000 - Centro, Londrina-PR.
Recebe: Instrutor Cleverson Andrade.
""",
        ),
        esperado={
            "descricao_evento": Contem("Uso Progressivo da Força"),
            "data_inicio_evento": "2026-10-09",
            "horario_evento": "10:00",
            "quantidade": 40,
            "municipio": "Londrina",
            "local_entrega": Contem("10ª SDP"),
            "responsavel_recebimento": Contem("Cleverson Andrade"),
            "endereco": Contem("Rua Pernambuco, 1000"),
            "bairro": "Centro",
            "data_solicitacao": "2026-09-28",
        },
        nota="2 turmas de 20 = 40; 'Londrina-PR'.",
    ),
    Caso(
        id="cof-034",
        modulo="coffee_break",
        formato="eml",
        agora="2026-10-15 09:00",
        texto=_eml(
            "Delegada Aline Fiorentin <aline.fiorentin@pc.pr.gov.br>",
            _ASCOM,
            "Jornada de Estudos - coffee manhã e tarde",
            "2026-10-14 17:12",
            """
Prezados,

Para a Jornada de Estudos sobre Crimes Patrimoniais, no dia 29/10, precisaremos
de um coffee pela manhã (9h) para 40 pessoas e outro à tarde (15h) para 35.

Local: Auditório da Associação Comercial de Toledo, Rua Barão do Rio Branco,
1111 - Centro.
Responsável: Escrivão Everton Lamb.

Aline Fiorentin
Delegada – 20ª SDP – Toledo
""",
        ),
        esperado={
            "descricao_evento": Contem("Crimes Patrimoniais"),
            "data_inicio_evento": "2026-10-29",
            "horario_evento": "09:00",
            "quantidade": 40,
            "municipio": "Toledo",
            "local_entrega": Contem("Associação Comercial"),
            "responsavel_recebimento": Contem("Everton Lamb"),
            "bairro": "Centro",
            "data_solicitacao": "2026-10-14",
        },
        nota="Dois lotes no mesmo dia (9h/40 e 15h/35): vale o primeiro.",
    ),
    Caso(
        id="cof-035",
        modulo="coffee_break",
        formato="texto",
        agora="2026-11-19 10:00",
        texto="""
SOLICITO COFFE BREAK PARA 32 PESSOAS, DIA 03/12, AS 14:00H, EVENTO: CURSO DE PRIMEIROS SOCORROS, LOCAL: DELEGACIA DE POLICIA DE UNIÃO DA VITORIA, RUA CEL. AMAZONAS, 555, CENTRO. RESPONSAVEL: INV. JOSÉ CARLOS BRANDALIZE
""",
        esperado={
            "descricao_evento": Contem("PRIMEIROS SOCORROS"),
            "data_inicio_evento": "2026-12-03",
            "horario_evento": "14:00",
            "quantidade": 32,
            "municipio": "União da Vitória",
            "local_entrega": Contem("DELEGACIA DE POLICIA"),
            "responsavel_recebimento": Contem("JOSÉ CARLOS"),
            "endereco": Contem("RUA CEL. AMAZONAS, 555"),
            "bairro": "Centro",
        },
        nota="Tudo em maiúsculas, 'UNIÃO DA VITORIA' sem acento; '14:00H'.",
    ),
    Caso(
        id="cof-036",
        modulo="coffee_break",
        formato="eml",
        agora="2026-11-12 10:00",
        texto=_eml(
            "Escrivã Bianca Trevisan <bianca.trevisan@pc.pr.gov.br>",
            _ASCOM,
            _q("Oficina de Mediação – coffee"),
            "2026-11-11 16:40",
            """
Olá,

Solicito coffee break para a Oficina de Mediação de Conflitos, dia 02 de
dezembro, 20 pessoas. Chegada dos participantes às 7h30, coffee às 8h.
A oficina será na Sala de Reuniões do Fórum da Comarca de Cornélio Procópio.
Receber com a Escrivã Bianca.

Bianca Trevisan
Escrivã – 12ª SDP
Rua Minas Gerais, 400 – Centro – Cornélio Procópio/PR – CEP 86300-000
""",
        ),
        esperado={
            "descricao_evento": Contem("Mediação de Conflitos"),
            "data_inicio_evento": "2026-12-02",
            "horario_evento": "08:00",
            "quantidade": 20,
            "municipio": "Cornélio Procópio",
            "local_entrega": Contem("Fórum"),
            "responsavel_recebimento": Contem("Bianca"),
            "endereco": AUSENTE,
            "cep": AUSENTE,
            "data_solicitacao": "2026-11-11",
        },
        nota="Chegada 7h30 ≠ coffee 8h; endereço/CEP só na assinatura (a entrega é no Fórum).",
    ),
    Caso(
        id="cof-037",
        modulo="coffee_break",
        formato="eml",
        agora="2026-10-05 09:00",
        texto=_eml(
            "Investigador Wagner Lipinski <wagner.lipinski@pc.pr.gov.br>",
            _ASCOM,
            "Coffee - Semana de Prevenção às Drogas",
            "2026-10-02 15:48",
            """
Boa tarde,

Na Semana de Prevenção às Drogas faremos palestra para estudantes no dia 19/10,
das 8h às 12h, com coffee às 10h, para 90 pessoas.

Local: Auditório do SESC, Rua Comendador Miró, 800 - Centro, Ponta Grossa, CEP 84010-160.
Responsável pelo recebimento: Wagner (42) 3220-3344.

Wagner Lipinski
Investigador – 13ª SDP
""",
        ),
        esperado={
            "descricao_evento": Contem("Prevenção às Drogas"),
            "data_inicio_evento": "2026-10-19",
            "horario_evento": "10:00",
            "quantidade": 90,
            "municipio": "Ponta Grossa",
            "local_entrega": Contem("Auditório do SESC"),
            "responsavel_recebimento": Contem("Wagner"),
            "endereco": Contem("Rua Comendador Miró, 800"),
            "bairro": "Centro",
            "cep": "84010-160",
            "data_solicitacao": "2026-10-02",
        },
        nota="Palestra 8h–12h, coffee 10h.",
    ),
    Caso(
        id="cof-038",
        modulo="coffee_break",
        formato="texto",
        agora="2026-12-15 10:00",
        texto="""
De: Delegado Rafael Iurk <rafael.iurk@pc.pr.gov.br>
Enviado em: terça-feira, 15 de dezembro de 2026 09:12
Para: ASCOM PCPR
Assunto: coffee abertura Operação Verão Guaratuba

Prezados,

Solicito coffee break para a Reunião de Abertura da Operação Verão em Guaratuba,
dia 12/01, às 9h, para 50 policiais.
Local: Base da Operação Verão, Av. Atlântica, 3000 - Brejatuba, Guaratuba.
Recebe: Investigador Ivo Salamuchi.

Rafael Iurk
Delegado de Polícia
""",
        esperado={
            "descricao_evento": Contem("Operação Verão"),
            "data_inicio_evento": "2027-01-12",
            "horario_evento": "09:00",
            "quantidade": 50,
            "municipio": "Guaratuba",
            "local_entrega": Contem("Base da Operação Verão"),
            "responsavel_recebimento": Contem("Ivo Salamuchi"),
            "endereco": Contem("Av. Atlântica, 3000"),
            "bairro": "Brejatuba",
            "data_solicitacao": "2026-12-15",
        },
        nota="Pedido em dezembro para 12/01 sem ano: é 2027.",
    ),
    Caso(
        id="cof-039",
        modulo="coffee_break",
        formato="eml",
        agora="2026-09-29 10:00",
        texto=_eml(
            "Escrivão Jean Carlos Vogel <jean.vogel@pc.pr.gov.br>",
            _ASCOM,
            "Solicitação coffee Medianeira",
            "2026-09-28 17:03",
            """
Boa tarde.

Solicito coffee para 24 pessoas, no dia 8/10 às 13h30, para o Treinamento de
Plantão Integrado, no Auditório da Delegacia de Medianeira.
Recebimento: Escrivão Jean.

--
Jean Carlos Vogel
Escrivão de Polícia – Subdivisão de Foz do Iguaçu
Av. Juscelino Kubitschek, 1800 – Centro – Foz do Iguaçu/PR
CEP 85851-210 | Ramal 330
""",
        ),
        esperado={
            "descricao_evento": Contem("Plantão Integrado"),
            "data_inicio_evento": "2026-10-08",
            "horario_evento": "13:30",
            "quantidade": 24,
            "municipio": "Medianeira",
            "local_entrega": Contem("Delegacia de Medianeira"),
            "responsavel_recebimento": Contem("Jean"),
            "endereco": AUSENTE,
            "bairro": AUSENTE,
            "cep": AUSENTE,
            "data_solicitacao": "2026-09-28",
        },
        nota="Assinatura com endereço em Foz; entrega em Medianeira sem endereço.",
    ),
    Caso(
        id="cof-040",
        modulo="coffee_break",
        formato="eml",
        agora="2026-10-06 08:00",
        texto=_eml(
            "Investigadora Sueli Bonatto <sueli.bonatto@pc.pr.gov.br>",
            _ASCOM,
            "Coffee palestra golpes digitais",
            "2026-10-05 11:25",
            """
Bom dia!

Para a palestra "Golpes Digitais contra Idosos" precisaremos de coffee break
para vinte e cinco pessoas, no dia 21 de outubro (quarta-feira), às 14h.

Local: Centro de Convivência do Idoso de Sarandi, Rua das Flores, 90 - Jardim
Esperança, Sarandi.
Quem recebe: Sueli, (44) 3264-7788.

Sueli Bonatto
Investigadora
""",
            html=True,
        ),
        esperado={
            "descricao_evento": Contem("Golpes Digitais"),
            "data_inicio_evento": "2026-10-21",
            "horario_evento": "14:00",
            "quantidade": 25,
            "municipio": "Sarandi",
            "local_entrega": Contem("Centro de Convivência do Idoso"),
            "responsavel_recebimento": Contem("Sueli"),
            "endereco": Contem("Rua das Flores, 90"),
            "bairro": "Jardim Esperança",
            "data_solicitacao": "2026-10-05",
        },
        nota="'vinte e cinco' por extenso; bairro quebrado em duas linhas.",
    ),
]

CASOS += [
    Caso(
        id="cof-041",
        modulo="coffee_break",
        formato="texto",
        agora="2026-10-20 10:00",
        texto="""
Segue pedido abaixo, favor providenciar.

---------- Forwarded message ---------
De: Investigador Osmar Czelusniak <osmar.czelusniak@pc.pr.gov.br>
Date: seg., 19 de out. de 2026 às 16:40
Subject: coffee reunião CONSEG Jaguariaíva
To: ASCOM PCPR <ascom@pc.pr.gov.br>

Boa tarde, solicito coffee break para 30 pessoas na Reunião do CONSEG de
Jaguariaíva, no dia 28/10 às 19h.
Local: Salão da Paróquia Senhor Bom Jesus, Rua Getúlio Vargas, 250 - Centro, Jaguariaíva.
Quem recebe: Osmar (43) 3535-2020.
""",
        esperado={
            "descricao_evento": Contem("CONSEG"),
            "data_inicio_evento": "2026-10-28",
            "horario_evento": "19:00",
            "quantidade": 30,
            "municipio": "Jaguariaíva",
            "local_entrega": Contem("Salão da Paróquia"),
            "responsavel_recebimento": Contem("Osmar"),
            "endereco": Contem("Rua Getúlio Vargas, 250"),
            "bairro": "Centro",
            "data_solicitacao": "2026-10-19",
        },
        nota="Gmail encaminhado por colega; data do pedido = mensagem original.",
    ),
    Caso(
        id="cof-042",
        modulo="coffee_break",
        formato="eml",
        agora="2026-10-22 09:40",
        texto=_eml(
            "Chefia de Gabinete DG <gabinete.dg@pc.pr.gov.br>",
            _ASCOM,
            "URGENTE - coffee para hoje",
            "2026-10-22 09:31",
            """
Bom dia,

Se possível, precisamos de coffee break para hoje (quinta) às 16h, Reunião
Extraordinária do Conselho Superior da Polícia Civil, 12 pessoas.

Entrega no Gabinete da Delegacia-Geral, 3º andar – Rua José Loureiro, 376 –
Centro, Curitiba.
Recebe: Secretária Denise Mikos, ramal 1001.
""",
        ),
        esperado={
            "descricao_evento": Contem("Conselho Superior"),
            "data_inicio_evento": "2026-10-22",
            "horario_evento": "16:00",
            "quantidade": 12,
            "municipio": "Curitiba",
            "local_entrega": Contem("Gabinete da Delegacia-Geral"),
            "responsavel_recebimento": Contem("Denise Mikos"),
            "endereco": Contem("Rua José Loureiro, 376"),
            "bairro": "Centro",
            "data_solicitacao": "2026-10-22",
        },
        nota="'hoje' = data do e-mail; '3º andar' e ramal 1001 não são quantidade.",
    ),
    Caso(
        id="cof-043",
        modulo="coffee_break",
        formato="eml",
        agora="2026-11-24 11:00",
        texto=_eml(
            "Delegado Luiz Fernando Colla – 19ª SDP <luiz.colla@pc.pr.gov.br>",
            _ASCOM,
            "Encontro de Policiais Civis do Sudoeste - coffee",
            "2026-11-24 08:55",
            """
Senhores,

No Encontro de Policiais Civis do Sudoeste, dia 10 de dezembro, teremos 200
participantes. Almoço é por conta da organização; precisamos só do coffee da
tarde, às 15h30.

Local: Parque de Exposições de Dois Vizinhos, Rodovia PR-473, km 2.
Responsável: Investigador Adair Bressan.

Luiz Fernando Colla
Delegado Chefe – 19ª SDP
""",
        ),
        esperado={
            "descricao_evento": Contem("Encontro de Policiais Civis do Sudoeste"),
            "data_inicio_evento": "2026-12-10",
            "horario_evento": "15:30",
            "quantidade": 200,
            "municipio": "Dois Vizinhos",
            "local_entrega": Contem("Parque de Exposições"),
            "responsavel_recebimento": Contem("Adair Bressan"),
            "endereco": Contem("PR-473, km 2"),
            "data_solicitacao": "2026-11-24",
        },
        nota="Só o coffee da tarde (15h30); endereço em rodovia estadual.",
    ),
    Caso(
        id="cof-044",
        modulo="coffee_break",
        formato="texto",
        agora="2026-10-28 18:00",
        texto="""
[28/10/2026 14:02] Inv. Márcio Tokarski: boa tarde, preciso de coffee p curso de direção defensiva dia 5/11 às 9h
[28/10/2026 14:03] Inv. Márcio Tokarski: 30 pessoas
[28/10/2026 14:03] Inv. Márcio Tokarski: no pátio da Delegacia de Arapongas, Rua Garças, 1500 - Centro
[28/10/2026 16:47] Inv. Márcio Tokarski: corrigindo, serão 36 pessoas
[28/10/2026 16:47] Inv. Márcio Tokarski: eu recebo
""",
        esperado={
            "descricao_evento": Contem("direção defensiva"),
            "data_inicio_evento": "2026-11-05",
            "horario_evento": "09:00",
            "quantidade": 36,
            "municipio": "Arapongas",
            "local_entrega": Contem("Delegacia de Arapongas"),
            "responsavel_recebimento": Contem("Márcio"),
            "endereco": Contem("Rua Garças, 1500"),
            "bairro": "Centro",
            "data_solicitacao": "2026-10-28",
        },
        nota="Quantidade corrigida em mensagem posterior (36, não 30).",
    ),
    Caso(
        id="cof-045",
        modulo="coffee_break",
        formato="eml",
        agora="2026-10-30 20:00",
        texto=_eml(
            "Delegado Paulo Sérgio Heck <paulo.heck@pc.pr.gov.br>",
            _ASCOM,
            _q("Posse – coffee break Assis Chateaubriand"),
            "2026-10-30 19:12",
            """
Boa noite, solicito coffee para 60 pessoas na solenidade de posse do novo
delegado titular, dia 13/11 às 17h, na Câmara Municipal de Assis Chateaubriand,
Rua Duque de Caxias, 1000 - Centro. Recebe a escrivã Neide (44) 3528-1010.

Enviado do meu iPhone
""",
        ),
        esperado={
            "descricao_evento": Contem("posse"),
            "data_inicio_evento": "2026-11-13",
            "horario_evento": "17:00",
            "quantidade": 60,
            "municipio": "Assis Chateaubriand",
            "local_entrega": Contem("Câmara Municipal"),
            "responsavel_recebimento": Contem("Neide"),
            "endereco": Contem("Rua Duque de Caxias, 1000"),
            "bairro": "Centro",
            "data_solicitacao": "2026-10-30",
        },
        nota="Assunto QP; 'Enviado do meu iPhone'; 'Duque de Caxias' é rua.",
    ),
    Caso(
        id="cof-046",
        modulo="coffee_break",
        formato="eml",
        agora="2026-09-30 15:00",
        texto=_eml(
            "Escrivã Ivone Schneider <ivone.schneider@pc.pr.gov.br>",
            _ASCOM,
            "Novo pedido de coffee - Marechal Cândido Rondon",
            "2026-09-30 10:20",
            """
Bom dia!

Assim como no evento do dia 10/09 (que foi para 25 pessoas), precisamos de
coffee break, agora para 40 pessoas, no Seminário de Enfrentamento ao Tráfico
de Pessoas, dia 15/10 às 14h.

Local: Auditório da Delegacia de Marechal Cândido Rondon, Rua Sete de Setembro,
600 - Centro.
Recebimento: Escrivã Ivone.
""",
        ),
        esperado={
            "descricao_evento": Contem("Tráfico de Pessoas"),
            "data_inicio_evento": "2026-10-15",
            "horario_evento": "14:00",
            "quantidade": 40,
            "municipio": "Marechal Cândido Rondon",
            "local_entrega": Contem("Delegacia de Marechal Cândido Rondon"),
            "responsavel_recebimento": Contem("Ivone"),
            "bairro": "Centro",
            "data_solicitacao": "2026-09-30",
        },
        nota="Evento anterior (10/09, 25 pessoas) citado ≠ pedido atual (15/10, 40); 'Rua Sete de Setembro' não é data.",
    ),
    Caso(
        id="cof-047",
        modulo="coffee_break",
        formato="texto",
        agora="2026-11-02 11:00",
        texto="""
Prezados,

Solicitamos coffee break para o Curso de Gestão de Cartório, dia 18/11, às 15h45,
para 42 alunos.
Local de entrega: Escola Superior de Polícia Civil, Rua Professor Algacyr Munhoz
Mader nº 2800, bairro Cidade Industrial, Curitiba.
Responsável: Agente Rosemeri Taques.

Coordenação de Cursos – ESPC
""",
        esperado={
            "descricao_evento": Contem("Gestão de Cartório"),
            "data_inicio_evento": "2026-11-18",
            "horario_evento": "15:45",
            "quantidade": 42,
            "municipio": "Curitiba",
            "local_entrega": Contem("Escola Superior de Polícia Civil"),
            "responsavel_recebimento": Contem("Rosemeri Taques"),
            "endereco": Contem("Mader"),
            "bairro": "Cidade Industrial",
        },
        nota="Endereço com 'nº' e quebra de linha no meio da rua; horário 15h45.",
    ),
    Caso(
        id="cof-048",
        modulo="coffee_break",
        formato="eml",
        agora="2026-09-15 10:30",
        texto=_eml(
            "Investigador Robson Faccin <robson.faccin@pc.pr.gov.br>",
            _ASCOM,
            "Coffee break - Palestra para a Guarda Mirim de Cianorte",
            "2026-09-15 09:44",
            """
Bom dia, equipe!

Pedimos 80 kits de lanche para a Palestra para a Guarda Mirim, no dia 25 de
setembro, às 9h.

Local: Ginásio de Esportes Municipal de Cianorte
Av. Américo Belay, 1500 - Zona 1 - Cianorte/PR

Recebimento: Investigador Robson Faccin, (44) 3631-4000.
""",
            html=True,
        ),
        esperado={
            "descricao_evento": Contem("Guarda Mirim"),
            "data_inicio_evento": "2026-09-25",
            "horario_evento": "09:00",
            "quantidade": 80,
            "municipio": "Cianorte",
            "local_entrega": Contem("Ginásio de Esportes"),
            "responsavel_recebimento": Contem("Robson Faccin"),
            "endereco": Contem("Av. Américo Belay, 1500"),
            "bairro": "Zona 1",
            "data_solicitacao": "2026-09-15",
        },
        nota="HTML; '80 kits'; endereço em linha separada.",
    ),
    Caso(
        id="cof-049",
        modulo="coffee_break",
        formato="texto",
        agora="2026-10-15 17:00",
        texto="""
De: Delegada Carolina Mattar <carolina.mattar@pc.pr.gov.br>
Enviado em: quinta-feira, 15 de outubro de 2026 16:02
Para: ASCOM PCPR
Assunto: Seminário de Polícia Comunitária - Lapa

Prezados,

Segue a programação do Seminário de Polícia Comunitária da Lapa, dia 3 de
novembro:
8h – abertura
10h – coffee break
12h – encerramento

Precisaremos de coffee para 45 pessoas, no Auditório da Prefeitura da Lapa,
Rua Barão do Rio Branco, 1500 - Centro.
Recebe: Escrivão Gustavo Hey.
""",
        esperado={
            "descricao_evento": Contem("Polícia Comunitária"),
            "data_inicio_evento": "2026-11-03",
            "horario_evento": "10:00",
            "quantidade": 45,
            "municipio": "Lapa",
            "local_entrega": Contem("Auditório da Prefeitura"),
            "responsavel_recebimento": Contem("Gustavo Hey"),
            "endereco": Contem("Rua Barão do Rio Branco, 1500"),
            "bairro": "Centro",
            "data_solicitacao": "2026-10-15",
        },
        nota="Programação com 3 horários: o do coffee é 10h.",
    ),
    Caso(
        id="cof-050",
        modulo="coffee_break",
        formato="eml",
        agora="2026-11-10 14:00",
        texto=_eml(
            "Escrivão Edson Kachel <edson.kachel@pc.pr.gov.br>",
            _ASCOM,
            "Capacitação de Escrivães - coffee",
            "2026-11-10 11:12",
            """
Olá,

Solicito coffee break para 22 pessoas na Capacitação de Escrivães, dia 26/11
às 15h.

Local de entrega: Sala de Treinamento da Delegacia de Prudentópolis, Rua
Visconde de Guarapuava, 800 - Centro, Prudentópolis.
Receber com: Edson.
""",
        ),
        esperado={
            "descricao_evento": Contem("Capacitação de Escrivães"),
            "data_inicio_evento": "2026-11-26",
            "horario_evento": "15:00",
            "quantidade": 22,
            "municipio": "Prudentópolis",
            "local_entrega": Contem("Delegacia de Prudentópolis"),
            "responsavel_recebimento": Contem("Edson"),
            "bairro": "Centro",
            "data_solicitacao": "2026-11-10",
        },
        nota="'Rua Visconde de Guarapuava' em Prudentópolis: município não é Guarapuava.",
    ),
    Caso(
        id="cof-051",
        modulo="coffee_break",
        formato="eml",
        agora="2026-11-23 16:00",
        texto=_eml(
            "Investigadora Mirela Justus <mirela.justus@pc.pr.gov.br>",
            _ASCOM,
            "Pedido coffee - treinamento atendimento",
            "2026-11-23 14:30",
            """
Boa tarde,

Solicito coffee para 28 pessoas no Treinamento de Atendimento ao Público, dia
07/12 às 14h, no Distrito Policial do Bairro Alto, Rua Londrina, 250 - Bairro
Alto, Curitiba.
Quem recebe: Mirela, ramal 7720.
""",
        ),
        esperado={
            "descricao_evento": Contem("Atendimento ao Público"),
            "data_inicio_evento": "2026-12-07",
            "horario_evento": "14:00",
            "quantidade": 28,
            "municipio": "Curitiba",
            "local_entrega": Contem("Distrito Policial"),
            "responsavel_recebimento": Contem("Mirela"),
            "endereco": Contem("Rua Londrina, 250"),
            "bairro": "Bairro Alto",
            "data_solicitacao": "2026-11-23",
        },
        nota="'Rua Londrina' em Curitiba: município não é Londrina.",
    ),
    Caso(
        id="cof-052",
        modulo="coffee_break",
        formato="texto",
        agora="2026-10-20 21:00",
        texto="""
[20/10/2026 20:11] Del. Arnaldo Pietsch: Ascom, preciso de lanche pra operação Fronteira Segura
[20/10/2026 20:12] Del. Arnaldo Pietsch: sábado 24/10, entrega 5h30 da manhã
[20/10/2026 20:12] Del. Arnaldo Pietsch: pessoal da operação, uns 40
[20/10/2026 20:13] Del. Arnaldo Pietsch: na Delegacia de Foz, Rua Almirante Barroso, 1300. recebe o plantão, inv. Cristiano
""",
        esperado={
            "descricao_evento": Contem("Fronteira Segura"),
            "data_inicio_evento": "2026-10-24",
            "horario_evento": "05:30",
            "quantidade": 40,
            "municipio": "Foz do Iguaçu",
            "local_entrega": Contem("Delegacia de Foz"),
            "responsavel_recebimento": Contem("Cristiano"),
            "endereco": Contem("Rua Almirante Barroso, 1300"),
            "data_solicitacao": "2026-10-20",
        },
        nota="'Foz' abreviado = Foz do Iguaçu; 'uns 40'; 5h30 da manhã.",
    ),
    Caso(
        id="cof-053",
        modulo="coffee_break",
        formato="eml",
        agora="2026-10-09 16:00",
        texto=_eml(
            "Investigador Jonas Pedroso <jonas.pedroso@pc.pr.gov.br>",
            _ASCOM,
            _q("Solicitação – reunião Conselho da Comunidade – Ibaiti"),
            "2026-10-09 15:05",
            """
Prezados,

Solicito coffee break no dia 20.10, às 16 horas, para 25 pessoas, na Reunião com
o Conselho da Comunidade, no Salão Nobre da Prefeitura de Ibaiti, Rua Tertuliano
de Moura Bueno, 200 - Centro.
Recebe: Jonas.

Jonas Pedroso
Investigador de Polícia – Delegacia de Ibaiti
""",
        ),
        esperado={
            "descricao_evento": Contem("Conselho da Comunidade"),
            "data_inicio_evento": "2026-10-20",
            "horario_evento": "16:00",
            "quantidade": 25,
            "municipio": "Ibaiti",
            "local_entrega": Contem("Salão Nobre"),
            "responsavel_recebimento": Contem("Jonas"),
            "bairro": "Centro",
            "data_solicitacao": "2026-10-09",
        },
        nota="Data com ponto (20.10) e '16 horas'.",
    ),
    Caso(
        id="cof-054",
        modulo="coffee_break",
        formato="eml",
        agora="2026-11-03 14:00",
        texto=_eml(
            "Delegado Renato Brusamolin <renato.brusamolin@pc.pr.gov.br>",
            _ASCOM,
            "ALTERAÇÃO DE DATA - coffee reunião preparatória Operação Verão",
            "2026-11-03 12:40",
            """
Prezados,

A Reunião Preparatória da Operação Verão, que seria dia 12/11, foi adiada para
19/11, mesmo horário (10h). Mantemos o pedido de coffee para 30 pessoas.

Local: Auditório da Delegacia de Matinhos, Av. Paranaguá, 450 - Centro, Matinhos.
Recebe: Investigadora Joice Ramos.
""",
        ),
        esperado={
            "descricao_evento": Contem("Operação Verão"),
            "data_inicio_evento": "2026-11-19",
            "horario_evento": "10:00",
            "quantidade": 30,
            "municipio": "Matinhos",
            "local_entrega": Contem("Delegacia de Matinhos"),
            "responsavel_recebimento": Contem("Joice Ramos"),
            "endereco": Contem("Av. Paranaguá, 450"),
            "bairro": "Centro",
            "data_solicitacao": "2026-11-03",
        },
        nota="Adiado de 12/11 para 19/11; 'Av. Paranaguá' em Matinhos.",
    ),
    Caso(
        id="cof-055",
        modulo="coffee_break",
        formato="texto",
        agora="2026-11-05 10:00",
        texto="""
Bom dia, a Delegacia de Colombo solicita coffee break para a Palestra de Educação
no Trânsito, dia 17/11 (terça), 9h30, 35 pessoas, no Colégio Estadual Rui Barbosa,
Rua Guaratuba, 300 - Centro, Colombo. Entregar na portaria para o sr. Valdir.
Att, Escrivã Gisele Bortoluzzi
""",
        esperado={
            "descricao_evento": Contem("Educação no Trânsito"),
            "data_inicio_evento": "2026-11-17",
            "horario_evento": "09:30",
            "quantidade": 35,
            "municipio": "Colombo",
            "local_entrega": Contem("Colégio Estadual Rui Barbosa"),
            "responsavel_recebimento": Contem("Valdir"),
            "endereco": Contem("Rua Guaratuba, 300"),
            "bairro": "Centro",
        },
        nota="'Rua Guaratuba' em Colombo; quem recebe é o sr. Valdir, não a escrivã que assina.",
    ),
    Caso(
        id="cof-056",
        modulo="coffee_break",
        formato="eml",
        agora="2026-10-26 15:00",
        texto=_eml(
            "Instrutor Ademir Gluszczak <ademir.gluszczak@pc.pr.gov.br>",
            _ASCOM,
            "Coffee Curso de Investigação de Homicídios - Turma 12/2026",
            "2026-10-26 13:50",
            """
Boa tarde,

Para o Curso de Investigação de Homicídios – Turma 12/2026, solicito coffee para
40 pessoas (30 alunos + 10 instrutores), no dia 9 de novembro, às 15h.

Local: Auditório da Delegacia de Rio Negro, Rua Barão do Rio Branco, 200 -
Centro, Rio Negro.
Recebimento: Ademir.
""",
        ),
        esperado={
            "descricao_evento": Contem("Investigação de Homicídios"),
            "data_inicio_evento": "2026-11-09",
            "horario_evento": "15:00",
            "quantidade": 40,
            "municipio": "Rio Negro",
            "local_entrega": Contem("Delegacia de Rio Negro"),
            "responsavel_recebimento": Contem("Ademir"),
            "endereco": Contem("Rua Barão do Rio Branco, 200"),
            "bairro": "Centro",
            "data_solicitacao": "2026-10-26",
        },
        nota="'Turma 12/2026' não é data; 40 = 30 + 10.",
    ),
    Caso(
        id="cof-057",
        modulo="coffee_break",
        formato="eml",
        agora="2026-10-27 16:00",
        texto=_eml(
            "Delegacia da Mulher de Ponta Grossa <dm.pgrossa@pc.pr.gov.br>",
            _ASCOM,
            "Encontro Regional das Delegacias da Mulher – coffee",
            "2026-10-27 15:01",
            """
Prezados,

Solicitamos coffee break para 70 pessoas no Encontro Regional das Delegacias da
Mulher, na segunda-feira, 9 de novembro, às 10h15.

Local de entrega: Salão de Eventos da OAB Ponta Grossa
Av. Vicente Machado, 500 - Centro - CEP 84010-000

Responsável: Agente Lucimara Bastos, (42) 3224-5050.
""",
            html=True,
        ),
        esperado={
            "descricao_evento": Contem("Encontro Regional das Delegacias da Mulher"),
            "data_inicio_evento": "2026-11-09",
            "horario_evento": "10:15",
            "quantidade": 70,
            "municipio": "Ponta Grossa",
            "local_entrega": Contem("Salão de Eventos"),
            "responsavel_recebimento": Contem("Lucimara Bastos"),
            "endereco": Contem("Av. Vicente Machado, 500"),
            "bairro": "Centro",
            "cep": "84010-000",
            "data_solicitacao": "2026-10-27",
        },
        nota="HTML; horário quebrado 10h15; município só no nome do local.",
    ),
    Caso(
        id="cof-058",
        modulo="coffee_break",
        formato="texto",
        agora="2026-10-08 16:00",
        texto="""
De: Escrivã Fabiana Kist <fabiana.kist@pc.pr.gov.br>
Enviado em: quinta-feira, 8 de outubro de 2026 14:55
Para: ASCOM PCPR
Assunto: coffee break reunião setorial

Boa tarde,

Solicito coffee para a Reunião Setorial de Cartórios, dia 22/10 às 9h, para 30
pessoas, na Sala de Reuniões da 7ª SDP em Umuarama.
Recebe: Fabiana.

Fabiana Kist
Escrivã de Polícia – 7ª SDP
Ramal 1530 | Tel. (44) 3621-2020 | Cel. (44) 99812-2211
""",
        esperado={
            "descricao_evento": Contem("Reunião Setorial"),
            "data_inicio_evento": "2026-10-22",
            "horario_evento": "09:00",
            "quantidade": 30,
            "municipio": "Umuarama",
            "local_entrega": Contem("Sala de Reuniões da 7ª SDP"),
            "responsavel_recebimento": Contem("Fabiana"),
            "data_solicitacao": "2026-10-08",
        },
        nota="Ramal 1530 parece horário (15:30); telefone 2020 não é ano.",
    ),
    Caso(
        id="cof-059",
        modulo="coffee_break",
        formato="eml",
        agora="2026-12-10 09:00",
        texto=_eml(
            "Associação Recreativa dos Policiais – DPC <recreativa.dpc@pc.pr.gov.br>",
            _ASCOM,
            "Coffee - confraternização de fim de ano",
            "2026-12-09 17:20",
            """
Olá!

Solicitamos coffee break para a Confraternização de Fim de Ano dos servidores do
DPC, no dia 18/12, às 17h, para 100 pessoas.

Local: Clube da Polícia Civil, Rua Mateus Leme, 4000 - São Lourenço, Curitiba,
CEP 82200-000.
Quem recebe: Agente Rodrigo Bittencourt.
""",
        ),
        esperado={
            "descricao_evento": Contem("Confraternização de Fim de Ano"),
            "data_inicio_evento": "2026-12-18",
            "horario_evento": "17:00",
            "quantidade": 100,
            "municipio": "Curitiba",
            "local_entrega": Contem("Clube da Polícia Civil"),
            "responsavel_recebimento": Contem("Rodrigo Bittencourt"),
            "endereco": Contem("Rua Mateus Leme, 4000"),
            "bairro": "São Lourenço",
            "cep": "82200-000",
            "data_solicitacao": "2026-12-09",
        },
        nota="CEP em outra linha; bairro composto.",
    ),
    Caso(
        id="cof-060",
        modulo="coffee_break",
        formato="eml",
        agora="2026-10-29 10:00",
        texto=_eml(
            "Luciane Moro – ASCOM <luciane.moro@pc.pr.gov.br>",
            "Secretaria ASCOM <secretaria.ascom@pc.pr.gov.br>",
            "Fwd: coffee Treinamento em Local de Crime - Palotina",
            "2026-10-29 08:40",
            """
Para lançar, por favor.

-------- Mensagem encaminhada --------
Assunto: coffee Treinamento em Local de Crime - Palotina
Data: Wed, 28 Oct 2026 17:15:00 -0300
De: Investigador Dirceu Weiss <dirceu.weiss@pc.pr.gov.br>
Para: ASCOM PCPR <ascom@pc.pr.gov.br>

Boa tarde, solicito coffee break para 26 pessoas no Treinamento em Local de
Crime, dia 12/11 às 15h, no Auditório da Delegacia de Palotina, Rua Santos
Dumont, 1100 - Centro. Recebe: Dirceu.
""",
        ),
        esperado={
            "descricao_evento": Contem("Local de Crime"),
            "data_inicio_evento": "2026-11-12",
            "horario_evento": "15:00",
            "quantidade": 26,
            "municipio": "Palotina",
            "local_entrega": Contem("Delegacia de Palotina"),
            "responsavel_recebimento": Contem("Dirceu"),
            "bairro": "Centro",
            "data_solicitacao": UmDe("2026-10-28", "2026-10-29"),
        },
        nota="Encaminhado dentro do .eml: pedido é do Dirceu, não da colega da ASCOM.",
    ),
    Caso(
        id="cof-061",
        modulo="coffee_break",
        formato="texto",
        agora="2026-11-12 16:10",
        texto="""
[12/11/2026 16:00] Inv. Beto: coffee p 20 amanha 9h aqui na 13ª, reunião de equipe. eu recebo
""",
        esperado={
            "descricao_evento": Contem("reunião"),
            "data_inicio_evento": "2026-11-13",
            "horario_evento": "09:00",
            "quantidade": 20,
            "local_entrega": Contem("13ª"),
            "responsavel_recebimento": Contem("Beto"),
            "endereco": AUSENTE,
            "cep": AUSENTE,
            "data_solicitacao": "2026-11-12",
        },
        nota="Mensagem mínima; município não informado (fora do gabarito), nada de endereço.",
    ),
    Caso(
        id="cof-062",
        modulo="coffee_break",
        formato="eml",
        agora="2026-10-01 10:00",
        texto=_eml(
            "Delegado Samuel Pontarolo <samuel.pontarolo@pc.pr.gov.br>",
            _ASCOM,
            "coffee break - Curso de Cadeia de Custódia",
            "2026-10-01 09:02",
            """
Prezados,

Solicito coffee break para 33 pessoas no Curso de Cadeia de Custódia, dia 14/10.
O curso será das 13h às 17h; o coffee às 15h.

Local: Auditório da Delegacia de Wenceslau Braz, Rua Frei Mathias, 410 - Centro.
Recebe: Escrivã Adriana Beltrame.
""",
        ),
        esperado={
            "descricao_evento": Contem("Cadeia de Custódia"),
            "data_inicio_evento": "2026-10-14",
            "horario_evento": "15:00",
            "quantidade": 33,
            "municipio": "Wenceslau Braz",
            "local_entrega": Contem("Delegacia de Wenceslau Braz"),
            "responsavel_recebimento": Contem("Adriana Beltrame"),
            "endereco": Contem("Rua Frei Mathias, 410"),
            "bairro": "Centro",
            "data_solicitacao": "2026-10-01",
        },
        nota="Curso 13h–17h; coffee 15h.",
    ),
    Caso(
        id="cof-063",
        modulo="coffee_break",
        formato="texto",
        agora="2026-09-29 14:00",
        texto="""
---------- Forwarded message ---------
De: Escrivão Valter Coutinho <valter.coutinho@pc.pr.gov.br>
Date: ter., 29 de set. de 2026 às 10:02
Subject: coffee reunião técnica Cambé
To: ASCOM PCPR <ascom@pc.pr.gov.br>

Bom dia. Solicito coffee break para 16 pessoas, Reunião Técnica de Inteligência,
no dia 1º de outubro, às 8h30, na sede da Delegacia de Cambé, Rua Pará, 100 - Centro.
Recebe: Valter.
""",
        esperado={
            "descricao_evento": Contem("Reunião Técnica"),
            "data_inicio_evento": "2026-10-01",
            "horario_evento": "08:30",
            "quantidade": 16,
            "municipio": "Cambé",
            "local_entrega": Contem("Delegacia de Cambé"),
            "responsavel_recebimento": Contem("Valter"),
            "endereco": Contem("Rua Pará, 100"),
            "bairro": "Centro",
            "data_solicitacao": "2026-09-29",
        },
        nota="'1º de outubro' com ordinal; mudança de mês.",
    ),
    Caso(
        id="cof-064",
        modulo="coffee_break",
        formato="eml",
        agora="2026-09-29 15:00",
        texto=_eml(
            "Protocolo DPC <protocolo.dpc@pc.pr.gov.br>",
            _ASCOM,
            "Ofício nº 233/2026-DPC - coffee break",
            "2026-09-29 11:10",
            """
OFÍCIO Nº 233/2026-DPC
Curitiba, 28 de setembro de 2026.

Senhor Assessor,

Solicito coffee break para 50 pessoas no Fórum Metropolitano de Segurança
Pública, no dia 13 de outubro, às 14h, no Auditório da Prefeitura de Almirante
Tamandaré, Av. Emílio Johnson, 360 - Centro, Almirante Tamandaré.
Responsável pelo recebimento: Investigador Célio Dalazen.

Atenciosamente,
Delegado Diretor
""",
        ),
        esperado={
            "descricao_evento": Contem("Fórum Metropolitano"),
            "data_inicio_evento": "2026-10-13",
            "horario_evento": "14:00",
            "quantidade": 50,
            "municipio": "Almirante Tamandaré",
            "local_entrega": Contem("Auditório da Prefeitura"),
            "responsavel_recebimento": Contem("Célio Dalazen"),
            "endereco": Contem("Av. Emílio Johnson, 360"),
            "bairro": "Centro",
            "data_solicitacao": UmDe("2026-09-28", "2026-09-29"),
        },
        nota="'Curitiba, 28 de setembro' é local/data do ofício: município é Almirante Tamandaré.",
    ),
    Caso(
        id="cof-065",
        modulo="coffee_break",
        formato="eml",
        agora="2026-11-03 10:00",
        texto=_eml(
            "Investigadora Mariane Voigt <mariane.voigt@pc.pr.gov.br>",
            _ASCOM,
            _q("Coffee – Oficina de Registro de Ocorrências – Ivaiporã"),
            "2026-11-03 08:22",
            """
Bom dia,

Serão 3 turmas de 15 na Oficina de Registro de Ocorrências, todas no mesmo
horário, dia 16/11 às 10h. Solicito coffee break para todos.

Local: Auditório do Colégio Estadual Barão do Cerro Azul, Rua Paraná, 123 -
Centro, Ivaiporã.
Recebe: Mariane.
""",
        ),
        esperado={
            "descricao_evento": Contem("Registro de Ocorrências"),
            "data_inicio_evento": "2026-11-16",
            "horario_evento": "10:00",
            "quantidade": 45,
            "municipio": "Ivaiporã",
            "local_entrega": Contem("Colégio Estadual Barão do Cerro Azul"),
            "responsavel_recebimento": Contem("Mariane"),
            "endereco": Contem("Rua Paraná, 123"),
            "bairro": "Centro",
            "data_solicitacao": "2026-11-03",
        },
        nota="3 turmas de 15 = 45.",
    ),
    Caso(
        id="cof-066",
        modulo="coffee_break",
        formato="texto",
        agora="2026-10-20 09:30",
        texto="""
De: Escrivão Moacir Stadler <moacir.stadler@pc.pr.gov.br>
Enviado em: terça-feira, 20 de outubro de 2026 09:05
Para: ASCOM PCPR
Assunto: coffee sexta

Bom dia! Solicito coffee break para 30 pessoas nesta sexta-feira, às 14h, para a
Reunião de Balanço Trimestral, na Delegacia de Fazenda Rio Grande, Av. das
Américas, 2000 - Eucaliptos. Quem recebe: Moacir.
""",
        esperado={
            "descricao_evento": Contem("Balanço Trimestral"),
            "data_inicio_evento": "2026-10-23",
            "horario_evento": "14:00",
            "quantidade": 30,
            "municipio": "Fazenda Rio Grande",
            "local_entrega": Contem("Delegacia de Fazenda Rio Grande"),
            "responsavel_recebimento": Contem("Moacir"),
            "bairro": "Eucaliptos",
            "data_solicitacao": "2026-10-20",
        },
        nota="'nesta sexta-feira' a partir de terça 20/10 = 23/10.",
    ),
    Caso(
        id="cof-067",
        modulo="coffee_break",
        formato="eml",
        agora="2026-10-13 16:00",
        texto=_eml(
            "Núcleo de Operações com Cães <noc@pc.pr.gov.br>",
            _ASCOM,
            "Coffee break - Formatura do Curso de Cães de Faro",
            "2026-10-13 14:18",
            """
Prezados,

Solicitamos coffee break para 55 pessoas na Formatura do Curso de Cães de Faro,
no dia 30 de outubro, às 10h30.

Local: Canil Central da PCPR, Rodovia BR-277, km 115, Campo Largo – CEP: 83.601-000
Recebimento: Investigador Fausto Wendler, (41) 3292-0000.
""",
            html=True,
        ),
        esperado={
            "descricao_evento": Contem("Cães de Faro"),
            "data_inicio_evento": "2026-10-30",
            "horario_evento": "10:30",
            "quantidade": 55,
            "municipio": "Campo Largo",
            "local_entrega": Contem("Canil Central"),
            "responsavel_recebimento": Contem("Fausto Wendler"),
            "endereco": Contem("BR-277, km 115"),
            "cep": "83601-000",
            "data_solicitacao": "2026-10-13",
        },
        nota="HTML; rodovia com km; CEP com ponto e dois-pontos.",
    ),
    Caso(
        id="cof-068",
        modulo="coffee_break",
        formato="eml",
        agora="2026-11-16 15:00",
        texto=_eml(
            "Divisão de Inteligência <dint@pc.pr.gov.br>",
            _ASCOM,
            "Coffee - Seminário de Inteligência em Maringá",
            "2026-11-16 13:25",
            """
Senhores,

O Seminário Estadual de Inteligência será em Maringá, nos dias 3 e 4 de
dezembro, no Hotel Central de Maringá. Precisamos de coffee apenas no dia 3, às
15h, para 90 pessoas. Recebe no local: Agente Marcelo Fontana.

Divisão de Inteligência – PCPR
Rua José Loureiro, 376 – Centro – Curitiba/PR – CEP 80010-000
""",
        ),
        esperado={
            "descricao_evento": Contem("Seminário Estadual de Inteligência"),
            "data_inicio_evento": "2026-12-03",
            "horario_evento": "15:00",
            "quantidade": 90,
            "municipio": "Maringá",
            "local_entrega": Contem("Hotel Central"),
            "responsavel_recebimento": Contem("Marcelo Fontana"),
            "endereco": AUSENTE,
            "bairro": AUSENTE,
            "cep": AUSENTE,
            "data_solicitacao": "2026-11-16",
        },
        nota="Evento de 2 dias, coffee só no 1º; endereço/CEP de Curitiba só na assinatura.",
    ),
    Caso(
        id="cof-069",
        modulo="coffee_break",
        formato="texto",
        agora="2026-11-02 10:00",
        texto="""
[02/11/2026 09:10] Inv. Carla Mendes: bom dia! o coffee de ontem foi ótimo, obrigada
[02/11/2026 09:11] Inv. Carla Mendes: agora preciso p dia 10/11, 20 pessoas, 14h, palestra sobre Estatuto do Idoso
[02/11/2026 09:12] Inv. Carla Mendes: na Delegacia de Santo Antônio da Platina, Rua Rui Barbosa, 510 - Centro. eu recebo
""",
        esperado={
            "descricao_evento": Contem("Estatuto do Idoso"),
            "data_inicio_evento": "2026-11-10",
            "horario_evento": "14:00",
            "quantidade": 20,
            "municipio": "Santo Antônio da Platina",
            "local_entrega": Contem("Delegacia de Santo Antônio da Platina"),
            "responsavel_recebimento": Contem("Carla"),
            "endereco": Contem("Rua Rui Barbosa, 510"),
            "bairro": "Centro",
            "data_solicitacao": "2026-11-02",
        },
        nota="'o coffee de ontem' é outro evento; o pedido é 10/11.",
    ),
    Caso(
        id="cof-070",
        modulo="coffee_break",
        formato="eml",
        agora="2026-11-10 17:00",
        texto=_eml(
            "Delegada Tânia Szymanski <tania.szymanski@pc.pr.gov.br>",
            _ASCOM,
            "coffee palestra feminicídio Goioerê",
            "2026-11-10 16:30",
            """
Boa tarde,

Esperamos entre 40 e 50 pessoas na Palestra sobre Feminicídio, dia 25/11 às 19h.
Pode mandar coffee para 50.

Local: Câmara Municipal de Goioerê, Av. Amazonas, 1000 - Centro.
Recebe: Escrivã Luzia.
""",
        ),
        esperado={
            "descricao_evento": Contem("Feminicídio"),
            "data_inicio_evento": "2026-11-25",
            "horario_evento": "19:00",
            "quantidade": 50,
            "municipio": "Goioerê",
            "local_entrega": Contem("Câmara Municipal"),
            "responsavel_recebimento": Contem("Luzia"),
            "endereco": Contem("Av. Amazonas, 1000"),
            "bairro": "Centro",
            "data_solicitacao": "2026-11-10",
        },
        nota="'entre 40 e 50' mas pede para 50: 50.",
    ),
    Caso(
        id="cof-071",
        modulo="coffee_break",
        formato="eml",
        agora="2026-10-19 11:00",
        texto=_eml(
            "Investigador Hélio Brasil <helio.brasil@pc.pr.gov.br>",
            _ASCOM,
            "Coffee reunião regional Bandeirantes",
            "2026-10-19 10:05",
            """
Bom dia,

Solicito coffee break para 26 pessoas na Reunião Regional de Planejamento, dia
28/10. Por favor entregar até as 9h45 para servirmos às 10h.

Local: Delegacia de Bandeirantes, Av. Prefeito Moysés Lupion, 1200 - Centro.
Recebe: Hélio.
""",
        ),
        esperado={
            "descricao_evento": Contem("Reunião Regional de Planejamento"),
            "data_inicio_evento": "2026-10-28",
            "horario_evento": UmDe("09:45", "10:00"),
            "quantidade": 26,
            "municipio": "Bandeirantes",
            "local_entrega": Contem("Delegacia de Bandeirantes"),
            "responsavel_recebimento": Contem("Hélio"),
            "endereco": Contem("Av. Prefeito Moysés Lupion, 1200"),
            "bairro": "Centro",
            "data_solicitacao": "2026-10-19",
        },
        nota="Entrega 9h45 x servir 10h: as duas valem; 'Brasil' é sobrenome.",
    ),
    Caso(
        id="cof-072",
        modulo="coffee_break",
        formato="texto",
        agora="2026-11-06 10:00",
        texto="""
De: Escrivão Mário Lazzarotto <mario.lazzarotto@pc.pr.gov.br>
Enviado em: sexta-feira, 6 de novembro de 2026 09:20
Para: ASCOM PCPR
Assunto: RE: coffee Curso de Técnicas de Investigação

Dia 19/11, às 15h, no auditório da Delegacia de Loanda. Recebe: Escrivão Mário.

De: ASCOM PCPR
Enviado em: quinta-feira, 5 de novembro de 2026 17:02
Para: Escrivão Mário Lazzarotto
Assunto: RE: coffee Curso de Técnicas de Investigação

Prezado, favor informar data, horário e local de entrega.

De: Escrivão Mário Lazzarotto
Enviado em: quinta-feira, 5 de novembro de 2026 15:40
Para: ASCOM PCPR
Assunto: coffee Curso de Técnicas de Investigação

Boa tarde, solicito coffee para 30 pessoas no Curso de Técnicas de Investigação.
""",
        esperado={
            "descricao_evento": Contem("Técnicas de Investigação"),
            "data_inicio_evento": "2026-11-19",
            "horario_evento": "15:00",
            "quantidade": 30,
            "municipio": "Loanda",
            "local_entrega": Contem("Delegacia de Loanda"),
            "responsavel_recebimento": Contem("Mário"),
            "data_solicitacao": UmDe("2026-11-05", "2026-11-06"),
        },
        nota="Informações espalhadas na conversa citada (quantidade só no e-mail original).",
    ),
    Caso(
        id="cof-073",
        modulo="coffee_break",
        formato="eml",
        agora="2026-10-27 17:00",
        texto=_eml(
            "Guarda de Treinamento – Delegacia de Araucária <treinamento.araucaria@pc.pr.gov.br>",
            _ASCOM,
            "Coffee - Treinamento de Tiro Araucária",
            "2026-10-27 15:33",
            """
Prezados,

Solicitamos coffee break para o Treinamento de Tiro na quinta-feira, 5/11, às
10h. Pessoas: 45 (quarenta e cinco).

Local: Estande da Guarda Municipal de Araucária, Rua Pedro Druszcz, 111 - Centro.
Recebe: Investigador Gerson Lech.
""",
        ),
        esperado={
            "descricao_evento": Contem("Treinamento de Tiro"),
            "data_inicio_evento": "2026-11-05",
            "horario_evento": "10:00",
            "quantidade": 45,
            "municipio": "Araucária",
            "local_entrega": Contem("Estande"),
            "responsavel_recebimento": Contem("Gerson Lech"),
            "endereco": Contem("Rua Pedro Druszcz, 111"),
            "bairro": "Centro",
            "data_solicitacao": "2026-10-27",
        },
        nota="Quantidade com extenso entre parênteses; data curta '5/11'.",
    ),
    Caso(
        id="cof-074",
        modulo="coffee_break",
        formato="eml",
        agora="2026-11-13 11:00",
        texto=_eml(
            "Delegado Fabrício Zanchet <fabricio.zanchet@pc.pr.gov.br>",
            _ASCOM,
            _q("Solicitação de coffee – Curso de Inteligência Policial"),
            "2026-11-13 10:10",
            """
Prezados,

Solicito coffee break para 35 pessoas no Curso de Inteligência Policial, no dia
30/11, às 15h.

Local de entrega: Centro de Treinamento da 15ª SDP
Avenida Brasil, 5000 - Centro, Cascavel/PR, CEP 85801-000
Recebimento: Investigador Juliano Rech.
""",
        ),
        esperado={
            "descricao_evento": Contem("Inteligência Policial"),
            "data_inicio_evento": "2026-11-30",
            "horario_evento": "15:00",
            "quantidade": 35,
            "municipio": "Cascavel",
            "local_entrega": Contem("Centro de Treinamento"),
            "responsavel_recebimento": Contem("Juliano Rech"),
            "endereco": Contem("Avenida Brasil, 5000"),
            "bairro": "Centro",
            "cep": "85801-000",
            "data_solicitacao": "2026-11-13",
        },
        nota="'Avenida Brasil' não é país/estado; CEP na mesma linha.",
    ),
    Caso(
        id="cof-075",
        modulo="coffee_break",
        formato="texto",
        agora="2026-10-20 18:00",
        texto="""
Boa tarde,
solicito coffee para 60 pessoas na Aula Inaugural do Curso de Especialização em
Investigação Criminal, dia 6 de novembro às 19h30.
Auditório do Centro de Estudos
Rua Sergipe, 900 - Centro
Londrina - PR, 86010-360
Quem recebe: Investigadora Natália Guedes

Enviado do meu iPhone
""",
        esperado={
            "descricao_evento": Contem("Aula Inaugural"),
            "data_inicio_evento": "2026-11-06",
            "horario_evento": "19:30",
            "quantidade": 60,
            "municipio": "Londrina",
            "local_entrega": Contem("Centro de Estudos"),
            "responsavel_recebimento": Contem("Natália Guedes"),
            "endereco": Contem("Rua Sergipe, 900"),
            "bairro": "Centro",
            "cep": "86010-360",
        },
        nota="CEP sem rótulo 'CEP'; 'Rua Sergipe' não é estado.",
    ),
    Caso(
        id="cof-076",
        modulo="coffee_break",
        formato="texto",
        agora="2026-10-07 11:00",
        texto="""
Bom dia, pessoal. Desconsiderar o pedido anterior (dia 14/10, 20 pessoas). O novo
pedido é para 21/10, às 14h, para 28 pessoas, mesmo evento: Reunião de Delegados
da 14ª SDP, no Auditório da 14ª SDP, Rua XV de Novembro, 7050 - Centro, Guarapuava.
Recebe: Escrivã Rosângela.
""",
        esperado={
            "descricao_evento": Contem("Reunião de Delegados"),
            "data_inicio_evento": "2026-10-21",
            "horario_evento": "14:00",
            "quantidade": 28,
            "municipio": "Guarapuava",
            "local_entrega": Contem("Auditório da 14ª SDP"),
            "responsavel_recebimento": Contem("Rosângela"),
            "endereco": Contem("Rua XV de Novembro, 7050"),
            "bairro": "Centro",
        },
        nota="Pedido anterior (14/10, 20) desconsiderado; 'XV de Novembro' não é data.",
    ),
    Caso(
        id="cof-077",
        modulo="coffee_break",
        formato="eml",
        agora="2026-11-06 14:00",
        texto=_eml(
            "Investigador Dorival Carneiro <dorival.carneiro@pc.pr.gov.br>",
            _ASCOM,
            "coffee - curso de negociação - Castro",
            "2026-11-06 12:08",
            """
Olá,

Solicito coffee para 40 pessoas no Curso de Negociação em Crises, dia 26/11,
horário a confirmar (informo até a semana que vem).

Local: Auditório da Delegacia de Castro, Rua Doutor Jorge Xavier da Silva, 100 -
Centro, Castro.
Recebe: Dorival.
""",
        ),
        esperado={
            "descricao_evento": Contem("Negociação em Crises"),
            "data_inicio_evento": "2026-11-26",
            "horario_evento": AUSENTE,
            "quantidade": 40,
            "municipio": "Castro",
            "local_entrega": Contem("Delegacia de Castro"),
            "responsavel_recebimento": Contem("Dorival"),
            "endereco": Contem("Rua Doutor Jorge Xavier da Silva, 100"),
            "bairro": "Centro",
            "data_solicitacao": "2026-11-06",
        },
        nota="Horário a confirmar: AUSENTE.",
    ),
    Caso(
        id="cof-078",
        modulo="coffee_break",
        formato="texto",
        agora="2026-11-25 09:00",
        texto="""
Evento: Workshop de Perícia Digital
Data: 08/12/2026
Horário: 14h
Quantidade: 25
Local de entrega: Laboratório de Informática da ESPC, Rua Tenente Francisco Ferreira de Souza, 2600 - Hauer, Curitiba
Responsável: Investigador Caio Ribeiro – ramal 4420
Prazo para confirmação do pedido: 01/12
""",
        esperado={
            "descricao_evento": Contem("Perícia Digital"),
            "data_inicio_evento": "2026-12-08",
            "horario_evento": "14:00",
            "quantidade": 25,
            "municipio": "Curitiba",
            "local_entrega": Contem("Laboratório de Informática"),
            "responsavel_recebimento": Contem("Caio Ribeiro"),
            "endereco": Contem("Rua Tenente Francisco Ferreira de Souza, 2600"),
            "bairro": "Hauer",
        },
        nota="Lista de campos; 'prazo para confirmação 01/12' não é data do evento.",
    ),
    Caso(
        id="cof-079",
        modulo="coffee_break",
        formato="eml",
        agora="2026-11-05 15:00",
        texto=_eml(
            "Gabinete 5ª SDP <gabinete.5sdp@pc.pr.gov.br>",
            _ASCOM,
            "Reunião de Delegados do Sudoeste - coffee",
            "2026-11-05 13:47",
            """
Prezados,

Solicitamos coffee break para a Reunião de Delegados do Sudoeste, no dia 17/11,
às 9h, para 25 pessoas.

Local: Auditório da 5ª SDP, Rua Itabira, 1500 - Centro, Pato Branco.
Recebimento: Escrivã Solange Dal Molin.

Gabinete – 5ª SDP

"""
            + _SIGILO,
            html=True,
        ),
        esperado={
            "descricao_evento": Contem("Reunião de Delegados do Sudoeste"),
            "data_inicio_evento": "2026-11-17",
            "horario_evento": "09:00",
            "quantidade": 25,
            "municipio": "Pato Branco",
            "local_entrega": Contem("Auditório da 5ª SDP"),
            "responsavel_recebimento": Contem("Solange Dal Molin"),
            "endereco": Contem("Rua Itabira, 1500"),
            "bairro": "Centro",
            "data_solicitacao": "2026-11-05",
        },
        nota="HTML com aviso de confidencialidade (Lei 13.709/2018 não é número útil).",
    ),
    Caso(
        id="cof-080",
        modulo="coffee_break",
        formato="texto",
        agora="2026-11-26 17:30",
        texto="""
[26/11/2026 17:02] Esc. Paulo Roberto – 7ª SDP: boa tarde ascom
[26/11/2026 17:03] Esc. Paulo Roberto – 7ª SDP: coffee pra segunda que vem, no intervalo das 10h, 50 pessoas, Encontro de Conselhos Tutelares
[26/11/2026 17:04] Esc. Paulo Roberto – 7ª SDP: no Auditório da Prefeitura de Umuarama, Av. Rio Branco, 3717 - Centro
[26/11/2026 17:04] Esc. Paulo Roberto – 7ª SDP: recebe a investigadora Célia
""",
        esperado={
            "descricao_evento": Contem("Conselhos Tutelares"),
            "data_inicio_evento": "2026-11-30",
            "horario_evento": "10:00",
            "quantidade": 50,
            "municipio": "Umuarama",
            "local_entrega": Contem("Auditório da Prefeitura"),
            "responsavel_recebimento": Contem("Célia"),
            "endereco": Contem("Av. Rio Branco, 3717"),
            "bairro": "Centro",
            "data_solicitacao": "2026-11-26",
        },
        nota="'segunda que vem' a partir de quinta 26/11 = 30/11; recebe Célia, não o remetente.",
    ),
]
