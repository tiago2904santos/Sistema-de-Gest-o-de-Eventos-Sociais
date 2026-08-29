from django.shortcuts import redirect


def home(request):
    """Raiz do site: envia para o dashboard (ou login, se não autenticado)."""
    if request.user.is_authenticated:
        return redirect("dashboard:index")
    return redirect("accounts:login")
