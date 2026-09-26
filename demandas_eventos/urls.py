from django.urls import path

from . import views

app_name = "demandas_eventos"

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("lista/", views.lista_demandas, name="lista"),
    path("exportar/", views.exportar_demandas, name="exportar"),
    path("nova/", views.editar_demanda, name="nova"),
    # "Preencher com um e-mail" da tela nova: lê e sugere, não grava (POST, JSON).
    path("nova/ler-email/", views.ler_email, name="ler_email"),
    path("<int:pk>/editar/", views.editar_demanda, name="editar"),
    path("<int:pk>/andamento/", views.registrar_andamento, name="andamento"),
    path("<int:pk>/responder/", views.responder, name="responder"),
    path("<int:pk>/encaminhar-dg/", views.encaminhar_dg, name="encaminhar_dg"),
    path("cadastros/<slug:tipo>/", views.lista_cadastro, name="cadastro_lista"),
    path("cadastros/<slug:tipo>/novo/", views.editar_cadastro, name="cadastro_novo"),
    path("cadastros/<slug:tipo>/<int:pk>/editar/", views.editar_cadastro, name="cadastro_editar"),
    path("cadastros/<slug:tipo>/<int:pk>/excluir/", views.excluir_cadastro, name="cadastro_excluir"),
]
