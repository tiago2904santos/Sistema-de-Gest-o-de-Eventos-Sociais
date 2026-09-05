from django.apps import AppConfig


class PublicacoesConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "publicacoes"
    verbose_name = "Publicações (ASCOM)"

    def ready(self):
        from accounts.modulos import registrar_modulo

        from .permissions import CODIGO_MODULO

        registrar_modulo(
            "publicacoes",
            nome="Publicações",
            descricao=(
                "Relatório de publicações da ASCOM: pautas recebidas, "
                "redação, revisão e publicação no site da PCPR e na AEN."
            ),
            icone="document",
            codigo=CODIGO_MODULO,
            entrada="publicacoes:painel",
            namespaces=["publicacoes"],
            ordem=40,
            itens=[
                {
                    "rotulo": "Painel",
                    "icone": "home",
                    "url": "publicacoes:painel",
                    "url_names": ("painel",),
                },
                {
                    "rotulo": "Publicações",
                    "icone": "document",
                    "url": "publicacoes:lista",
                    "url_names": ("lista", "nova", "detalhe", "editar", "exportar"),
                },
                {
                    "rotulo": "Cadastros",
                    "icone": "checklist",
                    "url": "publicacoes:cadastros",
                    "url_names": (
                        "cadastros", "cadastro_lista", "cadastro_novo",
                        "cadastro_editar", "cadastro_alternar",
                    ),
                    "somente_admin": True,
                },
            ],
        )
