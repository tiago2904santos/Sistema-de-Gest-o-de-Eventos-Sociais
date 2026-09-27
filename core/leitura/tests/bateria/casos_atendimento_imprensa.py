"""Bateria do módulo `atendimento_imprensa` (Atendimento à imprensa).

Pedidos de jornalistas à assessoria de imprensa da PCPR: entrevista com o
delegado, nota oficial/posicionamento, dados estatísticos, confirmação de
prisão, sonora para rádio/TV, imagens. Todos os nomes, veículos,
telefones, e-mails e endereços são inventados.

Convenções do gabarito deste módulo:

- ``data`` / ``horario``: quando o PEDIDO foi feito (Date do e-mail em
  horário de Brasília, "Enviado em:" do Outlook, carimbo do WhatsApp).
  Texto colado sem data nenhuma do pedido: fora do gabarito. O horário do
  prazo nunca é o horário do pedido.
- ``deadline`` é um DateField (``Atendimento.deadline``, "deadline /
  veiculação"): só a DATA do prazo ou da veiculação. "até as 16h" num
  e-mail de hoje → a data de hoje; "o quanto antes"/"com urgência" sem dia
  → AUSENTE. Datas de fatos da matéria (crime em 10/09) não são deadline.
- ``veiculo``: o veículo pelo qual o jornalista pede, pelo nome do
  cadastro. Fora do cadastro: ``veiculo`` AUSENTE e ``veiculo_novo`` com o
  nome citado. O domínio do e-mail não manda quando o texto diz outro.
- ``contato``: telefone ou e-mail do JORNALISTA. Quando os dois aparecem,
  qualquer um vale (``UmDe(Contem(tel), Contem(email))``). Contato de
  produtor/assessor que escreve em nome do repórter não é o do repórter.
- ``pedido``: um trecho essencial do que foi pedido (Contem).
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


def _eml(de, para, assunto, enviado, corpo, *, html=False, cc=None, utc=False):
    """Monta um .eml (RFC 822). `enviado`: "2026-09-24 09:12" (Brasília).

    `utc=True` escreve o Date em +0000 (o mesmo instante), como fazem
    alguns servidores de webmail.
    """
    dt = datetime.strptime(enviado, "%Y-%m-%d %H:%M").replace(tzinfo=_BRT)
    dt_cab = dt.astimezone(timezone.utc) if utc else dt
    cab = [
        f"From: {de}",
        f"To: {para}",
    ]
    if cc:
        cab.append(f"Cc: {cc}")
    cab += [
        f"Subject: {assunto}",
        f"Date: {format_datetime(dt_cab)}",
        f"Message-ID: <{dt:%Y%m%d%H%M}.imp{len(assunto) * 7919 % 10**6}@mail.exemplo.test>",
        "MIME-Version: 1.0",
    ]
    corpo = corpo.strip("\n") + "\n"
    if not html:
        cab += [
            "Content-Type: text/plain; charset=utf-8",
            "Content-Transfer-Encoding: 8bit",
        ]
        return "\n".join(cab) + "\n\n" + corpo
    fronteira = "----=_Parte_000_02A7_" + f"{dt:%Y%m%d%H%M}"
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
        f'<html><head><meta charset="utf-8"></head><body style="font-family:Arial">{paragrafos}</body></html>',
        "",
        f"--{fronteira}--",
        "",
    ]
    return "\n".join(cab) + "\n\n" + "\n".join(partes)


_ASCOM = "Assessoria de Imprensa PCPR <imprensa@pc.pr.gov.br>"
_M = "atendimento_imprensa"

_AVISO = (
    "AVISO LEGAL: Esta mensagem e seus anexos são destinados exclusivamente "
    "ao(s) destinatário(s) e podem conter informações confidenciais. Se você "
    "a recebeu por engano, apague-a e avise o remetente. Tratamento de dados "
    "conforme a Lei 13.709/2018."
)

CADASTROS = {
    "veiculo": [
        "Rádio Cidade FM",
        "TV Paraná Sul",
        "Jornal Diário do Oeste",
        "Portal Notícias Já",
        "Rádio Educadora AM",
        "TV Litoral Paranaense",
        "Gazeta dos Campos",
        "Folha do Norte Pioneiro",
        "Rádio Planalto 98 FM",
        "Portal Curitiba em Pauta",
        "Revista Segurança em Foco",
        "TV Iguaçu Canal 8",
        "Jornal Tribuna Ponta-grossense",
        "Agência Pinhão de Notícias",
        "Rádio Vale do Ribeira FM",
    ],
}

CASOS = [
    # ------------------------------------------------------------------ 001
    Caso(
        id="imp-001",
        modulo=_M,
        formato="eml",
        agora="2026-09-28 09:40",
        texto=_eml(
            "Camila Rezende <camila.rezende@tvparanasul.com.br>",
            _ASCOM,
            "Pedido de entrevista - furtos de fios em Curitiba",
            "2026-09-28 09:14",
            """
Bom dia, pessoal da assessoria!

Estou produzindo uma reportagem sobre o aumento dos furtos de fios de cobre
nos bairros do Boqueirão e do Xaxim. Gostaria de uma entrevista com o
delegado responsável pelas investigações, pode ser gravada na delegacia.

Preciso até as 16h de hoje para entrar no jornal da noite.

Obrigada!

Camila Rezende | Repórter | TV Paraná Sul | (41) 99812-4471
""",
        ),
        esperado={
            "jornalista": Contem("Camila Rezende"),
            "veiculo": "TV Paraná Sul",
            "contato": UmDe(Contem("99812-4471"), Contem("camila.rezende@tvparanasul.com.br")),
            "pedido": Contem("entrevista com o delegado"),
            "data": "2026-09-28",
            "horario": "09:14",
            "deadline": "2026-09-28",
        },
        nota="Clássico: 16h é o prazo (deadline hoje), não o horário do pedido (09:14).",
    ),
    # ------------------------------------------------------------------ 002
    Caso(
        id="imp-002",
        modulo=_M,
        formato="eml",
        agora="2026-09-15 18:05",
        texto=_eml(
            "Marcos Tieppo <marcos.tieppo@diariodooeste.com.br>",
            _ASCOM,
            _q("Nota oficial — prisão de suspeito de homicídio em Cascavel"),
            "2026-09-15 17:40",
            """
Boa tarde.

O homicídio aconteceu em 10/09, no bairro Periolo, e ontem (14/09) um
suspeito foi preso. Solicito nota oficial da Polícia Civil sobre a prisão e
o andamento do inquérito: a motivação já foi esclarecida? Há outros
envolvidos?

Fechamos a matéria amanhã às 10h.

Att.,
Marcos Tieppo
Editoria de Polícia - Jornal Diário do Oeste
(45) 3222-0187
""",
        ),
        esperado={
            "jornalista": Contem("Marcos Tieppo"),
            "veiculo": "Jornal Diário do Oeste",
            "contato": UmDe(Contem("3222-0187"), Contem("marcos.tieppo@diariodooeste.com.br")),
            "pedido": Contem("nota oficial"),
            "data": "2026-09-15",
            "horario": "17:40",
            "deadline": "2026-09-16",
        },
        nota="Assunto codificado; 10/09 e 14/09 são datas do crime/prisão, o prazo é amanhã (16/09).",
    ),
    # ------------------------------------------------------------------ 003
    Caso(
        id="imp-003",
        modulo=_M,
        formato="texto",
        agora="2026-10-02 08:20",
        texto="""
[02/10/2026 08:05] Rafa Portal Notícias Já: bom dia!! aqui é o Rafael Monteiro, do Portal Notícias Já
[02/10/2026 08:05] Rafa Portal Notícias Já: vcs confirmam a prisão do homem que atirou no vigilante em Araucária ontem a noite?
[02/10/2026 08:06] Rafa Portal Notícias Já: se puder me retornar o quanto antes agradeço
""",
        esperado={
            "jornalista": Contem("Rafael Monteiro"),
            "veiculo": "Portal Notícias Já",
            "contato": AUSENTE,
            "pedido": Contem("confirmam a prisão"),
            "data": "2026-10-02",
            "horario": "08:05",
            "deadline": AUSENTE,
        },
        nota="'O quanto antes' não é deadline; WhatsApp sem telefone visível: contato não se inventa.",
    ),
    # ------------------------------------------------------------------ 004
    Caso(
        id="imp-004",
        modulo=_M,
        formato="eml",
        agora="2026-10-06 18:40",
        texto=_eml(
            "JOAO PEDRO VARGAS <jpvargas.jornalismo@gmail.com>",
            _ASCOM,
            "sonora delegado - golpe do pix",
            "2026-10-06 18:22",
            """
boa noite

preciso de uma sonora de 30 segundos com o delegado da Delegacia de Estelionato
explicando como a população pode evitar o golpe do pix agendado. Pode ser
audio de whatsapp mesmo. Entramos ao vivo amanhã às 7h no Jornal da Manhã.

JOÃO PEDRO VARGAS
RÁDIO EDUCADORA AM

Enviado do meu Android
""",
            html=True,
        ),
        esperado={
            "jornalista": Contem("João Pedro Vargas"),
            "veiculo": "Rádio Educadora AM",
            "contato": Contem("jpvargas.jornalismo@gmail.com"),
            "pedido": Contem("sonora"),
            "data": "2026-10-06",
            "horario": "18:22",
            "deadline": "2026-10-07",
        },
        nota="Nome em CAIXA ALTA e gmail pessoal; veículo só na assinatura; 7h de amanhã → deadline 07/10.",
    ),
    # ------------------------------------------------------------------ 005
    Caso(
        id="imp-005",
        modulo=_M,
        formato="eml",
        agora="2026-10-07 11:00",
        texto=_eml(
            "Tatiane Moura <tatiane.moura@portalnoticiasja.com.br>",
            _ASCOM,
            "Pauta: laboratório de genética forense",
            "2026-10-07 10:31",
            """
Olá, tudo bem?

Apesar do e-mail do Portal, desta vez escrevo como colaboradora da Revista
Segurança em Foco, que prepara uma edição especial sobre perícia.
Gostaria de agendar uma entrevista com a delegada responsável pelo banco
de perfis genéticos e, se possível, fazer imagens do laboratório.

A revista fecha a edição na sexta-feira (16/10).

Tatiane Moura
(41) 99655-3090
""",
        ),
        esperado={
            "jornalista": Contem("Tatiane Moura"),
            "veiculo": "Revista Segurança em Foco",
            "contato": UmDe(Contem("99655-3090"), Contem("tatiane.moura@portalnoticiasja.com.br")),
            "pedido": Contem("entrevista com a delegada"),
            "data": "2026-10-07",
            "horario": "10:31",
            "deadline": "2026-10-16",
        },
        nota="Domínio do Portal Notícias Já, mas o pedido é pela Revista Segurança em Foco.",
    ),
    # ------------------------------------------------------------------ 006
    Caso(
        id="imp-006",
        modulo=_M,
        formato="eml",
        agora="2026-10-08 10:00",
        texto=_eml(
            "Produção Jornalismo TV Iguaçu <producao@tviguacu8.com.br>",
            _ASCOM,
            "Solicitação de entrevista - repórter Luana Brandt",
            "2026-10-08 09:47",
            """
Prezados,

Em nome da repórter Luana Brandt, solicitamos entrevista com o delegado-chefe
da 15ª SDP sobre a apreensão de cigarros contrabandeados na BR-277 na
madrugada de terça.

A gravação precisa acontecer até as 15h de hoje.
Contato direto da Luana: (45) 99901-2230.

Atenciosamente,
Roberta Kist
Produtora de Jornalismo - TV Iguaçu Canal 8
(45) 3025-7700
""",
        ),
        esperado={
            "jornalista": Contem("Luana Brandt"),
            "veiculo": "TV Iguaçu Canal 8",
            "contato": Contem("99901-2230"),
            "pedido": Contem("entrevista com o delegado-chefe"),
            "data": "2026-10-08",
            "horario": "09:47",
            "deadline": "2026-10-08",
        },
        nota="Produtora escreve em nome da repórter: jornalista é Luana, contato o dela (não o da produção).",
    ),
    # ------------------------------------------------------------------ 007
    Caso(
        id="imp-007",
        modulo=_M,
        formato="texto",
        agora="2026-10-09 11:15",
        texto="""
De: Edson Kravchuk <edson.plantao@hotmail.com>
Enviado em: sexta-feira, 9 de outubro de 2026 10:47
Para: Imprensa PCPR <imprensa@pc.pr.gov.br>
Assunto: pedido de informação - roubo a banco Guarapuava

Bom dia. Sou editor do blog Plantão Policial Guarapuava e gostaria de saber
se já há suspeitos identificados no roubo à agência bancária de quarta-feira.
Posso aguardar até segunda.

Edson Kravchuk
Plantão Policial Guarapuava
""",
        esperado={
            "jornalista": Contem("Edson Kravchuk"),
            "veiculo": AUSENTE,
            "veiculo_novo": Contem("Plantão Policial Guarapuava"),
            "contato": Contem("edson.plantao@hotmail.com"),
            "pedido": Contem("suspeitos identificados"),
            "data": "2026-10-09",
            "horario": "10:47",
            "deadline": "2026-10-12",
        },
        nota="Blog fora do cadastro → veiculo_novo; 'até segunda' a partir de sexta 09/10 = 12/10.",
    ),
    # ------------------------------------------------------------------ 008
    Caso(
        id="imp-008",
        modulo=_M,
        formato="eml",
        agora="2026-10-13 15:00",
        texto=_eml(
            "Helena Brunetti <helena.brunetti@folhanortepioneiro.com.br>",
            _ASCOM,
            _q("Solicitação de dados estatísticos — homicídios em Londrina"),
            "2026-10-13 14:02",
            """
Prezada equipe,

Para uma reportagem de fim de semana, solicito os dados estatísticos de
homicídios dolosos em Londrina de janeiro a setembro de 2025 e do mesmo
período de 2026, se possível com o percentual de casos esclarecidos.

Preciso das informações até sexta.

Cordialmente,
Helena Brunetti
Repórter | Folha do Norte Pioneiro
(43) 99120-5566
""",
            html=True,
        ),
        esperado={
            "jornalista": Contem("Helena Brunetti"),
            "veiculo": "Folha do Norte Pioneiro",
            "contato": UmDe(Contem("99120-5566"), Contem("helena.brunetti@folhanortepioneiro.com.br")),
            "pedido": Contem("dados estatísticos"),
            "data": "2026-10-13",
            "horario": "14:02",
            "deadline": "2026-10-16",
        },
        nota="'Até sexta' numa terça 13/10 = 16/10; anos 2025/2026 são o recorte dos dados.",
    ),
    # ------------------------------------------------------------------ 009
    Caso(
        id="imp-009",
        modulo=_M,
        formato="eml",
        agora="2026-10-20 14:10",
        texto=_eml(
            "Diego <diegorp@radiocidadefm.com.br>",
            _ASCOM,
            "posicionamento",
            "2026-10-20 13:58",
            """
boa tarde preciso de posicionamento da pc sobre o caso do menino desaparecido em colombo ate 16:30 de hj. obg

Diego - Rádio Cidade FM
""",
        ),
        esperado={
            "jornalista": Contem("Diego"),
            "veiculo": "Rádio Cidade FM",
            "contato": Contem("diegorp@radiocidadefm.com.br"),
            "pedido": Contem("menino desaparecido"),
            "data": "2026-10-20",
            "horario": "13:58",
            "deadline": "2026-10-20",
        },
        nota="E-mail curto e sem acento; 16:30 é prazo, o pedido é das 13:58.",
    ),
    # ------------------------------------------------------------------ 010
    Caso(
        id="imp-010",
        modulo=_M,
        formato="texto",
        agora="2026-10-21 10:00",
        texto="""
Oi, aqui é a Patrícia Lemos, da Gazeta dos Campos. Estou fechando uma matéria
sobre o golpe do falso advogado em Ponta Grossa e gostaria de uma nota oficial
da PCPR com orientações à população. Consigo esperar até o fim do dia.
Meu contato: (42) 99876-1203.
""",
        esperado={
            "jornalista": Contem("Patrícia Lemos"),
            "veiculo": "Gazeta dos Campos",
            "contato": Contem("99876-1203"),
            "pedido": Contem("nota oficial"),
            "deadline": "2026-10-21",
        },
        nota="Texto puro sem data do pedido (data/horário fora); 'fim do dia' = hoje pelo 'agora'.",
    ),
    # ------------------------------------------------------------------ 011
    Caso(
        id="imp-011",
        modulo=_M,
        formato="eml",
        agora="2026-10-22 08:30",
        texto=_eml(
            "Vinícius Albuquerque <vinicius.albuquerque@tvlitoralpr.com.br>",
            _ASCOM,
            "Imagens da operação em Paranaguá",
            "2026-10-22 08:10",
            """
Bom dia!

Vocês têm imagens da operação contra o tráfico cumprida hoje cedo no porto
de Paranaguá? Precisamos do vídeo da entrada das equipes e, se possível, das
apreensões. A reportagem vai ao ar hoje no jornal do meio-dia.

Abraço,
Vinícius Albuquerque
TV Litoral Paranaense
""",
        ),
        esperado={
            "jornalista": Contem("Vinícius Albuquerque"),
            "veiculo": "TV Litoral Paranaense",
            "contato": Contem("vinicius.albuquerque@tvlitoralpr.com.br"),
            "pedido": Contem("imagens da operação"),
            "data": "2026-10-22",
            "horario": "08:10",
            "deadline": "2026-10-22",
        },
        nota="'Vai ao ar hoje no jornal do meio-dia' é inequívoco: veiculação hoje.",
    ),
    # ------------------------------------------------------------------ 012
    Caso(
        id="imp-012",
        modulo=_M,
        formato="eml",
        agora="2026-10-23 17:50",
        texto=_eml(
            "Lívia Taborda <livia.taborda@tvparanasul.com.br>",
            _ASCOM,
            "Entrevista - violência contra idosos",
            "2026-10-23 17:30",
            """
Boa tarde,

Estamos preparando uma série sobre violência contra a pessoa idosa. Gostaria
de uma entrevista com a delegada do Núcleo de Proteção ao Idoso. A matéria
deve ir ao ar no jornal do meio-dia, mas ainda sem data definida pela chefia.

Lívia Taborda
Repórter - TV Paraná Sul
""",
        ),
        esperado={
            "jornalista": Contem("Lívia Taborda"),
            "veiculo": "TV Paraná Sul",
            "contato": Contem("livia.taborda@tvparanasul.com.br"),
            "pedido": Contem("entrevista com a delegada"),
            "data": "2026-10-23",
            "horario": "17:30",
            "deadline": AUSENTE,
        },
        nota="Jornal do meio-dia 'sem data definida': não há deadline; não pôr 12:00 nem hoje.",
    ),
    # ------------------------------------------------------------------ 013
    Caso(
        id="imp-013",
        modulo=_M,
        formato="eml",
        agora="2026-10-26 19:30",
        texto=_eml(
            "Fernanda Okamoto <fe.okamoto@agenciapinhao.com.br>",
            _ASCOM,
            "Re: número de presos na Operação Quimera",
            "2026-10-26 19:05",
            """
Oi, boa noite.

Vocês conseguem me passar o número de presos e de mandados cumpridos na
Operação Quimera? Preciso até amanhã cedo.

Obrigada,
Fernanda Okamoto
Agência Pinhão de Notícias
""",
        ),
        esperado={
            "jornalista": Contem("Fernanda Okamoto"),
            "veiculo": "Agência Pinhão de Notícias",
            "contato": Contem("fe.okamoto@agenciapinhao.com.br"),
            "pedido": Contem("número de presos"),
            "data": "2026-10-26",
            "horario": "19:05",
            "deadline": "2026-10-27",
        },
        nota="'Amanhã cedo' dá a data (27/10); o horário não é inventado (e o campo é só data).",
    ),
    # ------------------------------------------------------------------ 014
    Caso(
        id="imp-014",
        modulo=_M,
        formato="texto",
        agora="2026-10-28 07:15",
        texto="""
[27/10/2026 22:41] Bruna Salvatti TV Paraná Sul: Oi, boa noite! Desculpa o horário. Amanhã cedo te chamo sobre o caso de Pinhais
[28/10/2026 07:02] Bruna Salvatti TV Paraná Sul: Bom dia! Vcs confirmam a prisão do suspeito do latrocínio do taxista em Pinhais?
[28/10/2026 07:03] Bruna Salvatti TV Paraná Sul: Preciso pra hoje até 11h, entra no jornal do almoço
""",
        esperado={
            "jornalista": Contem("Bruna Salvatti"),
            "veiculo": "TV Paraná Sul",
            "pedido": Contem("prisão do suspeito"),
            "data": UmDe("2026-10-27", "2026-10-28"),
            "deadline": "2026-10-28",
        },
        nota="Conversa atravessa a meia-noite; 'hoje até 11h' é de 28/10 (dia da mensagem), não de 27/10.",
    ),
    # ------------------------------------------------------------------ 015
    Caso(
        id="imp-015",
        modulo=_M,
        formato="eml",
        agora="2026-10-27 16:00",
        texto=_eml(
            "Renata Scheffer <renata.scheffer@curitibaempauta.com.br>",
            _ASCOM,
            _q("Pedido de entrevista: medidas protetivas e descumprimento"),
            "2026-10-27 15:22",
            """
Prezada assessoria,

Sou repórter do Portal Curitiba em Pauta e estou produzindo uma reportagem
sobre o descumprimento de medidas protetivas de urgência. Os dados do
Judiciário mostram alta no primeiro semestre e queremos ouvir a Polícia
Civil sobre como funciona a investigação quando a vítima registra o
descumprimento.

Gostaria de uma entrevista com a delegada da Delegacia da Mulher de Curitiba,
por telefone ou vídeo. Prazo: até quinta-feira (29).

Obrigada desde já.

Renata Scheffer
Portal Curitiba em Pauta
(41) 98877-2104

{aviso}
""".format(aviso=_AVISO),
        ),
        esperado={
            "jornalista": Contem("Renata Scheffer"),
            "veiculo": "Portal Curitiba em Pauta",
            "contato": UmDe(Contem("98877-2104"), Contem("renata.scheffer@curitibaempauta.com.br")),
            "pedido": Contem("Delegacia da Mulher"),
            "data": "2026-10-27",
            "horario": "15:22",
            "deadline": "2026-10-29",
        },
        nota="Aviso legal com número de lei no rodapé; prazo 'quinta-feira (29)' = 29/10.",
    ),
    # ------------------------------------------------------------------ 016
    Caso(
        id="imp-016",
        modulo=_M,
        formato="eml",
        agora="2026-11-04 14:40",
        texto=_eml(
            "Otávio Rinaldi <otavio.rinaldi@gazetadoscampos.com.br>",
            _ASCOM,
            "RES: Pedido de dados - furtos de veículos",
            "2026-11-04 14:20",
            """
Olá, reforço o pedido abaixo. A pauta foi adiada e agora preciso até às 18h
de hoje, sem falta.

Otávio

-----Mensagem original-----
De: Otávio Rinaldi <otavio.rinaldi@gazetadoscampos.com.br>
Enviada em: segunda-feira, 2 de novembro de 2026 09:15
Para: imprensa@pc.pr.gov.br
Assunto: Pedido de dados - furtos de veículos

Bom dia. Solicito o número de furtos de veículos registrados em Ponta Grossa
em 2026, mês a mês. Prazo: 03/11.

Otávio Rinaldi
Gazeta dos Campos
""",
        ),
        esperado={
            "jornalista": Contem("Otávio Rinaldi"),
            "veiculo": "Gazeta dos Campos",
            "contato": Contem("otavio.rinaldi@gazetadoscampos.com.br"),
            "pedido": Contem("furtos de veículos"),
            "data": UmDe("2026-11-02", "2026-11-04"),
            "deadline": "2026-11-04",
        },
        nota="O prazo antigo (03/11) está na mensagem citada; vale o novo: hoje (04/11) até 18h.",
    ),
    # ------------------------------------------------------------------ 017
    Caso(
        id="imp-017",
        modulo=_M,
        formato="eml",
        agora="2026-11-05 12:00",
        texto=_eml(
            "Gilberto Nascimento <gilberto.n@tribunapg.com.br>",
            _ASCOM,
            "posicionamento sobre fuga da cadeia pública",
            "2026-11-05 11:30",
            """
Prezados, bom dia.

Solicito posicionamento oficial da PCPR sobre a fuga de dois presos da
carceragem da delegacia de Castro, ocorrida por volta das 3h desta madrugada.
Quantos fugiram, se já houve recaptura e que providências foram tomadas.

Nosso fechamento é às 18h.

Gilberto Nascimento
Jornal Tribuna Ponta-grossense
""",
        ),
        esperado={
            "jornalista": Contem("Gilberto Nascimento"),
            "veiculo": "Jornal Tribuna Ponta-grossense",
            "contato": Contem("gilberto.n@tribunapg.com.br"),
            "pedido": Contem("fuga de dois presos"),
            "data": "2026-11-05",
            "horario": "11:30",
            "deadline": "2026-11-05",
        },
        nota="'3h desta madrugada' é hora do fato; fechamento às 18h → deadline hoje.",
    ),
    # ------------------------------------------------------------------ 018
    Caso(
        id="imp-018",
        modulo=_M,
        formato="texto",
        agora="2026-11-06 15:30",
        texto="""
[06/11/2026 15:12] +55 41 99734-5521: Boa tarde, sou o Henrique Sato, da Rádio Planalto 98 FM
[06/11/2026 15:13] +55 41 99734-5521: Precisamos de uma sonora com o delegado sobre o sequestro relâmpago em São José dos Pinhais. Até as 17h consegue?
""",
        esperado={
            "jornalista": Contem("Henrique Sato"),
            "veiculo": "Rádio Planalto 98 FM",
            "contato": Contem("99734-5521"),
            "pedido": Contem("sonora com o delegado"),
            "data": "2026-11-06",
            "horario": UmDe("15:12", "15:13"),
            "deadline": "2026-11-06",
        },
        nota="Contato é o número do remetente no WhatsApp; 17h é o prazo.",
    ),
    # ------------------------------------------------------------------ 019
    Caso(
        id="imp-019",
        modulo=_M,
        formato="eml",
        agora="2026-11-10 10:00",
        texto=_eml(
            "Caio Werneck <caio.werneck@agenciapinhao.com.br>",
            _ASCOM,
            "Sonora + imagens Operação Rastro Frio",
            "2026-11-10 09:36",
            """
Bom dia,

Sobre a Operação Rastro Frio, deflagrada em 03/11 em Maringá e Sarandi:
solicito sonora do delegado que coordenou a ação e as imagens das
apreensões divulgadas no dia. Vamos publicar um especial até sexta (13).

Caio Werneck
Agência Pinhão de Notícias | (44) 99802-6613
""",
            html=True,
        ),
        esperado={
            "jornalista": Contem("Caio Werneck"),
            "veiculo": "Agência Pinhão de Notícias",
            "contato": UmDe(Contem("99802-6613"), Contem("caio.werneck@agenciapinhao.com.br")),
            "pedido": Contem("sonora do delegado"),
            "data": "2026-11-10",
            "horario": "09:36",
            "deadline": "2026-11-13",
        },
        nota="03/11 é a data da operação (fato), não prazo; prazo sexta 13/11.",
    ),
    # ------------------------------------------------------------------ 020
    Caso(
        id="imp-020",
        modulo=_M,
        formato="eml",
        agora="2026-11-11 09:10",
        texto=_eml(
            "Silvana Prestes <silvana@novaalianca104.com.br>",
            _ASCOM,
            _q("Solicitação urgente — nota sobre ataque a escola"),
            "2026-11-11 08:52",
            """
Bom dia!

Aqui é a Silvana Prestes, da Rádio Nova Aliança 104 FM, de Campo Mourão.
Precisamos de uma nota da Polícia Civil sobre as ameaças de ataque à escola
estadual divulgadas nas redes sociais. Se puderem responder o quanto antes,
agradecemos muito.

Silvana
""",
            html=True,
        ),
        esperado={
            "jornalista": Contem("Silvana Prestes"),
            "veiculo": AUSENTE,
            "veiculo_novo": Contem("Nova Aliança 104 FM"),
            "contato": Contem("silvana@novaalianca104.com.br"),
            "pedido": Contem("ameaças de ataque"),
            "data": "2026-11-11",
            "horario": "08:52",
            "deadline": AUSENTE,
        },
        nota="Rádio fora do cadastro; 'urgente'/'o quanto antes' sem dia → deadline AUSENTE.",
    ),
    # ------------------------------------------------------------------ 021
    Caso(
        id="imp-021",
        modulo=_M,
        formato="eml",
        agora="2026-11-17 08:00",
        texto=_eml(
            "Mateus Fontana <mateus.fontana@diariodooeste.com.br>",
            _ASCOM,
            "Pedido de confirmação - prisão em Toledo",
            "2026-11-16 22:40",
            """
Boa noite.

Recebemos a informação de que um homem foi preso hoje à tarde em Toledo,
suspeito de abusar da enteada. A Polícia Civil confirma a prisão? Qual
delegacia conduz o caso?

Preciso até amanhã às 10h.

Mateus Fontana
Jornal Diário do Oeste
""",
            utc=True,
        ),
        esperado={
            "jornalista": Contem("Mateus Fontana"),
            "veiculo": "Jornal Diário do Oeste",
            "contato": Contem("mateus.fontana@diariodooeste.com.br"),
            "pedido": Contem("confirma a prisão"),
            "data": "2026-11-16",
            "horario": "22:40",
            "deadline": "2026-11-17",
        },
        nota="Date em +0000 (17/11 01:40 UTC) = 16/11 22:40 em Brasília; 'amanhã' conta do envio.",
    ),
    # ------------------------------------------------------------------ 022
    Caso(
        id="imp-022",
        modulo=_M,
        formato="texto",
        agora="2026-11-18 16:20",
        texto="""
De: Priscila Andrade [mailto:priscila.andrade@radiocidadefm.com.br]
Enviado em: quarta-feira, 18 de novembro de 2026 16:02
Para: Imprensa PCPR
Assunto: Entrevista ao vivo amanhã

Boa tarde!

Gostaríamos de convidar o delegado-geral para uma entrevista ao vivo no
programa Cidade Alerta Manhã, amanhã, das 8h às 8h20, sobre o balanço das
ações de segurança para o fim de ano. Pode ser por telefone.

Priscila Andrade
Produção | Rádio Cidade FM
(41) 3344-9021
""",
        esperado={
            "jornalista": Contem("Priscila Andrade"),
            "veiculo": "Rádio Cidade FM",
            "contato": UmDe(Contem("3344-9021"), Contem("priscila.andrade@radiocidadefm.com.br")),
            "pedido": Contem("entrevista ao vivo"),
            "data": "2026-11-18",
            "horario": "16:02",
            "deadline": "2026-11-19",
        },
        nota="Outlook com [mailto:]; veiculação amanhã (19/11) às 8h; 8h/8h20 não são horário do pedido.",
    ),
    # ------------------------------------------------------------------ 023
    Caso(
        id="imp-023",
        modulo=_M,
        formato="eml",
        agora="2026-11-19 10:30",
        texto=_eml(
            "redacao@portalnoticiasja.com.br",
            _ASCOM,
            "nota",
            "2026-11-19 10:12",
            """
Bom dia, precisamos de uma nota sobre a morte do detento na delegacia de
Almirante Tamandaré. Até as 14h.

Redação Portal Notícias Já
""",
        ),
        esperado={
            "jornalista": AUSENTE,
            "veiculo": "Portal Notícias Já",
            "contato": Contem("redacao@portalnoticiasja.com.br"),
            "pedido": Contem("morte do detento"),
            "data": "2026-11-19",
            "horario": "10:12",
            "deadline": "2026-11-19",
        },
        nota="Sem nome de pessoa: jornalista não se inventa ('Redação' não é nome).",
    ),
    # ------------------------------------------------------------------ 024
    Caso(
        id="imp-024",
        modulo=_M,
        formato="eml",
        agora="2026-11-20 15:00",
        texto=_eml(
            "Alessandra Wojcik <ale.wojcik@tvparanasul.com.br>",
            _ASCOM,
            "Pedido de entrevista - Rádio Vale do Ribeira FM",
            "2026-11-20 14:25",
            """
Olá!

Mudei de emprego há poucas semanas (ainda estou com o e-mail antigo da
TV Paraná Sul) e agora apresento o programa da tarde na Rádio Vale do Ribeira FM.
Queria agendar uma entrevista com o delegado de Cerro Azul sobre os
furtos de gado na região. Pode ser na semana que vem,
até quarta (25).

Alessandra Wojcik
(41) 99210-7765
""",
        ),
        esperado={
            "jornalista": Contem("Alessandra Wojcik"),
            "veiculo": "Rádio Vale do Ribeira FM",
            "contato": UmDe(Contem("99210-7765"), Contem("ale.wojcik@tvparanasul.com.br")),
            "pedido": Contem("furtos de gado"),
            "data": "2026-11-20",
            "horario": "14:25",
            "deadline": "2026-11-25",
        },
        nota="E-mail antigo da TV Paraná Sul, mas pede pela Rádio Vale do Ribeira FM.",
    ),
    # ------------------------------------------------------------------ 025
    Caso(
        id="imp-025",
        modulo=_M,
        formato="texto",
        agora="2026-11-23 09:00",
        texto="""
[23/11/2026 08:41] Juliano Gazeta: bom dia, tudo bem?
[23/11/2026 08:42] Juliano Gazeta: Juliano Ferraz aqui, Gazeta dos Campos
[23/11/2026 08:44] Juliano Gazeta: consegue os dados de violência doméstica de Ponta Grossa no último trimestre? queria publicar amanhã
[23/11/2026 08:44] Juliano Gazeta: se me mandar até amanhã às 9h já dá
""",
        esperado={
            "jornalista": Contem("Juliano Ferraz"),
            "veiculo": "Gazeta dos Campos",
            "pedido": Contem("violência doméstica"),
            "data": "2026-11-23",
            "horario": "08:44",
            "deadline": "2026-11-24",
        },
        nota="O pedido é da mensagem das 08:44 (as anteriores são saudação); prazo amanhã 24/11.",
    ),
    # ------------------------------------------------------------------ 026
    Caso(
        id="imp-026",
        modulo=_M,
        formato="eml",
        agora="2026-11-24 11:10",
        texto=_eml(
            "Luciana Hartmann <luciana.hartmann@segurancaemfoco.com.br>",
            _ASCOM,
            _q("Revista Segurança em Foco — entrevista sobre crimes cibernéticos"),
            "2026-11-24 10:58",
            """
Prezados,

A Revista Segurança em Foco prepara a edição de dezembro com o tema
"Crimes cibernéticos contra idosos". Gostaríamos de entrevistar o delegado
titular do Núcleo de Combate aos Cibercrimes (NUCIBER), por e-mail mesmo,
com cinco perguntas que envio em anexo assim que houver o aceite.

O material precisa chegar até 04/12, data de fechamento da edição.

Um abraço,
Luciana Hartmann
Editora-assistente
Revista Segurança em Foco
Tel. (41) 3029-4410 | Cel. (41) 99155-0082
""",
            html=True,
        ),
        esperado={
            "jornalista": Contem("Luciana Hartmann"),
            "veiculo": "Revista Segurança em Foco",
            "contato": UmDe(
                Contem("3029-4410"), Contem("99155-0082"),
                Contem("luciana.hartmann@segurancaemfoco.com.br"),
            ),
            "pedido": Contem("NUCIBER"),
            "data": "2026-11-24",
            "horario": "10:58",
            "deadline": "2026-12-04",
        },
        nota="Prazo explícito 04/12; 'edição de dezembro' não é data.",
    ),
    # ------------------------------------------------------------------ 027
    Caso(
        id="imp-027",
        modulo=_M,
        formato="eml",
        agora="2026-11-25 17:30",
        texto=_eml(
            "Thiago <thiagorep@tviguacu8.com.br>",
            _ASCOM,
            "Re: Re: sonora",
            "2026-11-25 17:12",
            """
blz, obrigado pelo retorno. então fica pra amanhã até meio-dia a sonora do
delegado sobre o tráfico na ponte da amizade, pode ser?

Thiago
TV Iguaçu Canal 8
Enviado do meu iPhone

Em 25/11/2026 15:03, Imprensa PCPR <imprensa@pc.pr.gov.br> escreveu:
> Olá, Thiago. O delegado está em diligência hoje; conseguimos amanhã.
""",
        ),
        esperado={
            "jornalista": Contem("Thiago"),
            "veiculo": "TV Iguaçu Canal 8",
            "contato": Contem("thiagorep@tviguacu8.com.br"),
            "pedido": Contem("sonora do delegado"),
            "data": "2026-11-25",
            "horario": "17:12",
            "deadline": "2026-11-26",
        },
        nota="Horário 15:03 é da resposta da ASCOM citada; o pedido é das 17:12. Só primeiro nome.",
    ),
    # ------------------------------------------------------------------ 028
    Caso(
        id="imp-028",
        modulo=_M,
        formato="texto",
        agora="2026-11-26 13:00",
        texto="""
Boa tarde, meu nome é Rosângela Pires, trabalho no Jornal O Correio Cascavelense.
Gostaria de saber se a Polícia Civil já tem o laudo sobre a causa da morte da
jovem encontrada no Lago Municipal no dia 20. Estamos fechando para sábado.
Telefone: (45) 99967-3308
""",
        esperado={
            "jornalista": Contem("Rosângela Pires"),
            "veiculo": AUSENTE,
            "veiculo_novo": Contem("O Correio Cascavelense"),
            "contato": Contem("99967-3308"),
            "pedido": Contem("laudo"),
            "deadline": "2026-11-28",
        },
        nota="'Dia 20' é a data do fato; 'fechando para sábado' a partir de quinta 26/11 = 28/11.",
    ),
    # ------------------------------------------------------------------ 029
    Caso(
        id="imp-029",
        modulo=_M,
        formato="eml",
        agora="2026-11-30 09:30",
        texto=_eml(
            "Ricardo Bassani <ricardo.bassani@radioplanalto98.com.br>",
            _ASCOM,
            "entrevista delegado - operação verão",
            "2026-11-30 09:02",
            """
Bom dia, equipe.

Gostaríamos de entrevistar, ao vivo, o delegado que vai coordenar a Operação
Verão no litoral, que começa em 18/12. A entrevista seria no nosso programa
de sexta, dia 4, às 11h.

Ricardo Bassani
Rádio Planalto 98 FM
""",
        ),
        esperado={
            "jornalista": Contem("Ricardo Bassani"),
            "veiculo": "Rádio Planalto 98 FM",
            "contato": Contem("ricardo.bassani@radioplanalto98.com.br"),
            "pedido": Contem("Operação Verão"),
            "data": "2026-11-30",
            "horario": "09:02",
            "deadline": "2026-12-04",
        },
        nota="18/12 é o início da operação (fato); a veiculação é sexta 04/12.",
    ),
    # ------------------------------------------------------------------ 030
    Caso(
        id="imp-030",
        modulo=_M,
        formato="eml",
        agora="2026-12-01 16:00",
        texto=_eml(
            "Débora Lins <debora.lins@tvlitoralpr.com.br>",
            _ASCOM,
            _q("Pedido de informações — afogamento? não, homicídio em Matinhos"),
            "2026-12-01 15:41",
            """
Oi, pessoal!

Surgiu a informação de que o corpo encontrado na praia de Caiobá no domingo
tinha marcas de tiro. A Polícia Civil confirma que o caso é investigado
como homicídio? Tem algum suspeito?

Preciso da resposta até as 17h30.

Débora Lins | Repórter | TV Litoral Paranaense | (41) 99701-4492
""",
        ),
        esperado={
            "jornalista": Contem("Débora Lins"),
            "veiculo": "TV Litoral Paranaense",
            "contato": UmDe(Contem("99701-4492"), Contem("debora.lins@tvlitoralpr.com.br")),
            "pedido": Contem("investigado como homicídio"),
            "data": "2026-12-01",
            "horario": "15:41",
            "deadline": "2026-12-01",
        },
        nota="'Domingo' é quando o corpo foi achado; prazo hoje às 17h30.",
    ),
    # ------------------------------------------------------------------ 031
    Caso(
        id="imp-031",
        modulo=_M,
        formato="texto",
        agora="2026-12-02 10:15",
        texto="""
De: Assessoria de Comunicação - 3ª SDP <comunicacao.3sdp@pc.pr.gov.br>
Enviado em: quarta-feira, 2 de dezembro de 2026 10:05
Para: Imprensa PCPR
Assunto: ENC: pedido de entrevista

Colegas, encaminho pedido que chegou na delegacia de Ponta Grossa.

De: Wellington Bortolotto <wellington.b@tribunapg.com.br>
Enviado em: quarta-feira, 2 de dezembro de 2026 08:37
Para: Delegacia de Ponta Grossa
Assunto: pedido de entrevista

Bom dia. Sou do Jornal Tribuna Ponta-grossense e gostaria de entrevistar o
delegado sobre o golpe do bilhete premiado aplicado em idosos no centro.
Preciso até amanhã às 12h.

Wellington Bortolotto
""",
        esperado={
            "jornalista": Contem("Wellington Bortolotto"),
            "veiculo": "Jornal Tribuna Ponta-grossense",
            "contato": Contem("wellington.b@tribunapg.com.br"),
            "pedido": Contem("bilhete premiado"),
            "data": "2026-12-02",
            "horario": UmDe("08:37", "10:05"),
            "deadline": "2026-12-03",
        },
        nota="Encaminhado pela 3ª SDP: jornalista/contato são os do pedido original, não da unidade.",
    ),
    # ------------------------------------------------------------------ 032
    Caso(
        id="imp-032",
        modulo=_M,
        formato="eml",
        agora="2026-12-03 07:45",
        texto=_eml(
            "Nathalia Pacheco <nathalia.pacheco@curitibaempauta.com.br>",
            _ASCOM,
            "Pedido de dados: roubos a pedestres no Centro",
            "2026-12-03 00:17",
            """
Oi, gente, desculpem o horário!

Estou fechando uma matéria sobre roubos a pedestres no Centro de Curitiba e
precisaria do número de boletins registrados em novembro, comparado com
novembro de 2025. Preciso até as 10h de hoje.

Nathalia Pacheco
Portal Curitiba em Pauta
""",
        ),
        esperado={
            "jornalista": Contem("Nathalia Pacheco"),
            "veiculo": "Portal Curitiba em Pauta",
            "contato": Contem("nathalia.pacheco@curitibaempauta.com.br"),
            "pedido": Contem("roubos a pedestres"),
            "data": "2026-12-03",
            "horario": "00:17",
            "deadline": "2026-12-03",
        },
        nota="Enviado 00:17: 'hoje' já é 03/12 (não 02/12).",
    ),
    # ------------------------------------------------------------------ 033
    Caso(
        id="imp-033",
        modulo=_M,
        formato="eml",
        agora="2026-12-04 14:00",
        texto=_eml(
            "Eduardo Guimarães <eduardo.guimaraes@folhanortepioneiro.com.br>",
            _ASCOM,
            "Solicitação de posicionamento",
            "2026-12-04 13:33",
            """
Boa tarde.

A matéria da TV Paraná Sul de ontem afirmou que o inquérito sobre o
desvio de merenda em Jacarezinho foi arquivado. A PCPR confirma? Gostaria
de um posicionamento para a edição impressa de sábado.

Eduardo Guimarães
Folha do Norte Pioneiro
""",
        ),
        esperado={
            "jornalista": Contem("Eduardo Guimarães"),
            "veiculo": "Folha do Norte Pioneiro",
            "contato": Contem("eduardo.guimaraes@folhanortepioneiro.com.br"),
            "pedido": Contem("posicionamento"),
            "data": "2026-12-04",
            "horario": "13:33",
            "deadline": "2026-12-05",
        },
        nota="Cita outro veículo (TV Paraná Sul) só como referência; edição de sábado = 05/12.",
    ),
    # ------------------------------------------------------------------ 034
    Caso(
        id="imp-034",
        modulo=_M,
        formato="texto",
        agora="2026-12-07 09:20",
        texto="""
[07/12/2026 09:03] Kelly Educadora: Bom diaaa
[07/12/2026 09:04] Kelly Educadora: Kelly Ramalho, Rádio Educadora AM. Tem alguém pra falar sobre o balanço do Natal Seguro? Queremos gravar entrevista até quinta
""",
        esperado={
            "jornalista": Contem("Kelly Ramalho"),
            "veiculo": "Rádio Educadora AM",
            "pedido": Contem("Natal Seguro"),
            "data": "2026-12-07",
            "horario": "09:04",
            "deadline": "2026-12-10",
        },
        nota="'Até quinta' numa segunda 07/12 = 10/12; Natal não é data do prazo.",
    ),
    # ------------------------------------------------------------------ 035
    Caso(
        id="imp-035",
        modulo=_M,
        formato="eml",
        agora="2026-12-08 11:30",
        texto=_eml(
            "Paulo Henrique Sá <ph.sa@tvparanasul.com.br>",
            _ASCOM,
            _q("Pedido de imagens — apreensão recorde de drogas em Guaíra"),
            "2026-12-08 11:04",
            """
Bom dia!

Solicito as imagens da apreensão de 3 toneladas de maconha em Guaíra
(vídeo bruto e fotos). Vamos exibir no jornal do meio-dia de amanhã.

Paulo Henrique Sá
Repórter cinematográfico | TV Paraná Sul
""",
            html=True,
        ),
        esperado={
            "jornalista": Contem("Paulo Henrique Sá"),
            "veiculo": "TV Paraná Sul",
            "contato": Contem("ph.sa@tvparanasul.com.br"),
            "pedido": Contem("imagens da apreensão"),
            "data": "2026-12-08",
            "horario": "11:04",
            "deadline": "2026-12-09",
        },
        nota="'Jornal do meio-dia de amanhã' → veiculação 09/12.",
    ),
    # ------------------------------------------------------------------ 036
    Caso(
        id="imp-036",
        modulo=_M,
        formato="eml",
        agora="2026-12-09 16:10",
        texto=_eml(
            "Marina Kowalski <marina.kowalski@gmail.com>",
            _ASCOM,
            "pedido de entrevista",
            "2026-12-09 15:48",
            """
Olá, boa tarde

Sou jornalista freelancer e estou produzindo um documentário independente
sobre desaparecidos no Paraná. Gostaria de entrevistar alguém da Delegacia
de Pessoas Desaparecidas. Não tenho prazo fechado, quando for possível.

MARINA KOWALSKI
Jornalista - MTB 0099/PR
""",
        ),
        esperado={
            "jornalista": Contem("Marina Kowalski"),
            "veiculo": AUSENTE,
            "contato": Contem("marina.kowalski@gmail.com"),
            "pedido": Contem("Pessoas Desaparecidas"),
            "data": "2026-12-09",
            "horario": "15:48",
            "deadline": AUSENTE,
        },
        nota="Freelancer sem veículo: não inventar; 'sem prazo fechado' → deadline AUSENTE.",
    ),
    # ------------------------------------------------------------------ 037
    Caso(
        id="imp-037",
        modulo=_M,
        formato="eml",
        agora="2026-12-10 10:20",
        texto=_eml(
            "Sérgio Mazur <sergio.mazur@radiovaledoribeira.com.br>",
            _ASCOM,
            "Confirmação de prisão - Adrianópolis",
            "2026-12-10 10:01",
            """
Bom dia.

A PC confirma a prisão, ontem (09/12), do suspeito de matar o agricultor em
Adrianópolis em agosto? Entro no ar às 12h de hoje com a notícia.

Sérgio Mazur
Rádio Vale do Ribeira FM
Fone/WhatsApp (41) 99433-1287
""",
        ),
        esperado={
            "jornalista": Contem("Sérgio Mazur"),
            "veiculo": "Rádio Vale do Ribeira FM",
            "contato": UmDe(Contem("99433-1287"), Contem("sergio.mazur@radiovaledoribeira.com.br")),
            "pedido": Contem("confirma a prisão"),
            "data": "2026-12-10",
            "horario": "10:01",
            "deadline": "2026-12-10",
        },
        nota="09/12 (prisão) e agosto (crime) são fatos; entra no ar hoje às 12h.",
    ),
    # ------------------------------------------------------------------ 038
    Caso(
        id="imp-038",
        modulo=_M,
        formato="texto",
        agora="2026-12-11 08:30",
        texto="""
Enviado do meu Android

-------- Mensagem original --------
De: Anderson Klein <anderson.klein@diariodooeste.com.br>
Data: 11/12/2026 07:55
Para: imprensa@pc.pr.gov.br
Assunto: nota - ataque a posto em Foz

Bom dia, solicito nota sobre o assalto ao posto de combustíveis na Av. das
Cataratas nesta madrugada. Fechamento do online até as 10h.

Anderson Klein - Diário do Oeste
""",
        esperado={
            "jornalista": Contem("Anderson Klein"),
            "veiculo": "Jornal Diário do Oeste",
            "contato": Contem("anderson.klein@diariodooeste.com.br"),
            "pedido": Contem("assalto ao posto"),
            "data": "2026-12-11",
            "horario": "07:55",
            "deadline": "2026-12-11",
        },
        nota="Veículo abreviado ('Diário do Oeste') casa com o cadastro; 'Enviado do meu Android' no topo.",
    ),
    # ------------------------------------------------------------------ 039
    Caso(
        id="imp-039",
        modulo=_M,
        formato="eml",
        agora="2026-12-14 09:10",
        texto=_eml(
            "Isabela Cordeiro <isabela.cordeiro@agenciapinhao.com.br>",
            _ASCOM,
            "Dados - feminicídios 2026",
            "2026-12-14 08:49",
            """
Bom dia, equipe da assessoria!

Estamos preparando a retrospectiva 2026 e precisamos do número de
feminicídios registrados no Paraná de janeiro a novembro, por região.
O prazo é até o dia 18, porque a retrospectiva vai ao ar em 28/12.

Obrigada!
Isabela Cordeiro
Agência Pinhão de Notícias
""",
        ),
        esperado={
            "jornalista": Contem("Isabela Cordeiro"),
            "veiculo": "Agência Pinhão de Notícias",
            "contato": Contem("isabela.cordeiro@agenciapinhao.com.br"),
            "pedido": Contem("feminicídios"),
            "data": "2026-12-14",
            "horario": "08:49",
            "deadline": "2026-12-18",
        },
        nota="Dois dias: prazo de entrega 18/12 (é o que o jornalista pede) e veiculação 28/12.",
    ),
    # ------------------------------------------------------------------ 040
    Caso(
        id="imp-040",
        modulo=_M,
        formato="eml",
        agora="2026-12-15 13:40",
        texto=_eml(
            "Assessoria Portal Notícias Já <assessoria@portalnoticiasja.com.br>",
            _ASCOM,
            "Pedido do repórter Leandro Cunha",
            "2026-12-15 13:15",
            """
Boa tarde.

O repórter Leandro Cunha precisa de uma nota da PCPR sobre a investigação
do incêndio no barracão de recicláveis em Piraquara. Por favor, respondam
diretamente para ele: leandro.cunha@portalnoticiasja.com.br.

Prazo: até as 17h.

Assessoria de Comunicação
Portal Notícias Já
""",
        ),
        esperado={
            "jornalista": Contem("Leandro Cunha"),
            "veiculo": "Portal Notícias Já",
            "contato": Contem("leandro.cunha@portalnoticiasja.com.br"),
            "pedido": Contem("incêndio no barracão"),
            "data": "2026-12-15",
            "horario": "13:15",
            "deadline": "2026-12-15",
        },
        nota="Escrito pela assessoria do veículo: contato é o e-mail do repórter, não o do From.",
    ),
    # ------------------------------------------------------------------ 041
    Caso(
        id="imp-041",
        modulo=_M,
        formato="texto",
        agora="2026-08-03 11:00",
        texto="""
[03/08/2026 10:37] Fabiano Rádio Cidade: Bom dia! Fabiano Teles, da Rádio Cidade FM
[03/08/2026 10:38] Fabiano Rádio Cidade: Queria uma entrevista com o delegado sobre os roubos de celular no terminal do Pinheirinho. Consegue até 16:30 de hoje?
""",
        esperado={
            "jornalista": Contem("Fabiano Teles"),
            "veiculo": "Rádio Cidade FM",
            "pedido": Contem("roubos de celular"),
            "data": "2026-08-03",
            "horario": UmDe("10:37", "10:38"),
            "deadline": "2026-08-03",
        },
        nota="16:30 é prazo (hoje), não horário do pedido.",
    ),
    # ------------------------------------------------------------------ 042
    Caso(
        id="imp-042",
        modulo=_M,
        formato="eml",
        agora="2026-08-04 10:30",
        texto=_eml(
            "Cristiano Balbinot <cristiano.balbinot@diariodooeste.com.br>",
            _ASCOM,
            "Solicitação de dados - apreensão de armas no Oeste",
            "2026-08-04 10:12",
            """
Prezados,

Solicito o número de armas de fogo apreendidas pela Polícia Civil nas
regiões de Cascavel, Toledo e Foz do Iguaçu no primeiro semestre de 2026.

Prazo: 07/08.

Cristiano Balbinot
Jornal Diário do Oeste
(45) 99811-0923
""",
        ),
        esperado={
            "jornalista": Contem("Cristiano Balbinot"),
            "veiculo": "Jornal Diário do Oeste",
            "contato": UmDe(Contem("99811-0923"), Contem("cristiano.balbinot@diariodooeste.com.br")),
            "pedido": Contem("armas de fogo apreendidas"),
            "data": "2026-08-04",
            "horario": "10:12",
            "deadline": "2026-08-07",
        },
        nota="Prazo em dd/mm sem ano: o ano vem do e-mail (2026).",
    ),
    # ------------------------------------------------------------------ 043
    Caso(
        id="imp-043",
        modulo=_M,
        formato="texto",
        agora="2026-08-05 15:20",
        texto="""
Oi, é o Gustavo da TV Litoral Paranaense. Vocês têm imagens da prisão do
foragido lá em Pontal do Paraná? Se conseguir mandar o quanto antes ajuda
muito. Meu cel: (41) 99620-3317
""",
        esperado={
            "jornalista": Contem("Gustavo"),
            "veiculo": "TV Litoral Paranaense",
            "contato": Contem("99620-3317"),
            "pedido": Contem("imagens da prisão"),
            "deadline": AUSENTE,
        },
        nota="Só primeiro nome; 'o quanto antes' → sem deadline; texto sem data do pedido.",
    ),
    # ------------------------------------------------------------------ 044
    Caso(
        id="imp-044",
        modulo=_M,
        formato="eml",
        agora="2026-08-06 17:10",
        texto=_eml(
            "Bianca Loures <bianca.loures@curitibaempauta.com.br>",
            _ASCOM,
            _q("Nota oficial — policial civil preso em operação do GAECO"),
            "2026-08-06 16:55",
            """
Boa tarde,

Solicito nota oficial da Polícia Civil do Paraná sobre a prisão de um
investigador lotado em Curitiba durante operação do Ministério Público nesta
quinta-feira. A corporação vai instaurar procedimento administrativo?

Publicamos às 19h.

Bianca Loures
Portal Curitiba em Pauta
""",
            html=True,
        ),
        esperado={
            "jornalista": Contem("Bianca Loures"),
            "veiculo": "Portal Curitiba em Pauta",
            "contato": Contem("bianca.loures@curitibaempauta.com.br"),
            "pedido": Contem("nota oficial"),
            "data": "2026-08-06",
            "horario": "16:55",
            "deadline": "2026-08-06",
        },
        nota="'Nesta quinta-feira' é o dia do fato (e coincide com hoje); publica às 19h de hoje.",
    ),
    # ------------------------------------------------------------------ 045
    Caso(
        id="imp-045",
        modulo=_M,
        formato="texto",
        agora="2026-08-07 10:00",
        texto="""
De: Aline Takahashi <aline.takahashi@folhanortepioneiro.com.br>
Enviado em: sexta-feira, 7 de agosto de 2026 09:30
Para: imprensa@pc.pr.gov.br
Assunto: Entrevista - delegado de Cornélio Procópio

Bom dia! Gostaria de entrevistar o delegado de Cornélio Procópio sobre a
série de arrombamentos a lojas no centro. Precisamos para segunda às 10h.

Aline Takahashi
Folha do Norte Pioneiro | (43) 99304-7781
""",
        esperado={
            "jornalista": Contem("Aline Takahashi"),
            "veiculo": "Folha do Norte Pioneiro",
            "contato": UmDe(Contem("99304-7781"), Contem("aline.takahashi@folhanortepioneiro.com.br")),
            "pedido": Contem("arrombamentos"),
            "data": "2026-08-07",
            "horario": "09:30",
            "deadline": "2026-08-10",
        },
        nota="'Segunda às 10h' a partir de sexta 07/08 = 10/08.",
    ),
    # ------------------------------------------------------------------ 046
    Caso(
        id="imp-046",
        modulo=_M,
        formato="eml",
        agora="2026-08-10 11:30",
        texto=_eml(
            "Rodrigo Estevam <rodrigo.estevam@tvserraverde.com.br>",
            _ASCOM,
            "sonora - homicídio em Telêmaco Borba",
            "2026-08-10 11:02",
            """
Bom dia, sou repórter da TV Serra Verde, de Telêmaco Borba.
Preciso de uma sonora do delegado sobre o homicídio do comerciante no
sábado (08/08). Até o fim do dia está ótimo.

Rodrigo Estevam
TV Serra Verde
""",
        ),
        esperado={
            "jornalista": Contem("Rodrigo Estevam"),
            "veiculo": AUSENTE,
            "veiculo_novo": Contem("TV Serra Verde"),
            "contato": Contem("rodrigo.estevam@tvserraverde.com.br"),
            "pedido": Contem("sonora do delegado"),
            "data": "2026-08-10",
            "horario": "11:02",
            "deadline": "2026-08-10",
        },
        nota="TV fora do cadastro; 08/08 é o dia do crime; 'fim do dia' = 10/08.",
    ),
    # ------------------------------------------------------------------ 047
    Caso(
        id="imp-047",
        modulo=_M,
        formato="texto",
        agora="2026-08-12 19:55",
        texto="""
[12/08/2026 19:40] +55 44 99288-6120: Boa noite! Sou Leonardo Paixão, Rádio Planalto 98 FM
[12/08/2026 19:41] +55 44 99288-6120: A PC confirma a prisão do vereador de Umuarama? Nosso fechamento é às 21h
""",
        esperado={
            "jornalista": Contem("Leonardo Paixão"),
            "veiculo": "Rádio Planalto 98 FM",
            "contato": Contem("99288-6120"),
            "pedido": Contem("confirma a prisão"),
            "data": "2026-08-12",
            "horario": UmDe("19:40", "19:41"),
            "deadline": "2026-08-12",
        },
        nota="Fechamento às 21h = hoje; horário do pedido é 19:4x.",
    ),
    # ------------------------------------------------------------------ 048
    Caso(
        id="imp-048",
        modulo=_M,
        formato="eml",
        agora="2026-08-14 08:30",
        texto=_eml(
            "Jéssica Baldo <jessica.baldo@tviguacu8.com.br>",
            _ASCOM,
            "Agendamento de entrevista - tráfico de pessoas",
            "2026-08-14 08:05",
            """
Bom dia!

Gostaria de agendar uma entrevista com a delegada responsável pela
investigação de tráfico de pessoas na fronteira. A gravação seria na terça (18),
em Foz do Iguaçu, em qualquer horário.

Jéssica Baldo | Repórter | TV Iguaçu Canal 8 | (45) 99140-2208
""",
        ),
        esperado={
            "jornalista": Contem("Jéssica Baldo"),
            "veiculo": "TV Iguaçu Canal 8",
            "contato": UmDe(Contem("99140-2208"), Contem("jessica.baldo@tviguacu8.com.br")),
            "pedido": Contem("tráfico de pessoas"),
            "data": "2026-08-14",
            "horario": "08:05",
            "deadline": "2026-08-18",
        },
        nota="Gravação terça (18) → 18/08.",
    ),
    # ------------------------------------------------------------------ 049
    Caso(
        id="imp-049",
        modulo=_M,
        formato="texto",
        agora="2026-08-17 14:00",
        texto="""
Prezados, aqui é Valéria Munhoz, editora da Revista Segurança em Foco.
Solicito dados sobre o efetivo de delegadas mulheres na Polícia Civil do
Paraná e o número de delegacias chefiadas por elas. Prazo até dia 25 deste mês.
valeria.munhoz@segurancaemfoco.com.br
""",
        esperado={
            "jornalista": Contem("Valéria Munhoz"),
            "veiculo": "Revista Segurança em Foco",
            "contato": Contem("valeria.munhoz@segurancaemfoco.com.br"),
            "pedido": Contem("delegadas mulheres"),
            "deadline": "2026-08-25",
        },
        nota="'Dia 25 deste mês' pelo 'agora' (agosto) = 25/08.",
    ),
    # ------------------------------------------------------------------ 050
    Caso(
        id="imp-050",
        modulo=_M,
        formato="eml",
        agora="2026-08-19 15:00",
        texto=_eml(
            "Mônica Dziedzic <monica.dziedzic@gazetadoscampos.com.br>",
            _ASCOM,
            "Pedido de entrevista e fotos",
            "2026-08-19 14:31",
            """
Boa tarde!

Eu e o fotógrafo Caio Ramos gostaríamos de acompanhar o plantão da
delegacia de Ponta Grossa por algumas horas para uma reportagem especial,
com entrevista com o delegado de plantão e fotos.

Preciso da confirmação amanhã até as 9h.

Mônica Dziedzic
Gazeta dos Campos
""",
        ),
        esperado={
            "jornalista": Contem("Mônica Dziedzic"),
            "veiculo": "Gazeta dos Campos",
            "contato": Contem("monica.dziedzic@gazetadoscampos.com.br"),
            "pedido": Contem("acompanhar o plantão"),
            "data": "2026-08-19",
            "horario": "14:31",
            "deadline": "2026-08-20",
        },
        nota="O fotógrafo citado não é o jornalista que pede; confirmação amanhã (20/08).",
    ),
    # ------------------------------------------------------------------ 051
    Caso(
        id="imp-051",
        modulo=_M,
        formato="eml",
        agora="2026-08-21 18:45",
        texto=_eml(
            "Neide Carvalho <neide.carvalho@educadoraam.com.br>",
            _ASCOM,
            "entrevista programa de segunda",
            "2026-08-21 18:30",
            """
Boa noite!

Gostaríamos de uma entrevista com o delegado sobre a prevenção a golpes
contra aposentados. Pode me responder até segunda de manhã? O programa
é na segunda mesmo.

Neide Carvalho
Rádio Educadora AM
""",
            html=True,
        ),
        esperado={
            "jornalista": Contem("Neide Carvalho"),
            "veiculo": "Rádio Educadora AM",
            "contato": Contem("neide.carvalho@educadoraam.com.br"),
            "pedido": Contem("golpes contra aposentados"),
            "data": "2026-08-21",
            "horario": "18:30",
            "deadline": "2026-08-24",
        },
        nota="'Segunda de manhã' a partir de sexta 21/08 = 24/08 (sem horário inventado).",
    ),
    # ------------------------------------------------------------------ 052
    Caso(
        id="imp-052",
        modulo=_M,
        formato="texto",
        agora="2026-08-24 11:00",
        texto="""
De: CLÁUDIO REMPEL <claudio.rempel@tribunapg.com.br>
Enviado em: segunda-feira, 24 de agosto de 2026 10:22
Para: Imprensa PCPR <imprensa@pc.pr.gov.br>
Cc: Pauta Tribuna <pauta@tribunapg.com.br>
Assunto: ENTREVISTA - DELEGADO DE CASTRO

BOM DIA. SOLICITO ENTREVISTA COM O DELEGADO DE CASTRO SOBRE O DESAPARECIMENTO
DA ADOLESCENTE NO DISTRITO DE ABAPÃ. PRECISO ATÉ AS 16H.

CLÁUDIO REMPEL
JORNAL TRIBUNA PONTA-GROSSENSE
""",
        esperado={
            "jornalista": Contem("Cláudio Rempel"),
            "veiculo": "Jornal Tribuna Ponta-grossense",
            "contato": Contem("claudio.rempel@tribunapg.com.br"),
            "pedido": Contem("desaparecimento da adolescente"),
            "data": "2026-08-24",
            "horario": "10:22",
            "deadline": "2026-08-24",
        },
        nota="Tudo em CAIXA ALTA; o Cc da pauta não é o contato do jornalista.",
    ),
    # ------------------------------------------------------------------ 053
    Caso(
        id="imp-053",
        modulo=_M,
        formato="eml",
        agora="2026-08-26 09:30",
        texto=_eml(
            "Felipe Arruda <felipe.arruda@portalnoticiasja.com.br>",
            _ASCOM,
            "pedido - estatística de latrocínios",
            "2026-08-26 09:11",
            """
Oi, bom dia!

Vocês têm a estatística de latrocínios na Região Metropolitana de Curitiba
nos últimos cinco anos? É para uma pauta fria, sem pressa.

Felipe Arruda
Portal Notícias Já
""",
        ),
        esperado={
            "jornalista": Contem("Felipe Arruda"),
            "veiculo": "Portal Notícias Já",
            "contato": Contem("felipe.arruda@portalnoticiasja.com.br"),
            "pedido": Contem("latrocínios"),
            "data": "2026-08-26",
            "horario": "09:11",
            "deadline": AUSENTE,
        },
        nota="'Sem pressa' → sem deadline.",
    ),
    # ------------------------------------------------------------------ 054
    Caso(
        id="imp-054",
        modulo=_M,
        formato="texto",
        agora="2026-08-28 13:20",
        texto="""
[28/08/2026 13:02] Lu Brandt: oi! aqui é a Luana, da TV Iguaçu Canal 8
[28/08/2026 13:03] Lu Brandt: vcs conseguem o vídeo da recaptura do preso que fugiu do hospital? vai ao ar hoje no jornal da noite
""",
        esperado={
            "jornalista": Contem("Luana"),
            "veiculo": "TV Iguaçu Canal 8",
            "pedido": Contem("vídeo da recaptura"),
            "data": "2026-08-28",
            "horario": UmDe("13:02", "13:03"),
            "deadline": "2026-08-28",
        },
        nota="Veiculação hoje no jornal da noite → deadline 28/08.",
    ),
    # ------------------------------------------------------------------ 055
    Caso(
        id="imp-055",
        modulo=_M,
        formato="eml",
        agora="2026-09-01 10:00",
        texto=_eml(
            "Débora Nishimura <debora.nishimura@agenciapinhao.com.br>",
            _ASCOM,
            _q("Dados — roubos de carga nas rodovias estaduais"),
            "2026-09-01 09:26",
            """
Bom dia.

Solicito o número de inquéritos de roubo de carga instaurados em 2026 e
quantos resultaram em prisões. Consegue até 5/9?

Débora Nishimura
Agência Pinhão de Notícias
""",
        ),
        esperado={
            "jornalista": Contem("Débora Nishimura"),
            "veiculo": "Agência Pinhão de Notícias",
            "contato": Contem("debora.nishimura@agenciapinhao.com.br"),
            "pedido": Contem("roubo de carga"),
            "data": "2026-09-01",
            "horario": "09:26",
            "deadline": "2026-09-05",
        },
        nota="'5/9' sem zero e sem ano = 05/09/2026.",
    ),
    # ------------------------------------------------------------------ 056
    Caso(
        id="imp-056",
        modulo=_M,
        formato="texto",
        agora="2026-09-02 12:00",
        texto="""
De: Wagner Lopes <wagner.lopes@radiocidadefm.com.br>
Enviado em: quarta-feira, 2 de setembro de 2026 11:40
Para: imprensa@pc.pr.gov.br
Assunto: Coluna de domingo - entrevista

Olá!

Além da rádio, assino uma coluna no Portal Notícias Já, e é para ela este
pedido: uma entrevista curta com o delegado-geral sobre o concurso de
investigadores. Preciso até sexta.

Wagner Lopes
Repórter da Rádio Cidade FM | Colunista do Portal Notícias Já
""",
        esperado={
            "jornalista": Contem("Wagner Lopes"),
            "veiculo": "Portal Notícias Já",
            "contato": Contem("wagner.lopes@radiocidadefm.com.br"),
            "pedido": Contem("concurso de investigadores"),
            "data": "2026-09-02",
            "horario": "11:40",
            "deadline": "2026-09-04",
        },
        nota="Assinatura com dois veículos; o pedido é para a coluna do Portal. 'Coluna de domingo' não é o prazo (sexta 04/09).",
    ),
    # ------------------------------------------------------------------ 057
    Caso(
        id="imp-057",
        modulo=_M,
        formato="texto",
        agora="2026-09-03 11:00",
        texto="""
preciso nota sobre o caso da creche em colombo pra hj 15h
Bia - Radio Cidade FM 41 99123-4488
""",
        esperado={
            "jornalista": Contem("Bia"),
            "veiculo": "Rádio Cidade FM",
            "contato": Contem("99123-4488"),
            "pedido": Contem("creche"),
            "deadline": "2026-09-03",
        },
        nota="Duas linhas mal escritas; 'hj 15h' é prazo pelo 'agora'.",
    ),
    # ------------------------------------------------------------------ 058
    Caso(
        id="imp-058",
        modulo=_M,
        formato="eml",
        agora="2026-09-04 17:20",
        texto=_eml(
            "Rafaela Schmidt <rafaela.schmidt@tribunapg.com.br>",
            _ASCOM,
            "Pedido de posicionamento - agressão em escola",
            "2026-09-04 17:05",
            """
Boa tarde,

Solicito posicionamento da Polícia Civil sobre a agressão a uma professora
em escola de Carambeí, registrada ontem. A pauta é para a edição de
segunda-feira.

Rafaela Schmidt
Jornal Tribuna Ponta-grossense
(42) 99812-0034

Enviado do meu Android
""",
        ),
        esperado={
            "jornalista": Contem("Rafaela Schmidt"),
            "veiculo": "Jornal Tribuna Ponta-grossense",
            "contato": UmDe(Contem("99812-0034"), Contem("rafaela.schmidt@tribunapg.com.br")),
            "pedido": Contem("agressão a uma professora"),
            "data": "2026-09-04",
            "horario": "17:05",
            "deadline": "2026-09-07",
        },
        nota="Edição de segunda a partir de sexta 04/09 = 07/09; 'ontem' é o fato.",
    ),
    # ------------------------------------------------------------------ 059
    Caso(
        id="imp-059",
        modulo=_M,
        formato="texto",
        agora="2026-09-08 09:30",
        texto="""
De: Tânia Wosniak <tania.wosniak@tvlitoralpr.com.br>
Enviado em: terça-feira, 8 de setembro de 2026 09:12
Para: Imprensa PCPR
Assunto: RES: entrevista Guaratuba

Bom dia! Retomando nossa conversa por telefone: queremos a entrevista com
o delegado de Guaratuba sobre as invasões a casas de veraneio até
quinta, 10/09.

Tânia Wosniak
TV Litoral Paranaense
""",
        esperado={
            "jornalista": Contem("Tânia Wosniak"),
            "veiculo": "TV Litoral Paranaense",
            "contato": Contem("tania.wosniak@tvlitoralpr.com.br"),
            "pedido": Contem("casas de veraneio"),
            "data": "2026-09-08",
            "horario": "09:12",
            "deadline": "2026-09-10",
        },
        nota="Prazo com dia da semana e data concordantes (quinta 10/09).",
    ),
    # ------------------------------------------------------------------ 060
    Caso(
        id="imp-060",
        modulo=_M,
        formato="eml",
        agora="2026-09-09 12:10",
        texto=_eml(
            "Otília Saraiva <otilia.saraiva@radiovaledoribeira.com.br>",
            _ASCOM,
            "urgente - sonora",
            "2026-09-09 12:00",
            """
Boa tarde! Preciso de uma sonora rápida sobre o acidente com a viatura em
Adrianópolis. Nosso jornal é às 13h, então até as 13h.

Otília Saraiva | Rádio Vale do Ribeira FM
""",
            html=True,
        ),
        esperado={
            "jornalista": Contem("Otília Saraiva"),
            "veiculo": "Rádio Vale do Ribeira FM",
            "contato": Contem("otilia.saraiva@radiovaledoribeira.com.br"),
            "pedido": Contem("sonora"),
            "data": "2026-09-09",
            "horario": "12:00",
            "deadline": "2026-09-09",
        },
        nota="Pedido às 12:00 com prazo 13h: não trocar um pelo outro.",
    ),
    # ------------------------------------------------------------------ 061
    Caso(
        id="imp-061",
        modulo=_M,
        formato="texto",
        agora="2026-09-10 15:00",
        texto="""
[10/09/2026 14:20] Nathalia Curitiba em Pauta: Oi! Nathalia Pacheco, do Portal Curitiba em Pauta
[10/09/2026 14:21] Nathalia Curitiba em Pauta: Tem fotos da apreensão de celulares no presídio? O quanto antes
[10/09/2026 14:35] Nathalia Curitiba em Pauta: Até as 18h no máximo, depois disso não consigo usar
""",
        esperado={
            "jornalista": Contem("Nathalia Pacheco"),
            "veiculo": "Portal Curitiba em Pauta",
            "pedido": Contem("fotos da apreensão"),
            "data": "2026-09-10",
            "horario": UmDe("14:20", "14:21"),
            "deadline": "2026-09-10",
        },
        nota="'O quanto antes' seguido de prazo concreto (18h de hoje): vale o concreto.",
    ),
    # ------------------------------------------------------------------ 062
    Caso(
        id="imp-062",
        modulo=_M,
        formato="eml",
        agora="2026-09-11 10:00",
        texto=_eml(
            "Mariângela Toffoli <mariangela.toffoli@folhanortepioneiro.com.br>",
            _ASCOM,
            _q("Solicitação — estatísticas de furtos em propriedades rurais"),
            "2026-09-11 09:44",
            """
Bom dia, equipe.

Solicito as estatísticas de furtos em propriedades rurais nos municípios do
Norte Pioneiro em 2025 e 2026. Prazo: próxima quarta.

Mariângela Toffoli
Folha do Norte Pioneiro
""",
            html=True,
        ),
        esperado={
            "jornalista": Contem("Mariângela Toffoli"),
            "veiculo": "Folha do Norte Pioneiro",
            "contato": Contem("mariangela.toffoli@folhanortepioneiro.com.br"),
            "pedido": Contem("propriedades rurais"),
            "data": "2026-09-11",
            "horario": "09:44",
            "deadline": "2026-09-16",
        },
        nota="'Próxima quarta' a partir de sexta 11/09 = 16/09.",
    ),
    # ------------------------------------------------------------------ 063
    Caso(
        id="imp-063",
        modulo=_M,
        formato="eml",
        agora="2026-09-14 16:00",
        texto=_eml(
            "Everson Magalhães <everson.magalhaes@tvparanasul.com.br>",
            _ASCOM,
            "Re: Pedido de entrevista - explosão de caixa eletrônico",
            "2026-09-14 15:37",
            """
Oi, obrigado! Então aguardo a entrevista com o delegado da DRE sobre a
explosão do caixa eletrônico em Campo Largo até amanhã às 18h.

Everson

Em seg., 14 de set. de 2026 às 11:20, Assessoria de Imprensa PCPR
<imprensa@pc.pr.gov.br> escreveu:
> Olá, Everson. Vamos verificar a agenda do delegado e retornamos.
> Assessoria de Imprensa - Polícia Civil do Paraná
> (41) 3235-0000
""",
        ),
        esperado={
            "jornalista": Contem("Everson"),
            "veiculo": "TV Paraná Sul",
            "contato": Contem("everson.magalhaes@tvparanasul.com.br"),
            "pedido": Contem("explosão do caixa eletrônico"),
            "data": "2026-09-14",
            "horario": "15:37",
            "deadline": "2026-09-15",
        },
        nota="Telefone e horário (11:20) citados são da ASCOM; veículo só pelo domínio.",
    ),
    # ------------------------------------------------------------------ 064
    Caso(
        id="imp-064",
        modulo=_M,
        formato="texto",
        agora="2026-09-16 10:00",
        texto="""
Bom dia! Sou Adriana Kimura, da TV Paraná Sul. Estamos acompanhando o caso
do motorista de aplicativo assassinado no dia 12/09 em Fazenda Rio Grande.
Gostaríamos de uma entrevista com o delegado que investiga o crime.
Preciso até amanhã. Contato: adriana.kimura@tvparanasul.com.br
""",
        esperado={
            "jornalista": Contem("Adriana Kimura"),
            "veiculo": "TV Paraná Sul",
            "contato": Contem("adriana.kimura@tvparanasul.com.br"),
            "pedido": Contem("motorista de aplicativo"),
            "deadline": "2026-09-17",
        },
        nota="12/09 é a data do crime; 'até amanhã' pelo 'agora' = 17/09.",
    ),
    # ------------------------------------------------------------------ 065
    Caso(
        id="imp-065",
        modulo=_M,
        formato="eml",
        agora="2026-09-17 09:30",
        texto=_eml(
            "Gisele Portela <giseleportela@gmail.com>",
            _ASCOM,
            "[Rádio Planalto 98 FM] pedido de entrevista",
            "2026-09-17 09:00",
            """
Bom dia!

Queremos entrevistar o delegado de Maringá sobre a prisão da quadrilha
de furto de motos. Seria ao vivo, amanhã às 8h.

Gisele Portela
""",
        ),
        esperado={
            "jornalista": Contem("Gisele Portela"),
            "veiculo": "Rádio Planalto 98 FM",
            "contato": Contem("giseleportela@gmail.com"),
            "pedido": Contem("quadrilha de furto de motos"),
            "data": "2026-09-17",
            "horario": "09:00",
            "deadline": "2026-09-18",
        },
        nota="Veículo só no assunto (gmail pessoal); ao vivo amanhã 18/09.",
    ),
    # ------------------------------------------------------------------ 066
    Caso(
        id="imp-066",
        modulo=_M,
        formato="texto",
        agora="2026-09-18 20:30",
        texto="""
[18/09/2026 20:14] Everton (Diário do Oeste): Boa noite, Everton Zanella do Jornal Diário do Oeste
[18/09/2026 20:15] Everton (Diário do Oeste): Confirmam a prisão em flagrante do homem que esfaqueou a ex em Palotina hoje? Preciso até amanhã às 8h
""",
        esperado={
            "jornalista": Contem("Everton Zanella"),
            "veiculo": "Jornal Diário do Oeste",
            "pedido": Contem("prisão em flagrante"),
            "data": "2026-09-18",
            "horario": UmDe("20:14", "20:15"),
            "deadline": "2026-09-19",
        },
        nota="Pedido à noite; 'hoje' é o fato, prazo amanhã 19/09.",
    ),
    # ------------------------------------------------------------------ 067
    Caso(
        id="imp-067",
        modulo=_M,
        formato="eml",
        agora="2026-09-21 14:00",
        texto=_eml(
            "Juliana Brzezinski <juliana.b@segurancaemfoco.com.br>",
            _ASCOM,
            "Revista Segurança em Foco - pedido de fotos históricas",
            "2026-09-21 13:21",
            """
Prezados,

Para uma matéria sobre os 170 anos da Polícia Civil do Paraná, solicitamos
fotos históricas de delegacias e viaturas antigas, com os créditos. Se
possível, também uma entrevista com o responsável pelo museu da instituição.

O prazo de entrega do material é até o dia 30.

Juliana Brzezinski
Repórter - Revista Segurança em Foco
""",
            html=True,
        ),
        esperado={
            "jornalista": Contem("Juliana Brzezinski"),
            "veiculo": "Revista Segurança em Foco",
            "contato": Contem("juliana.b@segurancaemfoco.com.br"),
            "pedido": Contem("fotos históricas"),
            "data": "2026-09-21",
            "horario": "13:21",
            "deadline": "2026-09-30",
        },
        nota="'170 anos' não é data; 'até o dia 30' do mês corrente = 30/09.",
    ),
    # ------------------------------------------------------------------ 068
    Caso(
        id="imp-068",
        modulo=_M,
        formato="eml",
        agora="2026-09-22 11:00",
        texto=_eml(
            "Hugo Menegatti <hugo@maringaurgente.com.br>",
            _ASCOM,
            "nota - chacina em Sarandi",
            "2026-09-22 10:25",
            """
Bom dia.

Sou do Portal Maringá Urgente. Solicito nota sobre as três mortes em
Sarandi no fim de semana: a PC trabalha com a hipótese de chacina ligada
ao tráfico? Até as 15h.

Hugo Menegatti
Portal Maringá Urgente
(44) 99810-5521
""",
            utc=True,
        ),
        esperado={
            "jornalista": Contem("Hugo Menegatti"),
            "veiculo": AUSENTE,
            "veiculo_novo": Contem("Maringá Urgente"),
            "contato": UmDe(Contem("99810-5521"), Contem("hugo@maringaurgente.com.br")),
            "pedido": Contem("três mortes"),
            "data": "2026-09-22",
            "horario": "10:25",
            "deadline": "2026-09-22",
        },
        nota="Date em +0000 (13:25 UTC) = 10:25 em Brasília; portal fora do cadastro.",
    ),
    # ------------------------------------------------------------------ 069
    Caso(
        id="imp-069",
        modulo=_M,
        formato="texto",
        agora="2026-09-23 18:10",
        texto="""
De: Samuel Ferreira <samuel.ferreira@gazetadoscampos.com.br>
Enviado em: quarta-feira, 23 de setembro de 2026 17:59
Para: Imprensa PCPR
Assunto: posicionamento - morte em abordagem

Boa tarde. Solicito posicionamento sobre a morte de um homem durante
abordagem policial em Palmeira. Preciso até o fim do dia.

Samuel Ferreira | Gazeta dos Campos | (42) 99901-4417
""",
        esperado={
            "jornalista": Contem("Samuel Ferreira"),
            "veiculo": "Gazeta dos Campos",
            "contato": UmDe(Contem("99901-4417"), Contem("samuel.ferreira@gazetadoscampos.com.br")),
            "pedido": Contem("abordagem policial"),
            "data": "2026-09-23",
            "horario": "17:59",
            "deadline": "2026-09-23",
        },
        nota="Pedido às 17:59 'até o fim do dia' → mesmo dia, não amanhã.",
    ),
    # ------------------------------------------------------------------ 070
    Caso(
        id="imp-070",
        modulo=_M,
        formato="eml",
        agora="2026-09-24 10:30",
        texto=_eml(
            "Pâmela Costa <pamela.costa@tviguacu8.com.br>",
            _ASCOM,
            _q("Sonora + imagens para o Iguaçu Revista"),
            "2026-09-24 10:02",
            """
Bom dia!

Estamos produzindo uma reportagem para o programa Iguaçu Revista sobre o
trabalho do Núcleo de Repressão a Crimes Econômicos. Solicitamos sonora do
delegado e imagens do cumprimento de mandados da última operação.

A reportagem vai ao ar no domingo.

Pâmela Costa
TV Iguaçu Canal 8
""",
        ),
        esperado={
            "jornalista": Contem("Pâmela Costa"),
            "veiculo": "TV Iguaçu Canal 8",
            "contato": Contem("pamela.costa@tviguacu8.com.br"),
            "pedido": Contem("sonora do delegado"),
            "data": "2026-09-24",
            "horario": "10:02",
            "deadline": "2026-09-27",
        },
        nota="Veiculação no domingo a partir de quinta 24/09 = 27/09.",
    ),
    # ------------------------------------------------------------------ 071
    Caso(
        id="imp-071",
        modulo=_M,
        formato="texto",
        agora="2026-09-25 09:00",
        texto="""
[25/09/2026 08:47] Ícaro Agência Pinhão: Bom dia! Ícaro Benedetti, da Agência Pinhão de Notícias. A PC confirma a prisão do suspeito do roubo à joalheria no Batel, ocorrido em 21/09?
""",
        esperado={
            "jornalista": Contem("Ícaro Benedetti"),
            "veiculo": "Agência Pinhão de Notícias",
            "pedido": Contem("roubo à joalheria"),
            "data": "2026-09-25",
            "horario": "08:47",
            "deadline": AUSENTE,
        },
        nota="Sem prazo; 21/09 é a data do roubo, não deadline.",
    ),
    # ------------------------------------------------------------------ 072
    Caso(
        id="imp-072",
        modulo=_M,
        formato="eml",
        agora="2026-10-01 15:00",
        texto=_eml(
            "Viviane Salomão <viviane.salomao@radiocidadefm.com.br>",
            _ASCOM,
            "convite - entrevista ao vivo segunda",
            "2026-10-01 14:18",
            """
Boa tarde!

Convidamos um delegado da Divisão de Homicídios para uma entrevista ao vivo
no programa Manhã Cidade na segunda (5), às 7h30, sobre o Setembro Amarelo
e a investigação de induzimento ao suicídio na internet.

Viviane Salomão
Produtora - Rádio Cidade FM
""",
        ),
        esperado={
            "jornalista": Contem("Viviane Salomão"),
            "veiculo": "Rádio Cidade FM",
            "contato": Contem("viviane.salomao@radiocidadefm.com.br"),
            "pedido": Contem("entrevista ao vivo"),
            "data": "2026-10-01",
            "horario": "14:18",
            "deadline": "2026-10-05",
        },
        nota="'Setembro Amarelo' não é data; veiculação segunda (5) = 05/10.",
    ),
    # ------------------------------------------------------------------ 073
    Caso(
        id="imp-073",
        modulo=_M,
        formato="texto",
        agora="2026-10-05 09:00",
        texto="""
Prezada assessoria de imprensa da Polícia Civil,

Meu nome é Rogério Tavares Filho e sou repórter especial do Jornal Diário do
Oeste. Há três meses acompanhamos o caso da família desaparecida em Marechal
Cândido Rondon, visto pela última vez em 14 de junho. Na semana passada,
parentes relataram à nossa reportagem que a investigação teria sido
transferida para a Divisão de Homicídios.

Gostaria de saber: (1) se a transferência procede; (2) se há suspeitos; (3)
se a PCPR pode conceder entrevista com o delegado responsável.

Preciso das respostas até as 16h de amanhã, quando fechamos a edição
especial.

Rogério Tavares Filho
(45) 99987-3312
""",
        esperado={
            "jornalista": Contem("Rogério Tavares Filho"),
            "veiculo": "Jornal Diário do Oeste",
            "contato": Contem("99987-3312"),
            "pedido": Contem("família desaparecida"),
            "deadline": "2026-10-06",
        },
        nota="E-mail longo colado sem cabeçalho; 14 de junho é fato; 'amanhã' pelo 'agora' = 06/10.",
    ),
    # ------------------------------------------------------------------ 074
    Caso(
        id="imp-074",
        modulo=_M,
        formato="eml",
        agora="2026-10-14 08:30",
        texto=_eml(
            "Chefia de Reportagem TV Paraná Sul <chefia.reportagem@tvparanasul.com.br>",
            _ASCOM,
            "Pauta do dia - roubo a residência no Ecoville",
            "2026-10-14 07:58",
            """
Bom dia, assessoria.

A repórter Ingrid Salles (em cópia) vai cobrir o roubo à residência no
Ecoville e precisa de entrevista com o delegado da Delegacia de Furtos e
Roubos até as 11h.

Chefia de Reportagem
TV Paraná Sul
""",
            cc="Ingrid Salles <ingrid.salles@tvparanasul.com.br>",
        ),
        esperado={
            "jornalista": Contem("Ingrid Salles"),
            "veiculo": "TV Paraná Sul",
            "contato": Contem("ingrid.salles@tvparanasul.com.br"),
            "pedido": Contem("roubo à residência"),
            "data": "2026-10-14",
            "horario": "07:58",
            "deadline": "2026-10-14",
        },
        nota="From é a chefia; a jornalista é a repórter em cópia (contato dela).",
    ),
    # ------------------------------------------------------------------ 075
    Caso(
        id="imp-075",
        modulo=_M,
        formato="texto",
        agora="2026-10-15 16:00",
        texto="""
De: Ademir Kuss <ademir.kuss@educadoraam.com.br>
Enviado em: quinta-feira, 15 de outubro de 2026 15:26
Para: imprensa@pc.pr.gov.br
Assunto: dados - desaparecidos

Boa tarde. Solicito o número de pessoas desaparecidas localizadas pela PCPR
neste ano. Prazo: 20/10.

Ademir Kuss
Rádio Educadora AM

Este e-mail foi verificado contra vírus. Não imprima se não for necessário.
""",
        esperado={
            "jornalista": Contem("Ademir Kuss"),
            "veiculo": "Rádio Educadora AM",
            "contato": Contem("ademir.kuss@educadoraam.com.br"),
            "pedido": Contem("pessoas desaparecidas"),
            "data": "2026-10-15",
            "horario": "15:26",
            "deadline": "2026-10-20",
        },
        nota="Prazo explícito dd/mm; rodapé automático sem dado útil.",
    ),
    # ------------------------------------------------------------------ 076
    Caso(
        id="imp-076",
        modulo=_M,
        formato="texto",
        agora="2026-10-16 13:30",
        texto="""
[16/10/2026 13:11] Carol Notícias Já: Oi! Carolina Veiga, do Portal Notícias Já
[16/10/2026 13:12] Carol Notícias Já: Preciso ainda hoje de uma nota sobre a morte da criança atingida por bala perdida em Campo Magro
""",
        esperado={
            "jornalista": Contem("Carolina Veiga"),
            "veiculo": "Portal Notícias Já",
            "pedido": Contem("bala perdida"),
            "data": "2026-10-16",
            "horario": UmDe("13:11", "13:12"),
            "deadline": "2026-10-16",
        },
        nota="'Ainda hoje' → deadline hoje, sem hora.",
    ),
    # ------------------------------------------------------------------ 077
    Caso(
        id="imp-077",
        modulo=_M,
        formato="texto",
        agora="2026-10-19 17:00",
        texto="""
[19/10/2026 16:40] Márcio TV Litoral: Boa tarde! Márcio Figueira, TV Litoral Paranaense
[19/10/2026 16:41] Márcio TV Litoral: Consegue uma entrevista com o delegado de Paranaguá sobre o furto de contêineres? Pra amanhã meio dia
""",
        esperado={
            "jornalista": Contem("Márcio Figueira"),
            "veiculo": "TV Litoral Paranaense",
            "pedido": Contem("furto de contêineres"),
            "data": "2026-10-19",
            "horario": UmDe("16:40", "16:41"),
            "deadline": "2026-10-20",
        },
        nota="'Amanhã meio dia' → 20/10.",
    ),
    # ------------------------------------------------------------------ 078
    Caso(
        id="imp-078",
        modulo=_M,
        formato="eml",
        agora="2026-11-02 11:00",
        texto=_eml(
            "Lorena Guedes <lorena.guedes@tribunapg.com.br>",
            _ASCOM,
            _q("Pedido de entrevista — ocorrências no feriado de Finados"),
            "2026-11-02 10:44",
            """
Bom dia!

Gostaria de entrevistar o delegado plantonista de Ponta Grossa sobre o
balanço de ocorrências do feriado de Finados. Consigo esperar até
quarta-feira, dia 4.

Lorena Guedes
Jornal Tribuna Ponta-grossense
""",
        ),
        esperado={
            "jornalista": Contem("Lorena Guedes"),
            "veiculo": "Jornal Tribuna Ponta-grossense",
            "contato": Contem("lorena.guedes@tribunapg.com.br"),
            "pedido": Contem("feriado de Finados"),
            "data": "2026-11-02",
            "horario": "10:44",
            "deadline": "2026-11-04",
        },
        nota="Finados (02/11) é o feriado citado; prazo quarta 04/11.",
    ),
    # ------------------------------------------------------------------ 079
    Caso(
        id="imp-079",
        modulo=_M,
        formato="texto",
        agora="2026-12-16 10:00",
        texto="""
Bom dia, pessoal. É o Sérgio Mazur, da Rádio Vale do Ribeira FM.
Queria fechar com vocês uma entrevista com o delegado de Cerro Azul sobre
as ações de fim de ano. Preciso até sexta, antes do recesso.
WhatsApp (41) 99433-1287
""",
        esperado={
            "jornalista": Contem("Sérgio Mazur"),
            "veiculo": "Rádio Vale do Ribeira FM",
            "contato": Contem("99433-1287"),
            "pedido": Contem("ações de fim de ano"),
            "deadline": "2026-12-18",
        },
        nota="'Até sexta' pelo 'agora' (quarta 16/12) = 18/12; recesso não é data.",
    ),
    # ------------------------------------------------------------------ 080
    Caso(
        id="imp-080",
        modulo=_M,
        formato="eml",
        agora="2026-12-18 17:00",
        texto=_eml(
            "Eduardo Guimarães <eduardo.guimaraes@folhanortepioneiro.com.br>",
            _ASCOM,
            "Pedido de balanço anual",
            "2026-12-18 16:40",
            """
Boa tarde, equipe!

Solicito o balanço anual de 2026 da Polícia Civil na região de
Jacarezinho: prisões, inquéritos concluídos e apreensões. A edição de
retrospectiva sai em 31/12, mas preciso do material até segunda (21).

Boas festas!
Eduardo Guimarães
Folha do Norte Pioneiro

{aviso}
""".format(aviso=_AVISO),
            html=True,
        ),
        esperado={
            "jornalista": Contem("Eduardo Guimarães"),
            "veiculo": "Folha do Norte Pioneiro",
            "contato": Contem("eduardo.guimaraes@folhanortepioneiro.com.br"),
            "pedido": Contem("balanço anual"),
            "data": "2026-12-18",
            "horario": "16:40",
            "deadline": "2026-12-21",
        },
        nota="Duas datas: veiculação 31/12, mas o prazo pedido é segunda 21/12.",
    ),
]
