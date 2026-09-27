"""Escala e "Minha agenda" (m134): quem está em cada compromisso."""

from datetime import date

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.urls import reverse

from auditoria.models import RegistroAuditoria
from solicitacoes.permissions import GRUPO_ADMINISTRADOR
from solicitacoes.tests import BaseSolicitacaoTestCase
from viagens_cadastros.models import Cargo, Servidor
from viagens_oficios.models import Oficio
from viagens_viagem.models import Viagem

from . import escala
from .tests import _eventos

User = get_user_model()


class MinhaAgendaEPessoas(BaseSolicitacaoTestCase):
    def setUp(self):
        super().setUp()
        self.root = User.objects.create_superuser("escala_root", "escala_root@example.com", None)
        cargo = Cargo.objects.create(nome="AGENTE")
        self.ana = Servidor.objects.create(nome="ANA TESTE", cargo=cargo)
        self.bia = Servidor.objects.create(nome="BIA TESTE", cargo=cargo)
        self.viagem = Viagem.objects.create(
            titulo="Operação", destino_municipio=self.municipio, destino_estado=self.municipio.estado,
            data_inicio=date(2026, 9, 10), data_fim=date(2026, 9, 12),
        )
        self.oficio = Oficio.objects.create(viagem=self.viagem, motorista=self.motorista)
        self.oficio.servidores.add(self.ana, self.bia)

    def _viagem(self, usuario):
        self.client.force_login(usuario)
        (ev,) = [e for e in _eventos(self.client).json() if e["id"] == f"viagem-{self.viagem.pk}"]
        return ev["extendedProps"]

    def test_pessoas_da_viagem_vem_com_o_motorista_primeiro(self):
        props = self._viagem(self.root)
        self.assertEqual(props["pessoas"], ["Motorista Teste".upper(), "ANA TESTE", "BIA TESTE"])
        self.assertFalse(props["meu"])
        self.assertIn(["Equipe", "MOTORISTA TESTE, ANA TESTE, BIA TESTE"], props["detalhes"])

    def test_viagem_e_minha_quando_estou_escalado(self):
        self.root.servidor = self.bia
        self.root.save(update_fields=["servidor"])
        self.assertTrue(self._viagem(self.root)["meu"])

    def test_viagem_e_minha_quando_criei_o_oficio(self):
        RegistroAuditoria.objects.create(
            usuario=self.root, acao=RegistroAuditoria.Acao.CRIACAO,
            modelo="viagens_oficios.oficio", objeto_id=str(self.oficio.pk),
        )
        self.assertTrue(self._viagem(self.root)["meu"])
        # Outro usuário com acesso a viagens: a mesma viagem não é dele.
        outro = User.objects.create_superuser("escala_outro", "escala_outro@example.com", None)
        self.assertFalse(self._viagem(outro)["meu"])

    def test_solicitacao_e_minha_quando_sou_o_motorista(self):
        s = self.criar_solicitacao(criado_por=self.gestor, motorista=self.motorista)
        self.solicitante.servidor = self.motorista
        self.solicitante.save(update_fields=["servidor"])
        self.client.force_login(self.gestor)
        (ev,) = [e for e in _eventos(self.client).json() if e["id"] == f"solicitacao-{s.pk}"]
        self.assertEqual(ev["extendedProps"]["pessoas"], ["MOTORISTA TESTE"])

    def test_escala_monta_uma_linha_por_pessoa(self):
        quadro = escala.montar(self.root, date(2026, 9, 7), 7)
        nomes = [l["nome"] for l in quadro["linhas"]]
        self.assertEqual(nomes, ["ANA TESTE", "BIA TESTE", "MOTORISTA TESTE"])
        ana = quadro["linhas"][0]
        # 10, 11 e 12 de setembro: quarta, quinta e sexta dessa semana.
        ocupados = [i for i, celula in enumerate(ana["celulas"]) if celula]
        self.assertEqual(ocupados, [3, 4, 5])
        self.assertEqual(ana["dias_fora"], 3)
        self.assertEqual(ana["celulas"][3][0]["fonte"], "viagem")

    def test_escala_filtra_por_pessoa_e_respeita_a_permissao(self):
        so_bia = escala.montar(self.root, date(2026, 9, 7), 7, pessoa="bia")
        self.assertEqual([l["nome"] for l in so_bia["linhas"]], ["BIA TESTE"])
        # Sem o módulo de viagens, a escala das viagens não existe para a pessoa.
        self.assertEqual(escala.montar(self.solicitante, date(2026, 9, 7), 7)["linhas"], [])

    def test_tela_da_escala(self):
        self.assertEqual(self.client.get(reverse("agenda:escala")).status_code, 302)
        self.client.force_login(self.root)
        resposta = self.client.get(reverse("agenda:escala"), {"inicio": "2026-09-07", "dias": "14", "pessoa": "ana"})
        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, "ANA TESTE")
        self.assertNotContains(resposta, "BIA TESTE")
        self.assertContains(resposta, reverse("viagens_viagem:painel", args=[self.viagem.pk]))
        # Dias fora do limite e datas inválidas caem no padrão, sem erro.
        self.assertEqual(self.client.get(reverse("agenda:escala"), {"inicio": "x", "dias": "900"}).status_code, 200)

    def test_painel_tem_o_filtro_de_pessoa_e_a_minha_agenda(self):
        self.client.force_login(self.root)
        resposta = self.client.get(reverse("agenda:painel"))
        self.assertContains(resposta, 'id="ag-pessoa"')
        self.assertContains(resposta, "Minha agenda")
        self.assertNotContains(resposta, "Só o que eu criei")
        self.assertContains(resposta, reverse("agenda:escala"))


class VinculoUsuarioServidor(BaseSolicitacaoTestCase):
    def setUp(self):
        super().setUp()
        self.admin = User.objects.create_user("adm_escala", password="x")
        self.admin.groups.add(Group.objects.get_or_create(name=GRUPO_ADMINISTRADOR)[0])
        cargo = Cargo.objects.create(nome="ESCRIVÃO")
        self.servidor = Servidor.objects.create(nome="CARLA DE SOUZA", cargo=cargo)
        self.carla = User.objects.create_user("carla", password="x", first_name="Carla", last_name="de Souza")

    def test_tela_sugere_o_servidor_pelo_nome(self):
        self.client.force_login(self.admin)
        resposta = self.client.get(reverse("accounts:usuarios_editar", args=[self.carla.pk]))
        self.assertContains(resposta, "Sugerido pelo nome")
        self.assertContains(resposta, "CARLA DE SOUZA")

    def test_salvar_o_vinculo_e_um_servidor_so_por_usuario(self):
        self.client.force_login(self.admin)
        dados = {
            "first_name": "Carla", "last_name": "de Souza", "username": "carla", "email": "carla@example.com",
            "perfil": "SOLICITANTE", "servidor": self.servidor.pk,
        }
        resposta = self.client.post(reverse("accounts:usuarios_editar", args=[self.carla.pk]), dados)
        self.assertEqual(resposta.status_code, 302)
        self.carla.refresh_from_db()
        self.assertEqual(self.carla.servidor, self.servidor)
        # Para outro usuário, o servidor já tomado nem está entre as opções.
        outro = User.objects.create_user("outro_vinculo", password="x")
        dados.update({"username": "outro_vinculo", "first_name": "Outro", "email": "o@example.com"})
        resposta = self.client.post(reverse("accounts:usuarios_editar", args=[outro.pk]), dados)
        self.assertEqual(resposta.status_code, 200)
        outro.refresh_from_db()
        self.assertIsNone(outro.servidor)
