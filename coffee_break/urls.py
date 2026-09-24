from django.urls import path

from . import views

app_name = "coffee_break"

urlpatterns = [
    path("", views.painel, name="painel"),
    path("cadastros/", views.cadastros, name="cadastros"),
    path("cadastros/importar-planilha/", views.importar_planilha, name="importar_planilha"),
    path("cadastros/<str:tipo>/", views.lista_cadastro, name="cadastro_lista"),
    path(
        "cadastros/<str:tipo>/novo/",
        views.editar_cadastro,
        name="cadastro_novo",
    ),
    path(
        "cadastros/<str:tipo>/<int:pk>/editar/",
        views.editar_cadastro,
        name="cadastro_editar",
    ),
    path(
        "cadastros/<str:tipo>/<int:pk>/excluir/",
        views.excluir_cadastro,
        name="cadastro_excluir",
    ),
    path("lotes/", views.lista_lotes, name="lotes"),
    path("lotes/<int:pk>/", views.detalhe_lote, name="lote_detalhe"),
    path("solicitacoes/", views.lista_solicitacoes, name="solicitacoes"),
    path("solicitacoes/exportar/", views.exportar_solicitacoes, name="exportar"),
    path("solicitacoes/nova/", views.nova_solicitacao, name="nova"),
    path("solicitacoes/nova/ordem-de-servico/", views.nova_os_embutido, name="nova_os_embutido"),
    path("solicitacoes/nova/ordem-de-servico/folha/", views.nova_os_folha, name="nova_os_folha"),
    path("solicitacoes/<int:pk>/editar/", views.editar_solicitacao, name="editar"),
    path("solicitacoes/<int:pk>/nota/", views.etapa_nota, name="etapa_nota"),
    path("solicitacoes/<int:pk>/protocolo/", views.etapa_protocolo, name="etapa_protocolo"),
    path("solicitacoes/<int:pk>/andamento/", views.registrar_andamento, name="andamento"),
    path("solicitacoes/<int:pk>/ordem-de-servico.pdf", views.ordem_servico, name="ordem_servico"),
    path("solicitacoes/<int:pk>/ordem-de-servico/previa/", views.ordem_servico_previa, name="ordem_servico_previa"),
    path("solicitacoes/<int:pk>/oficio.pdf", views.oficio, name="oficio"),
    path("solicitacoes/<int:pk>/certifico.pdf", views.certifico, name="certifico"),
    path("solicitacoes/<int:pk>/protocolo.pdf", views.pacote_protocolo, name="pacote_protocolo"),
    path("solicitacoes/<int:pk>/protocolo.zip", views.pacote_protocolo_zip, name="pacote_protocolo_zip"),
    path("solicitacoes/<int:pk>/nota-fiscal/", views.nota_fiscal, name="nota_fiscal"),
    path("solicitacoes/<int:pk>/nota-fiscal/anexar/", views.anexar_nota, name="anexar_nota"),
    path("certidoes/", views.lista_certidoes, name="certidoes"),
    path("certidoes/<int:pk>/arquivo/", views.certidao_arquivo, name="certidao_arquivo"),
    path("certidoes/<int:fornecedor_pk>/<str:tipo>/anexar/", views.anexar_certidao, name="anexar_certidao"),
    path("cadastros/contratos/anexar/", views.anexar_contrato, name="anexar_contrato"),
    path(
        "cadastros/contratos/<int:pk>/<str:campo>/",
        views.contrato_arquivo,
        name="contrato_arquivo",
    ),
    path(
        "solicitacoes/<int:pk>/certificado/",
        views.certificado_solicitacao,
        name="certificado",
    ),
    # Mudanças de estado — somente POST, com CSRF.
    path(
        "solicitacoes/<int:pk>/cancelar/",
        views.cancelar_solicitacao,
        name="cancelar",
    ),
    path(
        "solicitacoes/<int:pk>/reativar/",
        views.reativar_solicitacao,
        name="reativar",
    ),
]
