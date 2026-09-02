"""Telas dos roteiros: montar, calcular e revisar.

O cálculo em si vive em ``services/`` — aqui só se decide quando chamá-lo e
como contar ao operador o que aconteceu. Quando ele recusa (falta vigência
cadastrada, faltam datas), a mensagem que sobe é a da exceção: ela já diz o que
fazer, e traduzi-la de novo aqui só criaria duas versões da mesma explicação.
"""

from contextlib import contextmanager

from django.contrib import messages
from django.core.paginator import Paginator
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.db.models import F, Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.http import urlencode
from django.views.decorators.http import require_POST

from auditoria.models import LogAuditoria

from cadastros.models import Estado, Municipio

from .forms import DestinoFormSet, RoteiroForm, TrechoFormSet
from .models import Roteiro
from .permissions import acesso_ao_modulo, pode_editar_roteiros
from .services.calculo import previa_diarias, recalcular_diarias
from .services.rota import (
    RotaIndisponivel,
    aplicar_rota_enviada,
    calcular_rota,
    conferir_rota_gravada,
    estimar_trecho as estimar_trecho_entre,
    rota_para_tela,
)
from .services.diarias import (
    RoteiroIncalculavel,
    SemTabelaDeDiarias,
    formatar_valor,
)

ITENS_POR_PAGINA = 20


def _exigir_edicao(request):
    if not pode_editar_roteiros(request.user):
        raise PermissionDenied


# Bem acima de qualquer ordem real; só serve para tirar as gravadas do caminho.
DESLOCAMENTO_DE_ORDEM = 1_000_000


@contextmanager
def _ordens_afastadas(roteiro):
    """Tira as ordens gravadas do caminho enquanto o formset valida e grava.

    Destino e trecho têm ordem única por roteiro. Renumerar o percurso troca
    ordens entre linhas, e uma linha nova pode assumir a ordem de outra que
    está sendo apagada no mesmo envio — o formset valida linha a linha
    contra o banco e recusava tudo. Com as ordens gravadas deslocadas para
    longe, cada linha assume a sua sem esbarrar em ninguém; o que não foi
    regravado volta ao lugar no fim.
    """
    roteiro.destinos.update(ordem=F("ordem") + DESLOCAMENTO_DE_ORDEM)
    roteiro.trechos.update(ordem=F("ordem") + DESLOCAMENTO_DE_ORDEM)
    try:
        yield
    finally:
        # O que ficou deslocado é linha que o envio não conhecia (não veio
        # com id). Volta à ordem original se ela ainda está livre; senão vai
        # para depois da última, sem derrubar a gravação.
        for relacao in (roteiro.destinos, roteiro.trechos):
            deslocados = list(
                relacao.filter(ordem__gte=DESLOCAMENTO_DE_ORDEM).order_by("ordem")
            )
            if not deslocados:
                continue
            ocupadas = set(
                relacao.filter(ordem__lt=DESLOCAMENTO_DE_ORDEM).values_list(
                    "ordem", flat=True
                )
            )
            proxima = (max(ocupadas) if ocupadas else 0) + 1
            for linha in deslocados:
                original = linha.ordem - DESLOCAMENTO_DE_ORDEM
                if original in ocupadas:
                    linha.ordem = proxima
                    proxima += 1
                else:
                    linha.ordem = original
                ocupadas.add(linha.ordem)
                linha.save(update_fields=["ordem"])


def _sem_identidade(post):
    """O POST do editor sem os ids das linhas nem a contagem de iniciais."""
    dados = post.copy()
    for chave in list(dados.keys()):
        # `-roteiro` é a chave estrangeira que o formset inline emite: com
        # valor, ela precisa bater com o pai — que a prévia não tem.
        if chave.endswith("-id") or chave.endswith("-roteiro"):
            dados[chave] = ""
        elif chave.endswith("-INITIAL_FORMS"):
            dados[chave] = "0"
    return dados


def _sanear_ids(post, roteiro):
    """Esquece, no POST, os ids de destinos e trechos que já não existem.

    A tela grava sozinha enquanto se monta o percurso, e uma gravação pode
    apagar linhas que a tela ainda carrega ocultas, marcadas para exclusão,
    com o id antigo. Para o formset um id inexistente é "escolha inválida" —
    e a gravação seguinte inteira falhava por causa de uma linha que já não
    era nada. Sem o id, a linha vira slot novo: em branco ou marcada para
    exclusão, é ignorada.
    """
    if not (roteiro and roteiro.pk):
        return post
    post = post.copy()
    existentes = {
        "destinos": {str(pk) for pk in roteiro.destinos.values_list("pk", flat=True)},
        "trechos": {str(pk) for pk in roteiro.trechos.values_list("pk", flat=True)},
    }
    for chave in list(post.keys()):
        partes = chave.split("-")
        if len(partes) != 3 or partes[2] != "id" or partes[0] not in existentes:
            continue
        if post[chave] and post[chave] not in existentes[partes[0]]:
            post[chave] = ""
    return post


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
        dados = _sanear_ids(request.POST, roteiro)
        form = RoteiroForm(dados, instance=roteiro)
        formset = TrechoFormSet(dados, instance=roteiro)
        destinos = DestinoFormSet(dados, instance=roteiro)
        rascunho = dados.get("acao") == "rascunho"
        if form.is_valid():
            salvo = form.save(commit=False)
            # Rascunho é o roteiro em construção; salvar de vez o finaliza.
            salvo.status = (
                Roteiro.Status.RASCUNHO if rascunho else Roteiro.Status.FINALIZADO
            )
            # A rota que a tela calculou viaja em campos ocultos e fica
            # gravada com o roteiro, para o mapa reabrir desenhado.
            aplicar_rota_enviada(salvo, dados)
            salvo.save()
            # Os formsets só sabem a que roteiro pertencem depois que ele existe.
            formset = TrechoFormSet(dados, instance=salvo)
            destinos = DestinoFormSet(dados, instance=salvo)
            with transaction.atomic(), _ordens_afastadas(salvo):
                if destinos.is_valid():
                    destinos.save()
                conferir_rota_gravada(salvo)
                trechos_ok = formset.is_valid()
                if trechos_ok:
                    formset.save()
            if trechos_ok:
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
                # Finalizado, o trabalho acabou: volta para a lista.
                return redirect("viagens_roteiros:lista")
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
            formset = TrechoFormSet(dados, instance=roteiro)
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


def _opcoes_roteiros_base(atual):
    """Roteiros salvos que podem servir de base, do mais recente para trás."""
    queryset = (
        Roteiro.objects.select_related("origem_municipio")
        .prefetch_related("destinos__municipio")
        .filter(cancelado=False)
        .order_by("-atualizado_em")
    )
    if atual and atual.pk:
        queryset = queryset.exclude(pk=atual.pk)
    opcoes = []
    for roteiro in queryset[:200]:
        destinos = [
            destino.municipio.nome
            for destino in roteiro.destinos.all()
            if destino.municipio_id
        ]
        percurso = " → ".join(destinos) if destinos else "sem destinos"
        sede = roteiro.origem_municipio.nome if roteiro.origem_municipio_id else "sem sede"
        opcoes.append(
            {"valor": str(roteiro.pk), "rotulo": f"#{roteiro.pk} · {sede} → {percurso}"}
        )
    return opcoes


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
        # Roteiros já cadastrados, para repetir um percurso conhecido em vez
        # de remontá-lo. Fora o próprio, que não serve de base para si mesmo.
        "opcoes_roteiros_base": _opcoes_roteiros_base(roteiro),
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
        # A composição parcela a parcela do último cálculo gravado: é o que
        # explica o valor depois, quando os valores vigentes já forem outros.
        # Vive aqui desde que a tela de detalhe deixou de existir.
        "parcelas": (
            roteiro.componentes_diarias.select_related("tabela_diaria").all()
            if roteiro and roteiro.pk
            else []
        ),
        "total_formatado": (
            f"R$ {formatar_valor(roteiro.valor_diarias)}"
            if roteiro and roteiro.valor_diarias is not None
            else "—"
        ),
        # A rota gravada, para o mapa reabrir desenhado; e os endereços que a
        # tela usa enquanto se monta o percurso.
        "rota_inicial": rota_para_tela(roteiro),
        "url_autosave": (
            reverse("viagens_roteiros:autosave", args=[roteiro.pk])
            if roteiro and roteiro.pk
            else reverse("viagens_roteiros:autosave_novo")
        ),
        # A gravação automática só vale enquanto o roteiro é rascunho: um
        # roteiro finalizado tem diárias congeladas que um trecho mexido em
        # silêncio deixaria mentindo. Nele, só o "Salvar" grava.
        "autosave_ligado": not (
            roteiro and roteiro.pk and roteiro.status == Roteiro.Status.FINALIZADO
        ),
        "titulo": "Editar roteiro" if roteiro and roteiro.pk else "Novo roteiro",
        "url_voltar": reverse("viagens_roteiros:lista"),
        "breadcrumb": [
            {"label": "Roteiros", "url": reverse("viagens_roteiros:lista")},
            {"label": "Editar roteiro" if roteiro and roteiro.pk else "Novo roteiro"},
        ],
    }


@acesso_ao_modulo
def dados_do_roteiro(request, pk):
    """Sede e destinos de um roteiro salvo, para reaproveitar na montagem.

    A tela usa isto quando se escolhe um roteiro como base: ela repete o
    percurso dele — sede e destinos, na ordem — e o operador ajusta datas e
    horários. Nada é copiado no banco; o roteiro novo nasce independente.
    """
    roteiro = get_object_or_404(
        Roteiro.objects.select_related("origem_municipio__estado"), pk=pk
    )
    destinos = roteiro.destinos.select_related("municipio__estado").all()
    return JsonResponse(
        {
            "sede": (
                {
                    "municipio": roteiro.origem_municipio_id,
                    "estado": roteiro.origem_municipio.estado_id,
                }
                if roteiro.origem_municipio_id
                else None
            ),
            "destinos": [
                {
                    "municipio": destino.municipio_id,
                    "estado": destino.municipio.estado_id,
                }
                for destino in destinos
            ],
        }
    )


@acesso_ao_modulo
@require_POST
def previa(request):
    """Prévia das diárias sobre o formulário como está, sem gravar.

    A tela chama a cada mudança relevante; a resposta é JSON porque o
    resultado atualiza só o bloco "Diárias" do editor.
    """
    _exigir_edicao(request)
    # Como se tudo fosse novo: a prévia não grava e não precisa saber quais
    # linhas existem — e, sem o roteiro, um id de trecho gravado seria
    # "escolha inválida" e derrubaria a linha da conta.
    dados = _sem_identidade(request.POST)
    form = RoteiroForm(dados)
    formset = TrechoFormSet(dados)
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
def estimar_trecho(request):
    """Distância e tempo de viagem de um trecho, para a tabela se preencher.

    A tela chama uma vez por trecho ainda sem tempo assim que sede e destinos
    existem. Nada é gravado.
    """
    _exigir_edicao(request)
    ids = [request.POST.get("origem") or "", request.POST.get("destino") or ""]
    if not all(ids):
        return JsonResponse({"ok": False, "motivo": "Informe origem e destino."})
    municipios = {
        str(m.pk): m
        for m in Municipio.objects.filter(pk__in=ids).select_related("estado")
    }
    if ids[0] not in municipios or ids[1] not in municipios:
        return JsonResponse({"ok": False, "motivo": "Município não encontrado."})
    try:
        resultado = estimar_trecho_entre(municipios[ids[0]], municipios[ids[1]])
    except RotaIndisponivel as erro:
        return JsonResponse({"ok": False, "motivo": str(erro)})
    return JsonResponse(dict(resultado, ok=True))


def _ids_gravados(formset):
    """`prefixo-N-id` → pk, para a tela aprender os ids que acabou de criar."""
    return {
        f"{form.prefix}-id": form.instance.pk
        for form in formset.forms
        if form.instance.pk and not form.cleaned_data.get("DELETE")
    }


@acesso_ao_modulo
@require_POST
def autosave(request, pk=None):
    """Grava o rascunho como está, sem sair da tela.

    A tela envia o formulário inteiro um segundo depois da última mudança. O
    roteiro nasce na primeira gravação — a resposta traz o endereço de edição
    e os ids dos destinos e trechos criados, para a tela passar a editá-los
    em vez de recriá-los. Um roteiro finalizado não recebe gravação
    automática: as diárias dele estão congeladas, e mexer nos trechos por
    baixo delas as deixaria mentindo.
    """
    _exigir_edicao(request)
    roteiro = get_object_or_404(Roteiro, pk=pk) if pk else None
    if roteiro and roteiro.status == Roteiro.Status.FINALIZADO:
        return JsonResponse(
            {"ok": False, "motivo": "Roteiro finalizado: grave pelo \u201cSalvar\u201d."}
        )
    dados = _sanear_ids(request.POST, roteiro)
    form = RoteiroForm(dados, instance=roteiro)
    if not form.is_valid():
        return JsonResponse({"ok": False, "motivo": "Corrija os campos destacados."})
    with transaction.atomic():
        salvo = form.save(commit=False)
        salvo.status = Roteiro.Status.RASCUNHO
        aplicar_rota_enviada(salvo, dados)
        salvo.save()
        destinos = DestinoFormSet(dados, instance=salvo)
        formset = TrechoFormSet(dados, instance=salvo)
        ids = {}
        with _ordens_afastadas(salvo):
            gravou = {"destinos": destinos.is_valid(), "trechos": formset.is_valid()}
            if gravou["destinos"]:
                destinos.save()
                ids.update(_ids_gravados(destinos))
            conferir_rota_gravada(salvo)
            if gravou["trechos"]:
                formset.save()
                ids.update(_ids_gravados(formset))
        if not pk:
            _registrar_auditoria(request.user, "VIAGENS_ROTEIRO_CRIADO", salvo)
    # O que não passou fica dito: a tela avisa que o rascunho está parcial.
    pendencias = []
    if not gravou["trechos"]:
        pendencias.append("os trechos não foram gravados (revise datas e destinos)")
    if not gravou["destinos"]:
        pendencias.append("os destinos não foram gravados")
    return JsonResponse(
        {
            "ok": True,
            "pk": salvo.pk,
            "criado": not pk,
            "url_editar": reverse("viagens_roteiros:editar", args=[salvo.pk]),
            "url_autosave": reverse("viagens_roteiros:autosave", args=[salvo.pk]),
            "url_voltar": reverse("viagens_roteiros:lista"),
            "ids": ids,
            "gravou": gravou,
            "motivo": "; ".join(pendencias),
            "rota_status": salvo.rota_status,
            "salvo_em": timezone.localtime().strftime("%H:%M"),
        }
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
    return redirect("viagens_roteiros:editar", pk=roteiro.pk)


@acesso_ao_modulo
@require_POST
def cancelar(request, pk):
    _exigir_edicao(request)
    roteiro = get_object_or_404(Roteiro, pk=pk)
    motivo = request.POST.get("motivo", "").strip()
    if not motivo:
        messages.error(request, "Informe o motivo do cancelamento.")
        return redirect("viagens_roteiros:editar", pk=roteiro.pk)
    roteiro.cancelar(motivo)
    _registrar_auditoria(request.user, "VIAGENS_ROTEIRO_CANCELADO", roteiro)
    messages.success(request, "Roteiro cancelado.")
    return redirect("viagens_roteiros:editar", pk=roteiro.pk)


@acesso_ao_modulo
@require_POST
def reativar(request, pk):
    _exigir_edicao(request)
    roteiro = get_object_or_404(Roteiro, pk=pk)
    roteiro.reativar()
    _registrar_auditoria(request.user, "VIAGENS_ROTEIRO_REATIVADO", roteiro)
    messages.success(request, "Roteiro reativado.")
    return redirect("viagens_roteiros:editar", pk=roteiro.pk)


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
