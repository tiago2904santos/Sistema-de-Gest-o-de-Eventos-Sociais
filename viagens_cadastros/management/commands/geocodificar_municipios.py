"""Preenche latitude/longitude dos municípios sem coordenadas.

Consulta a API Nominatim (OpenStreetMap) — gratuita e sem chave —, no mesmo
desenho validado na Central de Viagens 3. As coordenadas alimentam o mapa e o
cálculo de rota do editor de roteiros.

Uso:
    python manage.py geocodificar_municipios                  # todos sem coords
    python manage.py geocodificar_municipios --municipio Curitiba
    python manage.py geocodificar_municipios --limite 50
    python manage.py geocodificar_municipios --dry-run
"""

import time

from django.core.management.base import BaseCommand

from cadastros.models import Municipio

from viagens_cadastros.geocodificacao import INTERVALO_SEGUNDOS, _buscar_coordenadas


class Command(BaseCommand):
    help = "Geocodifica municípios sem latitude/longitude via Nominatim (OpenStreetMap)."

    def add_arguments(self, parser):
        parser.add_argument("--municipio", default="", help="Filtrar por nome (parcial).")
        parser.add_argument("--limite", type=int, default=0, help="Máximo de municípios nesta rodada.")
        parser.add_argument("--dry-run", action="store_true", help="Só mostra o que seria gravado.")

    def handle(self, *args, **opts):
        pendentes = (
            Municipio.objects.filter(latitude__isnull=True)
            .select_related("estado")
            .order_by("nome")
        )
        if opts["municipio"]:
            pendentes = pendentes.filter(nome__icontains=opts["municipio"])
        if opts["limite"]:
            pendentes = pendentes[: opts["limite"]]

        gravados = 0
        sem_resultado = []
        pendentes = list(pendentes)
        for indice, municipio in enumerate(pendentes):
            coordenadas = _buscar_coordenadas(municipio.nome, municipio.estado.sigla)
            if coordenadas is None:
                sem_resultado.append(str(municipio))
            else:
                latitude, longitude = coordenadas
                self.stdout.write(
                    f"{municipio.nome}/{municipio.estado.sigla}: {latitude}, {longitude}"
                )
                if not opts["dry_run"]:
                    Municipio.objects.filter(pk=municipio.pk).update(
                        latitude=latitude, longitude=longitude
                    )
                gravados += 1
            if indice < len(pendentes) - 1:
                time.sleep(INTERVALO_SEGUNDOS)

        sufixo = " (dry-run: nada gravado)" if opts["dry_run"] else ""
        self.stdout.write(
            self.style.SUCCESS(
                f"{gravados} município(s) geocodificado(s){sufixo}; "
                f"{len(sem_resultado)} sem resultado."
            )
        )
        for nome in sem_resultado:
            self.stdout.write(self.style.WARNING(f"Sem coordenadas para: {nome}"))
