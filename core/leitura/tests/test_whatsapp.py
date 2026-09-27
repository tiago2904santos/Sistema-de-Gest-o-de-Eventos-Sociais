"""Conversa do WhatsApp: formatos da exportação em texto, o .zip exportado e o print lido por OCR."""

import shutil
from datetime import date, datetime
from unittest import skipUnless

from django.test import SimpleTestCase, override_settings

from core.leitura.mensagem import MensagemIlegivel, conversa_do_print, ler_mensagem, ler_texto_colado
from core.leitura.tests import fabrica_whatsapp as w

TEM_TESSERACT = bool(shutil.which("tesseract"))


def _sem_fuso(valor):
    return valor.replace(tzinfo=None) if valor else valor


class FormatosDaExportacaoTests(SimpleTestCase):
    """Cada celular (e cada idioma do celular) exporta a linha de um jeito."""

    def conferir(self, texto, hora=datetime(2026, 9, 24, 14, 32)):
        mensagem = ler_texto_colado(texto)
        self.assertEqual(mensagem.origem, "whatsapp")
        self.assertEqual(mensagem.remetente_nome, "Ana Exemplo")
        self.assertEqual(_sem_fuso(mensagem.enviado_em), hora)
        self.assertEqual(mensagem.corpo, "Pauta amanhã no Colégio Exemplo.\n\nÀs 10h.")
        return mensagem

    def test_android_24h(self):
        self.conferir("24/09/2026 14:32 - Ana Exemplo: Pauta amanhã no Colégio Exemplo.\n24/09/2026 14:33 - Ana Exemplo: Às 10h.")

    def test_android_ano_com_dois_digitos(self):
        self.conferir("24/09/26 14:32 - Ana Exemplo: Pauta amanhã no Colégio Exemplo.\n24/09/26 14:33 - Ana Exemplo: Às 10h.")

    def test_iphone_com_segundos(self):
        self.conferir(
            "[24/09/2026, 14:32:10] Ana Exemplo: Pauta amanhã no Colégio Exemplo.\n"
            "[24/09/2026, 14:33:10] Ana Exemplo: Às 10h."
        )

    def test_iphone_ano_com_dois_digitos_sem_virgula(self):
        self.conferir(
            "[24/09/26 14:32:10] Ana Exemplo: Pauta amanhã no Colégio Exemplo.\n[24/09/26 14:33:10] Ana Exemplo: Às 10h."
        )

    def test_whatsapp_web_hora_antes_da_data(self):
        self.conferir("[14:32, 24/09/2026] Ana Exemplo: Pauta amanhã no Colégio Exemplo.\n[14:33, 24/09/2026] Ana Exemplo: Às 10h.")

    def test_doze_horas_com_am_pm(self):
        mensagem = self.conferir(
            "24/09/2026 2:32 PM - Ana Exemplo: Pauta amanhã no Colégio Exemplo.\n24/09/2026 2:33 PM - Ana Exemplo: Às 10h."
        )
        self.assertEqual(_sem_fuso(mensagem.extras["falas"][1]["enviado_em"]), datetime(2026, 9, 24, 14, 33))
        manha = ler_texto_colado("24/09/2026 12:05 AM - Ana Exemplo: Pauta.\n24/09/2026 9:10 am - Ana Exemplo: Ok.")
        self.assertEqual(_sem_fuso(manha.enviado_em), datetime(2026, 9, 24, 0, 5))

    def test_iphone_com_marcas_invisiveis_e_espaco_fino_antes_do_pm(self):
        self.conferir(
            "\u200e[24/09/2026, 2:32:10\u202fPM] Ana Exemplo: Pauta amanhã no Colégio Exemplo.\n"
            "\u200e[24/09/2026, 2:33:10\u202fPM] Ana Exemplo: Às 10h."
        )

    def test_linhas_de_sistema_do_iphone_nao_entram(self):
        mensagem = ler_texto_colado(
            "\u200e[24/09/2026, 14:30:00] Grupo Imprensa: \u200eAs mensagens e as ligações são protegidas com a "
            "criptografia de ponta a ponta.\n"
            "\u200e[24/09/2026, 14:31:00] Grupo Imprensa: \u200eBeto Exemplo adicionou você\n"
            "[24/09/2026, 14:32:00] Ana Exemplo: Pauta amanhã no Colégio Exemplo.\n"
            "\u200e[24/09/2026, 14:32:30] Ana Exemplo: \u200e<anexado: 00000012-PHOTO-2026-09-24.jpg>\n"
            "\u200e[24/09/2026, 14:32:40] Ana Exemplo: \u200eimagem ocultada\n"
            "\u200e[24/09/2026, 14:32:50] Ana Exemplo: \u200eáudio omitido\n"
            "\u200e[24/09/2026, 14:32:55] Grupo Imprensa: \u200eBeto Exemplo saiu\n"
            "[24/09/2026, 14:33:00] Ana Exemplo: Às 10h.\n"
        )
        self.assertEqual(mensagem.remetente_nome, "Ana Exemplo")  # o aviso da criptografia não conta
        self.assertEqual(_sem_fuso(mensagem.enviado_em), datetime(2026, 9, 24, 14, 32))
        self.assertEqual(mensagem.corpo, "Pauta amanhã no Colégio Exemplo.\n\nÀs 10h.")

    def test_linhas_de_sistema_do_android_nao_entram(self):
        mensagem = ler_texto_colado(
            "24/09/2026 14:30 - As mensagens e ligações são protegidas com a criptografia de ponta a ponta.\n"
            "24/09/2026 14:31 - Beto Exemplo adicionou você\n"
            "24/09/2026 14:32 - Ana Exemplo: Pauta amanhã no Colégio Exemplo.\n"
            "24/09/2026 14:32 - Ana Exemplo: <Mídia oculta>\n"
            "24/09/2026 14:32 - Beto Exemplo saiu\n"
            "24/09/2026 14:32 - Ana Exemplo: Esta mensagem foi apagada\n"
            "24/09/2026 14:32 - Ana Exemplo: IMG-20260924-WA0001.jpg (arquivo anexado)\n"
            "24/09/2026 14:33 - Ana Exemplo: Às 10h. <Mensagem editada>\n"
        )
        self.assertEqual(mensagem.corpo, "Pauta amanhã no Colégio Exemplo.\n\nÀs 10h.")
        self.assertNotIn("saiu", mensagem.corpo)

    def test_legenda_da_foto_fica(self):
        mensagem = ler_texto_colado(
            "24/09/2026 14:32 - Ana Exemplo: IMG-20260924-WA0001.jpg (arquivo anexado)\nConvite da formatura\n"
            "24/09/2026 14:33 - Ana Exemplo: Pode divulgar?"
        )
        self.assertEqual(mensagem.corpo, "Convite da formatura\n\nPode divulgar?")

    def test_mensagem_normal_com_saiu_continua(self):
        mensagem = ler_texto_colado(
            "24/09/2026 14:32 - Ana Exemplo: A matéria saiu ontem no jornal.\n24/09/2026 14:33 - Ana Exemplo: Podemos repercutir?"
        )
        self.assertEqual(mensagem.corpo, "A matéria saiu ontem no jornal.\n\nPodemos repercutir?")


class ZipDoWhatsappTests(SimpleTestCase):
    def test_iphone_le_a_conversa_e_anexa_as_fotos(self):
        mensagem = ler_mensagem("Conversa do WhatsApp com Maria Exemplo.zip", w.zip_whatsapp())
        self.assertEqual(mensagem.origem, "whatsapp")
        self.assertEqual(mensagem.remetente_nome, "Maria Exemplo")
        self.assertEqual(_sem_fuso(mensagem.enviado_em), datetime(2026, 9, 24, 10, 35))
        self.assertIn("entrevista com o delegado", mensagem.corpo)
        self.assertNotIn("criptografia", mensagem.corpo)
        self.assertNotIn("anexado", mensagem.corpo)
        self.assertEqual([nome for nome, _ in mensagem.anexos], ["00000012-PHOTO-2026-09-24-10-37-00.png"])
        self.assertTrue(mensagem.anexos[0][1].startswith(b"\x89PNG"))

    def test_android_com_o_nome_da_conversa(self):
        dados = w.zip_whatsapp(
            {"DOC-20260924-WA0002.pdf": b"%PDF-1.4\n%fim\n"},
            conversa=w.conversa_android(),
            nome_conversa="Conversa do WhatsApp com Maria Exemplo.txt",
        )
        mensagem = ler_mensagem("Conversa do WhatsApp com Maria Exemplo.zip", dados)
        self.assertEqual(mensagem.remetente_nome, "Maria Exemplo")
        self.assertIn("amanhã às 14h", mensagem.corpo)
        self.assertNotIn("saiu", mensagem.corpo)
        self.assertEqual(len(mensagem.anexos), 2)
        self.assertIn("DOC-20260924-WA0002.pdf", [nome for nome, _ in mensagem.anexos])

    def test_audio_video_e_falsa_foto_ficam_de_fora(self):
        dados = w.zip_whatsapp({
            "00000014-AUDIO-2026-09-24.opus": b"OggS" + b"\x00" * 20,
            "00000015-VIDEO-2026-09-24.mp4": b"\x00\x00\x00\x18ftypmp42",
            "00000016-PHOTO-2026-09-24.jpg": b"MZ\x90\x00 executavel renomeado",
        })
        mensagem = ler_mensagem("conversa.zip", dados)
        self.assertEqual(len(mensagem.anexos), 1)
        self.assertTrue(any("3 arquivo(s) da conversa" in aviso for aviso in mensagem.avisos))

    @override_settings(LEITURA_EMAIL_MAX_ANEXOS=2)
    def test_respeita_o_limite_de_anexos(self):
        mensagem = ler_mensagem("conversa.zip", w.zip_whatsapp(fotos=4))
        self.assertEqual(len(mensagem.anexos), 2)
        self.assertTrue(any("só os 2 primeiros" in aviso for aviso in mensagem.avisos))

    @override_settings(LEITURA_EMAIL_ANEXO_MAX_BYTES=50)
    def test_foto_grande_demais_vira_aviso(self):
        mensagem = ler_mensagem("conversa.zip", w.zip_whatsapp({"00000020-PHOTO.png": w.png_pequeno(tamanho=(300, 300))}, fotos=0))
        self.assertEqual(mensagem.anexos, [])
        self.assertTrue(any("00000020-PHOTO.png" in aviso for aviso in mensagem.avisos))

    def test_zip_sem_conversa_e_recusado(self):
        dados = w.zip_whatsapp({"leia-me.txt": "Só um arquivo de texto qualquer."}, nome_conversa="")
        with self.assertRaisesMessage(MensagemIlegivel, "não tem uma conversa exportada do WhatsApp"):
            ler_mensagem("fotos.zip", dados)

    def test_path_traversal_e_recusado(self):
        for nome in ("../../etc/cron.d/x.jpg", "/etc/passwd.txt", "C:\\Windows\\x.png", "fotos/../../x.png"):
            with self.subTest(nome=nome):
                with self.assertRaisesMessage(MensagemIlegivel, "caminhos de arquivo inválidos"):
                    ler_mensagem("conversa.zip", w.zip_whatsapp({nome: w.png_pequeno()}))

    def test_bomba_de_descompactacao_e_recusada(self):
        bomba = w.zip_bomba(megas=40)
        self.assertLess(len(bomba), 1024 * 1024)
        with self.assertRaisesMessage(MensagemIlegivel, "recusado por segurança"):
            ler_mensagem("conversa.zip", bomba)

    @override_settings(LEITURA_ZIP_MAX_DESCOMPACTADO=1024)
    def test_teto_do_descompactado(self):
        with self.assertRaisesMessage(MensagemIlegivel, "recusado por segurança"):
            ler_mensagem("conversa.zip", w.zip_whatsapp({"grande.txt": "x" * 5000}))

    @override_settings(LEITURA_ZIP_MAX_ARQUIVOS=10)
    def test_arquivos_demais(self):
        with self.assertRaisesMessage(MensagemIlegivel, "arquivos demais"):
            ler_mensagem("conversa.zip", w.zip_whatsapp(fotos=11))

    def test_zip_corrompido(self):
        with self.assertRaises(MensagemIlegivel):
            ler_mensagem("conversa.zip", w.zip_whatsapp()[:200])


class ConversaDoPrintTests(SimpleTestCase):
    """O texto do OCR de um print, montado em conversa (sem precisar do tesseract)."""

    OCR = (
        "10:52 4G 87%\n\n< Maria Exemplo\n\nonline\n\n24 DE SETEMBRO DE 2026\n\n"
        "Bom dia! Aqui é a Maria, do Jornal\n\nExemplo de Cidade Exemplo.\n10:35\n\n"
        "Gostaria de uma entrevista com o\ndelegado sobre a operação de ontem.\n\n10:36 W\n\n"
        "Bom dia, Maria! Vou verificar.\n10:40\n\n"
        "Pode ser amanhã às 14:00\nno Colégio Exemplo? 10:41\n\nMensagem\n"
    )

    def test_contato_falas_e_data(self):
        mensagem = conversa_do_print(self.OCR, hoje=date(2026, 9, 27))
        self.assertEqual(mensagem.origem, "print")
        self.assertEqual(mensagem.remetente_nome, "Maria Exemplo")
        self.assertEqual(_sem_fuso(mensagem.enviado_em), datetime(2026, 9, 24, 10, 35))
        self.assertEqual(
            mensagem.corpo,
            "Bom dia! Aqui é a Maria, do Jornal\nExemplo de Cidade Exemplo.\n\n"
            "Gostaria de uma entrevista com o\ndelegado sobre a operação de ontem.\n\n"
            "Bom dia, Maria! Vou verificar.\n\n"
            "Pode ser amanhã às 14:00\nno Colégio Exemplo?",
        )
        for ruido in ("87%", "online", "Mensagem", "10:52"):
            self.assertNotIn(ruido, mensagem.corpo)

    def test_hora_no_fim_da_frase_e_conteudo(self):
        mensagem = conversa_do_print("Maria Exemplo\nonline\nHOJE\nPode ser às 14:00\n10:41\n", hoje=date(2026, 9, 27))
        self.assertEqual(mensagem.corpo, "Pode ser às 14:00")
        self.assertEqual(mensagem.remetente_nome, "Maria Exemplo")
        self.assertEqual(_sem_fuso(mensagem.enviado_em), datetime(2026, 9, 27, 10, 41))
        self.assertTrue(any("HOJE" in aviso for aviso in mensagem.avisos))

    def test_ontem_e_data_sem_ano(self):
        ontem = conversa_do_print("< Maria Exemplo\nONTEM\nPauta\n09:15\n", hoje=date(2026, 9, 27))
        self.assertEqual(_sem_fuso(ontem.enviado_em), datetime(2026, 9, 26, 9, 15))
        sem_ano = conversa_do_print("< Maria Exemplo\nQui., 24 de set.\nPauta\n09:15\n", hoje=date(2026, 9, 27))
        self.assertEqual(_sem_fuso(sem_ano.enviado_em), datetime(2026, 9, 24, 9, 15))

    def test_sem_separador_a_data_fica_vazia(self):
        mensagem = conversa_do_print("< Maria Exemplo\ndigitando...\nPauta amanhã\n10:35\n", hoje=date(2026, 9, 27))
        self.assertIsNone(mensagem.enviado_em)
        self.assertTrue(any("não mostra a data" in aviso for aviso in mensagem.avisos))
        self.assertEqual(mensagem.corpo, "Pauta amanhã")

    def test_so_o_dia_da_semana_nao_inventa_a_data(self):
        mensagem = conversa_do_print("< Maria Exemplo\nQUINTA-FEIRA\nPauta amanhã\n10:35\n", hoje=date(2026, 9, 27))
        self.assertIsNone(mensagem.enviado_em)

    def test_sem_contato_reconhecivel(self):
        mensagem = conversa_do_print("Pauta amanhã no colégio\n10:35\nConfirmado\n10:36\n", hoje=date(2026, 9, 27))
        self.assertEqual(mensagem.remetente_nome, "")
        self.assertEqual(mensagem.corpo, "Pauta amanhã no colégio\n\nConfirmado")

    def test_texto_sem_bolha_com_hora_nao_e_conversa(self):
        self.assertIsNone(conversa_do_print("FORMATURA 2026\nColégio Exemplo\n", hoje=date(2026, 9, 27)))


class PrintPorOcrTests(SimpleTestCase):
    @override_settings(OCR_ATIVO=False)
    def test_sem_ocr_recusa_com_educacao(self):
        with self.assertRaisesMessage(MensagemIlegivel, "Colar o texto"):
            ler_mensagem("print.png", w.print_whatsapp())

    @override_settings(OCR_ATIVO=True)
    def test_imagem_corrompida(self):
        if not TEM_TESSERACT:
            self.skipTest("tesseract não instalado")
        with self.assertRaises(MensagemIlegivel):
            ler_mensagem("print.png", b"\x89PNG\r\n\x1a\n" + b"\x00" * 40)

    @skipUnless(TEM_TESSERACT, "tesseract não instalado")
    @override_settings(OCR_ATIVO=True)
    def test_print_de_verdade_tema_claro_e_escuro(self):
        for escuro, formato in ((False, "PNG"), (True, "JPEG")):
            with self.subTest(escuro=escuro):
                mensagem = ler_mensagem("Screenshot.png", w.print_whatsapp(escuro=escuro, formato=formato))
                self.assertEqual(mensagem.origem, "print")
                self.assertEqual(mensagem.remetente_nome, "Maria Exemplo")
                self.assertEqual(_sem_fuso(mensagem.enviado_em), datetime(2026, 9, 24, 10, 35))
                self.assertIn("entrevista com o", mensagem.corpo)
                self.assertIn("Pode ser amanhã", mensagem.corpo)
                for ruido in ("87%", "online", "10:35", "10:41", "Mensagem"):
                    self.assertNotIn(ruido, mensagem.corpo)
                self.assertTrue(any("OCR" in aviso for aviso in mensagem.avisos))
