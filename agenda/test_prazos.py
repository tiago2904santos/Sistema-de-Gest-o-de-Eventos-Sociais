"""A camada de prazos e pautas da agenda (m129): o que entra, como e para quem."""

import tempfile
from datetime import date, timedelta

from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from viagens_cadastros.models import Servidor
from viagens_oficios.models import Oficio
from viagens_prestacoes.models import PrestacaoContas, PrestacaoServidor

from . import fontes

User = get_user_model()


def _eventos(client, inicio, fim, **extra):
    params = {"start": inicio.isoformat(), "end": fim.isoformat()}
    params.update(extra)
    return client.get(reverse("agenda:eventos"), params).json()


class BasePrazos(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.root = User.objects.create_superuser("root_prazos", "root_prazos@example.com", None)
        cls.comum = User.objects.create_user("comum_prazos", password="x")
        cls.hoje = timezone.localdate()
        cls.inicio = cls.hoje - timedelta(days=30)
        cls.fim = cls.hoje + timedelta(days=30)

    def setUp(self):
        self.client.force_login(self.root)

    def eventos(self, **extra):
        return _eventos(self.client, self.inicio, self.fim, **extra)

    def prestacao(self, nome, prazo, *, finalizada=False, numero=None):
        oficio = Oficio.objects.create(assunto="Deslocamento", numero=numero, ano=2026 if numero else None)
        prestacao, _ = PrestacaoContas.objects.get_or_create(oficio=oficio)
        return PrestacaoServidor.objects.create(
            prestacao=prestacao, servidor=Servidor.objects.create(nome=nome),
            prazo_limite_saque=prazo, finalizada=finalizada,
        )


class FontesDePrazo(BasePrazos):
    def test_as_fontes_de_prazo_entram_para_quem_tem_o_modulo(self):
        slugs = {f.slug for f in fontes.fontes_de(self.root)}
        self.assertTrue({"prazo_diarias", "imprensa", "pauta", "contratos", "certidoes"} <= slugs)
        # Sem módulo nenhum: só o núcleo (solicitações), sem prazo de nada.
        self.assertEqual({f.slug for f in fontes.fontes_de(self.comum)}, {"solicitacao"})

    def test_prazo_de_saque_vira_evento_de_um_dia_com_as_classes_de_prazo(self):
        vencido = self.prestacao("ANA PRAZO", self.hoje - timedelta(days=2), numero=12)
        proximo = self.prestacao("BIA PRAZO", self.hoje + timedelta(days=3))
        longe = self.prestacao("CAIO PRAZO", self.hoje + timedelta(days=20))
        self.prestacao("DEA PRAZO", self.hoje + timedelta(days=3), finalizada=True)

        por_id = {e["id"]: e for e in self.eventos(fontes="prazo_diarias")}
        self.assertEqual(set(por_id), {f"prazo_diarias-{p.pk}" for p in (vencido, proximo, longe)})

        ev = por_id[f"prazo_diarias-{vencido.pk}"]
        self.assertTrue(ev["allDay"])
        self.assertEqual(ev["start"], (self.hoje - timedelta(days=2)).isoformat())
        self.assertEqual(ev["end"], (self.hoje - timedelta(days=1)).isoformat())
        self.assertIn("ag-prazo", ev["classNames"])
        self.assertIn("ag-prazo--vencido", ev["classNames"])
        self.assertEqual(ev["extendedProps"]["situacao"], "Vencido")
        self.assertIn("Ofício 12/2026", ev["title"])
        self.assertEqual(ev["extendedProps"]["url"], reverse("viagens_prestacoes:abrir_oficio", args=[vencido.oficio.pk]))

        self.assertIn("ag-prazo--proximo", por_id[f"prazo_diarias-{proximo.pk}"]["classNames"])
        classes_longe = por_id[f"prazo_diarias-{longe.pk}"]["classNames"]
        self.assertIn("ag-prazo", classes_longe)
        self.assertNotIn("ag-prazo--proximo", classes_longe)
        self.assertNotIn("ag-prazo--vencido", classes_longe)

    def test_deadline_da_imprensa_fechado_vem_encerrado(self):
        from atendimento_imprensa.models import Atendimento, SituacaoAtendimento

        aberto = Atendimento.objects.create(
            data=self.hoje, jornalista="Repórter A", pedido="Dados", deadline=self.hoje + timedelta(days=1),
            situacao=SituacaoAtendimento.EM_ANDAMENTO,
        )
        fechado = Atendimento.objects.create(
            data=self.hoje, jornalista="Repórter B", pedido="Dados", deadline=self.hoje + timedelta(days=1),
            situacao=SituacaoAtendimento.ATENDIDO,
        )
        por_id = {e["id"]: e for e in self.eventos(fontes="imprensa")}
        self.assertFalse(por_id[f"imprensa-{aberto.pk}"]["extendedProps"]["encerrado"])
        self.assertIn("ag-prazo--proximo", por_id[f"imprensa-{aberto.pk}"]["classNames"])
        self.assertTrue(por_id[f"imprensa-{fechado.pk}"]["extendedProps"]["encerrado"])
        self.assertNotIn("ag-prazo--proximo", por_id[f"imprensa-{fechado.pk}"]["classNames"])

    def test_pauta_traz_dia_horario_e_situacao_do_modulo(self):
        from datetime import time

        from publicacoes.models import Publicacao, Responsavel

        p = Publicacao.objects.create(
            data=self.hoje, jornalista=Responsavel.objects.create(nome="Jornalista P"),
            titulo="Operação na região", inicio_pauta=time(8, 30),
        )
        (ev,) = [e for e in self.eventos(fontes="pauta") if e["id"] == f"pauta-{p.pk}"]
        self.assertIn("08:30", ev["title"])
        self.assertIn("Operação na região", ev["title"])
        self.assertEqual(ev["extendedProps"]["situacao"], "Pendente")
        self.assertEqual(ev["extendedProps"]["url"], reverse("publicacoes:editar", args=[p.pk]))

    def test_contratos_aditivos_e_so_a_certidao_vigente_de_cada_tipo(self):
        from coffee_break.models import AditivoContrato, CertidaoFornecedor, ContratoCoffeeBreak, Fornecedor, TipoCertidao

        fornecedor = Fornecedor.objects.create(razao_social="PADARIA TESTE LTDA", cnpj="00000000000191")
        contrato = ContratoCoffeeBreak.objects.create(
            fornecedor=fornecedor, numero="0001/2026", vigencia_fim=self.hoje + timedelta(days=10),
        )
        aditivo = AditivoContrato.objects.create(contrato=contrato, numero="0002/2026", vigencia_fim=self.hoje + timedelta(days=20))
        with tempfile.TemporaryDirectory() as pasta, override_settings(MEDIA_ROOT=pasta):
            antiga = CertidaoFornecedor.objects.create(
                fornecedor=fornecedor, tipo=TipoCertidao.FEDERAL, validade=self.hoje + timedelta(days=2),
                arquivo=ContentFile(b"%PDF-1.4", name="a.pdf"),
            )
            nova = CertidaoFornecedor.objects.create(
                fornecedor=fornecedor, tipo=TipoCertidao.FEDERAL, validade=self.hoje + timedelta(days=25),
                arquivo=ContentFile(b"%PDF-1.4", name="b.pdf"),
            )
            ids = {e["id"] for e in self.eventos(fontes="contratos,certidoes")}
        self.assertIn(f"contratos-{contrato.pk}", ids)
        self.assertIn(f"contratos-a{aditivo.pk}", ids)
        self.assertIn(f"certidoes-{nova.pk}", ids)
        self.assertNotIn(f"certidoes-{antiga.pk}", ids)


class DossieDoPrazo(BasePrazos):
    def test_dossie_do_prazo_de_saque_e_a_permissao_do_modulo(self):
        ps = self.prestacao("MARIA PRAZO", self.hoje + timedelta(days=5), numero=7)
        resposta = self.client.get(reverse("agenda:detalhe", args=["prazo_diarias", ps.pk]))
        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, "MARIA PRAZO")
        self.assertContains(resposta, "Ofício 07/2026")
        self.assertContains(resposta, reverse("viagens_prestacoes:abrir_oficio", args=[ps.oficio.pk]))
        self.assertContains(resposta, "Prestar contas até")

        self.client.force_login(self.comum)
        self.assertEqual(self.client.get(reverse("agenda:detalhe", args=["prazo_diarias", ps.pk])).status_code, 403)

    def test_dossie_das_certidoes_lista_o_quadro_do_fornecedor(self):
        from coffee_break.models import Fornecedor

        fornecedor = Fornecedor.objects.create(razao_social="CAFÉ TESTE LTDA", cnpj="00000000000272")
        resposta = self.client.get(reverse("agenda:detalhe", args=["certidoes", fornecedor.pk]))
        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, "CAFÉ TESTE LTDA")
        self.assertContains(resposta, "não anexada")
