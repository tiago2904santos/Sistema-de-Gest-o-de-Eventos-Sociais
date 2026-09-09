from django.urls import path
from . import views, catalogs

app_name = 'viagens_oficios'
urlpatterns = [
    path('documentos/<uuid:pk>/assinatura/', views.assinatura_artefato, name='assinatura_artefato'),
    path('documentos/<uuid:pk>/preview/', views.preview_artefato, name='preview_artefato'),
    path('', views.lista, name='lista'),
    path('novo/', views.editar, name='novo'),
    path('numeracao/', views.numeracao, name='numeracao'),
    path('institucional/', catalogs.institucional, name='institucional'),
    path('catalogos/<str:tipo>/', catalogs.catalogo, name='catalogo'),
    path('catalogos/<str:tipo>/novo/', catalogs.catalogo, {'novo': True}, name='catalogo_novo'),
    path('catalogos/<str:tipo>/<int:pk>/', catalogs.catalogo, name='catalogo_editar'),
    path('<int:pk>/', views.detalhe, name='detalhe'),
    path('<int:pk>/editar/', views.editar, name='editar'),
    path('<int:pk>/acao/<str:acao>/', views.acao, name='acao'),
    path('<int:pk>/gerar/<str:tipo>/<str:formato>/', views.gerar, name='gerar'),
    path('<int:pk>/termos/<str:formato>/', views.termos, name='termos_lote'),
    path('<int:pk>/termos/<int:servidor_id>/<str:formato>/', views.termos, name='termo'),
]
