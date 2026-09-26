"""As telas da OS: lista com situações e busca, cadastro numa página, ações e documentos."""

from datetime import timedelta

from django.test import TestCase
from django.urls import NoReverseMatch, reverse

from documentos.models import DocumentoArtefato
from viagens_ordens.models import OrdemServico, OrdemServicoNumeroLacuna
from viagens_ordens.selectors import listar_ordens

from .fixtures import CenarioOrdemMixin


def _lista(cliente, **params):
    return cliente.get(reverse("viagens_ordens:lista"), params)


class ListaTests(CenarioOrdemMixin, TestCase):
    def test_lista_mostra_titulo_selos_fatos_e_menu(self):
        o = self.oficio(servidores=[self.a, self.b], motorista=self.a)
        ordem = self.ordem(servidores=[self.a, self.b], oficios=[o], motivo="Cobertura " * 60)
        r = _lista(self.client)
        self.assertContains(r, "Ordens de Serviço")
        self.assertContains(r, "Nova OS")
        self.assertContains(r, f'id="os-{ordem.pk}-titulo">{ordem.numero_formatado} · Londrina (PR) · ')
        self.assertContains(r, "faltam 3 dias")
        self.assertContains(r, "ANA TESTE (motorista), BRUNO TESTE")
        self.assertContains(r, reverse("viagens_oficios:editar", args=[o.pk]))
        self.assertContains(r, "BRUNO TESTE · INVESTIGADOR")  # assinante
        self.assertContains(r, "…")  # motivo cortado em 240
        for texto in ["Visualizar", "Baixar PDF", "Anexar assinado", "Editar", "Cancelar", "Excluir"]:
            self.assertContains(r, texto)
        self.assertContains(r, reverse("viagens_ordens:gerar", args=[ordem.pk, "pdf"]) + "?inline=1")
        self.assertEqual(r.context["situacoes"][0]["total"], 1)

    def test_vazios_nomeados_e_sem_data_vai_para_que_vao_acontecer(self):
        ordem = self.ordem(dias=None, destinos=[], motivo="")
        r = _lista(self.client)
        for texto in ["Sem período", "Sem destino", "Nenhum servidor informado", "Sem ofício vinculado", "Nenhum motivo informado"]:
            self.assertContains(r, texto)
        self.assertIn(ordem, listar_ordens(situacoes=["futuras"]))
        self.assertNotIn(ordem, listar_ordens(situacoes=["atuais"]))

    def test_abas_e_busca(self):
        futura = self.ordem(dias=3, servidores=[self.a])
        passada = self.ordem(dias=-10, servidores=[self.b], motivo="Operação antiga")
        cancelada = self.ordem(dias=2, cancelar=True)
        self.assertEqual(list(listar_ordens(situacoes=["futuras"])), [futura])
        self.assertEqual(list(listar_ordens(situacoes=["atuais"])), [passada])
        self.assertEqual(list(listar_ordens(situacoes=["cancelados"])), [cancelada])
        self.assertEqual(list(listar_ordens("BRUNO")), [passada])
        self.assertEqual(list(listar_ordens("antiga")), [passada])
        self.assertEqual(list(listar_ordens(str(futura.numero))), [futura])
        self.assertEqual(list(listar_ordens("Londrina")), [cancelada, passada, futura])
        r = _lista(self.client, situacao="cancelados")
        self.assertContains(r, "Cancelada")
        self.assertContains(r, "Reativar")
        self.assertEqual(r.context["situacao_ativa"], "cancelados")

    def test_leitor_ve_abrir_e_nao_grava(self):
        ordem = self.ordem()
        self.user.groups.clear()
        r = _lista(self.client)
        self.assertContains(r, "Abrir")
        self.assertNotContains(r, "Nova OS")
        self.assertEqual(self.client.get(reverse("viagens_ordens:editar", args=[ordem.pk])).status_code, 200)
        self.assertEqual(self.client.post(reverse("viagens_ordens:editar", args=[ordem.pk]), self.payload()).status_code, 403)
        self.assertEqual(self.client.get(reverse("viagens_ordens:novo")).status_code, 403)


class CadastroTests(CenarioOrdemMixin, TestCase):
    def test_tela_nova_segue_o_molde_do_termo_e_sem_aviso(self):
        r = self.client.get(reverse("viagens_ordens:novo"))
        html = r.content.decode()
        self.assertContains(r, "Nova Ordem de Serviço")
        posicoes = [html.index(t) for t in ["Destino e período", "Sem ofício vinculado", ">Período<", ">Destinos<", "Necessidade e motivo", "Modelo de motivo", ">Equipe<"]]
        self.assertEqual(posicoes, sorted(posicoes))
        for texto in ["Padrão / texto livre", "Operação policial - um dia posterior",
                      "Cerimonial - ida antecipada", "Mantém o texto livre usado nas OS atuais.", "Modelo de motivo", "Gerenciar modelos",
                      "Novo viajante", "Salvar como rascunho", "Voltar", 'name="funcao_servidor_']:
            self.assertContains(r, texto) if not texto.startswith("name=") else self.assertNotContains(r, texto)
        self.assertNotContains(r, "aviso--erro")
        self.assertNotContains(r, "Finalizar Ordem de Serviço")
        # Sem modelos, o seletor desabilitado não herda o dicionário de erros da página.
        self.assertNotContains(r, "<p class=\"form-erro\">data_evento_inicio</p>")
        self.assertContains(r, reverse("viagens_cadastros:lista", args=["motivos-oficio"]))
        self.assertContains(r, reverse("viagens_cadastros:novo", args=["servidores"]))
        self.assertContains(r, 'value="PADRAO" checked')
        # Só três necessidades na tela nova; caminhão e micro-ônibus ficam para as OS antigas.
        self.assertNotContains(r, 'value="CAMINHAO"')
        self.assertNotContains(r, 'value="MICROONIBUS"')

    def test_ordem_dos_destinos_definida_na_tela_e_mantida(self):
        """m069: Maringá primeiro fica primeiro — na tela reaberta, na lista e no documento."""
        from viagens_ordens.docxtpl_context import _destinos_display

        dados = self.payload(
            destino_cidade=str(self.outro.pk), quantidade_destinos="1",
            extra_estado_0=str(self.uf.pk), extra_cidade_0=str(self.destino.pk),
        )
        self.client.post(reverse("viagens_ordens:novo"), dados)
        ordem = OrdemServico.objects.get()
        self.assertEqual(list(ordem.destinos_em_ordem()), [self.outro, self.destino])
        self.assertTrue(_destinos_display(ordem).startswith("Maringá"))
        r = self.client.get(reverse("viagens_ordens:editar", args=[ordem.pk]))
        self.assertEqual(r.context["form"].initial["destino_cidade"], self.outro.pk)
        self.assertContains(_lista(self.client), "Maringá (PR), Londrina (PR)")

    def test_criar_pela_tela_com_destino_extra_e_funcoes(self):
        o = self.oficio(servidores=[self.a])
        dados = self.payload(
            oficios=[str(o.pk)], tipo_necessidade=OrdemServico.TIPO_CAMINHAO, quantidade_destinos="1",
            extra_estado_0=str(self.uf.pk), extra_cidade_0=str(self.outro.pk),
            **{f"funcao_servidor_{self.a.pk}": "CONDUCAO", f"funcao_servidor_{self.b.pk}": "APOIO", f"funcao_servidor_{self.c.pk}": "TECNICO"},
        )
        r = self.client.post(reverse("viagens_ordens:novo"), dados)
        self.assertRedirects(r, reverse("viagens_ordens:lista"), fetch_redirect_response=False)
        ordem = OrdemServico.objects.get()
        self.assertEqual(ordem.numero, 1)
        self.assertEqual(ordem.ano, self.hoje.year)
        self.assertEqual(set(ordem.destinos.all()), {self.destino, self.outro})
        self.assertEqual(set(ordem.servidores.all()), {self.a, self.b})
        self.assertEqual(list(ordem.oficios.all()), [o])
        # A função de quem não está na equipe (Carla) cai.
        self.assertEqual(ordem.funcoes_servidores, {str(self.a.pk): "CONDUCAO", str(self.b.pk): "APOIO"})
        r = _lista(self.client)
        self.assertContains(r, "Ordem de Serviço cadastrada.")

    def test_tipo_padrao_nao_grava_funcoes(self):
        self.client.post(reverse("viagens_ordens:novo"), self.payload(**{f"funcao_servidor_{self.a.pk}": "CONDUCAO"}))
        self.assertEqual(OrdemServico.objects.get().funcoes_servidores, {})

    def test_erros_so_depois_do_post(self):
        r = self.client.post(reverse("viagens_ordens:novo"), self.payload(destino_cidade="", data_evento_fim=(self.hoje).isoformat()))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "Não foi possível salvar a Ordem de Serviço")
        self.assertContains(r, "Informe a cidade do destino.")
        self.assertContains(r, "A data final não pode ser anterior à inicial.")
        self.assertFalse(OrdemServico.objects.exists())

    def test_editar_mostra_so_titulo_e_selo_e_grava(self):
        ordem = self.ordem(servidores=[self.a])
        r = self.client.get(reverse("viagens_ordens:editar", args=[ordem.pk]))
        self.assertContains(r, f"Editar <span class=\"frm-ident\">{ordem.numero_formatado}</span>")
        self.assertContains(r, "faltam 3 dias")
        self.assertContains(r, "Finalizar Ordem de Serviço")  # completa: período, destino, equipe, tipo e motivo
        self.assertNotContains(r, "frm-meta")
        r = self.client.post(reverse("viagens_ordens:editar", args=[ordem.pk]), self.payload(motivo="Motivo novo", servidores=[str(self.c.pk)]))
        self.assertRedirects(r, reverse("viagens_ordens:lista"), fetch_redirect_response=False)
        ordem.refresh_from_db()
        self.assertEqual(ordem.motivo, "Motivo novo")
        self.assertEqual(list(ordem.servidores.all()), [self.c])
        self.assertEqual(ordem.numero, 1)  # editar não renumera
        self.assertContains(_lista(self.client), "Ordem de Serviço atualizada.")

    def test_next_e_respeitado(self):
        destino = reverse("viagens_ordens:lista") + "?q=x"
        r = self.client.post(reverse("viagens_ordens:novo"), self.payload(next=destino))
        self.assertRedirects(r, destino, fetch_redirect_response=False)

    def test_oficio_cancelado_ja_vinculado_continua_na_tela(self):
        cancelado = self.oficio(cancelar=True)
        livre = self.oficio()
        ordem = self.ordem(oficios=[cancelado])
        # A busca é pela caixa do ofício: "value=1" solto casa com qualquer
        # outro campo da página quando o id gerado é baixo.
        r = self.client.get(reverse("viagens_ordens:editar", args=[ordem.pk]))
        self.assertContains(r, f'name="oficios" value="{cancelado.pk}" checked')
        self.assertContains(r, f'name="oficios" value="{livre.pk}"')
        r = self.client.get(reverse("viagens_ordens:novo"))
        self.assertNotContains(r, f'name="oficios" value="{cancelado.pk}"')

    def test_modelo_de_motivo_vai_para_a_tela(self):
        from viagens_oficios.models import ModeloMotivoOficio
        m = ModeloMotivoOficio.objects.create(nome="Cobertura", texto="Texto do modelo")
        r = self.client.get(reverse("viagens_ordens:novo"))
        self.assertContains(r, "COBERTURA")
        self.assertEqual(r.context["modelos_texto"][str(m.pk)], "Texto do modelo")
        self.assertContains(r, 'id="os-modelos-texto"')


class ViagemTests(CenarioOrdemMixin, TestCase):
    def _viagem(self):
        from viagens_viagem.models import Viagem
        return Viagem.objects.create(titulo="Viagem X", data_inicio=self.hoje, data_fim=self.hoje, motivo="Motivo da viagem",
                                     destino_estado=self.uf, destino_municipio=self.outro)

    def _etapa(self, viagem):
        try:
            return reverse("viagens_viagem:etapa", args=[viagem.pk, 4])
        except NoReverseMatch:
            return reverse("viagens_ordens:lista")

    def test_nova_a_partir_da_viagem_vem_semeada_e_volta_para_a_etapa(self):
        viagem = self._viagem()
        o = self.oficio(servidores=[self.a, self.b])
        o.viagem = viagem
        o.save(update_fields=["viagem"])
        r = self.client.get(reverse("viagens_ordens:novo") + f"?viagem={viagem.pk}")
        self.assertContains(r, f'name="viagem" value="{viagem.pk}"')
        self.assertContains(r, "Motivo da viagem")
        self.assertEqual(r.context["valores"]["data_evento_inicio"], self.hoje.isoformat())
        self.assertEqual(r.context["valores"]["destino_cidade"], str(self.outro.pk))
        self.assertContains(r, f'value="{o.pk}" checked')
        self.assertContains(r, f'value="{self.a.pk}" checked')
        r = self.client.post(reverse("viagens_ordens:novo") + f"?viagem={viagem.pk}", self.payload(viagem=str(viagem.pk)))
        self.assertRedirects(r, self._etapa(viagem), fetch_redirect_response=False)
        ordem = OrdemServico.objects.get()
        self.assertEqual(ordem.viagem, viagem)
        self.assertEqual(list(listar_ordens(viagem=viagem)), [ordem])
        self.assertEqual(listar_ordens(viagem=self._viagem()).count(), 0)


class AcoesTests(CenarioOrdemMixin, TestCase):
    def test_cancelar_reativar_excluir(self):
        ordem = self.ordem()
        numero = ordem.numero_formatado
        r = self.client.post(reverse("viagens_ordens:acao", args=[ordem.pk, "cancelar"]), {"motivo": "Chuva"})
        self.assertRedirects(r, reverse("viagens_ordens:lista"), fetch_redirect_response=False)
        ordem.refresh_from_db()
        self.assertTrue(ordem.cancelado)
        r = _lista(self.client)
        self.assertContains(r, f"Ordem de Serviço {numero} cancelada. O histórico foi mantido.")
        r = self.client.get(reverse("viagens_ordens:editar", args=[ordem.pk]))
        self.assertContains(r, "Ordem de Serviço cancelada")
        self.assertContains(r, "Chuva")
        self.client.post(reverse("viagens_ordens:acao", args=[ordem.pk, "reativar"]))
        ordem.refresh_from_db()
        self.assertFalse(ordem.cancelado)
        self.assertContains(_lista(self.client), f"Ordem de Serviço {numero} reativada.")
        self.client.post(reverse("viagens_ordens:acao", args=[ordem.pk, "excluir"]))
        self.assertFalse(OrdemServico.objects.filter(pk=ordem.pk).exists())
        self.assertTrue(OrdemServicoNumeroLacuna.objects.filter(ano=ordem.ano, numero=ordem.numero).exists())
        self.assertContains(_lista(self.client), f"Ordem de Serviço {numero} excluída.")

    def test_acao_desconhecida(self):
        ordem = self.ordem()
        self.assertEqual(self.client.post(reverse("viagens_ordens:acao", args=[ordem.pk, "sumir"])).status_code, 404)


class DocumentoTests(CenarioOrdemMixin, TestCase):
    def test_gerar_docx_e_pdf(self):
        ordem = self.ordem(servidores=[self.a, self.b])
        r = self.client.post(reverse("viagens_ordens:gerar", args=[ordem.pk, "docx"]))
        self.assertEqual(r.status_code, 200)
        self.assertIn("wordprocessingml", r["Content-Type"])
        r = self.client.post(reverse("viagens_ordens:gerar", args=[ordem.pk, "pdf"]))
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r["Content-Type"], "application/pdf")
        self.assertIn("attachment", r["Content-Disposition"])
        r = self.client.post(reverse("viagens_ordens:gerar", args=[ordem.pk, "pdf"]) + "?inline=1")
        self.assertEqual(r.status_code, 200)
        self.assertIn("inline", r["Content-Disposition"])
        art = DocumentoArtefato.objects.get(ordem_servico=ordem, formato="pdf")
        self.assertEqual(art.tipo, "ordem_servico")
        # Com PDF gerado, a lista oferece anexar o assinado pela rota da OS.
        url = reverse("viagens_ordens:assinatura_artefato", args=[art.pk])
        self.assertContains(_lista(self.client), url)
        r = self.client.get(url)
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, reverse("viagens_ordens:editar", args=[ordem.pk]))

    def test_modelo_docx_segue_o_tipo(self):
        from viagens_ordens.services import _template_ordem_servico
        self.assertEqual(_template_ordem_servico(self.ordem()), "ordem_servico.docx")
        self.assertEqual(_template_ordem_servico(self.ordem(tipo=OrdemServico.TIPO_CAMINHAO)), "ordem_servico_modelos.docx")

    def test_cancelada_nao_gera(self):
        ordem = self.ordem(cancelar=True)
        r = self.client.post(reverse("viagens_ordens:gerar", args=[ordem.pk, "pdf"]))
        self.assertEqual(r.status_code, 302)
        self.assertContains(_lista(self.client), "Reative a Ordem de Serviço antes de gerar documentos.")
        self.assertFalse(DocumentoArtefato.objects.filter(ordem_servico=ordem).exists())

    def test_formato_invalido(self):
        ordem = self.ordem()
        self.assertEqual(self.client.post(reverse("viagens_ordens:gerar", args=[ordem.pk, "txt"])).status_code, 404)


class ApiOficiosTests(CenarioOrdemMixin, TestCase):
    def test_busca_devolve_resumo_no_formato_da_tela(self):
        o = self.oficio(servidores=[self.a], protocolo="987654321")
        self.oficio(cancelar=True)
        r = self.client.get(reverse("viagens_ordens:api_buscar_oficios"), {"q": "ANA"})
        dados = r.json()
        self.assertEqual([x["id"] for x in dados["resultados"]], [o.pk])
        resumo = dados["resultados"][0]
        self.assertEqual(resumo["label"], f"Ofício {o.numero_formatado}")
        self.assertEqual(resumo["servidor_ids"], [self.a.pk])
        self.assertEqual(resumo["cidade_id"], self.destino.pk)
        self.assertEqual(resumo["estado_id"], self.uf.pk)
        self.assertEqual(resumo["data_inicio"], (self.hoje + timedelta(days=3)).isoformat())
        self.assertEqual(resumo["motivo"], "Missão do ofício")
        self.assertIn("Curitiba/PR -> Londrina/PR", resumo["roteiro"])
        # Sem busca vêm todos os não cancelados.
        self.assertEqual(len(self.client.get(reverse("viagens_ordens:api_buscar_oficios")).json()["resultados"]), 1)
