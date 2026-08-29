"""Gestão de usuários (perfil administrador) e conta do próprio usuário."""

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import PasswordChangeView
from django.contrib.messages.views import SuccessMessageMixin
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse_lazy
from django.views.decorators.http import require_POST

from auditoria.models import LogAuditoria
from solicitacoes.permissions import eh_administrador

from .forms import PERFIS, UsuarioForm, perfil_do_usuario

User = get_user_model()

ITENS_POR_PAGINA = 20


def _exigir_administrador(request):
    if not eh_administrador(request.user):
        raise PermissionDenied


def _registrar_auditoria(usuario_acao, acao, alvo):
    LogAuditoria.objects.create(
        usuario=usuario_acao,
        acao=acao,
        descricao=f"usuário '{alvo.username}' (id {alvo.pk})",
    )


@login_required
def lista_usuarios(request):
    _exigir_administrador(request)
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

    pagina = Paginator(queryset.distinct(), ITENS_POR_PAGINA).get_page(
        request.GET.get("pagina")
    )
    linhas = [
        {"usuario": usuario, "perfil": perfil_do_usuario(usuario)} for usuario in pagina
    ]
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
        },
    )


@login_required
def editar_usuario(request, pk=None):
    _exigir_administrador(request)
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
        },
    )


@login_required
@require_POST
def alternar_ativo_usuario(request, pk):
    _exigir_administrador(request)
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


class AlterarSenhaView(SuccessMessageMixin, PasswordChangeView):
    template_name = "pages/auth/alterar_senha.html"
    success_url = reverse_lazy("dashboard:index")
    success_message = "Senha alterada com sucesso."
