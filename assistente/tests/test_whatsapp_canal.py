"""O canal ponta a ponta: do POST da Meta até a resposta na fila de saída.

O teste que mais importa aqui é o da conversa inteira: ele prova que a
máquina de preenchimento — perguntar qual Silva, o município sede, o motivo e
só então confirmar — funciona igual pelo WhatsApp e pelo painel, porque é o
mesmo orquestrador. O canal não repete nenhuma regra.
"""

import datetime as dt
from unittest import mock

from django.test import TestCase
from django.utils import timezone

from assistente.models import MensagemEnviada, MensagemRecebida, VinculoWhatsApp
from assistente.whatsapp import servico
from assistente.whatsapp.transporte import EnvioIndisponivel

from .fixtures import criar_geografia, criar_pessoas, criar_usuario
from .whatsapp_fixtures import (
    TranscritorFake,
    TransporteFake,
    canal_configurado,
    entregar,
    payload_audio,
    payload_texto,
    vincular,
)


@canal_configurado
class ConversaPeloWhatsApp(TestCase):
    def setUp(self):
        self.usuario = criar_usuario()
        self.vinculo = vincular(self.usuario)
        self.geo = criar_geografia()
        self.pessoas = criar_pessoas()
        self.transporte = TransporteFake()

    def _turno(self, texto, wa_id):
        entregar(self.client, payload_texto(texto, wa_id=wa_id))
        servico.processar_pendentes(transporte=self.transporte, transcritor=None)
        return MensagemEnviada.objects.order_by("-pk").first()

    def test_consulta_simples_vai_e_volta(self):
        resposta = self._turno("o que está pendente?", "wamid.1")
        self.assertIn("pendência", resposta.texto.lower())
        self.assertEqual(resposta.numero, self.vinculo.numero)
        self.assertEqual(
            MensagemRecebida.objects.get().status, MensagemRecebida.Status.PROCESSADA
        )

    def test_a_conversa_inteira_cria_os_documentos(self):
        from viagens_oficios.models import Oficio
        from viagens_roteiros.models import Roteiro
        from viagens_termos.models import TermoAutorizacao
        from viagens_viagem.models import Viagem

        primeira = self._turno(
            "faça os documentos para um evento em Maringá dia 18/11/2026, "
            "vai o Silva com o motorista Pereira",
            "wamid.p1",
        )
        self.assertIn("mais de um servidor", primeira.texto)

        self.assertIn("município a equipe sai", self._turno("1", "wamid.p2").texto)
        self.assertIn("motivo da viagem", self._turno("Curitiba", "wamid.p3").texto)

        resumo = self._turno("Operação PCPR Mais Perto", "wamid.p4")
        self.assertIn("Destino: MARINGÁ/PR", resumo.texto)
        self.assertIn("Motorista: CARLOS PEREIRA", resumo.texto)
        self.assertIn("Confirma?", resumo.texto)
        # Até aqui, nada no banco: a confirmação ainda não veio.
        self.assertFalse(Viagem.objects.exists())

        final = self._turno("confirmar", "wamid.p5")
        viagem = Viagem.objects.get()
        self.assertEqual(viagem.destino_municipio, self.geo["maringa"])
        self.assertEqual(list(Oficio.objects.get().servidores.all()), [self.pessoas["joao"]])
        self.assertEqual(Roteiro.objects.get().origem_municipio, self.geo["curitiba"])
        self.assertTrue(TermoAutorizacao.objects.exists())
        self.assertIn(f"Viagem #{viagem.pk}", final.texto)

    def test_cancelar_pelo_whatsapp_nao_grava(self):
        from viagens_viagem.models import Viagem

        self._turno(
            "faça os documentos para um evento em Maringá dia 18/11/2026, "
            "vai o João Silva",
            "wamid.c1",
        )
        self._turno("Curitiba", "wamid.c2")
        self._turno("Operação", "wamid.c3")
        resposta = self._turno("cancelar", "wamid.c4")
        self.assertIn("Nada foi gravado", resposta.texto)
        self.assertFalse(Viagem.objects.exists())

    def test_a_conversa_continua_entre_mensagens(self):
        """Continuidade é o que faz "qual Silva?" → "1" funcionar no chat."""
        from assistente.models import Conversa

        self._turno("o que está pendente?", "wamid.k1")
        self._turno("quais viagens desta semana?", "wamid.k2")
        self.assertEqual(Conversa.objects.filter(canal=Conversa.Canal.WHATSAPP).count(), 1)

    def test_o_vinculo_registra_quando_o_numero_falou(self):
        self._turno("o que está pendente?", "wamid.t1")
        self.vinculo.refresh_from_db()
        self.assertIsNotNone(self.vinculo.ultima_entrada_em)


@canal_configurado
class QuemNaoPodeFalar(TestCase):
    def test_numero_sem_vinculo_e_ignorado_em_silencio(self):
        """Responder confirmaria que o sistema existe e abriria conversa paga."""
        entregar(self.client, payload_texto("quem vai para Maringá?", numero="5511888887777"))
        servico.processar_pendentes(transporte=TransporteFake(), transcritor=None)

        recebida = MensagemRecebida.objects.get()
        self.assertEqual(recebida.status, MensagemRecebida.Status.IGNORADA)
        self.assertFalse(MensagemEnviada.objects.exists())

    def test_o_assistente_usa_a_permissao_de_quem_esta_vinculado(self):
        """Quem só consulta pelas telas também só consulta pelo WhatsApp."""
        from viagens_viagem.models import Viagem

        usuario = criar_usuario("so_consulta", pode_escrever=False)
        vincular(usuario, "5541977776666")
        criar_geografia()
        criar_pessoas()

        entregar(
            self.client,
            payload_texto(
                "faça os documentos para um evento em Maringá dia 18/11/2026, "
                "vai o João Silva",
                numero="5541977776666",
            ),
        )
        servico.processar_pendentes(transporte=TransporteFake(), transcritor=None)

        self.assertIn("fora do seu acesso", MensagemEnviada.objects.get().texto)
        self.assertFalse(Viagem.objects.exists())


@canal_configurado
class Audio(TestCase):
    def setUp(self):
        self.usuario = criar_usuario()
        vincular(self.usuario)
        criar_geografia()
        criar_pessoas()

    def test_audio_e_transcrito_e_segue_o_mesmo_caminho_do_texto(self):
        transcritor = TranscritorFake("o que está pendente?")
        entregar(self.client, payload_audio())
        servico.processar_pendentes(
            transporte=TransporteFake(audio=b"ogg-falso"), transcritor=transcritor
        )
        self.assertEqual(transcritor.chamadas, 1)
        self.assertIn("pendência", MensagemEnviada.objects.get().texto.lower())

    def test_a_transcricao_fica_gravada_para_explicar_o_que_ele_entendeu(self):
        entregar(self.client, payload_audio())
        servico.processar_pendentes(
            transporte=TransporteFake(audio=b"ogg"),
            transcritor=TranscritorFake("quais viagens desta semana?"),
        )
        self.assertEqual(
            MensagemRecebida.objects.get().texto, "quais viagens desta semana?"
        )

    def test_sem_transcricao_instalada_ele_avisa_em_vez_de_sumir(self):
        entregar(self.client, payload_audio())
        with mock.patch(
            "assistente.whatsapp.servico.obter_transcritor", return_value=None
        ):
            servico.processar_pendentes(transporte=TransporteFake())
        self.assertIn("transcrição não está instalada", MensagemEnviada.objects.get().texto)

    def test_tipo_nao_suportado_recebe_explicacao(self):
        corpo = payload_texto("x", wa_id="wamid.fig")
        corpo["entry"][0]["changes"][0]["value"]["messages"][0] = {
            "from": "5541999998888", "id": "wamid.fig", "type": "sticker",
            "sticker": {"id": "s.1"},
        }
        entregar(self.client, corpo)
        servico.processar_pendentes(transporte=TransporteFake(), transcritor=None)
        self.assertIn("texto e áudio", MensagemEnviada.objects.get().texto)


@canal_configurado
class CaixaDeSaida(TestCase):
    def setUp(self):
        self.usuario = criar_usuario()
        self.vinculo = vincular(self.usuario)
        self.vinculo.ultima_entrada_em = timezone.now()
        self.vinculo.save()

    def _enfileirar(self, texto="resposta"):
        return MensagemEnviada.objects.create(numero=self.vinculo.numero, texto=texto)

    def test_envia_e_guarda_o_id_devolvido_pela_meta(self):
        mensagem = self._enfileirar()
        transporte = TransporteFake()
        self.assertEqual(servico.drenar_saida(transporte=transporte), 1)

        mensagem.refresh_from_db()
        self.assertEqual(mensagem.status, MensagemEnviada.Status.ENVIADA)
        self.assertTrue(mensagem.wa_message_id)
        self.assertEqual(transporte.enviadas, [(self.vinculo.numero, "resposta")])

    def test_fora_da_janela_de_24h_nao_tenta_enviar(self):
        """Fora dela só template aprovado funciona — e este canal não tem."""
        self.vinculo.ultima_entrada_em = timezone.now() - dt.timedelta(hours=25)
        self.vinculo.save()
        mensagem = self._enfileirar()
        transporte = TransporteFake()

        servico.drenar_saida(transporte=transporte)
        mensagem.refresh_from_db()
        self.assertEqual(mensagem.status, MensagemEnviada.Status.ERRO)
        self.assertIn("Fora da janela de 24h", mensagem.erro)
        self.assertEqual(transporte.enviadas, [])

    def test_falha_de_rede_mantem_na_fila_para_nova_tentativa(self):
        mensagem = self._enfileirar()
        transporte = TransporteFake(falha=EnvioIndisponivel("Rede indisponível"))

        servico.drenar_saida(transporte=transporte)
        mensagem.refresh_from_db()
        self.assertEqual(mensagem.status, MensagemEnviada.Status.PENDENTE)
        self.assertEqual(mensagem.tentativas, 1)
        self.assertIn("Rede indisponível", mensagem.erro)

    def test_depois_do_limite_de_tentativas_desiste(self):
        mensagem = self._enfileirar()
        transporte = TransporteFake(falha=EnvioIndisponivel("token vencido"))
        for _ in range(servico.MAX_TENTATIVAS):
            servico.drenar_saida(transporte=transporte)

        mensagem.refresh_from_db()
        self.assertEqual(mensagem.status, MensagemEnviada.Status.ERRO)
        self.assertEqual(mensagem.tentativas, servico.MAX_TENTATIVAS)

    def test_resposta_longa_e_cortada_dentro_do_limite_da_meta(self):
        recebida = MensagemRecebida.objects.create(
            wa_message_id="wamid.longa", numero=self.vinculo.numero, texto="x"
        )
        enviada = servico._enfileirar(recebida, "a" * 9000)
        self.assertLessEqual(len(enviada.texto), servico.LIMITE_CARACTERES)
        self.assertIn("Abra o sistema", enviada.texto)
