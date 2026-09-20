"""Cenário mínimo e realista: um setor com o módulo Viagens e gente cadastrada.

Dois servidores com o mesmo sobrenome são de propósito — é o caso que o
assistente **precisa** errar para o lado da pergunta, e sem eles o teste de
ambiguidade não valeria nada.
"""

import datetime as dt

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group

from accounts.models import Modulo, Setor
from cadastros.models import Estado, Municipio, Regiao
from viagens_cadastros.models import Cargo, Servidor, Unidade, Viatura
from viagens_cadastros.permissions import CODIGO_MODULO, GRUPO_OPERADOR


def criar_usuario(username="operador", *, com_modulo=True, pode_escrever=True):
    User = get_user_model()
    # Sem senha de propósito: os testes entram por `force_login`, então o
    # usuário nasce com senha inutilizável. Uma senha literal aqui não serviria
    # para nada e ainda dispararia o detector de segredos da CI.
    usuario = User.objects.create_user(username=username)
    if com_modulo:
        setor = Setor.objects.get_or_create(nome="DIVISÃO DE VIAGENS")[0]
        modulo = Modulo.objects.get_or_create(
            codigo=CODIGO_MODULO, defaults={"nome": "Viagens"}
        )[0]
        modulo.setores.add(setor)
        usuario.setores.add(setor)
    if pode_escrever:
        usuario.groups.add(Group.objects.get_or_create(name=GRUPO_OPERADOR)[0])
    return usuario


def criar_geografia():
    estado = Estado.objects.get_or_create(
        sigla="PR", defaults={"nome": "Paraná", "codigo_ibge": 41}
    )[0]
    regiao = Regiao.objects.get_or_create(nome="NORTE CENTRAL")[0]
    maringa = Municipio.objects.get_or_create(
        nome="MARINGÁ", estado=estado, defaults={"regiao": regiao}
    )[0]
    curitiba = Municipio.objects.get_or_create(
        nome="CURITIBA", estado=estado, defaults={"regiao": regiao, "capital": True}
    )[0]
    marialva = Municipio.objects.get_or_create(
        nome="MARIALVA", estado=estado, defaults={"regiao": regiao}
    )[0]
    return {"estado": estado, "maringa": maringa, "curitiba": curitiba, "marialva": marialva}


def criar_pessoas():
    cargo = Cargo.objects.get_or_create(nome="INVESTIGADOR")[0]
    unidade = Unidade.objects.get_or_create(nome="DELEGACIA DE CURITIBA")[0]
    joao = Servidor.objects.create(nome="JOÃO SILVA", cargo=cargo, unidade=unidade)
    marcos = Servidor.objects.create(nome="MARCOS SILVA", cargo=cargo, unidade=unidade)
    pereira = Servidor.objects.create(nome="CARLOS PEREIRA", cargo=cargo, unidade=unidade)
    viatura = Viatura.objects.create(placa="ABC1D23", modelo="DUSTER", unidade=unidade)
    viatura.motoristas.add(pereira)
    return {"joao": joao, "marcos": marcos, "pereira": pereira, "viatura": viatura}


def criar_viagem_com_equipe(municipio, data, servidores, motorista=None):
    """Uma viagem já montada, do jeito que o sistema a monta: viagem + ofício."""
    from viagens_oficios.models import Oficio
    from viagens_viagem.models import Viagem

    viagem = Viagem.objects.create(
        titulo=f"Viagem a {municipio.nome}",
        destino_municipio=municipio,
        destino_estado=municipio.estado,
        data_inicio=data,
        data_fim=data,
    )
    oficio = Oficio.objects.create(viagem=viagem, motorista=motorista, data_criacao=data)
    oficio.servidores.set(servidores)
    return viagem, oficio


def setembro_do_proximo(hoje=None):
    """O setembro que o sistema entende por "setembro" — ver `periodos`."""
    hoje = hoje or dt.date.today()
    ano = hoje.year if 9 >= hoje.month else hoje.year + 1
    return dt.date(ano, 9, 18)
