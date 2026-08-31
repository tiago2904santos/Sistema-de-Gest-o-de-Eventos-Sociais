from django.urls import reverse

from .modulos import (
    codigos_modulos_do_usuario,
    modulo_do_namespace,
    modulos_do_portal,
)

_VAZIO = {
    "modulos_usuario": set(),
    "modulos_portal": [],
    "modulo_ativo": None,
    "nav_itens": [],
}


def modulos(request):
    """Módulos do usuário: navegação dinâmica do portal e navbar contextual."""
    usuario = getattr(request, "user", None)
    if not usuario or not usuario.is_authenticated:
        return dict(_VAZIO)

    resolver = getattr(request, "resolver_match", None)
    namespace = resolver.namespace if resolver else ""
    ativo = modulo_do_namespace(namespace)

    nav_itens = []
    if ativo:
        # Import tardio: evita ciclo de import na carga dos apps.
        from solicitacoes.permissions import eh_administrador

        url_name = resolver.url_name if resolver else ""
        for item in ativo["itens"]:
            if item.get("somente_admin") and not eh_administrador(usuario):
                continue
            # Item ativo: mesmo namespace da rota do item e, quando o módulo
            # tem vários itens no mesmo namespace, o nome da rota decide.
            ns_item = item["url"].split(":")[0]
            url_names = item.get("url_names", ())
            nav_itens.append(
                {
                    "rotulo": item["rotulo"],
                    "icone": item["icone"],
                    "url": reverse(item["url"], args=item.get("url_args", ())),
                    "ativo": namespace == ns_item
                    and (not url_names or url_name in url_names),
                }
            )

    return {
        "modulos_usuario": codigos_modulos_do_usuario(usuario),
        "modulos_portal": modulos_do_portal(usuario),
        "modulo_ativo": ativo,
        "nav_itens": nav_itens,
    }
