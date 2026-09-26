"""A memória de leitura (core/aprendizado.py): aprender ao salvar, sugerir e triar melhor depois."""

import shutil
import tempfile
from email.message import EmailMessage

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse

from accounts.models import Modulo, Setor
from cadastros.models import Estado, Municipio, Regiao
from core import aprendizado
from core.leitura.mensagem import Mensagem
from core.models import MemoriaLeitura, Notificacao
from demandas_eventos.models import CanalSolicitacao, DemandaEvento, Tema, TipoEventoPalestra
from demandas_eventos.permissions import CODIGO_MODULO

User = get_user_model()


def email(assunto, corpo, de="Maria Exemplo <maria@escola.exemplo>"):
    mensagem = EmailMessage()
    mensagem["Subject"] = assunto
    mensagem["From"] = de
    mensagem["To"] = "ascom@pc.pr.gov.br"
    mensagem["Date"] = "Thu, 24 Sep 2026 14:32:00 -0300"
    mensagem.set_content(corpo)
    return mensagem.as_bytes()


class AprenderTests(TestCase):
    def test_aprende_remetente_dominio_palavras_e_campos(self):
        tocadas = aprendizado.aprender(
            "Maria@Escola.Exemplo", "Solicitação de palestra sobre golpes",
            "demandas_eventos", {"municipio": 12, "temas": [3, 5], "vazio": "", "nada": None},
        )
        self.assertGreater(tocadas, 0)
        self.assertEqual(MemoriaLeitura.objects.get(tipo="remetente", chave="maria@escola.exemplo", campo="").modulo, "demandas_eventos")
        self.assertTrue(MemoriaLeitura.objects.filter(tipo="dominio", chave="escola.exemplo", campo="").exists())
        self.assertEqual(
            set(MemoriaLeitura.objects.filter(tipo="palavra").values_list("chave", flat=True)),
            {"palestra", "golpes"},  # "solicitacao" e "sobre" são vazias
        )
        campo = MemoriaLeitura.objects.get(tipo="remetente", campo="temas")
        self.assertEqual((campo.valor, campo.vezes), ("3,5", 1))
        self.assertFalse(MemoriaLeitura.objects.filter(campo__in=["vazio", "nada"]).exists())
        # Palavra do assunto não guarda campo.
        self.assertFalse(MemoriaLeitura.objects.filter(tipo="palavra").exclude(campo="").exists())
        # Segunda vez: conta, não duplica.
        aprendizado.aprender("maria@escola.exemplo", "Palestra", "demandas_eventos", {"municipio": 12})
        self.assertEqual(MemoriaLeitura.objects.get(tipo="remetente", campo="municipio").vezes, 2)
        self.assertEqual(MemoriaLeitura.objects.get(tipo="remetente", chave="maria@escola.exemplo", campo="").vezes, 2)

    def test_dominio_generico_nao_e_guardado(self):
        aprendizado.aprender("fulano@gmail.com", "Coffee", "coffee_break", {})
        self.assertFalse(MemoriaLeitura.objects.filter(tipo="dominio").exists())
        self.assertTrue(MemoriaLeitura.objects.filter(tipo="remetente", chave="fulano@gmail.com").exists())

    def test_sem_email_nem_modulo_nao_aprende(self):
        self.assertEqual(aprendizado.aprender("", "Assunto", "coffee_break", {}), 0)
        self.assertEqual(aprendizado.aprender("a@b.c", "Assunto", "", {}), 0)
        self.assertFalse(MemoriaLeitura.objects.exists())

    def test_pesos_de_triagem(self):
        for _ in range(3):
            aprendizado.aprender("chefia@delegacia.exemplo", "Solicitação de coffee break", "coffee_break", {})
        aprendizado.aprender("outra@delegacia.exemplo", "Release operação", "publicacoes", {})
        pesos = aprendizado.pesos_de_triagem(Mensagem(remetente_email="chefia@delegacia.exemplo", assunto="RES: coffee break"))
        self.assertEqual(pesos["coffee_break"][0], (6.0, "3 pedidos anteriores deste remetente"))
        self.assertIn((4.0, "3 pedidos anteriores deste domínio"), pesos["coffee_break"])
        self.assertIn((1.5, "1 pedido anterior deste domínio"), pesos["publicacoes"])
        self.assertTrue(any("palavras do assunto" in sinal for _, sinal in pesos["coffee_break"]))
        self.assertEqual(aprendizado.pesos_de_triagem(Mensagem(remetente_email="", assunto="")), {})

    def test_sugestoes_aprendidas(self):
        aprendizado.aprender("maria@escola.exemplo", "Palestra", "demandas_eventos", {"municipio": 12, "solicitante": "Maria"})
        mensagem = Mensagem(remetente_email="maria@escola.exemplo", assunto="Palestra de novo")
        sugestoes = aprendizado.sugestoes_aprendidas(mensagem, "demandas_eventos", ja_sugeridos=["solicitante"])
        self.assertEqual(list(sugestoes), ["municipio"])
        self.assertEqual((sugestoes["municipio"]["valor"], sugestoes["municipio"]["confianca"]), ("12", "B"))
        self.assertIn("1 pedido anterior deste remetente", sugestoes["municipio"]["trecho"])
        aprendizado.aprender("maria@escola.exemplo", "Palestra", "demandas_eventos", {"municipio": 12})
        self.assertEqual(aprendizado.sugestoes_aprendidas(mensagem, "demandas_eventos")["municipio"]["confianca"], "M")
        # Outro módulo, nada; outra pessoa do mesmo domínio só com 2+ pedidos.
        self.assertEqual(aprendizado.sugestoes_aprendidas(mensagem, "coffee_break"), {})
        outra = Mensagem(remetente_email="joana@escola.exemplo", assunto="Palestra")
        self.assertEqual(aprendizado.sugestoes_aprendidas(outra, "demandas_eventos")["municipio"]["valor"], "12")


class AprenderAoSalvarTests(TestCase):
    """O ciclo inteiro numa palestra: ler o e-mail, salvar, e o próximo e-mail já vem melhor."""

    @classmethod
    def setUpTestData(cls):
        ascom = Setor.objects.get(sigla="ASCOM")
        cls.usuario = User.objects.create_user("ascom-aprende", password="x")
        cls.usuario.setores.add(ascom)
        outro_setor = Setor.objects.create(sigla="ASCOM-AP", nome="Outra equipe")
        outro_setor.modulos.add(Modulo.objects.get(codigo=CODIGO_MODULO))
        cls.colega = User.objects.create_user("colega-aprende", password="x")
        cls.colega.setores.add(outro_setor)
        cls.sem_modulo = User.objects.create_user("fora-aprende", password="x")
        parana = Estado.objects.get(codigo_ibge=41)
        regiao = Regiao.objects.get_or_create(nome="Região Teste")[0]
        cls.ponta_grossa = Municipio.objects.get_or_create(nome="Ponta Grossa", estado=parana, defaults={"regiao": regiao})[0]
        cls.tema = Tema.objects.create(nome="Crimes virtuais")

    def setUp(self):
        self.pasta = tempfile.mkdtemp(prefix="aprende-email-")
        ajustes = override_settings(PREENCHER_EMAIL_PASTA=self.pasta)
        ajustes.enable()
        self.addCleanup(ajustes.disable)
        self.addCleanup(shutil.rmtree, self.pasta, True)
        self.client.force_login(self.usuario)

    def ler(self, conteudo):
        return self.client.post(
            reverse("demandas_eventos:ler_email"), {"arquivo": SimpleUploadedFile("pedido.eml", conteudo)}
        ).json()

    def test_salvar_aprende_e_avisa_a_equipe_e_o_proximo_email_vem_melhor(self):
        primeiro = email("Solicitação de palestra", "Pedimos uma palestra sobre crimes virtuais em Ponta Grossa no dia 15/10/2026.")
        token = self.ler(primeiro)["arquivo"]["token"]
        resposta = self.client.post(reverse("demandas_eventos:nova"), {
            "evento": TipoEventoPalestra.PALESTRA,
            "solicitante": "Maria Exemplo — Colégio Estadual Exemplo",
            "data_solicitacao": "2026-09-24",
            "data_inicio_evento": "2026-10-15",
            "canal_solicitacao": CanalSolicitacao.EMAIL,
            "municipio": self.ponta_grossa.pk,
            "temas": [self.tema.pk],
            "email_origem": token,
        })
        demanda = DemandaEvento.objects.get()
        self.assertRedirects(resposta, reverse("demandas_eventos:editar", args=[demanda.pk]))

        # Aprendeu: remetente → módulo e os campos escolhidos (não a data, que muda a cada pedido).
        memoria = MemoriaLeitura.objects.filter(tipo="remetente", chave="maria@escola.exemplo", modulo="demandas_eventos")
        self.assertEqual(memoria.get(campo="").vezes, 1)
        self.assertEqual(memoria.get(campo="municipio").valor, str(self.ponta_grossa.pk))
        self.assertEqual(memoria.get(campo="temas").valor, str(self.tema.pk))
        self.assertEqual(memoria.get(campo="solicitante").valor, "Maria Exemplo — Colégio Estadual Exemplo")
        self.assertFalse(memoria.filter(campo="data_inicio_evento").exists())

        # Avisou a equipe do módulo (o colega), não o autor nem quem não tem o módulo.
        aviso = Notificacao.objects.get(usuario=self.colega)
        self.assertIn("Pedido por e-mail cadastrado", aviso.titulo)
        self.assertIn("15/10/2026", aviso.mensagem)
        self.assertEqual(aviso.link, reverse("demandas_eventos:editar", args=[demanda.pk]))
        self.assertFalse(Notificacao.objects.filter(usuario__in=[self.usuario, self.sem_modulo]).exists())

        # O próximo e-mail da mesma escola, sem dizer o município, já vem com ele sugerido.
        segundo = email("Nova conversa com os alunos", "Podem vir falar com a turma do 9º ano em novembro?")
        dados = self.ler(segundo)
        self.assertEqual(dados["campos"]["municipio"]["valor"], str(self.ponta_grossa.pk))
        self.assertEqual(dados["campos"]["municipio"]["confianca"], "B")
        self.assertIn("pedido anterior deste remetente", dados["campos"]["municipio"]["trecho"])
        self.assertEqual(dados["campos"]["temas"]["valor"], [str(self.tema.pk)])
        # Campo que o texto já preencheu não é substituído pela memória.
        self.assertEqual(dados["campos"]["solicitante"]["valor"], "Maria Exemplo")

        # E a triagem da página inicial passa a apontar Palestras mesmo sem sinal no texto.
        triagem = self.client.post(
            reverse("core:triagem_ler"), {"arquivo": SimpleUploadedFile("outro.eml", segundo)}
        ).json()
        self.assertEqual(triagem["sugerido"], "demandas_eventos")
        self.assertIn("1 pedido anterior deste remetente", triagem["candidatos"][0]["sinais"])

    def test_sem_email_de_origem_nada_e_aprendido(self):
        self.client.post(reverse("demandas_eventos:nova"), {
            "evento": TipoEventoPalestra.PALESTRA,
            "solicitante": "Fulano",
            "data_solicitacao": "2026-09-24",
            "canal_solicitacao": CanalSolicitacao.EMAIL,
        })
        self.assertTrue(DemandaEvento.objects.exists())
        self.assertFalse(MemoriaLeitura.objects.exists())
        self.assertFalse(Notificacao.objects.exists())
