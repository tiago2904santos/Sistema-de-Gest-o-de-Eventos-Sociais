import datetime as dt
import io
from unittest import mock, skipUnless

from django.core.exceptions import ValidationError
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from accounts.models import Modulo, Setor
from accounts.modulos import codigos_modulos_do_usuario, usuario_tem_modulo
from cadastros.models import Estado, Municipio, Regiao
from solicitacoes.permissions import GRUPO_ADMINISTRADOR

from .forms import SolicitacaoCoffeeBreakForm
from .management.commands.importar_coffee_break import (
    identificador_como_texto,
    parse_periodo_livre,
)
from .models import (
    AcaoHistoricoCoffeeBreak,
    ContratoCoffeeBreak,
    Fornecedor,
    LoteCoffeeBreak,
    SituacaoFinanceira,
    SolicitacaoCoffeeBreak,
    normalizar_cnpj,
)
from documentos.services.pdf_renderer import weasyprint_disponivel

from .permissions import CODIGO_MODULO
from . import certidoes, documentos, documents, services

User = get_user_model()


class BaseCoffeeBreakTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.setor_ascom = Setor.objects.get(nome="ASCOM")
        cls.modulo = Modulo.objects.get(codigo=CODIGO_MODULO)

        cls.ascom = User.objects.create_user("ascom", password="x")
        cls.ascom.setores.add(cls.setor_ascom)
        cls.sem_modulo = User.objects.create_user("comum", password="x")
        cls.superusuario = User.objects.create_superuser("root", password="x")
        cls.admin_modulo = User.objects.create_user("admin-coffee", password="x")
        cls.admin_modulo.setores.add(cls.setor_ascom)
        grupo_admin, _ = Group.objects.get_or_create(name=GRUPO_ADMINISTRADOR)
        cls.admin_modulo.groups.add(grupo_admin)

        cls.fornecedor = Fornecedor.objects.create(
            razao_social="PADARIA E CONFEITARIA FAVO E MEL LTDA",
            cnpj="35014719000166",
            email="contato@favoemel.com.br",
        )
        cls.contrato = ContratoCoffeeBreak.objects.create(
            fornecedor=cls.fornecedor,
            numero="0762/2024",
            numero_gms="7339/2024",
            fiscal_responsavel="Janine Lacerda do Prado",
        )
        cls.lote = LoteCoffeeBreak.objects.create(
            contrato=cls.contrato,
            numero=1,
            exercicio="2026",
            quantidade_total=100,
            empenho="2026NE030208",
        )
        # O lote é escolhido pelo município: Curitiba está na lista do lote 1.
        cls.estado_pr = Estado.objects.get(codigo_ibge=41)
        cls.regiao = Regiao.objects.get_or_create(nome="Região Teste")[0]
        cls.curitiba = Municipio.objects.get_or_create(
            nome="Curitiba", estado=cls.estado_pr, defaults={"regiao": cls.regiao}
        )[0]
        cls.lote.municipios.add(cls.curitiba)

    def criar_solicitacao(self, **kwargs):
        dados = {
            "lote": self.lote,
            "data_solicitacao": dt.date(2026, 8, 1),
            "descricao_evento": "Evento de teste",
            "quantidade": 30,
            "criado_por": self.ascom,
        }
        dados.update(kwargs)
        return SolicitacaoCoffeeBreak.objects.create(**dados)


# ---------------------------------------------------------------------------
# Autorização por módulo
# ---------------------------------------------------------------------------

class AutorizacaoModuloTests(BaseCoffeeBreakTestCase):
    ROTAS = [
        ("coffee_break:painel", []),
        ("coffee_break:lotes", []),
        ("coffee_break:solicitacoes", []),
        ("coffee_break:nova", []),
    ]

    def test_seed_criou_modulo_e_setor(self):
        self.assertTrue(Modulo.objects.filter(codigo=CODIGO_MODULO).exists())
        self.assertIn(self.setor_ascom, self.modulo.setores.all())

    def test_usuario_ascom_acessa_todas_as_telas(self):
        self.client.force_login(self.ascom)
        for rota, args in self.ROTAS:
            resposta = self.client.get(reverse(rota, args=args))
            self.assertEqual(resposta.status_code, 200, rota)

    def test_usuario_sem_modulo_recebe_403_por_url_direta(self):
        self.client.force_login(self.sem_modulo)
        solicitacao = self.criar_solicitacao()
        rotas = [reverse(rota, args=args) for rota, args in self.ROTAS]
        rotas += [
            reverse("coffee_break:editar", args=[solicitacao.pk]),
            reverse("coffee_break:certificado", args=[solicitacao.pk]),
            reverse("coffee_break:lote_detalhe", args=[self.lote.pk]),
        ]
        for url in rotas:
            self.assertEqual(self.client.get(url).status_code, 403, url)
        # Ações POST também são bloqueadas no backend.
        self.assertEqual(
            self.client.post(
                reverse("coffee_break:cancelar", args=[solicitacao.pk])
            ).status_code,
            403,
        )

    def test_anonimo_redireciona_para_login(self):
        resposta = self.client.get(reverse("coffee_break:painel"))
        self.assertEqual(resposta.status_code, 302)
        self.assertIn(reverse("accounts:login"), resposta.url)

    def test_superusuario_tem_visao_global(self):
        self.client.force_login(self.superusuario)
        self.assertEqual(
            self.client.get(reverse("coffee_break:painel")).status_code, 200
        )
        self.assertTrue(usuario_tem_modulo(self.superusuario, CODIGO_MODULO))

    def test_modulo_inativo_bloqueia_ascom(self):
        Modulo.objects.filter(pk=self.modulo.pk).update(ativo=False)
        self.assertFalse(usuario_tem_modulo(self.ascom, CODIGO_MODULO))

    def test_portal_mostra_modulo_conforme_acesso(self):
        """O hub lista o módulo só para quem tem o código ASCOM_COFFEE_BREAK."""
        self.client.force_login(self.ascom)
        resposta = self.client.get(reverse("core:home"))
        self.assertContains(resposta, reverse("coffee_break:painel"))

        self.client.force_login(self.sem_modulo)
        resposta = self.client.get(reverse("core:home"))
        self.assertNotContains(resposta, reverse("coffee_break:painel"))

    def test_navbar_contextual_dentro_e_fora_do_modulo(self):
        """Dentro do módulo só aparecem itens dele; fora, ele não aparece."""
        self.client.force_login(self.ascom)
        # No dashboard de Eventos Sociais não há navegação do Coffee Break.
        resposta = self.client.get(reverse("dashboard:index"))
        self.assertNotContains(
            resposta, f'href="{reverse("coffee_break:painel")}"'
        )
        self.assertContains(resposta, f'href="{reverse("solicitacoes:lista")}"')
        # Dentro do Coffee Break só há navegação do próprio módulo.
        resposta = self.client.get(reverse("coffee_break:painel"))
        self.assertContains(resposta, f'href="{reverse("coffee_break:lotes")}"')
        self.assertNotContains(
            resposta, f'href="{reverse("solicitacoes:lista")}"'
        )
        self.assertContains(resposta, f'href="{reverse("core:home")}"')

    def test_codigos_modulos_do_usuario(self):
        self.assertIn(CODIGO_MODULO, codigos_modulos_do_usuario(self.ascom))
        self.assertEqual(codigos_modulos_do_usuario(self.sem_modulo), set())
        self.assertIn(CODIGO_MODULO, codigos_modulos_do_usuario(self.superusuario))


# ---------------------------------------------------------------------------
# Modelos: fornecedor, contrato, lote e cálculos
# ---------------------------------------------------------------------------

class ModelosTests(BaseCoffeeBreakTestCase):
    def test_criacao_de_fornecedor_normaliza_cnpj(self):
        fornecedor = Fornecedor.objects.create(
            razao_social="GIACOMINI E CARVALHO LTDA",
            cnpj="45.549.407/0001-00",
        )
        self.assertEqual(fornecedor.cnpj, "45549407000100")
        self.assertEqual(fornecedor.cnpj_formatado, "45.549.407/0001-00")

    def test_cnpj_invalido_rejeitado_na_validacao(self):
        fornecedor = Fornecedor(razao_social="X LTDA", cnpj="123")
        with self.assertRaises(ValidationError):
            fornecedor.full_clean()

    def test_normalizar_cnpj(self):
        self.assertEqual(normalizar_cnpj("45.549.407/0001-00"), "45549407000100")
        self.assertEqual(normalizar_cnpj(None), "")

    def test_criacao_de_contrato_e_lote(self):
        self.assertEqual(str(self.contrato), "Contrato 0762/2024 — PADARIA E CONFEITARIA FAVO E MEL LTDA")
        self.assertEqual(self.lote.rotulo_curto, "Lote 1 (2026)")

    def test_consumido_e_restante_calculados(self):
        self.criar_solicitacao(quantidade=30)
        self.criar_solicitacao(quantidade=20, numero="02/2026")
        self.assertEqual(self.lote.quantidade_consumida, 50)
        self.assertEqual(self.lote.saldo_restante, 50)
        anotado = LoteCoffeeBreak.objects.com_consumo().get(pk=self.lote.pk)
        self.assertEqual(anotado.consumido, 50)
        self.assertEqual(anotado.restante, 50)

    def test_cancelada_nao_conta_no_consumo(self):
        self.criar_solicitacao(quantidade=30)
        self.criar_solicitacao(quantidade=60, cancelada=True, numero="02/2026")
        self.assertEqual(self.lote.quantidade_consumida, 30)

    def test_lotes_em_alerta(self):
        self.criar_solicitacao(quantidade=90)  # restam 10 de 100 (10% <= 15%)
        anotados = list(LoteCoffeeBreak.objects.com_consumo())
        em_alerta = services.lotes_em_alerta(anotados)
        self.assertEqual([lote.pk for lote in em_alerta], [self.lote.pk])


# ---------------------------------------------------------------------------
# Saldo e validações
# ---------------------------------------------------------------------------

class SaldoTests(BaseCoffeeBreakTestCase):
    def test_bloqueia_quantidade_acima_do_saldo(self):
        self.criar_solicitacao(quantidade=80)
        nova = SolicitacaoCoffeeBreak(
            lote=self.lote,
            descricao_evento="Estouro",
            quantidade=21,
            criado_por=self.ascom,
        )
        with self.assertRaises(ValidationError):
            services.salvar_com_saldo(nova)
        self.assertEqual(self.lote.solicitacoes.count(), 1)

    def test_edicao_nao_conta_a_propria_quantidade(self):
        solicitacao = self.criar_solicitacao(quantidade=80)
        solicitacao.quantidade = 100
        services.salvar_com_saldo(solicitacao)  # não deve levantar erro
        self.assertEqual(self.lote.quantidade_consumida, 100)

    def test_quantidade_zero_e_negativa_rejeitadas_no_form(self):
        for quantidade in ("0", "-5"):
            form = SolicitacaoCoffeeBreakForm(
                data={
                    "lote": self.lote.pk,
                    "data_solicitacao": "2026-08-01",
                    "descricao_evento": "Teste",
                    "quantidade": quantidade,
                }
            )
            self.assertFalse(form.is_valid(), quantidade)
            self.assertIn("quantidade", form.errors)

    def test_periodo_invalido_rejeitado(self):
        form = SolicitacaoCoffeeBreakForm(
            data={
                "lote": self.lote.pk,
                "data_solicitacao": "2026-08-01",
                "descricao_evento": "Teste",
                "quantidade": "10",
                "data_inicio_evento": "2026-08-10",
                "data_fim_evento": "2026-08-05",
            }
        )
        self.assertFalse(form.is_valid())
        self.assertIn("data_fim_evento", form.errors)

    def test_marcos_financeiros_exigem_sequencia(self):
        form = SolicitacaoCoffeeBreakForm(
            data={
                "lote": self.lote.pk,
                "data_solicitacao": "2026-08-01",
                "descricao_evento": "Teste",
                "quantidade": "10",
                "data_ordem_bancaria": "2026-08-10",
            }
        )
        self.assertFalse(form.is_valid())
        self.assertIn("data_ordem_bancaria", form.errors)

    def test_periodo_textual_e_datas_nao_sao_aceitos_juntos_em_novo_registro(self):
        form = SolicitacaoCoffeeBreakForm(
            data={
                "lote": self.lote.pk,
                "data_solicitacao": "2026-08-01",
                "descricao_evento": "Teste",
                "quantidade": "10",
                "data_inicio_evento": "2026-08-10",
                "data_fim_evento": "2026-08-11",
                "periodo_evento_texto": "10 e 11/08",
            }
        )
        self.assertFalse(form.is_valid())
        self.assertIn("periodo_evento_texto", form.errors)

    def test_cancelamento_devolve_saldo_e_registra_auditoria(self):
        solicitacao = self.criar_solicitacao(quantidade=80)
        services.cancelar(solicitacao, self.ascom, motivo="Evento adiado")
        solicitacao.refresh_from_db()
        self.assertTrue(solicitacao.cancelada)
        self.assertEqual(solicitacao.cancelada_por, self.ascom)
        self.assertEqual(solicitacao.motivo_cancelamento, "Evento adiado")
        self.assertIsNotNone(solicitacao.cancelada_em)
        self.assertEqual(self.lote.saldo_restante, 100)

    def test_reativacao_revalida_saldo(self):
        cancelada = self.criar_solicitacao(quantidade=80, cancelada=True)
        self.criar_solicitacao(quantidade=50, numero="02/2026")
        with self.assertRaises(ValidationError):
            services.reativar(cancelada)
        cancelada.refresh_from_db()
        self.assertTrue(cancelada.cancelada)


# ---------------------------------------------------------------------------
# Situação financeira derivada
# ---------------------------------------------------------------------------

class SituacaoFinanceiraTests(BaseCoffeeBreakTestCase):
    def test_derivacao_por_marcos(self):
        s = self.criar_solicitacao()
        self.assertEqual(
            s.situacao_financeira, SituacaoFinanceira.AGUARDANDO_NOTA_FISCAL
        )
        s.numero_nota_fiscal = "8046"
        self.assertEqual(
            s.situacao_financeira, SituacaoFinanceira.AGUARDANDO_PROTOCOLO
        )
        s.protocolo_pagamento = "25.419.856-0"
        self.assertEqual(s.situacao_financeira, SituacaoFinanceira.AGUARDANDO_ATESTO)
        s.data_atesto_gaf = dt.date(2026, 2, 18)
        self.assertEqual(
            s.situacao_financeira, SituacaoFinanceira.AGUARDANDO_ORDEM_BANCARIA
        )
        s.data_ordem_bancaria = dt.date(2026, 2, 24)
        self.assertEqual(
            s.situacao_financeira, SituacaoFinanceira.AGUARDANDO_ENVIO_EMPRESA
        )
        s.data_envio_empresa = dt.date(2026, 6, 16)
        self.assertEqual(s.situacao_financeira, SituacaoFinanceira.CONCLUIDA)

    def test_cancelada_prevalece(self):
        s = self.criar_solicitacao(
            cancelada=True,
            numero_nota_fiscal="8046",
            protocolo_pagamento="25.419.856-0",
            data_atesto_gaf=dt.date(2026, 2, 18),
            data_ordem_bancaria=dt.date(2026, 2, 24),
            data_envio_empresa=dt.date(2026, 6, 16),
        )
        self.assertEqual(s.situacao_financeira, SituacaoFinanceira.CANCELADA)


# ---------------------------------------------------------------------------
# Views: criação, edição, filtros, busca, ordenação e paginação
# ---------------------------------------------------------------------------

class ViewsTests(BaseCoffeeBreakTestCase):
    def setUp(self):
        self.client.force_login(self.ascom)

    def dados_post(self, **kwargs):
        dados = {
            "municipio": self.curitiba.pk,
            "data_solicitacao": "2026-08-01",
            "numero": "05/2026",
            "descricao_evento": "Inauguração da Delegacia Cidadã",
            "quantidade": "40",
            "data_inicio_evento": "",
            "data_fim_evento": "",
            "periodo_evento_texto": "",
            "numero_nota_fiscal": "",
            "protocolo_pagamento": "",
            "data_atesto_gaf": "",
            "data_ordem_bancaria": "",
            "data_envio_empresa": "",
            "observacoes": "",
        }
        dados.update(kwargs)
        return dados

    def test_criacao_pela_view(self):
        resposta = self.client.post(
            reverse("coffee_break:nova"), self.dados_post()
        )
        solicitacao = SolicitacaoCoffeeBreak.objects.get(numero="05/2026")
        # Salvar a etapa 1 volta para a lista.
        self.assertRedirects(resposta, reverse("coffee_break:solicitacoes"))
        self.assertEqual(solicitacao.criado_por, self.ascom)
        self.assertEqual(solicitacao.quantidade, 40)
        self.assertEqual(solicitacao.historico.count(), 1)

    def test_criacao_acima_do_saldo_mostra_erro(self):
        resposta = self.client.post(
            reverse("coffee_break:nova"), self.dados_post(quantidade="101")
        )
        self.assertEqual(resposta.status_code, 200)
        self.assertFalse(SolicitacaoCoffeeBreak.objects.exists())
        self.assertContains(resposta, "acima do saldo")

    def test_edicao_pela_view(self):
        solicitacao = self.criar_solicitacao(numero="05/2026")
        resposta = self.client.post(
            reverse("coffee_break:editar", args=[solicitacao.pk]),
            self.dados_post(
                quantidade="55",
                versao=str(int(solicitacao.atualizado_em.timestamp() * 1_000_000)),
            ),
        )
        solicitacao.refresh_from_db()
        self.assertRedirects(resposta, reverse("coffee_break:solicitacoes"))
        self.assertEqual(solicitacao.quantidade, 55)
        self.assertEqual(solicitacao.historico.count(), 1)
        # A nota fiscal é da etapa 2: a etapa 1 nem tem o campo.
        resposta = self.client.post(
            reverse("coffee_break:etapa_nota", args=[solicitacao.pk]),
            {
                "numero_nota_fiscal": "8046",
                "versao": str(int(solicitacao.atualizado_em.timestamp() * 1_000_000)),
            },
        )
        # A etapa 2 segue para a etapa 3.
        self.assertRedirects(
            resposta, reverse("coffee_break:etapa_protocolo", args=[solicitacao.pk]), fetch_redirect_response=False
        )
        solicitacao.refresh_from_db()
        self.assertEqual(solicitacao.numero_nota_fiscal, "8046")
        self.assertEqual(solicitacao.quantidade, 55)

    def test_formulario_concentra_historico_vinculo_e_acoes(self):
        """A tela única traz o que antes só existia no detalhe."""
        solicitacao = self.criar_solicitacao(numero="05/2026")
        services.registrar_historico(
            solicitacao,
            self.ascom,
            AcaoHistoricoCoffeeBreak.CRIACAO,
            "Solicitação registrada no sistema.",
        )
        resposta = self.client.get(
            reverse("coffee_break:editar", args=[solicitacao.pk])
        )
        self.assertEqual(resposta.status_code, 200)
        # Vínculo com o lote (link para a lista do lote) e dados contratuais.
        self.assertContains(
            resposta, reverse("coffee_break:lote_detalhe", args=[self.lote.pk])
        )
        self.assertContains(resposta, "PADARIA E CONFEITARIA FAVO E MEL LTDA")
        self.assertContains(resposta, "0762/2024")
        # Histórico e auditoria.
        self.assertContains(resposta, "Histórico")
        self.assertContains(resposta, "Solicitação registrada no sistema.")
        self.assertContains(resposta, "Criada por")
        # Transições de estado, fora do formulário principal.
        self.assertContains(resposta, 'name="motivo"')
        self.assertContains(
            resposta, reverse("coffee_break:cancelar", args=[solicitacao.pk])
        )

    def test_formulario_nao_tem_coluna_lateral(self):
        """Regra estrutural: coluna única, sem menu lateral flutuante."""
        solicitacao = self.criar_solicitacao(numero="05/2026")
        for url in (
            reverse("coffee_break:nova"),
            reverse("coffee_break:editar", args=[solicitacao.pk]),
            reverse("coffee_break:lote_detalhe", args=[self.lote.pk]),
            reverse("coffee_break:solicitacoes"),
            reverse("coffee_break:painel"),
        ):
            conteudo = self.client.get(url).content.decode()
            for marca in ("<aside", 'class="sticky"', "frm-lateral", "frm-acoes--flut"):
                self.assertNotIn(marca, conteudo, f"{marca} em {url}")

    def test_edicao_concorrente_e_rejeitada(self):
        solicitacao = self.criar_solicitacao(numero="05/2026")
        versao_antiga = str(int(solicitacao.atualizado_em.timestamp() * 1_000_000))
        solicitacao.observacoes = "Alterada por outra pessoa"
        solicitacao.save(update_fields=["observacoes", "atualizado_em"])
        resposta = self.client.post(
            reverse("coffee_break:editar", args=[solicitacao.pk]),
            self.dados_post(versao=versao_antiga),
        )
        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, "alterada por outra pessoa")

    def test_concluida_nao_abre_edicao(self):
        solicitacao = self.criar_solicitacao(
            numero="05/2026",
            numero_nota_fiscal="1",
            protocolo_pagamento="P1",
            data_atesto_gaf=dt.date(2026, 8, 2),
            data_ordem_bancaria=dt.date(2026, 8, 3),
            data_envio_empresa=dt.date(2026, 8, 4),
        )
        # A tela única do registro continua abrindo, mas sem permitir gravar.
        resposta = self.client.get(
            reverse("coffee_break:editar", args=[solicitacao.pk])
        )
        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, "bloqueadas para edição")
        self.assertNotContains(resposta, "Salvar solicitação")
        # E o POST é recusado sem alterar nada.
        resposta = self.client.post(
            reverse("coffee_break:editar", args=[solicitacao.pk]),
            self.dados_post(quantidade="77"),
        )
        self.assertRedirects(
            resposta, reverse("coffee_break:editar", args=[solicitacao.pk])
        )
        solicitacao.refresh_from_db()
        self.assertEqual(solicitacao.quantidade, 30)

    def test_form_nao_aceita_lote_inativo(self):
        lote_inativo = LoteCoffeeBreak.objects.create(
            contrato=self.contrato,
            numero=9,
            exercicio="2025",
            quantidade_total=500,
            ativo=False,
        )
        # Município só de lote inativo: não há lote para escolher.
        so_do_inativo = Municipio.objects.create(
            nome="Ponta Grossa", estado=self.estado_pr, regiao=self.regiao
        )
        lote_inativo.municipios.add(so_do_inativo)
        resposta = self.client.post(
            reverse("coffee_break:nova"), self.dados_post(municipio=so_do_inativo.pk)
        )
        self.assertEqual(resposta.status_code, 200)
        self.assertFalse(SolicitacaoCoffeeBreak.objects.exists())

    def test_busca_e_filtros_na_listagem(self):
        self.criar_solicitacao(descricao_evento="Curso de Power BI", numero="01/2026")
        self.criar_solicitacao(
            descricao_evento="Entrega de Medalhas",
            numero="02/2026",
            numero_nota_fiscal="8046",
        )
        url = reverse("coffee_break:solicitacoes")

        resposta = self.client.get(url, {"q": "Power"})
        self.assertContains(resposta, "Curso de Power BI")
        self.assertNotContains(resposta, "Entrega de Medalhas")

        resposta = self.client.get(url, {"q": "8046"})
        self.assertContains(resposta, "Entrega de Medalhas")

        resposta = self.client.get(
            url, {"situacao": SituacaoFinanceira.AGUARDANDO_PROTOCOLO}
        )
        self.assertContains(resposta, "Entrega de Medalhas")
        self.assertNotContains(resposta, "Curso de Power BI")

        resposta = self.client.get(url, {"lote": self.lote.pk, "q": "Power"})
        self.assertContains(resposta, "Curso de Power BI")

    def test_ordenacao_segura_ignora_campo_desconhecido(self):
        self.criar_solicitacao(numero="01/2026")
        resposta = self.client.get(
            reverse("coffee_break:solicitacoes"), {"ordem": "campo_malicioso"}
        )
        self.assertEqual(resposta.status_code, 200)

    def test_paginacao_preserva_filtros(self):
        for i in range(20):
            self.criar_solicitacao(quantidade=1, numero=f"{i + 1:02d}/2026")
        resposta = self.client.get(
            reverse("coffee_break:solicitacoes"), {"pagina": 2}
        )
        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, "pagina=1")

    def test_listagem_de_lotes_com_filtros(self):
        resposta = self.client.get(reverse("coffee_break:lotes"), {"q": "FAVO"})
        self.assertContains(resposta, "0762/2024")
        resposta = self.client.get(reverse("coffee_break:lotes"), {"q": "inexistente"})
        self.assertContains(resposta, "Nenhum lote encontrado")
        resposta = self.client.get(
            reverse("coffee_break:lotes"), {"situacao": "inativos"}
        )
        self.assertContains(resposta, "Nenhum lote encontrado")

    def test_detalhe_do_lote(self):
        self.criar_solicitacao(numero="01/2026")
        resposta = self.client.get(
            reverse("coffee_break:lote_detalhe", args=[self.lote.pk])
        )
        self.assertContains(resposta, "Lote 1 (2026)")
        self.assertContains(resposta, "0762/2024")
        self.assertContains(resposta, "01/2026")

    def test_painel_mostra_resumo(self):
        self.criar_solicitacao(quantidade=90)
        resposta = self.client.get(reverse("coffee_break:painel"))
        self.assertContains(resposta, "Capacidade contratada")
        self.assertContains(resposta, "Restam apenas")  # alerta de saldo baixo

    def test_cancelar_exige_post(self):
        solicitacao = self.criar_solicitacao()
        url = reverse("coffee_break:cancelar", args=[solicitacao.pk])
        # GET só abre o modal do motivo (da lista); fora dele, volta à solicitação.
        self.assertRedirects(self.client.get(url), reverse("coffee_break:editar", args=[solicitacao.pk]))
        self.assertContains(self.client.get(url, headers={"X-Cadastro-Modal": "1"}), 'name="motivo"')
        solicitacao.refresh_from_db()
        self.assertFalse(solicitacao.cancelada)
        resposta = self.client.post(url, {"motivo": "Adiado"})
        self.assertRedirects(
            resposta, reverse("coffee_break:editar", args=[solicitacao.pk])
        )
        solicitacao.refresh_from_db()
        self.assertTrue(solicitacao.cancelada)

    def test_cancelar_exige_motivo(self):
        solicitacao = self.criar_solicitacao()
        resposta = self.client.post(
            reverse("coffee_break:cancelar", args=[solicitacao.pk]), {"motivo": ""}
        )
        self.assertRedirects(
            resposta, reverse("coffee_break:editar", args=[solicitacao.pk])
        )
        solicitacao.refresh_from_db()
        self.assertFalse(solicitacao.cancelada)

    def test_concluida_nao_pode_ser_cancelada(self):
        solicitacao = self.criar_solicitacao(
            numero_nota_fiscal="1",
            protocolo_pagamento="P1",
            data_atesto_gaf=dt.date(2026, 8, 2),
            data_ordem_bancaria=dt.date(2026, 8, 3),
            data_envio_empresa=dt.date(2026, 8, 4),
        )
        resposta = self.client.post(
            reverse("coffee_break:cancelar", args=[solicitacao.pk]),
            {"motivo": "Tentativa indevida"},
        )
        self.assertRedirects(
            resposta, reverse("coffee_break:editar", args=[solicitacao.pk])
        )
        solicitacao.refresh_from_db()
        self.assertFalse(solicitacao.cancelada)
        formulario = self.client.get(
            reverse("coffee_break:editar", args=[solicitacao.pk])
        )
        self.assertNotContains(formulario, 'name="motivo"')
        self.assertContains(formulario, "bloqueadas para edição")


class CadastrosCoffeeBreakTests(BaseCoffeeBreakTestCase):
    def test_operador_comum_nao_acessa_cadastros_contratuais(self):
        self.client.force_login(self.ascom)
        resposta = self.client.get(
            reverse("coffee_break:cadastro_lista", args=["fornecedores"])
        )
        self.assertEqual(resposta.status_code, 403)
        self.assertNotContains(
            self.client.get(reverse("coffee_break:painel")),
            reverse("coffee_break:cadastros"),
        )

    def test_administrador_cria_fornecedor_pela_interface(self):
        self.client.force_login(self.admin_modulo)
        resposta = self.client.post(
            reverse("coffee_break:cadastro_novo", args=["fornecedores"]),
            {
                "razao_social": "Fornecedor Institucional Ltda",
                "cnpj": "12.345.678/0001-95",
                "contato": "Equipe comercial",
                "telefone": "41 3333-4444",
                "email": "contato@example.com",
                "ativo": "1",
            },
        )
        self.assertRedirects(
            resposta,
            reverse("coffee_break:cadastro_lista", args=["fornecedores"]),
        )
        self.assertTrue(
            Fornecedor.objects.filter(
                razao_social="Fornecedor Institucional Ltda",
                cnpj="12345678000195",
            ).exists()
        )
        painel = self.client.get(reverse("coffee_break:painel"))
        self.assertContains(painel, reverse("coffee_break:cadastros"))

    def test_cadastros_na_composicao_dos_cadastros_de_viagens(self):
        """Backoffice do módulo na mesma composição dos cadastros de apoio.

        A lateral flutuante continua proibida; a navegação entre as tabelas é
        a trilha do módulo (`cad_rail`), que no desenho do V3.2 aparece como
        uma faixa de chips acima da lista.
        """
        self.client.force_login(self.admin_modulo)
        conteudo = self.client.get(
            reverse("coffee_break:cadastro_lista", args=["fornecedores"])
        ).content.decode()
        for marca in ("<aside", 'class="sticky"'):
            self.assertNotIn(marca, conteudo, marca)
        self.assertIn("cad-rail", conteudo)
        # A navegação entre cadastros continua existindo.
        self.assertIn(reverse("coffee_break:cadastro_lista", args=["lotes"]), conteudo)

    def test_capacidade_do_lote_nao_pode_ficar_abaixo_do_consumido(self):
        self.criar_solicitacao(quantidade=30)
        self.client.force_login(self.admin_modulo)
        resposta = self.client.post(
            reverse("coffee_break:cadastro_editar", args=["lotes", self.lote.pk]),
            {
                "contrato": self.contrato.pk,
                "numero": self.lote.numero,
                "exercicio": self.lote.exercicio,
                "quantidade_total": 20,
                "empenho": self.lote.empenho,
                "municipios_texto": "",
                "orientacoes": "",
                "especificacoes_tecnicas": "",
                "observacoes": "",
                "ativo": "1",
                "versao": str(int(self.lote.atualizado_em.timestamp() * 1_000_000)),
            },
        )
        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, "já consumiu 30 unidades")


# ---------------------------------------------------------------------------
# Importação da planilha
# ---------------------------------------------------------------------------

def _planilha_de_teste():
    """Monta em memória uma planilha mínima no formato da original."""
    import openpyxl

    wb = openpyxl.Workbook()
    geral = wb.active
    geral.title = "Geral"
    geral["F2"] = "Orientações gerais de teste"
    geral["J3"] = "E" * 150  # especificações técnicas (texto longo)

    aba = wb.create_sheet(" LOTE 1- 2026")
    aba["A1"] = "COFFEE BREAK- ASCOM - LOTE 1 - FAVO E MEL (CONTRATO 0762/2024)"
    aba["A2"] = "CNPJ: 35014719000166 - EMPENHO: 2026NE030208"
    aba["J1"] = "TOTAL"
    aba["J3"] = 3800
    aba["L3"] = "CIDADES ABRANGENTES: Cidade Modelo, Desconhecida, Vila Exemplo e Cidade Par."
    aba["A3"] = "Data da Solicitação"
    aba["B3"] = "Data do evento"
    aba["C3"] = "N° da Solicitação "
    aba["D3"] = "Descrição do evento"
    aba["E3"] = "Número da Nota Fiscal"
    aba["F3"] = "Quantidade "
    aba["G3"] = "N° protocolo de pagamento"
    aba["H3"] = "Data de atesto e envio ao GAF "
    # Linha normal: nº de solicitação convertido em data pelo Excel.
    aba["A4"] = dt.datetime(2026, 2, 10)
    aba["B4"] = dt.datetime(2026, 2, 11)
    aba["C4"] = dt.datetime(2026, 2, 1)  # "02/2026"
    aba["D4"] = "Central de Flagrantes"
    aba["E4"] = 8046
    aba["F4"] = 40
    aba["G4"] = " 25.419.856-0 "
    aba["H4"] = dt.datetime(2026, 2, 18)
    # Linha com período textual e sem NF.
    aba["A5"] = dt.datetime(2026, 3, 18)
    aba["B5"] = "23,  24 e 25/03"
    aba["C5"] = "13/2026"
    aba["D5"] = "Encontro Nacional"
    aba["F5"] = 500
    # Linha cancelada.
    aba["A6"] = dt.datetime(2026, 6, 22)
    aba["B6"] = dt.datetime(2026, 6, 30)
    aba["C6"] = "16/2026"
    aba["D6"] = 'Projeto "Rota de Proteção" CANCELADO'
    aba["E6"] = "-"
    aba["F6"] = 0
    aba["G6"] = "-"
    aba["H6"] = "-"

    ob = wb.create_sheet("Controle de Ordem Bancária")
    ob["A1"] = "LOTE 1 - FAVO E MEL -  CNPJ: 35014719000166 - EMPENHO: 2026NE030208"
    ob["A2"] = "N° da Solicitação "
    ob["B2"] = "Descrição do evento"
    ob["C2"] = "Número da NF"
    ob["D2"] = "N° protocolo de pagamento"
    ob["E2"] = "OB emitida em"
    ob["F2"] = "Data de envio p/ empresa"
    ob["A3"] = dt.datetime(2026, 2, 1)  # "02/2026"
    ob["B3"] = "Central de Flagrantes"
    ob["C3"] = 8046
    ob["D3"] = " 25.419.856-0 "
    ob["E3"] = dt.datetime(2026, 2, 24)
    ob["F3"] = dt.datetime(2026, 6, 16)
    return wb


class ImportacaoTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.usuario = User.objects.create_superuser("importador", password="x")
        regiao = Regiao.objects.create(nome="Região Teste")
        estado = Estado.objects.get(codigo_ibge=41)
        Municipio.objects.create(nome="Cidade Modelo", estado=estado, regiao=regiao)
        Municipio.objects.create(nome="Vila Exemplo", estado=estado, regiao=regiao)
        Municipio.objects.create(nome="Cidade Par", estado=estado, regiao=regiao)

    def setUp(self):
        import tempfile

        wb = _planilha_de_teste()
        self.arquivo = tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False)
        wb.save(self.arquivo.name)
        self.arquivo.close()

    def tearDown(self):
        import os

        os.unlink(self.arquivo.name)

    def importar(self, *flags):
        saida = io.StringIO()
        call_command(
            "importar_coffee_break",
            self.arquivo.name,
            "--usuario",
            "importador",
            *flags,
            stdout=saida,
        )
        return saida.getvalue()

    def test_importacao_cria_estruturas_e_solicitacoes(self):
        self.importar()
        lote = LoteCoffeeBreak.objects.get(numero=1, exercicio="2026")
        self.assertEqual(lote.quantidade_total, 3800)
        self.assertEqual(lote.empenho, "2026NE030208")
        self.assertEqual(lote.contrato.numero, "0762/2024")
        self.assertEqual(
            lote.contrato.fornecedor.razao_social,
            "PADARIA E CONFEITARIA FAVO E MEL LTDA",
        )
        # Municípios reconhecidos, inclusive o par final "Vila Exemplo e
        # Cidade Par"; "Desconhecida" fica apenas no texto original.
        nomes = set(lote.municipios.values_list("nome", flat=True))
        self.assertEqual(nomes, {"Cidade Modelo", "Vila Exemplo", "Cidade Par"})
        self.assertIn("CIDADES ABRANGENTES", lote.municipios_texto)
        self.assertIn("Desconhecida", lote.municipios_texto)

        normal = SolicitacaoCoffeeBreak.objects.get(lote=lote, numero="02/2026")
        self.assertEqual(normal.quantidade, 40)
        self.assertEqual(normal.numero_nota_fiscal, "8046")
        self.assertEqual(normal.protocolo_pagamento, "25.419.856-0")
        self.assertEqual(normal.data_atesto_gaf, dt.date(2026, 2, 18))
        self.assertFalse(normal.cancelada)

        textual = SolicitacaoCoffeeBreak.objects.get(lote=lote, numero="13/2026")
        self.assertEqual(textual.periodo_evento_texto, "23, 24 e 25/03")
        self.assertEqual(textual.data_inicio_evento, dt.date(2026, 3, 23))
        self.assertEqual(textual.data_fim_evento, dt.date(2026, 3, 25))

        cancelada = SolicitacaoCoffeeBreak.objects.get(lote=lote, numero="16/2026")
        self.assertTrue(cancelada.cancelada)
        self.assertEqual(cancelada.quantidade, 0)
        # Cancelada fora do consumo.
        self.assertEqual(lote.quantidade_consumida, 540)

    def test_importa_marcos_da_ordem_bancaria(self):
        self.importar()
        solicitacao = SolicitacaoCoffeeBreak.objects.get(numero="02/2026")
        self.assertEqual(solicitacao.data_ordem_bancaria, dt.date(2026, 2, 24))
        self.assertEqual(solicitacao.data_envio_empresa, dt.date(2026, 6, 16))
        self.assertEqual(
            solicitacao.situacao_financeira, SituacaoFinanceira.CONCLUIDA
        )

    def test_importacao_idempotente(self):
        self.importar()
        contagens = (
            Fornecedor.objects.count(),
            ContratoCoffeeBreak.objects.count(),
            LoteCoffeeBreak.objects.count(),
            SolicitacaoCoffeeBreak.objects.count(),
        )
        self.importar()
        self.assertEqual(
            contagens,
            (
                Fornecedor.objects.count(),
                ContratoCoffeeBreak.objects.count(),
                LoteCoffeeBreak.objects.count(),
                SolicitacaoCoffeeBreak.objects.count(),
            ),
        )

    def test_dry_run_nao_persiste(self):
        saida = self.importar("--dry-run")
        self.assertIn("[dry-run]", saida)
        self.assertFalse(Fornecedor.objects.exists())
        self.assertFalse(SolicitacaoCoffeeBreak.objects.exists())

    def test_identificador_como_texto(self):
        self.assertEqual(
            identificador_como_texto(dt.datetime(2026, 2, 1)), "02/2026"
        )
        self.assertEqual(identificador_como_texto(8046.0), "8046")
        self.assertEqual(identificador_como_texto(" 13/2026 "), "13/2026")
        self.assertEqual(identificador_como_texto("-"), "")
        self.assertEqual(identificador_como_texto(None), "")

    def test_parse_periodo_livre(self):
        self.assertEqual(
            parse_periodo_livre("23,  24 e 25/03", 2026),
            (dt.date(2026, 3, 23), dt.date(2026, 3, 25)),
        )
        self.assertEqual(
            parse_periodo_livre("12 à 15/05", 2026),
            (dt.date(2026, 5, 12), dt.date(2026, 5, 15)),
        )
        self.assertEqual(
            parse_periodo_livre("03 e 10/11/2025", 2026),
            (dt.date(2025, 11, 3), dt.date(2025, 11, 10)),
        )
        # "17 e 20/2026": mês 20 não existe — fica só como texto.
        self.assertEqual(parse_periodo_livre("17 e 20/2026", 2026), (None, None))


# ---------------------------------------------------------------------------
# Administração
# ---------------------------------------------------------------------------

class AdminTests(BaseCoffeeBreakTestCase):
    def setUp(self):
        self.client.force_login(self.superusuario)

    def test_listas_do_admin_respondem(self):
        for rota in (
            "admin:coffee_break_fornecedor_changelist",
            "admin:coffee_break_contratocoffeebreak_changelist",
            "admin:coffee_break_lotecoffeebreak_changelist",
            "admin:coffee_break_solicitacaocoffeebreak_changelist",
            "admin:accounts_setor_changelist",
            "admin:accounts_modulo_changelist",
        ):
            self.assertEqual(self.client.get(reverse(rota)).status_code, 200, rota)

    def test_admin_bloqueia_capacidade_abaixo_do_consumido(self):
        self.criar_solicitacao(quantidade=80)
        resposta = self.client.post(
            reverse("admin:coffee_break_lotecoffeebreak_change", args=[self.lote.pk]),
            {
                "contrato": self.contrato.pk,
                "numero": 1,
                "exercicio": "2026",
                "quantidade_total": 50,  # abaixo dos 80 consumidos
                "empenho": "2026NE030208",
                "municipios_texto": "",
                "orientacoes": "",
                "especificacoes_tecnicas": "",
                "observacoes": "",
                "ativo": "on",
            },
        )
        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, "não pode ficar abaixo")
        self.lote.refresh_from_db()
        self.assertEqual(self.lote.quantidade_total, 100)

    def test_admin_bloqueia_solicitacao_acima_do_saldo(self):
        resposta = self.client.post(
            reverse("admin:coffee_break_solicitacaocoffeebreak_add"),
            {
                "lote": self.lote.pk,
                "data_solicitacao": "2026-08-01",
                "numero": "01/2026",
                "descricao_evento": "Estouro",
                "quantidade": 101,
                "numero_nota_fiscal": "",
                "protocolo_pagamento": "",
                "observacoes": "",
                "motivo_cancelamento": "",
                "criado_por": self.superusuario.pk,
            },
        )
        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, "acima do saldo")
        self.assertFalse(SolicitacaoCoffeeBreak.objects.exists())


# ---------------------------------------------------------------------------
# Processo da OS ao protocolo: lote pelo município, numeração, documentos e
# certidões
# ---------------------------------------------------------------------------

class LotePeloMunicipioTests(BaseCoffeeBreakTestCase):
    def setUp(self):
        self.client.force_login(self.ascom)

    def _post(self, **kwargs):
        dados = ViewsTests.dados_post(self, numero="", **kwargs)
        return self.client.post(reverse("coffee_break:nova"), dados)

    def test_municipio_da_lista_escolhe_o_lote_e_numera(self):
        self.criar_solicitacao(numero="07/2026")
        self._post()
        nova = SolicitacaoCoffeeBreak.objects.exclude(numero="07/2026").get()
        self.assertEqual(nova.lote, self.lote)
        self.assertEqual(nova.municipio, self.curitiba)
        self.assertEqual(nova.numero, "08/2026")

    def test_numeracao_e_por_ano(self):
        self.criar_solicitacao(numero="40/2025")
        self.assertEqual(services.proximo_numero(2026), "01/2026")

    def test_numeracao_unica_para_todos_os_lotes(self):
        outro = LoteCoffeeBreak.objects.create(
            contrato=self.contrato, numero=2, exercicio="2026", quantidade_total=100
        )
        self.criar_solicitacao(numero="10/2026")
        self.criar_solicitacao(lote=outro, numero="12/2026")
        # Vale a maior já usada + 1, de qualquer lote.
        self.assertEqual(services.proximo_numero(2026), "13/2026")

    def test_municipio_fora_dos_lotes_sem_coordenadas_da_erro(self):
        longe = Municipio.objects.create(
            nome="Cidade Sem Lote", estado=self.estado_pr, regiao=self.regiao
        )
        resposta = self._post(municipio=longe.pk)
        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, "Nenhum lote ativo atende Cidade Sem Lote")
        self.assertFalse(SolicitacaoCoffeeBreak.objects.exists())

    def test_municipio_fora_dos_lotes_vai_para_a_sede_mais_proxima(self):
        from decimal import Decimal

        Municipio.objects.filter(pk=self.curitiba.pk).update(
            latitude=Decimal("-25.4284"), longitude=Decimal("-49.2733")
        )
        outro_contrato = ContratoCoffeeBreak.objects.create(
            fornecedor=self.fornecedor, numero="0130/2025"
        )
        cascavel = Municipio.objects.create(
            nome="Cascavel", estado=self.estado_pr, regiao=self.regiao,
            latitude=Decimal("-24.9555"), longitude=Decimal("-53.4552"),
        )
        lote_oeste = LoteCoffeeBreak.objects.create(
            contrato=outro_contrato, numero=5, exercicio="2026", quantidade_total=50
        )
        lote_oeste.municipios.add(cascavel)
        campo_largo = Municipio.objects.create(
            nome="Campo Largo", estado=self.estado_pr, regiao=self.regiao,
            latitude=Decimal("-25.4597"), longitude=Decimal("-49.5236"),
        )
        lote, distancia = services.escolher_lote(campo_largo, dt.date(2026, 9, 1))
        self.assertEqual(lote, self.lote)
        self.assertLess(distancia, 40)


class DocumentosTests(BaseCoffeeBreakTestCase):
    def setUp(self):
        self.client.force_login(self.ascom)

    def test_detalhamento_montado_dos_campos(self):
        s = self.criar_solicitacao(
            data_inicio_evento=dt.date(2026, 10, 1), quantidade=40
        )
        s.horario_evento = dt.time(9, 30)
        self.assertEqual(
            s.detalhamento_efetivo, "Solicito coffee para:\nDia 01/10 às 9h30 p/ 40 pessoas."
        )

    def test_referencia_documental_do_contrato(self):
        self.contrato.termo_aditivo = "0355/2025"
        self.assertEqual(
            self.contrato.referencia_documental,
            "0762/2024 – GMS 7339/2024 - TERMO ADITIVO Nº 0355/2025",
        )

    def test_os_sem_local_volta_com_o_que_falta(self):
        s = self.criar_solicitacao(numero="05/2026")
        resposta = self.client.get(reverse("coffee_break:ordem_servico", args=[s.pk]))
        self.assertEqual(resposta.status_code, 302)

    def test_pacote_lista_o_que_falta(self):
        s = self.criar_solicitacao(numero="05/2026", numero_nota_fiscal="8696")
        faltas = " ".join(documentos.pendencias_pacote(s))
        self.assertIn("PDF da nota fiscal", faltas)
        self.assertIn("Contrato 0762/2024: Anexe o PDF", faltas)
        self.assertIn("Certidão Federal: Certidão não cadastrada", faltas)
        self.assertIn("número do ofício", faltas)


class CertidoesTests(BaseCoffeeBreakTestCase):
    def test_validade_lida_dos_textos_dos_portais(self):
        casos = {
            "Certidão emitida gratuitamente... Válida até 17/03/2027.": dt.date(2027, 3, 17),
            "Validade: 16/03/2027 - 180 (cento e oitenta) dias, contados da data": dt.date(2027, 3, 16),
            "Validade:14/09/2026 a 13/10/2026 Certificação Número:": dt.date(2026, 10, 13),
            "Emitida em 01/09/2026. Esta certidão é válida por 90 (noventa) dias.": dt.date(2026, 11, 30),
        }
        for texto, esperado in casos.items():
            self.assertEqual(certidoes.validade_do_texto(texto), esperado, texto)
        self.assertIsNone(certidoes.validade_do_texto("sem data nenhuma"))

    def test_quadro_classifica_por_validade(self):
        from django.core.files.base import ContentFile

        hoje = dt.date(2026, 9, 21)
        for tipo, validade in (("FEDERAL", dt.date(2026, 9, 1)), ("FGTS", dt.date(2026, 9, 30))):
            certidoes.registrar(self.fornecedor, tipo, ContentFile(b"%PDF-1.4", name="c.pdf"), validade)
        situacoes = {l["tipo"]: l["situacao"] for l in certidoes.quadro(self.fornecedor, hoje)}
        self.assertEqual(situacoes["FEDERAL"], "vencida")
        self.assertEqual(situacoes["FGTS"], "vencendo")
        self.assertEqual(situacoes["ESTADUAL"], "faltando")


class AndamentoCoffeeTests(BaseCoffeeBreakTestCase):
    def setUp(self):
        self.client.force_login(self.ascom)

    def test_marcos_em_ordem_pelo_modal(self):
        s = self.criar_solicitacao(numero="05/2026")
        url = reverse("coffee_break:andamento", args=[s.pk])
        # A OS enviada ao fornecedor saiu do fluxo: o primeiro marco é a nota fiscal.
        self.assertContains(self.client.get(url, headers={"X-Cadastro-Modal": "1"}), "Número da nota fiscal")
        modal = {"X-Cadastro-Modal": "1"}
        resposta = self.client.post(url, {"valor": "8696", "andamento": "NF chegou por e-mail."}, headers=modal)
        self.assertEqual(resposta.json(), {"ok": True})
        s.refresh_from_db()
        self.assertEqual(s.numero_nota_fiscal, "8696")
        self.assertEqual(services.proximo_marco(s)["campo"], "protocolo_pagamento")
        self.assertEqual(services.ultima_anotacao(s), "NF chegou por e-mail.")
        estados = [e["estado"] for e in services.etapas(s)]
        self.assertEqual(estados[:3], ["concluido", "concluido", "atual"])
        # Vazio não passa.
        self.assertContains(self.client.post(url, {"valor": ""}, headers=modal), "Informe")

    def test_marco_pulado_da_planilha_conta_como_feito(self):
        s = self.criar_solicitacao(numero="05/2026", numero_nota_fiscal="1")
        self.assertEqual(services.etapas(s)[1]["estado"], "concluido")

    def test_cadastro_em_modal_e_exclusao_so_sem_uso(self):
        self.client.force_login(self.admin_modulo)
        resposta = self.client.get(
            reverse("coffee_break:cadastro_editar", args=["fornecedores", self.fornecedor.pk]),
            headers={"X-Cadastro-Modal": "1"},
        )
        self.assertContains(resposta, "data-cadastro-form")
        self.client.post(reverse("coffee_break:cadastro_excluir", args=["fornecedores", self.fornecedor.pk]))
        self.assertTrue(Fornecedor.objects.filter(pk=self.fornecedor.pk).exists())
        livre = Fornecedor.objects.create(razao_social="SEM USO LTDA")
        self.client.post(reverse("coffee_break:cadastro_excluir", args=["fornecedores", livre.pk]))
        self.assertFalse(Fornecedor.objects.filter(pk=livre.pk).exists())
# Certificado da solicitação (HTML → PDF)
# ---------------------------------------------------------------------------

class CertificadoCoffeeBreakTests(BaseCoffeeBreakTestCase):
    """O certificado é o espelho do registro: o que está no banco, e só isso.

    O HTML é testado sempre (é template Django puro); o PDF, só onde o
    WeasyPrint carrega — como nos demais tipos documentais do projeto.
    """

    def setUp(self):
        self.solicitacao = self.criar_solicitacao(
            numero="02/2026",
            descricao_evento="Posse da nova diretoria",
            data_inicio_evento=dt.date(2026, 8, 20),
            data_fim_evento=dt.date(2026, 8, 20),
            numero_nota_fiscal="NF-4521",
            observacoes="Servir às 9h no auditório.",
        )

    def _html(self):
        from documentos.services.pdf_renderer import renderizar_html

        return renderizar_html(
            documents.TIPO, documents.contexto(self.solicitacao), modo="pdf"
        )

    def test_html_traz_o_pedido_o_lote_e_o_fornecedor(self):
        html = self._html()
        for texto in [
            "02/2026",
            "Posse da nova diretoria",
            "20/08/2026",
            "PADARIA E CONFEITARIA FAVO E MEL LTDA",
            "35.014.719/0001-66",
            "0762/2024",
            "2026NE030208",
            "Servir às 9h no auditório.",
            "doc-folha-ascom",
        ]:
            self.assertIn(texto, html, texto)

    def test_html_mostra_o_marco_cumprido_e_o_que_falta(self):
        """O fluxo financeiro é o motivo do papel: o pendente tem de aparecer."""
        html = self._html()
        self.assertIn("NF-4521", html)
        self.assertIn("Aguardando protocolo", html)
        # Quatro marcos ainda sem registro — protocolo, atesto, OB e envio.
        self.assertEqual(html.count("Pendente"), 4)

    def test_html_de_cancelada_abre_com_o_motivo(self):
        services.cancelar(self.solicitacao, self.ascom, "Evento adiado")
        self.solicitacao.refresh_from_db()
        html = self._html()
        self.assertIn("Solicitação cancelada", html)
        self.assertIn("Evento adiado", html)
        self.assertIn("não consome o saldo do lote", html)

    def test_cabecalho_nao_repete_o_orgao_sem_unidade(self):
        """Sem unidade configurada, a linha da unidade some — não vira o órgão.

        O atalho `unidade or nome_orgao` fazia o timbre imprimir o mesmo nome
        duas vezes seguidas, porque o template já imprime o órgão acima.
        """
        contexto = documents.contexto(self.solicitacao)
        institucional = contexto["institucional"]
        self.assertEqual(institucional["unidade_cabecalho"], "")
        html = self._html()
        self.assertEqual(html.count("doc-cabecalho__unidade"), 0)

    def test_data_de_emissao_com_mes_em_minuscula(self):
        """A convenção institucional é "21 de setembro de 2026", não "Setembro"."""
        extenso = documents.contexto(self.solicitacao)["cb"]["emitido_extenso"]
        self.assertRegex(extenso, r"^\d{1,2} de [a-zç]+ de \d{4}, às \d{2}:\d{2}$")

    def test_contexto_nao_grava_nada(self):
        antes = SolicitacaoCoffeeBreak.objects.get(pk=self.solicitacao.pk).atualizado_em
        documents.contexto(self.solicitacao)
        depois = SolicitacaoCoffeeBreak.objects.get(pk=self.solicitacao.pk).atualizado_em
        self.assertEqual(antes, depois)

    def test_nome_do_arquivo_neutraliza_a_barra_do_numero(self):
        nome = documents.nome_arquivo(self.solicitacao)
        self.assertEqual(nome, "certificado-coffee-break-02_2026.pdf")
        self.assertNotIn("/", nome.removeprefix("certificado-coffee-break-"))

    def test_sem_numero_o_arquivo_usa_a_chave(self):
        sem_numero = self.criar_solicitacao(numero="", quantidade=1)
        self.assertEqual(
            documents.nome_arquivo(sem_numero),
            f"certificado-coffee-break-{sem_numero.pk}.pdf",
        )

    def test_motor_indisponivel_avisa_e_volta_para_a_solicitacao(self):
        """Sem o runtime do WeasyPrint o pedido continua acessível."""
        from documentos.services.exceptions import DocumentRendererUnavailable

        self.client.force_login(self.ascom)
        url = reverse("coffee_break:certificado", args=[self.solicitacao.pk])
        with mock.patch.object(
            documents, "gerar_pdf", side_effect=DocumentRendererUnavailable("Sem GTK.")
        ):
            resposta = self.client.get(url, follow=True)
        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, "Não foi possível gerar o certificado")

    def test_lista_e_formulario_oferecem_o_certificado(self):
        self.client.force_login(self.ascom)
        url = reverse("coffee_break:certificado", args=[self.solicitacao.pk])
        for pagina in (reverse("coffee_break:editar", args=[self.solicitacao.pk]),):
            self.assertContains(self.client.get(pagina), url, msg_prefix=pagina)

    def test_concluida_bloqueada_para_edicao_ainda_oferece_o_certificado(self):
        """É justamente quando o pedido fecha que alguém precisa do papel."""
        concluida = self.criar_solicitacao(
            numero="03/2026",
            quantidade=1,
            numero_nota_fiscal="NF-9",
            protocolo_pagamento="21.000.000-0",
            data_atesto_gaf=dt.date(2026, 8, 25),
            data_ordem_bancaria=dt.date(2026, 8, 26),
            data_envio_empresa=dt.date(2026, 8, 27),
        )
        self.client.force_login(self.ascom)
        resposta = self.client.get(reverse("coffee_break:editar", args=[concluida.pk]))
        self.assertContains(
            resposta, reverse("coffee_break:certificado", args=[concluida.pk])
        )

    @skipUnless(weasyprint_disponivel(), "WeasyPrint sem as bibliotecas nativas")
    def test_view_devolve_pdf(self):
        self.client.force_login(self.ascom)
        resposta = self.client.get(
            reverse("coffee_break:certificado", args=[self.solicitacao.pk])
        )
        self.assertEqual(resposta.status_code, 200)
        self.assertEqual(resposta["Content-Type"], "application/pdf")
        self.assertIn(
            "certificado-coffee-break-02_2026.pdf", resposta["Content-Disposition"]
        )
        self.assertTrue(resposta.content.startswith(b"%PDF-"))

    @skipUnless(weasyprint_disponivel(), "WeasyPrint sem as bibliotecas nativas")
    def test_pdf_leva_o_pedido_ao_papel(self):
        """O que a tela mostra tem de chegar ao PDF — e num documento curto."""
        from pypdf import PdfReader

        paginas = PdfReader(
            io.BytesIO(documents.gerar_pdf(self.solicitacao, usuario=self.ascom))
        ).pages
        self.assertLessEqual(len(paginas), 2)
        # Palavras soltas, e não frases: o espaçamento do texto extraído de um
        # PDF é posicional, e comparar frase inteira testaria o extrator.
        texto = "".join(pagina.extract_text() or "" for pagina in paginas)
        for esperado in ("02/2026", "Posse", "diretoria", "NF-4521", "Pendente"):
            self.assertIn(esperado, texto, esperado)


# ---------------------------------------------------------------------------
# Etapas da solicitação: pedido/OS, nota/ofício/certifico, protocolo/pagamento
# ---------------------------------------------------------------------------

def _pdf_em_branco(paginas=1):
    from pypdf import PdfWriter

    escritor = PdfWriter()
    for _ in range(paginas):
        escritor.add_blank_page(width=595, height=842)
    saida = io.BytesIO()
    escritor.write(saida)
    return saida.getvalue()


class EtapasBase(BaseCoffeeBreakTestCase):
    """A solicitação das etapas e o que a deixa pronta para o protocolo (sem testes)."""

    def setUp(self):
        import tempfile

        from django.test import override_settings

        pasta = tempfile.TemporaryDirectory(prefix="coffee-etapas-")
        self.addCleanup(pasta.cleanup)
        config = override_settings(MEDIA_ROOT=pasta.name)
        config.enable()
        self.addCleanup(config.disable)
        self.client.force_login(self.ascom)
        self.solicitacao = self.criar_solicitacao(
            numero="41/2026",
            descricao_evento="Ciclo de Palestras Saúde e Bem-Estar - 1DP Curitiba",
            quantidade=40,
            local_entrega="1DP",
            responsavel_recebimento="Ana",
        )

    def _versao(self, s):
        s.refresh_from_db()
        return str(int(s.atualizado_em.timestamp() * 1_000_000))

    def _completar_para_protocolo(self, s):
        """Deixa tudo pronto para o anexo: NF, ofício, contrato, aditivo e certidões."""
        from django.core.files.base import ContentFile

        from .models import CertidaoFornecedor, TipoCertidao

        s.numero_nota_fiscal = "8957"
        s.numero_oficio = "124/2026"
        s.data_oficio = dt.date(2026, 9, 21)
        s.arquivo_nota_fiscal.save("nf.pdf", ContentFile(_pdf_em_branco()), save=False)
        s.save()
        self.contrato.termo_aditivo = "0355/2025"
        self.contrato.arquivo_contrato.save("c.pdf", ContentFile(_pdf_em_branco(3)), save=False)
        self.contrato.arquivo_termo_aditivo.save("a.pdf", ContentFile(_pdf_em_branco(2)), save=False)
        self.contrato.save()
        for tipo in TipoCertidao.values:
            CertidaoFornecedor.objects.create(
                fornecedor=self.fornecedor,
                tipo=tipo,
                validade=dt.date(2099, 1, 1),
                arquivo=ContentFile(_pdf_em_branco(), name=f"{tipo}.pdf"),
            )


class EtapasTests(EtapasBase):
    # -- Telas ---------------------------------------------------------------

    def test_as_tres_etapas_abrem_com_o_stepper(self):
        for rota in ("editar", "etapa_nota", "etapa_protocolo"):
            resposta = self.client.get(reverse(f"coffee_break:{rota}", args=[self.solicitacao.pk]))
            self.assertEqual(resposta.status_code, 200, rota)
            for titulo in ("Solicitação e OS", "Nota fiscal, ofício e certifico", "Protocolo e pagamento"):
                self.assertContains(resposta, titulo)
            self.assertContains(resposta, 'aria-current="step"')

    def test_nova_solicitacao_so_tem_a_etapa_1_aberta(self):
        resposta = self.client.get(reverse("coffee_break:nova"))
        self.assertContains(resposta, 'aria-disabled="true"', count=2)

    def test_cada_etapa_grava_so_os_seus_campos(self):
        s = self.solicitacao
        s.observacoes = "Não pode sumir"
        s.save()
        resposta = self.client.post(
            reverse("coffee_break:etapa_nota", args=[s.pk]),
            {"numero_nota_fiscal": "8957", "numero_oficio": "124/2026", "protocolo_pcpr_oficio": "266170580", "versao": self._versao(s)},
        )
        self.assertEqual(resposta.status_code, 302)
        s.refresh_from_db()
        self.assertEqual((s.numero_nota_fiscal, s.numero_oficio), ("8957", "124/2026"))
        self.assertEqual(s.quantidade, 40)
        self.assertEqual(s.descricao_evento, "Ciclo de Palestras Saúde e Bem-Estar - 1DP Curitiba")
        self.assertEqual(s.observacoes, "Não pode sumir")

        # O protocolo de pagamento é o do ofício (etapa 2).
        s.refresh_from_db()
        self.assertEqual(s.protocolo_pagamento, "26.617.058-0")
        resposta = self.client.post(
            reverse("coffee_break:etapa_protocolo", args=[s.pk]),
            {"observacoes": "ok", "versao": self._versao(s)},
        )
        self.assertRedirects(resposta, reverse("coffee_break:solicitacoes"))
        s.refresh_from_db()
        self.assertEqual(s.protocolo_pagamento, "26.617.058-0")
        self.assertEqual((s.numero_nota_fiscal, s.numero_oficio), ("8957", "124/2026"))

    def test_salvar_e_seguir_leva_a_proxima_etapa(self):
        s = self.solicitacao
        resposta = self.client.post(
            reverse("coffee_break:etapa_nota", args=[s.pk]),
            {"numero_nota_fiscal": "8957", "seguir": "protocolo", "versao": self._versao(s)},
        )
        self.assertRedirects(resposta, reverse("coffee_break:etapa_protocolo", args=[s.pk]))

    def test_nota_nao_fica_em_branco_depois_do_protocolo(self):
        s = self.solicitacao
        s.numero_nota_fiscal = "8957"
        s.protocolo_pagamento = "26.617.058-0"
        s.save()
        resposta = self.client.post(
            reverse("coffee_break:etapa_nota", args=[s.pk]),
            {"numero_nota_fiscal": "", "versao": self._versao(s)},
        )
        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, "a nota não pode ficar em branco")

    def test_erro_do_modelo_em_campo_de_outra_etapa_vai_para_o_topo(self):
        """O atesto sem protocolo é regra do modelo; na etapa 3 o erro aparece sem quebrar a tela."""
        s = self.solicitacao
        resposta = self.client.post(
            reverse("coffee_break:etapa_protocolo", args=[s.pk]),
            {"data_atesto_gaf": "2026-09-22", "versao": self._versao(s)},
        )
        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, "Informe o protocolo de pagamento antes do atesto.")

    def test_etapa_1_nao_apaga_a_nota(self):
        s = self.solicitacao
        s.numero_nota_fiscal = "8957"
        s.save()
        dados = {
            "municipio": self.curitiba.pk,
            "data_solicitacao": "2026-08-01",
            "local_entrega": "Outro local",
            "responsavel_recebimento": "Ana",
            "versao": self._versao(s),
        }
        resposta = self.client.post(reverse("coffee_break:editar", args=[s.pk]), dados)
        self.assertEqual(resposta.status_code, 302)
        s.refresh_from_db()
        self.assertEqual(s.local_entrega, "Outro local")
        self.assertEqual(s.numero_nota_fiscal, "8957")

    def test_stepper_marca_as_etapas_feitas(self):
        from . import views

        s = self.solicitacao
        # A OS sem pendências fecha a etapa 1.
        self.assertEqual(views._etapas_concluidas(s), {"pedido"})
        s.local_entrega = ""
        self.assertEqual(views._etapas_concluidas(s), set())
        s.local_entrega = "1DP"
        self._completar_para_protocolo(s)
        self.assertEqual(views._etapas_concluidas(s), {"pedido", "nota"})

    def test_etapa_3_traz_os_textos_do_eprotocolo_e_o_anexo(self):
        self.fornecedor.nome_curto = "Favo e Mel"
        self.fornecedor.save()
        self._completar_para_protocolo(self.solicitacao)
        resposta = self.client.get(reverse("coffee_break:etapa_protocolo", args=[self.solicitacao.pk]))
        self.assertContains(resposta, "ENVIO P/ PAGAMENTO DA NOTA FISCAL N 8957 - (FAVO E MEL)")
        self.assertContains(resposta, "Encaminhamos o presente protocolado com as devidas informações para o pagamento da Nota fiscal n° 8957.")
        self.assertContains(resposta, "LICITACAO")
        self.assertContains(resposta, "REGISTRO DE PRECO")
        self.assertContains(resposta, 'data-copiar-de="texto-detalhamento"')
        # Os quatro arquivos para baixar.
        for parte in ("os", "oficio", "notas", "contratos"):
            self.assertContains(resposta, reverse("coffee_break:pacote_parte", args=[self.solicitacao.pk, parte]))

    def test_andamento_volta_para_a_etapa_do_proximo_marco(self):
        s = self.solicitacao
        s.numero_nota_fiscal = "8957"
        s.save()
        resposta = self.client.post(
            reverse("coffee_break:andamento", args=[s.pk]), {"valor": "26.617.058-0"}
        )
        self.assertRedirects(
            resposta, reverse("coffee_break:etapa_protocolo", args=[s.pk]), fetch_redirect_response=False
        )

    # -- Documentos ----------------------------------------------------------

    def test_anexo_segue_a_ordem_do_processo(self):
        self._completar_para_protocolo(self.solicitacao)
        chaves = [item["chave"] for item in documentos.itens_anexo(self.solicitacao)]
        self.assertEqual(
            chaves,
            [
                "oficio", "nota", "certifico",
                "certidao-fgts", "certidao-trabalhista", "certidao-municipal",
                "certidao-estadual", "certidao-federal",
                "aditivo", "contrato",
            ],
        )
        self.assertEqual(documentos.pendencias_pacote(self.solicitacao), [])

    def test_sem_termo_aditivo_o_anexo_nao_pede_aditivo(self):
        chaves = [item["chave"] for item in documentos.itens_anexo(self.solicitacao)]
        self.assertNotIn("aditivo", chaves)

    def test_certidao_vencida_barra_o_anexo(self):
        from .models import CertidaoFornecedor

        self._completar_para_protocolo(self.solicitacao)
        CertidaoFornecedor.objects.filter(tipo="FGTS").update(validade=dt.date(2020, 1, 1))
        faltas = " ".join(documentos.pendencias_pacote(self.solicitacao))
        self.assertIn("Certidão FGTS: Vencida em 01/01/2020.", faltas)

    def test_ofício_so_sai_com_nota_e_numero(self):
        resposta = self.client.get(reverse("coffee_break:oficio", args=[self.solicitacao.pk]))
        self.assertRedirects(resposta, reverse("coffee_break:etapa_nota", args=[self.solicitacao.pk]))

    def test_nome_curto_do_fornecedor(self):
        self.assertEqual(self.fornecedor.nome_curto_efetivo, "PADARIA E CONFEITARIA FAVO E MEL")
        self.fornecedor.nome_curto = "favo e mel"
        self.assertEqual(self.fornecedor.nome_curto_efetivo, "FAVO E MEL")

    @skipUnless(weasyprint_disponivel(), "WeasyPrint sem as bibliotecas nativas")
    def test_oficio_no_texto_do_modelo(self):
        from pypdf import PdfReader

        self.contrato.termo_aditivo = "0355/2025"
        self.contrato.save()
        s = self.solicitacao
        s.numero_nota_fiscal = "8957"
        s.numero_oficio = "124/2026"
        s.data_oficio = dt.date(2026, 9, 21)
        s.protocolo_pcpr_oficio = "2026.050880.000"
        s.save()
        paginas = PdfReader(io.BytesIO(documentos.oficio_pdf(s))).pages
        self.assertEqual(len(paginas), 1)
        texto = " ".join((paginas[0].extract_text() or "").split())
        for esperado in (
            "OFÍCIO 124/2026",
            "PCPR Protocolo n.º: 2026.050880.000",
            "Curitiba, 21 de Setembro de 2026",
            "Excelentíssimo Senhor Delegado:",
            "Coffee Break para 40 (quarenta) pessoas.",
            "Nota Fiscal n° 8957",
            "Cláusula Décima, item 10.2.6",
            "TERMO ADITIVO Nº 0355/2025",
            "JOÃO MÁRIO NUNES DE GOES",
            "Grupo Auxiliar Financeiro - GAF",
        ):
            self.assertIn(esperado, texto, esperado)

    @skipUnless(weasyprint_disponivel(), "WeasyPrint sem as bibliotecas nativas")
    def test_anexo_completo_em_pdf_e_zip(self):
        import zipfile

        from pypdf import PdfReader

        self._completar_para_protocolo(self.solicitacao)
        resposta = self.client.get(
            reverse("coffee_break:pacote_protocolo", args=[self.solicitacao.pk]) + "?baixar=1"
        )
        self.assertEqual(resposta["Content-Type"], "application/pdf")
        # ofício 1 + NF 1 + certifico 1 + 5 certidões + aditivo 2 + contrato 3
        self.assertEqual(len(PdfReader(io.BytesIO(resposta.content)).pages), 13)

        resposta = self.client.get(
            reverse("coffee_break:pacote_protocolo_zip", args=[self.solicitacao.pk])
        )
        self.assertEqual(resposta["Content-Type"], "application/zip")
        self.assertIn("attachment", resposta["Content-Disposition"])
        nomes = zipfile.ZipFile(io.BytesIO(resposta.content)).namelist()
        self.assertEqual(len(nomes), 10)
        self.assertTrue(nomes[0].startswith("01 - Of.124"))
        self.assertTrue(nomes[-1].startswith("10 - Contrato 0762-2024"))


class ConfiguracaoOficioTests(BaseCoffeeBreakTestCase):
    def setUp(self):
        self.client.force_login(self.admin_modulo)

    def test_configuracao_aparece_nos_cadastros_e_nao_se_exclui(self):
        from .models import ConfiguracaoCoffeeBreak

        resposta = self.client.get(reverse("coffee_break:cadastro_lista", args=["oficio"]))
        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, "JOÃO MÁRIO NUNES DE GOES")
        self.assertNotContains(resposta, reverse("coffee_break:cadastro_novo", args=["oficio"]))
        resposta = self.client.post(reverse("coffee_break:cadastro_excluir", args=["oficio", 1]))
        self.assertEqual(resposta.status_code, 302)
        self.assertTrue(ConfiguracaoCoffeeBreak.objects.filter(pk=1).exists())
        resposta = self.client.get(reverse("coffee_break:cadastro_novo", args=["oficio"]))
        self.assertRedirects(resposta, reverse("coffee_break:cadastro_lista", args=["oficio"]))


class NumeroDaOSTests(BaseCoffeeBreakTestCase):
    """O número da OS como o N° do Ofício de Viagens: sequência + "/ ano"."""

    def setUp(self):
        self.client.force_login(self.ascom)

    def _post_nova(self, **extra):
        dados = {
            "municipio": self.curitiba.pk,
            "data_solicitacao": "2026-08-01",
            "descricao_evento": "Evento",
            "quantidade": "10",
        }
        dados.update(extra)
        return self.client.post(reverse("coffee_break:nova"), dados)

    def test_so_a_sequencia_vira_numero_com_o_ano_da_data(self):
        self._post_nova(numero="7")
        self.assertTrue(SolicitacaoCoffeeBreak.objects.filter(numero="07/2026").exists())

    def test_formato_completo_continua_valendo(self):
        self._post_nova(numero="12/2026")
        self.assertTrue(SolicitacaoCoffeeBreak.objects.filter(numero="12/2026").exists())

    def test_em_branco_numera_pelo_lote(self):
        self.criar_solicitacao(numero="04/2026")
        self._post_nova(numero="")
        self.assertTrue(SolicitacaoCoffeeBreak.objects.filter(numero="05/2026").exists())

    def test_nova_ja_vem_com_o_proximo_numero(self):
        self.criar_solicitacao(numero="41/2026")
        resposta = self.client.get(reverse("coffee_break:nova"))
        self.assertContains(resposta, 'name="numero" value="42"')
        self.assertContains(resposta, "/ 2026")

    def test_numero_repetido_de_outro_lote_da_erro(self):
        outro = LoteCoffeeBreak.objects.create(
            contrato=self.contrato, numero=2, exercicio="2026", quantidade_total=100
        )
        self.criar_solicitacao(lote=outro, numero="41/2026")
        resposta = self._post_nova(numero="41")
        self.assertContains(resposta, "A OS 41/2026 já existe")
        self.assertEqual(SolicitacaoCoffeeBreak.objects.filter(numero="41/2026").count(), 1)

    def test_edicao_mostra_a_sequencia_e_nao_acusa_alteracao(self):
        s = self.criar_solicitacao(numero="41/2026", local_entrega="1DP", responsavel_recebimento="Ana")
        resposta = self.client.get(reverse("coffee_break:editar", args=[s.pk]))
        self.assertContains(resposta, 'name="numero" value="41"')
        s.refresh_from_db()
        versao = str(int(s.atualizado_em.timestamp() * 1_000_000))
        self.client.post(
            reverse("coffee_break:editar", args=[s.pk]),
            {
                "municipio": self.curitiba.pk, "data_solicitacao": "2026-08-01",
                "numero": "41", "descricao_evento": s.descricao_evento,
                "quantidade": "30", "local_entrega": "1DP",
                "responsavel_recebimento": "Ana", "versao": versao,
            },
        )
        s.refresh_from_db()
        self.assertEqual(s.numero, "41/2026")
        self.assertNotIn("número da solicitação", s.historico.last().descricao)


class DescricaoUmaLinhaTests(BaseCoffeeBreakTestCase):
    def test_descricao_vira_uma_linha(self):
        self.client.force_login(self.ascom)
        self.client.post(reverse("coffee_break:nova"), {
            "municipio": self.curitiba.pk, "data_solicitacao": "2026-08-01",
            "descricao_evento": "Ciclo de Palestras\r\n  1DP Curitiba", "quantidade": "10",
        })
        self.assertTrue(
            SolicitacaoCoffeeBreak.objects.filter(descricao_evento="Ciclo de Palestras 1DP Curitiba").exists()
        )

    def test_campo_e_de_uma_linha(self):
        self.client.force_login(self.ascom)
        resposta = self.client.get(reverse("coffee_break:nova"))
        html = resposta.content.decode()
        self.assertRegex(html, r'<input[^>]*name="descricao_evento"')
        self.assertNotRegex(html, r'<textarea[^>]*name="descricao_evento"')


class VisualizadorDaOSTests(BaseCoffeeBreakTestCase):
    """A OS da etapa 1 no editor de documentos de Viagens: barra, pendências
    e a folha editável, gravando na própria solicitação."""

    CHAVE = "coffee_break_ordem_servico"

    def _url(self, nome, s, *args):
        return reverse(f"documentos:editor_{nome}", args=[self.CHAVE, s.pk, *args])

    def test_etapa_1_traz_o_editor_de_documentos(self):
        self.client.force_login(self.ascom)
        s = self.criar_solicitacao(numero="41/2026", local_entrega="1DP", responsavel_recebimento="Ana")
        resposta = self.client.get(reverse("coffee_break:editar", args=[s.pk]))
        self.assertContains(resposta, "data-ofc-doc")
        self.assertContains(resposta, f'data-de-embutir="{self._url("embutido", s)}"')
        self.assertContains(resposta, "js/documento-editor")
        self.assertNotContains(resposta, 'id="sec-os"')
        # O PDF continua abrindo no navegador (Imprimir e o menu do cartão).
        url = reverse("coffee_break:ordem_servico", args=[s.pk])
        self.assertContains(resposta, f'href="{url}"')
        with mock.patch.object(documentos, "ordem_servico_pdf", return_value=b"%PDF-1.7"):
            pdf = self.client.post(url + "?inline=1")
        self.assertEqual(pdf.status_code, 200)
        self.assertEqual(pdf["X-Frame-Options"], "SAMEORIGIN")

    def test_editor_mostra_a_barra_e_a_folha_marcada(self):
        self.client.force_login(self.ascom)
        s = self.criar_solicitacao(numero="41/2026", local_entrega="1DP", responsavel_recebimento="Ana")
        editor = self.client.get(self._url("embutido", s))
        self.assertEqual(editor.status_code, 200)
        self.assertContains(editor, "Tudo salvo")
        self.assertContains(editor, "Campos")
        self.assertContains(editor, reverse("coffee_break:ordem_servico", args=[s.pk]))
        self.assertNotContains(editor, "O PDF ainda não pode ser emitido.")
        folha = self.client.get(self._url("folha", s))
        self.assertEqual(folha.status_code, 200)
        self.assertEqual(folha["X-Frame-Options"], "SAMEORIGIN")
        texto = folha.content.decode()
        self.assertIn(">ORDEM DE SERVIÇO</span>", texto)
        self.assertIn(">41/2026</span>", texto)
        self.assertIn('data-doc-campo="cb_local"', texto)
        # Tudo se edita: o texto do modelo é bloco, e há pontos de quebra.
        self.assertIn('data-doc-bloco="cb_secretaria"', texto)
        self.assertIn('data-doc-bloco="cb_rodape_endereco"', texto)
        self.assertIn('data-doc-quebra="antes_assinatura"', texto)
        self.assertIn('data-doc-campo="cb_objeto"', texto)
        self.assertIn("Avenida Iguaçu, 470", texto)

    def test_pendencias_aparecem_no_editor(self):
        self.client.force_login(self.ascom)
        s = self.criar_solicitacao(numero="41/2026")
        editor = self.client.get(self._url("embutido", s))
        self.assertContains(editor, "O PDF ainda não pode ser emitido.")
        self.assertContains(editor, "Informe o local de entrega.")

    def test_editar_na_folha_grava_na_solicitacao(self):
        import json

        self.client.force_login(self.ascom)
        s = self.criar_solicitacao(numero="41/2026", local_entrega="1DP", responsavel_recebimento="Ana")
        url = self._url("campo", s, "cb_local")
        versao = self.client.get(url).json()["versao"]
        resposta = self.client.patch(
            url, json.dumps({"versao": versao, "valores": {"local_entrega": "  Casa da   Cultura "}}),
            content_type="application/json",
        )
        self.assertEqual(resposta.status_code, 200, resposta.content)
        s.refresh_from_db()
        self.assertEqual(s.local_entrega, "Casa da Cultura")
        # A versão é a mesma do formulário da etapa: salvar depois não acusa conflito.
        self.assertEqual(resposta.json()["versao"], str(int(s.atualizado_em.timestamp() * 1_000_000)))
        # Versão velha é conflito.
        velha = self.client.patch(
            url, json.dumps({"versao": versao, "valores": {"local_entrega": "Outro"}}),
            content_type="application/json",
        )
        self.assertEqual(velha.status_code, 409)

    def test_descricao_travada_depois_da_nota(self):
        import json

        self.client.force_login(self.ascom)
        s = self.criar_solicitacao(numero="41/2026", local_entrega="1DP", responsavel_recebimento="Ana")
        with mock.patch.object(SolicitacaoCoffeeBreak, "financeiro_iniciado", new_callable=mock.PropertyMock, return_value=True):
            url = self._url("campo", s, "cb_objeto")
            versao = self.client.get(url).json()["versao"]
            resposta = self.client.patch(
                url, json.dumps({"versao": versao, "valores": {"descricao_evento": "Outro"}}),
                content_type="application/json",
            )
        self.assertEqual(resposta.status_code, 400)
        s.refresh_from_db()
        self.assertEqual(s.descricao_evento, "Evento de teste")

    def test_cancelada_nao_edita_mas_ve(self):
        import json

        self.client.force_login(self.ascom)
        s = self.criar_solicitacao(numero="41/2026", local_entrega="1DP", responsavel_recebimento="Ana")
        SolicitacaoCoffeeBreak.objects.filter(pk=s.pk).update(cancelada=True)
        self.assertEqual(self.client.get(self._url("embutido", s)).status_code, 200)
        resposta = self.client.patch(
            self._url("campo", s, "cb_local"), json.dumps({"valores": {"local_entrega": "X"}}),
            content_type="application/json",
        )
        self.assertEqual(resposta.status_code, 403)

    def test_texto_do_modelo_editado_vai_para_o_pdf(self):
        import json

        self.client.force_login(self.ascom)
        s = self.criar_solicitacao(numero="41/2026", local_entrega="1DP", responsavel_recebimento="Ana")
        url = self._url("bloco", s, "cb_rotulo_local")
        resposta = self.client.patch(url, json.dumps({"valores": {"conteudo": "LOCAL DA ENTREGA:"}}), content_type="application/json")
        self.assertEqual(resposta.status_code, 200, resposta.content)
        quebra = self.client.patch(self._url("quebra", s, "antes_assinatura"), json.dumps({"ativa": True}), content_type="application/json")
        self.assertEqual(quebra.status_code, 200, quebra.content)
        contexto = documentos._contexto_os(s)
        self.assertEqual(contexto["b"]["cb_rotulo_local"], "LOCAL DA ENTREGA:")
        self.assertEqual(contexto["b"]["cb_titulo"], "ORDEM DE SERVIÇO")
        self.assertIn("antes_assinatura", contexto["quebras"])
        from django.template.loader import render_to_string

        html = render_to_string("coffee_break/documentos/ordem_servico.html", {**contexto, "imagens": {}})
        self.assertIn("LOCAL DA ENTREGA:", html)
        self.assertIn('class="quebra"', html)

    def test_numero_na_folha_segue_as_regras(self):
        import json

        self.client.force_login(self.ascom)
        self.criar_solicitacao(numero="42/2026")
        s = self.criar_solicitacao(numero="41/2026", local_entrega="1DP", responsavel_recebimento="Ana")
        url = self._url("campo", s, "cb_numero")
        versao = self.client.get(url).json()["versao"]
        repetido = self.client.patch(url, json.dumps({"versao": versao, "valores": {"numero": "42"}}), content_type="application/json")
        self.assertEqual(repetido.status_code, 400)
        ok = self.client.patch(url, json.dumps({"versao": versao, "valores": {"numero": "45"}}), content_type="application/json")
        self.assertEqual(ok.status_code, 200, ok.content)
        s.refresh_from_db()
        self.assertEqual(s.numero, "45/2026")

    def test_cadastros_na_folha_sao_da_administracao(self):
        import json

        s = self.criar_solicitacao(numero="41/2026", local_entrega="1DP", responsavel_recebimento="Ana")
        corpo = json.dumps({"valores": {"razao_social": "FAVO E MEL"}})
        self.client.force_login(self.ascom)
        self.assertNotIn('data-doc-campo="cb_fornecedor"', self.client.get(self._url("folha", s)).content.decode())
        self.assertEqual(self.client.patch(self._url("campo", s, "cb_fornecedor"), corpo, content_type="application/json").status_code, 403)
        self.client.force_login(self.admin_modulo)
        self.assertIn('data-doc-campo="cb_fornecedor"', self.client.get(self._url("folha", s)).content.decode())
        url = self._url("campo", s, "cb_fiscal")
        versao = self.client.get(url).json()["versao"]
        resposta = self.client.patch(url, json.dumps({"versao": versao, "valores": {"fiscal_responsavel": "Maria Souza"}}), content_type="application/json")
        self.assertEqual(resposta.status_code, 200, resposta.content)
        self.contrato.refresh_from_db()
        self.assertEqual(self.contrato.fiscal_responsavel, "Maria Souza")

    def test_sem_o_modulo_nao_abre(self):
        s = self.criar_solicitacao(numero="41/2026")
        self.client.force_login(self.sem_modulo)
        self.assertEqual(self.client.get(self._url("embutido", s)).status_code, 403)
        self.assertEqual(self.client.get(self._url("folha", s)).status_code, 403)


class OSDaNovaSolicitacaoTests(BaseCoffeeBreakTestCase):
    """A OS abre já na nova solicitação e acompanha o formulário, sem gravar."""

    def test_nova_solicitacao_abre_o_editor_da_os(self):
        self.client.force_login(self.ascom)
        resposta = self.client.get(reverse("coffee_break:nova"))
        self.assertContains(resposta, f'data-de-embutir="{reverse("coffee_break:nova_os_embutido")}"')
        self.assertContains(resposta, "data-cb-os-nova")
        editor = self.client.get(reverse("coffee_break:nova_os_embutido"))
        self.assertContains(editor, "O PDF ainda não pode ser emitido.")
        self.assertContains(editor, reverse("coffee_break:nova_os_folha"))

    def test_folha_acompanha_o_formulario_sem_gravar(self):
        self.client.force_login(self.ascom)
        antes = SolicitacaoCoffeeBreak.objects.count()
        vazia = self.client.get(reverse("coffee_break:nova_os_folha"))
        self.assertEqual(vazia.status_code, 200)
        self.assertNotContains(vazia, "None")
        folha = self.client.get(reverse("coffee_break:nova_os_folha"), {
            "data_solicitacao": "2026-08-01", "descricao_evento": "Palestra  na 1DP",
            "municipio": self.curitiba.pk, "quantidade": "40", "data_inicio_evento": "2026-10-01",
            "horario_evento": "09:30", "local_entrega": "Auditório",
        })
        self.assertEqual(folha["X-Frame-Options"], "SAMEORIGIN")
        texto = folha.content.decode()
        self.assertIn("ORDEM DE SERVIÇO 01/2026", texto)
        self.assertIn("PADARIA E CONFEITARIA FAVO E MEL LTDA", texto)
        self.assertIn("Palestra na 1DP", texto)
        self.assertIn("Dia 01/10 às 9h30 p/ 40 pessoas.", texto)
        self.assertIn("Auditório", texto)
        self.assertEqual(SolicitacaoCoffeeBreak.objects.count(), antes)

    def test_sem_o_modulo_nao_abre(self):
        self.client.force_login(self.sem_modulo)
        self.assertEqual(self.client.get(reverse("coffee_break:nova_os_folha")).status_code, 403)


class Etapa2ComoEtapa1Tests(BaseCoffeeBreakTestCase):
    """Etapa 2: ofício com número e data automáticos, NF pelo modal de anexo
    e o ofício e o certifico no editor de documentos, tudo editável."""

    def setUp(self):
        import tempfile

        from django.test import override_settings

        pasta = tempfile.TemporaryDirectory(prefix="coffee-etapa2-")
        self.addCleanup(pasta.cleanup)
        config = override_settings(MEDIA_ROOT=pasta.name)
        config.enable()
        self.addCleanup(config.disable)
        self.client.force_login(self.ascom)
        self.s = self.criar_solicitacao(
            numero="41/2026", quantidade=40, local_entrega="1DP", responsavel_recebimento="Ana",
        )
        self.url = reverse("coffee_break:etapa_nota", args=[self.s.pk])

    def _versao(self):
        self.s.refresh_from_db()
        return str(int(self.s.atualizado_em.timestamp() * 1_000_000))

    def test_numero_e_data_do_oficio_ja_vem_preenchidos(self):
        outra = self.criar_solicitacao(numero="40/2026", numero_oficio="124/2026")
        self.assertTrue(outra.pk)
        resposta = self.client.get(self.url)
        self.assertContains(resposta, 'name="numero_oficio" value="125"')
        self.assertContains(resposta, f'value="{dt.date.today().isoformat()}"')
        self.assertContains(resposta, "/ 2026")

    def test_salvar_em_branco_numera_e_data_do_dia(self):
        ano = dt.date.today().year
        self.criar_solicitacao(numero="40/2026", numero_oficio=f"124/{ano}")
        self.client.post(self.url, {"numero_nota_fiscal": "8957", "numero_oficio": "", "data_oficio": "", "versao": self._versao()})
        self.s.refresh_from_db()
        self.assertEqual(self.s.numero_oficio, f"125/{ano}")
        self.assertEqual(self.s.data_oficio, dt.date.today())

    def test_so_a_sequencia_vira_numero_e_nao_repete(self):
        self.criar_solicitacao(numero="40/2026", numero_oficio="124/2026")
        resposta = self.client.post(self.url, {
            "numero_nota_fiscal": "8957", "numero_oficio": "124", "data_oficio": "2026-09-21", "versao": self._versao(),
        })
        self.assertContains(resposta, "O ofício 124/2026 já existe")
        self.client.post(self.url, {
            "numero_nota_fiscal": "8957", "numero_oficio": "130", "data_oficio": "2026-09-21", "versao": self._versao(),
        })
        self.s.refresh_from_db()
        self.assertEqual(self.s.numero_oficio, "130/2026")

    def test_tudo_numa_linha_e_protocolo_com_a_mascara_de_viagens(self):
        resposta = self.client.get(self.url)
        self.assertContains(resposta, "cb-nota-linha-unica")
        self.assertContains(resposta, 'placeholder="00.000.000-0"')
        self.assertContains(resposta, "coffee-break-protocolo.js")
        self.client.post(self.url, {
            "numero_nota_fiscal": "8957", "numero_oficio": "130", "data_oficio": "2026-09-21",
            "protocolo_pcpr_oficio": "266170580", "versao": self._versao(),
        })
        self.s.refresh_from_db()
        self.assertEqual(self.s.protocolo_pcpr_oficio, "26.617.058-0")

    def test_nota_fiscal_pelo_modal_de_anexo(self):
        from django.core.files.uploadedfile import SimpleUploadedFile

        resposta = self.client.get(self.url)
        self.assertContains(resposta, "data-anexar-dialogo")
        self.assertContains(resposta, "Anexar nota fiscal")
        self.assertNotContains(resposta, 'type="file" id="id_arquivo_nota_fiscal"')
        url = reverse("coffee_break:anexar_nota", args=[self.s.pk])
        pdf = SimpleUploadedFile("nf.pdf", _pdf_em_branco(), content_type="application/pdf")
        volta = self.client.post(url, {"arquivo": pdf, "next": self.url})
        self.assertRedirects(volta, self.url, fetch_redirect_response=False)
        self.s.refresh_from_db()
        self.assertTrue(self.s.arquivo_nota_fiscal)
        self.assertContains(self.client.get(self.url), "Trocar")
        # Só PDF.
        texto = SimpleUploadedFile("nf.txt", b"oi", content_type="text/plain")
        self.client.post(url, {"arquivo": texto, "next": self.url})
        self.s.refresh_from_db()
        self.assertTrue(self.s.arquivo_nota_fiscal.name.endswith(".pdf"))
        # Remover.
        self.client.post(url, {"acao": "remover", "next": self.url})
        self.s.refresh_from_db()
        self.assertFalse(self.s.arquivo_nota_fiscal)
        # Endereço de volta de fora do sistema não vale.
        fora = self.client.post(url, {"acao": "remover", "next": "https://exemplo.com/"})
        self.assertRedirects(fora, self.url, fetch_redirect_response=False)

    def test_oficio_e_certifico_no_editor_tudo_editavel(self):
        resposta = self.client.get(self.url)
        for chave in ("coffee_break_oficio", "coffee_break_certifico"):
            embutido = reverse("documentos:editor_embutido", args=[chave, self.s.pk])
            self.assertContains(resposta, f'data-de-embutir="{embutido}"')
            editor = self.client.get(embutido)
            self.assertContains(editor, "O PDF ainda não pode ser emitido.")
            self.assertContains(editor, "Quebras de página")
            folha = self.client.get(reverse("documentos:editor_folha", args=[chave, self.s.pk])).content.decode()
            self.assertIn('data-doc-bloco="cb_secretaria"', folha)
            self.assertIn('data-doc-campo="cb_nota"', folha)
        oficio = self.client.get(reverse("documentos:editor_folha", args=["coffee_break_oficio", self.s.pk])).content.decode()
        self.assertIn('data-doc-bloco="cb_paragrafo_entrega"', oficio)
        self.assertIn('data-doc-campo="cb_oficio_numero"', oficio)
        self.assertIn("40 (quarenta)", oficio)

    def test_texto_editado_do_oficio_vai_para_o_pdf(self):
        import json

        from django.template.loader import render_to_string

        from .editor import TipoCoffee, textos_do_documento

        url = reverse("documentos:editor_bloco", args=["coffee_break_oficio", self.s.pk, "cb_fecho"])
        resposta = self.client.patch(url, json.dumps({"valores": {"conteudo": "Respeitosamente,"}}), content_type="application/json")
        self.assertEqual(resposta.status_code, 200, resposta.content)
        b, quebras = textos_do_documento(TipoCoffee.OFICIO, self.s)
        self.assertEqual(b["cb_fecho"], "Respeitosamente,")
        # O texto do certifico não muda com o do ofício.
        b_cert, _ = textos_do_documento(TipoCoffee.CERTIFICO, self.s)
        self.assertEqual(b_cert["cb_titulo"], "CERTIFICO DIGITAL")
        from .models import ConfiguracaoCoffeeBreak

        html = render_to_string("coffee_break/documentos/oficio.html", {
            "s": self.s, "contrato": self.contrato, "config": ConfiguracaoCoffeeBreak.atual(), "b": b,
            "quebras": quebras, "imagens": {}, "data_extenso": "21 de Setembro de 2026", "quantidade_extenso": "quarenta",
        })
        self.assertIn("Respeitosamente,", html)
        self.assertNotIn("Atenciosamente,", html)

    def test_numero_da_nota_na_folha_grava_na_solicitacao(self):
        import json

        url = reverse("documentos:editor_campo", args=["coffee_break_certifico", self.s.pk, "cb_nota"])
        versao = self.client.get(url).json()["versao"]
        resposta = self.client.patch(url, json.dumps({"versao": versao, "valores": {"numero_nota_fiscal": " 8957 "}}), content_type="application/json")
        self.assertEqual(resposta.status_code, 200, resposta.content)
        self.s.refresh_from_db()
        self.assertEqual(self.s.numero_nota_fiscal, "8957")


class NumeroDaNotaNoPDFTests(BaseCoffeeBreakTestCase):
    """Etapa 2: basta anexar a nota; o número sai do PDF."""

    def test_le_o_numero_do_danfe_e_da_chave(self):
        from .nota_fiscal import numero_no_texto

        # O DANFE da NF 8957 do processo 26.617.058-0.
        self.assertEqual(numero_no_texto("NF-e\nNº 000.008.957\nSÉRIE 001"), "8957")
        self.assertEqual(numero_no_texto("CHAVE DE ACESSO\n4126 0935 0147 1900 0166 5500 1000 0089 5715 7240 4356"), "8957")
        self.assertEqual(numero_no_texto("Número da NFS-e\n00000456"), "456")
        self.assertEqual(numero_no_texto("NFS-e Nº 1234"), "1234")
        self.assertEqual(numero_no_texto("Documento sem número de nota 2026"), "")

    def test_anexar_a_nota_preenche_o_numero(self):
        import tempfile

        from django.core.files.uploadedfile import SimpleUploadedFile
        from django.test import override_settings

        self.client.force_login(self.ascom)
        s = self.criar_solicitacao(numero="41/2026", local_entrega="1DP", responsavel_recebimento="Ana")
        url = reverse("coffee_break:anexar_nota", args=[s.pk])
        with tempfile.TemporaryDirectory() as pasta, override_settings(MEDIA_ROOT=pasta):
            with mock.patch("coffee_break.nota_fiscal.numero_da_nota", return_value="8957"):
                self.client.post(url, {"arquivo": SimpleUploadedFile("nf.pdf", _pdf_em_branco(), content_type="application/pdf")})
            s.refresh_from_db()
            self.assertEqual(s.numero_nota_fiscal, "8957")
            tela = self.client.get(reverse("coffee_break:etapa_nota", args=[s.pk]))
            # Lido o número, a tela não pede para digitar.
            self.assertContains(tela, 'type="hidden" name="numero_nota_fiscal" value="8957"')
            # PDF sem número legível: a tela pede o número.
            s.numero_nota_fiscal = ""
            s.save()
            with mock.patch("coffee_break.nota_fiscal.numero_da_nota", return_value=""):
                resposta = self.client.post(url, {"arquivo": SimpleUploadedFile("nf.pdf", _pdf_em_branco(), content_type="application/pdf")}, follow=True)
            self.assertContains(resposta, "não deu para ler o número")
            self.assertContains(resposta, 'placeholder="Não foi lido do PDF — digite"')


class Etapa3VisualizadorTests(EtapasBase):
    """Etapa 3: visualizador inline (sem editor), tudo fechado, PDF único com
    as certidões e aviso de certidão vencida."""

    def test_quatro_arquivos_no_visualizador_fechados(self):
        self._completar_para_protocolo(self.solicitacao)
        resposta = self.client.get(reverse("coffee_break:etapa_protocolo", args=[self.solicitacao.pk]))
        texto = resposta.content.decode()
        for parte in ("os", "oficio", "notas", "contratos"):
            self.assertIn(f'id="anexo-{parte}"', texto)
            self.assertIn(f'data-cb-pdf="{reverse("coffee_break:pacote_parte", args=[self.solicitacao.pk, parte])}"', texto)
        self.assertEqual(texto.count("data-cb-pdf="), 4)
        self.assertNotIn(" open>", texto.split('id="sec-anexo"')[1].split('id="sec-pagamento"')[0])
        self.assertNotIn("data-de-embutir", texto)  # sem editor

    def test_notas_e_certificos_intercalados_e_todos_os_aditivos(self):
        from django.core.files.base import ContentFile

        from .models import AditivoContrato

        self._completar_para_protocolo(self.solicitacao)
        for numero, inicio in (("0100/2024", dt.date(2024, 10, 31)), ("0355/2025", dt.date(2025, 10, 31))):
            aditivo = AditivoContrato(contrato=self.contrato, numero=numero, vigencia_inicio=inicio)
            aditivo.arquivo.save(f"{numero[:4]}.pdf", ContentFile(_pdf_em_branco()), save=True)
        outra = self.criar_solicitacao(numero="42/2026", local_entrega="DP", responsavel_recebimento="Ana", numero_nota_fiscal="8954")
        outra.arquivo_nota_fiscal.save("nf2.pdf", ContentFile(_pdf_em_branco()), save=True)
        services.definir_pagamento_conjunto(self.solicitacao, [outra.pk])
        self.solicitacao.refresh_from_db()
        partes = {p["chave"]: p for p in documentos.partes_do_anexo(self.solicitacao)}
        self.assertEqual(
            [i["chave"] for i in partes["notas"]["itens"]],
            [f"nota-{self.solicitacao.pk}", f"certifico-{self.solicitacao.pk}", f"nota-{outra.pk}", f"certifico-{outra.pk}"],
        )
        contratos = [i["titulo"] for i in partes["contratos"]["itens"]]
        self.assertEqual(contratos[:3], ["Contrato 0762/2024", "Termo aditivo 0100/2024", "Termo aditivo 0355/2025"])
        self.assertEqual(sum(1 for t in contratos if t.startswith("Certidão")), 5)
        self.assertEqual(len(partes["os"]["itens"]), 2)
        from pypdf import PdfReader

        for parte in documentos.PARTES:
            with mock.patch.object(documentos, "ordem_servico_pdf", return_value=_pdf_em_branco()), \
                 mock.patch.object(documentos, "oficio_pdf", return_value=_pdf_em_branco()), \
                 mock.patch.object(documentos, "certifico_pdf", return_value=_pdf_em_branco()):
                pdf = PdfReader(io.BytesIO(documentos.parte_pdf(self.solicitacao, parte)))
            self.assertGreaterEqual(len(pdf.pages), 1, parte)
        resposta = self.client.get(reverse("coffee_break:pacote_parte", args=[self.solicitacao.pk, "contratos"]))
        self.assertEqual(resposta["Content-Type"], "application/pdf")

    def test_certidao_vencida_entra_no_pdf_unico_com_aviso(self):
        from pypdf import PdfReader

        from .models import CertidaoFornecedor, TipoCertidao

        self._completar_para_protocolo(self.solicitacao)
        CertidaoFornecedor.objects.filter(tipo=TipoCertidao.FGTS).update(validade=dt.date(2020, 1, 1))
        resposta = self.client.get(reverse("coffee_break:etapa_protocolo", args=[self.solicitacao.pk]))
        self.assertContains(resposta, "Certidão vencida.")
        self.assertContains(resposta, 'cb-st--vencida">Certidão vencida')
        itens = documentos.itens_anexo(self.solicitacao)
        todas = sum(1 for item in itens if item["disponivel"])
        self.assertEqual(todas, len(itens))
        pdf = PdfReader(io.BytesIO(documentos.pacote_protocolo_pdf(self.solicitacao)))
        self.assertGreater(len(pdf.pages), 10)

    def test_pdf_unico_junta_o_que_existe(self):
        from .models import CertidaoFornecedor

        self._completar_para_protocolo(self.solicitacao)
        CertidaoFornecedor.objects.all().delete()
        avisos = documentos.avisos_do_pacote(documentos.itens_anexo(self.solicitacao))
        self.assertEqual(len(avisos["faltando"]), 5)
        resposta = self.client.get(reverse("coffee_break:pacote_protocolo", args=[self.solicitacao.pk]))
        self.assertEqual(resposta["Content-Type"], "application/pdf")


TEXTO_CONTRATO = """SECRETARIA DE ESTADO DA SEGURANÇA PÚBLICA
SETOR DE CONTRATOS E CONVÊNIOS – CONTRATO – Nº 0762/2024 – GMS Nº 7339/2024
CONTRATANTE: O ESTADO DO PARANÁ, inscrito no CNPJ sob n. º 76.416.932/0001-81
CONTRATADO(A): PADARIA E CONFEITARIA FAVO E MEL LTDA , CNPJ nº
35.014.719/0001-66, com sede na Avenida Iguaçu
LOTE - 01
Item Descrição Qtd. Valor Unitário Valor Total
10.000 R$ 20,0000 R$ 200.000,00
3.2 O valor total do contrato é de R$ 200.000,00 (duzentos mil reais).
8.1 O prazo de vigência do contrato é de 1 (um) ano, podendo ser prorrogado
Inserido ao Protocolo 22.906.321-9 por Maria Fernanda Bauer Divino em: 29/10/2024 14:51."""

TEXTO_ADITIVO = """CENTRO DE CONTRATOS E CONVÊNIOS – TERMO ADITIVO Nº 0355/2025
Protocolo nº 24.740.746-4–Contrato nº 0762/2024–GMS 7339/2024–1º Termo Aditivo
CONTRATANTE: O ESTADO DO PARANÁ, inscrito no CNPJ sob n. º 76.416.932/0001-81
CONTRATADO(A): PADARIA E CONFEITARIA FAVO E MEL LTDA, CNPJ nº
35.014.719/0001-66, com sede na Avenida Iguaçu
Fica prorrogada a vigência do contrato pelo prazo de 01 (um) ano, a partir de
31/10/2025 até 30/10/2026.
passando de R$ 200.000,00 (duzentos mil reais) para R$ 210.700,00 (duzentos e dez mil)
LOTE 01
ITEM DESCRIÇÃO QTD. VALOR UNITÁRIO VALOR REPACTUADO
TIPO: Coffee Break, 04 (quatro) tipos de 10.000 R$ 20,0000 R$ 21,07"""


class ContratoLidoDoPDFTests(BaseCoffeeBreakTestCase):
    """Contrato e termo aditivo: basta anexar; o sistema preenche tudo."""

    def test_le_o_contrato(self):
        from .contratos_pdf import ler

        dados = ler(TEXTO_CONTRATO)
        self.assertEqual(dados["tipo"], "contrato")
        self.assertEqual((dados["numero"], dados["numero_gms"]), ("0762/2024", "7339/2024"))
        self.assertEqual(dados["cnpj"], "35014719000166")
        self.assertEqual(dados["razao_social"], "PADARIA E CONFEITARIA FAVO E MEL LTDA")
        self.assertEqual((dados["numero_lote"], dados["quantidade"]), (1, 10000))
        self.assertEqual(str(dados["valor_total"]), "200000.00")
        self.assertEqual(dados["vigencia_fim"], dt.date(2025, 10, 28))
        self.assertTrue(dados["vigencia_estimada"])

    def test_le_o_aditivo(self):
        from .contratos_pdf import ler

        dados = ler(TEXTO_ADITIVO)
        self.assertEqual(dados["tipo"], "aditivo")
        self.assertEqual((dados["termo_aditivo"], dados["numero"]), ("0355/2025", "0762/2024"))
        self.assertEqual((dados["vigencia_inicio"], dados["vigencia_fim"]), (dt.date(2025, 10, 31), dt.date(2026, 10, 30)))
        self.assertFalse(dados["vigencia_estimada"])
        self.assertEqual(str(dados["valor_unitario"]), "21.07")
        self.assertEqual(str(dados["valor_total"]), "210700.00")

    def _anexar(self, texto):
        import tempfile

        from django.core.files.uploadedfile import SimpleUploadedFile
        from django.test import override_settings

        pasta = tempfile.mkdtemp()
        with override_settings(MEDIA_ROOT=pasta), mock.patch("coffee_break.contratos_pdf.texto_do_pdf", return_value=texto):
            return self.client.post(
                reverse("coffee_break:anexar_contrato"),
                {"arquivo": SimpleUploadedFile("doc.pdf", _pdf_em_branco(), content_type="application/pdf")},
                follow=True,
            )

    def test_anexar_contrato_e_aditivo_preenche_tudo(self):
        self.client.force_login(self.admin_modulo)
        resposta = self._anexar(TEXTO_CONTRATO)
        self.assertContains(resposta, "anexado e conferido")
        contrato = ContratoCoffeeBreak.objects.get(numero="0762/2024")
        self.assertEqual(contrato.quantidade_contratada, 10000)
        self.assertTrue(contrato.arquivo_contrato)
        self.assertTrue(contrato.vigencia_estimada)
        self._anexar(TEXTO_ADITIVO)
        contrato.refresh_from_db()
        self.assertEqual(contrato.termo_aditivo, "0355/2025")
        self.assertTrue(contrato.arquivo_termo_aditivo)
        self.assertEqual(contrato.vigencia_fim, dt.date(2026, 10, 30))
        self.assertFalse(contrato.vigencia_estimada)
        self.assertEqual(str(contrato.valor_unitario), "21.0700")

    def test_documento_de_outro_fornecedor_e_recusado(self):
        self.client.force_login(self.admin_modulo)
        outro = Fornecedor.objects.create(razao_social="OUTRA EMPRESA LTDA", cnpj="11222333000181")
        ContratoCoffeeBreak.objects.filter(pk=self.contrato.pk).update(numero="0762/2024", fornecedor=outro)
        resposta = self._anexar(TEXTO_ADITIVO)
        self.assertContains(resposta, "está cadastrado para OUTRA EMPRESA LTDA")

    def test_pdf_que_nao_e_contrato(self):
        self.client.force_login(self.admin_modulo)
        resposta = self._anexar("Um ofício qualquer, sem contrato.")
        self.assertContains(resposta, "não parece ser um contrato")

    def test_so_a_administracao_anexa(self):
        self.client.force_login(self.ascom)
        self.assertEqual(self._anexar(TEXTO_CONTRATO).status_code, 403)


class CertidaoConferidaTests(BaseCoffeeBreakTestCase):
    """Certidão: basta anexar; o sistema confere e lê a validade."""

    TRABALHISTA = (
        "CERTIDÃO NEGATIVA DE DÉBITOS TRABALHISTAS Nome: PADARIA E CONFEITARIA FAVO E MEL LTDA "
        "CNPJ: 35.014.719/0001-66 Validade: 15/02/2027 - 180 (cento e oitenta) dias"
    )

    def _anexar(self, tipo, texto, validade=""):
        import tempfile

        from django.core.files.uploadedfile import SimpleUploadedFile
        from django.test import override_settings

        pasta = tempfile.mkdtemp()
        with override_settings(MEDIA_ROOT=pasta), mock.patch("coffee_break.certidoes.texto_do_pdf", return_value=texto):
            return self.client.post(
                reverse("coffee_break:anexar_certidao", args=[self.fornecedor.pk, tipo]),
                {"arquivo": SimpleUploadedFile("c.pdf", _pdf_em_branco(), content_type="application/pdf"), "validade": validade},
                follow=True,
            )

    def setUp(self):
        self.client.force_login(self.ascom)

    def test_tela_so_com_anexar_e_emitir(self):
        resposta = self.client.get(reverse("coffee_break:certidoes"))
        self.assertContains(resposta, "data-anexar-dialogo")
        self.assertContains(resposta, "data-anexar-validade")
        self.assertNotContains(resposta, 'type="file" name="arquivo" id="arq-')
        self.assertContains(resposta, 'data-copiar-cnpj="35014719000166"')

    def test_certidao_certa_entra_com_a_validade_lida(self):
        from .models import CertidaoFornecedor

        resposta = self._anexar("TRABALHISTA", self.TRABALHISTA)
        self.assertContains(resposta, "conferida e anexada — válida até 15/02/2027")
        self.assertEqual(CertidaoFornecedor.objects.get(tipo="TRABALHISTA").validade, dt.date(2027, 2, 15))

    def test_certidao_de_outro_tipo_ou_cnpj_e_recusada(self):
        from .models import CertidaoFornecedor

        self.assertContains(self._anexar("FGTS", self.TRABALHISTA), "parece ser a certidão Trabalhista, não a FGTS")
        outro = self.TRABALHISTA.replace("35.014.719/0001-66", "11.222.333/0001-81")
        self.assertContains(self._anexar("TRABALHISTA", outro), "não é de PADARIA E CONFEITARIA FAVO E MEL LTDA")
        self.assertFalse(CertidaoFornecedor.objects.exists())

    def test_pdf_imagem_pede_a_validade(self):
        from .models import CertidaoFornecedor

        self.assertContains(self._anexar("MUNICIPAL", "Firefox https://cnd-cidadao.curitiba.pr.gov.br"), "parece uma imagem")
        resposta = self._anexar("MUNICIPAL", "Firefox https://cnd-cidadao.curitiba.pr.gov.br", "2026-12-01")
        self.assertContains(resposta, "vale a data informada")
        self.assertEqual(CertidaoFornecedor.objects.get(tipo="MUNICIPAL").validade, dt.date(2026, 12, 1))


class PagamentoConjuntoTests(EtapasBase):
    """Várias OS do mesmo lote num ofício e num protocolo, como o 26.613.666-8
    (notas 8952 e 8954): ofício único, um certifico por nota, espelhadas."""

    def setUp(self):
        super().setUp()
        LoteCoffeeBreak.objects.filter(pk=self.lote.pk).update(quantidade_total=500)
        self.a = self.solicitacao
        self.a.descricao_evento = "Encerramento do Curso Técnico Profissional"
        self.a.quantidade = 80
        self.a.numero_nota_fiscal = "8952"
        self.a.save()
        self.b = self.criar_solicitacao(
            numero="42/2026", descricao_evento="Reunião da Delegacia de Fazenda Rio Grande", quantidade=40,
            local_entrega="DP", responsavel_recebimento="Ana", numero_nota_fiscal="8954",
        )

    def _salvar_nota(self, s, **extra):
        s.refresh_from_db()
        dados = {
            "numero_nota_fiscal": s.numero_nota_fiscal, "numero_oficio": "123", "data_oficio": "2026-09-21",
            "versao": str(int(s.atualizado_em.timestamp() * 1_000_000)),
        }
        dados.update(extra)
        return self.client.post(reverse("coffee_break:etapa_nota", args=[s.pk]), dados)

    def test_lista_so_as_os_do_mesmo_lote_em_aberto(self):
        outro_lote = LoteCoffeeBreak.objects.create(contrato=self.contrato, numero=2, exercicio="2026", quantidade_total=100)
        fora = self.criar_solicitacao(lote=outro_lote, numero="43/2026")
        protocolada = self.criar_solicitacao(numero="44/2026", numero_nota_fiscal="1", protocolo_pagamento="26.000.000-1")
        candidatas = list(services.candidatas_ao_pagamento(self.a))
        self.assertIn(self.b, candidatas)
        self.assertNotIn(fora, candidatas)
        self.assertNotIn(protocolada, candidatas)
        tela = self.client.get(reverse("coffee_break:etapa_nota", args=[self.a.pk]))
        self.assertContains(tela, "Vincular outra OS")
        self.assertContains(tela, 'name="vinculadas" value="%d"' % self.b.pk)

    def test_vincular_espelha_o_oficio_e_o_protocolo(self):
        resposta = self._salvar_nota(self.a, vinculadas_enviado="1", vinculadas=[self.b.pk])
        self.assertEqual(resposta.status_code, 302, resposta.context and resposta.context.get("erros"))
        self.a.refresh_from_db()
        self.b.refresh_from_db()
        self.assertEqual(self.b.pagamento_com, self.a)
        self.assertEqual([s.pk for s in self.b.grupo_pagamento()], [self.a.pk, self.b.pk])
        self.assertEqual(self.b.numero_oficio, "123/2026")
        self.assertEqual(self.b.data_oficio, dt.date(2026, 9, 21))
        # O que se faz na etapa 2 da outra vale para as duas.
        self._salvar_nota(self.b, numero_oficio="125", protocolo_pcpr_oficio="266136668")
        self.a.refresh_from_db()
        self.assertEqual(self.a.numero_oficio, "125/2026")
        self.assertEqual(self.a.protocolo_pcpr_oficio, "26.613.666-8")
        # A tela das duas mostra o pagamento conjunto e um certifico por nota.
        tela = self.client.get(reverse("coffee_break:etapa_nota", args=[self.b.pk]))
        self.assertContains(tela, "Pagamento conjunto:")
        self.assertContains(tela, "Certifico digital — NF 8952")
        self.assertContains(tela, "Certifico digital — NF 8954")

    def test_marcar_na_lista_ja_vincula(self):
        url = reverse("coffee_break:vincular_pagamento", args=[self.a.pk])
        self.assertEqual(self.client.post(url, {"vinculadas": [self.b.pk]}).json(), {"ok": True})
        self.b.refresh_from_db()
        self.assertEqual(self.b.pagamento_com_id, self.a.pk)
        tela = self.client.get(reverse("coffee_break:etapa_nota", args=[self.a.pk]))
        self.assertContains(tela, 'data-anexar-os="%d"' % self.b.pk)
        self.assertEqual(self.client.post(url, {}).json(), {"ok": True})
        self.b.refresh_from_db()
        self.assertIsNone(self.b.pagamento_com_id)
        outro_lote = LoteCoffeeBreak.objects.create(contrato=self.contrato, numero=2, exercicio="2026", quantidade_total=100)
        fora = self.criar_solicitacao(lote=outro_lote, numero="43/2026")
        self.assertEqual(self.client.post(url, {"vinculadas": [fora.pk]}).status_code, 400)

    def test_oficio_unico_e_textos_no_plural(self):
        services.definir_pagamento_conjunto(self.a, [self.b.pk])
        self.a.refresh_from_db()
        self.b.refresh_from_db()
        self.assertEqual(documentos.juntar(documentos.notas_do_pagamento(self.b)), "8952 e 8954")
        itens = documentos.itens_do_oficio(self.b)
        self.assertEqual([i["s"].pk for i in itens], [self.a.pk, self.b.pk])
        self.assertEqual(itens[0]["quantidade_extenso"], "oitenta")
        textos = documentos.textos_eprotocolo(self.b)
        self.assertEqual(textos["detalhamento"], "ENVIO P/ PAGAMENTO DAS NOTAS FISCAIS N 8952 E 8954 - (PADARIA E CONFEITARIA FAVO E MEL)")
        self.assertIn("o pagamento das Notas fiscais n° 8952 e 8954.", textos["despacho"])
        from django.template.loader import render_to_string

        from .editor import TipoCoffee, textos_do_documento
        from .models import ConfiguracaoCoffeeBreak

        b, quebras = textos_do_documento(TipoCoffee.OFICIO, self.a)
        html = render_to_string("coffee_break/documentos/oficio.html", {
            "s": self.a, "contrato": self.contrato, "config": ConfiguracaoCoffeeBreak.atual(), "b": b, "quebras": quebras,
            "imagens": {}, "data_extenso": "21 de Setembro de 2026", "itens": itens, "notas": "8952 e 8954", "varias_notas": True,
        })
        self.assertIn("Encerramento do Curso Técnico Profissional - Coffee Break para 80 (oitenta)", html)
        self.assertIn("Reunião da Delegacia de Fazenda Rio Grande - Coffee Break para 40 (quarenta)", html)
        self.assertIn("Encaminho, em anexo, as Notas Fiscais n° 8952 e 8954, devidamente atestada", html)

    def test_anexo_com_nota_e_certifico_de_cada_os(self):
        services.definir_pagamento_conjunto(self.a, [self.b.pk])
        chaves = [item["chave"] for item in documentos.itens_anexo(self.a)]
        self.assertEqual(chaves[:5], ["oficio", f"nota-{self.a.pk}", f"certifico-{self.a.pk}", f"nota-{self.b.pk}", f"certifico-{self.b.pk}"])
        self.assertEqual(chaves.count("certidao-fgts"), 1)

    def test_marco_do_pagamento_vale_para_todas(self):
        services.definir_pagamento_conjunto(self.a, [self.b.pk])
        self.a.refresh_from_db()
        services.registrar_marco(self.a, self.ascom, "26.613.666-8")
        self.b.refresh_from_db()
        self.assertEqual(self.b.protocolo_pagamento, "26.613.666-8")

    def test_desvincular(self):
        services.definir_pagamento_conjunto(self.a, [self.b.pk])
        self._salvar_nota(self.a, vinculadas_enviado="1")
        self.b.refresh_from_db()
        self.assertIsNone(self.b.pagamento_com)
        self.assertEqual(self.a.grupo_pagamento(), [self.a])

    def test_os_sem_nota_nao_recebe_protocolo_nem_atesto(self):
        """m024: salvar a etapa 2 de uma OS não leva o protocolo para a OS do grupo sem nota."""
        SolicitacaoCoffeeBreak.objects.filter(pk=self.b.pk).update(numero_nota_fiscal="")
        services.definir_pagamento_conjunto(self.a, [self.b.pk])
        self._salvar_nota(self.a, protocolo_pcpr_oficio="266136668")
        self.a.refresh_from_db()
        self.b.refresh_from_db()
        self.assertEqual(self.b.protocolo_pcpr_oficio, "26.613.666-8")
        self.assertEqual(self.b.protocolo_pagamento, "")
        # Nem a própria OS recebe o protocolo enquanto o ofício não pode ser gerado.
        self.assertEqual(self.a.protocolo_pagamento, "")
        self.assertFalse(services.marcar_atesto(self.a))
        self.assertEqual(self.b.situacao_financeira, SituacaoFinanceira.AGUARDANDO_NOTA_FISCAL)
        # O marco registrado à mão também não passa para a OS sem nota.
        services.registrar_marco(self.a, self.ascom, "26.613.666-8")
        self.b.refresh_from_db()
        self.assertEqual(self.b.protocolo_pagamento, "")
        self.assertIsNone(self.b.data_atesto_gaf)
        # Chegou a nota da outra: o protocolo vale para as duas.
        self._salvar_nota(self.b, numero_nota_fiscal="8954", protocolo_pcpr_oficio="266136668")
        self.b.refresh_from_db()
        self.assertEqual(self.b.protocolo_pagamento, "26.613.666-8")

    def test_copia_do_pagamento_vai_para_o_historico_e_a_auditoria(self):
        """m029: o que o pagamento conjunto copia fica no histórico e na trilha da outra OS."""
        from auditoria.models import RegistroAuditoria

        services.definir_pagamento_conjunto(self.a, [self.b.pk], self.ascom)
        with self.captureOnCommitCallbacks(execute=True):
            self._salvar_nota(self.a, numero_oficio="130", protocolo_pcpr_oficio="266136668")
        self.b.refresh_from_db()
        self.assertEqual(self.b.numero_oficio, "130/2026")
        copia = self.b.historico.filter(descricao__contains="número do ofício: 130/2026").first()
        self.assertIsNotNone(copia)
        self.assertTrue(copia.descricao.startswith("Copiado da OS 41/2026"))
        self.assertEqual(copia.usuario, self.ascom)
        self.assertTrue(self.b.historico.filter(descricao__contains="protocolo de pagamento: 26.613.666-8").exists())
        trilha = RegistroAuditoria.objects.filter(
            modelo="coffee_break.solicitacaocoffeebreak", objeto_id=str(self.b.pk)
        )
        self.assertTrue(any("numero_oficio" in r.alteracoes for r in trilha))

    def test_os_cancelada_sai_do_oficio_e_do_anexo(self):
        """m025: a OS cancelada deixa o pagamento conjunto; a principal cancelada passa a vez."""
        c = self.criar_solicitacao(
            numero="43/2026", descricao_evento="Palestra C", quantidade=10,
            local_entrega="DP", responsavel_recebimento="Ana", numero_nota_fiscal="8960",
        )
        services.definir_pagamento_conjunto(self.a, [self.b.pk, c.pk])
        self.b.refresh_from_db()
        services.cancelar(self.b, self.ascom, "Evento desmarcado")
        self.b.refresh_from_db()
        self.assertIsNone(self.b.pagamento_com_id)
        self.assertEqual([s.pk for s in self.a.grupo_pagamento()], [self.a.pk, c.pk])
        self.assertEqual(documentos.juntar(documentos.notas_do_pagamento(self.a)), "8952 e 8960")
        self.assertNotIn(f"nota-{self.b.pk}", [i["chave"] for i in documentos.itens_anexo(self.a)])
        self.assertTrue(self.a.historico.filter(descricao__contains="42/2026 foi cancelada").exists())
        # Cancelar a principal: a próxima assume o pagamento.
        self.a.refresh_from_db()
        services.cancelar(self.a, self.ascom, "Evento desmarcado")
        c.refresh_from_db()
        self.assertIsNone(c.pagamento_com_id)
        self.assertEqual([s.pk for s in c.grupo_pagamento()], [c.pk])
        # Mesmo que algum registro antigo ainda aponte para o grupo, cancelada não entra.
        SolicitacaoCoffeeBreak.objects.filter(pk=self.b.pk).update(pagamento_com=c)
        self.assertEqual([s.pk for s in c.grupo_pagamento()], [c.pk])

    def test_so_entra_os_do_mesmo_lote(self):
        from django.core.exceptions import ValidationError

        outro_lote = LoteCoffeeBreak.objects.create(contrato=self.contrato, numero=2, exercicio="2026", quantidade_total=100)
        fora = self.criar_solicitacao(lote=outro_lote, numero="43/2026")
        with self.assertRaises(ValidationError):
            services.definir_pagamento_conjunto(self.a, [fora.pk])


class ListaEBaixarTests(EtapasBase):
    """Menu da lista (editar, baixar arquivos, cancelar, excluir), o atesto
    no dia em que se baixam os arquivos e o despacho do eProtocolo."""

    def test_menu_da_lista(self):
        resposta = self.client.get(reverse("coffee_break:solicitacoes"))
        texto = resposta.content.decode()
        self.assertIn(reverse("coffee_break:editar", args=[self.solicitacao.pk]), texto)
        self.assertIn("data-baixar-documentos", texto)
        self.assertIn(reverse("coffee_break:baixar_arquivos", args=[self.solicitacao.pk]), texto)
        self.assertIn(reverse("coffee_break:cancelar", args=[self.solicitacao.pk]), texto)
        self.assertIn(reverse("coffee_break:excluir", args=[self.solicitacao.pk]), texto)
        self.assertIn("data-baixar-dialogo", texto)
        self.assertNotIn("Registrar andamento", texto)

    def test_baixar_arquivos_escolhidos_e_marca_o_atesto(self):
        import zipfile

        self._completar_para_protocolo(self.solicitacao)
        self.solicitacao.protocolo_pagamento = "26.617.058-0"
        self.solicitacao.save()
        url = reverse("coffee_break:baixar_arquivos", args=[self.solicitacao.pk])
        with mock.patch.object(documentos, "parte_pdf", return_value=_pdf_em_branco()):
            um = self.client.post(url, {"itens": ["oficio"], "saida": "separados"})
            self.assertEqual(um["Content-Type"], "application/pdf")
            varios = self.client.post(url, {"itens": ["os", "oficio", "notas", "contratos"], "saida": "separados"})
            self.assertEqual(varios["Content-Type"], "application/zip")
            self.assertEqual(len(zipfile.ZipFile(io.BytesIO(varios.content)).namelist()), 4)
            unico = self.client.post(url, {"itens": ["oficio", "notas"], "saida": "unico"})
            self.assertEqual(unico["Content-Type"], "application/pdf")
        self.solicitacao.refresh_from_db()
        self.assertEqual(self.solicitacao.data_atesto_gaf, dt.date.today())

    def test_sem_protocolo_nao_marca_atesto(self):
        self._completar_para_protocolo(self.solicitacao)
        with mock.patch.object(documentos, "parte_pdf", return_value=_pdf_em_branco()):
            self.client.get(reverse("coffee_break:pacote_parte", args=[self.solicitacao.pk, "oficio"]) + "?baixar=1")
        self.solicitacao.refresh_from_db()
        self.assertIsNone(self.solicitacao.data_atesto_gaf)

    def test_excluir_so_antes_da_nota(self):
        livre = self.criar_solicitacao(numero="50/2026")
        self.assertRedirects(self.client.post(reverse("coffee_break:excluir", args=[livre.pk])), reverse("coffee_break:solicitacoes"))
        self.assertFalse(SolicitacaoCoffeeBreak.objects.filter(pk=livre.pk).exists())
        com_nota = self.criar_solicitacao(numero="51/2026", numero_nota_fiscal="1")
        self.client.post(reverse("coffee_break:excluir", args=[com_nota.pk]))
        self.assertTrue(SolicitacaoCoffeeBreak.objects.filter(pk=com_nota.pk).exists())

    def test_cancelar_pelo_modal(self):
        url = reverse("coffee_break:cancelar", args=[self.solicitacao.pk])
        resposta = self.client.post(url, {"motivo": "Evento adiado"}, headers={"X-Cadastro-Modal": "1"})
        self.assertEqual(resposta.json(), {"ok": True})
        self.solicitacao.refresh_from_db()
        self.assertTrue(self.solicitacao.cancelada)

    def test_despacho_e_interessado_separados(self):
        self.contrato.termo_aditivo = "0355/2025"
        self.contrato.save()
        textos = documentos.textos_eprotocolo(self.solicitacao)
        rotulos = {c["rotulo"]: c["valor"] for c in textos["campos"]}
        self.assertEqual(rotulos["CNPJ do interessado"], "35.014.719/0001-66")
        self.assertEqual(rotulos["Nome do interessado"], "PADARIA E CONFEITARIA FAVO E MEL LTDA")
        despacho = {c["rotulo"]: c["valor"] for c in textos["despacho_campos"]}
        self.assertEqual(despacho["Assunto do despacho"], "CONTRATO 0762/2024 - GMS 7339/2024 - TERMO ADITIVO No 0355/2025")
        self.assertEqual(despacho["Interessado"], "PADARIA E CONFEITARIA FAVO E MEL LTDA")


class ImportarPlanilhaTelaTests(BaseCoffeeBreakTestCase):
    """A planilha pelo navegador: simula sem gravar, confirma e grava."""

    def setUp(self):
        from django.core.files.uploadedfile import SimpleUploadedFile

        self.client.force_login(self.admin_modulo)
        saida = io.BytesIO()
        _planilha_de_teste().save(saida)
        self.planilha = lambda: SimpleUploadedFile(
            "CONTROLE COFFE ASCOM.xlsx", saida.getvalue(),
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        self.url = reverse("coffee_break:importar_planilha")

    def test_simula_sem_gravar_e_depois_importa(self):
        antes = SolicitacaoCoffeeBreak.objects.count()
        resposta = self.client.post(self.url, {"acao": "simular", "planilha": self.planilha()})
        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, "Resultado da simulação")
        self.assertContains(resposta, "Importar agora")
        self.assertEqual(SolicitacaoCoffeeBreak.objects.count(), antes)

        resposta = self.client.post(self.url, {"acao": "importar"})
        self.assertContains(resposta, "Importação feita")
        self.assertGreater(SolicitacaoCoffeeBreak.objects.count(), antes)
        # O arquivo temporário não fica para trás.
        self.assertNotIn("coffee_importacao", self.client.session)

    def test_importar_sem_simular_volta_com_aviso(self):
        resposta = self.client.post(self.url, {"acao": "importar"})
        self.assertRedirects(resposta, self.url)

    def test_so_aceita_xlsx(self):
        from django.core.files.uploadedfile import SimpleUploadedFile

        resposta = self.client.post(
            self.url, {"acao": "simular", "planilha": SimpleUploadedFile("dados.csv", b"a;b")}
        )
        self.assertRedirects(resposta, self.url)

    def test_operador_comum_nao_acessa(self):
        self.client.force_login(self.ascom)
        self.assertEqual(self.client.get(self.url).status_code, 403)


class PreviaDaOSTests(BaseCoffeeBreakTestCase):
    def test_previa_e_a_folha_em_html_e_pode_ser_embutida(self):
        self.client.force_login(self.ascom)
        s = self.criar_solicitacao(numero="41/2026", local_entrega="1DP", responsavel_recebimento="Ana")
        resposta = self.client.get(reverse("coffee_break:ordem_servico_previa", args=[s.pk]))
        self.assertEqual(resposta.status_code, 200)
        self.assertEqual(resposta["X-Frame-Options"], "SAMEORIGIN")
        self.assertContains(resposta, 'class="folha"')
        self.assertContains(resposta, "ORDEM DE SERVIÇO 41/2026")
        self.assertContains(resposta, "/static/")  # imagens pelo endereço estático, não file://
        self.assertNotContains(resposta, "file://")

    def test_previa_com_pendencia_diz_o_que_falta(self):
        self.client.force_login(self.ascom)
        s = self.criar_solicitacao(numero="41/2026")
        resposta = self.client.get(reverse("coffee_break:ordem_servico_previa", args=[s.pk]))
        self.assertContains(resposta, "Informe o local de entrega.")


class NumeracaoConjuntaComViagensTests(BaseCoffeeBreakTestCase):
    """m041: o ofício e a OS do Coffee Break saem da mesma sequência dos
    ofícios e das ordens de serviço de Viagens, sem repetição."""

    def setUp(self):
        self.client.force_login(self.ascom)

    def _oficio_viagens(self, numero, ano=2026):
        from viagens_oficios.models import Oficio

        return Oficio.objects.create(numero=numero, ano=ano)

    def _os_viagens(self, numero, ano=2026):
        from viagens_ordens.models import OrdemServico

        return OrdemServico.objects.create(numero=numero, ano=ano)

    def test_oficio_segue_o_maior_dos_dois_modulos(self):
        from viagens_oficios.models import Oficio

        self.criar_solicitacao(numero="01/2026", numero_oficio="124/2026")
        self._oficio_viagens(130)
        self.assertEqual(services.proxima_sequencia_oficio(2026), 131)
        self.criar_solicitacao(numero="02/2026", numero_oficio="140/2026")
        # E Viagens enxerga os ofícios do Coffee Break.
        self.assertEqual(Oficio.get_next_available_numero(2026), 141)
        # Números de outro ano não contam.
        self._oficio_viagens(900, ano=2025)
        self.assertEqual(services.proxima_sequencia_oficio(2026), 141)

    def test_os_segue_o_maior_dos_dois_modulos(self):
        from viagens_ordens.models import OrdemServico

        self.criar_solicitacao(numero="10/2026")
        self._os_viagens(15)
        self.assertEqual(services.proximo_numero(2026), "16/2026")
        self.criar_solicitacao(numero="20/2026")
        self.assertEqual(OrdemServico.proximo_numero_livre(2026), (21, None))

    def test_lacuna_de_viagens_ocupada_pelo_coffee_nao_e_reusada(self):
        from viagens_ordens.models import OrdemServico, OrdemServicoNumeroLacuna

        self._os_viagens(8)
        OrdemServicoNumeroLacuna.objects.create(ano=2026, numero=3)
        self.criar_solicitacao(numero="03/2026")
        self.assertEqual(OrdemServico.proximo_numero_livre(2026), (9, None))

    def test_nova_os_em_branco_reserva_na_sequencia_conjunta(self):
        self._os_viagens(30)
        dados = {
            "municipio": self.curitiba.pk, "data_solicitacao": "2026-08-01",
            "descricao_evento": "Evento", "quantidade": "10", "numero": "",
        }
        self.client.post(reverse("coffee_break:nova"), dados)
        self.assertTrue(SolicitacaoCoffeeBreak.objects.filter(numero="31/2026").exists())

    def test_numero_de_os_de_viagens_nao_pode_ser_repetido(self):
        self._os_viagens(5)
        dados = {
            "municipio": self.curitiba.pk, "data_solicitacao": "2026-08-01",
            "descricao_evento": "Evento", "quantidade": "10", "numero": "5",
        }
        resposta = self.client.post(reverse("coffee_break:nova"), dados)
        self.assertContains(resposta, "ordem de serviço de Viagens")
        self.assertFalse(SolicitacaoCoffeeBreak.objects.filter(numero="05/2026").exists())

    def _form_nota(self, s, numero_oficio):
        from .forms import NotaCoffeeBreakForm

        return NotaCoffeeBreakForm(
            {
                "numero_nota_fiscal": "8957", "numero_oficio": numero_oficio, "data_oficio": "2026-09-21",
                "protocolo_pcpr_oficio": "", "versao": str(int(s.atualizado_em.timestamp() * 1_000_000)),
            },
            instance=s,
        )

    def test_oficio_de_viagens_nao_pode_ser_repetido(self):
        s = self.criar_solicitacao(numero="41/2026")
        self._oficio_viagens(125)
        form = self._form_nota(s, "125")
        self.assertFalse(form.is_valid())
        self.assertIn("ofício de Viagens", form.errors["numero_oficio"][0])

    def test_sugerido_que_outro_usou_antes_de_gravar_pega_o_seguinte(self):
        s = self.criar_solicitacao(numero="41/2026")
        self._oficio_viagens(124)
        form = self._form_nota(s, "125")  # o sugerido na tela
        self.assertTrue(form.is_valid(), form.errors)
        # Entre a tela e o salvar, Viagens emitiu o 125.
        self._oficio_viagens(125)
        form.save()
        s.refresh_from_db()
        self.assertEqual(s.numero_oficio, "126/2026")

    def test_digitado_que_outro_usou_antes_de_gravar_e_recusado(self):
        s = self.criar_solicitacao(numero="41/2026")
        form = self._form_nota(s, "200")
        self.assertTrue(form.is_valid(), form.errors)
        self._oficio_viagens(200)
        with self.assertRaises(ValidationError):
            form.save()
        s.refresh_from_db()
        self.assertEqual(s.numero_oficio, "")

    def test_numero_usado_deixa_de_ser_lacuna_em_viagens(self):
        from viagens_oficios.models import Oficio, OficioNumeroLacuna

        self._oficio_viagens(9)
        OficioNumeroLacuna.objects.create(ano=2026, numero=4)
        s = self.criar_solicitacao(numero="41/2026")
        form = self._form_nota(s, "4")
        self.assertTrue(form.is_valid(), form.errors)
        form.save()
        self.assertFalse(OficioNumeroLacuna.objects.filter(ano=2026, numero=4).exists())
        self.assertEqual(Oficio.get_next_available_numero(2026), 10)

    def test_formulario_de_viagens_recusa_numero_do_coffee(self):
        from django import forms as dj_forms

        from viagens_oficios.forms import OficioForm

        self.criar_solicitacao(numero="41/2026", numero_oficio="77/2026")
        oficio = self._oficio_viagens(10)
        form = OficioForm(instance=oficio)
        form.cleaned_data = {"numero": 77}
        with self.assertRaises(dj_forms.ValidationError):
            form.clean_numero()
