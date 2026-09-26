"""Planos de trabalho — lista, cadastro em página única, eventos e documentos.

As quatro etapas do Gerenciador de Viagens viraram quatro cartões numerados
numa página só, gravados de uma vez por um único formulário. Sem autosave:
grava-se ao clicar. "Adicionar evento ao plano" e "Editar evento" gravam o
que está na tela antes de mexer no rascunho, para nada digitado se perder.
"""

import json

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.db import transaction
from django.http import Http404, HttpResponse, JsonResponse
from django.shortcuts import redirect, render
from django.urls import NoReverseMatch, reverse
from django.utils import timezone
from django.views.decorators.clickjacking import xframe_options_sameorigin
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from core.deletion import DelecaoProtegidaError
from core.listagens import ITENS_POR_PAGINA
from core.retorno import com_next, daqui, next_valido, voltar_para
from documentos.services.exceptions import DocumentError
from documentos.services.responses import build_inline_pdf_response
from documentos.services.types import DocumentoFormato
from viagens_cadastros.permissions import acesso_ao_modulo, pode_editar_cadastros
from viagens_oficios.views import exigir_operador, resposta_documento
from viagens_viagem.services import viagem_do_request

from . import abas as abas_de_plano
from .efetivo_services import linhas_do_formset, salvar_efetivo_e_diarias
from .forms import EfetivoPlanoFormSet, PlanoDiariasForm, PlanoIdentificacaoForm
from .identificacao_services import salvar_identificacao
from .models import PlanoTrabalho
from .presenters import apresentar_resumo_evento_card, apresentar_resumo_header, linha_da_lista, resumo_do_plano_para_tela, selo_do_plano
from .selectors import get_evento_do_plano_by_id, get_plano_by_id, listar_planos, obter_intervalo_dos_oficios_da_viagem
from .services import (
    adicionar_evento_ao_plano,
    atividades_catalogo,
    avaliar_pendencias_documento,
    calcular_diarias_combinadas,
    calcular_diarias_evento,
    calcular_diarias_plano,
    criar_plano_rascunho,
    editar_evento_no_scratchpad,
    eventos_para_cards,
    excluir_plano,
    gerar_plano_documento,
    marcar_plano_gerado,
    preset_padrao,
    presets_atividades,
    remover_evento,
    sincronizar_atividades,
    sincronizar_scratchpad,
)


@acesso_ao_modulo
def lista(request):
    q = request.GET.get("q", "").strip()
    escolhidas = abas_de_plano.normalizar_abas(request.GET.getlist("situacao"))
    base = listar_planos(q)
    queryset = listar_planos(q, situacoes=escolhidas)
    paginator = Paginator(queryset, ITENS_POR_PAGINA)
    pagina = paginator.get_page(request.GET.get("pagina"))
    parametros = request.GET.copy()
    parametros.pop("pagina", None)
    linhas = [linha_da_lista(p) for p in pagina]

    def url_da_situacao(aba=None):
        destino = parametros.copy()
        destino.pop("situacao", None)
        if aba:
            destino["situacao"] = aba
        return "?" + destino.urlencode()

    icones = {
        abas_de_plano.ABA_FUTURAS: "calendar",
        abas_de_plano.ABA_ATUAIS: "clock",
        abas_de_plano.ABA_FINALIZADOS: "check-circle",
        abas_de_plano.ABA_CANCELADOS: "ban",
    }
    contagem = abas_de_plano.contar_por_aba(base)
    situacoes = [{"slug": "todas", "titulo": "Todos", "total": base.count(), "icone": "checklist", "url": url_da_situacao()}] + [
        {"slug": chave, "titulo": rotulo, "total": contagem[chave], "icone": icones[chave], "url": url_da_situacao(chave)}
        for chave, rotulo in abas_de_plano.ABA_ROTULOS
    ]
    return render(request, "pages/viagens_planos/lista.html", {
        "linhas": linhas, "pagina": pagina, "querystring": parametros.urlencode(), "q": q,
        "paginas_visiveis": list(paginator.get_elided_page_range(pagina.number, on_each_side=1, on_ends=1)),
        "elipse": paginator.ELLIPSIS,
        "situacoes": situacoes,
        "situacoes_escolhidas": escolhidas,
        "situacao_ativa": "todas" if not escolhidas else escolhidas[0] if len(escolhidas) == 1 else "",
        "tem_filtros": bool(q or escolhidas), "url_atual": daqui(request),
        "pode_editar": pode_editar_cadastros(request.user),
    })


def _url_lista(plano=None):
    """A lista — ou a etapa 4 da viagem, quando o plano tem uma."""
    if plano is not None and plano.viagem_id:
        try:
            return reverse("viagens_viagem:etapa", args=[plano.viagem_id, 4])
        except NoReverseMatch:
            pass
    return reverse("viagens_planos:lista")


@acesso_ao_modulo
@require_http_methods(["GET", "POST"])
def criar(request):
    """"Novo plano": cria o rascunho já numerado e abre o cadastro. GET não cria nada."""
    if request.method == "GET":
        return redirect("viagens_planos:lista")
    exigir_operador(request)
    plano = criar_plano_rascunho(viagem=viagem_do_request(request))
    messages.success(request, f"Plano de Trabalho {plano.numero_formatado} criado como rascunho.")
    destino = reverse("viagens_planos:editar", args=[plano.pk])
    retorno = next_valido(request)
    return redirect(com_next(destino, retorno) if retorno else destino)


def _sugerir_deslocamento(plano):
    """Saída e chegada na sede pelos roteiros dos ofícios da viagem — só nas lacunas, só em memória."""
    campos = ("saida_sede_data", "saida_sede_hora", "chegada_sede_data", "chegada_sede_hora")
    if all(getattr(plano, campo) is not None for campo in campos):
        return
    intervalo = obter_intervalo_dos_oficios_da_viagem(plano)
    if not intervalo:
        return
    saida, chegada = intervalo["saida"], intervalo["chegada"]
    if timezone.is_aware(saida):
        saida = timezone.localtime(saida)
    if timezone.is_aware(chegada):
        chegada = timezone.localtime(chegada)
    sugestoes = {
        "saida_sede_data": saida.date(), "saida_sede_hora": saida.time().replace(tzinfo=None),
        "chegada_sede_data": chegada.date(), "chegada_sede_hora": chegada.time().replace(tzinfo=None),
    }
    for campo, valor in sugestoes.items():
        if getattr(plano, campo) is None:
            setattr(plano, campo, valor)


def _formularios(request, plano, dados=None):
    if dados is None:
        dados = request.POST if request.method == "POST" else None
    form = PlanoIdentificacaoForm(dados, instance=plano)
    diarias_form = PlanoDiariasForm(dados, instance=plano)
    formset = EfetivoPlanoFormSet(dados, instance=plano, prefix="efetivo")
    return form, diarias_form, formset


def _gravar(request, plano, dados=None):
    """Os quatro cartões numa transação. Devolve (ok, form, diarias_form, formset).

    `dados`: outro QueryDict no lugar do `request.POST` (o autosave).
    """
    form, diarias_form, formset = _formularios(request, plano, dados)
    if not (form.is_valid() and diarias_form.is_valid() and formset.is_valid()):
        return False, form, diarias_form, formset
    catalogo = atividades_catalogo()
    codigos = (dados if dados is not None else request.POST).getlist("atividades_codigos")
    with transaction.atomic():
        plano = salvar_identificacao(form)
        salvar_efetivo_e_diarias(plano, rows=linhas_do_formset(formset), diarias_form=diarias_form)
        plano.atividades_selecionadas.set([a for a in catalogo if a.codigo in codigos])
        sincronizar_atividades(plano)
    return True, form, diarias_form, formset


def _valor(form, nome):
    valor = form[nome].value()
    if valor in (None, ""):
        return ""
    if hasattr(valor, "strftime"):
        return valor.strftime("%H:%M") if hasattr(valor, "hour") and not hasattr(valor, "date") else valor.isoformat()
    return str(getattr(valor, "pk", valor))


def _contexto_identificacao(form, plano, request):
    from cadastros.models import Estado, Municipio
    from viagens_cadastros.models import Servidor

    valor = lambda nome: _valor(form, nome)  # noqa: E731
    servidores = [
        {"valor": str(s.pk), "rotulo": s.nome,
         "detalhes": " · ".join(p for p in [str(s.cargo) if s.cargo_id else "", (s.unidade.sigla or s.unidade.nome) if s.unidade_id else ""] if p),
         "dados": {"cargo": s.cargo.nome if s.cargo_id else ""}}
        for s in Servidor.objects.select_related("cargo", "unidade").order_by("nome")
    ]
    estados = [{"valor": str(e.pk), "rotulo": f"{e.sigla} — {e.nome}"} for e in Estado.objects.order_by("sigla")]
    municipios = [{"valor": str(m.pk), "rotulo": m.nome, "estado": str(m.estado_id)} for m in Municipio.objects.select_related("estado").order_by("nome")]
    adicionais = [
        {"i": i, "indice": str(i), "nome_estado": f"extra_estado_{i}", "nome_cidade": f"extra_cidade_{i}", "id_estado": f"id_extra_estado_{i}",
         "estado": valor(f"extra_estado_{i}"), "cidade": valor(f"extra_cidade_{i}"),
         "erros_estado": form.errors.get(f"extra_estado_{i}"), "erros_cidade": form.errors.get(f"extra_cidade_{i}")}
        for i in range(form.quantidade_destinos)
    ]
    # O campo de nome é um só. Num plano com servidor escolhido o nome manual
    # está vazio, e quem aparece na tela é o nome do cadastro; depois de um
    # POST com erro, vale o que a pessoa digitou.
    nomes_coordenador, cargos_coordenador = {}, {}
    for papel in ("adm", "op"):
        escolhido = getattr(plano, f"coordenador_{papel}", None)
        nomes_coordenador[papel] = valor(f"coordenador_{papel}_nome_manual") or (escolhido.nome if escolhido else "")
        # Servidor do cadastro: o cargo manual foi zerado na gravação, e o que
        # vale (e sai no documento) é o do cadastro — é esse que a tela mostra.
        cargos_coordenador[papel] = valor(f"coordenador_{papel}_cargo_manual") or (
            escolhido.cargo.nome if escolhido and escolhido.cargo_id else "")
    atual = daqui(request)
    return {
        "valores": {nome: valor(nome) for nome in form.fields},
        "nomes_coordenador": nomes_coordenador,
        "cargos_coordenador": cargos_coordenador,
        "erros": {nome: form.errors.get(nome) for nome in form.fields},
        "programas": [{"valor": v, "rotulo": r} for v, r in form.fields["programa"].choices if v],
        "programa_outro_valor": form.PROGRAMA_OUTRO_VALUE,
        "programa_outros_visivel": form.programa_outros_selected,
        "horarios": [{"valor": v, "rotulo": r} for v, r in form.fields["horario_atendimento"].choices if v],
        "cargos": {papel: [{"valor": v, "rotulo": r} for v, r in form.fields[f"coordenador_{papel}_cargo_manual"].choices if v] for papel in ("adm", "op")},
        "generos": [{"valor": v, "rotulo": r} for v, r in PlanoTrabalho.COORDENADOR_GENERO_CHOICES],
        "servidores": servidores,
        "estados": estados, "municipios": municipios, "adicionais": adicionais, "quantidade_destinos": str(form.quantidade_destinos),
        "url_programas": com_next(reverse("viagens_cadastros:lista", args=["programas"]), atual),
        "url_horarios": com_next(reverse("viagens_cadastros:lista", args=["horarios"]), atual),
        "url_cargos": com_next(reverse("viagens_cadastros:lista", args=["cargos"]), atual),
    }


def _contexto_efetivo(formset, plano):
    from viagens_cadastros.models import Cargo, Unidade

    def linha(f):
        return {
            "prefixo": f.prefix, "id": _valor(f, "id"), "unidade": _valor(f, "unidade"), "cargo": _valor(f, "cargo"),
            "quantidade": _valor(f, "quantidade") or "1", "apagar": bool(f["DELETE"].value()),
            "erros_cargo": f.errors.get("cargo"), "erros_quantidade": f.errors.get("quantidade"), "erros_unidade": f.errors.get("unidade"),
        }

    return {
        "formset": formset,
        "linhas_efetivo": [linha(f) for f in formset.forms],
        "modelo_efetivo": linha(formset.empty_form),
        "unidades": [{"valor": str(u.pk), "rotulo": u.sigla or u.nome, "detalhes": u.nome} for u in Unidade.objects.order_by("nome")],
        "cargos_efetivo": [{"valor": str(c.pk), "rotulo": c.nome} for c in Cargo.objects.order_by("nome")],
    }


def _contexto_atividades(plano, request):
    catalogo = atividades_catalogo()
    if request.method == "POST":
        selecionados = set(request.POST.getlist("atividades_codigos"))
    else:
        selecionados = set(plano.atividades_selecionadas.values_list("codigo", flat=True)) if plano.pk else set()
        # Plano sem atividade abre com o preset padrão marcado — na tela, não no banco.
        if not selecionados:
            padrao = preset_padrao()
            if padrao:
                selecionados = {a.codigo for a in padrao.atividades.all()}
    escolhidas = [a for a in catalogo if a.codigo in selecionados]
    metas, recursos = [], []
    for item in escolhidas:
        meta, recurso = (item.meta or "").strip(), (item.recurso_necessario or "").strip()
        if meta and meta not in metas:
            metas.append(meta)
        if recurso and recurso not in recursos:
            recursos.append(recurso)
    presets = presets_atividades()
    padrao = next((p for p in presets if p.is_padrao), None)
    atual = daqui(request)
    return {
        "atividades_catalogo": [{"codigo": a.codigo, "nome": a.nome, "meta": a.meta, "recurso": a.recurso_necessario, "selecionada": a.codigo in selecionados} for a in catalogo],
        "atividades_data": [{"codigo": a.codigo, "nome": a.nome, "meta": a.meta, "recurso": a.recurso_necessario} for a in catalogo],
        "presets": [{"valor": str(p.pk), "rotulo": f"{p.nome} — Padrão" if p.is_padrao else p.nome} for p in presets],
        "presets_data": [{"id": p.pk, "nome": p.nome, "codigos": [a.codigo for a in sorted(p.atividades.all(), key=lambda a: a.nome)]} for p in presets],
        "preset_padrao_id": str(padrao.pk) if padrao else "",
        "metas_preview": metas, "recursos_preview": recursos,
        "atividades_selecionadas_total": sum(1 for a in catalogo if a.codigo in selecionados),
        "url_atividades": com_next(reverse("viagens_cadastros:lista", args=["atividades-pt"]), atual),
        "url_presets": com_next(reverse("viagens_cadastros:lista", args=["presets-pt"]), atual),
    }


def _contexto_documentos(plano, request, pendencias):
    from documentos.editor.pagina import cartao

    disponivel = not pendencias and not plano.cancelado
    return {
        "pendencias": pendencias,
        "mostrar_pendencias": bool(pendencias) and request.GET.get("pendencias") == "1",
        "documento": {
            "titulo": f"Plano de Trabalho {plano.numero_formatado}",
            "disponivel": disponivel,
            "mensagem": "Plano cancelado: reative para emitir o documento." if plano.cancelado else "Complete as etapas anteriores para visualizar o documento.",
            "src": reverse("viagens_planos:visualizar", args=[plano.pk]),
            "url_pdf": reverse("viagens_planos:gerar", args=[plano.pk, "pdf"]),
            "url_docx": reverse("viagens_planos:gerar", args=[plano.pk, "docx"]),
            "url_anexar": "",
            "assinado": False,
            # O corpo do cartão é o editor do documento (a folha A4 editável).
            "embutido": cartao("plano_trabalho", plano.pk, f"Plano de Trabalho {plano.numero_formatado}"),
        },
        "url_evento_adicionar": reverse("viagens_planos:evento_adicionar", args=[plano.pk]),
        "resumo": resumo_do_plano_para_tela(plano),
    }


def _contexto_form(request, plano, form, diarias_form, formset):
    eventos = [apresentar_resumo_evento_card(e) for e in eventos_para_cards(plano)]
    pendencias = avaliar_pendencias_documento(plano)
    diarias = calcular_diarias_plano(plano)
    selo, tom = selo_do_plano(plano)
    return {
        "titulo": f"Plano de trabalho {plano.numero_formatado}",
        "plano": plano, "form": form, "diarias_form": diarias_form,
        "selo": selo, "selo_tom": tom,
        "erros_diarias": {nome: diarias_form.errors.get(nome) for nome in diarias_form.fields},
        "valores_diarias": {nome: _valor(diarias_form, nome) for nome in diarias_form.fields},
        "diarias_resultado": diarias,
        # Os erros do cálculo só depois de um envio: a tela não abre avisando.
        "mostrar_erros_calculo": request.method == "POST" and not diarias["ok"],
        "url_calcular": reverse("viagens_planos:calcular", args=[plano.pk]),
        "is_multi_evento": plano.is_multi_evento,
        "eventos_resumo": eventos,
        "resumo_header": apresentar_resumo_header(plano),
        "total_eventos": len(eventos),
        "em_edicao_evento": plano.evento_em_edicao_id,
        "tem_erros": bool(form.errors or diarias_form.errors or formset.errors and any(formset.errors) or formset.non_form_errors()),
        "next": next_valido(request),
        "url_voltar": voltar_para(request, _url_lista(plano)),
        "url_atual": daqui(request),
        "pode_editar": pode_editar_cadastros(request.user),
        # Rascunho que se salva sozinho (m050): só enquanto é rascunho.
        "autosave_url": (reverse("viagens_planos:autosalvar", args=[plano.pk])
                         if plano.status == plano.STATUS_RASCUNHO and not plano.cancelado and pode_editar_cadastros(request.user) else ""),
        **_contexto_identificacao(form, plano, request),
        **_contexto_efetivo(formset, plano),
        **_contexto_atividades(plano, request),
        **_contexto_documentos(plano, request, pendencias),
    }


def _render_form(request, plano, form, diarias_form, formset):
    return render(request, "pages/viagens_planos/form.html", _contexto_form(request, plano, form, diarias_form, formset))


@acesso_ao_modulo
@require_http_methods(["GET", "POST"])
def editar(request, pk):
    """A página única do plano: quem só consulta abre; gravar exige operador."""
    plano = get_plano_by_id(pk)
    if request.method == "POST":
        exigir_operador(request)
        ok, form, diarias_form, formset = _gravar(request, plano)
        if not ok:
            messages.error(request, "Não foi possível salvar o plano. Revise os campos indicados.")
            return _render_form(request, plano, form, diarias_form, formset)
        plano = get_plano_by_id(pk)
        url_editar = reverse("viagens_planos:editar", args=[plano.pk])
        retorno = next_valido(request)
        if request.POST.get("acao") == "finalizar":
            sincronizar_scratchpad(plano)
            if avaliar_pendencias_documento(plano):
                return redirect(com_next(url_editar + "?pendencias=1", retorno))
            marcar_plano_gerado(plano)
            messages.success(request, "Plano de trabalho finalizado com sucesso.")
            return redirect(voltar_para(request, _url_lista(plano)))
        messages.success(request, "Plano salvo.")
        return redirect(com_next(url_editar, retorno))
    _sugerir_deslocamento(plano)
    form, diarias_form, formset = _formularios(request, plano)
    return _render_form(request, plano, form, diarias_form, formset)


@acesso_ao_modulo
@require_POST
def autosalvar(request, pk):
    """Grava o rascunho do plano alguns segundos depois de cada alteração (m050).

    A mesma gravação do "Salvar" (os quatro cartões), sem finalizar e sem
    mexer no número — em branco, fica o reservado. Plano já finalizado só
    grava pelo botão.
    """
    from core.autosave import AutosavePayloadError, autosave_json_response, dados_do_formulario, parse_autosave_payload

    exigir_operador(request)
    plano = get_plano_by_id(pk)
    if plano.cancelado or plano.status != plano.STATUS_RASCUNHO:
        return autosave_json_response(ok=False, message="Plano fora de rascunho: salve pelo botão.")
    try:
        payload = parse_autosave_payload(request, expected_model="plano_trabalho")
    except AutosavePayloadError as exc:
        return autosave_json_response(ok=False, message=str(exc))
    ok, form, diarias_form, formset = _gravar(request, plano, dados_do_formulario(payload, fixos={"numero": ""}))
    if not ok:
        erros = {**form.errors.get_json_data(), **diarias_form.errors.get_json_data()}
        mensagens = {k: [e["message"] for e in v] for k, v in erros.items()}
        if formset.total_error_count():
            mensagens["efetivo"] = ["Revise as linhas do efetivo."]
        return autosave_json_response(ok=False, message="Rascunho não salvo: revise os campos indicados.", errors=mensagens)
    return autosave_json_response(ok=True, object_id=plano.pk)


@acesso_ao_modulo
@require_POST
def calcular(request, pk):
    """A prévia ao vivo das diárias, sem gravar nada."""
    plano = get_plano_by_id(pk)
    try:
        payload = json.loads(request.body or "{}")
    except (TypeError, ValueError):
        return JsonResponse({"ok": False, "erros": ["Payload inválido."]}, status=400)
    dados = {campo: payload.get(campo) or "" for campo in PlanoDiariasForm.Meta.fields}
    form = PlanoDiariasForm(dados, instance=plano)
    if not form.is_valid():
        return JsonResponse({"ok": False, "erros": [m for lista_ in form.errors.values() for m in lista_]})
    for campo, valor in form.cleaned_data.items():
        setattr(plano, campo, valor)
    # O destino da tela vale para a prévia: numa página só, ela roda antes de
    # o plano ser gravado, e o destino do banco ainda está vazio.
    destino = payload.get("destino_cidade")
    if destino:
        from cadastros.models import Municipio

        cidade = Municipio.objects.select_related("estado").filter(pk=destino).first()
        if cidade is not None:
            plano.destino_cidade, plano.destino_estado = cidade, cidade.estado
    total_efetivo = payload.get("total_efetivo")
    if total_efetivo is not None:
        try:
            total_efetivo = max(0, int(total_efetivo))
        except (TypeError, ValueError):
            total_efetivo = None

    def publico(r):
        return {
            "ok": r["ok"], "erros": r.get("erros", []),
            "composicao": r.get("composicao", ""),
            "valor_unitario_display": r.get("valor_unitario_display", ""),
            "valor_total_display": r.get("valor_total_display", ""),
            "valor_unitario_extenso": r.get("valor_unitario_extenso", ""),
            "valor_total_extenso": r.get("valor_total_extenso", ""),
            "quantidade_servidores": r.get("quantidade_servidores", 0),
        }

    if plano.is_multi_evento:
        combinada = publico(calcular_diarias_combinadas(plano))
        por_evento = [
            {"evento_id": e.pk, "ordem": e.ordem, **publico(calcular_diarias_evento(plano, e))}
            for e in plano.eventos.order_by("ordem", "data_evento_inicio", "pk")
        ]
        return JsonResponse({**combinada, "modo": "multi", "per_evento": por_evento, "combinada": combinada})
    return JsonResponse(publico(calcular_diarias_plano(plano, total_efetivo=total_efetivo)))


@acesso_ao_modulo
@require_POST
def evento_adicionar(request, pk):
    """Grava a tela, guarda o rascunho como evento e limpa a identificação para o próximo."""
    exigir_operador(request)
    plano = get_plano_by_id(pk)
    ok, form, diarias_form, formset = _gravar(request, plano)
    if not ok:
        messages.error(request, "Não foi possível salvar o plano. Revise os campos indicados.")
        return _render_form(request, plano, form, diarias_form, formset)
    plano = get_plano_by_id(pk)
    evento = adicionar_evento_ao_plano(plano)
    if evento is None:
        messages.warning(request, "Preencha os dados do evento antes de adicioná-lo ao plano.")
    else:
        messages.success(request, f"Evento {evento.ordem} salvo. Preencha a identificação para adicionar o próximo evento.")
    return redirect(com_next(reverse("viagens_planos:editar", args=[plano.pk]), next_valido(request)))


@acesso_ao_modulo
@require_POST
def evento_editar(request, pk, evento_pk):
    """Guarda o que está na tela e carrega o evento escolhido no rascunho."""
    exigir_operador(request)
    plano = get_plano_by_id(pk)
    evento = get_evento_do_plano_by_id(plano, evento_pk)
    ok, form, diarias_form, formset = _gravar(request, plano)
    if not ok:
        messages.error(request, "Não foi possível salvar o plano. Revise os campos indicados.")
        return _render_form(request, plano, form, diarias_form, formset)
    editar_evento_no_scratchpad(get_plano_by_id(pk), evento)
    messages.success(request, f"Editando o evento {evento.ordem}.")
    return redirect(com_next(reverse("viagens_planos:editar", args=[plano.pk]), next_valido(request)))


@acesso_ao_modulo
@require_POST
def evento_remover(request, pk, evento_pk):
    exigir_operador(request)
    plano = get_plano_by_id(pk)
    evento = get_evento_do_plano_by_id(plano, evento_pk)
    # O que estava na tela vai junto, quando é válido; o resto não impede remover.
    if "efetivo-TOTAL_FORMS" in request.POST:
        ok, *_ = _gravar(request, plano)
        if ok:
            plano = get_plano_by_id(pk)
    remover_evento(plano, evento)
    messages.success(request, "Evento removido do plano.")
    return redirect(com_next(reverse("viagens_planos:editar", args=[plano.pk]), next_valido(request)))


def _bloqueio_do_documento(request, plano):
    """Cancelado ou incompleto: a mensagem e para onde voltar; None quando pode gerar."""
    if plano.cancelado:
        return "Reative o plano antes de gerar documentos."
    if avaliar_pendencias_documento(plano):
        return "Documento não gerado porque o plano está incompleto."
    return None


@acesso_ao_modulo
@require_POST
def gerar(request, pk, formato):
    """PDF ou DOCX do plano; `?inline=1` abre o PDF no navegador. Gerar marca o plano como gerado.

    Vindo do formulário (os botões do cartão 4), o que está na tela é gravado antes.
    """
    exigir_operador(request)
    if formato not in ("pdf", "docx"):
        raise Http404
    plano = get_plano_by_id(pk)
    url_editar = reverse("viagens_planos:editar", args=[plano.pk])
    if "efetivo-TOTAL_FORMS" in request.POST and not plano.cancelado:
        ok, *_ = _gravar(request, plano)
        if not ok:
            messages.error(request, "Não foi possível salvar o plano. Revise os campos indicados.")
            return redirect(url_editar)
        plano = get_plano_by_id(pk)
        sincronizar_scratchpad(plano)
    bloqueio = _bloqueio_do_documento(request, plano)
    if bloqueio:
        messages.error(request, bloqueio)
        return redirect(url_editar + ("?pendencias=1" if not plano.cancelado else ""))
    try:
        doc = gerar_plano_documento(plano, DocumentoFormato(formato))
    except (ValidationError, DocumentError) as exc:
        messages.error(request, "; ".join(exc.messages) if isinstance(exc, ValidationError) else str(exc))
        return redirect(url_editar)
    marcar_plano_gerado(plano)
    return resposta_documento(request, doc)


@acesso_ao_modulo
@require_GET
@xframe_options_sameorigin
def visualizar(request, pk):
    """O PDF dentro do cartão da página (iframe)."""
    plano = get_plano_by_id(pk)
    bloqueio = _bloqueio_do_documento(request, plano)
    if bloqueio:
        return HttpResponse(bloqueio, status=409, content_type="text/plain; charset=utf-8")
    try:
        doc = gerar_plano_documento(plano, DocumentoFormato.PDF)
    except (ValidationError, DocumentError) as exc:
        return HttpResponse("; ".join(exc.messages) if isinstance(exc, ValidationError) else str(exc), status=409, content_type="text/plain; charset=utf-8")
    marcar_plano_gerado(plano)
    return build_inline_pdf_response(request, content=doc.conteudo, tipo=doc.tipo, cache_hit=doc.cache_hit, x_document_sha256=doc.hash_sha256)


@acesso_ao_modulo
@require_POST
def acao(request, pk, acao):
    exigir_operador(request)
    plano = get_plano_by_id(pk)
    destino = voltar_para(request, reverse("viagens_planos:editar", args=[pk]))
    numero = plano.numero_formatado
    if acao == "cancelar":
        plano.cancelar(request.POST.get("motivo", ""))
        messages.success(request, f"Plano de Trabalho {numero} cancelado. O histórico foi mantido.")
    elif acao == "reativar":
        plano.reativar()
        messages.success(request, f"Plano de Trabalho {numero} reativado.")
    elif acao == "excluir":
        retorno = voltar_para(request, _url_lista(plano))
        try:
            excluir_plano(plano)
        except DelecaoProtegidaError as exc:
            messages.error(request, str(exc))
            return redirect(retorno)
        messages.success(request, f"Plano de Trabalho {numero} excluído.")
        return redirect(retorno)
    else:
        raise Http404
    return redirect(destino)


@acesso_ao_modulo
@require_http_methods(["GET", "POST"])
def resultados(request, pk):
    """Resultados do evento: o realizado de cada atividade e o relatório final (m073)."""
    from .resultados import linhas_de_resultado, salvar_resultados, texto_do_relatorio

    plano = get_plano_by_id(pk)
    url_editar = reverse("viagens_planos:editar", args=[plano.pk])
    if request.method == "POST":
        exigir_operador(request)
        dados = {}
        for chave, valor in request.POST.items():
            if chave.startswith("realizado_"):
                try:
                    atividade_pk = int(chave.removeprefix("realizado_"))
                except ValueError:
                    continue
                dados[atividade_pk] = (valor, request.POST.get(f"observacao_{atividade_pk}", ""))
        erros = salvar_resultados(plano, dados)
        for erro in erros:
            messages.error(request, erro)
        if not erros:
            messages.success(request, "Resultados salvos.")
        return redirect(com_next(reverse("viagens_planos:resultados", args=[plano.pk]), next_valido(request)))
    return render(request, "pages/viagens_planos/resultados.html", {
        "titulo": f"Resultados do plano {plano.numero_formatado}",
        "plano": plano,
        "linhas": linhas_de_resultado(plano),
        "relatorio": texto_do_relatorio(plano),
        "pode_editar": pode_editar_cadastros(request.user) and not plano.cancelado,
        "url_voltar": voltar_para(request, url_editar),
        "next": next_valido(request),
    })
