import io
import json
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from auditoria.models import LogAuditoria
from solicitacoes.permissions import GRUPO_ADMINISTRADOR

from .models import Estado, Municipio, OrgaoResponsavel, Regiao, Servico, TipoEvento

User = get_user_model()


class SeedTests(TestCase):
    def test_seed_e_idempotente(self):
        call_command("seed_initial_data")
        totais = (
            Group.objects.count(),
            TipoEvento.objects.count(),
            Estado.objects.count(),
            Municipio.objects.count(),
            Regiao.objects.count(),
        )
        call_command("seed_initial_data")
        self.assertEqual(
            totais,
            (
                Group.objects.count(),
                TipoEvento.objects.count(),
                Estado.objects.count(),
                Municipio.objects.count(),
                Regiao.objects.count(),
            ),
        )
        self.assertTrue(Group.objects.filter(name=GRUPO_ADMINISTRADOR).exists())

    @patch("cadastros.management.commands.importar_localidades_ibge.urlopen")
    def test_importacao_oficial_do_ibge(self, urlopen_mock):
        estados = [
            {"id": 41, "nome": "Paraná", "sigla": "PR", "regiao": {"nome": "Sul"}}
        ]
        municipios = [
            {
                "id": 4106902,
                "nome": "Curitiba",
                "microrregiao": {
                    "mesorregiao": {"UF": estados[0]}
                },
                "regiao-imediata": {},
            }
        ]
        urlopen_mock.side_effect = [
            io.BytesIO(json.dumps(estados).encode()),
            io.BytesIO(json.dumps(municipios).encode()),
        ]

        call_command("importar_localidades_ibge")

        municipio = Municipio.objects.get(codigo_ibge=4106902)
        self.assertEqual(municipio.nome, "Curitiba")
        self.assertEqual(municipio.estado.sigla, "PR")
        # Região operacional da PCPR, não a macrorregião do IBGE.
        self.assertEqual(municipio.regiao.nome, "Capital")


class CrudCadastrosTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.comum = User.objects.create_user("comum", password="x")
        cls.admin = User.objects.create_user("admin", password="x")
        cls.admin.groups.add(Group.objects.create(name=GRUPO_ADMINISTRADOR))

    def test_usuario_comum_nao_acessa(self):
        self.client.force_login(self.comum)
        resposta = self.client.get(reverse("cadastros:index"))
        self.assertEqual(resposta.status_code, 403)

    def test_administrador_cria_edita_e_inativa(self):
        self.client.force_login(self.admin)
        resposta = self.client.get(reverse("cadastros:index"))
        self.assertEqual(resposta.status_code, 200)

        resposta = self.client.post(
            reverse("cadastros:novo", args=["tipos-evento"]), {"nome": "Novo tipo"}
        )
        self.assertEqual(resposta.status_code, 302)
        tipo = TipoEvento.objects.get(nome="Novo tipo")

        resposta = self.client.post(
            reverse("cadastros:editar", args=["tipos-evento", tipo.pk]),
            {"nome": "Tipo renomeado"},
        )
        self.assertEqual(resposta.status_code, 302)
        tipo.refresh_from_db()
        self.assertEqual(tipo.nome, "Tipo renomeado")

        resposta = self.client.post(
            reverse("cadastros:alternar_ativo", args=["tipos-evento", tipo.pk])
        )
        tipo.refresh_from_db()
        self.assertFalse(tipo.ativo)

        # Cada ação administrativa gera auditoria.
        self.assertEqual(LogAuditoria.objects.count(), 3)

    def test_cadastro_de_regioes_nao_existe_na_interface(self):
        self.client.force_login(self.admin)

        resposta = self.client.get(reverse("cadastros:index"))
        self.assertNotContains(resposta, "Regiões")

        resposta = self.client.get(
            reverse("cadastros:lista", args=["regioes"])
        )
        self.assertEqual(resposta.status_code, 404)

        resposta = self.client.get(
            reverse("cadastros:novo", args=["regioes"])
        )
        self.assertEqual(resposta.status_code, 404)

    def test_validacao_no_form(self):
        self.client.force_login(self.admin)
        TipoEvento.objects.create(nome="Duplicado")
        resposta = self.client.post(
            reverse("cadastros:novo", args=["tipos-evento"]), {"nome": "Duplicado"}
        )
        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, "form-erro")

    def test_orgao_responsavel_possui_apenas_campo_nome(self):
        self.client.force_login(self.admin)

        resposta = self.client.post(
            reverse("cadastros:novo", args=["orgaos"]),
            {"nome": "Secretaria de Estado da Justiça"},
        )

        self.assertEqual(resposta.status_code, 302)
        self.assertTrue(
            OrgaoResponsavel.objects.filter(nome="Secretaria de Estado da Justiça").exists()
        )
        edicao = self.client.get(reverse("cadastros:novo", args=["orgaos"]))
        self.assertNotContains(edicao, 'name="sigla"')

    def test_excluir_registro_livre(self):
        self.client.force_login(self.admin)
        tipo = TipoEvento.objects.create(nome="Descartável")
        resposta = self.client.post(
            reverse("cadastros:excluir", args=["tipos-evento", tipo.pk])
        )
        self.assertEqual(resposta.status_code, 302)
        self.assertFalse(TipoEvento.objects.filter(pk=tipo.pk).exists())
        self.assertTrue(
            LogAuditoria.objects.filter(acao="CADASTRO_EXCLUIDO").exists()
        )

    def test_excluir_registro_vinculado_e_bloqueado(self):
        from solicitacoes.models import SolicitacaoEvento

        tipo = TipoEvento.objects.create(nome="Em uso")
        SolicitacaoEvento.objects.create(tipo_evento=tipo, criado_por=self.admin)
        self.client.force_login(self.admin)
        resposta = self.client.post(
            reverse("cadastros:excluir", args=["tipos-evento", tipo.pk]), follow=True
        )
        self.assertTrue(TipoEvento.objects.filter(pk=tipo.pk).exists())
        mensagens = [str(m) for m in resposta.context["messages"]]
        self.assertTrue(any("não pode ser excluído" in m for m in mensagens))

    def test_excluir_exige_administrador_e_post(self):
        tipo = TipoEvento.objects.create(nome="Protegido")
        self.client.force_login(self.comum)
        resposta = self.client.post(
            reverse("cadastros:excluir", args=["tipos-evento", tipo.pk])
        )
        self.assertEqual(resposta.status_code, 403)
        self.client.force_login(self.admin)
        resposta = self.client.get(
            reverse("cadastros:excluir", args=["tipos-evento", tipo.pk])
        )
        self.assertEqual(resposta.status_code, 405)
        self.assertTrue(TipoEvento.objects.filter(pk=tipo.pk).exists())

    def test_servico_possui_apenas_campo_nome(self):
        self.client.force_login(self.admin)

        resposta = self.client.post(
            reverse("cadastros:novo", args=["servicos"]),
            {"nome": "Plantão de atendimento"},
        )

        self.assertEqual(resposta.status_code, 302)
        self.assertTrue(Servico.objects.filter(nome="Plantão de atendimento").exists())
        edicao = self.client.get(reverse("cadastros:novo", args=["servicos"]))
        self.assertNotContains(edicao, 'name="descricao"')
