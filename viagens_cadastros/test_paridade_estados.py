from django.contrib.auth.models import Permission
from django.urls import reverse

from auditoria.models import LogAuditoria
from cadastros.models import Estado, Municipio, Regiao
from .estados import EstadoForm
from .tests import BaseViagensTestCase


class ParidadeEstadosTests(BaseViagensTestCase):
    def setUp(self):
        self.usuario = self.criar_usuario("estados_admin")
        self.usuario.is_staff = self.usuario.is_superuser = True
        self.usuario.save()
        self.client.force_login(self.usuario)
        self.url = reverse("viagens_cadastros:estados")
        self.estado = Estado.objects.create(nome="ESTADO DE ENSAIO", sigla="ZT", codigo_ibge=999, ativo=False)

    def test_lista_busca_nome_sigla_sem_acentos_e_pagina_15(self):
        self.estado.nome = "ESTADO ÁGUA"
        self.estado.save()
        for termo in ["agua", "zt"]:
            response = self.client.get(self.url, {"q": termo})
            self.assertEqual(list(response.context["pagina"]), [self.estado])
            self.assertEqual(response.context["pagina"].paginator.per_page, 15)
            self.assertContains(response, "ZT · 999")
        self.assertNotContains(self.client.get(self.url, {"q": "999"}), "ESTADO ÁGUA")

    def test_inclusao_edicao_preservam_campos_compartilhados(self):
        response = self.client.post(self.url, {"nome": "NOVO ENSAIO", "sigla": "ZX", "codigo_ibge": 998, "ativo": "false"}, follow=True)
        self.assertContains(response, "Estado criado com sucesso.")
        self.assertTrue(Estado.objects.get(sigla="ZX").ativo)
        response = self.client.post(reverse("viagens_cadastros:estado_editar", args=[self.estado.pk]), {
            "nome": "ESTADO RENOMEADO", "sigla": "ZT", "codigo_ibge": 999, "ativo": "true",
        }, follow=True)
        self.assertContains(response, "Estado atualizado com sucesso.")
        self.estado.refresh_from_db()
        self.assertFalse(self.estado.ativo)

    def test_regras_existentes_preservadas_e_erro_nao_grava(self):
        self.assertEqual(EstadoForm().fields["nome"].max_length, 150)
        response = self.client.post(self.url, {"nome": "NÃO GRAVAR", "sigla": "ZX"})
        self.assertTrue(response.context["form"].has_error("codigo_ibge"))
        self.assertFalse(Estado.objects.filter(sigla="ZX").exists())
        response = self.client.post(reverse("viagens_cadastros:estado_editar", args=[self.estado.pk]), {
            "nome": "NÃO GRAVAR", "sigla": "ZT", "codigo_ibge": "",
        }, follow=True)
        self.assertContains(response, "Não foi possível salvar o estado. Verifique os dados informados.")
        self.estado.refresh_from_db()
        self.assertEqual(self.estado.nome, "ESTADO DE ENSAIO")

    def test_get_edicao_e_confirmacao_nao_gravam(self):
        self.assertRedirects(self.client.get(reverse("viagens_cadastros:estado_editar", args=[self.estado.pk])), self.url)
        response = self.client.get(reverse("viagens_cadastros:estado_excluir", args=[self.estado.pk]))
        self.assertContains(response, "Não é possível excluir se existirem cidades vinculadas.")
        self.assertTrue(Estado.objects.filter(pk=self.estado.pk).exists())
        self.assertFalse(LogAuditoria.objects.filter(usuario=self.usuario).exists())

    def test_exclusao_protege_municipio_e_audita_somente_sucesso(self):
        regiao, _ = Regiao.objects.get_or_create(nome="REGIÃO ENSAIO")
        municipio = Municipio.objects.create(nome="MUNICÍPIO ENSAIO", estado=self.estado, regiao=regiao)
        url = reverse("viagens_cadastros:estado_excluir", args=[self.estado.pk])
        response = self.client.post(url, follow=True)
        self.assertContains(response, "Não foi possível excluir este cadastro porque ele está vinculado a outros registros.")
        self.assertTrue(Estado.objects.filter(pk=self.estado.pk).exists())
        self.assertFalse(LogAuditoria.objects.filter(usuario=self.usuario).exists())
        municipio.delete()
        response = self.client.post(url, follow=True)
        self.assertContains(response, "Estado excluído com sucesso.")
        log = LogAuditoria.objects.get(usuario=self.usuario, acao="VIAGENS_CADASTRO_EXCLUIDO")
        self.assertIn(f"id {self.estado.pk}", log.descricao)

    def test_escrita_exige_permissoes_administrativas_do_modelo(self):
        usuario = self.criar_usuario("estados_leitor")
        self.client.force_login(usuario)
        self.assertNotContains(self.client.get(self.url), "Cadastrar estado")
        self.assertEqual(self.client.post(self.url, {}).status_code, 403)
        usuario.is_staff = True
        usuario.save()
        usuario.user_permissions.add(Permission.objects.get(content_type__app_label="cadastros", codename="add_estado"))
        self.assertContains(self.client.get(self.url), "Cadastrar estado")
        self.assertEqual(self.client.post(reverse("viagens_cadastros:estado_editar", args=[self.estado.pk]), {}).status_code, 403)
        self.assertEqual(self.client.post(reverse("viagens_cadastros:estado_excluir", args=[self.estado.pk]), {}).status_code, 403)
