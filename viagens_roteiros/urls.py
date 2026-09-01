from django.urls import path

from . import views

app_name = "viagens_roteiros"

urlpatterns = [
    path("", views.lista, name="lista"),
    path("novo/", views.editar, name="novo"),
    # Prévia das diárias do formulário em edição — POST, nada é gravado.
    path("previa-diarias/", views.previa, name="previa_diarias"),
    # Rota do percurso para o mapa — POST, nada é gravado.
    path("calcular-rota/", views.rota, name="calcular_rota"),
    path("<int:pk>/", views.detalhe, name="detalhe"),
    # Sede e destinos de um roteiro salvo, para reaproveitar na montagem.
    path("<int:pk>/dados/", views.dados_do_roteiro, name="dados"),
    path("<int:pk>/editar/", views.editar, name="editar"),
    path("<int:pk>/calcular/", views.calcular, name="calcular"),
    path("<int:pk>/cancelar/", views.cancelar, name="cancelar"),
    path("<int:pk>/reativar/", views.reativar, name="reativar"),
    path("<int:pk>/excluir/", views.excluir, name="excluir"),
]
