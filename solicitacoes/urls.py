from django.urls import path

from . import views

app_name = "solicitacoes"

urlpatterns = [
    path("", views.lista_solicitacoes, name="lista"),
    path("nova/", views.nova_solicitacao, name="nova"),
    path("exportar/", views.exportar_solicitacoes, name="exportar"),
    path("<int:pk>/", views.detalhe_solicitacao, name="detalhe"),
    path("<int:pk>/editar/", views.editar_solicitacao, name="editar"),
    # Transições de workflow — somente POST.
    path("<int:pk>/enviar/", views.enviar_solicitacao, name="enviar"),
    path("<int:pk>/excluir/", views.excluir_solicitacao, name="excluir"),
    # Anexos da solicitação.
    path("<int:pk>/anexos/adicionar/", views.adicionar_anexo, name="anexo_adicionar"),
    path(
        "<int:pk>/anexos/<int:anexo_pk>/baixar/",
        views.baixar_anexo,
        name="anexo_baixar",
    ),
    path(
        "<int:pk>/anexos/<int:anexo_pk>/excluir/",
        views.excluir_anexo,
        name="anexo_excluir",
    ),
    path("<int:pk>/despachar/", views.despachar, name="despachar"),
]
