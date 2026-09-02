from django.urls import path
from django.views.generic import RedirectView

from . import views

app_name = "viagens_roteiros"

urlpatterns = [
    path("", views.lista, name="lista"),
    path("novo/", views.editar, name="novo"),
    # Prévia das diárias do formulário em edição — POST, nada é gravado.
    path("previa-diarias/", views.previa, name="previa_diarias"),
    # Rota do percurso para o mapa — POST, nada é gravado.
    path("calcular-rota/", views.rota, name="calcular_rota"),
    # Distância e tempo de um trecho, para preencher a tabela antes da rota.
    path("estimar-trecho/", views.estimar_trecho, name="estimar_trecho"),
    # Gravação automática do rascunho enquanto se monta — cria na primeira.
    path("autosave/", views.autosave, name="autosave_novo"),
    # A tela de detalhe deixou de existir: o roteiro tem uma tela só, a de
    # edição. O endereço antigo continua levando a ela — links guardados e
    # históricos de navegação não viram 404.
    path(
        "<int:pk>/",
        RedirectView.as_view(pattern_name="viagens_roteiros:editar", permanent=True),
        name="detalhe",
    ),
    # Sede e destinos de um roteiro salvo, para reaproveitar na montagem.
    path("<int:pk>/dados/", views.dados_do_roteiro, name="dados"),
    path("<int:pk>/editar/", views.editar, name="editar"),
    path("<int:pk>/autosave/", views.autosave, name="autosave"),
    path("<int:pk>/calcular/", views.calcular, name="calcular"),
    path("<int:pk>/cancelar/", views.cancelar, name="cancelar"),
    path("<int:pk>/reativar/", views.reativar, name="reativar"),
    path("<int:pk>/excluir/", views.excluir, name="excluir"),
]
