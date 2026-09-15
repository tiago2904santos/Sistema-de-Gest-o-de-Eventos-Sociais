from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.views.decorators.http import require_POST
from django.core.paginator import Paginator
from core.listagens import ITENS_POR_PAGINA
from core.normalizers import normalize_spaces
from core.autosave import parse_autosave_payload, autosave_json_response, AutosavePayloadError
from core.retorno import voltar_para
from .view_common import _prestacao_servidor_queryset, _prestacao_queryset, _primeiro_servidor, _autosave_version, _prestacao_servidor_full, contexto_do_fluxo, _build_identificacao
from .solicitacao_services import salvar_solicitacao_do_autosave, salvar_solicitacoes_em_lote, valores_do_lote
from .selectors import listar_prestacoes, contar_por_aba
from .services import pendencias_consolidado, gerar_prestacao_consolidado_pdf, nome_arquivo_prestacao_consolidado
from .ui import render, resposta_bytes
from .rt_views import *
from .diario_views import *
from .document_views import *
from .download_views import *
from .model_views import *


def _redirect_lista(request, _obj=None):
    return redirect(voltar_para(request, reverse("viagens_prestacoes:index")))


def index(request):
    if request.method == "POST":
        valores = valores_do_lote(request.POST)
        resultado = salvar_solicitacoes_em_lote(_prestacao_servidor_queryset().filter(pk__in=valores), valores)
        if resultado.erro:
            messages.error(request, resultado.erro)
        else:
            messages.success(request, "Solicitações atualizadas.")
        return _redirect_lista(request)
    filtros = {k: request.GET.get(k) or None for k in ("q", "status", "viagem_de", "viagem_ate", "sort")}
    from .cartoes import SITUACOES, cartao_da_lista
    from .presenters import get_configuracao_sistema, marcar_agrupamento_cards
    from .selectors import normalizar_abas
    from core.retorno import daqui
    from viagens_cadastros.permissions import pode_editar_cadastros
    abas = normalizar_abas(request.GET.getlist("aba")) if request.GET.getlist("aba") else []
    itens = listar_prestacoes(**filtros, aba=abas)
    paginator = Paginator(itens, ITENS_POR_PAGINA)
    pagina = paginator.get_page(request.GET.get("page"))
    contagem = contar_por_aba(**{k:v for k,v in filtros.items() if k != "sort"})
    rotulos = dict(SITUACOES)
    vazias = {"nao_liberadas": "Nenhum servidor com diárias pendentes de liberação.", "liberadas": "Nenhum servidor com diárias já liberadas.", "arquivados": "Nenhuma prestação de servidor arquivada.", "finalizados": "Nenhuma prestação de servidor finalizada ainda."}
    configuracao = get_configuracao_sistema()
    cards = marcar_agrupamento_cards([cartao_da_lista(ps, configuracao=configuracao) for ps in pagina])
    parametros = request.GET.copy()
    parametros.pop("page", None)
    return render(request, "viagens_prestacoes/index.html", {
        "page_title": "Prestações de contas", "page_obj": pagina, "pagina": pagina, "cards": cards,
        "prestacoes": pagina.object_list, "contagem": contagem,
        "q": filtros["q"] or "", "abas_selecionadas": abas,
        "has_filters": bool(abas or any(v for k,v in filtros.items() if k != "sort")),
        "situacao_options": [{"value": key, "label": f"{rotulos[key]} ({value})"} for key,value in contagem.items()],
        "opcoes_situacao": [{"valor": key, "rotulo": f"{rotulo} ({contagem[key]})", "selecionado": key in abas} for key, rotulo in SITUACOES],
        "empty_message": vazias.get(abas[0], "Nenhuma prestação encontrada.") if len(abas) == 1 else "Nenhuma prestação encontrada.",
        "querystring": parametros.urlencode(),
        "paginas_visiveis": list(paginator.get_elided_page_range(pagina.number, on_each_side=1, on_ends=1)),
        "elipse": paginator.ELLIPSIS,
        "url_atual": daqui(request),
        "pode_editar": pode_editar_cadastros(request.user),
    })


def consolidado(request, pc_pk):
    pc = get_object_or_404(_prestacao_queryset(), pk=pc_pk)
    ps = _primeiro_servidor(pc)
    return redirect("viagens_prestacoes:documentos_servidor", ps_pk=ps.pk) if ps else _redirect_lista(request)


def consolidado_download(request, ps_pk):
    from documentos.services.exceptions import DocumentValidationError
    from .view_common import _preview_error_response
    ps = _prestacao_servidor_full(ps_pk)
    try:
        pdf = gerar_prestacao_consolidado_pdf(ps)
    except DocumentValidationError as exc:
        return _preview_error_response(exc)
    return resposta_bytes(request, pdf, nome_arquivo_prestacao_consolidado(ps), "pdf")

def _solicitacao_autosave_value(payload):
    for name, value in payload.fields.items():
        clean_name = str(name or '').strip()
        if clean_name == 'numero_solicitacao' or clean_name.endswith('-numero_solicitacao'):
            return normalize_spaces(value or '')
    return None

def _date_autosave_value(payload, field_name):
    """Valor ISO bruto (ou vazio) de um campo de data individual, se presente."""
    for name, value in payload.fields.items():
        clean_name = str(name or '').strip()
        if clean_name == field_name or clean_name.endswith(f'-{field_name}'):
            return (value or '').strip()
    return None

def prestacao_servidor_arquivar(request, ps_pk):
    """Arquiva ou desarquiva a prestação deste servidor."""
    ps = get_object_or_404(_prestacao_servidor_queryset(), pk=ps_pk)
    ps.definir_arquivada(not ps.arquivada)
    if ps.arquivada:
        messages.success(request, f'Prestação de {ps.servidor.nome} arquivada.')
    else:
        messages.success(request, f'Prestação de {ps.servidor.nome} desarquivada.')
    return _redirect_lista(request)

def prestacao_servidor_finalizar(request, ps_pk):
    """Conclui ou reabre a prestação deste servidor."""
    ps = get_object_or_404(_prestacao_servidor_queryset(), pk=ps_pk)
    ps.definir_finalizada(not ps.finalizada)
    if ps.finalizada:
        messages.success(request, f'Prestação de {ps.servidor.nome} finalizada.')
    else:
        messages.success(request, f'Prestação de {ps.servidor.nome} reaberta.')
    return _redirect_lista(request)

def prestacao_arquivar(request, pc_pk):
    """Compatibilidade: arquiva o primeiro servidor da prestação do ofício."""
    prestacao = get_object_or_404(_prestacao_queryset(), pk=pc_pk)
    ps = _primeiro_servidor(prestacao)
    if ps is None:
        messages.error(request, 'Esta prestação ainda não possui servidores.')
        return _redirect_lista(request)
    return prestacao_servidor_arquivar(request, ps.pk)

def prestacao_finalizar(request, pc_pk):
    """Compatibilidade: finaliza o primeiro servidor da prestação do ofício."""
    prestacao = get_object_or_404(_prestacao_queryset(), pk=pc_pk)
    ps = _primeiro_servidor(prestacao)
    if ps is None:
        messages.error(request, 'Esta prestação ainda não possui servidores.')
        return _redirect_lista(request)
    return prestacao_servidor_finalizar(request, ps.pk)

def prestacao_servidor_solicitacao_autosave(request, ps_pk):
    ps = get_object_or_404(_prestacao_servidor_queryset(), pk=ps_pk)
    try:
        payload = parse_autosave_payload(request, expected_model='prestacao_servidor')
    except AutosavePayloadError as exc:
        return autosave_json_response(ok=False, message=str(exc))
    resultado = salvar_solicitacao_do_autosave(ps, numero=_solicitacao_autosave_value(payload), datas={campo: _date_autosave_value(payload, campo) for campo in ('data_liberacao_diarias', 'prazo_limite_saque')})
    if resultado.erro:
        return autosave_json_response(ok=False, message=resultado.erro)
    return autosave_json_response(ok=True, object_id=ps.pk, version=_autosave_version(ps))


def abrir_oficio(request, pk):
    from viagens_oficios.models import Oficio
    from viagens_oficios.views import exigir_operador
    from .signals import _sincronizar_prestacao_servidores
    exigir_operador(request)
    oficio = get_object_or_404(Oficio, pk=pk, cancelado=False)
    _sincronizar_prestacao_servidores(oficio)
    ps = oficio.prestacao_contas.servidores_prestacao.first()
    if ps is None:
        messages.error(request, "Inclua a equipe no ofício antes de abrir a prestação.")
        return redirect("viagens_oficios:editar", pk=oficio.pk)
    return redirect("viagens_prestacoes:diario_servidor", ps_pk=ps.pk)
