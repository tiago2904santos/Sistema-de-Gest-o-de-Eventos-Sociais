import io
import struct
from datetime import date, datetime, timedelta, timezone
from email.message import EmailMessage
from unittest import mock

from django.test import SimpleTestCase, override_settings

from core.leitura.mensagem import (
    MensagemIlegivel,
    assunto_sem_prefixos,
    html_para_texto,
    ler_mensagem,
    ler_texto_colado,
    mascarar_para_log,
    separar_assinatura,
)

# ---------------------------------------------------------------------------
# .msg sintético: o olefile só lê, então o CFB (OLE2) mínimo é montado aqui.
# ---------------------------------------------------------------------------

_LIVRE, _FIM, _SETOR_FAT, _SEM_ENTRADA = 0xFFFFFFFF, 0xFFFFFFFE, 0xFFFFFFFD, 0xFFFFFFFF
_ENTRADA = "<64sHBBIII16sIQQIQ"


def cfb(entradas):
    """Arquivo CFB v3 com os streams dados: {("storage", "stream"): bytes}.

    Streams menores que 4096 bytes vão para o mini stream, como manda o
    formato; os irmãos de cada storage ficam encadeados pela direita (o
    olefile não confere as cores da árvore rubro-negra).
    """
    raiz = {"nome": "Root Entry", "tipo": 5, "filhos": {}, "dados": b""}
    for caminho, dados in entradas.items():
        atual = raiz
        for parte in caminho[:-1]:
            atual = atual["filhos"].setdefault(parte, {"nome": parte, "tipo": 1, "filhos": {}, "dados": b""})
        atual["filhos"][caminho[-1]] = {"nome": caminho[-1], "tipo": 2, "filhos": {}, "dados": dados}
    nos = []

    def numerar(no):
        no["id"] = len(nos)
        nos.append(no)
        for filho in no["filhos"].values():
            numerar(filho)

    numerar(raiz)
    setores, fat = [], []

    def alocar(dados):
        if not dados:
            return _FIM
        inicio = len(setores)
        quantos = (len(dados) + 511) // 512
        for k in range(quantos):
            setores.append(dados[k * 512:(k + 1) * 512].ljust(512, b"\0"))
            fat.append(inicio + k + 1 if k < quantos - 1 else _FIM)
        return inicio

    mini, minifat = bytearray(), []
    for no in nos:
        no["inicio"] = 0
        if no["tipo"] == 2 and len(no["dados"]) < 4096:
            if not no["dados"]:
                no["inicio"] = _FIM
                continue
            no["inicio"] = len(mini) // 64
            quantos = (len(no["dados"]) + 63) // 64
            minifat += [no["inicio"] + k + 1 if k < quantos - 1 else _FIM for k in range(quantos)]
            mini += no["dados"].ljust(quantos * 64, b"\0")
    raiz["dados"] = bytes(mini)
    raiz["inicio"] = alocar(raiz["dados"])
    for no in nos:
        if no["tipo"] == 2 and len(no["dados"]) >= 4096:
            no["inicio"] = alocar(no["dados"])
    tabela_minifat = b"".join(struct.pack("<I", x) for x in minifat)
    setores_minifat = (len(tabela_minifat) + 511) // 512
    inicio_minifat = alocar(tabela_minifat.ljust(setores_minifat * 512, b"\xff")) if minifat else _FIM

    for no in nos:
        no.update(esquerda=_SEM_ENTRADA, direita=_SEM_ENTRADA, filho=_SEM_ENTRADA)
    for no in nos:
        irmaos = sorted(no["filhos"].values(), key=lambda f: (len(f["nome"]), f["nome"].upper()))
        if irmaos:
            no["filho"] = irmaos[0]["id"]
            for a, b in zip(irmaos, irmaos[1:]):
                a["direita"] = b["id"]
    diretorio = bytearray()
    for no in nos:
        nome = no["nome"].encode("utf-16-le") + b"\0\0"
        diretorio += struct.pack(
            _ENTRADA, nome.ljust(64, b"\0"), len(nome), no["tipo"], 1, no["esquerda"], no["direita"],
            no["filho"], b"\0" * 16, 0, 0, 0, no["inicio"], len(no["dados"]) if no["tipo"] != 1 else 0,
        )
    while len(diretorio) % 512:
        diretorio += struct.pack(
            _ENTRADA, b"\0" * 64, 0, 0, 0, _SEM_ENTRADA, _SEM_ENTRADA, _SEM_ENTRADA, b"\0" * 16, 0, 0, 0, 0, 0
        )
    inicio_diretorio = alocar(bytes(diretorio))
    setores_fat = 1
    while len(setores) + setores_fat > setores_fat * 128:
        setores_fat += 1
    indices_fat = list(range(len(setores), len(setores) + setores_fat))
    fat += [_SETOR_FAT] * setores_fat
    fat += [_LIVRE] * (setores_fat * 128 - len(fat))
    for k in range(setores_fat):
        setores.append(b"".join(struct.pack("<I", x) for x in fat[k * 128:(k + 1) * 128]))
    cabecalho = struct.pack(
        "<8s16sHHHHH6sIIIIIIIII", b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1", b"\0" * 16, 0x3E, 3, 0xFFFE, 9, 6,
        b"\0" * 6, 0, setores_fat, inicio_diretorio, 0, 4096, inicio_minifat, setores_minifat, _FIM, 0,
    ) + b"".join(struct.pack("<I", x) for x in indices_fat + [_LIVRE] * (109 - len(indices_fat)))
    return cabecalho + b"".join(setores)


def _u(texto):
    return texto.encode("utf-16-le")


def _propriedades(cabecalho, valores):
    """Stream "__properties_version1.0": {id: (tipo, 8 bytes)}."""
    corpo = b"".join(
        struct.pack("<II", (ident << 16) | tipo, 6) + valor.ljust(8, b"\0") for ident, (tipo, valor) in valores.items()
    )
    return b"\0" * cabecalho + corpo


def _filetime(quando):
    return struct.pack("<Q", int((quando - datetime(1601, 1, 1, tzinfo=timezone.utc)) / timedelta(microseconds=1)) * 10)


def msg_sintetico(*, assunto="Pedido de palestra", corpo="", html=None, rtf=None, transporte=None,
                  com_data=True, anexos=(), embutida=None):
    raiz = ()
    entradas = {raiz + ("__substg1.0_0037001F",): _u(assunto)}
    if corpo:
        entradas[("__substg1.0_1000001F",)] = _u(corpo)
    if html is not None:
        entradas[("__substg1.0_10130102",)] = html
    if rtf is not None:
        entradas[("__substg1.0_10090102",)] = rtf
    entradas[("__substg1.0_0C1A001F",)] = _u("Maria Exemplo")
    entradas[("__substg1.0_0C1F001F",)] = _u("/O=EXCHANGELABS/OU=EXCHANGE ADMINISTRATIVE GROUP/CN=MARIA")
    entradas[("__substg1.0_5D01001F",)] = _u("Maria.Exemplo@Escola.PR.gov.br")
    if transporte is not None:
        entradas[("__substg1.0_007D001F",)] = _u(transporte)
    props = {0x3FFD: (0x0003, struct.pack("<I", 1252))}
    if com_data:
        props[0x0039] = (0x0040, _filetime(datetime(2026, 9, 24, 17, 32, tzinfo=timezone.utc)))
    entradas[("__properties_version1.0",)] = _propriedades(32, props)
    for numero, (nome, dados, extra) in enumerate(anexos):
        pasta = f"__attach_version1.0_#{numero:08X}"
        entradas[(pasta, "__substg1.0_3707001F")] = _u(nome)
        entradas[(pasta, "__substg1.0_37010102")] = dados
        for prop, valor in (extra or {}).items():
            entradas[(pasta, f"__substg1.0_{prop}001F")] = _u(valor)
        entradas[(pasta, "__properties_version1.0")] = _propriedades(8, {0x3705: (0x0003, struct.pack("<I", 1))})
    if embutida is not None:
        pasta = f"__attach_version1.0_#{len(anexos):08X}"
        interna = (pasta, "__substg1.0_3701000D")
        entradas[(pasta, "__properties_version1.0")] = _propriedades(8, {0x3705: (0x0003, struct.pack("<I", 5))})
        entradas[interna + ("__substg1.0_0037001F",)] = _u(embutida["assunto"])
        entradas[interna + ("__substg1.0_1000001F",)] = _u(embutida["corpo"])
        entradas[interna + ("__substg1.0_0C1A001F",)] = _u(embutida["nome"])
        entradas[interna + ("__substg1.0_5D01001F",)] = _u(embutida["email"])
        entradas[interna + ("__properties_version1.0",)] = _propriedades(24, {})
    return cfb(entradas)


# RTF comprimido do exemplo da especificação MS-OXRTFCP ("hello world").
RTF_COMPRIMIDO_EXEMPLO = bytes.fromhex(
    "2d0000002b0000004c5a4675f1c5c7a703000a007263706731323542320af32068656c090020627705b06c647d0a800fa0"
)


def pdf_de_linhas(*paginas):
    """PDF com texto de verdade (o e-mail "impresso"), uma lista de linhas por página."""
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas

    saida = io.BytesIO()
    folha = canvas.Canvas(saida, pagesize=A4)
    for linhas in paginas:
        y = 800
        for linha in linhas:
            folha.drawString(40, y, linha)
            y -= 16
        folha.showPage()
    folha.save()
    return saida.getvalue()


def pdf_so_imagem():
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas

    saida = io.BytesIO()
    folha = canvas.Canvas(saida, pagesize=A4)
    folha.rect(40, 40, 200, 200, fill=1)
    folha.showPage()
    folha.save()
    return saida.getvalue()


def email_basico(**kwargs):
    mensagem = EmailMessage()
    mensagem["Subject"] = kwargs.get("assunto", "Solicitação de palestra – Colégio Estadual Exemplo")
    mensagem["From"] = kwargs.get("de", "Maria Exemplo <maria.exemplo@escola.pr.gov.br>")
    mensagem["To"] = "ascom@pc.pr.gov.br"
    mensagem["Date"] = kwargs.get("data", "Thu, 24 Sep 2026 14:32:00 -0300")
    mensagem["Message-ID"] = kwargs.get("message_id", "<pedido-1@escola.pr.gov.br>")
    return mensagem


HTML_PEDIDO = (
    "<html><head><title>x</title><style>p{color:red}</style><script>alert('oi')</script></head><body>"
    "<p>Bom dia,</p><p>Solicitamos palestra sobre <b>golpes digitais</b> no dia 15/10 às 14h, "
    "para cerca de 120 alunos, em Ponta Grossa.</p>"
    "<p>Mais informações <a href='https://exemplo.invalid/rastreio'>aqui</a>.<img src='https://exemplo.invalid/pixel.png'></p>"
    "<p>Att,<br>Maria Exemplo<br>Diretora<br>(42) 99999-0000</p>"
    "<p>Esta mensagem é confidencial e destinada exclusivamente ao destinatário.</p></body></html>"
)


class EmlTests(SimpleTestCase):
    def test_eml_so_html_com_anexo(self):
        email = email_basico()
        email.set_content(HTML_PEDIDO, subtype="html")
        email.add_attachment(b"%PDF-1.4 oficio", maintype="application", subtype="pdf", filename="oficio_pedido.pdf")
        mensagem = ler_mensagem("pedido.eml", email.as_bytes())

        self.assertEqual(mensagem.origem, "eml")
        self.assertEqual(mensagem.assunto, "Solicitação de palestra – Colégio Estadual Exemplo")
        self.assertEqual((mensagem.remetente_nome, mensagem.remetente_email), ("Maria Exemplo", "maria.exemplo@escola.pr.gov.br"))
        self.assertEqual(mensagem.enviado_em, datetime(2026, 9, 24, 17, 32, tzinfo=timezone.utc))
        self.assertEqual(mensagem.data_referencia, date(2026, 9, 24))
        self.assertEqual(mensagem.message_id, "<pedido-1@escola.pr.gov.br>")
        self.assertTrue(mensagem.corpo.startswith("Bom dia,\n"))
        self.assertIn("Solicitamos palestra sobre golpes digitais no dia 15/10", mensagem.corpo)
        self.assertNotIn("alert", mensagem.corpo)
        self.assertNotIn("https://", mensagem.corpo)
        self.assertNotIn("confidencial", mensagem.corpo + mensagem.assinatura)
        self.assertEqual(mensagem.assinatura, "Maria Exemplo\nDiretora\n(42) 99999-0000")
        self.assertEqual(mensagem.anexos, [("oficio_pedido.pdf", b"%PDF-1.4 oficio")])

    def test_prefere_texto_simples_e_ignora_imagem_da_assinatura(self):
        email = email_basico(assunto="=?utf-8?q?Pedido_de_coffee_break_=E2=80=93_S=C3=A3o_Jos=C3=A9?=")
        email.set_content("Bom dia,\nPedimos coffee break para 80 pessoas.\n\nAtenciosamente,\nJoão\n")
        email.add_alternative("<p>Bom dia,</p><p>Pedimos coffee break para 80 pessoas.</p>", subtype="html")
        html = email.get_payload()[1]
        html.add_related(b"\x89PNG logo", maintype="image", subtype="png", cid="<logo@x>", filename="image001.png", disposition="inline")
        mensagem = ler_mensagem("pedido.eml", email.as_bytes())
        self.assertEqual(mensagem.assunto, "Pedido de coffee break – São José")
        self.assertEqual(mensagem.corpo, "Bom dia,\nPedimos coffee break para 80 pessoas.")
        self.assertEqual(mensagem.assinatura, "João")
        self.assertEqual(mensagem.anexos, [])

    def test_encaminhamento_do_gmail_usa_a_mensagem_mais_interna(self):
        email = email_basico(assunto="Fwd: Pedido de unidade móvel", de="Chefe <chefe@pc.pr.gov.br>")
        email.set_content(
            "Por favor, atender.\n\n"
            "---------- Forwarded message ---------\n"
            "De: João Silva <joao@prefeitura.pr.gov.br>\n"
            "Date: qui., 24 de set. de 2026 às 09:15\n"
            "Subject: Pedido de unidade móvel\n"
            "To: <gabinete@pc.pr.gov.br>\n\n\n"
            "Bom dia! Pedimos a unidade móvel para emissão de RG em Castro, no dia 20/10.\n\n"
            "--\nJoão Silva\nPrefeitura de Castro\n"
        )
        mensagem = ler_mensagem("fwd.eml", email.as_bytes())
        self.assertEqual((mensagem.remetente_nome, mensagem.remetente_email), ("João Silva", "joao@prefeitura.pr.gov.br"))
        self.assertEqual(mensagem.encaminhada_por, "Chefe <chefe@pc.pr.gov.br>")
        self.assertEqual(mensagem.assunto, "Pedido de unidade móvel")
        self.assertEqual(mensagem.enviado_em.replace(tzinfo=None), datetime(2026, 9, 24, 9, 15))
        self.assertEqual(mensagem.corpo, "Bom dia! Pedimos a unidade móvel para emissão de RG em Castro, no dia 20/10.")
        self.assertEqual(mensagem.assinatura, "João Silva\nPrefeitura de Castro")
        self.assertNotIn("atender", mensagem.corpo)

    def test_encaminhado_como_anexo(self):
        interna = email_basico(assunto="Palestra no colégio", de="Ana <ana@colegio.pr.gov.br>",
                               data="Mon, 21 Sep 2026 10:00:00 -0300", message_id="<interna@x>")
        interna.set_content("Solicitamos palestra no dia 05/10.\n\nAtt,\nAna\nPedagoga\n")
        interna.add_attachment(b"%PDF-1.4 oficio", maintype="application", subtype="pdf", filename="oficio.pdf")
        externa = email_basico(assunto="ENC: Palestra no colégio", de="Chefe <chefe@pc.pr.gov.br>")
        externa.set_content("Segue.")
        externa.add_attachment(interna)
        mensagem = ler_mensagem("enc.eml", externa.as_bytes())
        self.assertEqual(mensagem.remetente_email, "ana@colegio.pr.gov.br")
        self.assertEqual(mensagem.encaminhada_por, "Chefe <chefe@pc.pr.gov.br>")
        self.assertEqual(mensagem.corpo, "Solicitamos palestra no dia 05/10.")
        self.assertEqual(mensagem.assinatura, "Ana\nPedagoga")
        self.assertEqual(mensagem.anexos, [("oficio.pdf", b"%PDF-1.4 oficio")])
        self.assertEqual(mensagem.message_id, "<pedido-1@escola.pr.gov.br>")

    def test_resposta_corta_a_citacao(self):
        email = email_basico(assunto="RES: Solicitação de palestra")
        email.set_content(
            "Confirmo: 120 alunos, dia 15/10 às 14h.\n\n"
            "Em qua., 23 de set. de 2026 às 10:00, ASCOM <ascom@pc.pr.gov.br>\nescreveu:\n"
            "> Quantos alunos serão?\n> Qual o horário?\n"
        )
        mensagem = ler_mensagem("res.eml", email.as_bytes())
        self.assertEqual(mensagem.corpo, "Confirmo: 120 alunos, dia 15/10 às 14h.")
        self.assertIn("Quantos alunos", mensagem.citado)
        self.assertEqual(mensagem.remetente_nome, "Maria Exemplo")

    def test_resposta_do_outlook_com_cabecalho_citado(self):
        email = email_basico(assunto="RES: Solicitação de coffee break")
        email.set_content(
            "Segue o ofício. O coffee será para 80 pessoas no dia 10/10.\n\n"
            "________________________________\n"
            "De: ASCOM <ascom@pc.pr.gov.br>\nEnviado: quarta-feira, 23 de setembro de 2026 10:00\n"
            "Para: Maria Exemplo\nAssunto: Solicitação de coffee break\n\nFavor enviar o ofício.\n"
        )
        mensagem = ler_mensagem("res.eml", email.as_bytes())
        self.assertEqual(mensagem.corpo, "Segue o ofício. O coffee será para 80 pessoas no dia 10/10.")
        self.assertEqual(mensagem.remetente_email, "maria.exemplo@escola.pr.gov.br")
        self.assertIn("Favor enviar o ofício.", mensagem.citado)

    def test_mht_do_outlook(self):
        email = email_basico()
        email.set_content("<div>Linha um</div><div>Linha dois</div><blockquote>citado</blockquote>", subtype="html")
        mensagem = ler_mensagem("pedido.mht", email.as_bytes())
        self.assertEqual(mensagem.origem, "mht")
        self.assertEqual(mensagem.corpo, "Linha um\nLinha dois")
        self.assertEqual(mensagem.citado, "> citado")

    def test_charset_desconhecido_nao_derruba(self):
        bruto = (
            b"From: Maria <maria@x.pr.gov.br>\r\nSubject: Teste\r\nDate: Thu, 24 Sep 2026 14:32:00 -0300\r\n"
            b"MIME-Version: 1.0\r\nContent-Type: text/plain; charset=x-inexistente\r\n\r\nPalestra em 15/10\r\n"
        )
        mensagem = ler_mensagem("x.eml", bruto)
        self.assertEqual(mensagem.corpo, "Palestra em 15/10")

    def test_eml_sem_extensao_reconhecido_pelo_conteudo(self):
        email = email_basico()
        email.set_content("Pedido simples.")
        self.assertEqual(ler_mensagem("arquivo", email.as_bytes()).origem, "eml")


class LimitesTests(SimpleTestCase):
    def test_arquivo_vazio_ou_estranho(self):
        with self.assertRaisesMessage(MensagemIlegivel, "vazio"):
            ler_mensagem("x.eml", b"")
        with self.assertRaisesMessage(MensagemIlegivel, "Formato não reconhecido"):
            ler_mensagem("x.bin", bytes(range(256)) * 4)

    @override_settings(LEITURA_EMAIL_MAX_BYTES=100)
    def test_limite_do_arquivo(self):
        with self.assertRaisesMessage(MensagemIlegivel, "limite"):
            ler_mensagem("x.txt", b"a" * 101)

    @override_settings(LEITURA_EMAIL_ANEXO_MAX_BYTES=10, LEITURA_EMAIL_MAX_ANEXOS=1)
    def test_limite_dos_anexos(self):
        email = email_basico()
        email.set_content("Pedido.")
        email.add_attachment(b"pequeno", maintype="application", subtype="octet-stream", filename="a.txt")
        email.add_attachment(b"grande demais", maintype="application", subtype="octet-stream", filename="b.pdf")
        email.add_attachment(b"outro", maintype="application", subtype="octet-stream", filename="../../c.txt")
        mensagem = ler_mensagem("x.eml", email.as_bytes())
        self.assertEqual(mensagem.anexos, [("a.txt", b"pequeno")])
        self.assertTrue(any("b.pdf" in aviso for aviso in mensagem.avisos))
        self.assertTrue(any("só os 1 primeiros" in aviso for aviso in mensagem.avisos))

    def test_nome_do_anexo_sem_caminho(self):
        email = email_basico()
        email.set_content("Pedido.")
        email.add_attachment(b"x", maintype="application", subtype="octet-stream", filename="..\\..\\evil.txt")
        self.assertEqual(ler_mensagem("x.eml", email.as_bytes()).anexos[0][0], "evil.txt")

    def test_msg_corrompido_vira_mensagem_para_a_tela(self):
        with self.assertRaises(MensagemIlegivel):
            ler_mensagem("x.msg", b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + b"\0" * 600)


class MsgTests(SimpleTestCase):
    def test_msg_com_cabecalhos_de_transporte_e_anexos(self):
        transporte = (
            "Received: from x\r\nFrom: Maria Exemplo <maria.exemplo@escola.pr.gov.br>\r\n"
            "Date: Thu, 24 Sep 2026 14:32:00 -0300\r\nMessage-ID: <msg-1@escola>\r\nSubject: Pedido\r\n\r\n"
        )
        dados = msg_sintetico(
            corpo="Bom dia,\r\nSolicitamos palestra em Ponta Grossa [cid:image001.png@01DC] no dia 15/10.\r\n\r\n"
                  "Atenciosamente,\r\nMaria Exemplo\r\nDiretora\r\n",
            transporte=transporte,
            com_data=False,
            anexos=[
                ("oficio.pdf", b"%PDF-1.4 " + b"x" * 5000, None),
                ("image001.png", b"\x89PNG", {"3712": "image001.png@01DC", "370E": "image/png"}),
            ],
        )
        mensagem = ler_mensagem("pedido.msg", dados)
        self.assertEqual(mensagem.origem, "msg")
        self.assertEqual(mensagem.assunto, "Pedido de palestra")
        self.assertEqual((mensagem.remetente_nome, mensagem.remetente_email), ("Maria Exemplo", "maria.exemplo@escola.pr.gov.br"))
        self.assertEqual(mensagem.enviado_em, datetime(2026, 9, 24, 17, 32, tzinfo=timezone.utc))
        self.assertEqual(mensagem.message_id, "<msg-1@escola>")
        self.assertEqual(mensagem.corpo, "Bom dia,\nSolicitamos palestra em Ponta Grossa no dia 15/10.")
        self.assertEqual(mensagem.assinatura, "Maria Exemplo\nDiretora")
        self.assertEqual([nome for nome, _ in mensagem.anexos], ["oficio.pdf"])
        self.assertEqual(len(mensagem.anexos[0][1]), 5009)

    def test_msg_sem_transporte_usa_a_data_das_propriedades(self):
        mensagem = ler_mensagem("x.msg", msg_sintetico(corpo="Pedido."))
        self.assertEqual(mensagem.enviado_em, datetime(2026, 9, 24, 17, 32, tzinfo=timezone.utc))

    def test_msg_so_com_html(self):
        html = "<html><body><p class=MsoNormal>Bom dia,</p><p class=MsoNormal>Pedido de café.</p></body></html>"
        mensagem = ler_mensagem("x.msg", msg_sintetico(html=html.encode("cp1252")))
        self.assertEqual(mensagem.corpo, "Bom dia,\nPedido de café.")

    def test_msg_so_com_rtf_comprimido(self):
        mensagem = ler_mensagem("x.msg", msg_sintetico(rtf=RTF_COMPRIMIDO_EXEMPLO))
        self.assertEqual(mensagem.corpo, "hello world")

    def test_msg_encaminhado_como_anexo(self):
        dados = msg_sintetico(
            assunto="ENC: Palestra",
            corpo="Segue.",
            embutida={"assunto": "Palestra", "corpo": "Pedimos palestra dia 05/10.", "nome": "Ana", "email": "ana@colegio.pr.gov.br"},
        )
        mensagem = ler_mensagem("x.msg", dados)
        self.assertEqual((mensagem.remetente_nome, mensagem.remetente_email), ("Ana", "ana@colegio.pr.gov.br"))
        self.assertEqual(mensagem.encaminhada_por, "Maria Exemplo <maria.exemplo@escola.pr.gov.br>")
        self.assertEqual(mensagem.corpo, "Pedimos palestra dia 05/10.")

    def test_msg_renomeado_e_lido_pelo_conteudo(self):
        self.assertEqual(ler_mensagem("pedido.eml", msg_sintetico(corpo="x")).origem, "msg")

    def test_documento_do_office_que_nao_e_email(self):
        with self.assertRaisesMessage(MensagemIlegivel, "não é um e-mail"):
            ler_mensagem("planilha.xls", cfb({("Workbook",): b"x" * 100}))


class PdfImpressoTests(SimpleTestCase):
    def test_outlook_em_portugues(self):
        dados = pdf_de_linhas([
            "Tiago Santos",
            "De: Maria Exemplo <maria@escola.pr.gov.br>",
            "Enviado em: quinta-feira, 24 de setembro de 2026 14:32",
            "Para: ASCOM <ascom@pc.pr.gov.br>",
            "Assunto: Solicitação de palestra",
            "Anexos: oficio.pdf",
            "",
            "Bom dia, solicitamos palestra no dia 15/10 às 14h.",
            "",
            "Atenciosamente,",
            "Maria Exemplo",
            "Diretora",
        ])
        mensagem = ler_mensagem("impresso.pdf", dados)
        self.assertEqual(mensagem.origem, "pdf")
        self.assertEqual(mensagem.assunto, "Solicitação de palestra")
        self.assertEqual(mensagem.remetente_email, "maria@escola.pr.gov.br")
        self.assertEqual(mensagem.enviado_em.replace(tzinfo=None), datetime(2026, 9, 24, 14, 32))
        self.assertIn("solicitamos palestra no dia 15/10", mensagem.corpo)
        self.assertNotIn("Tiago", mensagem.corpo)
        self.assertEqual(mensagem.assinatura, "Maria Exemplo\nDiretora")
        self.assertEqual(mensagem.anexos_citados, ["oficio.pdf"])
        self.assertTrue(any("oficio.pdf" in aviso for aviso in mensagem.avisos))

    def test_outlook_em_ingles_com_am_pm(self):
        dados = pdf_de_linhas([
            "From: Maria Exemplo <maria@escola.pr.gov.br>",
            "Sent: Thursday, September 24, 2026 2:32 PM",
            "To: ASCOM",
            "Subject: Coffee break",
            "",
            "Coffee break para 50 pessoas.",
        ])
        mensagem = ler_mensagem("x.pdf", dados)
        self.assertEqual(mensagem.enviado_em.replace(tzinfo=None), datetime(2026, 9, 24, 14, 32))
        self.assertEqual(mensagem.corpo, "Coffee break para 50 pessoas.")

    def test_gmail(self):
        dados = pdf_de_linhas([
            "24/09/2026, 14:40 Gmail - Solicitação de palestra",
            "Tiago Santos <tiago@gmail.com>",
            "Solicitação de palestra",
            "2 mensagens",
            "Maria Exemplo <maria@escola.pr.gov.br> 24 de setembro de 2026 às 14:32",
            "Para: tiago@gmail.com",
            "Bom dia, pedimos palestra no dia 15/10.",
            "Maria Exemplo",
            "Tiago Santos <tiago@gmail.com> 24 de setembro de 2026 às 15:00",
            "Para: Maria Exemplo <maria@escola.pr.gov.br>",
            "Recebido, obrigado.",
            "https://mail.google.com/mail/u/0/?ik=abc&view=pt 1/1",
        ])
        mensagem = ler_mensagem("gmail.pdf", dados)
        self.assertEqual(mensagem.assunto, "Solicitação de palestra")
        self.assertEqual((mensagem.remetente_nome, mensagem.remetente_email), ("Maria Exemplo", "maria@escola.pr.gov.br"))
        self.assertEqual(mensagem.enviado_em.replace(tzinfo=None), datetime(2026, 9, 24, 14, 32))
        self.assertIn("pedimos palestra no dia 15/10", mensagem.corpo)
        self.assertNotIn("Recebido", mensagem.corpo)
        self.assertIn("Recebido", mensagem.citado)
        self.assertNotIn("mail.google.com", mensagem.corpo + mensagem.citado)

    @mock.patch("core.leitura.mensagem._texto_por_ocr", return_value="")
    def test_pdf_so_imagem_sem_ocr_avisa(self, _ocr):
        mensagem = ler_mensagem("scan.pdf", pdf_so_imagem())
        self.assertEqual(mensagem.corpo, "")
        self.assertTrue(any("não tem texto" in aviso for aviso in mensagem.avisos))

    @mock.patch("core.leitura.mensagem._texto_por_ocr", return_value="Pedimos coffee break para 30 pessoas.")
    def test_pdf_so_imagem_com_ocr_avisa_para_conferir(self, _ocr):
        mensagem = ler_mensagem("scan.pdf", pdf_so_imagem())
        self.assertEqual(mensagem.corpo, "Pedimos coffee break para 30 pessoas.")
        self.assertTrue(any("OCR" in aviso for aviso in mensagem.avisos))

    def test_pdf_quebrado(self):
        with self.assertRaises(MensagemIlegivel), self.assertLogs("pypdf", level="WARNING"):
            ler_mensagem("x.pdf", b"%PDF-1.4\n" + b"lixo" * 50)


class TextoColadoTests(SimpleTestCase):
    def test_txt_em_cp1252(self):
        mensagem = ler_mensagem("pedido.txt", "Solicitação de palestra em São José.".encode("cp1252"))
        self.assertEqual((mensagem.origem, mensagem.corpo), ("txt", "Solicitação de palestra em São José."))

    def test_txt_do_outlook_em_ingles_nao_e_lido_como_mime(self):
        texto = (
            "From: Maria Exemplo <maria@escola.pr.gov.br>\nSent: Thursday, September 24, 2026 2:32 PM\n"
            "To: ASCOM\nSubject: Palestra\n\nPedido de palestra.\n"
        )
        mensagem = ler_mensagem("colado.txt", texto.encode("utf-8"))
        self.assertEqual(mensagem.origem, "txt")
        self.assertEqual(mensagem.enviado_em.replace(tzinfo=None), datetime(2026, 9, 24, 14, 32))
        self.assertEqual(mensagem.corpo, "Pedido de palestra.")

    def test_texto_do_outlook_colado_com_resposta(self):
        texto = (
            "De: Maria Exemplo <maria@escola.pr.gov.br>\n"
            "Enviado em: quinta-feira, 24 de setembro de 2026 14:32\n"
            "Para: ASCOM\nAssunto: RES: Palestra\n\n"
            "Confirmo o dia 15/10.\n\nAtt,\nMaria\n\n"
            "De: ASCOM\nEnviado em: quarta-feira, 23 de setembro de 2026 10:00\n"
            "Para: Maria Exemplo\nAssunto: Palestra\n\nQual a data?\n"
        )
        mensagem = ler_texto_colado(texto)
        self.assertEqual(mensagem.origem, "texto")
        self.assertEqual(mensagem.assunto, "RES: Palestra")
        self.assertEqual(mensagem.assunto_limpo, "Palestra")
        self.assertEqual(mensagem.corpo, "Confirmo o dia 15/10.")
        self.assertEqual(mensagem.assinatura, "Maria")
        self.assertIn("Qual a data?", mensagem.citado)

    def test_encaminhamento_do_apple_mail_com_citacao(self):
        texto = (
            "Veja abaixo.\n\nBegin forwarded message:\n\n"
            "> From: Ana <ana@colegio.pr.gov.br>\n> Subject: Palestra\n> Date: 21 September 2026 10:00\n"
            "> To: ascom@pc.pr.gov.br\n>\n> Pedimos palestra no dia 05/10.\n"
        )
        mensagem = ler_texto_colado(texto)
        self.assertEqual(mensagem.remetente_email, "ana@colegio.pr.gov.br")
        self.assertEqual(mensagem.corpo, "Pedimos palestra no dia 05/10.")

    def test_whatsapp_exportado(self):
        texto = (
            "[24/09/2026 14:32] Maria Exemplo: Bom dia! Gostaria de agendar uma palestra\n"
            "para 80 alunos\n"
            "[24/09/2026 14:33] Maria Exemplo: <Mídia oculta>\n"
            "[24/09/2026 14:40] ASCOM: Qual a data?\n"
        )
        mensagem = ler_texto_colado(texto)
        self.assertEqual(mensagem.origem, "whatsapp")
        self.assertEqual(mensagem.remetente_nome, "Maria Exemplo")
        self.assertEqual(mensagem.enviado_em.replace(tzinfo=None), datetime(2026, 9, 24, 14, 32))
        self.assertEqual(mensagem.corpo, "Bom dia! Gostaria de agendar uma palestra\npara 80 alunos\nQual a data?")

    def test_whatsapp_web_e_android(self):
        self.assertEqual(ler_texto_colado("[14:32, 24/09/2026] Ana: palestra amanhã").remetente_nome, "Ana")
        self.assertEqual(ler_texto_colado("24/09/2026 14:32 - Ana: palestra amanhã").remetente_nome, "Ana")

    def test_texto_vazio(self):
        with self.assertRaises(MensagemIlegivel):
            ler_texto_colado("   ")


class AssinaturaTests(SimpleTestCase):
    def test_fechos(self):
        for fecho in ("Att,", "Atenciosamente,", "Cordialmente", "Respeitosamente,", "--"):
            with self.subTest(fecho=fecho):
                corpo, assinatura = separar_assinatura(f"Pedido de palestra.\n\n{fecho}\nMaria\nDiretora")
                self.assertEqual((corpo, assinatura), ("Pedido de palestra.", "Maria\nDiretora"))

    def test_fecho_e_nome_na_mesma_linha(self):
        self.assertEqual(separar_assinatura("Pedido.\nAtt, Maria Exemplo"), ("Pedido.", "Maria Exemplo"))

    def test_sem_fecho_o_ultimo_bloco_com_nome_e_telefone(self):
        corpo, assinatura = separar_assinatura("Pedido de palestra.\n\nMaria Exemplo\nDiretora\n(42) 99999-0000")
        self.assertEqual((corpo, assinatura), ("Pedido de palestra.", "Maria Exemplo\nDiretora\n(42) 99999-0000"))

    def test_obrigado_no_meio_do_texto_nao_corta(self):
        texto = "Obrigado pelo retorno.\n" + "\n".join(f"Linha {n} do pedido com detalhes." for n in range(15))
        self.assertEqual(separar_assinatura(texto), (texto, ""))

    def test_enviado_do_iphone_sai(self):
        self.assertEqual(separar_assinatura("Pedido.\n\nEnviado do meu iPhone"), ("Pedido.", ""))


class AuxiliaresTests(SimpleTestCase):
    def test_html_nao_gruda_paragrafos(self):
        self.assertEqual(html_para_texto("<p>Bom dia,</p><p>Solicitamos</p>"), "Bom dia,\n\nSolicitamos")
        self.assertEqual(html_para_texto("Bom dia,<br>Solicitamos &amp; aguardo"), "Bom dia,\nSolicitamos & aguardo")
        self.assertEqual(html_para_texto("<table><tr><td>Data</td><td>15/10</td></tr><tr><td>Local</td></tr></table>"),
                         "Data 15/10\nLocal")

    def test_html_descarta_script_e_link(self):
        texto = html_para_texto("<script>document.cookie</script><style>x{}</style><a href='http://x.invalid'>clique</a>")
        self.assertEqual(texto, "clique")

    def test_assunto_sem_prefixos(self):
        self.assertEqual(assunto_sem_prefixos("RES: ENC: [EXTERNO] Fwd: Pedido de palestra"), "Pedido de palestra")
        self.assertEqual(assunto_sem_prefixos("Resposta ao ofício"), "Resposta ao ofício")

    def test_mascarar_para_log(self):
        texto = mascarar_para_log("CPF 123.456.789-00, fone (41) 99999-0000, maria@escola.pr.gov.br")
        self.assertNotIn("123.456", texto)
        self.assertNotIn("99999", texto)
        self.assertNotIn("maria@", texto)
        self.assertIn("m***@escola", texto)


class GmailImpressoRealTests(SimpleTestCase):
    """Os jeitos de o Gmail imprimir que os e-mails de verdade trouxeram."""

    def test_assunto_e_para_em_mais_de_uma_linha_e_anexos_no_fim(self):
        dados = pdf_de_linhas([
            "POLICIA CIVIL DO PARANA - ASSESSORIA DE COMUNICACAO SOCIAL",
            "<ascom@exemplo.pr.gov.br>",
            "Fwd: Proposta de Parceria e Sediamento de Evento – Programa na Comunidade e",
            "Centro Universitário Exemplo",
            "1 mensagem",
            "Ana Coordenadora <ana@universidade.exemplo> 21 de setembro de 2026 às 20:56",
            "Para: PCPR - ASSESSORIA <ascom@exemplo.pr.gov.br>, Thiago Monitor",
            "<monitor@exemplo.com>, Wilson Apoio <wilson@universidade.exemplo>",
            "Prezados, boa noite.",
            "Gostaríamos de sediar uma edição do evento no nosso campus, no dia 20/11/2026.",
            "Atenciosamente,",
            "Ana Coordenadora",
            "Coordenadora do curso de Direito",
            "OFÍCIO CONVITE.docx",
            "15K",
            "23/09/2026, 10:09 E-mail de PR - Polícia Civil - Fwd: Proposta de Parceria",
            "https://mail.google.com/mail/u/0/?ik=abc&view=pt 1/1",
        ])
        mensagem = ler_mensagem("gmail.pdf", dados)
        self.assertEqual(
            mensagem.assunto_limpo,
            "Proposta de Parceria e Sediamento de Evento – Programa na Comunidade e Centro Universitário Exemplo",
        )
        self.assertEqual(mensagem.remetente_email, "ana@universidade.exemplo")
        self.assertTrue(mensagem.corpo.startswith("Prezados, boa noite."), mensagem.corpo)
        self.assertNotIn("monitor@exemplo.com", mensagem.corpo)
        self.assertEqual(mensagem.anexos_citados, ["OFÍCIO CONVITE.docx"])
        self.assertNotIn("15K", mensagem.corpo + mensagem.assinatura)
        self.assertEqual(mensagem.assinatura, "Ana Coordenadora\nCoordenadora do curso de Direito")

    def test_rodape_legal_sem_linha_em_branco_nao_apaga_o_corpo(self):
        dados = pdf_de_linhas([
            "ASSESSORIA <ascom@exemplo.pr.gov.br>",
            "Solicitação de Coffee Break",
            "1 mensagem",
            "ADRIANA EXEMPLO <ass.exemplo@exemplo.pr.gov.br> 22 de setembro de 2026 às 13:26",
            "Para: ASSESSORIA <ascom@exemplo.pr.gov.br>",
            "Prezado(s),",
            "Solicito a disponibilidade de coffee break para:",
            "Data: 28 de setembro de 2026 (segunda-feira)",
            "Horário: 15h30min",
            "Local: Delegacia Cidadã - Auditório",
            "Quantidade de pessoas: 100",
            "At.te,",
            "--",
            "ADRIANA EXEMPLO",
            "Assessora da 15ª SDP",
            "(45) 99999-0000 | ass.exemplo@exemplo.pr.gov.br",
            "Esta mensagem pode conter informações confidenciais e/ou privilegiadas. É vedado o uso",
            "destinatários. Em caso de recebimento por engano, por favor, avise o remetente.",
        ])
        mensagem = ler_mensagem("gmail.pdf", dados)
        self.assertIn("Data: 28 de setembro de 2026", mensagem.corpo)
        self.assertIn("Quantidade de pessoas: 100", mensagem.corpo)
        self.assertNotIn("confidenciais", mensagem.corpo + mensagem.assinatura)
        self.assertEqual(mensagem.assinatura.split("\n")[0], "ADRIANA EXEMPLO")

    def test_obrigado_pela_atencao_nao_vira_assinatura(self):
        corpo, assinatura = separar_assinatura(
            "Segue o pedido.\nObrigado pela sua atenção\nMarcos Exemplo\nCoordenador\n041 999999999"
        )
        self.assertEqual(corpo, "Segue o pedido.")
        self.assertEqual(assinatura, "Marcos Exemplo\nCoordenador\n041 999999999")

    def test_despacho_do_eprotocolo_nao_e_whatsapp(self):
        texto = (
            "DEPARTAMENTO DE POLICIA CIVIL\nProtocolo: 26.635.814-8\nAssunto: Solicitação de coffee break\n"
            "SÉTIMA SUBDIVISÃOInteressado:\n24/09/2026 10:25Data:\nSolicito coffee break para 60 policiais.\n"
            "24/09/2026 15:29Data:\nEncaminhe-se à ASCOM."
        )
        mensagem = ler_texto_colado(texto)
        self.assertNotEqual(mensagem.origem, "whatsapp")
        self.assertNotEqual(mensagem.remetente_nome, "Data")

    def test_pdf_com_uma_palavra_por_linha_reflui(self):
        palavras = ("Ofício n.º 450/2026 Curitiba, 17 de setembro de 2026. Assunto: Solicitação de unidade móvel. "
                    "Senhor Delegado, solicito a unidade móvel para a operação que será deflagrada no dia "
                    "06/10/2026, às 06h00min, no município de Rio Branco do Ivaí. Atenciosamente, Taís Exemplo "
                    "Delegada de Polícia").split()
        linhas = []
        for palavra in palavras:
            linhas.extend([palavra, " "])
        mensagem = ler_mensagem("oficio.pdf", pdf_de_linhas(linhas[:60], linhas[60:]))
        self.assertIn("deflagrada no dia 06/10/2026, às 06h00min", mensagem.corpo)


class ProcessoEprotocoloTests(SimpleTestCase):
    """O PDF do processo do eProtocolo lido como pedido (ofício ou despacho que veio pelo protocolo)."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        from core.leitura.tests import fabrica as f

        oficio = f.pagina([
            "SECRETARIA DE ESTADO DA SEGURANÇA PÚBLICA",
            "POLÍCIA CIVIL DO PARANÁ",
            "3.ª DELEGACIA REGIONAL DE POLÍCIA DE CIDADE EXEMPLO",
            "OFÍCIO 1532/2026",
            "Cidade Exemplo, 16 de Setembro de 2026",
            "Assunto: Solicitação de Coffee Break",
            "Senhor(a) Delegado(a),",
            "Cumprimentando-o cordialmente, venho solicitar a disponibilização de coffee break",
            "destinado a aproximadamente 40 pessoas, a ser servido durante reunião agendada",
            "para o dia 01 de outubro de 2026, as 10:00, nas dependências desta Unidade Policial.",
            "Atenciosamente,",
            "Gessica Exemplo",
            "Delegada de Polícia",
        ])
        cls.pdf = f.processo_eprotocolo(
            [f.Doc(pdf=oficio, arquivo="Protocolo_2026_049934_000.pdf", assinantes=[("Gessica Exemplo", "52998224725")])],
            protocolo="26.591.587-6", numero_ano="1532/2026", assunto="ALIMENTACAO", cidade="CIDADE EXEMPLO / PR",
            palavras_chave="PEDIDO DE AUXILIO E/OU RECURSOS", detalhamento="SOLICITAÇÃO DE COFFEE BREAK",
            interessados=("DELEGACIA DE CIDADE EXEMPLO",), inserido_em="16/09/2026 10:23",
        )

    def test_capa_da_assunto_interessado_data_e_extras(self):
        mensagem = ler_mensagem("Processo_26.591.587-6_1.pdf", self.pdf)
        self.assertEqual(mensagem.origem, "eprotocolo")
        self.assertEqual(mensagem.assunto, "SOLICITAÇÃO DE COFFEE BREAK")
        self.assertEqual(mensagem.remetente_nome, "DELEGACIA DE CIDADE EXEMPLO")
        self.assertEqual(mensagem.enviado_em.date(), date(2026, 9, 16))
        self.assertEqual(mensagem.extras["protocolo"], "265915876")
        self.assertEqual(mensagem.extras["cidade"], "CIDADE EXEMPLO / PR")
        self.assertEqual(mensagem.extras["numero_ano"], "1532/2026")
        self.assertTrue(any("eProtocolo" in aviso for aviso in mensagem.avisos))

    def test_corpo_e_o_oficio_sem_a_moldura(self):
        mensagem = ler_mensagem("Processo_26.591.587-6_1.pdf", self.pdf)
        self.assertIn("reunião agendada", mensagem.corpo)
        self.assertIn("01 de outubro de 2026", mensagem.corpo)
        for ruido in ("Assinatura Avançada", "Inserido ao protocolo", "validarDocumento", "Órgão Cadastro"):
            self.assertNotIn(ruido, mensagem.corpo + mensagem.assinatura, ruido)
