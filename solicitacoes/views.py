from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Q
from django.http import FileResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from .forms import AnexoForm, DespachoForm, FiltroSolicitacoesForm, SolicitacaoForm
from .models import (
    AcaoHistorico,
    AnexoSolicitacao,
    SolicitacaoEvento,
    StatusSolicitacao,
    TipoOperacao,
)
from . import permissions, services

ITENS_POR_PAGINA = 15


# ---------------------------------------------------------------------------
# Helpers de contexto para os components do design system
# ---------------------------------------------------------------------------

def _opcoes(iteravel):
    return [{"valor": str(getattr(item, "pk", item)), "rotulo": str(item)} for item in iteravel]


def _opcoes_municipios(iteravel):
    return [
        {
            "valor": str(item.pk),
            "rotulo": str(item),
            "estado": str(item.estado_id),
        }
        for item in iteravel
    ]


def _opcoes_choices(choices):
    return [{"valor": str(valor), "rotulo": str(rotulo)} for valor, rotulo in choices]


def _valores(form):
    """Valores atuais (POST ou instância) como strings para os templates."""
    valores = {}
    for nome in form.fields:
        valor = form[nome].value()
        if isinstance(valor, bool):
            valor = "1" if valor else "0"
        valores[nome] = "" if valor is None else str(valor)
    return valores


def _marcados(form, nome):
    """IDs selecionados de um campo múltiplo, como strings."""
    valor = form[nome].value() or []
    return [str(getattr(item, "pk", item)) for item in valor]


CAMPOS_FORMULARIO = [
    "data_solicitacao", "data_inicio_evento", "data_fim_evento", "tipo_evento",
    "municipio", "local_evento", "solicitante_nome", "solicitante_cargo_unidade",
    "contato", "orgao_responsavel", "unidade_movel", "unidade_movel_designada",
    "veiculo_exposicao", "descricao_complementar", "quantidade_servidores",
    "tipo_operacao", "quantidade_cin", "motorista", "decisao_dg", "observacoes_dg",
]

CAMPOS_FK = {
    "tipo_evento", "municipio", "orgao_responsavel", "motorista",
    "unidade_movel_designada",
}


def _valor_da_instancia(solicitacao, nome):
    if nome in CAMPOS_FK:
        valor = getattr(solicitacao, f"{nome}_id")
    else:
        valor = getattr(solicitacao, nome)
    if isinstance(valor, bool):
        return "1" if valor else "0"
    return "" if valor is None else str(valor)


def _contexto_formulario(request, form, solicitacao=None):
    if solicitacao:
        acoes = permissions.acoes_permitidas(request.user, solicitacao)
    else:
        acoes = {"editar_dados": True, "enviar": True, "despachar": False}

    valores = _valores(form)
    # Campos fora do formulário (seções desabilitadas) exibem o valor salvo.
    if solicitacao:
        for nome in CAMPOS_FORMULARIO:
            if nome not in valores:
                valores[nome] = _valor_da_instancia(solicitacao, nome)
    if "estado" not in valores:
        valores["estado"] = (
            str(solicitacao.municipio.estado_id)
            if solicitacao and solicitacao.municipio_id
            else ""
        )

    def opcoes_de(nome, fallback_relacao=None):
        if nome in form.fields:
            return _opcoes(form.fields[nome].queryset)
        if solicitacao and fallback_relacao:
            return _opcoes(fallback_relacao)
        if solicitacao and getattr(solicitacao, nome, None):
            return _opcoes([getattr(solicitacao, nome)])
        return []

    def marcados_de(nome, relacao):
        if nome in form.fields:
            return _marcados(form, nome)
        if solicitacao:
            return [str(item.pk) for item in relacao]
        return []

    servicos_salvos = list(solicitacao.servicos.all()) if solicitacao else []
    equipes_salvas = list(solicitacao.equipes.all()) if solicitacao else []
    estados_salvos = (
        [solicitacao.municipio.estado]
        if solicitacao and solicitacao.municipio_id
        else []
    )
    equipes_disponiveis = opcoes_de("equipes", equipes_salvas)
    equipes_marcadas = marcados_de("equipes", equipes_salvas)
    quantidades_salvas = {
        str(item.equipe_id): item.quantidade_servidores
        for item in solicitacao.itens_equipe.all()
    } if solicitacao else {}
    equipes_planejamento = []
    for equipe in equipes_disponiveis:
        nome_quantidade = f"quantidade_equipe_{equipe['valor']}"
        if form.is_bound:
            quantidade = form.data.get(nome_quantidade, "")
        else:
            quantidade = quantidades_salvas.get(equipe["valor"], "")
        equipes_planejamento.append(
            {
                **equipe,
                "selecionada": equipe["valor"] in equipes_marcadas,
                "nome_quantidade": nome_quantidade,
                "quantidade": "" if quantidade is None else str(quantidade),
            }
        )

    return {
        "form": form,
        "solicitacao": solicitacao,
        "valores": valores,
        "erros": form.errors,
        "erro_periodo": form.errors.get("data_inicio_evento")
        or form.errors.get("data_fim_evento"),
        "tipos_evento": opcoes_de("tipo_evento"),
        "estados": opcoes_de("estado", estados_salvos),
        "municipios": _opcoes_municipios(form.fields["municipio"].queryset)
        if "municipio" in form.fields
        else _opcoes_municipios([solicitacao.municipio])
        if solicitacao and solicitacao.municipio_id
        else [],
        "orgaos": opcoes_de("orgao_responsavel"),
        "servicos": opcoes_de("servicos", servicos_salvos),
        "equipes": equipes_disponiveis,
        "equipes_planejamento": equipes_planejamento,
        "motoristas": opcoes_de("motorista"),
        "unidades_moveis": opcoes_de("unidade_movel_designada"),
        "tipos_operacao": _opcoes_choices(TipoOperacao.choices),
        "servicos_marcados": marcados_de("servicos", servicos_salvos),
        "equipes_marcadas": equipes_marcadas,
        "timeline": services.montar_timeline(solicitacao),
        "dados_desabilitado": bool(solicitacao) and not acoes["editar_dados"],
        # Formulário único: o planejamento acompanha a edição dos dados.
        "planejamento_desabilitado": bool(solicitacao) and not acoes["editar_dados"],
        "mostrar_enviar": acoes["enviar"] if solicitacao else True,
        "mostrar_despacho_dg": bool(solicitacao)
        and permissions.eh_gestor_dg(request.user),
        "anexos": list(solicitacao.anexos.select_related("enviado_por"))
        if solicitacao
        else [],
        "pode_gerenciar_anexos": acoes["editar_dados"] if solicitacao else False,
    }


def _obter_visivel(request, pk):
    solicitacao = get_object_or_404(
        SolicitacaoEvento.objects.select_related(
            "municipio__estado", "regiao", "tipo_evento", "orgao_responsavel", "motorista",
            "criado_por", "decidido_por",
        ).prefetch_related(
            "servicos", "equipes", "itens_equipe__equipe", "historico__usuario"
        ),
        pk=pk,
    )
    if not permissions.pode_ver(request.user, solicitacao):
        raise PermissionDenied
    return solicitacao


# ---------------------------------------------------------------------------
# Criação e edição
# ---------------------------------------------------------------------------

@login_required
def nova_solicitacao(request):
    """Tela "Nova Solicitação de Evento Social" com persistência real."""
    if request.method == "POST":
        acao = request.POST.get("acao", "rascunho")
        form = SolicitacaoForm(request.POST, enviar=(acao == "enviar"))
        if form.is_valid():
            with transaction.atomic():
                solicitacao = form.save(criado_por=request.user)
                services.registrar_historico(
                    solicitacao, request.user, AcaoHistorico.CRIACAO,
                    status_novo=solicitacao.status,
                )
                if acao == "enviar":
                    services.enviar(solicitacao, request.user)
            if acao == "enviar":
                messages.success(request, f"Solicitação #{solicitacao.pk} enviada com sucesso.")
            else:
                messages.success(request, f"Rascunho #{solicitacao.pk} salvo com sucesso.")
            return redirect("solicitacoes:detalhe", pk=solicitacao.pk)
        else:
            messages.error(request, "Corrija os campos destacados para continuar.")
    else:
        form = SolicitacaoForm()
    contexto = _contexto_formulario(request, form)
    contexto["titulo_pagina"] = "Nova Solicitação de Evento Social"
    return render(request, "pages/solicitacoes/form.html", contexto)


@login_required
def editar_solicitacao(request, pk):
    """Revisão do rascunho pelo criador, antes do envio à DG."""
    solicitacao = _obter_visivel(request, pk)
    if not permissions.pode_editar_dados(request.user, solicitacao):
        raise PermissionDenied

    if request.method == "POST":
        acao = request.POST.get("acao", "rascunho")
        if acao == "enviar" and not permissions.pode_enviar(request.user, solicitacao):
            raise PermissionDenied
        form = SolicitacaoForm(
            request.POST, instance=solicitacao, enviar=(acao == "enviar")
        )
        if form.is_valid():
            try:
                with transaction.atomic():
                    solicitacao = form.save()
                    services.registrar_historico(
                        solicitacao,
                        request.user,
                        AcaoHistorico.ATUALIZACAO,
                        status_novo=solicitacao.status,
                    )
                    if acao == "enviar":
                        services.enviar(solicitacao, request.user)
            except ValidationError as erro:
                for mensagem_erro in erro.messages:
                    messages.error(request, mensagem_erro)
            else:
                if acao == "enviar":
                    messages.success(
                        request, f"Solicitação #{solicitacao.pk} enviada com sucesso."
                    )
                else:
                    messages.success(request, f"Solicitação #{solicitacao.pk} atualizada.")
                return redirect("solicitacoes:detalhe", pk=solicitacao.pk)
        else:
            messages.error(request, "Corrija os campos destacados para continuar.")
    else:
        form = SolicitacaoForm(instance=solicitacao)

    contexto = _contexto_formulario(request, form, solicitacao)
    contexto["titulo_pagina"] = f"Editar Solicitação #{solicitacao.pk}"
    return render(request, "pages/solicitacoes/form.html", contexto)


# ---------------------------------------------------------------------------
# Listagem e detalhe
# ---------------------------------------------------------------------------

FILAS = {
    "despacho": {
        "rotulo": "Aguardando despacho",
        "status": [StatusSolicitacao.AGUARDANDO_DESPACHO],
    },
    "rascunhos": {
        "rotulo": "Meus rascunhos",
        "status": [StatusSolicitacao.RASCUNHO],
        "apenas_do_usuario": True,
    },
    "devolvidas": {
        "rotulo": "Devolvidas para ajuste",
        "status": [StatusSolicitacao.DEVOLVIDA],
        "apenas_do_usuario": True,
    },
}


def _filas_do_usuario(user, queryset):
    """Atalhos de fila com contagem, conforme o perfil do usuário."""
    # A fila de despacho é da DG; rascunhos e devolvidas são de cada um.
    filas = []
    if permissions.eh_gestor_dg(user):
        filas.append("despacho")
    filas.extend(["rascunhos", "devolvidas"])
    resultado = []
    for chave in filas:
        config = FILAS[chave]
        parcial = queryset.filter(status__in=config["status"])
        if config.get("apenas_do_usuario"):
            parcial = parcial.filter(criado_por=user)
        resultado.append(
            {"chave": chave, "rotulo": config["rotulo"], "total": parcial.count()}
        )
    return resultado


def _queryset_filtrado(request):
    """Solicitações visíveis com fila e filtros da listagem aplicados."""
    filtros = FiltroSolicitacoesForm(request.GET or None)
    base = permissions.queryset_visivel(
        request.user,
        SolicitacaoEvento.objects.select_related(
            "municipio", "tipo_evento", "regiao", "criado_por"
        ),
    )
    queryset = base.order_by("-data_solicitacao", "-pk")

    fila = request.GET.get("fila", "")
    if fila in FILAS:
        queryset = queryset.filter(status__in=FILAS[fila]["status"])
        if FILAS[fila].get("apenas_do_usuario"):
            queryset = queryset.filter(criado_por=request.user)

    if filtros.is_valid():
        dados = filtros.cleaned_data
        if dados.get("q"):
            termo = dados["q"]
            queryset = queryset.filter(
                Q(solicitante_nome__icontains=termo)
                | Q(local_evento__icontains=termo)
                | Q(municipio__nome__icontains=termo)
            )
        if dados.get("status"):
            queryset = queryset.filter(status=dados["status"])
        if dados.get("municipio"):
            queryset = queryset.filter(municipio=dados["municipio"])
        if dados.get("tipo_evento"):
            queryset = queryset.filter(tipo_evento=dados["tipo_evento"])
        if dados.get("inicio"):
            queryset = queryset.filter(data_inicio_evento__gte=dados["inicio"])
        if dados.get("fim"):
            queryset = queryset.filter(data_inicio_evento__lte=dados["fim"])

    return queryset, base, filtros, fila


@login_required
def lista_solicitacoes(request):
    queryset, base, filtros, fila = _queryset_filtrado(request)

    paginador = Paginator(queryset, ITENS_POR_PAGINA)
    pagina = paginador.get_page(request.GET.get("pagina"))

    parametros = request.GET.copy()
    parametros.pop("pagina", None)

    return render(
        request,
        "pages/solicitacoes/lista.html",
        {
            "pagina": pagina,
            "filtros": filtros,
            "valores_filtro": {
                nome: ("" if filtros[nome].value() is None else str(filtros[nome].value()))
                for nome in filtros.fields
            },
            "opcoes_status": _opcoes_choices(StatusSolicitacao.choices),
            "opcoes_municipios": _opcoes(filtros.fields["municipio"].queryset),
            "opcoes_tipos": _opcoes(filtros.fields["tipo_evento"].queryset),
            "querystring": parametros.urlencode(),
            "filas": _filas_do_usuario(request.user, base),
            "fila_ativa": fila,
            "linhas": [
                {"solicitacao": s, "acoes": permissions.acoes_permitidas(request.user, s)}
                for s in pagina
            ],
        },
    )


@login_required
def exportar_solicitacoes(request):
    """Exporta a listagem filtrada em CSV legível pelo Excel (pt-BR)."""
    import csv

    from django.http import HttpResponse
    from django.utils import timezone as tz

    queryset, _base, _filtros, _fila = _queryset_filtrado(request)
    queryset = queryset.select_related(
        "orgao_responsavel", "motorista", "decidido_por"
    ).prefetch_related("servicos", "itens_equipe__equipe")

    hoje = tz.localdate().strftime("%Y-%m-%d")
    resposta = HttpResponse(content_type="text/csv; charset=utf-8")
    resposta["Content-Disposition"] = (
        f'attachment; filename="solicitacoes-{hoje}.csv"'
    )
    # BOM para o Excel reconhecer UTF-8; ponto e vírgula para o Excel pt-BR.
    resposta.write("﻿")
    escritor = csv.writer(resposta, delimiter=";", lineterminator="\r\n")
    escritor.writerow([
        "Nº", "Status", "Data da solicitação", "Início do evento", "Fim do evento",
        "Município", "Região", "Tipo de evento", "Local", "Solicitante",
        "Cargo / unidade", "Contato", "Órgão responsável", "Serviços",
        "Equipes (servidores)", "Total de servidores", "Tipo de operação",
        "Unidade móvel", "Veículo de exposição", "Qtde CIN", "Motorista",
        "Decisão DG", "Observações DG", "Decidido por", "Decidido em",
        "Criado por",
    ])

    def data(valor, formato="%d/%m/%Y"):
        if not valor:
            return ""
        if hasattr(valor, "astimezone"):
            valor = tz.localtime(valor)
        return valor.strftime(formato)

    for s in queryset:
        equipes = "; ".join(
            f"{item.equipe} ({item.quantidade_servidores or '-'})"
            for item in s.itens_equipe.all()
        )
        escritor.writerow([
            s.pk,
            s.get_status_display(),
            data(s.data_solicitacao),
            data(s.data_inicio_evento),
            data(s.data_fim_evento),
            s.municipio or "",
            s.regiao or "",
            s.tipo_evento or "",
            s.local_evento,
            s.solicitante_nome,
            s.solicitante_cargo_unidade,
            s.contato,
            s.orgao_responsavel or "",
            "; ".join(str(servico) for servico in s.servicos.all()),
            equipes,
            s.quantidade_servidores or "",
            s.get_tipo_operacao_display() if s.tipo_operacao else "",
            "Sim" if s.unidade_movel else "Não",
            "Sim" if s.veiculo_exposicao else "Não",
            s.quantidade_cin or "",
            s.motorista or "",
            s.get_decisao_dg_display(),
            s.observacoes_dg,
            s.decidido_por or "",
            data(s.decidido_em, "%d/%m/%Y %H:%M"),
            s.criado_por,
        ])
    return resposta


@login_required
def detalhe_solicitacao(request, pk):
    solicitacao = _obter_visivel(request, pk)
    contexto = _contexto_formulario(
        request,
        SolicitacaoForm(instance=solicitacao),
        solicitacao,
    )
    contexto.update(
        {
            "titulo_pagina": f"Solicitação #{solicitacao.pk}",
            "subtitulo_pagina": "Visualização completa da solicitação",
            "acoes": permissions.acoes_permitidas(request.user, solicitacao),
            "historico": solicitacao.historico.all(),
            "somente_leitura": True,
            "dados_desabilitado": True,
            "planejamento_desabilitado": True,
            "mostrar_enviar": False,
        }
    )
    return render(request, "pages/solicitacoes/form.html", contexto)


# ---------------------------------------------------------------------------
# Transições de workflow (somente POST)
# ---------------------------------------------------------------------------

def _executar_transicao(request, solicitacao, funcao, mensagem, **kwargs):
    try:
        funcao(solicitacao, request.user, **kwargs)
    except ValidationError as erro:
        for mensagem_erro in erro.messages:
            messages.error(request, mensagem_erro)
    else:
        messages.success(request, mensagem)
    return redirect("solicitacoes:detalhe", pk=solicitacao.pk)


@login_required
@require_POST
def enviar_solicitacao(request, pk):
    solicitacao = _obter_visivel(request, pk)
    if not permissions.pode_enviar(request.user, solicitacao):
        raise PermissionDenied
    return _executar_transicao(
        request, solicitacao, services.enviar,
        f"Solicitação #{solicitacao.pk} enviada com sucesso.",
    )


# ---------------------------------------------------------------------------
# Anexos
# ---------------------------------------------------------------------------

@login_required
@require_POST
def adicionar_anexo(request, pk):
    solicitacao = _obter_visivel(request, pk)
    if not permissions.pode_editar_dados(request.user, solicitacao):
        raise PermissionDenied
    form = AnexoForm(request.POST, request.FILES)
    if form.is_valid():
        arquivo = form.cleaned_data["arquivo"]
        AnexoSolicitacao.objects.create(
            solicitacao=solicitacao,
            arquivo=arquivo,
            nome_original=arquivo.name,
            tamanho=arquivo.size,
            enviado_por=request.user,
        )
        services.registrar_historico(
            solicitacao, request.user, AcaoHistorico.ATUALIZACAO,
            status_novo=solicitacao.status,
            observacao=f"Anexo adicionado: {arquivo.name}",
        )
        messages.success(request, f"Arquivo {arquivo.name} anexado.")
    else:
        for erros_campo in form.errors.values():
            for erro in erros_campo:
                messages.error(request, erro)
    return redirect("solicitacoes:detalhe", pk=solicitacao.pk)


@login_required
def baixar_anexo(request, pk, anexo_pk):
    solicitacao = _obter_visivel(request, pk)
    anexo = get_object_or_404(solicitacao.anexos, pk=anexo_pk)
    return FileResponse(
        anexo.arquivo.open("rb"),
        as_attachment=True,
        filename=anexo.nome_original,
    )


@login_required
@require_POST
def excluir_anexo(request, pk, anexo_pk):
    solicitacao = _obter_visivel(request, pk)
    if not permissions.pode_editar_dados(request.user, solicitacao):
        raise PermissionDenied
    anexo = get_object_or_404(solicitacao.anexos, pk=anexo_pk)
    nome = anexo.nome_original
    anexo.delete()
    services.registrar_historico(
        solicitacao, request.user, AcaoHistorico.ATUALIZACAO,
        status_novo=solicitacao.status,
        observacao=f"Anexo removido: {nome}",
    )
    messages.success(request, f"Anexo {nome} removido.")
    return redirect("solicitacoes:detalhe", pk=solicitacao.pk)


@login_required
@require_POST
def excluir_solicitacao(request, pk):
    solicitacao = _obter_visivel(request, pk)
    if not permissions.pode_excluir(request.user, solicitacao):
        raise PermissionDenied
    numero = solicitacao.pk
    solicitacao.delete()
    messages.success(request, f"Rascunho #{numero} excluído.")
    return redirect("solicitacoes:lista")


def _quantidades_dg_do_post(request, solicitacao):
    """Quantidades por equipe informadas pela DG no formulário de despacho."""
    quantidades = {}
    for item in solicitacao.itens_equipe.all():
        valor = str(request.POST.get(f"quantidade_dg_{item.equipe_id}", "")).strip()
        if valor:
            try:
                quantidades[item.equipe_id] = int(valor)
            except ValueError:
                quantidades[item.equipe_id] = 0
    return quantidades


@login_required
@require_POST
def despachar(request, pk):
    solicitacao = _obter_visivel(request, pk)
    if not permissions.pode_despachar(request.user, solicitacao):
        raise PermissionDenied

    # Salvar apenas os ajustes de quantidade, sem decidir ainda.
    if request.POST.get("acao_despacho") == "salvar_ajustes":
        try:
            mudancas = services.salvar_ajustes_dg(
                solicitacao, request.user, _quantidades_dg_do_post(request, solicitacao)
            )
        except ValidationError as erro:
            for mensagem_erro in erro.messages:
                messages.error(request, mensagem_erro)
        else:
            if mudancas:
                messages.success(
                    request,
                    f"Ajustes salvos para a solicitação #{solicitacao.pk}: "
                    + "; ".join(mudancas) + ".",
                )
            else:
                messages.info(request, "Nenhuma alteração nas quantidades.")
        return redirect("solicitacoes:detalhe", pk=solicitacao.pk)

    form = DespachoForm(request.POST)
    if not form.is_valid():
        for erros_campo in form.errors.values():
            for erro in erros_campo:
                messages.error(request, erro)
        return redirect("solicitacoes:detalhe", pk=solicitacao.pk)
    if form.cleaned_data["decisao"] == DespachoForm.DEVOLVER:
        return _executar_transicao(
            request, solicitacao, services.devolver,
            f"Solicitação #{solicitacao.pk} devolvida para ajuste.",
            observacao=form.cleaned_data["observacao"],
        )
    # A DG aceita as quantidades propostas ou informa novas por equipe.
    return _executar_transicao(
        request, solicitacao, services.despachar,
        f"Decisão registrada para a solicitação #{solicitacao.pk}.",
        decisao=form.cleaned_data["decisao"],
        observacao=form.cleaned_data["observacao"],
        quantidades=_quantidades_dg_do_post(request, solicitacao),
    )
