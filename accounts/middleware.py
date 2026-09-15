"""Troca obrigatória da senha definida por outra pessoa."""

from django.contrib import messages
from django.shortcuts import redirect
from django.urls import resolve, reverse

# Rotas que continuam acessíveis enquanto a senha não é trocada: a própria
# troca, o logout e os estáticos servidos pela aplicação.
ROTAS_LIBERADAS = {"accounts:alterar_senha", "accounts:logout"}


class TrocaDeSenhaObrigatoriaMiddleware:
    """Prende o usuário na tela de troca até ele definir a própria senha."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        usuario = getattr(request, "user", None)
        if (
            usuario is not None
            and usuario.is_authenticated
            and getattr(usuario, "deve_trocar_senha", False)
            and not self._liberada(request)
        ):
            messages.info(
                request,
                "Defina uma senha só sua para continuar — a atual foi "
                "cadastrada por outra pessoa.",
            )
            return redirect("accounts:alterar_senha")
        return self.get_response(request)

    def _liberada(self, request):
        try:
            rota = resolve(request.path_info)
        except Exception:
            return True
        nome = f"{rota.namespace}:{rota.url_name}" if rota.namespace else rota.url_name
        if nome in ROTAS_LIBERADAS:
            return True
        # O admin do Django tem o próprio fluxo de senha; não sequestra.
        return request.path_info.startswith(reverse("admin:index"))
