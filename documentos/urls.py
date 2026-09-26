from django.urls import path

from . import views
from .editor import api as editor_api
from .editor import completo as editor_completo
from .editor import modelos as editor_modelos
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
    # Editor completo (m057): o documento inteiro editado à mão, com histórico.
    path("editor/<str:tipo>/<int:pk>/completo/", editor_completo.pagina, name="editor_completo"),
    path("editor/<str:tipo>/<int:pk>/completo/folha/", editor_completo.folha, name="editor_completo_folha"),
    path("editor/<str:tipo>/<int:pk>/completo/salvar/", editor_completo.salvar, name="editor_completo_salvar"),
    path("editor/<str:tipo>/<int:pk>/completo/modelo/", editor_completo.voltar_ao_modelo, name="editor_completo_modelo"),
    path("editor/<str:tipo>/<int:pk>/completo/restaurar/<int:versao>/", editor_completo.restaurar, name="editor_completo_restaurar"),
    # Textos-base dos modelos de cada tipo de documento (m057).
    path("modelos/", editor_modelos.indice, name="modelos"),
    path("modelos/<str:tipo>/", editor_modelos.tipo, name="modelos_tipo"),
]
