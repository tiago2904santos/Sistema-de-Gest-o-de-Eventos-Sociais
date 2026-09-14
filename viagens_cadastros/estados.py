"""Tela de Estados sobre a base compartilhada, sem mudar esquema ou permissões."""
from django import forms
from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.db.models import ProtectedError, RestrictedError
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.http import urlencode
from django.views.decorators.http import require_http_methods

from cadastros.models import Estado
from auditoria.models import LogAuditoria
from .permissions import acesso_ao_modulo
from .views import _campo_para_template, _registrar_auditoria, _texto_busca


class EstadoForm(forms.ModelForm):
    class Meta:
        model = Estado
        fields = ["nome", "sigla", "codigo_ibge"]
        labels = {"codigo_ibge": "Codigo ibge"}


def _permitido(usuario, acao):
    # Mesma barreira da administração Django já disponível para esta base.
    return usuario.is_active and usuario.is_staff and usuario.has_perm(f"cadastros.{acao}_estado")


@acesso_ao_modulo
@require_http_methods(["GET", "POST"])
def lista(request):
    form = EstadoForm(request.POST if request.method == "POST" else None)
    if request.method == "POST":
        if not _permitido(request.user, "add"):
            raise PermissionDenied
        if form.is_valid():
            estado = form.save()
            _registrar_auditoria(request.user, "VIAGENS_CADASTRO_CRIADO", estado)
            messages.success(request, "Estado criado com sucesso.")
            return redirect("viagens_cadastros:estados")
    termo = request.GET.get("q", "").strip()
    estados = Estado.objects.order_by("nome")
    if termo:
        busca = _texto_busca(termo)
        ids = [e.pk for e in estados if busca in _texto_busca(e.nome) or busca in _texto_busca(e.sigla)]
        estados = estados.filter(pk__in=ids)
    pagina = Paginator(estados, 15).get_page(request.GET.get("page"))
    return render(request, "pages/viagens_cadastros/estados/lista.html", {
        "form": form, "nome": _campo_para_template(form, "nome"),
        "sigla": _campo_para_template(form, "sigla"),
        "codigo_ibge": _campo_para_template(form, "codigo_ibge"),
        "termo": termo, "pagina": pagina,
        "querystring": urlencode({"q": termo}) if termo else "",
        "paginas_visiveis": list(pagina.paginator.get_elided_page_range(pagina.number, on_each_side=1, on_ends=1)),
        "elipse": pagina.paginator.ELLIPSIS,
        "pode_criar": _permitido(request.user, "add"),
        "pode_editar": _permitido(request.user, "change"),
        "pode_excluir": _permitido(request.user, "delete"),
    })


@acesso_ao_modulo
@require_http_methods(["GET", "POST"])
def editar(request, pk):
    if not _permitido(request.user, "change"):
        raise PermissionDenied
    estado = get_object_or_404(Estado, pk=pk)
    if request.method == "POST":
        form = EstadoForm(request.POST, instance=estado)
        if form.is_valid():
            form.save()
            _registrar_auditoria(request.user, "VIAGENS_CADASTRO_ATUALIZADO", estado)
            messages.success(request, "Estado atualizado com sucesso.")
        else:
            messages.error(request, "Não foi possível salvar o estado. Verifique os dados informados.")
    return redirect("viagens_cadastros:estados")


@acesso_ao_modulo
@require_http_methods(["GET", "POST"])
def excluir(request, pk):
    if not _permitido(request.user, "delete"):
        raise PermissionDenied
    estado = get_object_or_404(Estado, pk=pk)
    if request.method == "POST":
        descricao = f"estado '{estado}' (id {estado.pk})"
        try:
            estado.delete()
        except (ProtectedError, RestrictedError):
            messages.error(request, "Não foi possível excluir este cadastro porque ele está vinculado a outros registros.")
        else:
            LogAuditoria.objects.create(usuario=request.user, acao="VIAGENS_CADASTRO_EXCLUIDO", descricao=descricao)
            messages.success(request, "Estado excluído com sucesso.")
        return redirect("viagens_cadastros:estados")
    return render(request, "pages/viagens_cadastros/estados/confirmar_exclusao.html", {
        "estado": estado, "url_voltar": reverse("viagens_cadastros:estados"),
    })
