"""O protocolo que o sistema abre sozinho enquanto o ofício é feito.

O que estes testes protegem, em ordem de importância:

1. **Gravar o ofício sempre vence.** eProtocolo fora do ar não pode perder o
   que a pessoa digitou — a falha vira aviso, não exceção.
2. **O que foi digitado não é sobrescrito.** Protocolo informado à mão
   continua sendo dele, e a ficha para de dizer que veio do barramento.
3. **Simulado não se disfarça de real.** Sem credencial o número é gerado
   aqui, e tanto o banco quanto a tela dizem isso.
"""

from unittest import mock

from django.contrib import messages
from django.contrib.messages import get_messages
from django.test import TestCase, override_settings
from django.urls import reverse

from integracoes.eprotocolo.exceptions import EProtocoloUnavailableError, EProtocoloValidationError
from integracoes.eprotocolo.schemas import ResultadoOperacao
from viagens_oficios.form_context import ajuda_do_protocolo
from viagens_oficios.models import Oficio
from viagens_oficios.protocolo_services import abrir_protocolo_do_oficio, mensagens_do_protocolo

from .fixtures import CenarioOficioMixin

EPROTOCOLO_REAL = {
    "AMBIENTE": "homologacao",
    "BASE_URL": "https://exemplo.invalido/spi-servicos",
    "TOKEN_URL": "https://exemplo.invalido/token",
    "CLIENT_ID": "cliente",
    "CLIENT_SECRET": "segredo",
    "CONSUMER_ID": "consumidor",
    "TIMEOUT": 5,
    "VERIFY_SSL": True,
    "REAL_READONLY": False,
    "AUTO_PROTOCOLO_OFICIO": True,
    "COD_ORGAO_PADRAO": "10",
    "COD_LOCAL_ORIGEM_PADRAO": "20",
    "COD_ASSUNTO_VIAGEM": "30",
    "COD_ESPECIE_OFICIO": "40",
}


def _sem_protocolo(payload):
    """O cenário padrão preenche o protocolo à mão; aqui o campo vai vazio."""
    return {**payload, "protocolo": ""}


class ProtocoloAutomaticoTests(CenarioOficioMixin, TestCase):
    def _criar_sem_protocolo(self):
        resposta = self.client.post(reverse("viagens_oficios:novo"), _sem_protocolo(self.payload()))
        self.assertEqual(resposta.status_code, 302, resposta.content[:2000])
        return Oficio.objects.latest("pk")

    def test_gravar_oficio_sem_protocolo_abre_um_e_marca_a_origem(self):
        oficio = self._criar_sem_protocolo()
        self.assertEqual(len(oficio.protocolo), 9, oficio.protocolo)
        self.assertTrue(oficio.protocolo.isdigit())
        # Sem credencial na suíte, o número é simulado — e a ficha diz isso.
        self.assertEqual(oficio.protocolo_origem, Oficio.PROTOCOLO_ORIGEM_SIMULADO)
        self.assertEqual(oficio.protocolo_situacao, "CRIADO")
        self.assertIsNotNone(oficio.protocolo_criado_em)

    def test_protocolo_digitado_e_preservado_e_fica_como_manual(self):
        resposta = self.client.post(reverse("viagens_oficios:novo"), self.payload())
        self.assertEqual(resposta.status_code, 302)
        oficio = Oficio.objects.latest("pk")
        self.assertEqual(oficio.protocolo, "123456789")
        self.assertEqual(oficio.protocolo_origem, Oficio.PROTOCOLO_ORIGEM_MANUAL)

    def test_gravar_de_novo_nao_troca_o_protocolo_ja_aberto(self):
        oficio = self._criar_sem_protocolo()
        numero = oficio.protocolo
        resposta = self.client.post(
            reverse("viagens_oficios:editar", args=[oficio.pk]),
            {**_sem_protocolo(self.payload()), "protocolo": numero},
        )
        self.assertEqual(resposta.status_code, 302)
        oficio.refresh_from_db()
        self.assertEqual(oficio.protocolo, numero)

    def test_digitar_por_cima_do_automatico_devolve_a_origem_para_manual(self):
        oficio = self._criar_sem_protocolo()
        resposta = self.client.post(
            reverse("viagens_oficios:editar", args=[oficio.pk]),
            {**self.payload(), "protocolo": "98.765.432-1"},
        )
        self.assertEqual(resposta.status_code, 302)
        oficio.refresh_from_db()
        self.assertEqual(oficio.protocolo, "987654321")
        self.assertEqual(oficio.protocolo_origem, Oficio.PROTOCOLO_ORIGEM_MANUAL)
        self.assertEqual(oficio.protocolo_situacao, "")
        self.assertIsNone(oficio.protocolo_criado_em)

    def test_eprotocolo_fora_do_ar_nao_derruba_a_gravacao(self):
        with mock.patch(
            "viagens_oficios.protocolo_services.epro.criar_protocolo_de_oficio",
            side_effect=EProtocoloUnavailableError(),
        ):
            resposta = self.client.post(reverse("viagens_oficios:novo"), _sem_protocolo(self.payload()))
        self.assertEqual(resposta.status_code, 302)
        oficio = Oficio.objects.latest("pk")
        self.assertEqual(oficio.motivo, "Missão F4")  # o ofício foi salvo
        self.assertEqual(oficio.protocolo, "")
        self.assertEqual(oficio.protocolo_origem, Oficio.PROTOCOLO_ORIGEM_MANUAL)
        avisos = [str(m) for m in get_messages(resposta.wsgi_request)]
        self.assertTrue(any("indisponível" in texto for texto in avisos), avisos)

    def test_falha_inesperada_tambem_e_contida(self):
        oficio = self._criar_sem_protocolo()
        Oficio.objects.filter(pk=oficio.pk).update(protocolo="")
        oficio.refresh_from_db()
        with mock.patch(
            "viagens_oficios.protocolo_services.epro.criar_protocolo_de_oficio",
            side_effect=RuntimeError("boom"),
        ):
            resultado = abrir_protocolo_do_oficio(oficio)
        self.assertFalse(resultado.criado)
        self.assertIn("inesperada", resultado.erro)

    def test_resposta_sem_numero_nao_grava_nada(self):
        oficio = self._criar_sem_protocolo()
        Oficio.objects.filter(pk=oficio.pk).update(protocolo="")
        oficio.refresh_from_db()
        with mock.patch(
            "viagens_oficios.protocolo_services.epro.criar_protocolo_de_oficio",
            return_value=ResultadoOperacao(sucesso=True, dados={"situacao": "CRIADO"}, mock=True),
        ):
            resultado = abrir_protocolo_do_oficio(oficio)
        oficio.refresh_from_db()
        self.assertEqual(oficio.protocolo, "")
        self.assertIn("sem número", resultado.erro)

    def test_dois_oficios_nao_recebem_o_mesmo_numero_simulado(self):
        primeiro = self._criar_sem_protocolo()
        segundo = self._criar_sem_protocolo()
        self.assertNotEqual(primeiro.protocolo, segundo.protocolo)

    @override_settings(EPROTOCOLO={**EPROTOCOLO_REAL, "AMBIENTE": "mock", "AUTO_PROTOCOLO_OFICIO": False})
    def test_desligado_por_configuracao_o_campo_volta_a_ser_manual(self):
        oficio = self._criar_sem_protocolo()
        self.assertEqual(oficio.protocolo, "")
        self.assertEqual(oficio.protocolo_origem, Oficio.PROTOCOLO_ORIGEM_MANUAL)

    def test_oficio_cancelado_nao_abre_protocolo(self):
        oficio = self._criar_sem_protocolo()
        Oficio.objects.filter(pk=oficio.pk).update(protocolo="")
        oficio.refresh_from_db()
        oficio.cancelar("teste")
        resultado = abrir_protocolo_do_oficio(oficio)
        self.assertFalse(resultado.criado)
        oficio.refresh_from_db()
        self.assertEqual(oficio.protocolo, "")


EPROTOCOLO_TREINAMENTO = {**EPROTOCOLO_REAL, "AMBIENTE": "treinamento"}


@override_settings(EPROTOCOLO={**EPROTOCOLO_REAL, "AMBIENTE": "producao"})
class ProtocoloModoRealTests(CenarioOficioMixin, TestCase):
    """Com credenciais, o número vem do barramento — e é marcado como tal."""

    def test_numero_do_barramento_e_gravado_como_eprotocolo(self):
        oficio = Oficio.objects.create(numero=1, ano=2026, motivo="Missão real")
        resposta = {"numero": "24.123.456-7", "situacao": "EM_TRAMITACAO"}
        with mock.patch("integracoes.eprotocolo.services.get_client") as fabrica:
            fabrica.return_value.post.return_value = resposta
            resultado = abrir_protocolo_do_oficio(oficio)
            payload = fabrica.return_value.post.call_args.kwargs["json_body"]

        oficio.refresh_from_db()
        self.assertTrue(resultado.criado)
        self.assertFalse(resultado.simulado)
        self.assertEqual(oficio.protocolo, "241234567")
        self.assertEqual(oficio.protocolo_origem, Oficio.PROTOCOLO_ORIGEM_EPROTOCOLO)
        self.assertEqual(oficio.protocolo_situacao, "EM_TRAMITACAO")
        # O payload leva o documento e os códigos institucionais do .env.
        self.assertEqual(payload["numeroDocumento"], 1)
        self.assertEqual(payload["codOrgao"], "10")
        self.assertIn("diárias", payload["assunto"])

    @override_settings(EPROTOCOLO={**EPROTOCOLO_REAL, "AMBIENTE": "producao", "COD_ASSUNTO_VIAGEM": ""})
    def test_codigo_institucional_faltando_nao_sai_para_a_rede(self):
        oficio = Oficio.objects.create(numero=2, ano=2026, motivo="Missão real")
        with mock.patch("integracoes.eprotocolo.services.get_client") as fabrica:
            resultado = abrir_protocolo_do_oficio(oficio)
        fabrica.assert_not_called()
        self.assertTrue(resultado.incompleto)
        self.assertIn("EPROTOCOLO_COD_ASSUNTO_VIAGEM", resultado.erro)
        oficio.refresh_from_db()
        self.assertEqual(oficio.protocolo, "")

    @override_settings(EPROTOCOLO={**EPROTOCOLO_REAL, "AMBIENTE": "producao", "REAL_READONLY": True})
    def test_trava_de_somente_consulta_impede_abrir_protocolo(self):
        oficio = Oficio.objects.create(numero=3, ano=2026, motivo="Missão real")
        with mock.patch("integracoes.eprotocolo.services.get_client") as fabrica:
            resultado = abrir_protocolo_do_oficio(oficio)
        fabrica.assert_not_called()
        self.assertFalse(resultado.criado)
        self.assertIn("EPROTOCOLO_REAL_READONLY", resultado.erro)

    def test_oficio_sem_motivo_nem_numero_e_recusado_antes_da_chamada(self):
        oficio = Oficio.objects.create(motivo="")
        with mock.patch("integracoes.eprotocolo.services.get_client") as fabrica:
            resultado = abrir_protocolo_do_oficio(oficio)
        fabrica.assert_not_called()
        self.assertTrue(resultado.incompleto)
        self.assertIsInstance(
            EProtocoloValidationError(resultado.erro), EProtocoloValidationError
        )


class ProtocoloNoEditorDocumentalTests(CenarioOficioMixin, TestCase):
    """Trocar o protocolo pela prévia A4 também desfaz a marca de automático."""

    def test_patch_do_editor_devolve_a_origem_para_manual(self):
        import json

        resposta = self.client.post(reverse("viagens_oficios:novo"), _sem_protocolo(self.payload()))
        self.assertEqual(resposta.status_code, 302)
        oficio = Oficio.objects.latest("pk")
        self.assertEqual(oficio.protocolo_origem, Oficio.PROTOCOLO_ORIGEM_SIMULADO)

        url = reverse("documentos:editor_campo", args=["oficio", oficio.pk, "protocolo"])
        corpo = {"valores": {"protocolo": "987654321"}, "versao": oficio.atualizado_em.isoformat()}
        resposta = self.client.patch(url, data=json.dumps(corpo), content_type="application/json")
        self.assertEqual(resposta.status_code, 200, resposta.content)

        oficio.refresh_from_db()
        self.assertEqual(oficio.protocolo, "987654321")
        self.assertEqual(oficio.protocolo_origem, Oficio.PROTOCOLO_ORIGEM_MANUAL)
        self.assertIsNone(oficio.protocolo_criado_em)


@override_settings(EPROTOCOLO=EPROTOCOLO_TREINAMENTO)
class ProtocoloTreinamentoTests(CenarioOficioMixin, TestCase):
    """O barramento de treinamento abre processo de verdade — que não vale.

    É a situação da instalação hoje: há credencial de treinamento e nenhuma de
    produção. O número existe lá dentro, mas ninguém pode protocolar com ele, e
    o sistema não pode deixar isso implícito em lugar nenhum.
    """

    def _abrir(self, oficio):
        with mock.patch("integracoes.eprotocolo.services.get_client") as fabrica:
            fabrica.return_value.post.return_value = {"numero": "24.123.456-7", "situacao": "CRIADO"}
            return abrir_protocolo_do_oficio(oficio)

    def test_numero_de_treinamento_nao_e_marcado_como_oficial(self):
        oficio = Oficio.objects.create(numero=10, ano=2026, motivo="Missão de treino")
        resultado = self._abrir(oficio)
        oficio.refresh_from_db()
        self.assertTrue(resultado.criado)
        self.assertFalse(resultado.simulado)  # a chamada saiu de verdade
        self.assertFalse(resultado.oficial)   # e mesmo assim não vale
        self.assertEqual(oficio.protocolo, "241234567")
        self.assertEqual(oficio.protocolo_origem, Oficio.PROTOCOLO_ORIGEM_TREINAMENTO)
        self.assertIn(oficio.protocolo_origem, Oficio.PROTOCOLO_ORIGENS_NAO_OFICIAIS)

    def test_a_tela_avisa_que_o_numero_nao_e_oficial(self):
        oficio = Oficio.objects.create(numero=11, ano=2026, motivo="Missão de treino")
        resultado = self._abrir(oficio)
        (nivel, texto), = mensagens_do_protocolo(resultado)
        self.assertEqual(nivel, messages.WARNING)
        self.assertIn("treinamento", texto)
        self.assertIn("NÃO vale como protocolo oficial", texto)

    def test_a_ajuda_do_campo_tambem_avisa(self):
        oficio = Oficio.objects.create(numero=12, ano=2026, motivo="Missão de treino")
        self._abrir(oficio)
        oficio.refresh_from_db()
        self.assertIn("NÃO vale como protocolo oficial", ajuda_do_protocolo(oficio))

    def test_campo_vazio_ja_avisa_antes_de_abrir(self):
        oficio = Oficio.objects.create(numero=13, ano=2026, motivo="Missão de treino")
        self.assertIn("treinamento", ajuda_do_protocolo(oficio))

    def test_homologacao_recebe_o_mesmo_tratamento_de_treinamento(self):
        oficio = Oficio.objects.create(numero=14, ano=2026, motivo="Missão de treino")
        with override_settings(EPROTOCOLO={**EPROTOCOLO_REAL, "AMBIENTE": "homologacao"}):
            resultado = self._abrir(oficio)
        oficio.refresh_from_db()
        self.assertFalse(resultado.oficial)
        self.assertEqual(oficio.protocolo_origem, Oficio.PROTOCOLO_ORIGEM_TREINAMENTO)
