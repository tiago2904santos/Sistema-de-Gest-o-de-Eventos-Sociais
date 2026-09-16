from django.urls import path

from . import views
from .editor import api as editor_api

app_name = "documentos"
urlpatterns = [
    path("<uuid:pk>/baixar/", views.baixar, name="baixar"),
    # Editor documental: GET devolve o painel do campo, PATCH grava.
    path("editor/<str:tipo>/<int:pk>/campos/<str:chave>/", editor_api.campo, name="editor_campo"),
]
