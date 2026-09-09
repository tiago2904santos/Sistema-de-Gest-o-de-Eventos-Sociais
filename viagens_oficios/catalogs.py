from django import forms
from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse
from django.views.decorators.http import require_http_methods
from viagens_cadastros.models import ConfiguracaoSistema, AssinaturaConfiguracao
from viagens_cadastros.permissions import acesso_ao_modulo, eh_gestor_viagens, pode_editar_cadastros
from .models import ModeloMotivoOficio, ModeloJustificativa
from .forms import ModeloMotivoOficioForm, ModeloJustificativaForm
from .views import exigir_operador
from .view_helpers import campos_v32

ConfiguracaoForm = forms.modelform_factory(ConfiguracaoSistema, exclude=['chave', 'sede'], labels={
    'prazo_justificativa_dias': 'Prazo mínimo para justificativa (dias)',
    'nome_orgao': 'Nome do órgão', 'sigla_orgao': 'Sigla do órgão', 'cep': 'CEP',
    'cidade_endereco': 'Cidade do endereço', 'uf': 'UF', 'numero': 'Número do endereço',
    'nome_chefia': 'Nome da chefia (compatibilidade)', 'cargo_chefia': 'Cargo da chefia (compatibilidade)',
    'destinatario_oficio_nome': 'Nome do destinatário', 'destinatario_oficio_cargo': 'Cargo do destinatário',
    'destinatario_oficio_unidade': 'Unidade do destinatário',
})
AssinaturaForm = forms.modelform_factory(AssinaturaConfiguracao, fields=['tipo', 'servidor', 'ordem', 'ativo'])


class ConfiguracaoInstitucionalForm(ConfiguracaoForm):
    from cadastros.models import Estado
    sede_estado = forms.ModelChoiceField(Estado.objects.all(), required=False, label='Estado da sede')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.order_fields(['sede_estado', 'cidade_sede_padrao'])
        if not self.is_bound and self.instance.cidade_sede_padrao_id:
            self.initial['sede_estado'] = self.instance.cidade_sede_padrao.estado_id

    def clean(self):
        cd = super().clean()
        sede, estado = cd.get('cidade_sede_padrao'), cd.get('sede_estado')
        if sede and (not estado or sede.estado_id != estado.pk):
            self.add_error('cidade_sede_padrao', 'Selecione uma sede do estado informado.')
        return cd


CATALOGOS = {
    'motivos': (ModeloMotivoOficio, ModeloMotivoOficioForm, 'Motivos de ofício'),
    'justificativas': (ModeloJustificativa, ModeloJustificativaForm, 'Modelos de justificativa'),
    'assinaturas': (AssinaturaConfiguracao, AssinaturaForm, 'Assinantes dos documentos'),
}


@acesso_ao_modulo
@require_http_methods(['GET', 'POST'])
def catalogo(request, tipo, pk=None, novo=False):
    from django.http import Http404
    if tipo not in CATALOGOS:
        raise Http404
    modelo, form_cls, titulo = CATALOGOS[tipo]
    if tipo == 'assinaturas' and not eh_gestor_viagens(request.user):
        raise PermissionDenied
    if pk is None and not novo:
        qs = modelo.objects.all()
        if request.GET.get('q') and tipo != 'assinaturas':
            qs = qs.filter(nome__icontains=request.GET['q'])
        return render(request, 'pages/viagens_oficios/catalogo.html', {
            'titulo': titulo, 'objetos': qs, 'tipo': tipo,
            'pode_editar': eh_gestor_viagens(request.user) if tipo == 'assinaturas' else pode_editar_cadastros(request.user),
        })
    exigir_operador(request)
    obj = get_object_or_404(modelo, pk=pk) if pk else modelo()
    if tipo == 'assinaturas':
        obj.configuracao = ConfiguracaoSistema.get_singleton()
    form = form_cls(request.POST or None, instance=obj)
    if request.method == 'POST':
        if request.POST.get('acao') == 'excluir' and pk:
            obj.delete()
            return redirect('viagens_oficios:catalogo', tipo=tipo)
        if form.is_valid():
            form.save()
            messages.success(request, 'Cadastro salvo.')
            return redirect('viagens_oficios:catalogo', tipo=tipo)
    return render(request, 'pages/viagens_oficios/form_simples.html', {
        'titulo': titulo, 'form': form, 'campos': campos_v32(form), 'excluir': bool(pk),
        'url_voltar': reverse('viagens_oficios:catalogo', args=[tipo]),
    })


@acesso_ao_modulo
@require_http_methods(['GET', 'POST'])
def institucional(request):
    if not eh_gestor_viagens(request.user):
        raise PermissionDenied
    form = ConfiguracaoInstitucionalForm(request.POST or None, instance=ConfiguracaoSistema.get_singleton())
    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, 'Configuração institucional salva.')
        return redirect('viagens_oficios:institucional')
    return render(request, 'pages/viagens_oficios/form_simples.html', {
        'titulo': 'Configuração institucional de viagens', 'form': form, 'campos': campos_v32(form),
        'url_voltar': reverse('viagens_oficios:lista'), 'assinaturas_url': reverse('viagens_oficios:catalogo', args=['assinaturas']),
    })
