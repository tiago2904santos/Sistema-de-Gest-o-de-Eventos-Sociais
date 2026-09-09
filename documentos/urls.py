from django.urls import path

from . import views

app_name = "documentos"
urlpatterns = [path("<uuid:pk>/baixar/", views.baixar, name="baixar")]
