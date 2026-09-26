from django.apps import AppConfig


class DemandasEventosConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "demandas_eventos"
    verbose_name = "Palestras e Eventos da ASCOM"

    def ready(self):
        from django.db.models.signals import post_save

        from accounts.modulos import registrar_modulo

        from .encaminhamento import acompanhar_solicitacao
        from .permissions import CODIGO_MODULO

        # O que a DG faz na solicitação encaminhada volta ao histórico da palestra.
        post_save.connect(
            acompanhar_solicitacao,
            sender="solicitacoes.HistoricoSolicitacao",
            dispatch_uid="demandas_eventos_acompanhar_solicitacao",
        )

        # Cataloga o módulo no portal; o middleware protege o namespace.
        registrar_modulo(
            "demandas_eventos",
            nome="Palestras e Eventos",
            descricao=(
                "Palestras, PCPR na Comunidade e eventos da ASCOM, no desenho "
                "da planilha: pedidos, palestrantes, temas e respostas padrão."
            ),
            icone="users",
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
                    "rotulo": "Palestras",
                    "icone": "users",
                    "url": "demandas_eventos:lista",
                    "url_names": ("lista", "nova", "detalhe", "editar"),
                },
                {
                    "rotulo": "Cadastros",
                    "icone": "checklist",
                    "url": "demandas_eventos:cadastro_lista",
                    "url_args": ("palestrantes",),
                    "url_names": (
                        "cadastro_lista", "cadastro_novo", "cadastro_editar",
                    ),
                },
            ],
        )
