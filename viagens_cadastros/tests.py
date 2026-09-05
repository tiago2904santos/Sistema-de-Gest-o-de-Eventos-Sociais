import re
from datetime import date, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.db import IntegrityError, transaction
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse

from accounts.models import Modulo, Setor
from cadastros.models import Regiao

from .forms import CargoForm, ServidorForm, TabelaDiariaForm, UnidadeForm, ViaturaForm
from .models import (
    Cargo,
    Combustivel,
    Servidor,
    TabelaDiaria,
    Unidade,
    Viatura,
    faixa_da_regiao,
)
from .permissions import (
    CODIGO_MODULO,
    GRUPO_GESTOR,
    GRUPO_OPERADOR,
    pode_editar_cadastros,
    pode_editar_diarias,
)

User = get_user_model()


class BaseViagensTestCase(TestCase):
    """Usuário com o módulo VIAGENS, que é o mínimo para abrir as telas."""

    @classmethod
    def setUpTestData(cls):
        # O setor ASCOM já vem de uma migração de outro módulo.
        cls.setor, _ = Setor.objects.get_or_create(
            nome="ASCOM", defaults={"sigla": "ASCOM"}
        )
        cls.modulo = Modulo.objects.get(codigo=CODIGO_MODULO)
        cls.modulo.setores.add(cls.setor)
        cls.cargo = Cargo.objects.create(nome="Investigador")
        cls.unidade = Unidade.objects.create(nome="Delegacia de Curitiba", sigla="DC")

    def criar_usuario(self, username, *grupos):
        usuario = User.objects.create_user(username=username)
        usuario.setores.add(self.setor)
        for nome in grupos:
            usuario.groups.add(Group.objects.get(name=nome))
        return usuario


class NormalizacaoTests(TestCase):
    def test_servidor_grava_nome_em_maiusculas_sem_espaco_duplo(self):
        servidor = Servidor.objects.create(nome="  maria   da silva ")
        self.assertEqual(servidor.nome, "MARIA DA SILVA")

    def test_cpf_e_telefone_guardam_apenas_digitos(self):
        servidor = Servidor.objects.create(
            nome="João", cpf="529.982.247-25", telefone="(41) 99999-8888"
        )
        self.assertEqual(servidor.cpf, "52998224725")
        self.assertEqual(servidor.telefone, "41999998888")

    def test_cpf_formatado_para_exibicao(self):
        servidor = Servidor.objects.create(nome="João", cpf="52998224725")
        self.assertEqual(servidor.cpf_formatado, "529.982.247-25")

    def test_campo_vazio_exibe_travessao(self):
        servidor = Servidor.objects.create(nome="Sem dados")
        self.assertEqual(servidor.cpf_formatado, "—")
        self.assertEqual(servidor.telefone_formatado, "—")

    def test_servidor_sem_rg_recebe_marca_canonica(self):
        servidor = Servidor.objects.create(nome="Sem RG")
        self.assertTrue(servidor.sem_rg)
        self.assertEqual(servidor.rg_formatado, "NÃO POSSUI RG")

    def test_placa_normaliza_hifen_e_minuscula(self):
        viatura = Viatura.objects.create(placa="abc-1234")
        self.assertEqual(viatura.placa, "ABC1234")
        self.assertEqual(viatura.placa_formatada, "ABC-1234")

    def test_placa_mercosul_nao_recebe_hifen(self):
        viatura = Viatura.objects.create(placa="ABC1D23")
        self.assertEqual(viatura.placa_formatada, "ABC1D23")


class StatusDerivadoTests(TestCase):
    def test_servidor_completo_quando_tem_cargo_cpf_e_rg(self):
        cargo = Cargo.objects.create(nome="Investigador")
        servidor = Servidor.objects.create(
            nome="Completa", cargo=cargo, cpf="52998224725", rg="123456789"
        )
        self.assertEqual(servidor.status, Servidor.Status.COMPLETO)

    def test_servidor_sem_cpf_fica_rascunho(self):
        cargo = Cargo.objects.create(nome="Investigador")
        servidor = Servidor.objects.create(nome="Parcial", cargo=cargo, rg="123456789")
        self.assertEqual(servidor.status, Servidor.Status.RASCUNHO)

    def test_status_e_recalculado_ao_completar_o_cadastro(self):
        servidor = Servidor.objects.create(nome="Evolui")
        self.assertEqual(servidor.status, Servidor.Status.RASCUNHO)
        servidor.cargo = Cargo.objects.create(nome="Escrivão")
        servidor.cpf = "52998224725"
        servidor.rg = "123456789"
        servidor.save()
        self.assertEqual(servidor.status, Servidor.Status.COMPLETO)

    def test_viatura_completa_exige_modelo_combustivel_e_tipo(self):
        viatura = Viatura.objects.create(placa="ABC1234", modelo="Duster")
        self.assertEqual(viatura.status, Viatura.Status.RASCUNHO)
        viatura.combustivel = Combustivel.objects.create(nome="Gasolina")
        viatura.tipo = Viatura.Tipo.CARACTERIZADA
        viatura.save()
        self.assertEqual(viatura.status, Viatura.Status.COMPLETO)


class ConstraintsTests(TestCase):
    def test_dois_servidores_nao_dividem_o_mesmo_cpf(self):
        Servidor.objects.create(nome="Primeira", cpf="52998224725")
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Servidor.objects.create(nome="Segunda", cpf="52998224725")

    def test_varios_servidores_podem_ficar_sem_cpf(self):
        Servidor.objects.create(nome="Sem cpf um")
        Servidor.objects.create(nome="Sem cpf dois")
        self.assertEqual(Servidor.objects.filter(cpf="").count(), 2)

    def test_varios_servidores_podem_estar_sem_rg(self):
        # "NAO POSSUI RG" é marca canônica, não documento: não colide.
        Servidor.objects.create(nome="Sem rg um")
        Servidor.objects.create(nome="Sem rg dois")
        self.assertEqual(Servidor.objects.filter(sem_rg=True).count(), 2)

    def test_placa_e_unica_no_sistema(self):
        Viatura.objects.create(placa="ABC1234")
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Viatura.objects.create(placa="ABC1234")

    def test_marcar_novo_padrao_rebaixa_o_anterior(self):
        primeiro = Cargo.objects.create(nome="Investigador", is_padrao=True)
        segundo = Cargo.objects.create(nome="Escrivão", is_padrao=True)
        primeiro.refresh_from_db()
        self.assertFalse(primeiro.is_padrao)
        self.assertTrue(segundo.is_padrao)
        self.assertEqual(Cargo.objects.filter(is_padrao=True).count(), 1)

    def test_padrao_de_combustivel_tambem_e_unico(self):
        Combustivel.objects.create(nome="Gasolina", is_padrao=True)
        Combustivel.objects.create(nome="Diesel", is_padrao=True)
        self.assertEqual(Combustivel.objects.filter(is_padrao=True).count(), 1)

    def test_banco_recusa_diaria_com_valor_derivado_zerado(self):
        # Um `update()` cru não passa pelo `save()` que deriva os valores.
        tabela = TabelaDiaria.objects.create(
            faixa=TabelaDiaria.Faixa.INTERIOR,
            vigencia_inicio=date(2026, 1, 1),
            valor_24h=Decimal("300.00"),
        )
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                TabelaDiaria.objects.filter(pk=tabela.pk).update(valor_15=Decimal("0"))


class TabelaDiariaTests(TestCase):
    def test_percentuais_sao_derivados_do_valor_de_24h(self):
        tabela = TabelaDiaria.objects.create(
            faixa=TabelaDiaria.Faixa.CAPITAL,
            vigencia_inicio=date(2026, 1, 1),
            valor_24h=Decimal("300.00"),
        )
        self.assertEqual(tabela.valor_15, Decimal("45.00"))
        self.assertEqual(tabela.valor_30, Decimal("90.00"))

    def test_arredondamento_e_meio_para_cima(self):
        # 468,10 × 30% = 140,43 exatos; 468,15 × 30% = 140,445 → 140,45.
        self.assertEqual(
            TabelaDiaria.derivar(Decimal("468.15"))[1], Decimal("140.45")
        )

    def test_vigente_em_devolve_a_mais_recente_ja_iniciada(self):
        antiga = TabelaDiaria.objects.create(
            faixa=TabelaDiaria.Faixa.INTERIOR,
            vigencia_inicio=date(2026, 1, 1),
            valor_24h=Decimal("300.00"),
        )
        nova = TabelaDiaria.objects.create(
            faixa=TabelaDiaria.Faixa.INTERIOR,
            vigencia_inicio=date(2026, 6, 1),
            valor_24h=Decimal("350.00"),
        )
        self.assertEqual(
            TabelaDiaria.vigente_em(TabelaDiaria.Faixa.INTERIOR, date(2026, 5, 31)),
            antiga,
        )
        self.assertEqual(
            TabelaDiaria.vigente_em(TabelaDiaria.Faixa.INTERIOR, date(2026, 6, 1)),
            nova,
        )

    def test_sem_vigencia_iniciada_devolve_none_em_vez_de_valor_inventado(self):
        TabelaDiaria.objects.create(
            faixa=TabelaDiaria.Faixa.INTERIOR,
            vigencia_inicio=date(2026, 6, 1),
            valor_24h=Decimal("350.00"),
        )
        self.assertIsNone(
            TabelaDiaria.vigente_em(TabelaDiaria.Faixa.INTERIOR, date(2026, 5, 31))
        )

    def test_mesma_faixa_nao_repete_data_de_vigencia(self):
        TabelaDiaria.objects.create(
            faixa=TabelaDiaria.Faixa.CAPITAL,
            vigencia_inicio=date(2026, 1, 1),
            valor_24h=Decimal("300.00"),
        )
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                TabelaDiaria.objects.create(
                    faixa=TabelaDiaria.Faixa.CAPITAL,
                    vigencia_inicio=date(2026, 1, 1),
                    valor_24h=Decimal("400.00"),
                )

    def test_faixa_da_regiao_liga_as_regioes_operacionais(self):
        # As três regiões já existem, criadas pela migração `0006`.
        for nome, faixa in [
            ("Capital", "CAPITAL"),
            ("Interior", "INTERIOR"),
            ("Brasília", "BRASILIA"),
        ]:
            regiao, _ = Regiao.objects.get_or_create(nome=nome)
            self.assertEqual(faixa_da_regiao(regiao), faixa)

    def test_regiao_sem_faixa_correspondente_devolve_none(self):
        regiao, _ = Regiao.objects.get_or_create(nome="Litoral")
        self.assertIsNone(faixa_da_regiao(regiao))
        self.assertIsNone(faixa_da_regiao(None))


class FormulariosTests(TestCase):
    def test_cadastros_nao_possuem_mais_estado_ativo_inativo(self):
        for modelo in (Unidade, Cargo, Combustivel, Servidor, Viatura):
            self.assertNotIn("ativo", {campo.name for campo in modelo._meta.fields})

    def test_cpf_com_digito_verificador_errado_e_recusado(self):
        form = ServidorForm(data={"nome": "Teste", "cpf": "11111111111"})
        self.assertFalse(form.is_valid())
        self.assertIn("cpf", form.errors)

    def test_cpf_com_pontuacao_e_aceito(self):
        # O modelo guarda 11 dígitos, mas ninguém digita CPF sem pontuação.
        form = ServidorForm(data={"nome": "Teste", "cpf": "529.982.247-25"})
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data["cpf"], "52998224725")

    def test_telefone_com_pontuacao_e_aceito(self):
        form = ServidorForm(data={"nome": "Teste", "telefone": "(41) 99999-8888"})
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data["telefone"], "41999998888")

    def test_placa_com_hifen_e_aceita(self):
        form = ViaturaForm(data={"placa": "ABC-1234"})
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data["placa"], "ABC1234")

    def test_nome_duplicado_em_caixa_diferente_vira_erro_de_campo(self):
        # O modelo grava em maiúsculas; sem normalizar no form, a checagem de
        # unicidade consultaria outro texto e a gravação estouraria em 500.
        Servidor.objects.create(nome="MARIA DA SILVA")
        form = ServidorForm(data={"nome": "Maria da Silva"})
        self.assertFalse(form.is_valid())
        self.assertIn("nome", form.errors)

    def test_nome_com_espaco_duplo_tambem_colide(self):
        Cargo.objects.create(nome="INVESTIGADOR")
        form = CargoForm(data={"nome": "  investigador  "})
        self.assertFalse(form.is_valid())
        self.assertIn("nome", form.errors)

    def test_rg_escrito_com_acento_e_reconhecido_como_sem_rg(self):
        form = ServidorForm(data={"nome": "Sem documento", "rg": "NÃO POSSUI RG"})
        self.assertTrue(form.is_valid(), form.errors)
        servidor = form.save()
        self.assertTrue(servidor.sem_rg)
        self.assertEqual(servidor.rg_formatado, "NÃO POSSUI RG")

    def test_dois_servidores_sem_rg_escrito_por_extenso_convivem(self):
        for nome in ("Primeira", "Segunda"):
            form = ServidorForm(data={"nome": nome, "rg": "NÃO POSSUI RG"})
            self.assertTrue(form.is_valid(), form.errors)
            form.save()
        self.assertEqual(Servidor.objects.filter(sem_rg=True).count(), 2)

    def test_rg_duplicado_com_pontuacao_vira_erro_de_campo(self):
        Servidor.objects.create(nome="Primeira", rg="123456789")
        form = ServidorForm(data={"nome": "Segunda", "rg": "12.345.678-9"})
        self.assertFalse(form.is_valid())

    def test_diaria_de_valor_irrisorio_e_recusada_no_form(self):
        # R$ 0,03 × 15% arredonda para R$ 0,00 e o banco recusa o derivado.
        form = TabelaDiariaForm(
            data={
                "faixa": TabelaDiaria.Faixa.INTERIOR,
                "vigencia_inicio": "2026-01-01",
                "valor_24h": "0.03",
            }
        )
        self.assertFalse(form.is_valid())
        self.assertIn("valor_24h", form.errors)

    def test_todos_os_cargos_aparecem_no_formulario_de_servidor(self):
        primeiro = Cargo.objects.create(nome="Investigador")
        segundo = Cargo.objects.create(nome="Delegado")
        opcoes = list(ServidorForm().fields["cargo"].queryset)
        self.assertEqual(opcoes, [segundo, primeiro])

    def test_unidade_form_copia_vinculo_de_servidores_do_gerenciador_original(self):
        unidade = Unidade.objects.create(nome="Unidade Norte")
        servidor = Servidor.objects.create(nome="Lotada", unidade=unidade)
        form = UnidadeForm(instance=unidade)
        self.assertIn("servidores", form.fields)
        self.assertIn(servidor.pk, form.initial["servidores"])

    def test_unidade_form_atualiza_os_servidores_lotados(self):
        unidade = Unidade.objects.create(nome="Unidade Norte")
        outra = Unidade.objects.create(nome="Unidade Sul")
        entra = Servidor.objects.create(nome="Entra", unidade=outra)
        sai = Servidor.objects.create(nome="Sai", unidade=unidade)
        form = UnidadeForm(
            data={"nome": unidade.nome, "sigla": "UN", "servidores": [entra.pk]},
            instance=unidade,
        )
        self.assertTrue(form.is_valid(), form.errors)
        form.save()
        entra.refresh_from_db()
        sai.refresh_from_db()
        self.assertEqual(entra.unidade, unidade)
        self.assertIsNone(sai.unidade)

    def test_cpf_em_branco_e_aceito(self):
        form = ServidorForm(data={"nome": "Teste", "cpf": ""})
        self.assertTrue(form.is_valid(), form.errors)

    def test_telefone_sem_ddd_e_recusado(self):
        form = ServidorForm(data={"nome": "Teste", "telefone": "99998888"})
        self.assertFalse(form.is_valid())
        self.assertIn("telefone", form.errors)

    def test_placa_fora_dos_dois_formatos_e_recusada(self):
        form = ViaturaForm(data={"placa": "AB12"})
        self.assertFalse(form.is_valid())
        self.assertIn("placa", form.errors)

    def test_placa_mercosul_e_aceita(self):
        form = ViaturaForm(data={"placa": "abc1d23"})
        self.assertTrue(form.is_valid(), form.errors)

    def test_diaria_com_valor_zero_e_recusada(self):
        form = TabelaDiariaForm(
            data={
                "faixa": TabelaDiaria.Faixa.INTERIOR,
                "vigencia_inicio": "2026-01-01",
                "valor_24h": "0",
            }
        )
        self.assertFalse(form.is_valid())
        self.assertIn("valor_24h", form.errors)

    def test_viatura_com_placa_invalida_falha_no_clean_do_modelo(self):
        viatura = Viatura(placa="XX")
        with self.assertRaises(ValidationError):
            viatura.full_clean()


class AcessoAoModuloTests(BaseViagensTestCase):
    def test_sem_modulo_o_namespace_inteiro_e_negado(self):
        forasteiro = User.objects.create_user(username="forasteiro")
        self.client.force_login(forasteiro)
        resposta = self.client.get(reverse("viagens_cadastros:index"))
        self.assertEqual(resposta.status_code, 403)

    def test_com_modulo_a_tela_abre(self):
        usuario = self.criar_usuario("consulta")
        self.client.force_login(usuario)
        resposta = self.client.get(reverse("viagens_cadastros:index"))
        self.assertEqual(resposta.status_code, 200)

    def test_anonimo_e_mandado_para_o_login(self):
        resposta = self.client.get(reverse("viagens_cadastros:index"))
        self.assertEqual(resposta.status_code, 302)
        self.assertIn("entrar", resposta["Location"])

    def test_modulo_inativo_bloqueia_mesmo_com_setor(self):
        usuario = self.criar_usuario("bloqueada")
        Modulo.objects.filter(pk=self.modulo.pk).update(ativo=False)
        self.client.force_login(usuario)
        resposta = self.client.get(reverse("viagens_cadastros:index"))
        self.assertEqual(resposta.status_code, 403)


class PermissoesDeEscritaTests(BaseViagensTestCase):
    def test_quem_so_tem_o_modulo_consulta_mas_nao_escreve(self):
        usuario = self.criar_usuario("leitora")
        self.assertFalse(pode_editar_cadastros(usuario))
        self.assertFalse(pode_editar_diarias(usuario))

    def test_operador_edita_cadastros_mas_nao_diarias(self):
        usuario = self.criar_usuario("operadora", GRUPO_OPERADOR)
        self.assertTrue(pode_editar_cadastros(usuario))
        self.assertFalse(pode_editar_diarias(usuario))

    def test_gestor_edita_tudo(self):
        usuario = self.criar_usuario("gestora", GRUPO_GESTOR)
        self.assertTrue(pode_editar_cadastros(usuario))
        self.assertTrue(pode_editar_diarias(usuario))

    def test_leitora_recebe_403_ao_tentar_criar_servidor(self):
        self.client.force_login(self.criar_usuario("leitora2"))
        resposta = self.client.post(
            reverse("viagens_cadastros:novo", args=["servidores"]),
            {"nome": "Intrusa", "ativo": "on"},
        )
        self.assertEqual(resposta.status_code, 403)
        self.assertFalse(Servidor.objects.filter(nome="INTRUSA").exists())

    def test_operador_recebe_403_ao_tentar_criar_vigencia_de_diaria(self):
        self.client.force_login(self.criar_usuario("operadora2", GRUPO_OPERADOR))
        resposta = self.client.post(
            reverse("viagens_cadastros:diaria_nova"),
            {
                "faixa": TabelaDiaria.Faixa.INTERIOR,
                "vigencia_inicio": "2026-01-01",
                "valor_24h": "300",
            },
        )
        self.assertEqual(resposta.status_code, 403)
        self.assertFalse(TabelaDiaria.objects.exists())

    def test_gestor_cria_vigencia_de_diaria(self):
        self.client.force_login(self.criar_usuario("gestora2", GRUPO_GESTOR))
        resposta = self.client.post(
            reverse("viagens_cadastros:diaria_nova"),
            {
                "faixa": TabelaDiaria.Faixa.INTERIOR,
                "vigencia_inicio": "2026-01-01",
                "valor_24h": "300",
            },
        )
        self.assertRedirects(resposta, reverse("viagens_cadastros:diarias"))
        self.assertEqual(TabelaDiaria.objects.get().valor_15, Decimal("45.00"))


class TelasTests(BaseViagensTestCase):
    def setUp(self):
        self.usuario = self.criar_usuario("operadora3", GRUPO_OPERADOR)
        self.client.force_login(self.usuario)

    def test_lista_de_servidores_renderiza_com_registros(self):
        Servidor.objects.create(nome="Maria da Silva", cargo=self.cargo)
        resposta = self.client.get(
            reverse("viagens_cadastros:lista", args=["servidores"])
        )
        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, "MARIA DA SILVA")

    def test_busca_filtra_por_nome(self):
        Servidor.objects.create(nome="Maria da Silva")
        Servidor.objects.create(nome="João Souza")
        resposta = self.client.get(
            reverse("viagens_cadastros:lista", args=["servidores"]), {"q": "maria"}
        )
        self.assertContains(resposta, "MARIA DA SILVA")
        self.assertNotContains(resposta, "JOÃO SOUZA")

    def test_busca_de_viatura_encontra_pela_placa(self):
        Viatura.objects.create(placa="ABC1234", modelo="Duster")
        resposta = self.client.get(
            reverse("viagens_cadastros:lista", args=["viaturas"]), {"q": "ABC"}
        )
        self.assertContains(resposta, "ABC-1234")

    def test_formulario_invalido_reexibe_a_tela_com_o_erro_no_campo(self):
        resposta = self.client.post(
            reverse("viagens_cadastros:novo", args=["servidores"]),
            {"nome": "Teste", "cpf": "11111111111"},
        )
        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, "CPF inválido")
        self.assertFalse(Servidor.objects.filter(nome="TESTE").exists())

    def test_tela_de_nova_vigencia_renderiza_para_quem_pode(self):
        self.client.force_login(self.criar_usuario("gestora3", GRUPO_GESTOR))
        resposta = self.client.get(reverse("viagens_cadastros:diaria_nova"))
        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, "Nova vigência")

    def test_slug_inexistente_devolve_404(self):
        resposta = self.client.get(
            reverse("viagens_cadastros:lista", args=["inexistente"])
        )
        self.assertEqual(resposta.status_code, 404)

    def test_criar_servidor_pela_tela(self):
        resposta = self.client.post(
            reverse("viagens_cadastros:novo", args=["servidores"]),
            {
                "nome": "nova servidora",
                "cargo": self.cargo.pk,
                "cpf": "529.982.247-25",
                "unidade": self.unidade.pk,
                "ativo": "on",
            },
        )
        self.assertRedirects(
            resposta, reverse("viagens_cadastros:lista", args=["servidores"])
        )
        servidor = Servidor.objects.get(nome="NOVA SERVIDORA")
        self.assertEqual(servidor.cpf, "52998224725")

    def test_editar_viatura_grava_os_motoristas_escolhidos(self):
        viatura = Viatura.objects.create(placa="ABC1234", modelo="Duster")
        um = Servidor.objects.create(nome="Motorista Um")
        outro = Servidor.objects.create(nome="Motorista Dois")
        resposta = self.client.post(
            reverse("viagens_cadastros:editar", args=["viaturas", viatura.pk]),
            {
                "placa": "ABC-1234",
                "modelo": "Duster",
                "tipo": Viatura.Tipo.CARACTERIZADA,
                "motoristas": [um.pk, outro.pk],
                "ativo": "on",
            },
        )
        self.assertRedirects(
            resposta, reverse("viagens_cadastros:lista", args=["viaturas"])
        )
        self.assertEqual(viatura.motoristas.count(), 2)

    def test_formulario_de_edicao_marca_os_motoristas_ja_vinculados(self):
        viatura = Viatura.objects.create(placa="ABC1234")
        servidor = Servidor.objects.create(nome="Já Vinculado")
        viatura.motoristas.add(servidor)
        resposta = self.client.get(
            reverse("viagens_cadastros:editar", args=["viaturas", viatura.pk])
        )
        campo = next(
            c for c in resposta.context["campos"] if c["name"] == "motoristas"
        )
        marcados = [o["rotulo"] for o in campo["opcoes"] if o["selecionado"]]
        self.assertEqual(marcados, ["JÁ VINCULADO"])

    def test_lista_expoe_apenas_editar_e_excluir(self):
        Servidor.objects.create(nome="Sem alternância")
        resposta = self.client.get(
            reverse("viagens_cadastros:lista", args=["servidores"])
        )
        self.assertContains(resposta, "Editar")
        self.assertContains(resposta, "Excluir")
        self.assertNotContains(resposta, "Inativar")
        self.assertNotContains(resposta, "Ativar")

    def test_excluir_vinculado_avisa_em_vez_de_apagar(self):
        from solicitacoes.models import SolicitacaoEvento

        servidor = Servidor.objects.create(nome="Vinculada")
        criador = User.objects.create_user(username="criador")
        SolicitacaoEvento.objects.create(criado_por=criador, motorista=servidor)
        resposta = self.client.post(
            reverse("viagens_cadastros:excluir", args=["servidores", servidor.pk]),
            follow=True,
        )
        self.assertTrue(Servidor.objects.filter(pk=servidor.pk).exists())
        self.assertContains(resposta, "Exclusão bloqueada")
        self.assertContains(resposta, "Solicitações de evento")

    def test_exclusao_simples_exige_confirmacao_e_remove_no_post(self):
        servidor = Servidor.objects.create(nome="Pode excluir")
        url = reverse(
            "viagens_cadastros:excluir", args=["servidores", servidor.pk]
        )
        resposta = self.client.get(url)
        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, "Excluir definitivamente")
        self.assertTrue(Servidor.objects.filter(pk=servidor.pk).exists())
        resposta = self.client.post(url)
        self.assertRedirects(
            resposta, reverse("viagens_cadastros:lista", args=["servidores"])
        )
        self.assertFalse(Servidor.objects.filter(pk=servidor.pk).exists())

    def test_gestor_pode_excluir_vigencia_de_diaria(self):
        self.client.force_login(self.criar_usuario("gestora4", GRUPO_GESTOR))
        tabela = TabelaDiaria.objects.create(
            faixa=TabelaDiaria.Faixa.BRASILIA,
            vigencia_inicio=date(2026, 1, 1),
            valor_24h=Decimal("468.15"),
        )
        url = reverse("viagens_cadastros:diaria_excluir", args=[tabela.pk])
        self.assertEqual(self.client.get(url).status_code, 200)
        self.client.post(url)
        self.assertFalse(TabelaDiaria.objects.filter(pk=tabela.pk).exists())

    def test_tela_de_diarias_mostra_a_vigencia_atual_por_faixa(self):
        TabelaDiaria.objects.create(
            faixa=TabelaDiaria.Faixa.INTERIOR,
            vigencia_inicio=date.today() - timedelta(days=1),
            valor_24h=Decimal("300.00"),
        )
        resposta = self.client.get(reverse("viagens_cadastros:diarias"))
        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, "300,00")


class TrilhaDeAuditoriaTests(TestCase):
    """O app precisa estar coberto pela trilha criada na Fase 0."""

    def test_criar_servidor_deixa_rastro(self):
        from auditoria.models import RegistroAuditoria

        with self.captureOnCommitCallbacks(execute=True):
            servidor = Servidor.objects.create(nome="Auditada")
        registro = RegistroAuditoria.objects.get(
            modelo="viagens_cadastros.servidor", objeto_id=str(servidor.pk)
        )
        self.assertEqual(registro.acao, RegistroAuditoria.Acao.CRIACAO)

    def test_alterar_valor_de_diaria_deixa_rastro_com_o_antes_e_o_depois(self):
        from auditoria.models import RegistroAuditoria

        tabela = TabelaDiaria.objects.create(
            faixa=TabelaDiaria.Faixa.INTERIOR,
            vigencia_inicio=date(2026, 1, 1),
            valor_24h=Decimal("300.00"),
        )
        with self.captureOnCommitCallbacks(execute=True):
            tabela.valor_24h = Decimal("350.00")
            tabela.save()
        registro = RegistroAuditoria.objects.get(
            modelo="viagens_cadastros.tabeladiaria",
            acao=RegistroAuditoria.Acao.ATUALIZACAO,
        )
        self.assertEqual(
            registro.alteracoes["valor_24h"], {"antes": "300.00", "depois": "350.00"}
        )
        # Os derivados também entram no rastro: são o valor que de fato vale.
        self.assertIn("valor_15", registro.alteracoes)


class SelecaoDeMotoristaNaSolicitacaoTests(TestCase):
    """O select da solicitação lista quem dirige, não o quadro inteiro."""

    def _queryset(self, instance_pk=None):
        from solicitacoes.forms import _queryset_motoristas

        return list(_queryset_motoristas(instance_pk))

    def test_servidor_com_cargo_motorista_aparece(self):
        cargo = Cargo.objects.create(nome="MOTORISTA")
        motorista = Servidor.objects.create(nome="Quem Dirige", cargo=cargo)
        self.assertIn(motorista, self._queryset())

    def test_servidor_designado_em_viatura_aparece_mesmo_com_outro_cargo(self):
        cargo = Cargo.objects.create(nome="Investigador")
        servidor = Servidor.objects.create(nome="Dirige Ocasional", cargo=cargo)
        Viatura.objects.create(placa="ABC1234").motoristas.add(servidor)
        self.assertIn(servidor, self._queryset())

    def test_servidor_que_nao_dirige_fica_fora_do_select(self):
        cargo = Cargo.objects.create(nome="Delegado")
        alheio = Servidor.objects.create(nome="Nao Dirige", cargo=cargo)
        self.assertNotIn(alheio, self._queryset())

    def test_motorista_cadastrado_fica_disponivel_sem_estado_ativo_inativo(self):
        cargo = Cargo.objects.create(nome="MOTORISTA")
        motorista = Servidor.objects.create(nome="Condutor", cargo=cargo)
        self.assertIn(motorista, self._queryset())
        self.assertIn(motorista, self._queryset(instance_pk=motorista.pk))


class SeedDoModuloTests(TestCase):
    def test_modulo_e_grupos_existem_apos_as_migracoes(self):
        self.assertTrue(Modulo.objects.filter(codigo=CODIGO_MODULO).exists())
        self.assertTrue(Group.objects.filter(name=GRUPO_GESTOR).exists())
        self.assertTrue(Group.objects.filter(name=GRUPO_OPERADOR).exists())

    def test_modulo_nasce_sem_setor_vinculado(self):
        # Vincular a ASCOM por padrão daria acesso a quem talvez não deva ter.
        modulo = Modulo.objects.get(codigo=CODIGO_MODULO)
        self.assertEqual(modulo.setores.count(), 0)


class TelaDeDiariasTests(BaseViagensTestCase):
    """Os cartões do topo e a tabela mostram os mesmos números."""

    def setUp(self):
        self.client.force_login(self.criar_usuario("leitora_diarias"))
        TabelaDiaria.objects.create(
            faixa=TabelaDiaria.Faixa.INTERIOR,
            valor_24h=Decimal("290.55"),
            vigencia_inicio=date(2026, 1, 1),
        )

    def test_o_cartao_escreve_os_derivados_no_padrao_brasileiro(self):
        # O cartão era montado com f-string crua e saía "43.58" logo acima de um
        # "43,58" renderizado pelo Django: o mesmo número com duas caras.
        resposta = self.client.get(reverse("viagens_cadastros:diarias"))
        self.assertContains(resposta, "15%: R$ 43,58 · 30%: R$ 87,17")
        self.assertNotContains(resposta, "43.58")

    def test_o_cartao_mostra_o_valor_como_dinheiro(self):
        # Olhar só a página inteira não serve: a tabela abaixo já escreve
        # "R$ 290,55" e o teste passaria mesmo com o cartão exibindo um número
        # solto. O que se afirma aqui é o conteúdo do cartão.
        resposta = self.client.get(reverse("viagens_cadastros:diarias"))
        valores = re.findall(
            r'summary-card__valor">(.*?)</p>', resposta.content.decode(), re.S
        )
        self.assertIn("R$ 290,55", [v.strip() for v in valores])

    def test_faixa_sem_vigencia_nao_finge_ter_valor(self):
        resposta = self.client.get(reverse("viagens_cadastros:diarias"))
        self.assertContains(resposta, "Sem vigência cadastrada")
