from django.urls import path

from . import assinatura, views

app_name = "agenda"

urlpatterns = [
    path("", views.painel, name="painel"),
    path("eventos/", views.eventos, name="eventos"),
    path("detalhe/<str:fonte>/<int:pk>/", views.detalhe, name="detalhe"),
    # Assinatura no Outlook/Google/celular: o feed é público (só pelo token);
    # gerar, trocar e revogar o link exige login (POST).
    path("ics/<str:token>.ics", assinatura.feed_ics, name="ics"),
    path("assinatura/", assinatura.assinatura, name="assinatura"),
]
