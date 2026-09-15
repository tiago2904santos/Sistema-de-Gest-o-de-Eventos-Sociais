"""Reconcilia os servidores das prestações com a equipe atual de cada ofício.

Historicamente o sinal que preenche ``PrestacaoServidor`` só *adicionava* linhas
(nunca removia). Quando um ofício é criado dentro de um evento, o wizard semeia a
equipe a partir do ofício anterior; se o usuário depois trocava os servidores, as
linhas semeadas ficavam órfãs na prestação, misturando equipes entre ofícios
(ex.: o ofício 87 exibindo servidores que na verdade pertencem ao 86).

Este comando alinha cada prestação ao ``oficio.servidores`` atual: remove as
linhas de servidores que saíram do ofício e cria as que faltam. Servidores que
permanecem — e seus dados individuais (solicitação, comprovante) —
não são tocados.

``DB-06``: "remover" segue a mesma regra do sinal
(``PrestacaoServidor.sair_da_equipe``). Linha sem nada coletado é apagada; linha
com comprovante ou número de solicitação é apenas marcada como fora
da equipe e some das telas, sem perder nada. O dry-run diz qual dos dois vai
acontecer com cada servidor, porque é essa a diferença que importa revisar antes
de rodar com ``--confirmar``.

Por padrão roda em modo dry-run (só lista o que mudaria). Só mexe no banco com
--confirmar.

Uso:
    python manage.py sincronizar_prestacao_servidores
    python manage.py sincronizar_prestacao_servidores --confirmar
    python manage.py sincronizar_prestacao_servidores --oficio 87/2026 --confirmar
"""

from django.core.management.base import BaseCommand
from django.core.management.base import CommandError
from django.db import transaction

from viagens_prestacoes.models import PrestacaoContas
from viagens_prestacoes.models import PrestacaoServidor


class Command(BaseCommand):
    help = (
        "Alinha os servidores de cada prestacao a equipe atual do oficio "
        "(remove orfaos e cria faltantes). Dry-run por padrao; use --confirmar."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--confirmar",
            action="store_true",
            help="Aplica de fato. Sem essa flag, apenas lista as divergencias (dry-run).",
        )
        parser.add_argument(
            "--oficio",
            default=None,
            help="Limita a um unico oficio, no formato numero/ano (ex.: 87/2026).",
        )

    def _oficios_alvo(self, filtro):
        qs = PrestacaoContas.objects.select_related("oficio").order_by(
            "oficio__ano", "oficio__numero"
        )
        if filtro:
            try:
                numero_str, ano_str = filtro.split("/")
                numero, ano = int(numero_str), int(ano_str)
            except (ValueError, TypeError):
                raise CommandError("--oficio deve estar no formato numero/ano, ex.: 87/2026.") from None
            qs = qs.filter(oficio__numero=numero, oficio__ano=ano)
        return qs

    def _restaurar(self, prestacao, ids_na_equipe):
        """Desfaz a marca de quem voltou para a equipe do ofício (`DB-06`)."""
        marcadas = PrestacaoServidor.todos.filter(
            prestacao=prestacao,
            servidor_id__in=ids_na_equipe,
            removida_em__isnull=False,
        )
        for servidor_prestacao in marcadas:
            servidor_prestacao.voltar_para_equipe()

    def handle(self, *args, **options):
        confirmar = options["confirmar"]
        filtro = options["oficio"]

        prestacoes = self._oficios_alvo(filtro)
        if not prestacoes.exists():
            self.stdout.write("Nenhuma prestacao encontrada para o filtro informado.")
            return

        total_removidos = 0
        total_preservados = 0
        total_criados = 0
        divergentes = 0

        for prestacao in prestacoes:
            oficio = prestacao.oficio
            ids_atuais = set(oficio.servidores.values_list("pk", flat=True))
            # `todos`: as já marcadas como fora da equipe (`DB-06`) precisam ser
            # vistas aqui, senão o comando tentaria recriá-las e esbarraria em
            # `unique_servidor_por_prestacao`.
            saindo = list(
                PrestacaoServidor.todos.filter(
                    prestacao=prestacao, removida_em__isnull=True
                )
                .exclude(servidor_id__in=ids_atuais)
                .select_related("servidor")
            )
            ids_prestacao = set(
                PrestacaoServidor.todos.filter(prestacao=prestacao).values_list(
                    "servidor_id", flat=True
                )
            )

            a_criar = ids_atuais - ids_prestacao
            voltando = ids_atuais & ids_prestacao
            if not saindo and not a_criar:
                # Alguém pode ter voltado para a equipe sem que nada mais mude;
                # nesse caso não há divergência a relatar, só a marca a desfazer.
                if confirmar:
                    self._restaurar(prestacao, voltando)
                continue

            divergentes += 1
            self.stdout.write(
                self.style.WARNING(
                    f"Oficio {oficio.numero_formatado} (prestacao {prestacao.pk}):"
                )
            )
            for servidor_prestacao in saindo:
                destino = (
                    "preservar (tem dados coletados)"
                    if servidor_prestacao.tem_dados_coletados()
                    else "apagar"
                )
                self.stdout.write(
                    f"    sair da equipe: {servidor_prestacao.servidor.nome} -> {destino}"
                )
            if a_criar:
                from viagens_cadastros.models import Servidor

                nomes = list(
                    Servidor.objects.filter(pk__in=a_criar).values_list("nome", flat=True)
                )
                self.stdout.write(f"    criar:   {', '.join(nomes)}")

            if confirmar:
                with transaction.atomic():
                    for servidor_prestacao in saindo:
                        if servidor_prestacao.sair_da_equipe():
                            total_preservados += 1
                        else:
                            total_removidos += 1
                    for servidor_id in a_criar:
                        PrestacaoServidor.todos.get_or_create(
                            prestacao=prestacao, servidor_id=servidor_id
                        )
                    self._restaurar(prestacao, voltando)
                total_criados += len(a_criar)

        if divergentes == 0:
            self.stdout.write(self.style.SUCCESS("Tudo sincronizado. Nada a fazer."))
            return

        if confirmar:
            self.stdout.write(
                self.style.SUCCESS(
                    f"Concluido: {divergentes} prestacoes ajustadas, "
                    f"{total_removidos} linhas apagadas, "
                    f"{total_preservados} preservadas fora da equipe, "
                    f"{total_criados} criadas."
                )
            )
        else:
            self.stdout.write(
                self.style.NOTICE(
                    f"Dry-run: {divergentes} prestacoes divergentes. "
                    "Rode com --confirmar para aplicar."
                )
            )
