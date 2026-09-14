from django.urls import reverse

from .models import Combustivel, ConfiguracaoSistema, Servidor, Unidade, Viatura
from .permissions import GRUPO_OPERADOR
from .tests import BaseViagensTestCase


class ParidadeViaturasTests(BaseViagensTestCase):
    def setUp(self):
        self.client.force_login(self.criar_usuario("viaturas_paridade", GRUPO_OPERADOR))
        self.lista = reverse("viagens_cadastros:lista", args=["viaturas"])
        self.flex = Combustivel.objects.create(nome="FLEX")
        self.diesel = Combustivel.objects.create(nome="DIESEL")
        self.viatura = Viatura.objects.create(placa="AAA1234", modelo="DÚSTER", tipo="DESCARACTERIZADA", combustivel=self.flex, unidade=self.unidade)

    def test_busca_em_todos_os_dados_sem_duplicar_motoristas(self):
        self.viatura.motoristas.add(Servidor.objects.create(nome="JOÃO SILVA"), Servidor.objects.create(nome="JOÃO SOUZA"))
        for termo in ["AAA1234", "duster", "flex", "descaracterizada", "delegacia", "DC", "joao"]:
            with self.subTest(termo=termo):
                response = self.client.get(self.lista, {"q": termo})
                self.assertEqual(response.context["pagina"].paginator.count, 1)
                self.assertContains(response, "JOÃO SILVA, JOÃO SOUZA")
                self.assertContains(response, "DÚSTER — AAA-1234")

    def test_filtro_prioriza_combustivel_e_ignora_identificador_invalido(self):
        outra = Unidade.objects.create(nome="OUTRA UNIDADE")
        diesel = Viatura.objects.create(placa="BBB1234", combustivel=self.diesel, unidade=outra)
        response = self.client.get(self.lista, {"combustivel": self.diesel.pk, "unidade": self.unidade.pk})
        self.assertEqual([r["objeto"].pk for r in response.context["viaturas"]], [diesel.pk])
        self.assertNotIn("unidade", response.context["querystring"])
        response = self.client.get(self.lista, {"combustivel": "9" * 100, "unidade": self.unidade.pk})
        self.assertEqual([r["objeto"].pk for r in response.context["viaturas"]], [self.viatura.pk])

    def test_filtros_da_unidade_configurada_e_top_tres_respeitam_busca(self):
        cfg = ConfiguracaoSistema.get_singleton()
        cfg.unidade = self.unidade
        cfg.save()
        Viatura.objects.create(placa="BBB1234", modelo="OUTRO", combustivel=self.diesel)
        response = self.client.get(self.lista, {"q": "duster"})
        filtros = response.context["filtros"]
        self.assertEqual([f["rotulo"] for f in filtros], ["Todos (1)", "DC (1)", "DIESEL (0)", "FLEX (1)"])
        self.assertTrue(all("q=duster" in f["valor"] for f in filtros))
        for i in range(3):
            combustivel = Combustivel.objects.create(nome=f"ADICIONAL {i}")
            for j in range(2):
                Viatura.objects.create(placa=f"CCC{i}{j}12", combustivel=combustivel)
        response = self.client.get(self.lista)
        self.assertEqual(len(response.context["filtros"]), 5)
        self.assertTrue(all("ADICIONAL" in f["rotulo"] for f in response.context["filtros"][2:]))

    def test_paginacao_de_15_preserva_busca_e_filtro(self):
        for i in range(16):
            Viatura.objects.create(placa=f"BBB{i:04d}", modelo="MODELO", combustivel=self.flex)
        response = self.client.get(self.lista, {"q": "modelo", "combustivel": self.flex.pk, "page": 2})
        self.assertEqual(response.context["pagina"].paginator.per_page, 15)
        self.assertEqual(len(response.context["viaturas"]), 1)
        self.assertIn("q=modelo", response.context["querystring"])
        self.assertIn(f"combustivel={self.flex.pk}", response.context["querystring"])

    def test_lista_nao_cria_configuracao_e_nao_expoe_acoes_para_leitor(self):
        ConfiguracaoSistema.objects.all().delete()
        self.client.force_login(self.criar_usuario("leitor_viaturas"))
        response = self.client.get(self.lista)
        self.assertFalse(ConfiguracaoSistema.objects.exists())
        self.assertNotContains(response, "data-catalogo-excluir")
        self.assertNotContains(response, "Nova viatura")
        self.assertContains(response, "Nenhum motorista vinculado")

    def test_sem_resultado_preserva_mensagem_da_origem(self):
        response = self.client.get(self.lista, {"q": "zzsemresultado"})
        self.assertContains(response, "Nenhum registro cadastrado")
        self.assertContains(response, "Nenhuma viatura cadastrada ainda.")
        self.assertContains(response, "Nova viatura")

    def test_formulario_proprio_preserva_padrao_e_caminhos_de_gerenciamento(self):
        self.flex.is_padrao = True
        self.flex.save()
        url = reverse("viagens_cadastros:novo", args=["viaturas"])
        response = self.client.get(url)
        self.assertTemplateUsed(response, "pages/viagens_cadastros/viaturas/form.html")
        self.assertTemplateNotUsed(response, "pages/viagens_cadastros/_campos.html")
        self.assertEqual(response.context["combustivel"]["valor"], str(self.flex.pk))
        self.assertEqual(response.context["tipo"]["valor"], Viatura.Tipo.DESCARACTERIZADA)
        for slug in ["combustiveis", "unidades", "servidores"]:
            self.assertIn("next=%2Fviagens%2Fcadastros%2Fviaturas%2Fnovo%2F", response.context[f"url_{slug}"])

    def test_edicao_preserva_motoristas_e_erro_na_placa(self):
        pessoa = Servidor.objects.create(nome="JOÃO DE ENSAIO", cargo=self.cargo, cpf="52998224725")
        self.viatura.motoristas.add(pessoa)
        url = reverse("viagens_cadastros:editar", args=["viaturas", self.viatura.pk])
        response = self.client.get(url)
        self.assertTrue(next(p for p in response.context["pessoas"] if p["valor"] == str(pessoa.pk))["selecionado"])
        response = self.client.post(url, {"placa": "INVALIDA", "modelo": "MODELO DIGITADO", "motoristas": [pessoa.pk]})
        self.assertContains(response, "Placa inválida")
        self.assertContains(response, 'value="MODELO DIGITADO"')
        self.assertTrue(response.context["motoristas_selecionados"])
        self.viatura.refresh_from_db()
        self.assertEqual(self.viatura.placa, "AAA1234")
        self.assertContains(response, "529.982.247-25")

    def test_busca_do_seletor_inclui_identificacao_formatada_e_lotacao(self):
        pessoa = Servidor.objects.create(
            nome="JOÃO DE ENSAIO", cargo=self.cargo, cpf="52998224725",
            rg="12345678", unidade=self.unidade,
        )
        response = self.client.get(reverse("viagens_cadastros:novo", args=["viaturas"]))
        dados = next(p for p in response.context["pessoas"] if p["valor"] == str(pessoa.pk))
        for termo in ["joao", self.cargo.nome.lower(), "529.982.247-25",
                      pessoa.rg_formatado, self.unidade.sigla.lower(), self.unidade.nome.lower()]:
            self.assertIn(termo, dados["busca"])
        self.assertNotIn(pessoa.cpf, dados["busca"])
        self.assertFalse(dados["selecionado"])
        self.assertFalse(self.viatura.motoristas.exists())

    def test_gravacao_dos_motoristas_e_mensagem_de_rascunho(self):
        primeiro = Servidor.objects.create(nome="PRIMEIRO MOTORISTA")
        segundo = Servidor.objects.create(nome="SEGUNDO MOTORISTA")
        url = reverse("viagens_cadastros:novo", args=["viaturas"])
        response = self.client.post(url, {"placa": "DDD1234", "motoristas": [primeiro.pk, segundo.pk]}, follow=True)
        self.assertContains(response, "Viatura salva como rascunho. Complete modelo, combustível e tipo quando possível.")
        viatura = Viatura.objects.get(placa="DDD1234")
        self.assertSetEqual(set(viatura.motoristas.values_list("pk", flat=True)), {primeiro.pk, segundo.pk})
        response = self.client.post(reverse("viagens_cadastros:editar", args=["viaturas", viatura.pk]), {
            "placa": "DDD1234", "modelo": "MODELO", "combustivel": self.flex.pk,
            "tipo": Viatura.Tipo.DESCARACTERIZADA, "motoristas": [segundo.pk],
        }, follow=True)
        self.assertContains(response, "Viatura atualizada com sucesso.")
        self.assertEqual(list(viatura.motoristas.values_list("pk", flat=True)), [segundo.pk])
