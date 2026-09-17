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

    def test_etapa_1_traz_os_blocos_da_origem_sem_avisos(self):
        v = Viagem.objects.create()
        r = self.client.get(self.etapa(v, 1))
        html = r.content.decode()
        for texto in ["Nova viagem", "Dados da viagem", "Identificação", "Tipo da viagem", "Gerenciar tipos", "Modelo de motivo",
                      "Gerenciar modelos", "Contextualize a atividade…", "Data da viagem", "Data de início", "Data de fim",
                      "Destinos", "Documentos vinculados", "Ofícios", "Roteiros", "Plano de Trabalho", "Ordem de Serviço", "Termos",
                      "Nenhum ofício disponível para o período.", "Voltar à lista", "Salvar e avançar", "Etapa 1 de 5 · Dados da viagem"]:
            self.assertIn(texto, html)
        self.assertNotIn("aviso--erro", html)
        # A ordem dos blocos é a da origem.
        self.assertLess(html.index("Identificação"), html.index("Motivo</strong>"))
        self.assertLess(html.index("Motivo</strong>"), html.index("Data da viagem"))
        self.assertLess(html.index("Data da viagem"), html.index("Destinos</strong>"))
        self.assertLess(html.index("Destinos</strong>"), html.index("Documentos vinculados"))
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
        v = self.viagem()
        Roteiro.objects.create(origem_municipio=self.sede, viagem=v)
        r = self.client.get(self.etapa(v, 3))
        etapas = {e["numero"]: e for e in r.context["etapas"]}
        self.assertTrue(etapas[1]["concluida"])
        self.assertTrue(etapas[2]["concluida"])
        self.assertTrue(etapas[3]["atual"])
        self.assertFalse(etapas[5]["concluida"])
        self.assertContains(r, "Etapa 3 de 5 · Ofícios / Justificativas")
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
        for texto in ["Documentos de solicitação", "Ofícios solicitantes, convites, despachos ou imagens.", "Anexar documento",
                      "Escolher arquivos", "Anexar documentos", "Nenhum documento de solicitação anexado ainda.",
                      "Planejamento e autorização", "Nenhum plano ou OS vinculado a esta viagem.", "Ordem de Serviço", "Plano de Trabalho"]:
            self.assertContains(r, texto)
        url = reverse("viagens_viagem:solicitacao_anexar", args=[v.pk])
        r = self.client.post(url, {}, follow=True)
        self.assertContains(r, "Nenhum arquivo selecionado.")
        r = self.client.post(url, {"arquivo": SimpleUploadedFile("x.txt", b"nada", content_type="text/plain")}, follow=True)
        self.assertContains(r, "Formato inválido. Envie um PDF ou arquivo de imagem.")
        r = self.client.post(url, {"arquivo": [SimpleUploadedFile("oficio.pdf", b"%PDF-1.4", content_type="application/pdf"), self._imagem()]}, follow=True)
        self.assertContains(r, "Documentos de solicitação anexados com sucesso.")
        anexos = list(ViagemDocumentoSolicitacao.objects.filter(viagem=v).order_by("pk"))
        self.assertEqual([a.nome_original for a in anexos], ["oficio.pdf", "convite.pdf"])
        with anexos[1].arquivo.open("rb") as arquivo:
            self.assertTrue(arquivo.read().startswith(b"%PDF"))
        r = self.client.get(reverse("viagens_viagem:solicitacao_conteudo", args=[v.pk, anexos[0].pk]))
        self.assertEqual(r.status_code, 200)
        self.assertEqual(b"".join(r.streaming_content), b"%PDF-1.4")
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
