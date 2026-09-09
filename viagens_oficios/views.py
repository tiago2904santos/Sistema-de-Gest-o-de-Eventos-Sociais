import io
from zipfile import ZipFile

from django.contrib import messages
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction, IntegrityError
from django.http import Http404, HttpResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse
from django.views.decorators.http import require_http_methods, require_POST

from core.listagens import paginar, opcoes_choices
from core.numeracao import bloquear_escopo_numeracao, NAMESPACE_OFICIO
from viagens_cadastros.permissions import acesso_ao_modulo, pode_editar_cadastros, eh_gestor_viagens
from documentos.services.types import DocumentoTipo, DocumentoFormato
from documentos.services.responses import build_download_response, build_inline_pdf_response
from documentos.services.exceptions import DocumentError
from .models import Oficio, ConfiguracaoNumeracaoOficio, ModeloMotivoOficio, ModeloJustificativa
from .forms import OficioForm, JustificativaForm, NumeracaoForm
from .selectors import listar_oficios, get_oficio_by_id
from .services import reservar_numero_oficio, excluir_oficio, retificar_oficio, marcar_oficio_complementar, validar_oficio_para_documento
from .justificativas_services import atualizar_justificativa_oficio, avaliar_justificativa_oficio
from .document_generation import gerar_documento
from .view_helpers import campos_v32, secoes_oficio


def exigir_operador(request):
    if not pode_editar_cadastros(request.user):
        raise PermissionDenied


@acesso_ao_modulo
def preview_artefato(request, pk):
    from documentos.services.access import obter_artefato_para_download
    from django.http import FileResponse
    artefato = obter_artefato_para_download(request.user, pk)
    if artefato.formato != 'pdf':
        raise Http404
    response = FileResponse(artefato.arquivo_efetivo.open('rb'), content_type='application/pdf')
    response['Cache-Control'] = 'no-store'
    return response


@acesso_ao_modulo
@require_http_methods(['GET', 'POST'])
def assinatura_artefato(request, pk):
    from django import forms
    from documentos.services.access import obter_artefato_para_download
    from documentos.services.persistence import anexar_arquivo_assinado, remover_arquivo_assinado
    exigir_operador(request)
    artefato = obter_artefato_para_download(request.user, pk)
    if artefato.formato != 'pdf' or not (artefato.oficio_id or artefato.termo_id):
        raise Http404
    voltar = reverse('viagens_termos:detalhe', args=[artefato.termo_id]) if artefato.termo_id else reverse('viagens_oficios:detalhe', args=[artefato.oficio_id])

    class UploadForm(forms.Form):
        arquivo = forms.FileField(label='Documento assinado (PDF)')

    form = UploadForm(request.POST or None, request.FILES or None)
    if request.method == 'POST':
        try:
            if request.POST.get('acao') == 'remover':
                remover_arquivo_assinado(artefato)
                return redirect(voltar)
            if form.is_valid():
                anexar_arquivo_assinado(artefato, form.cleaned_data['arquivo'])
                messages.success(request, 'Versão assinada anexada. A anterior permanece no histórico.')
                return redirect(voltar)
        except DocumentError as exc:
            form.add_error('arquivo', str(exc))
    return render(request, 'pages/viagens_oficios/assinatura.html', {'form': form, 'artefato': artefato, 'url_voltar': voltar})


@acesso_ao_modulo
def lista(request):
    q, status, ano, fila = [request.GET.get(n, '') for n in ['q', 'status', 'ano', 'fila']]
    pagina, paginas, query = paginar(request, listar_oficios(q, status, ano, fila))
    return render(request, 'pages/viagens_oficios/lista.html', {
        'titulo': 'Ofícios', 'pagina': pagina, 'paginas_visiveis': paginas, 'querystring': query,
        'q': q, 'status': status, 'ano': ano, 'fila': fila,
        'opcoes_status': opcoes_choices(Oficio.STATUS_CHOICES),
        'opcoes_fila': opcoes_choices([('ativos', 'Ativos'), ('cancelados', 'Cancelados'), ('todos', 'Todos')]),
        'pode_editar': pode_editar_cadastros(request.user), 'gestor': eh_gestor_viagens(request.user),
    })


@acesso_ao_modulo
@require_http_methods(['GET', 'POST'])
def editar(request, pk=None):
    exigir_operador(request)
    oficio = get_oficio_by_id(pk) if pk else Oficio()
    form = OficioForm(request.POST or None, instance=oficio)
    justificativa = oficio.justificativa if pk and hasattr(oficio, 'justificativa') else None
    jform = JustificativaForm(request.POST or None, instance=justificativa, prefix='justificativa')
    if request.method == 'POST':
        valido, jvalido = form.is_valid(), jform.is_valid()
        if valido and jvalido:
            with transaction.atomic():
                oficio = form.save()
                reservar_numero_oficio(oficio, ano=oficio.data_criacao.year)
                atualizar_justificativa_oficio(oficio, jform, action='save_continue')
            messages.success(request, 'Ofício salvo.')
            return redirect('viagens_oficios:detalhe', pk=oficio.pk)
    return render(request, 'pages/viagens_oficios/form.html', {
        'titulo': 'Editar ofício' if pk else 'Novo ofício', 'form': form, 'jform': jform,
        'oficio': oficio, 'secoes': secoes_oficio(form, jform), 'pode_editar': True,
        'url_voltar': reverse('viagens_oficios:detalhe', args=[pk]) if pk else reverse('viagens_oficios:lista'),
        'regra': avaliar_justificativa_oficio(oficio),
        'modelos_texto': {
            'modelo_motivo': dict(ModeloMotivoOficio.objects.filter(ativo=True).values_list('pk', 'texto')),
            'justificativa-modelo': dict(ModeloJustificativa.objects.filter(ativo=True).values_list('pk', 'texto')),
        },
    })


@acesso_ao_modulo
def detalhe(request, pk):
    from auditoria.models import RegistroAuditoria
    from .presenters import apresentar_oficio
    oficio = get_oficio_by_id(pk)
    return render(request, 'pages/viagens_oficios/detalhe.html', {
        'oficio': oficio, 'avaliacao': validar_oficio_para_documento(oficio),
        'resumo': apresentar_oficio(oficio),
        'regra': avaliar_justificativa_oficio(oficio),
        'pode_editar': pode_editar_cadastros(request.user),
        'artefatos': oficio.artefatos.order_by('-criado_em')[:30],
        'historico': RegistroAuditoria.objects.filter(modelo='viagens_oficios.oficio', objeto_id=str(pk)).order_by('-criado_em')[:20],
    })


@acesso_ao_modulo
@require_POST
def acao(request, pk, acao):
    exigir_operador(request)
    oficio = get_oficio_by_id(pk)
    if acao == 'cancelar':
        oficio.cancelar(request.POST.get('motivo', ''))
    elif acao == 'reativar':
        oficio.reativar()
    elif acao == 'arquivar':
        oficio.status = Oficio.STATUS_ARQUIVADO
        oficio.save(update_fields=['status', 'atualizado_em'])
    elif acao == 'retificar':
        retificar_oficio(oficio)
    elif acao == 'complementar':
        marcar_oficio_complementar(oficio)
    elif acao == 'excluir':
        excluir_oficio(oficio)
        return redirect('viagens_oficios:lista')
    else:
        raise Http404
    messages.success(request, 'Ofício atualizado.')
    return redirect('viagens_oficios:detalhe', pk=pk)


def resposta_documento(request, doc):
    if request.GET.get('inline') == '1' and doc.formato == DocumentoFormato.PDF:
        return build_inline_pdf_response(request, content=doc.conteudo, tipo=doc.tipo,
            cache_hit=doc.cache_hit, x_document_sha256=doc.hash_sha256)
    return build_download_response(content=doc.conteudo, tipo=doc.tipo, formato=doc.formato, cache_hit=doc.cache_hit)


@acesso_ao_modulo
@require_POST
def gerar(request, pk, tipo, formato):
    exigir_operador(request)
    if tipo not in ['oficio', 'justificativa'] or formato not in ['docx', 'pdf']:
        raise Http404
    oficio = get_oficio_by_id(pk)
    try:
        doc = gerar_documento(oficio, DocumentoFormato(formato), DocumentoTipo(tipo))
    except (ValidationError, DocumentError) as exc:
        messages.error(request, '; '.join(exc.messages) if isinstance(exc, ValidationError) else str(exc))
        return redirect('viagens_oficios:detalhe', pk=pk)
    return resposta_documento(request, doc)


@acesso_ao_modulo
@require_POST
def termos(request, pk, formato, servidor_id=None):
    from viagens_termos.services import gerar_termo_um, gerar_termo_lote
    exigir_operador(request)
    if formato not in ['docx', 'pdf']:
        raise Http404
    oficio = get_oficio_by_id(pk)
    if oficio.cancelado:
        messages.error(request, 'Reative o ofício antes de gerar termos.')
        return redirect('viagens_oficios:detalhe', pk=pk)
    fmt = DocumentoFormato(formato)
    try:
        if servidor_id:
            servidor = get_object_or_404(oficio.servidores_termo_autorizacao, pk=servidor_id)
            return resposta_documento(request, gerar_termo_um(oficio, servidor, fmt))
        return resposta_lote(gerar_termo_lote(oficio, fmt))
    except (ValidationError, DocumentError) as exc:
        messages.error(request, '; '.join(exc.messages) if isinstance(exc, ValidationError) else str(exc))
        return redirect('viagens_oficios:detalhe', pk=pk)


def resposta_lote(documentos):
    buffer = io.BytesIO()
    with ZipFile(buffer, 'w') as zipfile:
        for doc in documentos:
            zipfile.writestr(doc.nome_arquivo, doc.conteudo)
    response = HttpResponse(buffer.getvalue(), content_type='application/zip')
    response['Content-Disposition'] = 'attachment; filename="termos.zip"'
    response['Cache-Control'] = 'no-store'
    return response


@acesso_ao_modulo
@require_http_methods(['GET', 'POST'])
def numeracao(request):
    if not eh_gestor_viagens(request.user):
        raise PermissionDenied
    from django.utils import timezone
    ano = request.POST.get('ano') or request.GET.get('ano') or timezone.localdate().year
    cfg = ConfiguracaoNumeracaoOficio.objects.filter(ano=int(ano)).first() if str(ano).isdigit() else None
    form = NumeracaoForm(request.POST or None, instance=cfg, initial={'ano': ano})
    if request.method == 'POST' and form.is_valid():
        with transaction.atomic():
            bloquear_escopo_numeracao(namespace=NAMESPACE_OFICIO, ano=form.cleaned_data['ano'], modelo=Oficio)
            form.save()
        messages.success(request, 'Piso de numeração salvo.')
        return redirect('viagens_oficios:numeracao')
    return render(request, 'pages/viagens_oficios/form_simples.html', {
        'titulo': 'Numeração de ofícios', 'form': form, 'campos': campos_v32(form),
        'ajuda': 'A sequência é calculada pelo maior número ocupado e pelas lacunas liberadas. O piso não renumera ofícios existentes.',
        'url_voltar': reverse('viagens_oficios:lista'),
    })
