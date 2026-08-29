"""Seed idempotente dos dados institucionais iniciais.

Uso: python manage.py seed_initial_data

Pode ser executado quantas vezes for necessário: usa get_or_create e não
duplica registros. Municípios são semeados com uma amostra de municípios do
Paraná associados às mesorregiões do IBGE (dado público); a carga completa dos
399 municípios deve ser feita com `python manage.py importar_municipios <csv>`
a partir de um dataset oficial (ver ajuda do comando).
"""

from django.contrib.auth.models import Group
from django.core.management.base import BaseCommand
from django.db import transaction

from cadastros.models import (
    Equipe,
    Estado,
    Municipio,
    OrgaoResponsavel,
    Regiao,
    Servico,
    TipoEvento,
)
from solicitacoes.permissions import GRUPOS_PADRAO

TIPOS_EVENTO = [
    "Ação social",
    "Feira de serviços",
    "Mutirão CIN",
    "Evento institucional",
    "Paraná em Ação",
]

SERVICOS = [
    "Emissão de CIN",
    "Coleta de digitais",
    "Atendimento social",
    "Orientação jurídica",
    "Fotografia para documento",
]

ORGAOS = [
    "Instituto de Identificação do Paraná",
    "Delegacia-Geral",
    "Delegacia-Geral Adjunta",
]

EQUIPES = ["Equipe Alfa", "Equipe Bravo", "Equipe Charlie"]

# Amostra de municípios do PR por mesorregião do IBGE (dado público).
MUNICIPIOS_PR = {
    "Metropolitana de Curitiba": ["Curitiba", "São José dos Pinhais", "Paranaguá"],
    "Norte Central Paranaense": ["Londrina", "Maringá", "Apucarana"],
    "Oeste Paranaense": ["Cascavel", "Foz do Iguaçu", "Toledo"],
    "Centro Oriental Paranaense": ["Ponta Grossa", "Telêmaco Borba"],
    "Centro-Sul Paranaense": ["Guarapuava"],
    "Sudoeste Paranaense": ["Pato Branco", "Francisco Beltrão"],
    "Noroeste Paranaense": ["Umuarama", "Paranavaí"],
    "Norte Pioneiro Paranaense": ["Jacarezinho", "Cornélio Procópio"],
    "Sudeste Paranaense": ["Irati", "União da Vitória"],
    "Centro Ocidental Paranaense": ["Campo Mourão"],
}


class Command(BaseCommand):
    help = "Cadastra grupos de perfil e dados institucionais iniciais sem duplicar registros."

    @transaction.atomic
    def handle(self, *args, **options):
        criados = 0

        for nome in GRUPOS_PADRAO:
            _, criado = Group.objects.get_or_create(name=nome)
            criados += criado

        for nome in TIPOS_EVENTO:
            _, criado = TipoEvento.objects.get_or_create(nome=nome)
            criados += criado

        for nome in SERVICOS:
            _, criado = Servico.objects.get_or_create(nome=nome)
            criados += criado

        for nome in ORGAOS:
            _, criado = OrgaoResponsavel.objects.get_or_create(nome=nome)
            criados += criado

        for nome in EQUIPES:
            _, criado = Equipe.objects.get_or_create(nome=nome)
            criados += criado

        parana, criado = Estado.objects.get_or_create(
            codigo_ibge=41,
            defaults={"nome": "Paraná", "sigla": "PR"},
        )
        criados += criado

        for regiao_nome, municipios in MUNICIPIOS_PR.items():
            regiao, criado = Regiao.objects.get_or_create(nome=regiao_nome)
            criados += criado
            for municipio_nome in municipios:
                _, criado = Municipio.objects.get_or_create(
                    nome=municipio_nome,
                    estado=parana,
                    defaults={"regiao": regiao},
                )
                criados += criado

        self.stdout.write(
            self.style.SUCCESS(
                f"Seed concluído: {criados} novo(s) registro(s); os demais já existiam."
            )
        )
        self.stdout.write(
            "Para sincronizar todos os estados e municípios do Brasil use: "
            "python manage.py importar_localidades_ibge"
        )
