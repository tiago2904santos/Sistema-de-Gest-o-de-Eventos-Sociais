"""m050: os rascunhos de ofício, OS e plano se salvam sozinhos."""
import json
from datetime import date
from unittest.mock import patch

from django.urls import reverse

from viagens_oficios.models import Oficio
from viagens_ordens.models import OrdemServico
from viagens_planos.models import PlanoTrabalho

from .fixtures import CenarioViagem


class AutosaveRascunhoTests(CenarioViagem):
    def _post(self, url, model, pk, campos):
        corpo = {"model": model, "object_id": str(pk), "form_id": "", "dirty_fields": list(campos), "fields": campos, "snapshots": {}}
        return self.client.post(url, json.dumps(corpo), content_type="application/json")

    def test_oficio_grava_rascunho_sem_numero_data_nem_protocolo_automatico(self):
        oficio = Oficio.objects.create(numero=50, ano=2026, data_criacao=date(2026, 9, 20), motivo="Antes")
        url = reverse("viagens_oficios:autosalvar", args=[oficio.pk])
        self.assertContains(self.client.get(reverse("viagens_oficios:editar", args=[oficio.pk])), f'data-autosave-url="{url}"')
        with patch("viagens_oficios.protocolo_services.abrir_protocolo_do_oficio") as abrir:
            r = self._post(url, "oficio", oficio.pk, {
                "motivo": "Texto digitado antes de a sessão cair", "custeio": Oficio.CUSTEIO_UNIDADE_DPC,
                "servidores": [str(self.a.pk), str(self.b.pk)], "servidores_termo_autorizacao_present": "1",
                "numero": "7", "data_criacao": "2026-01-02", "motorista_modo": Oficio.MOTORISTA_MODO_SERVIDOR,
                "justificativa-texto": "Justificativa em andamento",
            })
        self.assertEqual(r.status_code, 200, r.content)
        self.assertTrue(r.json()["ok"])
        abrir.assert_not_called()
        oficio.refresh_from_db()
        self.assertEqual(oficio.motivo, "Texto digitado antes de a sessão cair")
        self.assertEqual(set(oficio.servidores.all()), {self.a, self.b})
        self.assertEqual((oficio.numero, oficio.data_criacao), (50, date(2026, 9, 20)))
        self.assertEqual(oficio.status, Oficio.STATUS_RASCUNHO)
        self.assertEqual(oficio.justificativa.texto, "Justificativa em andamento")

    def test_oficio_finalizado_nao_se_salva_sozinho(self):
        oficio = Oficio.objects.create(numero=51, ano=2026, motivo="Final", status=Oficio.STATUS_FINALIZADO)
        self.assertNotContains(self.client.get(reverse("viagens_oficios:editar", args=[oficio.pk])), "data-autosave-rascunho")
        r = self._post(reverse("viagens_oficios:autosalvar", args=[oficio.pk]), "oficio", oficio.pk, {"motivo": "Outro"})
        self.assertEqual(r.status_code, 400)
        oficio.refresh_from_db()
        self.assertEqual(oficio.motivo, "Final")

    def test_os_grava_sem_mexer_no_numero(self):
        ordem = OrdemServico.objects.create(numero=60, ano=2026, motivo="Antes")
        url = reverse("viagens_ordens:autosalvar", args=[ordem.pk])
        self.assertContains(self.client.get(reverse("viagens_ordens:editar", args=[ordem.pk])), f'data-autosave-url="{url}"')
        r = self._post(url, "ordem_servico", ordem.pk, {
            "numero": "1", "tipo_necessidade": OrdemServico.TIPO_PADRAO, "motivo": "Motivo novo",
            "servidores": [str(self.a.pk)], "data_evento_inicio": "2026-10-05", "data_evento_fim": "2026-10-06",
            "destino_estado": str(self.pr.pk), "destino_cidade": str(self.londrina.pk), "quantidade_destinos": "0",
        })
        self.assertEqual(r.status_code, 200, r.content)
        ordem.refresh_from_db()
        self.assertEqual((ordem.numero, ordem.motivo), (60, "Motivo novo"))
        self.assertEqual(list(ordem.servidores.all()), [self.a])
        # Modelo errado no payload não passa.
        self.assertEqual(self._post(url, "oficio", ordem.pk, {}).status_code, 400)

    def test_plano_grava_rascunho_e_para_depois_de_finalizado(self):
        plano = PlanoTrabalho.objects.create(numero=70, ano=2026)
        url = reverse("viagens_planos:autosalvar", args=[plano.pk])
        self.assertContains(self.client.get(reverse("viagens_planos:editar", args=[plano.pk])), f'data-autosave-url="{url}"')
        campos = {
            "numero": "3", "programa_outros": "Ação comunitária", "data_evento_inicio": "2026-10-05",
            "data_evento_fim": "2026-10-05", "destino_estado": str(self.pr.pk), "destino_cidade": str(self.londrina.pk),
            "quantidade_destinos": "0",
            "efetivo-TOTAL_FORMS": "0", "efetivo-INITIAL_FORMS": "0", "efetivo-MIN_NUM_FORMS": "0", "efetivo-MAX_NUM_FORMS": "1000",
        }
        r = self._post(url, "plano_trabalho", plano.pk, campos)
        self.assertEqual(r.status_code, 200, r.content)
        plano.refresh_from_db()
        self.assertEqual((plano.numero, plano.destino_cidade, plano.data_evento_inicio), (70, self.londrina, date(2026, 10, 5)))
        plano.status = PlanoTrabalho.STATUS_GERADO
        plano.save(update_fields=["status"])
        self.assertEqual(self._post(url, "plano_trabalho", plano.pk, campos).status_code, 400)
