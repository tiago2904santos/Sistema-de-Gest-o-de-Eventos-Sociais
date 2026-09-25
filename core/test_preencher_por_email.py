"""Parte comum do "Preencher com um e-mail" (core/preencher_por_email.py)."""

import os
import shutil
import tempfile
import time
from datetime import date, datetime, time as hora, timezone as fuso
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
