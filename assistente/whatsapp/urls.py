from django.urls import path

from . import views

# Fora do catálogo de módulos: a Meta não se autentica como usuário de setor,
# então esta rota não pode passar pelo middleware de autorização por módulo.
app_name = "assistente_whatsapp"

urlpatterns = [path("webhook/", views.webhook, name="webhook")]
