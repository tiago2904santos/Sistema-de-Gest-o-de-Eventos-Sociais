"""Worker do canal: esvazia a caixa de entrada e a de saída.

Sem broker de propósito. O projeto roda em Windows com waitress, onde Celery
e Redis seriam infraestrutura nova para atender um volume de dezenas de
mensagens por dia. Uma tabela e um comando resolvem — e o dia que o volume
justificar, troca-se o worker sem tocar no resto.

Em produção: uma tarefa agendada chamando `--uma-vez` de minuto em minuto, ou
o modo `--loop` sob um supervisor. As duas formas são seguras de repetir,
porque a idempotência está no banco.
"""

import time

from django.core.management.base import BaseCommand

from assistente.whatsapp import servico


class Command(BaseCommand):
    help = "Processa mensagens recebidas do WhatsApp e envia as respostas."

    def add_arguments(self, parser):
        parser.add_argument(
            "--loop",
            action="store_true",
            help="Fica rodando em vez de fazer uma passada só.",
        )
        parser.add_argument(
            "--intervalo",
            type=int,
            default=5,
            help="Segundos entre as passadas no modo --loop (padrão: 5).",
        )
        parser.add_argument(
            "--limite",
            type=int,
            default=50,
            help="Máximo de mensagens por passada, em cada caixa (padrão: 50).",
        )

    def handle(self, *args, **opcoes):
        if not opcoes["loop"]:
            self._uma_passada(opcoes["limite"])
            return
        self.stdout.write("Processando WhatsApp em laço. Ctrl+C para parar.")
        try:
            while True:
                self._uma_passada(opcoes["limite"], silencioso=True)
                time.sleep(opcoes["intervalo"])
        except KeyboardInterrupt:
            self.stdout.write("\nEncerrado.")

    def _uma_passada(self, limite, silencioso=False):
        recebidas = servico.processar_pendentes(limite=limite)
        enviadas = servico.drenar_saida(limite=limite)
        if silencioso and not (recebidas or enviadas):
            return
        self.stdout.write(
            self.style.SUCCESS(f"{recebidas} processada(s), {enviadas} enviada(s).")
        )
