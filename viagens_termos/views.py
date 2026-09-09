from django.contrib import messages
from django.core.exceptions import ValidationError
from documentos.services.exceptions import DocumentError
from django.http import Http404
from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse
from django.views.decorators.http import require_http_methods, require_POST
from core.listagens import paginar
from viagens_cadastros.permissions import acesso_ao_modulo, pode_editar_cadastros
from viagens_oficios.views import exigir_operador, resposta_documento, resposta_lote
from viagens_oficios.view_helpers import campos_v32
from documentos.services.types import DocumentoFormato
from .models import TermoAutorizacao
from .forms import TermoAutorizacaoForm
from .selectors import listar_termos, get_termo_by_id
from .services import gerar_termo_cadastro_um, gerar_termo_cadastro_lote, build_termo_cadastro_payload


@acesso_ao_modulo
def lista(request):
    pagina, paginas, query = paginar(request, listar_termos(request.GET.get('q', ''), request.GET.get('cancelados') == '1'))
    return render(request, 'pages/viagens_termos/lista.html', {
        'pagina': pagina, 'querystring': query, 'q': request.GET.get('q', ''),
        'pode_editar': pode_editar_cadastros(request.user),
    })


@acesso_ao_modulo
@require_http_methods(['GET', 'POST'])
def editar(request, pk=None):
    exigir_operador(request)
    termo = get_termo_by_id(pk) if pk else TermoAutorizacao()
    form = TermoAutorizacaoForm(request.POST or None, instance=termo)
    if request.method == 'POST' and request.POST.get('acao') != 'adicionar_destino' and form.is_valid():
        termo = form.save()
        messages.success(request, 'Termo salvo.')
        return redirect('viagens_termos:detalhe', pk=termo.pk)
    return render(request, 'pages/viagens_oficios/form_simples.html', {
        'titulo': 'Editar termo' if pk else 'Novo termo', 'form': form, 'campos': campos_v32(form),
        'ajuda': 'Campos deixados em branco herdam os valores do ofício vinculado.',
        'url_voltar': reverse('viagens_termos:lista'),
        'quantidade_destinos': str(form.quantidade_destinos),
    })


@acesso_ao_modulo
def detalhe(request, pk):
    termo = get_termo_by_id(pk)
    return render(request, 'pages/viagens_termos/detalhe.html', {
        'termo': termo, 'servidores': termo.servidores_efetivos(),
        'pode_editar': pode_editar_cadastros(request.user), 'artefatos': termo.artefatos.order_by('-criado_em')[:30],
    })


@acesso_ao_modulo
def preview(request, pk, servidor_id=None):
    termo = get_termo_by_id(pk)
    servidor = get_object_or_404(termo.servidores_efetivos(), pk=servidor_id) if servidor_id else termo.servidores_efetivos().first()
    return render(request, 'pages/viagens_termos/preview.html', {'termo': termo, 'payload': build_termo_cadastro_payload(termo, servidor)})


@acesso_ao_modulo
@require_POST
def gerar(request, pk, formato, servidor_id=None):
    exigir_operador(request)
    termo = get_termo_by_id(pk)
    if formato not in ['docx', 'pdf']:
        raise Http404
    if termo.cancelado or (termo.oficio_id and termo.oficio.cancelado):
        messages.error(request, 'Reative o termo e o ofício antes de gerar documentos.')
        return redirect('viagens_termos:detalhe', pk=pk)
    try:
        if servidor_id is not None:
            servidor = get_object_or_404(termo.servidores_efetivos(), pk=servidor_id) if servidor_id else None
            return resposta_documento(request, gerar_termo_cadastro_um(termo, servidor, DocumentoFormato(formato)))
        return resposta_lote(gerar_termo_cadastro_lote(termo, DocumentoFormato(formato)))
    except (ValidationError, DocumentError) as exc:
        messages.error(request, '; '.join(exc.messages) if isinstance(exc, ValidationError) else str(exc))
        return redirect('viagens_termos:detalhe', pk=pk)


@acesso_ao_modulo
@require_POST
def acao(request, pk, acao):
    exigir_operador(request)
    termo = get_termo_by_id(pk)
    if acao == 'cancelar':
        termo.cancelar(request.POST.get('motivo', ''))
    elif acao == 'reativar':
        termo.reativar()
    elif acao == 'excluir':
        termo.delete()
        return redirect('viagens_termos:lista')
    else:
        raise Http404
    return redirect('viagens_termos:detalhe', pk=pk)
