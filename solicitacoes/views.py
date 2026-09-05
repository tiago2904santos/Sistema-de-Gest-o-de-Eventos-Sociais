from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Count, Q
from django.http import FileResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from .forms import (
    AnexoForm,
    DespachoForm,
    FiltroSolicitacoesForm,
    SolicitacaoForm,
    validar_arquivo_anexo,
)
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
    "descricao_complementar", "quantidade_servidores",
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


def _breadcrumb(titulo):
    """Trilha das telas de solicitação, sempre passando pela listagem."""
    return [
        {"label": "Solicitações", "url": reverse("solicitacoes:lista")},
        {"label": titulo},
    ]


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
        # Só aparece para quem pode decidir agora: fora disso a decisão da DG
        # já está no resumo, e um formulário desabilitado só confunde.
        "mostrar_despacho_dg": bool(solicitacao) and acoes.get("despachar", False),
        "anexos": list(solicitacao.anexos.select_related("enviado_por"))
        if solicitacao
        else [],
        "pode_gerenciar_anexos": acoes.get("gerenciar_anexos", False)
        if solicitacao
        else False,
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

def _criar_anexos_enviados(solicitacao, arquivos, usuario):
    for arquivo in arquivos:
        AnexoSolicitacao.objects.create(
            solicitacao=solicitacao,
            arquivo=arquivo,
            nome_original=arquivo.name,
            tamanho=arquivo.size,
            enviado_por=usuario,
        )


@login_required
def nova_solicitacao(request):
    """Tela "Nova Solicitação de Evento Social" com persistência real."""
    if request.method == "POST":
        acao = request.POST.get("acao", "rascunho")
        form = SolicitacaoForm(request.POST, enviar=(acao == "enviar"))
        arquivos = request.FILES.getlist("anexos")
        erros_anexos = [
            erro
            for erro in (validar_arquivo_anexo(arquivo) for arquivo in arquivos)
            if erro
        ]
        for erro in erros_anexos:
            messages.error(request, erro)
        if form.is_valid() and not erros_anexos:
            with transaction.atomic():
                solicitacao = form.save(criado_por=request.user)
                services.registrar_historico(
                    solicitacao, request.user, AcaoHistorico.CRIACAO,
                    status_novo=solicitacao.status,
                )
                _criar_anexos_enviados(solicitacao, arquivos, request.user)
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
    contexto["breadcrumb"] = _breadcrumb("Nova solicitação")
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
    contexto["breadcrumb"] = _breadcrumb(f"Editar #{solicitacao.pk}")
    return render(request, "pages/solicitacoes/form.html", contexto)


# ---------------------------------------------------------------------------
# Listagem e detalhe
# ---------------------------------------------------------------------------

# Filas = atalhos de status no mesmo escopo da tabela (todo mundo), exceto
# as pessoais, marcadas com "apenas_do_usuario" e rotuladas como "minhas".
FILAS = {
    "despacho": {
        "rotulo": "Aguardando despacho",
        "status": [StatusSolicitacao.AGUARDANDO_DESPACHO],
    },
    "devolvidas": {
        "rotulo": "Devolvidas para ajuste",
        "status": [StatusSolicitacao.DEVOLVIDA],
    },
    "andamento": {
        "rotulo": "Deferidas",
        "status": [StatusSolicitacao.DEFERIDA_EM_ANDAMENTO],
    },
    "canceladas": {
        "rotulo": "Canceladas",
        "status": [StatusSolicitacao.CANCELADA],
    },
    "rascunhos": {
        "rotulo": "Meus rascunhos",
        "status": [StatusSolicitacao.RASCUNHO],
        "apenas_do_usuario": True,
    },
    "minhas": {
        "rotulo": "Minhas",
        "apenas_do_usuario": True,
    },
}


def _filas_do_usuario(user, queryset):
    """Atalhos de fila com contagem, conforme o perfil do usuário."""
    # A fila de despacho é da DG; as pessoais valem para todos.
    filas = []
    if permissions.eh_gestor_dg(user):
        filas.append("despacho")
    filas.extend(["devolvidas", "andamento", "canceladas", "rascunhos", "minhas"])
    agregacoes = {}
    for chave in filas:
        config = FILAS[chave]
        condicao = Q()
        if config.get("status"):
            condicao &= Q(status__in=config["status"])
        if config.get("apenas_do_usuario"):
            condicao &= Q(criado_por=user)
        agregacoes[chave] = Count("pk", filter=condicao)
    totais = queryset.aggregate(**agregacoes)
    resultado = []
    for chave in filas:
        config = FILAS[chave]
        resultado.append(
            {
                "chave": chave,
                "rotulo": config["rotulo"],
                "total": totais[chave],
            }
        )
    return resultado


# Colunas ordenáveis da listagem: rótulo da URL -> campos do banco.
ORDENACOES = {
    "numero": ["pk"],
    "municipio": ["municipio__nome", "-data_solicitacao"],
    "tipo": ["tipo_evento__nome", "-data_solicitacao"],
    "periodo": ["data_inicio_evento", "-pk"],
    "solicitante": ["solicitante_nome", "-data_solicitacao"],
    "data": ["data_solicitacao", "-pk"],
    "status": ["status", "-data_solicitacao"],
}
ORDENACAO_PADRAO = "-data"

# Ordenações oferecidas no bottom sheet mobile (mesmas chaves de ORDENACOES).
ORDENACOES_MOBILE = [
    {"valor": "-data", "rotulo": "Mais recentes primeiro"},
    {"valor": "data", "rotulo": "Mais antigas primeiro"},
    {"valor": "periodo", "rotulo": "Evento mais próximo"},
    {"valor": "-numero", "rotulo": "Número (maior primeiro)"},
    {"valor": "municipio", "rotulo": "Município (A–Z)"},
    {"valor": "status", "rotulo": "Status (A–Z)"},
]


def _ordenacao(request):
    """Lê `ordem` da URL (com "-" para decrescente) e devolve (chave, campos)."""
    pedido = request.GET.get("ordem") or ORDENACAO_PADRAO
    decrescente = pedido.startswith("-")
    chave = pedido.lstrip("-")
    if chave not in ORDENACOES:
        pedido, decrescente, chave = ORDENACAO_PADRAO, True, "data"
    campos = ORDENACOES[chave]
    if decrescente:
        campos = [
            campo[1:] if campo.startswith("-") else f"-{campo}" for campo in campos
        ]
    return pedido, campos


def _queryset_filtrado(request):
    """Solicitações visíveis com fila e filtros da listagem aplicados."""
    filtros = FiltroSolicitacoesForm(request.GET or None)
    base = permissions.queryset_visivel(
        request.user,
        SolicitacaoEvento.objects.select_related(
            "municipio", "tipo_evento", "regiao", "criado_por"
        ),
    )
    _pedido, campos_ordem = _ordenacao(request)
    queryset = base.order_by(*campos_ordem)

    fila = request.GET.get("fila", "")
    if fila in FILAS:
        if FILAS[fila].get("status"):
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


CAMPOS_FILTRO = ["q", "status", "municipio", "tipo_evento", "inicio", "fim"]


def _colunas_ordenaveis(request, pedido):
    """Cabeçalhos com o link e a seta da próxima ordenação."""
    parametros = request.GET.copy()
    parametros.pop("pagina", None)
    parametros.pop("ordem", None)
    base = parametros.urlencode()
    atual = pedido.lstrip("-")
    decrescente = pedido.startswith("-")

    colunas = []
    # Ordem e classes das colunas seguem o padrão de listagem V3.2 aprovado.
    for chave, rotulo, classe in [
        ("numero", "Nº", "c-id"), ("status", "Status", "c-status"),
        ("tipo", "Tipo de evento", "c-tipo"), ("municipio", "Município", "c-mun"),
        ("periodo", "Período do evento", "c-per"), ("solicitante", "Solicitante", "c-sol"),
        ("data", "Data da solicitação", "c-data"),
    ]:
        ativa = chave == atual
        # Clicar na coluna ativa inverte; numa nova coluna começa crescente.
        proximo = f"-{chave}" if ativa and not decrescente else chave
        colunas.append({
            "chave": chave,
            "rotulo": rotulo,
            "classe": classe,
            "ativa": ativa,
            "descendente": ativa and decrescente,
            "url": f"?{base}&ordem={proximo}" if base else f"?ordem={proximo}",
        })
    return colunas


@login_required
def lista_solicitacoes(request):
    queryset, base, filtros, fila = _queryset_filtrado(request)
    pedido, _campos = _ordenacao(request)

    paginador = Paginator(queryset, ITENS_POR_PAGINA)
    pagina = paginador.get_page(request.GET.get("pagina"))
    # Números de página com reticências ("1 2 3 … 7") para pular direto.
    paginas_visiveis = list(
        paginador.get_elided_page_range(pagina.number, on_each_side=1, on_ends=1)
    )

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
            "total_geral": base.count(),
            "tem_filtros": any(request.GET.get(nome) for nome in CAMPOS_FILTRO),
            # Filtros além da busca: contagem exibida no botão "Filtros" do mobile.
            "filtros_ativos": sum(
                1 for nome in CAMPOS_FILTRO if nome != "q" and request.GET.get(nome)
            ),
            "ordenacoes_mobile": ORDENACOES_MOBILE,
            "ordem_atual": pedido,
            "total_resultados": paginador.count,
            "paginas_visiveis": paginas_visiveis,
            "elipse": Paginator.ELLIPSIS,
            "colunas": _colunas_ordenaveis(request, pedido),
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
        "Unidade móvel", "Qtde CIN", "Motorista",
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
            s.quantidade_cin or "",
            s.motorista or "",
            s.get_decisao_dg_display(),
            s.observacoes_dg,
            s.decidido_por or "",
            data(s.decidido_em, "%d/%m/%Y %H:%M"),
            s.criado_por,
        ])
    return resposta


def _despacho_pendente(request, solicitacao):
    """Decisão e observação que o gestor tentou registrar e não passaram."""
    pendente = request.session.pop("despacho_pendente", None)
    if not pendente or pendente.get("solicitacao") != solicitacao.pk:
        return None
    return pendente


@login_required
def detalhe_solicitacao(request, pk):
    solicitacao = _obter_visivel(request, pk)
    contexto = _contexto_formulario(
        request,
        SolicitacaoForm(instance=solicitacao),
        solicitacao,
    )
    acoes = permissions.acoes_permitidas(request.user, solicitacao)
    devolucao = (
        solicitacao.historico.filter(acao=AcaoHistorico.DEVOLUCAO).last()
        if solicitacao.status == StatusSolicitacao.DEVOLVIDA
        else None
    )
    contexto.update(
        {
            "titulo_pagina": f"Solicitação #{solicitacao.pk}",
            "breadcrumb": _breadcrumb(f"Solicitação #{solicitacao.pk}"),
            "subtitulo_pagina": "Resumo para despacho da Diretoria-Geral"
            if acoes["despachar"]
            else "Visualização completa da solicitação",
            "acoes": acoes,
            "historico": solicitacao.historico.all(),
            "somente_leitura": True,
            "dados_desabilitado": True,
            "planejamento_desabilitado": True,
            "mostrar_enviar": False,
            # Ler é ler: a página inteira vira resumo, nunca formulário.
            "modo_resumo": True,
            "itens_equipe": list(solicitacao.itens_equipe.select_related("equipe")),
            "motivo_devolucao": devolucao,
            "despacho_pendente": _despacho_pendente(request, solicitacao),
        }
    )
    return render(request, "pages/solicitacoes/detalhe.html", contexto)


# ---------------------------------------------------------------------------
# Transições de workflow (somente POST)
# ---------------------------------------------------------------------------

def _voltar_ao_despacho(request, solicitacao, decisao="", observacao=""):
    """Devolve o gestor à seção do despacho com o que ele já tinha escolhido."""
    request.session["despacho_pendente"] = {
        "solicitacao": solicitacao.pk,
        "decisao": decisao,
        "observacao": observacao,
    }
    url = reverse("solicitacoes:detalhe", args=[solicitacao.pk])
    return redirect(f"{url}#despacho-dg")


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


@login_required
@require_POST
def concluir_solicitacao(request, pk):
    """O solicitante confirma que o evento aconteceu e foi atendido."""
    solicitacao = _obter_visivel(request, pk)
    if not permissions.pode_concluir(request.user, solicitacao):
        raise PermissionDenied
    return _executar_transicao(
        request, solicitacao, services.concluir_atendimento,
        f"Atendimento da solicitação #{solicitacao.pk} confirmado.",
    )


@login_required
@require_POST
def cancelar_evento(request, pk):
    """Criador ou perfil institucional autorizado registra o cancelamento."""
    solicitacao = _obter_visivel(request, pk)
    if not permissions.pode_cancelar(request.user, solicitacao):
        raise PermissionDenied
    return _executar_transicao(
        request, solicitacao, services.cancelar_evento,
        f"Evento da solicitação #{solicitacao.pk} registrado como cancelado.",
        observacao=request.POST.get("motivo_cancelamento", ""),
    )


# ---------------------------------------------------------------------------
# Anexos
# ---------------------------------------------------------------------------

@login_required
@require_POST
def adicionar_anexo(request, pk):
    solicitacao = _obter_visivel(request, pk)
    if not permissions.pode_gerenciar_anexos(request.user, solicitacao):
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
    if not permissions.pode_gerenciar_anexos(request.user, solicitacao):
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
        return _voltar_ao_despacho(
            request,
            solicitacao,
            request.POST.get("decisao", ""),
            request.POST.get("observacao", ""),
        )

    decisao = form.cleaned_data["decisao"]
    observacao = form.cleaned_data["observacao"]
    try:
        if decisao == DespachoForm.DEVOLVER:
            services.devolver(solicitacao, request.user, observacao=observacao)
            sucesso = f"Solicitação #{solicitacao.pk} devolvida para ajuste."
        else:
            # A DG aceita as quantidades propostas ou informa novas por equipe.
            services.despachar(
                solicitacao,
                request.user,
                decisao=decisao,
                observacao=observacao,
                quantidades=_quantidades_dg_do_post(request, solicitacao),
            )
            sucesso = f"Decisão registrada para a solicitação #{solicitacao.pk}."
    except ValidationError as erro:
        for mensagem_erro in erro.messages:
            messages.error(request, mensagem_erro)
        return _voltar_ao_despacho(request, solicitacao, decisao, observacao)

    messages.success(request, sucesso)
    return redirect("solicitacoes:detalhe", pk=solicitacao.pk)
