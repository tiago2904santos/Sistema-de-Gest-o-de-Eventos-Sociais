from django.apps import AppConfig


class AgendaConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "agenda"
    verbose_name = "Agenda"

    def ready(self):
        from accounts.modulos import registrar_modulo

        # Aberta a todo usuário autenticado (sem `codigo`): o que cada pessoa
        # enxerga dentro dela é decidido fonte a fonte, pela permissão do
        # módulo de origem — ver `agenda.fontes`. Restringir a agenda inteira
        # a um módulo deixaria de fora quem só tem Solicitações, que é o
        # núcleo do sistema.
        registrar_modulo(
            "agenda",
            nome="Agenda",
            descricao=(
                "Viagens, eventos, coffee break e demandas num calendário só, "
                "com o que você tem acesso."
            ),
            icone="calendar",
            entrada="agenda:painel",
            namespaces=["agenda"],
            ordem=5,
            itens=[{"rotulo": "Agenda", "icone": "calendar", "url": "agenda:painel"}],
        )
