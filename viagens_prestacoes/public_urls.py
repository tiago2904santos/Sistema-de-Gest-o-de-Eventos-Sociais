from django.urls import path
from django.views.decorators.http import require_http_methods, require_safe
from . import assinatura_views as views
app_name = "viagens_assinaturas"
urlpatterns = [
 path("verificar/<str:codigo>/", views.publico_verificar, name="verificar"),
 path("<str:token>/", views.publico_landing, name="assinatura_landing"),
 path("<str:token>/concluido/", views.publico_concluido, name="assinatura_concluido"),
 path("<str:token>/<str:tipo>/identidade/", views.publico_identidade, name="assinatura_identidade"),
 path("<str:token>/<str:tipo>/assinar/", views.publico_assinar, name="assinatura_assinar"),
 path("<str:token>/<str:tipo>/origem.pdf", views.publico_pdf_origem, name="assinatura_pdf_origem"),
]
for route in urlpatterns:
    decorator = require_http_methods(["GET", "POST"]) if route.name in {"assinatura_identidade", "assinatura_assinar"} else require_safe
    route.callback = views.acesso_publico(decorator(route.callback))
