import io
from zipfile import ZipFile

from django.contrib import messages
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction, IntegrityError
from django.http import Http404, HttpResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse
from django.views.decorators.http import require_http_methods, require_POST

from core.listagens import ITENS_POR_PAGINA, paginar, opcoes_choices
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
from .view_helpers import campos_v32


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


def _artefatos_pdf_da_pagina(oficios):
    """Último PDF de cada documento dos ofícios da página, para "Visualizar" e "Anexar assinado".

    Uma consulta para a página inteira: (ofício, tipo, servidor) → artefato.
    """
    from documentos.models import DocumentoArtefato
    ids = [o.pk for o in oficios]
    if not ids:
        return {}
    mapa = {}
    for art in DocumentoArtefato.objects.filter(oficio_id__in=ids, formato='pdf').order_by('criado_em').values_list('oficio_id', 'tipo', 'servidor_id', 'pk'):
        mapa[(art[0], art[1], art[2])] = art[3]
    return mapa


@acesso_ao_modulo
def lista(request):
    from django.core.paginator import Paginator
    from core.retorno import com_next, daqui
    from . import abas as abas_de_oficio
    from .presenters import cartao_da_lista
    from .selectors import ORDENACAO_PADRAO, normalizar_ordenacao, opcoes_de_ordenacao

    q = request.GET.get('q', '').strip()
    datas = {n: request.GET.get(n, '') for n in ['viagem_de', 'viagem_ate', 'criacao_de', 'criacao_ate']}
    sort = normalizar_ordenacao(request.GET.get('sort', ''))
    escolhidas = abas_de_oficio.normalizar_abas(request.GET.getlist('situacao'))

    # As contagens de situação valem para a busca e os períodos já aplicados,
    # e não para a situação escolhida: é assim que "Cancelados (3)" continua
    # dizendo quantos existem mesmo com outra situação marcada.
    base = listar_oficios(q, **datas)
    opcoes_situacao = abas_de_oficio.opcoes_de_aba(base, escolhidas)
    queryset = listar_oficios(q, situacoes=escolhidas, sort=sort, **datas)

    # A origem pagina com `page`, vinte por página.
    paginator = Paginator(queryset, ITENS_POR_PAGINA)
    pagina = paginator.get_page(request.GET.get('page'))
    paginas_visiveis = list(paginator.get_elided_page_range(pagina.number, on_each_side=1, on_ends=1))
    parametros = request.GET.copy()
    parametros.pop('page', None)

    volta = daqui(request)
    artefatos = _artefatos_pdf_da_pagina(pagina.object_list)
    cartoes = []
    for oficio in pagina:
        termos = {servidor_id: pk for (oficio_id, tipo, servidor_id), pk in artefatos.items()
                  if oficio_id == oficio.pk and tipo == DocumentoTipo.TERMO_AUTORIZACAO.value and servidor_id}
        cartoes.append(cartao_da_lista(
            oficio,
            editar_url=com_next(reverse('viagens_oficios:editar', args=[oficio.pk]), volta),
            artefatos_termo=termos,
            artefato_oficio_pdf=artefatos.get((oficio.pk, DocumentoTipo.OFICIO.value, None)),
            artefato_justificativa_pdf=artefatos.get((oficio.pk, DocumentoTipo.JUSTIFICATIVA.value, None)),
        ))

    tem_filtros = bool(q or escolhidas or any(datas.values()) or sort != ORDENACAO_PADRAO)
    return render(request, 'pages/viagens_oficios/lista.html', {
        'titulo': 'Ofícios', 'pagina': pagina, 'paginas_visiveis': paginas_visiveis,
        'elipse': paginator.ELLIPSIS, 'querystring': parametros.urlencode(),
        'cartoes': cartoes, 'q': q, 'sort': sort, 'datas': datas,
        'opcoes_situacao': opcoes_situacao, 'opcoes_ordenacao': opcoes_de_ordenacao(),
        'tem_filtros': tem_filtros, 'url_limpar': reverse('viagens_oficios:lista'),
        'url_atual': volta,
        'pode_editar': pode_editar_cadastros(request.user), 'gestor': eh_gestor_viagens(request.user),
    })


@acesso_ao_modulo
@require_POST
def criar(request):
    """"Novo ofício" da origem: cria o rascunho já numerado e abre o formulário."""
    from .services import criar_oficio_rascunho
    exigir_operador(request)
    oficio = criar_oficio_rascunho()
    return redirect('viagens_oficios:editar', pk=oficio.pk)


@acesso_ao_modulo
@require_http_methods(['GET', 'POST'])
def editar(request, pk=None):
    from core.retorno import next_valido, voltar_para
    from .form_context import contexto_form_oficio
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
            messages.success(request, f'Ofício {oficio.numero_formatado} salvo.')
            # "Salvar e continuar" segue para o resumo (etapa 5); "Salvar" volta
            # para onde a pessoa estava, quando a tela foi aberta com ?next=.
            if request.POST.get('acao') == 'salvar' and next_valido(request):
                return redirect(voltar_para(request, reverse('viagens_oficios:detalhe', args=[oficio.pk])))
            return redirect('viagens_oficios:detalhe', pk=oficio.pk)
        messages.error(request, 'Não foi possível salvar o ofício. Revise os campos indicados.')
    avaliacao = validar_oficio_para_documento(oficio) if pk else None
    regra = avaliar_justificativa_oficio(oficio)
    contexto = contexto_form_oficio(form, jform, oficio, avaliacao=avaliacao, regra=regra)
    contexto.update({
        'titulo': f'Ofício {oficio.numero_formatado}' if pk else 'Novo ofício', 'form': form, 'jform': jform,
        'oficio': oficio, 'pode_editar': True, 'next': next_valido(request),
        'url_voltar': voltar_para(request, reverse('viagens_oficios:detalhe', args=[pk]) if pk else reverse('viagens_oficios:lista')),
        'url_novo_roteiro': reverse('viagens_roteiros:novo'),
        'modelos_texto': {
            'modelo_motivo': dict(ModeloMotivoOficio.objects.filter(ativo=True).values_list('pk', 'texto')),
            'justificativa-modelo': dict(ModeloJustificativa.objects.filter(ativo=True).values_list('pk', 'texto')),
        },
    })
    return render(request, 'pages/viagens_oficios/form.html', contexto)


@acesso_ao_modulo
def detalhe(request, pk):
    """Conferência, resumo e documentos: as etapas 5 e 6 do wizard da origem."""
    from auditoria.models import RegistroAuditoria
    from core.retorno import com_next, daqui
    from .form_context import etapas_do_oficio
    from .presenters import apresentar_oficio, cartao_da_lista
    oficio = get_oficio_by_id(pk)
    avaliacao = validar_oficio_para_documento(oficio)
    regra = avaliar_justificativa_oficio(oficio)
    artefatos = _artefatos_pdf_da_pagina([oficio])
    termos = {servidor_id: art for (_, tipo, servidor_id), art in artefatos.items()
              if tipo == DocumentoTipo.TERMO_AUTORIZACAO.value and servidor_id}
    cartao = cartao_da_lista(
        oficio, editar_url=com_next(reverse('viagens_oficios:editar', args=[pk]), daqui(request)),
        artefatos_termo=termos,
        artefato_oficio_pdf=artefatos.get((pk, DocumentoTipo.OFICIO.value, None)),
        artefato_justificativa_pdf=artefatos.get((pk, DocumentoTipo.JUSTIFICATIVA.value, None)),
    )
    return render(request, 'pages/viagens_oficios/detalhe.html', {
        'oficio': oficio, 'c': cartao, 'avaliacao': avaliacao, 'regra': regra,
        'etapas': etapas_do_oficio(oficio, avaliacao, regra),
        'resumo': apresentar_oficio(oficio),
        'pode_editar': pode_editar_cadastros(request.user),
        'artefatos': oficio.artefatos.select_related('servidor').order_by('-criado_em')[:30],
        'historico': RegistroAuditoria.objects.filter(modelo='viagens_oficios.oficio', objeto_id=str(pk)).order_by('-criado_em')[:20],
        'url_atual': daqui(request),
        'tem_prestacao': hasattr(oficio, 'prestacao_contas'),
    })


@acesso_ao_modulo
@require_POST
def acao(request, pk, acao):
    from core.retorno import voltar_para
    from .services import OficioVinculadoError, desfazer_complementar_oficio, desfazer_retificacao_oficio
    exigir_operador(request)
    oficio = get_oficio_by_id(pk)
    # Da lista a ação volta para a lista como estava; do detalhe, para o detalhe.
    destino = voltar_para(request, reverse('viagens_oficios:detalhe', args=[pk]))
    if acao == 'cancelar':
        oficio.cancelar(request.POST.get('motivo', ''))
        messages.success(request, f'Ofício {oficio.numero_formatado} cancelado. O histórico foi mantido.')
    elif acao == 'reativar':
        oficio.reativar()
        messages.success(request, f'Ofício {oficio.numero_formatado} reativado.')
    elif acao == 'arquivar':
        oficio.status = Oficio.STATUS_ARQUIVADO
        oficio.save(update_fields=['status', 'atualizado_em'])
        messages.success(request, f'Ofício {oficio.numero_formatado} arquivado.')
    elif acao == 'retificar':
        # O mesmo item do menu liga e desliga a marca, como o estado de retificação da origem.
        if oficio.retificado_documento:
            desfazer_retificacao_oficio(oficio)
            messages.success(request, f'Ofício {oficio.numero_formatado} deixou de ser retificado.')
        else:
            retificar_oficio(oficio)
            messages.success(request, f'Ofício {oficio.numero_formatado} marcado como retificado.')
    elif acao == 'complementar':
        if oficio.complementar_documento:
            desfazer_complementar_oficio(oficio)
            messages.success(request, f'Ofício {oficio.numero_formatado} deixou de ser complementar.')
        else:
            marcar_oficio_complementar(oficio)
            messages.success(request, f'Ofício {oficio.numero_formatado} identificado como complementar.')
    elif acao == 'excluir':
        numero = oficio.numero_formatado
        try:
            excluir_oficio(oficio)
        except OficioVinculadoError:
            messages.error(request, f'O ofício {numero} tem prestação de contas ou documentos vinculados e não pode ser excluído.')
            return redirect(destino)
        messages.success(request, f'Ofício {numero} excluído. O número volta para a sequência.')
        return redirect(voltar_para(request, reverse('viagens_oficios:lista')))
    else:
        raise Http404
    return redirect(destino)


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
