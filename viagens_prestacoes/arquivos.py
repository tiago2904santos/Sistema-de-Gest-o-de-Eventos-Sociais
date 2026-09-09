"""Compensa arquivos novos quando a operação transacional falha.

O contexto deve envolver a transação inteira, incluindo geração e carimbo.
Arquivos anteriores só são removidos depois do commit.
"""
from contextlib import contextmanager
from contextvars import ContextVar
from functools import wraps
from django.db import transaction
from django.db.models import FileField
from django.db.models.fields.files import FieldFile

_criados = ContextVar("prestacao_arquivos_criados", default=None)


def registrar_arquivo_criado(storage, nome):
    criados = _criados.get()
    if criados is not None:
        criados.append((storage, nome))


class ArquivoPrivado(FieldFile):
    def save(self, name, content, save=True):
        super().save(name, content, save=False)
        registrar_arquivo_criado(self.storage, self.name)
        try:
            if save:
                self.instance.save()
        except Exception:
            self.storage.delete(self.name)
            raise


class ArquivoPrivadoField(FileField):
    attr_class = ArquivoPrivado


@contextmanager
def transacao_de_arquivos():
    existentes = _criados.get()
    criados = [] if existentes is None else existentes
    inicio = len(criados)
    token = _criados.set(criados)
    try:
        with transaction.atomic():
            yield
    except Exception:
        for storage, nome in reversed(criados[inicio:]):
            storage.delete(nome)
        del criados[inicio:]
        raise
    finally:
        _criados.reset(token)


def atomico_com_arquivos(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        with transacao_de_arquivos():
            return func(*args, **kwargs)
    return wrapper
