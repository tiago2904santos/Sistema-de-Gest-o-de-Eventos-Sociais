from django.urls import path
from . import views, catalogs, justificativas_views

app_name = 'viagens_oficios'
urlpatterns = [
    path('documentos/<uuid:pk>/assinatura/', views.assinatura_artefato, name='assinatura_artefato'),
    path('documentos/<uuid:pk>/preview/', views.preview_artefato, name='preview_artefato'),
    path('', views.lista, name='lista'),
    path('novo/', views.editar, name='novo'),
    path('criar/', views.criar, name='criar'),
    path('numeracao/', views.numeracao, name='numeracao'),
    # Justificativas: lista com cadastro e edição no modal, e exclusão do texto.
    path('justificativas/', justificativas_views.index, name='justificativas'),
    path('justificativas/nova/', justificativas_views.editar, name='justificativa_nova'),
    path('justificativas/<int:pk>/editar/', justificativas_views.editar, name='justificativa_editar'),
    path('justificativas/<int:pk>/excluir/', justificativas_views.excluir, name='justificativa_excluir'),
    path('justificativas/<int:pk>/baixar/', justificativas_views.baixar, name='justificativa_baixar'),
    path('institucional/', catalogs.institucional, name='institucional'),
    path('catalogos/<str:tipo>/', catalogs.catalogo, name='catalogo'),
    path('catalogos/<str:tipo>/novo/', catalogs.catalogo, {'novo': True}, name='catalogo_novo'),
    path('catalogos/<str:tipo>/<int:pk>/', catalogs.catalogo, name='catalogo_editar'),
    path('<int:pk>/editar/', views.editar, name='editar'),
    path('<int:pk>/acao/<str:acao>/', views.acao, name='acao'),
    path('<int:pk>/baixar/', views.baixar, name='baixar'),
    path('<int:pk>/gerar/<str:tipo>/<str:formato>/', views.gerar, name='gerar'),
    path('<int:pk>/documento/', views.documento, name='documento'),
    path('<int:pk>/visualizar/<str:tipo>/', views.visualizar, name='visualizar'),
    path('<int:pk>/visualizar/termo/<int:servidor_id>/', views.visualizar_termo, name='visualizar_termo'),
    path('<int:pk>/documento/folha/', views.documento_folha, name='documento_folha'),
    path('<int:pk>/termos/todos/pdf/', views.termos_todos_pdf, name='termos_todos_pdf'),
    path('<int:pk>/termos/<str:formato>/', views.termos, name='termos_lote'),
    path('<int:pk>/termos/<int:servidor_id>/<str:formato>/', views.termos, name='termo'),
]
