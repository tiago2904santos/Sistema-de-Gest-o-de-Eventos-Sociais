"""Autorização por módulo (Setor ↔ Modulo).

Cada app de módulo registra seu namespace de URL no `AppConfig.ready()`:

    from accounts.modulos import registrar_namespace
    registrar_namespace("coffee_break", "ASCOM_COFFEE_BREAK")

Com isso o middleware bloqueia no backend qualquer URL do namespace para
usuários sem o módulo, e as views ainda podem usar o decorator
`modulo_requerido` como segunda camada explícita.
"""

from functools import wraps

from django.contrib.auth.views import redirect_to_login
from django.core.exceptions import PermissionDenied
from django.urls import resolve

# Namespace de URL -> código do módulo exigido. Preenchido pelos apps.
NAMESPACES_MODULOS = {}

# Catálogo dos módulos do portal: slug -> descritor com nome, ícone, itens de
# navegação e ponto de entrada. Alimenta a tela inicial (hub) e a navbar
# contextual — dentro de um módulo, só a navegação daquele módulo aparece.
MODULOS_PORTAL = {}


def registrar_namespace(namespace, codigo_modulo):
    NAMESPACES_MODULOS[namespace] = codigo_modulo


def registrar_modulo(
    slug,
    *,
    nome,
    icone,
    entrada,
    namespaces,
    itens,
    descricao="",
    codigo=None,
    ordem=100,
):
    """Cataloga um módulo no portal.

    - ``codigo`` None = módulo aberto a todo usuário autenticado; com código,
      os ``namespaces`` são registrados no middleware de autorização.
    - ``itens``: navegação do módulo — dicts com ``rotulo``, ``url`` (nome da
      rota), ``icone`` e opcionalmente ``url_args``, ``url_names`` (nomes de
      rota que marcam o item como ativo) e ``somente_admin``.
    """
    if codigo:
        for namespace in namespaces:
            registrar_namespace(namespace, codigo)
    MODULOS_PORTAL[slug] = {
        "slug": slug,
        "nome": nome,
        "descricao": descricao,
        "icone": icone,
        "codigo": codigo,
        "entrada": entrada,
        "namespaces": list(namespaces),
        "itens": list(itens),
        "ordem": ordem,
    }


def modulos_do_portal(usuario):
    """Descritores dos módulos que o usuário pode acessar, em ordem."""
    visiveis = []
    for modulo in sorted(MODULOS_PORTAL.values(), key=lambda m: m["ordem"]):
        if modulo["codigo"] and not usuario_tem_modulo(usuario, modulo["codigo"]):
            continue
        visiveis.append(modulo)
    return visiveis


def modulo_do_namespace(namespace):
    """Descritor do módulo dono do namespace atual (ou None fora de módulo)."""
    if not namespace:
        return None
    for modulo in MODULOS_PORTAL.values():
        if namespace in modulo["namespaces"]:
            return modulo
    return None


def usuario_tem_modulo(usuario, codigo):
    """Usuário autenticado com algum setor autorizado no módulo ativo."""
    if not usuario or not usuario.is_authenticated:
        return False
    if usuario.is_superuser:
        return True
    # Import tardio para evitar ciclo com accounts.models.
    from .models import Modulo

    return Modulo.objects.filter(
        codigo=codigo,
        ativo=True,
        setores__ativo=True,
        setores__usuarios=usuario,
    ).exists()


def codigos_modulos_do_usuario(usuario):
    """Códigos de módulos que o usuário enxerga (navegação dinâmica)."""
    if not usuario or not usuario.is_authenticated:
        return set()
    from .models import Modulo

    if usuario.is_superuser:
        return set(Modulo.objects.filter(ativo=True).values_list("codigo", flat=True))
    return set(
        Modulo.objects.filter(
            ativo=True, setores__ativo=True, setores__usuarios=usuario
        ).values_list("codigo", flat=True)
    )


def modulo_requerido(codigo):
    """Decorator de view: exige login e o módulo indicado."""

    def decorator(view):
        @wraps(view)
        def wrapper(request, *args, **kwargs):
            if not request.user.is_authenticated:
                return redirect_to_login(request.get_full_path())
            if not usuario_tem_modulo(request.user, codigo):
                raise PermissionDenied
            return view(request, *args, **kwargs)

        return wrapper

    return decorator


class AutorizacaoPorModuloMiddleware:
    """Bloqueia no backend todo o namespace de um módulo restrito."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        codigo = self._codigo_exigido(request)
        if codigo:
            usuario = getattr(request, "user", None)
            if not usuario or not usuario.is_authenticated:
                return redirect_to_login(request.get_full_path())
            if not usuario_tem_modulo(usuario, codigo):
                raise PermissionDenied
        return self.get_response(request)

    def _codigo_exigido(self, request):
        try:
            rota = resolve(request.path_info)
        except Exception:
            return None
        return NAMESPACES_MODULOS.get(rota.namespace)
