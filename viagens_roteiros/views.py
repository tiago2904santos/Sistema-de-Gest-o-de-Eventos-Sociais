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
from .presenters import linhas_do_calculo
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


@acesso_ao_modulo
def lista(request):
    from core.retorno import com_next, daqui

    from . import abas as abas_de_roteiro
    from .presenters import linha_da_lista

    base = abas_de_roteiro.anotar_finalizacao(
        Roteiro.objects.select_related("origem_municipio__estado").prefetch_related(
            "trechos__destino_municipio__estado"
        )
    )
    termo = request.GET.get("q", "").strip()
    if termo:
        base = base.filter(
            Q(origem_municipio__nome__icontains=termo)
            | Q(trechos__destino_municipio__nome__icontains=termo)
            | Q(observacoes__icontains=termo)
        ).distinct()

    # As situações são combináveis e nenhuma marcada significa "todas" — é o
    # comportamento da origem, e o que permite achar o roteiro da página 3.
    escolhidas = abas_de_roteiro.normalizar_abas(request.GET.getlist("aba"))
    filtro = abas_de_roteiro.q_das_abas(escolhidas)
    queryset = base.filter(filtro) if filtro is not None else base

    paginator = Paginator(queryset, ITENS_POR_PAGINA)
    pagina = paginator.get_page(request.GET.get("pagina"))

    volta = daqui(request)
    linhas = [
        linha_da_lista(
            roteiro,
            editar_url=com_next(
                reverse("viagens_roteiros:editar", args=[roteiro.pk]), volta
            ),
            excluir_url=reverse("viagens_roteiros:excluir", args=[roteiro.pk]),
        )
        for roteiro in pagina
    ]
    parametros = request.GET.copy()
    parametros.pop("pagina", None)

    # Situações como chips da trilha, iguais às tabelas de apoio dos cadastros:
    # cada chip troca só a situação e mantém a busca.
    contagem = abas_de_roteiro.contar_por_aba(base)

    def url_da_situacao(aba=None):
        destino = parametros.copy()
        destino.pop("aba", None)
        if aba:
            destino["aba"] = aba
        return "?" + destino.urlencode()

    icones = {
        abas_de_roteiro.ABA_FUTURAS: "calendar",
        abas_de_roteiro.ABA_ATUAIS: "clock",
        abas_de_roteiro.ABA_FINALIZADOS: "check-circle",
        abas_de_roteiro.ABA_CANCELADOS: "ban",
    }
    situacoes = [{"slug": "todas", "titulo": "Todas", "total": base.count(), "icone": "checklist", "url": url_da_situacao()}] + [
        {"slug": chave, "titulo": rotulo, "total": contagem[chave], "icone": icones[chave], "url": url_da_situacao(chave)}
        for chave, rotulo in abas_de_roteiro.ABA_ROTULOS
    ]

    return render(
        request,
        "pages/viagens_roteiros/lista.html",
        {
            "pagina": pagina,
            "linhas": linhas,
            "termo": termo,
            "abas": abas_de_roteiro.opcoes_de_aba(base, escolhidas, contagem),
            "abas_escolhidas": escolhidas,
            "situacoes": situacoes,
            # Chip aceso: nenhuma situação é "Todas"; várias (link antigo) não acendem nenhum.
            "situacao_ativa": "todas" if not escolhidas else escolhidas[0] if len(escolhidas) == 1 else "",
            "tem_filtros": bool(termo or escolhidas),
            "pode_editar": pode_editar_roteiros(request.user),
            "querystring": parametros.urlencode(),
            "paginas_visiveis": list(
                paginator.get_elided_page_range(pagina.number, on_each_side=2, on_ends=1)
            ),
            "elipse": paginator.ELLIPSIS,
        },
    )


def _sede_inicial(request, roteiro):
    """Roteiro novo já nasce com a sede das configurações.

    A sede da unidade é o município do endereço (cidade e UF vindas do CEP)
    gravado em Configurações. Continua editável: a viagem pode sair de outro lugar.
    """
    if roteiro is not None:
        return None
    from viagens_cadastros.models import ConfiguracaoSistema

    sede = ConfiguracaoSistema.para_usuario(request.user).cidade_sede_padrao_id
    return {"origem_municipio": sede} if sede else None


def historico_do_roteiro(roteiro):
    from auditoria.historico import historico_de
    return historico_de(
        roteiro,
        filhos=(("viagens_roteiros.roteirodestino", "roteiro"), ("viagens_roteiros.roteirotrecho", "roteiro")),
        sobre_filhos={"viagens_roteiros.roteirodestino": "Destino", "viagens_roteiros.roteirotrecho": "Trecho"},
    )


class GravacaoDoEditor:
    """O que sobrou de uma gravação do editor: o roteiro, os formulários
    (com os erros, quando houver) e o que dizer ao operador."""

    def __init__(self, roteiro, form, formset, destinos):
        self.roteiro = roteiro
        self.form = form
        self.formset = formset
        self.destinos = destinos
        self.ok = False
        self.mensagens = []  # (nível, texto)


def gravar_editor(dados, roteiro, *, rascunho, usuario):
    """Grava o POST do editor de roteiro: sede, destinos, trechos e a rota.

    É o salvamento da tela de roteiros, também usado pelo cadastro de ofício,
    que embute o mesmo editor. ``ok`` só é verdadeiro com trechos válidos; um
    roteiro novo cujos trechos falharam já existe no banco e volta em
    ``roteiro`` para a edição continuar nele.
    """
    dados = _sanear_ids(dados, roteiro)
    form = RoteiroForm(dados, instance=roteiro)
    formset = TrechoFormSet(dados, instance=roteiro)
    destinos = DestinoFormSet(dados, instance=roteiro)
    resultado = GravacaoDoEditor(roteiro, form, formset, destinos)
    if not form.is_valid():
        formset.is_valid()
        return resultado
    novo = not (roteiro and roteiro.pk)
    salvo = form.save(commit=False)
    # Rascunho é o roteiro em construção; salvar de vez o finaliza.
    salvo.status = Roteiro.Status.RASCUNHO if rascunho else Roteiro.Status.FINALIZADO
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
            salvo.sincronizar_periodo()
    resultado.roteiro, resultado.formset, resultado.destinos = salvo, formset, destinos
    if not trechos_ok:
        return resultado
    resultado.ok = True
    _registrar_auditoria(
        usuario, "VIAGENS_ROTEIRO_CRIADO" if novo else "VIAGENS_ROTEIRO_ATUALIZADO", salvo
    )
    # O cálculo acompanha o salvamento, como no editor de referência: quem
    # preencheu o percurso vê o valor na hora.
    try:
        calculo = recalcular_diarias(salvo)
    except (SemTabelaDeDiarias, RoteiroIncalculavel) as erro:
        resultado.mensagens.append((messages.INFO, f"Diárias ainda não calculadas: {erro}"))
    else:
        totais = calculo["totais"]
        resultado.mensagens.append((
            messages.SUCCESS,
            f"Diárias: R$ {totais['total_valor']} ({totais['resumo_diarias']}).",
        ))
    return resultado


def _url_de_volta(roteiro, viagem=None):
    """Para onde se volta ao sair do roteiro: a etapa 2 da viagem dele, ou a lista."""
    viagem_id = getattr(viagem, "pk", None) or getattr(roteiro, "viagem_id", None)
    if viagem_id:
        return reverse("viagens_viagem:etapa", args=[viagem_id, 2])
    return reverse("viagens_roteiros:lista")


def _iniciais_da_viagem(viagem, sede):
    """O que um roteiro novo herda da viagem: os destinos (todos) e o percurso
    com as datas — saída no primeiro dia (horário inicial ou 08:00) e retorno
    no último (horário final ou 16:00). Devolve (destinos, trechos) para os
    formsets; a tela mostra os trechos já datados e estima os tempos."""
    from datetime import time

    from viagens_viagem.services import destinos_para_formulario, semente_de_documentos

    semente = semente_de_documentos(viagem)
    destinos = [{"ordem": i + 1, "municipio": municipio_id} for i, (_, municipio_id) in enumerate(destinos_para_formulario(semente))]
    if not destinos:
        return [], []
    inicio, fim = semente["data_inicio"], semente["data_fim"] or semente["data_inicio"]
    saida = (viagem.horario_inicio or time(8, 0)).strftime("%H:%M") if inicio else ""
    retorno = (viagem.horario_fim or time(16, 0)).strftime("%H:%M") if fim else ""
    trechos, anterior = [], sede
    for destino in destinos:
        if anterior:
            trechos.append({"ordem": len(trechos) + 1, "sentido": "IDA", "origem_municipio": anterior, "destino_municipio": destino["municipio"],
                            "saida_data": inicio.isoformat() if inicio else "", "saida_hora": saida})
        anterior = destino["municipio"]
    if sede:
        trechos.append({"ordem": len(trechos) + 1, "sentido": "RETORNO", "origem_municipio": anterior, "destino_municipio": sede,
                        "saida_data": fim.isoformat() if fim else "", "saida_hora": retorno})
    return destinos, trechos


def _datas_da_viagem(viagem):
    """As pontas da viagem para a tela: sem sede configurada o servidor não
    monta os trechos, e é o editor que datará os que nascerem ali."""
    from datetime import time

    if viagem is None:
        return {}
    inicio, fim = viagem.data_inicio, viagem.data_fim or viagem.data_inicio
    return {
        "inicio": inicio.isoformat() if inicio else "",
        "fim": fim.isoformat() if fim else "",
        "hora_inicio": (viagem.horario_inicio or time(8, 0)).strftime("%H:%M") if inicio else "",
        "hora_fim": (viagem.horario_fim or time(16, 0)).strftime("%H:%M") if fim else "",
    }


def _formset_com_iniciais(classe, iniciais):
    """Um formset novo já com `iniciais` linhas preenchidas (uma extra por linha)."""
    formset = classe(instance=None, initial=iniciais)
    formset.extra = max(1, len(iniciais))
    return formset


@acesso_ao_modulo
def editar(request, pk=None):
    _exigir_edicao(request)
    from core.retorno import next_valido
    from viagens_viagem.services import viagem_do_request
    retorno = next_valido(request)
    roteiro = get_object_or_404(Roteiro, pk=pk) if pk else None
    # Criado a partir do painel da viagem: nasce preso a ela e herda o percurso.
    viagem = viagem_do_request(request) if not pk else None

    if request.method == "POST":
        gravacao = gravar_editor(
            request.POST, roteiro if roteiro is not None else (Roteiro(viagem=viagem) if viagem else None),
            rascunho=request.POST.get("acao") == "rascunho", usuario=request.user,
        )
        form, formset, destinos = gravacao.form, gravacao.formset, gravacao.destinos
        if gravacao.ok:
            calculado = [texto for nivel, texto in gravacao.mensagens if nivel == messages.SUCCESS]
            if calculado:
                messages.success(request, "Roteiro salvo — " + calculado[0][0].lower() + calculado[0][1:])
            else:
                messages.success(request, "Roteiro salvo com sucesso.")
                for nivel, texto in gravacao.mensagens:
                    messages.add_message(request, nivel, texto)
            # Salvou, acabou: a lista (ou a etapa 2 da viagem) é para onde se
            # volta, rascunho ou não. Quem chegou com `next` continua voltando para lá.
            return redirect(retorno or _url_de_volta(gravacao.roteiro, viagem))
        if form.is_valid() and not pk:
            # Trechos inválidos num roteiro recém-criado: ele já existe no
            # banco, então a tela continua a edição dele em vez de criar
            # outro na próxima tentativa.
            messages.error(request, "Corrija os trechos destacados para continuar.")
            return render(
                request,
                "pages/viagens_roteiros/form.html",
                _contexto_do_form(gravacao.roteiro, form, formset, destinos, viagem=viagem),
            )
        messages.error(request, "Corrija os campos destacados para continuar.")
    else:
        sede = _sede_inicial(request, roteiro)
        form = RoteiroForm(instance=roteiro, initial=sede)
        if viagem is not None:
            destinos_iniciais, trechos_iniciais = _iniciais_da_viagem(viagem, (sede or {}).get("origem_municipio"))
            formset = _formset_com_iniciais(TrechoFormSet, trechos_iniciais)
            destinos = _formset_com_iniciais(DestinoFormSet, destinos_iniciais)
        else:
            formset = TrechoFormSet(instance=roteiro)
            destinos = DestinoFormSet(instance=roteiro)

    return render(
        request,
        "pages/viagens_roteiros/form.html",
        _contexto_do_form(roteiro, form, formset, destinos, viagem=viagem),
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


def _municipios_referenciados(form, formset, destinos):
    """Opções dos municípios que a tela já mostra: sede, destinos e trechos.

    Também servem de dicionário de rótulos ao roteiro-editor.js, que nomeia
    os trechos pelo id do município.
    """
    from cadastros.busca_municipios import opcoes_dos_municipios

    ids = [form["origem_municipio"].value()]
    ids += [f["municipio"].value() for f in destinos.forms]
    for trecho in formset.forms:
        ids += [trecho["origem_municipio"].value(), trecho["destino_municipio"].value()]
    return opcoes_dos_municipios(getattr(i, "pk", i) for i in ids)


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
        # Linha pré-preenchida (roteiro nascido de uma viagem) já aparece.
        if not visivel and not form_trecho.is_bound:
            visivel = bool(form_trecho.initial.get("destino_municipio"))
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
        if not visivel and not form_destino.is_bound:
            visivel = bool(form_destino.initial.get("municipio"))
        if not visivel and form_destino.is_bound:
            visivel = bool(
                form_destino.data.get(f"{form_destino.prefix}-municipio")
            )
        cards.append({"form": form_destino, "visivel": visivel})
    return cards


def _estado_padrao_destino():
    """Estado da sede das configurações: todo destino sem município já nasce com ele.

    Usa a configuração do setor de quem faz a requisição (a mesma que define a sede).
    """
    from viagens_cadastros.models import ConfiguracaoSistema

    sede = ConfiguracaoSistema.atual().cidade_sede_padrao
    return str(sede.estado_id) if sede else ""


def _contexto_do_form(roteiro, form, formset, destinos, viagem=None):
    return {
        "roteiro": roteiro,
        "estado_padrao_destino": _estado_padrao_destino(),
        "form": form,
        "formset": formset,
        "destinos": destinos,
        "trechos_cards": _cards_de_trechos(formset),
        "destinos_cards": _cards_de_destinos(destinos),
        # Só os municípios já no roteiro: o resto o seletor busca conforme se
        # digita (m075). A lista inteira pesava megabytes em cada campo.
        "opcoes_municipios": _municipios_referenciados(form, formset, destinos),
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
        # Todas as alterações do roteiro, dos destinos e dos trechos.
        "historico": historico_do_roteiro(roteiro),
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
        # Parcela a parcela, como o valor gravado foi composto (m074).
        "como_calculado": linhas_do_calculo(roteiro.componentes_diarias.all()) if roteiro and roteiro.pk else [],
        "titulo": "Editar roteiro" if roteiro and roteiro.pk else "Novo roteiro",
        "url_voltar": _url_de_volta(roteiro, viagem),
        "viagem_id": getattr(viagem, "pk", None),
        "viagem_datas": _datas_da_viagem(viagem),
        "breadcrumb": [
            {"label": "Roteiros", "url": reverse("viagens_roteiros:lista")},
            {"label": "Editar roteiro" if roteiro and roteiro.pk else "Novo roteiro"},
        ],
    }


def _rotulos_do_roteiro(roteiro):
    ids = {roteiro.origem_municipio_id}
    ids.update(roteiro.destinos.values_list("municipio_id", flat=True))
    for origem, destino in roteiro.trechos.values_list("origem_municipio_id", "destino_municipio_id"):
        ids.update((origem, destino))
    ids.discard(None)
    return {str(pk): nome for pk, nome in Municipio.objects.filter(pk__in=ids).values_list("pk", "nome")}


@acesso_ao_modulo
def dados_do_roteiro(request, pk):
    """Sede, destinos, trechos e rota de um roteiro salvo, para reaproveitar na montagem.

    A tela usa isto quando se escolhe um roteiro como base: ela repete o
    percurso dele — sede e destinos, na ordem — e o operador ajusta datas e
    horários. Nada é copiado no banco; o roteiro novo nasce independente.
    """
    roteiro = get_object_or_404(
        Roteiro.objects.select_related("origem_municipio__estado"), pk=pk
    )
    destinos = roteiro.destinos.select_related("municipio__estado").all()

    def local(valor):
        return timezone.localtime(valor) if valor and timezone.is_aware(valor) else valor

    trechos = []
    for trecho in roteiro.trechos.order_by("ordem"):
        saida = local(trecho.saida_dt)
        trechos.append({
            "sentido": trecho.sentido,
            "origem": trecho.origem_municipio_id,
            "destino": trecho.destino_municipio_id,
            "saida_data": saida.date().isoformat() if saida else "",
            "saida_hora": saida.strftime("%H:%M") if saida else "",
            "tempo_viagem_min": trecho.tempo_viagem_min,
            "tempo_adicional_min": trecho.tempo_adicional_min or 0,
            "distancia_km": float(trecho.distancia_km) if trecho.distancia_km is not None else None,
            "rota_fonte": trecho.rota_fonte or "",
        })
    return JsonResponse(
        {
            # Com os trechos e a rota, a tela do ofício mostra o roteiro
            # escolhido inteiro sem recarregar; a de roteiros usa só sede e destinos.
            "trechos": trechos,
            # Nome de cada município citado: os seletores da tela só trazem
            # os já escolhidos e buscam o resto (m075).
            "rotulos": _rotulos_do_roteiro(roteiro),
            "rota": rota_para_tela(roteiro),
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
        equipe = int(request.POST.get("diarias_servidores") or 0) or None
    except ValueError:
        equipe = None
    try:
        resultado = previa_diarias(form, formset, equipe)
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
            "como_calculado": linhas_do_calculo(getattr(resultado, "componentes", [])),
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
    from core.retorno import next_valido
    from viagens_viagem.services import viagem_do_request
    retorno = next_valido(request)
    roteiro = get_object_or_404(Roteiro, pk=pk) if pk else None
    # A primeira gravação automática de um roteiro do painel já o prende à viagem.
    if roteiro is None and viagem_do_request(request) is not None:
        roteiro = Roteiro(viagem=viagem_do_request(request))
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
                salvo.sincronizar_periodo()
        if not pk:
            _registrar_auditoria(request.user, "VIAGENS_ROTEIRO_CRIADO", salvo)
    if gravou["trechos"]:
        # O rascunho gravado sozinho também leva as diárias: sem isso, a lista
        # mostrava "Sem diárias" num roteiro que a tela já calculava.
        try:
            recalcular_diarias(salvo)
        except (SemTabelaDeDiarias, RoteiroIncalculavel):
            pass
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


def _recusa_de_exclusao(roteiro):
    """Mensagem de recusa quando o roteiro está em uso, ou None.

    Apagar um roteiro usado tiraria destino, período e diárias do ofício (a
    chave é SET_NULL) e o "roteiro ajustado" da prestação, sem aviso.
    """
    from django.utils.html import format_html, format_html_join

    from viagens_prestacoes.models import PrestacaoContas

    oficios = list(roteiro.oficios.order_by("ano", "numero", "pk"))
    prestacoes = PrestacaoContas.objects.filter(roteiro_ajustado=roteiro).select_related("oficio")
    oficios += [p.oficio for p in prestacoes if p.oficio not in oficios]
    if not oficios:
        return None
    links = format_html_join(
        ", ", '<a href="{}">Ofício {}</a>',
        ((reverse("viagens_oficios:editar", args=[o.pk]), o.numero_formatado if o.numero else f"sem número (#{o.pk})") for o in oficios),
    )
    return format_html(
        "Este roteiro não pode ser excluído: está em uso por {}. "
        "Se a viagem não vai mais acontecer, cancele o ofício.",
        links,
    )


@acesso_ao_modulo
@require_POST
def excluir(request, pk):
    _exigir_edicao(request)
    roteiro = get_object_or_404(Roteiro, pk=pk)
    descricao = f"roteiro {roteiro.pk} ({roteiro.sede_cidade or 'sem sede'})"
    volta = _url_de_volta(roteiro)
    from core.retorno import voltar_para

    recusa = _recusa_de_exclusao(roteiro)
    if recusa:
        messages.error(request, recusa)
        return redirect(voltar_para(request, volta))
    roteiro.delete()
    LogAuditoria.objects.create(
        usuario=request.user, acao="VIAGENS_ROTEIRO_EXCLUIDO", descricao=descricao
    )
    messages.success(request, "Roteiro excluído.")
    # Excluir da lista devolve à lista como ela estava, com busca e filtros.
    return redirect(voltar_para(request, volta))
