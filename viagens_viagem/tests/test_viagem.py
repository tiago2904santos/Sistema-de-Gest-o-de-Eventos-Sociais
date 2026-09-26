"""A lista, o painel de cinco etapas e os documentos que nascem da viagem."""
import io
from datetime import date, datetime, timedelta

from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from django.utils import timezone

from viagens_oficios.models import Oficio
from viagens_roteiros.models import Roteiro, RoteiroDestino
from viagens_termos.models import TermoAutorizacao
from viagens_viagem.models import Viagem, ViagemDocumentoSolicitacao

from .fixtures import CenarioViagem


class ListaTests(CenarioViagem):
    def test_lista_com_abas_busca_e_selos(self):
        futura = self.viagem(data_inicio=timezone.localdate() + timedelta(days=10), data_fim=timezone.localdate() + timedelta(days=11))
        passada = self.viagem(titulo="Operação antiga", data_inicio=date(2025, 1, 1), data_fim=date(2025, 1, 2))
        cancelada = self.viagem(titulo="Cancelada")
        cancelada.cancelar("Adiada")
        r = self.client.get(reverse("viagens_viagem:lista"))
        self.assertContains(r, "PCPR na Comunidade · Londrina/PR")
        self.assertContains(r, "Nova viagem")
        self.assertContains(r, "Contas prestadas")
        self.assertContains(r, "Que vão acontecer")
        self.assertContains(r, 'class="st st--pendente">Rascunho')
        self.assertContains(r, 'class="st st--cancelada">Cancelado')
        self.assertContains(r, reverse("viagens_viagem:etapa", args=[futura.pk, 1]))
        self.assertContains(r, reverse("viagens_viagem:etapa", args=[futura.pk, 3]))
        self.assertEqual(r.context["situacoes"][0]["total"], 3)
        self.assertEqual(self.client.get(reverse("viagens_viagem:lista"), {"situacao": "futuras"}).context["pagina"].paginator.count, 1)
        self.assertEqual(self.client.get(reverse("viagens_viagem:lista"), {"situacao": "atuais"}).context["pagina"].paginator.count, 1)
        self.assertEqual(self.client.get(reverse("viagens_viagem:lista"), {"situacao": "cancelados"}).context["pagina"].paginator.count, 1)
        r = self.client.get(reverse("viagens_viagem:lista"), {"q": "antiga"})
        self.assertEqual([l["viagem"].pk for l in r.context["linhas"]], [passada.pk])
        r = self.client.get(reverse("viagens_viagem:lista"), {"q": "Londrina"})
        self.assertEqual(r.context["pagina"].paginator.count, 3)

    def test_busca_por_servidor_placa_oficio_e_protocolo(self):
        """m079: acha a viagem pelo dado que se tem em mãos."""
        alvo = self.viagem(titulo="Justiça no Bairro")
        self.viagem(titulo="Outra viagem")
        oficio = Oficio.objects.create(viagem=alvo, numero=15, ano=2026, protocolo="123456789",
                                       viatura=self.viatura, motorista=self.b)
        oficio.servidores.set([self.a])

        def achadas(termo):
            r = self.client.get(reverse("viagens_viagem:lista"), {"q": termo})
            return [l["viagem"].pk for l in r.context["linhas"]]

        for termo in ("ANA VIAGEM", "bruno", "abc-1d23", "15/2026", "12.345.678-9"):
            with self.subTest(termo=termo):
                self.assertEqual(achadas(termo), [alvo.pk])
        self.assertEqual(achadas("16/2026"), [])

    def test_selo_quando_pela_saida_do_roteiro(self):
        v = self.viagem()
        saida = timezone.make_aware(datetime.combine(timezone.localdate() + timedelta(days=3), datetime.min.time().replace(hour=8)))
        Roteiro.objects.create(origem_municipio=self.sede, saida_dt=saida, retorno_chegada_dt=saida + timedelta(hours=10), viagem=v)
        r = self.client.get(reverse("viagens_viagem:lista"))
        self.assertContains(r, "faltam 3 dias")


class CriarEPainelTests(CenarioViagem):
    def test_criar_abre_a_etapa_1_e_get_volta_a_lista(self):
        self.assertRedirects(self.client.get(reverse("viagens_viagem:criar")), reverse("viagens_viagem:lista"))
        r = self.client.post(reverse("viagens_viagem:criar"))
        v = Viagem.objects.latest("pk")
        self.assertRedirects(r, self.etapa(v, 1))
        self.assertRedirects(self.client.get(reverse("viagens_viagem:painel", args=[v.pk])), self.etapa(v, 1))

    def test_nova_viagem_reaproveita_a_vazia_abandonada(self):
        from datetime import timedelta

        from django.utils import timezone

        self.client.post(reverse("viagens_viagem:criar"))
        vazia = Viagem.objects.get()
        # Recém-aberta: pode estar sendo preenchida por alguém, então não se reaproveita.
        self.client.post(reverse("viagens_viagem:criar"))
        self.assertEqual(Viagem.objects.count(), 2)
        Viagem.objects.update(atualizado_em=timezone.now() - timedelta(hours=1))
        r = self.client.post(reverse("viagens_viagem:criar"))
        self.assertRedirects(r, self.etapa(vazia, 1))
        self.assertEqual(Viagem.objects.count(), 2)
        # Com conteúdo, a viagem é de alguém e não volta.
        Viagem.objects.update(titulo="Expo")
        self.client.post(reverse("viagens_viagem:criar"))
        self.assertEqual(Viagem.objects.count(), 3)

    def test_etapa_1_busca_municipios_em_vez_de_embutir(self):
        """m075: só o destino escolhido vem na página; o resto, pela busca."""
        v = self.viagem()
        corpo = self.client.get(self.etapa(v, 1)).content.decode()
        self.assertIn('data-remote-url="%s"' % reverse("cadastros:municipios_buscar"), corpo)
        self.assertIn(">Londrina<", corpo)
        self.assertNotIn(">Maringá<", corpo)

    def test_etapa_1_traz_os_blocos_da_origem_sem_avisos(self):
        v = Viagem.objects.create()
        r = self.client.get(self.etapa(v, 1))
        html = r.content.decode()
        for texto in ["Nova viagem", "Dados da viagem", "Identificação", "Tipo da viagem", "Gerenciar tipos", "Modelo de motivo",
                      "Gerenciar modelos", "Contextualize a atividade…", "Período e destinos", "Período da viagem",
                      "Destinos", "Documentos vinculados", "Ofícios", "Roteiros", "Plano de Trabalho", "Ordem de Serviço", "Termos",
                      "Nenhum ofício disponível para o período.", "Voltar à lista", "Salvar e avançar"]:
            self.assertIn(texto, html)
        self.assertNotIn("aviso--erro", html)
        # A ordem dos blocos é a da origem.
        self.assertLess(html.index("Identificação"), html.index("Motivo</strong>"))
        self.assertLess(html.index("Motivo</strong>"), html.index("Período e destinos"))
        self.assertLess(html.index("Período e destinos"), html.index("Documentos vinculados"))
        # A UF nasce com a da sede das Configurações.
        self.assertEqual(r.context["valores"]["destino_estado"], str(self.pr.pk))

    def test_etapa_fora_de_1_a_5_vira_1_ou_5(self):
        v = self.viagem()
        self.assertEqual(self.client.get(self.etapa(v, 9)).context["etapa_atual"], 5)
        self.assertEqual(self.client.get(self.etapa(v, 0)).context["etapa_atual"], 1)

    def test_salvar_etapa_1_deriva_o_titulo_grava_destinos_vinculos_e_termo(self):
        v = Viagem.objects.create()
        solto = Oficio.objects.create(motivo="Solto")
        r = self.client.post(self.etapa(v, 1), self.payload_etapa1(oficios_vinculados=[str(solto.pk)]))
        self.assertRedirects(r, self.etapa(v, 2))
        v.refresh_from_db()
        solto.refresh_from_db()
        self.assertEqual(v.titulo, "PCPR na Comunidade")
        self.assertEqual(v.motivo, "Atividade comunitária")
        self.assertEqual((v.data_inicio, v.data_fim), (date(2026, 10, 5), date(2026, 10, 7)))
        self.assertEqual((v.destino_estado, v.destino_municipio), (self.pr, self.londrina))
        self.assertEqual(v.destinos_extras, [{"estado": self.pr.pk, "municipio": self.maringa.pk}])
        self.assertEqual(solto.viagem, v)
        # O termo automático nasce com destino e datas da viagem.
        termo = TermoAutorizacao.objects.get(viagem=v)
        self.assertEqual((termo.destino_cidade, termo.data_evento_inicio), (self.londrina, date(2026, 10, 5)))
        # Desmarcar o ofício desfaz o vínculo; sem tipos o título é "Nova viagem".
        self.client.post(self.etapa(v, 1), self.payload_etapa1(tipos=[], oficios_vinculados=[]))
        v.refresh_from_db()
        solto.refresh_from_db()
        self.assertEqual(v.titulo, "Nova viagem")
        self.assertIsNone(solto.viagem)
        self.assertEqual(TermoAutorizacao.objects.filter(viagem=v).count(), 1)
        # Editar reabre com o vínculo marcado na aba dos ofícios.
        solto.viagem = v
        solto.save(update_fields=["viagem"])
        r = self.client.get(self.etapa(v, 1))
        aba = next(a for a in r.context["abas_documentos"] if a["chave"] == "oficios")
        self.assertTrue(aba["ativa"])
        self.assertEqual(aba["vinculados"], 1)

    def test_data_final_anterior_a_inicial_e_erro(self):
        v = Viagem.objects.create()
        r = self.client.post(self.etapa(v, 1), self.payload_etapa1(data_fim="2026-10-01"))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "A data final não pode ser anterior à data inicial.")
        self.assertContains(r, "aviso--erro")

    def test_stepper_marca_concluidas(self):
        from decimal import Decimal

        v = self.viagem()
        roteiro = Roteiro.objects.create(origem_municipio=self.sede, viagem=v)
        # m066: roteiro sem saída, destino e diárias existe, mas não está concluído.
        r = self.client.get(self.etapa(v, 3))
        self.assertFalse({e["numero"]: e for e in r.context["etapas"]}[2]["concluida"])
        roteiro.saida_dt = timezone.make_aware(datetime(2026, 10, 5, 8, 0))
        roteiro.valor_diarias = Decimal("100.00")
        roteiro.save()
        RoteiroDestino.objects.create(roteiro=roteiro, municipio=self.londrina)
        r = self.client.get(self.etapa(v, 3))
        etapas = {e["numero"]: e for e in r.context["etapas"]}
        self.assertTrue(etapas[1]["concluida"])
        self.assertTrue(etapas[2]["concluida"])
        self.assertTrue(etapas[3]["atual"])
        self.assertFalse(etapas[5]["concluida"])
        self.assertContains(r, 'aria-current="step" title="Ofícios / Justificativas — Atual"')
        self.assertContains(r, "Novo ofício")

    def test_etapas_2_e_5_listam_os_documentos_da_viagem(self):
        v = self.viagem()
        oficio = Oficio.objects.create(motivo="Da viagem", viagem=v)
        roteiro = Roteiro.objects.create(origem_municipio=self.sede)
        RoteiroDestino.objects.create(roteiro=roteiro, municipio=self.londrina)
        oficio.roteiro = roteiro
        oficio.save(update_fields=["roteiro"])
        termo_generico = TermoAutorizacao.objects.create(viagem=v, destino_cidade=self.londrina, destino_estado=self.pr, data_evento_inicio=date(2026, 10, 5))
        termo_do_oficio = TermoAutorizacao.objects.create(oficio=oficio, destino_cidade=self.londrina, destino_estado=self.pr, data_evento_inicio=date(2026, 10, 5))
        r = self.client.get(self.etapa(v, 2))
        self.assertEqual([l["roteiro"].pk for l in r.context["roteiros"]], [roteiro.pk])
        self.assertContains(r, reverse("viagens_roteiros:novo") + f"?viagem={v.pk}")
        r = self.client.get(self.etapa(v, 5))
        self.assertEqual([l["termo"].pk for l in r.context["termos"]], [termo_generico.pk, termo_do_oficio.pk])
        self.assertContains(r, reverse("viagens_termos:novo") + f"?viagem={v.pk}")
        r = self.client.get(self.etapa(v, 3))
        self.assertEqual([l["oficio"].pk for l in r.context["oficios"]], [oficio.pk])


class SolicitacaoTests(CenarioViagem):
    def _imagem(self):
        from PIL import Image

        buffer = io.BytesIO()
        Image.new("RGB", (4, 4), "white").save(buffer, format="PNG")
        return SimpleUploadedFile("convite.png", buffer.getvalue(), content_type="image/png")

    def test_etapa_4_anexa_ve_e_remove_documentos(self):
        v = self.viagem()
        r = self.client.get(self.etapa(v, 4))
        for texto in ["Documentos de solicitação", "Anexar documento de solicitação", "Documento de solicitação",
                      "Escolher arquivos", "Anexar documentos", "Nenhum documento de solicitação anexado ainda.",
                      "Nenhum plano de trabalho vinculado a esta viagem.", "Nenhuma ordem de serviço vinculada a esta viagem.",
                      "Ordem de Serviço", "Plano de Trabalho"]:
            self.assertContains(r, texto)
        url = reverse("viagens_viagem:solicitacao_anexar", args=[v.pk])
        r = self.client.post(url, {}, follow=True)
        self.assertContains(r, "Nenhum arquivo selecionado.")
        r = self.client.post(url, {"arquivo": SimpleUploadedFile("x.txt", b"nada", content_type="text/plain")}, follow=True)
        self.assertContains(r, "Arquivo recusado — x.txt")
        pdf = _pdf_valido()
        r = self.client.post(url, {"arquivo": [SimpleUploadedFile("oficio.pdf", pdf, content_type="application/pdf"), self._imagem()]}, follow=True)
        self.assertContains(r, "Documentos de solicitação anexados com sucesso.")
        anexos = list(ViagemDocumentoSolicitacao.objects.filter(viagem=v).order_by("pk"))
        self.assertEqual([a.nome_original for a in anexos], ["oficio.pdf", "convite.pdf"])
        with anexos[1].arquivo.open("rb") as arquivo:
            self.assertTrue(arquivo.read().startswith(b"%PDF"))
        r = self.client.get(reverse("viagens_viagem:solicitacao_conteudo", args=[v.pk, anexos[0].pk]))
        self.assertEqual(r.status_code, 200)
        self.assertEqual(b"".join(r.streaming_content), pdf)
        # Fecha só o arquivo servido (não a resposta: `close()` derrubaria a
        # conexão da transação do teste); no Windows o arquivo aberto impede a
        # limpeza da pasta temporária.
        for fechar in list(getattr(r, "_resource_closers", [])):
            fechar()
        r = self.client.post(reverse("viagens_viagem:solicitacao_excluir", args=[v.pk, anexos[0].pk]), follow=True)
        self.assertContains(r, "Documento removido.")
        self.assertEqual(ViagemDocumentoSolicitacao.objects.filter(viagem=v).count(), 1)
        # Com solicitação anexada e nenhum rascunho, a viagem está pronta.
        self.assertContains(self.client.get(reverse("viagens_viagem:lista")), 'class="st st--atendido">Pronto')


    def test_anexo_disfarcado_ou_grande_demais_e_recusado(self):
        """m070: o nome terminar em .pdf não basta; o tamanho tem limite."""
        v = self.viagem()
        url = reverse("viagens_viagem:solicitacao_anexar", args=[v.pk])
        html = SimpleUploadedFile("oficio.pdf", b"<html><script>alert(1)</script></html>", content_type="application/pdf")
        r = self.client.post(url, {"arquivo": [html, SimpleUploadedFile("bom.pdf", _pdf_valido(), content_type="application/pdf")]}, follow=True)
        self.assertContains(r, "Arquivo recusado — oficio.pdf")
        self.assertContains(r, "1 documento(s) anexado(s)")
        self.assertEqual(list(ViagemDocumentoSolicitacao.objects.filter(viagem=v).values_list("nome_original", flat=True)), ["bom.pdf"])
        with self.settings(PRIVATE_UPLOAD_MAX_BYTES=100):
            r = self.client.post(url, {"arquivo": SimpleUploadedFile("grande.pdf", _pdf_valido(), content_type="application/pdf")}, follow=True)
        self.assertContains(r, "excede o limite")
        self.assertEqual(ViagemDocumentoSolicitacao.objects.filter(viagem=v).count(), 1)


def _pdf_valido():
    from pypdf import PdfWriter

    buffer = io.BytesIO()
    escritor = PdfWriter()
    escritor.add_blank_page(width=72, height=72)
    escritor.write(buffer)
    return buffer.getvalue()


class Etapa4ListasTests(CenarioViagem):
    def test_pt_e_os_aparecem_nas_linhas_das_listas_dos_modulos(self):
        from viagens_ordens.models import OrdemServico
        from viagens_planos.models import PlanoTrabalho

        v = self.viagem()
        plano = PlanoTrabalho.objects.create(numero=7, ano=2026, viagem=v)
        ordem = OrdemServico.objects.create(numero=9, ano=2026, viagem=v, motivo="Apoio ao evento")
        r = self.client.get(self.etapa(v, 4))
        self.assertEqual(r.status_code, 200)
        # A mesma linha e o mesmo menu de ações das listas de PT e de OS.
        self.assertContains(r, f'id="plano-{plano.pk}-titulo"')
        self.assertContains(r, f'id="os-{ordem.pk}-titulo"')
        self.assertContains(r, "Apoio ao evento")
        self.assertContains(r, f"Ações da {ordem.numero_formatado}")
        self.assertNotContains(r, "Nenhum plano de trabalho vinculado")
        self.assertNotContains(r, "Nenhuma ordem de serviço vinculada")


class BaixarDocumentosTests(CenarioViagem):
    def _anexar(self, v, nome, conteudo=b"%PDF-1.4 x"):
        from django.core.files.base import ContentFile

        anexo = ViagemDocumentoSolicitacao(viagem=v, nome_original=nome)
        anexo.arquivo.save(nome, ContentFile(conteudo), save=True)
        return anexo

    def test_modal_da_viagem_lista_os_documentos_e_baixa_os_marcados(self):
        import json
        import zipfile

        from viagens_ordens.models import OrdemServico
        from viagens_viagem.downloads import itens_para_baixar

        v = self.viagem()
        ordem = OrdemServico.objects.create(numero=9, ano=2026, viagem=v)
        a = self._anexar(v, "convite.pdf")
        b = self._anexar(v, "despacho.pdf")
        valores = [i["valor"] for i in itens_para_baixar(v)]
        self.assertEqual(valores, [f"os-{ordem.pk}", f"sol-{a.pk}", f"sol-{b.pk}"])

        # O botão do cabeçalho leva os itens ao modal.
        r = self.client.get(self.etapa(v, 2))
        self.assertContains(r, "Baixar documentos")
        self.assertContains(r, reverse("viagens_viagem:baixar", args=[v.pk]))
        self.assertIn(f"sol-{a.pk}", json.dumps(valores))

        url = reverse("viagens_viagem:baixar", args=[v.pk])
        r = self.client.post(url, {"itens": [f"sol-{a.pk}"], "formato": "pdf"})
        self.assertEqual(r["Content-Type"], "application/pdf")
        self.assertIn("convite.pdf", r["Content-Disposition"])
        r = self.client.post(url, {"itens": [f"sol-{a.pk}", f"sol-{b.pk}"], "formato": "pdf", "saida": "separados"})
        self.assertEqual(r["Content-Type"], "application/zip")
        with zipfile.ZipFile(io.BytesIO(r.content)) as z:
            self.assertEqual(sorted(z.namelist()), ["convite.pdf", "despacho.pdf"])
        # Item de outra viagem (ou inventado) não passa.
        self.assertEqual(self.client.post(url, {"itens": ["sol-999999"], "formato": "pdf"}).status_code, 404)
        r = self.client.post(url, {"formato": "pdf"}, follow=True)
        self.assertContains(r, "Marque ao menos um documento para baixar.")


    def test_baixar_tudo_entrega_zip_com_cada_documento_separado_e_numerado(self):
        """m065: um arquivo por documento (cada um é assinado à parte), numerados."""
        import zipfile

        from viagens_ordens.models import OrdemServico

        v = self.viagem()
        OrdemServico.objects.create(numero=9, ano=2026, viagem=v, motivo="Apoio")
        self._anexar(v, "convite.pdf")
        # Ofício incompleto (sem protocolo, equipe...) não impede o resto.
        Oficio.objects.create(viagem=v, numero=21, ano=2026)
        r = self.client.get(self.etapa(v, 1))
        self.assertContains(r, "Baixar tudo (ZIP)")
        r = self.client.post(reverse("viagens_viagem:baixar_tudo", args=[v.pk]))
        self.assertEqual(r["Content-Type"], "application/zip")
        with zipfile.ZipFile(io.BytesIO(r.content)) as z:
            nomes = z.namelist()
            leia = z.read("00 - LEIA-ME.txt").decode("utf-8")
        self.assertEqual(nomes[0], "00 - LEIA-ME.txt")
        self.assertTrue(any(n.startswith("01 - ") and "OS 009-2026" in n for n in nomes), nomes)
        self.assertTrue(any(n.startswith("02 - ") and n.endswith(".pdf") and "convite" in n for n in nomes), nomes)
        self.assertNotIn("/", "".join(nomes))
        self.assertIn("Não entraram", leia)
        self.assertIn("Ofício 21/2026", leia)
        self.assertIn("Ainda sem a versão assinada", leia)

    def test_baixar_tudo_sem_documento_pronto_avisa(self):
        v = self.viagem()
        r = self.client.post(reverse("viagens_viagem:baixar_tudo", args=[v.pk]), follow=True)
        self.assertContains(r, "Nenhum documento pronto para baixar ainda.")


class AcoesTests(CenarioViagem):
    def test_cancelar_exige_motivo_e_cancela_os_documentos(self):
        v = self.viagem()
        oficio = Oficio.objects.create(motivo="Da viagem", viagem=v)
        r = self.client.post(reverse("viagens_viagem:acao", args=[v.pk, "cancelar"]), {}, follow=True)
        self.assertContains(r, "Informe o motivo do cancelamento.")
        r = self.client.post(reverse("viagens_viagem:acao", args=[v.pk, "cancelar"]), {"motivo": "Chuva"}, follow=True)
        self.assertContains(r, "Viagem cancelada. Todos os documentos vinculados também foram cancelados.")
        self.assertContains(r, "Reativar viagem")
        self.assertContains(r, "Chuva")
        v.refresh_from_db()
        oficio.refresh_from_db()
        self.assertTrue(v.cancelado and oficio.cancelado)
        r = self.client.post(reverse("viagens_viagem:acao", args=[v.pk, "reativar"]), {}, follow=True)
        self.assertContains(r, "Viagem reativada. Os documentos cancelados junto com ela também foram reativados.")
        oficio.refresh_from_db()
        self.assertFalse(oficio.cancelado)

    def test_excluir_leva_os_documentos_so_dela(self):
        v = self.viagem()
        Oficio.objects.create(motivo="Da viagem", viagem=v)
        r = self.client.post(reverse("viagens_viagem:acao", args=[v.pk, "excluir"]))
        self.assertRedirects(r, reverse("viagens_viagem:lista"))
        self.assertFalse(Viagem.objects.filter(pk=v.pk).exists())
        self.assertFalse(Oficio.objects.filter(viagem_id=v.pk).exists())

    def test_leitor_nao_cria(self):
        self.user.groups.clear()
        self.assertEqual(self.client.post(reverse("viagens_viagem:criar")).status_code, 403)
        v = self.viagem()
        self.assertEqual(self.client.get(self.etapa(v, 1)).status_code, 200)
        self.assertEqual(self.client.post(self.etapa(v, 1), self.payload_etapa1()).status_code, 403)


class DocumentosNascidosDaViagemTests(CenarioViagem):
    def test_novo_oficio_do_painel_herda_motivo_e_volta_a_etapa_3(self):
        v = self.viagem(motivo="Atividade comunitária")
        r = self.client.post(reverse("viagens_oficios:criar"), {"viagem": v.pk})
        oficio = Oficio.objects.latest("pk")
        self.assertRedirects(r, reverse("viagens_oficios:editar", args=[oficio.pk]))
        self.assertEqual((oficio.viagem, oficio.motivo, oficio.solicitante), (v, "Atividade comunitária", self.unidade))
        r = self.client.get(reverse("viagens_oficios:editar", args=[oficio.pk]))
        self.assertEqual(r.context["url_voltar"], self.etapa(v, 3))
        r = self.client.post(reverse("viagens_oficios:acao", args=[oficio.pk, "excluir"]))
        self.assertRedirects(r, self.etapa(v, 3))

    def test_novo_roteiro_do_painel_vem_preenchido_e_volta_a_etapa_2(self):
        v = self.viagem()
        v.destinos_extras = [{"estado": self.pr.pk, "municipio": self.maringa.pk}]
        v.save()
        r = self.client.get(reverse("viagens_roteiros:novo"), {"viagem": v.pk})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.context["valores"]["origem_municipio"], str(self.sede.pk))
        destinos = [c["form"].initial.get("municipio") for c in r.context["destinos_cards"] if c["visivel"]]
        self.assertEqual(destinos, [self.londrina.pk, self.maringa.pk])
        trechos = [c["form"].initial for c in r.context["trechos_cards"] if c["visivel"]]
        self.assertEqual([(t["origem_municipio"], t["destino_municipio"], t["saida_data"], t["saida_hora"]) for t in trechos], [
            (self.sede.pk, self.londrina.pk, "2026-10-05", "08:00"),
            (self.londrina.pk, self.maringa.pk, "2026-10-05", "08:00"),
            (self.maringa.pk, self.sede.pk, "2026-10-07", "16:00"),
        ])
        self.assertContains(r, f'name="viagem" value="{v.pk}"')
        dados = {
            "viagem": v.pk, "origem_municipio": self.sede.pk,
            "destinos-TOTAL_FORMS": "1", "destinos-INITIAL_FORMS": "0", "destinos-MIN_NUM_FORMS": "0", "destinos-MAX_NUM_FORMS": "1000",
            "destinos-0-ordem": "1", "destinos-0-municipio": self.londrina.pk,
            "trechos-TOTAL_FORMS": "1", "trechos-INITIAL_FORMS": "0", "trechos-MIN_NUM_FORMS": "0", "trechos-MAX_NUM_FORMS": "1000",
            "trechos-0-ordem": "1", "trechos-0-origem_municipio": self.sede.pk, "trechos-0-destino_municipio": self.londrina.pk,
            "trechos-0-saida_data": "2026-10-05", "trechos-0-saida_hora": "08:00", "trechos-0-chegada_data": "2026-10-05", "trechos-0-chegada_hora": "18:00",
        }
        r = self.client.post(reverse("viagens_roteiros:novo"), dados)
        roteiro = Roteiro.objects.latest("pk")
        self.assertRedirects(r, self.etapa(v, 2))
        self.assertEqual(roteiro.viagem, v)

    def test_novo_termo_do_painel_herda_a_semente_e_volta_a_etapa_5(self):
        v = self.viagem()
        oficio = Oficio.objects.create(motivo="Da viagem", viagem=v, viatura=self.viatura)
        oficio.servidores.set([self.a, self.b])
        oficio.servidores_termo_autorizacao.set([self.a])
        r = self.client.get(reverse("viagens_termos:novo"), {"viagem": v.pk})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.context["valores"]["oficio"], str(oficio.pk))
        self.assertEqual(r.context["valores"]["destino_cidade"], str(self.londrina.pk))
        self.assertEqual(r.context["valores"]["data_evento_inicio"], "2026-10-05")
        self.assertEqual(r.context["valores"]["viatura"], str(self.viatura.pk))
        self.assertEqual([s["valor"] for s in r.context["servidores"] if s["selecionado"]], [str(self.a.pk)])
        r = self.client.post(reverse("viagens_termos:novo"), {
            "viagem": v.pk, "oficio": oficio.pk, "destino_estado": self.pr.pk, "destino_cidade": self.londrina.pk,
            "data_evento_inicio": "2026-10-05", "data_evento_fim": "2026-10-07", "servidores": [self.a.pk], "viatura": self.viatura.pk,
            "quantidade_destinos": "0",
        })
        termo = TermoAutorizacao.objects.latest("pk")
        self.assertRedirects(r, self.etapa(v, 5))
        self.assertEqual(termo.viagem, v)


class RepetirViagemTests(CenarioViagem):
    """m076: repetir a viagem em outra data, com os documentos em rascunho."""

    def montar(self):
        from viagens_ordens.models import OrdemServico
        from viagens_planos.models import PlanoTrabalho
        from viagens_planos.services import salvar_plano_numerado
        from viagens_roteiros.models import RoteiroTrecho

        v = self.viagem(data_inicio=date(2026, 10, 5), data_fim=date(2026, 10, 7))
        saida = timezone.make_aware(datetime(2026, 10, 5, 8, 0))
        roteiro = Roteiro.objects.create(origem_municipio=self.sede, viagem=v, saida_dt=saida)
        RoteiroDestino.objects.create(roteiro=roteiro, municipio=self.londrina)
        RoteiroTrecho.objects.create(roteiro=roteiro, ordem=1, origem_municipio=self.sede, destino_municipio=self.londrina,
                                     saida_dt=saida, chegada_dt=saida + timedelta(hours=5), distancia_km=380)
        oficio = Oficio.objects.create(viagem=v, roteiro=roteiro, numero=7, ano=2026, protocolo="123456789",
                                       viatura=self.viatura, motorista=self.a, status=Oficio.STATUS_FINALIZADO)
        oficio.servidores.set([self.a, self.b])
        ordem = OrdemServico.objects.create(viagem=v, data_evento_inicio=date(2026, 10, 5), motivo="Apoio")
        ordem.definir_destinos([self.londrina.pk, self.maringa.pk])
        ordem.oficios.set([oficio])
        plano = salvar_plano_numerado(PlanoTrabalho(viagem=v, destino_estado=self.pr, destino_cidade=self.londrina,
                                                    data_evento_inicio=date(2026, 10, 5), data_evento_fim=date(2026, 10, 6)))
        termo = TermoAutorizacao.objects.create(viagem=v, oficio=oficio, destino_estado=self.pr, destino_cidade=self.londrina,
                                                data_evento_inicio=date(2026, 10, 5))
        termo.servidores.set([self.a])
        return v, oficio, ordem, plano

    def test_repetir_copia_documentos_com_datas_novas_e_sem_numeros_antigos(self):
        from viagens_ordens.models import OrdemServico
        from viagens_planos.models import PlanoTrabalho

        v, oficio, ordem, plano = self.montar()
        r = self.client.post(reverse("viagens_viagem:repetir", args=[v.pk]), {"nova_data": "2026-11-02"})
        nova = Viagem.objects.exclude(pk=v.pk).get()
        self.assertRedirects(r, self.etapa(nova, 1), fetch_redirect_response=False)
        self.assertEqual((nova.data_inicio, nova.data_fim), (date(2026, 11, 2), date(2026, 11, 4)))
        self.assertEqual(list(nova.tipos.all()), [self.tipo])

        roteiro = nova.roteiros.get()
        self.assertEqual(timezone.localtime(roteiro.saida_dt), timezone.make_aware(datetime(2026, 11, 2, 8, 0)))
        self.assertEqual(timezone.localtime(roteiro.trechos.get().chegada_dt).hour, 13)

        novo_oficio = nova.oficios.get()
        self.assertEqual(novo_oficio.roteiro, roteiro)
        self.assertNotEqual((novo_oficio.numero, novo_oficio.ano), (oficio.numero, oficio.ano))
        self.assertEqual(novo_oficio.protocolo, "")
        self.assertEqual(novo_oficio.status, Oficio.STATUS_RASCUNHO)
        self.assertEqual(set(novo_oficio.servidores.all()), {self.a, self.b})
        self.assertEqual((novo_oficio.viatura, novo_oficio.motorista), (self.viatura, self.a))

        nova_os = OrdemServico.objects.get(viagem=nova)
        self.assertNotEqual(nova_os.numero, ordem.numero)
        self.assertEqual(nova_os.data_evento_inicio, date(2026, 11, 2))
        self.assertEqual(list(nova_os.destinos_em_ordem()), [self.londrina, self.maringa])
        self.assertEqual(list(nova_os.oficios.all()), [novo_oficio])

        novo_plano = PlanoTrabalho.objects.get(viagem=nova)
        self.assertNotEqual(novo_plano.numero, plano.numero)
        self.assertEqual(novo_plano.data_evento_fim, date(2026, 11, 3))

        novo_termo = TermoAutorizacao.objects.get(viagem=nova)
        self.assertEqual(novo_termo.oficio, novo_oficio)
        self.assertEqual(list(novo_termo.servidores.all()), [self.a])
        # A original fica como estava.
        oficio.refresh_from_db()
        self.assertEqual((oficio.numero, oficio.protocolo), (7, "123456789"))

    def test_repetir_em_outra_cidade_troca_o_destino_principal(self):
        from viagens_ordens.models import OrdemServico

        v = self.montar()[0]
        self.client.post(reverse("viagens_viagem:repetir", args=[v.pk]),
                         {"nova_data": "2026-11-02", f"nova_cidade_{v.pk}": self.maringa.pk})
        nova = Viagem.objects.exclude(pk=v.pk).get()
        self.assertEqual(nova.destino_municipio, self.maringa)
        roteiro = nova.roteiros.get()
        self.assertEqual(list(roteiro.destinos.values_list("municipio", flat=True)), [self.maringa.pk])
        self.assertIsNone(roteiro.trechos.get().distancia_km)
        self.assertEqual(TermoAutorizacao.objects.get(viagem=nova).destino_cidade, self.maringa)
        self.assertEqual(OrdemServico.objects.get(viagem=nova).destinos_em_ordem()[0], self.maringa)

    def test_repetir_exige_data_e_a_lista_oferece_a_acao(self):
        v = self.viagem()
        r = self.client.post(reverse("viagens_viagem:repetir", args=[v.pk]), {"nova_data": ""}, follow=True)
        self.assertContains(r, "Informe a data da nova edição")
        self.assertEqual(Viagem.objects.count(), 1)
        self.assertContains(self.client.get(reverse("viagens_viagem:lista")), reverse("viagens_viagem:repetir", args=[v.pk]))
