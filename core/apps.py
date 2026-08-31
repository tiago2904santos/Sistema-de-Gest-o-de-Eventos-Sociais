from django.apps import AppConfig


class CoreConfig(AppConfig):
    name = 'core'

    def ready(self):
        from accounts.modulos import registrar_modulo

        # Módulo histórico do sistema: aberto a todo usuário autenticado.
        registrar_modulo(
            "eventos",
            nome="Eventos Sociais",
            descricao=(
                "Solicitações de eventos sociais, despacho da Diretoria-Geral "
                "e cadastros de apoio."
            ),
            icone="document",
            entrada="dashboard:index",
            namespaces=["dashboard", "solicitacoes", "cadastros"],
            ordem=10,
            itens=[
                {"rotulo": "Dashboard", "icone": "home", "url": "dashboard:index"},
                {
                    "rotulo": "Solicitações",
                    "icone": "document",
                    "url": "solicitacoes:lista",
                },
                {
                    "rotulo": "Cadastros",
                    "icone": "checklist",
                    "url": "cadastros:index",
                    "somente_admin": True,
                },
            ],
        )
