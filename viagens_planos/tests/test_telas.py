"""As telas: lista com abas e busca, criar, a página única, eventos, ações e o leitor."""

import json
from datetime import date, timedelta

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from viagens_planos.models import EfetivoPlano, PlanoTrabalho
from viagens_planos.presenters import cartao_para_viagem
from viagens_planos.selectors import listar_planos
from viagens_planos.services import atualizar_snapshot_diarias

from .fixtures import CenarioPlanoMixin


class ListaTests(CenarioPlanoMixin, TestCase):
    def test_lista_abre_com_abas_busca_e_acoes(self):
        plano = self.criar_plano_maringa()
        plano.programa = self.programa
        plano.coordenador_adm = self.juliana
        plano.save()
        r = self.client.get(reverse("viagens_planos:lista"))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "Plano de Trabalho 20/2026/ASCOM")
        self.assertContains(r, 'class="st st--neutro">Rascunho')
        for fato in ["25/06/2026 a 27/06/2026", "Maringá/PR", "PROGRAMA PARANÁ EM AÇÃO", "6 no efetivo"]:
            self.assertContains(r, fato)
        self.assertContains(r, "Novo plano")
        self.assertContains(r, reverse("viagens_planos:editar", args=[plano.pk]) + "?next=")
        self.assertContains(r, reverse("viagens_planos:gerar", args=[plano.pk, "pdf"]) + "?inline=1")
        self.assertEqual(r.context["situacoes"][0]["total"], 1)
        self.assertEqual([s["titulo"] for s in r.context["situacoes"]], ["Todos", "Que vão acontecer", "Em andamento e realizados", "Finalizados", "Cancelados"])

    def test_abas_e_busca(self):
        hoje = timezone.localdate()
        futuro = self.criar_plano_maringa()
        futuro.data_evento_inicio = hoje + timedelta(days=10)
        futuro.data_evento_fim = hoje + timedelta(days=12)
        futuro.save()
        passado = PlanoTrabalho.objects.create(numero=21, ano=2026, destino_cidade=self.sarandi, destino_estado=self.uf, data_evento_inicio=hoje - timedelta(days=5), data_evento_fim=hoje - timedelta(days=4))
        sem_data = PlanoTrabalho.objects.create(numero=22, ano=2026, programa_outros="Feira do Livro")
        cancelado = PlanoTrabalho.objects.create(numero=23, ano=2026)
        cancelado.cancelar("Adiado")
        self.assertEqual(set(listar_planos(situacoes=["futuras"])), {futuro, sem_data})
        self.assertEqual(list(listar_planos(situacoes=["atuais"])), [passado])
        self.assertEqual(list(listar_planos(situacoes=["cancelados"])), [cancelado])
        self.assertEqual(list(listar_planos(situacoes=["finalizados"])), [])
        self.assertEqual(list(listar_planos("Sarandi")), [passado])
        self.assertEqual(list(listar_planos("feira")), [sem_data])
        self.assertEqual(list(listar_planos("21")), [passado])
        self.assertEqual(list(listar_planos("20/2026")), [futuro])
        r = self.client.get(reverse("viagens_planos:lista"), {"situacao": "cancelados"})
        self.assertContains(r, "23/2026")
        self.assertNotContains(r, "21/2026")

    def test_leitor_ve_a_lista_sem_acoes(self):
        plano = self.criar_plano_maringa()
        self.user.groups.clear()
        r = self.client.get(reverse("viagens_planos:lista"))
        self.assertNotContains(r, "Novo plano")
        self.assertContains(r, "Abrir")
        self.assertContains(r, reverse("viagens_planos:editar", args=[plano.pk]))


class CriarTests(CenarioPlanoMixin, TestCase):
    def test_post_cria_rascunho_numerado_e_abre_o_cadastro(self):
        r = self.client.post(reverse("viagens_planos:criar"))
        plano = PlanoTrabalho.objects.latest("pk")
        ano = timezone.localdate().year
        self.assertEqual(plano.numero_formatado, f"01/{ano}/ASCOM")
        self.assertRedirects(r, reverse("viagens_planos:editar", args=[plano.pk]), fetch_redirect_response=False)
        r = self.client.get(r["Location"])
        self.assertContains(r, f"Plano de Trabalho 01/{ano}/ASCOM criado como rascunho.")

    def test_get_nao_cria_nada(self):
        r = self.client.get(reverse("viagens_planos:criar"))
        self.assertRedirects(r, reverse("viagens_planos:lista"))
        self.assertFalse(PlanoTrabalho.objects.exists())

    def test_criar_com_viagem_grava_o_vinculo(self):
        from viagens_viagem.models import Viagem

        viagem = Viagem.objects.create(titulo="Ação em Maringá", destino_estado=self.uf, destino_municipio=self.maringa, data_inicio=date(2026, 6, 25))
        self.client.post(reverse("viagens_planos:criar"), {"viagem": viagem.pk})
        plano = PlanoTrabalho.objects.latest("pk")
        self.assertEqual(plano.viagem, viagem)
        self.assertEqual(plano.destino_cidade, self.maringa)
        self.assertEqual(plano.programa_outros, "Ação em Maringá")

    def test_novo_plano_reaproveita_rascunho_vazio_abandonado(self):
        self.client.post(reverse("viagens_planos:criar"))
        vazio = PlanoTrabalho.objects.get()
        # Recém-aberto: pode estar sendo preenchido por alguém, então não se reaproveita.
        self.client.post(reverse("viagens_planos:criar"))
        self.assertEqual(PlanoTrabalho.objects.count(), 2)
        PlanoTrabalho.objects.update(atualizado_em=timezone.now() - timedelta(hours=1))
        r = self.client.post(reverse("viagens_planos:criar"))
        self.assertRedirects(r, reverse("viagens_planos:editar", args=[vazio.pk]), fetch_redirect_response=False)
        self.assertEqual(PlanoTrabalho.objects.count(), 2)
        # Com conteúdo, o rascunho é de alguém e não volta.
        PlanoTrabalho.objects.update(destino_cidade=self.maringa)
        self.client.post(reverse("viagens_planos:criar"))
        self.assertEqual(PlanoTrabalho.objects.count(), 3)

    def test_leitor_nao_cria(self):
        self.user.groups.clear()
        self.assertEqual(self.client.post(reverse("viagens_planos:criar")).status_code, 403)


class PaginaUnicaTests(CenarioPlanoMixin, TestCase):
    def setUp(self):
        super().setUp()
        self.plano = self.criar_pela_tela()
        self.url = reverse("viagens_planos:editar", args=[self.plano.pk])

    def test_abre_sem_avisos_com_os_quatro_cartoes(self):
        r = self.client.get(self.url)
        self.assertEqual(r.status_code, 200)
        for titulo in ["Identificação e atuação", "Efetivo e diárias", "Atividades, metas e recursos", "Resumo e documentos"]:
            self.assertContains(r, titulo)
        for rotulo in ["Programa solicitante", "Outro programa", "Coordenador administrativo", "Coordenador operacional (opcional)",
                       "Período do evento", "Data de ida", "Data de volta", "Horário de atendimento", "Destinos", "Breve contextualização",
                       "Coordenação do evento", "Considerações finais", "Data de saída da sede", "Hora de saída", "Data de chegada na sede",
                       "Hora de chegada", "Valor total do plano", "Valor por servidor", "Quantidade de diárias", "Efetivo total",
                       "Filtrar atividades por nome", "Aplicar preset…", "Limpar seleção", "Gerenciar atividades", "Sem metas ainda",
                       "Sem recursos ainda", "Adicionar evento ao plano", "Salvar plano", "Salvar rascunho", "Voltar"]:
            self.assertContains(r, rotulo)
        self.assertContains(r, "Plano de trabalho <span")
        self.assertNotContains(r, "Corrija os itens abaixo")
        self.assertNotContains(r, "Informe o coordenador administrativo")
        self.assertNotContains(r, "aviso aviso--erro\" role=\"alert\"")
        # O preset padrão vem marcado no plano novo; o texto automático já preenchido.
        self.assertContains(r, 'value="CIN" id="pt-atividade-CIN" checked')
        self.assertContains(r, "no âmbito do")
        self.assertContains(r, reverse("viagens_cadastros:lista", args=["programas"]))
        self.assertContains(r, reverse("viagens_cadastros:lista", args=["atividades-pt"]))

    def test_gravar_pela_tela_fica_na_pagina(self):
        r = self.client.post(self.url, self.payload())
        self.assertRedirects(r, self.url, fetch_redirect_response=False)
        plano = PlanoTrabalho.objects.get(pk=self.plano.pk)
        self.assertEqual(plano.programa, self.programa)
        self.assertEqual(plano.destino_cidade, self.maringa)
        self.assertEqual(plano.data_evento_fim, date(2026, 6, 27))
        self.assertEqual(plano.coordenador_adm, self.juliana)
        self.assertEqual(plano.coordenador_adm_genero, "FEMININO")
        self.assertEqual((plano.coordenador_op_modo, plano.coordenador_op_nome_manual, plano.coordenador_op_cargo_manual), ("MANUAL", "JOSÉ PEREIRA", "Policial Civil"))
        self.assertEqual(plano.total_efetivo, 6)
        self.assertEqual(plano.diarias_composicao, "4 x 100% + 1 x 15%")
        self.assertEqual(list(plano.atividades_selecionadas.values_list("codigo", flat=True)), ["CIN"])
        self.assertIn("Maringá/PR", plano.contextualizacao)
        self.assertIn("Papiloscopista Juliana Villela de Barros", plano.coordenacao)
        self.assertIn("Policial Civil José Pereira", plano.coordenacao)
        r = self.client.get(self.url)
        self.assertContains(r, "Plano salvo.")
        self.assertContains(r, "R$ 7.234,68")
        self.assertContains(r, "Finalizar plano")

    def test_texto_editado_a_mao_desliga_o_automatico(self):
        self.client.post(self.url, self.payload(contextualizacao="Texto meu.", contextualizacao_auto="0"))
        plano = PlanoTrabalho.objects.get(pk=self.plano.pk)
        self.assertEqual(plano.contextualizacao, "Texto meu.")
        self.assertFalse(plano.contextualizacao_auto)

    def test_destinos_extras_e_erros(self):
        dados = self.payload(quantidade_destinos="1", extra_estado_0=str(self.uf.pk), extra_cidade_0=str(self.sarandi.pk))
        self.client.post(self.url, dados)
        plano = PlanoTrabalho.objects.get(pk=self.plano.pk)
        self.assertEqual([d.cidade for d in plano.destinos_rascunho()], [self.maringa, self.sarandi])
        r = self.client.post(self.url, self.payload(data_evento_fim="2026-06-20", programa="__outro__", programa_outros=""))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "Não foi possível salvar o plano")
        self.assertContains(r, "A data final não pode ser anterior à data inicial.")
        self.assertContains(r, "Informe o outro programa.")

    def test_erro_do_calculo_so_aparece_depois_do_envio(self):
        r = self.client.post(self.url, self.payload(chegada_sede_data="2026-06-24", chegada_sede_hora="06:00"))
        self.assertContains(r, "A chegada na sede deve ser depois da saída.")

    def test_efetivo_incompleto_acusa(self):
        r = self.client.post(self.url, self.payload(**{"efetivo-0-cargo": ""}))
        self.assertContains(r, "Selecione o cargo.")

    def test_finalizar_com_pendencia_mostra_a_lista(self):
        r = self.client.post(self.url, self.payload(**{"efetivo-0-cargo": "", "efetivo-0-quantidade": "", "efetivo-0-unidade": ""}, acao="finalizar"), follow=True)
        self.assertContains(r, "Corrija os itens abaixo antes de finalizar o plano ou gerar DOCX/PDF.")
        self.assertContains(r, "Informe o efetivo (cargo e quantidade) em efetivo e diárias.")
        self.assertEqual(PlanoTrabalho.objects.get(pk=self.plano.pk).status, PlanoTrabalho.STATUS_RASCUNHO)

    def test_finalizar_vai_para_a_lista(self):
        r = self.client.post(self.url, self.payload(acao="finalizar"))
        self.assertRedirects(r, reverse("viagens_planos:lista"), fetch_redirect_response=False)
        self.assertEqual(PlanoTrabalho.objects.get(pk=self.plano.pk).status, PlanoTrabalho.STATUS_GERADO)
        r = self.client.get(reverse("viagens_planos:lista"))
        self.assertContains(r, "Plano de trabalho finalizado com sucesso.")

    def test_calcular_devolve_a_previa(self):
        self.client.post(self.url, self.payload())
        r = self.client.post(reverse("viagens_planos:calcular", args=[self.plano.pk]), data=json.dumps({
            "saida_sede_data": "2026-06-24", "saida_sede_hora": "07:00", "chegada_sede_data": "2026-06-28", "chegada_sede_hora": "14:00", "total_efetivo": 10,
        }), content_type="application/json")
        dados = r.json()
        self.assertTrue(dados["ok"])
        self.assertEqual((dados["composicao"], dados["valor_total_display"], dados["quantidade_servidores"]), ("4 x 100% + 1 x 15%", "12.057,80", 10))
        r = self.client.post(reverse("viagens_planos:calcular", args=[self.plano.pk]), data=json.dumps({"saida_sede_data": "", "total_efetivo": 0}), content_type="application/json")
        self.assertFalse(r.json()["ok"])
        self.assertIn("Informe data e hora de saída da sede.", r.json()["erros"])

    def test_leitor_abre_mas_nao_grava(self):
        self.user.groups.clear()
        r = self.client.get(self.url)
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, 'class="frm-fieldset" disabled')
        self.assertNotContains(r, "Salvar plano")
        self.assertEqual(self.client.post(self.url, self.payload()).status_code, 403)


class EventosTests(CenarioPlanoMixin, TestCase):
    def setUp(self):
        super().setUp()
        self.plano = self.criar_pela_tela()
        self.url = reverse("viagens_planos:editar", args=[self.plano.pk])

    def test_adicionar_editar_e_remover_evento(self):
        r = self.client.post(reverse("viagens_planos:evento_adicionar", args=[self.plano.pk]), self.payload(), follow=True)
        self.assertContains(r, "Evento 1 salvo.")
        plano = PlanoTrabalho.objects.get(pk=self.plano.pk)
        self.assertTrue(plano.is_multi_evento)
        evento = plano.eventos.get()
        self.assertEqual(evento.destino_display, "Maringá/PR")
        self.assertEqual(evento.total_efetivo, 6)
        self.assertIsNone(plano.destino_cidade)
        self.assertContains(r, "Evento 1 de 1")
        self.assertContains(r, "Nº " + plano.numero_formatado + " · Maringá/PR")
        self.assertContains(r, "6 · POLICIAL CIVIL · ASCOM")

        segundo = self.payload(destino_cidade=str(self.sarandi.pk), data_evento_inicio="2026-06-29", data_evento_fim="2026-06-29", **{"efetivo-0-quantidade": "4"})
        self.client.post(reverse("viagens_planos:evento_adicionar", args=[self.plano.pk]), segundo)
        plano.refresh_from_db()
        self.assertEqual(plano.eventos.count(), 2)
        self.assertEqual(plano.total_efetivo_combinado, 6)

        # A tela volta com a identificação em branco depois de adicionar: editar só carrega o evento.
        r = self.client.post(reverse("viagens_planos:evento_editar", args=[self.plano.pk, evento.pk]), self.payload_vazio(), follow=True)
        self.assertContains(r, "Editando o evento 1.")
        plano.refresh_from_db()
        self.assertEqual(plano.eventos.count(), 2)
        self.assertEqual(plano.evento_em_edicao, evento)
        self.assertEqual(plano.destino_cidade, self.maringa)
        self.assertContains(r, "Editando um evento existente")

        r = self.client.post(reverse("viagens_planos:evento_remover", args=[self.plano.pk, evento.pk]), follow=True)
        self.assertContains(r, "Evento removido do plano.")
        plano.refresh_from_db()
        self.assertEqual(plano.eventos.count(), 1)
        self.assertTrue(plano.is_multi_evento)

    def test_editar_evento_guarda_o_que_estava_na_tela(self):
        """Quem digita um evento novo e clica em "Editar" no anterior não perde o que digitou."""
        self.client.post(reverse("viagens_planos:evento_adicionar", args=[self.plano.pk]), self.payload())
        plano = PlanoTrabalho.objects.get(pk=self.plano.pk)
        primeiro = plano.eventos.get()
        digitando = self.payload(destino_cidade=str(self.sarandi.pk), data_evento_inicio="2026-06-29", data_evento_fim="2026-06-29")
        self.client.post(reverse("viagens_planos:evento_editar", args=[self.plano.pk, primeiro.pk]), digitando)
        plano.refresh_from_db()
        self.assertEqual(plano.eventos.count(), 2)
        self.assertEqual(plano.eventos.exclude(pk=primeiro.pk).get().destino_display, "Sarandi/PR")
        self.assertEqual(plano.evento_em_edicao, primeiro)

    def test_rascunho_vazio_nao_vira_evento(self):
        plano = PlanoTrabalho.objects.get(pk=self.plano.pk)
        plano.destino_cidade = None
        plano.destino_estado = None
        plano.save()
        vazio = self.payload(programa="", destino_estado="", destino_cidade="", data_evento_inicio="", data_evento_fim="",
                             **{"efetivo-0-cargo": "", "efetivo-0-quantidade": "", "efetivo-0-unidade": ""}, atividades_codigos=[])
        r = self.client.post(reverse("viagens_planos:evento_adicionar", args=[self.plano.pk]), vazio, follow=True)
        self.assertContains(r, "Preencha os dados do evento antes de adicioná-lo ao plano.")
        self.assertFalse(PlanoTrabalho.objects.get(pk=self.plano.pk).is_multi_evento)


class AcoesTests(CenarioPlanoMixin, TestCase):
    def setUp(self):
        super().setUp()
        self.plano = self.criar_plano_maringa()

    def test_cancelar_reativar_excluir(self):
        url = lambda acao: reverse("viagens_planos:acao", args=[self.plano.pk, acao])  # noqa: E731
        r = self.client.post(url("cancelar"), {"motivo": "Adiado"}, follow=True)
        self.assertContains(r, "Plano de Trabalho 20/2026/ASCOM cancelado. O histórico foi mantido.")
        self.assertContains(r, "Plano cancelado")
        self.assertContains(r, "Adiado")
        self.assertTrue(PlanoTrabalho.objects.get(pk=self.plano.pk).cancelado)
        r = self.client.post(url("reativar"), follow=True)
        self.assertContains(r, "Plano de Trabalho 20/2026/ASCOM reativado.")
        self.assertFalse(PlanoTrabalho.objects.get(pk=self.plano.pk).cancelado)
        r = self.client.post(url("excluir"), follow=True)
        self.assertRedirects(r, reverse("viagens_planos:lista"))
        self.assertContains(r, "Plano de Trabalho 20/2026/ASCOM excluído.")
        self.assertFalse(PlanoTrabalho.objects.filter(pk=self.plano.pk).exists())
        self.assertEqual(self.client.post(url("outra")).status_code, 404)

    def test_excluir_volta_para_o_next(self):
        r = self.client.post(reverse("viagens_planos:acao", args=[self.plano.pk, "excluir"]), {"next": reverse("viagens_planos:lista") + "?q=x"})
        self.assertRedirects(r, reverse("viagens_planos:lista") + "?q=x", fetch_redirect_response=False)


class ContratoDaViagemTests(CenarioPlanoMixin, TestCase):
    def test_cartao_para_viagem(self):
        plano = self.criar_plano_maringa()
        plano.programa = self.programa
        plano.save()
        atualizar_snapshot_diarias(plano)
        cartao = cartao_para_viagem(plano)
        self.assertEqual(cartao["titulo"], "Plano de Trabalho 20/2026/ASCOM")
        self.assertEqual(cartao["detalhes"], "25/06/2026 a 27/06/2026 · Maringá/PR · PROGRAMA PARANÁ EM AÇÃO")
        self.assertEqual((cartao["selo"], cartao["metodo_documento"], cartao["cancelado"]), ("Rascunho", "post", False))
        for chave in ["pk", "url_editar", "url_visualizar", "url_pdf", "url_docx", "url_excluir", "selo_tom"]:
            self.assertIn(chave, cartao)

    def test_listar_por_viagem(self):
        from viagens_viagem.models import Viagem

        viagem = Viagem.objects.create(titulo="V")
        com = PlanoTrabalho.objects.create(numero=1, ano=2026, viagem=viagem)
        PlanoTrabalho.objects.create(numero=2, ano=2026)
        self.assertEqual(list(listar_planos(viagem=viagem)), [com])
