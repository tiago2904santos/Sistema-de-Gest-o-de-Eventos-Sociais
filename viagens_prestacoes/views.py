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
        # m092: finalizada fica só para leitura; o lote ignora essas linhas.
        travados = set(_prestacao_servidor_queryset().filter(pk__in=valores, finalizada=True).values_list("pk", flat=True))
        if travados:
            messages.warning(request, "Prestação finalizada — reabra para editar. As linhas finalizadas não foram alteradas.")
            valores = {pk: v for pk, v in valores.items() if pk not in travados}
        resultado = salvar_solicitacoes_em_lote(_prestacao_servidor_queryset().filter(pk__in=valores), valores, autor=request.user)
        if resultado.erro:
            messages.error(request, resultado.erro)
        else:
            messages.success(request, "Solicitações atualizadas.")
        return _redirect_lista(request)
    filtros = {k: request.GET.get(k) or None for k in ("q", "status", "viagem_de", "viagem_ate", "sort")}
    from .cartoes import SITUACOES, cartao_da_lista
    from .presenters import get_configuracao_sistema
    from .selectors import normalizar_abas
    from core.retorno import daqui
    from viagens_cadastros.permissions import pode_editar_cadastros
    from .importacao.entrada import limite_de_bytes
    abas = normalizar_abas(request.GET.getlist("aba")) if request.GET.getlist("aba") else []
    itens = listar_prestacoes(**filtros, aba=abas)
    # A lista agrupa os servidores do mesmo ofício numa linha só: a página é de
    # prestações (ofícios), não de servidores, para a equipe nunca se partir
    # entre duas páginas. A ordem é a da consulta.
    ordem = list(itens.values_list("pk", "prestacao_id"))
    paginator = Paginator(list(dict.fromkeys(p for _, p in ordem)), ITENS_POR_PAGINA)
    pagina = paginator.get_page(request.GET.get("page"))
    da_pagina = set(pagina.object_list)
    ids = [pk for pk, prestacao in ordem if prestacao in da_pagina]
    por_pk = {ps.pk: ps for ps in itens.filter(pk__in=ids)}
    contagem = contar_por_aba(**{k:v for k,v in filtros.items() if k != "sort"})
    rotulos = dict(SITUACOES)
    vazias = {"nao_liberadas": "Nenhum servidor com diárias pendentes de liberação.", "liberadas": "Nenhum servidor com diárias já liberadas.", "arquivados": "Nenhuma prestação de servidor arquivada.", "finalizados": "Nenhuma prestação de servidor finalizada ainda.", "devolvidas": "Nenhuma prestação devolvida para correção.", "saque_vencendo": "Nenhum saque perto do prazo sem comprovante.", "prestacao_vencida": "Nenhuma prestação com o prazo vencido."}
    configuracao = get_configuracao_sistema()
    cards = [cartao_da_lista(por_pk[pk], configuracao=configuracao) for pk in ids]
    grupos = {}
    for card in cards:
        grupo = grupos.setdefault(card["prestacao_pk"], {
            "prestacao_pk": card["prestacao_pk"], "oficio": card["oficio"], "cards": [],
            # O valor do ofício por servidor (diárias do roteiro ÷ servidores) e a composição.
            "valor_por_servidor": card["valor_diarias_display"], "quantidade_diarias": card["quantidade_diarias_display"],
            "oficio_url": reverse("viagens_oficios:editar", args=[por_pk[card["ps_pk"]].prestacao.oficio_id]),
            "acoes_url": {a: reverse("viagens_prestacoes:prestacao_equipe_acao", args=[card["prestacao_pk"], a])
                          for a in ("finalizar", "reabrir", "arquivar", "desarquivar")},
            "importar_url": reverse("viagens_prestacoes:importacao_enviar_prestacao", args=[card["prestacao_pk"]]),
        })
        grupo["cards"].append(card)
    for grupo in grupos.values():
        grupo["todos_finalizados"] = all(c["finalizada"] for c in grupo["cards"])
        grupo["todos_arquivados"] = all(c["arquivada"] for c in grupo["cards"])
    grupos = [grupos[p] for p in pagina.object_list if p in grupos]
    parametros = request.GET.copy()
    parametros.pop("page", None)

    # A trilha de situações, no padrão das outras listas: "Todas" e uma por aba.
    def url_da_aba(aba=None):
        destino = parametros.copy()
        destino.pop("aba", None)
        if aba:
            destino["aba"] = aba
        return "?" + destino.urlencode()

    icones = {"nao_liberadas": "hourglass", "liberadas": "check-circle", "arquivados": "lock", "finalizados": "checklist", "devolvidas": "undo", "saque_vencendo": "clock", "prestacao_vencida": "alert"}
    total = listar_prestacoes(**{k: v for k, v in filtros.items() if k != "sort"}).count()
    situacoes = [{"slug": "todas", "titulo": "Todas", "total": total, "icone": "chart", "url": url_da_aba()}] + [
        {"slug": chave, "titulo": rotulo, "total": contagem[chave], "icone": icones[chave], "url": url_da_aba(chave)}
        for chave, rotulo in SITUACOES
    ]
    return render(request, "pages/viagens_prestacoes/index.html", {
        "situacoes": situacoes,
        "situacao_ativa": "todas" if not abas else abas[0] if len(abas) == 1 else "",
        "page_title": "Prestações de contas", "page_obj": pagina, "pagina": pagina, "cards": cards, "grupos": grupos, "contagem": contagem,
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
        "importacao_limite_mb": limite_de_bytes() // (1024 * 1024),
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

def _estado_pedido(request, atual, *, ligar, desligar):
    """O estado que o botão pediu (`acao`), e não o inverso do atual (m089).

    Sem `acao` (formulário antigo, rota de compatibilidade) continua invertendo,
    como sempre fez. Com ela, clicar de novo — ou numa aba antiga — não desfaz nada.
    """
    acao = (request.POST.get("acao") or "").strip()
    if acao == ligar:
        return True
    if acao == desligar:
        return False
    return not atual


def prestacao_servidor_arquivar(request, ps_pk):
    """Arquiva ou desarquiva a prestação deste servidor."""
    ps = get_object_or_404(_prestacao_servidor_queryset(), pk=ps_pk)
    pedido = _estado_pedido(request, ps.arquivada, ligar="arquivar", desligar="desarquivar")
    rotulo = "arquivada" if pedido else "desarquivada"
    if pedido == ps.arquivada:
        messages.info(request, f'A prestação de {ps.servidor.nome} já estava {rotulo}.')
        return _redirect_lista(request)
    ps.definir_arquivada(pedido)
    messages.success(request, f'Prestação de {ps.servidor.nome} {rotulo}.')
    return _redirect_lista(request)

def prestacao_servidor_finalizar(request, ps_pk):
    """Conclui ou reabre a prestação deste servidor."""
    ps = get_object_or_404(_prestacao_servidor_queryset(), pk=ps_pk)
    pedido = _estado_pedido(request, ps.finalizada, ligar="finalizar", desligar="reabrir")
    if pedido == ps.finalizada:
        messages.info(request, f'A prestação de {ps.servidor.nome} já estava {"finalizada" if pedido else "aberta"}.')
        return _redirect_lista(request)
    justificativa = None
    if pedido:
        # m092: com pendência, só finaliza com justificativa ("Finalizar mesmo assim").
        from .services import pendencias_para_finalizar
        pendencias = pendencias_para_finalizar(ps)
        justificativa = normalize_spaces(request.POST.get("justificativa") or "") if pendencias else ""
        if pendencias and not justificativa:
            messages.error(request, f'A prestação de {ps.servidor.nome} tem pendências: ' + " ".join(pendencias) + ' Para finalizar mesmo assim, escreva a justificativa no fim da Etapa 3.')
            return _redirect_lista(request)
        if pendencias:
            _registrar_finalizacao_com_pendencias(request, ps, pendencias, justificativa)
    ps.definir_finalizada(pedido, justificativa=justificativa)
    messages.success(request, f'Prestação de {ps.servidor.nome} {"finalizada" if pedido else "reaberta"}.')
    return _redirect_lista(request)


def _registrar_finalizacao_com_pendencias(request, ps, pendencias, justificativa):
    """A justificativa vai para a auditoria, com o que faltava no momento."""
    from auditoria.models import LogAuditoria
    LogAuditoria.objects.create(
        usuario=request.user if request.user.is_authenticated else None,
        acao="prestacao_finalizada_com_pendencias",
        descricao=f"{ps} — pendências: {' '.join(pendencias)} — justificativa: {justificativa}",
    )

def prestacao_servidor_envio(request, ps_pk, acao):
    """Registra o envio ao financeiro, a aprovação ou a devolução (m093)."""
    import datetime
    from django.http import Http404
    from .envio_services import registrar_aprovacao, registrar_devolucao, registrar_envio
    ps = get_object_or_404(_prestacao_servidor_queryset().select_related("servidor", "prestacao__oficio"), pk=ps_pk)
    if acao == "enviar":
        try:
            data = datetime.date.fromisoformat(request.POST.get("enviada_em") or "") if request.POST.get("enviada_em") else None
        except ValueError:
            data = None
        servidores = list(ps.prestacao.servidores_prestacao.select_related("servidor")) if request.POST.get("equipe") else [ps]
        resultado = registrar_envio(servidores, data=data, protocolo=request.POST.get("protocolo_envio") or "")
        sucesso = f"Envio registrado para {resultado.afetados} servidor{'es' if resultado.afetados != 1 else ''}."
    elif acao == "aprovar":
        resultado = registrar_aprovacao(ps)
        sucesso = f"Prestação de {ps.servidor.nome} aprovada."
    elif acao == "devolver":
        resultado = registrar_devolucao(ps, motivo=request.POST.get("motivo_devolucao") or "", autor=request.user)
        sucesso = f"Prestação de {ps.servidor.nome} devolvida e reaberta para correção."
    else:
        raise Http404
    if resultado.erro:
        messages.error(request, resultado.erro)
    else:
        messages.success(request, sucesso)
    return _redirect_lista(request)


def prestacao_equipe_acao(request, pc_pk, acao):
    """Finaliza, reabre, arquiva ou desarquiva a prestação da equipe inteira do ofício.

    O menu da linha do ofício na lista. Diferente das rotas antigas por
    ofício (que só tocam o primeiro servidor), aqui cada servidor recebe o
    mesmo estado.
    """
    from django.http import Http404
    acoes = {
        "finalizar": ("definir_finalizada", True, "finalizada"),
        "reabrir": ("definir_finalizada", False, "reaberta"),
        "arquivar": ("definir_arquivada", True, "arquivada"),
        "desarquivar": ("definir_arquivada", False, "desarquivada"),
    }
    if acao not in acoes:
        raise Http404
    metodo, valor, rotulo = acoes[acao]
    prestacao = get_object_or_404(_prestacao_queryset(), pk=pc_pk)
    servidores = list(prestacao.servidores_prestacao.all())
    com_pendencia = []
    if acao == "finalizar":
        # m092: quem tem pendência não é finalizado em lote; a justificativa é por servidor, na Etapa 3.
        from .services import pendencias_para_finalizar
        com_pendencia = [ps for ps in servidores if not ps.finalizada and pendencias_para_finalizar(ps)]
        servidores = [ps for ps in servidores if ps not in com_pendencia]
    for ps in servidores:
        if acao == "finalizar":
            if not ps.finalizada:
                ps.definir_finalizada(True, justificativa="")
        else:
            getattr(ps, metodo)(valor)
    total = len(servidores)
    plural = "es" if total != 1 else ""
    if total:
        messages.success(request, f"Prestação de {total} servidor{plural} {rotulo}.")
    if com_pendencia:
        nomes = ", ".join(ps.servidor.nome for ps in com_pendencia)
        messages.warning(request, f"Não finalizados por pendência: {nomes}. Abra a Etapa 3 de cada um para ver o que falta ou finalizar com justificativa.")
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
    resultado = salvar_solicitacao_do_autosave(ps, numero=_solicitacao_autosave_value(payload), datas={campo: _date_autosave_value(payload, campo) for campo in ('data_liberacao_diarias', 'prazo_limite_saque')}, autor=request.user)
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
