from django.apps import AppConfig


class ViagensCadastrosConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "viagens_cadastros"
    verbose_name = "Viagens — cadastros"

    def ready(self):
        from accounts.modulos import registrar_modulo

        from .permissions import CODIGO_MODULO, eh_gestor_viagens

        registrar_modulo(
            "viagens",
            nome="Viagens",
            descricao=(
                "Domínio de viagens: roteiros com cálculo de diárias e os "
                "cadastros que os sustentam — servidores, viaturas e vigências."
            ),
            icone="volante",
            codigo=CODIGO_MODULO,
            entrada="viagens_roteiros:lista",
            # O módulo cobre os dois apps: o middleware protege ambos
            # os namespaces, e a navegação abaixo mistura as telas dos dois.
            namespaces=["viagens_cadastros", "viagens_roteiros", "viagens_oficios", "viagens_termos", "viagens_prestacoes"],
            ordem=40,
            itens=[
                {"rotulo": "Prestações", "icone": "checklist", "url": "viagens_prestacoes:index"},
                # Ofícios e Justificativas dividem o namespace: o nome da rota
                # decide qual item fica aceso.
                {"rotulo": "Ofícios", "icone": "file-text", "url": "viagens_oficios:lista",
                 "url_names": ("lista", "novo", "criar", "editar", "detalhe", "acao", "gerar", "termos_lote", "termo",
                               "catalogo", "catalogo_novo", "catalogo_editar", "numeracao",
                               "assinatura_artefato", "preview_artefato")},
                {"rotulo": "Justificativas", "icone": "document", "url": "viagens_oficios:justificativas",
                 "url_names": ("justificativas", "justificativa_excluir", "justificativas_buscar_oficios")},
                {"rotulo": "Termos", "icone": "file-text", "url": "viagens_termos:lista"},
                {
                    "rotulo": "Roteiros",
                    "icone": "map-pin",
                    "url": "viagens_roteiros:lista",
                },
                # Servidores, viaturas e diárias moram DENTRO de Cadastros:
                # o item abre direto em Servidores e fica aceso em todo o
                # namespace; a trilha lateral troca de tabela.
                {
                    "rotulo": "Cadastros",
                    "icone": "checklist",
                    "url": "viagens_cadastros:lista",
                    "url_args": ("servidores",),
                },
                # Dados institucionais e assinaturas dos documentos: a tela é
                # restrita ao gestor, então o item só aparece para ele.
                {
                    "rotulo": "Configurações",
                    "icone": "settings",
                    "url": "viagens_oficios:institucional",
                    "url_names": ("institucional",),
                    "visivel_para": eh_gestor_viagens,
                },
            ],
        )
