"""Diagnóstico da configuração do eProtocolo — sem tocar a rede.

Diz em que ambiente o sistema está, se a abertura automática de protocolo vai
mesmo acontecer e o que falta no `.env`. Credenciais saem mascaradas; o
`client_secret` nunca aparece.

    python manage.py eprotocolo_check
    python manage.py eprotocolo_check --escopos
"""

from __future__ import annotations

from django.core.management.base import BaseCommand

from integracoes.eprotocolo import settings as cfg
from integracoes.eprotocolo.schemas import ESCOPOS_ESPERADOS


class Command(BaseCommand):
    help = "Valida a configuração da integração eProtocolo (sem chamar a API)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--escopos", action="store_true",
            help="Lista os escopos OAuth2 esperados pelo barramento spi-servicos.",
        )

    def handle(self, *args, **options):
        info = cfg.validar_configuracao()

        self.stdout.write(self.style.NOTICE("== Diagnóstico eProtocolo =="))
        self.stdout.write(f"Ambiente: {info['ambiente']}")
        self.stdout.write(f"Base URL: {'configurada' if info['base_url_configurada'] else 'AUSENTE'}")
        self.stdout.write(f"Token URL: {'configurada' if info['token_url_configurada'] else 'AUSENTE'}")
        self.stdout.write(f"Client ID: {info['client_id']}")
        self.stdout.write(f"Client Secret: {'configurado' if info['client_secret_configurado'] else 'AUSENTE'}")
        self.stdout.write(f"Consumer ID: {info['consumer_id']}")
        self.stdout.write(f"Modo real: {'sim' if info['modo_real'] else 'não'}")
        self.stdout.write(f"Somente consulta: {'sim' if info['read_only'] else 'não'}")
        self.stdout.write(
            f"Protocolo automático do ofício: {'ligado' if info['auto_protocolo_oficio'] else 'desligado'}"
        )
        self.stdout.write(f"Situação: {cfg.descricao_ambiente()}")

        if info["ok"]:
            self.stdout.write(self.style.SUCCESS("Status: configuração mínima OK"))
        else:
            faltantes = ", ".join(info["campos_faltantes"]) or "(desconhecido)"
            self.stdout.write(self.style.ERROR(
                f"Status: configuração incompleta — faltam: {faltantes}"
            ))

        if info["auto_protocolo_oficio"] and not info["mutacao_liberada"]:
            self.stdout.write(self.style.WARNING(
                "Os ofícios estão recebendo protocolo SIMULADO. Para abrir protocolo "
                "de verdade: credenciais preenchidas, EPROTOCOLO_AMBIENTE diferente de "
                "mock e EPROTOCOLO_REAL_READONLY=False."
            ))

        if options.get("escopos"):
            self.stdout.write(self.style.NOTICE("\nEscopos OAuth2 esperados:"))
            for escopo in ESCOPOS_ESPERADOS:
                self.stdout.write(f"  - {escopo}")
