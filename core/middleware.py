"""Requisição corrente em thread-local.

Permite que camadas sem acesso à view (signals de auditoria, por exemplo)
saibam quem é o usuário e qual o caminho da requisição em andamento.
"""

import threading

_local = threading.local()


def obter_requisicao_atual():
    """Devolve a requisição em andamento nesta thread, ou None fora dela."""
    return getattr(_local, "requisicao", None)


class RequisicaoAtualMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        _local.requisicao = request
        try:
            return self.get_response(request)
        finally:
            _local.requisicao = None
