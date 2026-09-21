from django.urls import path

from . import views
from .editor import api as editor_api
from .editor import pagina as editor_pagina

app_name = "documentos"
urlpatterns = [
    path("<uuid:pk>/baixar/", views.baixar, name="baixar"),
    path("<uuid:pk>/abrir/", views.abrir, name="abrir"),
    # Editor documental: o editor embutido nos formulários, a folha e o
    # endereço antigo da tela (leva ao formulário).
    path("editor/<str:tipo>/<int:pk>/", editor_pagina.pagina, name="editor_pagina"),
    path("editor/<str:tipo>/<int:pk>/folha/", editor_pagina.folha, name="editor_folha"),
    path("editor/<str:tipo>/<int:pk>/embutido/", editor_pagina.embutido, name="editor_embutido"),
    # Editor documental: GET devolve o painel do campo, PATCH grava.
    path("editor/<str:tipo>/<int:pk>/campos/<str:chave>/", editor_api.campo, name="editor_campo"),
    path("editor/<str:tipo>/<int:pk>/blocos/<str:chave>/", editor_api.bloco, name="editor_bloco"),
    path("editor/<str:tipo>/<int:pk>/quebras/<str:chave>/", editor_api.quebra, name="editor_quebra"),
]
