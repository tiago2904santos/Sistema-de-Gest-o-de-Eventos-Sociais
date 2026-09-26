"""m021: formulário público de pedido de palestra/evento (sem login)."""

import io
import shutil
import tempfile
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from accounts.models import Setor
from cadastros.models import Estado, Municipio, Regiao
from core.models import Notificacao

from . import pedido_publico
from .models import CanalSolicitacao, DemandaEvento, HistoricoDemanda, StatusDemanda

User = get_user_model()
MEDIA = tempfile.mkdtemp(prefix="pedido-publico-")


def _pdf():
    from pypdf import PdfWriter

    escritor = PdfWriter()
    escritor.add_blank_page(width=200, height=200)
    saida = io.BytesIO()
    escritor.write(saida)
    return saida.getvalue()


@override_settings(MEDIA_ROOT=MEDIA, PEDIDO_PUBLICO_TEMPO_MINIMO=0)
class PedidoPublicoTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.ascom = Setor.objects.get(sigla="ASCOM")
        cls.equipe = User.objects.create_user("ascom_triagem", password="x")
        cls.equipe.setores.add(cls.ascom)
        cls.fora = User.objects.create_user("fora_ascom", password="x")
        cls.fora.setores.add(Setor.objects.create(sigla="IIPR-P", nome="Outro setor"))
        estado = Estado.objects.filter(sigla="PR").first() or Estado.objects.create(
            nome="Paraná", sigla="PR", codigo_ibge=41
        )
        cls.municipio = Municipio.objects.create(
            nome="Cidade Sintética", estado=estado, regiao=Regiao.objects.get_or_create(nome="Interior")[0]
        )

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(MEDIA, ignore_errors=True)

    def setUp(self):
        cache.clear()
        self.url = reverse("pedido_publico:pedido")

    def dados(self, **extra):
        dados = {
            "evento": "PALESTRA",
            "instituicao": "Escola Estadual Exemplo",
            "nome_contato": "Pessoa Teste",
            "telefone": "(41) 99999-0000",
            "email": "contato@exemplo.test",
            "municipio": str(self.municipio.pk),
            "data_desejada": (timezone.localdate() + timedelta(days=20)).isoformat(),
            "horario": "09:30",
            "local": "Rua Fictícia, 100",
            "publico_estimado": "80",
            "tema": "Crimes virtuais",
            "descricao": "Turmas do ensino médio.",
            "aceite_lgpd": "on",
            "site": "",
            "carimbo": pedido_publico.novo_carimbo(),
        }
        dados.update(extra)
        return dados

    def test_pagina_abre_sem_login_e_nao_expoe_dados(self):
        existente = DemandaEvento.objects.create(
            solicitante="Instituição Secreta Anterior", data_solicitacao=timezone.localdate()
        )
        resposta = self.client.get(self.url)
        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, "csrfmiddlewaretoken")
        self.assertContains(resposta, 'name="site"')
        self.assertContains(resposta, "Lei Geral de Proteção de Dados")
        self.assertNotContains(resposta, existente.solicitante)

    def test_csrf_ativo(self):
        cliente = Client(enforce_csrf_checks=True)
        resposta = cliente.post(self.url, self.dados())
        self.assertEqual(resposta.status_code, 403)
        self.assertFalse(DemandaEvento.objects.exists())

    def test_pedido_entra_pendente_notifica_e_mostra_so_o_numero(self):
        resposta = self.client.post(self.url, self.dados())
        self.assertRedirects(resposta, reverse("pedido_publico:recebido"), fetch_redirect_response=False)
        demanda = DemandaEvento.objects.get()
        self.assertEqual(demanda.status, StatusDemanda.PENDENTE)
        self.assertEqual(demanda.canal_solicitacao, CanalSolicitacao.PORTAL)
        self.assertIsNone(demanda.criado_por)
        self.assertEqual(list(demanda.setores.all()), [self.ascom])
        self.assertIn("Rua Fictícia", demanda.descricao)
        self.assertTrue(HistoricoDemanda.objects.filter(demanda=demanda, descricao__icontains="triagem").exists())
        self.assertTrue(Notificacao.objects.filter(usuario=self.equipe).exists())
        self.assertFalse(Notificacao.objects.filter(usuario=self.fora).exists())
        # O token não fica em claro no banco.
        self.assertEqual(len(demanda.token_acompanhamento), 64)

        confirmacao = self.client.get(reverse("pedido_publico:recebido"))
        self.assertContains(confirmacao, str(demanda.pk))
        self.assertNotContains(confirmacao, "contato@exemplo.test")
        # A confirmação só aparece uma vez.
        self.assertRedirects(self.client.get(reverse("pedido_publico:recebido")), self.url)

    def test_acompanhamento_pelo_token(self):
        self.client.post(self.url, self.dados())
        link = self.client.get(reverse("pedido_publico:recebido")).context["recebido"]["link"]
        caminho = link.split("testserver", 1)[1]
        resposta = self.client.get(caminho)
        self.assertContains(resposta, "Recebido, aguardando análise")
        self.assertEqual(resposta["Referrer-Policy"], "no-referrer")
        self.assertNotContains(resposta, "Pessoa Teste")
        self.assertNotContains(resposta, "contato@exemplo.test")

    def test_token_invalido_da_404(self):
        self.client.post(self.url, self.dados())
        for token in ("x", "a" * 43, DemandaEvento.objects.get().token_acompanhamento):
            resposta = self.client.get(reverse("pedido_publico:acompanhar", args=[token]))
            self.assertEqual(resposta.status_code, 404)

    def test_honeypot_nao_grava(self):
        resposta = self.client.post(self.url, self.dados(site="http://spam.test"))
        self.assertRedirects(resposta, reverse("pedido_publico:recebido"))
        self.assertFalse(DemandaEvento.objects.exists())
        self.assertFalse(Notificacao.objects.exists())

    @override_settings(PEDIDO_PUBLICO_TEMPO_MINIMO=60)
    def test_envio_rapido_demais_e_recusado(self):
        resposta = self.client.post(self.url, self.dados())
        self.assertEqual(resposta.status_code, 200)
        self.assertFalse(DemandaEvento.objects.exists())

    def test_carimbo_ausente_ou_forjado_e_recusado(self):
        for carimbo in ("", "forjado:123"):
            self.client.post(self.url, self.dados(carimbo=carimbo))
        self.assertFalse(DemandaEvento.objects.exists())

    @override_settings(PEDIDO_PUBLICO_LIMITE=2)
    def test_limite_de_pedidos_por_ip(self):
        for _ in range(2):
            self.client.post(self.url, self.dados())
        resposta = self.client.post(self.url, self.dados())
        self.assertEqual(resposta.status_code, 429)
        self.assertEqual(DemandaEvento.objects.count(), 2)
        # Outro IP segue podendo pedir.
        self.client.post(self.url, self.dados(), REMOTE_ADDR="10.0.0.99")
        self.assertEqual(DemandaEvento.objects.count(), 3)

    @override_settings(PEDIDO_PUBLICO_LIMITE_TENTATIVAS=3)
    def test_limite_de_tentativas_invalidas(self):
        for _ in range(3):
            self.client.post(self.url, self.dados(email="invalido"))
        resposta = self.client.post(self.url, self.dados())
        self.assertEqual(resposta.status_code, 429)
        self.assertFalse(DemandaEvento.objects.exists())

    def test_campos_longos_data_passada_e_sem_aceite(self):
        casos = [
            {"instituicao": "x" * 201},
            {"descricao": "x" * 2001},
            {"data_desejada": (timezone.localdate() - timedelta(days=1)).isoformat()},
            {"aceite_lgpd": ""},
        ]
        for extra in casos:
            with self.subTest(extra=list(extra)):
                resposta = self.client.post(self.url, self.dados(**extra))
                self.assertEqual(resposta.status_code, 200)
        self.assertFalse(DemandaEvento.objects.exists())

    def test_anexo_passa_pela_validacao_central(self):
        falso = SimpleUploadedFile("oficio.pdf", b"nao sou pdf", content_type="application/pdf")
        resposta = self.client.post(self.url, self.dados(anexo=falso))
        self.assertEqual(resposta.status_code, 200)
        self.assertFalse(DemandaEvento.objects.exists())

        valido = SimpleUploadedFile("oficio.pdf", _pdf(), content_type="application/pdf")
        self.client.post(self.url, self.dados(anexo=valido))
        demanda = DemandaEvento.objects.get()
        self.assertTrue(demanda.anexo_pedido)
        # O anexo só sai para quem enxerga a linha.
        url_anexo = reverse("demandas_eventos:anexo_pedido", args=[demanda.pk])
        self.assertEqual(self.client.get(url_anexo).status_code, 302)
        self.client.force_login(self.fora)
        self.assertEqual(self.client.get(url_anexo).status_code, 403)
        self.client.force_login(self.equipe)
        self.assertEqual(self.client.get(url_anexo).status_code, 200)

    def test_anonimo_nao_acessa_o_modulo(self):
        self.client.post(self.url, self.dados())
        demanda = DemandaEvento.objects.get()
        for url in (
            reverse("demandas_eventos:lista"),
            reverse("demandas_eventos:editar", args=[demanda.pk]),
            reverse("demandas_eventos:solicitantes"),
        ):
            resposta = self.client.get(url)
            self.assertEqual(resposta.status_code, 302)
            self.assertIn(reverse("accounts:login"), resposta["Location"])
