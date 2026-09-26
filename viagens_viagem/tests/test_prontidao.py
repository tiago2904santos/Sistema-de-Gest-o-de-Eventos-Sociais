"""m066: o quadro "o que falta para a viagem ficar pronta", etapa por etapa."""
from django.urls import reverse

from cadastros.models import Equipe
from viagens_cadastros.models import Servidor
from viagens_oficios.models import Oficio
from viagens_viagem.models import EquipePrevista
from viagens_viagem.prontidao import quadro_de_prontidao

from .fixtures import CenarioViagem


def _por_chave(quadro):
    return {e["chave"]: e for e in quadro["etapas"]}


class ProntidaoTests(CenarioViagem):
    def test_viagem_vazia_aponta_cada_etapa_com_link(self):
        v = self.viagem()
        quadro = quadro_de_prontidao(v)
        etapas = _por_chave(quadro)
        self.assertEqual(list(etapas), ["dados", "roteiro", "oficios", "equipe", "ordem", "plano", "termos", "assinaturas", "protocolo"])
        self.assertTrue(etapas["dados"]["ok"])
        self.assertIn("Crie o roteiro", etapas["roteiro"]["itens"][0]["texto"])
        self.assertIn(f"viagem={v.pk}", etapas["roteiro"]["itens"][0]["url"])
        self.assertEqual(etapas["oficios"]["itens"][0]["url"], reverse("viagens_viagem:gerar_documentos", args=[v.pk]))
        self.assertFalse(etapas["ordem"]["ok"])
        self.assertFalse(etapas["plano"]["ok"])
        self.assertFalse(quadro["pronta"])

        r = self.client.get(self.etapa(v, 1))
        self.assertContains(r, "O que falta para a viagem ficar pronta")
        self.assertContains(r, 'data-prontidao open')
        # Nas outras etapas o quadro vem fechado, só com o resumo.
        r = self.client.get(self.etapa(v, 2))
        self.assertContains(r, "data-prontidao>")

    def test_oficio_aponta_cadastro_meta_protocolo_simulado_e_termo(self):
        v = self.viagem()
        EquipePrevista.objects.create(viagem=v, equipe=Equipe.objects.create(nome="ASCOM"), quantidade=3)
        sem_rg = Servidor.objects.create(nome="SEM DOCUMENTO", cargo=self.cargo)
        oficio = Oficio.objects.create(viagem=v, numero=30, ano=2026, protocolo="123456789",
                                       protocolo_origem=Oficio.PROTOCOLO_ORIGEM_SIMULADO, viatura=self.viatura)
        oficio.servidores.set([self.a, sem_rg])
        etapas = _por_chave(quadro_de_prontidao(v))
        textos = lambda chave: " | ".join(i["texto"] for i in etapas[chave]["itens"])
        self.assertIn("Ofício 30/2026", textos("oficios"))
        self.assertIn("Falta 1 servidor da ASCOM.", textos("equipe"))
        self.assertIn("Cadastro de SEM DOCUMENTO sem CPF, unidade", textos("equipe"))
        self.assertIn("viatura ABC1D23", textos("equipe"))
        self.assertIn("simulado", textos("protocolo"))
        # A é da unidade emissora (configuração): sem termo é o esperado; o outro não.
        self.assertIn("sem termo para SEM DOCUMENTO", textos("termos"))
        self.assertNotIn("ANA VIAGEM", textos("termos"))
        self.assertTrue(all(i["url"] for e in etapas.values() for i in e["itens"]))
