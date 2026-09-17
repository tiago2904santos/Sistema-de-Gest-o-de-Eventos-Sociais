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
            namespaces=["viagens_cadastros", "viagens_roteiros", "viagens_oficios", "viagens_termos", "viagens_prestacoes",
                        "viagens_viagem", "viagens_ordens", "viagens_planos"],
            ordem=40,
            itens=[
                # A viagem agrupa os documentos de um deslocamento (o "evento" do GV).
                {"rotulo": "Viagens", "icone": "volante", "url": "viagens_viagem:lista"},
                {"rotulo": "Prestações", "icone": "checklist", "url": "viagens_prestacoes:index"},
                # Ofícios e Justificativas dividem o namespace: o nome da rota
                # decide qual item fica aceso.
                {"rotulo": "Ofícios", "icone": "file-text", "url": "viagens_oficios:lista",
                 "url_names": ("lista", "novo", "criar", "editar", "visualizar", "visualizar_termo", "detalhe", "acao", "baixar", "gerar", "termos_lote", "termo",
                               "catalogo", "catalogo_novo", "catalogo_editar", "numeracao",
                               "assinatura_artefato", "preview_artefato")},
                {"rotulo": "Justificativas", "icone": "document", "url": "viagens_oficios:justificativas",
                 "url_names": ("justificativas", "justificativa_nova", "justificativa_editar", "justificativa_excluir")},
                {"rotulo": "Termos", "icone": "file-text", "url": "viagens_termos:lista"},
                {
                    "rotulo": "Roteiros",
                    "icone": "map-pin",
                    "url": "viagens_roteiros:lista",
                },
                {"rotulo": "Planos de trabalho", "icone": "clipboard", "url": "viagens_planos:lista"},
                {"rotulo": "Ordens de serviço", "icone": "gavel", "url": "viagens_ordens:lista"},
                # Servidores, viaturas e diárias moram DENTRO de Cadastros:
                # o item abre direto em Servidores e fica aceso em todo o
                # namespace; a trilha lateral troca de tabela.
                {
                    "rotulo": "Cadastros",
                    "icone": "checklist",
                    "url": "viagens_cadastros:lista",
                    "url_args": ("servidores",),
                    # Os catálogos de modelos moram no mesmo namespace, mas
                    # acendem o item "Modelos".
                    "slugs_fora": ("motivos-oficio", "modelos-justificativa", "modelos-texto-rt"),
                    # Gaveta ao passar o mouse: as seis tabelas da trilha.
                    "subitens": [
                        {"rotulo": "Servidores", "icone": "users", "url": "viagens_cadastros:lista", "url_args": ("servidores",)},
                        {"rotulo": "Viaturas", "icone": "truck", "url": "viagens_cadastros:lista", "url_args": ("viaturas",)},
                        {"rotulo": "Unidades", "icone": "landmark", "url": "viagens_cadastros:lista", "url_args": ("unidades",)},
                        {"rotulo": "Cargos", "icone": "shield", "url": "viagens_cadastros:lista", "url_args": ("cargos",)},
                        {"rotulo": "Combustíveis", "icone": "activity", "url": "viagens_cadastros:lista", "url_args": ("combustiveis",)},
                        {"rotulo": "Diárias", "icone": "chart", "url": "viagens_cadastros:diarias"},
                        {"rotulo": "Tipos de viagem", "icone": "map-pin", "url": "viagens_cadastros:lista", "url_args": ("tipos-viagem",)},
                        {"rotulo": "Programas", "icone": "landmark", "url": "viagens_cadastros:lista", "url_args": ("programas",)},
                        {"rotulo": "Horários", "icone": "clock", "url": "viagens_cadastros:lista", "url_args": ("horarios",)},
                        {"rotulo": "Atividades do plano", "icone": "checklist", "url": "viagens_cadastros:lista", "url_args": ("atividades-pt",)},
                        {"rotulo": "Presets", "icone": "clipboard", "url": "viagens_cadastros:lista", "url_args": ("presets-pt",)},
                    ],
                },
                # Modelos de texto: catálogos no padrão dos cadastros, com a
                # gaveta listando cada um.
                {
                    "rotulo": "Modelos",
                    "icone": "document",
                    "url": "viagens_cadastros:lista",
                    "url_args": ("motivos-oficio",),
                    "slugs": ("motivos-oficio", "modelos-justificativa", "modelos-texto-rt"),
                    "subitens": [
                        {"rotulo": "Motivos de ofício", "icone": "document", "url": "viagens_cadastros:lista", "url_args": ("motivos-oficio",)},
                        {"rotulo": "Modelos de justificativa", "icone": "document", "url": "viagens_cadastros:lista", "url_args": ("modelos-justificativa",)},
                        {"rotulo": "Modelos de texto do RT", "icone": "document", "url": "viagens_cadastros:lista", "url_args": ("modelos-texto-rt",)},
                    ],
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
