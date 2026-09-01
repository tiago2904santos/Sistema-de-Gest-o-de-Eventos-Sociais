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
                "Domínio de viagens: roteiros com cálculo de diárias e os "
                "cadastros que os sustentam — servidores, viaturas e vigências."
            ),
            icone="volante",
            codigo=CODIGO_MODULO,
            entrada="viagens_roteiros:lista",
            # O módulo cobre os dois apps: o middleware protege ambos
            # os namespaces, e a navegação abaixo mistura as telas dos dois.
            namespaces=["viagens_cadastros", "viagens_roteiros"],
            ordem=40,
            itens=[
                {
                    "rotulo": "Roteiros",
                    "icone": "map-pin",
                    "url": "viagens_roteiros:lista",
                },
                # Servidores, viaturas e diárias moram DENTRO de Cadastros:
                # o hub em viagens_cadastros:index lista todos os grupos.
                {
                    "rotulo": "Cadastros",
                    "icone": "checklist",
                    "url": "viagens_cadastros:index",
                },
            ],
        )
