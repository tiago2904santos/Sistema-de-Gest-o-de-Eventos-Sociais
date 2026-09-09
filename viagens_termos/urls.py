from django.urls import path
from . import views

app_name = 'viagens_termos'
urlpatterns = [
    path('', views.lista, name='lista'),
    path('novo/', views.editar, name='novo'),
    path('<int:pk>/', views.detalhe, name='detalhe'),
    path('<int:pk>/editar/', views.editar, name='editar'),
    path('<int:pk>/preview/', views.preview, name='preview'),
    path('<int:pk>/preview/<int:servidor_id>/', views.preview, name='preview_servidor'),
    path('<int:pk>/gerar/<str:formato>/', views.gerar, name='lote'),
    path('<int:pk>/gerar/<int:servidor_id>/<str:formato>/', views.gerar, name='gerar'),
    path('<int:pk>/acao/<str:acao>/', views.acao, name='acao'),
]
