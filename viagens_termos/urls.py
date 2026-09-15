from django.urls import path
from . import views

app_name = 'viagens_termos'
urlpatterns = [
    path('', views.lista, name='lista'),
    path('api/oficios/', views.api_buscar_oficios, name='api_buscar_oficios'),
    path('novo/', views.editar, name='novo'),
    path('<int:pk>/editar/', views.editar, name='editar'),
    path('<int:pk>/preview/', views.preview, name='preview'),
    path('<int:pk>/preview/<int:servidor_id>/', views.preview, name='preview_servidor'),
    # Todos os termos: um PDF só (`todos/pdf`) ou um ZIP por formato (`lote`).
    path('<int:pk>/todos/pdf/', views.gerar_todos_pdf, name='todos_pdf'),
    path('<int:pk>/gerar/<str:formato>/', views.gerar_lote, name='lote'),
    path('<int:pk>/gerar/viatura/<str:formato>/', views.gerar_viatura, name='gerar_viatura'),
    # servidor_id=0 é o termo genérico (semipreenchido), sem servidor.
    path('<int:pk>/gerar/<int:servidor_id>/<str:formato>/', views.gerar, name='gerar'),
    path('<int:pk>/acao/<str:acao>/', views.acao, name='acao'),
]
