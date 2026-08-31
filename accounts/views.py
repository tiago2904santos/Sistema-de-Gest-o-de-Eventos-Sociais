"""Gestão de usuários (administrador ou gestor DG) e conta do próprio usuário."""

from datetime import timedelta

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import LoginView, PasswordChangeView
from django.contrib.messages.views import SuccessMessageMixin
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse_lazy
from django.utils import timezone
from django.utils.http import urlencode
from django.views.decorators.http import require_POST

from auditoria.models import LogAuditoria
from solicitacoes.permissions import pode_gerenciar_usuarios

from .forms import PERFIS, AcessoForm, UsuarioForm, perfil_do_usuario

User = get_user_model()

ITENS_POR_PAGINA = 20


def _exigir_gestao_de_usuarios(request):
    """Gestão de usuários: administrador ou gestor DG."""
    if not pode_gerenciar_usuarios(request.user):
        raise PermissionDenied


def _registrar_auditoria(usuario_acao, acao, alvo):
    LogAuditoria.objects.create(
        usuario=usuario_acao,
        acao=acao,
        descricao=f"usuário '{alvo.username}' (id {alvo.pk})",
    )


def _iniciais(usuario):
    letras = ""
    for parte in [usuario.first_name, usuario.last_name]:
        primeira = next((ch for ch in parte if ch.isalpha()), "")
        letras += primeira
    return (letras or usuario.username[:2]).upper()[:2]


def _ultimo_acesso(usuario):
    if not usuario.last_login:
        return "—"
    momento = timezone.localtime(usuario.last_login)
    hoje = timezone.localdate()
    if momento.date() == hoje:
        return f"Hoje às {momento:%H:%M}"
    if momento.date() == hoje - timedelta(days=1):
        return f"Ontem às {momento:%H:%M}"
    return f"{momento:%d/%m/%Y} às {momento:%H:%M}"


def _perfil_slug(usuario):
    """Chave visual do selo de perfil (superusuário tem selo próprio)."""
    if usuario.is_superuser:
        return "super"
    grupo = usuario.groups.filter(name__in=["SOLICITANTE", "GESTOR_DG", "ADMINISTRADOR"]).first()
    return grupo.name.lower() if grupo else ""


@login_required
def lista_usuarios(request):
    _exigir_gestao_de_usuarios(request)
    queryset = User.objects.order_by("first_name", "username")

    termo = request.GET.get("q", "").strip()
    perfil = request.GET.get("perfil", "")
    situacao = request.GET.get("situacao", "")
    if termo:
        queryset = queryset.filter(
            Q(username__icontains=termo)
            | Q(first_name__icontains=termo)
            | Q(last_name__icontains=termo)
            | Q(email__icontains=termo)
        )
    if perfil:
        queryset = queryset.filter(groups__name=perfil)
    if situacao == "ativos":
        queryset = queryset.filter(is_active=True)
    elif situacao == "inativos":
        queryset = queryset.filter(is_active=False)

    paginator = Paginator(queryset.distinct(), ITENS_POR_PAGINA)
    pagina = paginator.get_page(request.GET.get("pagina"))
    linhas = [
        {
            "usuario": usuario,
            "perfil": perfil_do_usuario(usuario),
            "perfil_slug": _perfil_slug(usuario),
            "iniciais": _iniciais(usuario),
            "ultimo_acesso": _ultimo_acesso(usuario),
        }
        for usuario in pagina
    ]
    parametros = {}
    if termo:
        parametros["q"] = termo
    if perfil:
        parametros["perfil"] = perfil
    if situacao:
        parametros["situacao"] = situacao
    return render(
        request,
        "pages/accounts/lista.html",
        {
            "pagina": pagina,
            "linhas": linhas,
            "termo": termo,
            "perfil_filtro": perfil,
            "situacao_filtro": situacao,
            "opcoes_perfil": [{"valor": valor, "rotulo": rotulo} for valor, rotulo in PERFIS],
            "opcoes_situacao": [
                {"valor": "ativos", "rotulo": "Ativos"},
                {"valor": "inativos", "rotulo": "Inativos"},
            ],
            "querystring": urlencode(parametros),
            "paginas_visiveis": list(
                paginator.get_elided_page_range(pagina.number, on_each_side=2, on_ends=1)
            ),
            "elipse": paginator.ELLIPSIS,
        },
    )


@login_required
def editar_usuario(request, pk=None):
    _exigir_gestao_de_usuarios(request)
    instancia = get_object_or_404(User, pk=pk) if pk else None
    if request.method == "POST":
        form = UsuarioForm(request.POST, instance=instancia)
        if form.is_valid():
            usuario = form.save()
            if pk:
                _registrar_auditoria(request.user, "USUARIO_ATUALIZADO", usuario)
                if form.senha_definida:
                    _registrar_auditoria(request.user, "USUARIO_SENHA_REDEFINIDA", usuario)
                messages.success(request, f"Usuário '{usuario.username}' atualizado.")
            else:
                _registrar_auditoria(request.user, "USUARIO_CRIADO", usuario)
                messages.success(request, f"Usuário '{usuario.username}' criado com sucesso.")
            return redirect("accounts:usuarios_lista")
        messages.error(request, "Corrija os campos destacados para continuar.")
    else:
        form = UsuarioForm(instance=instancia)

    valores = {}
    for nome in ["first_name", "last_name", "username", "email", "perfil"]:
        valor = form[nome].value()
        valores[nome] = "" if valor is None else str(valor)

    return render(
        request,
        "pages/accounts/form.html",
        {
            "form": form,
            "instancia": instancia,
            "valores": valores,
            "erros": form.errors,
            "opcoes_perfil": [{"valor": valor, "rotulo": rotulo} for valor, rotulo in PERFIS],
            "titulo_pagina": (
                f"Editar usuário: {instancia.username}" if instancia else "Novo usuário"
            ),
            "breadcrumb": [
                {"label": "Usuários", "url": reverse_lazy("accounts:usuarios_lista")},
                {"label": "Editar usuário" if instancia else "Novo usuário"},
            ],
        },
    )


@login_required
@require_POST
def alternar_ativo_usuario(request, pk):
    _exigir_gestao_de_usuarios(request)
    usuario = get_object_or_404(User, pk=pk)
    if usuario == request.user:
        messages.error(request, "Você não pode inativar o seu próprio usuário.")
        return redirect("accounts:usuarios_lista")
    usuario.is_active = not usuario.is_active
    usuario.save(update_fields=["is_active"])
    _registrar_auditoria(
        request.user,
        "USUARIO_ATIVADO" if usuario.is_active else "USUARIO_INATIVADO",
        usuario,
    )
    messages.success(
        request,
        f"Usuário '{usuario.username}' {'ativado' if usuario.is_active else 'inativado'}.",
    )
    return redirect("accounts:usuarios_lista")


class AcessoView(LoginView):
    template_name = "pages/auth/login.html"
    authentication_form = AcessoForm
    redirect_authenticated_user = True

    def form_valid(self, form):
        resposta = super().form_valid(form)
        # Sem "mantenha-me conectado", a sessão morre com o navegador; com,
        # vale o prazo padrão do Django (duas semanas).
        if not form.cleaned_data.get("manter_conectado"):
            self.request.session.set_expiry(0)
        return resposta


class AlterarSenhaView(SuccessMessageMixin, PasswordChangeView):
    template_name = "pages/auth/alterar_senha.html"
    success_url = reverse_lazy("dashboard:index")
    success_message = "Senha alterada com sucesso."

    def get_context_data(self, **kwargs):
        contexto = super().get_context_data(**kwargs)
        contexto["troca_obrigatoria"] = self.request.user.deve_trocar_senha
        return contexto

    def form_valid(self, form):
        resposta = super().form_valid(form)
        if self.request.user.deve_trocar_senha:
            self.request.user.deve_trocar_senha = False
            self.request.user.save(update_fields=["deve_trocar_senha"])
        return resposta
