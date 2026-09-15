from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from core.retorno import voltar_para, next_valido
from urllib.parse import urlencode
from .models import ModeloTextoRelatorioTecnico
from .forms import ModeloTextoRelatorioTecnicoForm
from .services import excluir_modelo_texto
from .ui import render


def modelos_index(request):
    campos = dict(ModeloTextoRelatorioTecnico.CAMPO_CHOICES)
    campo = request.POST.get("quick_add_campo") or request.GET.get("campo") or ModeloTextoRelatorioTecnico.CAMPO_MOTIVO
    if campo not in campos:
        campo = ModeloTextoRelatorioTecnico.CAMPO_MOTIVO
    prefixo = f"modelo-{campo}" if request.POST.get("quick_add_campo") else None
    form = ModeloTextoRelatorioTecnicoForm(request.POST or None, prefix=prefixo, initial={"campo": campo})
    base = reverse("viagens_prestacoes:modelos_index")
    if request.method == "POST" and form.is_valid():
        modelo = form.save()
        messages.success(request, "Modelo de texto salvo.")
        return redirect(voltar_para(request, f"{base}?campo={modelo.campo}#grupo-{modelo.campo}"))
    modelos = ModeloTextoRelatorioTecnico.objects.filter(campo=campo)
    busca = request.GET.get("q") or ""
    if busca:
        modelos = modelos.filter(nome__icontains=busca)
    retorno = next_valido(request)
    abas = []
    for key,label in campos.items():
        parametros = {"campo": key}
        if busca: parametros["q"] = busca
        if retorno: parametros["next"] = retorno
        abas.append({"campo": key, "label": label, "url": f"{base}?{urlencode(parametros)}", "ativa": key==campo})
    grupos = [{"campo": campo, "quick_add_form": form, "rows": [{"title": m.nome} for m in modelos]}]
    return render(request, "viagens_prestacoes/modelos.html", {**_contexto_form_modelo(form), "modelos": modelos, "campo": campo, "campo_rotulo": campos[campo], "abas": abas, "grupos": grupos, "q": busca, "page_title": "Modelos de texto do RT", "back_url": retorno, "back_label": "Voltar para o relatório técnico" if retorno else "", "next": retorno, "url_atual": request.get_full_path()})


def _contexto_form_modelo(form):
    from .view_common import opcoes
    valor = lambda nome: form[nome].value() or ""
    return {"form": form, "valores": {n: valor(n) for n in form.fields}, "erros": {n: form.errors.get(n) for n in form.fields},
            "opcoes_campo": opcoes(ModeloTextoRelatorioTecnico.CAMPO_CHOICES), "prefixo": (form.prefix + "-") if form.prefix else ""}


def modelo_editar(request, pk):
    modelo = get_object_or_404(ModeloTextoRelatorioTecnico, pk=pk)
    form = ModeloTextoRelatorioTecnicoForm(request.POST or None, instance=modelo)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Modelo de texto salvo.")
        return redirect(voltar_para(request, reverse("viagens_prestacoes:modelos_index") + f"?campo={modelo.campo}"))
    campos = dict(ModeloTextoRelatorioTecnico.CAMPO_CHOICES)
    return render(request, "viagens_prestacoes/modelos.html", {**_contexto_form_modelo(form), "modelo": modelo, "campo": modelo.campo, "campo_rotulo": campos.get(modelo.campo, ""), "page_title": "Editar modelo de texto", "next": next_valido(request), "url_atual": request.get_full_path()})


def modelo_excluir(request, pk):
    modelo = get_object_or_404(ModeloTextoRelatorioTecnico, pk=pk)
    excluir_modelo_texto(modelo)
    messages.success(request, "Modelo excluído.")
    return redirect(voltar_para(request, reverse("viagens_prestacoes:modelos_index") + f"?campo={modelo.campo}"))
