"""Importar o processo de pagamento do eProtocolo no Coffee Break.

Os processos são sintéticos (`core.leitura.tests.fabrica`), com a estrutura
dos dois processos reais de pagamento: capa, ofício 123/2026 com "PCPR
Protocolo n.º", notas com a folha de assinatura, certificos, cinco
certidões, aditivo e contrato aninhados, despacho ao GAF, empenho e
liquidação.
"""

import datetime as dt
import functools
import shutil
import tempfile
from pathlib import Path
from unittest import mock

from django.core.files.base import ContentFile
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from django.urls import reverse

from core.leitura.tests import fabrica

from . import importacao_processo as importacao
from . import importacao_views
from . import services
from .models import CertidaoFornecedor
from .models import HistoricoCoffeeBreak
from .models import SolicitacaoCoffeeBreak
from .models import TipoCertidao
from .tests import BaseCoffeeBreakTestCase
from .tests import _pdf_em_branco

URL = reverse("coffee_break:importar_processo")


@functools.lru_cache(maxsize=None)
def processo_conjunto() -> bytes:
    """O 26.613.666-8: ofício 123/2026, notas 8952 (R$ 1.600) e 8954 (R$ 800), PCPR 2026.050731.000."""
    return fabrica.processo_coffee_break()


@functools.lru_cache(maxsize=None)
def processo_unico() -> bytes:
    """O 26.617.058-0: ofício 124/2026, nota 8957 (R$ 800), PCPR 2026.050880.000."""
    return fabrica.processo_coffee_break(
        numero=124, protocolo="26.617.058-0", notas=((8957, "800,00"),), pcpr="2026.050880.000"
    )


def arquivo(dados, nome="Processo_26.613.666-8_1.pdf"):
    return SimpleUploadedFile(nome, dados, content_type="application/pdf")


class ImportacaoBase(BaseCoffeeBreakTestCase):
    def setUp(self):
        self.media = tempfile.mkdtemp(prefix="coffee-importacao-")
        self.addCleanup(shutil.rmtree, self.media, ignore_errors=True)
        config = override_settings(MEDIA_ROOT=self.media)
        config.enable()
        self.addCleanup(config.disable)
        # A pasta das conferências pendentes também fica isolada.
        self.pendentes = Path(tempfile.mkdtemp(prefix="coffee-processos-"))
        self.addCleanup(shutil.rmtree, self.pendentes, ignore_errors=True)
        pasta = mock.patch.object(importacao_views, "_pasta", return_value=self.pendentes)
        pasta.start()
        self.addCleanup(pasta.stop)
        self.client.force_login(self.ascom)

    def enviar(self, dados, **extra):
        return self.client.post(URL, {"arquivo": arquivo(dados), **extra})

    def conjunto(self, **kwargs):
        """As OS 41 e 42/2026 em pagamento conjunto, com as notas 8952 e 8954 já digitadas (sem o PDF)."""
        a = self.criar_solicitacao(numero="41/2026", numero_nota_fiscal="8952", quantidade=80, **kwargs)
        b = self.criar_solicitacao(numero="42/2026", numero_nota_fiscal="8954", quantidade=40, pagamento_com=a)
        return a, b


class ImportarProcessoConjuntoTests(ImportacaoBase):
    def test_pagamento_conjunto_aplica_sozinho_pelas_notas_e_pelo_oficio(self):
        a, b = self.conjunto(numero_oficio="123/2026")
        resposta = self.enviar(processo_conjunto())
        self.assertEqual(resposta.status_code, 302)
        self.assertIn("/importar-processo/", resposta.url)
        a.refresh_from_db()
        b.refresh_from_db()
        for s, nota in ((a, "8952"), (b, "8954")):
            self.assertEqual(s.protocolo_pagamento, "26.613.666-8")
            self.assertEqual(s.data_atesto_gaf, dt.date(2026, 9, 21))
            self.assertTrue(s.arquivo_nota_fiscal)
            self.assertIn(f"NF{nota}", s.arquivo_nota_fiscal.name)
            # Só a página da nota: sem a folha de assinatura do eProtocolo.
            from pypdf import PdfReader

            with s.arquivo_nota_fiscal.open("rb") as pdf:
                paginas = PdfReader(pdf).pages
                self.assertEqual(len(paginas), 1)
                self.assertIn(nota, paginas[0].extract_text().replace(".", ""))
            historico = s.historico.order_by("-pk").first()
            self.assertIn("Processo de pagamento 26.613.666-8 importado", historico.descricao)
            self.assertIn("ref. ", historico.descricao)

        tela = self.client.get(resposta.url)
        self.assertContains(tela, "O que foi feito")
        self.assertContains(tela, "Solicitação 41/2026")
        self.assertContains(tela, "Solicitação 42/2026")
        self.assertContains(tela, "Nota fiscal")
        self.assertContains(tela, "Despacho ao GAF em 21/09/2026")

    def test_notas_numeradas_sem_oficio_bastam_e_certidoes_entram(self):
        a, b = self.conjunto()
        self.enviar(processo_conjunto())
        a.refresh_from_db()
        self.assertEqual(a.protocolo_pagamento, "26.613.666-8")
        # As cinco certidões do processo, conferidas pelo leitor de certidões.
        certidoes = CertidaoFornecedor.objects.filter(fornecedor=self.fornecedor)
        self.assertEqual(
            sorted(certidoes.values_list("tipo", flat=True)),
            sorted(TipoCertidao.values),
        )
        self.assertEqual({c.validade for c in certidoes}, {dt.date(2027, 2, 15)})

    def test_certidao_cadastrada_mais_nova_fica(self):
        self.conjunto()
        CertidaoFornecedor.objects.create(
            fornecedor=self.fornecedor, tipo=TipoCertidao.FGTS, validade=dt.date(2099, 1, 1),
            arquivo=ContentFile(_pdf_em_branco(), name="fgts.pdf"),
        )
        self.enviar(processo_conjunto())
        fgts = CertidaoFornecedor.objects.filter(fornecedor=self.fornecedor, tipo=TipoCertidao.FGTS)
        self.assertEqual(list(fgts.values_list("validade", flat=True)), [dt.date(2099, 1, 1)])
        self.assertEqual(CertidaoFornecedor.objects.filter(fornecedor=self.fornecedor).count(), 5)

    def test_nota_ja_anexada_nao_e_trocada(self):
        a, b = self.conjunto(numero_oficio="123/2026")
        a.arquivo_nota_fiscal.save("minha-nota.pdf", ContentFile(_pdf_em_branco(2)), save=True)
        self.enviar(processo_conjunto())
        a.refresh_from_db()
        b.refresh_from_db()
        self.assertIn("minha-nota", a.arquivo_nota_fiscal.name)
        self.assertEqual(a.protocolo_pagamento, "26.613.666-8")
        self.assertTrue(b.arquivo_nota_fiscal)

    def test_mesmo_arquivo_de_novo_pede_conferencia(self):
        a, _b = self.conjunto(numero_oficio="123/2026")
        self.enviar(processo_conjunto())
        historico_antes = HistoricoCoffeeBreak.objects.count()
        resposta = self.enviar(processo_conjunto())
        self.assertEqual(HistoricoCoffeeBreak.objects.count(), historico_antes)
        tela = self.client.get(resposta.url)
        self.assertContains(tela, "Este mesmo arquivo já foi importado")
        self.assertContains(tela, "Aguardando conferência")
        # Aplicar de novo não duplica: só completa o que faltar (nada).
        token = resposta.url.rstrip("/").rsplit("/", 1)[-1]
        self.client.post(
            reverse("coffee_break:aplicar_importacao_processo", args=[token]), {"solicitacoes": [str(a.pk)]}
        )
        self.assertEqual(HistoricoCoffeeBreak.objects.count(), historico_antes)
        self.assertEqual(SolicitacaoCoffeeBreak.objects.get(pk=a.pk).protocolo_pagamento, "26.613.666-8")


class ImportarProcessoUnicoTests(ImportacaoBase):
    def test_oficio_identifica_e_a_nota_e_a_unica_sem_numero(self):
        s = self.criar_solicitacao(numero="41/2026", numero_oficio="124/2026", quantidade=40)
        self.enviar(processo_unico(), next=reverse("coffee_break:etapa_protocolo", args=[s.pk]))
        s.refresh_from_db()
        self.assertEqual(s.numero_nota_fiscal, "8957")
        self.assertEqual(s.protocolo_pagamento, "26.617.058-0")
        self.assertEqual(s.data_atesto_gaf, dt.date(2026, 9, 21))
        self.assertTrue(s.arquivo_nota_fiscal)

    def test_protocolo_do_oficio_gravado_com_mascara_identifica(self):
        s = self.criar_solicitacao(numero="41/2026", protocolo_pcpr_oficio="26.617.058-0")
        self.enviar(processo_unico())
        s.refresh_from_db()
        self.assertEqual((s.numero_nota_fiscal, s.protocolo_pagamento), ("8957", "26.617.058-0"))

    def test_pcpr_do_oficio_identifica(self):
        s = self.criar_solicitacao(numero="41/2026", protocolo_pcpr_oficio="2026.050880.000")
        self.enviar(processo_unico())
        s.refresh_from_db()
        self.assertEqual(s.protocolo_pagamento, "26.617.058-0")

    def test_protocolo_copiado_do_pcpr_vira_o_do_processo_e_nao_volta(self):
        s = self.criar_solicitacao(
            numero="41/2026", numero_nota_fiscal="8957",
            protocolo_pcpr_oficio="2026.050880.000", protocolo_pagamento="2026.050880.000",
        )
        self.enviar(processo_unico())
        s.refresh_from_db()
        self.assertEqual(s.protocolo_pagamento, "26.617.058-0")
        self.assertIn("trocado de 2026.050880.000", s.historico.order_by("-pk").first().descricao)
        # Salvar a etapa 2 de novo não põe o PCPR de volta no lugar do protocolo do processo.
        self.assertFalse(services.sincronizar_protocolo(s))
        s.refresh_from_db()
        self.assertEqual(s.protocolo_pagamento, "26.617.058-0")

    def test_protocolo_de_outro_processo_pede_conferencia_e_nao_e_trocado(self):
        s = self.criar_solicitacao(
            numero="41/2026", numero_nota_fiscal="8957", numero_oficio="124/2026", protocolo_pagamento="11.111.111-1",
        )
        resposta = self.enviar(processo_unico())
        s.refresh_from_db()
        self.assertFalse(s.arquivo_nota_fiscal)  # conferência: nada gravado ainda
        tela = self.client.get(resposta.url)
        self.assertContains(tela, "já tem o protocolo de pagamento 11.111.111-1, de outro processo")
        self.assertNotContains(tela, "checked")  # a contradita vem desmarcada
        token = resposta.url.rstrip("/").rsplit("/", 1)[-1]
        resultado = self.client.post(
            reverse("coffee_break:aplicar_importacao_processo", args=[token]), {"solicitacoes": [str(s.pk)]}
        )
        s.refresh_from_db()
        self.assertEqual(s.protocolo_pagamento, "11.111.111-1")
        self.assertIsNone(s.data_atesto_gaf)
        self.assertTrue(s.arquivo_nota_fiscal)  # a nota que faltava entra
        self.assertContains(self.client.get(resultado.url), "diferente do processo")

    def test_nota_so_citada_identifica_com_conferencia(self):
        # A liquidação cita as notas 8952 e 8954, mas o PDF delas não está no processo.
        s = self.criar_solicitacao(numero="41/2026", numero_nota_fiscal="8952")
        plano = importacao.analisar(processo_unico(), "Processo_26.617.058-0_1.pdf")
        self.assertEqual([x.pk for x in plano.solicitacoes], [s.pk])
        self.assertFalse(plano.seguro)
        self.assertTrue(any("citado no processo" in c for c in plano.conferir))

    def test_nota_de_numero_diferente_nao_e_trocada(self):
        s = self.criar_solicitacao(numero="41/2026", numero_nota_fiscal="9999", numero_oficio="124/2026")
        resposta = self.enviar(processo_unico())
        s.refresh_from_db()
        self.assertEqual(s.numero_nota_fiscal, "9999")
        self.assertFalse(s.arquivo_nota_fiscal)
        # A nota 8957 não tem destino: vai para a conferência, nada gravado.
        self.assertEqual(s.protocolo_pagamento, "")
        self.assertContains(self.client.get(resposta.url), "Aguardando conferência")

    def test_nota_de_outro_fornecedor_nao_identifica(self):
        from .models import ContratoCoffeeBreak, Fornecedor, LoteCoffeeBreak

        outro = Fornecedor.objects.create(razao_social="OUTRA PADARIA LTDA", cnpj="11222333000181")
        contrato = ContratoCoffeeBreak.objects.create(fornecedor=outro, numero="0001/2025")
        lote = LoteCoffeeBreak.objects.create(contrato=contrato, numero=2, exercicio="2026", quantidade_total=100)
        s = self.criar_solicitacao(numero="41/2026", numero_nota_fiscal="8957", lote=lote)
        resposta = self.enviar(processo_unico())
        s.refresh_from_db()
        self.assertEqual(s.protocolo_pagamento, "")
        self.assertContains(self.client.get(resposta.url), "Nenhuma solicitação combina")

    def test_cancelada_nao_e_identificada(self):
        s = self.criar_solicitacao(numero="41/2026", numero_oficio="124/2026", cancelada=True)
        self.enviar(processo_unico())
        s.refresh_from_db()
        self.assertEqual((s.numero_nota_fiscal, s.protocolo_pagamento), ("", ""))


class ConferenciaTests(ImportacaoBase):
    def test_sem_identificacao_abre_conferencia_e_aplica_a_escolha(self):
        s = self.criar_solicitacao(numero="41/2026", quantidade=40)
        resposta = self.enviar(processo_unico())
        s.refresh_from_db()
        self.assertEqual(s.protocolo_pagamento, "")
        self.assertEqual(len(list(self.pendentes.glob("*.pdf"))), 1)
        tela = self.client.get(resposta.url)
        self.assertContains(tela, "De quem é o processo")
        self.assertContains(tela, "Solicitação 41/2026")  # candidata: do fornecedor do processo, sem protocolo
        self.assertContains(tela, 'name="nota-3"')
        token = resposta.url.rstrip("/").rsplit("/", 1)[-1]
        aplicar = self.client.post(
            reverse("coffee_break:aplicar_importacao_processo", args=[token]),
            {"solicitacoes": [str(s.pk)], "nota-3": str(s.pk)},
        )
        self.assertEqual(aplicar.status_code, 302)
        s.refresh_from_db()
        self.assertEqual((s.numero_nota_fiscal, s.protocolo_pagamento), ("8957", "26.617.058-0"))
        self.assertTrue(s.arquivo_nota_fiscal)
        self.assertEqual(list(self.pendentes.glob("*.pdf")), [])
        self.assertContains(self.client.get(aplicar.url), "O que foi feito")

    def test_aplicar_sem_marcar_nada_nao_grava(self):
        self.criar_solicitacao(numero="41/2026")
        resposta = self.enviar(processo_unico())
        token = resposta.url.rstrip("/").rsplit("/", 1)[-1]
        aplicar = self.client.post(reverse("coffee_break:aplicar_importacao_processo", args=[token]), {})
        self.assertEqual(aplicar.url, resposta.url)
        self.assertFalse(SolicitacaoCoffeeBreak.objects.exclude(protocolo_pagamento="").exists())

    def test_outra_solicitacao_pelo_numero_da_os(self):
        s = self.criar_solicitacao(numero="41/2026")
        resposta = self.enviar(processo_unico())
        token = resposta.url.rstrip("/").rsplit("/", 1)[-1]
        self.client.post(reverse("coffee_break:aplicar_importacao_processo", args=[token]), {"outras": "41/2026"})
        s.refresh_from_db()
        self.assertEqual(s.protocolo_pagamento, "26.617.058-0")

    def test_descartar_apaga_o_arquivo_e_nao_grava(self):
        self.criar_solicitacao(numero="41/2026")
        resposta = self.enviar(processo_unico())
        token = resposta.url.rstrip("/").rsplit("/", 1)[-1]
        self.client.post(reverse("coffee_break:descartar_importacao_processo", args=[token]))
        self.assertEqual(list(self.pendentes.glob("*.pdf")), [])
        self.assertEqual(self.client.get(resposta.url).status_code, 302)

    def test_ancora_de_outro_pagamento_pede_conferencia(self):
        certa = self.criar_solicitacao(numero="41/2026", numero_oficio="124/2026")
        errada = self.criar_solicitacao(numero="50/2026")
        resposta = self.enviar(processo_unico(), solicitacao=str(errada.pk))
        certa.refresh_from_db()
        errada.refresh_from_db()
        self.assertEqual((certa.protocolo_pagamento, errada.protocolo_pagamento), ("", ""))
        self.assertContains(self.client.get(resposta.url), "O processo parece ser de Solicitação 41/2026")

    def test_ancora_sem_outros_sinais_aplica_na_propria(self):
        s = self.criar_solicitacao(numero="50/2026")
        self.enviar(processo_unico(), solicitacao=str(s.pk))
        s.refresh_from_db()
        self.assertEqual((s.numero_nota_fiscal, s.protocolo_pagamento), ("8957", "26.617.058-0"))


class EntradaTests(ImportacaoBase):
    def test_pdf_que_nao_e_processo(self):
        # Nem com o nome de um processo: o número só no nome do arquivo não basta.
        resposta = self.enviar(fabrica.pagina(["Um PDF qualquer, sem ofício nem nota."]))
        self.assertRedirects(resposta, reverse("coffee_break:solicitacoes"), fetch_redirect_response=False)
        mensagens = [str(m) for m in resposta.wsgi_request._messages]
        self.assertTrue(any("não parece um processo de pagamento" in m for m in mensagens))

    def test_nao_pdf_e_recusado(self):
        resposta = self.client.post(URL, {"arquivo": SimpleUploadedFile("processo.txt", b"texto")})
        self.assertEqual(resposta.status_code, 302)
        self.assertFalse(list(self.pendentes.glob("*")))

    @override_settings(IMPORTACAO_MAX_BYTES=1000)
    def test_limite_de_tamanho(self):
        resposta = self.enviar(processo_unico())
        mensagens = [str(m) for m in resposta.wsgi_request._messages]
        self.assertTrue(any("limite de 0 MB" in m or "passa do limite" in m for m in mensagens))

    def test_sem_modulo_nao_importa(self):
        self.client.force_login(self.sem_modulo)
        self.assertEqual(self.enviar(processo_unico()).status_code, 403)

    def test_lista_etapa3_e_menu_tem_a_importacao(self):
        s = self.criar_solicitacao(numero="41/2026")
        lista = self.client.get(reverse("coffee_break:solicitacoes"))
        self.assertContains(lista, "Importar processo de pagamento")
        self.assertContains(lista, "data-cb-importar-soltar")
        self.assertContains(lista, f'data-solicitacao="{s.pk}"')  # ⋮ da linha
        self.assertContains(lista, "coffee-break-importar.js")
        etapa = self.client.get(reverse("coffee_break:etapa_protocolo", args=[s.pk]))
        self.assertContains(etapa, "Já protocolou? Importe o processo de pagamento")
        self.assertContains(etapa, "data-cb-importar-dialogo")

    def test_aplicacao_e_atomica_com_os_arquivos(self):
        a, b = self.conjunto(numero_oficio="123/2026")
        plano = importacao.analisar(processo_conjunto(), "Processo_26.613.666-8_1.pdf")
        self.assertTrue(plano.seguro)
        with mock.patch.object(importacao.certidoes, "registrar", side_effect=RuntimeError("disco cheio")):
            with self.assertRaises(RuntimeError):
                importacao.aplicar(plano, processo_conjunto(), self.ascom)
        a.refresh_from_db()
        self.assertEqual((a.protocolo_pagamento, bool(a.arquivo_nota_fiscal)), ("", False))
        notas = list(Path(self.media).rglob("NF*.pdf"))
        self.assertEqual(notas, [])


class AnaliseTests(ImportacaoBase):
    def test_o_que_a_leitura_acha(self):
        plano = importacao.analisar(processo_conjunto(), "Processo_26.613.666-8_1.pdf")
        self.assertEqual(plano.protocolo, "266136668")
        self.assertEqual(plano.oficio, (123, 2026))
        self.assertEqual(plano.pcpr, "2026.050731.000")
        self.assertEqual(plano.despacho_gaf, dt.date(2026, 9, 21))
        self.assertEqual([n.numero for n in plano.notas], ["8952", "8954"])
        self.assertEqual({c.tipo for c in plano.certidoes}, set(TipoCertidao.values))
        self.assertTrue(any("2026NE108096" in lido for lido in plano.lidos))
        tipos = [d["tipo"] for d in plano.documentos]
        self.assertEqual(tipos[:3], ["capa", "oficio", "nota_fiscal"])
        self.assertFalse(plano.solicitacoes)
        self.assertTrue(plano.conferir)

    def test_nota_pelo_valor_quando_as_duas_estao_sem_numero(self):
        self.contrato.valor_unitario = 20
        self.contrato.save()
        a = self.criar_solicitacao(numero="41/2026", numero_oficio="123/2026", quantidade=40)  # R$ 800
        b = self.criar_solicitacao(numero="42/2026", quantidade=80, pagamento_com=a)  # R$ 1.600
        plano = importacao.analisar(processo_conjunto(), "Processo_26.613.666-8_1.pdf")
        destinos = {n.numero: n.solicitacao_id for n in plano.notas}
        self.assertEqual(destinos, {"8952": b.pk, "8954": a.pk})
        self.assertTrue(plano.seguro)

    def test_duas_sem_numero_e_sem_valor_pedem_conferencia(self):
        a = self.criar_solicitacao(numero="41/2026", numero_oficio="123/2026")
        self.criar_solicitacao(numero="42/2026", pagamento_com=a)
        plano = importacao.analisar(processo_conjunto(), "Processo_26.613.666-8_1.pdf")
        self.assertFalse(plano.seguro)
        self.assertTrue(any("não tem solicitação neste pagamento" in c for c in plano.conferir))

    def test_tela_so_leva_texto(self):
        import json

        self.conjunto(numero_oficio="123/2026")
        plano = importacao.analisar(processo_conjunto(), "Processo_26.613.666-8_1.pdf")
        json.dumps(plano.para_tela())  # vai para a sessão
