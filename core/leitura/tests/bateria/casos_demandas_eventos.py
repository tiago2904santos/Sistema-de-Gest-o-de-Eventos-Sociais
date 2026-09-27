"""Bateria do módulo `demandas_eventos` (Palestras e eventos da ASCOM).

Pedidos de palestra e de participação da PCPR em eventos: escolas, CRAS,
empresas, igrejas, conselhos, universidades, associações. Todos os nomes,
telefones, e-mails, endereços e números de protocolo são inventados.

Convenções do gabarito deste módulo:

- ``evento`` é o tipo da coluna "Evento" da planilha (choice
  `TipoEventoPalestra`): ``"PALESTRA"`` quando pedem palestra/fala,
  ``"EVENTO"`` quando convidam a PCPR para um evento que não é palestra
  (solenidade, desfile, feira, formatura), ``"PCPR_NA_COMUNIDADE"`` só quando
  o programa é citado pelo nome. Na dúvida, fica fora.
- ``data_solicitacao`` é a data em que o pedido foi feito (data do e-mail,
  da mensagem de WhatsApp, do recado ou do ofício). Quando o ofício e o envio
  têm datas diferentes, ou o pedido chegou encaminhado, as duas valem (`UmDe`).
  Texto colado sem data nenhuma do pedido: fica fora do gabarito.
- ``data_fim_evento`` só entra quando o evento tem mais de um dia.
- ``solicitante``: a instituição que pede (ou a pessoa, quando não há
  instituição). ``palestrantes`` só quando pedem nominalmente um servidor do
  cadastro; servidor citado que não está no cadastro, ou que só assina o
  encaminhamento, não é palestrante pedido.
- ``local``/``endereco``/``bairro``/``cep``: o lugar do EVENTO. Endereço da
  assinatura, da delegacia que encaminhou ou da sede de quem pede (quando o
  evento é em outro lugar) não é o do evento.
- ``canal_solicitacao``: "EMAIL" para e-mail (.eml ou colado do Outlook/
  Gmail), "WHATSAPP" para conversa de WhatsApp, "TELEFONE"/"PRESENCIAL" para
  recado de atendimento, "PROTOCOLO" quando o pedido chegou pelo eProtocolo
  (aí ``protocolo`` é o número).
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
        f"Message-ID: <{dt:%Y%m%d%H%M}.{sum(map(ord, assunto)) % 10**8}@mail.exemplo.test>",
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


_ASCOM = "ASCOM - Polícia Civil do Paraná <ascom.palestras@pc.pr.gov.br>"
_M = "demandas_eventos"

CADASTROS = {
    "tema": [
        "Drogas",
        "Bullying",
        "Violência doméstica",
        "Crimes cibernéticos",
        "Segurança da mulher",
        "Golpes e fraudes",
        "Trânsito",
        "Abuso sexual infantil",
        "Violência escolar",
        "Violência contra a pessoa idosa",
        "Carreira policial",
        "Assédio moral e sexual",
        "Tráfico de pessoas",
        "Educação para a cidadania",
        "Armas de fogo e desarmamento",
    ],
    "palestrante": [
        "Marcelo Tomaszewski",
        "Andréia Kovalski Lemos",
        "Ricardo Faoro",
        "Juliana Bittencourt Mehl",
        "Everton Scheffer",
        "Patrícia Andrade Zanlorenzi",
        "Cláudio Wosniak",
        "Fernanda Trevisan",
        "Rogério Batistella",
        "Simone Czelusniak",
        "Leandro Pacheco Gusso",
        "Tatiane Rauber",
    ],
}

CASOS = [
    # ------------------------------------------------------------------ 001
    Caso(
        id="dem-001",
        modulo=_M,
        formato="eml",
        agora="2026-09-22 10:00",
        texto=_eml(
            "Colégio Estadual Professor Brandão <cepbrandao.irati@escola.pr.gov.br>",
            _ASCOM,
            "Pedido de palestra sobre drogas",
            "2026-09-21 09:14",
            """
Bom dia,

O Colégio Estadual Professor Brandão, de Irati-PR, solicita uma palestra sobre
prevenção ao uso de drogas para os alunos do ensino médio.

Data: 20/10
Horário: 19h (turma do noturno)
Local: aqui no colégio, Rua XV de Novembro, 1200 - Centro
Público: cerca de 200 alunos

Ficamos no aguardo.

Silvana Dombrowski
Direção
Colégio Estadual Professor Brandão
(42) 3422-1187
""",
        ),
        esperado={
            "evento": "PALESTRA",
            "temas": ["Drogas"],
            "solicitante": Contem("Colégio Estadual Professor Brandão"),
            "email": "cepbrandao.irati@escola.pr.gov.br",
            "telefone": Contem("3422-1187"),
            "data_inicio_evento": "2026-10-20",
            "hora_inicio": "19:00",
            "municipio": "Irati",
            "estado": "PR",
            "quantidade_publico": 200,
            "canal_solicitacao": "EMAIL",
            "data_solicitacao": "2026-09-21",
            "local": Contem("Colégio Estadual Professor Brandão"),
            "endereco": Contem("Rua XV de Novembro, 1200"),
            "bairro": "Centro",
        },
        nota="Caso-base; 'Irati-PR' desambigua Irati (existe também em SC); '20/10' sem ano.",
    ),
    # ------------------------------------------------------------------ 002
    Caso(
        id="dem-002",
        modulo=_M,
        formato="eml",
        agora="2026-10-01 09:30",
        texto=_eml(
            "CRAS Lagoão <cras.lagoao@palmas.pr.gov.br>",
            _ASCOM,
            _q("Solicitação – palestra Lei Maria da Penha (grupo PAIF)"),
            "2026-09-30 15:02",
            """
Prezados, boa tarde.

O CRAS Lagoão, da Secretaria Municipal de Assistência Social de Palmas,
gostaria de solicitar uma palestra sobre violência doméstica e Lei Maria da
Penha para o grupo de mulheres do PAIF.

O encontro será no dia 5 de novembro (quinta-feira), às 14h, na sede do CRAS,
Rua Bandeirantes, 455 - Bairro Lagoão. Participam em média 40 mulheres.

Agradecemos desde já.

Elaine Cristina Wojcik
Assistente Social - CRAS Lagoão
Secretaria Municipal de Assistência Social - Palmas/PR
Fone: (46) 3263-4410
Horário de atendimento: segunda a sexta, 8h às 12h e 13h30 às 17h30
""",
            html=True,
        ),
        esperado={
            "evento": "PALESTRA",
            "temas": ["Violência doméstica"],
            "solicitante": Contem("CRAS Lagoão"),
            "email": "cras.lagoao@palmas.pr.gov.br",
            "telefone": Contem("3263-4410"),
            "data_inicio_evento": "2026-11-05",
            "hora_inicio": "14:00",
            "municipio": "Palmas",
            "estado": "PR",
            "quantidade_publico": 40,
            "canal_solicitacao": "EMAIL",
            "data_solicitacao": "2026-09-30",
            "local": Contem("CRAS Lagoão"),
            "endereco": Contem("Rua Bandeirantes, 455"),
            "bairro": "Lagoão",
        },
        nota="'Rua Bandeirantes' não é o município Bandeirantes; expediente '8h às 12h' não é a hora.",
    ),
    # ------------------------------------------------------------------ 003
    Caso(
        id="dem-003",
        modulo=_M,
        formato="texto",
        agora="2026-09-29 11:00",
        texto="""
De: Recursos Humanos - Móveis Nogueira <rh@moveisnogueira.com.br>
Enviado em: segunda-feira, 28 de setembro de 2026 15:32
Para: ASCOM PCPR <ascom.palestras@pc.pr.gov.br>
Assunto: SIPAT 2026 - convite para palestra

Boa tarde!

Somos da Indústria de Móveis Nogueira Ltda., em Arapongas. Nossa SIPAT 2026
acontece de 3 a 5 de novembro e gostaríamos muito de uma palestra da Polícia
Civil sobre golpes e fraudes (golpe do Pix, falso boleto, falsa central
bancária) no dia 4, às 8h30.

A palestra seria no refeitório da fábrica: Rodovia PR-218, km 3,
Parque Industrial II. Estimamos cerca de 350 colaboradores.

Att.,
Karina Szymanski
Analista de RH
(43) 3252-7788 ramal 214
""",
        esperado={
            "evento": "PALESTRA",
            "temas": ["Golpes e fraudes"],
            "solicitante": Contem("Móveis Nogueira"),
            "email": "rh@moveisnogueira.com.br",
            "telefone": Contem("3252-7788"),
            "data_inicio_evento": "2026-11-04",
            "hora_inicio": "08:30",
            "municipio": "Arapongas",
            "estado": "PR",
            "quantidade_publico": 350,
            "canal_solicitacao": "EMAIL",
            "data_solicitacao": "2026-09-28",
            "endereco": Contem("Rodovia PR-218, km 3"),
            "bairro": "Parque Industrial II",
        },
        nota="A SIPAT vai de 3 a 5/11, mas a palestra é só no dia 4 às 8h30; Outlook colado.",
    ),
    # ------------------------------------------------------------------ 004
    Caso(
        id="dem-004",
        modulo=_M,
        formato="texto",
        agora="2026-10-03 08:40",
        texto="""
[02/10/2026 19:41] Pr. Valdir Ramos: boa noite, a paz
[02/10/2026 19:42] Pr. Valdir Ramos: sou pastor da Igreja Batista Renascer aqui em Castro, queria ver se a policia civil pode fazer uma palestra sobre drogas pros nossos jovens
[02/10/2026 19:43] Pr. Valdir Ramos: seria sabado dia 17 as 19h30 no templo, rua coronel jorge marcondes 310 vila rio branco
[02/10/2026 19:44] Pr. Valdir Ramos: uns 80 jovens mais ou menos
[02/10/2026 19:44] Pr. Valdir Ramos: meu numero é esse mesmo 42 99876-5521 Deus abençoe
""",
        esperado={
            "evento": "PALESTRA",
            "temas": ["Drogas"],
            "solicitante": Contem("Igreja Batista Renascer"),
            "telefone": Contem("5521"),
            "data_inicio_evento": "2026-10-17",
            "hora_inicio": "19:30",
            "municipio": "Castro",
            "estado": "PR",
            "quantidade_publico": 80,
            "canal_solicitacao": "WHATSAPP",
            "data_solicitacao": "2026-10-02",
            "endereco": Contem("rua coronel jorge marcondes"),
            "bairro": UmDe("Vila Rio Branco", "vila rio branco"),
        },
        nota="WhatsApp tudo minúsculo; 'sabado dia 17' sem mês = outubro; bairro 'Rio Branco' lembra município.",
    ),
    # ------------------------------------------------------------------ 005
    Caso(
        id="dem-005",
        modulo=_M,
        formato="eml",
        agora="2026-09-21 14:00",
        texto=_eml(
            "Protocolo Geral - DG <protocolo.dg@pc.pr.gov.br>",
            _ASCOM,
            "Protocolo 23.456.781-4 - SEMED Telêmaco Borba - Semana de Prevenção ao Bullying",
            "2026-09-18 10:47",
            """
Encaminho o protocolo em epígrafe para análise e providências dessa ASCOM.

Protocolo Geral - Gabinete do Delegado-Geral
Av. Iguaçu, 470 - Rebouças - Curitiba/PR

------------------------------------------------------------

Telêmaco Borba, 15 de setembro de 2026.

OFÍCIO Nº 087/2026 - SEMED

Ao Senhor Delegado-Geral da Polícia Civil do Paraná

Assunto: Solicitação de palestras - Semana Municipal de Prevenção ao Bullying

Senhor Delegado-Geral,

A Secretaria Municipal de Educação de Telêmaco Borba realizará, nos dias 10,
11 e 12 de novembro de 2026, a Semana Municipal de Prevenção ao Bullying, com
atividades em todas as escolas da rede municipal, atendendo aproximadamente
1.500 estudantes do 4º e 5º anos.

Solicitamos a participação de policiais civis para palestras sobre bullying
e suas consequências. Pedimos manifestação até 30/09/2026.

Contato: semed@telemacoborba.pr.gov.br / (42) 3271-9040.

Respeitosamente,

ADRIANA PRZYBYSZ
Secretária Municipal de Educação
""",
        ),
        esperado={
            "temas": ["Bullying"],
            "solicitante": Contem("Secretaria Municipal de Educação"),
            "email": "semed@telemacoborba.pr.gov.br",
            "telefone": Contem("3271-9040"),
            "data_inicio_evento": "2026-11-10",
            "data_fim_evento": "2026-11-12",
            "municipio": "Telêmaco Borba",
            "estado": "PR",
            "quantidade_publico": 1500,
            "canal_solicitacao": "PROTOCOLO",
            "protocolo": "23.456.781-4",
            "data_solicitacao": UmDe("2026-09-15", "2026-09-18"),
            "endereco": AUSENTE,
            "bairro": AUSENTE,
        },
        nota="Ofício via eProtocolo; data do ofício e prazo 30/09 não são o evento; endereço do Protocolo Geral (Curitiba) não é o do evento.",
    ),
    # ------------------------------------------------------------------ 006
    Caso(
        id="dem-006",
        modulo=_M,
        formato="texto",
        agora="2026-10-20 16:00",
        texto="""
boa tarde quero pedir uma palestra sobre golpe de telefone e whatsapp pros idoso do grupo da terceira idade aqui de pinhao
seria dia 14 11 2026 as 14 hs no salao da igreja matriz
vem umas 60 pessoa
qualquer coisa fala com dona cida 42 99811-2034
""",
        esperado={
            "evento": "PALESTRA",
            "temas": ["Golpes e fraudes"],
            "telefone": Contem("2034"),
            "data_inicio_evento": "2026-11-14",
            "hora_inicio": "14:00",
            "municipio": "Pinhão",
            "estado": "PR",
            "quantidade_publico": 60,
            "local": Contem("igreja matriz"),
        },
        nota="Sem acento nem pontuação; '14 11 2026' com espaços; 'pinhao' sem til.",
    ),
    # ------------------------------------------------------------------ 007
    Caso(
        id="dem-007",
        modulo=_M,
        formato="eml",
        agora="2026-09-16 09:00",
        texto=_eml(
            "Delegacia de Cianorte <dp.cianorte@pc.pr.gov.br>",
            _ASCOM,
            "Fwd: Palestra crimes ciberneticos - CE Vinicius de Moraes",
            "2026-09-15 08:31",
            """
Prezados da ASCOM, encaminho pedido recebido nesta unidade para as providências.

Att.
Escrivão Hélio Marchetti
Delegacia de Polícia de Cianorte
Av. América, 2000 - Zona 1 - Cianorte/PR
Atendimento ao público: 8h30 às 18h

---------- Forwarded message ---------
De: Direção CE Vinícius de Moraes <direcao.cevm@escola.pr.gov.br>
Date: seg., 14 de set. de 2026 às 10:22
Subject: Palestra crimes ciberneticos
To: <dp.cianorte@pc.pr.gov.br>

Bom dia, senhores.

O Colégio Estadual Vinícius de Moraes solicita uma palestra sobre crimes
cibernéticos e exposição nas redes sociais para 3 turmas de 35 alunos do
9º ano, no dia 08/10, no período da manhã.

Nosso endereço: Rua Ipiranga, 1045 - Zona 2.

Grata,
Profª Denise Kaminski - Diretora
(44) 3629-1450
""",
            html=True,
        ),
        esperado={
            "evento": "PALESTRA",
            "temas": ["Crimes cibernéticos"],
            "solicitante": Contem("Vinícius de Moraes"),
            "email": "direcao.cevm@escola.pr.gov.br",
            "telefone": Contem("3629-1450"),
            "data_inicio_evento": "2026-10-08",
            "hora_inicio": AUSENTE,
            "municipio": "Cianorte",
            "estado": "PR",
            "canal_solicitacao": "EMAIL",
            "data_solicitacao": UmDe("2026-09-14", "2026-09-15"),
            "local": Contem("Vinícius de Moraes"),
            "endereco": Contem("Rua Ipiranga, 1045"),
            "bairro": "Zona 2",
        },
        nota="Encaminhado pela delegacia: endereço e expediente da assinatura do escrivão não são do evento; 'período da manhã' não vira hora.",
    ),
    # ------------------------------------------------------------------ 008
    Caso(
        id="dem-008",
        modulo=_M,
        formato="eml",
        agora="2026-09-25 13:10",
        texto=_eml(
            "Coordenação de Direito - Faculdade Campos Gerais <direito@fcg-exemplo.edu.br>",
            _ASCOM,
            _q("Convite – XV Semana Acadêmica de Direito"),
            "2026-09-24 17:55",
            """
Prezada Assessoria de Comunicação,

A Coordenação do Curso de Direito da Faculdade Campos Gerais, em Ponta Grossa,
convida a Polícia Civil do Paraná para compor a mesa de debates sobre tráfico
de pessoas na XV Semana Acadêmica de Direito.

Data: 20.10.2026
Horário: 19h30
Local: Auditório do Bloco B - Av. Visconde de Taunay, 1800 - Ronda
Público estimado: cerca de 300 acadêmicos

Se possível, gostaríamos de contar com a Delegada Fernanda Trevisan, que
esteve conosco na edição de 2025 (12/09/2025) e foi muito elogiada.

Atenciosamente,

Prof. Me. Otávio Rehbein
Coordenador do Curso de Direito
(42) 3220-4455
""",
        ),
        esperado={
            "temas": ["Tráfico de pessoas"],
            "palestrantes": ["Fernanda Trevisan"],
            "solicitante": Contem("Faculdade Campos Gerais"),
            "email": "direito@fcg-exemplo.edu.br",
            "telefone": Contem("3220-4455"),
            "data_inicio_evento": "2026-10-20",
            "hora_inicio": "19:30",
            "municipio": "Ponta Grossa",
            "estado": "PR",
            "quantidade_publico": 300,
            "canal_solicitacao": "EMAIL",
            "data_solicitacao": "2026-09-24",
            "local": Contem("Auditório do Bloco B"),
            "endereco": Contem("Av. Visconde de Taunay, 1800"),
            "bairro": "Ronda",
        },
        nota="Data '20.10.2026' com pontos; data da edição de 2025 é armadilha; palestrante pedida pelo nome.",
    ),
    # ------------------------------------------------------------------ 009
    Caso(
        id="dem-009",
        modulo=_M,
        formato="eml",
        agora="2026-10-06 10:20",
        texto=_eml(
            "EEB Frei Rogério <eeb.freirogerio@sed.sc.gov.br>",
            _ASCOM,
            _q("Solicitação de palestra sobre bullying – Porto União/SC"),
            "2026-10-05 11:40",
            """
Bom dia!

Somos a Escola de Educação Básica Frei Rogério, de Porto União (SC), cidade
vizinha a União da Vitória. Sabemos que é outro estado, mas muitos de nossos
alunos moram do lado paranaense e gostaríamos de uma palestra sobre bullying.

Data sugerida: 12/11, às 13h30
Endereço: Rua Prudente de Morais, 540 - Centro - Porto União/SC - CEP 89400-000
Público: 180 alunos do 6º ao 9º ano

Obrigada!
Luciane Hoffmann - Orientadora Educacional
(42) 3522-0971
""",
        ),
        esperado={
            "evento": "PALESTRA",
            "temas": ["Bullying"],
            "solicitante": Contem("Frei Rogério"),
            "email": "eeb.freirogerio@sed.sc.gov.br",
            "telefone": Contem("3522-0971"),
            "data_inicio_evento": "2026-11-12",
            "hora_inicio": "13:30",
            "municipio": "Porto União",
            "estado": "SC",
            "quantidade_publico": 180,
            "canal_solicitacao": "EMAIL",
            "data_solicitacao": "2026-10-05",
            "local": Contem("Frei Rogério"),
            "endereco": Contem("Rua Prudente de Morais, 540"),
            "bairro": "Centro",
            "cep": "89400-000",
        },
        nota="Evento em SC; União da Vitória (PR) só é citada como vizinha.",
    ),
    # ------------------------------------------------------------------ 010
    Caso(
        id="dem-010",
        modulo=_M,
        formato="texto",
        agora="2026-10-05 14:00",
        texto="""
[05/10/2026 08:12] Profª Rosângela: Bom dia! Aqui é a Rosângela, pedagoga do Colégio Estadual do Campo Santa Rosa, de Cruz Machado
[05/10/2026 08:13] Profª Rosângela: Gostaríamos de uma palestra sobre drogas para os alunos, pode ser dia 22/10?
[05/10/2026 08:15] Profª Rosângela: ops, corrigindo: dia 23/10, sexta, às 10h. O dia 22 temos conselho de classe
[05/10/2026 08:16] Profª Rosângela: Fica na Linha Santa Rosa, s/n, interior. São uns 120 alunos
""",
        esperado={
            "evento": "PALESTRA",
            "temas": ["Drogas"],
            "solicitante": Contem("Colégio Estadual do Campo Santa Rosa"),
            "data_inicio_evento": "2026-10-23",
            "hora_inicio": "10:00",
            "municipio": "Cruz Machado",
            "estado": "PR",
            "quantidade_publico": 120,
            "canal_solicitacao": "WHATSAPP",
            "data_solicitacao": "2026-10-05",
            "local": Contem("Colégio Estadual do Campo Santa Rosa"),
            "endereco": Contem("Linha Santa Rosa"),
        },
        nota="A data é corrigida na mensagem seguinte (22/10 → 23/10).",
    ),
    # ------------------------------------------------------------------ 011
    Caso(
        id="dem-011",
        modulo=_M,
        formato="eml",
        agora="2026-10-14 15:00",
        texto=_eml(
            "Conselho Municipal dos Direitos da Mulher <cmdm@campolargo.pr.gov.br>",
            _ASCOM,
            "Seminário Mulheres Seguras - 25 de novembro",
            "2026-10-13 16:20",
            """
Prezados,

O Conselho Municipal dos Direitos da Mulher de Campo Largo realizará o
Seminário "Mulheres Seguras", em alusão ao Dia Internacional pela Eliminação
da Violência contra a Mulher.

Gostaríamos de uma palestra sobre segurança da mulher e autodefesa.

Quando: 25 de novembro, às 8h30
Onde: Teatro Municipal Bento Mossurunga
Rua Xavier da Silva, 1500 - Centro
Público previsto: 250 pessoas

Aguardamos confirmação até o dia 06/11.

Cordialmente,
Márcia Bortolini
Presidente do CMDM
(41) 3291-5050
""",
        ),
        esperado={
            "evento": "PALESTRA",
            "temas": ["Segurança da mulher"],
            "solicitante": Contem("Conselho Municipal dos Direitos da Mulher"),
            "email": "cmdm@campolargo.pr.gov.br",
            "telefone": Contem("3291-5050"),
            "data_inicio_evento": "2026-11-25",
            "hora_inicio": "08:30",
            "municipio": "Campo Largo",
            "estado": "PR",
            "quantidade_publico": 250,
            "canal_solicitacao": "EMAIL",
            "data_solicitacao": "2026-10-13",
            "local": Contem("Teatro Municipal Bento Mossurunga"),
            "endereco": Contem("Rua Xavier da Silva, 1500"),
            "bairro": "Centro",
        },
        nota="Prazo de confirmação 06/11 não é a data; endereço em linha separada do local.",
    ),
    # ------------------------------------------------------------------ 012
    Caso(
        id="dem-012",
        modulo=_M,
        formato="eml",
        agora="2026-10-08 11:00",
        texto=_eml(
            "Escola Municipal Rio Negro <em.rionegro@educacao.curitiba.pr.gov.br>",
            _ASCOM,
            "palestra",
            "2026-10-08 07:52",
            """
Bom dia

A Escola Municipal Rio Negro, aqui de Curitiba, pede uma palestra sobre
abuso sexual infantil (autoproteção) para as famílias, na próxima terça às 18h.

Rua Ponta Grossa, 870 - Portão

Obrigada
Vanessa Tulio - pedagoga
41 3345-8820
""",
        ),
        esperado={
            "evento": "PALESTRA",
            "temas": ["Abuso sexual infantil"],
            "solicitante": Contem("Escola Municipal Rio Negro"),
            "email": "em.rionegro@educacao.curitiba.pr.gov.br",
            "telefone": Contem("3345-8820"),
            "data_inicio_evento": "2026-10-13",
            "hora_inicio": "18:00",
            "municipio": "Curitiba",
            "estado": "PR",
            "canal_solicitacao": "EMAIL",
            "data_solicitacao": "2026-10-08",
            "local": Contem("Escola Municipal Rio Negro"),
            "endereco": Contem("Rua Ponta Grossa, 870"),
            "bairro": "Portão",
        },
        nota="'Rio Negro' é nome da escola e 'Ponta Grossa' é rua; o município é Curitiba; 'próxima terça' a partir de qui 08/10.",
    ),
    # ------------------------------------------------------------------ 013
    Caso(
        id="dem-013",
        modulo=_M,
        formato="texto",
        agora="2026-11-09 17:30",
        texto="""
[09/11/2026 16:58] Cristiane Direção: Boa tarde! A palestra de trânsito que combinamos com o investigador pode ser amanhã às 8h?
[09/11/2026 16:59] Cristiane Direção: É para os alunos do 1º ano da Escola Estadual Toledo, aqui em Cascavel
[09/11/2026 17:01] Cristiane Direção: Rua Paraná, 3200, Centro. Uns 90 alunos
""",
        esperado={
            "evento": "PALESTRA",
            "temas": ["Trânsito"],
            "solicitante": Contem("Escola Estadual Toledo"),
            "data_inicio_evento": "2026-11-10",
            "hora_inicio": "08:00",
            "municipio": "Cascavel",
            "estado": "PR",
            "quantidade_publico": 90,
            "canal_solicitacao": "WHATSAPP",
            "data_solicitacao": "2026-11-09",
            "local": Contem("Escola Estadual Toledo"),
            "endereco": Contem("Rua Paraná, 3200"),
            "bairro": "Centro",
            "palestrantes": AUSENTE,
        },
        nota="'amanhã às 8h' relativo à mensagem; 'Toledo' é nome da escola, o município é Cascavel; investigador sem nome.",
    ),
    # ------------------------------------------------------------------ 014
    Caso(
        id="dem-014",
        modulo=_M,
        formato="eml",
        agora="2026-08-12 09:00",
        texto=_eml(
            _q("Associação Comercial e Empresarial de Umuarama") + " <acium@acium-exemplo.com.br>",
            _ASCOM,
            _q("Café Empresarial – Golpes contra o comércio"),
            "2026-08-11 10:05",
            """
Prezados,

A Associação Comercial e Empresarial de Umuarama (ACIUM) promove mensalmente o
Café Empresarial e gostaria de convidar a Polícia Civil para falar sobre
golpes e fraudes contra o comércio (cheque, cartão clonado, falso fornecedor).

O café será no dia 03/09, às 7h30, na sede da ACIUM:
Av. Presidente Castelo Branco, 3777 - Zona I
CEP 87501-170

Esperamos cerca de 120 empresários.

Atenciosamente,
Giovana Parolin
Eventos ACIUM
(44) 3621-2020
""",
            html=True,
        ),
        esperado={
            "evento": "PALESTRA",
            "temas": ["Golpes e fraudes"],
            "solicitante": Contem("Associação Comercial"),
            "email": "acium@acium-exemplo.com.br",
            "telefone": Contem("3621-2020"),
            "data_inicio_evento": "2026-09-03",
            "hora_inicio": "07:30",
            "municipio": "Umuarama",
            "estado": "PR",
            "quantidade_publico": 120,
            "canal_solicitacao": "EMAIL",
            "data_solicitacao": "2026-08-11",
            "local": Contem("ACIUM"),
            "endereco": Contem("Av. Presidente Castelo Branco, 3777"),
            "bairro": "Zona I",
            "cep": "87501-170",
        },
        nota="Nome do remetente codificado; 'Castelo Branco' na avenida; CEP em linha separada.",
    ),
    # ------------------------------------------------------------------ 015
    Caso(
        id="dem-015",
        modulo=_M,
        formato="eml",
        agora="2026-10-19 10:00",
        texto=_eml(
            "Mariluz Ferreira <mariluz.ferreira@exemplo-mail.com>",
            _ASCOM,
            "Palestra para o Clube de Mães",
            "2026-10-16 21:14",
            """
Olá, boa noite.

Me chamo Mariluz Ferreira e coordeno o Clube de Mães Esperança, em Apucarana.
Queria saber se é possível uma palestra sobre violência contra a pessoa idosa
para as nossas associadas e seus pais, no sábado dia 7 de novembro, das 14h às
16h, no salão do clube (Rua Munhoz da Rocha, 88 - Vila Nova).

Somos umas 50 pessoas.

Abraço,
Mariluz
(43) 99920-1187

Enviado do meu iPhone
""",
        ),
        esperado={
            "evento": "PALESTRA",
            "temas": ["Violência contra a pessoa idosa"],
            "solicitante": Contem("Clube de Mães Esperança"),
            "email": "mariluz.ferreira@exemplo-mail.com",
            "telefone": Contem("99920-1187"),
            "data_inicio_evento": "2026-11-07",
            "hora_inicio": "14:00",
            "municipio": "Apucarana",
            "estado": "PR",
            "quantidade_publico": 50,
            "canal_solicitacao": "EMAIL",
            "data_solicitacao": "2026-10-16",
            "endereco": Contem("Rua Munhoz da Rocha, 88"),
            "bairro": "Vila Nova",
        },
        nota="'Mariluz' é o nome da pessoa, não o município; 'das 14h às 16h' → hora 14:00.",
    ),
    # ------------------------------------------------------------------ 016
    Caso(
        id="dem-016",
        modulo=_M,
        formato="eml",
        agora="2026-10-07 09:15",
        texto=_eml(
            "Colégio Estadual Arminda Kuster <ce.armindakuster@escola.pr.gov.br>",
            _ASCOM,
            "RE: Palestra violência escolar - mudança de data",
            "2026-10-06 13:48",
            """
Boa tarde!

Confirmando a alteração: por causa das provas, a palestra sobre violência
escolar passa para o dia 17/11, mesmo horário (9h). O restante continua igual.

Obrigada pela compreensão.

Juliane Stresser
Equipe Pedagógica
Colégio Estadual Arminda Kuster - Guarapuava
(42) 3623-5190

Em sex., 2 de out. de 2026 às 10:05, Colégio Estadual Arminda Kuster <ce.armindakuster@escola.pr.gov.br> escreveu:
> Bom dia,
> Solicitamos palestra sobre violência escolar para 220 alunos no dia
> 10/11, às 9h, no ginásio do colégio (Rua Saldanha Marinho, 1500 -
> Santa Cruz), em Guarapuava.
> Atenciosamente, Equipe Pedagógica
""",
        ),
        esperado={
            "evento": "PALESTRA",
            "temas": ["Violência escolar"],
            "solicitante": Contem("Arminda Kuster"),
            "email": "ce.armindakuster@escola.pr.gov.br",
            "telefone": Contem("3623-5190"),
            "data_inicio_evento": "2026-11-17",
            "hora_inicio": "09:00",
            "municipio": "Guarapuava",
            "estado": "PR",
            "quantidade_publico": 220,
            "canal_solicitacao": "EMAIL",
            "data_solicitacao": UmDe("2026-10-02", "2026-10-06"),
            "local": Contem("ginásio do colégio"),
            "endereco": Contem("Rua Saldanha Marinho, 1500"),
            "bairro": "Santa Cruz",
        },
        nota="Mensagem citada tem a data antiga (10/11); vale a nova (17/11) do topo.",
    ),
    # ------------------------------------------------------------------ 017
    Caso(
        id="dem-017",
        modulo=_M,
        formato="texto",
        agora="2026-10-14 16:40",
        texto="""
RECADO - 14/10/2026 - 15h20 - atendido pela estagiária Bruna

Ligou a Sra. Joana Pietrobelli, secretária da APAE de Jacarezinho, pedindo
palestra sobre abuso sexual infantil para os pais dos alunos.
Dia 28/10 às 19h, na própria APAE (Rua Coronel Cecílio Rocha, 500 - Vila Setti).
Mais ou menos 70 pais.
Retornar no (43) 3525-1144.
""",
        esperado={
            "evento": "PALESTRA",
            "temas": ["Abuso sexual infantil"],
            "solicitante": Contem("APAE"),
            "telefone": Contem("3525-1144"),
            "data_inicio_evento": "2026-10-28",
            "hora_inicio": "19:00",
            "municipio": "Jacarezinho",
            "estado": "PR",
            "quantidade_publico": 70,
            "canal_solicitacao": "TELEFONE",
            "data_solicitacao": "2026-10-14",
            "local": Contem("APAE"),
            "endereco": Contem("Rua Coronel Cecílio Rocha, 500"),
            "bairro": "Vila Setti",
        },
        nota="Recado de telefone: 15h20 é a hora do recado, não do evento.",
    ),
    # ------------------------------------------------------------------ 018
    Caso(
        id="dem-018",
        modulo=_M,
        formato="eml",
        agora="2026-08-20 10:00",
        texto=_eml(
            "Gabinete - Prefeitura de Bandeirantes <gabinete@bandeirantes-exemplo.pr.gov.br>",
            _ASCOM,
            _q("Convite – Desfile Cívico de 7 de Setembro"),
            "2026-08-19 14:30",
            """
Bandeirantes, 18 de agosto de 2026.

Senhor(a) Assessor(a),

O Município de Bandeirantes tem a honra de convidar a Polícia Civil do Paraná
para participar do Desfile Cívico em comemoração à Independência, com efetivo e
viaturas, no dia 7 de setembro de 2026, com concentração às 8h e início às 9h,
na Avenida Brasil (concentração em frente à Praça da Matriz).

Público esperado: aproximadamente 5.000 pessoas.

Solicitamos a confirmação até 28/08.

Respeitosamente,

Gabinete do Prefeito
(43) 3542-4500
""",
        ),
        esperado={
            "evento": "EVENTO",
            "solicitante": Contem("Bandeirantes"),
            "email": "gabinete@bandeirantes-exemplo.pr.gov.br",
            "telefone": Contem("3542-4500"),
            "data_inicio_evento": "2026-09-07",
            "hora_inicio": UmDe("08:00", "09:00"),
            "municipio": "Bandeirantes",
            "estado": "PR",
            "quantidade_publico": 5000,
            "canal_solicitacao": "EMAIL",
            "data_solicitacao": UmDe("2026-08-18", "2026-08-19"),
            "endereco": Contem("Avenida Brasil"),
            "temas": AUSENTE,
        },
        nota="Convite para desfile (EVENTO, sem tema); data do ofício e prazo 28/08 são armadilhas.",
    ),
    # ------------------------------------------------------------------ 019
    Caso(
        id="dem-019",
        modulo=_M,
        formato="eml",
        agora="2026-10-19 15:00",
        texto=_eml(
            "Priscila Andretta <priscila.andretta@autopecaskreutz.com.br>",
            _ASCOM,
            "Treinamento lideranças - assédio",
            "2026-10-19 11:26",
            """
Olá, tudo bem?

Sou do RH da Autopeças Kreutz, em São José dos Pinhais. Estamos com um ciclo
de treinamento para as lideranças e gostaríamos de uma palestra sobre assédio
moral e sexual no ambiente de trabalho.

Seria na semana que vem, na quinta-feira, às 14h, no nosso auditório:
Rua Joinville, 2500 - São Pedro.

São 45 líderes.

Obrigada!
Priscila Andretta
Business Partner RH
(41) 3382-6600 | (41) 99655-0142
""",
        ),
        esperado={
            "evento": "PALESTRA",
            "temas": ["Assédio moral e sexual"],
            "solicitante": Contem("Autopeças Kreutz"),
            "email": "priscila.andretta@autopecaskreutz.com.br",
            "data_inicio_evento": "2026-10-29",
            "hora_inicio": "14:00",
            "municipio": "São José dos Pinhais",
            "estado": "PR",
            "quantidade_publico": 45,
            "canal_solicitacao": "EMAIL",
            "data_solicitacao": "2026-10-19",
            "endereco": Contem("Rua Joinville, 2500"),
            "bairro": "São Pedro",
        },
        nota="'semana que vem, na quinta' a partir de seg 19/10 → 29/10; 'Rua Joinville' não é o município (SC).",
    ),
    # ------------------------------------------------------------------ 020
    Caso(
        id="dem-020",
        modulo=_M,
        formato="texto",
        agora="2026-11-04 10:00",
        texto="""
---------- Forwarded message ---------
De: Thaís Machado <thais.machado@colombo-exemplo.pr.gov.br>
Date: ter., 3 de nov. de 2026 às 09:12
Subject: PCPR na Comunidade - Guaraituba
To: Andréia Kovalski Lemos <andreia.lemos@pc.pr.gov.br>

Oi Andréia, tudo bem? Como conversamos, segue o pedido oficial:

A Secretaria de Assistência Social de Colombo, por meio do CRAS Guaraituba,
solicita a realização do PCPR na Comunidade no dia 5/12 (sábado), a partir das
9h, no Ginásio de Esportes do Guaraituba - Rua Dom Pedro I, 1400.

Pedimos também uma fala sobre drogas para os adolescentes do Serviço de
Convivência. Público estimado de 400 pessoas ao longo do dia.

Thaís Machado
Coordenadora CRAS Guaraituba
(41) 3656-7120
""",
        esperado={
            "evento": "PCPR_NA_COMUNIDADE",
            "temas": ["Drogas"],
            "solicitante": Contem("CRAS Guaraituba"),
            "email": "thais.machado@colombo-exemplo.pr.gov.br",
            "telefone": Contem("3656-7120"),
            "data_inicio_evento": "2026-12-05",
            "hora_inicio": "09:00",
            "municipio": "Colombo",
            "estado": "PR",
            "quantidade_publico": 400,
            "canal_solicitacao": "EMAIL",
            "data_solicitacao": "2026-11-03",
            "local": Contem("Ginásio de Esportes do Guaraituba"),
            "endereco": Contem("Rua Dom Pedro I, 1400"),
            "palestrantes": AUSENTE,
        },
        nota="Encaminhado a uma servidora cadastrada (Andréia) — ela é destinatária, não palestrante pedida.",
    ),
    # ------------------------------------------------------------------ 021
    Caso(
        id="dem-021",
        modulo=_M,
        formato="eml",
        agora="2026-11-10 08:30",
        texto=_eml(
            "Jéssica Castro <jessica.castro@oesteforte-exemplo.coop.br>",
            _ASCOM,
            "SIPAT Cooperativa Oeste Forte - palestra",
            "2026-11-09 17:03",
            """
Boa tarde,

A Cooperativa Agroindustrial Oeste Forte, de Toledo, convida a Polícia Civil
para uma palestra sobre crimes cibernéticos na SIPAT, no dia 3 de dezembro de
2026, às 15h, no auditório da matriz (Rua Barão do Rio Branco, 2233 -
Jardim Gisela).

Público: cerca de 600 cooperados e colaboradores.

Atenciosamente,
Jéssica Castro
Técnica em Segurança do Trabalho
(45) 3277-9100
""",
            html=True,
        ),
        esperado={
            "evento": "PALESTRA",
            "temas": ["Crimes cibernéticos"],
            "solicitante": Contem("Oeste Forte"),
            "email": "jessica.castro@oesteforte-exemplo.coop.br",
            "telefone": Contem("3277-9100"),
            "data_inicio_evento": "2026-12-03",
            "hora_inicio": "15:00",
            "municipio": "Toledo",
            "estado": "PR",
            "quantidade_publico": 600,
            "canal_solicitacao": "EMAIL",
            "data_solicitacao": "2026-11-09",
            "local": Contem("auditório da matriz"),
            "endereco": Contem("Rua Barão do Rio Branco, 2233"),
            "bairro": "Jardim Gisela",
        },
        nota="Sobrenome 'Castro' da remetente não é município; 'Rio Branco' na rua.",
    ),
    # ------------------------------------------------------------------ 022
    Caso(
        id="dem-022",
        modulo=_M,
        formato="texto",
        agora="2026-10-27 09:00",
        texto="""
De: Colégio Estadual Dom Alberto Gonçalves <ce.domalberto@escola.pr.gov.br>
Enviado em: segunda-feira, 26 de outubro de 2026 10:11
Para: ascom.palestras@pc.pr.gov.br
Assunto: Feira de Profissões

Prezados,

O Colégio Estadual Dom Alberto Gonçalves, de Palmeira-PR, realizará sua Feira
de Profissões no dia 19/11, das 8h às 12h, e gostaríamos que a Polícia Civil
apresentasse a carreira policial aos alunos do 3º ano (como ingressar,
concursos, rotina de trabalho).

Local: quadra coberta do colégio, Praça Marechal Floriano Peixoto, s/n - Centro.
Cerca de 400 alunos devem circular pela feira.

Atenciosamente,
Direção
(42) 3252-1398
""",
        esperado={
            "temas": ["Carreira policial"],
            "solicitante": Contem("Dom Alberto Gonçalves"),
            "email": "ce.domalberto@escola.pr.gov.br",
            "telefone": Contem("3252-1398"),
            "data_inicio_evento": "2026-11-19",
            "hora_inicio": "08:00",
            "municipio": "Palmeira",
            "estado": "PR",
            "quantidade_publico": 400,
            "canal_solicitacao": "EMAIL",
            "data_solicitacao": "2026-10-26",
            "local": Contem("quadra coberta"),
            "endereco": Contem("Praça Marechal Floriano Peixoto"),
            "bairro": "Centro",
        },
        nota="'Palmeira-PR' (há Palmeira em SC); 'Palmeira' ≠ 'Palmas'.",
    ),
    # ------------------------------------------------------------------ 023
    Caso(
        id="dem-023",
        modulo=_M,
        formato="eml",
        agora="2026-09-30 11:00",
        texto=_eml(
            "CAMARA MUNICIPAL DA LAPA <cerimonial@camaralapa-exemplo.pr.gov.br>",
            _ASCOM,
            "CONVITE SESSAO SOLENE",
            "2026-09-29 16:44",
            """
PREZADOS,

A CÂMARA MUNICIPAL DA LAPA CONVIDA A POLÍCIA CIVIL DO PARANÁ PARA A SESSÃO
SOLENE DE ENTREGA DE MOÇÕES DE APLAUSO AOS POLICIAIS CIVIS DA 22ª DELEGACIA,
NO DIA 21 DE OUTUBRO, ÀS 19H, NO PLENÁRIO DA CÂMARA -
RUA BARÃO DO RIO BRANCO, 1675 - CENTRO HISTÓRICO - LAPA.

PEDIMOS A GENTILEZA DE INFORMAR OS NOMES DOS REPRESENTANTES ATÉ 14/10.

CERIMONIAL
(41) 3622-1230
""",
        ),
        esperado={
            "evento": "EVENTO",
            "solicitante": Contem("Câmara Municipal da Lapa"),
            "email": "cerimonial@camaralapa-exemplo.pr.gov.br",
            "telefone": Contem("3622-1230"),
            "data_inicio_evento": "2026-10-21",
            "hora_inicio": "19:00",
            "municipio": "Lapa",
            "estado": "PR",
            "canal_solicitacao": "EMAIL",
            "data_solicitacao": "2026-09-29",
            "local": Contem("Plenário da Câmara"),
            "endereco": Contem("Rua Barão do Rio Branco, 1675"),
            "bairro": UmDe("Centro Histórico", "CENTRO HISTÓRICO"),
            "temas": AUSENTE,
        },
        nota="Tudo em CAIXA ALTA; sessão solene é EVENTO; prazo 14/10 não é data.",
    ),
    # ------------------------------------------------------------------ 024
    Caso(
        id="dem-024",
        modulo=_M,
        formato="texto",
        agora="2026-10-06 13:00",
        texto="""
ESCOLA MUNICIPAL PROFESSORA OLGA WASILEWSKI
Rua Getúlio Vargas, 1010 - Centro - Prudentópolis - PR
Fone: (42) 3446-2231 - escola.olga@prudentopolis-exemplo.pr.gov.br

Prudentópolis, 02 de outubro de 2026.

OFÍCIO Nº 45/2026

À Assessoria de Comunicação da Polícia Civil do Paraná

Assunto: Solicitação de palestra

Prezados Senhores,

Vimos, respeitosamente, solicitar a realização de palestra sobre bullying e
crimes na internet para os alunos do 5º ano desta escola, no dia 29 de outubro
de 2026, às 13h15, em nossa sede.

Serão aproximadamente 95 alunos.

Certos de contarmos com a vossa colaboração, antecipamos agradecimentos.

Atenciosamente,

LÚCIA HAVRYLIUK
Diretora
""",
        esperado={
            "evento": "PALESTRA",
            "temas": ["Bullying", "Crimes cibernéticos"],
            "solicitante": Contem("Olga Wasilewski"),
            "email": "escola.olga@prudentopolis-exemplo.pr.gov.br",
            "telefone": Contem("3446-2231"),
            "data_inicio_evento": "2026-10-29",
            "hora_inicio": "13:15",
            "municipio": "Prudentópolis",
            "estado": "PR",
            "quantidade_publico": 95,
            "data_solicitacao": "2026-10-02",
            "local": Contem("Olga Wasilewski"),
            "endereco": Contem("Rua Getúlio Vargas, 1010"),
            "bairro": "Centro",
        },
        nota="Ofício colado sem cabeçalho de e-mail: a data do ofício é a da solicitação; o evento é 'em nossa sede' (endereço do timbre vale).",
    ),
    # ------------------------------------------------------------------ 025
    Caso(
        id="dem-025",
        modulo=_M,
        formato="eml",
        agora="2026-10-02 10:30",
        texto=_eml(
            "Curso de Enfermagem - UniNoroeste <enfermagem@uninoroeste-exemplo.edu.br>",
            _ASCOM,
            _q("Semana de Enfermagem – palestra violência doméstica"),
            "2026-10-01 20:10",
            """
Boa noite!

O Curso de Enfermagem do Centro Universitário Noroeste (UniNoroeste), em
Paranavaí, convida a PCPR para palestra sobre violência doméstica e o papel
dos profissionais de saúde na notificação.

Data: 10/11/2026
Horário: 19:30
Local: Anfiteatro Central - Av. Paraná, 5000 - Jardim Ouro Branco

Público de aproximadamente 180 acadêmicos.

PS: no ano passado vocês vieram no dia 08/11/2025 e foi ótimo!

Profª Dra. Heloísa Grzybowski
Coordenadora
(44) 3421-7700
""",
            html=True,
        ),
        esperado={
            "evento": "PALESTRA",
            "temas": ["Violência doméstica"],
            "solicitante": Contem("UniNoroeste"),
            "email": "enfermagem@uninoroeste-exemplo.edu.br",
            "telefone": Contem("3421-7700"),
            "data_inicio_evento": "2026-11-10",
            "hora_inicio": "19:30",
            "municipio": "Paranavaí",
            "estado": "PR",
            "quantidade_publico": 180,
            "canal_solicitacao": "EMAIL",
            "data_solicitacao": "2026-10-01",
            "local": Contem("Anfiteatro Central"),
            "endereco": Contem("Av. Paraná, 5000"),
            "bairro": "Jardim Ouro Branco",
        },
        nota="Data do ano anterior no PS; hora '19:30'.",
    ),
    # ------------------------------------------------------------------ 026
    Caso(
        id="dem-026",
        modulo=_M,
        formato="texto",
        agora="2026-09-14 11:00",
        texto="""
[14/09/2026 10:02] Sec. Educação Mariluz: Bom dia! Aqui é da Secretaria Municipal de Educação de Mariluz
[14/09/2026 10:03] Sec. Educação Mariluz: A gente precisava de uma palestra sobre drogas na Escola Municipal Castro Alves, dia 30/09 as 9 horas
[14/09/2026 10:03] Sec. Educação Mariluz: umas 150 crianças do 4 e 5 ano
""",
        esperado={
            "evento": "PALESTRA",
            "temas": ["Drogas"],
            "solicitante": Contem("Secretaria Municipal de Educação"),
            "data_inicio_evento": "2026-09-30",
            "hora_inicio": "09:00",
            "municipio": "Mariluz",
            "estado": "PR",
            "quantidade_publico": 150,
            "canal_solicitacao": "WHATSAPP",
            "data_solicitacao": "2026-09-14",
            "local": Contem("Escola Municipal Castro Alves"),
        },
        nota="'Castro Alves' é nome de escola, não o município Castro; município é Mariluz.",
    ),
    # ------------------------------------------------------------------ 027
    Caso(
        id="dem-027",
        modulo=_M,
        formato="eml",
        agora="2026-10-26 09:00",
        texto=_eml(
            "Paróquia São Pedro Apóstolo <secretaria@paroquiasaopedro-exemplo.org.br>",
            _ASCOM,
            "Encontro de Casais - pedido de palestra",
            "2026-10-24 10:37",
            """
Paz e bem!

A Pastoral Familiar da Paróquia São Pedro Apóstolo, de Pinhais, realizará o
Encontro de Casais no sábado, 21/11, e pede uma palestra sobre violência
doméstica às 20h.

O encontro será no salão paroquial, Rua Jacob Macanhan, 2100 - Centro.
Participam cerca de 60 casais.

Secretaria Paroquial
Atendimento: terça a sexta das 9h às 17h
(41) 3653-2288
""",
        ),
        esperado={
            "evento": "PALESTRA",
            "temas": ["Violência doméstica"],
            "solicitante": Contem("Paróquia São Pedro Apóstolo"),
            "email": "secretaria@paroquiasaopedro-exemplo.org.br",
            "telefone": Contem("3653-2288"),
            "data_inicio_evento": "2026-11-21",
            "hora_inicio": "20:00",
            "municipio": "Pinhais",
            "estado": "PR",
            "canal_solicitacao": "EMAIL",
            "data_solicitacao": "2026-10-24",
            "local": Contem("salão paroquial"),
            "endereco": Contem("Rua Jacob Macanhan, 2100"),
            "bairro": "Centro",
        },
        nota="'60 casais' — deixado fora do gabarito (120 pessoas é conta); expediente 9h às 17h não é hora.",
    ),
    # ------------------------------------------------------------------ 028
    Caso(
        id="dem-028",
        modulo=_M,
        formato="eml",
        agora="2026-10-05 08:50",
        texto=_eml(
            "Secretaria de Saúde de Céu Azul <saude@ceuazul-exemplo.pr.gov.br>",
            _ASCOM,
            _q("Outubro Rosa – palestra sobre segurança da mulher"),
            "2026-10-02 11:19",
            """
Bom dia!

Dentro da programação do Outubro Rosa, a Secretaria Municipal de Saúde de Céu
Azul gostaria de uma palestra sobre segurança da mulher no dia 22/10 às 19h, no
Centro de Convivência (Av. Nilo Umberto Deitos, 1426 - Centro).

Esperamos umas 150 mulheres.

Att,
Cleusa Brandalise
Enfermeira - Coordenação da Atenção Primária
(45) 3266-1300
""",
        ),
        esperado={
            "evento": "PALESTRA",
            "temas": ["Segurança da mulher"],
            "solicitante": Contem("Secretaria Municipal de Saúde"),
            "email": "saude@ceuazul-exemplo.pr.gov.br",
            "telefone": Contem("3266-1300"),
            "data_inicio_evento": "2026-10-22",
            "hora_inicio": "19:00",
            "municipio": "Céu Azul",
            "estado": "PR",
            "quantidade_publico": 150,
            "canal_solicitacao": "EMAIL",
            "data_solicitacao": "2026-10-02",
            "local": Contem("Centro de Convivência"),
            "endereco": Contem("Av. Nilo Umberto Deitos, 1426"),
            "bairro": "Centro",
        },
        nota="Município de duas palavras comuns ('Céu Azul').",
    ),
    # ------------------------------------------------------------------ 029
    Caso(
        id="dem-029",
        modulo=_M,
        formato="texto",
        agora="2026-10-09 10:00",
        texto="""
oi td bem sou da escola estadual pe anchieta de ivai
precisamos de palestra sobre bulling urgente pq ta tendo mt caso aqui
pode ser dia 16/10 de manha
sao uns 250 alunos
rua antonio santos 45 centro
obg
""",
        esperado={
            "evento": "PALESTRA",
            "temas": ["Bullying"],
            "solicitante": Contem("anchieta"),
            "data_inicio_evento": "2026-10-16",
            "hora_inicio": AUSENTE,
            "municipio": "Ivaí",
            "estado": "PR",
            "quantidade_publico": 250,
            "endereco": Contem("rua antonio santos 45"),
            "bairro": UmDe("Centro", "centro"),
        },
        nota="Sem acento ('ivai', 'bulling'); 'de manha' não é hora.",
    ),
    # ------------------------------------------------------------------ 030
    Caso(
        id="dem-030",
        modulo=_M,
        formato="eml",
        agora="2026-11-12 14:00",
        texto=_eml(
            "NRE Área Metropolitana Sul <nre.ams@educacao.pr.gov.br>",
            _ASCOM,
            "Solicitação de palestra - CE Pedro Druszcz (Araucária)",
            "2026-11-11 09:30",
            """
Prezados,

O Núcleo Regional de Educação da Área Metropolitana Sul solicita, a pedido do
Colégio Estadual Pedro Druszcz, de Araucária, palestra sobre crimes
cibernéticos para os alunos do ensino médio, no dia 3 de dezembro, às 10h.

Local: Colégio Estadual Pedro Druszcz - Rua Victor do Amaral, 845 - Estação.
Aproximadamente 300 alunos.

Atenciosamente,

Equipe de Programas e Projetos
Núcleo Regional de Educação - Área Metropolitana Sul
Rua Engenheiros Rebouças, 1500 - Rebouças - Curitiba/PR - CEP 80215-100
(41) 3312-4400
""",
        ),
        esperado={
            "evento": "PALESTRA",
            "temas": ["Crimes cibernéticos"],
            "email": "nre.ams@educacao.pr.gov.br",
            "data_inicio_evento": "2026-12-03",
            "hora_inicio": "10:00",
            "municipio": "Araucária",
            "estado": "PR",
            "quantidade_publico": 300,
            "canal_solicitacao": "EMAIL",
            "data_solicitacao": "2026-11-11",
            "local": Contem("Colégio Estadual Pedro Druszcz"),
            "endereco": Contem("Rua Victor do Amaral, 845"),
            "bairro": "Estação",
            "cep": AUSENTE,
        },
        nota="Quem envia é o NRE com sede em Curitiba (assinatura com endereço e CEP): o evento é em Araucária.",
    ),
    # ------------------------------------------------------------------ 031
    Caso(
        id="dem-031",
        modulo=_M,
        formato="eml",
        agora="2026-10-15 10:00",
        texto=_eml(
            "OAB Subseção Campo Mourão <eventos@oabcm-exemplo.org.br>",
            _ASCOM,
            _q("II Jornada de Enfrentamento à Violência Doméstica – convite"),
            "2026-10-14 18:02",
            """
Prezados(as),

A Subseção de Campo Mourão da Ordem dos Advogados realizará a II Jornada de
Enfrentamento à Violência Doméstica e Familiar, de 3 a 5 de novembro, sempre às
19h, no auditório da Subseção (Rua Harrison José Borges, 1350 - Centro).

Convidamos a Polícia Civil do Paraná a participar com uma palestra sobre o
atendimento às vítimas de violência doméstica na delegacia. Público estimado de
200 pessoas por noite.

Atenciosamente,
Comissão da Mulher Advogada
(44) 3523-6612
""",
        ),
        esperado={
            "evento": "PALESTRA",
            "temas": ["Violência doméstica"],
            "solicitante": Contem("OAB"),
            "email": "eventos@oabcm-exemplo.org.br",
            "telefone": Contem("3523-6612"),
            "data_inicio_evento": "2026-11-03",
            "data_fim_evento": "2026-11-05",
            "hora_inicio": "19:00",
            "municipio": "Campo Mourão",
            "estado": "PR",
            "quantidade_publico": 200,
            "canal_solicitacao": "EMAIL",
            "data_solicitacao": "2026-10-14",
            "local": Contem("auditório da Subseção"),
            "endereco": Contem("Rua Harrison José Borges, 1350"),
            "bairro": "Centro",
        },
        nota="Período 'de 3 a 5 de novembro' → início e fim.",
    ),
    # ------------------------------------------------------------------ 032
    Caso(
        id="dem-032",
        modulo=_M,
        formato="texto",
        agora="2026-11-05 09:00",
        texto="""
De: CRAS Cachoeira <cras.cachoeira@tamandare-exemplo.pr.gov.br>
Enviado em: quarta-feira, 4 de novembro de 2026 14:27
Para: ASCOM PCPR
Assunto: Palestra drogas - Escola Municipal Vereador Nilo Berlitz

Boa tarde,

Solicitamos palestra sobre prevenção às drogas para os alunos do 5º ano da
Escola Municipal Vereador Nilo Berlitz, na quarta-feira, 18/11, às 9h.

São 3 turmas.

Atenciosamente,

Rosane Veiga
Coordenadora
CRAS Cachoeira - Secretaria Municipal de Assistência Social
Rua Emílio Johnson, 1560 - Cachoeira - Almirante Tamandaré/PR - CEP 83507-000
(41) 3699-8520
""",
        esperado={
            "evento": "PALESTRA",
            "temas": ["Drogas"],
            "solicitante": Contem("CRAS Cachoeira"),
            "email": "cras.cachoeira@tamandare-exemplo.pr.gov.br",
            "telefone": Contem("3699-8520"),
            "data_inicio_evento": "2026-11-18",
            "hora_inicio": "09:00",
            "municipio": "Almirante Tamandaré",
            "estado": "PR",
            "canal_solicitacao": "EMAIL",
            "data_solicitacao": "2026-11-04",
            "local": Contem("Escola Municipal Vereador Nilo Berlitz"),
            "endereco": AUSENTE,
            "bairro": AUSENTE,
            "cep": AUSENTE,
        },
        nota="O endereço é só o do CRAS na assinatura; a palestra é na escola (sem endereço).",
    ),
    # ------------------------------------------------------------------ 033
    Caso(
        id="dem-033",
        modulo=_M,
        formato="eml",
        agora="2026-12-11 10:00",
        texto=_eml(
            "Associação de Moradores de Caiobá <amcaioba@exemplo-mail.com>",
            _ASCOM,
            "Palestra golpes aluguel temporada",
            "2026-12-10 19:40",
            """
Boa noite!

A Associação de Moradores de Caiobá, em Matinhos, gostaria de uma palestra sobre
golpes e fraudes no aluguel de temporada para proprietários de imóveis, antes
do pico do verão.

Pode ser dia 15/01 às 19h, na sede da associação: Av. Atlântica, 3300 - Caiobá.
Umas 70 pessoas.

Grato,
Nelson Gawlik - presidente
(41) 99101-4455
""",
        ),
        esperado={
            "evento": "PALESTRA",
            "temas": ["Golpes e fraudes"],
            "solicitante": Contem("Associação de Moradores de Caiobá"),
            "email": "amcaioba@exemplo-mail.com",
            "telefone": Contem("99101-4455"),
            "data_inicio_evento": "2027-01-15",
            "hora_inicio": "19:00",
            "municipio": "Matinhos",
            "estado": "PR",
            "quantidade_publico": 70,
            "canal_solicitacao": "EMAIL",
            "data_solicitacao": "2026-12-10",
            "local": Contem("sede da associação"),
            "endereco": Contem("Av. Atlântica, 3300"),
            "bairro": "Caiobá",
        },
        nota="Virada de ano: '15/01' pedido em dezembro → 2027.",
    ),
    # ------------------------------------------------------------------ 034
    Caso(
        id="dem-034",
        modulo=_M,
        formato="eml",
        agora="2026-09-10 11:30",
        texto=_eml(
            "Colégio Estadual Souza Naves <ce.souzanaves.rolandia@escola.pr.gov.br>",
            _ASCOM,
            "Palestra para professores - Dra. Juliana Mehl",
            "2026-09-09 13:12",
            """
Boa tarde,

Na reunião pedagógica de outubro gostaríamos de uma palestra sobre assédio
moral e sexual para os professores e funcionários do Colégio Estadual Souza
Naves, de Rolândia. Se possível, com a Dra. Juliana Mehl, que já nos atendeu.

Data: 09/10 (sexta)
Horário: 18h
Local: biblioteca do colégio - Av. Presidente Bernardes, 1011 - Centro
Público: 65 servidores

Atenciosamente,
Direção
(43) 3256-1170
""",
        ),
        esperado={
            "evento": "PALESTRA",
            "temas": ["Assédio moral e sexual"],
            "palestrantes": ["Juliana Bittencourt Mehl"],
            "solicitante": Contem("Souza Naves"),
            "email": "ce.souzanaves.rolandia@escola.pr.gov.br",
            "telefone": Contem("3256-1170"),
            "data_inicio_evento": "2026-10-09",
            "hora_inicio": "18:00",
            "municipio": "Rolândia",
            "estado": "PR",
            "quantidade_publico": 65,
            "canal_solicitacao": "EMAIL",
            "data_solicitacao": "2026-09-09",
            "local": Contem("biblioteca do colégio"),
            "endereco": Contem("Av. Presidente Bernardes, 1011"),
            "bairro": "Centro",
        },
        nota="Palestrante pedida pelo nome abreviado ('Dra. Juliana Mehl'); 'reunião pedagógica de outubro' não é data.",
    ),
    # ------------------------------------------------------------------ 035
    Caso(
        id="dem-035",
        modulo=_M,
        formato="texto",
        agora="2026-12-15 09:00",
        texto="""
[14/12/2026 18:22] Pedagoga Kátia - EM Santa Terezinha: Boa noite, desculpe o horário
[14/12/2026 18:23] Pedagoga Kátia - EM Santa Terezinha: Já queremos garantir para a semana pedagógica do ano que vem uma palestra sobre violência escolar para os professores da Escola Municipal Santa Terezinha, de Fazenda Rio Grande
[14/12/2026 18:24] Pedagoga Kátia - EM Santa Terezinha: Dia 12/02, às 8h, aqui na escola: Rua Caviúna, 520 - Eucaliptos
[14/12/2026 18:24] Pedagoga Kátia - EM Santa Terezinha: umas 40 pessoas
""",
        esperado={
            "evento": "PALESTRA",
            "temas": ["Violência escolar"],
            "solicitante": Contem("Santa Terezinha"),
            "data_inicio_evento": "2027-02-12",
            "hora_inicio": "08:00",
            "municipio": "Fazenda Rio Grande",
            "estado": "PR",
            "quantidade_publico": 40,
            "canal_solicitacao": "WHATSAPP",
            "data_solicitacao": "2026-12-14",
            "local": Contem("Santa Terezinha"),
            "endereco": Contem("Rua Caviúna, 520"),
            "bairro": "Eucaliptos",
        },
        nota="Virada de ano ('ano que vem', 12/02 → 2027); hora da mensagem (18h22) não é a hora.",
    ),
    # ------------------------------------------------------------------ 036
    Caso(
        id="dem-036",
        modulo=_M,
        formato="eml",
        agora="2026-09-01 10:00",
        texto=_eml(
            "CE Barão de Antonina <ce.baraoantonina@escola.pr.gov.br>",
            _ASCOM,
            "Semana Nacional do Trânsito - palestra",
            "2026-08-31 15:18",
            """
Boa tarde!

O Colégio Estadual Barão de Antonina, de Rio Negro-PR (divisa com Mafra/SC),
solicita palestra sobre trânsito para os alunos que estão tirando a primeira
habilitação, na Semana Nacional do Trânsito.

Dia 23/09, às 14h, no auditório do colégio (Rua Dr. Vicente Machado, 520 -
Centro). 110 alunos.

Obrigado,
Edson Wendt - Diretor auxiliar
(47) 3642-2210
""",
        ),
        esperado={
            "evento": "PALESTRA",
            "temas": ["Trânsito"],
            "solicitante": Contem("Barão de Antonina"),
            "email": "ce.baraoantonina@escola.pr.gov.br",
            "telefone": Contem("3642-2210"),
            "data_inicio_evento": "2026-09-23",
            "hora_inicio": "14:00",
            "municipio": "Rio Negro",
            "estado": "PR",
            "quantidade_publico": 110,
            "canal_solicitacao": "EMAIL",
            "data_solicitacao": "2026-08-31",
            "local": Contem("auditório do colégio"),
            "endereco": Contem("Rua Dr. Vicente Machado, 520"),
            "bairro": "Centro",
        },
        nota="Rio Negro (PR) com DDD 47 e Mafra/SC citada; 'Barão de Antonina' não é o município Antonina.",
    ),
    # ------------------------------------------------------------------ 037
    Caso(
        id="dem-037",
        modulo=_M,
        formato="texto",
        agora="2026-10-21 15:00",
        texto="""
Prezados,

A Associação de Moradores do Jardim Araucária, em Campo Mourão, solicita uma
palestra sobre golpes e fraudes pela internet e telefone para a comunidade.

Sugerimos o dia 18 de novembro, às 19h30, no auditório da
Escola Estadual Ivone Castanharo (R. das Flores, s/n, Jardim Araucária).

Contamos com a presença de cerca de 100 moradores.

Sebastião Lemes
Presidente da Associação
(44) 99934-7781
""",
        esperado={
            "evento": "PALESTRA",
            "temas": ["Golpes e fraudes"],
            "solicitante": Contem("Associação de Moradores do Jardim Araucária"),
            "telefone": Contem("99934-7781"),
            "data_inicio_evento": "2026-11-18",
            "hora_inicio": "19:30",
            "municipio": "Campo Mourão",
            "estado": "PR",
            "quantidade_publico": 100,
            "local": Contem("Escola Estadual Ivone Castanharo"),
            "endereco": Contem("R. das Flores"),
            "bairro": "Jardim Araucária",
        },
        nota="Bairro 'Jardim Araucária' não é o município Araucária; texto puro sem data do pedido.",
    ),
    # ------------------------------------------------------------------ 038
    Caso(
        id="dem-038",
        modulo=_M,
        formato="eml",
        agora="2026-10-13 09:45",
        texto=_eml(
            "EEB Santo Antônio <eeb.santoantonio.irati@sed.sc.gov.br>",
            _ASCOM,
            _q("Pedido de palestra – Irati/SC"),
            "2026-10-09 10:10",
            """
Bom dia,

Somos da Escola de Educação Básica Santo Antônio, em Irati/SC (oeste
catarinense, perto de Chapecó). Um professor nosso fez curso em Irati-PR e
indicou a Polícia Civil do Paraná para uma palestra sobre crimes cibernéticos.

Seria no dia 11/11, às 9h, na escola (Rua Sete de Setembro, 210 - Centro).
Público: 90 alunos.

Atenciosamente,
Marlene Pagliosa
Diretora
(49) 3349-0112
""",
        ),
        esperado={
            "evento": "PALESTRA",
            "temas": ["Crimes cibernéticos"],
            "solicitante": Contem("Santo Antônio"),
            "email": "eeb.santoantonio.irati@sed.sc.gov.br",
            "telefone": Contem("3349-0112"),
            "data_inicio_evento": "2026-11-11",
            "hora_inicio": "09:00",
            "municipio": "Irati",
            "estado": "SC",
            "quantidade_publico": 90,
            "canal_solicitacao": "EMAIL",
            "data_solicitacao": "2026-10-09",
            "endereco": Contem("Rua Sete de Setembro, 210"),
            "bairro": "Centro",
        },
        nota="Irati existe no PR e em SC: aqui é SC (Irati-PR só aparece como citação).",
    ),
    # ------------------------------------------------------------------ 039
    Caso(
        id="dem-039",
        modulo=_M,
        formato="eml",
        agora="2026-11-23 16:00",
        texto=_eml(
            "SESMT - Papéis Vale do Jaguari <sesmt@valedojaguari-exemplo.com.br>",
            _ASCOM,
            "Semana do Motorista - palestra de transito",
            "2026-11-23 10:04",
            """
Prezados,

A Papéis Vale do Jaguari S.A., de Jaguariaíva, realiza a Semana do Motorista
para os caminhoneiros terceirizados e solicita uma palestra sobre trânsito
(direção defensiva, álcool e direção, documentação).

Data: dia 16.12
Horário: 7h, antes da troca de turno
Local: pátio de expedição da unidade fabril - Rodovia PR-151, km 212
Público: 130 motoristas

Obs.: o SESMT funciona das 7h às 16h48.

Atenciosamente,
Fabiano Lach
Técnico de Segurança
(43) 3535-8000
""",
            html=True,
        ),
        esperado={
            "evento": "PALESTRA",
            "temas": ["Trânsito"],
            "solicitante": Contem("Vale do Jaguari"),
            "email": "sesmt@valedojaguari-exemplo.com.br",
            "telefone": Contem("3535-8000"),
            "data_inicio_evento": "2026-12-16",
            "hora_inicio": "07:00",
            "municipio": "Jaguariaíva",
            "estado": "PR",
            "quantidade_publico": 130,
            "canal_solicitacao": "EMAIL",
            "data_solicitacao": "2026-11-23",
            "local": Contem("pátio de expedição"),
            "endereco": Contem("Rodovia PR-151, km 212"),
        },
        nota="Data 'dia 16.12' com ponto e sem ano; horário do SESMT não é o do evento.",
    ),
    # ------------------------------------------------------------------ 040
    Caso(
        id="dem-040",
        modulo=_M,
        formato="texto",
        agora="2026-10-20 12:00",
        texto="""
[19/10/2026 21:03] Diretor Anselmo CE Hugo Simas: Boa noite. Aqui é o Anselmo, diretor do Colégio Estadual Hugo Simas, em Londrina
[19/10/2026 21:04] Diretor Anselmo CE Hugo Simas: Os pais gostaram muito da palestra do investigador Everton no ano passado. Dá para ele voltar e falar sobre drogas de novo?
[19/10/2026 21:05] Diretor Anselmo CE Hugo Simas: Seria 05/11 às 19h, reunião de pais. Rua Guilherme de Almeida, 350 - Jardim Bandeirantes
[19/10/2026 21:05] Diretor Anselmo CE Hugo Simas: umas 300 pessoas
""",
        esperado={
            "evento": "PALESTRA",
            "temas": ["Drogas"],
            "palestrantes": ["Everton Scheffer"],
            "solicitante": Contem("Hugo Simas"),
            "data_inicio_evento": "2026-11-05",
            "hora_inicio": "19:00",
            "municipio": "Londrina",
            "estado": "PR",
            "quantidade_publico": 300,
            "canal_solicitacao": "WHATSAPP",
            "data_solicitacao": "2026-10-19",
            "endereco": Contem("Rua Guilherme de Almeida, 350"),
            "bairro": "Jardim Bandeirantes",
        },
        nota="Palestrante só pelo primeiro nome (único no cadastro); bairro 'Jardim Bandeirantes' ≠ município Bandeirantes.",
    ),
    # ------------------------------------------------------------------ 041
    Caso(
        id="dem-041",
        modulo=_M,
        formato="eml",
        agora="2026-11-03 14:20",
        texto=_eml(
            "Conselho Tutelar Zona Sul <ct.zonasul@maringa-exemplo.pr.gov.br>",
            _ASCOM,
            "Capacitação de professores - abuso sexual infantil",
            "2026-11-03 08:55",
            """
Bom dia,

O Conselho Tutelar Zona Sul de Maringá está organizando uma capacitação para
professores da rede municipal sobre identificação de sinais de abuso sexual
infantil e fluxo de denúncia, e gostaria da participação da Polícia Civil.

Data: 26/11
Horário: das 8h às 11h30
Local: Auditório da Secretaria de Educação - Av. XV de Novembro, 701 - Zona 01
Público: 160 professores

Conselheira Débora Nascimento
(44) 3218-3390 / plantão (44) 99976-0012
""",
        ),
        esperado={
            "evento": "PALESTRA",
            "temas": ["Abuso sexual infantil"],
            "solicitante": Contem("Conselho Tutelar"),
            "email": "ct.zonasul@maringa-exemplo.pr.gov.br",
            "telefone": Contem("3218-3390"),
            "data_inicio_evento": "2026-11-26",
            "hora_inicio": "08:00",
            "municipio": "Maringá",
            "estado": "PR",
            "quantidade_publico": 160,
            "canal_solicitacao": "EMAIL",
            "data_solicitacao": "2026-11-03",
            "local": Contem("Auditório da Secretaria de Educação"),
            "endereco": Contem("Av. XV de Novembro, 701"),
            "bairro": "Zona 01",
        },
        nota="Dois telefones: o fixo é o contato; faixa '8h às 11h30' → 08:00.",
    ),
    # ------------------------------------------------------------------ 042
    Caso(
        id="dem-042",
        modulo=_M,
        formato="eml",
        agora="2026-10-08 09:30",
        texto=_eml(
            "Subdivisão Policial de Pato Branco <sdp.patobranco@pc.pr.gov.br>",
            _ASCOM,
            "eProtocolo 24.118.330-7 - Rotary Club Pato Branco - palestra",
            "2026-10-07 17:22",
            """
Senhores,

Encaminho, via eProtocolo nº 24.118.330-7, o pedido do Rotary Club de Pato
Branco para palestra, para análise dessa Assessoria.

Delegado Titular - SDP Pato Branco
Rua Itabira, 1500 - Pato Branco/PR - (46) 3225-1800

=== Documento anexo ao protocolo ===

Pato Branco, 29 de setembro de 2026.

Ao Delegado da Subdivisão Policial de Pato Branco

O Rotary Club de Pato Branco solicita a realização de palestra sobre golpes e
fraudes para seus associados e convidados, na reunião festiva do dia 12 de
novembro de 2026, às 20h, na sede do clube (Rua Tocantins, 1880 - Centro).

Estimamos 90 participantes.

Contato: secretaria@rotarypb-exemplo.org.br - (46) 99111-2323

Paulo Roberto Dall'Agnol
Presidente 2026-2027
""",
        ),
        esperado={
            "evento": "PALESTRA",
            "temas": ["Golpes e fraudes"],
            "solicitante": Contem("Rotary Club"),
            "email": "secretaria@rotarypb-exemplo.org.br",
            "telefone": Contem("99111-2323"),
            "data_inicio_evento": "2026-11-12",
            "hora_inicio": "20:00",
            "municipio": "Pato Branco",
            "estado": "PR",
            "quantidade_publico": 90,
            "canal_solicitacao": "PROTOCOLO",
            "protocolo": "24.118.330-7",
            "data_solicitacao": UmDe("2026-09-29", "2026-10-07"),
            "local": Contem("sede do clube"),
            "endereco": Contem("Rua Tocantins, 1880"),
            "bairro": "Centro",
        },
        nota="eProtocolo pela SDP: telefone/endereço da SDP não são do solicitante nem do evento; 'Presidente 2026-2027' não é data.",
    ),
    # ------------------------------------------------------------------ 043
    Caso(
        id="dem-043",
        modulo=_M,
        formato="texto",
        agora="2026-09-17 10:00",
        texto="""
De: Sindicato Rural de Castro <contato@srcastro-exemplo.org.br>
Enviado em: quarta-feira, 16 de setembro de 2026 09:40
Para: 'ascom.palestras@pc.pr.gov.br'
Assunto: Dia de Campo - palestra armas de fogo

Prezados, bom dia.

O Sindicato Rural de Castro organiza, junto com a Associação Rural de Carambeí,
o Dia de Campo 2026 e gostaria de uma palestra sobre posse e porte de armas de
fogo na propriedade rural (registro, regularização, desarmamento).

O evento será em Carambeí, no dia 15/10, às 10h, no
Pavilhão da Associação Rural - Rua dos Pioneiros, 3000.

Esperamos 250 produtores.

Atenciosamente,
Márcio Van der Neut
Sindicato Rural de Castro
Rua Doutor Jorge Xavier da Silva, 480 - Centro - Castro/PR
(42) 3232-1515
""",
        esperado={
            "evento": "PALESTRA",
            "temas": ["Armas de fogo e desarmamento"],
            "solicitante": Contem("Sindicato Rural de Castro"),
            "email": "contato@srcastro-exemplo.org.br",
            "telefone": Contem("3232-1515"),
            "data_inicio_evento": "2026-10-15",
            "hora_inicio": "10:00",
            "municipio": "Carambeí",
            "estado": "PR",
            "quantidade_publico": 250,
            "canal_solicitacao": "EMAIL",
            "data_solicitacao": "2026-09-16",
            "local": Contem("Pavilhão da Associação Rural"),
            "endereco": Contem("Rua dos Pioneiros, 3000"),
            "bairro": AUSENTE,
        },
        nota="Sede do solicitante em Castro (assinatura com endereço e bairro Centro); o evento é em Carambeí.",
    ),
    # ------------------------------------------------------------------ 044
    Caso(
        id="dem-044",
        modulo=_M,
        formato="eml",
        agora="2026-10-21 10:00",
        texto=_eml(
            "Colégio Estadual Senador Wosgrau <ce.senadorwosgrau@escola.pr.gov.br>",
            _ASCOM,
            _q("Palestra – prevenção às drogas – reunião de pais"),
            "2026-10-20 14:15",
            """
Boa tarde,

O Colégio Estadual Senador Wosgrau, localizado na Rua Cruz Machado, 380 -
Centro, Curitiba, solicita palestra sobre prevenção às drogas para os pais e
responsáveis, no dia 05/11 às 19h, no nosso pátio coberto.

Público aproximado: 200 pessoas.

Grata,
Beatriz Zaniolo - Pedagoga
(41) 3232-0987
""",
            html=True,
        ),
        esperado={
            "evento": "PALESTRA",
            "temas": ["Drogas"],
            "solicitante": Contem("Senador Wosgrau"),
            "email": "ce.senadorwosgrau@escola.pr.gov.br",
            "telefone": Contem("3232-0987"),
            "data_inicio_evento": "2026-11-05",
            "hora_inicio": "19:00",
            "municipio": "Curitiba",
            "estado": "PR",
            "quantidade_publico": 200,
            "canal_solicitacao": "EMAIL",
            "data_solicitacao": "2026-10-20",
            "local": Contem("pátio coberto"),
            "endereco": Contem("Rua Cruz Machado, 380"),
            "bairro": "Centro",
        },
        nota="'Rua Cruz Machado' em Curitiba não é o município Cruz Machado.",
    ),
    # ------------------------------------------------------------------ 045
    Caso(
        id="dem-045",
        modulo=_M,
        formato="eml",
        agora="2026-10-05 08:00",
        texto=_eml(
            "Supermercados Cambeense <gente@cambeense-exemplo.com.br>",
            _ASCOM,
            "Palestra sobre golpes para os operadores de caixa",
            "2026-10-02 16:30",
            """
Olá!

Os Supermercados Cambeense, de Cambé, gostariam de agendar uma palestra sobre
golpes e fraudes (notas falsas, golpe do Pix agendado, troco) para os nossos
operadores de caixa das 4 lojas.

Ainda não temos data: pode ser em novembro, no horário que for melhor para a
Polícia Civil. Nos informem as opções, por favor.

Setor Gente & Gestão
(43) 3251-4040
Rua Pará, 777 - Centro - Cambé/PR
""",
        ),
        esperado={
            "evento": "PALESTRA",
            "temas": ["Golpes e fraudes"],
            "solicitante": Contem("Cambeense"),
            "email": "gente@cambeense-exemplo.com.br",
            "telefone": Contem("3251-4040"),
            "data_inicio_evento": AUSENTE,
            "hora_inicio": AUSENTE,
            "municipio": "Cambé",
            "estado": "PR",
            "canal_solicitacao": "EMAIL",
            "data_solicitacao": "2026-10-02",
            "endereco": AUSENTE,
        },
        nota="Sem data ('em novembro') nem hora; endereço só na assinatura da empresa.",
    ),
    # ------------------------------------------------------------------ 046
    Caso(
        id="dem-046",
        modulo=_M,
        formato="texto",
        agora="2026-11-03 17:00",
        texto="""
ATENDIMENTO PRESENCIAL - 03/11/2026

Compareceu à ASCOM o Sr. Osvaldo Kachuk, presidente do Lions Clube de Irati,
pedindo uma palestra sobre golpes e fraudes contra idosos (falso parente,
falso empréstimo consignado) para os associados e familiares.

Data pretendida: 24/11, às 19h30.
Local: sede do Lions - Rua Coronel Emílio Gomes, 700 - Centro.
Cerca de 80 pessoas.
Telefone dele: (42) 99902-6611.
""",
        esperado={
            "evento": "PALESTRA",
            "temas": ["Golpes e fraudes"],
            "solicitante": Contem("Lions Clube"),
            "telefone": Contem("99902-6611"),
            "data_inicio_evento": "2026-11-24",
            "hora_inicio": "19:30",
            "municipio": "Irati",
            "estado": "PR",
            "quantidade_publico": 80,
            "canal_solicitacao": "PRESENCIAL",
            "data_solicitacao": "2026-11-03",
            "local": Contem("sede do Lions"),
            "endereco": Contem("Rua Coronel Emílio Gomes, 700"),
            "bairro": "Centro",
        },
        nota="Atendimento presencial; golpes contra idosos é tema 'Golpes e fraudes'; Irati com DDD 42 (PR).",
    ),
    # ------------------------------------------------------------------ 047
    Caso(
        id="dem-047",
        modulo=_M,
        formato="eml",
        agora="2026-10-28 11:00",
        texto=_eml(
            "CE Ilha dos Valadares <ce.valadares@escola.pr.gov.br>",
            _ASCOM,
            "Palestra drogas - dois turnos",
            "2026-10-27 09:50",
            """
Bom dia,

O Colégio Estadual Ilha dos Valadares, de Paranaguá, solicita palestra sobre
drogas nos dias 24 e 25/11 (um dia para cada turno), sempre às 10h,
na quadra do colégio: Rua Principal, s/n - Ilha dos Valadares.

Serão cerca de 350 alunos no total.

Direção - (41) 3423-5566
""",
        ),
        esperado={
            "evento": "PALESTRA",
            "temas": ["Drogas"],
            "solicitante": Contem("Ilha dos Valadares"),
            "email": "ce.valadares@escola.pr.gov.br",
            "telefone": Contem("3423-5566"),
            "data_inicio_evento": "2026-11-24",
            "data_fim_evento": "2026-11-25",
            "hora_inicio": "10:00",
            "municipio": "Paranaguá",
            "estado": "PR",
            "quantidade_publico": 350,
            "canal_solicitacao": "EMAIL",
            "data_solicitacao": "2026-10-27",
            "local": Contem("quadra do colégio"),
            "endereco": Contem("Rua Principal, s/n"),
            "bairro": "Ilha dos Valadares",
        },
        nota="Dois dias ('24 e 25/11') com mês só no fim.",
    ),
    # ------------------------------------------------------------------ 048
    Caso(
        id="dem-048",
        modulo=_M,
        formato="texto",
        agora="2026-10-20 09:00",
        texto="""
[20/10/2026 07:55] Diretora Marli: <áudio omitido>
[20/10/2026 07:57] Diretora Marli: Desculpa o áudio, escrevendo: preciso de uma palestra de trânsito para os alunos do 8º e 9º ano aqui em Umuarama
[20/10/2026 07:58] Diretora Marli: Dia 3/11 terça às 14h, no Colégio Estadual Dr. Ângelo Moreira da Fonseca
[20/10/2026 07:58] Diretora Marli: Av. Rio Branco, 3456 - Zona III
""",
        esperado={
            "evento": "PALESTRA",
            "temas": ["Trânsito"],
            "solicitante": Contem("Ângelo Moreira da Fonseca"),
            "data_inicio_evento": "2026-11-03",
            "hora_inicio": "14:00",
            "municipio": "Umuarama",
            "estado": "PR",
            "canal_solicitacao": "WHATSAPP",
            "data_solicitacao": "2026-10-20",
            "local": Contem("Ângelo Moreira da Fonseca"),
            "endereco": Contem("Av. Rio Branco, 3456"),
            "bairro": "Zona III",
        },
        nota="Mensagem de áudio omitida; data '3/11 terça' com dia da semana.",
    ),
    # ------------------------------------------------------------------ 049
    Caso(
        id="dem-049",
        modulo=_M,
        formato="eml",
        agora="2026-10-16 10:00",
        texto=_eml(
            "UMADS - Juventude Assembleia de Deus Sarandi <umads.sarandi@exemplo-mail.com>",
            _ASCOM,
            _q("Congresso de Jovens 2026 – convite para palestra"),
            "2026-10-15 22:31",
            """
A paz do Senhor!

A União de Mocidade da Assembleia de Deus em Sarandi convida a Polícia Civil
para uma palestra sobre drogas e álcool no nosso Congresso de Jovens, nos dias
13 e 14 de novembro, às 19h30, no templo central: Av. Maringá, 1200 -
Jardim Independência.

Público esperado: cerca de 800 jovens por noite.

Ev. Rodrigo Semczuk
Líder de jovens
(44) 99845-3301
""",
            html=True,
        ),
        esperado={
            "evento": "PALESTRA",
            "temas": ["Drogas"],
            "solicitante": Contem("Assembleia de Deus"),
            "email": "umads.sarandi@exemplo-mail.com",
            "telefone": Contem("99845-3301"),
            "data_inicio_evento": "2026-11-13",
            "data_fim_evento": "2026-11-14",
            "hora_inicio": "19:30",
            "municipio": "Sarandi",
            "estado": "PR",
            "quantidade_publico": 800,
            "canal_solicitacao": "EMAIL",
            "data_solicitacao": "2026-10-15",
            "local": Contem("templo central"),
            "endereco": Contem("Av. Maringá, 1200"),
            "bairro": "Jardim Independência",
        },
        nota="'Av. Maringá' não é o município Maringá; e-mail às 22h31 não é hora do evento.",
    ),
    # ------------------------------------------------------------------ 050
    Caso(
        id="dem-050",
        modulo=_M,
        formato="texto",
        agora="2026-09-28 15:00",
        texto="""
---------- Forwarded message ---------
De: Gabinete Dep. Estadual <gabinete.dep.exemplo@assembleia-exemplo.pr.gov.br>
Date: sex., 25 de set. de 2026 às 16:02
Subject: Pedido de palestra - Pitanga
To: ASCOM PCPR <ascom.palestras@pc.pr.gov.br>

Prezados,

A pedido da diretora Sandra Mikosz, do Colégio Estadual Antônio Dorigon, de
Pitanga, encaminhamos solicitação de palestra sobre crimes cibernéticos para
os alunos do ensino médio, em data a combinar com a escola, preferencialmente
na segunda quinzena de outubro.

O contato da escola é ce.dorigon@escola.pr.gov.br / (42) 3646-1122.

Atenciosamente,
Renan Ostrowski
Assessor Parlamentar
Gabinete - Curitiba/PR
(41) 3350-4000
""",
        esperado={
            "evento": "PALESTRA",
            "temas": ["Crimes cibernéticos"],
            "solicitante": Contem("Antônio Dorigon"),
            "email": "ce.dorigon@escola.pr.gov.br",
            "telefone": Contem("3646-1122"),
            "data_inicio_evento": AUSENTE,
            "municipio": "Pitanga",
            "estado": "PR",
            "canal_solicitacao": "EMAIL",
            "data_solicitacao": "2026-09-25",
        },
        nota="Assessor pede em nome da escola: o contato é o da escola, não o do gabinete (Curitiba); sem data definida.",
    ),
    # ------------------------------------------------------------------ 051
    Caso(
        id="dem-051",
        modulo=_M,
        formato="eml",
        agora="2026-11-16 10:00",
        texto=_eml(
            "Instituto Natal Solidário <contato@natalsolidario-exemplo.org.br>",
            _ASCOM,
            "Convite - Feira de Natal Solidária na Praça Rui Barbosa",
            "2026-11-13 12:00",
            """
Olá!

O Instituto Natal Solidário realiza a Feira de Natal Solidária de 14 a 18 de
dezembro, das 10h às 18h, na Praça Rui Barbosa, centro de Curitiba.

Convidamos a Polícia Civil a participar da feira com um estande de orientação
sobre golpes e fraudes de fim de ano (compras on-line, falsos sorteios, cartão).
O público circulante estimado é de 15 mil pessoas nos cinco dias.

Abraços,
Equipe Natal Solidário
(41) 3029-7788
""",
        ),
        esperado={
            "evento": "EVENTO",
            "temas": ["Golpes e fraudes"],
            "solicitante": Contem("Instituto Natal Solidário"),
            "email": "contato@natalsolidario-exemplo.org.br",
            "telefone": Contem("3029-7788"),
            "data_inicio_evento": "2026-12-14",
            "data_fim_evento": "2026-12-18",
            "hora_inicio": "10:00",
            "municipio": "Curitiba",
            "estado": "PR",
            "quantidade_publico": 15000,
            "canal_solicitacao": "EMAIL",
            "data_solicitacao": "2026-11-13",
            "endereco": Contem("Praça Rui Barbosa"),
            "bairro": "Centro",
        },
        nota="Estande em feira = EVENTO; 'de 14 a 18 de dezembro'; '15 mil pessoas'.",
    ),
    # ------------------------------------------------------------------ 052
    Caso(
        id="dem-052",
        modulo=_M,
        formato="eml",
        agora="2026-10-26 13:30",
        texto=_eml(
            "Luana Sobczak <luana.sobczak@escola.pr.gov.br>",
            _ASCOM,
            "Educação para a Cidadania - palestra",
            "2026-10-26 07:12",
            """
Bom dia!

Sou professora do Colégio Estadual Francisco Carneiro Martins, em Guarapuava,
e coordeno o projeto de Educação para a Cidadania. Gostaríamos de uma palestra
da PCPR para os alunos do 2º ano na terça-feira, 10 de novembro, às 10h20,
no auditório do colégio (Rua Padre Chagas, 2200 - Centro).

Cerca de 140 alunos.

Luana Sobczak

Enviado do meu iPhone

AVISO DE CONFIDENCIALIDADE: Esta mensagem e seus anexos são destinados
exclusivamente ao(s) destinatário(s) e podem conter informações
confidenciais. Se você a recebeu por engano, apague-a e avise o remetente.
Secretaria de Estado da Educação - Av. Água Verde, 2140 - Curitiba/PR.
""",
        ),
        esperado={
            "evento": "PALESTRA",
            "temas": ["Educação para a cidadania"],
            "solicitante": Contem("Francisco Carneiro Martins"),
            "email": "luana.sobczak@escola.pr.gov.br",
            "data_inicio_evento": "2026-11-10",
            "hora_inicio": "10:20",
            "municipio": "Guarapuava",
            "estado": "PR",
            "quantidade_publico": 140,
            "canal_solicitacao": "EMAIL",
            "data_solicitacao": "2026-10-26",
            "local": Contem("auditório do colégio"),
            "endereco": Contem("Rua Padre Chagas, 2200"),
            "bairro": "Centro",
        },
        nota="Aviso de confidencialidade com endereço da SEED em Curitiba; 'Enviado do meu iPhone'.",
    ),
    # ------------------------------------------------------------------ 053
    Caso(
        id="dem-053",
        modulo=_M,
        formato="texto",
        agora="2026-10-22 14:00",
        texto="""
bom dia gostaria de agendar uma palestra na escola municipal professora zilda arns em sao jose dos pinhais sobre abuso sexual pras criança do 3 ano
dia 10/11 as 14:00
endereço av rui barbosa 1500 afonso pena
sou a pedagoga fabiana 41 3381 2200
""",
        esperado={
            "evento": "PALESTRA",
            "temas": ["Abuso sexual infantil"],
            "solicitante": Contem("zilda arns"),
            "telefone": Contem("2200"),
            "data_inicio_evento": "2026-11-10",
            "hora_inicio": "14:00",
            "municipio": "São José dos Pinhais",
            "estado": "PR",
            "local": Contem("zilda arns"),
            "endereco": Contem("rui barbosa"),
            "bairro": UmDe("Afonso Pena", "afonso pena"),
        },
        nota="Tudo minúsculo e sem acento; telefone com espaços.",
    ),
    # ------------------------------------------------------------------ 054
    Caso(
        id="dem-054",
        modulo=_M,
        formato="eml",
        agora="2026-10-06 16:00",
        texto=_eml(
            "Secretaria de Educação de Francisco Beltrão <educacao@beltrao-exemplo.pr.gov.br>",
            _ASCOM,
            _q("Ofício nº 312/2026 – convite formatura Guarda Mirim"),
            "2026-10-05 11:11",
            """
Francisco Beltrão, 1º de outubro de 2026.

Ofício nº 312/2026 - SMEC

Ilustríssimo(a) Senhor(a),

A Secretaria Municipal de Educação e Cultura de Francisco Beltrão tem a
satisfação de convidar a Polícia Civil do Paraná para a Formatura da 18ª Turma
da Guarda Mirim, que será realizada no dia 27 de novembro de 2026, às 19 horas,
no Ginásio Municipal Irmão Cirilo, Rua Tenente Camargo, 2200 - Centro.

Estima-se a presença de aproximadamente 1.200 pessoas.

Atenciosamente,

ROSICLÉIA FACHINELLO
Secretária Municipal de Educação e Cultura
(46) 3520-2100
""",
            html=True,
        ),
        esperado={
            "evento": "EVENTO",
            "solicitante": Contem("Secretaria Municipal de Educação"),
            "email": "educacao@beltrao-exemplo.pr.gov.br",
            "telefone": Contem("3520-2100"),
            "data_inicio_evento": "2026-11-27",
            "hora_inicio": "19:00",
            "municipio": "Francisco Beltrão",
            "estado": "PR",
            "quantidade_publico": 1200,
            "canal_solicitacao": "EMAIL",
            "data_solicitacao": UmDe("2026-10-01", "2026-10-05"),
            "local": Contem("Ginásio Municipal Irmão Cirilo"),
            "endereco": Contem("Rua Tenente Camargo, 2200"),
            "bairro": "Centro",
            "temas": AUSENTE,
        },
        nota="Formatura = EVENTO; '1º de outubro' é a data do ofício; '19 horas' por extenso.",
    ),
    # ------------------------------------------------------------------ 055
    Caso(
        id="dem-055",
        modulo=_M,
        formato="texto",
        agora="2026-10-30 10:00",
        texto="""
[29/10/2026 13:40] Prof Adilson: boa tarde
[29/10/2026 13:41] Prof Adilson: palestra drogas pros aluno do colegio estadual santa barbara de bituruna
[29/10/2026 13:41] Prof Adilson: 3 turmas de 35
[29/10/2026 13:42] Prof Adilson: dia 12/11 as 8h30
""",
        esperado={
            "evento": "PALESTRA",
            "temas": ["Drogas"],
            "solicitante": Contem("santa barbara"),
            "data_inicio_evento": "2026-11-12",
            "hora_inicio": "08:30",
            "municipio": "Bituruna",
            "estado": "PR",
            "canal_solicitacao": "WHATSAPP",
            "data_solicitacao": "2026-10-29",
        },
        nota="'3 turmas de 35' fica fora (não é número declarado); '8h30'.",
    ),
    # ------------------------------------------------------------------ 056
    Caso(
        id="dem-056",
        modulo=_M,
        formato="eml",
        agora="2026-10-05 09:00",
        texto=_eml(
            "CRAS Cará-Cará <cras.caracara@pontagrossa-exemplo.pr.gov.br>",
            _ASCOM,
            "Palestra tráfico de pessoas - adolescentes SCFV",
            "2026-10-02 14:44",
            """
Prezados,

O CRAS Cará-Cará, de Ponta Grossa, solicita palestra sobre aliciamento e
tráfico de pessoas (falsas propostas de emprego e de modelo nas redes sociais)
para os adolescentes do Serviço de Convivência.

Dia 14 de outubro, quarta-feira, às 15h.
Local: Salão Comunitário - Rua Visconde de Mauá, 3900 - Oficinas.
Público: 45 adolescentes e familiares.

Atenciosamente,
Gislaine Mendes Taques
Psicóloga - CRAS Cará-Cará
(42) 3220-1090
""",
        ),
        esperado={
            "evento": "PALESTRA",
            "temas": ["Tráfico de pessoas"],
            "solicitante": Contem("CRAS Cará-Cará"),
            "email": "cras.caracara@pontagrossa-exemplo.pr.gov.br",
            "telefone": Contem("3220-1090"),
            "data_inicio_evento": "2026-10-14",
            "hora_inicio": "15:00",
            "municipio": "Ponta Grossa",
            "estado": "PR",
            "quantidade_publico": 45,
            "canal_solicitacao": "EMAIL",
            "data_solicitacao": "2026-10-02",
            "local": Contem("Salão Comunitário"),
            "endereco": Contem("Rua Visconde de Mauá, 3900"),
            "bairro": "Oficinas",
        },
        nota="O CRAS fica no bairro Cará-Cará, mas o endereço do evento é no bairro Oficinas.",
    ),
    # ------------------------------------------------------------------ 057
    Caso(
        id="dem-057",
        modulo=_M,
        formato="eml",
        agora="2026-10-29 11:00",
        texto=_eml(
            "SESMT Cooperativa Agrária Centro-Sul <sesmt@coopcentrosul-exemplo.coop.br>",
            _ASCOM,
            "SIPAT - pedido de palestra (Delegado Paulo Henrique)",
            "2026-10-28 15:05",
            """
Prezados,

Para a SIPAT da Cooperativa Agrária Centro-Sul, em Guarapuava, gostaríamos de
uma palestra sobre drogas no ambiente de trabalho. Se possível, com o Delegado
Paulo Henrique Sotomaior, que conhecemos de outro evento.

Data: 26/11, às 13h30
Local: Auditório da Unidade Industrial - BR-277, km 340 - Distrito Industrial
Público: 220 colaboradores

Atenciosamente,
Tânia Wiebe
(42) 3625-8800
""",
        ),
        esperado={
            "evento": "PALESTRA",
            "temas": ["Drogas"],
            "palestrantes": AUSENTE,
            "solicitante": Contem("Cooperativa Agrária Centro-Sul"),
            "email": "sesmt@coopcentrosul-exemplo.coop.br",
            "telefone": Contem("3625-8800"),
            "data_inicio_evento": "2026-11-26",
            "hora_inicio": "13:30",
            "municipio": "Guarapuava",
            "estado": "PR",
            "quantidade_publico": 220,
            "canal_solicitacao": "EMAIL",
            "data_solicitacao": "2026-10-28",
            "local": Contem("Auditório da Unidade Industrial"),
            "endereco": Contem("BR-277, km 340"),
            "bairro": "Distrito Industrial",
        },
        nota="Palestrante pedido não está no cadastro → palestrantes vazio.",
    ),
    # ------------------------------------------------------------------ 058
    Caso(
        id="dem-058",
        modulo=_M,
        formato="texto",
        agora="2026-10-09 16:00",
        texto="""
Recado telefônico - 09/10/2026, 14h05

Ligou a diretora Regiane, do Colégio Estadual José de Anchieta, de União da
Vitória. Quer palestra sobre bullying para o 6º ano "pra semana que vem", mas
ainda vai ver o dia e o horário com a equipe. Pediu retorno no (42) 3522-4870.
""",
        esperado={
            "evento": "PALESTRA",
            "temas": ["Bullying"],
            "solicitante": Contem("José de Anchieta"),
            "telefone": Contem("3522-4870"),
            "data_inicio_evento": AUSENTE,
            "hora_inicio": AUSENTE,
            "municipio": "União da Vitória",
            "estado": "PR",
            "canal_solicitacao": "TELEFONE",
            "data_solicitacao": "2026-10-09",
        },
        nota="'semana que vem' sem dia definido e hora do recado (14h05) não viram data/hora do evento.",
    ),
    # ------------------------------------------------------------------ 059
    Caso(
        id="dem-059",
        modulo=_M,
        formato="eml",
        agora="2026-11-02 09:00",
        texto=_eml(
            "Bruno Toledo <bruno.toledo@ielb-exemplo.org.br>",
            _ASCOM,
            "Culto de Jovens - palestra sobre drogas",
            "2026-10-30 18:48",
            """
Boa tarde!

Sou o Bruno Toledo, líder da juventude da Comunidade Evangélica Luterana Cristo,
de Marechal Cândido Rondon. Pedimos uma palestra sobre drogas no Culto de
Jovens de sábado, 28/11, às 19h30.

Endereço: Rua Sete de Setembro, 1100 - Centro
Cerca de 90 jovens.

Bruno Toledo
(45) 99921-5050
""",
        ),
        esperado={
            "evento": "PALESTRA",
            "temas": ["Drogas"],
            "solicitante": Contem("Comunidade Evangélica Luterana Cristo"),
            "email": "bruno.toledo@ielb-exemplo.org.br",
            "telefone": Contem("99921-5050"),
            "data_inicio_evento": "2026-11-28",
            "hora_inicio": "19:30",
            "municipio": "Marechal Cândido Rondon",
            "estado": "PR",
            "quantidade_publico": 90,
            "canal_solicitacao": "EMAIL",
            "data_solicitacao": "2026-10-30",
            "endereco": Contem("Rua Sete de Setembro, 1100"),
            "bairro": "Centro",
        },
        nota="Sobrenome 'Toledo' não é o município.",
    ),
    # ------------------------------------------------------------------ 060
    Caso(
        id="dem-060",
        modulo=_M,
        formato="eml",
        agora="2026-11-17 14:00",
        texto=_eml(
            "Secretaria de Segurança de Quatro Barras <seguranca@quatrobarras-exemplo.pr.gov.br>",
            _ASCOM,
            "Seminario Municipal de Seguranca Publica",
            "2026-11-16 10:30",
            """
Prezados,

A Secretaria Municipal de Segurança e Trânsito de Quatro Barras realizará o
1º Seminário Municipal de Segurança Pública e convida a Polícia Civil do Paraná
a compor a mesa de abertura e o painel "Integração das forças de segurança".

Data: 03/12/2026, às 9h
Local: Câmara Municipal de Quatro Barras - Av. Dom Pedro II, 245 - Centro

Contamos com a presença de 150 participantes.

Att.
Coordenação do Seminário
(41) 3672-8080
""",
        ),
        esperado={
            "solicitante": Contem("Quatro Barras"),
            "email": "seguranca@quatrobarras-exemplo.pr.gov.br",
            "telefone": Contem("3672-8080"),
            "data_inicio_evento": "2026-12-03",
            "hora_inicio": "09:00",
            "municipio": "Quatro Barras",
            "estado": "PR",
            "quantidade_publico": 150,
            "canal_solicitacao": "EMAIL",
            "data_solicitacao": "2026-11-16",
            "local": Contem("Câmara Municipal"),
            "endereco": Contem("Av. Dom Pedro II, 245"),
            "bairro": "Centro",
            "palestrantes": AUSENTE,
            "temas": AUSENTE,
        },
        nota="'Trânsito' no nome da secretaria não é tema pedido; painel sem tema do cadastro; sem acentos no assunto.",
    ),
    # ------------------------------------------------------------------ 061
    Caso(
        id="dem-061",
        modulo=_M,
        formato="texto",
        agora="2026-10-30 09:00",
        texto="""
De: Escola Municipal Rocha Pombo <em.rochapombo@morretes-exemplo.pr.gov.br>
Enviado em: quinta-feira, 29 de outubro de 2026 16:50
Para: ascom.palestras@pc.pr.gov.br
Cc: Secretaria Municipal de Educação
Assunto: Palestra - autoproteção infantil

Prezados,

A Escola Municipal Rocha Pombo, de Morretes, solicita palestra sobre abuso
sexual infantil (autoproteção) para os alunos do 3º ao 5º ano no dia 19 de
novembro, quinta-feira, em dois horários: às 8h (turma da manhã) e às 13h30
(turma da tarde).

Endereço: Rua XV de Novembro, 45 - Centro Histórico.
Total de aproximadamente 160 crianças.

Atenciosamente,
Terezinha Bonato
Diretora
(41) 3462-1155
""",
        esperado={
            "evento": "PALESTRA",
            "temas": ["Abuso sexual infantil"],
            "solicitante": Contem("Rocha Pombo"),
            "email": "em.rochapombo@morretes-exemplo.pr.gov.br",
            "telefone": Contem("3462-1155"),
            "data_inicio_evento": "2026-11-19",
            "hora_inicio": "08:00",
            "municipio": "Morretes",
            "estado": "PR",
            "quantidade_publico": 160,
            "canal_solicitacao": "EMAIL",
            "data_solicitacao": "2026-10-29",
            "local": Contem("Rocha Pombo"),
            "endereco": Contem("Rua XV de Novembro, 45"),
            "bairro": "Centro Histórico",
        },
        nota="Dois horários no mesmo dia: o início é 8h; Cc para a Secretaria não muda o solicitante.",
    ),
    # ------------------------------------------------------------------ 062
    Caso(
        id="dem-062",
        modulo=_M,
        formato="eml",
        agora="2026-11-20 10:00",
        texto=_eml(
            "Compliance - Rede Farmavida <compliance@farmavida-exemplo.com.br>",
            _ASCOM,
            "Palestra assédio - filial Maringá",
            "2026-11-19 15:40",
            """
Prezados,

A Rede Farmavida gostaria de uma palestra sobre assédio moral e sexual para os
gerentes da regional norte, no encontro que faremos na filial de Maringá:

11/12, às 16h - Av. Colombo, 5790 - Zona 7 - Maringá
Cerca de 70 gerentes.

Atenciosamente,

Departamento de Compliance
Rede Farmavida - Matriz
Rua Marechal Deodoro, 900 - Centro - Curitiba/PR - CEP 80010-010
(41) 3021-5500
""",
        ),
        esperado={
            "evento": "PALESTRA",
            "temas": ["Assédio moral e sexual"],
            "solicitante": Contem("Farmavida"),
            "email": "compliance@farmavida-exemplo.com.br",
            "telefone": Contem("3021-5500"),
            "data_inicio_evento": "2026-12-11",
            "hora_inicio": "16:00",
            "municipio": "Maringá",
            "estado": "PR",
            "quantidade_publico": 70,
            "canal_solicitacao": "EMAIL",
            "data_solicitacao": "2026-11-19",
            "endereco": Contem("Av. Colombo, 5790"),
            "bairro": "Zona 7",
            "cep": AUSENTE,
        },
        nota="'Av. Colombo' não é o município Colombo; matriz em Curitiba (CEP da assinatura não é do evento).",
    ),
    # ------------------------------------------------------------------ 063
    Caso(
        id="dem-063",
        modulo=_M,
        formato="eml",
        agora="2026-11-05 10:00",
        texto=_eml(
            "EEB Dom Pio de Freitas <eeb.dompio.mafra@sed.sc.gov.br>",
            _ASCOM,
            _q("Solicitação de palestra – Mafra/SC"),
            "2026-11-04 08:20",
            """
Bom dia!

A Escola de Educação Básica Dom Pio de Freitas, de Mafra (SC), cidade gêmea de
Rio Negro (PR), solicita uma palestra sobre drogas para os alunos do ensino
médio, no dia 1º de dezembro, às 14h.

Endereço: Rua Felipe Schmidt, 300 - Centro - Mafra/SC - CEP 89300-000.
Aproximadamente 230 alunos.

Atenciosamente,
Orientação Escolar
(47) 3642-0303
""",
        ),
        esperado={
            "evento": "PALESTRA",
            "temas": ["Drogas"],
            "solicitante": Contem("Dom Pio de Freitas"),
            "email": "eeb.dompio.mafra@sed.sc.gov.br",
            "telefone": Contem("3642-0303"),
            "data_inicio_evento": "2026-12-01",
            "hora_inicio": "14:00",
            "municipio": "Mafra",
            "estado": "SC",
            "quantidade_publico": 230,
            "canal_solicitacao": "EMAIL",
            "data_solicitacao": "2026-11-04",
            "endereco": Contem("Rua Felipe Schmidt, 300"),
            "bairro": "Centro",
            "cep": "89300-000",
        },
        nota="Evento em SC; Rio Negro (PR) só como cidade gêmea; '1º de dezembro'.",
    ),
    # ------------------------------------------------------------------ 064
    Caso(
        id="dem-064",
        modulo=_M,
        formato="texto",
        agora="2026-11-26 10:00",
        texto="""
[25/11/2026 11:30] Profe Nilce: Bom dia!! A palestra do ano passado foi nota 10, merece uma salva de palmas 👏👏
[25/11/2026 11:31] Profe Nilce: Queremos de novo sobre bullying aqui no Colégio Estadual Floriano Peixoto, em Laranjeiras do Sul
[25/11/2026 11:32] Profe Nilce: dia 9/12 as 10h, umas 200 crianças
""",
        esperado={
            "evento": "PALESTRA",
            "temas": ["Bullying"],
            "solicitante": Contem("Floriano Peixoto"),
            "data_inicio_evento": "2026-12-09",
            "hora_inicio": "10:00",
            "municipio": "Laranjeiras do Sul",
            "estado": "PR",
            "quantidade_publico": 200,
            "canal_solicitacao": "WHATSAPP",
            "data_solicitacao": "2026-11-25",
            "local": Contem("Floriano Peixoto"),
        },
        nota="'salva de palmas' não é o município Palmas.",
    ),
    # ------------------------------------------------------------------ 065
    Caso(
        id="dem-065",
        modulo=_M,
        formato="eml",
        agora="2026-10-23 14:00",
        texto=_eml(
            "Vara da Infância e Juventude - Ivaiporã <vij.ivaipora@tj-exemplo.jus.br>",
            _ASCOM,
            _q("Ofício nº 1.104/2026 – Projeto Justiça na Escola"),
            "2026-10-22 13:15",
            """
Ivaiporã, 20 de outubro de 2026.

Ofício nº 1.104/2026 - VIJ

Senhor(a) Assessor(a),

Com os cumprimentos de estilo, no âmbito do Projeto Justiça na Escola,
solicito a Vossa Senhoria a designação de policial civil para proferir
palestra sobre drogas e ato infracional aos alunos do
Colégio Estadual Barbosa Ferraz, no dia 24 de novembro próximo, às 14 horas, no auditório do colégio
(Rua Paraná, 1400 - Centro, Ivaiporã).

Público estimado: 280 estudantes.

Contato da Secretaria: (43) 3472-8800.

Respeitosamente,

Juíza de Direito
Vara da Infância e Juventude da Comarca de Ivaiporã
""",
        ),
        esperado={
            "evento": "PALESTRA",
            "temas": ["Drogas"],
            "solicitante": Contem("Vara da Infância"),
            "email": "vij.ivaipora@tj-exemplo.jus.br",
            "telefone": Contem("3472-8800"),
            "data_inicio_evento": "2026-11-24",
            "hora_inicio": "14:00",
            "municipio": "Ivaiporã",
            "estado": "PR",
            "quantidade_publico": 280,
            "canal_solicitacao": "EMAIL",
            "data_solicitacao": UmDe("2026-10-20", "2026-10-22"),
            "local": Contem("Colégio Estadual Barbosa Ferraz"),
            "endereco": Contem("Rua Paraná, 1400"),
            "bairro": "Centro",
        },
        nota="Ofício formal; 'Ivaiporã' ≠ 'Ivaí'; número do ofício '1.104/2026' não é protocolo nem público; 'Barbosa Ferraz' também é município.",
    ),
    # ------------------------------------------------------------------ 066
    Caso(
        id="dem-066",
        modulo=_M,
        formato="texto",
        agora="2026-11-18 10:00",
        texto="""
Semana de Prevenção às Drogas - Colégio Estadual Presidente Castelo Branco (Toledo)

Prezados, o colégio fará a Semana de Prevenção às Drogas nos dias 10, 11 e 12
de dezembro e gostaríamos de uma palestra da Polícia Civil em cada dia, às 9h,
para turmas diferentes (cerca de 150 alunos por dia).

Local: anfiteatro do colégio - Rua Almirante Barroso, 2900 - Vila Industrial.

Contato: Coordenação Pedagógica - (45) 3252-1020 - ce.castelobranco@escola.pr.gov.br
""",
        esperado={
            "evento": "PALESTRA",
            "temas": ["Drogas"],
            "solicitante": Contem("Presidente Castelo Branco"),
            "email": "ce.castelobranco@escola.pr.gov.br",
            "telefone": Contem("3252-1020"),
            "data_inicio_evento": "2026-12-10",
            "data_fim_evento": "2026-12-12",
            "hora_inicio": "09:00",
            "municipio": "Toledo",
            "estado": "PR",
            "local": Contem("anfiteatro do colégio"),
            "endereco": Contem("Rua Almirante Barroso, 2900"),
            "bairro": "Vila Industrial",
        },
        nota="'nos dias 10, 11 e 12' → período; '150 alunos por dia' fica fora; município só entre parênteses no título.",
    ),
    # ------------------------------------------------------------------ 067
    Caso(
        id="dem-067",
        modulo=_M,
        formato="eml",
        agora="2026-11-09 11:00",
        texto=_eml(
            "Conselho Municipal do Idoso de Apucarana <cmi@apucarana-exemplo.pr.gov.br>",
            _ASCOM,
            "Palestra - violência contra a pessoa idosa",
            "2026-11-06 10:00",
            """
Prezados,

O Conselho Municipal dos Direitos da Pessoa Idosa de Apucarana solicita uma
palestra sobre violência contra a pessoa idosa (maus-tratos, abandono,
apropriação de benefício) para cuidadores e familiares.

Dia 1/12, às 14h30, no Centro de Convivência do Idoso:
Rua Osvaldo Cruz, 510 - Centro - CEP 86800-720.

Público de cerca de 120 pessoas.

Atenciosamente,
Hilda Marcondes Prestes
Presidente do CMDPI
(43) 3162-4120
""",
        ),
        esperado={
            "evento": "PALESTRA",
            "temas": ["Violência contra a pessoa idosa"],
            "solicitante": Contem("Pessoa Idosa"),
            "email": "cmi@apucarana-exemplo.pr.gov.br",
            "telefone": Contem("3162-4120"),
            "data_inicio_evento": "2026-12-01",
            "hora_inicio": "14:30",
            "municipio": "Apucarana",
            "estado": "PR",
            "quantidade_publico": 120,
            "canal_solicitacao": "EMAIL",
            "data_solicitacao": "2026-11-06",
            "local": Contem("Centro de Convivência do Idoso"),
            "endereco": Contem("Rua Osvaldo Cruz, 510"),
            "bairro": "Centro",
            "cep": "86800-720",
        },
        nota="Data '1/12' sem zero; CEP do local do evento.",
    ),
    # ------------------------------------------------------------------ 068
    Caso(
        id="dem-068",
        modulo=_M,
        formato="eml",
        agora="2026-10-01 10:00",
        texto=_eml(
            "Colégio Integração <coordenacao@colegiointegracao-exemplo.com.br>",
            _ASCOM,
            _q("Solicitação de palestra – crimes cibernéticos (7h45)"),
            "2026-09-30 17:25",
            """
Prezados,

O Colégio Integração, escola particular de Telêmaco Borba, gostaria de agendar
uma palestra sobre crimes cibernéticos (golpes em jogos on-line, sextorsão,
vazamento de dados) para o ensino fundamental II.

Data: 20/10
Horário: às 7h45
Local: Auditório - Rua Marechal Floriano, 777 - Centro
Público: 260 alunos

Horário da secretaria: 7h às 18h.

Coordenação Pedagógica
(42) 3272-3131
""",
            html=True,
        ),
        esperado={
            "evento": "PALESTRA",
            "temas": ["Crimes cibernéticos"],
            "solicitante": Contem("Colégio Integração"),
            "email": "coordenacao@colegiointegracao-exemplo.com.br",
            "telefone": Contem("3272-3131"),
            "data_inicio_evento": "2026-10-20",
            "hora_inicio": "07:45",
            "municipio": "Telêmaco Borba",
            "estado": "PR",
            "quantidade_publico": 260,
            "canal_solicitacao": "EMAIL",
            "data_solicitacao": "2026-09-30",
            "local": Contem("Auditório"),
            "endereco": Contem("Rua Marechal Floriano, 777"),
            "bairro": "Centro",
        },
        nota="Horário da secretaria (7h às 18h) não é o do evento (7h45).",
    ),
    # ------------------------------------------------------------------ 069
    Caso(
        id="dem-069",
        modulo=_M,
        formato="texto",
        agora="2026-10-09 10:00",
        texto="""
---------- Forwarded message ---------
De: Colégio Estadual Dom Carlos <ce.domcarlos@escola.pr.gov.br>
Date: qui., 8 de out. de 2026 às 11:03
Subject: palestra bullying
To: <nucleo.palmas@educacao.pr.gov.br>

Bom dia, pessoal do Núcleo!

Aqui é de Palmas-PR (não é Tocantins, rs). Precisamos de uma palestra sobre
bullying na próxima sexta-feira (16/10), às 13h30, para 120 alunos do 6º ano.
Pode encaminhar para a Polícia Civil?

Endereço do colégio: Av. Coronel José Osório, 890 - Centro.

Obrigada, Kelly (vice-direção) - (46) 3262-1414
""",
        esperado={
            "evento": "PALESTRA",
            "temas": ["Bullying"],
            "solicitante": Contem("Dom Carlos"),
            "email": "ce.domcarlos@escola.pr.gov.br",
            "telefone": Contem("3262-1414"),
            "data_inicio_evento": "2026-10-16",
            "hora_inicio": "13:30",
            "municipio": "Palmas",
            "estado": "PR",
            "quantidade_publico": 120,
            "canal_solicitacao": "EMAIL",
            "data_solicitacao": "2026-10-08",
            "local": Contem("Dom Carlos"),
            "endereco": Contem("Av. Coronel José Osório, 890"),
            "bairro": "Centro",
        },
        nota="Palmas-PR, não Palmas/TO; encaminhado pelo Núcleo (e-mail de contato é o da escola).",
    ),
    # ------------------------------------------------------------------ 070
    Caso(
        id="dem-070",
        modulo=_M,
        formato="eml",
        agora="2026-10-27 09:00",
        texto=_eml(
            "APMF CE Leocádia Braga Ramos <apmf.leocadia@exemplo-mail.com>",
            _ASCOM,
            "pedido palestra piraquara",
            "2026-10-26 20:30",
            """
Boa noite

A APMF do Colégio Estadual Leocádia Braga Ramos, de Piraquara, pede palestra
sobre drogas e violência escolar para pais e alunos, dia 19/11 as 19h, no
ginásio do colégio.

Rua Mário Seabra, 100 - Centro
CEP 83301-010

grata
Dirce (presidente da APMF)
41 99680-7272
""",
        ),
        esperado={
            "evento": "PALESTRA",
            "temas": ["Drogas", "Violência escolar"],
            "solicitante": Contem("Leocádia Braga Ramos"),
            "email": "apmf.leocadia@exemplo-mail.com",
            "telefone": Contem("99680-7272"),
            "data_inicio_evento": "2026-11-19",
            "hora_inicio": "19:00",
            "municipio": "Piraquara",
            "estado": "PR",
            "canal_solicitacao": "EMAIL",
            "data_solicitacao": "2026-10-26",
            "local": Contem("ginásio do colégio"),
            "endereco": Contem("Rua Mário Seabra, 100"),
            "bairro": "Centro",
            "cep": "83301-010",
        },
        nota="Dois temas; endereço e CEP em linhas separadas.",
    ),
    # ------------------------------------------------------------------ 071
    Caso(
        id="dem-071",
        modulo=_M,
        formato="eml",
        agora="2026-12-01 15:00",
        texto=_eml(
            "Segurança do Trabalho - Cerâmica Itaqui <seg.trabalho@ceramicaitaqui-exemplo.com.br>",
            _ASCOM,
            _q("URGENTE – DDS especial amanhã às 8h"),
            "2026-12-01 09:05",
            """
Bom dia,

Sei que o prazo é curto, mas surgiu a oportunidade: a Cerâmica Itaqui, de
Campo Largo, gostaria de uma fala rápida (30 min) sobre trânsito e álcool na
direção no nosso DDS especial de fim de ano, amanhã às 8h.

Local: Rodovia do Café (BR-277), km 115 - Itaqui.
Cerca de 180 colaboradores.

Rafael Moro
Técnico de Segurança do Trabalho
(41) 3292-6060
""",
        ),
        esperado={
            "evento": "PALESTRA",
            "temas": ["Trânsito"],
            "solicitante": Contem("Cerâmica Itaqui"),
            "email": "seg.trabalho@ceramicaitaqui-exemplo.com.br",
            "telefone": Contem("3292-6060"),
            "data_inicio_evento": "2026-12-02",
            "hora_inicio": "08:00",
            "municipio": "Campo Largo",
            "estado": "PR",
            "quantidade_publico": 180,
            "canal_solicitacao": "EMAIL",
            "data_solicitacao": "2026-12-01",
            "endereco": Contem("km 115"),
            "bairro": "Itaqui",
        },
        nota="'amanhã às 8h' relativo ao envio (01/12); '30 min' não é hora.",
    ),
    # ------------------------------------------------------------------ 072
    Caso(
        id="dem-072",
        modulo=_M,
        formato="texto",
        agora="2026-11-12 10:00",
        texto="""
[11/11/2026 20:15] Coord. Grupo Mulheres Vivas: Oi, boa noite! Sou a Rosemeri, coordeno o grupo Mulheres Vivas, de apoio a mulheres vítimas de violência, aqui em Castro
[11/11/2026 20:16] Coord. Grupo Mulheres Vivas: Queremos uma palestra sobre violência doméstica, medidas protetivas, como denunciar
[11/11/2026 20:17] Coord. Grupo Mulheres Vivas: Dia 5 de dezembro, sábado, às 15h, no Salão da Igreja São Judas - Rua Santos Dumont, 45 - Santa Cruz
[11/11/2026 20:17] Coord. Grupo Mulheres Vivas: umas 35 mulheres
""",
        esperado={
            "evento": "PALESTRA",
            "temas": ["Violência doméstica"],
            "solicitante": Contem("Mulheres Vivas"),
            "data_inicio_evento": "2026-12-05",
            "hora_inicio": "15:00",
            "municipio": "Castro",
            "estado": "PR",
            "quantidade_publico": 35,
            "canal_solicitacao": "WHATSAPP",
            "data_solicitacao": "2026-11-11",
            "local": Contem("Salão da Igreja São Judas"),
            "endereco": Contem("Rua Santos Dumont, 45"),
            "bairro": "Santa Cruz",
        },
        nota="'Mulheres Vivas'/'vítimas de violência' não tornam o tema 'Segurança da mulher': pedem violência doméstica.",
    ),
    # ------------------------------------------------------------------ 073
    Caso(
        id="dem-073",
        modulo=_M,
        formato="eml",
        agora="2026-10-30 10:00",
        texto=_eml(
            "AMUVI - Associação dos Municípios do Vale do Ivaí <eventos@amuvi-exemplo.org.br>",
            _ASCOM,
            "Encontro Regional de Mulheres - Jandaia do Sul",
            "2026-10-29 14:00",
            """
Prezados,

A Associação dos Municípios do Vale do Ivaí (AMUVI) promove o Encontro Regional
de Mulheres Lideranças e solicita uma palestra sobre segurança da mulher.

O encontro será em Jandaia do Sul, no dia 25/11, às 8h30, no
Centro de Eventos Municipal - Rua Marechal Deodoro, 555 - Centro. Público: 300 mulheres.

Atenciosamente,

AMUVI
Av. Curitiba, 1000 - Centro - Apucarana/PR
(43) 3422-5050
""",
        ),
        esperado={
            "evento": "PALESTRA",
            "temas": ["Segurança da mulher"],
            "solicitante": Contem("AMUVI"),
            "email": "eventos@amuvi-exemplo.org.br",
            "telefone": Contem("3422-5050"),
            "data_inicio_evento": "2026-11-25",
            "hora_inicio": "08:30",
            "municipio": "Jandaia do Sul",
            "estado": "PR",
            "quantidade_publico": 300,
            "canal_solicitacao": "EMAIL",
            "data_solicitacao": "2026-10-29",
            "local": Contem("Centro de Eventos Municipal"),
            "endereco": Contem("Rua Marechal Deodoro, 555"),
            "bairro": "Centro",
        },
        nota="Sede da AMUVI em Apucarana (assinatura) e 'Vale do Ivaí' no nome; o evento é em Jandaia do Sul.",
    ),
    # ------------------------------------------------------------------ 074
    Caso(
        id="dem-074",
        modulo=_M,
        formato="texto",
        agora="2026-11-20 10:00",
        texto="""
Solicito palestra sobre drogas para os alunos do 9º ano da Escola Estadual
Monsenhor Pedro Lech, de Imbituva, no dia 4/12 (sexta), no período da tarde,
na própria escola. São 3 turmas.

Atenciosamente,
Direção
""",
        esperado={
            "evento": "PALESTRA",
            "temas": ["Drogas"],
            "solicitante": Contem("Monsenhor Pedro Lech"),
            "data_inicio_evento": "2026-12-04",
            "hora_inicio": AUSENTE,
            "municipio": "Imbituva",
            "estado": "PR",
            "local": Contem("Monsenhor Pedro Lech"),
            "email": AUSENTE,
            "telefone": AUSENTE,
        },
        nota="Texto curto sem contato; 'período da tarde' não é hora; '3 turmas' não é número de público.",
    ),
    # ------------------------------------------------------------------ 075
    Caso(
        id="dem-075",
        modulo=_M,
        formato="eml",
        agora="2026-10-16 09:00",
        texto=_eml(
            "Centro Acadêmico de Direito - Faculdade Metropolitana <cadir@facmetro-exemplo.edu.br>",
            _ASCOM,
            _q("Semana Jurídica – mesa sobre crimes cibernéticos"),
            "2026-10-15 16:00",
            """
Prezados,

O Centro Acadêmico de Direito da Faculdade Metropolitana de Curitiba realizará
a Semana Jurídica de 9 a 11 de novembro. Gostaríamos de convidar os Delegados
Ricardo Faoro e Simone Czelusniak para a mesa sobre crimes cibernéticos, no
dia 10/11, às 19h.

Local: Auditório Principal - Rua Chile, 1800 - Rebouças.
Público: 250 estudantes.

Atenciosamente,
Gabriel Nowak - Presidente do CADIR
(41) 99876-1010
""",
            html=True,
        ),
        esperado={
            "evento": "PALESTRA",
            "temas": ["Crimes cibernéticos"],
            "palestrantes": ["Ricardo Faoro", "Simone Czelusniak"],
            "solicitante": Contem("Faculdade Metropolitana"),
            "email": "cadir@facmetro-exemplo.edu.br",
            "telefone": Contem("99876-1010"),
            "data_inicio_evento": "2026-11-10",
            "hora_inicio": "19:00",
            "municipio": "Curitiba",
            "estado": "PR",
            "quantidade_publico": 250,
            "canal_solicitacao": "EMAIL",
            "data_solicitacao": "2026-10-15",
            "local": Contem("Auditório Principal"),
            "endereco": Contem("Rua Chile, 1800"),
            "bairro": "Rebouças",
        },
        nota="A Semana vai de 9 a 11/11, mas a mesa pedida é só no dia 10; dois palestrantes nominais.",
    ),
    # ------------------------------------------------------------------ 076
    Caso(
        id="dem-076",
        modulo=_M,
        formato="texto",
        agora="2026-10-28 10:00",
        texto="""
De: CREAS Goioerê <creas@goioere-exemplo.pr.gov.br>
Enviado em: terça-feira, 27 de outubro de 2026 11:12
Para: ASCOM PCPR <ascom.palestras@pc.pr.gov.br>
Assunto: 21 Dias de Ativismo - palestra

Bom dia!

Dentro da campanha dos 21 Dias de Ativismo pelo Fim da Violência contra as
Mulheres, o CREAS de Goioerê solicita palestra sobre violência doméstica e Lei
Maria da Penha no dia 20.11.2026 às 14h, no auditório da Prefeitura
(Rua Mato Grosso, 1234 - Centro). Público: 100 pessoas.

Atenciosamente,
Equipe CREAS
(44) 3522-7070
Atendimento: segunda a sexta, das 8h às 17h
""",
        esperado={
            "evento": "PALESTRA",
            "temas": ["Violência doméstica"],
            "solicitante": Contem("CREAS"),
            "email": "creas@goioere-exemplo.pr.gov.br",
            "telefone": Contem("3522-7070"),
            "data_inicio_evento": "2026-11-20",
            "hora_inicio": "14:00",
            "municipio": "Goioerê",
            "estado": "PR",
            "quantidade_publico": 100,
            "canal_solicitacao": "EMAIL",
            "data_solicitacao": "2026-10-27",
            "local": Contem("auditório da Prefeitura"),
            "endereco": Contem("Rua Mato Grosso, 1234"),
            "bairro": "Centro",
        },
        nota="'21 Dias' não é data; '20.11.2026'; horário de atendimento não é hora.",
    ),
    # ------------------------------------------------------------------ 077
    Caso(
        id="dem-077",
        modulo=_M,
        formato="eml",
        agora="2026-10-13 10:00",
        texto=_eml(
            "Escola Estadual Nossa Senhora do Carmo <ee.nscarmo.mallet@escola.pr.gov.br>",
            _ASCOM,
            "Palestra bullying - Mallet",
            "2026-10-12 19:35",
            """
Boa noite,

Pedimos uma palestra sobre bullying para os alunos do 6º e 7º ano, na quinta,
dia 22/10, às 13h, aqui na escola, em Mallet: Rua Barão do Rio Branco, 300 -
Centro. Uns 130 alunos.

Na última vez (em 2024, dia 17/10/2024) foi muito proveitoso.

Irmã Olga Kobren
Diretora
(42) 3542-1188
""",
        ),
        esperado={
            "evento": "PALESTRA",
            "temas": ["Bullying"],
            "solicitante": Contem("Nossa Senhora do Carmo"),
            "email": "ee.nscarmo.mallet@escola.pr.gov.br",
            "telefone": Contem("3542-1188"),
            "data_inicio_evento": "2026-10-22",
            "hora_inicio": "13:00",
            "municipio": "Mallet",
            "estado": "PR",
            "quantidade_publico": 130,
            "canal_solicitacao": "EMAIL",
            "data_solicitacao": "2026-10-12",
            "endereco": Contem("Rua Barão do Rio Branco, 300"),
            "bairro": "Centro",
        },
        nota="Data de 2024 citada; 'quinta, dia 22/10'.",
    ),
    # ------------------------------------------------------------------ 078
    Caso(
        id="dem-078",
        modulo=_M,
        formato="eml",
        agora="2026-11-06 14:00",
        texto=_eml(
            "CE Timbu Velho <ce.timbuvelho@escola.pr.gov.br>",
            _ASCOM,
            "Re: Palestra sobre drogas - Campina Grande do Sul",
            "2026-11-06 10:02",
            """
Pode ser a segunda opção, dia 20. Obrigada!!

Edna Loyola - Pedagoga
CE Timbu Velho - Campina Grande do Sul
(41) 3676-2020

Em qui., 5 de nov. de 2026 às 16:20, ASCOM - Polícia Civil do Paraná <ascom.palestras@pc.pr.gov.br> escreveu:
> Boa tarde, Edna. Podemos atender no dia 19/11 às 9h ou no dia 20/11 às 14h.
> Qual prefere?
>
> Em ter., 3 de nov. de 2026 às 08:40, CE Timbu Velho <ce.timbuvelho@escola.pr.gov.br> escreveu:
>> Bom dia, gostaríamos de uma palestra sobre drogas para 150 alunos do
>> ensino médio, em novembro, no Colégio Estadual Timbu Velho
>> (Estrada da Ribeira, 3500 - Timbu Velho).
""",
        ),
        esperado={
            "evento": "PALESTRA",
            "temas": ["Drogas"],
            "solicitante": Contem("Timbu Velho"),
            "email": "ce.timbuvelho@escola.pr.gov.br",
            "telefone": Contem("3676-2020"),
            "data_inicio_evento": "2026-11-20",
            "hora_inicio": "14:00",
            "municipio": "Campina Grande do Sul",
            "estado": "PR",
            "quantidade_publico": 150,
            "canal_solicitacao": "EMAIL",
            "data_solicitacao": UmDe("2026-11-03", "2026-11-06"),
            "local": Contem("Timbu Velho"),
            "endereco": Contem("Estrada da Ribeira, 3500"),
        },
        nota="Resposta escolhe a 'segunda opção' da ASCOM (20/11 às 14h), não 19/11 às 9h.",
    ),
    # ------------------------------------------------------------------ 079
    Caso(
        id="dem-079",
        modulo=_M,
        formato="texto",
        agora="2026-11-23 09:00",
        texto="""
[23/11/2026 08:02] Neide - Assoc. Aposentados Ibiporã: Bom dia! Sei que é em cima da hora, mas o palestrante que tínhamos para hoje cancelou
[23/11/2026 08:03] Neide - Assoc. Aposentados Ibiporã: Tem como alguém da Polícia Civil falar sobre golpes e fraudes com os aposentados hoje às 19h?
[23/11/2026 08:04] Neide - Assoc. Aposentados Ibiporã: É na sede da Associação dos Aposentados de Ibiporã, Rua Pará, 250, uns 60 associados
""",
        esperado={
            "evento": "PALESTRA",
            "temas": ["Golpes e fraudes"],
            "solicitante": Contem("Associação dos Aposentados"),
            "data_inicio_evento": "2026-11-23",
            "hora_inicio": "19:00",
            "municipio": "Ibiporã",
            "estado": "PR",
            "quantidade_publico": 60,
            "canal_solicitacao": "WHATSAPP",
            "data_solicitacao": "2026-11-23",
            "local": Contem("Associação dos Aposentados"),
            "endereco": Contem("Rua Pará, 250"),
        },
        nota="'hoje às 19h' = dia da mensagem.",
    ),
    # ------------------------------------------------------------------ 080
    Caso(
        id="dem-080",
        modulo=_M,
        formato="eml",
        agora="2026-11-13 09:00",
        texto=_eml(
            "eProtocolo - Notificação <naoresponda@eprotocolo-exemplo.pr.gov.br>",
            _ASCOM,
            "Protocolo 24.556.019-2 tramitado para ASCOM/PCPR",
            "2026-11-12 18:00",
            """
Protocolo: 24.556.019-2
Data de abertura: 10/11/2026
Interessado: APMF do Colégio Estadual Castro Alves - Cornélio Procópio
Assunto: Solicitação de palestra
Tramitado para: ASCOM/PCPR em 12/11/2026

Detalhamento:
A APMF do Colégio Estadual Castro Alves, de Cornélio Procópio, solicita
palestra sobre violência escolar para pais e alunos, no dia 01/12, às 19h30,
no ginásio do colégio - Rua Minas Gerais, 800 - Vila Seugling. Público
estimado: 400 pessoas. Contato: apmf.castroalves@exemplo-mail.com - (43)
99144-3030.

Esta é uma mensagem automática. Não responda.
""",
        ),
        esperado={
            "evento": "PALESTRA",
            "temas": ["Violência escolar"],
            "solicitante": Contem("Castro Alves"),
            "email": "apmf.castroalves@exemplo-mail.com",
            "telefone": Contem("99144-3030"),
            "data_inicio_evento": "2026-12-01",
            "hora_inicio": "19:30",
            "municipio": "Cornélio Procópio",
            "estado": "PR",
            "quantidade_publico": 400,
            "canal_solicitacao": "PROTOCOLO",
            "protocolo": "24.556.019-2",
            "data_solicitacao": UmDe("2026-11-10", "2026-11-12"),
            "local": Contem("ginásio do colégio"),
            "endereco": Contem("Rua Minas Gerais, 800"),
            "bairro": "Vila Seugling",
        },
        nota="Notificação automática do eProtocolo: e-mail 'naoresponda' não é contato; 'Castro Alves' não é Castro.",
    ),
    # ------------------------------------------------------------------ 081
    Caso(
        id="dem-081",
        modulo=_M,
        formato="texto",
        agora="2026-11-10 10:00",
        texto="""
De: EEB Almirante Barroso <eeb.almirantebarroso@sed.sc.gov.br>
Enviado em: segunda-feira, 9 de novembro de 2026 13:30
Para: ascom.palestras@pc.pr.gov.br
Assunto: Palestra sobre drogas - Três Barras (SC)

Boa tarde,

Somos a Escola de Educação Básica Almirante Barroso, de Três Barras (SC), no
Planalto Norte catarinense. Solicitamos palestra sobre drogas para os alunos
do ensino médio no dia 26/11, às 9h.

Endereço: Rua Ruy Barbosa, 100 - Centro.
Público: 170 alunos.

Att.
Direção - (47) 3623-1100
""",
        esperado={
            "evento": "PALESTRA",
            "temas": ["Drogas"],
            "solicitante": Contem("Almirante Barroso"),
            "email": "eeb.almirantebarroso@sed.sc.gov.br",
            "telefone": Contem("3623-1100"),
            "data_inicio_evento": "2026-11-26",
            "hora_inicio": "09:00",
            "municipio": "Três Barras",
            "estado": "SC",
            "quantidade_publico": 170,
            "canal_solicitacao": "EMAIL",
            "data_solicitacao": "2026-11-09",
            "endereco": Contem("Rua Ruy Barbosa, 100"),
            "bairro": "Centro",
        },
        nota="Três Barras (SC) ≠ Três Barras do Paraná (PR).",
    ),
    # ------------------------------------------------------------------ 082
    Caso(
        id="dem-082",
        modulo=_M,
        formato="eml",
        agora="2026-11-11 10:00",
        texto=_eml(
            "Fórum Regional dos Conselhos Tutelares dos Campos Gerais <forumct.camposgerais@exemplo-mail.com>",
            _ASCOM,
            _q("Encontro Regional de Conselheiros Tutelares – Tibagi"),
            "2026-11-10 17:10",
            """
Prezados,

O Fórum Regional dos Conselhos Tutelares dos Campos Gerais (Castro, Palmeira,
Carambeí, Tibagi, Ponta Grossa e Telêmaco Borba) realizará o Encontro Regional
de Conselheiros Tutelares nos dias 3 e 4 de dezembro, em Tibagi.

Solicitamos uma palestra sobre abuso sexual infantil e escuta protegida no
primeiro dia (3/12), às 14h, no Centro de Eventos de Tibagi -
Rua Coronel Pedro Dias, 100 - Centro.

Público: 120 conselheiros.

Coordenação do Fórum
(42) 99915-8080
""",
        ),
        esperado={
            "evento": "PALESTRA",
            "temas": ["Abuso sexual infantil"],
            "solicitante": Contem("Conselhos Tutelares"),
            "email": "forumct.camposgerais@exemplo-mail.com",
            "telefone": Contem("99915-8080"),
            "data_inicio_evento": "2026-12-03",
            "hora_inicio": "14:00",
            "municipio": "Tibagi",
            "estado": "PR",
            "quantidade_publico": 120,
            "canal_solicitacao": "EMAIL",
            "data_solicitacao": "2026-11-10",
            "local": Contem("Centro de Eventos de Tibagi"),
            "endereco": Contem("Rua Coronel Pedro Dias, 100"),
            "bairro": "Centro",
        },
        nota="Lista de seis municípios; o evento é em Tibagi e a palestra é no dia 3/12.",
    ),
    # ------------------------------------------------------------------ 083
    Caso(
        id="dem-083",
        modulo=_M,
        formato="texto",
        agora="2026-11-04 10:00",
        texto="""
[03/11/2026 14:20] EM Monteiro Lobato: Boa tarde
[03/11/2026 14:21] EM Monteiro Lobato: Gostaria de solicitar uma palestra sobre drogas para os alunos do 5º ano da Escola Municipal Monteiro Lobato
[03/11/2026 14:21] EM Monteiro Lobato: dia 20/11 às 9h
[03/11/2026 14:22] EM Monteiro Lobato: 80 alunos. Obrigada
""",
        esperado={
            "evento": "PALESTRA",
            "temas": ["Drogas"],
            "solicitante": Contem("Monteiro Lobato"),
            "data_inicio_evento": "2026-11-20",
            "hora_inicio": "09:00",
            "municipio": AUSENTE,
            "quantidade_publico": 80,
            "canal_solicitacao": "WHATSAPP",
            "data_solicitacao": "2026-11-03",
            "local": Contem("Monteiro Lobato"),
        },
        nota="Nenhuma cidade citada ('Monteiro Lobato' não é município do PR): não inventar município.",
    ),
    # ------------------------------------------------------------------ 084
    Caso(
        id="dem-084",
        modulo=_M,
        formato="eml",
        agora="2026-10-20 10:00",
        texto=_eml(
            "CE Mendes Gonçalves <ce.mendesgoncalves@escola.pr.gov.br>",
            _ASCOM,
            "Palestra - tráfico de pessoas na fronteira",
            "2026-10-19 09:15",
            """
Prezados,

O Colégio Estadual Mendes Gonçalves, de Guaíra, na fronteira com o Paraguai,
pede palestra sobre tráfico de pessoas e aliciamento de jovens, para alunos e
pais, no dia 17/11, às 19h, no pátio do colégio (Av. Otávio Tosta, 1200 -
Centro).

Cerca de 250 pessoas.

Atenciosamente,
Direção
(44) 3642-1515
""",
        ),
        esperado={
            "evento": "PALESTRA",
            "temas": ["Tráfico de pessoas"],
            "solicitante": Contem("Mendes Gonçalves"),
            "email": "ce.mendesgoncalves@escola.pr.gov.br",
            "telefone": Contem("3642-1515"),
            "data_inicio_evento": "2026-11-17",
            "hora_inicio": "19:00",
            "municipio": "Guaíra",
            "estado": "PR",
            "quantidade_publico": 250,
            "canal_solicitacao": "EMAIL",
            "data_solicitacao": "2026-10-19",
            "local": Contem("pátio do colégio"),
            "endereco": Contem("Av. Otávio Tosta, 1200"),
            "bairro": "Centro",
        },
        nota="Paraguai citado não muda o estado.",
    ),
    # ------------------------------------------------------------------ 085
    Caso(
        id="dem-085",
        modulo=_M,
        formato="eml",
        agora="2026-10-09 10:00",
        texto=_eml(
            "Comissão Organizadora - CONDIRE 2026 <condire2026@exemplo-mail.com>",
            _ASCOM,
            _q("Convite – palestra no Congresso Estadual de Diretores Escolares"),
            "2026-10-08 11:45",
            """
Prezados,

O Congresso Estadual de Diretores Escolares (CONDIRE 2026) acontecerá de 26 a
28 de novembro, em Foz do Iguaçu, no Centro de Convenções do Hotel Cataratas
Park - Av. das Cataratas, 1118 - Vila Yolanda.

Convidamos a Polícia Civil do Paraná para a palestra "Violência escolar:
prevenção e protocolo de resposta", no dia 27/11, às 10h.

Estimamos cerca de 1.000 diretores.

Comissão Organizadora
(45) 3025-9090
""",
            html=True,
        ),
        esperado={
            "evento": "PALESTRA",
            "temas": ["Violência escolar"],
            "solicitante": Contem("CONDIRE"),
            "email": "condire2026@exemplo-mail.com",
            "telefone": Contem("3025-9090"),
            "data_inicio_evento": "2026-11-27",
            "hora_inicio": "10:00",
            "municipio": "Foz do Iguaçu",
            "estado": "PR",
            "quantidade_publico": 1000,
            "canal_solicitacao": "EMAIL",
            "data_solicitacao": "2026-10-08",
            "local": Contem("Centro de Convenções"),
            "endereco": Contem("Av. das Cataratas, 1118"),
            "bairro": "Vila Yolanda",
        },
        nota="Congresso de 26 a 28/11, palestra só em 27/11.",
    ),
    # ------------------------------------------------------------------ 086
    Caso(
        id="dem-086",
        modulo=_M,
        formato="texto",
        agora="2026-12-18 10:00",
        texto="""
[17/12/2026 10:40] Cláudio - Assoc. Motoristas Aplicativo Litoral: Bom dia! Aqui é o Cláudio, presidente da Associação dos Motoristas de Aplicativo do Litoral
[17/12/2026 10:41] Cláudio - Assoc. Motoristas Aplicativo Litoral: Queremos uma palestra sobre trânsito, álcool e direção para os motoristas antes do pico da temporada
[17/12/2026 10:42] Cláudio - Assoc. Motoristas Aplicativo Litoral: Dia 8 de janeiro, às 20h, no salão da colônia de pescadores, em Pontal do Paraná (Av. Beira-Mar, 2500 - Shangri-lá)
[17/12/2026 10:42] Cláudio - Assoc. Motoristas Aplicativo Litoral: uns 90 motoristas
""",
        esperado={
            "evento": "PALESTRA",
            "temas": ["Trânsito"],
            "solicitante": Contem("Associação dos Motoristas de Aplicativo"),
            "data_inicio_evento": "2027-01-08",
            "hora_inicio": "20:00",
            "municipio": "Pontal do Paraná",
            "estado": "PR",
            "quantidade_publico": 90,
            "canal_solicitacao": "WHATSAPP",
            "data_solicitacao": "2026-12-17",
            "local": Contem("colônia de pescadores"),
            "endereco": Contem("Av. Beira-Mar, 2500"),
            "bairro": "Shangri-lá",
            "palestrantes": AUSENTE,
        },
        nota="Virada de ano (8 de janeiro → 2027); 'Cláudio' remetente não é o palestrante Cláudio Wosniak.",
    ),
    # ------------------------------------------------------------------ 087
    Caso(
        id="dem-087",
        modulo=_M,
        formato="eml",
        agora="2026-10-22 10:00",
        texto=_eml(
            "Faculdade do Noroeste Paranaense <extensao@fanop-exemplo.edu.br>",
            _ASCOM,
            "Palestra carreira policial",
            "2026-10-21 08:44",
            """
Prezados,

A Faculdade do Noroeste Paranaense (FANOP), de Cruzeiro do Oeste, gostaria de
uma palestra sobre a carreira policial (Polícia Civil: cargos, concurso,
atribuições) para os acadêmicos de Direito e de Gestão Pública, em 14/11/26
às 9h.

Local: Auditório Central - Rua Prof. Bento Munhoz, 60 - Centro.
Público: 150 acadêmicos.

Setor de Extensão
(44) 3676-4400
""",
        ),
        esperado={
            "evento": "PALESTRA",
            "temas": ["Carreira policial"],
            "solicitante": Contem("Faculdade do Noroeste Paranaense"),
            "email": "extensao@fanop-exemplo.edu.br",
            "telefone": Contem("3676-4400"),
            "data_inicio_evento": "2026-11-14",
            "hora_inicio": "09:00",
            "municipio": "Cruzeiro do Oeste",
            "estado": "PR",
            "quantidade_publico": 150,
            "canal_solicitacao": "EMAIL",
            "data_solicitacao": "2026-10-21",
            "local": Contem("Auditório Central"),
            "endereco": Contem("Rua Prof. Bento Munhoz, 60"),
            "bairro": "Centro",
        },
        nota="Ano com dois dígitos ('14/11/26').",
    ),
    # ------------------------------------------------------------------ 088
    Caso(
        id="dem-088",
        modulo=_M,
        formato="eml",
        agora="2026-11-05 10:00",
        texto=_eml(
            "DIRECAO ESCOLA <escolaestadualsengesdirecao@exemplo-mail.com>",
            _ASCOM,
            "PALESTRA",
            "2026-11-04 12:12",
            """
BOM DIA
SOLICITO PALESTRA SOBRE DROGAS NA ESCOLA ESTADUAL VEREADOR JOAO BATISTA DE SOUZA EM SENGES DIA 25 DE NOVEMBRO AS 10 HORAS PARA 200 ALUNOS
ENDERECO RUA SAO PAULO 300 CENTRO
TELEFONE 43 3567 1234
""",
        ),
        esperado={
            "evento": "PALESTRA",
            "temas": ["Drogas"],
            "solicitante": Contem("VEREADOR JOAO BATISTA DE SOUZA"),
            "email": "escolaestadualsengesdirecao@exemplo-mail.com",
            "telefone": Contem("1234"),
            "data_inicio_evento": "2026-11-25",
            "hora_inicio": "10:00",
            "municipio": "Sengés",
            "estado": "PR",
            "quantidade_publico": 200,
            "canal_solicitacao": "EMAIL",
            "data_solicitacao": "2026-11-04",
            "local": Contem("VEREADOR JOAO BATISTA DE SOUZA"),
            "endereco": Contem("RUA SAO PAULO 300"),
        },
        nota="Tudo em CAIXA ALTA, sem acento nem pontuação ('SENGES' → Sengés); 'Rua São Paulo' não é estado.",
    ),
    # ------------------------------------------------------------------ 089
    Caso(
        id="dem-089",
        modulo=_M,
        formato="texto",
        agora="2026-11-18 10:00",
        texto="""
De: Andressa Cordeiro <andressa.cordeiro@transportesmatrix-exemplo.com.br>
Enviado em: terça-feira, 17 de novembro de 2026 16:05
Para: ASCOM PCPR <ascom.palestras@pc.pr.gov.br>
Assunto: Palestra sobre assédio - Transportes Matrix

Olá,

A Transportes Matrix, de Guarapuava, está implantando o canal de denúncias e
gostaria de uma palestra sobre assédio moral e sexual para os colaboradores.

Dia 3/12, às 14h, no galpão da empresa: Rua Rio Grande do Sul, 3300 - Boqueirão.
Aproximadamente 110 pessoas.

Obrigada,
Andressa Cordeiro | Recursos Humanos
(42) 3035-2020 | (42) 99812-0909
""",
        esperado={
            "evento": "PALESTRA",
            "temas": ["Assédio moral e sexual"],
            "solicitante": Contem("Transportes Matrix"),
            "email": "andressa.cordeiro@transportesmatrix-exemplo.com.br",
            "data_inicio_evento": "2026-12-03",
            "hora_inicio": "14:00",
            "municipio": "Guarapuava",
            "estado": "PR",
            "quantidade_publico": 110,
            "canal_solicitacao": "EMAIL",
            "data_solicitacao": "2026-11-17",
            "local": Contem("galpão da empresa"),
            "endereco": Contem("Rua Rio Grande do Sul, 3300"),
            "bairro": "Boqueirão",
        },
        nota="'Rua Rio Grande do Sul' não é estado; bairro Boqueirão (também bairro de Curitiba).",
    ),
    # ------------------------------------------------------------------ 090
    Caso(
        id="dem-090",
        modulo=_M,
        formato="eml",
        agora="2026-11-16 10:00",
        texto=_eml(
            "Grupo de Jovens Unidos <jovensunidos.cg@exemplo-mail.com>",
            _ASCOM,
            "palestra drogas dezembro",
            "2026-11-14 20:20",
            """
Oi, boa noite

Somos um grupo de jovens de igrejas dos Campos Gerais e queremos fazer um
encontro com palestra sobre drogas no dia 10/12, às 19h. Ainda estamos
decidindo se vai ser em Castro ou em Carambeí, dependendo do salão que
conseguirmos. Assim que definir mandamos o endereço.

Devem ser umas 150 pessoas.

Mateus Holzmann
(42) 99901-3355
""",
        ),
        esperado={
            "evento": "PALESTRA",
            "temas": ["Drogas"],
            "email": "jovensunidos.cg@exemplo-mail.com",
            "telefone": Contem("99901-3355"),
            "data_inicio_evento": "2026-12-10",
            "hora_inicio": "19:00",
            "municipio": AUSENTE,
            "quantidade_publico": 150,
            "canal_solicitacao": "EMAIL",
            "data_solicitacao": "2026-11-14",
            "endereco": AUSENTE,
        },
        nota="Local indefinido entre Castro e Carambeí: não escolher município.",
    ),
    # ------------------------------------------------------------------ 091
    Caso(
        id="dem-091",
        modulo=_M,
        formato="eml",
        agora="2026-11-09 10:00",
        texto=_eml(
            "Pastoral Familiar - Paróquia Santa Rita <pastoral.santarita@exemplo-mail.com>",
            _ASCOM,
            _q("Encontro de Pais – segurança dos filhos na internet"),
            "2026-11-07 09:30",
            """
Bom dia!

A Pastoral Familiar da Paróquia Santa Rita de Cássia, de Almirante Tamandaré,
convida a Polícia Civil para uma palestra sobre crimes cibernéticos e a
proteção dos filhos na internet, no Encontro de Pais do dia 29/11 (domingo),
às 9h, no salão paroquial (Rua Ângelo Tosin, 90 - Lamenha Pequena).

Esperamos umas 100 pessoas.

Deus abençoe,
Casal coordenador: Vilmar e Rosana Pasqualin
(41) 99677-4545
""",
        ),
        esperado={
            "evento": "PALESTRA",
            "temas": ["Crimes cibernéticos"],
            "solicitante": Contem("Paróquia Santa Rita"),
            "email": "pastoral.santarita@exemplo-mail.com",
            "telefone": Contem("99677-4545"),
            "data_inicio_evento": "2026-11-29",
            "hora_inicio": "09:00",
            "municipio": "Almirante Tamandaré",
            "estado": "PR",
            "quantidade_publico": 100,
            "canal_solicitacao": "EMAIL",
            "data_solicitacao": "2026-11-07",
            "local": Contem("salão paroquial"),
            "endereco": Contem("Rua Ângelo Tosin, 90"),
            "bairro": "Lamenha Pequena",
        },
        nota="Domingo 29/11; 'Santa Rita' não é município aqui.",
    ),
    # ------------------------------------------------------------------ 092
    Caso(
        id="dem-092",
        modulo=_M,
        formato="texto",
        agora="2026-11-02 10:00",
        texto="""
Olá! Sou a conselheira do Clube de Desbravadores Águias do Norte, de Arapongas.
Gostaríamos de uma palestra sobre drogas para os desbravadores (10 a 15 anos)
no próximo sábado, das 14h às 16h, na Igreja Adventista Central - Rua
Beija-Flor, 1200 - Centro. Somos 45 crianças e adolescentes.
Contato: Priscila (43) 99744-2323
""",
        esperado={
            "evento": "PALESTRA",
            "temas": ["Drogas"],
            "solicitante": Contem("Clube de Desbravadores"),
            "telefone": Contem("99744-2323"),
            "data_inicio_evento": "2026-11-07",
            "hora_inicio": "14:00",
            "municipio": "Arapongas",
            "estado": "PR",
            "quantidade_publico": 45,
            "local": Contem("Igreja Adventista Central"),
            "endereco": Contem("Beija-Flor, 1200"),
            "bairro": "Centro",
        },
        nota="Texto sem data do pedido: 'próximo sábado' relativo a agora (seg 02/11) → 07/11; 'das 14h às 16h'.",
    ),
    # ------------------------------------------------------------------ 093
    Caso(
        id="dem-093",
        modulo=_M,
        formato="eml",
        agora="2026-10-14 10:00",
        texto=_eml(
            "Escola Municipal Irati <em.irati@araucaria-exemplo.pr.gov.br>",
            _ASCOM,
            "Palestra para pais - autoproteção infantil",
            "2026-10-13 15:22",
            """
Boa tarde,

A Escola Municipal Irati, de Araucária, solicita uma palestra sobre abuso
sexual infantil para os pais dos alunos da educação infantil e anos iniciais,
no dia 05/11, às 19h, no refeitório da escola.

Rua Irati, 455 - Capela Velha - Araucária/PR - CEP 83705-000

Público: cerca de 130 pais.

Direção
(41) 3614-2626
""",
        ),
        esperado={
            "evento": "PALESTRA",
            "temas": ["Abuso sexual infantil"],
            "solicitante": Contem("Escola Municipal Irati"),
            "email": "em.irati@araucaria-exemplo.pr.gov.br",
            "telefone": Contem("3614-2626"),
            "data_inicio_evento": "2026-11-05",
            "hora_inicio": "19:00",
            "municipio": "Araucária",
            "estado": "PR",
            "quantidade_publico": 130,
            "canal_solicitacao": "EMAIL",
            "data_solicitacao": "2026-10-13",
            "local": Contem("refeitório da escola"),
            "endereco": Contem("Rua Irati, 455"),
            "bairro": "Capela Velha",
            "cep": "83705-000",
        },
        nota="'Irati' é nome da escola e da rua; o município é Araucária.",
    ),
    # ------------------------------------------------------------------ 094
    Caso(
        id="dem-094",
        modulo=_M,
        formato="texto",
        agora="2026-08-04 10:00",
        texto="""
[03/08/2026 17:30] Auto Escola Esperança: Boa tarde, somos da Auto Escola Esperança de Nova Esperança
[03/08/2026 17:31] Auto Escola Esperança: Queríamos uma palestra sobre trânsito (embriaguez ao volante, fuga do local de acidente) para nossos alunos no dia 15/08 às 9h
[03/08/2026 17:31] Auto Escola Esperança: na nossa sala: Av. Rocha Pombo, 1450 - Centro. São 40 alunos
[03/08/2026 17:32] Auto Escola Esperança: Atendemos de segunda a sábado das 8h às 20h, qualquer coisa liga (44) 3252-8181
""",
        esperado={
            "evento": "PALESTRA",
            "temas": ["Trânsito"],
            "solicitante": Contem("Auto Escola Esperança"),
            "telefone": Contem("3252-8181"),
            "data_inicio_evento": "2026-08-15",
            "hora_inicio": "09:00",
            "municipio": "Nova Esperança",
            "estado": "PR",
            "quantidade_publico": 40,
            "canal_solicitacao": "WHATSAPP",
            "data_solicitacao": "2026-08-03",
            "endereco": Contem("Av. Rocha Pombo, 1450"),
            "bairro": "Centro",
        },
        nota="'Esperança' repetido no nome da empresa; horário de atendimento não é hora.",
    ),
    # ------------------------------------------------------------------ 095
    Caso(
        id="dem-095",
        modulo=_M,
        formato="eml",
        agora="2026-09-08 10:00",
        texto=_eml(
            "Coordenação de Direito - Faculdade Vale do Jordão <direito@fvj-exemplo.edu.br>",
            _ASCOM,
            _q("Semana de Direito – palestra com a Escrivã Tatiane Rauber"),
            "2026-09-04 16:40",
            """
Prezados,

Na Semana de Direito da Faculdade Vale do Jordão, em Guarapuava, gostaríamos
de uma palestra sobre carreira policial, com a Escrivã Tatiane Rauber, ex-aluna
da nossa instituição.

Data: 29/09
Horário: 19h
Local: Auditório - Rua XV de Novembro, 7050 - Centro
Público: 200 acadêmicos

Atenciosamente,
Profª Daniela Ferri
(42) 3629-7000
""",
        ),
        esperado={
            "evento": "PALESTRA",
            "temas": ["Carreira policial"],
            "palestrantes": ["Tatiane Rauber"],
            "solicitante": Contem("Faculdade Vale do Jordão"),
            "email": "direito@fvj-exemplo.edu.br",
            "telefone": Contem("3629-7000"),
            "data_inicio_evento": "2026-09-29",
            "hora_inicio": "19:00",
            "municipio": "Guarapuava",
            "estado": "PR",
            "quantidade_publico": 200,
            "canal_solicitacao": "EMAIL",
            "data_solicitacao": "2026-09-04",
            "local": Contem("Auditório"),
            "endereco": Contem("Rua XV de Novembro, 7050"),
            "bairro": "Centro",
        },
        nota="Palestrante nominal no assunto e no corpo.",
    ),
    # ------------------------------------------------------------------ 096
    Caso(
        id="dem-096",
        modulo=_M,
        formato="texto",
        agora="2026-11-26 10:00",
        texto="""
De: Sindicato dos Vigilantes de Londrina <secretaria@sindvigilantes-exemplo.org.br>
Enviado em: quarta-feira, 25 de novembro de 2026 08:48
Para: ascom.palestras@pc.pr.gov.br
Assunto: Palestra - armas de fogo

Prezados,

O Sindicato dos Vigilantes de Londrina solicita palestra sobre armas de fogo
(legislação, porte funcional, Estatuto do Desarmamento) para a reciclagem dos
vigilantes, no dia 9/12, às 8h, na sede do sindicato: Rua Pernambuco, 540 -
Centro - CEP 86020-120.

Público: 60 vigilantes.

Secretaria do Sindicato
(43) 3324-1122
""",
        esperado={
            "evento": "PALESTRA",
            "temas": ["Armas de fogo e desarmamento"],
            "solicitante": Contem("Sindicato dos Vigilantes"),
            "email": "secretaria@sindvigilantes-exemplo.org.br",
            "telefone": Contem("3324-1122"),
            "data_inicio_evento": "2026-12-09",
            "hora_inicio": "08:00",
            "municipio": "Londrina",
            "estado": "PR",
            "quantidade_publico": 60,
            "canal_solicitacao": "EMAIL",
            "data_solicitacao": "2026-11-25",
            "local": Contem("sede do sindicato"),
            "endereco": Contem("Rua Pernambuco, 540"),
            "bairro": "Centro",
            "cep": "86020-120",
        },
        nota="Outlook colado; 'Rua Pernambuco' não é estado.",
    ),
    # ------------------------------------------------------------------ 097
    Caso(
        id="dem-097",
        modulo=_M,
        formato="eml",
        agora="2026-11-24 10:00",
        texto=_eml(
            "Escola Estadual do Campo Faxinal dos Silvérios <ee.faxinalsilverios@escola.pr.gov.br>",
            _ASCOM,
            "Pedido de palestra sobre drogas",
            "2026-11-23 13:00",
            """
Boa tarde!

A Escola Estadual do Campo Faxinal dos Silvérios, no interior de Pinhão,
solicita uma palestra sobre drogas para os alunos do 6º ao 9º ano, no dia
10/12 às 9h, na própria escola (Estrada Faxinal dos Silvérios, km 18 - Distrito
de Faxinal dos Silvérios).

São cerca de 75 alunos.

Direção
(42) 3677-1290
""",
        ),
        esperado={
            "evento": "PALESTRA",
            "temas": ["Drogas"],
            "solicitante": Contem("Faxinal dos Silvérios"),
            "email": "ee.faxinalsilverios@escola.pr.gov.br",
            "telefone": Contem("3677-1290"),
            "data_inicio_evento": "2026-12-10",
            "hora_inicio": "09:00",
            "municipio": "Pinhão",
            "estado": "PR",
            "quantidade_publico": 75,
            "canal_solicitacao": "EMAIL",
            "data_solicitacao": "2026-11-23",
            "local": Contem("Faxinal dos Silvérios"),
            "endereco": Contem("Estrada Faxinal dos Silvérios, km 18"),
        },
        nota="'Faxinal' (também município) é distrito de Pinhão aqui.",
    ),
    # ------------------------------------------------------------------ 098
    Caso(
        id="dem-098",
        modulo=_M,
        formato="texto",
        agora="2026-11-25 10:00",
        texto="""
ASSOCIAÇÃO DE MORADORES DO JARDIM CONCÓRDIA - PALOTINA

Prezados,

Solicitamos uma palestra sobre golpes e fraudes (golpe do falso parente,
falso sequestro, Pix) para a comunidade, no dia 7 de dezembro, segunda-feira,
às 19h.

Local: Salão Comunitário do Jardim Concórdia
Rua Rio de Janeiro, 850
Jardim Concórdia
CEP 85950-000

Público estimado: 70 moradores.

Contato: Ivo Kunz - (44) 99988-7070
""",
        esperado={
            "evento": "PALESTRA",
            "temas": ["Golpes e fraudes"],
            "solicitante": Contem("Associação de Moradores do Jardim Concórdia"),
            "telefone": Contem("99988-7070"),
            "data_inicio_evento": "2026-12-07",
            "hora_inicio": "19:00",
            "municipio": "Palotina",
            "estado": "PR",
            "quantidade_publico": 70,
            "local": Contem("Salão Comunitário do Jardim Concórdia"),
            "endereco": Contem("Rua Rio de Janeiro, 850"),
            "bairro": "Jardim Concórdia",
            "cep": "85950-000",
        },
        nota="Endereço em linhas separadas; 'Concórdia' é município de SC mas aqui é bairro de Palotina.",
    ),
    # ------------------------------------------------------------------ 099
    Caso(
        id="dem-099",
        modulo=_M,
        formato="eml",
        agora="2026-12-18 10:00",
        texto=_eml(
            "CE Carlos Gomes <ce.carlosgomes.assis@escola.pr.gov.br>",
            _ASCOM,
            "Abertura do ano letivo 2027 - palestra",
            "2026-12-16 11:30",
            """
Prezados,

O Colégio Estadual Carlos Gomes, de Assis Chateaubriand, gostaria de uma
palestra sobre educação para a cidadania na abertura do ano letivo, no dia
18/02/2027, às 8h, na quadra do colégio (Rua Guaíra, 1500 - Centro).

Público: 500 alunos.

Em 2026 a abertura foi dia 12/02/2026 e a direção quer repetir o formato.

Atenciosamente,
Direção
(44) 3528-3030
""",
        ),
        esperado={
            "evento": "PALESTRA",
            "temas": ["Educação para a cidadania"],
            "solicitante": Contem("Carlos Gomes"),
            "email": "ce.carlosgomes.assis@escola.pr.gov.br",
            "telefone": Contem("3528-3030"),
            "data_inicio_evento": "2027-02-18",
            "hora_inicio": "08:00",
            "municipio": "Assis Chateaubriand",
            "estado": "PR",
            "quantidade_publico": 500,
            "canal_solicitacao": "EMAIL",
            "data_solicitacao": "2026-12-16",
            "local": Contem("quadra do colégio"),
            "endereco": Contem("Rua Guaíra, 1500"),
            "bairro": "Centro",
        },
        nota="Evento em 2027 com ano explícito; data de 2026 citada; 'Rua Guaíra' não é o município.",
    ),
    # ------------------------------------------------------------------ 100
    Caso(
        id="dem-100",
        modulo=_M,
        formato="texto",
        agora="2026-11-17 10:00",
        texto="""
[16/11/2026 19:10] Lurdes Arapongas: Oi, boa noite. Sou de Arapongas, mas a palestra que quero pedir é em Apucarana, no Grupo de Mulheres Empreendedoras
[16/11/2026 19:11] Lurdes Arapongas: tema: segurança da mulher, dicas de autoproteção
[16/11/2026 19:12] Lurdes Arapongas: sexta dia 27/11 as 20h no Hotel Colonial, Rua Ponta Grossa, 1500 - Centro
[16/11/2026 19:12] Lurdes Arapongas: 50 mulheres
""",
        esperado={
            "evento": "PALESTRA",
            "temas": ["Segurança da mulher"],
            "solicitante": Contem("Grupo de Mulheres Empreendedoras"),
            "data_inicio_evento": "2026-11-27",
            "hora_inicio": "20:00",
            "municipio": "Apucarana",
            "estado": "PR",
            "quantidade_publico": 50,
            "canal_solicitacao": "WHATSAPP",
            "data_solicitacao": "2026-11-16",
            "local": Contem("Hotel Colonial"),
            "endereco": Contem("Rua Ponta Grossa, 1500"),
            "bairro": "Centro",
        },
        nota="Remetente é de Arapongas (até no nome do contato); o evento é em Apucarana; 'Rua Ponta Grossa'.",
    ),
    # ------------------------------------------------------------------ 101
    Caso(
        id="dem-101",
        modulo=_M,
        formato="eml",
        agora="2026-10-27 10:00",
        texto=_eml(
            "Débora Chiquim <debora.chiquim@escola.pr.gov.br>",
            _ASCOM,
            "palestra bullying rio branco do sul",
            "2026-10-26 22:47",
            """
boa noite, sou pedagoga do colegio estadual rio branco, em rio branco do sul.
precisamos de palestra sobre bullying dia 18/11 as 13h para o 6 ano (uns 90 alunos)
endereço rua horacio lemos 50 centro

Enviado do meu iPhone
""",
        ),
        esperado={
            "evento": "PALESTRA",
            "temas": ["Bullying"],
            "solicitante": Contem("rio branco"),
            "email": "debora.chiquim@escola.pr.gov.br",
            "data_inicio_evento": "2026-11-18",
            "hora_inicio": "13:00",
            "municipio": "Rio Branco do Sul",
            "estado": "PR",
            "quantidade_publico": 90,
            "canal_solicitacao": "EMAIL",
            "data_solicitacao": "2026-10-26",
            "endereco": Contem("rua horacio lemos 50"),
            "bairro": UmDe("Centro", "centro"),
        },
        nota="Minúsculas e sem acento; 'rio branco' escola vs 'rio branco do sul' município; hora do envio (22h47) não é do evento.",
    ),
    # ------------------------------------------------------------------ 102
    Caso(
        id="dem-102",
        modulo=_M,
        formato="eml",
        agora="2026-11-20 10:00",
        texto=_eml(
            "Associação Comunitária do Cajuru <ascajuru@exemplo-mail.com>",
            _ASCOM,
            _q("PCPR na Comunidade – pedido para o Cajuru"),
            "2026-11-18 14:14",
            """
Prezados,

A Associação Comunitária do Cajuru, em Curitiba, gostaria de receber o PCPR na
Comunidade no sábado, 12/12, das 9h às 13h, na quadra da associação
(Rua Luiz França, 2200 - Cajuru).

Esperamos cerca de 500 moradores ao longo da manhã.

Diretoria
(41) 3266-4040
""",
            html=True,
        ),
        esperado={
            "evento": "PCPR_NA_COMUNIDADE",
            "solicitante": Contem("Associação Comunitária do Cajuru"),
            "email": "ascajuru@exemplo-mail.com",
            "telefone": Contem("3266-4040"),
            "data_inicio_evento": "2026-12-12",
            "hora_inicio": "09:00",
            "municipio": "Curitiba",
            "estado": "PR",
            "quantidade_publico": 500,
            "canal_solicitacao": "EMAIL",
            "data_solicitacao": "2026-11-18",
            "local": Contem("quadra da associação"),
            "endereco": Contem("Rua Luiz França, 2200"),
            "bairro": "Cajuru",
            "temas": AUSENTE,
        },
        nota="Programa PCPR na Comunidade citado pelo nome; sem tema.",
    ),
    # ------------------------------------------------------------------ 103
    Caso(
        id="dem-103",
        modulo=_M,
        formato="texto",
        agora="2026-10-30 10:00",
        texto="""
De: Secretaria de Assistência Social - Teixeira Soares <social@teixeirasoares-exemplo.pr.gov.br>
Enviado em: quinta-feira, 29 de outubro de 2026 09:05
Para: ascom.palestras@pc.pr.gov.br
Assunto: Ciclo de palestras - violência doméstica

Bom dia,

A Secretaria Municipal de Assistência Social de Teixeira Soares organiza um
ciclo de palestras sobre violência doméstica nas comunidades rurais, de 23 a
25/11, sempre às 19h, no Salão Paroquial Central (Rua Coronel Dulcídio, 40 -
Centro).

Pedimos a participação da Polícia Civil nas três noites.

Rosicler Mazur
Secretária
(42) 3460-1212
Endereço da Secretaria: Rua Getúlio Vargas, 222 - Centro - Teixeira Soares/PR
""",
        esperado={
            "evento": "PALESTRA",
            "temas": ["Violência doméstica"],
            "solicitante": Contem("Assistência Social"),
            "email": "social@teixeirasoares-exemplo.pr.gov.br",
            "telefone": Contem("3460-1212"),
            "data_inicio_evento": "2026-11-23",
            "data_fim_evento": "2026-11-25",
            "hora_inicio": "19:00",
            "municipio": "Teixeira Soares",
            "estado": "PR",
            "canal_solicitacao": "EMAIL",
            "data_solicitacao": "2026-10-29",
            "local": Contem("Salão Paroquial Central"),
            "endereco": Contem("Rua Coronel Dulcídio, 40"),
            "bairro": "Centro",
        },
        nota="Dois endereços: o do evento (salão) e o da Secretaria na assinatura; período '23 a 25/11'.",
    ),
    # ------------------------------------------------------------------ 104
    Caso(
        id="dem-104",
        modulo=_M,
        formato="eml",
        agora="2026-11-26 10:00",
        texto=_eml(
            "Eventos - Cresol Campos Gerais <eventos@cresolcg-exemplo.coop.br>",
            _ASCOM,
            "Palestra golpes - agência Castro",
            "2026-11-25 16:16",
            """
Prezados,

A cooperativa de crédito Cresol Campos Gerais convida a Polícia Civil para uma
palestra sobre golpes e fraudes bancárias para os associados da agência de
Castro, no dia 15/12, às 10h, no auditório da agência (Av. Pedro Gomes, 3000 -
Santa Cruz - Castro).

Público: 120 associados.

Na edição passada (dezembro de 2025) a palestra foi em Ponta Grossa.

Att.,
Marketing e Eventos
Cresol Campos Gerais - Sede Administrativa
Rua Balduíno Taques, 1200 - Centro - Ponta Grossa/PR
(42) 3223-9900
""",
        ),
        esperado={
            "evento": "PALESTRA",
            "temas": ["Golpes e fraudes"],
            "solicitante": Contem("Cresol"),
            "email": "eventos@cresolcg-exemplo.coop.br",
            "telefone": Contem("3223-9900"),
            "data_inicio_evento": "2026-12-15",
            "hora_inicio": "10:00",
            "municipio": "Castro",
            "estado": "PR",
            "quantidade_publico": 120,
            "canal_solicitacao": "EMAIL",
            "data_solicitacao": "2026-11-25",
            "local": Contem("auditório da agência"),
            "endereco": Contem("Av. Pedro Gomes, 3000"),
            "bairro": "Santa Cruz",
        },
        nota="Sede em Ponta Grossa e edição de 2025 em Ponta Grossa: o evento é em Castro.",
    ),
    # ------------------------------------------------------------------ 105
    Caso(
        id="dem-105",
        modulo=_M,
        formato="texto",
        agora="2026-11-12 10:00",
        texto="""
DESPACHO - eProtocolo nº 25.001.442-8

Origem: 9ª Subdivisão Policial - Medianeira
Destino: ASCOM/PCPR
Data: 11/11/2026

Encaminho a esta Assessoria o pedido do Colégio Estadual João Manoel Mondrone,
de Medianeira, que solicita palestra sobre drogas para pais e alunos no dia
11/12/2026, às 19h, no ginásio do colégio (Rua Argentina, 1100 - Centro).
Público estimado de 300 pessoas.

Contato do colégio: (45) 3264-2020 - ce.mondrone@escola.pr.gov.br
Pedido do colégio datado de 05/11/2026.
""",
        esperado={
            "evento": "PALESTRA",
            "temas": ["Drogas"],
            "solicitante": Contem("João Manoel Mondrone"),
            "email": "ce.mondrone@escola.pr.gov.br",
            "telefone": Contem("3264-2020"),
            "data_inicio_evento": "2026-12-11",
            "hora_inicio": "19:00",
            "municipio": "Medianeira",
            "estado": "PR",
            "quantidade_publico": 300,
            "canal_solicitacao": "PROTOCOLO",
            "protocolo": "25.001.442-8",
            "data_solicitacao": UmDe("2026-11-05", "2026-11-11"),
            "local": Contem("ginásio do colégio"),
            "endereco": Contem("Rua Argentina, 1100"),
            "bairro": "Centro",
        },
        nota="Despacho do eProtocolo colado; '9ª Subdivisão' não é quantidade nem data; 'Rua Argentina'.",
    ),
    # ------------------------------------------------------------------ 106
    Caso(
        id="dem-106",
        modulo=_M,
        formato="eml",
        agora="2026-11-04 10:00",
        texto=_eml(
            "Feira de Profissões - Universidade do Oeste <feiradeprofissoes@unioeste-exemplo.edu.br>",
            _ASCOM,
            _q("Convite – Feira de Profissões 2026 (estande da Polícia Civil)"),
            "2026-11-03 10:30",
            """
Prezados,

A Universidade do Oeste realizará a Feira de Profissões 2026 nos dias 2 e 3 de
dezembro, das 8h às 17h, no Campus Cascavel
(Rua Universitária, 2069 - Jardim Universitário), e convida a Polícia Civil a montar um estande e apresentar a
carreira policial aos estudantes do ensino médio.

Público estimado: aproximadamente 6.000 estudantes nos dois dias.

Comissão da Feira
(45) 3220-3000
""",
        ),
        esperado={
            "temas": ["Carreira policial"],
            "solicitante": Contem("Universidade do Oeste"),
            "email": "feiradeprofissoes@unioeste-exemplo.edu.br",
            "telefone": Contem("3220-3000"),
            "data_inicio_evento": "2026-12-02",
            "data_fim_evento": "2026-12-03",
            "hora_inicio": "08:00",
            "municipio": "Cascavel",
            "estado": "PR",
            "quantidade_publico": 6000,
            "canal_solicitacao": "EMAIL",
            "data_solicitacao": "2026-11-03",
            "local": Contem("Campus Cascavel"),
            "endereco": Contem("Rua Universitária, 2069"),
            "bairro": "Jardim Universitário",
        },
        nota="Dois dias; 'aproximadamente 6.000' com ponto de milhar.",
    ),
    # ------------------------------------------------------------------ 107
    Caso(
        id="dem-107",
        modulo=_M,
        formato="texto",
        agora="2026-11-16 10:00",
        texto="""
ola bom dia
aqui é do cras de uvaranas em ponta grossa
queremos palestra de violencia domestica pras mulheres do grupo
dia 30/11 as 19 e 30
rua carlos cavalcanti 4000 bairro uvaranas
umas 40 mulher
tel 42 3220 5566
""",
        esperado={
            "evento": "PALESTRA",
            "temas": ["Violência doméstica"],
            "solicitante": Contem("cras"),
            "telefone": Contem("5566"),
            "data_inicio_evento": "2026-11-30",
            "hora_inicio": "19:30",
            "municipio": "Ponta Grossa",
            "estado": "PR",
            "quantidade_publico": 40,
            "endereco": Contem("rua carlos cavalcanti 4000"),
            "bairro": UmDe("Uvaranas", "uvaranas"),
        },
        nota="'19 e 30' = 19h30; tudo minúsculo sem acento.",
    ),
    # ------------------------------------------------------------------ 108
    Caso(
        id="dem-108",
        modulo=_M,
        formato="eml",
        agora="2026-11-19 10:00",
        texto=_eml(
            "Igreja do Evangelho Quadrangular - Sede <ieq.sap@exemplo-mail.com>",
            _ASCOM,
            "Culto da Família - palestra sobre drogas",
            "2026-11-18 08:08",
            """
Prezados, bom dia.

A Igreja do Evangelho Quadrangular - Sede, de Santo Antônio da Platina,
convida a Polícia Civil para falar sobre drogas no Culto da Família do
domingo, 6 de dezembro, às 18h.

Endereço: Rua Rui Barbosa, 1010 - Vila Setti.
Público: cerca de 300 membros.

Pr. Josué Machado
(43) 99621-7788
Secretaria: terça a sexta, 14h às 18h
""",
        ),
        esperado={
            "evento": "PALESTRA",
            "temas": ["Drogas"],
            "solicitante": Contem("Evangelho Quadrangular"),
            "email": "ieq.sap@exemplo-mail.com",
            "telefone": Contem("99621-7788"),
            "data_inicio_evento": "2026-12-06",
            "hora_inicio": "18:00",
            "municipio": "Santo Antônio da Platina",
            "estado": "PR",
            "quantidade_publico": 300,
            "canal_solicitacao": "EMAIL",
            "data_solicitacao": "2026-11-18",
            "endereco": Contem("Rua Rui Barbosa, 1010"),
            "bairro": "Vila Setti",
        },
        nota="Sobrenome 'Machado' do pastor não é município; horário da secretaria 14h às 18h não é o da palestra.",
    ),
    # ------------------------------------------------------------------ 109
    Caso(
        id="dem-109",
        modulo=_M,
        formato="eml",
        agora="2026-08-04 10:00",
        texto=_eml(
            "CE Dom Pedro I - Guaratuba <ce.dompedro.guaratuba@escola.pr.gov.br>",
            _ASCOM,
            _q("Palestra crimes cibernéticos – volta às aulas"),
            "2026-08-03 14:30",
            """
Boa tarde,

Na volta às aulas do segundo semestre, o Colégio Estadual Dom Pedro I, de
Guaratuba, gostaria de uma palestra sobre crimes cibernéticos (nudes,
extorsão, perfis falsos) para o ensino médio.

Data: 18/08, às 10h
Local: pátio coberto - Av. Damião Botelho de Souza, 1000 - Centro
Público: aproximadamente 280 alunos

Prazo para retorno: 10/08.

Direção
(41) 3442-1818
""",
            html=True,
        ),
        esperado={
            "evento": "PALESTRA",
            "temas": ["Crimes cibernéticos"],
            "solicitante": Contem("Dom Pedro I"),
            "email": "ce.dompedro.guaratuba@escola.pr.gov.br",
            "telefone": Contem("3442-1818"),
            "data_inicio_evento": "2026-08-18",
            "hora_inicio": "10:00",
            "municipio": "Guaratuba",
            "estado": "PR",
            "quantidade_publico": 280,
            "canal_solicitacao": "EMAIL",
            "data_solicitacao": "2026-08-03",
            "local": Contem("pátio coberto"),
            "endereco": Contem("Av. Damião Botelho de Souza, 1000"),
            "bairro": "Centro",
        },
        nota="Prazo para retorno 10/08 não é data do evento.",
    ),
    # ------------------------------------------------------------------ 110
    Caso(
        id="dem-110",
        modulo=_M,
        formato="texto",
        agora="2026-08-10 10:00",
        texto="""
[10/08/2026 09:12] Tio Beto - Van Escolar: bom dia sou presidente da associacao dos transportadores escolares de rio negro
[10/08/2026 09:13] Tio Beto - Van Escolar: queria uma palestra de transito pros motoristas de van dia 1/9 as 15h na camara de vereadores
[10/08/2026 09:14] Tio Beto - Van Escolar: uns 35 motoristas, vlw
""",
        esperado={
            "evento": "PALESTRA",
            "temas": ["Trânsito"],
            "solicitante": Contem("transportadores escolares"),
            "data_inicio_evento": "2026-09-01",
            "hora_inicio": "15:00",
            "municipio": "Rio Negro",
            "estado": "PR",
            "quantidade_publico": 35,
            "canal_solicitacao": "WHATSAPP",
            "data_solicitacao": "2026-08-10",
            "local": Contem("camara de vereadores"),
        },
        nota="'rio negro' minúsculo (PR, não Rio Negrinho/SC); '1/9' sem zero.",
    ),
]
