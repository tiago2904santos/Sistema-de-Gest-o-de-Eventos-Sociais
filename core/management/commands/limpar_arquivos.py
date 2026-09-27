"""`limpar_arquivos [--dias 90] [--apagar]`: o mesmo que a limpeza semanal
das rotinas diárias (core/limpeza.py), à mão. Sem `--apagar`, só simula."""

from __future__ import annotations

from django.core.management.base import BaseCommand

from core import limpeza


class Command(BaseCommand):
    help = (
        "Lista (e, com --apagar, remove) os PDFs antigos dos documentos, os arquivos "
        "órfãos de todas as pastas de upload, as planilhas temporárias do Coffee Break "
        "e as sessões vencidas. Sempre ficam a via emitida, a mais recente e as assinadas."
    )

    def add_arguments(self, parser):
        parser.add_argument("--dias", type=int, default=limpeza.DIAS_GUARDA_ARTEFATOS,
                            help=f"Idade mínima, em dias, dos PDFs de documentos a remover (padrão {limpeza.DIAS_GUARDA_ARTEFATOS}).")
        parser.add_argument("--apagar", action="store_true", help="Remove de fato; sem esta opção, só lista.")

    def handle(self, *args, **options):
        resumo = limpeza.limpar(dias=options["dias"], apagar=options["apagar"])
        for artefato in resumo["artefatos"]:
            self.stdout.write(f"Documento antigo: {artefato.nome_exibicao or artefato.pk} ({artefato.criado_em:%d/%m/%Y})")
        for anexo in resumo["anexos_removidos"]:
            self.stdout.write(f"Anexo de prestação removido: {anexo.pk}")
        for nome in resumo["orfaos"]:
            self.stdout.write(f"Arquivo órfão: {nome}")
        for nome in resumo["importacoes_coffee"]:
            self.stdout.write(f"Planilha temporária: {nome}")
        if options["apagar"]:
            self.stdout.write(self.style.SUCCESS(f"Removidos: {limpeza.descrever(resumo)}."))
        elif limpeza.total(resumo):
            self.stdout.write(self.style.WARNING(f"Diagnóstico: {limpeza.descrever(resumo)}; nada foi apagado. Use --apagar para remover."))
        else:
            self.stdout.write(self.style.SUCCESS("Nada a remover."))
