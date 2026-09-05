from django.apps import AppConfig


class AtendimentoImprensaConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "atendimento_imprensa"
    verbose_name = "Atendimento à Imprensa (ASCOM)"

    def ready(self):
        from accounts.modulos import registrar_modulo

        from .permissions import CODIGO_MODULO

        registrar_modulo(
            "atendimento_imprensa",
            nome="Atendimento à Imprensa",
            descricao=(
                "Relatório de atendimento à imprensa da ASCOM: pedidos dos "
                "jornalistas, fontes consultadas, prazos e respostas."
            ),
            icone="mail",
            codigo=CODIGO_MODULO,
            entrada="atendimento_imprensa:painel",
            namespaces=["atendimento_imprensa"],
            ordem=50,
            itens=[
                {
                    "rotulo": "Painel",
                    "icone": "home",
                    "url": "atendimento_imprensa:painel",
                    "url_names": ("painel",),
                },
                {
                    "rotulo": "Atendimentos",
                    "icone": "mail",
                    "url": "atendimento_imprensa:lista",
                    "url_names": ("lista", "novo", "detalhe", "editar", "exportar"),
                },
                {
                    "rotulo": "Cadastros",
                    "icone": "checklist",
                    "url": "atendimento_imprensa:cadastros",
                    "url_names": (
                        "cadastros", "cadastro_lista", "cadastro_novo",
                        "cadastro_editar", "cadastro_alternar",
                    ),
                    "somente_admin": True,
                },
            ],
        )
