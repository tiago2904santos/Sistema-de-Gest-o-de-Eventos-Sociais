from django.urls import path

from . import views

app_name = "solicitacoes"

urlpatterns = [
    path("", views.lista_solicitacoes, name="lista"),
    path("nova/", views.nova_solicitacao, name="nova"),
    # "Preencher com um e-mail" da tela nova: lê e sugere, não grava (POST, JSON).
    path("nova/ler-email/", views.ler_email, name="ler_email"),
    path("exportar/", views.exportar_solicitacoes, name="exportar"),
    # Tela única do registro: o formulário. Não existe mais rota de detalhe.
    path("<int:pk>/editar/", views.editar_solicitacao, name="editar"),
    # Transições de workflow — somente POST.
    path("<int:pk>/enviar/", views.enviar_solicitacao, name="enviar"),
    path("<int:pk>/excluir/", views.excluir_solicitacao, name="excluir"),
    # Anexos da solicitação.
    path("<int:pk>/anexos/adicionar/", views.adicionar_anexo, name="anexo_adicionar"),
    path(
        "<int:pk>/anexos/<int:anexo_pk>/baixar/",
        views.baixar_anexo,
        name="anexo_baixar",
    ),
    path(
        "<int:pk>/anexos/<int:anexo_pk>/excluir/",
        views.excluir_anexo,
        name="anexo_excluir",
    ),
    path("<int:pk>/despachar/", views.despachar, name="despachar"),
    path("<int:pk>/concluir/", views.concluir_solicitacao, name="concluir"),
    path("<int:pk>/cancelar-evento/", views.cancelar_evento, name="cancelar_evento"),
    path("<int:pk>/transferir/", views.transferir_solicitacao, name="transferir"),
    # Rascunho novo com os mesmos dados, serviços e equipes (eventos recorrentes).
    path("<int:pk>/duplicar/", views.duplicar_solicitacao, name="duplicar"),
    # Viagem em Viagens a partir da solicitação deferida (quando não nasceu sozinha).
    path("<int:pk>/gerar-viagem/", views.gerar_viagem, name="gerar_viagem"),
    # Última movimentação do protocolo no eProtocolo (só leitura).
    path("<int:pk>/consultar-protocolo/", views.consultar_protocolo, name="consultar_protocolo"),
]
