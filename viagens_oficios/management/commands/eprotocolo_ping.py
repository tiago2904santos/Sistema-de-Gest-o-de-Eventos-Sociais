"""Autenticação de verdade no eProtocolo — a única que sai para a rede.

Pede um token e, se conseguir, faz uma consulta de leitura (órgãos). Não cria
e não altera nada. Em modo simulado responde sem sair da máquina, dizendo que
foi simulado.

    python manage.py eprotocolo_ping
"""

from __future__ import annotations

from django.core.management.base import BaseCommand

from integracoes.eprotocolo import services as epro
from integracoes.eprotocolo import settings as cfg
from integracoes.eprotocolo.exceptions import EProtocoloError


class Command(BaseCommand):
    help = "Testa autenticação e leitura no eProtocolo (nenhuma gravação)."

    def handle(self, *args, **options):
        self.stdout.write(self.style.NOTICE("== eProtocolo: autenticação =="))
        self.stdout.write(f"Situação: {cfg.descricao_ambiente()}")
        try:
            autenticacao = epro.testar_autenticacao()
            self.stdout.write(self.style.SUCCESS(
                autenticacao.mensagem or "Autenticação bem-sucedida."
            ))
            conexao = epro.testar_conexao()
            self.stdout.write(self.style.SUCCESS(
                conexao.mensagem or "Consulta de leitura bem-sucedida."
            ))
        except EProtocoloError as exc:
            self.stderr.write(self.style.ERROR(
                f"{getattr(exc, 'mensagem_usuario', '')} ({exc})".strip()
            ))
            return
        if autenticacao.mock:
            self.stdout.write(
                "Nenhuma chamada real foi feita — preencha as credenciais no .env "
                "para falar com o barramento."
            )
