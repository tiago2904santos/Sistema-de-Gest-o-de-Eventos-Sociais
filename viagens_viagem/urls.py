from django.urls import path

from . import views

app_name = "viagens_viagem"

urlpatterns = [
    path("", views.lista, name="lista"),
    # "Nova viagem" cria o registro e abre a etapa 1; o GET só devolve a lista.
    path("criar/", views.criar, name="criar"),
    path("<int:pk>/", views.painel, name="painel"),
    path("<int:pk>/etapa-<int:etapa>/", views.etapa, name="etapa"),
    path("<int:pk>/acao/<str:acao>/", views.acao, name="acao"),
    path("<int:pk>/baixar/", views.baixar, name="baixar"),
    path("<int:pk>/solicitacao/anexar/", views.solicitacao_anexar, name="solicitacao_anexar"),
    path("<int:pk>/solicitacao/<int:anexo_pk>/", views.solicitacao_conteudo, name="solicitacao_conteudo"),
    path("<int:pk>/solicitacao/<int:anexo_pk>/excluir/", views.solicitacao_excluir, name="solicitacao_excluir"),
]
