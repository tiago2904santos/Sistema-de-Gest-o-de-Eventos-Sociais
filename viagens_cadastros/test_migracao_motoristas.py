"""Exercita a migração que converte motoristas em servidores.

É a peça mais arriscada da fase: roda uma vez, em produção, sobre dados que
não podem ser perdidos. Testá-la pela API do modelo não serviria — o que
precisa de prova é a migração real, com os modelos históricos que ela enxerga.
Por isso o teste anda com o banco para trás, semeia o legado e anda de volta
para a frente.
"""

from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase

# Todos os apps envolvidos são fixados, e não só `solicitacoes`: o estado
# histórico de um alvo só inclui as migrações de que ele depende, e sem
# `accounts` no alvo o `User` da migração viria de antes de ganhar seus campos
# atuais — divergindo das colunas que o banco de teste realmente tem.
ANTES = [
    ("accounts", "0003_setor_modulo_user_setores"),
    ("cadastros", "0007_normaliza_nomes_em_caixa_alta"),
    ("viagens_cadastros", "0002_seed_modulo_viagens"),
    ("solicitacoes", "0016_acao_historico_importacao"),
]
DEPOIS = [
    ("accounts", "0003_setor_modulo_user_setores"),
    ("viagens_cadastros", "0003_remove_cargo_ativo_remove_combustivel_ativo_and_more"),
    ("solicitacoes", "0019_motorista_aponta_para_servidor"),
    ("cadastros", "0008_remove_motorista"),
]


def _criar_usuario(User):
    return User.objects.create(username="criadora", password="")


class MigracaoMotoristaParaServidorTests(TransactionTestCase):
    # A migração cria o cargo MOTORISTA e mexe em `accounts`; sem os apps
    # todos disponíveis o executor não consegue montar o grafo.
    available_apps = None

    def _migrar(self, alvo):
        executor = MigrationExecutor(connection)
        executor.loader.build_graph()
        executor.migrate(alvo)
        executor.loader.build_graph()
        return executor

    def _estado_anterior(self):
        """Volta ao ponto imediatamente anterior à conversão."""
        executor = self._migrar(ANTES)
        return executor.loader.project_state(ANTES).apps

    def _aplicar_conversao(self):
        executor = self._migrar(DEPOIS)
        return executor.loader.project_state(DEPOIS).apps

    def tearDown(self):
        # Deixa o banco no estado final: os outros testes contam com ele.
        self._migrar(DEPOIS)

    def test_motorista_vira_servidor_e_a_solicitacao_segue_apontando_para_ele(self):
        apps = self._estado_anterior()
        Motorista = apps.get_model("cadastros", "Motorista")
        Solicitacao = apps.get_model("solicitacoes", "SolicitacaoEvento")
        User = apps.get_model("accounts", "User")

        motorista = Motorista.objects.create(nome="João da Silva", telefone="(41) 99999-8888")
        usuario = _criar_usuario(User)
        solicitacao = Solicitacao.objects.create(
            criado_por=usuario, motorista=motorista, data_solicitacao="2026-08-01"
        )

        apps = self._aplicar_conversao()
        Servidor = apps.get_model("viagens_cadastros", "Servidor")
        Solicitacao = apps.get_model("solicitacoes", "SolicitacaoEvento")

        servidor = Servidor.objects.get(legado_origem="cadastros.Motorista")
        self.assertEqual(servidor.nome, "JOÃO DA SILVA")
        self.assertEqual(servidor.telefone, "41999998888")
        self.assertEqual(servidor.legado_pk, motorista.pk)
        self.assertEqual(servidor.cargo.nome, "MOTORISTA")

        convertida = Solicitacao.objects.get(pk=solicitacao.pk)
        self.assertEqual(convertida.motorista_id, servidor.pk)

    def test_motoristas_que_sao_a_mesma_pessoa_viram_um_servidor_so(self):
        apps = self._estado_anterior()
        Motorista = apps.get_model("cadastros", "Motorista")
        Solicitacao = apps.get_model("solicitacoes", "SolicitacaoEvento")
        User = apps.get_model("accounts", "User")

        # Difere só em caixa e espaçamento: é a mesma pessoa cadastrada duas vezes.
        primeiro = Motorista.objects.create(nome="José Silva")
        segundo = Motorista.objects.create(nome="JOSÉ  SILVA")
        usuario = _criar_usuario(User)
        uma = Solicitacao.objects.create(
            criado_por=usuario, motorista=primeiro, data_solicitacao="2026-08-01"
        )
        outra = Solicitacao.objects.create(
            criado_por=usuario, motorista=segundo, data_solicitacao="2026-08-02"
        )

        apps = self._aplicar_conversao()
        Servidor = apps.get_model("viagens_cadastros", "Servidor")
        Solicitacao = apps.get_model("solicitacoes", "SolicitacaoEvento")

        self.assertEqual(Servidor.objects.filter(nome="JOSÉ SILVA").count(), 1)
        servidor = Servidor.objects.get(nome="JOSÉ SILVA")
        self.assertEqual(Solicitacao.objects.get(pk=uma.pk).motorista_id, servidor.pk)
        self.assertEqual(Solicitacao.objects.get(pk=outra.pk).motorista_id, servidor.pk)

    def test_fusao_de_duplicatas_preserva_o_telefone_de_qualquer_uma_delas(self):
        apps = self._estado_anterior()
        Motorista = apps.get_model("cadastros", "Motorista")

        # `Motorista` é ordenado por nome, então a linha SEM telefone sai
        # primeiro do banco: sem a fusão, o telefone da outra sumiria.
        Motorista.objects.create(nome="ANA  PAULA", telefone="")
        Motorista.objects.create(nome="Ana Paula", telefone="(41) 99999-8888")

        apps = self._aplicar_conversao()
        Servidor = apps.get_model("viagens_cadastros", "Servidor")

        servidor = Servidor.objects.get(nome="ANA PAULA")
        self.assertEqual(servidor.telefone, "41999998888")

    def test_fusao_de_duplicatas_mantem_a_pessoa_ativa_se_uma_delas_estiver(self):
        apps = self._estado_anterior()
        Motorista = apps.get_model("cadastros", "Motorista")

        Motorista.objects.create(nome="BRUNO  DIAS", ativo=False)
        Motorista.objects.create(nome="Bruno Dias", ativo=True)

        apps = self._aplicar_conversao()
        Servidor = apps.get_model("viagens_cadastros", "Servidor")

        self.assertTrue(Servidor.objects.filter(nome="BRUNO DIAS").exists())

    def test_telefone_repetido_no_legado_nao_derruba_a_conversao(self):
        apps = self._estado_anterior()
        Motorista = apps.get_model("cadastros", "Motorista")

        Motorista.objects.create(nome="Primeira", telefone="41999998888")
        Motorista.objects.create(nome="Segunda", telefone="41999998888")

        apps = self._aplicar_conversao()
        Servidor = apps.get_model("viagens_cadastros", "Servidor")

        self.assertEqual(Servidor.objects.count(), 2)
        # O telefone fica com quem foi convertido primeiro; o outro fica em
        # branco, para ser corrigido na tela — melhor que perder o servidor.
        telefones = sorted(Servidor.objects.values_list("telefone", flat=True))
        self.assertEqual(telefones, ["", "41999998888"])

    def test_telefone_invalido_no_legado_e_descartado_sem_travar(self):
        apps = self._estado_anterior()
        Motorista = apps.get_model("cadastros", "Motorista")
        Motorista.objects.create(nome="Contato ruim", telefone="ramal 4523")

        apps = self._aplicar_conversao()
        Servidor = apps.get_model("viagens_cadastros", "Servidor")
        self.assertEqual(Servidor.objects.get(nome="CONTATO RUIM").telefone, "")

    def test_reverter_recria_os_motoristas_e_os_vinculos(self):
        apps = self._estado_anterior()
        Motorista = apps.get_model("cadastros", "Motorista")
        Solicitacao = apps.get_model("solicitacoes", "SolicitacaoEvento")
        User = apps.get_model("accounts", "User")

        motorista = Motorista.objects.create(nome="Reversível")
        usuario = _criar_usuario(User)
        solicitacao = Solicitacao.objects.create(
            criado_por=usuario, motorista=motorista, data_solicitacao="2026-08-01"
        )

        self._aplicar_conversao()
        apps = self._estado_anterior()

        Motorista = apps.get_model("cadastros", "Motorista")
        Solicitacao = apps.get_model("solicitacoes", "SolicitacaoEvento")
        self.assertTrue(Motorista.objects.filter(nome="REVERSÍVEL").exists())
        revertida = Solicitacao.objects.get(pk=solicitacao.pk)
        self.assertIsNotNone(revertida.motorista_id)
