from django.test import TestCase

from assistente import resolucao

from .fixtures import criar_geografia, criar_pessoas


class ResolucaoDeEntidades(TestCase):
    def setUp(self):
        self.geo = criar_geografia()
        self.pessoas = criar_pessoas()

    def test_nome_exato_resolve_mesmo_sem_acento(self):
        achado = resolucao.resolver_municipio("maringa")
        self.assertTrue(achado.resolvido)
        self.assertEqual(achado.escolhido, self.geo["maringa"])

    def test_sobrenome_repetido_nao_escolhe_sozinho(self):
        achado = resolucao.resolver_servidor("Silva")
        self.assertEqual(achado.status, resolucao.AMBIGUO)
        self.assertEqual(len(achado.candidatos), 2)
        self.assertIsNone(achado.escolhido)

    def test_nome_completo_desempata(self):
        achado = resolucao.resolver_servidor("João Silva")
        self.assertTrue(achado.resolvido)
        self.assertEqual(achado.escolhido, self.pessoas["joao"])

    def test_termo_desconhecido_nao_vira_palpite(self):
        self.assertEqual(resolucao.resolver_servidor("Ferreira").status, resolucao.NENHUM)

    def test_motorista_so_considera_quem_dirige(self):
        self.assertTrue(resolucao.resolver_servidor("Pereira", apenas_motoristas=True).resolvido)
        self.assertEqual(
            resolucao.resolver_servidor("João Silva", apenas_motoristas=True).status,
            resolucao.NENHUM,
        )

    def test_viatura_pela_placa(self):
        self.assertTrue(resolucao.resolver_viatura("ABC1D23").resolvido)

    def test_prefixo_nao_confunde_municipios_parecidos(self):
        # "MARINGÁ" e "MARIALVA" começam igual; o degrau de igualdade resolve.
        self.assertTrue(resolucao.resolver_municipio("Marialva").resolvido)
        self.assertEqual(resolucao.resolver_municipio("Mari").status, resolucao.AMBIGUO)

    def test_descricao_do_candidato_ajuda_a_escolher(self):
        texto = resolucao.descrever(self.pessoas["joao"])
        self.assertIn("JOÃO SILVA", texto)
        self.assertIn("INVESTIGADOR", texto)
