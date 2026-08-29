from django.urls import path

from . import views

app_name = "solicitacoes"

urlpatterns = [
    path("", views.lista_solicitacoes, name="lista"),
    path("nova/", views.nova_solicitacao, name="nova"),
    path("<int:pk>/", views.detalhe_solicitacao, name="detalhe"),
    path("<int:pk>/editar/", views.editar_solicitacao, name="editar"),
    # Transições de workflow — somente POST.
    path("<int:pk>/enviar/", views.enviar_solicitacao, name="enviar"),
    path("<int:pk>/iniciar-analise/", views.iniciar_analise, name="iniciar_analise"),
    path("<int:pk>/encaminhar-despacho/", views.encaminhar_despacho, name="encaminhar_despacho"),
    path("<int:pk>/despachar/", views.despachar, name="despachar"),
]
