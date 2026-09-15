from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from decimal import Decimal
from .test_helpers import PrestacaoTestCase as TestCase
from django.test import override_settings
from django.core.files.uploadedfile import SimpleUploadedFile
from django.contrib.auth import get_user_model
from django.urls import reverse
from pypdf import PdfReader, PdfWriter
from .test_helpers import PrestacaoFixturesMixin, pdf_minimo
from .test_carimbo import pdf_do_oficio
from .models import PrestacaoServidor, PrestacaoDocumentoAnexo as Anexo
from .services import gerar_prestacao_consolidado_pdf, _diaria_por_servidor
from .anexo_services import substituir_anexo_assinado
from .carimbo_services import posicoes_automaticas
from .diario_services import garantir_roteiro_ajustado, obter_ou_criar_diario, sincronizar_trechos


class GatesF5aTests(PrestacaoFixturesMixin, TestCase):
    def setUp(self):
        self.setUpPrestacaoFixtures()
        self.fixture = self.criar_prestacao(numero=911)
        self.pc = self.fixture.prestacao
        self.ps = self.fixture.prestacoes_servidor[0]

    def test_remocao_e_retorno_preservam_numero_e_identidade_da_linha(self):
        self.ps.numero_solicitacao = "SOL-F5"
        self.ps.save()
        self.fixture.oficio.servidores.remove(self.ps.servidor)
        self.assertFalse(PrestacaoServidor.objects.filter(pk=self.ps.pk).exists())
        self.assertEqual(PrestacaoServidor.todos.get(pk=self.ps.pk).numero_solicitacao, "SOL-F5")
        self.fixture.oficio.servidores.add(self.ps.servidor)
        self.assertEqual(PrestacaoServidor.objects.get(pk=self.ps.pk).numero_solicitacao, "SOL-F5")

    def test_total_de_diarias_da_f2_e_convertido_para_valor_individual(self):
        roteiro = self.fixture.roteiro
        roteiro.quantidade_servidores = 4
        roteiro.valor_diarias = Decimal("3200.00")
        self.assertEqual(_diaria_por_servidor(roteiro), Decimal("800.00"))

    def test_copia_do_roteiro_preserva_km_sem_modificar_original(self):
        diario = obter_ou_criar_diario(self.pc)
        linha = sincronizar_trechos(diario)[0]
        linha.km_inicial=120; linha.km_final=210; linha.save()
        original_id = linha.trecho_id
        copia = garantir_roteiro_ajustado(self.pc)
        self.assertNotEqual(copia.pk, self.fixture.roteiro.pk)
        nova = sincronizar_trechos(diario)[0]
        self.assertEqual(nova.pk, linha.pk)
        self.assertNotEqual(nova.trecho_id, original_id)
        self.assertEqual((nova.km_inicial,nova.km_final), (120,210))
        self.fixture.oficio.refresh_from_db()
        self.assertEqual(self.fixture.oficio.roteiro_id, self.fixture.roteiro.pk)

    def test_consolidado_preserva_ordem_e_total_de_paginas(self):
        self.ps.numero_solicitacao="SOL-F5"; self.ps.save()
        specs = [(Anexo.TIPO_OFICIO_ASSINADO,"OFICIO",False), (Anexo.TIPO_DESPACHO,"DESPACHO",False), (Anexo.TIPO_RT_ASSINADO,"RELATORIO",True), (Anexo.TIPO_DB_ASSINADO,"DIARIO",False), (Anexo.TIPO_COMPROVANTE,"COMPROVANTE",True)]
        with TemporaryDirectory() as pasta, override_settings(MEDIA_ROOT=pasta):
            for tipo,texto,individual in specs:
                Anexo.objects.create(prestacao=self.pc,servidor_prestacao=self.ps if individual else None,tipo=tipo,arquivo=SimpleUploadedFile(texto+".pdf",pdf_minimo(texto)))
            pdf = PdfReader(BytesIO(gerar_prestacao_consolidado_pdf(self.ps)))
            self.assertEqual(len(pdf.pages),5)
            self.assertEqual([p.extract_text().strip() for p in pdf.pages],[s[1] for s in specs])

    def test_ancora_encontra_servidor_com_pagina_de_protocolo_antes(self):
        self.ps.numero_solicitacao="SOL-F5"; self.ps.save()
        nome = self.ps.servidor.nome
        referencia = pdf_do_oficio([(nome,"SOL-F5")])
        corpo = pdf_do_oficio([(nome,"")],deslocamento=30,com_numero=False)
        writer = PdfWriter()
        writer.append(BytesIO(pdf_minimo("PROTOCOLO")))
        writer.append(BytesIO(corpo))
        out=BytesIO(); writer.write(out)
        with patch("viagens_prestacoes.services.gerar_oficio_prestacao_pdf",return_value=referencia):
            posicao=posicoes_automaticas(self.pc,out.getvalue())[self.ps.pk]
        self.assertEqual(posicao.pagina,1)
        self.assertAlmostEqual((1-posicao.y)*842,670,places=1)

    def test_falha_depois_do_upload_nao_deixa_arquivo_novo(self):
        with TemporaryDirectory() as pasta, override_settings(MEDIA_ROOT=pasta):
            with patch("viagens_prestacoes.anexo_services.marcar_servidores_pendentes",side_effect=RuntimeError("falha de gravação")):
                with self.assertRaises(RuntimeError):
                    substituir_anexo_assinado(self.pc,tipo=Anexo.TIPO_DESPACHO,arquivo=SimpleUploadedFile("despacho.pdf",pdf_minimo()),nome_original="despacho.pdf")
            self.assertFalse(self.pc.documentos_anexos.exists())
            self.assertEqual([p for p in Path(pasta).rglob("*") if p.is_file()],[])

    def test_usuario_sem_modulo_recebe_403_nas_etapas(self):
        usuario=get_user_model().objects.create_user(username="sem_modulo_f5")
        self.client.force_login(usuario)
        for rota,args in [("index",[]),("modelos_index",[]),("diario_servidor",[self.ps.pk]),("rt_servidor",[self.ps.pk]),("documentos_servidor",[self.ps.pk]),("consolidado_download",[self.ps.pk]),("prestacao_downloads",[self.ps.pk])]:
            with self.subTest(rota=rota):
                self.assertEqual(self.client.get(reverse("viagens_prestacoes:"+rota,args=args)).status_code,403)

    def test_rollback_da_facade_remove_artefato_e_arquivo(self):
        from .arquivos import transacao_de_arquivos
        from documentos.services.facade import DocumentoFacade
        from documentos.services.types import DocumentoTipo, DocumentoFormato
        from documentos.models import DocumentoArtefato
        with TemporaryDirectory() as pasta, override_settings(MEDIA_ROOT=pasta, DOCUMENTOS_PERSIST_ARTEFATOS=True):
            with self.assertRaises(RuntimeError):
                with transacao_de_arquivos():
                    DocumentoFacade().gerar(tipo=DocumentoTipo.RELATORIO_TECNICO, formato=DocumentoFormato.DOCX, payload={"oficio": "TESTE", "nome_servidor": "TESTE"}, prestacao_id=self.pc.pk)
                    raise RuntimeError("falha depois da geração")
            self.assertFalse(DocumentoArtefato.objects.filter(prestacao=self.pc).exists())
            self.assertEqual([p for p in Path(pasta).rglob("*") if p.is_file()], [])

    def test_relacao_reversa_remove_e_restaura_com_dados(self):
        self.ps.numero_solicitacao = "SOL-F5"; self.ps.save()
        servidor = self.ps.servidor
        relacao = self.fixture.oficio._meta.get_field("servidores").remote_field.get_accessor_name()
        equipe = getattr(servidor, relacao)
        equipe.clear()
        self.assertFalse(PrestacaoServidor.objects.filter(pk=self.ps.pk).exists())
        equipe.add(self.fixture.oficio)
        self.assertEqual(PrestacaoServidor.objects.get(pk=self.ps.pk).numero_solicitacao,"SOL-F5")

    def test_abastecimento_padrao_aparece_selecionado(self):
        response = self.client.get(reverse("viagens_prestacoes:diario_servidor", args=[self.ps.pk]))
        self.assertContains(response, 'value="sim" selected')

    def test_fragmentacao_do_word_nao_desloca_numero_para_coluna_do_nome(self):
        from reportlab.pdfgen import canvas
        self.ps.numero_solicitacao="SOL-F5-001"; self.ps.save()
        def documento(com_numero):
            buf=BytesIO(); c=canvas.Canvas(buf,pagesize=(595,842))
            c.drawString(50,700,self.ps.servidor.nome)
            if com_numero:
                for x,parte in [(400,"SOL"),(425,"-"),(435,"F5"),(455,"-"),(465,"001")]:c.drawString(x,700,parte)
            c.save();return buf.getvalue()
        with patch("viagens_prestacoes.services.gerar_oficio_prestacao_pdf",return_value=documento(True)):
            posicao=posicoes_automaticas(self.pc,documento(False))[self.ps.pk]
        self.assertAlmostEqual(posicao.x*595,400)
