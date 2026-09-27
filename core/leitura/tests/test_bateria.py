"""A bateria do preenchimento automático tem de passar inteira.

Centenas de e-mails e conversas de WhatsApp fictícios, com o gabarito do que
uma secretária atenta preencheria (`core/leitura/tests/bateria/`). Qualquer
mudança no leitor que erre um campo, invente um valor ou mande o e-mail para
a tela errada reprova aqui — com a lista do que mudou. Para ver o placar no
terminal: `python manage.py avaliar_leitura --erros`.
"""

from django.test import TestCase

from .bateria import avaliar


class BateriaDoPreenchimentoTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.casos, cadastros = avaliar.carregar()
        avaliar.preparar_banco(cadastros)

    def test_zero_erro_na_bateria_inteira(self):
        self.assertGreaterEqual(len(self.casos), 500)
        relatorio = avaliar.avaliar(self.casos)
        falhas = "\n".join(f.linha() for f in relatorio.falhas)
        self.assertEqual(relatorio.falhas, [], f"\n{relatorio.resumo()}\n{falhas}")
