from django.apps import AppConfig


class AssistenteConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "assistente"
    verbose_name = "Assistente"

    def ready(self):
        from accounts.modulos import registrar_modulo
        from viagens_cadastros.permissions import CODIGO_MODULO

        # O catálogo se registra na importação; sem isto o assistente sobe
        # sem ferramenta nenhuma e responde "não reconheci" a tudo.
        from . import catalogo  # noqa: F401

        # Hoje todas as ferramentas são do domínio de viagens, então o
        # assistente vive sob o mesmo código de módulo: quem não enxerga
        # Viagens pelas telas também não abre o assistente. Quando entrar a
        # primeira ferramenta de outro módulo, isto vira código próprio e o
        # recorte passa a ser por ferramenta, que já é como a permissão
        # funciona lá dentro.
        registrar_modulo(
            "assistente",
            nome="Assistente",
            descricao=(
                "Consulte e prepare viagens conversando — o assistente usa as "
                "suas permissões e confirma antes de gravar."
            ),
            icone="send",
            codigo=CODIGO_MODULO,
            entrada="assistente:painel",
            namespaces=["assistente"],
            ordem=45,
            itens=[{"rotulo": "Assistente", "icone": "send", "url": "assistente:painel"}],
        )
