"""Desfaz uma carga do Gerenciador de Viagens (`migrar_gv`).

    python manage.py desfazer_migracao_gv <lote>            # simulação
    python manage.py desfazer_migracao_gv <lote> --commit   # desfaz

Pelo diário da carga, na ordem inversa: apaga o que a carga criou e devolve
aos registros que já estavam aqui os valores de antes (o padrão de um
catálogo, o número de um ofício de teste). Arquivos copiados ficam em
`media/legado/` (sem referência, não são servidos) e a leitura do GV não é
tocada.
"""

from django.apps import apps
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from migracao_legado.models import Etapa, Lote, Registro, Vinculo


class Command(BaseCommand):
    help = "Desfaz uma carga do GV (simulação por padrão; --commit desfaz)."

    def add_arguments(self, parser):
        parser.add_argument("lote", help="O id do lote (saída de migrar_gv).")
        parser.add_argument("--commit", action="store_true")

    def handle(self, *args, lote, commit, **opcoes):
        from django.db import connection

        try:
            alvo = Lote.objects.get(pk=lote)
        except (Lote.DoesNotExist, ValueError):
            raise CommandError(f"Lote {lote} não encontrado.")
        self.stdout.write(f"Destino: {connection.settings_dict['NAME']} · lote {alvo.pk} · " + ("DESFAZENDO" if commit else "SIMULAÇÃO"))
        apagados, restaurados, faltando = 0, 0, 0
        with transaction.atomic():
            for registro in Registro.objects.filter(lote=alvo).order_by("-id"):
                modelo = apps.get_model(registro.modelo)
                consulta = modelo._base_manager.filter(pk=registro.destino_pk)
                if not consulta.exists():
                    faltando += 1
                elif registro.criado:
                    consulta.delete()
                    apagados += 1
                elif registro.antes:
                    campos = {f.name: f for f in modelo._meta.concrete_fields}
                    valores = {k: campos[k].to_python(v) for k, v in registro.antes.items() if k in campos}
                    consulta.update(**valores)
                    restaurados += 1
            Vinculo.objects.filter(lote=alvo).delete()
            Registro.objects.filter(lote=alvo).delete()
            Etapa.objects.filter(lote=alvo).delete()
            Lote.objects.filter(pk=alvo.pk).update(desfeito_em=timezone.now())
            if not commit:
                transaction.set_rollback(True)
        self.stdout.write(f"Apagados: {apagados} · restaurados: {restaurados} · já não existiam: {faltando}")
        if not commit:
            self.stdout.write("Nada foi alterado (simulação). Use --commit para desfazer.")
