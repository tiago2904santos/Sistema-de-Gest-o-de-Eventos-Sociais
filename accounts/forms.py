"""Formulários de gestão de usuários e perfis de acesso."""

from django import forms
from django.contrib.auth import get_user_model, password_validation
from django.contrib.auth.models import Group
from django.core.exceptions import ValidationError

from solicitacoes.permissions import GRUPOS_PADRAO

User = get_user_model()

PERFIS = [
    ("SOLICITANTE", "Solicitante"),
    ("ANALISTA", "Analista"),
    ("GESTOR_DG", "Gestor DG"),
    ("ADMINISTRADOR", "Administrador"),
]

ROTULOS_PERFIS = dict(PERFIS)


def perfil_do_usuario(usuario):
    """Nome do perfil (grupo padrão) do usuário, para exibição."""
    if usuario.is_superuser:
        return "Superusuário"
    grupo = usuario.groups.filter(name__in=GRUPOS_PADRAO).first()
    return ROTULOS_PERFIS.get(grupo.name, grupo.name) if grupo else "—"


class UsuarioForm(forms.ModelForm):
    perfil = forms.ChoiceField(choices=PERFIS, label="Perfil de acesso")
    senha = forms.CharField(required=False, label="Senha")
    confirmacao_senha = forms.CharField(required=False, label="Confirmação da senha")

    class Meta:
        model = User
        fields = ["first_name", "last_name", "username", "email"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["first_name"].label = "Nome"
        self.fields["first_name"].required = True
        self.fields["last_name"].label = "Sobrenome"
        self.fields["username"].label = "Usuário"
        self.fields["email"].label = "E-mail institucional"
        if self.instance.pk:
            grupo = self.instance.groups.filter(name__in=GRUPOS_PADRAO).first()
            if grupo:
                self.initial.setdefault("perfil", grupo.name)

    def clean(self):
        dados = super().clean()
        criacao = not self.instance.pk
        senha = dados.get("senha") or ""
        confirmacao = dados.get("confirmacao_senha") or ""
        if criacao and not senha:
            self.add_error("senha", "Defina a senha inicial do usuário.")
        if senha:
            if senha != confirmacao:
                self.add_error("confirmacao_senha", "As senhas não conferem.")
            else:
                try:
                    password_validation.validate_password(senha, self.instance)
                except ValidationError as erro:
                    self.add_error("senha", erro)
        return dados

    @property
    def senha_definida(self):
        return bool(self.cleaned_data.get("senha"))

    def save(self):
        usuario = super().save(commit=False)
        if self.cleaned_data.get("senha"):
            usuario.set_password(self.cleaned_data["senha"])
        usuario.save()
        # Perfil único dentre os grupos padrão (outros grupos são preservados).
        usuario.groups.remove(*usuario.groups.filter(name__in=GRUPOS_PADRAO))
        grupo, _ = Group.objects.get_or_create(name=self.cleaned_data["perfil"])
        usuario.groups.add(grupo)
        return usuario
