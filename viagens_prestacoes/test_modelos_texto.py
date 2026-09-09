"""NOVO-03 — `_CAMPO_LABELS` ficou para trás quando as views de modelo saíram de
`views.py` para `model_views.py`.

O nome continuou definido no fim de `viagens_prestacoes/views.py`, onde ninguém mais
lê, e `model_views.py` passou a referenciá-lo sem defini-lo. Resultado: `NameError`
em rota viva, nas duas entradas que consultam o rótulo do campo —
`_voltar_modelos_url`, que é o redirect de sucesso de editar e excluir.

Nenhum teste cobria essas quatro views, e nenhum auditor do projeto lê código como
código: foi o `ruff` do `QA-07` que apontou (`F821`). Este teste é o que impede o
nome de sumir de novo.
"""
from __future__ import annotations
from viagens_prestacoes.test_helpers import autorizar_viagens, pdf_minimo
from django.contrib.auth import get_user_model
from .test_helpers import PrestacaoTestCase as TestCase
from django.urls import Resolver404
from django.urls import resolve
from django.urls import reverse
from viagens_prestacoes.models import ModeloTextoRelatorioTecnico
CAMPO = ModeloTextoRelatorioTecnico.CAMPO_MOTIVO

class ModelosDeTextoRTTests(TestCase):

    def setUp(self):
        self.user = get_user_model().objects.create_user(username='rt_modelos', password='123456')
        autorizar_viagens(self.user)
        self.client.force_login(self.user)

    def _criar(self, nome='Modelo A'):
        return ModeloTextoRelatorioTecnico.objects.create(nome=nome, texto='Texto do modelo', campo=CAMPO)

    def test_index_abre(self):
        self._criar()
        response = self.client.get(reverse('viagens_prestacoes:modelos_index'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'aria-label="Campos do relatório"')
        self.assertContains(response, 'Modelo A')

    def test_quick_add_fica_no_formulario_antes_das_abas_e_da_lista(self):
        self._criar()
        response = self.client.get(reverse('viagens_prestacoes:modelos_index'))
        html = response.content.decode()
        self.assertLess(html.index('aria-label="Campos do relatório"'), html.index('Salvar modelo'))
        self.assertLess(html.index('Salvar modelo'), html.index('<h2>Modelo A</h2>'))

    def test_busca_ocupa_a_largura_do_formulario(self):
        response = self.client.get(reverse('viagens_prestacoes:modelos_index'))
        self.assertContains(response, 'role="search"', count=1)

    def test_topico_ativo_usa_lista_simples_sem_form_block_proprio(self):
        self._criar()
        response = self.client.get(reverse('viagens_prestacoes:modelos_index'))
        self.assertContains(response, '<h2>Modelo A</h2>')
        self.assertNotContains(response, '<c-v2.')

    def test_toggle_abre_somente_a_lista_do_topico_selecionado(self):
        campo, label = ModeloTextoRelatorioTecnico.CAMPO_CHOICES[1]
        modelo_visivel = ModeloTextoRelatorioTecnico.objects.create(nome='Modelo do objetivo', texto='Texto do objetivo', campo=campo)
        self._criar(nome='Modelo da descrição')
        response = self.client.get(reverse('viagens_prestacoes:modelos_index'), {'campo': campo})
        self.assertEqual(len(response.context['grupos']), 1)
        self.assertEqual(response.context['grupos'][0]['campo'], campo)
        self.assertEqual(response.context['grupos'][0]['rows'][0]['title'], modelo_visivel.nome)
        self.assertContains(response, label)
        self.assertContains(response, f'''href="{reverse('viagens_prestacoes:modelos_index')}?campo={campo}" aria-current="page"''', count=1)
        self.assertNotContains(response, 'Modelo da descrição')

    def test_toggle_preserva_busca_e_retorno_ao_relatorio(self):
        retorno = '/viagens/prestacoes/servidor-prestacao/41/rt/'
        campo = ModeloTextoRelatorioTecnico.CAMPO_CHOICES[1][0]
        response = self.client.get(reverse('viagens_prestacoes:modelos_index'), {'campo': CAMPO, 'q': 'evento', 'next': retorno})
        aba = next((item for item in response.context['abas'] if item['campo'] == campo))
        self.assertIn(f'campo={campo}', aba['url'])
        self.assertIn('q=evento', aba['url'])
        self.assertIn('next=%2Fviagens%2Fprestacoes%2Fservidor-prestacao%2F41%2Frt%2F', aba['url'])

    def test_quick_add_cria_modelo_no_proprio_grupo(self):
        prefixo = f'modelo-{CAMPO}'
        response = self.client.post(reverse('viagens_prestacoes:modelos_index'), {'quick_add_campo': CAMPO, f'{prefixo}-campo': CAMPO, f'{prefixo}-nome': 'Modelo rápido', f'{prefixo}-texto': 'Texto criado sem sair da lista.'})
        self.assertRedirects(response, f"{reverse('viagens_prestacoes:modelos_index')}?campo={CAMPO}#grupo-{CAMPO}", fetch_redirect_response=False)
        self.assertTrue(ModeloTextoRelatorioTecnico.objects.filter(nome='Modelo rápido', texto='Texto criado sem sair da lista.', campo=CAMPO).exists())

    def test_quick_add_invalido_reabre_somente_o_grupo_enviado(self):
        prefixo = f'modelo-{CAMPO}'
        response = self.client.post(reverse('viagens_prestacoes:modelos_index'), {'quick_add_campo': CAMPO, f'{prefixo}-campo': CAMPO, f'{prefixo}-nome': '', f'{prefixo}-texto': 'Texto sem nome.'})
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context['form'].errors)
        self.assertFalse(ModeloTextoRelatorioTecnico.objects.exists())

    def test_quick_add_usa_inputs_v32(self):
        response = self.client.get(reverse('viagens_prestacoes:modelos_index'))
        self.assertContains(response, 'name="nome"')
        self.assertContains(response, 'name="texto"')
        self.assertNotContains(response, '<c-v2.')

    def test_index_exibe_retorno_para_relatorio_tecnico_de_origem(self):
        retorno = '/viagens/prestacoes/servidor-prestacao/41/rt/'
        response = self.client.get(reverse('viagens_prestacoes:modelos_index'), {'next': retorno})
        self.assertEqual(response.context['back_url'], retorno)
        self.assertEqual(response.context['back_label'], 'Voltar para o relatório técnico')
        self.assertContains(response, f'href="{retorno}"')
        self.assertContains(response, 'Voltar para o relatório técnico')

    def test_index_ignora_retorno_externo(self):
        response = self.client.get(reverse('viagens_prestacoes:modelos_index'), {'next': 'https://externo.invalido/rt/'})
        self.assertEqual(response.context['back_url'], '')
        self.assertNotContains(response, 'Voltar para o relatório técnico')

    def test_rota_de_cadastro_separado_nao_existe(self):
        with self.assertRaises(Resolver404):
            resolve('/viagens/prestacoes/modelos-texto/novo/')

    def test_editar_redireciona_para_a_aba_do_campo(self):
        modelo = self._criar()
        response = self.client.post(reverse('viagens_prestacoes:modelo_update', args=[modelo.pk]), {'nome': 'Modelo A editado', 'texto': 'Texto editado', 'campo': CAMPO})
        self.assertRedirects(response, f"{reverse('viagens_prestacoes:modelos_index')}?campo={CAMPO}")
        modelo.refresh_from_db()
        self.assertEqual(modelo.nome, 'Modelo A editado')

    def test_excluir_redireciona_para_a_aba_do_campo(self):
        modelo = self._criar()
        response = self.client.post(reverse('viagens_prestacoes:modelo_delete', args=[modelo.pk]))
        self.assertRedirects(response, f"{reverse('viagens_prestacoes:modelos_index')}?campo={CAMPO}")
        self.assertFalse(ModeloTextoRelatorioTecnico.objects.filter(pk=modelo.pk).exists())
