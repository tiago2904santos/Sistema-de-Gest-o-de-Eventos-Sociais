"""SQL de leitura, sem importar ou executar código do GV."""

import re
from contextlib import contextmanager

from django.core.management.base import CommandError
from django.db import connections, transaction


class RouterLegado:
    def allow_migrate(self, db, app_label, model_name=None, **hints):
        return False if db == "legado" else None

    def allow_relation(self, obj1, obj2, **hints):
        if "legado" in (obj1._state.db, obj2._state.db):
            return False
        return None


class OrigemSQL:
    """Uma fotografia consistente do PostgreSQL, protegida também no servidor.

    Identificadores vêm exclusivamente do catálogo interno. Valores são sempre
    parâmetros. Não oferece um método para executar SQL arbitrário.
    """

    def __init__(self, cursor):
        self.cursor = cursor

    @staticmethod
    def identificador(nome):
        if not re.fullmatch(r"[a-z][a-z0-9_]*", nome):
            raise ValueError("Identificador SQL inválido.")
        return '"' + nome + '"'

    def linhas(self, tabela, *, colunas=None):
        nome = self.identificador(tabela)
        # Exclua tokens na própria consulta: nunca entram na memória da carga.
        if colunas is None:
            self.cursor.execute(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_schema = 'public' AND table_name = %s ORDER BY ordinal_position",
                [tabela],
            )
            colunas = [r[0] for r in self.cursor.fetchall() if r[0] not in {"link_token", "link_token_hash"}]
        if not colunas:
            raise CommandError(f"Tabela de origem ausente: {tabela}.")
        colunas = [c for c in colunas if c not in {"link_token", "link_token_hash"}]
        if not colunas:
            raise CommandError("Não é permitido ler tokens do legado.")
        campos = ", ".join(self.identificador(c) for c in colunas)
        self.cursor.execute(f"SELECT {campos} FROM {nome} ORDER BY id")
        return [dict(zip(colunas, r)) for r in self.cursor.fetchall()]


@contextmanager
def abrir_origem():
    if "legado" not in connections:
        raise CommandError("Configure LEGADO_DB_NAME/USER/PASSWORD/HOST/PORT para ler o GV.")
    conn = connections["legado"]
    if conn.vendor != "postgresql":
        raise CommandError("A conexão legado deve ser PostgreSQL em somente leitura.")
    with transaction.atomic(using="legado"):
        with conn.cursor() as cursor:
            cursor.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
            cursor.execute("SHOW transaction_read_only")
            if cursor.fetchone()[0] != "on":
                raise CommandError("Origem não está em somente leitura; operação recusada.")
            yield OrigemSQL(cursor)
