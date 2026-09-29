from django.urls import path

from . import views

app_name = "agent_lab"

urlpatterns = [
    path("", views.index, name="index"),
    path("c/<slug:spec_id>/", views.specimen, name="specimen"),
    path("specimens.json", views.specimens_json, name="specimens"),
    path("health/", views.health, name="health"),
    path("erro/<int:code>/", views.error_preview, name="error_preview"),
]
