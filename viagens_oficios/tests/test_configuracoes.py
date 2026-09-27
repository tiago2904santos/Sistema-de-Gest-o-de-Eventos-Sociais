"""Tela de configurações dos documentos: dados por setor, assinantes únicos e acesso só do gestor."""
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser, Group
from django.test import RequestFactory, TestCase
from django.urls import reverse

from accounts.models import Modulo, Setor
from core import middleware
from viagens_cadastros.models import AssinaturaConfiguracao, Cargo, ConfiguracaoSistema, Servidor, Unidade
from viagens_cadastros.selectors import build_configuracao_context


class ConfiguracoesDosDocumentosTests(TestCase):
    def setUp(self):
        self.setor = self.criar_setor('ASCOM TESTE')
        self.user = self.criar_gestor('gestor-config', self.setor)
        self.client.force_login(self.user)
        cargo = Cargo.objects.create(nome='Delegado')
        self.unidade = Unidade.objects.create(nome='Unidade Config', sigla='UC')
        self.ana = Servidor.objects.create(nome='ANA CONFIG', cargo=cargo, unidade=self.unidade)
        self.bia = Servidor.objects.create(nome='BIA CONFIG', cargo=cargo, unidade=self.unidade)
        self.url = reverse('viagens_oficios:institucional')

    def criar_setor(self, nome):
        setor = Setor.objects.create(nome=nome)
        Modulo.objects.get(codigo='VIAGENS').setores.add(setor)
        return setor

    def criar_gestor(self, username, setor):
        user = get_user_model().objects.create_user(username=username, deve_trocar_senha=False)
        user.setores.add(setor)
        user.groups.add(Group.objects.get(name='VIAGENS_GESTOR'))
        return user

    def payload(self, **extra):
        dados = {'nome_orgao': 'polícia civil do paraná', 'sigla_orgao': 'pcpr', 'unidade': self.unidade.pk,
                 'cep': '80000-000', 'telefone': '(41) 3333-4444', 'prazo_justificativa_dias': '10'}
        dados.update(extra)
        return dados

    def ativos(self, tipo):
        global_ = ConfiguracaoSistema.get_singleton()
        return list(global_.assinaturas.filter(tipo=tipo, ativo=True).values_list('servidor__nome', flat=True))

    def test_pagina_mostra_o_setor_as_cinco_secoes_e_a_busca_de_cep(self):
        r = self.client.get(self.url)
        self.assertEqual(r.status_code, 200)
        for texto in ['ASCOM TESTE', 'Órgão emissor', 'Endereço e contato', 'Destinatário do ofício', 'Assinaturas',
                      'Prazo', 'name="assina_oficio"', 'name="assina_justificativa"', 'Salvar configurações']:
            self.assertContains(r, texto)
        self.assertContains(r, 'data-cep-url="%s"' % reverse('viagens_cadastros:api_consulta_cep', args=['00000000']))
        self.assertNotContains(r, 'Gerenciar assinantes')
        self.assertNotContains(r, 'name="nome_chefia"')
        self.assertNotContains(r, 'name="sede_estado"')
        self.assertNotContains(r, 'name="cidade_sede_padrao"')

    def test_salvar_grava_no_setor_do_usuario_e_assinantes_na_global(self):
        r = self.client.post(self.url, self.payload(assina_oficio=self.ana.pk, assina_justificativa=self.bia.pk))
        self.assertRedirects(r, self.url)
        cfg = ConfiguracaoSistema.objects.get(setor=self.setor)
        self.assertEqual((cfg.nome_orgao, cfg.sigla_orgao, cfg.cep, cfg.telefone),
                         ('POLÍCIA CIVIL DO PARANÁ', 'PCPR', '80000000', '4133334444'))
        self.assertEqual(ConfiguracaoSistema.get_singleton().nome_orgao, '')
        self.assertFalse(cfg.assinaturas.exists())
        self.assertEqual(self.ativos('OFICIO'), ['ANA CONFIG'])
        self.assertEqual(self.ativos('JUSTIFICATIVA'), ['BIA CONFIG'])

    def test_sede_vem_da_cidade_e_uf_do_endereco(self):
        from cadastros.models import Estado, Municipio, Regiao
        pr = Estado.objects.get_or_create(sigla='PR', defaults={'nome': 'Paraná', 'codigo_ibge': 41})[0]
        regiao = Regiao.objects.get_or_create(nome='Capital')[0]
        curitiba = Municipio.objects.get_or_create(codigo_ibge=4106902, defaults={'nome': 'Curitiba', 'estado': pr, 'regiao': regiao})[0]
        self.client.post(self.url, self.payload(cidade_endereco='CURITIBA', uf='pr'))
        self.assertEqual(ConfiguracaoSistema.objects.get(setor=self.setor).cidade_sede_padrao, curitiba)
        self.client.post(self.url, self.payload(cidade_endereco='Cidade Inexistente', uf='PR'))
        self.assertIsNone(ConfiguracaoSistema.objects.get(setor=self.setor).cidade_sede_padrao)

    def test_setor_novo_nasce_da_global_e_setores_nao_se_misturam(self):
        global_ = ConfiguracaoSistema.get_singleton()
        global_.nome_orgao = 'ÓRGÃO GERAL'
        global_.save()
        self.assertContains(self.client.get(self.url), 'value="ÓRGÃO GERAL"')
        self.client.post(self.url, self.payload(nome_orgao='órgão da ascom'))

        outro = self.criar_gestor('gestor-outro', self.criar_setor('OUTRA UNIDADE'))
        self.client.force_login(outro)
        r = self.client.get(self.url)
        self.assertContains(r, 'OUTRA UNIDADE')
        self.assertContains(r, 'value="ÓRGÃO GERAL"')
        self.assertNotContains(r, 'ÓRGÃO DA ASCOM')
        self.assertEqual(ConfiguracaoSistema.objects.get(setor=self.setor).nome_orgao, 'ÓRGÃO DA ASCOM')

    def test_documento_usa_o_setor_de_quem_gera_e_a_global_fora_de_requisicao(self):
        cfg = ConfiguracaoSistema.do_setor(self.setor)
        cfg.nome_orgao = 'órgão ascom'
        cfg.save()
        AssinaturaConfiguracao.objects.create(configuracao=ConfiguracaoSistema.get_singleton(), tipo='OFICIO', servidor=self.ana)
        requisicao = RequestFactory().get('/')
        requisicao.user = self.user
        middleware._local.requisicao = requisicao
        try:
            contexto = build_configuracao_context()
        finally:
            middleware._local.requisicao = None
        self.assertEqual(contexto['nome_orgao'], 'ÓRGÃO ASCOM')
        self.assertEqual(contexto['assinaturas']['OFICIO'][0]['nome'], 'ANA CONFIG')
        self.assertEqual(build_configuracao_context()['nome_orgao'], '')
        requisicao.user = AnonymousUser()
        middleware._local.requisicao = requisicao
        try:
            self.assertEqual(build_configuracao_context()['nome_orgao'], '')
        finally:
            middleware._local.requisicao = None

    def test_trocar_assinante_reaproveita_o_primeiro_e_limpar_desativa(self):
        AssinaturaConfiguracao.objects.create(configuracao=ConfiguracaoSistema.get_singleton(), tipo='OFICIO', servidor=self.ana, ordem=1)
        self.assertContains(self.client.get(self.url), f'value="{self.ana.pk}" selected')
        self.client.post(self.url, self.payload(assina_oficio=self.bia.pk))
        self.assertEqual(self.ativos('OFICIO'), ['BIA CONFIG'])
        self.assertEqual(ConfiguracaoSistema.get_singleton().assinaturas.filter(tipo='OFICIO').count(), 1)
        self.client.post(self.url, self.payload(assina_oficio=''))
        self.assertEqual(self.ativos('OFICIO'), [])

    def test_substituto_por_periodo_assina_pela_data_do_documento(self):
        """m114: o documento datado no período sai com o substituto; fora dele, o titular; o assinante do documento vence os dois."""
        from datetime import date
        from viagens_cadastros.models import AssinaturaSubstituicao
        from viagens_oficios.docxtpl_context import _assinatura_nome_cargo
        global_ = ConfiguracaoSistema.get_singleton()
        AssinaturaConfiguracao.objects.create(configuracao=global_, tipo=AssinaturaConfiguracao.ORDEM_SERVICO, servidor=self.ana)
        AssinaturaSubstituicao.objects.create(configuracao=global_, tipo=AssinaturaSubstituicao.TODOS, servidor=self.bia,
                                              inicio=date(2026, 7, 1), fim=date(2026, 7, 31), motivo='Férias')
        inst = build_configuracao_context()
        self.assertEqual(_assinatura_nome_cargo(inst, 'ORDEM_SERVICO', fallback_geral=False, data=date(2026, 7, 15))[0], 'BIA CONFIG')
        self.assertEqual(_assinatura_nome_cargo(inst, 'ORDEM_SERVICO', fallback_geral=False, data=date(2026, 8, 1))[0], 'ANA CONFIG')
        self.assertEqual(_assinatura_nome_cargo(inst, 'ORDEM_SERVICO', fallback_geral=False, data=date(2026, 7, 15), assinante=self.ana)[0], 'ANA CONFIG')
        # Substituição só de um tipo não alcança os outros; sem fim, vale até segunda ordem.
        AssinaturaSubstituicao.objects.create(configuracao=global_, tipo=AssinaturaConfiguracao.OFICIO, servidor=self.bia, inicio=date(2026, 9, 1))
        inst = build_configuracao_context()
        self.assertEqual(_assinatura_nome_cargo(inst, 'ORDEM_SERVICO', fallback_geral=False, data=date(2026, 9, 20))[0], 'ANA CONFIG')
        self.assertEqual(_assinatura_nome_cargo(inst, 'OFICIO', fallback_geral=False, data=date(2027, 1, 1))[0], 'BIA CONFIG')

    def test_tela_de_substituicoes_no_catalogo_e_link_nas_configuracoes(self):
        from viagens_cadastros.models import AssinaturaSubstituicao
        url = reverse('viagens_cadastros:lista', args=['substituicoes-assinatura'])
        self.assertContains(self.client.get(self.url), url)
        r = self.client.get(url)
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, 'Substituições de assinante')
        r = self.client.post(reverse('viagens_cadastros:novo', args=['substituicoes-assinatura']),
                             {'tipo': 'TODOS', 'servidor': self.bia.pk, 'inicio': '2026-07-01', 'fim': '2026-06-01', 'motivo': 'Férias', 'ativo': 'on'})
        self.assertFalse(AssinaturaSubstituicao.objects.exists())
        r = self.client.post(reverse('viagens_cadastros:novo', args=['substituicoes-assinatura']),
                             {'tipo': 'TODOS', 'servidor': self.bia.pk, 'inicio': '2026-07-01', 'fim': '2026-07-31', 'motivo': 'Férias', 'ativo': 'on'})
        self.assertEqual(r.status_code, 302, r.content[:300])
        s = AssinaturaSubstituicao.objects.get()
        self.assertEqual((s.servidor, s.configuracao), (self.bia, ConfiguracaoSistema.get_singleton()))
        self.assertContains(self.client.get(url), '01/07/2026 a 31/07/2026')

    def test_delegado_geral_e_rodape_da_ascom_vem_da_configuracao(self):
        """m115: o nome do Delegado-Geral e os dados da ASCOM saem da configuração."""
        from documentos.services.document_blocks import completar_blocos
        from documentos.services.types import DocumentoTipo
        from coffee_break.editor import BLOCOS_OS  # noqa: F401 (registra os blocos do Coffee Break)
        cfg = ConfiguracaoSistema.atual()
        self.assertEqual(cfg.delegado_geral_nome, 'Silvio Jacob Rockembach')
        blocos = completar_blocos(DocumentoTipo.ORDEM_SERVICO)
        self.assertIn('Delegado-Geral Silvio Jacob Rockembach, bem como', blocos['atribuicoes']['conteudo'])
        cfg.delegado_geral_nome = 'Fulano Delegado'
        cfg.ascom_rodape_endereco = 'Rua Nova, 10 – Centro—CEP: 80.000-000'
        cfg.save()
        blocos = completar_blocos(DocumentoTipo.ORDEM_SERVICO)
        self.assertIn('Delegado-Geral Fulano Delegado, bem como', blocos['atribuicoes']['conteudo'])
        from documentos.services.document_blocks import valores_institucionais
        self.assertEqual(valores_institucionais()['ascom_endereco_hifens'], 'Rua Nova, 10 - Centro - CEP: 80000-000')
        r = self.client.get(self.url)
        self.assertContains(r, 'name="delegado_geral_nome"')
        self.assertContains(r, 'name="ascom_rodape_contato"')

    def test_antigo_catalogo_de_assinantes_leva_para_a_secao(self):
        r = self.client.get(reverse('viagens_oficios:catalogo', args=['assinaturas']))
        self.assertRedirects(r, self.url + '#assinaturas')

    def test_operador_sem_gestao_recebe_403(self):
        self.user.groups.clear()
        self.user.groups.add(Group.objects.get(name='VIAGENS_OPERADOR'))
        self.assertEqual(self.client.get(self.url).status_code, 403)
