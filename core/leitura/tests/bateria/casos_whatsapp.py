"""Bateria do WhatsApp: pedidos de imprensa e pautas de publicação.

Na assessoria da PCPR, os pedidos de jornalistas (entrevista, nota,
posicionamento, dados, sonora, com prazo) e o material das delegacias para
divulgar (release, fotos de operação, prisão, apreensão) chegam quase
sempre pelo WhatsApp. A pessoa exporta ou copia a conversa e cola na tela.
Todos os nomes, veículos, telefones e e-mails são inventados; suspeitos
nunca têm nome.

Formatos cobertos:

- exportação do Android: ``24/09/2026 14:32 - Fulano: texto`` (e ano curto
  ``24/09/26``), com ``<Mídia oculta>``, "áudio omitido" e linhas do
  sistema (criptografia, "criou o grupo", "adicionou");
- exportação do iPhone: ``[24/09/2026, 14:32:10] Fulano: texto`` (e
  ``[24/09/26 14:32:10]``), com o U+200E invisível no começo de algumas
  linhas, ``<anexado: ...jpg>`` e "imagem ocultada";
- WhatsApp Web copiado: ``[14:32, 24/09/2026] Fulano: texto``;
- texto de uma mensagem só, sem cabeçalho.

Convenções do gabarito (as mesmas de ``casos_atendimento_imprensa.py`` e
``casos_publicacoes.py``):

- imprensa: ``data``/``horario`` = carimbo da primeira mensagem do
  JORNALISTA com o pedido (nunca a resposta da Ascom, linha do sistema,
  cobrança dias depois ou o horário do prazo); ``deadline`` = só a data do
  prazo ou da veiculação; ``contato`` = telefone/e-mail do jornalista (o
  número do remetente sem nome salvo conta; o fixo da Ascom não);
- publicações: ``data``/``inicio_pauta`` = carimbo da mensagem que trouxe a
  pauta (não a data da prisão/operação, nem a foto que chegou depois da
  meia-noite); ``unidade`` = quem manda, não a parceira; ``fonte`` = o
  servidor que passou o material; ``jornalista`` nunca é o delegado.
"""

from . import AUSENTE, Caso, Contem, UmDe

_I = "atendimento_imprensa"
_P = "publicacoes"

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
        # novos desta bateria
        "TV Norte Paranaense",
        "Portal Maringá Agora",
    ],
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
        # novos desta bateria
        "Delegacia de Polícia de Paranaguá",
        "Delegacia de Polícia de Toledo",
    ],
}

_CRIPTO_ANDROID = (
    "As mensagens e as chamadas são protegidas com a criptografia de ponta a "
    "ponta e ficam somente entre você e os participantes desta conversa. Nem "
    "mesmo o WhatsApp pode ler ou ouvi-las. Toque para saber mais."
)
_CRIPTO_IPHONE = (
    "‎As mensagens e as chamadas são protegidas com a criptografia de "
    "ponta a ponta. Ninguém fora desta conversa, nem mesmo o WhatsApp, pode "
    "ler ou ouvi-las."
)

# ==========================================================================
# ATENDIMENTO À IMPRENSA
# ==========================================================================

_IMPRENSA = [
    Caso(
        id="wpi-001",
        modulo=_I,
        formato="texto",
        agora="2026-09-24 14:50",
        texto=f"""24/09/2026 14:30 - {_CRIPTO_ANDROID}
24/09/2026 14:32 - Ju Gazeta: Oi, boa tarde! Aqui é a Juliana Stadler, da Gazeta dos Campos
24/09/2026 14:32 - Ju Gazeta: Preciso de uma nota da PCPR sobre o incêndio criminoso no barracão de reciclagem em Castro, na madrugada de domingo (20)
24/09/2026 14:33 - Ju Gazeta: Fecho a edição às 18h de hoje
24/09/2026 14:41 - Ascom PCPR: Boa tarde, Juliana! Vamos verificar com a delegacia e te retornamos.""",
        esperado={
            "jornalista": Contem("Juliana Stadler"),
            "veiculo": "Gazeta dos Campos",
            "contato": AUSENTE,
            "pedido": Contem("incêndio criminoso"),
            "data": "2026-09-24",
            "horario": "14:32",
            "deadline": "2026-09-24",
        },
        nota="Android; 'Ju Gazeta' é o contato salvo; 14:30 é a linha da criptografia; domingo (20) é o fato.",
    ),
    Caso(
        id="wpi-002",
        modulo=_I,
        formato="texto",
        agora="2026-10-05 10:40",
        texto="""05/10/26 10:12 - +55 41 99876-5432: Bom dia! Aqui é o Henrique Dalla Costa, repórter da Rádio Planalto 98 FM
05/10/26 10:12 - +55 41 99876-5432: Queria uma sonora com o delegado responsável pela investigação do golpe do falso consórcio em São José dos Pinhais
05/10/26 10:13 - +55 41 99876-5432: A matéria entra no Jornal do Meio-Dia de amanhã
05/10/26 10:30 - Ascom PCPR: Bom dia, Henrique. Vamos acionar a delegacia e te retornamos.""",
        esperado={
            "jornalista": Contem("Henrique Dalla Costa"),
            "veiculo": "Rádio Planalto 98 FM",
            "contato": Contem("99876-5432"),
            "pedido": Contem("sonora com o delegado"),
            "data": "2026-10-05",
            "horario": "10:12",
            "deadline": "2026-10-06",
        },
        nota="Android ano curto; número sem nome salvo é o contato; veiculação amanhã = 06/10.",
    ),
    Caso(
        id="wpi-003",
        modulo=_I,
        formato="texto",
        agora="2026-10-12 08:15",
        texto=f"""‎[12/10/2026, 07:58:12] Renata TV Iguaçu: {_CRIPTO_IPHONE}
[12/10/2026, 07:58:41] Renata TV Iguaçu: Bom dia! Renata Kloss, da TV Iguaçu Canal 8 🙋‍♀️
[12/10/2026, 07:59:03] Renata TV Iguaçu: Recebemos essa foto de uma apreensão de cigarros contrabandeados na PR-317, em Santa Helena
‎[12/10/2026, 07:59:10] Renata TV Iguaçu: ‎<anexado: 00000031-PHOTO-2026-10-12-07-59-10.jpg>
[12/10/2026, 08:00:22] Renata TV Iguaçu: Vcs conseguem confirmar se foi a Polícia Civil e mandar imagens oficiais da apreensão? Preciso até as 11h pro jornal do almoço""",
        esperado={
            "jornalista": Contem("Renata Kloss"),
            "veiculo": "TV Iguaçu Canal 8",
            "contato": AUSENTE,
            "pedido": Contem("imagens oficiais da apreensão"),
            "data": "2026-10-12",
            "horario": "07:58",
            "deadline": "2026-10-12",
        },
        nota="iPhone com U+200E e anexo; 11h é prazo (hoje), não o horário; 07:58:12 é a linha da criptografia mas o mesmo minuto.",
    ),
    Caso(
        id="wpi-004",
        modulo=_I,
        formato="texto",
        agora="2026-11-07 16:45",
        texto="""[07/11/26 16:20:05] Produção Diário do Oeste: Boa tarde, Ascom
[07/11/26 16:20:48] Produção Diário do Oeste: Aqui é da produção do Jornal Diário do Oeste. Precisamos do número de homicídios registrados em Toledo de janeiro a outubro deste ano, comparando com o mesmo período de 2025
[07/11/26 16:21:30] Produção Diário do Oeste: Pode ser até segunda, a matéria sai na terça 📊
‎[07/11/26 16:40:12] Ascom PCPR: Boa tarde! Vamos solicitar à Coordenação de Análise e mandamos até segunda.""",
        esperado={
            "jornalista": AUSENTE,
            "veiculo": "Jornal Diário do Oeste",
            "contato": AUSENTE,
            "pedido": Contem("número de homicídios"),
            "data": "2026-11-07",
            "horario": "16:20",
            "deadline": UmDe("2026-11-09", "2026-11-10"),
        },
        nota="iPhone ano curto; 'produção' sem nome: jornalista não se inventa; sábado → segunda 09 (prazo) ou terça 10 (veiculação).",
    ),
    Caso(
        id="wpi-005",
        modulo=_I,
        formato="texto",
        agora="2026-09-17 15:00",
        texto="""[14:32, 17/09/2026] Diego Anhaia: Boa tarde. Sou Diego Anhaia, do Portal Curitiba em Pauta
[14:32, 17/09/2026] Diego Anhaia: Leitores relatam demora de mais de 6 horas para registrar flagrante na Central de Flagrantes no último fim de semana. A PCPR tem algum posicionamento?
[14:33, 17/09/2026] Diego Anhaia: Assim que puder me retorna, obrigado
[14:51, 17/09/2026] Assessoria PCPR: Olá, Diego. Estamos levantando as informações.""",
        esperado={
            "jornalista": Contem("Diego Anhaia"),
            "veiculo": "Portal Curitiba em Pauta",
            "contato": AUSENTE,
            "pedido": Contem("posicionamento"),
            "data": "2026-09-17",
            "horario": "14:32",
            "deadline": AUSENTE,
        },
        nota="WhatsApp Web (hora antes da data); 'assim que puder' não é prazo; '6 horas' não é horário.",
    ),
    Caso(
        id="wpi-006",
        modulo=_I,
        formato="texto",
        agora="2026-08-13 16:10",
        texto="""Olá, boa tarde! Sou a Patrícia Hoffmann, da Rádio Educadora AM. Gostaria de uma entrevista ao vivo com a delegada da Delegacia da Mulher de Ponta Grossa sobre a campanha Agosto Lilás, amanhã às 7h30, no programa Educadora Notícias. Meu número é (42) 99911-3040. Obrigada!""",
        esperado={
            "jornalista": Contem("Patrícia Hoffmann"),
            "veiculo": "Rádio Educadora AM",
            "contato": Contem("99911-3040"),
            "pedido": Contem("entrevista ao vivo"),
            "horario": AUSENTE,
            "deadline": "2026-08-14",
        },
        nota="Texto de uma mensagem só, sem carimbo: 7h30 é a entrevista, não o horário do pedido; 'amanhã' pelo agora.",
    ),
    Caso(
        id="wpi-007",
        modulo=_I,
        formato="texto",
        agora="2026-09-02 10:30",
        texto="""02/09/2026 09:58 - Sabrina Produção TVPS criou o grupo "Pauta furtos Água Verde"
02/09/2026 09:58 - Sabrina Produção TVPS adicionou você
02/09/2026 09:59 - Sabrina Produção TVPS adicionou Gustavo Lenz
02/09/2026 10:03 - Sabrina Produção TVPS: Bom dia, Ascom! Sou a Sabrina, produtora da TV Paraná Sul. Criei o grupo pra facilitar
02/09/2026 10:03 - Sabrina Produção TVPS: O repórter Gustavo Lenz está fazendo uma matéria sobre a onda de furtos a residências no Água Verde e gostaria de gravar entrevista com o delegado da área
02/09/2026 10:04 - Sabrina Produção TVPS: Contato: Gustavo Lenz TV Paraná Sul
+55 41 99702-5518
02/09/2026 10:05 - Gustavo Lenz: Bom dia! Poderia ser amanhã (quinta) de manhã? A reportagem vai ao ar quinta à noite
02/09/2026 10:20 - Ascom PCPR: Bom dia! Vamos verificar a agenda do delegado.""",
        esperado={
            "jornalista": Contem("Gustavo Lenz"),
            "veiculo": "TV Paraná Sul",
            "contato": Contem("99702-5518"),
            "pedido": Contem("entrevista com o delegado"),
            "data": "2026-09-02",
            "horario": "10:03",
            "deadline": "2026-09-03",
        },
        nota="Grupo criado pela produtora; linhas do sistema às 09:58/09:59 não são o pedido; jornalista é o repórter (cartão de contato).",
    ),
    Caso(
        id="wpi-008",
        modulo=_I,
        formato="texto",
        agora="2026-10-31 07:10",
        texto="""30/10/2026 23:47 - Beto Plantão Rádio Cidade: Boa noite, desculpa o horário
30/10/2026 23:47 - Beto Plantão Rádio Cidade: Aqui é o Roberto Nascimento, do plantão da Rádio Cidade FM. Chegou pra gente que houve um homicídio agora há pouco no bairro Maracanã, em Colombo. A Civil já está no local? Tem alguma informação?
30/10/2026 23:52 - Beto Plantão Rádio Cidade: <Mídia oculta>
31/10/2026 00:06 - Beto Plantão Rádio Cidade: Preciso de algo até as 6h pro primeiro jornal da manhã 🙏
31/10/2026 00:40 - Ascom PCPR: Boa noite, Roberto. A equipe da Delegacia de Colombo está no local, assim que tivermos informações repassamos.""",
        esperado={
            "jornalista": Contem("Roberto Nascimento"),
            "veiculo": "Rádio Cidade FM",
            "contato": AUSENTE,
            "pedido": Contem("homicídio"),
            "data": "2026-10-30",
            "horario": "23:47",
            "deadline": "2026-10-31",
        },
        nota="Atravessa a meia-noite: pedido em 30/10 23:47; prazo 6h é do dia 31.",
    ),
    Caso(
        id="wpi-009",
        modulo=_I,
        formato="texto",
        agora="2026-11-04 16:00",
        texto="""[09:10, 02/11/2026] Carol Folha Norte: Bom dia! Carolina Brisola, da Folha do Norte Pioneiro
[09:10, 02/11/2026] Carol Folha Norte: Estou fazendo um especial sobre desaparecimentos em Jacarezinho e gostaria de entrevistar o delegado titular. Preciso fechar o material até sexta
[09:32, 02/11/2026] Ascom PCPR: Bom dia, Carolina! Vamos pedir a agenda
[15:47, 04/11/2026] Carol Folha Norte: Oi! Alguma novidade sobre a entrevista? 😅""",
        esperado={
            "jornalista": Contem("Carolina Brisola"),
            "veiculo": "Folha do Norte Pioneiro",
            "contato": AUSENTE,
            "pedido": Contem("entrevistar o delegado titular"),
            "data": "2026-11-02",
            "horario": "09:10",
            "deadline": "2026-11-06",
        },
        nota="Cobrança em 04/11 não é novo pedido; 'sexta' contada de segunda 02/11.",
    ),
    Caso(
        id="wpi-010",
        modulo=_I,
        formato="texto",
        agora="2026-08-18 11:30",
        texto="""18/08/26 11:02 - +55 42 98821-7766: áudio omitido
18/08/26 11:02 - +55 42 98821-7766: (áudio transcrito) Oi, bom dia, aqui é o Vinícius Prado, do Jornal Tribuna Ponta-grossense. Eu queria saber se vocês têm os dados de roubo de carga na BR-376 no primeiro semestre, lá na região dos Campos Gerais. É pra uma matéria de domingo, se puder mandar até sexta eu agradeço.
18/08/26 11:15 - Ascom PCPR: Oi, Vinícius! Vamos solicitar os dados.""",
        esperado={
            "jornalista": Contem("Vinícius Prado"),
            "veiculo": "Jornal Tribuna Ponta-grossense",
            "contato": Contem("98821-7766"),
            "pedido": Contem("roubo de carga"),
            "data": "2026-08-18",
            "horario": "11:02",
            "deadline": UmDe("2026-08-21", "2026-08-23"),
        },
        nota="Áudio transcrito de número sem nome; terça 18 → sexta 21 (prazo) ou domingo 23 (veiculação).",
    ),
    Caso(
        id="wpi-011",
        modulo=_I,
        formato="texto",
        agora="2026-09-21 13:30",
        texto="""[21/09/2026, 13:05:17] Everton Blog Fronteira: Boa tarde! Everton Schaefer, editor do blog Fronteira em Foco, de Guaíra
[21/09/2026, 13:05:59] Everton Blog Fronteira: Gostaria de uma nota da PCPR sobre a prisão de dois homens com armas na balsa ontem. Contato: everton@fronteiraemfoco.blog.br
‎[21/09/2026, 13:20:44] Ascom PCPR: Boa tarde, Everton. Vamos verificar.""",
        esperado={
            "jornalista": Contem("Everton Schaefer"),
            "veiculo": AUSENTE,
            "veiculo_novo": Contem("Fronteira em Foco"),
            "contato": Contem("everton@fronteiraemfoco.blog.br"),
            "pedido": Contem("nota da PCPR"),
            "data": "2026-09-21",
            "horario": "13:05",
            "deadline": AUSENTE,
        },
        nota="Blog fora do cadastro (não é a Revista Segurança em Foco); 'ontem' é o fato; sem prazo.",
    ),
    Caso(
        id="wpi-012",
        modulo=_I,
        formato="texto",
        agora="2026-12-09 16:20",
        texto="""[16:03, 09/12/2026] Ale Portal Notícias Já: Encaminhada
URGENTE!!! Polícia Civil prende quadrilha que clonava cartões em shopping de Curitiba, mais de 40 cartões apreendidos 🚨🚨
[16:03, 09/12/2026] Ale Portal Notícias Já: Oi, aqui é a Alessandra Guimarães, do Portal Notícias Já. Esse texto está circulando nos grupos, vocês confirmam? É verdade?
[16:04, 09/12/2026] Ale Portal Notícias Já: Queria publicar ainda hoje
[16:05, 09/12/2026] Ale Portal Notícias Já: Esta mensagem foi apagada""",
        esperado={
            "jornalista": Contem("Alessandra Guimarães"),
            "veiculo": "Portal Notícias Já",
            "contato": AUSENTE,
            "pedido": Contem("vocês confirmam"),
            "data": "2026-12-09",
            "horario": "16:03",
            "deadline": "2026-12-09",
        },
        nota="Mensagem encaminhada é o boato, não o pedido; 'ainda hoje' = 09/12; mensagem apagada ignorada.",
    ),
    Caso(
        id="wpi-013",
        modulo=_I,
        formato="texto",
        agora="2026-09-22 09:00",
        texto="""22/09/2026 08:41 - Mauro Gazeta Campos: Bom dia! Mauro Kulik, da Gazeta dos Campos
22/09/2026 08:41 - Mauro Gazeta Campos: Sobre o latrocínio do comerciante em Carambeí no dia 15/09: vocês têm atualização da investigação? Algum suspeito identificado?
22/09/2026 08:42 - Mauro Gazeta Campos: Se conseguir até sexta (25) seria ótimo. Meu e-mail: mauro.kulik@gazetadoscampos.com.br""",
        esperado={
            "jornalista": Contem("Mauro Kulik"),
            "veiculo": "Gazeta dos Campos",
            "contato": Contem("mauro.kulik@gazetadoscampos.com.br"),
            "pedido": Contem("atualização da investigação"),
            "data": "2026-09-22",
            "horario": "08:41",
            "deadline": "2026-09-25",
        },
        nota="15/09 é a data do crime, não do pedido nem prazo.",
    ),
    Caso(
        id="wpi-014",
        modulo=_I,
        formato="texto",
        agora="2026-08-03 14:40",
        texto="""[03/08/26 14:10:33] Lucas Ferri: Boa tarde. Lucas Ferri, repórter da Folha do Norte Pioneiro
[03/08/26 14:10:59] Lucas Ferri: Preciso de posicionamento da PCPR sobre a falta de escrivães na delegacia de Santo Antônio da Platina. Manda no meu e-mail: lucas.ferri@folhanortepioneiro.com.br
‎[03/08/26 14:25:40] Ascom PCPR: Boa tarde, Lucas. Recebido. Para agilizar, você pode falar também no fixo da Assessoria: (41) 3235-7700.
[03/08/26 14:26:02] Lucas Ferri: Blz! Fecho amanhã às 15h""",
        esperado={
            "jornalista": Contem("Lucas Ferri"),
            "veiculo": "Folha do Norte Pioneiro",
            "contato": Contem("lucas.ferri@folhanortepioneiro.com.br"),
            "pedido": Contem("posicionamento"),
            "data": "2026-08-03",
            "horario": "14:10",
            "deadline": "2026-08-04",
        },
        nota="O fixo que aparece é da Ascom, não do jornalista; prazo 'amanhã' dito após a resposta.",
    ),
    Caso(
        id="wpi-015",
        modulo=_I,
        formato="texto",
        agora="2026-10-15 11:00",
        texto="""[10:18, 15/10/2026] Fernanda Litoral: Bom dia, equipe! Fernanda Reis, TV Litoral Paranaense
[10:18, 15/10/2026] Fernanda Litoral: Vamos fazer uma série sobre segurança na temporada de verão em Matinhos e Guaratuba. Gostaria de entrevista com o delegado de Matinhos, gravação na semana que vem
[10:19, 15/10/2026] Fernanda Litoral: Meu cel: (41) 99640-2281 | fernanda.reis@tvlitoral.com.br
[10:40, 15/10/2026] Ascom PCPR: Oi, Fernanda! Vamos verificar.""",
        esperado={
            "jornalista": Contem("Fernanda Reis"),
            "veiculo": "TV Litoral Paranaense",
            "contato": UmDe(Contem("99640-2281"), Contem("fernanda.reis@tvlitoral.com.br")),
            "pedido": Contem("entrevista com o delegado de Matinhos"),
            "data": "2026-10-15",
            "horario": "10:18",
            "deadline": AUSENTE,
        },
        nota="'Semana que vem' sem dia não é deadline; dois contatos, qualquer um vale.",
    ),
    Caso(
        id="wpi-016",
        modulo=_I,
        formato="texto",
        agora="2026-11-26 19:40",
        texto="""[26/11/2026, 19:12:08] Juninho Rádio Vale: Boa noite, pessoal da Ascom
‎[26/11/2026, 19:12:30] Juninho Rádio Vale: ‎imagem ocultada
[26/11/2026, 19:13:02] Juninho Rádio Vale: Esse print de boletim sobre furto de defensivos agrícolas em Cerro Azul está rodando nos grupos da cidade. É documento da Civil mesmo?
[26/11/2026, 19:14:15] Juninho Rádio Vale: Se for, queria uma entrevista por telefone com o delegado amanhã no programa das 7h. Osvaldo Júnior Tanaka, Rádio Vale do Ribeira FM""",
        esperado={
            "jornalista": Contem("Osvaldo Júnior Tanaka"),
            "veiculo": "Rádio Vale do Ribeira FM",
            "contato": AUSENTE,
            "pedido": Contem("entrevista por telefone"),
            "data": "2026-11-26",
            "horario": "19:12",
            "deadline": "2026-11-27",
        },
        nota="Apelido no contato; nome real só na assinatura do fim; imagem ocultada; 7h é o programa (amanhã).",
    ),
    Caso(
        id="wpi-017",
        modulo=_I,
        formato="texto",
        agora="2026-11-18 15:20",
        texto="""18/11/2026 14:55 - Igor Menegatti TV Iguaçu: Boa tarde! Igor Menegatti, TV Iguaçu Canal 8
18/11/2026 14:55 - Igor Menegatti TV Iguaçu: Estamos preparando uma reportagem especial sobre tráfico na Ponte da Amizade. Precisamos dos dados de apreensão de drogas da 9ª SDP em 2025 e 2026 e, se possível, uma sonora do delegado-chefe
18/11/2026 14:56 - Igor Menegatti TV Iguaçu: A reportagem vai ao ar no domingo (22) 🎥
18/11/2026 14:56 - Igor Menegatti TV Iguaçu: <Mídia oculta>""",
        esperado={
            "jornalista": Contem("Igor Menegatti"),
            "veiculo": "TV Iguaçu Canal 8",
            "contato": AUSENTE,
            "pedido": Contem("dados de apreensão de drogas"),
            "data": "2026-11-18",
            "horario": "14:55",
            "deadline": "2026-11-22",
        },
        nota="Veiculação no domingo (22) é o deadline; 2025/2026 são o período dos dados.",
    ),
    Caso(
        id="wpi-018",
        modulo=_I,
        formato="texto",
        agora="2026-12-03 13:10",
        texto="""03/12/26 12:47 - Letícia Arantes Agência Pinhão: Oi, boa tarde! Letícia Arantes, da Agência Pinhão de Notícias
03/12/26 12:47 - Letícia Arantes Agência Pinhão: A PCPR confirma a prisão do motorista que atropelou um ciclista e fugiu no Batel no sábado (28)? Queria uma nota curta
03/12/26 12:48 - Letícia Arantes Agência Pinhão: Publicamos hoje à noite
03/12/26 12:48 - Letícia Arantes Agência Pinhão: 41 99317-6620""",
        esperado={
            "jornalista": Contem("Letícia Arantes"),
            "veiculo": "Agência Pinhão de Notícias",
            "contato": Contem("99317-6620"),
            "pedido": Contem("confirma a prisão"),
            "data": "2026-12-03",
            "horario": "12:47",
            "deadline": "2026-12-03",
        },
        nota="'Hoje à noite' = 03/12; sábado (28/11) é o fato.",
    ),
    Caso(
        id="wpi-019",
        modulo=_I,
        formato="texto",
        agora="2026-10-08 11:00",
        texto="""[10:45, 08/10/2026] Paula Ascom: Gente, a Tânia Weber, da Revista Segurança em Foco, ligou às 10h20 pedindo entrevista com o delegado-geral sobre o novo sistema de B.O. online
[10:45, 08/10/2026] Paula Ascom: Contato dela: (41) 98450-1177. Prazo: dia 20
[10:47, 08/10/2026] Marcelo Ascom: Deixa que eu vejo com o gabinete 👍""",
        esperado={
            "jornalista": Contem("Tânia Weber"),
            "veiculo": "Revista Segurança em Foco",
            "contato": Contem("98450-1177"),
            "pedido": Contem("entrevista com o delegado-geral"),
            "data": "2026-10-08",
            "horario": "10:20",
            "deadline": "2026-10-20",
        },
        nota="Grupo interno da Ascom repassando ligação: jornalista não é a Paula; o pedido foi feito às 10h20, não 10:45.",
    ),
    Caso(
        id="wpi-020",
        modulo=_I,
        formato="texto",
        agora="2026-09-09 10:00",
        texto="""09/09/2026 09:21 - Kátia 📻 Educadora AM: Bom diaaa ☀️ é a Kátia Gonçalves da Educadora
09/09/2026 09:21 - Kátia 📻 Educadora AM: Consigo uma sonora sobre a operação contra furto de gado de ontem em Tibagi? Até as 17h, pode ser por áudio mesmo
09/09/2026 09:35 - Ascom PCPR: Bom dia, Kátia! Vamos pedir ao delegado.
09/09/2026 11:02 - Ascom PCPR: <Mídia oculta>
09/09/2026 11:02 - Ascom PCPR: Segue a sonora do delegado""",
        esperado={
            "jornalista": Contem("Kátia Gonçalves"),
            "veiculo": "Rádio Educadora AM",
            "contato": AUSENTE,
            "pedido": Contem("sonora"),
            "data": "2026-09-09",
            "horario": "09:21",
            "deadline": "2026-09-09",
        },
        nota="Emoji no contato; 'Educadora' → Rádio Educadora AM; resposta da Ascom às 11:02 não é o pedido.",
    ),
    Caso(
        id="wpi-021",
        modulo=_I,
        formato="texto",
        agora="2026-10-21 15:00",
        texto="""[21/10/2026, 11:30:02] Ascom PCPR: Bom dia, Anderson! Enviamos no seu e-mail o release da operação contra fraudes em licitações em Cascavel.
[21/10/2026, 14:08:47] Anderson Lückmann: Obrigado! Aqui é do Jornal Diário do Oeste. Consigo uma entrevista com o delegado responsável hoje ainda? Até as 18h
[21/10/2026, 14:09:15] Anderson Lückmann: meu cel 45 99120-4433""",
        esperado={
            "jornalista": Contem("Anderson Lückmann"),
            "veiculo": "Jornal Diário do Oeste",
            "contato": Contem("99120-4433"),
            "pedido": Contem("entrevista com o delegado responsável"),
            "data": "2026-10-21",
            "horario": "14:08",
            "deadline": "2026-10-21",
        },
        nota="A Ascom abre a conversa (11:30), mas o pedido do jornalista é às 14:08.",
    ),
    Caso(
        id="wpi-022",
        modulo=_I,
        formato="texto",
        agora="2026-09-14 10:10",
        texto="""10/08/2026 15:02 - Diana TV Norte: Boa tarde! Pode me mandar a nota sobre a prisão em Cornélio?
10/08/2026 15:40 - Ascom PCPR: Nota enviada no seu e-mail ✅
10/08/2026 15:41 - Diana TV Norte: Obrigada!!
14/09/2026 09:48 - Diana TV Norte: Bom dia! Diana Fukuda, TV Norte Paranaense, tudo bem?
14/09/2026 09:48 - Diana TV Norte: Agora preciso de dados sobre violência doméstica em Cornélio Procópio neste ano, para uma série que estreia no dia 21
14/09/2026 09:49 - Diana TV Norte: <Mídia oculta>""",
        esperado={
            "jornalista": Contem("Diana Fukuda"),
            "veiculo": "TV Norte Paranaense",
            "contato": AUSENTE,
            "pedido": Contem("violência doméstica"),
            "data": "2026-09-14",
            "horario": "09:48",
            "deadline": "2026-09-21",
        },
        nota="Pedido novo um mês depois de um atendimento já encerrado: vale o de 14/09.",
    ),
    Caso(
        id="wpi-023",
        modulo=_I,
        formato="texto",
        agora="2026-11-12 17:30",
        texto="""[17:02, 12/11/2026] Rafaela Portal Maringá: Oi! Rafaela Bortolotto, do Portal Maringá Agora 👋
[17:02, 12/11/2026] Rafaela Portal Maringá: Estamos fazendo um levantamento sobre golpes do falso advogado na região de Maringá. Vocês conseguem os números de boletins registrados em 2026?
[17:03, 12/11/2026] Rafaela Portal Maringá: Sem pressa, pode ser até o fim do mês""",
        esperado={
            "jornalista": Contem("Rafaela Bortolotto"),
            "veiculo": "Portal Maringá Agora",
            "contato": AUSENTE,
            "pedido": Contem("golpes do falso advogado"),
            "data": "2026-11-12",
            "horario": "17:02",
            "deadline": "2026-11-30",
        },
        nota="'Até o fim do mês' = 30/11; 'sem pressa' não apaga o prazo.",
    ),
    Caso(
        id="wpi-024",
        modulo=_I,
        formato="texto",
        agora="2026-12-01 08:30",
        texto="""[00:15, 01/12/2026] Thiago Rádio Cidade: Boa noite/bom dia 😅 Thiago Kessler, Rádio Cidade FM
[00:15, 01/12/2026] Thiago Rádio Cidade: A PCPR vai se manifestar sobre a fuga de presos da carceragem em Almirante Tamandaré? Preciso de um posicionamento hoje até as 10h
[00:16, 01/12/2026] Thiago Rádio Cidade: thiago.kessler@radiocidadefm.com.br""",
        esperado={
            "jornalista": Contem("Thiago Kessler"),
            "veiculo": "Rádio Cidade FM",
            "contato": Contem("thiago.kessler@radiocidadefm.com.br"),
            "pedido": Contem("posicionamento"),
            "data": "2026-12-01",
            "horario": "00:15",
            "deadline": "2026-12-01",
        },
        nota="Depois da meia-noite: pedido já é 01/12 e 'hoje até as 10h' é 01/12.",
    ),
    Caso(
        id="wpi-025",
        modulo=_I,
        formato="texto",
        agora="2026-09-29 16:00",
        texto="""29/09/2026 15:12 - Léo Rádio Cidade: Oi, pessoal! Leonardo Batista aqui
29/09/2026 15:12 - Léo Rádio Cidade: Dessa vez não é pela rádio: estou fazendo uma reportagem como freela para a Revista Segurança em Foco sobre a atuação do NUCIBER em crimes digitais contra idosos. Gostaria de entrevistar o delegado titular
29/09/2026 15:13 - Léo Rádio Cidade: Entrego a matéria dia 09/10""",
        esperado={
            "jornalista": Contem("Leonardo Batista"),
            "veiculo": "Revista Segurança em Foco",
            "contato": AUSENTE,
            "pedido": Contem("entrevistar o delegado titular"),
            "data": "2026-09-29",
            "horario": "15:12",
            "deadline": "2026-10-09",
        },
        nota="Contato salvo diz Rádio Cidade, mas o pedido é pela Revista.",
    ),
    Caso(
        id="wpi-026",
        modulo=_I,
        formato="texto",
        agora="2026-08-24 10:00",
        texto="""[24/08/2026, 09:05:33] Tribuna PG - Redação: Bom dia
[24/08/2026, 09:05:51] Tribuna PG - Redação: Precisamos confirmar o número de mandados cumpridos na Operação Pedra Branca, deflagrada na sexta (21) em Ponta Grossa, e quantas pessoas foram presas
[24/08/2026, 09:06:20] Tribuna PG - Redação: Pode responder ainda nesta manhã? Att, Débora Szymanski – Jornal Tribuna Ponta-grossense – (42) 3025-8190""",
        esperado={
            "jornalista": Contem("Débora Szymanski"),
            "veiculo": "Jornal Tribuna Ponta-grossense",
            "contato": Contem("3025-8190"),
            "pedido": Contem("número de mandados cumpridos"),
            "data": "2026-08-24",
            "horario": "09:05",
            "deadline": "2026-08-24",
        },
        nota="Contato genérico da redação ('Tribuna PG'); a jornalista só assina no fim; sexta (21) é a operação.",
    ),
    Caso(
        id="wpi-027",
        modulo=_I,
        formato="texto",
        agora="2026-10-26 12:00",
        texto="""26/10/26 11:20 - Podcast Linha Invest.: Olá! Somos do Podcast Linha de Investigação, produzido pela jornalista Mirela Castanho
26/10/26 11:20 - Podcast Linha Invest.: Gostaríamos de convidar um delegado do DHPP para um episódio sobre como funciona a investigação de homicídios
26/10/26 11:21 - Podcast Linha Invest.: A gravação seria remota, em qualquer dia até 13/11. E-mail: contato@linhadeinvestigacao.com.br""",
        esperado={
            "jornalista": Contem("Mirela Castanho"),
            "veiculo": AUSENTE,
            "veiculo_novo": Contem("Linha de Investigação"),
            "contato": Contem("contato@linhadeinvestigacao.com.br"),
            "pedido": Contem("delegado do DHPP"),
            "data": "2026-10-26",
            "horario": "11:20",
            "deadline": "2026-11-13",
        },
        nota="Podcast fora do cadastro (não é o Portal Curitiba em Pauta); DHPP não é veículo.",
    ),
    Caso(
        id="wpi-028",
        modulo=_I,
        formato="texto",
        agora="2026-09-10 18:30",
        texto="""10/09/2026 17:55 - Bia TV Norte: Boa tarde! Tudo bem?
10/09/2026 17:55 - Bia TV Norte: Preciso de uma nota sobre a morte do detento na cadeia pública de Arapongas nesta madrugada. Entro ao vivo às 19h15
10/09/2026 17:56 - Bia TV Norte: Beatriz Almeida Souza
Repórter | TV Norte Paranaense
(43) 99870-3312
10/09/2026 18:10 - Ascom PCPR: Oi, Beatriz! Estamos apurando.""",
        esperado={
            "jornalista": Contem("Beatriz Almeida Souza"),
            "veiculo": "TV Norte Paranaense",
            "contato": Contem("99870-3312"),
            "pedido": Contem("nota sobre a morte do detento"),
            "data": "2026-09-10",
            "horario": "17:55",
            "deadline": "2026-09-10",
        },
        nota="Assinatura em várias linhas numa mensagem só; 19h15 é a entrada ao vivo (hoje).",
    ),
    Caso(
        id="wpi-029",
        modulo=_I,
        formato="texto",
        agora="2026-09-30 09:00",
        texto="""Bom dia! Aqui é o Caio Ferrante, do Portal Notícias Já. Gostaria de saber quantos inquéritos de feminicídio a PCPR instaurou em 2026 até agora e, se possível, uma entrevista com a coordenadora das Delegacias da Mulher. Preciso até o dia 06/10. Obrigado! caio.ferrante@portalnoticiasja.com.br""",
        esperado={
            "jornalista": Contem("Caio Ferrante"),
            "veiculo": "Portal Notícias Já",
            "contato": Contem("caio.ferrante@portalnoticiasja.com.br"),
            "pedido": Contem("inquéritos de feminicídio"),
            "horario": AUSENTE,
            "deadline": "2026-10-06",
        },
        nota="Mensagem copiada sem carimbo: horário do pedido não se inventa; prazo absoluto 06/10.",
    ),
    Caso(
        id="wpi-030",
        modulo=_I,
        formato="texto",
        agora="2026-10-02 18:40",
        texto="""[02/10/26 17:31:40] Marina Portal CWB em Pauta: Boa tarde! Marina Toledo, Portal Curitiba em Pauta
[02/10/26 17:32:05] Marina Portal CWB em Pauta: Queria confirmar o número de celulares recuperados na operação de hoje no Centro e se o delegado pode dar entrevista
[02/10/26 17:32:30] Marina Portal CWB em Pauta: Até as 18h, por favor
[02/10/26 17:58:12] Marina Portal CWB em Pauta: Ops, corrigindo: pode ser até amanhã às 18h, a matéria ficou pra amanhã 🙏""",
        esperado={
            "jornalista": Contem("Marina Toledo"),
            "veiculo": "Portal Curitiba em Pauta",
            "contato": AUSENTE,
            "pedido": Contem("celulares recuperados"),
            "data": "2026-10-02",
            "horario": "17:31",
            "deadline": "2026-10-03",
        },
        nota="O prazo foi corrigido pela jornalista: vale 'amanhã' (03/10), não hoje.",
    ),
    Caso(
        id="wpi-031",
        modulo=_I,
        formato="texto",
        agora="2026-11-20 10:30",
        texto="""20/11/2026 10:02 - Wagner Rádio Planalto: Bom dia! Wagner Oliveira, da Rádio Planalto 98 FM
20/11/2026 10:02 - Wagner Rádio Planalto: Precisamos de uma sonora sobre a operação contra o tráfico em Pato Branco. É urgente, pra ontem 😂
20/11/2026 10:03 - Wagner Rádio Planalto: meu zap é esse mesmo, 46 99901-7788""",
        esperado={
            "jornalista": Contem("Wagner Oliveira"),
            "veiculo": "Rádio Planalto 98 FM",
            "contato": Contem("99901-7788"),
            "pedido": Contem("sonora"),
            "data": "2026-11-20",
            "horario": "10:02",
            "deadline": AUSENTE,
        },
        nota="'Pra ontem' é força de expressão: não é deadline em 19/11.",
    ),
    Caso(
        id="wpi-032",
        modulo=_I,
        formato="texto",
        agora="2026-08-27 15:30",
        texto="""27/08/2026 14:40 - +55 43 99655-1020: Boa tarde, é da assessoria da Polícia Civil?
27/08/2026 14:41 - Ascom PCPR: Boa tarde! Sim, em que podemos ajudar?
27/08/2026 14:43 - +55 43 99655-1020: Sou repórter da Folha do Norte Pioneiro. Queria saber se tem previsão de concurso para escrivão e investigador e quantas vagas estão abertas hoje nas delegacias do Norte Pioneiro
27/08/2026 14:43 - +55 43 99655-1020: A matéria sai no sábado""",
        esperado={
            "jornalista": AUSENTE,
            "veiculo": "Folha do Norte Pioneiro",
            "contato": Contem("99655-1020"),
            "pedido": Contem("previsão de concurso"),
            "data": "2026-08-27",
            "horario": UmDe("14:40", "14:43"),
            "deadline": "2026-08-29",
        },
        nota="Repórter sem nome: jornalista AUSENTE; contato abre às 14:40, pedido às 14:43; contato é o número; sábado a partir de quinta 27/08 = 29/08.",
    ),
    Caso(
        id="wpi-033",
        modulo=_I,
        formato="texto",
        agora="2026-12-15 11:00",
        texto="""[10:12, 15/12/2026] Aline Produção TV Paraná Sul: Bom dia! Sou a Aline, produtora da TV Paraná Sul
[10:12, 15/12/2026] Aline Produção TV Paraná Sul: A repórter Helena Duarte vai fazer uma matéria sobre golpes no fim de ano (falsas entregas, falsos sorteios). Pode indicar um delegado do NUCIBER para gravar amanhã?
[10:13, 15/12/2026] Aline Produção TV Paraná Sul: Se precisar falar com a Helena: 41 99234-5510. Meu número é este aqui mesmo
[10:30, 15/12/2026] Ascom PCPR: Bom dia, Aline! Vamos verificar com o NUCIBER.""",
        esperado={
            "jornalista": Contem("Helena Duarte"),
            "veiculo": "TV Paraná Sul",
            "contato": Contem("99234-5510"),
            "pedido": Contem("delegado do NUCIBER"),
            "data": "2026-12-15",
            "horario": "10:12",
            "deadline": "2026-12-16",
        },
        nota="Produtora pede em nome da repórter: jornalista e contato são da Helena.",
    ),
    Caso(
        id="wpi-034",
        modulo=_I,
        formato="texto",
        agora="2026-09-04 20:00",
        texto="""‎[04/09/26 18:02:10] Gabi Diário do Oeste: ‎áudio omitido
[04/09/26 18:02:10] Gabi Diário do Oeste: (áudio transcrito) Oi, tudo bem? É a Gabriela Wendt do Diário do Oeste. Tô precisando de uma posição da Polícia Civil sobre aquele corpo encontrado no rio em Marechal Cândido Rondon hoje de manhã. Já identificaram? A gente fecha a página às nove da noite.
‎[04/09/26 18:20:55] Ascom PCPR: Oi, Gabriela! Aguardando retorno da delegacia.""",
        esperado={
            "jornalista": Contem("Gabriela Wendt"),
            "veiculo": "Jornal Diário do Oeste",
            "contato": AUSENTE,
            "pedido": Contem("corpo encontrado no rio"),
            "data": "2026-09-04",
            "horario": "18:02",
            "deadline": "2026-09-04",
        },
        nota="Áudio com transcrição; 'nove da noite' = hoje; 'Diário do Oeste' → Jornal Diário do Oeste.",
    ),
    Caso(
        id="wpi-035",
        modulo=_I,
        formato="texto",
        agora="2026-10-19 09:30",
        texto="""16/10/2026 17:48 - Samuel Agência Pinhão: Boa tarde! Samuel Koerich, da Agência Pinhão de Notícias
16/10/2026 17:48 - Samuel Agência Pinhão: Queremos fazer um perfil das mulheres delegadas no comando de delegacias em Curitiba. Poderiam indicar duas para entrevista?
16/10/2026 17:49 - Samuel Agência Pinhão: Pode me responder na segunda
19/10/2026 08:55 - Ascom PCPR: Bom dia, Samuel! Temos duas indicações, vou te passar.""",
        esperado={
            "jornalista": Contem("Samuel Koerich"),
            "veiculo": "Agência Pinhão de Notícias",
            "contato": AUSENTE,
            "pedido": Contem("mulheres delegadas"),
            "data": "2026-10-16",
            "horario": "17:48",
            "deadline": "2026-10-19",
        },
        nota="Pedido na sexta 16/10, resposta da Ascom na segunda (19): data é a do pedido; 'segunda' = 19/10.",
    ),
    Caso(
        id="wpi-036",
        modulo=_I,
        formato="texto",
        agora="2026-08-11 16:00",
        texto="""[15:21, 11/08/2026] Jéssica Litoral: Oi, Ascom!! 🌊
[15:21, 11/08/2026] Jéssica Litoral: Jéssica Pacheco, da TV Litoral Paranaense
[15:22, 11/08/2026] Jéssica Litoral: Vocês têm imagens da apreensão de cocaína no Porto de Paranaguá de ontem? Precisamos até quinta (13) para o programa de sábado
[15:22, 11/08/2026] Jéssica Litoral: <Mídia oculta>""",
        esperado={
            "jornalista": Contem("Jéssica Pacheco"),
            "veiculo": "TV Litoral Paranaense",
            "contato": AUSENTE,
            "pedido": Contem("imagens da apreensão"),
            "data": "2026-08-11",
            "horario": "15:21",
            "deadline": UmDe("2026-08-13", "2026-08-15"),
        },
        nota="Prazo quinta (13) e veiculação sábado (15): qualquer um; 'ontem' é o fato.",
    ),
    Caso(
        id="wpi-037",
        modulo=_I,
        formato="texto",
        agora="2026-11-03 14:00",
        texto="""03/11/2026 13:05 - Coordenação Jornalismo Rádio Educadora: Boa tarde
03/11/2026 13:05 - Coordenação Jornalismo Rádio Educadora: O nosso repórter Márcio Zanlorenzi vai procurar vocês sobre o assalto à agência dos Correios em Carambeí. Ele precisa de entrevista com o delegado ainda hoje
03/11/2026 13:06 - Coordenação Jornalismo Rádio Educadora: Contato: Márcio Zanlorenzi Educadora
+55 42 99813-4050
03/11/2026 13:40 - Ascom PCPR: Recebido. Vamos acionar a delegacia.""",
        esperado={
            "jornalista": Contem("Márcio Zanlorenzi"),
            "veiculo": "Rádio Educadora AM",
            "contato": Contem("99813-4050"),
            "pedido": Contem("entrevista com o delegado"),
            "data": "2026-11-03",
            "horario": "13:05",
            "deadline": "2026-11-03",
        },
        nota="Coordenação pede pelo repórter; cartão de contato; 'Rádio Educadora' → Rádio Educadora AM.",
    ),
    Caso(
        id="wpi-038",
        modulo=_I,
        formato="texto",
        agora="2026-12-18 09:40",
        texto="""[17/12/2026, 22:58:03] Otávio Gazeta: Boa noite! Otávio Marcondes, Gazeta dos Campos
[17/12/2026, 22:58:40] Otávio Gazeta: Vocês confirmam que o suspeito do duplo homicídio em Palmeira se apresentou hoje na delegacia?
[18/12/2026, 00:12:19] Otávio Gazeta: Desculpa insistir, preciso fechar até as 8h
‎[18/12/2026, 07:31:02] Ascom PCPR: Bom dia, Otávio! Confirmado, segue nota.""",
        esperado={
            "jornalista": Contem("Otávio Marcondes"),
            "veiculo": "Gazeta dos Campos",
            "contato": AUSENTE,
            "pedido": Contem("se apresentou"),
            "data": "2026-12-17",
            "horario": "22:58",
            "deadline": "2026-12-18",
        },
        nota="iPhone atravessando a meia-noite: pedido 17/12 22:58; prazo 8h dito depois da meia-noite = 18/12.",
    ),
    Caso(
        id="wpi-039",
        modulo=_I,
        formato="texto",
        agora="2026-08-06 11:20",
        texto="""06/08/26 10:47 - Nathalia Portal Maringá Agora: Olá, bom dia! Nathalia Serra, do Portal Maringá Agora
06/08/26 10:47 - Nathalia Portal Maringá Agora: Gostaria de um posicionamento sobre a denúncia de que a Delegacia da Mulher de Maringá não estaria registrando ocorrências aos fins de semana
06/08/26 10:48 - Nathalia Portal Maringá Agora: Publicamos amanhã cedo. E-mail: nathalia.serra@maringaagora.com.br / (44) 99102-8877""",
        esperado={
            "jornalista": Contem("Nathalia Serra"),
            "veiculo": "Portal Maringá Agora",
            "contato": UmDe(Contem("nathalia.serra@maringaagora.com.br"), Contem("99102-8877")),
            "pedido": Contem("posicionamento"),
            "data": "2026-08-06",
            "horario": "10:47",
            "deadline": "2026-08-07",
        },
        nota="Delegacia citada é o assunto, não o veículo; dois contatos.",
    ),
    Caso(
        id="wpi-040",
        modulo=_I,
        formato="texto",
        agora="2026-10-13 15:00",
        texto="""[14:05, 13/10/2026] Ascom PCPR: Boa tarde, Pedro! A entrevista de ontem com o delegado de Guarapuava já foi ao ar?
[14:20, 13/10/2026] Pedro Rádio Planalto: Foi sim, obrigado!
[14:21, 13/10/2026] Pedro Rádio Planalto: Aproveitando: agora preciso dos dados de furtos de veículos em Guarapuava nos últimos 12 meses, para quinta-feira (15). Pedro Albuquerque, Rádio Planalto 98 FM""",
        esperado={
            "jornalista": Contem("Pedro Albuquerque"),
            "veiculo": "Rádio Planalto 98 FM",
            "contato": AUSENTE,
            "pedido": Contem("furtos de veículos"),
            "data": "2026-10-13",
            "horario": "14:21",
            "deadline": "2026-10-15",
        },
        nota="Mensagens anteriores são sobre atendimento antigo; o novo pedido é às 14:21 (não 14:05 da Ascom).",
    ),
    Caso(
        id="wpi-041",
        modulo=_I,
        formato="texto",
        agora="2026-09-15 10:00",
        texto="""15/09/2026 09:30 - Ascom PCPR adicionou Ricardo Vale Ribeira
15/09/2026 09:31 - Ascom PCPR: Bom dia, Ricardo! Este é o grupo da imprensa regional do Vale do Ribeira
15/09/2026 09:44 - Ricardo Vale Ribeira: Bom dia a todos! Ricardo Moraes, da Rádio Vale do Ribeira FM
15/09/2026 09:44 - Ricardo Vale Ribeira: Já aproveito para pedir: há balanço da Operação Serra Verde, de combate a furtos em propriedades rurais em Adrianópolis? Preciso para o jornal de amanhã""",
        esperado={
            "jornalista": Contem("Ricardo Moraes"),
            "veiculo": "Rádio Vale do Ribeira FM",
            "contato": AUSENTE,
            "pedido": Contem("balanço da Operação Serra Verde"),
            "data": "2026-09-15",
            "horario": "09:44",
            "deadline": "2026-09-16",
        },
        nota="A Ascom adiciona e dá boas-vindas: o pedido começa às 09:44.",
    ),
    Caso(
        id="wpi-042",
        modulo=_I,
        formato="texto",
        agora="2026-11-24 09:15",
        texto="""[08:50, 24/11/2026] Vitor Hugo TV Iguaçu: Bom dia! Vitor Hugo Ramalho, TV Iguaçu Canal 8
[08:50, 24/11/2026] Vitor Hugo TV Iguaçu: Sobre o sequestro relâmpago em Foz na noite de 22/11: podemos gravar com o delegado da 9ª SDP? A matéria vai ao ar no dia 26/11
[08:51, 24/11/2026] Vitor Hugo TV Iguaçu: vitorhugo.ramalho@tviguacu8.com.br""",
        esperado={
            "jornalista": Contem("Vitor Hugo Ramalho"),
            "veiculo": "TV Iguaçu Canal 8",
            "contato": Contem("vitorhugo.ramalho@tviguacu8.com.br"),
            "pedido": Contem("gravar com o delegado"),
            "data": "2026-11-24",
            "horario": "08:50",
            "deadline": "2026-11-26",
        },
        nota="22/11 é o crime; 26/11 é a veiculação.",
    ),
    Caso(
        id="wpi-043",
        modulo=_I,
        formato="texto",
        agora="2026-12-07 15:00",
        texto="""07/12/26 14:17 - Cris Folha NP: Boa tarde
07/12/26 14:17 - Cris Folha NP: <Mídia oculta>
07/12/26 14:18 - Cris Folha NP: Esse cartaz de procurado que circula em Bandeirantes é oficial da Polícia Civil? Se for, podem mandar a versão oficial e um contato para denúncias?
07/12/26 14:18 - Cris Folha NP: Cristiane Maeda, Folha do Norte Pioneiro. Quando puderem
07/12/26 14:30 - Ascom PCPR: Esta mensagem foi apagada
07/12/26 14:31 - Ascom PCPR: Boa tarde, Cristiane! Vamos verificar com a delegacia de Bandeirantes.""",
        esperado={
            "jornalista": Contem("Cristiane Maeda"),
            "veiculo": "Folha do Norte Pioneiro",
            "contato": AUSENTE,
            "pedido": Contem("cartaz de procurado"),
            "data": "2026-12-07",
            "horario": "14:17",
            "deadline": AUSENTE,
        },
        nota="'Quando puderem' sem prazo; 'NP' = Norte Pioneiro; a mensagem apagada é da Ascom.",
    ),
    Caso(
        id="wpi-044",
        modulo=_I,
        formato="texto",
        agora="2026-08-20 18:00",
        texto="""[20/08/2026, 17:10:45] +55 41 98765-0021: Boa tarde, meu nome é Sílvia Prestes, trabalho na Agência Pinhão de Notícias
[20/08/2026, 17:11:20] +55 41 98765-0021: Precisamos de um posicionamento sobre a morte de um homem durante abordagem em Pinhais ontem, citada pela família nas redes
‎[20/08/2026, 17:11:31] +55 41 98765-0021: ‎<anexado: 00000044-PHOTO-2026-08-20-17-11-31.jpg>
[20/08/2026, 17:12:02] +55 41 98765-0021: Nosso fechamento é às 20h""",
        esperado={
            "jornalista": Contem("Sílvia Prestes"),
            "veiculo": "Agência Pinhão de Notícias",
            "contato": Contem("98765-0021"),
            "pedido": Contem("posicionamento"),
            "data": "2026-08-20",
            "horario": "17:10",
            "deadline": "2026-08-20",
        },
        nota="iPhone com número sem nome salvo: o número é o contato; 20h é fechamento de hoje.",
    ),
    Caso(
        id="wpi-045",
        modulo=_I,
        formato="texto",
        agora="2026-10-28 10:10",
        texto="""28/10/2026 09:33 - Ascom PCPR: Bom dia! Chegou este pedido pelo direct do Instagram, encaminho aqui:
28/10/2026 09:33 - Ascom PCPR: Encaminhada
"Olá, sou Lorena Vasconcellos, repórter da Revista Segurança em Foco. Gostaria de entrevistar um perito ou delegado sobre o uso de reconhecimento facial nas investigações. Prazo: 05/11. Meu telefone: (41) 99508-7123"
28/10/2026 09:40 - Ascom PCPR: Quem assume?""",
        esperado={
            "jornalista": Contem("Lorena Vasconcellos"),
            "veiculo": "Revista Segurança em Foco",
            "contato": Contem("99508-7123"),
            "pedido": Contem("reconhecimento facial"),
            "data": "2026-10-28",
            "horario": "09:33",
            "deadline": "2026-11-05",
        },
        nota="Pedido encaminhado no grupo interno: quem escreve é a Ascom, mas a jornalista é Lorena.",
    ),
]

# ==========================================================================
# PUBLICAÇÕES
# ==========================================================================

_PUBLICACOES = [
    Caso(
        id="wpp-001",
        modulo=_P,
        formato="texto",
        agora="2026-09-22 09:00",
        texto=f"""22/09/2026 08:12 - {_CRIPTO_ANDROID}
22/09/2026 08:14 - Del. Marcos DP Palmas: Bom dia, Ascom! Segue material para divulgação
22/09/2026 08:14 - Del. Marcos DP Palmas: PCPR PRENDE SUSPEITO DE AGREDIR IDOSO DURANTE ROUBO EM PALMAS

A Polícia Civil do Paraná (PCPR) prendeu no domingo (20) um homem de 27 anos suspeito de agredir e roubar um idoso de 81 anos no bairro Lagoão, em Palmas. O suspeito foi localizado a partir de imagens de câmeras de segurança.

"A vítima segue internada. O suspeito vai responder por roubo majorado", explicou o delegado Marcos Wendler.

Delegado Marcos Wendler
Delegacia de Polícia de Palmas
22/09/2026 08:15 - Del. Marcos DP Palmas: <Mídia oculta>
22/09/2026 08:15 - Del. Marcos DP Palmas: <Mídia oculta>
22/09/2026 08:31 - Ascom PCPR: Recebido, doutor! Vamos produzir.""",
        esperado={
            "titulo": Contem("agredir idoso"),
            "unidade": "Delegacia de Polícia de Palmas",
            "fonte": Contem("Marcos Wendler"),
            "data": "2026-09-22",
            "inicio_pauta": "08:14",
            "jornalista": AUSENTE,
        },
        nota="Contato 'Del. Marcos DP Palmas'; prisão no domingo (20); 08:12 é a criptografia; delegado não é jornalista.",
    ),
    Caso(
        id="wpp-002",
        modulo=_P,
        formato="texto",
        agora="2026-10-06 11:00",
        texto="""[06/10/2026, 09:37:18] Inv. Szeremeta DENARC: Bom dia! Release da operação de ontem
[06/10/2026, 09:37:52] Inv. Szeremeta DENARC: DENARC APREENDE 300 KG DE MACONHA EM BARRACÃO NA CIC

A Divisão Estadual de Narcóticos (DENARC) da Polícia Civil do Paraná apreendeu na segunda-feira (5) cerca de 300 quilos de maconha em um barracão na Cidade Industrial de Curitiba. Dois homens, de 34 e 41 anos, foram presos em flagrante. A ação teve apoio do Centro de Operações Policiais Especiais (COPE).

Investigador Rafael Szeremeta – DENARC
‎[06/10/2026, 09:38:05] Inv. Szeremeta DENARC: ‎<anexado: 00000017-PHOTO-2026-10-06-09-38-05.jpg>
‎[06/10/2026, 09:38:06] Inv. Szeremeta DENARC: ‎<anexado: 00000018-PHOTO-2026-10-06-09-38-06.jpg>
[06/10/2026, 09:52:40] Ascom PCPR: Recebido! Obrigada""",
        esperado={
            "titulo": Contem("300 kg de maconha"),
            "unidade": "DENARC",
            "fonte": Contem("Rafael Szeremeta"),
            "data": "2026-10-06",
            "inicio_pauta": "09:37",
            "jornalista": AUSENTE,
        },
        nota="iPhone com U+200E e anexos; COPE só apoiou; operação na segunda (5), pauta em 06/10.",
    ),
    Caso(
        id="wpp-003",
        modulo=_P,
        formato="texto",
        agora="2026-08-10 16:00",
        texto="""[15:02, 10/08/2026] Escrivã Luana DP Guarapuava: Boa tarde, pessoal
[15:02, 10/08/2026] Escrivã Luana DP Guarapuava: A delegada pediu pra mandar esse texto:

PCPR CUMPRE MANDADO CONTRA SUSPEITO DE ESTUPRO DE VULNERÁVEL EM GUARAPUAVA

A Delegacia de Polícia de Guarapuava cumpriu na sexta-feira (7) mandado de prisão preventiva contra um homem de 52 anos investigado por estupro de vulnerável. O crime teria ocorrido em maio deste ano.

Luana Kowalski, escrivã
[15:04, 10/08/2026] Escrivã Luana DP Guarapuava: Não temos fotos pra preservar a vítima
[15:10, 10/08/2026] Ascom PCPR: Ok, Luana, obrigada!""",
        esperado={
            "titulo": Contem("estupro de vulnerável"),
            "unidade": "Delegacia de Polícia de Guarapuava",
            "fonte": Contem("Luana Kowalski"),
            "data": "2026-08-10",
            "inicio_pauta": "15:02",
            "jornalista": AUSENTE,
        },
        nota="WhatsApp Web; sexta (7) e maio são do fato; quem mandou é a escrivã (fonte).",
    ),
    Caso(
        id="wpp-004",
        modulo=_P,
        formato="texto",
        agora="2026-11-17 10:00",
        texto="""17/11/26 08:40 - Inv. Moacir Castro: Bom dia! Aqui é o investigador Moacir Stroparo, da Delegacia de Polícia de Castro
17/11/26 08:40 - Inv. Moacir Castro: Ontem prendemos em flagrante dois homens que furtavam cabos de energia em propriedades rurais do interior de Castro. Foram recuperados 400 metros de cabos de cobre. Dá pra divulgar?
17/11/26 08:41 - Inv. Moacir Castro: <Mídia oculta>
17/11/26 08:41 - Inv. Moacir Castro: <Mídia oculta>""",
        esperado={
            "titulo": Contem("cabos"),
            "unidade": AUSENTE,
            "unidade_nova": Contem("Castro"),
            "fonte": Contem("Moacir Stroparo"),
            "data": "2026-11-17",
            "inicio_pauta": "08:40",
            "jornalista": AUSENTE,
        },
        nota="Android ano curto; Castro fora do cadastro → unidade_nova; 'ontem' é o fato.",
    ),
    Caso(
        id="wpp-005",
        modulo=_P,
        formato="texto",
        agora="2026-09-03 15:30",
        texto="""03/09/2026 13:50 - Ascom PCPR criou o grupo "Ascom x 9ª SDP Foz"
03/09/2026 13:50 - Ascom PCPR adicionou Del. Henrique Foz, Escrivã Talita 9ª SDP
03/09/2026 14:26 - Escrivã Talita 9ª SDP: Boa tarde! Segue release da 9ª SDP
03/09/2026 14:26 - Escrivã Talita 9ª SDP: OPERAÇÃO TRÍPLICE PRENDE QUATRO POR CONTRABANDO DE ELETRÔNICOS EM FOZ DO IGUAÇU

A 9ª Subdivisão Policial de Foz do Iguaçu deflagrou nesta quinta-feira (3) a Operação Tríplice, que cumpriu quatro mandados de prisão e seis de busca contra um grupo suspeito de contrabando de eletrônicos pela Ponte da Amizade. A Receita Federal participou da ação.

Talita Brenner – escrivã
03/09/2026 14:27 - Escrivã Talita 9ª SDP: <Mídia oculta>
03/09/2026 14:40 - Del. Henrique Foz: Pode divulgar, sem mostrar rostos
03/09/2026 14:42 - Ascom PCPR: Perfeito, obrigado!""",
        esperado={
            "titulo": Contem("Operação Tríplice"),
            "unidade": "9ª Subdivisão Policial de Foz do Iguaçu",
            "fonte": UmDe(Contem("Talita Brenner"), Contem("Henrique")),
            "data": "2026-09-03",
            "inicio_pauta": "14:26",
            "jornalista": AUSENTE,
        },
        nota="Grupo criado pela Ascom às 13:50 (sistema); a pauta entra às 14:26; Receita Federal é parceira.",
    ),
    Caso(
        id="wpp-006",
        modulo=_P,
        formato="texto",
        agora="2026-10-24 08:30",
        texto="""23/10/2026 23:52 - DH Londrina Plantão: Boa noite, Ascom. Material para amanhã cedo
23/10/2026 23:52 - DH Londrina Plantão: PCPR PRENDE SUSPEITO DE MATAR JOVEM A FACADAS EM LONDRINA

A Delegacia de Homicídios de Londrina prendeu nesta sexta-feira (23) um homem de 24 anos suspeito de matar um jovem de 19 anos a facadas no Jardim União da Vitória, na zona sul de Londrina, no dia 11 de outubro.

Investigadora Camila Yamamoto
Delegacia de Homicídios de Londrina
24/10/2026 00:03 - DH Londrina Plantão: <Mídia oculta>
24/10/2026 00:03 - DH Londrina Plantão: <Mídia oculta>
24/10/2026 07:45 - Ascom PCPR: Bom dia! Recebido.""",
        esperado={
            "titulo": Contem("matar jovem a facadas"),
            "unidade": "Delegacia de Homicídios de Londrina",
            "fonte": Contem("Camila Yamamoto"),
            "data": "2026-10-23",
            "inicio_pauta": "23:52",
            "jornalista": AUSENTE,
        },
        nota="Atravessa a meia-noite: fotos 00:03 do dia 24 não mudam a pauta (23/10 23:52); 'Jardim União da Vitória' não é a DP de União da Vitória.",
    ),
    Caso(
        id="wpp-007",
        modulo=_P,
        formato="texto",
        agora="2026-10-09 14:00",
        texto="""[10:05, 05/10/2026] Del. Fabiana Pato Branco: Bom dia! Release da prisão do suspeito de furto de gado
[10:05, 05/10/2026] Del. Fabiana Pato Branco: <Mídia oculta>
[11:40, 05/10/2026] Ascom PCPR: Publicado! pc.pr.gov.br/noticia/furto-gado-pato-branco ✅
[13:18, 09/10/2026] Del. Fabiana Pato Branco: Boa tarde! Mais uma pra vocês 😊
[13:18, 09/10/2026] Del. Fabiana Pato Branco: PCPR RECUPERA MAQUINÁRIO AGRÍCOLA FURTADO AVALIADO EM R$ 800 MIL EM PATO BRANCO

A Delegacia de Polícia de Pato Branco recuperou nesta sexta-feira (9) uma colheitadeira e um trator furtados de uma propriedade rural em Clevelândia. Um homem de 45 anos foi preso.

Delegada Fabiana Czarnecki
[13:19, 09/10/2026] Del. Fabiana Pato Branco: <Mídia oculta>""",
        esperado={
            "titulo": Contem("maquinário agrícola"),
            "unidade": "Delegacia de Polícia de Pato Branco",
            "fonte": Contem("Fabiana"),
            "data": "2026-10-09",
            "inicio_pauta": "13:18",
            "jornalista": AUSENTE,
        },
        nota="Pauta nova dias depois de uma já publicada: vale a de 09/10 13:18; Clevelândia não é a unidade.",
    ),
    Caso(
        id="wpp-008",
        modulo=_P,
        formato="texto",
        agora="2026-11-09 10:00",
        texto="""NUCRIA PRENDE HOMEM POR ARMAZENAR MATERIAL DE ABUSO SEXUAL INFANTIL EM CURITIBA

O Núcleo de Proteção à Criança e ao Adolescente Vítimas de Crimes (NUCRIA) de Curitiba prendeu em flagrante, na manhã desta sexta-feira (6), um homem de 38 anos que armazenava arquivos de abuso sexual infantil. A investigação começou a partir de denúncia recebida em setembro.

Informações: delegada Sandra Pilotto
NUCRIA de Curitiba""",
        esperado={
            "titulo": Contem("material de abuso sexual infantil"),
            "unidade": "NUCRIA de Curitiba",
            "fonte": Contem("Sandra Pilotto"),
            "data": AUSENTE,
            "inicio_pauta": AUSENTE,
            "jornalista": AUSENTE,
        },
        nota="Texto de uma mensagem só, sem carimbo: sexta (6) é o fato, não a pauta.",
    ),
    Caso(
        id="wpp-009",
        modulo=_P,
        formato="texto",
        agora="2026-08-25 17:00",
        texto="""25/08/2026 16:12 - +55 42 99130-2254: Boa tarde, Ascom. Segue material
25/08/2026 16:12 - +55 42 99130-2254: PCPR E POLÍCIA CIVIL DE SC PRENDEM SUSPEITO DE ROUBO A POSTO DE COMBUSTÍVEL NA DIVISA

A Delegacia de Polícia de União da Vitória, com apoio da Polícia Civil de Santa Catarina em Porto União, prendeu nesta terça-feira (25) um homem de 30 anos suspeito de roubar um posto de combustível na BR-153 em 16 de agosto.

Inv. Sandro Mielke – DP União da Vitória
25/08/2026 16:13 - +55 42 99130-2254: <Mídia oculta>""",
        esperado={
            "titulo": Contem("roubo a posto de combustível"),
            "unidade": "Delegacia de Polícia de União da Vitória",
            "fonte": Contem("Sandro Mielke"),
            "data": "2026-08-25",
            "inicio_pauta": "16:12",
            "jornalista": AUSENTE,
        },
        nota="Número sem nome salvo; PC de SC (Porto União) é parceira; 16/08 é o crime.",
    ),
    Caso(
        id="wpp-010",
        modulo=_P,
        formato="texto",
        agora="2026-09-18 11:00",
        texto="""[18/09/2026, 10:24:13] Paula Ascom: Pessoal, o DHPP mandou no meu particular, encaminhando:
[18/09/2026, 10:24:20] Paula Ascom: DHPP ESCLARECE HOMICÍDIO DE MOTORISTA DE APLICATIVO NO TATUQUARA

O Departamento de Homicídios e Proteção à Pessoa (DHPP) prendeu nesta quinta-feira (17) dois suspeitos de matar um motorista de aplicativo de 33 anos no Tatuquara, em julho.

Delegado Emerson Taborda – DHPP
‎[18/09/2026, 10:24:31] Paula Ascom: ‎<anexado: 00000052-PHOTO-2026-09-18-10-24-31.jpg>
[18/09/2026, 10:30:02] Marcelo Ascom: Deixa comigo""",
        esperado={
            "titulo": Contem("motorista de aplicativo"),
            "unidade": "DHPP",
            "fonte": Contem("Emerson Taborda"),
            "data": "2026-09-18",
            "inicio_pauta": "10:24",
        },
        nota="Grupo interno da Ascom repassando release: fonte é o delegado do DHPP, não a Paula; prisão na quinta (17).",
    ),
    Caso(
        id="wpp-011",
        modulo=_P,
        formato="texto",
        agora="2026-12-02 12:00",
        texto="""02/12/2026 11:05 - Del. Otávio Campo Mourão: áudio omitido
02/12/2026 11:05 - Del. Otávio Campo Mourão: (áudio transcrito) Bom dia, pessoal da Ascom, aqui é o delegado Otávio Rizzardi, da Delegacia de Campo Mourão. Hoje de manhã a gente deflagrou a Operação Colheita, contra um grupo que furtava defensivos agrícolas de cooperativas da região. Foram cinco presos. Vou mandar as fotos aqui, dá pra fazer uma matéria?
02/12/2026 11:06 - Del. Otávio Campo Mourão: <Mídia oculta>
02/12/2026 11:06 - Del. Otávio Campo Mourão: <Mídia oculta>
02/12/2026 11:06 - Del. Otávio Campo Mourão: <Mídia oculta>""",
        esperado={
            "titulo": Contem("Operação Colheita"),
            "unidade": "Delegacia de Polícia de Campo Mourão",
            "fonte": Contem("Otávio Rizzardi"),
            "data": "2026-12-02",
            "inicio_pauta": "11:05",
            "jornalista": AUSENTE,
        },
        nota="Pauta só em áudio transcrito, sem release.",
    ),
    Caso(
        id="wpp-012",
        modulo=_P,
        formato="texto",
        agora="2026-08-19 18:00",
        texto="""19/08/26 16:48 - Inv. Kelly Irati: IMG-20260819-WA0012.jpg (arquivo anexado)
Operação Ferrolho: armas e munições apreendidas hoje em Irati e Rebouças
19/08/26 16:48 - Inv. Kelly Irati: IMG-20260819-WA0013.jpg (arquivo anexado)
19/08/26 16:50 - Inv. Kelly Irati: Boa tarde! A Delegacia de Polícia de Irati cumpriu hoje 8 mandados de busca na Operação Ferrolho, contra comércio ilegal de armas. Três presos. Qualquer dúvida falar comigo, investigadora Kelly Bortolini""",
        esperado={
            "titulo": Contem("Operação Ferrolho"),
            "unidade": "Delegacia de Polícia de Irati",
            "fonte": Contem("Kelly Bortolini"),
            "data": "2026-08-19",
            "inicio_pauta": "16:48",
            "jornalista": AUSENTE,
        },
        nota="Pauta começa pela legenda da foto (16:48), não pelo texto das 16:50; Rebouças não é unidade.",
    ),
    Caso(
        id="wpp-013",
        modulo=_P,
        formato="texto",
        agora="2026-11-05 15:00",
        texto="""[05/11/2026, 13:40:09] Escrivão Fábio DEDC: Boa tarde
[05/11/2026, 13:40:44] Escrivão Fábio DEDC: PCPR DESARTICULA GRUPO QUE APLICAVA GOLPE DO FALSO LEILÃO DE VEÍCULOS

A Delegacia de Estelionato e Desvio de Cargas, com apoio do Núcleo de Combate aos Cibercrimes (NUCIBER), cumpriu nesta quinta-feira (5) seis mandados de busca contra um grupo que criava sites falsos de leilão. O prejuízo estimado é de R$ 2 milhões.

Fábio Carvalhal – Escrivão""",
        esperado={
            "titulo": Contem("falso leilão"),
            "unidade": "Delegacia de Estelionato e Desvio de Cargas",
            "fonte": Contem("Fábio Carvalhal"),
            "data": "2026-11-05",
            "inicio_pauta": "13:40",
            "jornalista": AUSENTE,
        },
        nota="NUCIBER é apoio; a unidade que manda é a de Estelionato (sigla no contato).",
    ),
    Caso(
        id="wpp-014",
        modulo=_P,
        formato="texto",
        agora="2026-10-20 10:00",
        texto="""[08:57, 20/10/2026] DM Maringá - Ana Paula: Bom dia, Ascom!
[08:57, 20/10/2026] DM Maringá - Ana Paula: Prisão de ontem para divulgar:

PCPR PRENDE HOMEM QUE AMEAÇAVA EX-COMPANHEIRA COM ARMA EM MARINGÁ

A Delegacia da Mulher de Maringá prendeu na segunda-feira (19) um homem de 36 anos que ameaçava a ex-companheira com uma arma de fogo. Ele já havia sido denunciado em agosto.

Ana Paula Scheffer, investigadora
[08:58, 20/10/2026] DM Maringá - Ana Paula: Por favor não divulgar o bairro""",
        esperado={
            "titulo": Contem("ameaçava ex-companheira"),
            "unidade": "Delegacia da Mulher de Maringá",
            "fonte": Contem("Ana Paula Scheffer"),
            "data": "2026-10-20",
            "inicio_pauta": "08:57",
            "jornalista": AUSENTE,
        },
        nota="'DM Maringá' no contato; prisão na segunda (19), pauta na terça (20).",
    ),
    Caso(
        id="wpp-015",
        modulo=_P,
        formato="texto",
        agora="2026-12-11 11:30",
        texto="""[11/12/26 09:15:44] Del. Priscila DHPP: Bom dia!!
[11/12/26 09:15:59] Del. Priscila DHPP: Conseguimos esclarecer aquele caso de setembro 🙌
[11/12/26 09:16:30] Del. Priscila DHPP: DHPP PRENDE AUTOR DE HOMICÍDIO EM BAR DO BAIRRO ALTO APÓS TRÊS MESES DE INVESTIGAÇÃO

O DHPP da Polícia Civil do Paraná prendeu nesta quinta-feira (10) um homem de 29 anos, autor do homicídio ocorrido em 12 de setembro em um bar no Bairro Alto, em Curitiba.

Delegada Priscila Honorato
‎[11/12/26 09:16:41] Del. Priscila DHPP: ‎<anexado: 00000077-PHOTO-2026-12-11-09-16-41.jpg>""",
        esperado={
            "titulo": Contem("homicídio em bar do Bairro Alto"),
            "unidade": "DHPP",
            "fonte": Contem("Priscila Honorato"),
            "data": "2026-12-11",
            "inicio_pauta": "09:15",
            "jornalista": AUSENTE,
        },
        nota="iPhone ano curto; 12/09 (crime) e quinta (10) (prisão) não são a pauta.",
    ),
    Caso(
        id="wpp-016",
        modulo=_P,
        formato="texto",
        agora="2026-09-08 16:00",
        texto="""08/09/2026 14:33 - Del. Jonas Telêmaco: Boa tarde. Segue para publicação:
08/09/2026 14:33 - Del. Jonas Telêmaco: POLÍCIA CIVIL PRENDE SUSPEITO DE INCENDIAR CASA DA EX-SOGRA EM TELÊMACO BORBA

A Delegacia de Polícia de Telêmaco Borba prendeu nesta terça-feira (8) um homem de 33 anos suspeito de atear fogo na casa da ex-sogra no dia 29 de agosto.

Delegado Jonas Ferraciolli
Delegacia de Polícia de Telêmaco Borba
08/09/2026 14:34 - Del. Jonas Telêmaco: <Mídia oculta>""",
        esperado={
            "titulo": Contem("incendiar casa"),
            "unidade": AUSENTE,
            "unidade_nova": Contem("Telêmaco Borba"),
            "fonte": Contem("Jonas Ferraciolli"),
            "data": "2026-09-08",
            "inicio_pauta": "14:33",
            "jornalista": AUSENTE,
        },
        nota="Unidade fora do cadastro → unidade_nova; 29/08 é o crime.",
    ),
    Caso(
        id="wpp-017",
        modulo=_P,
        formato="texto",
        agora="2026-11-26 12:00",
        texto="""[10:48, 26/11/2026] Inv. Cássio Lapa: Bom dia, sou o investigador Cássio Dembinski, da Delegacia de Polícia da Lapa
[10:48, 26/11/2026] Inv. Cássio Lapa: Hoje cedo cumprimos mandado de prisão de um foragido condenado por latrocínio em 2019, que estava escondido num sítio no interior do município. Mando fotos da viatura com ele (sem rosto)
[10:49, 26/11/2026] Inv. Cássio Lapa: <Mídia oculta>""",
        esperado={
            "titulo": Contem("foragido"),
            "unidade": AUSENTE,
            "unidade_nova": Contem("Lapa"),
            "fonte": Contem("Cássio Dembinski"),
            "data": "2026-11-26",
            "inicio_pauta": "10:48",
            "jornalista": AUSENTE,
        },
        nota="Lapa fora do cadastro; 2019 é a condenação.",
    ),
    Caso(
        id="wpp-018",
        modulo=_P,
        formato="texto",
        agora="2026-08-31 09:30",
        texto="""31/08/2026 07:55 - Plantão 15ª SDP Cascavel: Bom dia, Ascom. Ocorrência do plantão da madrugada
31/08/2026 07:55 - Plantão 15ª SDP Cascavel: PCPR PRENDE EM FLAGRANTE HOMEM QUE AGREDIU A COMPANHEIRA EM CASCAVEL

O plantão da 15ª Subdivisão Policial de Cascavel prendeu em flagrante, na madrugada desta segunda-feira (31), um homem de 40 anos que agrediu a companheira no bairro Brasília. O caso será encaminhado à Delegacia da Mulher de Cascavel.

Escrivão Ronaldo Pertile – 15ª SDP
31/08/2026 07:56 - Plantão 15ª SDP Cascavel: <Mídia oculta>""",
        esperado={
            "titulo": Contem("agrediu a companheira"),
            "unidade": "15ª Subdivisão Policial de Cascavel",
            "fonte": Contem("Ronaldo Pertile"),
            "data": "2026-08-31",
            "inicio_pauta": "07:55",
            "jornalista": AUSENTE,
        },
        nota="Violência doméstica, mas quem manda é a 15ª SDP; a Delegacia da Mulher só vai receber o caso.",
    ),
    Caso(
        id="wpp-019",
        modulo=_P,
        formato="texto",
        agora="2026-10-01 18:00",
        texto="""[01/10/2026, 16:21:05] COPE - Sgt Informações: Boa tarde. Aqui é o agente Wellington Braga, do COPE
[01/10/2026, 16:21:40] COPE - Sgt Informações: COPE PRENDE TRIO SUSPEITO DE ROUBOS A FARMÁCIAS EM CURITIBA

O Centro de Operações Policiais Especiais (COPE) prendeu nesta quinta-feira (1º) três homens suspeitos de uma série de roubos a farmácias em Curitiba. A investigação contou com apoio da Delegacia de Furtos e Roubos.
‎[01/10/2026, 16:22:02] COPE - Sgt Informações: ‎<anexado: 00000090-VIDEO-2026-10-01-16-22-02.mp4>""",
        esperado={
            "titulo": Contem("roubos a farmácias"),
            "unidade": "COPE",
            "fonte": Contem("Wellington Braga"),
            "data": "2026-10-01",
            "inicio_pauta": "16:21",
            "jornalista": AUSENTE,
        },
        nota="Delegacia de Furtos e Roubos é apoio; unidade é o COPE.",
    ),
    Caso(
        id="wpp-020",
        modulo=_P,
        formato="texto",
        agora="2026-09-25 10:00",
        texto="""25/09/26 08:22 - DP Rio Negro - Inv. Lígia: Bom dia! 🚔
25/09/26 08:22 - DP Rio Negro - Inv. Lígia: PCPR E PCSC PRENDEM SUSPEITOS DE FURTOS A RESIDÊNCIAS EM RIO NEGRO E MAFRA

A Delegacia de Polícia de Rio Negro, em ação conjunta com a Polícia Civil de Santa Catarina em Mafra, prendeu nesta quinta-feira (24) dois homens suspeitos de ao menos 15 furtos a residências nas duas cidades.

Investigadora Lígia Mehret
25/09/26 08:23 - DP Rio Negro - Inv. Lígia: <Mídia oculta>""",
        esperado={
            "titulo": Contem("furtos a residências"),
            "unidade": "Delegacia de Polícia de Rio Negro",
            "fonte": Contem("Lígia Mehret"),
            "data": "2026-09-25",
            "inicio_pauta": "08:22",
            "jornalista": AUSENTE,
        },
        nota="Prisão na quinta (24), pauta na sexta (25); PC de SC é parceira.",
    ),
    Caso(
        id="wpp-021",
        modulo=_P,
        formato="texto",
        agora="2026-11-11 15:00",
        texto="""[13:55, 11/11/2026] Eduardo Inv. Ortigueira: Boa tarde, equipe
[13:55, 11/11/2026] Eduardo Inv. Ortigueira: Release que o doutor pediu pra mandar:

PCPR APREENDE 12 ARMAS EM PROPRIEDADE RURAL DE ORTIGUEIRA

A Delegacia de Polícia de Ortigueira apreendeu nesta quarta-feira (11) doze armas de fogo sem registro em uma propriedade rural. "Seguimos investigando a origem do armamento", disse o delegado Mauro Kotaka.

Eduardo Sokolowski – Investigador
[13:56, 11/11/2026] Eduardo Inv. Ortigueira: <Mídia oculta>""",
        esperado={
            "titulo": Contem("12 armas"),
            "unidade": "Delegacia de Polícia de Ortigueira",
            "fonte": Contem("Eduardo Sokolowski"),
            "data": "2026-11-11",
            "inicio_pauta": "13:55",
            "jornalista": AUSENTE,
        },
        nota="O delegado só aparece na citação; quem mandou é o investigador (fonte).",
    ),
    Caso(
        id="wpp-022",
        modulo=_P,
        formato="texto",
        agora="2026-08-05 12:00",
        texto="""05/08/2026 10:30 - Karina DFRV: Bom dia! Material da DFRV
05/08/2026 10:30 - Karina DFRV: DFRV RECUPERA CAMINHONETES ROUBADAS QUE SERIAM LEVADAS AO PARAGUAI

A DFRV recuperou na terça-feira (4) três caminhonetes roubadas em Curitiba e Região Metropolitana que seriam levadas ao Paraguai. Um homem foi preso na BR-277, em Balsa Nova.

Karina Pedroso, escrivã
05/08/2026 10:31 - Karina DFRV: <Mídia oculta>""",
        esperado={
            "titulo": Contem("caminhonetes roubadas"),
            "unidade": "Delegacia de Furtos e Roubos de Veículos",
            "fonte": Contem("Karina Pedroso"),
            "data": "2026-08-05",
            "inicio_pauta": "10:30",
            "jornalista": AUSENTE,
        },
        nota="Só a sigla DFRV: é a de Veículos, não a Delegacia de Furtos e Roubos.",
    ),
    Caso(
        id="wpp-023",
        modulo=_P,
        formato="texto",
        agora="2026-12-14 17:00",
        texto="""[14/12/2026, 15:44:28] Rogério DFR Curitiba: Boa tarde, Ascom
[14/12/2026, 15:44:55] Rogério DFR Curitiba: PCPR DEVOLVE 60 CELULARES FURTADOS A VÍTIMAS EM CURITIBA

A Delegacia de Furtos e Roubos (DFR) devolveu nesta segunda-feira (14) 60 celulares recuperados em operação realizada em novembro contra receptadores no Centro de Curitiba.

Rogério Anzolin – investigador
‎[14/12/2026, 15:45:10] Rogério DFR Curitiba: ‎<anexado: 00000101-PHOTO-2026-12-14-15-45-10.jpg>""",
        esperado={
            "titulo": Contem("60 celulares"),
            "unidade": "Delegacia de Furtos e Roubos",
            "fonte": Contem("Rogério Anzolin"),
            "data": "2026-12-14",
            "inicio_pauta": "15:44",
            "jornalista": AUSENTE,
        },
        nota="DFR (celulares) não é a DFRV; operação em novembro é passado.",
    ),
    Caso(
        id="wpp-024",
        modulo=_P,
        formato="texto",
        agora="2026-09-16 12:00",
        texto="""16/09/26 11:07 - NUCIBER - Del. Tatiana: Bom dia! Alerta + prisão, pode sair hoje?
16/09/26 11:07 - NUCIBER - Del. Tatiana: NUCIBER PRENDE SUSPEITO DE APLICAR GOLPE DO FALSO PIX EM LOJISTAS

O Núcleo de Combate aos Cibercrimes (NUCIBER) da PCPR prendeu nesta quarta-feira (16), em Ponta Grossa, um homem de 23 anos suspeito de aplicar o golpe do falso Pix em ao menos 30 lojistas de Curitiba.

Delegada Tatiana Lorusso
16/09/26 11:08 - NUCIBER - Del. Tatiana: <Mídia oculta>""",
        esperado={
            "titulo": Contem("golpe do falso Pix"),
            "unidade": "NUCIBER",
            "fonte": Contem("Tatiana Lorusso"),
            "data": "2026-09-16",
            "inicio_pauta": "11:07",
            "jornalista": AUSENTE,
        },
        nota="Prisão em Ponta Grossa não faz da 13ª SDP a unidade.",
    ),
    Caso(
        id="wpp-025",
        modulo=_P,
        formato="texto",
        agora="2026-10-27 17:30",
        texto="""[16:02, 27/10/2026] DM PG - Simara: Boa tarde, gente
[16:02, 27/10/2026] DM PG - Simara: DELEGACIA DA MULHER DE PONTA GROSSA PRENDE SUSPEITO DE PERSEGUIR EX-NAMORADA

A Delegacia da Mulher de Ponta Grossa, vinculada à 13ª Subdivisão Policial, prendeu nesta terça-feira (27) um homem de 26 anos investigado por perseguição (stalking) contra a ex-namorada.

Simara Doubek – investigadora
[16:03, 27/10/2026] DM PG - Simara: Sem fotos""",
        esperado={
            "titulo": Contem("perseguir ex-namorada"),
            "unidade": "Delegacia da Mulher de Ponta Grossa",
            "fonte": Contem("Simara Doubek"),
            "data": "2026-10-27",
            "inicio_pauta": "16:02",
            "jornalista": AUSENTE,
        },
        nota="13ª SDP é só vinculação; 'DM PG' no contato.",
    ),
    Caso(
        id="wpp-026",
        modulo=_P,
        formato="texto",
        agora="2026-08-14 11:00",
        texto="""14/08/2026 09:10 - Del. Regional PG - Gilmar: Bom dia! Release da operação de hoje
14/08/2026 09:10 - Del. Regional PG - Gilmar: 13ª SDP DEFLAGRA OPERAÇÃO TEAR CONTRA FACÇÃO EM PONTA GROSSA

A 13ª Subdivisão Policial de Ponta Grossa deflagrou nesta sexta-feira (14) a Operação Tear, com 22 mandados de busca e 9 de prisão. A Delegacia da Mulher de Ponta Grossa e o COPE deram apoio.

Delegado Gilmar Hauer – 13ª SDP
14/08/2026 09:11 - Del. Regional PG - Gilmar: <Mídia oculta>
14/08/2026 09:11 - Del. Regional PG - Gilmar: <Mídia oculta>""",
        esperado={
            "titulo": Contem("Operação Tear"),
            "unidade": "13ª Subdivisão Policial de Ponta Grossa",
            "fonte": Contem("Gilmar Hauer"),
            "data": "2026-08-14",
            "inicio_pauta": "09:10",
            "jornalista": AUSENTE,
        },
        nota="Delegacia da Mulher de PG e COPE são apoio.",
    ),
    Caso(
        id="wpp-027",
        modulo=_P,
        formato="texto",
        agora="2026-11-24 09:00",
        texto="""[23/11/2026, 18:05:33] Inv. Bruno DP Guarapuava: Boa noite! Prendemos hoje o suspeito de atear fogo em ônibus no terminal de Guarapuava
[23/11/2026, 18:06:10] Inv. Bruno DP Guarapuava: Amanhã cedo mando as fotos, o texto segue:

PCPR PRENDE SUSPEITO DE INCENDIAR ÔNIBUS EM GUARAPUAVA

A Delegacia de Polícia de Guarapuava prendeu nesta segunda-feira (23) um jovem de 20 anos suspeito de incendiar um ônibus do transporte coletivo no último dia 15.

Bruno Tokarski – investigador
‎[24/11/2026, 07:42:18] Inv. Bruno DP Guarapuava: ‎<anexado: 00000120-PHOTO-2026-11-24-07-42-18.jpg>
[24/11/2026, 07:42:40] Inv. Bruno DP Guarapuava: Fotos 👆""",
        esperado={
            "titulo": Contem("incendiar ônibus"),
            "unidade": "Delegacia de Polícia de Guarapuava",
            "fonte": Contem("Bruno Tokarski"),
            "data": "2026-11-23",
            "inicio_pauta": "18:05",
            "jornalista": AUSENTE,
        },
        nota="Fotos chegam no dia seguinte: a pauta entrou em 23/11 18:05.",
    ),
    Caso(
        id="wpp-028",
        modulo=_P,
        formato="texto",
        agora="2026-10-14 09:00",
        texto="""Bom dia, pessoal. Delegacia de Polícia de Palmas.

PCPR PRENDE DUPLA POR TRÁFICO DE DROGAS PRÓXIMO A ESCOLA EM PALMAS

A Delegacia de Polícia de Palmas prendeu em flagrante, na tarde de segunda-feira (12), dois homens que vendiam drogas próximo a uma escola estadual no bairro São Sebastião. Foram apreendidos 200 gramas de cocaína.

Investigador Alceu Dranka
(46) 99812-0045""",
        esperado={
            "titulo": Contem("tráfico de drogas próximo a escola"),
            "unidade": "Delegacia de Polícia de Palmas",
            "fonte": Contem("Alceu Dranka"),
            "data": AUSENTE,
            "inicio_pauta": AUSENTE,
            "jornalista": AUSENTE,
        },
        nota="Texto copiado sem carimbo: segunda (12) é a prisão, não a pauta.",
    ),
    Caso(
        id="wpp-029",
        modulo=_P,
        formato="texto",
        agora="2026-12-17 16:00",
        texto="""[14:10, 17/12/2026] Inv. Tomás DENARC: Boa tarde, Ascom!
[14:10, 17/12/2026] Inv. Tomás DENARC: DENARC FECHA LABORATÓRIO DE DROGAS SINTÉTICAS EM COLOMBO

A Divisão Estadual de Narcóticos (DENARC) fechou nesta quinta-feira (17) um laboratório clandestino de drogas sintéticas em Colombo, na Região Metropolitana de Curitiba. Um químico de 44 anos foi preso. A Delegacia de Colombo acompanhou a ação.

Tomás Brandalise – investigador DENARC
[14:11, 17/12/2026] Inv. Tomás DENARC: <Mídia oculta>
[14:25, 17/12/2026] Ascom PCPR: Recebido, Tomás!""",
        esperado={
            "titulo": Contem("laboratório de drogas sintéticas"),
            "unidade": "DENARC",
            "fonte": Contem("Tomás Brandalise"),
            "data": "2026-12-17",
            "inicio_pauta": "14:10",
            "jornalista": AUSENTE,
        },
        nota="WhatsApp Web; Delegacia de Colombo só acompanhou.",
    ),
    Caso(
        id="wpp-030",
        modulo=_P,
        formato="texto",
        agora="2026-11-13 18:30",
        texto="""13/11/2026 17:40 - Del. Fabiana Pato Branco: Boa tarde! Segue material, mas só pode divulgar amanhã a partir das 8h, ainda tem mandado pra cumprir
13/11/2026 17:41 - Del. Fabiana Pato Branco: PCPR PRENDE GRUPO SUSPEITO DE ROUBAR COOPERATIVA DE CRÉDITO EM PATO BRANCO

A Delegacia de Polícia de Pato Branco prendeu três homens suspeitos do roubo a uma cooperativa de crédito ocorrido em 30 de outubro.

Delegada Fabiana Czarnecki
13/11/2026 17:41 - Del. Fabiana Pato Branco: <Mídia oculta>""",
        esperado={
            "titulo": Contem("cooperativa de crédito"),
            "unidade": "Delegacia de Polícia de Pato Branco",
            "fonte": Contem("Fabiana Czarnecki"),
            "data": "2026-11-13",
            "inicio_pauta": "17:40",
            "jornalista": AUSENTE,
        },
        nota="Embargo 'amanhã às 8h' não é o início da pauta; 30/10 é o crime.",
    ),
    Caso(
        id="wpp-031",
        modulo=_P,
        formato="texto",
        agora="2026-12-20 10:00",
        texto="""[18/12/2026, 11:03:52] Inv. Heloísa DP Paranaguá: Bom dia!
[18/12/2026, 11:04:15] Inv. Heloísa DP Paranaguá: PCPR PRENDE SUSPEITOS DE FURTAR CONTÊINERES NO PORTO DE PARANAGUÁ

A Delegacia de Polícia de Paranaguá prendeu nesta sexta-feira (18) quatro homens suspeitos de furtar cargas de contêineres na área portuária. A Receita Federal e a Portos do Paraná colaboraram com a investigação.

Heloísa Cordeiro – investigadora
‎[18/12/2026, 11:04:30] Inv. Heloísa DP Paranaguá: ‎<anexado: 00000131-PHOTO-2026-12-18-11-04-30.jpg>""",
        esperado={
            "titulo": Contem("contêineres"),
            "unidade": "Delegacia de Polícia de Paranaguá",
            "fonte": Contem("Heloísa Cordeiro"),
            "data": "2026-12-18",
            "inicio_pauta": "11:03",
            "jornalista": AUSENTE,
        },
        nota="Lida dias depois (agora 20/12): a pauta é de 18/12, não de hoje.",
    ),
    Caso(
        id="wpp-032",
        modulo=_P,
        formato="texto",
        agora="2026-09-29 11:00",
        texto="""29/09/2026 09:48 - Escrivão Maicon Toledo: Bom dia, Ascom!
29/09/2026 09:48 - Escrivão Maicon Toledo: PCPR PRENDE SUSPEITO DE ESTELIONATO CONTRA AGRICULTORES EM TOLEDO

A Delegacia de Polícia de Toledo prendeu nesta terça-feira (29) um homem de 47 anos suspeito de aplicar golpes em agricultores com a venda de sementes falsificadas. A 15ª Subdivisão Policial de Cascavel apoiou a ação.

Maicon Hendges – escrivão
29/09/2026 09:49 - Escrivão Maicon Toledo: <Mídia oculta>""",
        esperado={
            "titulo": Contem("estelionato contra agricultores"),
            "unidade": "Delegacia de Polícia de Toledo",
            "fonte": Contem("Maicon Hendges"),
            "data": "2026-09-29",
            "inicio_pauta": "09:48",
            "jornalista": AUSENTE,
        },
        nota="'Estelionato' no título não faz da unidade a Delegacia de Estelionato; 15ª SDP é apoio.",
    ),
    Caso(
        id="wpp-033",
        modulo=_P,
        formato="texto",
        agora="2026-08-28 15:00",
        texto="""28/08/26 13:20 - Kleber: Boa tarde, pessoal
28/08/26 13:20 - Kleber: Segue foto e texto da prisão de hoje de manhã aqui em Curitiba: um homem de 31 anos foi preso com uma pistola e munições dentro do carro durante abordagem no bairro Pinheirinho. Foi autuado por porte ilegal de arma
28/08/26 13:21 - Kleber: <Mídia oculta>
28/08/26 13:40 - Ascom PCPR: Oi, Kleber! Qual unidade fez a prisão?""",
        esperado={
            "titulo": Contem("porte ilegal de arma"),
            "unidade": AUSENTE,
            "unidade_nova": AUSENTE,
            "fonte": Contem("Kleber"),
            "data": "2026-08-28",
            "inicio_pauta": "13:20",
            "jornalista": AUSENTE,
        },
        nota="Unidade não informada (a Ascom até pergunta): Curitiba/Pinheirinho não são unidade.",
    ),
    Caso(
        id="wpp-034",
        modulo=_P,
        formato="texto",
        agora="2026-11-01 09:00",
        texto="""[31/10/26 23:58:59] Del. Henrique Foz: Boa noite. Material da prisão de agora há pouco
[31/10/26 23:59:40] Del. Henrique Foz: 9ª SDP PRENDE SUSPEITO DE TRÁFICO INTERNACIONAL DE ARMAS EM FOZ DO IGUAÇU

A 9ª Subdivisão Policial de Foz do Iguaçu prendeu na noite deste sábado (31) um homem de 35 anos com seis fuzis desmontados escondidos no fundo falso de uma caminhonete.

Delegado Henrique Albuquerque Neto
‎[01/11/26 00:01:12] Del. Henrique Foz: ‎<anexado: 00000140-PHOTO-2026-11-01-00-01-12.jpg>""",
        esperado={
            "titulo": Contem("tráfico internacional de armas"),
            "unidade": "9ª Subdivisão Policial de Foz do Iguaçu",
            "fonte": Contem("Henrique Albuquerque"),
            "data": "2026-10-31",
            "inicio_pauta": "23:58",
            "jornalista": AUSENTE,
        },
        nota="23:58:59 é 23:58 (não arredonda); foto depois da meia-noite não muda a data.",
    ),
    Caso(
        id="wpp-035",
        modulo=_P,
        formato="texto",
        agora="2026-09-11 12:00",
        texto="""11/09/2026 10:15 - Inv. Juliano Campo Mourão 🚓: 🚨🚨🚨 BOM DIA ASCOM 🚨🚨🚨
11/09/2026 10:15 - Inv. Juliano Campo Mourão 🚓: 🔥 PCPR DEFLAGRA OPERAÇÃO BRASA CONTRA INCÊNDIOS CRIMINOSOS EM CAMPO MOURÃO 🔥

👉 A Delegacia de Polícia de Campo Mourão cumpriu nesta sexta-feira (11) quatro mandados de busca contra suspeitos de provocar incêndios em áreas de preservação.
👉 Um homem de 50 anos foi preso.

📸 fotos abaixo
✍️ Juliano Pscheidt – investigador
11/09/2026 10:16 - Inv. Juliano Campo Mourão 🚓: <Mídia oculta>
11/09/2026 10:16 - Inv. Juliano Campo Mourão 🚓: <Mídia oculta>""",
        esperado={
            "titulo": Contem("Operação Brasa"),
            "unidade": "Delegacia de Polícia de Campo Mourão",
            "fonte": Contem("Juliano Pscheidt"),
            "data": "2026-09-11",
            "inicio_pauta": "10:15",
            "jornalista": AUSENTE,
        },
        nota="Muitos emojis no nome e no texto.",
    ),
    Caso(
        id="wpp-036",
        modulo=_P,
        formato="texto",
        agora="2026-10-07 12:00",
        texto="""[07/10/2026, 09:02:17] +55 42 99744-3310: Bom dia! Prendemos ontem o suspeito do roubo à lotérica, texto abaixo
[07/10/2026, 09:02:50] +55 42 99744-3310: PCPR PRENDE SUSPEITO DE ROUBO A LOTÉRICA

Um homem de 22 anos foi preso na terça-feira (6) suspeito de roubar uma casa lotérica no centro da cidade no dia 28 de setembro. Ele foi reconhecido pelas vítimas.
[07/10/2026, 09:20:05] Ascom PCPR: Bom dia! Quem fala? E de qual delegacia?
[07/10/2026, 09:31:44] +55 42 99744-3310: Desculpa! Aqui é a escrivã Rosana Kuchla, da Delegacia de Polícia de Irati""",
        esperado={
            "titulo": Contem("roubo a lotérica"),
            "unidade": "Delegacia de Polícia de Irati",
            "fonte": Contem("Rosana Kuchla"),
            "data": "2026-10-07",
            "inicio_pauta": "09:02",
            "jornalista": AUSENTE,
        },
        nota="Unidade e nome só vêm depois da pergunta da Ascom; o início continua 09:02.",
    ),
    Caso(
        id="wpp-037",
        modulo=_P,
        formato="texto",
        agora="2026-12-04 15:00",
        texto="""04/12/2026 13:27 - Del. Vanessa União da Vitória: Boa tarde! Segue release
04/12/2026 13:27 - Del. Vanessa União da Vitória: PCPR LOCALIZA IDOSA DESAPARECIDA HÁ TRÊS DIAS EM UNIÃO DA VITÓRIA

A Delegacia de Polícia de União da Vitória localizou nesta sexta-feira (4) uma idosa de 79 anos que estava desaparecida desde terça-feira (1º). Ela estava em uma área de mata e passa bem.

Delegada Vanessa Groff
04/12/2026 13:28 - Del. Vanessa União da Vitória: Se a imprensa quiser detalhes, falar com o investigador que coordenou as buscas:
04/12/2026 13:28 - Del. Vanessa União da Vitória: Contato: Inv. Luan Beber
+55 42 99655-7123""",
        esperado={
            "titulo": Contem("idosa desaparecida"),
            "unidade": "Delegacia de Polícia de União da Vitória",
            "fonte": Contem("Vanessa Groff"),
            "data": "2026-12-04",
            "inicio_pauta": "13:27",
            "jornalista": AUSENTE,
        },
        nota="Cartão de contato é do investigador para a imprensa; quem passou a pauta é a delegada.",
    ),
    Caso(
        id="wpp-038",
        modulo=_P,
        formato="texto",
        agora="2026-08-21 18:00",
        texto="""[16:44, 21/08/2026] DM Cascavel - Inv. Érica: IMG-20260821-WA0044.jpg (arquivo anexado)
PCPR prende homem por feminicídio tentado em Cascavel. Delegacia da Mulher de Cascavel cumpriu hoje mandado de prisão preventiva. Envio: investigadora Érica Lanznaster
[16:45, 21/08/2026] DM Cascavel - Inv. Érica: Sem mais fotos""",
        esperado={
            "titulo": Contem("feminicídio tentado"),
            "unidade": "Delegacia da Mulher de Cascavel",
            "fonte": Contem("Érica Lanznaster"),
            "data": "2026-08-21",
            "inicio_pauta": "16:44",
            "jornalista": AUSENTE,
        },
        nota="Pauta toda na legenda de uma foto (WhatsApp Web).",
    ),
    Caso(
        id="wpp-039",
        modulo=_P,
        formato="texto",
        agora="2026-10-16 11:00",
        texto="""16/10/26 09:33 - DH Londrina - Del. Artur: Bom dia! Release
16/10/26 09:33 - DH Londrina - Del. Artur: PCPR PRENDE EM CURITIBA SUSPEITO DE HOMICÍDIO OCORRIDO EM LONDRINA

A Delegacia de Homicídios de Londrina prendeu nesta quinta-feira (15), em Curitiba, com apoio do DHPP, um homem de 28 anos suspeito de matar um comerciante em Londrina em junho.

Delegado Artur Pagnoncelli
16/10/26 09:34 - DH Londrina - Del. Artur: <Mídia oculta>""",
        esperado={
            "titulo": Contem("homicídio ocorrido em Londrina"),
            "unidade": "Delegacia de Homicídios de Londrina",
            "fonte": Contem("Artur Pagnoncelli"),
            "data": "2026-10-16",
            "inicio_pauta": "09:33",
            "jornalista": AUSENTE,
        },
        nota="DHPP é apoio; prisão em Curitiba (15), pauta de Londrina (16).",
    ),
    Caso(
        id="wpp-040",
        modulo=_P,
        formato="texto",
        agora="2026-11-19 10:00",
        texto="""[11:02, 12/11/2026] Del. Artur Maringá: Bom dia, publicaram a matéria da prisão de ontem?
[11:30, 12/11/2026] Ascom PCPR: Ainda não, doutor, sai hoje à tarde
[16:20, 12/11/2026] Ascom PCPR: Publicado ✅
[08:47, 19/11/2026] Ana Paula DM Maringá: Bom dia! Nova pauta da Delegacia da Mulher de Maringá:
[08:47, 19/11/2026] Ana Paula DM Maringá: PCPR PRENDE HOMEM QUE DESCUMPRIU MEDIDA PROTETIVA E INVADIU CASA DA EX EM MARINGÁ

A Delegacia da Mulher de Maringá prendeu nesta quarta-feira (18) um homem de 44 anos que invadiu a casa da ex-companheira apesar de medida protetiva.

Ana Paula Scheffer, investigadora""",
        esperado={
            "titulo": Contem("descumpriu medida protetiva"),
            "unidade": "Delegacia da Mulher de Maringá",
            "fonte": Contem("Ana Paula Scheffer"),
            "data": "2026-11-19",
            "inicio_pauta": "08:47",
            "jornalista": AUSENTE,
        },
        nota="Conversa antiga (12/11) sobre outra matéria; a pauta nova é de 19/11 08:47; prisão na quarta (18).",
    ),
    Caso(
        id="wpp-041",
        modulo=_P,
        formato="texto",
        agora="2026-09-24 12:00",
        texto="""24/09/2026 10:02 - Escrivã Denise DENARC: Encaminhada
DENARC PRENDE CASAL COM 40 KG DE COCAÍNA EM PARANAGUÁ

A Divisão Estadual de Narcóticos (DENARC) prendeu nesta quarta-feira (23) um casal com 40 quilos de cocaína escondidos em um fundo falso de carro, em Paranaguá. A Delegacia de Polícia de Paranaguá apoiou a ação.

Delegado Leandro Quadros – DENARC
24/09/2026 10:03 - Escrivã Denise DENARC: Bom dia, o doutor pediu pra repassar. Denise Farias, escrivã
24/09/2026 10:03 - Escrivã Denise DENARC: <Mídia oculta>""",
        esperado={
            "titulo": Contem("40 kg de cocaína"),
            "unidade": "DENARC",
            "fonte": UmDe(Contem("Denise Farias"), Contem("Leandro Quadros")),
            "data": "2026-09-24",
            "inicio_pauta": "10:02",
            "jornalista": AUSENTE,
        },
        nota="Release encaminhado pela escrivã; Paranaguá (cadastrada) só apoiou; prisão em 23/09.",
    ),
    Caso(
        id="wpp-042",
        modulo=_P,
        formato="texto",
        agora="2026-12-08 11:00",
        texto="""08/12/26 09:40 - Inv. Rogério Ortigueira: Bom dia!
08/12/26 09:40 - Inv. Rogério Ortigueira: Esta mensagem foi apagada
08/12/26 09:42 - Inv. Rogério Ortigueira: Corrigindo o texto, eram quatro presos e não três:

OPERAÇÃO ÁGATA PRENDE QUATRO POR ROUBOS A CAMINHONEIROS NA PR-340

A Delegacia de Polícia de Ortigueira deflagrou nesta terça-feira (8) a Operação Ágata contra um grupo que roubava caminhoneiros na PR-340. Quatro homens foram presos.

Rogério Wisniewski – investigador
08/12/26 09:43 - Inv. Rogério Ortigueira: <Mídia oculta>""",
        esperado={
            "titulo": Contem("Operação Ágata"),
            "unidade": "Delegacia de Polícia de Ortigueira",
            "fonte": Contem("Rogério Wisniewski"),
            "data": "2026-12-08",
            "inicio_pauta": "09:40",
            "jornalista": AUSENTE,
        },
        nota="Mensagem apagada e texto corrigido; a conversa da pauta começa às 09:40.",
    ),
    Caso(
        id="wpp-043",
        modulo=_P,
        formato="texto",
        agora="2026-11-30 11:00",
        texto="""[30/11/2026, 09:59:59] Karina DFRV: Bom dia!
[30/11/2026, 10:00:31] Karina DFRV: DFRV DESMONTA DESMANCHE CLANDESTINO EM SÃO JOSÉ DOS PINHAIS

A Delegacia de Furtos e Roubos de Veículos (DFRV) localizou nesta segunda-feira (30) um desmanche clandestino com peças de 15 veículos roubados em São José dos Pinhais. Dois homens foram presos.

Karina Pedroso, escrivã
‎[30/11/2026, 10:00:48] Karina DFRV: ‎<anexado: 00000155-PHOTO-2026-11-30-10-00-48.jpg>""",
        esperado={
            "titulo": Contem("desmanche clandestino"),
            "unidade": "Delegacia de Furtos e Roubos de Veículos",
            "fonte": Contem("Karina Pedroso"),
            "data": "2026-11-30",
            "inicio_pauta": "09:59",
            "jornalista": AUSENTE,
        },
        nota="09:59:59 é 09:59 (segundos não arredondam).",
    ),
    Caso(
        id="wpp-044",
        modulo=_P,
        formato="texto",
        agora="2026-08-17 09:00",
        texto="""[15/08/2026, 21:14:06] Inv. Mariane NUCRIA: Boa noite, desculpem o sábado
[15/08/2026, 21:14:40] Inv. Mariane NUCRIA: NUCRIA RESGATA ADOLESCENTE MANTIDA EM CÁRCERE PRIVADO EM CURITIBA

O NUCRIA de Curitiba resgatou nesta sexta-feira (14) uma adolescente de 15 anos que era mantida em cárcere privado pelo padrasto no bairro Sítio Cercado. Ele foi preso em flagrante.

Mariane Toaldo – investigadora
[17/08/2026, 08:30:12] Ascom PCPR: Bom dia, Mariane! Vamos publicar hoje.""",
        esperado={
            "titulo": Contem("cárcere privado"),
            "unidade": "NUCRIA de Curitiba",
            "fonte": Contem("Mariane Toaldo"),
            "data": "2026-08-15",
            "inicio_pauta": "21:14",
            "jornalista": AUSENTE,
        },
        nota="Pauta no sábado (15) à noite, resposta na segunda (17); resgate na sexta (14).",
    ),
    Caso(
        id="wpp-045",
        modulo=_P,
        formato="texto",
        agora="2026-10-30 16:00",
        texto="""30/10/2026 14:02 - Ascom PCPR adicionou Del. Otávio Campo Mourão
30/10/2026 14:02 - Ascom PCPR: Doutor, adicionei o senhor no grupo de pautas. Pode mandar aqui
30/10/2026 14:37 - Del. Otávio Campo Mourão: Obrigado! Já tem uma:
30/10/2026 14:37 - Del. Otávio Campo Mourão: PCPR PRENDE SUSPEITO DE ABUSO SEXUAL CONTRA ENTEADA EM CAMPO MOURÃO

A Delegacia de Polícia de Campo Mourão cumpriu nesta sexta-feira (30) mandado de prisão contra um homem de 41 anos suspeito de abusar sexualmente da enteada. O NUCRIA de Curitiba colaborou com a escuta especializada.

Delegado Otávio Rizzardi
30/10/2026 14:38 - Ascom PCPR: Obrigada, doutor!""",
        esperado={
            "titulo": Contem("abuso sexual contra enteada"),
            "unidade": "Delegacia de Polícia de Campo Mourão",
            "fonte": Contem("Otávio Rizzardi"),
            "data": "2026-10-30",
            "inicio_pauta": "14:37",
            "jornalista": AUSENTE,
        },
        nota="A Ascom adiciona e escreve às 14:02; a pauta chega às 14:37; NUCRIA é colaborador.",
    ),
]

CASOS = _IMPRENSA + _PUBLICACOES
