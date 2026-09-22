"""Importa o JSON do `exportar_eventos_sociais` neste ambiente.

Cada vínculo chega por nome e é resolvido aqui: município por nome + UF,
serviço/equipe/tipo de evento/órgão por nome (criados se faltarem), usuário
por username (criado com o mesmo hash de senha, sem virar administrador se já
existir por aqui). Solicitação já importada não entra duas vezes: a chave é o instante de
criação somado ao solicitante, que vem do outro banco e não se repete.

    python manage.py importar_eventos_sociais eventos.json --commit
"""

import json
from pathlib import Path

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from accounts.models import Setor
from cadastros.models import (
    Equipe,
    Municipio,
    OrgaoResponsavel,
    Regiao,
    Servico,
    TipoEvento,
    UnidadeMovel,
)
from solicitacoes.models import (
    AnexoSolicitacao,
    HistoricoSolicitacao,
    SolicitacaoEvento,
    SolicitacaoEventoEquipe,
    SolicitacaoEventoServico,
)
from viagens_cadastros.models import Servidor

from .exportar_eventos_sociais import CAMPOS_SIMPLES

User = get_user_model()

class Command(BaseCommand):
    help = "Importa solicitações de evento exportadas de outro ambiente."

    def add_arguments(self, parser):
        parser.add_argument("arquivo", type=Path)
        parser.add_argument(
            "--commit", action="store_true",
            help="Grava. Sem isso, apenas relata o que faria.",
        )

    def handle(self, arquivo, commit, **_opcoes):
        if not arquivo.exists():
            raise CommandError(f"arquivo não encontrado: {arquivo}")
        dados = json.loads(arquivo.read_text(encoding="utf-8"))
        self.criados = {"usuarios": 0, "cadastros": 0, "solicitacoes": 0, "anexos": 0}
        self.pulados = []
        try:
            with transaction.atomic():
                usuarios = self._usuarios(dados["usuarios"])
                for registro in dados["solicitacoes"]:
                    self._solicitacao(registro, usuarios)
                if not commit:
                    raise _Ensaio
        except _Ensaio:
            self.stdout.write(self.style.WARNING("Ensaio: nada foi gravado."))
        for chave, total in self.criados.items():
            self.stdout.write(f"{chave}: {total}")
        for aviso in self.pulados:
            self.stdout.write(self.style.WARNING(aviso))

    # -- vínculos ---------------------------------------------------------
    def _usuarios(self, lista):
        mapa = {}
        for dados in lista:
            usuario = User.objects.filter(username=dados["username"]).first()
            if usuario is None:
                usuario = User(
                    username=dados["username"],
                    first_name=dados["first_name"],
                    last_name=dados["last_name"],
                    email=dados["email"],
                    is_active=dados["is_active"],
                    is_staff=dados["is_staff"],
                    is_superuser=dados["is_superuser"],
                    deve_trocar_senha=dados["deve_trocar_senha"],
                )
                usuario.password = dados["password"]
                usuario.save()
                self.criados["usuarios"] += 1
                for nome in dados["grupos"]:
                    grupo = Group.objects.filter(name=nome).first()
                    if grupo:
                        usuario.groups.add(grupo)
                for nome in dados["setores"]:
                    setor = Setor.objects.filter(nome=nome).first()
                    if setor:
                        usuario.setores.add(setor)
            mapa[dados["username"]] = usuario
        return mapa

    def _por_nome(self, modelo, nome):
        if not nome:
            return None
        objeto = modelo.objects.filter(nome=nome).first()
        if objeto is None:
            objeto = modelo.objects.create(nome=nome)
            self.criados["cadastros"] += 1
        return objeto

    def _municipio(self, dados):
        if not dados:
            return None
        municipio = Municipio.objects.filter(
            nome=dados["nome"], estado__sigla=dados["uf"]
        ).first()
        if municipio is None:
            self.pulados.append(f"município não encontrado: {dados['nome']}/{dados['uf']}")
        return municipio

    # -- registros --------------------------------------------------------
    def _solicitacao(self, registro, usuarios):
        if SolicitacaoEvento.objects.filter(
            criado_em=registro["criado_em"],
            solicitante_nome=registro["solicitante_nome"],
        ).exists():
            self.pulados.append(f"já importada: #{registro['referencia']}")
            return
        solicitacao = SolicitacaoEvento(
            **{campo: registro[campo] for campo in CAMPOS_SIMPLES if campo not in
               {"criado_em", "atualizado_em"}},
            municipio=self._municipio(registro["municipio"]),
            regiao=self._por_nome(Regiao, registro["regiao"]),
            tipo_evento=self._por_nome(TipoEvento, registro["tipo_evento"]),
            orgao_responsavel=self._por_nome(
                OrgaoResponsavel, registro["orgao_responsavel"]
            ),
            unidade_movel_designada=self._por_nome(
                UnidadeMovel, registro["unidade_movel_designada"]
            ),
            motorista=Servidor.objects.filter(nome=registro["motorista"]).first(),
            criado_por=usuarios.get(registro["criado_por"]),
            decidido_por=usuarios.get(registro["decidido_por"]),
        )
        solicitacao.save()
        # auto_now_add/auto_now ignoram o que se põe no construtor: grava depois.
        SolicitacaoEvento.objects.filter(pk=solicitacao.pk).update(
            criado_em=registro["criado_em"], atualizado_em=registro["atualizado_em"]
        )
        self.criados["solicitacoes"] += 1

        for item in registro["servicos"]:
            servico = self._por_nome(Servico, item["nome"])
            SolicitacaoEventoServico.objects.create(
                solicitacao=solicitacao, servico=servico, observacao=item["observacao"]
            )
        for item in registro["equipes"]:
            equipe = self._por_nome(Equipe, item["nome"])
            SolicitacaoEventoEquipe.objects.create(
                solicitacao=solicitacao,
                equipe=equipe,
                quantidade_servidores=item["quantidade_servidores"],
                observacao=item["observacao"],
            )
        for item in registro["historico"]:
            historico = HistoricoSolicitacao.objects.create(
                solicitacao=solicitacao,
                usuario=usuarios.get(item["usuario"]),
                acao=item["acao"],
                status_anterior=item["status_anterior"],
                status_novo=item["status_novo"],
                observacao=item["observacao"],
            )
            HistoricoSolicitacao.objects.filter(pk=historico.pk).update(
                criado_em=item["criado_em"]
            )
        for item in registro["anexos"]:
            anexo = AnexoSolicitacao.objects.create(
                solicitacao=solicitacao,
                arquivo=item["arquivo"],
                nome_original=item["nome_original"],
                tamanho=item["tamanho"],
                enviado_por=usuarios.get(item["enviado_por"]),
            )
            AnexoSolicitacao.objects.filter(pk=anexo.pk).update(
                criado_em=item["criado_em"]
            )
            self.criados["anexos"] += 1


class _Ensaio(Exception):
    """Desfaz a transação do ensaio (--commit ausente)."""
