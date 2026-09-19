"""Traz os dados do Gerenciador de Viagens (GV) para o módulo de viagens.

    python manage.py migrar_gv                # simulação: lê tudo, grava nada
    python manage.py migrar_gv --commit       # grava
    python manage.py migrar_gv --sem-arquivos # só os registros

Repetível (o diário da carga sabe o que já veio) e reversível
(`desfazer_migracao_gv`). O relatório vai para a tela e para
`migracao_relatorios/<lote>.json`. A regra de cada tabela está em
`migracao_legado/carga.py`.
"""

import json
import os
import time
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import transaction

from migracao_legado.carga import Carga
from migracao_legado.models import Etapa, Lote
from migracao_legado.origem import abrir_origem

MEDIA_GV_PADRAO = r"C:\Users\tiago\OneDrive\Documentos\Gerenciador de Viagens\media"
BANCOS_PRINCIPAIS = {"eventos_sociais"}


class Command(BaseCommand):
    help = "Migra os dados do Gerenciador de Viagens (simulação por padrão; --commit grava)."

    def add_arguments(self, parser):
        parser.add_argument("--commit", action="store_true", help="Grava. Sem ele, tudo é desfeito no fim.")
        parser.add_argument("--area", type=int, action="append", help="Área do GV (padrão: 1, a da Polícia Civil).")
        parser.add_argument("--sem-arquivos", action="store_true", help="Não copia PDFs, anexos e assinados.")
        parser.add_argument("--media-gv", default=os.environ.get("LEGADO_MEDIA_ROOT", MEDIA_GV_PADRAO))
        parser.add_argument("--banco-principal", action="store_true",
                            help="Permite gravar no banco principal. Sem ele, --commit só grava numa cópia (POSTGRES_DB=...).")

    def handle(self, *args, **opcoes):
        from django.core.management.base import CommandError
        from django.db import connection, connections

        commit = opcoes["commit"]
        areas = opcoes["area"] or [1]
        inicio = time.monotonic()
        banco = connection.settings_dict["NAME"]
        legado = connections["legado"].settings_dict if "legado" in connections else {}
        self.stdout.write(f"Origem: {legado.get('NAME', '?')}@{legado.get('HOST', '?')} · destino: {banco} · mídia do GV: {opcoes['media_gv']}")
        if commit and str(banco) in BANCOS_PRINCIPAIS and not opcoes["banco_principal"]:
            raise CommandError(f"{banco} é o banco principal: grave numa cópia (POSTGRES_DB=...) ou use --banco-principal.")
        self.stdout.write(("GRAVANDO" if commit else "SIMULAÇÃO (nada é gravado; use --commit)") + f" · áreas {areas}")
        with abrir_origem() as origem, transaction.atomic():
            lote = Lote.objects.create(areas=areas, opcoes={"commit": commit, "arquivos": not opcoes["sem_arquivos"]})
            carga = Carga(origem, lote=lote, areas=areas, media_gv=opcoes["media_gv"], commit=commit,
                          copiar_arquivos=not opcoes["sem_arquivos"], saida=self.stdout.write)
            relatorios = carga.executar()
            Etapa.objects.create(lote=lote, nome="carga", relatorio=relatorios)
            if not commit:
                transaction.set_rollback(True)
        pasta = Path(settings.BASE_DIR) / "migracao_relatorios"
        pasta.mkdir(exist_ok=True)
        arquivo = pasta / f"{'commit' if commit else 'simulacao'}-{lote.pk}.json"
        arquivo.write_text(json.dumps(relatorios, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
        total = {k: sum(r.get(k, 0) if isinstance(r.get(k, 0), int) else 0 for r in relatorios.values() if isinstance(r, dict)) for k in ("criadas", "vinculadas", "atualizadas", "reprovadas")}
        self.stdout.write(f"\nTotal: {total} · {time.monotonic() - inicio:.1f}s · relatório: {arquivo}")
        if commit:
            self.stdout.write(self.style.SUCCESS(f"Lote {lote.pk} gravado. Para desfazer: python manage.py desfazer_migracao_gv {lote.pk} --commit"))
