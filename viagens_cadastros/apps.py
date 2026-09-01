from django.apps import AppConfig


class ViagensCadastrosConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "viagens_cadastros"
    verbose_name = "Viagens — cadastros"

    def ready(self):
        from accounts.modulos import registrar_modulo

        from .permissions import CODIGO_MODULO

        registrar_modulo(
            "viagens",
            nome="Viagens",
            descricao=(
                "Cadastros do domínio de viagens: servidores, viaturas, "
                "unidades e a tabela de diárias vigente."
            ),
            icone="volante",
            codigo=CODIGO_MODULO,
            entrada="viagens_cadastros:index",
            namespaces=["viagens_cadastros"],
            ordem=40,
            itens=[
                {
                    "rotulo": "Cadastros",
                    "icone": "home",
                    "url": "viagens_cadastros:index",
                    "url_names": ("index",),
                },
                {
                    "rotulo": "Servidores",
                    "icone": "users",
                    "url": "viagens_cadastros:lista",
                    "url_args": ("servidores",),
                    "url_names": ("lista", "novo", "editar"),
                },
                {
                    "rotulo": "Viaturas",
                    "icone": "truck",
                    "url": "viagens_cadastros:lista",
                    "url_args": ("viaturas",),
                },
                {
                    "rotulo": "Diárias",
                    "icone": "chart",
                    "url": "viagens_cadastros:diarias",
                    "url_names": ("diarias", "diaria_nova", "diaria_editar"),
                },
            ],
        )
