"""A agenda — o que cada pessoa vê, e o que o calendário recebe."""

from datetime import date

from django.contrib.auth import get_user_model
from django.urls import reverse

from solicitacoes.models import DecisaoDG, StatusSolicitacao
from solicitacoes.tests import BaseSolicitacaoTestCase
from viagens_viagem.models import Viagem

from . import fontes

User = get_user_model()


def _eventos(client, inicio="2026-09-01", fim="2026-10-01", **extra):
    params = {"start": inicio, "end": fim}
    params.update(extra)
    return client.get(reverse("agenda:eventos"), params)


class AcessoAAgenda(BaseSolicitacaoTestCase):
    def test_anonimo_vai_para_o_login(self):
        for nome in ("agenda:painel", "agenda:eventos"):
            resposta = self.client.get(reverse(nome))
            self.assertEqual(resposta.status_code, 302, nome)
            self.assertIn("entrar", resposta["Location"])

    def test_painel_carrega_o_calendario_vendorizado(self):
        self.client.force_login(self.solicitante)
        resposta = self.client.get(reverse("agenda:painel"))
        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, "vendor/fullcalendar/index.global.min.js")
        self.assertContains(resposta, "pt-br.global.min.js")
        self.assertContains(resposta, 'data-url-eventos="' + reverse("agenda:eventos"))

    def test_periodo_invalido_ou_grande_demais_e_recusado(self):
        self.client.force_login(self.solicitante)
        self.assertEqual(self.client.get(reverse("agenda:eventos")).status_code, 400)
        self.assertEqual(_eventos(self.client, "2026-09-10", "2026-09-01").status_code, 400)
        self.assertEqual(_eventos(self.client, "2026-01-01", "2028-01-01").status_code, 400)
        # A borda: um ano e pouco passa, porque a visão anual precisa disso.
        self.assertEqual(_eventos(self.client, "2026-01-01", "2027-01-31").status_code, 200)


class OQueCadaUmVe(BaseSolicitacaoTestCase):
    """As fontes respeitam a permissão do módulo de origem, não uma cópia dela."""

    def setUp(self):
        super().setUp()
        self.minha = self.criar_solicitacao(criado_por=self.solicitante)
        self.de_outro = self.criar_solicitacao(criado_por=self.gestor)
        self.viagem = Viagem.objects.create(
            titulo="Teste",
            destino_municipio=self.municipio,
            destino_estado=self.municipio.estado,
            data_inicio=date(2026, 9, 10),
            data_fim=date(2026, 9, 12),
        )

    def test_solicitante_ve_so_o_proprio_dossie(self):
        self.client.force_login(self.solicitante)
        lista = _eventos(self.client).json()
        ids = {e["id"] for e in lista}
        self.assertIn(f"solicitacao-{self.minha.pk}", ids)
        self.assertNotIn(f"solicitacao-{self.de_outro.pk}", ids)

    def test_sem_o_modulo_viagens_a_fonte_nem_aparece(self):
        """Nem no filtro, nem pedindo pelo nome: pedir não é o que abre a porta."""
        self.client.force_login(self.solicitante)
        self.assertNotIn("viagem", {f.slug for f in fontes.fontes_de(self.solicitante)})
        lista = _eventos(self.client, fontes="viagem").json()
        self.assertEqual([e for e in lista if e["extendedProps"]["fonte"] == "viagem"], [])

    def test_superusuario_ve_todas_as_fontes(self):
        root = User.objects.create_superuser("agenda_root", "agenda_root@example.com", None)
        self.client.force_login(root)
        slugs = {f.slug for f in fontes.fontes_de(root)}
        self.assertEqual(slugs, {"viagem", "solicitacao", "coffee", "demanda"})
        ids = {e["id"] for e in _eventos(self.client).json()}
        self.assertIn(f"viagem-{self.viagem.pk}", ids)
        self.assertIn(f"solicitacao-{self.de_outro.pk}", ids)

    def test_filtro_por_fonte_restringe_o_que_volta(self):
        root = User.objects.create_superuser("agenda_root2", "agenda_root2@example.com", None)
        self.client.force_login(root)
        lista = _eventos(self.client, fontes="solicitacao").json()
        self.assertTrue(lista)
        self.assertEqual({e["extendedProps"]["fonte"] for e in lista}, {"solicitacao"})


class FormatoDoCalendario(BaseSolicitacaoTestCase):
    def setUp(self):
        super().setUp()
        self.client.force_login(self.solicitante)

    def test_fim_e_exclusivo(self):
        """Evento de 10 a 11 chega como end=12 — senão perde um dia na tela."""
        s = self.criar_solicitacao(
            criado_por=self.solicitante,
            data_inicio_evento=date(2026, 9, 10),
            data_fim_evento=date(2026, 9, 11),
        )
        (ev,) = [e for e in _eventos(self.client).json() if e["id"] == f"solicitacao-{s.pk}"]
        self.assertEqual(ev["start"], "2026-09-10")
        self.assertEqual(ev["end"], "2026-09-12")
        self.assertTrue(ev["allDay"])

    def test_evento_de_um_dia_sem_fim_ocupa_um_dia(self):
        s = self.criar_solicitacao(
            criado_por=self.solicitante,
            data_inicio_evento=date(2026, 9, 20),
            data_fim_evento=None,
        )
        (ev,) = [e for e in _eventos(self.client).json() if e["id"] == f"solicitacao-{s.pk}"]
        self.assertEqual(ev["end"], "2026-09-21")

    def test_fora_do_periodo_nao_vem(self):
        s = self.criar_solicitacao(criado_por=self.solicitante, data_inicio_evento=date(2026, 12, 1), data_fim_evento=date(2026, 12, 2))
        ids = {e["id"] for e in _eventos(self.client, "2026-09-01", "2026-10-01").json()}
        self.assertNotIn(f"solicitacao-{s.pk}", ids)

    def test_evento_que_atravessa_a_borda_do_mes_vem(self):
        s = self.criar_solicitacao(criado_por=self.solicitante, data_inicio_evento=date(2026, 9, 29), data_fim_evento=date(2026, 10, 2))
        ids = {e["id"] for e in _eventos(self.client, "2026-10-01", "2026-11-01").json()}
        self.assertIn(f"solicitacao-{s.pk}", ids)

    def test_cancelada_vem_marcada_como_encerrada(self):
        """A tela esconde por padrão e deixa mostrar — nunca some em silêncio."""
        s = self.criar_solicitacao(criado_por=self.solicitante)
        s.status = StatusSolicitacao.CANCELADA
        s.decisao_dg = DecisaoDG.CANCELADO
        s.save()
        (ev,) = [e for e in _eventos(self.client).json() if e["id"] == f"solicitacao-{s.pk}"]
        self.assertTrue(ev["extendedProps"]["encerrado"])
        self.assertIn("ag-encerrado", ev["classNames"])

    def test_detalhes_e_link_para_a_tela(self):
        s = self.criar_solicitacao(criado_por=self.solicitante)
        (ev,) = [e for e in _eventos(self.client).json() if e["id"] == f"solicitacao-{s.pk}"]
        props = ev["extendedProps"]
        self.assertEqual(props["url"], reverse("solicitacoes:editar", args=[s.pk]))
        rotulos = {rotulo for rotulo, _ in props["detalhes"]}
        self.assertIn("Município", rotulos)
        self.assertIn("Local", rotulos)
        # Detalhe vazio não vira linha em branco na gaveta.
        self.assertTrue(all(valor for _, valor in props["detalhes"]))


class DossieDoCompromisso(BaseSolicitacaoTestCase):
    """O modal pede o dossiê ao servidor — e a permissão mora lá."""

    def setUp(self):
        super().setUp()
        self.minha = self.criar_solicitacao(criado_por=self.solicitante)
        self.minha.itens_equipe.create(equipe=self.equipe, quantidade_servidores=3)
        self.de_outro = self.criar_solicitacao(criado_por=self.gestor)
        self.viagem = Viagem.objects.create(
            titulo="Teste",
            destino_municipio=self.municipio,
            destino_estado=self.municipio.estado,
            data_inicio=date(2026, 9, 10),
            data_fim=date(2026, 9, 12),
            motivo="Operação de teste",
        )

    def _detalhe(self, fonte, pk):
        return self.client.get(reverse("agenda:detalhe", args=[fonte, pk]))

    def test_e_um_fragmento_sem_o_shell(self):
        self.client.force_login(self.solicitante)
        resposta = self._detalhe("solicitacao", self.minha.pk)
        self.assertEqual(resposta.status_code, 200)
        self.assertNotContains(resposta, "<html")
        self.assertContains(resposta, 'data-fonte="solicitacao"')
        self.assertContains(resposta, "Abrir no sistema")

    def test_solicitacao_traz_equipes_historico_e_link_da_tela(self):
        self.client.force_login(self.solicitante)
        resposta = self._detalhe("solicitacao", self.minha.pk)
        self.assertContains(resposta, "Equipes autorizadas")
        self.assertContains(resposta, str(self.equipe))
        self.assertContains(resposta, reverse("solicitacoes:editar", args=[self.minha.pk]))

    def test_dossie_de_outro_e_recusado_com_texto_curto(self):
        """Pedir pelo número não abre a porta: 403, e o modal mostra o motivo."""
        self.client.force_login(self.solicitante)
        resposta = self._detalhe("solicitacao", self.de_outro.pk)
        self.assertEqual(resposta.status_code, 403)
        self.assertIn("fora do seu acesso", resposta.content.decode())

    def test_viagem_exige_o_modulo(self):
        self.client.force_login(self.solicitante)
        self.assertEqual(self._detalhe("viagem", self.viagem.pk).status_code, 403)

    def test_viagem_para_quem_pode_traz_oficio_equipe_e_pdfs(self):
        from viagens_cadastros.models import Servidor
        from viagens_oficios.models import Oficio

        root = User.objects.create_superuser("agenda_root3", "agenda_root3@example.com", None)
        servidor = Servidor.objects.create(nome="MARIA DA SILVA", telefone="41999990000")
        oficio = Oficio.objects.create(viagem=self.viagem, assunto="Deslocamento")
        oficio.servidores.add(servidor)

        self.client.force_login(root)
        resposta = self._detalhe("viagem", self.viagem.pk)
        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, "MARIA DA SILVA")
        # O contato sai formatado, como nas telas — não o número cru do banco.
        self.assertContains(resposta, "(41) 99999-0000")
        self.assertContains(resposta, reverse("viagens_oficios:editar", args=[oficio.pk]))
        self.assertContains(resposta, reverse("viagens_prestacoes:abrir_oficio", args=[oficio.pk]))
        self.assertContains(resposta, "Operação de teste")

    def test_fonte_desconhecida_e_404(self):
        self.client.force_login(self.solicitante)
        self.assertEqual(self._detalhe("nada", 1).status_code, 404)
        self.assertEqual(self._detalhe("solicitacao", 999999).status_code, 404)

    def test_eventos_trazem_o_que_os_filtros_locais_precisam(self):
        self.client.force_login(self.solicitante)
        (ev,) = [e for e in _eventos(self.client).json() if e["id"] == f"solicitacao-{self.minha.pk}"]
        props = ev["extendedProps"]
        self.assertEqual(props["municipio"], str(self.municipio))
        self.assertEqual(props["tipo"], str(self.tipo))
        self.assertTrue(props["meu"])

    def test_pdf_do_documento_abre_no_navegador(self):
        """Quem confere um documento quer vê-lo, não baixar um arquivo."""
        from documentos.models import DocumentoArtefato
        from viagens_oficios.models import Oficio

        root = User.objects.create_superuser("agenda_root4", "agenda_root4@example.com", None)
        oficio = Oficio.objects.create(viagem=self.viagem)
        artefato = DocumentoArtefato.objects.create(
            tipo="oficio", formato="pdf", oficio=oficio, nome_exibicao="oficio_900001_20260101.pdf"
        )

        self.client.force_login(root)
        html = self._detalhe("viagem", self.viagem.pk).content.decode()
        self.assertIn(reverse("documentos:abrir", args=[artefato.pk]), html)
        self.assertIn(reverse("documentos:baixar", args=[artefato.pk]), html)
        # E o nome mostrado é legível, não o do arquivo em disco.
        self.assertIn("Ofício", html)
        self.assertNotIn("oficio_900001_20260101.pdf<", html)
