"""m064: gerar os documentos da viagem de uma vez, um ofício por equipe."""
from django.urls import reverse

from cadastros.models import Equipe
from viagens_cadastros.models import Servidor, Unidade, Viatura
from viagens_oficios.models import Oficio
from viagens_ordens.models import OrdemServico
from viagens_planos.models import PlanoTrabalho
from viagens_roteiros.models import Roteiro
from viagens_viagem.models import EquipePrevista, Viagem

from .fixtures import CenarioViagem


class GerarDocumentosTests(CenarioViagem):
    def setUp(self):
        super().setUp()
        outra = Unidade.objects.create(nome="Outra unidade")
        self.c = Servidor.objects.create(nome="CARLA VIAGEM", cargo=self.cargo, unidade=outra, cpf="99988877766")
        self.d = Servidor.objects.create(nome="DIEGO VIAGEM", cargo=self.cargo, unidade=outra, cpf="12312312312")
        self.vtr2 = Viatura.objects.create(placa="XYZ9A87", modelo="VEÍCULO 2")
        self.v = self.viagem()
        self.roteiro = Roteiro.objects.create(origem_municipio=self.sede, viagem=self.v)
        self.url = reverse("viagens_viagem:gerar_documentos", args=[self.v.pk])

    def _post(self, **extras):
        # Exemplo do usuário: servidor 1 dirige a VTR 1 no ofício 1; servidores
        # 2, 3 e 4, com o 4 dirigindo a VTR 2, no ofício 2.
        dados = {
            "quantidade_oficios": "2", "acao": "gerar",
            "oficio-0-servidores": [str(self.a.pk)], "oficio-0-motorista": str(self.a.pk), "oficio-0-viatura": str(self.viatura.pk),
            "oficio-1-servidores": [str(self.b.pk), str(self.c.pk), str(self.d.pk)],
            "oficio-1-motorista": str(self.d.pk), "oficio-1-viatura": str(self.vtr2.pk),
            "gerar_termos": "1", "gerar_ordem": "1", "gerar_plano": "1",
        }
        dados.update(extras)
        return self.client.post(self.url, dados)

    def test_tela_mostra_o_contador_da_meta(self):
        EquipePrevista.objects.create(viagem=self.v, equipe=Equipe.objects.create(nome="ASCOM"), quantidade=4)
        r = self.client.get(self.url)
        self.assertContains(r, "Ofício 1")
        self.assertContains(r, 'data-meta="4"')
        self.assertContains(r, "Faltam 4 servidores da ASCOM.")
        self.assertContains(self.client.get(self.etapa(self.v, 1)), self.url)

    def test_um_oficio_por_equipe_com_motorista_viatura_termos_os_e_plano(self):
        r = self._post()
        self.assertRedirects(r, self.etapa(self.v, 3), fetch_redirect_response=False)
        oficios = list(Oficio.objects.filter(viagem=self.v).order_by("numero"))
        self.assertEqual(len(oficios), 2)
        um, dois = oficios
        self.assertEqual(set(um.servidores.all()), {self.a})
        self.assertEqual((um.motorista, um.viatura, um.roteiro), (self.a, self.viatura, self.roteiro))
        self.assertEqual(set(dois.servidores.all()), {self.b, self.c, self.d})
        self.assertEqual((dois.motorista, dois.viatura), (self.d, self.vtr2))
        self.assertEqual(dois.diarias_quantidade_servidores, 3)
        self.assertTrue(all(o.status == Oficio.STATUS_RASCUNHO and not o.protocolo for o in oficios))
        # Termos: todos, menos quem é da unidade emissora (a da configuração).
        self.assertEqual(set(um.servidores_termo_autorizacao.all()), set())
        self.assertEqual(set(dois.servidores_termo_autorizacao.all()), {self.c, self.d})
        ordem = OrdemServico.objects.get(viagem=self.v)
        self.assertEqual(set(ordem.servidores.all()), {self.a, self.b, self.c, self.d})
        self.assertEqual(set(ordem.oficios.all()), {um, dois})
        self.assertEqual([m.pk for m in ordem.destinos_em_ordem()], [self.londrina.pk])
        self.assertTrue(PlanoTrabalho.objects.filter(viagem=self.v).exists())
        self.v.refresh_from_db()
        self.assertEqual(self.v.status, Viagem.STATUS_DOCUMENTOS_GERADOS)

    def test_motorista_fora_das_equipes_entra_na_do_seu_oficio(self):
        self._post(**{"oficio-1-servidores": [str(self.b.pk), str(self.c.pk)]})
        dois = Oficio.objects.filter(viagem=self.v).order_by("numero").last()
        self.assertEqual(set(dois.servidores.all()), {self.b, self.c, self.d})

    def test_motorista_de_outro_oficio_vira_referencia(self):
        self._post(**{"oficio-1-motorista": str(self.a.pk)})
        um, dois = Oficio.objects.filter(viagem=self.v).order_by("numero")
        self.assertEqual(dois.motorista, self.a)
        self.assertNotIn(self.a, dois.servidores.all())
        self.assertEqual(dois.motorista_oficio_referencia, f"{um.numero}/{um.ano}")

    def test_servidor_em_dois_oficios_ou_viatura_repetida_nao_gera(self):
        r = self._post(**{"oficio-1-servidores": [str(self.a.pk), str(self.b.pk)], "oficio-1-viatura": str(self.viatura.pk)})
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "cada servidor vai em um ofício só")
        self.assertContains(r, "está nos ofícios 1 e 2")
        self.assertFalse(Oficio.objects.filter(viagem=self.v).exists())

    def test_nao_mexe_na_os_e_no_plano_que_ja_existem(self):
        OrdemServico.objects.create(numero=5, ano=2026, viagem=self.v)
        PlanoTrabalho.objects.create(numero=6, ano=2026, viagem=self.v)
        r = self._post()
        self.assertEqual(OrdemServico.objects.filter(viagem=self.v).count(), 1)
        self.assertEqual(PlanoTrabalho.objects.filter(viagem=self.v).count(), 1)
        mensagens = [str(m) for m in r.wsgi_request._messages]
        self.assertTrue(any("já tinha a OS 005/2026" in m for m in mensagens), mensagens)

    def test_adicionar_e_remover_oficio_reenviam_a_tela(self):
        r = self.client.post(self.url, {"quantidade_oficios": "1", "acao": "adicionar", "oficio-0-servidores": [str(self.a.pk)]})
        self.assertEqual(r.context["quantidade"], 2)
        self.assertTrue(r.context["blocos"][0]["servidores"][0]["selecionado"])
        r = self.client.post(self.url, {"quantidade_oficios": "2", "acao": "remover-0", "oficio-1-servidores": [str(self.b.pk)]})
        self.assertEqual(r.context["quantidade"], 1)
        escolhidos = [o["rotulo"] for o in r.context["blocos"][0]["servidores"] if o["selecionado"]]
        self.assertEqual(escolhidos, ["BRUNO VIAGEM"])
        self.assertFalse(Oficio.objects.filter(viagem=self.v).exists())
