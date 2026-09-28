"""Multieventos: o mesmo evento em escolas diferentes da mesma cidade, em dias
encostados, vira uma viagem só com o plano de trabalho multieventos."""
from datetime import date

from django.urls import reverse

from solicitacoes import integracao_viagens as iv
from solicitacoes import services
from solicitacoes.models import DecisaoDG
from solicitacoes.tests import BaseSolicitacaoTestCase
from viagens_viagem.multieventos import encostam, eventos_vizinhos


class MultieventosTests(BaseSolicitacaoTestCase):
    def evento(self, inicio, fim=None, *, local, servidores=3):
        solicitacao = self.criar_solicitacao(data_inicio_evento=inicio, data_fim_evento=fim or inicio, local_evento=local)
        solicitacao.itens_servico.create(servico=self.servico)
        solicitacao.itens_equipe.create(equipe=self.equipe, quantidade_servidores=servidores)
        services.enviar(solicitacao, self.solicitante)
        return solicitacao

    def deferir(self, solicitacao):
        self.efetivar(services.despachar, solicitacao, self.gestor, DecisaoDG.ATENDER, observacao="Ok")
        return iv.viagem_da_solicitacao(solicitacao)

    def tres_escolas(self):
        return [
            self.evento(date(2026, 10, 6), local="Escola A", servidores=3),
            self.evento(date(2026, 10, 7), local="Escola B", servidores=4),
            self.evento(date(2026, 10, 8), date(2026, 10, 9), local="Escola C", servidores=2),
        ]

    def test_periodos_que_encostam(self):
        dia = lambda d: (date(2026, 10, d), date(2026, 10, d))
        self.assertTrue(encostam(dia(6), dia(7)))
        self.assertTrue(encostam(dia(6), dia(8)))  # um dia livre no meio ainda é a mesma viagem
        self.assertFalse(encostam(dia(6), dia(9)))
        self.assertTrue(encostam((date(2026, 10, 8), date(2026, 10, 9)), dia(7)))

    def test_antes_do_deferimento_a_tela_ja_sugere_juntar(self):
        a, b, c = self.tres_escolas()
        # 06 e 08 não encostam entre si, mas a de 07 liga as três.
        self.assertEqual(eventos_vizinhos(a), [b, c])
        self.client.force_login(self.solicitante)
        resposta = self.client.get(reverse("solicitacoes:editar", args=[a.pk]))
        self.assertContains(resposta, "viram <b>uma viagem só</b>")
        self.assertContains(resposta, f"Solicitação #{c.pk}")

    def test_tres_escolas_uma_viagem_so(self):
        a, b, c = self.tres_escolas()
        viagem = self.deferir(a)
        self.assertEqual(self.deferir(b), viagem)
        self.assertEqual(self.deferir(c), viagem)
        viagem.refresh_from_db()
        self.assertEqual((viagem.data_inicio, viagem.data_fim), (date(2026, 10, 6), date(2026, 10, 9)))
        self.assertIn("3 eventos", viagem.titulo)
        for solicitacao in (a, b, c):
            self.assertIn(f"Solicitação #{solicitacao.pk}", viagem.motivo)
            self.assertEqual(iv.viagens_da_solicitacao(solicitacao), [viagem])
        # A mesma equipe atende as três escolas: a meta é a maior, não a soma.
        self.assertEqual([p.quantidade for p in viagem.equipes_previstas.all()], [4])
        self.assertEqual(viagem.roteiros.filter(cancelado=False).count(), 1)
        self.assertIn("multieventos", viagem.roteiros.get().observacoes)

    def test_plano_de_trabalho_sai_multieventos_completo(self):
        from viagens_cadastros.models import Cargo
        from viagens_planos.services import criar_plano_rascunho, eventos_para_cards, scratchpad_tem_conteudo

        Cargo.objects.create(nome="AGENTE", is_padrao=True)
        a, b, c = self.tres_escolas()
        for solicitacao in (a, b, c):
            viagem = self.deferir(solicitacao)
        plano = criar_plano_rascunho(viagem)
        self.assertTrue(plano.is_multi_evento)
        eventos = list(plano.eventos.order_by("ordem"))
        self.assertEqual([(e.data_evento_inicio, e.data_evento_fim) for e in eventos], [
            (date(2026, 10, 6), date(2026, 10, 6)),
            (date(2026, 10, 7), date(2026, 10, 7)),
            (date(2026, 10, 8), date(2026, 10, 9)),
        ])
        for evento in eventos:
            self.assertEqual(evento.destino_principal.cidade, self.municipio)
            self.assertEqual(evento.programa_display, "Ação social")
            self.assertEqual(evento.total_efetivo, 4)
        # A tela do plano mostra os três como cartões, com o rascunho livre para mais um.
        self.assertEqual(len(eventos_para_cards(plano)), 3)
        self.assertFalse(scratchpad_tem_conteudo(plano))

    def test_evento_longe_das_datas_ganha_viagem_propria(self):
        a, _b, _c = self.tres_escolas()
        viagem = self.deferir(a)
        outro = self.evento(date(2026, 10, 20), local="Escola D")
        self.assertNotEqual(self.deferir(outro), viagem)

    def test_viagem_com_documento_nao_recebe_evento(self):
        from viagens_oficios.models import Oficio

        a, b, _c = self.tres_escolas()
        viagem = self.deferir(a)
        Oficio.objects.create(viagem=viagem)
        nova = self.deferir(b)
        self.assertNotEqual(nova, viagem)
        viagem.refresh_from_db()
        self.assertEqual(viagem.data_fim, date(2026, 10, 6))


class ViagensPendentesTests(BaseSolicitacaoTestCase):
    """Deferidas sem viagem (importadas da planilha, anteriores à integração) ganham a sua."""

    def deferida_sem_despacho(self, inicio, **extra):
        from solicitacoes.models import StatusSolicitacao

        solicitacao = self.criar_solicitacao(data_inicio_evento=inicio, data_fim_evento=inicio,
                                             status=StatusSolicitacao.DEFERIDA_EM_ANDAMENTO, **extra)
        solicitacao.itens_equipe.create(equipe=self.equipe, quantidade_servidores=2)
        return solicitacao

    def test_importada_deferida_ganha_viagem_e_evento_passado_nao(self):
        from django.core.management import call_command

        hoje = date(2026, 9, 28)
        futura = self.deferida_sem_despacho(date(2026, 10, 15))
        passada = self.deferida_sem_despacho(date(2026, 9, 1))
        self.assertEqual(iv.viagens_da_solicitacao(futura), [])
        self.assertEqual(iv.gerar_viagens_pendentes(hoje=hoje), 1)
        self.assertEqual(len(iv.viagens_da_solicitacao(futura)), 1)
        self.assertEqual(iv.viagens_da_solicitacao(passada), [])
        # Rodar de novo não duplica.
        self.assertEqual(iv.gerar_viagens_pendentes(hoje=hoje), 0)
        call_command("gerar_viagens_pendentes", stdout=__import__("io").StringIO())
        self.assertEqual(len(iv.viagens_da_solicitacao(futura)), 1)
