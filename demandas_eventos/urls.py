from django.urls import path

from . import views

app_name = "demandas_eventos"

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("lista/", views.lista_demandas, name="lista"),
    path("exportar/", views.exportar_demandas, name="exportar"),
    # Quem já pediu antes (JSON): telefone e e-mail do último pedido.
    path("solicitantes/", views.solicitantes_anteriores, name="solicitantes"),
    path("nova/", views.editar_demanda, name="nova"),
    # "Preencher com um e-mail" da tela nova: lê e sugere, não grava (POST, JSON).
    path("nova/ler-email/", views.ler_email, name="ler_email"),
    path("<int:pk>/editar/", views.editar_demanda, name="editar"),
    # O anexo de um pedido feito pelo formulário público (/pedido/).
    path("<int:pk>/anexo/", views.anexo_pedido, name="anexo_pedido"),
    path("<int:pk>/andamento/", views.registrar_andamento, name="andamento"),
    path("<int:pk>/responder/", views.responder, name="responder"),
    path("<int:pk>/encaminhar-dg/", views.encaminhar_dg, name="encaminhar_dg"),
    # Última movimentação do protocolo no eProtocolo (só leitura).
    path("<int:pk>/consultar-protocolo/", views.consultar_protocolo, name="consultar_protocolo"),
    path("cadastros/<slug:tipo>/", views.lista_cadastro, name="cadastro_lista"),
    path("cadastros/<slug:tipo>/novo/", views.editar_cadastro, name="cadastro_novo"),
    path("cadastros/<slug:tipo>/<int:pk>/editar/", views.editar_cadastro, name="cadastro_editar"),
    path("cadastros/<slug:tipo>/<int:pk>/excluir/", views.excluir_cadastro, name="cadastro_excluir"),
]
