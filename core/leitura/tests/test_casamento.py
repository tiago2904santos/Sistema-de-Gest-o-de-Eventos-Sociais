from django.test import SimpleTestCase, TestCase

from cadastros.models import Estado, Municipio, Regiao, TipoEvento
from core.leitura.casamento import (
    cadastro_no_texto,
    cadastros_no_texto,
    municipio_no_texto,
    municipios_no_texto,
    protocolo_no_texto,
    quantidade_de_pessoas,
    quantidade_no_texto,
    telefone_no_texto,
    telefones_no_texto,
)


class MunicipioTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        regiao, _ = Regiao.objects.get_or_create(nome="Região Teste")
        cls.pr = Estado.objects.get(sigla="PR")
        cls.to, _ = Estado.objects.get_or_create(sigla="TO", defaults={"nome": "Tocantins", "codigo_ibge": 17})

        def criar(nome, estado=None, ativo=True):
            return Municipio.objects.create(nome=nome, estado=estado or cls.pr, regiao=regiao, ativo=ativo)

        cls.curitiba = criar("Curitiba")
        cls.ponta_grossa = criar("Ponta Grossa")
        cls.pinhais = criar("Pinhais")
        cls.sjp = criar("São José dos Pinhais")
        cls.castro = criar("Castro")
        cls.toledo = criar("Toledo")
        cls.palmas_pr = criar("Palmas")
        cls.palmas_to = criar("Palmas", cls.to)
        cls.diamante = criar("Diamante D'Oeste")
        cls.londrina = criar("Londrina")
        cls.platina = criar("Santo Antônio da Platina")
        cls.foz = criar("Foz do Iguaçu")
        cls.inativo = criar("Cidade Desativada", ativo=False)

    def achar(self, texto, **kwargs):
        achado = municipio_no_texto(texto, **kwargs)
        return achado.valor if achado else None

    def test_ancora_da_confianca_alta(self):
        achado = municipio_no_texto("Solicitamos palestra no Colégio X, em Ponta Grossa, para 120 alunos.")
        self.assertEqual(achado.valor, self.ponta_grossa)
        self.assertEqual(achado.confianca, "A")
        self.assertEqual(achado.exibir, "Ponta Grossa/PR")
        self.assertIn("em Ponta Grossa", achado.trecho)

    def test_sem_ancora_e_sem_acento_confere_depois(self):
        achado = municipio_no_texto("evento para os servidores de londrina")
        self.assertEqual((achado.valor, achado.confianca), (self.londrina, "M"))

    def test_nome_mais_longo_primeiro(self):
        achados = municipios_no_texto("Palestra em São José dos Pinhais.")
        self.assertEqual([a.valor for a in achados], [self.sjp])

    def test_nome_ambiguo_so_vale_com_ancora_e_maiuscula(self):
        self.assertIsNone(self.achar("A reserva do auditório está feita; o Castro Alves é o poeta."))
        self.assertIsNone(self.achar("palestra em castro"))
        self.assertEqual(self.achar("Vamos fazer a ação em Castro no dia 10."), self.castro)
        self.assertEqual(self.achar("Prefeitura Municipal de Toledo"), self.toledo)
        self.assertEqual(self.achar("Local: Ginásio Municipal, Av. Brasil, 100 - Toledo"), self.toledo)
        self.assertEqual(self.achar("Toledo/PR"), self.toledo)

    def test_rua_e_escola_com_nome_de_cidade_nao_contam(self):
        self.assertEqual(self.achar("Evento na Rua Curitiba, 45 - Londrina"), self.londrina)
        self.assertEqual(self.achar("Colégio Estadual Castro Alves, em Londrina"), self.londrina)

    def test_mesmo_nome_em_dois_estados(self):
        self.assertEqual(self.achar("Evento em Palmas"), self.palmas_pr)
        self.assertEqual(self.achar("Evento em Palmas/TO"), self.palmas_to)
        self.assertEqual(self.achar("Evento em Palmas, Tocantins"), self.palmas_to)
        self.assertEqual(self.achar("Evento em Palmas", ddd="(63) 99999-0000"), self.palmas_to)
        self.assertEqual(self.achar("Evento em Palmas", uf_preferida="TO"), self.palmas_to)

    def test_variacoes_de_grafia(self):
        self.assertEqual(self.achar("no município de Diamante do Oeste"), self.diamante)
        self.assertEqual(self.achar("em Diamante d´Oeste"), self.diamante)
        self.assertEqual(self.achar("Sto. Antônio da Platina"), self.platina)
        self.assertEqual(self.achar("evento em Foz"), self.foz)
        self.assertEqual(self.achar("unidade de pinhias"), self.pinhais)

    def test_municipio_inativo_nao_casa(self):
        self.assertIsNone(self.achar("em Cidade Desativada"))

    def test_mais_de_um_citado_ancorado_vence(self):
        achados = municipios_no_texto("Somos de Londrina e a palestra será em Ponta Grossa.")
        self.assertEqual(achados[0].valor, self.ponta_grossa)
        self.assertEqual(achados[1].valor, self.londrina)

    def test_lista_passada_pelo_chamador(self):
        achado = municipio_no_texto("em Curitiba", Municipio.objects.filter(pk=self.curitiba.pk))
        self.assertEqual(achado.valor, self.curitiba)
        self.assertIsNone(municipio_no_texto("em Londrina", Municipio.objects.filter(pk=self.curitiba.pk)))


class CadastroTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        nomes = ["Capacitação", "Evento", "Inauguração/Solenidade", "PCPR na Comunidade", "Palestra", "Paraná em Ação"]
        cls.tipos = {nome: TipoEvento.objects.get_or_create(nome=nome)[0] for nome in nomes}
        cls.sinonimos = {
            "curso": "Capacitação",
            "treinamento": "Capacitação",
            "formatura": "Inauguração/Solenidade",
            "bate-papo": "Palestra",
            "roda de conversa": "Palestra",
            "jurídic*": "Capacitação",
        }

    def opcoes(self):
        return TipoEvento.objects.filter(nome__in=self.tipos)

    def test_nome_sem_acento_e_plural(self):
        achado = cadastro_no_texto("Pedido de PALESTRAS para os alunos", self.opcoes())
        self.assertEqual(achado.valor, self.tipos["Palestra"])
        self.assertEqual(achado.confianca, "M")

    def test_sinonimo_e_prefixo(self):
        self.assertEqual(cadastro_no_texto("Convite para a formatura", self.opcoes(), sinonimos=self.sinonimos).valor,
                         self.tipos["Inauguração/Solenidade"])
        self.assertEqual(cadastro_no_texto("uma roda de conversa", self.opcoes(), sinonimos=self.sinonimos).valor,
                         self.tipos["Palestra"])
        self.assertEqual(cadastro_no_texto("orientação jurídica", self.opcoes(), sinonimos=self.sinonimos).valor,
                         self.tipos["Capacitação"])

    def test_nome_mais_especifico_vence(self):
        achado = cadastro_no_texto("Paraná em Ação com palestra e evento", self.opcoes())
        self.assertEqual(achado.valor, self.tipos["Paraná em Ação"])

    def test_varios_para_campo_multiplo(self):
        achados = cadastros_no_texto("palestra e curso", self.opcoes(), sinonimos=self.sinonimos)
        self.assertEqual({a.valor for a in achados}, {self.tipos["Palestra"], self.tipos["Capacitação"]})

    def test_padrao_quando_nada_casa(self):
        achado = cadastro_no_texto("nada a ver", self.opcoes(), padrao="Evento")
        self.assertEqual((achado.valor, achado.confianca), (self.tipos["Evento"], "B"))
        self.assertIsNone(cadastro_no_texto("nada a ver", self.opcoes()))


class TelefoneTests(SimpleTestCase):
    def test_prefere_celular_e_le_ramal(self):
        achados = telefones_no_texto("Fone (43)3322-1100 ramal 12 ou 41 99999-0000")
        self.assertEqual([a.valor for a in achados], ["(43) 3322-1100", "(41) 99999-0000"])
        self.assertEqual(achados[0].exibir, "(43) 3322-1100 ramal 12")
        self.assertEqual(achados[0].detalhes["tipo"], "fixo")
        self.assertEqual(telefone_no_texto("Fone (43)3322-1100 ramal 12 ou 41 99999-0000").valor, "(41) 99999-0000")

    def test_formatos(self):
        for texto in ("+55 (41) 9 9876-5432", "41998765432", "41 99876.5432"):
            with self.subTest(texto=texto):
                self.assertEqual(telefone_no_texto(texto).valor, "(41) 99876-5432")

    def test_cpf_protocolo_e_numero_sem_ddd_nao_sao_telefone(self):
        for texto in (
            "CPF 529.982.247-25",
            "52998224725",
            "CPF 123.***.***-00",
            "protocolo 26.613.666-8",
            "ramal 3322-1100",
            "conta 12345-6",
        ):
            with self.subTest(texto=texto):
                self.assertIsNone(telefone_no_texto(texto))

    def test_so_com_ddd_valido(self):
        self.assertIsNone(telefone_no_texto("(00) 99999-0000"))


class ProtocoloTests(SimpleTestCase):
    def test_so_com_ancora(self):
        self.assertEqual(protocolo_no_texto("protocolo nº 26.613.666-8").valor, "26.613.666-8")
        self.assertEqual(protocolo_no_texto("e-Protocolo: 26613666-8").valor, "26.613.666-8")
        self.assertEqual(protocolo_no_texto("Processo 26.617.058-0 de 10/09").valor, "26.617.058-0")

    def test_cpf_telefone_e_rg_nao_viram_protocolo(self):
        for texto in (
            "CPF 123.456.789-00",
            "CPF 123.***.***-00",
            "41 99999-0000",
            "número 26.613.666-8",
            "protocolo do RG 12.345.678-9",
        ):
            with self.subTest(texto=texto):
                self.assertIsNone(protocolo_no_texto(texto))


class QuantidadeTests(SimpleTestCase):
    def test_pessoas(self):
        casos = {
            "120 alunos": 120,
            "para cerca de 80 participantes": 80,
            "80 (oitenta) participantes": 80,
            "Público estimado: 200": 200,
            "turmas de 30 alunos, 120 alunos no total": 120,
            "às 14h para 1.200 pessoas": 1200,
            "150 servidores públicos": 150,
        }
        for texto, esperado in casos.items():
            with self.subTest(texto=texto):
                self.assertEqual(quantidade_de_pessoas(texto).valor, esperado)

    def test_numero_que_nao_e_publico(self):
        for texto in ("alunos do 9º ano", "R$ 50,00 por pessoa", "10 dias para servidores", "às 14h"):
            with self.subTest(texto=texto):
                self.assertIsNone(quantidade_de_pessoas(texto))

    def test_palavras_do_chamador(self):
        achado = quantidade_no_texto("previsão de 300 atendimentos de RG", ["atendimentos", "carteiras", "CIN"])
        self.assertEqual(achado.valor, 300)
        self.assertIsNone(quantidade_no_texto("Público estimado: 200", ["carteiras"]))
