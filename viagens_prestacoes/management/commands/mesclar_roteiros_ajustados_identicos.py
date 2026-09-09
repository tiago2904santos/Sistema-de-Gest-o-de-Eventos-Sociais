"""Descarta cópias de roteiro (`roteiro_ajustado`) que são idênticas ao roteiro
original do ofício — ou seja, foram criadas ao abrir "Ajustar roteiro" mas nunca
foram de fato editadas. A prestação volta a usar o roteiro do ofício
(`roteiro_efetivo()` já cai para `oficio.roteiro` quando `roteiro_ajustado` é
None), então nada muda no diário/documentos gerados.

Cópias que divergem do original (têm ajuste real) NUNCA são tocadas.

Por padrão roda em modo dry-run (só lista). Só mexe no banco com --confirmar.

Uso:
    python manage.py mesclar_roteiros_ajustados_identicos
    python manage.py mesclar_roteiros_ajustados_identicos --confirmar
"""

from django.core.management.base import BaseCommand
from django.db import transaction

from viagens_oficios.models import Oficio
from viagens_prestacoes.diario_services import diferencas_entre_roteiros
from viagens_prestacoes.models import PrestacaoContas
from viagens_roteiros.models import Roteiro


class Command(BaseCommand):
    help = (
        "Descarta copias de roteiro_ajustado identicas ao roteiro do oficio "
        "(nunca editadas), fazendo a prestacao voltar a usar o roteiro do oficio. "
        "Dry-run por padrao; use --confirmar para aplicar."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--confirmar",
            action="store_true",
            help="Executa a mesclagem de fato. Sem essa flag, apenas lista os candidatos (dry-run).",
        )

    def handle(self, *args, **options):
        confirmar = options["confirmar"]

        prestacoes = (
            PrestacaoContas.objects.filter(roteiro_ajustado_id__isnull=False)
            .select_related("oficio", "oficio__roteiro", "roteiro_ajustado")
            .order_by("pk")
        )

        candidatos = []
        for pc in prestacoes:
            original = pc.oficio.roteiro if pc.oficio_id else None
            copia = pc.roteiro_ajustado
            if original is None or original.pk == copia.pk:
                continue
            if diferencas_entre_roteiros(original, copia):
                continue
            candidatos.append((pc, original, copia))

        if not candidatos:
            self.stdout.write(self.style.SUCCESS("Nenhuma copia identica ao original encontrada."))
            return

        for pc, original, copia in candidatos:
            oficio_label = f"#{pc.oficio.numero}/{pc.oficio.ano}" if pc.oficio.numero else f"oficio_pk{pc.oficio_id}"
            self.stdout.write(
                f"PC#{pc.pk:<5} oficio={oficio_label:<12} copia=#{copia.pk} -> volta a usar roteiro=#{original.pk}"
            )

        if not confirmar:
            self.stdout.write(
                self.style.WARNING(
                    f"{len(candidatos)} copia(s) seriam descartadas. Rode novamente com --confirmar para aplicar."
                )
            )
            return

        apagados = 0
        with transaction.atomic():
            for pc, _original, copia in candidatos:
                pc.roteiro_ajustado = None
                pc.save(update_fields=["roteiro_ajustado", "atualizado_em"])

                ainda_referenciado = (
                    Oficio.objects.filter(roteiro_id=copia.pk).exists()
                    or PrestacaoContas.objects.filter(roteiro_ajustado_id=copia.pk).exists()
                )
                if not ainda_referenciado:
                    Roteiro.objects.filter(pk=copia.pk).delete()
                    apagados += 1

        self.stdout.write(
            self.style.WARNING(
                f"{len(candidatos)} prestacao(oes) voltaram a usar o roteiro do oficio; "
                f"{apagados} copia(s) apagada(s)."
            )
        )
