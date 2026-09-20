"""A tela: o mesmo orquestrador, por HTTP, com o middleware de módulo ativo."""

from django.test import TestCase
from django.urls import reverse

from assistente.models import Conversa, Mensagem

from .fixtures import criar_geografia, criar_pessoas, criar_usuario


class PainelDoAssistente(TestCase):
    def setUp(self):
        self.usuario = criar_usuario()
        criar_geografia()
        criar_pessoas()
        self.client.force_login(self.usuario)

    def test_abre_e_lista_as_ferramentas_do_usuario(self):
        resposta = self.client.get(reverse("assistente:painel"))
        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, "consultar_deslocamentos")
        self.assertContains(resposta, "preparar_viagem")

    def test_enviar_grava_a_conversa_e_volta_para_o_painel(self):
        resposta = self.client.post(
            reverse("assistente:enviar"), {"texto": "o que está pendente?"}
        )
        self.assertRedirects(resposta, reverse("assistente:painel"))
        conversa = Conversa.objects.get()
        autores = list(conversa.mensagens.values_list("autor", flat=True))
        self.assertEqual(autores, [Mensagem.Autor.PESSOA, Mensagem.Autor.ASSISTENTE])

    def test_mensagem_vazia_nao_cria_nada(self):
        self.client.post(reverse("assistente:enviar"), {"texto": "   "})
        self.assertFalse(Mensagem.objects.exists())

    def test_nova_conversa_preserva_a_anterior(self):
        self.client.post(reverse("assistente:enviar"), {"texto": "o que está pendente?"})
        self.client.post(reverse("assistente:nova"))
        self.assertEqual(Conversa.objects.count(), 2)
        self.assertEqual(Mensagem.objects.count(), 2)

    def test_a_resposta_aparece_na_tela(self):
        self.client.post(
            reverse("assistente:enviar"), {"texto": "quem vai para Maringá em setembro?"}
        )
        resposta = self.client.get(reverse("assistente:painel"))
        self.assertContains(resposta, "Ninguém escalado")


class AcessoAoPainel(TestCase):
    def test_sem_o_modulo_o_middleware_barra(self):
        usuario = criar_usuario("estranho", com_modulo=False, pode_escrever=False)
        self.client.force_login(usuario)
        resposta = self.client.get(reverse("assistente:painel"))
        self.assertEqual(resposta.status_code, 403)

    def test_visitante_anonimo_vai_para_o_login(self):
        resposta = self.client.get(reverse("assistente:painel"))
        self.assertEqual(resposta.status_code, 302)
        self.assertIn("/conta/", resposta["Location"])
