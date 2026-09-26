"""m063: a viagem nasce sozinha no deferimento, no ambiente de cada equipe.

"Evento X designado 2 ASCOM": a viagem nasce no ambiente ASCOM já com sede,
percurso, datas e anexos; um ofício com um servidor mostra que ainda falta
um; o segundo servidor (no mesmo ofício ou em outro) completa a meta.
"""

import tempfile
from datetime import date, timedelta

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from django.urls import reverse

from accounts.models import Modulo, Setor
from cadastros.models import Equipe, Municipio
from solicitacoes import integracao_viagens as iv
from solicitacoes import services
from solicitacoes.models import AnexoSolicitacao, DecisaoDG
from solicitacoes.tests import BaseSolicitacaoTestCase
from viagens_cadastros.models import ConfiguracaoSistema, Servidor, Unidade
from viagens_oficios.models import Oficio
from viagens_viagem.meta_equipe import contador_de_servidores
from viagens_viagem.models import TipoViagem, ViagemDocumentoSolicitacao


class ViagemPorAmbienteTests(BaseSolicitacaoTestCase):
    def setUp(self):
        pasta = tempfile.TemporaryDirectory()
        self.addCleanup(pasta.cleanup)
        self.enterContext(override_settings(MEDIA_ROOT=pasta.name))
        self.setor = Setor.objects.create(nome="Assessoria de Comunicação", sigla="ASCOM")
        Modulo.objects.get(codigo="VIAGENS").setores.add(self.setor)
        self.ascom = Equipe.objects.create(nome="ASCOM")
        self.sede = Municipio.objects.create(nome="Sede Teste", estado=self.estado, regiao=self.regiao)
        self.unidade = Unidade.objects.create(nome="Assessoria de Comunicação Social", sigla="ASCOM")
        ConfiguracaoSistema.objects.create(
            setor=self.setor, cidade_sede_padrao=self.sede, prazo_justificativa_dias=10
        )
        self.servidor_a = Servidor.objects.create(nome="SERVIDORA A", unidade=self.unidade)
        self.servidor_b = Servidor.objects.create(nome="SERVIDOR B", unidade=self.unidade)

    def _deferida(self, **kwargs):
        solicitacao = self.criar_solicitacao(**kwargs)
        solicitacao.itens_servico.create(servico=self.servico)
        solicitacao.itens_equipe.create(equipe=self.ascom, quantidade_servidores=2)
        services.enviar(solicitacao, self.solicitante)
        self.efetivar(services.despachar, solicitacao, self.gestor, DecisaoDG.ATENDER)
        return solicitacao

    def test_deferimento_gera_a_viagem_no_ambiente_da_equipe(self):
        solicitacao = self._deferida()
        viagem = iv.viagem_da_solicitacao(solicitacao)
        self.assertIsNotNone(viagem)
        self.assertEqual(viagem.setor, self.setor)
        self.assertEqual(viagem.unidade_responsavel, self.unidade)
        self.assertIn("(ASCOM)", viagem.titulo)
        prevista = viagem.equipes_previstas.get()
        self.assertEqual((prevista.equipe, prevista.quantidade), (self.ascom, 2))

    def test_sede_e_trechos_de_ida_e_volta_vem_da_configuracao_do_setor(self):
        solicitacao = self._deferida()
        roteiro = iv.viagem_da_solicitacao(solicitacao).roteiros.get()
        self.assertEqual(roteiro.origem_municipio, self.sede)
        self.assertEqual(roteiro.quantidade_servidores, 2)
        trechos = list(roteiro.trechos.order_by("ordem"))
        self.assertEqual([t.sentido for t in trechos], ["IDA", "RETORNO"])
        self.assertEqual(trechos[0].origem_municipio, self.sede)
        self.assertEqual(trechos[1].destino_municipio, self.sede)
        self.assertIsNotNone(roteiro.saida_dt)
        self.assertNotIn("Data e hora da saída", iv.o_que_falta(roteiro.viagem))

    def test_equipe_sem_setor_vai_para_outra_viagem(self):
        solicitacao = self.criar_solicitacao()
        solicitacao.itens_servico.create(servico=self.servico)
        solicitacao.itens_equipe.create(equipe=self.ascom, quantidade_servidores=2)
        solicitacao.itens_equipe.create(equipe=self.equipe, quantidade_servidores=1)
        services.enviar(solicitacao, self.solicitante)
        self.efetivar(services.despachar, solicitacao, self.gestor, DecisaoDG.ATENDER)
        viagens = iv.viagens_da_solicitacao(solicitacao)
        self.assertEqual([v.setor for v in viagens], [self.setor, None])
        self.assertEqual(
            [p.equipe for p in viagens[1].equipes_previstas.all()], [self.equipe]
        )

    def test_contador_mostra_quantos_faltam_ate_bater_a_meta(self):
        solicitacao = self._deferida()
        viagem = iv.viagem_da_solicitacao(solicitacao)
        self.assertEqual(contador_de_servidores(viagem)["faltam"], 2)

        primeiro = Oficio.objects.create(viagem=viagem, motivo="Evento")
        primeiro.servidores.add(self.servidor_a)
        contador = contador_de_servidores(viagem)
        self.assertEqual(contador["faltam"], 1)
        self.assertEqual(contador["texto"], "Falta 1 servidor da ASCOM.")
        self.assertIn("Falta 1 servidor da ASCOM.", iv.o_que_falta(viagem))

        # Ofício cancelado não conta.
        cancelado = Oficio.objects.create(viagem=viagem, motivo="Evento", cancelado=True)
        cancelado.servidores.add(self.servidor_b)
        self.assertEqual(contador_de_servidores(viagem)["faltam"], 1)

        # Outro ofício com o segundo servidor completa a meta.
        segundo = Oficio.objects.create(viagem=viagem, motivo="Evento")
        segundo.servidores.add(self.servidor_b, self.servidor_a)
        contador = contador_de_servidores(viagem)
        self.assertEqual((contador["faltam"], contador["em_oficios"]), (0, 2))
        self.assertTrue(contador["completo"])

    def test_cartao_da_solicitacao_e_lista_de_viagens_mostram_o_contador(self):
        from django.contrib.auth.models import Group

        solicitacao = self._deferida()
        viagem = iv.viagem_da_solicitacao(solicitacao)
        Oficio.objects.create(viagem=viagem, motivo="Evento").servidores.add(self.servidor_a)

        self.client.force_login(self.gestor)
        resposta = self.client.get(reverse("solicitacoes:editar", args=[solicitacao.pk]))
        self.assertContains(resposta, "Falta 1 servidor da ASCOM.")
        self.assertContains(resposta, "Ambiente ASCOM")
        self.assertNotContains(resposta, "Tentar de novo")

        self.gestor.groups.add(Group.objects.get(name="VIAGENS_OPERADOR"))
        self.gestor.setores.add(self.setor)
        lista = self.client.get(reverse("viagens_viagem:lista"))
        self.assertContains(lista, "Falta 1 servidor")
        painel = self.client.get(reverse("viagens_viagem:painel", args=[viagem.pk]), follow=True)
        self.assertContains(painel, "data-meta-da-solicitacao")
        self.assertContains(painel, "Falta 1 servidor da ASCOM.")

    def test_data_limite_do_oficio_sem_justificativa(self):
        solicitacao = self._deferida()
        viagem = iv.viagem_da_solicitacao(solicitacao)
        self.assertEqual(
            iv.data_limite_sem_justificativa(viagem),
            solicitacao.data_inicio_evento - timedelta(days=11),
        )

    def test_novo_deferimento_atualiza_a_meta(self):
        solicitacao = self._deferida()
        viagem = iv.viagem_da_solicitacao(solicitacao)
        Oficio.objects.create(viagem=viagem, motivo="Evento")  # documento emitido
        solicitacao.itens_equipe.filter(equipe=self.ascom).update(quantidade_servidores=3)
        iv.sincronizar_viagem(solicitacao, self.gestor)
        self.assertEqual(viagem.equipes_previstas.get().quantidade, 3)

    def test_anexos_tipo_de_viagem_unidade_movel_e_motorista(self):
        TipoViagem.objects.create(nome="AÇÃO SOCIAL")
        solicitacao = self.criar_solicitacao(
            unidade_movel=True, unidade_movel_designada=self.van, motorista=self.motorista
        )
        solicitacao.itens_servico.create(servico=self.servico)
        solicitacao.itens_equipe.create(equipe=self.ascom, quantidade_servidores=2)
        AnexoSolicitacao.objects.create(
            solicitacao=solicitacao, nome_original="convite.pdf",
            arquivo=SimpleUploadedFile("convite.pdf", b"%PDF-1.4 teste", content_type="application/pdf"),
        )
        AnexoSolicitacao.objects.create(
            solicitacao=solicitacao, nome_original="planilha.xlsx",
            arquivo=SimpleUploadedFile("planilha.xlsx", b"x"),
        )
        services.enviar(solicitacao, self.solicitante)
        self.efetivar(services.despachar, solicitacao, self.gestor, DecisaoDG.ATENDER)
        viagem = iv.viagem_da_solicitacao(solicitacao)

        documentos = list(ViagemDocumentoSolicitacao.objects.filter(viagem=viagem))
        self.assertEqual([d.nome_original for d in documentos], ["convite.pdf"])
        # Cópia, não o mesmo arquivo: apagar o anexo não leva o da viagem.
        self.assertNotEqual(documentos[0].arquivo.name, solicitacao.anexos.first().arquivo.name)
        self.assertEqual([t.nome for t in viagem.tipos.all()], ["AÇÃO SOCIAL"])
        observacoes = viagem.roteiros.get().observacoes
        self.assertIn("Unidade móvel designada: Van CIN 01", observacoes)
        self.assertIn(f"Motorista designado: {self.motorista.nome}", observacoes)

        from viagens_viagem.services import semente_de_documentos

        self.assertEqual(semente_de_documentos(viagem)["motorista"], self.motorista)

    def test_sem_setor_correspondente_continua_uma_viagem_so(self):
        solicitacao = self.solicitacao_completa()  # "Equipe Alfa", sem setor
        services.enviar(solicitacao, self.solicitante)
        self.efetivar(services.despachar, solicitacao, self.gestor, DecisaoDG.ATENDER)
        viagens = iv.viagens_da_solicitacao(solicitacao)
        self.assertEqual(len(viagens), 1)
        self.assertIsNone(viagens[0].setor)
        self.assertEqual(contador_de_servidores(viagens[0])["previstos"], 5)

    def test_sem_viagem_o_cartao_oferece_tentar_de_novo(self):
        solicitacao = self.criar_solicitacao(data_inicio_evento=None, data_fim_evento=None)
        solicitacao.status = "DEFERIDA_EM_ANDAMENTO"
        solicitacao.decisao_dg = DecisaoDG.ATENDER
        solicitacao.save()
        solicitacao.data_inicio_evento = date(2026, 9, 10)
        solicitacao.save()
        self.client.force_login(self.gestor)
        resposta = self.client.get(reverse("solicitacoes:editar", args=[solicitacao.pk]))
        self.assertContains(resposta, "Tentar de novo")
