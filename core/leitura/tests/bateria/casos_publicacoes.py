"""Bateria de Publicações: material de divulgação que as delegacias mandam.

Releases de operações, prisões, apreensões e cumprimento de mandados que
chegam à assessoria por e-mail ou WhatsApp, pedindo publicação no site e
nas redes. Tudo fictício: servidores inventados, suspeitos só por iniciais
ou idade.

Leitura dos campos (conferida em `publicacoes/models.py`):

- ``data`` ("data da pauta") e ``inicio_pauta`` ("início da pauta") são o
  dia e a hora em que a pauta entrou na assessoria — o envio do e-mail
  (convertido para o horário de Brasília) ou o carimbo da mensagem do
  WhatsApp. A data/hora da prisão ou da operação NÃO serve; texto sem
  carimbo de envio fica com ``AUSENTE``;
- ``fonte`` é quem passou a informação (o servidor que mandou o material);
- ``jornalista`` é alguém da equipe de comunicação: nunca o delegado nem o
  escrivão que mandou o release;
- ``unidade`` é a unidade que manda a pauta (o nome do cadastro), não a
  parceira que "deu apoio" nem a cidade da assinatura.
"""

from __future__ import annotations

import base64
import datetime as _dt
import itertools
import quopri
from email.charset import BASE64, QP, Charset
from email.header import Header
from email.utils import format_datetime, formataddr
from html import escape

from . import AUSENTE, Caso, Contem, UmDe

CADASTROS = {
    "unidade": [
        "Delegacia de Polícia de Palmas",
        "13ª Subdivisão Policial de Ponta Grossa",
        "Delegacia da Mulher de Cascavel",
        "Delegacia da Mulher de Ponta Grossa",
        "Delegacia da Mulher de Maringá",
        "DHPP",
        "Delegacia de Furtos e Roubos de Veículos",
        "Delegacia de Furtos e Roubos",
        "15ª Subdivisão Policial de Cascavel",
        "9ª Subdivisão Policial de Foz do Iguaçu",
        "Delegacia de Polícia de Guarapuava",
        "Delegacia de Estelionato e Desvio de Cargas",
        "DENARC",
        "NUCRIA de Curitiba",
        "Delegacia de Polícia de Pato Branco",
        "Delegacia de Polícia de União da Vitória",
        "Delegacia de Homicídios de Londrina",
        "COPE",
        "Delegacia de Polícia de Irati",
        "NUCIBER",
        "Delegacia de Polícia de Campo Mourão",
        "Delegacia de Polícia de Rio Negro",
        "Delegacia de Polícia de Ortigueira",
    ],
}


# --------------------------------------------------------------------------
# Montagem dos .eml (cabeçalhos RFC 822 de verdade, dia da semana certo)
# --------------------------------------------------------------------------

_DIAS = [
    "segunda-feira", "terça-feira", "quarta-feira", "quinta-feira",
    "sexta-feira", "sábado", "domingo",
]
_MESES = [
    "janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho",
    "agosto", "setembro", "outubro", "novembro", "dezembro",
]
_SEQ = itertools.count(1001)
_JPEG = base64.encodebytes(b"\xff\xd8\xff\xe0\x00\x10JFIF" + bytes(96) + b"\xff\xd9").decode()


def _data_rfc(quando, tz="-0300"):
    d = _dt.datetime.strptime(quando, "%Y-%m-%d %H:%M")
    sinal = 1 if tz[0] == "+" else -1
    off = _dt.timedelta(hours=int(tz[1:3]), minutes=int(tz[3:5])) * sinal
    return format_datetime(d.replace(tzinfo=_dt.timezone(off)))


def _outlook(quando):
    d = _dt.datetime.strptime(quando, "%Y-%m-%d %H:%M")
    return (
        f"{_DIAS[d.weekday()]}, {d.day} de {_MESES[d.month - 1]} de "
        f"{d.year} {d:%H:%M}"
    )


def _parte(tipo, corpo, qp):
    if qp:
        return (
            f'Content-Type: {tipo}; charset="utf-8"\n'
            "Content-Transfer-Encoding: quoted-printable\n\n"
            + quopri.encodestring(corpo.encode("utf-8")).decode("ascii")
        )
    return (
        f'Content-Type: {tipo}; charset="utf-8"\n'
        "Content-Transfer-Encoding: 8bit\n\n" + corpo
    )


def _html(corpo):
    paragrafos = "".join(
        "<p>" + escape(p).replace("\n", "<br>") + "</p>\n"
        for p in corpo.strip().split("\n\n")
    )
    return (
        '<html><head><meta charset="utf-8"></head>'
        '<body style="font-family: Calibri, sans-serif">\n'
        f"{paragrafos}</body></html>\n"
    )


def _eml(de, para, assunto, quando, corpo, *, tz="-0300", cod=None,
         html=False, anexos=(), cc=None, qp=False):
    """Um .eml completo. `cod` = "b"/"q" codifica Subject e From (RFC 2047)."""
    nome, endereco = de
    if cod:
        cs = Charset("utf-8")
        cs.header_encoding = BASE64 if cod == "b" else QP
        subject = Header(assunto, cs).encode()
        remetente = formataddr((nome, endereco), charset="utf-8")
    else:
        subject = assunto
        remetente = f"{nome} <{endereco}>"
    n = next(_SEQ)
    cab = [
        f"Return-Path: <{endereco}>",
        f"Received: from mail.exemplo.pr.gov.br (10.15.3.{n % 250}) by "
        f"mx.exemplo.pr.gov.br; {_data_rfc(quando, tz)}",
        f"Message-ID: <{n}.{quando[:10].replace('-', '')}@exemplo.pr.gov.br>",
        f"Date: {_data_rfc(quando, tz)}",
        f"From: {remetente}",
        f"To: {para}",
    ]
    if cc:
        cab.append(f"Cc: {cc}")
    cab += [f"Subject: {subject}", "MIME-Version: 1.0"]

    if html:
        fr = f"----=_alt_{n}"
        conteudo = (
            f'Content-Type: multipart/alternative; boundary="{fr}"\n\n'
            f"--{fr}\n{_parte('text/plain', corpo, qp)}\n"
            f"--{fr}\n{_parte('text/html', _html(corpo), qp)}\n"
            f"--{fr}--\n"
        )
    else:
        conteudo = _parte("text/plain", corpo, qp) + "\n"

    if anexos:
        fm = f"----=_mix_{n}"
        partes = [f"--{fm}\n{conteudo}"]
        for nome_arq in anexos:
            partes.append(
                f"--{fm}\n"
                f'Content-Type: image/jpeg; name="{nome_arq}"\n'
                f'Content-Disposition: attachment; filename="{nome_arq}"\n'
                "Content-Transfer-Encoding: base64\n\n" + _JPEG
            )
        conteudo = (
            f'Content-Type: multipart/mixed; boundary="{fm}"\n\n'
            + "".join(partes) + f"--{fm}--\n"
        )
    return "\n".join(cab) + "\n" + conteudo


_ASCOM = "Assessoria de Comunicação PCPR <ascom.pautas@exemplo.pr.gov.br>"
_SIGILO = (
    "AVISO DE CONFIDENCIALIDADE: Esta mensagem e seus anexos podem conter "
    "informações sigilosas, de uso restrito ao destinatário. Se você a "
    "recebeu por engano, apague-a e comunique o remetente. A divulgação, "
    "cópia ou distribuição não autorizada é proibida."
)


# --------------------------------------------------------------------------
# Casos
# --------------------------------------------------------------------------

CASOS = [
    Caso(
        id="pub-001",
        modulo="publicacoes",
        formato="eml",
        agora="2026-09-14 10:30",
        texto=_eml(
            ("Juliana Portela Maciel", "juliana.maciel@exemplo.pr.gov.br"),
            _ASCOM,
            "Release para divulgação - prisão por tráfico em Palmas",
            "2026-09-14 09:14",
            """Bom dia!

Segue release para divulgação no site e redes. Fotos em anexo.

PCPR PRENDE HOMEM POR TRÁFICO DE DROGAS EM PALMAS

A Polícia Civil do Paraná (PCPR) prendeu em flagrante, nesta sexta-feira (11), um homem de 29 anos por tráfico de drogas, em Palmas, no Sudoeste do estado. Com ele foram apreendidos 3,2 kg de maconha, 180 gramas de cocaína e uma balança de precisão.

Segundo o delegado Henrique Vasconi Prado, o suspeito vinha sendo monitorado havia dois meses. "Recebemos diversas denúncias anônimas e conseguimos confirmar a atividade no imóvel", afirmou.

O preso foi encaminhado à cadeia pública e está à disposição da Justiça.

Att.,
Juliana Portela Maciel
Escrivã de Polícia
Delegacia de Polícia de Palmas
(46) 3262-0000 – ramal 214
""",
            anexos=("IMG_2041.jpg", "IMG_2042.jpg"),
        ),
        esperado={
            "titulo": Contem("tráfico de drogas em Palmas"),
            "unidade": "Delegacia de Polícia de Palmas",
            "fonte": Contem("Juliana Portela"),
            "data": "2026-09-14",
            "inicio_pauta": "09:14",
            "jornalista": AUSENTE,
        },
        nota="Data da prisão (sexta, 11) não é a data da pauta; delegado citado não é jornalista.",
    ),
    Caso(
        id="pub-002",
        modulo="publicacoes",
        formato="eml",
        agora="2026-09-15 11:00",
        texto=_eml(
            ("Rodrigo Kasper Lemes", "rodrigo.lemes@exemplo.pr.gov.br"),
            _ASCOM,
            "Divulgação – Operação Vento Sul (13ª SDP)",
            "2026-09-15 08:47",
            """Prezados, bom dia.

A pedido da autoridade policial, encaminho material da Operação Vento Sul para publicação. Seguem fotos em anexo (sem rosto dos presos).

OPERAÇÃO VENTO SUL CUMPRE 14 MANDADOS CONTRA FACÇÃO EM PONTA GROSSA

A 13ª SDP deflagrou, no sábado (12/09), a Operação Vento Sul, que cumpriu 14 mandados de busca e apreensão e 6 de prisão preventiva contra integrantes de um grupo criminoso ligado ao tráfico de drogas nos Campos Gerais. A ação contou com apoio do COPE e da Polícia Militar.

Foram apreendidos dois revólveres, R$ 18 mil em espécie e 4 kg de crack.

Rodrigo Kasper Lemes
Investigador de Polícia – Setor de Inteligência
13ª Subdivisão Policial – Ponta Grossa/PR
""",
            cod="b",
            html=True,
        ),
        esperado={
            "titulo": Contem("Operação Vento Sul"),
            "unidade": "13ª Subdivisão Policial de Ponta Grossa",
            "fonte": Contem("Rodrigo Kasper"),
            "data": "2026-09-15",
            "inicio_pauta": "08:47",
        },
        nota="Subject em base64; COPE só deu apoio; operação em 12/09 não é a data da pauta.",
    ),
    Caso(
        id="pub-003",
        modulo="publicacoes",
        formato="texto",
        agora="2026-09-16 08:10",
        texto="""[15/09/2026 17:03] Carla Bento DM Cascavel: Boa tarde, pessoal da Ascom! Material para divulgação 👇
[15/09/2026 17:03] Carla Bento DM Cascavel: PCPR PRENDE HOMEM POR DESCUMPRIR MEDIDA PROTETIVA EM CASCAVEL

A Delegacia da Mulher de Cascavel prendeu nesta terça-feira (15) um homem de 41 anos que descumpriu medida protetiva de urgência concedida à ex-companheira. Ele foi localizado no bairro Periolo após a vítima acionar o botão do pânico.

"A medida protetiva é para ser cumprida. Não vamos tolerar", disse a delegada Aline Moschetta Ribas.
[15/09/2026 17:04] Carla Bento DM Cascavel: IMG-20260915-WA0031.jpg (arquivo anexado)
[15/09/2026 17:04] Carla Bento DM Cascavel: Sem divulgar nome, por favor, pra não expor a vítima
[15/09/2026 17:20] Ascom PCPR: Recebido, Carla! Obrigada""",
        esperado={
            "titulo": Contem("descumprir medida protetiva"),
            "unidade": "Delegacia da Mulher de Cascavel",
            "fonte": Contem("Carla Bento"),
            "data": "2026-09-15",
            "inicio_pauta": "17:03",
            "jornalista": AUSENTE,
        },
        nota="WhatsApp; 'DM Cascavel' no nome do contato; a resposta da Ascom às 17:20 não é o início.",
    ),
    Caso(
        id="pub-004",
        modulo="publicacoes",
        formato="eml",
        agora="2026-09-16 15:00",
        texto=_eml(
            ("Diego Farinon", "diego.farinon@exemplo.pr.gov.br"),
            _ASCOM,
            "Material para divulgação - DHPP",
            "2026-09-16 13:22",
            """Boa tarde,

Segue material para publicação, favor não divulgar o nome do investigado.

DHPP PRENDE SUSPEITO DE HOMICÍDIO NO BAIRRO CAJURU

A Divisão de Homicídios e Proteção à Pessoa (DHPP) cumpriu nesta quarta-feira mandado de prisão temporária contra um homem de 24 anos suspeito de matar um jovem de 19 anos em 30 de agosto, no bairro Cajuru, em Curitiba. A prisão contou com apoio da Delegacia de Furtos e Roubos de Veículos, que localizou a motocicleta usada no crime.

Segundo o delegado responsável, a motivação seria uma dívida de drogas.

Diego Farinon
Escrivão – DHPP
Curitiba – PR
""",
            html=True,
        ),
        esperado={
            "titulo": Contem("suspeito de homicídio"),
            "unidade": "DHPP",
            "fonte": Contem("Diego Farinon"),
            "data": "2026-09-16",
            "inicio_pauta": "13:22",
        },
        nota="DFRV aparece como parceira; data do crime (30/08) é armadilha.",
    ),
    Caso(
        id="pub-005",
        modulo="publicacoes",
        formato="texto",
        agora="2026-09-16 15:00",
        texto=f"""De: Patrícia Loyola Weber <patricia.weber@exemplo.pr.gov.br>
Enviado em: {_outlook("2026-09-16 11:20")}
Para: Ascom PCPR <ascom.pautas@exemplo.pr.gov.br>
Assunto: DFRV recupera sete veículos roubados - para publicação

Olá,

Encaminho release da DFRV para publicação. As fotos seguem no próximo e-mail (arquivo pesado).

DFRV RECUPERA SETE VEÍCULOS ROUBADOS E DESARTICULA DESMANCHE EM COLOMBO

Policiais da Delegacia de Furtos e Roubos de Veículos localizaram, na terça-feira (15), um desmanche clandestino em Colombo, na Região Metropolitana de Curitiba. Sete veículos com registro de roubo foram recuperados e dois homens, de 33 e 45 anos, foram presos em flagrante.

Patrícia Loyola Weber
Investigadora – DFRV
Tel. (41) 3000-0000""",
        esperado={
            "titulo": Contem("recupera sete veículos"),
            "unidade": "Delegacia de Furtos e Roubos de Veículos",
            "fonte": Contem("Patrícia Loyola"),
            "data": "2026-09-16",
            "inicio_pauta": "11:20",
        },
        nota="Outlook colado; sigla DFRV; fato na terça (15), envio na quarta (16).",
    ),
    Caso(
        id="pub-006",
        modulo="publicacoes",
        formato="eml",
        agora="2026-09-17 11:40",
        texto=_eml(
            ("Marcos Tavernaro", "marcos.tavernaro@exemplo.pr.gov.br"),
            _ASCOM,
            "Prisão em Palmeira - para divulgação",
            "2026-09-17 10:05",
            """Bom dia, colegas da assessoria.

Segue texto e fotos (em anexo) da prisão realizada ontem, para divulgação.

PCPR PRENDE FORAGIDO POR ROUBO A MÃO ARMADA EM PALMEIRA

A Polícia Civil do Paraná prendeu na quarta-feira (16), em Palmeira, nos Campos Gerais, um homem de 36 anos que estava foragido havia um ano. Ele foi condenado por roubo a mão armada contra um posto de combustíveis.

Marcos Tavernaro
Investigador de Polícia
Delegacia de Polícia de Palmeira
""",
            anexos=("foto1.jpg",),
        ),
        esperado={
            "titulo": Contem("foragido por roubo"),
            "unidade": AUSENTE,
            "unidade_nova": Contem("Palmeira"),
            "fonte": Contem("Marcos Tavernaro"),
            "data": "2026-09-17",
            "inicio_pauta": "10:05",
        },
        nota="Palmeira não está no cadastro (não confundir com Palmas).",
    ),
    Caso(
        id="pub-007",
        modulo="publicacoes",
        formato="texto",
        agora="2026-10-05 09:00",
        texto="""PCPR CUMPRE MANDADOS CONTRA SUSPEITOS DE FURTO DE GADO EM PATO BRANCO

A Polícia Civil do Paraná, por meio da DP de Pato Branco, cumpriu no sábado (03/10) quatro mandados de busca e apreensão contra suspeitos de furtar 38 cabeças de gado em propriedades rurais da região. A ação começou por volta das 6h e terminou com a prisão de dois homens, de 27 e 51 anos.

De acordo com o delegado Otávio Brandalise, os animais eram abatidos em um abatedouro clandestino e a carne revendida em açougues da região.

Favor publicar. Fotos no drive da assessoria.""",
        esperado={
            "titulo": Contem("furto de gado"),
            "unidade": "Delegacia de Polícia de Pato Branco",
            "data": AUSENTE,
            "inicio_pauta": AUSENTE,
        },
        nota="Texto sem carimbo de envio: 03/10 e 6h são do fato, não da pauta.",
    ),
    Caso(
        id="pub-008",
        modulo="publicacoes",
        formato="eml",
        agora="2026-10-06 19:00",
        texto=_eml(
            ("Del. Fábio Guarienti", "fabio.guarienti@exemplo.pr.gov.br"),
            _ASCOM,
            "Op. Muralha - fotos",
            "2026-10-06 18:40",
            """Segue material da operação de hoje.

Fábio Guarienti
Delegado de Polícia
15ª SDP – Cascavel/PR

Enviado do meu iPhone
""",
            anexos=("op_muralha_01.jpg", "op_muralha_02.jpg", "op_muralha_03.jpg"),
        ),
        esperado={
            "titulo": Contem("Muralha"),
            "unidade": "15ª Subdivisão Policial de Cascavel",
            "fonte": Contem("Fábio Guarienti"),
            "data": "2026-10-06",
            "inicio_pauta": "18:40",
            "jornalista": AUSENTE,
        },
        nota="E-mail curtíssimo; unidade só na assinatura (15ª SDP), não é a Delegacia da Mulher de Cascavel.",
    ),
    Caso(
        id="pub-009",
        modulo="publicacoes",
        formato="eml",
        agora="2026-10-07 15:00",
        texto=_eml(
            ("Simone Rech Andrade", "simone.andrade@exemplo.pr.gov.br"),
            _ASCOM,
            "Pedido de divulgação - Delegacia da Mulher de PG",
            "2026-10-07 14:12",
            """Boa tarde.

Solicito a divulgação do release abaixo.

PCPR PRENDE HOMEM POR TENTATIVA DE FEMINICÍDIO EM PONTA GROSSA

A Delegacia da Mulher de Ponta Grossa, vinculada à 13ª Subdivisão Policial, prendeu nesta quarta-feira (07) um homem de 38 anos suspeito de tentar matar a companheira a facadas no último domingo (04). A vítima segue internada.

A delegada ressaltou que a violência doméstica pode ser denunciada pelo 181 ou pelo 190.

Simone Rech Andrade
Escrivã de Polícia
Delegacia da Mulher – Ponta Grossa
""",
        ),
        esperado={
            "titulo": Contem("tentativa de feminicídio"),
            "unidade": "Delegacia da Mulher de Ponta Grossa",
            "fonte": Contem("Simone Rech"),
            "data": "2026-10-07",
            "inicio_pauta": "14:12",
        },
        nota="13ª SDP citada só como vinculação; a unidade é a Delegacia da Mulher de PG.",
    ),
    Caso(
        id="pub-010",
        modulo="publicacoes",
        formato="texto",
        agora="2026-10-08 10:00",
        texto="""[08/10/2026 07:58] Leandro Scussel DENARC: Bom dia! Vou mandar material da apreensão de ontem à noite pra divulgação
[08/10/2026 08:15] Leandro Scussel DENARC: DENARC APREENDE 120 KG DE MACONHA EM CAMINHÃO NA BR-277

A Divisão Estadual de Narcóticos (DENARC) apreendeu na noite de quarta-feira (07) 120 quilos de maconha escondidos em um carregamento de soja, em Balsa Nova. O motorista, de 47 anos, foi preso em flagrante.
[08/10/2026 08:16] Leandro Scussel DENARC: <anexado: 00000041-PHOTO-2026-10-08-08-16-02.jpg>
[08/10/2026 08:16] Leandro Scussel DENARC: <anexado: 00000042-PHOTO-2026-10-08-08-16-03.jpg>
[08/10/2026 08:30] Ascom PCPR: Show, já vamos subir""",
        esperado={
            "titulo": Contem("120 kg de maconha"),
            "unidade": "DENARC",
            "fonte": Contem("Leandro Scussel"),
            "data": "2026-10-08",
            "inicio_pauta": "07:58",
        },
        nota="Pauta começa no aviso das 07:58, não no release das 08:15; apreensão foi na noite anterior.",
    ),
    Caso(
        id="pub-011",
        modulo="publicacoes",
        formato="eml",
        agora="2026-09-29 08:00",
        texto=_eml(
            ("Everton Sachet", "everton.sachet@exemplo.pr.gov.br"),
            _ASCOM,
            "9ª SDP - apreensão de armas em Foz - divulgação",
            "2026-09-29 01:40",
            """Boa noite,

Segue para divulgação. Fotos em anexo.

PCPR APREENDE ARSENAL COM FUZIL E 900 MUNIÇÕES EM FOZ DO IGUAÇU

A 9ª Subdivisão Policial de Foz do Iguaçu apreendeu nesta segunda-feira (28) um fuzil calibre 5.56, três pistolas e cerca de 900 munições em uma residência no bairro Três Lagoas. Um homem de 31 anos foi preso.

Everton Sachet
Investigador – 9ª SDP
""",
            tz="+0000",
            anexos=("armas.jpg",),
        ),
        esperado={
            "titulo": Contem("fuzil"),
            "unidade": "9ª Subdivisão Policial de Foz do Iguaçu",
            "fonte": Contem("Everton Sachet"),
            "data": "2026-09-28",
            "inicio_pauta": "22:40",
        },
        nota="Date em +0000 (01:40 do dia 29) = 22:40 do dia 28 em Brasília.",
    ),
    Caso(
        id="pub-012",
        modulo="publicacoes",
        formato="eml",
        agora="2026-10-02 15:00",
        texto=_eml(
            ("Gabinete 10ª SDP", "gabinete.londrina@exemplo.pr.gov.br"),
            _ASCOM,
            "ENC: Divulgação - prisão de suspeito de duplo homicídio",
            "2026-10-02 14:05",
            """Encaminho para providências.

________________________________
De: Renata Colussi Dalmolin <renata.dalmolin@exemplo.pr.gov.br>
Enviado: sexta-feira, 2 de outubro de 2026 13:30
Para: Gabinete 10ª SDP
Assunto: Divulgação - prisão de suspeito de duplo homicídio

Doutor, segue o release para encaminhar à Ascom.

PCPR PRENDE SUSPEITO DE DUPLO HOMICÍDIO NA ZONA NORTE DE LONDRINA

A Delegacia de Homicídios de Londrina prendeu nesta sexta-feira (02) um homem de 22 anos suspeito de matar duas pessoas em um bar no Jardim Santiago, em 19 de setembro.

Renata Colussi Dalmolin
Delegada de Polícia
Delegacia de Homicídios de Londrina
""",
        ),
        esperado={
            "titulo": Contem("duplo homicídio"),
            "unidade": "Delegacia de Homicídios de Londrina",
            "data": "2026-10-02",
            "inicio_pauta": UmDe("14:05", "13:30"),
            "jornalista": AUSENTE,
        },
        nota="Encaminhado pelo gabinete: unidade é a DH de Londrina (não '10ª SDP', que não é cadastro).",
    ),
    Caso(
        id="pub-013",
        modulo="publicacoes",
        formato="texto",
        agora="2026-10-09 17:00",
        texto="""[09/10/2026 16:20] Dr. Marcelo Antunes Nucria: Boa tarde. Segue p/ divulgação, SEM divulgar nomes nem bairro (vítima criança)
[09/10/2026 16:21] Dr. Marcelo Antunes Nucria: NUCRIA PRENDE HOMEM SUSPEITO DE ESTUPRO DE VULNERÁVEL EM CURITIBA

O Núcleo de Proteção à Criança e ao Adolescente Vítimas de Crimes (Nucria) de Curitiba cumpriu nesta sexta-feira (9) mandado de prisão preventiva contra um homem de 52 anos investigado por estupro de vulnerável contra a enteada, de 11 anos.

A investigação começou após denúncia da escola, em agosto.
[09/10/2026 16:22] Dr. Marcelo Antunes Nucria: Foto só da fachada, por favor""",
        esperado={
            "titulo": Contem("estupro de vulnerável"),
            "unidade": "NUCRIA de Curitiba",
            "fonte": Contem("Marcelo Antunes"),
            "data": "2026-10-09",
            "inicio_pauta": "16:20",
            "jornalista": AUSENTE,
        },
        nota="Delegado manda direto; 'Nucria' em minúsculas; não pôr o delegado como jornalista.",
    ),
    Caso(
        id="pub-014",
        modulo="publicacoes",
        formato="eml",
        agora="2026-10-13 09:00",
        texto=_eml(
            ("COPE - Setor de Operações", "cope.operacoes@exemplo.pr.gov.br"),
            _ASCOM,
            "COPE - cumprimento de mandados em União da Vitória",
            "2026-10-13 06:55",
            """Bom dia.

Segue material para divulgação. Fotos em anexo.

COPE CUMPRE MANDADOS CONTRA GRUPO SUSPEITO DE ROUBOS A AGÊNCIAS BANCÁRIAS

O Centro de Operações Policiais Especiais (COPE) cumpriu na madrugada desta terça-feira (13) oito mandados de busca e três de prisão em União da Vitória e Porto União (SC), contra um grupo suspeito de roubos a agências bancárias. A ação teve apoio da Delegacia de Polícia de União da Vitória.

Inv. Alessandro Pilati
COPE – Curitiba
""",
            anexos=("cope1.jpg", "cope2.jpg"),
        ),
        esperado={
            "titulo": Contem("agências bancárias"),
            "unidade": "COPE",
            "fonte": Contem("Alessandro Pilati"),
            "data": "2026-10-13",
            "inicio_pauta": "06:55",
        },
        nota="DP de União da Vitória só apoiou; quem manda é o COPE.",
    ),
    Caso(
        id="pub-015",
        modulo="publicacoes",
        formato="eml",
        agora="2026-10-14 16:00",
        texto=_eml(
            ("Tatiane Grigolo Bassani", "tatiane.bassani@exemplo.pr.gov.br"),
            _ASCOM,
            "Divulgação: golpe do falso advogado – presos em Curitiba",
            "2026-10-14 15:30",
            """Olá, equipe!

Material para publicação no site e Instagram:

NUCIBER PRENDE DUPLA QUE APLICAVA O GOLPE DO FALSO ADVOGADO

O Núcleo de Combate aos Cibercrimes (NUCIBER) da PCPR prendeu nesta quarta-feira (14) dois homens, de 25 e 28 anos, suspeitos de aplicar o golpe do falso advogado contra ao menos 40 vítimas no Paraná. O prejuízo estimado passa de R$ 600 mil.

Dica da delegada: desconfie de mensagens pedindo pagamento para "liberar" valores de processos.

Tatiane Grigolo Bassani
Delegada – NUCIBER
""",
            cod="q",
        ),
        esperado={
            "titulo": Contem("falso advogado"),
            "unidade": "NUCIBER",
            "fonte": Contem("Tatiane Grigolo"),
            "data": "2026-10-14",
            "inicio_pauta": "15:30",
            "jornalista": AUSENTE,
        },
        nota="Subject e From em quoted-printable (RFC 2047).",
    ),
    Caso(
        id="pub-016",
        modulo="publicacoes",
        formato="texto",
        agora="2026-10-15 11:00",
        texto=f"""De: Luana Pertile <luana.pertile@exemplo.pr.gov.br>
Enviado em: {_outlook("2026-10-15 10:02")}
Para: ascom.pautas@exemplo.pr.gov.br
Cc: Delegada Titular DM Maringá
Assunto: Para divulgação

Bom dia!

PCPR PRENDE HOMEM QUE AMEAÇOU EX-COMPANHEIRA COM ARMA DE FOGO EM MARINGÁ

A DM de Maringá prendeu em flagrante na noite de terça-feira (13) um homem de 34 anos que ameaçou a ex-companheira com uma pistola. A arma, sem registro, foi apreendida.

Seguem 2 fotos em anexo.

Luana Pertile
Investigadora – Delegacia da Mulher de Maringá
Maringá/PR""",
        esperado={
            "titulo": Contem("ameaçou ex-companheira"),
            "unidade": "Delegacia da Mulher de Maringá",
            "fonte": Contem("Luana Pertile"),
            "data": "2026-10-15",
            "inicio_pauta": "10:02",
        },
        nota="Assunto genérico: título vem do release; prisão na terça (13).",
    ),
    Caso(
        id="pub-017",
        modulo="publicacoes",
        formato="eml",
        agora="2026-10-17 08:30",
        texto=_eml(
            ("Gustavo Menegatti", "gustavo.menegatti@exemplo.pr.gov.br"),
            _ASCOM,
            "Release - apreensão de cigarros contrabandeados em Campo Mourão",
            "2026-10-16 21:15",
            f"""Boa noite, segue release e fotos pra publicarem amanhã cedo se possível.

PCPR APREENDE 200 MIL MAÇOS DE CIGARRO CONTRABANDEADO EM CAMPO MOURÃO

A Delegacia de Polícia de Campo Mourão apreendeu nesta sexta-feira (16) cerca de 200 mil maços de cigarros de origem paraguaia em um barracão às margens da BR-487. Dois homens foram presos.

Gustavo Menegatti
Delegado de Polícia
DP de Campo Mourão – Campo Mourão/PR

Enviado do meu iPhone

{_SIGILO}
""",
            anexos=("IMG_7781.jpg",),
        ),
        esperado={
            "titulo": Contem("cigarro"),
            "unidade": "Delegacia de Polícia de Campo Mourão",
            "fonte": Contem("Gustavo Menegatti"),
            "data": "2026-10-16",
            "inicio_pauta": "21:15",
            "jornalista": AUSENTE,
        },
        nota="'Publicarem amanhã' não muda a data da pauta (recebida 16/10); aviso de sigilo.",
    ),
    Caso(
        id="pub-018",
        modulo="publicacoes",
        formato="eml",
        agora="2026-10-19 11:00",
        texto=_eml(
            ("Cristiane Bortolini", "cristiane.bortolini@exemplo.pr.gov.br"),
            _ASCOM,
            "Divulgação - prisão de suspeito de latrocínio",
            "2026-10-19 09:40",
            """Bom dia.

Encaminho release para divulgação, favor publicar.

PCPR PRENDE SUSPEITO DE LATROCÍNIO DE TAXISTA EM GUARAPUAVA

A Delegacia de Polícia de Guarapuava prendeu no domingo (18) um homem de 26 anos suspeito de matar um taxista durante um assalto em 2 de outubro. Ele foi localizado em Pato Branco, com apoio da Delegacia de Polícia de Pato Branco.

Cristiane Bortolini
Escrivã – DP Guarapuava
""",
        ),
        esperado={
            "titulo": Contem("latrocínio"),
            "unidade": "Delegacia de Polícia de Guarapuava",
            "fonte": Contem("Cristiane Bortolini"),
            "data": "2026-10-19",
            "inicio_pauta": "09:40",
        },
        nota="Prisão em Pato Branco com apoio da DP de Pato Branco: parceira, não é quem manda.",
    ),
    Caso(
        id="pub-019",
        modulo="publicacoes",
        formato="texto",
        agora="2026-10-20 14:00",
        texto="""[20/10/2026 11:11] Inv. Sérgio Zanella - DP Irati: Boa tarde, segue matéria pra divulgar
[20/10/2026 11:11] Inv. Sérgio Zanella - DP Irati: PCPR RECUPERA TRATOR FURTADO E PRENDE RECEPTADOR EM IRATI

Policiais civis de Irati recuperaram nesta terça-feira (20) um trator avaliado em R$ 280 mil, furtado em setembro de uma propriedade rural de Rebouças. Um homem de 58 anos foi preso por receptação.
[20/10/2026 11:12] Inv. Sérgio Zanella - DP Irati: IMG-20261020-WA0007.jpg (arquivo anexado)
[20/10/2026 11:40] Mariana Ascom: Recebido! Vou redigir e te mando o link
[20/10/2026 13:05] Mariana Ascom: Publicado 👍""",
        esperado={
            "titulo": Contem("trator furtado"),
            "unidade": "Delegacia de Polícia de Irati",
            "fonte": Contem("Sérgio Zanella"),
            "data": "2026-10-20",
            "inicio_pauta": "11:11",
        },
        nota="Fonte é o investigador, não a Mariana da Ascom que respondeu.",
    ),
    Caso(
        id="pub-020",
        modulo="publicacoes",
        formato="eml",
        agora="2026-10-21 17:00",
        texto=_eml(
            ("Anderson Klein Moraes", "anderson.moraes@exemplo.pr.gov.br"),
            _ASCOM,
            "Carga de defensivos recuperada - divulgação",
            "2026-10-21 16:05",
            """Boa tarde,

Segue release da Delegacia de Estelionato e Desvio de Cargas para divulgação. Fotos em anexo.

PCPR RECUPERA CARGA DE R$ 1,2 MILHÃO EM DEFENSIVOS AGRÍCOLAS

A Delegacia de Estelionato e Desvio de Cargas recuperou nesta quarta-feira (21), em São José dos Pinhais, uma carga de defensivos agrícolas avaliada em R$ 1,2 milhão, desviada em Cascavel no início do mês. Dois homens foram presos.

Anderson Klein Moraes
Investigador de Polícia
""",
            anexos=("carga01.jpg", "carga02.jpg"),
        ),
        esperado={
            "titulo": Contem("defensivos agrícolas"),
            "unidade": "Delegacia de Estelionato e Desvio de Cargas",
            "fonte": Contem("Anderson Klein"),
            "data": "2026-10-21",
            "inicio_pauta": "16:05",
        },
        nota="Cascavel citada como local do desvio não aponta para unidades de Cascavel.",
    ),
    Caso(
        id="pub-021",
        modulo="publicacoes",
        formato="eml",
        agora="2026-10-22 12:00",
        texto=_eml(
            ("Vanessa Trevisan", "vanessa.trevisan@exemplo.pr.gov.br"),
            _ASCOM,
            "DFR - dupla presa por roubo a residência",
            "2026-10-22 10:30",
            """Bom dia!

Solicitamos a publicação do release abaixo.

PCPR PRENDE DUPLA SUSPEITA DE ROUBOS A RESIDÊNCIAS NO BATEL

A Delegacia de Furtos e Roubos (DFR) prendeu nesta quinta-feira (22) dois homens, de 30 e 35 anos, suspeitos de ao menos seis roubos a residências no bairro Batel, em Curitiba. O carro usado pelos suspeitos, que tinha placa clonada, também foi apreendido.

Vanessa Trevisan
Escrivã – DFR
""",
        ),
        esperado={
            "titulo": Contem("roubos a residências"),
            "unidade": "Delegacia de Furtos e Roubos",
            "fonte": Contem("Vanessa Trevisan"),
            "data": "2026-10-22",
            "inicio_pauta": "10:30",
        },
        nota="DFR não é a DFRV, mesmo com carro apreendido no texto.",
    ),
    Caso(
        id="pub-022",
        modulo="publicacoes",
        formato="eml",
        agora="2026-10-23 16:30",
        texto=_eml(
            ("Paulo Roberto Dambros", "paulo.dambros@exemplo.pr.gov.br"),
            _ASCOM,
            "RES: Pedido de release - operação em Irati",
            "2026-10-23 15:47",
            """Boa tarde, segue o release conforme pedido. Fotos em anexo.

OPERAÇÃO ÁGUA TURVA PRENDE QUATRO POR TRÁFICO EM IRATI

A Delegacia de Polícia de Irati deflagrou nesta sexta-feira (23) a Operação Água Turva, com cumprimento de nove mandados de busca e quatro de prisão contra suspeitos de tráfico de drogas nos bairros Rio Bonito e Vila São João.

Paulo Roberto Dambros
Delegado de Polícia – DP Irati

-----Mensagem original-----
De: Ascom PCPR <ascom.pautas@exemplo.pr.gov.br>
Enviada em: sexta-feira, 23 de outubro de 2026 14:00
Para: Paulo Roberto Dambros
Assunto: Pedido de release - operação em Irati

Dr. Paulo, boa tarde. Vimos a operação na imprensa local, consegue nos mandar um release com fotos?
Obrigada, Mariana – Ascom
""",
            anexos=("agua_turva.jpg",),
        ),
        esperado={
            "titulo": Contem("Água Turva"),
            "unidade": "Delegacia de Polícia de Irati",
            "fonte": Contem("Paulo Roberto Dambros"),
            "data": "2026-10-23",
            "jornalista": AUSENTE,
        },
        nota="Resposta a pedido da Ascom; mensagem citada é da própria assessoria.",
    ),
    Caso(
        id="pub-023",
        modulo="publicacoes",
        formato="texto",
        agora="2026-10-26 09:30",
        texto="""PCPR ESCLARECE HOMICÍDIO E PRENDE SUSPEITO EM RIO NEGRO

A Polícia Civil do Paraná prendeu no último sábado (24) um homem de 43 anos suspeito de matar um vizinho após uma discussão por causa de divisa de terreno, no interior de Rio Negro. O crime ocorreu em 10 de outubro.

Segundo o delegado Luciano Hartmann Pires, o suspeito confessou o crime.

Assessoria – Delegacia de Polícia de Rio Negro""",
        esperado={
            "titulo": Contem("homicídio"),
            "unidade": "Delegacia de Polícia de Rio Negro",
            "data": AUSENTE,
            "inicio_pauta": AUSENTE,
        },
        nota="Release solto, sem data de envio: 24/10 e 10/10 são do fato.",
    ),
    Caso(
        id="pub-024",
        modulo="publicacoes",
        formato="eml",
        agora="2026-10-27 13:00",
        texto=_eml(
            ("DP Ortigueira", "dp.ortigueira@exemplo.pr.gov.br"),
            _ASCOM,
            "Material para divulgação - DP Ortigueira",
            "2026-10-27 12:20",
            """Prezados,

Segue fotos em anexo e texto para divulgação.

PCPR PRENDE HOMEM POR POSSE ILEGAL DE ARMA E CAÇA DE ANIMAIS SILVESTRES EM ORTIGUEIRA

A Delegacia de Polícia de Ortigueira cumpriu mandado de busca nesta terça-feira (27) em uma propriedade rural e apreendeu duas espingardas, munições e carcaças de animais silvestres. Um homem de 60 anos foi preso.

Informações: escrivão Adilson Groff
""",
            anexos=("ortigueira1.jpg", "ortigueira2.jpg", "ortigueira3.jpg"),
        ),
        esperado={
            "titulo": Contem("animais silvestres"),
            "unidade": "Delegacia de Polícia de Ortigueira",
            "fonte": Contem("Adilson Groff"),
            "data": "2026-10-27",
            "inicio_pauta": "12:20",
        },
        nota="Remetente é a caixa da DP; fonte é quem assina as informações.",
    ),
    Caso(
        id="pub-025",
        modulo="publicacoes",
        formato="eml",
        agora="2026-10-28 10:00",
        texto=_eml(
            ("Elisa Mocellin", "elisa.mocellin@exemplo.pr.gov.br"),
            _ASCOM,
            "Divulgação - Tibagi",
            "2026-10-28 09:05",
            """Bom dia.

Segue release da Delegacia de Tibagi, subordinada à 13ª SDP, para publicação.

PCPR PRENDE SUSPEITO DE INCENDIAR CASA DA EX-COMPANHEIRA EM TIBAGI

A Delegacia de Polícia de Tibagi prendeu na terça-feira (27) um homem de 45 anos suspeito de atear fogo à casa da ex-companheira. Ninguém ficou ferido.

Elisa Mocellin
Escrivã de Polícia – DP Tibagi
""",
        ),
        esperado={
            "titulo": Contem("incendiar casa"),
            "unidade": AUSENTE,
            "unidade_nova": Contem("Tibagi"),
            "fonte": Contem("Elisa Mocellin"),
            "data": "2026-10-28",
            "inicio_pauta": "09:05",
        },
        nota="Tibagi fora do cadastro; a 13ª SDP é só a subordinação, não a unidade.",
    ),
    Caso(
        id="pub-026",
        modulo="publicacoes",
        formato="texto",
        agora="2026-10-29 08:00",
        texto="""28/10/2026 17:45 - Rodrigo Kasper: Boa tarde, material da 13 SDP pra divulgação
28/10/2026 17:45 - Rodrigo Kasper: PCPR PRENDE SUSPEITOS DE EXPLODIR CAIXAS ELETRÔNICOS NOS CAMPOS GERAIS

Três homens, de 23, 27 e 40 anos, foram presos nesta quarta-feira (28) em Ponta Grossa, suspeitos de explodir caixas eletrônicos em Castro e Carambeí. Foram apreendidos explosivos e um veículo roubado.
28/10/2026 17:46 - Rodrigo Kasper: <Mídia oculta>
28/10/2026 17:46 - Rodrigo Kasper: <Mídia oculta>""",
        esperado={
            "titulo": Contem("caixas eletrônicos"),
            "unidade": "13ª Subdivisão Policial de Ponta Grossa",
            "fonte": Contem("Rodrigo Kasper"),
            "data": "2026-10-28",
            "inicio_pauta": "17:45",
        },
        nota="Exportação Android ('dd/mm/aaaa hh:mm - Nome:'); '13 SDP' sem ordinal.",
    ),
    Caso(
        id="pub-027",
        modulo="publicacoes",
        formato="eml",
        agora="2026-10-29 10:00",
        texto=_eml(
            ("Fernanda Zortéa", "fernanda.zortea@exemplo.pr.gov.br"),
            _ASCOM,
            "Pedido de publicação - SDP de Ponta Grossa",
            "2026-10-29 08:30",
            """Bom dia, pessoal.

Pedimos a publicação do texto abaixo. Seguem fotos em anexo.

SDP DE PONTA GROSSA PRENDE ESTELIONATÁRIO QUE VENDIA CARROS FALSOS PELA INTERNET

Um homem de 30 anos foi preso nesta quarta-feira (28) pela Subdivisão Policial de Ponta Grossa, suspeito de anunciar veículos inexistentes em sites de venda. Ao menos 15 vítimas foram identificadas.

Fernanda Zortéa
Investigadora
""",
            html=True,
            anexos=("estelionato_pg.jpg",),
        ),
        esperado={
            "titulo": Contem("carros falsos"),
            "unidade": "13ª Subdivisão Policial de Ponta Grossa",
            "fonte": Contem("Fernanda Zortéa"),
            "data": "2026-10-29",
            "inicio_pauta": "08:30",
        },
        nota="'SDP de Ponta Grossa' sem número = 13ª SDP; não é a Delegacia de Estelionato.",
    ),
    Caso(
        id="pub-028",
        modulo="publicacoes",
        formato="eml",
        agora="2026-10-31 09:00",
        texto=_eml(
            ("Maurício Sganzerla", "mauricio.sganzerla@exemplo.pr.gov.br"),
            _ASCOM,
            "Para divulgação: homicídio no Sítio Cercado esclarecido",
            "2026-10-30 19:02",
            """Boa noite,

Segue matéria para divulgação amanhã (sábado), se possível.

HOMICÍDIO DE MOTORISTA DE APLICATIVO NO SÍTIO CERCADO É ESCLARECIDO

A Divisão de Homicídios e Proteção à Pessoa prendeu nesta sexta-feira (30) dois suspeitos, de 19 e 21 anos, de matar um motorista de aplicativo em 14 de outubro, no Sítio Cercado, em Curitiba.

Maurício Sganzerla
Delegado – Divisão de Homicídios e Proteção à Pessoa
""",
        ),
        esperado={
            "titulo": Contem("motorista de aplicativo"),
            "unidade": "DHPP",
            "fonte": Contem("Maurício Sganzerla"),
            "data": "2026-10-30",
            "inicio_pauta": "19:02",
            "jornalista": AUSENTE,
        },
        nota="Nome por extenso vira DHPP; 'divulgação amanhã' não é a data da pauta.",
    ),
    Caso(
        id="pub-029",
        modulo="publicacoes",
        formato="texto",
        agora="2026-10-30 15:00",
        texto=f"""De: Otávio Brandalise <otavio.brandalise@exemplo.pr.gov.br>
Enviado em: {_outlook("2026-10-30 13:15")}
Para: Ascom PCPR
Assunto: Delegacia de Pato Branco - pedido de divulgação

Boa tarde,

Peço a divulgação da prisão abaixo.

PCPR PRENDE HOMEM COM MANDADO POR PENSÃO ALIMENTÍCIA EM PATO BRANCO

A Delegacia de Pato Branco cumpriu nesta sexta-feira mandado de prisão civil contra um homem de 39 anos que devia R$ 42 mil em pensão alimentícia.

Otávio Brandalise
Delegado de Polícia
Pato Branco/PR""",
        esperado={
            "titulo": Contem("pensão alimentícia"),
            "unidade": "Delegacia de Polícia de Pato Branco",
            "fonte": Contem("Otávio Brandalise"),
            "data": "2026-10-30",
            "inicio_pauta": "13:15",
            "jornalista": AUSENTE,
        },
        nota="'Delegacia de Pato Branco' = DP de Pato Branco do cadastro.",
    ),
    Caso(
        id="pub-030",
        modulo="publicacoes",
        formato="eml",
        agora="2026-11-03 11:00",
        texto=_eml(
            ("Juliana Portela Maciel", "juliana.maciel@exemplo.pr.gov.br"),
            _ASCOM,
            "DP Palmas - prisão em Clevelândia",
            "2026-11-03 10:10",
            """Bom dia!

Mais um material nosso para divulgação 😊 Fotos em anexo.

PCPR PRENDE CONDENADO POR ESTUPRO QUE SE ESCONDIA EM CLEVELÂNDIA

Investigadores da DP Palmas prenderam na segunda-feira (2), em Clevelândia, um homem de 48 anos condenado a 12 anos de prisão por estupro. Ele estava foragido desde 2024.

Juliana Portela Maciel
Escrivã de Polícia – DP Palmas
""",
            anexos=("prisao.jpg",),
        ),
        esperado={
            "titulo": Contem("condenado por estupro"),
            "unidade": "Delegacia de Polícia de Palmas",
            "fonte": Contem("Juliana Portela"),
            "data": "2026-11-03",
            "inicio_pauta": "10:10",
        },
        nota="Prisão em outra cidade (Clevelândia), unidade continua sendo a DP de Palmas.",
    ),
    Caso(
        id="pub-031",
        modulo="publicacoes",
        formato="texto",
        agora="2026-11-04 15:00",
        texto="""[04/11/2026 14:00] Wagner Tessaro: Boa tarde! Aqui é da Delegacia de Mangueirinha. Temos uma prisão pra divulgar
[04/11/2026 14:02] Wagner Tessaro: PCPR PRENDE SUSPEITO DE ABIGEATO EM MANGUEIRINHA

A Delegacia de Polícia de Mangueirinha, com apoio da Delegacia de Polícia de Palmas, prendeu nesta quarta-feira (4) um homem de 33 anos suspeito de furtar gado em propriedades do interior do município.
[04/11/2026 14:02] Wagner Tessaro: IMG-20261104-WA0015.jpg (arquivo anexado)""",
        esperado={
            "titulo": Contem("abigeato"),
            "unidade": AUSENTE,
            "unidade_nova": Contem("Mangueirinha"),
            "fonte": Contem("Wagner Tessaro"),
            "data": "2026-11-04",
            "inicio_pauta": "14:00",
        },
        nota="DP de Palmas (no cadastro) é só apoio; Mangueirinha, quem manda, não está cadastrada.",
    ),
    Caso(
        id="pub-032",
        modulo="publicacoes",
        formato="eml",
        agora="2026-11-05 12:00",
        texto=_eml(
            ("Ricardo Fontanella", "ricardo.fontanella@exemplo.pr.gov.br"),
            _ASCOM,
            "DEAM - apreensão de armas e munições - para publicação",
            "2026-11-05 11:25",
            """Bom dia,

Segue material para publicação.

PCPR APREENDE 40 ARMAS EM LOJA CLANDESTINA NA REGIÃO METROPOLITANA

A Delegacia de Explosivos, Armas e Munições (DEAM) apreendeu nesta quinta-feira (5) 40 armas de fogo e 12 mil munições em uma loja que funcionava sem autorização em Pinhais. O proprietário, de 55 anos, foi preso.

Ricardo Fontanella
Investigador – DEAM
""",
        ),
        esperado={
            "titulo": Contem("40 armas"),
            "unidade": AUSENTE,
            "unidade_nova": Contem("Explosivos, Armas e Munições"),
            "fonte": Contem("Ricardo Fontanella"),
            "data": "2026-11-05",
            "inicio_pauta": "11:25",
        },
        nota="DEAM aqui é Explosivos/Armas (fora do cadastro), não Delegacia da Mulher.",
    ),
    Caso(
        id="pub-033",
        modulo="publicacoes",
        formato="texto",
        agora="2026-11-11 09:00",
        texto="""Sugestão de título: PCPR prende quadrilha que furtava fios de cobre em Guarapuava

Texto:
A Delegacia de Polícia de Guarapuava prendeu nesta terça-feira (10) quatro homens suspeitos de furtar cabos de cobre da rede de telefonia e energia em ao menos 20 bairros da cidade. Cerca de 800 kg de fios foram recuperados em um ferro-velho.

Fonte: delegado Caio Remor Silvestri, DP Guarapuava.
Fotos: seguem no grupo.""",
        esperado={
            "titulo": Contem("fios de cobre"),
            "unidade": "Delegacia de Polícia de Guarapuava",
            "fonte": Contem("Caio Remor Silvestri"),
            "data": AUSENTE,
            "inicio_pauta": AUSENTE,
            "jornalista": AUSENTE,
        },
        nota="Texto puro com 'Sugestão de título' e 'Fonte:'; sem data de envio.",
    ),
    Caso(
        id="pub-034",
        modulo="publicacoes",
        formato="eml",
        agora="2026-11-06 18:30",
        texto=_eml(
            ("Priscila Ogliari", "priscila.ogliari@exemplo.pr.gov.br"),
            _ASCOM,
            "Operação Fronteira Limpa – 9ª SDP de Foz do Iguaçu",
            "2026-11-06 17:50",
            """Boa tarde, equipe!

Segue release da Operação Fronteira Limpa. Fotos em anexo (rostos borrados).

OPERAÇÃO FRONTEIRA LIMPA PRENDE 11 SUSPEITOS DE LAVAGEM DE DINHEIRO EM FOZ

A 9ª SDP de Foz do Iguaçu deflagrou nesta sexta-feira (6) a Operação Fronteira Limpa, que cumpriu 11 mandados de prisão e bloqueou R$ 3 milhões em contas de um grupo suspeito de lavar dinheiro do tráfico por meio de casas de câmbio.

"É um golpe no braço financeiro do crime organizado", disse o delegado.

Priscila Ogliari
Escrivã – 9ª SDP
Foz do Iguaçu/PR
""",
            cod="b",
            html=True,
            anexos=("fronteira1.jpg", "fronteira2.jpg"),
        ),
        esperado={
            "titulo": Contem("Fronteira Limpa"),
            "unidade": "9ª Subdivisão Policial de Foz do Iguaçu",
            "fonte": Contem("Priscila Ogliari"),
            "data": "2026-11-06",
            "inicio_pauta": "17:50",
        },
        nota="Subject base64 + HTML + anexos.",
    ),
    Caso(
        id="pub-035",
        modulo="publicacoes",
        formato="eml",
        agora="2026-11-09 09:00",
        texto=_eml(
            ("Renata Colussi Dalmolin", "renata.dalmolin@exemplo.pr.gov.br"),
            _ASCOM,
            "PCPR PRENDE SUSPEITO DE MATAR JOVEM A TIROS EM LONDRINA",
            "2026-11-09 08:05",
            """Bom dia. Release em anexo no corpo do e-mail. Favor publicar.

PCPR PRENDE SUSPEITO DE MATAR JOVEM A TIROS EM LONDRINA

A DH de Londrina prendeu no sábado (7) um homem de 20 anos suspeito de matar um jovem de 17 anos a tiros no Conjunto Vivi Xavier, em 25 de outubro.

Renata Colussi Dalmolin
Delegada de Polícia – DH Londrina
""",
        ),
        esperado={
            "titulo": Contem("matar jovem a tiros"),
            "unidade": "Delegacia de Homicídios de Londrina",
            "fonte": Contem("Renata Colussi"),
            "data": "2026-11-09",
            "inicio_pauta": "08:05",
            "jornalista": AUSENTE,
        },
        nota="Assunto em caixa alta; 'DH de Londrina' abreviado.",
    ),
    Caso(
        id="pub-036",
        modulo="publicacoes",
        formato="texto",
        agora="2026-11-09 16:30",
        texto="""[09/11/2026 15:33] Luana Pertile: Oi! Tudo bem?
[09/11/2026 15:33] Luana Pertile: áudio omitido
[09/11/2026 15:35] Luana Pertile: Resumindo o áudio: a Delegacia da Mulher de Maringá prendeu hoje um homem de 50 anos por stalking contra a ex-namorada, ele mandou mais de 300 mensagens e aparecia no trabalho dela
[09/11/2026 15:36] Luana Pertile: Dá pra fazer uma matéria? Título sugestão: PCPR prende homem por perseguição (stalking) em Maringá
[09/11/2026 15:36] Luana Pertile: Sem nomes!""",
        esperado={
            "titulo": Contem("stalking"),
            "unidade": "Delegacia da Mulher de Maringá",
            "fonte": Contem("Luana Pertile"),
            "data": "2026-11-09",
            "inicio_pauta": "15:33",
        },
        nota="Conversa informal com áudio omitido; título sugerido no meio da conversa.",
    ),
    Caso(
        id="pub-037",
        modulo="publicacoes",
        formato="eml",
        agora="2026-11-10 12:00",
        texto=_eml(
            ("Carla Bento", "carla.bento@exemplo.pr.gov.br"),
            _ASCOM,
            "Divulgação - Operação Laço de Proteção",
            "2026-11-10 10:44",
            """Bom dia!

Segue release para divulgação. Fotos em anexo.

OPERAÇÃO LAÇO DE PROTEÇÃO PRENDE 9 AGRESSORES EM CASCAVEL

A Delegacia da Mulher de Cascavel deflagrou nesta terça-feira (10) a Operação Laço de Proteção, com o cumprimento de nove mandados de prisão contra investigados por violência doméstica.

Carla Bento
Investigadora de Polícia
Delegacia da Mulher – 15ª SDP – Cascavel/PR
""",
            cc="Gabinete 15ª SDP <gabinete.15sdp@exemplo.pr.gov.br>",
            anexos=("laco1.jpg",),
        ),
        esperado={
            "titulo": Contem("Laço de Proteção"),
            "unidade": "Delegacia da Mulher de Cascavel",
            "fonte": Contem("Carla Bento"),
            "data": "2026-11-10",
            "inicio_pauta": "10:44",
        },
        nota="Assinatura e Cc citam a 15ª SDP; a unidade é a Delegacia da Mulher de Cascavel.",
    ),
    Caso(
        id="pub-038",
        modulo="publicacoes",
        formato="eml",
        agora="2026-11-11 17:00",
        texto=_eml(
            ("Gustavo Menegatti", "gustavo.menegatti@exemplo.pr.gov.br"),
            _ASCOM,
            "Divulgação: PCPR prende suspeito de agressão a idosa em Campo Mourão",
            "2026-11-11 16:16",
            """Boa tarde,

Segue para publicação no site.

PCPR PRENDE SUSPEITO DE AGREDIR IDOSA DE 82 ANOS EM CAMPO MOURÃO

A DP de Campo Mourão prendeu nesta quarta-feira (11) o neto de uma idosa de 82 anos, de 27 anos, suspeito de agredi-la e se apropriar da aposentadoria dela.

Gustavo Menegatti
Delegado de Polícia
""",
            cod="q",
            qp=True,
        ),
        esperado={
            "titulo": Contem("idosa"),
            "unidade": "Delegacia de Polícia de Campo Mourão",
            "fonte": Contem("Gustavo Menegatti"),
            "data": "2026-11-11",
            "inicio_pauta": "16:16",
            "jornalista": AUSENTE,
        },
        nota="Subject Q-encoded e corpo quoted-printable.",
    ),
    Caso(
        id="pub-039",
        modulo="publicacoes",
        formato="texto",
        agora="2026-11-12 10:00",
        texto=f"""De: Tatiane Grigolo Bassani
Enviado em: {_outlook("2026-11-12 09:12")}
Para: Imprensa PCPR
Assunto: Material p/ divulgação - Nuciber

Bom dia!

NUCIBER PRENDE HACKER QUE INVADIU CONTAS DE PREFEITURA

O NUCIBER prendeu nesta quinta-feira (12), em Maringá, um jovem de 21 anos suspeito de invadir o sistema de uma prefeitura do Norte do estado e desviar R$ 350 mil. A investigação teve apoio da Delegacia da Mulher de Maringá, que cedeu equipe para a abordagem.

Seguem fotos em anexo.

Tatiane Grigolo Bassani
Delegada de Polícia""",
        esperado={
            "titulo": Contem("hacker"),
            "unidade": "NUCIBER",
            "fonte": Contem("Tatiane Grigolo"),
            "data": "2026-11-12",
            "inicio_pauta": "09:12",
            "jornalista": AUSENTE,
        },
        nota="Delegacia da Mulher de Maringá (no cadastro) só apoiou.",
    ),
    Caso(
        id="pub-040",
        modulo="publicacoes",
        formato="eml",
        agora="2026-11-12 09:00",
        texto=_eml(
            ("Jéssica Sbardelotto", "jessica.sbardelotto@exemplo.pr.gov.br"),
            _ASCOM,
            "DP de União da Vitória - Operação Iguaçu - divulgação",
            "2026-11-12 07:30",
            """Bom dia!

Segue release e fotos (anexas) da Operação Iguaçu, deflagrada hoje cedo.

OPERAÇÃO IGUAÇU CUMPRE 12 MANDADOS CONTRA TRÁFICO EM UNIÃO DA VITÓRIA

A Delegacia de Polícia de União da Vitória deflagrou na manhã desta quinta-feira (12) a Operação Iguaçu, com 12 mandados de busca e cinco de prisão. A ação teve apoio do COPE e do canil da PCPR.

Jéssica Sbardelotto
Escrivã – DP de União da Vitória
""",
            anexos=("iguacu1.jpg", "iguacu2.jpg"),
        ),
        esperado={
            "titulo": Contem("Operação Iguaçu"),
            "unidade": "Delegacia de Polícia de União da Vitória",
            "fonte": Contem("Jéssica Sbardelotto"),
            "data": "2026-11-12",
            "inicio_pauta": "07:30",
        },
        nota="Inverso do pub-014: aqui o COPE é o apoio.",
    ),
    Caso(
        id="pub-041",
        modulo="publicacoes",
        formato="eml",
        agora="2026-11-13 15:30",
        texto=_eml(
            ("Patrícia Loyola Weber", "patricia.weber@exemplo.pr.gov.br"),
            _ASCOM,
            "DFRV - recuperação de caminhão roubado com carga",
            "2026-11-13 14:48",
            """Boa tarde!

Segue material pra publicação. Fotos anexas.

PCPR RECUPERA CAMINHÃO ROUBADO COM CARGA DE ELETRÔNICOS

A DFRV recuperou nesta sexta-feira (13) em Araucária um caminhão roubado na BR-116 com carga de eletrônicos avaliada em R$ 900 mil. O motorista havia sido mantido refém por seis horas. Um suspeito de 29 anos foi preso.

Patrícia Loyola Weber
Investigadora – DFRV
""",
            anexos=("caminhao.jpg",),
        ),
        esperado={
            "titulo": Contem("caminhão roubado"),
            "unidade": "Delegacia de Furtos e Roubos de Veículos",
            "fonte": Contem("Patrícia Loyola"),
            "data": "2026-11-13",
            "inicio_pauta": "14:48",
        },
        nota="Carga roubada, mas quem manda é a DFRV (não a Delegacia de Desvio de Cargas).",
    ),
    Caso(
        id="pub-042",
        modulo="publicacoes",
        formato="texto",
        agora="2026-11-16 10:00",
        texto="""[13/11/2026 18:20] Juliana Portela: Obrigada pela publicação de ontem!
[13/11/2026 18:25] Ascom PCPR: Imagina 🙏
[16/11/2026 09:02] Juliana Portela: Bom dia! Mais uma pra divulgar, da DP de Palmas
[16/11/2026 09:03] Juliana Portela: PCPR PRENDE DUPLA POR ROUBO A MERCADO EM PALMAS

Dois homens, de 19 e 22 anos, foram presos no domingo (15) suspeitos de roubar um mercado no bairro Lagoão, em Palmas. Parte do dinheiro foi recuperada.
[16/11/2026 09:03] Juliana Portela: IMG-20261116-WA0003.jpg (arquivo anexado)""",
        esperado={
            "titulo": Contem("roubo a mercado"),
            "unidade": "Delegacia de Polícia de Palmas",
            "fonte": Contem("Juliana Portela"),
            "data": "2026-11-16",
            "inicio_pauta": "09:02",
        },
        nota="Conversa começa dias antes (13/11) com assunto velho; a pauta é a de 16/11.",
    ),
    Caso(
        id="pub-043",
        modulo="publicacoes",
        formato="eml",
        agora="2026-11-17 12:00",
        texto=_eml(
            ("Anderson Klein Moraes", "anderson.moraes@exemplo.pr.gov.br"),
            _ASCOM,
            "Golpe contra idosos - para divulgação (sem nomes das vítimas)",
            "2026-11-17 14:00",
            """Bom dia,

Segue release. Pedimos não divulgar os nomes das vítimas.

PCPR PRENDE GRUPO QUE APLICAVA GOLPE DO CARTÃO CLONADO EM IDOSOS

A Delegacia de Estelionato e Desvio de Cargas prendeu nesta terça-feira (17) três suspeitos de aplicar o golpe do "funcionário do banco" contra idosos em Curitiba. O prejuízo estimado é de R$ 480 mil.

Anderson Klein Moraes
Investigador de Polícia
""",
            tz="+0000",
        ),
        esperado={
            "titulo": Contem("golpe"),
            "unidade": "Delegacia de Estelionato e Desvio de Cargas",
            "fonte": Contem("Anderson Klein"),
            "data": "2026-11-17",
            "inicio_pauta": "11:00",
        },
        nota="Date em +0000: 14:00 UTC = 11:00 em Brasília.",
    ),
    Caso(
        id="pub-044",
        modulo="publicacoes",
        formato="texto",
        agora="2026-11-18 08:30",
        texto="""PARA DIVULGAÇÃO

POLÍCIA CIVIL DE IRATI PRENDE SUSPEITO DE ASSALTO A POSTO DE COMBUSTÍVEIS

Irati, 17 de novembro de 2026 – A Delegacia de Polícia de Irati prendeu nesta terça-feira um homem de 25 anos suspeito de assaltar um posto de combustíveis na PR-153 no dia 8. Ele foi reconhecido pelas câmeras de segurança.

Mais informações com o delegado Paulo Roberto Dambros.""",
        esperado={
            "titulo": Contem("posto de combustíveis"),
            "unidade": "Delegacia de Polícia de Irati",
            "data": AUSENTE,
            "inicio_pauta": AUSENTE,
        },
        nota="'Irati, 17 de novembro' é dateline do release, não o recebimento da pauta.",
    ),
    Caso(
        id="pub-045",
        modulo="publicacoes",
        formato="eml",
        agora="2026-11-18 17:00",
        texto=_eml(
            ("Luciano Hartmann Pires", "luciano.pires@exemplo.pr.gov.br"),
            _ASCOM,
            "segue material para divulgação",
            "2026-11-18 16:40",
            """segue material para divulgação

Operação Divisa: cumprimos hoje 6 mandados de busca em Rio Negro e Mafra (SC) contra receptadores de motos furtadas, com apoio da Polícia Civil de SC. 2 presos, 14 motos recuperadas.

Luciano Hartmann Pires
Delegado – DP Rio Negro

Enviado do meu iPhone
""",
            anexos=("divisa1.jpg", "divisa2.jpg"),
        ),
        esperado={
            "titulo": Contem("Operação Divisa"),
            "unidade": "Delegacia de Polícia de Rio Negro",
            "fonte": Contem("Luciano Hartmann"),
            "data": "2026-11-18",
            "inicio_pauta": "16:40",
            "jornalista": AUSENTE,
        },
        nota="Assunto genérico; título a partir do nome da operação; motos não apontam para a DFRV.",
    ),
    Caso(
        id="pub-046",
        modulo="publicacoes",
        formato="texto",
        agora="2026-11-19 08:00",
        texto="""[18/11/2026 23:58] Adilson Groff DP Ortigueira: Boa noite, desculpe o horário. Segue release para amanhã
[18/11/2026 23:59] Adilson Groff DP Ortigueira: PCPR PRENDE HOMEM QUE MANTINHA ESPOSA EM CÁRCERE PRIVADO EM ORTIGUEIRA

Uma mulher de 37 anos foi resgatada nesta quarta-feira (18) pela Polícia Civil em uma casa na zona rural de Ortigueira, onde era mantida trancada pelo marido, de 44 anos, que foi preso.
[19/11/2026 00:01] Adilson Groff DP Ortigueira: <anexado: 00000077-PHOTO-2026-11-19-00-01-12.jpg>""",
        esperado={
            "titulo": Contem("cárcere privado"),
            "unidade": "Delegacia de Polícia de Ortigueira",
            "fonte": Contem("Adilson Groff"),
            "data": "2026-11-18",
            "inicio_pauta": "23:58",
        },
        nota="Mensagens viram a meia-noite; início é 18/11 23:58, não 19/11.",
    ),
    Caso(
        id="pub-047",
        modulo="publicacoes",
        formato="texto",
        agora="2026-11-20 08:00",
        texto="""19/11/2026 20:12 - Diego Farinon DHPP: Boa noite! Material pra divulgar amanhã
19/11/2026 20:12 - Diego Farinon DHPP: DHPP PRENDE SUSPEITO DE MATAR ENTREGADOR EM CURITIBA

Um homem de 31 anos foi preso nesta quinta-feira (19) pela DHPP, suspeito de matar um entregador por aplicativo após uma discussão de trânsito no bairro Boqueirão, em 3 de novembro.
19/11/2026 20:13 - Diego Farinon DHPP: <Mídia oculta>""",
        esperado={
            "titulo": Contem("entregador"),
            "unidade": "DHPP",
            "fonte": Contem("Diego Farinon"),
            "data": "2026-11-19",
            "inicio_pauta": "20:12",
        },
        nota="Android; 'divulgar amanhã' não muda a data da pauta.",
    ),
    Caso(
        id="pub-048",
        modulo="publicacoes",
        formato="eml",
        agora="2026-11-20 10:00",
        texto=_eml(
            ("Otávio Brandalise", "otavio.brandalise@exemplo.pr.gov.br"),
            _ASCOM,
            "Operação Colheita Segura - DP Pato Branco",
            "2026-11-20 09:09",
            """Bom dia,

Segue release para divulgação no site e redes. Fotos em anexo.

OPERAÇÃO COLHEITA SEGURA RECUPERA MÁQUINAS AGRÍCOLAS FURTADAS NO SUDOESTE

A Delegacia de Polícia de Pato Branco deflagrou nesta sexta-feira (20) a Operação Colheita Segura e recuperou três colheitadeiras e um trator furtados em Palmas, Clevelândia e Coronel Vivida. Três homens foram presos.

Otávio Brandalise
Delegado de Polícia
""",
            html=True,
            anexos=("colheita.jpg",),
        ),
        esperado={
            "titulo": Contem("Colheita Segura"),
            "unidade": "Delegacia de Polícia de Pato Branco",
            "fonte": Contem("Otávio Brandalise"),
            "data": "2026-11-20",
            "inicio_pauta": "09:09",
            "jornalista": AUSENTE,
        },
        nota="Palmas citada como local dos furtos não é a unidade.",
    ),
    Caso(
        id="pub-049",
        modulo="publicacoes",
        formato="eml",
        agora="2026-11-23 14:30",
        texto=_eml(
            ("Débora Zanatta", "debora.zanatta@exemplo.pr.gov.br"),
            _ASCOM,
            "Pedido de divulgação - DP Coronel Vivida",
            "2026-11-23 13:37",
            """Boa tarde!

Segue para divulgação. A investigação foi coordenada com a Delegacia de Pato Branco.

PCPR PRENDE SUSPEITO DE MATAR IRMÃO EM CORONEL VIVIDA

A Delegacia de Polícia de Coronel Vivida prendeu no domingo (22) um homem de 35 anos suspeito de matar o irmão a golpes de faca durante uma briga familiar.

Débora Zanatta
Escrivã de Polícia
DP de Coronel Vivida
""",
        ),
        esperado={
            "titulo": Contem("matar irmão"),
            "unidade": AUSENTE,
            "unidade_nova": Contem("Coronel Vivida"),
            "fonte": Contem("Débora Zanatta"),
            "data": "2026-11-23",
            "inicio_pauta": "13:37",
        },
        nota="Coronel Vivida fora do cadastro; Pato Branco (cadastrada) é só coordenação.",
    ),
    Caso(
        id="pub-050",
        modulo="publicacoes",
        formato="texto",
        agora="2026-11-24 10:00",
        texto=f"""De: Fernanda Zortéa <fernanda.zortea@exemplo.pr.gov.br>
Enviado em: {_outlook("2026-11-24 08:55")}
Para: Ascom PCPR <ascom.pautas@exemplo.pr.gov.br>
Assunto: 13ª Subdivisão Policial - Operação Tropeiro

Bom dia!

Segue o release da Operação Tropeiro para publicação. Fotos seguem por WhatsApp.

OPERAÇÃO TROPEIRO DESARTICULA GRUPO DE FURTO DE CARGAS DE MADEIRA NOS CAMPOS GERAIS

A 13ª Subdivisão Policial cumpriu nesta terça-feira (24) sete mandados de busca em Ponta Grossa, Castro e Telêmaco Borba contra um grupo suspeito de desviar cargas de madeira. A Delegacia de Estelionato e Desvio de Cargas colaborou com informações.

Fernanda Zortéa
Investigadora de Polícia""",
        esperado={
            "titulo": Contem("Operação Tropeiro"),
            "unidade": "13ª Subdivisão Policial de Ponta Grossa",
            "fonte": Contem("Fernanda Zortéa"),
            "data": "2026-11-24",
            "inicio_pauta": "08:55",
        },
        nota="Delegacia de Desvio de Cargas só colaborou.",
    ),
    Caso(
        id="pub-051",
        modulo="publicacoes",
        formato="texto",
        agora="2026-11-25 08:00",
        texto=f"""De: Caio Remor Silvestri <caio.silvestri@exemplo.pr.gov.br>
Enviado em: {_outlook("2026-11-24 18:20")}
Para: ascom.pautas@exemplo.pr.gov.br
Assunto: Guarapuava - prisão de estelionatário

Boa noite, favor publicar.

PCPR PRENDE ESTELIONATÁRIO QUE APLICOU GOLPE DO FALSO EMPRÉSTIMO EM 60 PESSOAS

A Delegacia de Polícia de Guarapuava prendeu nesta terça-feira (24) um homem de 41 anos suspeito de oferecer empréstimos falsos a aposentados. O prejuízo passa de R$ 200 mil.

Caio Remor Silvestri
Delegado de Polícia
DP Guarapuava

Enviado do meu iPhone""",
        esperado={
            "titulo": Contem("falso empréstimo"),
            "unidade": "Delegacia de Polícia de Guarapuava",
            "fonte": Contem("Caio Remor"),
            "data": "2026-11-24",
            "inicio_pauta": "18:20",
            "jornalista": AUSENTE,
        },
        nota="Estelionato praticado, mas a unidade é a DP de Guarapuava (não a Delegacia de Estelionato).",
    ),
    Caso(
        id="pub-052",
        modulo="publicacoes",
        formato="eml",
        agora="2026-11-25 11:00",
        texto=_eml(
            ("Nucria Curitiba", "nucria.cartorio@exemplo.pr.gov.br"),
            _ASCOM,
            "Para divulgação - Nucria",
            "2026-11-25 10:00",
            f"""Prezados,

Encaminhamos release para divulgação. Não divulgar nomes, idades das vítimas ou bairro.

PCPR PRENDE HOMEM POR ARMAZENAR MATERIAL DE ABUSO SEXUAL INFANTIL

O Núcleo de Proteção à Criança e ao Adolescente Vítimas de Crimes (Nucria) de Curitiba prendeu em flagrante nesta quarta-feira (25) um homem de 45 anos que armazenava milhares de arquivos de abuso sexual infantil. A investigação começou a partir de informações do NUCIBER.

Inv. Marina Costella Viero
Nucria – Curitiba

{_SIGILO}
""",
        ),
        esperado={
            "titulo": Contem("abuso sexual infantil"),
            "unidade": "NUCRIA de Curitiba",
            "fonte": Contem("Marina Costella"),
            "data": "2026-11-25",
            "inicio_pauta": "10:00",
        },
        nota="NUCIBER deu as informações, mas quem manda é o Nucria.",
    ),
    Caso(
        id="pub-053",
        modulo="publicacoes",
        formato="texto",
        agora="2026-11-25 15:00",
        texto="""[25/11/2026 14:26] Everton Sachet 9ª SDP: Boa tarde, favor divulgar
[25/11/2026 14:27] Everton Sachet 9ª SDP: PCPR prende em Foz suspeito de matar comerciante paraguaio

A 9ª SDP prendeu nesta quarta-feira (25) um homem de 28 anos suspeito de matar um comerciante durante assalto em 15 de novembro, na Vila Portes, em Foz do Iguaçu.
[25/11/2026 14:27] Everton Sachet 9ª SDP: IMG-20261125-WA0021.jpg (arquivo anexado)""",
        esperado={
            "titulo": Contem("comerciante"),
            "unidade": "9ª Subdivisão Policial de Foz do Iguaçu",
            "fonte": Contem("Everton Sachet"),
            "data": "2026-11-25",
            "inicio_pauta": "14:26",
        },
        nota="Título em caixa normal; crime em 15/11.",
    ),
    Caso(
        id="pub-054",
        modulo="publicacoes",
        formato="eml",
        agora="2026-11-26 16:00",
        texto=_eml(
            ("Leandro Scussel", "leandro.scussel@exemplo.pr.gov.br"),
            _ASCOM,
            "Divisão Estadual de Narcóticos - laboratório de drogas",
            "2026-11-26 15:15",
            """Boa tarde, pessoal.

Segue release para divulgação. Fotos em anexo.

PCPR DESCOBRE LABORATÓRIO DE REFINO DE COCAÍNA EM CHÁCARA DE MANDIRITUBA

A Divisão Estadual de Narcóticos descobriu nesta quinta-feira (26) um laboratório de refino de cocaína em uma chácara em Mandirituba. Foram apreendidos 35 kg da droga e produtos químicos. Dois homens foram presos.

Leandro Scussel
Investigador
""",
            html=True,
            anexos=("lab1.jpg", "lab2.jpg"),
        ),
        esperado={
            "titulo": Contem("laboratório"),
            "unidade": "DENARC",
            "fonte": Contem("Leandro Scussel"),
            "data": "2026-11-26",
            "inicio_pauta": "15:15",
        },
        nota="Nome por extenso da divisão = sigla DENARC do cadastro.",
    ),
    Caso(
        id="pub-055",
        modulo="publicacoes",
        formato="eml",
        agora="2026-11-27 09:00",
        texto=_eml(
            ("Helena Gaspari", "helena.gaspari.dm@exemplo.com.br"),
            _ASCOM,
            "Fwd: release DM Maringá",
            "2026-11-27 08:22",
            """Bom dia! Mandei do meu e-mail pessoal porque o institucional está fora do ar.

---------- Forwarded message ---------
De: Helena Gaspari <helena.gaspari.dm@exemplo.com.br>
Date: qui., 26 de nov. de 2026 às 22:10
Subject: release DM Maringá
To: Helena Gaspari <helena.gaspari.dm@exemplo.com.br>

PCPR PRENDE HOMEM QUE AGREDIU COMPANHEIRA GRÁVIDA EM MARINGÁ

A Delegacia da Mulher de Maringá prendeu na quinta-feira (26) um homem de 29 anos que agrediu a companheira, grávida de seis meses.

Helena Gaspari
Delegada de Polícia – Delegacia da Mulher de Maringá
""",
        ),
        esperado={
            "titulo": Contem("companheira grávida"),
            "unidade": "Delegacia da Mulher de Maringá",
            "fonte": Contem("Helena Gaspari"),
            "data": "2026-11-27",
            "inicio_pauta": "08:22",
            "jornalista": AUSENTE,
        },
        nota="Encaminhou para si mesma na véspera; a pauta entrou na Ascom em 27/11 08:22.",
    ),
    Caso(
        id="pub-056",
        modulo="publicacoes",
        formato="texto",
        agora="2026-11-30 09:00",
        texto="""DH DE LONDRINA PRENDE SUSPEITO DE MATAR MORADOR DE RUA

A Delegacia de Homicídios de Londrina prendeu na sexta-feira (27) um homem de 34 anos suspeito de matar a pauladas um morador de rua na região central, no dia 20.

"O crime foi gravado por câmeras e o suspeito foi identificado rapidamente", afirmou a delegada.

Por gentileza, publicar sem imagem do preso.""",
        esperado={
            "titulo": Contem("morador de rua"),
            "unidade": "Delegacia de Homicídios de Londrina",
            "data": AUSENTE,
            "inicio_pauta": AUSENTE,
        },
        nota="Release solto sem remetente nem data de envio.",
    ),
    Caso(
        id="pub-057",
        modulo="publicacoes",
        formato="texto",
        agora="2026-11-30 13:00",
        texto="""[30/11/2026 11:48] Gustavo Menegatti Del.: Segue para divulgação
[30/11/2026 11:48] Gustavo Menegatti Del.: PCPR CUMPRE MANDADO CONTRA SUSPEITO DE ESTUPRO EM CAMPO MOURÃO

A Delegacia de Polícia de Campo Mourão prendeu nesta segunda-feira (30) um homem de 40 anos investigado por estupro. O mandado foi expedido pela Vara Criminal de Maringá, onde a vítima registrou o boletim na Delegacia da Mulher de Maringá.""",
        esperado={
            "titulo": Contem("estupro em Campo Mourão"),
            "unidade": "Delegacia de Polícia de Campo Mourão",
            "fonte": Contem("Gustavo Menegatti"),
            "data": "2026-11-30",
            "inicio_pauta": "11:48",
            "jornalista": AUSENTE,
        },
        nota="Delegacia da Mulher de Maringá citada só como origem do BO.",
    ),
    Caso(
        id="pub-058",
        modulo="publicacoes",
        formato="texto",
        agora="2026-12-01 10:00",
        texto="""[01/12/2026 09:31] Vanessa Trevisan Furtos e Roubos: Bom dia! Material pra divulgar
[01/12/2026 09:31] Vanessa Trevisan Furtos e Roubos: PCPR PRENDE SUSPEITOS DE ARROMBAR LOJAS DE CELULAR NO CENTRO DE CURITIBA

A Delegacia de Furtos e Roubos prendeu nesta terça-feira (1º) três homens suspeitos de arrombar ao menos oito lojas de celulares no Centro de Curitiba desde outubro.
[01/12/2026 09:32] Vanessa Trevisan Furtos e Roubos: <anexado: 00000102-PHOTO-2026-12-01-09-32-00.jpg>""",
        esperado={
            "titulo": Contem("lojas de celular"),
            "unidade": "Delegacia de Furtos e Roubos",
            "fonte": Contem("Vanessa Trevisan"),
            "data": "2026-12-01",
            "inicio_pauta": "09:31",
        },
        nota="'Furtos e Roubos' sem 'de Veículos': é a DFR.",
    ),
    Caso(
        id="pub-059",
        modulo="publicacoes",
        formato="eml",
        agora="2026-12-02 08:00",
        texto=_eml(
            ("Leandro Scussel", "leandro.scussel@exemplo.pr.gov.br"),
            _ASCOM,
            "DENARC/COPE - Operação Maré Branca",
            "2026-12-02 06:40",
            """Bom dia, segue material da operação em andamento. Fotos em anexo.

OPERAÇÃO MARÉ BRANCA MIRA REDE DE DISTRIBUIÇÃO DE COCAÍNA EM CURITIBA E LITORAL

A DENARC deflagrou na madrugada desta quarta-feira (2), em ação conjunta com o COPE, a Operação Maré Branca, que cumpre 22 mandados de busca e 10 de prisão em Curitiba, Paranaguá e Matinhos.

Leandro Scussel
Investigador – DENARC
""",
            anexos=("mare1.jpg",),
        ),
        esperado={
            "titulo": Contem("Maré Branca"),
            "unidade": "DENARC",
            "fonte": Contem("Leandro Scussel"),
            "data": "2026-12-02",
            "inicio_pauta": "06:40",
        },
        nota="Assunto cita DENARC/COPE; o COPE é conjunto, quem manda e conduz é a DENARC.",
    ),
    Caso(
        id="pub-060",
        modulo="publicacoes",
        formato="eml",
        agora="2026-12-03 08:00",
        texto=_eml(
            ("Sérgio Zanella", "sergio.zanella@exemplo.pr.gov.br"),
            _ASCOM,
            "Irati - apreensão de drogas em ônibus",
            "2026-12-03 02:15",
            """Boa noite, segue para publicação.

PCPR APREENDE 8 KG DE SKUNK EM ÔNIBUS INTERESTADUAL EM IRATI

Policiais civis de Irati apreenderam na noite desta quarta-feira (2) 8 kg de skunk na bagagem de uma passageira de 23 anos, em um ônibus que seguia de Foz do Iguaçu para Curitiba.

Sérgio Zanella
Investigador – DP Irati
""",
            tz="+0000",
        ),
        esperado={
            "titulo": Contem("skunk"),
            "unidade": "Delegacia de Polícia de Irati",
            "fonte": Contem("Sérgio Zanella"),
            "data": "2026-12-02",
            "inicio_pauta": "23:15",
        },
        nota="Date 02:15 +0000 do dia 3 = 23:15 do dia 2 em Brasília; Foz citada só como origem do ônibus.",
    ),
    Caso(
        id="pub-061",
        modulo="publicacoes",
        formato="texto",
        agora="2026-12-03 16:00",
        texto=f"""De: Luciano Hartmann Pires <luciano.pires@exemplo.pr.gov.br>
Enviado em: {_outlook("2026-12-03 14:42")}
Para: Ascom PCPR
Assunto: RES: Divulgação Rio Negro

Segue o texto revisado, pode publicar:

PCPR PRENDE SUSPEITO DE FURTOS EM IGREJAS DE RIO NEGRO E CAMPO DO TENENTE

A Delegacia de Polícia de Rio Negro prendeu nesta quinta-feira (3) um homem de 30 anos suspeito de furtar objetos sacros de cinco igrejas da região em novembro.

Luciano Hartmann Pires
Delegado de Polícia""",
        esperado={
            "titulo": Contem("igrejas"),
            "unidade": "Delegacia de Polícia de Rio Negro",
            "fonte": Contem("Luciano Hartmann"),
            "data": "2026-12-03",
            "inicio_pauta": "14:42",
            "jornalista": AUSENTE,
        },
        nota="Outlook colado com 'RES:'; data do envio certa.",
    ),
    Caso(
        id="pub-062",
        modulo="publicacoes",
        formato="eml",
        agora="2026-12-04 18:00",
        texto=_eml(
            ("Adilson Groff", "adilson.groff@exemplo.pr.gov.br"),
            _ASCOM,
            "Operação Serra Negra",
            "2026-12-04 17:05",
            """segue material da operação de hoje, fotos em anexo

Adilson Groff
Escrivão de Polícia
Delegacia de Polícia de Ortigueira
(42) 3277-0000
""",
            anexos=("serra_negra_1.jpg", "serra_negra_2.jpg"),
        ),
        esperado={
            "titulo": Contem("Serra Negra"),
            "unidade": "Delegacia de Polícia de Ortigueira",
            "fonte": Contem("Adilson Groff"),
            "data": "2026-12-04",
            "inicio_pauta": "17:05",
        },
        nota="Só o nome da operação no assunto; unidade na assinatura.",
    ),
    Caso(
        id="pub-063",
        modulo="publicacoes",
        formato="texto",
        agora="2026-12-07 11:00",
        texto="""[07/12/2026 10:10] Henrique Vasconi - Delegado Palmas: Bom dia. Release para divulgação:

PCPR PRENDE SUSPEITO DE TENTATIVA DE HOMICÍDIO EM FESTA NO INTERIOR DE PALMAS

A Polícia Civil prendeu no sábado (5) um homem de 23 anos suspeito de esfaquear dois jovens durante uma festa na localidade de Horizonte, interior de Palmas. As vítimas estão fora de perigo.

Henrique Vasconi Prado
Delegado de Polícia – DP Palmas
[07/12/2026 10:11] Henrique Vasconi - Delegado Palmas: Foto em anexo: fachada da DP""",
        esperado={
            "titulo": Contem("tentativa de homicídio"),
            "unidade": "Delegacia de Polícia de Palmas",
            "fonte": Contem("Henrique Vasconi"),
            "data": "2026-12-07",
            "inicio_pauta": "10:10",
            "jornalista": AUSENTE,
        },
        nota="Fato no sábado (5), mensagem em 07/12.",
    ),
    Caso(
        id="pub-064",
        modulo="publicacoes",
        formato="eml",
        agora="2026-12-08 13:00",
        texto=_eml(
            ("Fábio Guarienti", "fabio.guarienti@exemplo.pr.gov.br"),
            _ASCOM,
            "15ª SDP - homicídio esclarecido - divulgação",
            "2026-12-08 12:12",
            """Boa tarde,

Segue para divulgação.

PCPR ESCLARECE HOMICÍDIO DE AGRICULTOR EM CASCAVEL

A 15ª SDP prendeu nesta terça-feira (8) dois irmãos, de 26 e 31 anos, suspeitos de matar um agricultor em uma disputa por terras no distrito de Rio do Salto, em Cascavel, em 22 de novembro.

Fábio Guarienti
Delegado de Polícia – 15ª Subdivisão Policial
""",
        ),
        esperado={
            "titulo": Contem("agricultor"),
            "unidade": "15ª Subdivisão Policial de Cascavel",
            "fonte": Contem("Fábio Guarienti"),
            "data": "2026-12-08",
            "inicio_pauta": "12:12",
            "jornalista": AUSENTE,
        },
        nota="'15ª SDP' sem cidade no nome; crime em 22/11.",
    ),
    Caso(
        id="pub-065",
        modulo="publicacoes",
        formato="texto",
        agora="2026-12-09 17:30",
        texto="""[09/12/2026 16:48] Simone Rech DM PG: Boa tarde! Segue da Delegacia da Mulher de PG para divulgar
[09/12/2026 16:49] Simone Rech DM PG: PCPR PRENDE HOMEM QUE DIVULGOU FOTOS ÍNTIMAS DA EX-NAMORADA EM PONTA GROSSA

Um homem de 27 anos foi preso nesta quarta-feira (9) pela Delegacia da Mulher de Ponta Grossa por divulgar fotos íntimas da ex-namorada em redes sociais. O celular dele foi apreendido.
[09/12/2026 16:49] Simone Rech DM PG: Não divulgar nome da vítima nem do autor""",
        esperado={
            "titulo": Contem("fotos íntimas"),
            "unidade": "Delegacia da Mulher de Ponta Grossa",
            "fonte": Contem("Simone Rech"),
            "data": "2026-12-09",
            "inicio_pauta": "16:48",
        },
        nota="'DM PG' abreviado; não é a 13ª SDP nem o NUCIBER.",
    ),
    Caso(
        id="pub-066",
        modulo="publicacoes",
        formato="texto",
        agora="2026-12-10 15:00",
        texto="""[10/12/2026 13:50] Anderson Klein Estelionato: Boa tarde. Para divulgação: PCPR prende falso corretor que vendeu o mesmo apartamento para 5 pessoas em Curitiba. A Delegacia de Estelionato prendeu hoje um homem de 44 anos; prejuízo de R$ 1,1 milhão. Fotos daqui a pouco.""",
        esperado={
            "titulo": Contem("falso corretor"),
            "unidade": "Delegacia de Estelionato e Desvio de Cargas",
            "fonte": Contem("Anderson Klein"),
            "data": "2026-12-10",
            "inicio_pauta": "13:50",
        },
        nota="Mensagem única; 'Delegacia de Estelionato' = cadastro completo.",
    ),
    Caso(
        id="pub-067",
        modulo="publicacoes",
        formato="eml",
        agora="2026-12-11 11:00",
        texto=_eml(
            ("Renata Colussi Dalmolin", "renata.dalmolin@exemplo.pr.gov.br"),
            _ASCOM,
            "Operação Réquiem – Homicídios Londrina – divulgação",
            "2026-12-11 09:55",
            """Bom dia,

Segue release da Operação Réquiem para publicação. Fotos em anexo.

OPERAÇÃO RÉQUIEM PRENDE SEIS SUSPEITOS DE EXECUÇÕES EM LONDRINA

A Delegacia de Homicídios de Londrina deflagrou nesta sexta-feira (11) a Operação Réquiem, com seis prisões de suspeitos de envolvimento em quatro execuções ocorridas entre agosto e outubro na Zona Sul. A DHPP de Curitiba compartilhou informações de inteligência.

Renata Colussi Dalmolin
Delegada de Polícia
""",
            cod="q",
            html=True,
            anexos=("requiem.jpg",),
        ),
        esperado={
            "titulo": Contem("Operação Réquiem"),
            "unidade": "Delegacia de Homicídios de Londrina",
            "fonte": Contem("Renata Colussi"),
            "data": "2026-12-11",
            "inicio_pauta": "09:55",
            "jornalista": AUSENTE,
        },
        nota="DHPP citada só por inteligência compartilhada.",
    ),
    Caso(
        id="pub-068",
        modulo="publicacoes",
        formato="texto",
        agora="2026-12-14 16:00",
        texto="""[14/12/2026 15:05] Tatiane Grigolo NUCIBER: Boa tarde! Pode divulgar?

ALERTA DE GOLPE: PCPR ORIENTA SOBRE FALSOS SITES DE PROMOÇÃO DE NATAL

O NUCIBER identificou ao menos 30 sites falsos que simulam lojas conhecidas com descontos de Natal. Nesta segunda-feira (14), a unidade pediu a retirada das páginas do ar.
[14/12/2026 15:06] Tatiane Grigolo NUCIBER: Sem foto, pode usar arte de alerta""",
        esperado={
            "titulo": Contem("sites"),
            "unidade": "NUCIBER",
            "fonte": Contem("Tatiane Grigolo"),
            "data": "2026-12-14",
            "inicio_pauta": "15:05",
            "jornalista": AUSENTE,
        },
        nota="Pauta de orientação (não prisão); sem foto.",
    ),
    Caso(
        id="pub-069",
        modulo="publicacoes",
        formato="texto",
        agora="2026-12-15 11:00",
        texto=f"""De: Cristiane Bortolini <cristiane.bortolini@exemplo.pr.gov.br>
Enviado em: {_outlook("2026-12-15 10:20")}
Para: Imprensa PCPR
Assunto: Guarapuava - foragido de Palmas preso

Bom dia!

Segue para divulgação. Fotos em anexo.

PCPR PRENDE EM GUARAPUAVA FORAGIDO PROCURADO POR HOMICÍDIO EM PALMAS

A Delegacia de Polícia de Guarapuava prendeu nesta segunda-feira (14) um homem de 37 anos que era procurado pela Delegacia de Polícia de Palmas por um homicídio cometido em 2023.

Cristiane Bortolini
Escrivã – DP Guarapuava""",
        esperado={
            "titulo": Contem("foragido"),
            "unidade": "Delegacia de Polícia de Guarapuava",
            "fonte": Contem("Cristiane Bortolini"),
            "data": "2026-12-15",
            "inicio_pauta": "10:20",
        },
        nota="DP de Palmas é quem procurava o foragido; quem prende e manda é Guarapuava.",
    ),
    Caso(
        id="pub-070",
        modulo="publicacoes",
        formato="texto",
        agora="2026-12-16 18:00",
        texto=f"""De: Maurício Sganzerla <mauricio.sganzerla@exemplo.pr.gov.br>
Enviado em: {_outlook("2026-12-16 17:25")}
Para: Ascom PCPR <ascom.pautas@exemplo.pr.gov.br>
Cc: Diego Farinon
Assunto: DHPP - balanço anual

Boa tarde,

Para divulgação:

DHPP ESCLARECE 82% DOS HOMICÍDIOS REGISTRADOS EM CURITIBA EM 2026

A Divisão de Homicídios e Proteção à Pessoa atingiu em 2026 o maior índice de esclarecimento de sua história: 82% dos casos registrados na capital até 30 de novembro tiveram autoria identificada.

Maurício Sganzerla
Delegado-chefe – DHPP

{_SIGILO}""",
        esperado={
            "titulo": Contem("82%"),
            "unidade": "DHPP",
            "fonte": Contem("Maurício Sganzerla"),
            "data": "2026-12-16",
            "inicio_pauta": "17:25",
            "jornalista": AUSENTE,
        },
        nota="Balanço (não prisão); escrivão em Cc não é a fonte; 30/11 é dado do texto.",
    ),
]
