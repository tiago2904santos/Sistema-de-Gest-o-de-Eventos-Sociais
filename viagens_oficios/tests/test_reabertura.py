"""Ofício finalizado ou assinado fica só para leitura; "Reabrir para
correção" pede o motivo e o registra no histórico; o PDF assinado que ficou
para trás dos dados ganha o selo "Assinado, mas os dados mudaram" (m109)."""
from django.core.files.base import ContentFile
from django.test import TestCase
from django.urls import reverse

from auditoria.models import RegistroAuditoria
from documentos.models import DocumentoArtefato, DocumentoAssinaturaVersao
from documentos.services.persistence import _payload_snapshot_json_seguro
from viagens_oficios.models import Oficio

from .fixtures import CenarioOficioMixin


class OficioFechadoTests(CenarioOficioMixin, TestCase):
    def setUp(self):
        super().setUp()
        self.oficio = self.criar()
        self.url = reverse('viagens_oficios:editar', args=[self.oficio.pk])

    def finalizar(self):
        Oficio.objects.filter(pk=self.oficio.pk).update(status=Oficio.STATUS_FINALIZADO)
        self.oficio.refresh_from_db()

    def assinar(self, payload=None):
        from documentos.editor.vinculos import vinculo_do_tipo
        payload = payload if payload is not None else vinculo_do_tipo('oficio').payload_atual(self.oficio)
        artefato = DocumentoArtefato.objects.create(
            tipo='oficio', formato='pdf', oficio=self.oficio, hash_sha256='0' * 64,
            nome_exibicao='oficio_1-2026_x.pdf', payload_snapshot=_payload_snapshot_json_seguro(payload),
            arquivo=ContentFile(b'%PDF-1.4', name='o.pdf'))
        return DocumentoAssinaturaVersao.objects.create(artefato=artefato, arquivo=ContentFile(b'%PDF-1.4 a', name='a.pdf'),
                                                        hash_sha256='1' * 64)

    def test_finalizado_fica_so_leitura_e_o_post_nao_grava(self):
        self.finalizar()
        r = self.client.get(self.url)
        self.assertContains(r, 'Ofício finalizado: somente leitura')
        self.assertContains(r, 'Reabrir para correção')
        self.assertContains(r, 'data-ofc-fechado="1"')
        self.assertNotContains(r, 'value="finalizar"')
        dados = self.payload() | {'motivo': 'Motivo trocado'}
        r = self.client.post(self.url, dados)
        self.assertEqual(r.status_code, 302)
        self.oficio.refresh_from_db()
        self.assertEqual(self.oficio.motivo, 'Missão F4')
        self.assertContains(self.client.get(self.url), 'reabra o ofício para correção')

    def test_reabrir_pede_motivo_e_o_registra_no_historico(self):
        self.finalizar()
        acao = reverse('viagens_oficios:acao', args=[self.oficio.pk, 'reabrir'])
        self.client.post(acao, {'motivo': '  '})
        self.oficio.refresh_from_db()
        self.assertEqual(self.oficio.status, Oficio.STATUS_FINALIZADO)
        self.client.post(acao, {'motivo': 'Data da viagem errada'})
        self.oficio.refresh_from_db()
        self.assertEqual(self.oficio.status, Oficio.STATUS_GERADO)
        registro = RegistroAuditoria.objects.filter(modelo='viagens_oficios.oficio', objeto_id=str(self.oficio.pk),
                                                    alteracoes__has_key='reabertura').latest('criado_em')
        self.assertEqual(registro.usuario, self.user)
        self.assertIn('Data da viagem errada', registro.alteracoes['reabertura']['depois'])
        self.assertNotContains(self.client.get(self.url), 'somente leitura')

    def test_reabrir_o_assinado_revoga_a_versao_e_libera_a_edicao(self):
        versao = self.assinar()
        r = self.client.get(self.url)
        self.assertContains(r, 'Ofício com PDF assinado: somente leitura')
        self.client.post(reverse('viagens_oficios:acao', args=[self.oficio.pk, 'reabrir']), {'motivo': 'Servidor a mais'})
        versao.refresh_from_db()
        self.assertIsNotNone(versao.revogada_em)
        self.assertEqual(versao.revogada_por, self.user)
        self.assertNotContains(self.client.get(self.url), 'somente leitura')

    def test_assinado_que_ficou_para_tras_dos_dados_ganha_o_selo(self):
        self.assinar()
        r = self.client.get(self.url)
        self.assertContains(r, '>Assinado</span>')
        self.assertNotContains(r, 'Assinado, mas os dados mudaram')
        # Mudança de fora do ofício (a tela do ofício está fechada): o cadastro do servidor.
        self.a.nome = 'ANA TESTE SILVA'
        self.a.save()
        r = self.client.get(self.url)
        self.assertContains(r, 'Assinado, mas os dados mudaram')
        from documentos.editor.vinculos import vinculo_do_tipo
        situacao = vinculo_do_tipo('oficio').assinatura(self.oficio)
        self.assertTrue(situacao['desatualizado'])
        self.assertTrue(any(m.startswith('Ofício:') for m in situacao['mudancas']), situacao['mudancas'])
        # O editor embutido do ofício explica o que mudou.
        embutido = self.client.get(reverse('documentos:editor_embutido', args=['oficio', self.oficio.pk]))
        self.assertContains(embutido, 'Assinado, mas os dados mudaram desde então')

    def test_artefato_antigo_sem_snapshot_nao_e_dado_como_desatualizado(self):
        self.assinar(payload={})
        from documentos.editor.vinculos import vinculo_do_tipo
        situacao = vinculo_do_tipo('oficio').assinatura(self.oficio)
        self.assertEqual(situacao, {'assinado': True, 'desatualizado': False, 'mudancas': []})
