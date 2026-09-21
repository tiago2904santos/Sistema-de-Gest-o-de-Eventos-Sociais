from django.apps import AppConfig


class RelatoriosConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "relatorios"
    verbose_name = "Relatórios"

    def ready(self):
        from accounts.modulos import registrar_modulo

        # Como a agenda: aberto a todo usuário autenticado (sem `codigo`), e
        # cada seção só aparece para quem tem o módulo de origem — ver
        # `relatorios.consolidacao`.
        registrar_modulo(
            "relatorios",
            nome="Relatório",
            descricao=(
                "Palestras, PCPR na Comunidade, eventos, coffee break, "
                "publicações, imprensa e viagens num relatório só."
            ),
            icone="chart",
            entrada="relatorios:painel",
            namespaces=["relatorios"],
            ordem=6,
            itens=[{"rotulo": "Relatório", "icone": "chart", "url": "relatorios:painel"}],
        )
