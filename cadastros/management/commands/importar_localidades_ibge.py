"""Importa estados e municípios a partir da API oficial de localidades do IBGE."""

import json
import gzip
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from cadastros.models import Estado, Municipio, Regiao


URL_ESTADOS = "https://servicodados.ibge.gov.br/api/v1/localidades/estados?orderBy=nome"
URL_MUNICIPIOS = (
    "https://servicodados.ibge.gov.br/api/v1/localidades/municipios?orderBy=nome"
)

# Regiões operacionais da PCPR (ver regiao_do_municipio).
REGIAO_CAPITAL = "Capital"
REGIAO_INTERIOR = "Interior"
REGIAO_BRASILIA = "Brasília"
NOME_CAPITAL = "Curitiba"
NOME_BRASILIA = "Brasília"


def obter_json(url):
    requisicao = Request(url, headers={"User-Agent": "PCPR-Eventos-Sociais/1.0"})
    try:
        with urlopen(requisicao, timeout=120) as resposta:
            conteudo = resposta.read()
            if conteudo.startswith(b"\x1f\x8b"):
                conteudo = gzip.decompress(conteudo)
            return json.loads(conteudo.decode("utf-8"))
    except (
        HTTPError,
        URLError,
        TimeoutError,
        UnicodeError,
        OSError,
        json.JSONDecodeError,
    ) as erro:
        raise CommandError(f"Não foi possível consultar o IBGE: {erro}") from erro


def uf_do_municipio(item):
    microrregiao = item.get("microrregiao") or {}
    mesorregiao = microrregiao.get("mesorregiao") or {}
    uf = mesorregiao.get("UF")
    if uf:
        return uf
    regiao_imediata = item.get("regiao-imediata") or {}
    regiao_intermediaria = regiao_imediata.get("regiao-intermediaria") or {}
    return regiao_intermediaria.get("UF")


def regiao_do_municipio(nome_municipio, estado):
    """Região operacional da PCPR: Capital, Brasília ou Interior.

    Não é a divisão geográfica do IBGE — é como a Diretoria-Geral organiza o
    deslocamento das equipes. Curitiba é a Capital, Brasília entra à parte por
    causa dos eventos nacionais, e todo o resto é Interior.
    """
    if estado.sigla == "PR" and nome_municipio == NOME_CAPITAL:
        return REGIAO_CAPITAL
    if nome_municipio == NOME_BRASILIA:
        return REGIAO_BRASILIA
    return REGIAO_INTERIOR


class Command(BaseCommand):
    help = "Baixa e sincroniza todos os estados e municípios da API oficial do IBGE."

    @transaction.atomic
    def handle(self, *args, **options):
        estados_recebidos = obter_json(URL_ESTADOS)
        municipios_recebidos = obter_json(URL_MUNICIPIOS)

        estados = {}
        for item in estados_recebidos:
            estado, _ = Estado.objects.update_or_create(
                codigo_ibge=item["id"],
                defaults={
                    "nome": item["nome"],
                    "sigla": item["sigla"],
                    "ativo": True,
                },
            )
            estados[item["id"]] = estado

        criados = atualizados = ignorados = 0
        for item in municipios_recebidos:
            uf = uf_do_municipio(item)
            if not uf or uf.get("id") not in estados:
                ignorados += 1
                continue
            estado = estados[uf["id"]]
            regiao, _ = Regiao.objects.get_or_create(
                nome=regiao_do_municipio(item["nome"], estado)
            )

            municipio = Municipio.objects.filter(codigo_ibge=item["id"]).first()
            if not municipio:
                municipio = Municipio.objects.filter(
                    nome=item["nome"], estado=estado
                ).first()
            if municipio:
                municipio.nome = item["nome"]
                municipio.codigo_ibge = item["id"]
                municipio.estado = estado
                municipio.regiao = regiao
                municipio.ativo = True
                municipio.save()
                atualizados += 1
            else:
                Municipio.objects.create(
                    nome=item["nome"],
                    codigo_ibge=item["id"],
                    estado=estado,
                    regiao=regiao,
                )
                criados += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"IBGE sincronizado: {len(estados)} estados, {criados} municípios "
                f"criados, {atualizados} atualizados e {ignorados} ignorados."
            )
        )
