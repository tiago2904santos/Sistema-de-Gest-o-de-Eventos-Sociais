"""Diagnóstico somente leitura: compara cada `roteiro_ajustado` (cópia editável
criada por `diario_editar_roteiro`) com o roteiro original do ofício.

Não apaga nem altera nada. Serve para decidir com segurança quais cópias nunca
foram de fato alteradas (podem ser descartadas, voltando a usar o roteiro do
ofício) e quais têm um ajuste real que precisa ser preservado.

Uso:
    python manage.py diagnosticar_roteiros_ajustados
"""

from django.core.management.base import BaseCommand

from viagens_prestacoes.diario_services import diferencas_entre_roteiros
from viagens_prestacoes.models import PrestacaoContas


class Command(BaseCommand):
    help = (
        "Compara cada roteiro_ajustado (cópia da Prestação de Contas) com o roteiro "
        "original do ofício e diz se são idênticos (cópia nunca editada, segura de "
        "descartar) ou se divergem (tem ajuste real, não pode ser descartada)."
    )

    def handle(self, *args, **options):
        prestacoes = (
            PrestacaoContas.objects.filter(roteiro_ajustado_id__isnull=False)
            .select_related("oficio", "oficio__roteiro", "roteiro_ajustado")
            .order_by("pk")
        )
        if not prestacoes.exists():
            self.stdout.write(self.style.SUCCESS("Nenhuma prestação com roteiro ajustado encontrada."))
            return

        identicas = 0
        divergentes = 0
        sem_original = 0

        for pc in prestacoes:
            original = pc.oficio.roteiro if pc.oficio_id else None
            copia = pc.roteiro_ajustado
            oficio_label = f"#{pc.oficio.numero}/{pc.oficio.ano}" if pc.oficio and pc.oficio.numero else f"oficio_pk{pc.oficio_id}"

            if original is None:
                sem_original += 1
                self.stdout.write(
                    f"PC#{pc.pk:<5} oficio={oficio_label:<12} copia=#{copia.pk} "
                    f"-> SEM ORIGINAL (ofício não tem roteiro próprio; não mexer)"
                )
                continue

            if original.pk == copia.pk:
                self.stdout.write(
                    f"PC#{pc.pk:<5} oficio={oficio_label:<12} copia=#{copia.pk} "
                    f"-> copia É o proprio roteiro do oficio (sem clone)"
                )
                continue

            diffs = diferencas_entre_roteiros(original, copia)
            if diffs:
                divergentes += 1
                self.stdout.write(
                    f"PC#{pc.pk:<5} oficio={oficio_label:<12} original=#{original.pk} copia=#{copia.pk} "
                    f"-> DIVERGENTE (campos diferentes: {', '.join(diffs)}) - NAO descartar"
                )
            else:
                identicas += 1
                self.stdout.write(
                    f"PC#{pc.pk:<5} oficio={oficio_label:<12} original=#{original.pk} copia=#{copia.pk} "
                    f"-> IDENTICA (nunca foi alterada, segura de descartar)"
                )

        self.stdout.write("")
        self.stdout.write(
            self.style.WARNING(
                f"Resumo: {prestacoes.count()} prestacoes com copia | {identicas} identicas | "
                f"{divergentes} divergentes | {sem_original} sem original"
            )
        )
