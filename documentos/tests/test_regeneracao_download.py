"""Download de artefato antigo: o PDF é refeito pelo motor de hoje.

O que se testa aqui é a regra de decisão (`precisa_regerar`) e a proteção do
`regerar` — não a geração de cada tipo, que tem os testes dela.
"""

from unittest import mock

from django.test import SimpleTestCase

from documentos.services import regeneracao
from documentos.services.regeneracao import MOTOR_ATUAL, precisa_regerar, regerar
from documentos.services.types import DocumentoTipo


class ArtefatoFalso:
    def __init__(self, tipo=DocumentoTipo.OFICIO.value, formato="pdf", engine="word_com"):
        self.tipo = tipo
        self.formato = formato
        self.engine = engine
        self.pk = "id-de-teste"


class PrecisaRegerarTests(SimpleTestCase):
    def setUp(self):
        self._original = dict(regeneracao._REGERADORES)
        regeneracao._REGERADORES[DocumentoTipo.OFICIO.value] = lambda a: b"%PDF novo"

    def tearDown(self):
        regeneracao._REGERADORES.clear()
        regeneracao._REGERADORES.update(self._original)

    def test_pdf_do_motor_antigo_e_refeito(self):
        self.assertTrue(precisa_regerar(ArtefatoFalso(), assinado=False))

    def test_pdf_que_ja_nasceu_do_html_fica_como_esta(self):
        self.assertFalse(precisa_regerar(ArtefatoFalso(engine=MOTOR_ATUAL), assinado=False))

    def test_arquivo_assinado_nunca_e_refeito(self):
        self.assertFalse(precisa_regerar(ArtefatoFalso(), assinado=True))

    def test_docx_nao_e_refeito(self):
        self.assertFalse(precisa_regerar(ArtefatoFalso(formato="docx"), assinado=False))

    def test_tipo_sem_regerador_registrado_fica_como_esta(self):
        # O termo não é registrado: a variante do modelo não fica gravada no
        # artefato, então refazer poderia devolver outro documento.
        self.assertFalse(
            precisa_regerar(ArtefatoFalso(tipo=DocumentoTipo.TERMO_AUTORIZACAO.value), assinado=False)
        )


class RegerarTests(SimpleTestCase):
    def setUp(self):
        self._original = dict(regeneracao._REGERADORES)

    def tearDown(self):
        regeneracao._REGERADORES.clear()
        regeneracao._REGERADORES.update(self._original)

    def test_devolve_os_bytes_do_regerador(self):
        regeneracao._REGERADORES[DocumentoTipo.OFICIO.value] = lambda a: b"%PDF refeito"
        self.assertEqual(regerar(ArtefatoFalso()), b"%PDF refeito")

    def test_registro_de_origem_sumido_devolve_none(self):
        regeneracao._REGERADORES[DocumentoTipo.OFICIO.value] = lambda a: None
        self.assertIsNone(regerar(ArtefatoFalso()))

    def test_erro_ao_refazer_nao_derruba_o_download(self):
        def explode(artefato):
            raise ValueError("ofício inválido hoje")

        regeneracao._REGERADORES[DocumentoTipo.OFICIO.value] = explode
        with mock.patch.object(regeneracao.logger, "warning") as aviso:
            self.assertIsNone(regerar(ArtefatoFalso()))
        self.assertTrue(aviso.called)

    def test_tipo_sem_regerador_devolve_none(self):
        regeneracao._REGERADORES.clear()
        self.assertIsNone(regerar(ArtefatoFalso()))


class RegeradoresRegistradosTests(SimpleTestCase):
    """Os apps registram os seus tipos no `ready()` do AppConfig."""

    def test_os_seis_tipos_regeraveis_estao_registrados(self):
        esperados = {
            DocumentoTipo.OFICIO.value,
            DocumentoTipo.JUSTIFICATIVA.value,
            DocumentoTipo.ORDEM_SERVICO.value,
            DocumentoTipo.PLANO_TRABALHO.value,
            DocumentoTipo.RELATORIO_TECNICO.value,
            DocumentoTipo.DIARIO_BORDO.value,
        }
        self.assertTrue(esperados.issubset(set(regeneracao._REGERADORES)))
