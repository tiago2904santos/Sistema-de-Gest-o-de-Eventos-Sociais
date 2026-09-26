"""Parte comum do "Preencher com um e-mail" (core/preencher_por_email.py)."""

import os
import shutil
import tempfile
import time
from datetime import date, datetime, time as hora, timedelta, timezone as fuso
from pathlib import Path

from django.contrib.sessions.backends.db import SessionStore
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import RequestFactory, SimpleTestCase, TestCase, override_settings

from cadastros.models import Estado
from core import preencher_por_email as pe
from core.leitura.mensagem import Mensagem, ler_texto_colado


class SugestaoTests(TestCase):
    def test_valor_no_formato_do_campo(self):
        parana = Estado.objects.get(codigo_ibge=41)
        casos = [
            (date(2026, 10, 8), "2026-10-08"),
            (hora(9, 30), "09:30"),
            (True, "1"),
            (60, "60"),
            (parana, str(parana.pk)),
            ([parana], [str(parana.pk)]),
        ]
        for valor, esperado in casos:
            self.assertEqual(pe.Sugestao(valor, "x").como_json()["valor"], esperado)

    def test_sugestao_vazia_nao_entra(self):
        s = pe.Sugestoes()
        s.por("a", None)
        s.por("b", pe.Sugestao("", ""))
        s.por("c", pe.Sugestao([], ""))
        s.por("d", pe.Sugestao(0, "0"))
        self.assertEqual(list(s), ["d"])
        s.avisar("x")
        s.avisar("x")
        self.assertEqual(s.avisos, ["x"])


class QuemPedeTests(SimpleTestCase):
    def test_nome_cargo_unidade_e_celular_da_assinatura(self):
        mensagem = Mensagem(
            remetente_nome="Gabinete",
            assinatura="Maria Aparecida Souza\nCoordenadora de Projetos Sociais\n"
                       "Secretaria Municipal de Assistência Social - Ponta Grossa\n(42) 3220-1000 | (42) 99876-5432",
        )
        pessoa = pe.quem_pede(mensagem)
        self.assertEqual(pessoa.nome, "Maria Aparecida Souza")
        self.assertEqual(pessoa.cargo, "Coordenadora de Projetos Sociais")
        self.assertEqual(pessoa.unidade, "Secretaria Municipal de Assistência Social - Ponta Grossa")
        self.assertEqual(pessoa.telefone.valor, "(42) 99876-5432")

    def test_cargo_que_cita_o_orgao_continua_cargo(self):
        mensagem = Mensagem(assinatura="Carlos Menezes\nDelegado de Polícia\n1ª Delegacia de Polícia de Curitiba")
        pessoa = pe.quem_pede(mensagem)
        self.assertEqual(pessoa.cargo_e_unidade, "Delegado de Polícia / 1ª Delegacia de Polícia de Curitiba")

    def test_assinatura_sem_nome_usa_o_remetente(self):
        mensagem = Mensagem(remetente_nome="João Pereira", assinatura="Prefeitura de Toledo\n(45) 3055-8800")
        pessoa = pe.quem_pede(mensagem)
        self.assertEqual(pessoa.nome, "João Pereira")
        self.assertEqual(pessoa.unidade, "Prefeitura de Toledo")
        self.assertEqual(pessoa.telefone.valor, "(45) 3055-8800")

    def test_sem_nada_nao_ha_pessoa(self):
        self.assertIsNone(pe.quem_pede(Mensagem(corpo="Pedido.")))


class LocalTests(SimpleTestCase):
    def test_rotulo_vale_mais(self):
        achado = pe.local_no_texto("Evento dia 10.\nLocal: Casa da Cultura, Rua XV, 100\nAtt")
        self.assertEqual((achado.valor, achado.confianca), ("Casa da Cultura, Rua XV, 100", "A"))

    def test_lugar_com_endereco_junto(self):
        achado = pe.local_no_texto("Será realizada no Ginásio de Esportes Oscar Pereira, Rua Carlos Cavalcanti, 500. Obrigado")
        self.assertEqual(achado.valor, "Ginásio de Esportes Oscar Pereira, Rua Carlos Cavalcanti, 500")
        self.assertEqual(achado.confianca, "M")

    def test_lugar_sem_nome_nao_conta(self):
        self.assertIsNone(pe.local_no_texto("O atendimento será na escola, pela manhã."))
        self.assertIsNone(pe.local_no_texto("A Prefeitura solicita o apoio da Polícia Civil."))

    def test_endereco_solto(self):
        achado = pe.local_no_texto("Entregar os lanches na Av. Sete de Setembro, 2000 - Centro. Obrigado")
        self.assertEqual(achado.valor, "Av. Sete de Setembro, 2000 - Centro")


class TextoDeOrigemTests(SimpleTestCase):
    def test_historico(self):
        quando = datetime(2026, 9, 24, 17, 32, tzinfo=fuso.utc)
        self.assertEqual(
            pe.texto_de_origem("Pedido", "Maria", quando),
            "Criada a partir do e-mail 'Pedido' de Maria (24/09/2026 14:32)",
        )
        self.assertEqual(pe.texto_de_origem("", "", None, verbo="Criado"), "Criado a partir do e-mail")
        self.assertEqual(
            pe.texto_de_origem("", "Ana", None, origem="whatsapp"), "Criada a partir da conversa do WhatsApp de Ana"
        )


class GuardarOriginalTests(TestCase):
    def setUp(self):
        self.pasta = tempfile.mkdtemp(prefix="preencher-email-core-")
        self.addCleanup(shutil.rmtree, self.pasta, True)
        ajustes = override_settings(PREENCHER_EMAIL_PASTA=self.pasta)
        ajustes.enable()
        self.addCleanup(ajustes.disable)

    def pedido(self, **post):
        request = RequestFactory().post("/x/", post)
        request.session = SessionStore()
        return request

    def test_ler_do_pedido_texto_e_arquivo(self):
        mensagem, nome, dados = pe.ler_do_pedido(self.pedido(texto="Pedido de evento em Toledo."))
        self.assertEqual((nome, dados), ("texto-do-email.txt", "Pedido de evento em Toledo.".encode()))
        self.assertEqual(mensagem.origem, "texto")
        request = self.pedido(arquivo=SimpleUploadedFile("C:\\Users\\x\\pedido.txt", b"Pedido de evento."))
        _mensagem, nome, _dados = pe.ler_do_pedido(request)
        self.assertEqual(nome, "pedido.txt")

    def test_sessao_guarda_poucos_e_apaga_o_resto(self):
        request = self.pedido()
        mensagem = ler_texto_colado("Pedido.")
        tokens = [pe._guardar(request, "solicitacoes", "x.txt", b"x", mensagem) for _ in range(7)]
        pendentes = request.session["preencher_por_email"]
        self.assertEqual(len(pendentes), 5)
        pasta = Path(self.pasta) / "preencher-por-email"
        self.assertEqual(sorted(p.stem for p in pasta.glob("*.bin")), sorted(pendentes))
        self.assertNotIn(tokens[0], pendentes)

    def test_temporario_esquecido_some(self):
        pasta = Path(self.pasta) / "preencher-por-email"
        pasta.mkdir(parents=True)
        velho = pasta / ("c" * 32 + ".bin")
        velho.write_bytes(b"x")
        dois_dias = time.time() - 2 * 24 * 3600
        os.utime(velho, (dois_dias, dois_dias))
        pe._guardar(self.pedido(), "solicitacoes", "x.txt", b"x", ler_texto_colado("Pedido."))
        self.assertFalse(velho.exists())

    def test_origem_e_concluir(self):
        request = self.pedido()
        token = pe._guardar(request, "coffee_break", "pedido.txt", b"Pedido", ler_texto_colado("Pedido."))
        request.POST = {"email_origem": token.upper()}
        self.assertIsNone(pe.origem_do_pedido(request, "solicitacoes"))
        origem = pe.origem_do_pedido(request, "coffee_break")
        self.assertEqual((origem.nome, origem.dados), ("pedido.txt", b"Pedido"))
        pe.concluir_origem(request, origem)
        self.assertIsNone(pe.origem_do_pedido(request, "coffee_break"))
        self.assertFalse((Path(self.pasta) / "preencher-por-email" / f"{token}.bin").exists())


class QuandoDoPedidoTests(SimpleTestCase):
    def mensagem(self, corpo, citado="", enviado=datetime(2026, 9, 22, 8, 41, tzinfo=fuso.utc)):
        return Mensagem(assunto="Solicitação de palestra", corpo=corpo, citado=citado, enviado_em=enviado)

    def test_sem_data_no_corpo_procura_na_conversa_anterior_com_aviso(self):
        quando, avisos = pe.quando_do_pedido(self.mensagem(
            "Segue o ofício para confirmação da palestra.",
            citado="Gostaríamos da palestra em uma das datas: 05 de outubro ou 07 de outubro de 2026, às 14h.",
        ))
        self.assertEqual((quando.inicio, quando.confianca), (date(2026, 10, 5), "M"))
        self.assertTrue(any("mensagem anterior" in a for a in avisos), avisos)
        self.assertTrue(any("mais de uma data (05/10 ou 07/10)" in a for a in avisos), avisos)

    def test_sem_data_nenhuma_avisa_que_a_de_envio_nao_vale(self):
        quando, avisos = pe.quando_do_pedido(self.mensagem("Pedimos a emissão de identidades para 10 pacientes."))
        self.assertIsNone(quando)
        self.assertTrue(any("não é a data do evento" in a for a in avisos), avisos)

    def test_prazo_curto_e_fim_de_semana(self):
        hoje = date.today()
        dia = hoje + timedelta(days=3)
        quando, avisos = pe.quando_do_pedido(self.mensagem(
            f"A palestra será no dia {dia:%d/%m/%Y} às 9h.", enviado=datetime.combine(hoje, hora(8), tzinfo=fuso.utc)
        ))
        self.assertEqual(quando.inicio, dia)
        self.assertTrue(any("Prazo curto" in a and "3 dias" in a for a in avisos), avisos)
        if dia.weekday() >= 5:
            self.assertTrue(any("fim de semana" in a for a in avisos), avisos)


class NomeNaOrdemTests(SimpleTestCase):
    def test_sobrenome_primeiro_vira_nome_sobrenome(self):
        self.assertEqual(pe._nome_na_ordem("PAIS, Andres"), "Andres Pais")
        self.assertEqual(pe._nome_na_ordem("DA SILVA, Ana"), "Ana da Silva")
        self.assertEqual(pe._nome_na_ordem("Maria Souza"), "Maria Souza")
        self.assertEqual(pe._nome_na_ordem("Escola, a melhor, de Castro"), "Escola, a melhor, de Castro")

    def test_quem_pede_usa_o_nome_na_ordem(self):
        pessoa = pe.quem_pede(Mensagem(remetente_nome="PAIS, Andres", remetente_email="a@x.com"))
        self.assertEqual(pessoa.nome, "Andres Pais")


class TokenDaTriagemTests(GuardarOriginalTests):
    def test_ler_guardado_assume_o_token_da_triagem(self):
        request = self.pedido()
        token = pe._guardar(request, pe.MODULO_TRIAGEM, "pedido.txt", b"Pedido de palestra dia 15/10.", ler_texto_colado("Pedido."))
        self.assertIsNone(pe.ler_guardado(request, "coffee_break", "x" * 32))
        lido = pe.ler_guardado(request, "coffee_break", token)
        self.assertIsNotNone(lido)
        mensagem, nome, dados = lido
        self.assertEqual((nome, dados), ("pedido.txt", b"Pedido de palestra dia 15/10."))
        self.assertIn("palestra", mensagem.corpo)
        # O token passou a ser do módulo: o formulário salvo dele o encontra.
        request.POST = {"email_origem": token}
        self.assertIsNotNone(pe.origem_do_pedido(request, "coffee_break"))
        self.assertIsNone(pe.origem_do_pedido(request, "solicitacoes"))

    def test_origem_da_tela_por_get_e_por_post(self):
        request = self.pedido()
        token = pe._guardar(request, "solicitacoes", "pedido.txt", b"Pedido", ler_texto_colado("Pedido."))
        get = RequestFactory().get("/x/", {"email_origem": token})
        get.session = request.session
        origem = pe.origem_da_tela(get, "solicitacoes")
        self.assertEqual((origem["token"], origem["auto"]), (token, True))
        self.assertIsNone(pe.origem_da_tela(get, "coffee_break"))
        request.POST = {"email_origem": token}
        self.assertEqual(pe.origem_da_tela(request, "solicitacoes")["auto"], False)

    def test_origem_traz_o_email_do_remetente(self):
        request = self.pedido()
        mensagem = ler_texto_colado("De: Ana <ana@escola.exemplo>\nEnviado em: 24/09/2026 14:32\nAssunto: Palestra\n\nPedido.")
        token = pe._guardar(request, "solicitacoes", "pedido.txt", b"Pedido", mensagem)
        request.POST = {"email_origem": token}
        self.assertEqual(pe.origem_do_pedido(request, "solicitacoes").remetente_email, "ana@escola.exemplo")


class ArquivoDoCelularTests(GuardarOriginalTests):
    """O celular manda o arquivo sem extensão ("document"): o conteúdo decide."""

    def test_pdf_sem_extensao(self):
        from core.leitura.tests.test_mensagem import pdf_de_linhas

        pdf = pdf_de_linhas(["De: Ana <ana@escola.exemplo>", "Enviado em: 24/09/2026 14:32", "Assunto: Palestra", "", "Pedido."])
        request = self.pedido(arquivo=SimpleUploadedFile("document", pdf, content_type="application/octet-stream"))
        mensagem, nome, _dados = pe.ler_do_pedido(request)
        self.assertEqual((nome, mensagem.origem), ("document.pdf", "pdf"))

    def test_eml_sem_extensao_pelo_tipo(self):
        eml = b"From: Ana <ana@escola.exemplo>\r\nDate: Thu, 24 Sep 2026 14:32:00 -0300\r\nSubject: Palestra\r\nMIME-Version: 1.0\r\nContent-Type: text/plain\r\n\r\nPedido.\r\n"
        request = self.pedido(arquivo=SimpleUploadedFile("mensagem", eml, content_type="message/rfc822"))
        mensagem, nome, _dados = pe.ler_do_pedido(request)
        self.assertEqual((nome, mensagem.remetente_email), ("mensagem.eml", "ana@escola.exemplo"))

    def test_arquivo_desconhecido_continua_recusado(self):
        request = self.pedido(arquivo=SimpleUploadedFile("foto", b"\x89PNG\r\n\x1a\n" + b"\x00" * 40, content_type="image/png"))
        with self.assertRaises(pe.EmailRecusado):
            pe.ler_do_pedido(request)
