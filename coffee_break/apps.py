from django.apps import AppConfig


class CoffeeBreakConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "coffee_break"
    verbose_name = "Coffee Break (ASCOM)"

    def ready(self):
        from accounts.modulos import registrar_modulo

        from .permissions import CODIGO_MODULO

        # Cataloga o módulo no portal; o middleware protege o namespace.
        registrar_modulo(
            "coffee_break",
            nome="Coffee Break",
            descricao=(
                "Controle dos lotes contratados de coffee break da ASCOM: "
                "saldo, solicitações e fluxo de pagamento."
            ),
            icone="coffee",
            codigo=CODIGO_MODULO,
            entrada="coffee_break:painel",
            namespaces=["coffee_break"],
            ordem=20,
            itens=[
                {
                    "rotulo": "Painel",
                    "icone": "home",
                    "url": "coffee_break:painel",
                    "url_names": ("painel",),
                },
                {
                    "rotulo": "Lotes",
                    "icone": "coffee",
                    "url": "coffee_break:lotes",
                    "url_names": ("lotes", "lote_detalhe"),
                },
                {
                    "rotulo": "Solicitações",
                    "icone": "document",
                    "url": "coffee_break:solicitacoes",
                    "url_names": (
                        "solicitacoes", "nova", "detalhe", "editar",
                        "cancelar", "reativar",
                    ),
                },
            ],
        )
