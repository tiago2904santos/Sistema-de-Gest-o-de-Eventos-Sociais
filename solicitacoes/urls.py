from django.urls import path

from . import views

app_name = "solicitacoes"

urlpatterns = [
    path("nova/", views.nova_solicitacao, name="nova"),
]
