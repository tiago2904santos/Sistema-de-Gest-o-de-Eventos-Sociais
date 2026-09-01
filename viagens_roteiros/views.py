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
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.http import urlencode
from django.views.decorators.http import require_POST

from auditoria.models import LogAuditoria

from cadastros.models import Estado, Municipio

from .forms import DestinoFormSet, RoteiroForm, TrechoFormSet
from .models import Roteiro
from .permissions import acesso_ao_modulo, pode_editar_roteiros
from .services.calculo import previa_diarias, recalcular_diarias
from .services.rota import RotaIndisponivel, calcular_rota
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
        destinos = DestinoFormSet(request.POST, instance=roteiro)
        rascunho = request.POST.get("acao") == "rascunho"
        if form.is_valid():
            salvo = form.save()
            # Rascunho é o roteiro em construção; salvar de vez o finaliza.
            salvo.status = (
                Roteiro.Status.RASCUNHO if rascunho else Roteiro.Status.FINALIZADO
            )
            salvo.save(update_fields=["status", "atualizado_em"])
            # Os formsets só sabem a que roteiro pertencem depois que ele existe.
            formset = TrechoFormSet(request.POST, instance=salvo)
            destinos = DestinoFormSet(request.POST, instance=salvo)
            if destinos.is_valid():
                destinos.save()
            if formset.is_valid():
                formset.save()
                _registrar_auditoria(
                    request.user,
                    "VIAGENS_ROTEIRO_ATUALIZADO" if pk else "VIAGENS_ROTEIRO_CRIADO",
                    salvo,
                )
                # O cálculo acompanha o salvamento, como no editor de
                # referência: quem preencheu o percurso vê o valor na hora.
                try:
                    resultado = recalcular_diarias(salvo)
                except (SemTabelaDeDiarias, RoteiroIncalculavel) as erro:
                    messages.success(request, "Roteiro salvo com sucesso.")
                    messages.info(request, f"Diárias ainda não calculadas: {erro}")
                else:
                    totais = resultado["totais"]
                    messages.success(
                        request,
                        "Roteiro salvo — diárias: "
                        f"R$ {totais['total_valor']} ({totais['resumo_diarias']}).",
                    )
                if rascunho:
                    # Rascunho continua em edição: quem salvou ainda está montando.
                    return redirect("viagens_roteiros:editar", pk=salvo.pk)
                return redirect("viagens_roteiros:detalhe", pk=salvo.pk)
            if not pk:
                # Trechos inválidos num roteiro recém-criado: ele já existe no
                # banco, então a tela continua a edição dele em vez de criar
                # outro na próxima tentativa.
                messages.error(request, "Corrija os trechos destacados para continuar.")
                return render(
                    request,
                    "pages/viagens_roteiros/form.html",
                    _contexto_do_form(salvo, form, formset, destinos),
                )
        else:
            formset = TrechoFormSet(request.POST, instance=roteiro)
            formset.is_valid()
        messages.error(request, "Corrija os campos destacados para continuar.")
    else:
        form = RoteiroForm(instance=roteiro)
        formset = TrechoFormSet(instance=roteiro)
        destinos = DestinoFormSet(instance=roteiro)

    return render(
        request,
        "pages/viagens_roteiros/form.html",
        _contexto_do_form(roteiro, form, formset, destinos),
    )


def _opcoes(iteravel):
    """Formato que `components/select.html` espera: valor + rótulo."""
    return [
        {"valor": str(getattr(item, "pk", item)), "rotulo": str(item)}
        for item in iteravel
    ]


def _opcoes_municipios(queryset):
    """Municípios com o estado no `data-parent-value`, para o filtro em cascata.

    O select do estado é só da tela: quem vai para o banco é o município.
    """
    return [
        {
            "valor": str(municipio.pk),
            "rotulo": municipio.nome,
            "estado": str(municipio.estado_id),
        }
        for municipio in queryset
    ]


def _valor_str(campo_bound):
    valor = campo_bound.value()
    return "" if valor is None else str(valor)


def _cards_de_trechos(formset):
    """Cada form do formset vira um card; os vazios ficam como slots ocultos.

    O botão "Adicionar trecho" da tela só revela o próximo slot — assim todo
    controle já nasce com o comportamento do design system ligado, sem DOM
    dinâmico.
    """
    cards = []
    for form_trecho in formset.forms:
        visivel = bool(form_trecho.instance.pk) or bool(form_trecho.errors)
        if not visivel and form_trecho.is_bound:
            visivel = any(
                form_trecho.data.get(f"{form_trecho.prefix}-{nome}")
                for nome in form_trecho.CAMPOS_DE_CONTEUDO
            )
        cards.append({"form": form_trecho, "visivel": visivel})
    return cards


def _cards_de_destinos(destinos):
    """Linhas de destino visíveis; slots vazios ficam ocultos até o "+"."""
    cards = []
    for form_destino in destinos.forms:
        visivel = bool(form_destino.instance.pk) or bool(form_destino.errors)
        if not visivel and form_destino.is_bound:
            visivel = bool(
                form_destino.data.get(f"{form_destino.prefix}-municipio")
            )
        cards.append({"form": form_destino, "visivel": visivel})
    return cards


def _contexto_do_form(roteiro, form, formset, destinos):
    return {
        "roteiro": roteiro,
        "form": form,
        "formset": formset,
        "destinos": destinos,
        "trechos_cards": _cards_de_trechos(formset),
        "destinos_cards": _cards_de_destinos(destinos),
        "opcoes_municipios": _opcoes_municipios(
            form.fields["origem_municipio"].queryset
        ),
        "opcoes_estados": _opcoes(
            Estado.objects.filter(municipios__ativo=True).distinct().order_by("nome")
        ),
        "opcoes_solicitacoes": _opcoes(form.fields["solicitacao"].queryset),
        "valores": {
            nome: _valor_str(form[nome]) for nome in form.fields
        },
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
def previa(request):
    """Prévia das diárias sobre o formulário como está, sem gravar.

    A tela chama a cada mudança relevante; a resposta é JSON porque o
    resultado atualiza só o bloco "Diárias" do editor.
    """
    _exigir_edicao(request)
    form = RoteiroForm(request.POST)
    formset = TrechoFormSet(request.POST)
    try:
        resultado = previa_diarias(form, formset)
    except (SemTabelaDeDiarias, RoteiroIncalculavel) as erro:
        return JsonResponse({"ok": False, "motivo": str(erro)})
    totais = resultado["totais"]
    # O tipo de destino sai das faixas efetivamente usadas (ex.: "Interior",
    # ou "Interior + Capital" num percurso misto).
    faixas = list(
        dict.fromkeys(t.get("tipo", "") for t in resultado["trechos"] if t.get("tipo"))
    )
    return JsonResponse(
        {
            "ok": True,
            "totais": {
                "total_valor": totais["total_valor"],
                "resumo_diarias": totais["resumo_diarias"],
                "valor_extenso": totais["valor_extenso"],
                "quantidade_servidores": totais["quantidade_servidores"],
                "valor_por_servidor": totais["valor_por_servidor"],
                "tipo_destino": " + ".join(faixas),
            },
        }
    )


@acesso_ao_modulo
@require_POST
def rota(request):
    """Rota do percurso no mapa: sede e destinos em ordem, ida e retorno.

    Recebe os ids dos municípios na ordem do percurso e devolve os totais,
    os segmentos (para preencher distância e tempo de viagem por trecho) e a
    geometria da linha. Nada é gravado.
    """
    _exigir_edicao(request)
    ids = [valor for valor in request.POST.getlist("municipios") if valor]
    municipios_por_id = {
        str(m.pk): m
        for m in Municipio.objects.filter(pk__in=ids).select_related("estado")
    }
    ordenados = [municipios_por_id[i] for i in ids if i in municipios_por_id]
    try:
        resultado = calcular_rota(ordenados)
    except RotaIndisponivel as erro:
        return JsonResponse({"ok": False, "motivo": str(erro)})
    resultado["ok"] = True
    return JsonResponse(resultado)


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
