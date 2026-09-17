"""Os textos do documento por tipo de necessidade — os testes da origem, sem área."""

from datetime import date

from django.test import TestCase

from viagens_cadastros.models import Servidor
from viagens_ordens.docxtpl_context import _equipe_deslocamento, _periodo_extenso, build_os_docxtpl_context
from viagens_ordens.forms import OrdemServicoForm
from viagens_ordens.models import OrdemServico

from .fixtures import CenarioOrdemMixin


class DocxtplContextTests(CenarioOrdemMixin, TestCase):
    def setUp(self):
        super().setUp()
        self.motorista = Servidor.objects.create(nome="MOTORISTA TESTE")
        self.tecnico = Servidor.objects.create(nome="TECNICO TESTE")
        self.montagem = Servidor.objects.create(nome="APOIO MONTAGEM")
        self.escolta = Servidor.objects.create(nome="APOIO ESCOLTA")
        self.apoio_extra = Servidor.objects.create(nome="APOIO EXTRA")
        self.coordenador = Servidor.objects.create(nome="COORDENADOR CERIMONIAL")
        self.apoio = Servidor.objects.create(nome="APOIO CERIMONIAL")
        self.preparacao = Servidor.objects.create(nome="APOIO PREPARACAO")

    def _ordem(self, tipo):
        ordem = OrdemServico.objects.create(
            tipo_necessidade=tipo, data_evento_inicio=date(2026, 8, 10), data_evento_fim=date(2026, 8, 12),
            motivo="evento institucional", motorista_equipe=self.motorista, tecnico_equipe=self.tecnico,
            apoio_montagem=self.montagem, apoio_escolta=self.escolta, coordenador_cerimonial=self.coordenador,
            apoio_cerimonial=self.apoio, apoio_preparacao=self.preparacao,
        )
        ordem.destinos.set([self.sede])
        ordem.servidores.set([self.motorista, self.tecnico, self.montagem, self.escolta, self.apoio_extra])
        return ordem

    def test_cabecalho_assinante_e_periodo(self):
        ctx = build_os_docxtpl_context(self._ordem(OrdemServico.TIPO_PADRAO))
        self.assertEqual(ctx["ordem_de_servico"], f"001/{self.hoje.year}")
        self.assertEqual(ctx["nome_chefia"], "Bruno Teste")
        self.assertEqual(ctx["cargo_chefia"], "Investigador")
        self.assertEqual(ctx["destino"], "Curitiba/PR")
        self.assertEqual(ctx["data_extenso"], "nos dias 10 a 12 de agosto de 2026")
        self.assertEqual(ctx["referencia"], "Diligências")
        self.assertIn("para o município de Curitiba/PR, nos dias 10 a 12 de agosto de 2026, para realizar Evento Institucional.", ctx["determinacao"])
        self.assertEqual(ctx["unidade"], "UNIDADE OS")

    def test_periodo_extenso(self):
        self.assertEqual(_periodo_extenso(date(2026, 8, 10), None), "no dia 10 de agosto de 2026")
        self.assertEqual(_periodo_extenso(date(2026, 8, 30), date(2026, 9, 2)), "nos dias 30 de agosto de 2026 a 2 de setembro de 2026")
        self.assertEqual(_periodo_extenso(None, None), "")

    def test_equipe_por_cargo_com_plural(self):
        ordem = self.ordem(servidores=[self.a, self.b, self.motorista])
        self.assertEqual(_equipe_deslocamento(ordem), "dos investigadores Ana Teste e Bruno Teste e Motorista Teste")
        self.assertEqual(_equipe_deslocamento(self.ordem(servidores=[self.a])), "do investigador Ana Teste")
        self.assertEqual(_equipe_deslocamento(self.ordem()), "da equipe")

    def test_caminhao_descreve_competencias_por_funcao_e_dois_dias(self):
        ordem = self._ordem(OrdemServico.TIPO_CAMINHAO)
        ordem.funcoes_servidores = {
            str(self.motorista.pk): OrdemServico.FUNCAO_CONDUCAO, str(self.tecnico.pk): OrdemServico.FUNCAO_TECNICO,
            str(self.montagem.pk): OrdemServico.FUNCAO_APOIO, str(self.escolta.pk): OrdemServico.FUNCAO_APOIO,
        }
        ordem.save(update_fields=["funcoes_servidores"])
        ctx = build_os_docxtpl_context(ordem)
        self.assertEqual(ctx["referencia"], "Deslocamento - Caminhão de apoio")
        self.assertEqual(len(ctx["competencias_equipe"]), 3)
        self.assertIn("Motorista Teste – conduzir a Unidade Móvel (caminhão)", ctx["competencias_equipe"][0])
        self.assertIn("Tecnico Teste – prestar apoio técnico", ctx["competencias_equipe"][1])
        self.assertIn("Apoio Montagem e Apoio Escolta: realizar a escolta", ctx["competencias_equipe"][2])
        self.assertIn("entre Curitiba e Curitiba/PR", ctx["competencias_equipe"][2])
        self.assertNotIn("Apoio Extra", " ".join(ctx["competencias_equipe"]))
        self.assertIn("dois dias de antecedência", " ".join(ctx["justificativas"]))
        self.assertIn("dois dias posteriores", " ".join(ctx["justificativas"]))

    def test_caminhao_sem_funcao_gera_texto_padrao(self):
        ctx = build_os_docxtpl_context(self._ordem(OrdemServico.TIPO_CAMINHAO))
        self.assertEqual(ctx["referencia"], "Diligências")
        self.assertEqual(ctx["competencias_equipe"], [])
        self.assertEqual(ctx["justificativas"], [])

    def test_caminhao_tecnico_e_opcional(self):
        ordem = self._ordem(OrdemServico.TIPO_CAMINHAO)
        ordem.funcoes_servidores = {str(self.motorista.pk): "CONDUCAO", str(self.montagem.pk): "APOIO", str(self.escolta.pk): "APOIO"}
        ordem.save(update_fields=["funcoes_servidores"])
        ctx = build_os_docxtpl_context(ordem)
        self.assertEqual(len(ctx["competencias_equipe"]), 2)
        self.assertNotIn("prestar apoio técnico", " ".join(ctx["competencias_equipe"]))

    def test_microonibus_sem_funcao_usa_os_papeis_fixos(self):
        ctx = build_os_docxtpl_context(self._ordem(OrdemServico.TIPO_MICROONIBUS))
        self.assertEqual(ctx["referencia"], "Deslocamento - Micro-ônibus")
        self.assertEqual(len(ctx["competencias_equipe"]), 4)
        self.assertIn("sem necessidade de deslocamento com dois dias de antecedência", " ".join(ctx["justificativas"]))

    def test_microonibus_descreve_competencias_por_funcao(self):
        ordem = self._ordem(OrdemServico.TIPO_MICROONIBUS)
        ordem.funcoes_servidores = {str(self.motorista.pk): "CONDUCAO", str(self.tecnico.pk): "TECNICO", str(self.montagem.pk): "APOIO"}
        ordem.save(update_fields=["funcoes_servidores"])
        ctx = build_os_docxtpl_context(ordem)
        self.assertEqual(len(ctx["competencias_equipe"]), 3)
        self.assertIn("conduzir o micro-ônibus oficial", ctx["competencias_equipe"][0])
        self.assertIn("prestar suporte técnico", ctx["competencias_equipe"][1])
        self.assertIn("prestar apoio operacional", ctx["competencias_equipe"][2])

    def test_cerimonial_descreve_ida_antecipada_e_competencias(self):
        ctx = build_os_docxtpl_context(self._ordem(OrdemServico.TIPO_CERIMONIAL_ANTECIPADO))
        self.assertEqual(ctx["referencia"], "Deslocamento - Equipe de Cerimonial")
        self.assertEqual(len(ctx["competencias_equipe"]), 3)
        self.assertIn("Coordenador Cerimonial", ctx["competencias_equipe"][0])
        self.assertEqual(len(ctx["justificativas"]), 2)
        self.assertIn("inexistência de visita técnica prévia", ctx["justificativas"][0])
        self.assertIn("padrões da Polícia Civil do Paraná", ctx["finalidade"])

    def test_cerimonial_descreve_competencias_por_funcao(self):
        ordem = self._ordem(OrdemServico.TIPO_CERIMONIAL_ANTECIPADO)
        ordem.funcoes_servidores = {str(self.coordenador.pk): "COORDENACAO", str(self.apoio.pk): "APOIO", str(self.preparacao.pk): "PREPARACAO"}
        ordem.servidores.set([self.coordenador, self.apoio, self.preparacao])
        ordem.save(update_fields=["funcoes_servidores"])
        ctx = build_os_docxtpl_context(ordem)
        self.assertEqual(len(ctx["competencias_equipe"]), 3)
        self.assertIn("coordenar as atividades de Cerimonial", ctx["competencias_equipe"][0])
        self.assertIn("prestar apoio às atividades de Cerimonial", ctx["competencias_equipe"][1])
        self.assertIn("auxiliar na preparação da solenidade", ctx["competencias_equipe"][2])

    def test_operacao_policial_justifica_apenas_um_dia_posterior(self):
        ctx = build_os_docxtpl_context(self._ordem(OrdemServico.TIPO_OPERACAO_RETORNO_POSTERIOR))
        self.assertEqual(ctx["referencia"], "Deslocamento - Operação policial com um dia posterior")
        self.assertEqual(len(ctx["justificativas"]), 1)
        self.assertIn("A concessão de um dia posterior justifica-se", ctx["justificativas"][0])
        self.assertNotIn("ida antecipada", ctx["justificativas"][0].lower())

    def test_form_salva_funcoes_dinamicas(self):
        form = OrdemServicoForm(data={
            "data_evento_inicio": "2026-08-10", "data_evento_fim": "2026-08-12",
            "destino_estado": str(self.uf.pk), "destino_cidade": str(self.sede.pk),
            "servidores": [str(self.motorista.pk), str(self.montagem.pk), str(self.escolta.pk)],
            "tipo_necessidade": OrdemServico.TIPO_CAMINHAO,
            f"funcao_servidor_{self.motorista.pk}": "CONDUCAO", f"funcao_servidor_{self.montagem.pk}": "APOIO",
            f"funcao_servidor_{self.escolta.pk}": "APOIO", "motivo": "evento institucional",
        })
        self.assertTrue(form.is_valid(), form.errors.as_data())
        ordem = form.save()
        self.assertEqual(ordem.funcoes_servidores, {str(self.motorista.pk): "CONDUCAO", str(self.montagem.pk): "APOIO", str(self.escolta.pk): "APOIO"})
        self.assertEqual(list(ordem.destinos.all()), [self.sede])

    def test_form_recusa_funcao_invalida(self):
        form = OrdemServicoForm(data={
            "destino_estado": str(self.uf.pk), "destino_cidade": str(self.sede.pk), "servidores": [str(self.motorista.pk)],
            "tipo_necessidade": OrdemServico.TIPO_MICROONIBUS, f"funcao_servidor_{self.motorista.pk}": "PILOTO",
        })
        self.assertFalse(form.is_valid())
        self.assertIn("Selecione uma função válida para os servidores da equipe.", form.non_field_errors())
