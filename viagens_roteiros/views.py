"""Telas dos roteiros: montar, calcular e revisar.

O cálculo em si vive em ``services/`` — aqui só se decide quando chamá-lo e
como contar ao operador o que aconteceu. Quando ele recusa (falta vigência
cadastrada, faltam datas), a mensagem que sobe é a da exceção: ela já diz o que
fazer, e traduzi-la de novo aqui só criaria duas versões da mesma explicação.
"""

from django.contrib import messages
from django.core.paginator import Paginator
from django.core.exceptions import PermissionDenied
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.http import urlencode
from django.views.decorators.http import require_POST

from auditoria.models import LogAuditoria

from .forms import RoteiroForm, TrechoFormSet
from .models import Roteiro
from .permissions import acesso_ao_modulo, pode_editar_roteiros
from .services.calculo import recalcular_diarias
from .services.diarias import (
    RoteiroIncalculavel,
    SemTabelaDeDiarias,
    formatar_valor,
)

ITENS_POR_PAGINA = 20


def _exigir_edicao(request):
    if not pode_editar_roteiros(request.user):
        raise PermissionDenied


def _registrar_auditoria(usuario, acao, roteiro):
    LogAuditoria.objects.create(
        usuario=usuario,
        acao=acao,
        descricao=f"roteiro {roteiro.pk} ({roteiro.sede_cidade or 'sem sede'})",
    )


def _resumo_do_destino(roteiro):
    """Para onde se foi, na ordem — o que identifica o roteiro na lista."""
    nomes = [
        trecho.destino_municipio.nome
        for trecho in roteiro.trechos.all()
        if trecho.destino_municipio_id
    ]
    # A volta à sede não é destino: repetir a sede no fim polui a lista.
    if len(nomes) > 1 and nomes[-1] == roteiro.sede_cidade:
        nomes = nomes[:-1]
    return " → ".join(nomes) if nomes else "—"


@acesso_ao_modulo
def lista(request):
    queryset = (
        Roteiro.objects.select_related("origem_municipio__estado")
        .prefetch_related("trechos__destino_municipio")
        .all()
    )
    termo = request.GET.get("q", "").strip()
    if termo:
        queryset = queryset.filter(
            Q(origem_municipio__nome__icontains=termo)
            | Q(trechos__destino_municipio__nome__icontains=termo)
            | Q(observacoes__icontains=termo)
        ).distinct()
    situacao = request.GET.get("situacao", "").strip()
    if situacao == "ativos":
        queryset = queryset.filter(cancelado=False)
    elif situacao == "cancelados":
        queryset = queryset.filter(cancelado=True)

    paginator = Paginator(queryset, ITENS_POR_PAGINA)
    pagina = paginator.get_page(request.GET.get("pagina"))

    linhas = [
        {
            "roteiro": roteiro,
            "destinos": _resumo_do_destino(roteiro),
            "icone": "document" if roteiro.solicitacao_id else "map-pin",
        }
        for roteiro in pagina
    ]
    parametros = {}
    if termo:
        parametros["q"] = termo
    if situacao:
        parametros["situacao"] = situacao

    return render(
        request,
        "pages/viagens_roteiros/lista.html",
        {
            "pagina": pagina,
            "linhas": linhas,
            "termo": termo,
            "situacao": situacao,
            "tem_filtros": bool(termo or situacao),
            "pode_editar": pode_editar_roteiros(request.user),
            "opcoes_situacao": [
                {"valor": "ativos", "rotulo": "Ativos"},
                {"valor": "cancelados", "rotulo": "Cancelados"},
            ],
            "querystring": urlencode(parametros),
            "paginas_visiveis": list(
                paginator.get_elided_page_range(pagina.number, on_each_side=2, on_ends=1)
            ),
            "elipse": paginator.ELLIPSIS,
        },
    )


@acesso_ao_modulo
def editar(request, pk=None):
    _exigir_edicao(request)
    roteiro = get_object_or_404(Roteiro, pk=pk) if pk else None

    if request.method == "POST":
        form = RoteiroForm(request.POST, instance=roteiro)
        formset = TrechoFormSet(request.POST, instance=roteiro)
        if form.is_valid():
            salvo = form.save()
            # O formset só sabe a que roteiro pertence depois que ele existe.
            formset = TrechoFormSet(request.POST, instance=salvo)
            if formset.is_valid():
                formset.save()
                _registrar_auditoria(
                    request.user,
                    "VIAGENS_ROTEIRO_ATUALIZADO" if pk else "VIAGENS_ROTEIRO_CRIADO",
                    salvo,
                )
                messages.success(request, "Roteiro salvo com sucesso.")
                return redirect("viagens_roteiros:detalhe", pk=salvo.pk)
            if not pk:
                # Trechos inválidos num roteiro recém-criado: ele já existe no
                # banco, então a tela continua a edição dele em vez de criar
                # outro na próxima tentativa.
                messages.error(request, "Corrija os trechos destacados para continuar.")
                return render(
                    request,
                    "pages/viagens_roteiros/form.html",
                    _contexto_do_form(salvo, form, formset),
                )
        else:
            formset = TrechoFormSet(request.POST, instance=roteiro)
            formset.is_valid()
        messages.error(request, "Corrija os campos destacados para continuar.")
    else:
        form = RoteiroForm(instance=roteiro)
        formset = TrechoFormSet(instance=roteiro)

    return render(
        request,
        "pages/viagens_roteiros/form.html",
        _contexto_do_form(roteiro, form, formset),
    )


def _contexto_do_form(roteiro, form, formset):
    return {
        "roteiro": roteiro,
        "form": form,
        "formset": formset,
        # Um roteiro recém-criado cujos trechos não passaram continua sendo
        # editado no endereço dele. Reenviar para /novo/ criaria um segundo
        # roteiro a cada correção.
        "url_acao": (
            reverse("viagens_roteiros:editar", args=[roteiro.pk])
            if roteiro and roteiro.pk
            else ""
        ),
        "titulo": "Editar roteiro" if roteiro and roteiro.pk else "Novo roteiro",
        "url_voltar": (
            reverse("viagens_roteiros:detalhe", args=[roteiro.pk])
            if roteiro and roteiro.pk
            else reverse("viagens_roteiros:lista")
        ),
        "breadcrumb": [
            {"label": "Roteiros", "url": reverse("viagens_roteiros:lista")},
            {"label": "Editar roteiro" if roteiro and roteiro.pk else "Novo roteiro"},
        ],
    }


@acesso_ao_modulo
def detalhe(request, pk):
    roteiro = get_object_or_404(
        Roteiro.objects.select_related("origem_municipio__estado", "solicitacao"), pk=pk
    )
    trechos = roteiro.trechos.select_related(
        "origem_municipio", "destino_municipio"
    ).all()
    parcelas = roteiro.componentes_diarias.select_related("tabela_diaria").all()
    equipe = roteiro.quantidade_servidores
    return render(
        request,
        "pages/viagens_roteiros/detalhe.html",
        {
            "roteiro": roteiro,
            "trechos": trechos,
            "parcelas": parcelas,
            "destinos": _resumo_do_destino(roteiro),
            "total_formatado": (
                f"R$ {formatar_valor(roteiro.valor_diarias)}"
                if roteiro.valor_diarias is not None
                else "—"
            ),
            "resumo_equipe": f"{equipe} servidor{'es' if equipe != 1 else ''}",
            "rotulo_vinculo": (
                f"Solicitação {roteiro.solicitacao_id}"
                if roteiro.solicitacao_id
                else "Avulso"
            ),
            "detalhe_vinculo": (
                "Roteiro de solicitação de evento"
                if roteiro.solicitacao_id
                else "Sem solicitação vinculada"
            ),
            "breadcrumb": [
                {"label": "Roteiros", "url": reverse("viagens_roteiros:lista")},
                {"label": _resumo_do_destino(roteiro)},
            ],
            "pode_editar": pode_editar_roteiros(request.user),
        },
    )


@acesso_ao_modulo
@require_POST
def calcular(request, pk):
    _exigir_edicao(request)
    roteiro = get_object_or_404(Roteiro, pk=pk)
    try:
        resultado = recalcular_diarias(roteiro)
    except (SemTabelaDeDiarias, RoteiroIncalculavel) as erro:
        # A exceção já explica o que falta; repetir a explicação aqui criaria
        # duas versões da mesma mensagem.
        messages.error(request, str(erro))
    else:
        _registrar_auditoria(request.user, "VIAGENS_ROTEIRO_CALCULADO", roteiro)
        messages.success(
            request,
            "Diárias calculadas: R$ "
            f"{resultado['totais']['total_valor']} "
            f"({resultado['totais']['resumo_diarias']}).",
        )
    return redirect("viagens_roteiros:detalhe", pk=roteiro.pk)


@acesso_ao_modulo
@require_POST
def cancelar(request, pk):
    _exigir_edicao(request)
    roteiro = get_object_or_404(Roteiro, pk=pk)
    motivo = request.POST.get("motivo", "").strip()
    if not motivo:
        messages.error(request, "Informe o motivo do cancelamento.")
        return redirect("viagens_roteiros:detalhe", pk=roteiro.pk)
    roteiro.cancelar(motivo)
    _registrar_auditoria(request.user, "VIAGENS_ROTEIRO_CANCELADO", roteiro)
    messages.success(request, "Roteiro cancelado.")
    return redirect("viagens_roteiros:detalhe", pk=roteiro.pk)


@acesso_ao_modulo
@require_POST
def reativar(request, pk):
    _exigir_edicao(request)
    roteiro = get_object_or_404(Roteiro, pk=pk)
    roteiro.reativar()
    _registrar_auditoria(request.user, "VIAGENS_ROTEIRO_REATIVADO", roteiro)
    messages.success(request, "Roteiro reativado.")
    return redirect("viagens_roteiros:detalhe", pk=roteiro.pk)


@acesso_ao_modulo
@require_POST
def excluir(request, pk):
    _exigir_edicao(request)
    roteiro = get_object_or_404(Roteiro, pk=pk)
    descricao = f"roteiro {roteiro.pk} ({roteiro.sede_cidade or 'sem sede'})"
    roteiro.delete()
    LogAuditoria.objects.create(
        usuario=request.user, acao="VIAGENS_ROTEIRO_EXCLUIDO", descricao=descricao
    )
    messages.success(request, "Roteiro excluído.")
    return redirect("viagens_roteiros:lista")
