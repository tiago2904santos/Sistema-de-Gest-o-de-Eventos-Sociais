from django.contrib import messages
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.utils import timezone
from django.utils.html import escape
from core.presenters.text import join_non_empty
from core.retorno import com_next
from core.utils.masks import format_protocolo
from .forms import CAMPOS_COM_MODELO, CAMPOS_CUSTEIO_COM_OUTRO
from .models import DiarioBordo, PrestacaoContas, PrestacaoServidor, RelatorioTecnico

def _prestacao_queryset():
    return PrestacaoContas.objects

def _prestacao_servidor_queryset():
    return PrestacaoServidor.objects

def _relatorio_queryset():
    return RelatorioTecnico.objects

def _diario_queryset():
    return DiarioBordo.objects

def _destino_display(oficio) -> str:
    try:
        destinos = list(oficio.roteiro.destinos.select_related('municipio', 'municipio__estado').order_by('ordem'))
        if not destinos:
            return ''
        parts = [f'{d.municipio} ({d.municipio.estado.sigla})' for d in destinos[:3]]
        result = ', '.join(parts)
        if len(destinos) > 3:
            result += f' +{len(destinos) - 3}'
        return result
    except (AttributeError, TypeError, ValueError):
        return ''

def _periodo_display(oficio) -> str:
    try:
        from django.utils import timezone as tz_module
        roteiro = oficio.roteiro
        saida_dt = roteiro.saida_dt
        if not saida_dt:
            return ''
        current_tz = tz_module.get_current_timezone()
        saida = saida_dt.astimezone(current_tz).date() if tz_module.is_aware(saida_dt) else saida_dt.date()
        chegada_dt = getattr(roteiro, 'retorno_chegada_dt', None) or getattr(roteiro, 'chegada_dt', None)
        if chegada_dt:
            chegada = chegada_dt.astimezone(current_tz).date() if tz_module.is_aware(chegada_dt) else chegada_dt.date()
            if saida == chegada:
                return saida.strftime('%d/%m/%Y')
            return f"{saida.strftime('%d/%m')} a {chegada.strftime('%d/%m/%Y')}"
        return saida.strftime('%d/%m/%Y')
    except (AttributeError, TypeError, ValueError):
        return ''

def _build_campos_modelo(form, *, return_url='') -> list:
    """Para cada campo de texto longo: select de modelos + textarea + URL de gerência."""
    base_url = reverse('viagens_prestacoes:modelos_index')
    campos = []
    for campo, label in CAMPOS_COM_MODELO:
        select = form[f'modelo_{campo}']
        campos.append({'campo': campo, 'label': label, 'select': select, 'textarea': form[campo], 'manage_url': f'{com_next(base_url, return_url)}#grupo-{campo}', 'tem_modelos': select.field.queryset.exists(), 'section_id': f'rt-topic-{campo}-title'})
    return campos

def _build_campos_custeio(form) -> list:
    campos = [{'campo': 'diaria', 'label': 'Diária', 'field': form['diaria'], 'other': None, 'uses_other': False}]
    for campo, label in CAMPOS_CUSTEIO_COM_OUTRO:
        campos.append({'campo': campo, 'label': label, 'field': form[campo], 'other': form[f'{campo}_outro'], 'uses_other': True})
    return campos

def _servidor_identificacao(ps) -> dict:
    from .presenters import _iniciais_nome_servidor
    servidor = ps.servidor
    cargo = str(servidor.cargo) if servidor.cargo_id else '—'
    unidade = str(servidor.unidade) if servidor.unidade_id else ''
    cpf = servidor.cpf_formatado
    cpf_display = f'CPF {cpf}' if cpf and cpf != '—' else ''
    return {'ps_pk': ps.pk, 'nome_servidor': servidor.nome, 'cpf_servidor': cpf, 'cargo': cargo, 'unidade': unidade, 'meta': join_non_empty([cargo, unidade, cpf_display]), 'is_motorista': ps.is_motorista, 'numero_solicitacao': ps.numero_solicitacao, 'iniciais': _iniciais_nome_servidor(servidor.nome)}

def _servidor_removido_identificacao(ps) -> dict:
    """`DB-06`: quem saiu da equipe, com a data e o que ficou guardado dele."""
    identificacao = _servidor_identificacao(ps)
    guardados = []
    if ps.numero_solicitacao.strip():
        guardados.append('número da solicitação')
    if ps.documentos_anexos.exists():
        guardados.append('comprovante')
    identificacao['removida_em'] = ps.removida_em
    identificacao['guardados'] = ', '.join(guardados)
    return identificacao

def _build_identificacao(prestacao) -> dict:
    """Identificação de nível ofício + lista de servidores da prestação."""
    from .selectors import servidores_removidos_da_equipe
    oficio = prestacao.oficio
    servidores = [_servidor_identificacao(ps) for ps in prestacao.servidores_prestacao.all()]
    removidos = [_servidor_removido_identificacao(ps) for ps in servidores_removidos_da_equipe(prestacao)]
    return {'numero': oficio.numero_formatado, 'protocolo': format_protocolo(oficio.protocolo) or '—', 'data_oficio': oficio.data_criacao.strftime('%d/%m/%Y') if oficio.data_criacao else '—', 'custeio': oficio.get_custeio_display() if oficio.custeio else '—', 'destino': _destino_display(oficio) or '—', 'periodo': _periodo_display(oficio) or '—', 'servidores': servidores, 'servidores_count': len(servidores), 'servidores_removidos': removidos}

def _primeiro_servidor(prestacao):
    return prestacao.servidores_prestacao.order_by('pk').first()

def _redirect_primeiro_servidor(request, prestacao, viewname):
    ps = _primeiro_servidor(prestacao)
    if ps is None:
        messages.error(request, 'Esta prestação ainda não possui servidores.')
        return redirect('viagens_prestacoes:index')
    return redirect(viewname, ps_pk=ps.pk)

def _build_prestacao_steps(ps, atual: str) -> list:
    """Etapas do wizard da prestação de contas (navegação por servidor)."""
    documentos_url = reverse('viagens_prestacoes:documentos_servidor', args=[ps.pk])
    rt_url = reverse('viagens_prestacoes:rt_servidor', args=[ps.pk])
    diario_url = reverse('viagens_prestacoes:diario_servidor', args=[ps.pk])
    etapas = [('diario', 'Etapa 1', 'Diário de Bordo', diario_url), ('rt', 'Etapa 2', 'Relatório Técnico', rt_url), ('documentos', 'Etapa 3', 'Documentos e fechamento', documentos_url)]
    steps = []
    atingiu_atual = False
    for chave, step_label, titulo, url in etapas:
        if chave == atual:
            state_class = 'is-current'
            aria_current = 'step'
            atingiu_atual = True
            status = 'Em edição'
        elif atingiu_atual:
            state_class = ''
            aria_current = ''
            status = 'A seguir'
        else:
            state_class = 'is-complete'
            aria_current = ''
            status = 'Concluído'
        steps.append({'label': titulo, 'state': 'current' if state_class == 'is-current' else 'done' if state_class == 'is-complete' else '', 'marker': '✓' if state_class == 'is-complete' else str(len(steps) + 1), 'step_label': step_label, 'title': titulo, 'status': status, 'state_class': state_class, 'aria_current': aria_current, 'url': url})
    return steps
_ROTULO_DA_ETAPA = {'diario': 'Diário de Bordo', 'rt': 'Relatório Técnico', 'documentos': 'Documentos e fechamento'}

def contexto_do_fluxo(ps, atual: str, *, back_label=None, back_url=None) -> dict:
    """Cabeçalho e stepper das telas de fluxo da prestação, num lugar só."""
    return {'wizard_page_steps': _build_prestacao_steps(ps, atual), 'flow_eyebrow': 'PRESTAÇÕES', 'flow_icon_label': 'PC', 'flow_module_label': 'Prestações de Contas', 'flow_back_label': back_label or 'Voltar à lista', 'flow_back_url': back_url or reverse('viagens_prestacoes:index'), 'flow_status_label': _ROTULO_DA_ETAPA[atual], 'flow_status_variant': 'draft',
            # A equipe da lateral troca de servidor sem sair da etapa: é a navegação por servidor da origem.
            'flow_view_name': _VIEW_DA_ETAPA[atual], 'flow_etapa': atual, 'flow_numero': [chave for chave, *_ in _ETAPAS].index(atual) + 1}


_ETAPAS = [('diario', 'Etapa 1', 'Diário de Bordo'), ('rt', 'Etapa 2', 'Relatório Técnico'), ('documentos', 'Etapa 3', 'Documentos e fechamento')]
_VIEW_DA_ETAPA = {'diario': 'viagens_prestacoes:diario_servidor', 'rt': 'viagens_prestacoes:rt_servidor', 'documentos': 'viagens_prestacoes:documentos_servidor'}


def opcoes(choices):
    """`[(valor, rótulo)]` → o formato do `components/select.html`."""
    return [{'valor': str(valor), 'rotulo': str(rotulo)} for valor, rotulo in choices if valor not in (None, '')]

def _autosave_version(obj, field_name='atualizado_em') -> int:
    obj.refresh_from_db()
    value = getattr(obj, field_name, None)
    if value is None:
        return 0
    return int(timezone.localtime(value).timestamp())

def _autosave_form_errors(form):
    return {field: [str(item) for item in messages_list] for field, messages_list in form.errors.items()}

def _prestacao_full(pc_pk):
    return get_object_or_404(_prestacao_queryset().select_related('oficio__roteiro').prefetch_related('servidores_prestacao__servidor__cargo', 'servidores_prestacao__servidor__unidade', 'servidores_prestacao__documentos_anexos', 'documentos_anexos'), pk=pc_pk)

def _prestacao_servidor_full(ps_pk):
    return get_object_or_404(_prestacao_servidor_queryset().select_related('prestacao__oficio__roteiro', 'servidor__cargo', 'servidor__unidade').prefetch_related('prestacao__servidores_prestacao__servidor__cargo', 'prestacao__servidores_prestacao__servidor__unidade', 'prestacao__servidores_prestacao__documentos_anexos', 'prestacao__documentos_anexos', 'documentos_anexos'), pk=ps_pk)

def _is_inline_request(request) -> bool:
    """Indica se o PDF deve ser servido embutido (iframe) em vez de baixado."""
    return (request.GET.get('inline') or '').strip() in {'1', 'true', 'sim'}

def _preview_error_response(exc) -> HttpResponse:
    """Mensagem amigável renderizada dentro do iframe quando a geração falha."""
    html = f'<!doctype html><html lang="pt-br"><head><meta charset="utf-8"><style>body{{margin:0;display:flex;align-items:center;justify-content:center;min-height:100vh;font-family:system-ui,sans-serif;color:#52657a;background:#f8fafd;}}.msg{{max-width:32rem;padding:1.5rem;text-align:center;line-height:1.5;}}</style></head><body><div class="msg"><strong>Não foi possível gerar o documento.</strong><br>{escape(str(exc))}</div></body></html>'
    return HttpResponse(html, content_type='text/html; charset=utf-8', status=422)
