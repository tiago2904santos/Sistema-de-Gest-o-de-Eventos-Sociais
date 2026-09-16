"""Meta 3 — paridade das telas de ofícios com o Gerenciador de Viagens.

Cobre o que a origem tem e a tela daqui passou a ter: busca por número,
protocolo, motivo ou destino; as quatro situações combináveis com contagem;
as seis ordenações; os dois períodos; o cartão com equipe, transporte,
trechos, valor e justificativa; os menus de ação; o formulário por blocos, com
a conferência, os documentos, o histórico e o encerramento na mesma tela; e os
catálogos no padrão dos cadastros.
"""

from datetime import datetime, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import Modulo, Setor
from cadastros.models import Estado, Municipio, Regiao
from viagens_cadastros.models import Cargo, Servidor, Unidade, Viatura
from viagens_oficios.models import ModeloJustificativa, ModeloMotivoOficio, Oficio
from viagens_oficios.justificativas_services import get_or_create_justificativa_oficio
from viagens_oficios.services import reservar_numero_oficio
from viagens_roteiros.models import Roteiro, RoteiroDestino, RoteiroTrecho


class Cenario(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="operador-m3", deve_trocar_senha=False)
        setor = Setor.objects.create(nome="Setor M3")
        Modulo.objects.get(codigo="VIAGENS").setores.add(setor)
        self.user.setores.add(setor)
        self.user.groups.add(Group.objects.get(name="VIAGENS_OPERADOR"))
        self.client.force_login(self.user)

        regiao = Regiao.objects.get_or_create(nome="Interior")[0]
        self.pr = Estado.objects.get_or_create(sigla="PR", defaults={"nome": "Paraná", "codigo_ibge": 41})[0]
        self.curitiba = Municipio.objects.get_or_create(codigo_ibge=4106902, defaults={"nome": "Curitiba", "estado": self.pr, "regiao": regiao})[0]
        self.antonina = Municipio.objects.get_or_create(codigo_ibge=4101309, defaults={"nome": "Antonina", "estado": self.pr, "regiao": regiao})[0]
        cargo = Cargo.objects.create(nome="AGENTE DE POLÍCIA JUDICIÁRIA")
        self.ascom = Unidade.objects.create(nome="ASSESSORIA DE COMUNICAÇÃO", sigla="ASCOM")
        self.janine = Servidor.objects.create(nome="JANINE LACERDA DO PRADO", cargo=cargo, unidade=self.ascom, cpf="11111111111")
        self.joao = Servidor.objects.create(nome="JOÃO MARIO DE GOES", cargo=cargo, unidade=self.ascom, cpf="22222222222")
        self.duster = Viatura.objects.create(placa="AAA1234", modelo="DUSTER")
        self.hoje = timezone.localdate()

    def roteiro(self, dias, destino=None, valor=Decimal("4358.25")):
        saida = timezone.make_aware(datetime.combine(self.hoje + timedelta(days=dias), datetime.min.time()).replace(hour=8))
        r = Roteiro.objects.create(origem_municipio=self.curitiba, saida_dt=saida, retorno_chegada_dt=saida + timedelta(days=5, hours=1),
                                   valor_diarias=valor, resumo_diarias="5 x 100%", quantidade_servidores=2,
                                   valor_diarias_extenso="quatro mil trezentos e cinquenta e oito reais e vinte e cinco centavos")
        RoteiroDestino.objects.create(roteiro=r, municipio=destino or self.antonina, ordem=1)
        RoteiroTrecho.objects.create(roteiro=r, ordem=1, origem_municipio=self.curitiba, destino_municipio=destino or self.antonina,
                                     saida_dt=saida, chegada_dt=saida + timedelta(minutes=45))
        return r

    def oficio(self, dias=None, protocolo="", servidores=(), motorista=None, viatura=None, justificativa="", cancelar=False, data_criacao=None):
        o = Oficio(data_criacao=data_criacao or self.hoje, protocolo=protocolo, motivo="Cobertura jornalística",
                   roteiro=self.roteiro(dias) if dias is not None else None, viatura=viatura, motorista=motorista)
        o.diarias_quantidade_servidores = len(servidores) or None
        o.save()
        o.servidores.set(servidores)
        o.servidores_termo_autorizacao.set(servidores)
        reservar_numero_oficio(o, ano=o.data_criacao.year)
        j = get_or_create_justificativa_oficio(o)
        if justificativa:
            j.texto = justificativa
            j.save()
        if cancelar:
            o.cancelar("Adiado")
        return o

    def lista(self, **params):
        return self.client.get(reverse("viagens_oficios:lista"), params)


class ListaOficiosTests(Cenario):
    def test_cartao_mostra_o_que_a_origem_mostra(self):
        o = self.oficio(dias=-20, protocolo="123456789", servidores=[self.janine, self.joao], motorista=self.joao, viatura=self.duster, justificativa="teste 1")
        r = self.lista()
        self.assertContains(r, f"Nº {o.numero_formatado} · Protocolo 12.345.678-9")
        self.assertContains(r, "ANTONINA/PR")
        self.assertContains(r, "há 15 dias")
        self.assertContains(r, "JANINE LACERDA DO PRADO")
        self.assertContains(r, "AGENTE DE POLÍCIA JUDICIÁRIA · ASCOM")
        self.assertContains(r, 'class="of-tag">Motorista')
        self.assertContains(r, "AAA-1234")
        self.assertContains(r, "DUSTER")
        self.assertContains(r, "CURITIBA/PR → ANTONINA/PR")
        self.assertContains(r, "R$ 4.358,25")
        self.assertContains(r, "quatro mil trezentos e cinquenta e oito reais e vinte e cinco centavos")
        self.assertContains(r, "5 x 100%")
        self.assertContains(r, "Preenchida")
        self.assertContains(r, "teste 1")
        self.assertContains(r, "Mostrando <strong>1–1</strong> de <strong>1</strong>")

    def test_cartao_de_rascunho_vazio(self):
        self.oficio()
        r = self.lista()
        self.assertContains(r, "Nenhum servidor informado")
        self.assertContains(r, "Não informado")
        self.assertContains(r, "Pendente")
        self.assertContains(r, "Nenhuma justificativa informada.")
        self.assertContains(r, 'class="st st--rascunho">Rascunho')

    def test_menus_do_cartao(self):
        o = self.oficio(dias=3, servidores=[self.janine])
        r = self.lista()
        self.assertContains(r, "Ações do termo de JANINE LACERDA DO PRADO")
        self.assertContains(r, f"Abrir documentos do ofício {o.numero_formatado}")
        self.assertContains(r, "Mais ações do ofício")
        self.assertContains(r, "Editar justificativa")
        self.assertContains(r, "Abrir documentos da justificativa")
        for texto in ["Visualizar termo", "Documento pronto para assinatura", "Arquivo editável do termo", "Anexar assinado",
                      "Visualizar ofício", "Abrir o documento no navegador", "Documento pronto para impressão", "Arquivo editável do ofício",
                      "Retificar ofício", "Atualizar o estado de retificação", "Ofício complementar", "Identificar o documento como complementar",
                      "Cancelar ofício", "Interromper o fluxo mantendo o histórico", "Excluir ofício", "Remover permanentemente quando permitido",
                      "Visualizar justificativa", "Arquivo editável da justificativa"]:
            self.assertContains(r, texto)

    def test_leitor_nao_ve_menus_de_escrita(self):
        self.oficio(dias=3, servidores=[self.janine])
        self.user.groups.clear()
        r = self.lista()
        self.assertEqual(r.status_code, 200)
        self.assertNotContains(r, "Mais ações do ofício")
        self.assertNotContains(r, "Ações do termo de")
        self.assertNotContains(r, "Novo ofício")

    def test_busca_por_numero_protocolo_motivo_e_destino(self):
        a = self.oficio(dias=3, protocolo="123456789")
        b = self.oficio()
        b.motivo = "Curso em Foz"
        b.save()
        self.assertContains(self.lista(q="12.345.678-9"), f"Nº {a.numero_formatado}")
        self.assertNotContains(self.lista(q="12.345.678-9"), f"Nº {b.numero_formatado}")
        self.assertContains(self.lista(q="Antonina"), f"Nº {a.numero_formatado}")
        self.assertContains(self.lista(q="Foz"), f"Nº {b.numero_formatado}")
        self.assertContains(self.lista(q=b.numero_formatado), f"Nº {b.numero_formatado}")
        self.assertNotContains(self.lista(q=b.numero_formatado), f"Nº {a.numero_formatado}")

    def test_sem_resultado(self):
        self.oficio()
        r = self.lista(q="ZZZ_PARIDADE")
        self.assertContains(r, "Nenhum ofício")
        self.assertContains(r, "Nenhum ofício encontrado com os filtros aplicados.")
        self.assertContains(r, "Limpar")

    def test_situacoes_combinaveis_com_contagem(self):
        futuro = self.oficio(dias=10)
        atual = self.oficio(dias=-3)
        rascunho = self.oficio()
        cancelado = self.oficio(dias=20, cancelar=True)
        r = self.lista()
        self.assertContains(r, "Que vão acontecer (1)")
        self.assertContains(r, "Em andamento e realizados (2)")
        self.assertContains(r, "Finalizados (0)")
        self.assertContains(r, "Cancelados (1)")
        r = self.lista(situacao=["futuras", "cancelados"])
        self.assertContains(r, f"Nº {futuro.numero_formatado}")
        self.assertContains(r, f"Nº {cancelado.numero_formatado}")
        self.assertNotContains(r, f"Nº {atual.numero_formatado}")
        self.assertNotContains(r, f"Nº {rascunho.numero_formatado}")
        r = self.lista(situacao="atuais")
        self.assertContains(r, f"Nº {atual.numero_formatado}")
        self.assertContains(r, f"Nº {rascunho.numero_formatado}")
        # A contagem não muda com a situação marcada: continua dizendo quantos existem.
        self.assertContains(r, "Cancelados (1)")

    def test_ordenacoes(self):
        primeiro = self.oficio(dias=30, data_criacao=self.hoje - timedelta(days=5))
        segundo = self.oficio(dias=2, data_criacao=self.hoje)

        def ordem(sort):
            html = self.lista(sort=sort).content.decode()
            return html.index(f"Nº {primeiro.numero_formatado}") < html.index(f"Nº {segundo.numero_formatado}")

        self.assertFalse(ordem("numero_desc"))
        self.assertTrue(ordem("numero_asc"))
        self.assertFalse(ordem("criacao_desc"))
        self.assertTrue(ordem("criacao_asc"))
        self.assertFalse(ordem("viagem_asc"))
        self.assertTrue(ordem("viagem_desc"))
        r = self.lista()
        for rotulo in ["Número: maior", "Número: menor", "Criação: mais recente", "Criação: mais antiga", "Viagem: mais próxima", "Viagem: mais distante"]:
            self.assertContains(r, rotulo)

    def test_periodos_de_viagem_e_criacao(self):
        perto = self.oficio(dias=2, data_criacao=self.hoje)
        longe = self.oficio(dias=40, data_criacao=self.hoje - timedelta(days=30))
        de, ate = (self.hoje + timedelta(days=1)).isoformat(), (self.hoje + timedelta(days=10)).isoformat()
        r = self.lista(viagem_de=de, viagem_ate=ate)
        self.assertContains(r, f"Nº {perto.numero_formatado}")
        self.assertNotContains(r, f"Nº {longe.numero_formatado}")
        r = self.lista(criacao_de=(self.hoje - timedelta(days=40)).isoformat(), criacao_ate=(self.hoje - timedelta(days=20)).isoformat())
        self.assertContains(r, f"Nº {longe.numero_formatado}")
        self.assertNotContains(r, f"Nº {perto.numero_formatado}")

    def test_paginacao_de_vinte_com_page(self):
        for _ in range(21):
            self.oficio()
        r = self.lista()
        self.assertContains(r, "Mostrando <strong>1–20</strong> de <strong>21</strong>")
        self.assertContains(r, "Ir para a página 2")
        r = self.lista(page=2)
        self.assertContains(r, "Mostrando <strong>21–21</strong> de <strong>21</strong>")


class AcoesDaListaTests(Cenario):
    def test_novo_oficio_cria_rascunho_numerado_e_abre_o_editor(self):
        r = self.client.post(reverse("viagens_oficios:criar"))
        o = Oficio.objects.get()
        self.assertRedirects(r, reverse("viagens_oficios:editar", args=[o.pk]))
        self.assertEqual(o.numero, 1)

    def test_acoes_voltam_para_a_lista_filtrada(self):
        o = self.oficio(dias=3)
        volta = reverse("viagens_oficios:lista") + "?sort=numero_asc"
        r = self.client.post(reverse("viagens_oficios:acao", args=[o.pk, "retificar"]), {"next": volta})
        self.assertRedirects(r, volta)
        o.refresh_from_db()
        self.assertTrue(o.retificado_documento)
        # O mesmo item desliga a marca.
        self.client.post(reverse("viagens_oficios:acao", args=[o.pk, "retificar"]), {"next": volta})
        o.refresh_from_db()
        self.assertFalse(o.retificado_documento)
        r = self.client.post(reverse("viagens_oficios:acao", args=[o.pk, "excluir"]), {"next": volta})
        self.assertRedirects(r, volta)
        self.assertFalse(Oficio.objects.filter(pk=o.pk).exists())

    def test_cancelar_e_reativar_pela_lista(self):
        o = self.oficio(dias=3)
        self.client.post(reverse("viagens_oficios:acao", args=[o.pk, "cancelar"]), {"motivo": "Adiado"})
        o.refresh_from_db()
        self.assertTrue(o.cancelado)
        self.assertContains(self.lista(situacao="cancelados"), "Reativar ofício")
        self.client.post(reverse("viagens_oficios:acao", args=[o.pk, "reativar"]))
        o.refresh_from_db()
        self.assertFalse(o.cancelado)


class FormularioTests(Cenario):
    def payload(self, **extra):
        dados = {"data_criacao": self.hoje.isoformat(), "protocolo": "12.345.678-9", "motivo": "Missão", "custeio": "UNIDADE_DPC",
                 "servidores": [str(self.janine.pk)], "servidores_termo_autorizacao": [str(self.janine.pk)],
                 "motorista_modo": "SERVIDOR", "motorista": self.janine.pk, "viatura": self.duster.pk,
                 "transporte_placa_manual": "XYZ9A87", "transporte_modelo_manual": "SPIN"}
        dados.update(extra)
        return dados

    def test_blocos_proprios_sem_renderizador_generico(self):
        o = self.oficio(dias=3, servidores=[self.janine])
        r = self.client.get(reverse("viagens_oficios:editar", args=[o.pk]))
        for texto in ["Dados e viajantes", "Identificação", "Motivo", "Custeio", "Equipe", "Termo de autorização",
                      "Transporte", "Origem da viatura", "Cartão do motorista externo", "Ofício do motorista",
                      "Porte/transporte de armas", "Roteiro", "Resumo da rota", "Justificativa", "Regra de prazo",
                      "Documentos"]:
            self.assertContains(r, texto)
        self.assertNotContains(r, "viagem-campos")
        self.assertTemplateNotUsed(r, "pages/viagens_oficios/_campos.html")
        # Coluna única: nada de menu lateral flutuante em tela nenhuma.
        for marca in ["<aside", "frm-lateral", 'class="sticky', "step-v", "frm-acoes--flut"]:
            self.assertNotContains(r, marca)

    def test_viatura_cadastrada_apaga_a_manual(self):
        r = self.client.post(reverse("viagens_oficios:novo"), self.payload())
        self.assertEqual(r.status_code, 302)
        o = Oficio.objects.get()
        self.assertEqual(o.viatura, self.duster)
        self.assertEqual(o.transporte_placa_manual, "")
        self.assertEqual(o.transporte_modelo_manual, "")

    def test_custeio_de_outra_instituicao_exige_observacao(self):
        r = self.client.post(reverse("viagens_oficios:novo"), self.payload(custeio="OUTRA_INSTITUICAO"))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "Informe a observação de custeio")
        self.assertContains(r, "Não foi possível salvar o ofício")
        self.assertEqual(Oficio.objects.count(), 0)

    def test_salvar_com_next_volta_para_a_lista(self):
        o = self.oficio(dias=3)
        volta = reverse("viagens_oficios:lista") + "?situacao=futuras"
        r = self.client.post(reverse("viagens_oficios:editar", args=[o.pk]), self.payload(next=volta, acao="salvar"))
        self.assertRedirects(r, volta)
        r = self.client.post(reverse("viagens_oficios:editar", args=[o.pk]), self.payload())
        self.assertRedirects(r, reverse("viagens_oficios:editar", args=[o.pk]))


class ConferenciaNoFormularioTests(Cenario):
    """O que era a tela de detalhe agora é o fim do formulário do ofício."""

    def test_conferencia_documentos_e_acoes(self):
        o = self.oficio(dias=-20, protocolo="123456789", servidores=[self.janine, self.joao], motorista=self.joao, viatura=self.duster, justificativa="teste 1")
        r = self.client.get(reverse("viagens_oficios:editar", args=[o.pk]))
        for texto in ["Dados e viajantes", "Documentos", "pronto para emissão",
                      "Equipe", "Termos de autorização", "Todos num PDF", "Todos em PDF (ZIP)", "Todos em DOCX (ZIP)",
                      "Transporte", "Roteiro", "Justificativa", "Visualizar ofício", "Visualizar justificativa",
                      "Baixar DOCX", "Documentos gerados", "Encerramento", "Retificar ofício", "Ofício complementar",
                      "Arquivar ofício", "Cancelamento", "Excluir ofício", "Histórico", "Abrir prestação de contas"]:
            with self.subTest(texto=texto):
                self.assertContains(r, texto)

    def test_formularios_secundarios_ficam_fora_do_formulario_do_oficio(self):
        """HTML aninhado não existe: os POSTs de documento e de estado vêm depois.

        O formulário do ofício engloba a página; um <form> de emissão ou de
        cancelamento dentro dele seria HTML inválido e os dois posts se
        atrapalhariam.
        """
        o = self.oficio(dias=-20, servidores=[self.janine], motorista=self.janine, viatura=self.duster)
        corpo = self.client.get(reverse("viagens_oficios:editar", args=[o.pk])).content.decode()
        abertura = corpo.index('id="form-oficio"')
        fim_do_formulario = corpo.index("</form>", abertura)
        for rota, args in [("viagens_oficios:gerar", [o.pk, "oficio", "pdf"]),
                           ("viagens_oficios:termos_todos_pdf", [o.pk]),
                           ("viagens_oficios:termos_lote", [o.pk, "docx"]),
                           ("viagens_oficios:acao", [o.pk, "cancelar"]),
                           ("viagens_oficios:acao", [o.pk, "retificar"]),
                           ("viagens_oficios:acao", [o.pk, "excluir"])]:
            with self.subTest(rota=rota, args=args):
                self.assertGreater(corpo.index(reverse(rota, args=args)), fim_do_formulario)

    def test_acao_volta_para_o_formulario(self):
        o = self.oficio(dias=3, servidores=[self.janine])
        r = self.client.post(reverse("viagens_oficios:acao", args=[o.pk, "arquivar"]))
        self.assertRedirects(r, reverse("viagens_oficios:editar", args=[o.pk]))

    def test_pendencias_no_rascunho(self):
        o = self.oficio()
        r = self.client.get(reverse("viagens_oficios:editar", args=[o.pk]))
        self.assertContains(r, "Faltam informações para emitir o documento")
        self.assertContains(r, "Selecione ao menos um viajante.")
        self.assertContains(r, "Completar o ofício")


class CatalogosTests(Cenario):
    def test_catalogos_no_padrao_dos_cadastros(self):
        ModeloMotivoOficio.objects.create(nome="COBERTURA", texto="Texto", is_padrao=True)
        ModeloMotivoOficio.objects.create(nome="CAPACITAÇÃO", texto="Texto", ativo=False)
        r = self.client.get(reverse("viagens_oficios:catalogo", args=["motivos"]))
        self.assertEqual(r.status_code, 200)
        self.assertTemplateUsed(r, "pages/viagens_cadastros/lista.html")
        for texto in ["Motivos de ofício", "COBERTURA", "CAPACITAÇÃO", "Inativo", "Definir padrão", "Excluir", "Novo modelo de motivo"]:
            self.assertContains(r, texto)
        r = self.client.get(reverse("viagens_oficios:catalogo_novo", args=["motivos"]))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "Texto que vai para o ofício ao escolher este modelo")
        r = self.client.get(reverse("viagens_oficios:catalogo", args=["justificativas"]))
        self.assertContains(r, "Modelos de justificativa")

    def test_criar_e_definir_padrao(self):
        r = self.client.post(reverse("viagens_cadastros:novo", args=["modelos-justificativa"]),
                             {"nome": "demanda urgente", "texto": "Texto", "ordem": 10, "ativo": "1", "ativo__enviado": "1", "is_padrao__enviado": "1"})
        self.assertEqual(r.status_code, 302)
        m = ModeloJustificativa.objects.get()
        self.assertEqual(m.nome, "DEMANDA URGENTE")
        self.assertFalse(m.is_padrao)
        self.client.post(reverse("viagens_cadastros:definir_padrao", args=["modelos-justificativa", m.pk]))
        m.refresh_from_db()
        self.assertTrue(m.is_padrao)
        # Fora da trilha de cadastros (o rótulo segue na gaveta "Modelos" da navegação).
        self.assertNotContains(self.client.get(reverse("viagens_cadastros:index"), follow=True), 'class="cad-i__t">Motivos de ofício')
