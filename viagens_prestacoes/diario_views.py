from urllib.parse import urlencode

from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse

from core.autosave import AutosavePayloadError, autosave_json_response, parse_autosave_payload
from core.utils.masks import format_cpf, format_protocolo
from .ui import gerar_resposta_documento

from .diario_services import (
    ESCOPO_EQUIPE,
    ESCOPO_SERVIDOR,
    DiarioValidacaoError,
    diaria_info,
    garantir_roteiro_ajustado,
    motorista_diario,
    motorista_do_oficio,
    obter_ou_criar_diario,
    salvar_autosave_do_diario,
    salvar_linhas_do_diario,
    sincronizar_trechos,
    trocar_motorista_do_diario,
    viatura_resumo_diario,
    viatura_resumo_oficio,
    alteracoes_datas_horarios_roteiro,
)
from .forms import DiarioBordoTrechoFormSet, DiarioMotoristaForm
from .models import DiarioBordo
from .selectors import oficios_para_prefill_de_motorista
from .view_common import (
    _autosave_version,
    _build_identificacao,
    contexto_do_fluxo,
    _diario_queryset,
    _is_inline_request,
    _prestacao_queryset,
    _prestacao_servidor_full,
    _prestacao_servidor_queryset,
    _redirect_primeiro_servidor,
)


_MOTORISTA_ORIGEM_LABEL = {
    DiarioBordo.MOTORISTA_MODO_OFICIO: "Motorista do ofício",
    DiarioBordo.MOTORISTA_MODO_SERVIDOR: "Outro servidor deste ofício",
    DiarioBordo.MOTORISTA_MODO_OUTRO: "Motorista de outro ofício",
}


def _trecho_display(linha) -> dict:
    """Dados somente-leitura de um trecho (origem/destino/datas) para o card do diário."""
    from django.utils import timezone as tz

    trecho = linha.trecho

    def cidade(c, e):
        if c is not None:
            return str(getattr(c, "nome", c)).upper()
        if e is not None:
            return str(getattr(e, "sigla", e)).upper()
        return "—"

    def fmt(dt):
        if not dt:
            return {"data": "", "hora": ""}
        local = tz.localtime(dt) if tz.is_aware(dt) else dt
        return {"data": local.strftime("%d/%m/%Y"), "hora": local.strftime("%H:%M")}

    origem = cidade(getattr(trecho, "origem_municipio", None), getattr(trecho, "origem_estado", None)) if trecho else "—"
    destino = cidade(getattr(trecho, "destino_municipio", None), getattr(trecho, "destino_estado", None)) if trecho else "—"
    saida = fmt(getattr(trecho, "saida_dt", None)) if trecho else {"data": "", "hora": ""}
    chegada = fmt(getattr(trecho, "chegada_dt", None)) if trecho else {"data": "", "hora": ""}
    return {
        "ordem": linha.ordem + 1,
        "origem": origem,
        "destino": destino,
        "rota": f"{origem} → {destino}",
        "saida": saida,
        "chegada": chegada,
    }


def diario_criar(request, pc_pk):
    """Compatibilidade: redireciona para o primeiro servidor."""
    prestacao = get_object_or_404(_prestacao_queryset(), pk=pc_pk)
    return _redirect_primeiro_servidor(request, prestacao, "viagens_prestacoes:diario_servidor")


def diario_servidor(request, ps_pk, motorista_form=None):
    """Etapa 1 do wizard: diário compartilhado; navegação por servidor.

    A troca de motorista/viatura é um modal desta tela. `motorista_form` chega
    quando o envio do modal volta com erro: a tela abre com o modal aberto.
    """
    ps = _prestacao_servidor_full(ps_pk)
    prestacao = ps.prestacao

    diario = obter_ou_criar_diario(prestacao)
    sincronizar_trechos(diario)
    queryset = diario.trechos.select_related(
        "trecho__origem_municipio",
        "trecho__origem_municipio__estado",
        "trecho__destino_municipio",
        "trecho__destino_municipio__estado",
    ).order_by("ordem", "pk")

    if request.method == "POST" and motorista_form is None:
        formset = DiarioBordoTrechoFormSet(request.POST, queryset=queryset)
        if formset.is_valid():
            salvar_linhas_do_diario(formset, ps)
            formato = "pdf" if request.POST.get("action") == "download_pdf" else "xlsx"
            if request.POST.get("action") in {"download_pdf", "download_xlsx"}:
                return redirect("viagens_prestacoes:diario_download_formato", pk=diario.pk, formato=formato)
            messages.success(request, "Diário de bordo salvo.")
            return redirect("viagens_prestacoes:rt_servidor", ps_pk=ps.pk)
    else:
        formset = DiarioBordoTrechoFormSet(queryset=queryset)

    linhas = list(queryset)
    trechos = [
        {"form": form, "display": _trecho_display(linha)}
        for form, linha in zip(formset.forms, linhas, strict=True)
    ]

    return render(
        request,
        "pages/viagens_prestacoes/diario_bordo_form.html",
        {
            "page_title": f"Diário de Bordo — {ps.servidor.nome}",
            "prestacao": prestacao,
            "ps": ps,
            "diario": diario,
            "formset": formset,
            "trechos": trechos,
            "opcoes_abastecimento": [{"valor": "sim", "rotulo": "Sim"}, {"valor": "nao", "rotulo": "Não"}],
            "identificacao": _build_identificacao(prestacao),
            **contexto_do_fluxo(ps, "diario"),
            "diaria_info": diaria_info(prestacao),
            "back_url": reverse("viagens_prestacoes:index"),

            "editar_roteiro_url": reverse("viagens_prestacoes:diario_servidor_editar_roteiro", args=[ps.pk]),
            "editar_motorista_url": reverse("viagens_prestacoes:diario_servidor_motorista", args=[ps.pk]),
            "motorista_resumo": _motorista_resumo(diario),
            "viatura_resumo": viatura_resumo_diario(diario),
            "alteracoes_roteiro": alteracoes_datas_horarios_roteiro(prestacao),
            "rt_url": reverse("viagens_prestacoes:rt_servidor", args=[ps.pk]),
            "documentos_url": reverse("viagens_prestacoes:documentos_servidor", args=[ps.pk]),
            "autosave_url": reverse("viagens_prestacoes:diario_servidor_autosave", args=[ps.pk]),
            "preview_inline_url": reverse("viagens_prestacoes:diario_download_formato", args=[diario.pk, "pdf"]) + "?inline=1",
            "preview_pdf_url": reverse("viagens_prestacoes:diario_download_formato", args=[diario.pk, "pdf"]),
            "preview_xlsx_url": reverse("viagens_prestacoes:diario_download_formato", args=[diario.pk, "xlsx"]),
            # O modal "Trocar motorista / viatura" (o mesmo formulário da página própria).
            **_contexto_motorista(ps, prestacao, diario, motorista_form or DiarioMotoristaForm(instance=diario, oficio=prestacao.oficio)),
            "abrir_modal_motorista": motorista_form is not None,
        },
    )


def diario_servidor_autosave(request, ps_pk):
    ps = get_object_or_404(_prestacao_servidor_queryset().select_related("prestacao"), pk=ps_pk)
    diario = get_object_or_404(_diario_queryset(), prestacao=ps.prestacao)
    sincronizar_trechos(diario)
    try:
        payload = parse_autosave_payload(request, expected_model="diario_bordo")
    except AutosavePayloadError as exc:
        return autosave_json_response(ok=False, message=str(exc))

    try:
        salvar_autosave_do_diario(
            diario,
            fields=payload.fields,
            dirty_fields=payload.dirty_fields,
            escopo=ESCOPO_SERVIDOR,
            servidor_prestacao=ps,
        )
    except DiarioValidacaoError as exc:
        # `NOVO-116`: km invertido é erro do operador, não falha do servidor. Sem isto
        # a violação da constraint subia como `IntegrityError` e virava 500.
        return autosave_json_response(ok=False, message=str(exc))
    return autosave_json_response(
        ok=True,
        object_id=diario.pk,
        version=_autosave_version(diario),
    )


def diario_autosave(request, pk):
    diario = get_object_or_404(_diario_queryset().select_related("prestacao"), pk=pk)
    sincronizar_trechos(diario)
    try:
        payload = parse_autosave_payload(request, expected_model="diario_bordo")
    except AutosavePayloadError as exc:
        return autosave_json_response(ok=False, message=str(exc))

    try:
        salvar_autosave_do_diario(
            diario,
            fields=payload.fields,
            dirty_fields=payload.dirty_fields,
            escopo=ESCOPO_EQUIPE,
        )
    except DiarioValidacaoError as exc:
        # Ver `diario_servidor_autosave`: mesma tradução, mesma razão (`NOVO-116`).
        return autosave_json_response(ok=False, message=str(exc))
    return autosave_json_response(
        ok=True,
        object_id=diario.pk,
        version=_autosave_version(diario),
    )


def diario_editar_roteiro(request, pc_pk):
    """Compatibilidade: redireciona para o primeiro servidor."""
    prestacao = get_object_or_404(_prestacao_queryset(), pk=pc_pk)
    return _redirect_primeiro_servidor(request, prestacao, "viagens_prestacoes:diario_servidor_editar_roteiro")


def diario_servidor_editar_roteiro(request, ps_pk):
    """Abre o editor de roteiro sobre a cópia da prestação (clona do ofício na 1ª vez)."""
    ps = get_object_or_404(
        _prestacao_servidor_queryset().select_related("prestacao__oficio__roteiro"),
        pk=ps_pk,
    )
    prestacao = ps.prestacao
    copia = garantir_roteiro_ajustado(prestacao)
    diario_url = reverse("viagens_prestacoes:diario_servidor", args=[ps.pk])
    if copia is None:
        messages.error(request, "Este ofício não possui roteiro para editar.")
        return redirect(diario_url)
    editar_url = reverse("viagens_roteiros:editar", args=[copia.pk])
    return redirect(f"{editar_url}?{urlencode({'next': diario_url})}")


def _motorista_resumo(diario) -> dict:
    """Motorista efetivo do diário (considerando a troca) para exibir na Etapa 3."""
    nome, cpf = motorista_diario(diario)
    return {
        "nome": nome or "—",
        "cpf": cpf or "",
        "origem": _MOTORISTA_ORIGEM_LABEL.get(diario.motorista_modo, "Motorista do ofício"),
        "alterado": diario.motorista_alterado,
    }


def _oficio_prefill_dados(oficio) -> dict:
    """Dados de um ofício para auto-preencher o formulário de troca (motorista + viatura)."""

    nome, cpf = motorista_do_oficio(oficio)
    numero = str(oficio.numero or "").strip()
    ano = str(oficio.ano or "").strip()
    numero_ano = f"{numero}/{ano}" if numero and ano else numero

    viatura = {"modo": "", "id": "", "modelo": "", "placa": "", "tipo": "", "combustivel": ""}
    if oficio.viatura_id:
        v = oficio.viatura
        viatura = {
            "modo": DiarioBordo.VIATURA_MODO_BANCO,
            "id": str(oficio.viatura_id),
            "modelo": v.modelo or "",
            "placa": v.placa or "",
            "tipo": v.tipo or "",
            "combustivel": str(v.combustivel) if v.combustivel_id else "",
        }
    elif (oficio.transporte_modelo_manual or oficio.transporte_placa_manual or oficio.transporte_tipo_manual):
        viatura = {
            "modo": DiarioBordo.VIATURA_MODO_MANUAL,
            "id": "",
            "modelo": oficio.transporte_modelo_manual or "",
            "placa": oficio.transporte_placa_manual or "",
            "tipo": oficio.transporte_tipo_manual or "",
            "combustivel": str(oficio.transporte_combustivel_manual) if oficio.transporte_combustivel_manual_id else "",
        }

    label = numero_ano or f"Ofício {oficio.pk}"
    if nome:
        label = f"{label} — {nome}"
    return {
        "id": oficio.pk,
        "label": label,
        "numero_ano": numero_ano,
        "protocolo": format_protocolo(oficio.protocolo) or "",
        "motorista_nome": nome or "",
        "motorista_cpf": format_cpf(cpf) or cpf or "",
        "viatura": viatura,
    }


def diario_motorista(request, pc_pk):
    """Compatibilidade: redireciona para o primeiro servidor."""
    prestacao = get_object_or_404(_prestacao_queryset(), pk=pc_pk)
    return _redirect_primeiro_servidor(request, prestacao, "viagens_prestacoes:diario_servidor_motorista")


def _contexto_motorista(ps, prestacao, diario, form):
    """O que o formulário de motorista/viatura mostra — no modal do diário e na página própria."""
    from viagens_cadastros.models import Viatura
    from .view_common import opcoes

    oficio_nome, oficio_cpf = motorista_do_oficio(prestacao.oficio)
    oficios_prefill = [_oficio_prefill_dados(o) for o in oficios_para_prefill_de_motorista(prestacao.oficio)]
    viatura_oficio = viatura_resumo_oficio(prestacao.oficio)
    valor = lambda nome: (str(getattr(form[nome].value(), "pk", form[nome].value())) if form[nome].value() not in (None, "") else "")
    return {
        "form": form,
        "url_motorista": reverse("viagens_prestacoes:diario_servidor_motorista", args=[ps.pk]),
        "motorista_oficio_nome": oficio_nome or "—",
        "motorista_oficio_cpf": oficio_cpf,
        "motorista_oficio_sufixo_cpf": f" · CPF {oficio_cpf}" if oficio_cpf else "",
        "viatura_oficio": viatura_oficio,
        "viatura_oficio_sufixo_placa": (f" · {viatura_oficio['placa']}" if viatura_oficio.get("placa") else ""),
        "oficios_prefill": oficios_prefill,
        "opcoes_prefill": [{"valor": o["id"], "rotulo": o["label"]} for o in oficios_prefill],
        # Blocos próprios da tela (sem laço genérico): as opções de cada seletor e os valores atuais.
        "valores": {n: valor(n) for n in form.fields},
        "erros": {n: form.errors.get(n) for n in form.fields},
        "opcoes_motorista_modo": opcoes(DiarioBordo.MOTORISTA_MODO_CHOICES),
        "opcoes_viatura_modo": opcoes(DiarioBordo.VIATURA_MODO_CHOICES),
        "opcoes_servidores": [{"valor": str(s.pk), "rotulo": s.nome} for s in form.fields["motorista_servidor"].queryset],
        "opcoes_viaturas": [{"valor": str(v.pk), "rotulo": f"{v.placa_formatada} — {v.modelo}" if v.modelo else v.placa_formatada} for v in form.fields["viatura"].queryset],
        "opcoes_tipos": opcoes(Viatura.Tipo.choices),
        "modo_motorista": valor("motorista_modo") or DiarioBordo.MOTORISTA_MODO_OFICIO,
        "modo_viatura": valor("viatura_modo") or DiarioBordo.VIATURA_MODO_OFICIO,
    }


def diario_servidor_motorista(request, ps_pk):
    """Troca o motorista/viatura apenas deste diário, sem alterar o ofício.

    Na tela, é o modal do diário: o envio grava e volta ao diário; com erro, o
    diário reabre com o modal aberto e os campos marcados. O GET continua
    servindo a página própria (link direto e quem não tem JavaScript).
    """
    ps = get_object_or_404(
        _prestacao_servidor_queryset()
        .select_related("prestacao__oficio", "prestacao__oficio__viatura")
        .prefetch_related(
            "prestacao__oficio__servidores__cargo",
            "prestacao__oficio__servidores__unidade",
        ),
        pk=ps_pk,
    )
    prestacao = ps.prestacao
    diario = obter_ou_criar_diario(prestacao)
    diario_url = reverse("viagens_prestacoes:diario_servidor", args=[ps.pk])

    if request.method == "POST":
        form = DiarioMotoristaForm(request.POST, instance=diario, oficio=prestacao.oficio)
        if form.is_valid():
            trocar_motorista_do_diario(form, prestacao, ps)
            messages.success(request, "Diário de bordo atualizado (motorista/viatura).")
            return redirect(diario_url)
        return diario_servidor(request, ps.pk, motorista_form=form)

    form = DiarioMotoristaForm(instance=diario, oficio=prestacao.oficio)
    return render(
        request,
        "pages/viagens_prestacoes/diario_motorista_form.html",
        {
            "page_title": "Trocar motorista / viatura",
            "prestacao": prestacao,
            "ps": ps,
            "diario": diario,
            "identificacao": _build_identificacao(prestacao),
            **contexto_do_fluxo(ps, "diario", back_label="Voltar ao diário", back_url=diario_url),
            "back_url": reverse("viagens_prestacoes:index"),
            "diario_url": diario_url,
            **_contexto_motorista(ps, prestacao, diario, form),
        },
    )


def diario_download(request, pk, formato="xlsx"):
    diario = get_object_or_404(
        _diario_queryset().select_related(
            "prestacao__oficio__roteiro",
            "prestacao__oficio__viatura",
            "prestacao__oficio__motorista",
        ),
        pk=pk,
    )

    inline = _is_inline_request(request)
    formato = (formato or "xlsx").strip().lower()
    if formato not in {"pdf", "xlsx"}:
        formato = "xlsx"
    return gerar_resposta_documento(
        request,
        tipo="prestacao_diario",
        parametros={"object_id": diario.pk, "formato": formato},
        disposicao="inline" if inline and formato == "pdf" else "attachment",
    )

from .ui import render
