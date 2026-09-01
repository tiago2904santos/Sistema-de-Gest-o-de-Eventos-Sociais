from django.urls import path

from . import views

app_name = "demandas_eventos"

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("demandas/", views.lista_demandas, name="lista"),
    path("demandas/exportar/", views.exportar_demandas, name="exportar"),
    path("demandas/nova/", views.editar_demanda, name="nova"),
    path("demandas/<int:pk>/", views.detalhe_demanda, name="detalhe"),
    path("demandas/<int:pk>/editar/", views.editar_demanda, name="editar"),
    path("demandas/<int:pk>/status/", views.transicionar_demanda, name="transicionar"),
    path("cadastros/<slug:tipo>/", views.lista_cadastro, name="cadastro_lista"),
    path("cadastros/<slug:tipo>/novo/", views.editar_cadastro, name="cadastro_novo"),
    path("cadastros/<slug:tipo>/<int:pk>/editar/", views.editar_cadastro, name="cadastro_editar"),
]
