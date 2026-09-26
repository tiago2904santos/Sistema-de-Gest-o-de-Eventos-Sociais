from django.apps import AppConfig


class CoffeeBreakConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "coffee_break"
    verbose_name = "Coffee Break (ASCOM)"

    def ready(self):
        from accounts.modulos import registrar_modulo

        from .editor import registrar as registrar_editor
        from .permissions import CODIGO_MODULO

        # A OS no editor de documentos de Viagens.
        registrar_editor()

        # O ofício e a OS do Coffee Break saem da mesma numeração dos de
        # Viagens: os números daqui contam como ocupados lá.
        from core.numeracao import NAMESPACE_OFICIO, NAMESPACE_ORDEM_SERVICO, registrar_numeros_externos

        from . import services

        registrar_numeros_externos(NAMESPACE_OFICIO, services.sequencias_oficio_no_ano)
        registrar_numeros_externos(NAMESPACE_ORDEM_SERVICO, services.sequencias_os_no_ano)

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
                        "etapa_nota", "etapa_protocolo",
                        "cancelar", "reativar",
                    ),
                },
                {
                    "rotulo": "Certidões",
                    "icone": "check-circle",
                    "url": "coffee_break:certidoes",
                    "url_names": ("certidoes",),
                },
                {
                    "rotulo": "Cadastros",
                    "icone": "checklist",
                    "url": "coffee_break:cadastros",
                    "url_names": (
                        "cadastros", "cadastro_lista", "cadastro_novo", "cadastro_editar",
                    ),
                    "somente_admin": True,
                },
                # Textos-base da OS, do ofício e do certifico (m057).
                {
                    "rotulo": "Textos dos documentos",
                    "icone": "document",
                    "url": "documentos:modelos_modulo",
                    "url_args": ("coffee_break",),
                    "somente_admin": True,
                },
            ],
        )
