"""m071: apontar e corrigir diferenças entre a viagem e os documentos dela."""
from datetime import date, datetime
from unittest.mock import patch

from django.urls import reverse
from django.utils import timezone

from viagens_cadastros.models import Viatura
from viagens_oficios.models import Oficio
from viagens_ordens.models import OrdemServico
from viagens_planos.models import PlanoTrabalho
from viagens_roteiros.models import Roteiro
from viagens_termos.models import TermoAutorizacao
from viagens_viagem.coerencia import aplicar_coerencia, verificar_coerencia

from .fixtures import CenarioViagem


class CoerenciaTests(CenarioViagem):
    def setUp(self):
        super().setUp()
        self.v = self.viagem()  # 05 a 07/10/2026, Londrina
        self.oficio = Oficio.objects.create(viagem=self.v, numero=40, ano=2026, viatura=self.viatura)
        self.oficio.servidores.set([self.a, self.b])

    def _documentos_adiados(self):
        """Documentos criados para a data antiga; a viagem foi adiada e mudou de cidade."""
        antigo = {"data_evento_inicio": date(2026, 9, 1), "data_evento_fim": date(2026, 9, 2)}
        ordem = OrdemServico.objects.create(numero=11, ano=2026, viagem=self.v, **antigo)
        ordem.definir_destinos([self.maringa.pk])
        ordem.servidores.set([self.a])
        plano = PlanoTrabalho.objects.create(numero=12, ano=2026, viagem=self.v, destino_cidade=self.maringa,
                                             destino_estado=self.pr, **antigo)
        outra = Viatura.objects.create(placa="OUT1A11", modelo="OUTRA")
        termo = TermoAutorizacao.objects.create(viagem=self.v, oficio=self.oficio, destino_cidade=self.maringa,
                                                destino_estado=self.pr, viatura=outra, **antigo)
        return ordem, plano, termo

    def test_aponta_periodo_destino_equipe_viatura_e_roteiro(self):
        ordem, plano, termo = self._documentos_adiados()
        Roteiro.objects.create(origem_municipio=self.sede, viagem=self.v,
                               saida_dt=timezone.make_aware(datetime(2026, 10, 6, 8, 0)))
        chaves = {d["chave"] for d in verificar_coerencia(self.v)}
        self.assertLessEqual({
            f"os-{ordem.pk}:periodo", f"os-{ordem.pk}:destinos", f"os-{ordem.pk}:equipe",
            f"pt-{plano.pk}:periodo", f"pt-{plano.pk}:destinos",
            f"termo-{termo.pk}:periodo", f"termo-{termo.pk}:destinos", f"termo-{termo.pk}:viatura",
        }, chaves)
        self.assertTrue(any(c.endswith(":saida") for c in chaves))
        r = self.client.get(self.etapa(self.v, 1))
        self.assertContains(r, "Documentos que não batem com a viagem.")
        self.assertContains(r, "Aplicar em todos")
        r = self.client.get(reverse("viagens_viagem:lista"))
        self.assertContains(r, "diferenças nos documentos")

    def test_aplicar_em_todos_sincroniza_e_poupa_o_assinado(self):
        ordem, plano, termo = self._documentos_adiados()
        with patch("viagens_viagem.coerencia._assinados", return_value={f"termo-{termo.pk}"}):
            aplicadas, puladas = aplicar_coerencia(self.v)
        self.assertTrue(aplicadas)
        self.assertEqual({d["documento"] for d in puladas}, {f"Termo #{termo.pk}"})
        ordem.refresh_from_db()
        plano.refresh_from_db()
        termo.refresh_from_db()
        self.assertEqual((ordem.data_evento_inicio, ordem.data_evento_fim), (date(2026, 10, 5), date(2026, 10, 7)))
        self.assertEqual([m.pk for m in ordem.destinos_em_ordem()], [self.londrina.pk])
        self.assertEqual(set(ordem.servidores.all()), {self.a, self.b})
        self.assertIn(self.oficio, ordem.oficios.all())
        self.assertEqual((plano.data_evento_inicio, plano.destino_cidade), (date(2026, 10, 5), self.londrina))
        # Assinado não muda por baixo de quem assinou.
        self.assertEqual(termo.data_evento_inicio, date(2026, 9, 1))
        restantes = {d["chave"].split(":")[0] for d in verificar_coerencia(self.v)}
        self.assertEqual(restantes, {f"termo-{termo.pk}"})

    def test_botao_do_painel_aplica(self):
        ordem, plano, termo = self._documentos_adiados()
        r = self.client.post(reverse("viagens_viagem:coerencia", args=[self.v.pk]), follow=True)
        self.assertContains(r, "Documentos atualizados com os dados da viagem")
        self.assertEqual(verificar_coerencia(self.v), [])
        termo.refresh_from_db()
        self.assertEqual(termo.viatura, self.viatura)

    def test_viagem_coerente_nao_mostra_cartao(self):
        self.assertEqual(verificar_coerencia(self.v), [])
        self.assertNotContains(self.client.get(self.etapa(self.v, 1)), "Documentos que não batem com a viagem.")
