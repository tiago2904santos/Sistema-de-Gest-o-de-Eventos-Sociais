import csv
import io

from django.contrib.auth.models import Group
from django.urls import reverse

from cadastros.models import Estado, Municipio, Regiao
from .tests import BaseViagensTestCase


class ParidadeCidadesTests(BaseViagensTestCase):
    def setUp(self):
        self.usuario = self.criar_usuario("cidades_admin")
        self.usuario.groups.add(Group.objects.get_or_create(name="ADMINISTRADOR")[0])
        self.client.force_login(self.usuario)
        self.url = reverse("viagens_cadastros:cidades")
        self.exportar = reverse("viagens_cadastros:cidades_exportar_csv")
        self.estado = Estado.objects.create(nome="ESTADO ÁGUA", sigla="ZT", codigo_ibge=999)
        self.regiao = Regiao.objects.create(nome="REGIÃO ENSAIO CIDADES")
        self.cidade = Municipio.objects.create(nome="CIDADE AÇÚCAR", estado=self.estado, regiao=self.regiao, ativo=False)

    def test_busca_por_nome_uf_e_estado_sem_acentos_inclui_inativos(self):
        for termo in ["acucar", "zt", "estado agua"]:
            response = self.client.get(self.url, {"q": termo})
            self.assertEqual(list(response.context["pagina"]), [self.cidade])
            self.assertContains(response, "ZT · —")
        self.assertNotContains(self.client.get(self.url, {"q": "regiao ensaio cidades"}), "CIDADE AÇÚCAR")

    def test_paginacao_15_ordena_por_uf_depois_nome_e_preserva_busca(self):
        estado = Estado.objects.create(nome="ESTADO ZULU", sigla="ZS", codigo_ibge=998)
        for numero in range(17):
            Municipio.objects.create(nome=f"CIDADE ENSAIO {numero:02d}", estado=estado, regiao=self.regiao)
        response = self.client.get(self.url, {"q": "cidade", "page": 2})
        pagina = response.context["pagina"]
        self.assertEqual(pagina.paginator.per_page, 15)
        self.assertEqual([m.nome for m in pagina], ["CIDADE ENSAIO 15", "CIDADE ENSAIO 16", "CIDADE AÇÚCAR"])
        self.assertContains(response, "q=cidade&amp;page=1")
        self.assertEqual(self.client.get(self.url, {"page": "inválida"}).context["pagina"].number, 1)

    def test_permissao_administrativa_e_consultas_sem_gravacao(self):
        antes = list(Municipio.objects.values())
        for url in [self.url, self.exportar]:
            self.assertEqual(self.client.get(url).status_code, 200)
            self.assertEqual(self.client.post(url, {"nome": "NÃO GRAVAR"}).status_code, 405)
        self.assertEqual(list(Municipio.objects.values()), antes)
        self.client.force_login(self.criar_usuario("cidades_leitor"))
        for url in [self.url, self.exportar]:
            self.assertEqual(self.client.get(url).status_code, 403)

    def test_csv_exporta_toda_base_com_bom_duas_colunas_e_aspas(self):
        self.cidade.nome = 'CIDADE "A", B'
        self.cidade.save()
        response = self.client.get(self.exportar, {"q": "SEM RESULTADO", "page": 99})
        self.assertEqual(response["Content-Disposition"], 'attachment; filename="cidades.csv"')
        self.assertTrue(response.content.startswith(b"\xef\xbb\xbf"))
        linhas = list(csv.reader(io.StringIO(response.content.decode("utf-8-sig"))))
        self.assertEqual(linhas[0], ["Cidade", "UF"])
        self.assertIn(['CIDADE "A", B', "ZT"], linhas)
        self.assertEqual(len(linhas), Municipio.objects.count() + 1)
