from django.urls import path

from . import importacao_views, views

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
    path("lotes/virada-de-exercicio/", views.virada_exercicio, name="virada_exercicio"),
    path("contratos/<int:pk>/relatorio/", views.relatorio_contrato, name="relatorio_contrato"),
    path("solicitacoes/", views.lista_solicitacoes, name="solicitacoes"),
    path("solicitacoes/exportar/", views.exportar_solicitacoes, name="exportar"),
    path("solicitacoes/nova/", views.nova_solicitacao, name="nova"),
    # "Preencher com um e-mail" da tela nova: lê e sugere, não grava (POST, JSON).
    path("solicitacoes/nova/ler-email/", views.ler_email, name="ler_email"),
    path("solicitacoes/nova/ordem-de-servico/", views.nova_os_embutido, name="nova_os_embutido"),
    path("solicitacoes/nova/ordem-de-servico/folha/", views.nova_os_folha, name="nova_os_folha"),
    # "Duplicar": a nova solicitação com o evento copiado, pedindo só a data.
    path("solicitacoes/<int:pk>/duplicar/", views.duplicar_solicitacao, name="duplicar"),
    # Local e responsável já usados no município (JSON): a tela sugere, o clique preenche.
    path("solicitacoes/locais-de-entrega/", views.locais_entrega, name="locais_entrega"),
    path("solicitacoes/<int:pk>/editar/", views.editar_solicitacao, name="editar"),
    path("solicitacoes/<int:pk>/nota/", views.etapa_nota, name="etapa_nota"),
    path("solicitacoes/<int:pk>/protocolo/", views.etapa_protocolo, name="etapa_protocolo"),
    path("solicitacoes/<int:pk>/andamento/", views.registrar_andamento, name="andamento"),
    path("solicitacoes/<int:pk>/entrega/", views.registrar_entrega, name="entrega"),
    path("ocorrencias/<int:pk>/arquivo/", views.ocorrencia_arquivo, name="ocorrencia_arquivo"),
    path("solicitacoes/<int:pk>/ordem-de-servico.pdf", views.ordem_servico, name="ordem_servico"),
    path("solicitacoes/<int:pk>/ordem-de-servico/previa/", views.ordem_servico_previa, name="ordem_servico_previa"),
    # E-mail ao fornecedor: mostra o e-mail pronto e só envia com a confirmação (POST).
    path("solicitacoes/<int:pk>/enviar-os/", views.enviar_os, name="enviar_os"),
    path("solicitacoes/<int:pk>/enviar-ob/", views.enviar_ob, name="enviar_ob"),
    path("solicitacoes/<int:pk>/ordem-bancaria/", views.ordem_bancaria_arquivo, name="ordem_bancaria_arquivo"),
    path("solicitacoes/<int:pk>/ordem-bancaria/anexar/", views.anexar_ob, name="anexar_ob"),
    path("solicitacoes/<int:pk>/oficio.pdf", views.oficio, name="oficio"),
    path("solicitacoes/<int:pk>/certifico.pdf", views.certifico, name="certifico"),
    # A via assinada da OS, do ofício ou do certifico (os, oficio, certifico); as vias guardadas.
    path("solicitacoes/<int:pk>/<str:documento>/assinado/", views.anexar_assinado, name="anexar_assinado"),
    path("vias/<uuid:pk>/", views.via_arquivo, name="via_arquivo"),
    path("solicitacoes/<int:pk>/protocolo/<str:parte>.pdf", views.pacote_parte, name="pacote_parte"),
    path("aditivos/<int:pk>/arquivo/", views.aditivo_arquivo, name="aditivo_arquivo"),
    path("solicitacoes/<int:pk>/nota-fiscal/", views.nota_fiscal, name="nota_fiscal"),
    path("solicitacoes/<int:pk>/nota-fiscal/anexar/", views.anexar_nota, name="anexar_nota"),
    path("solicitacoes/<int:pk>/vincular/", views.vincular_pagamento, name="vincular_pagamento"),
    # "Importar processo de pagamento": o PDF do eProtocolo preenche protocolo, nota e atesto.
    path("solicitacoes/importar-processo/", importacao_views.importar_processo, name="importar_processo"),
    path(
        "solicitacoes/importar-processo/<str:token>/",
        importacao_views.importacao_processo,
        name="importacao_processo",
    ),
    path(
        "solicitacoes/importar-processo/<str:token>/aplicar/",
        importacao_views.aplicar_importacao_processo,
        name="aplicar_importacao_processo",
    ),
    path(
        "solicitacoes/importar-processo/<str:token>/descartar/",
        importacao_views.descartar_importacao_processo,
        name="descartar_importacao_processo",
    ),
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
    path("solicitacoes/<int:pk>/excluir/", views.excluir_solicitacao, name="excluir"),
    path("solicitacoes/<int:pk>/baixar/", views.baixar_arquivos, name="baixar_arquivos"),
    path("solicitacoes/<int:pk>/reabrir/", views.reabrir_solicitacao, name="reabrir"),
    path(
        "solicitacoes/<int:pk>/reativar/",
        views.reativar_solicitacao,
        name="reativar",
    ),
]
