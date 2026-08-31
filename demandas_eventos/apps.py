from django.apps import AppConfig


class DemandasEventosConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "demandas_eventos"
    verbose_name = "Demandas de eventos da ASCOM"

    def ready(self):
        from accounts.modulos import registrar_modulo

        from .permissions import CODIGO_MODULO

        # Cataloga o módulo no portal; o middleware protege o namespace.
        registrar_modulo(
            "demandas_eventos",
            nome="Demandas ASCOM",
            descricao=(
                "Demandas de palestras e eventos da ASCOM: pedidos, "
                "palestrantes, temas e respostas padrão."
            ),
            icone="calendar",
            codigo=CODIGO_MODULO,
            entrada="demandas_eventos:dashboard",
            namespaces=["demandas_eventos"],
            ordem=30,
            itens=[
                {
                    "rotulo": "Dashboard",
                    "icone": "home",
                    "url": "demandas_eventos:dashboard",
                    "url_names": ("dashboard",),
                },
                {
                    "rotulo": "Demandas",
                    "icone": "document",
                    "url": "demandas_eventos:lista",
                    "url_names": ("lista", "nova", "detalhe", "editar"),
                },
                {
                    "rotulo": "Cadastros",
                    "icone": "checklist",
                    "url": "demandas_eventos:cadastro_lista",
                    "url_args": ("temas",),
                    "url_names": (
                        "cadastro_lista", "cadastro_novo", "cadastro_editar",
                    ),
                },
            ],
        )
