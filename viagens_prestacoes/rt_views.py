from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse

from core.autosave import (
    AutosavePayloadError,
    autosave_json_response,
    parse_autosave_payload,
)
from .ui import gerar_resposta_documento

from .diario_services import diaria_info
from .forms import (
    RelatorioTecnicoForm,
)
from .rt_services import ESCOPO_EQUIPE
from .rt_services import ESCOPO_SERVIDOR
from .rt_services import obter_ou_criar_relatorio_tecnico
from .rt_services import salvar_rt_do_autosave
from .rt_services import salvar_rt_do_formulario
from .rt_services import criar_modelo_do_campo
from .rt_services import rts_para_copiar
from .rt_services import sugestoes_iniciais_rt
from .services import (
    diaria_inicial_da_prestacao,
    garantir_campos_padrao_relatorio_tecnico,
)
from .view_common import (
    _autosave_version,
    _build_campos_custeio,
    _build_campos_modelo,
    _build_identificacao,
    contexto_do_fluxo,
    _is_inline_request,
    _prestacao_queryset,
    _prestacao_servidor_full,
    _prestacao_servidor_queryset,
    _redirect_primeiro_servidor,
    _relatorio_queryset,
)


def _servidor_rt_ctx(ps):
    return {
        "ps_pk": ps.pk,
        "nome": ps.servidor.nome,
        "is_motorista": ps.is_motorista,
        # O selo também acende quando só sobrou a observação: é o caso dos
        # valores legados que a migração não conseguiu virar número, e são
        # justamente os que alguém precisa olhar.
        "diaria_ajustada": bool(
            ps.diaria_valor_override is not None
            or ps.diaria_valor_override_observacao
        ),
        "download_pdf_url": reverse(
            "viagens_prestacoes:rt_download_servidor_formato", args=[ps.pk, "pdf"]
        ),
        "download_docx_url": reverse(
            "viagens_prestacoes:rt_download_servidor_formato", args=[ps.pk, "docx"]
        ),
        "preview_inline_url": reverse(
            "viagens_prestacoes:rt_download_servidor_formato", args=[ps.pk, "pdf"]
        ) + "?inline=1",
    }


def rt_criar(request, pc_pk):
    """Compatibilidade: redireciona para o primeiro servidor."""
    prestacao = get_object_or_404(_prestacao_queryset(), pk=pc_pk)
    return _redirect_primeiro_servidor(request, prestacao, "viagens_prestacoes:rt_servidor")


def rt_servidor(request, ps_pk):
    """Edição do texto compartilhado do RT; preview/download só do servidor atual."""
    ps = _prestacao_servidor_full(ps_pk)
    prestacao = ps.prestacao

    relatorio = obter_ou_criar_relatorio_tecnico(prestacao)
    garantir_campos_padrao_relatorio_tecnico(relatorio)
    identificacao = _build_identificacao(prestacao)

    if request.method == "POST":
        form = RelatorioTecnicoForm(request.POST, instance=relatorio, relatorio=relatorio)
        if form.is_valid():
            resultado = salvar_rt_do_formulario(
                form, prestacao, campos_diaria=request.POST, servidor_prestacao=ps
            )
            if resultado.erros:
                for mensagens in resultado.erros.values():
                    for mensagem in mensagens:
                        messages.error(request, mensagem)
            else:
                messages.success(request, "Texto do relatório técnico salvo.")
            if not resultado.erros and request.POST.get("continuar"):
                return redirect("viagens_prestacoes:documentos_servidor", ps_pk=ps.pk)
            return redirect("viagens_prestacoes:rt_servidor", ps_pk=ps.pk)
    else:
        initial = {}
        if not relatorio.diaria:
            initial["diaria"] = diaria_inicial_da_prestacao(prestacao)
        # m097: os textos vazios começam com o que o ofício, a viagem e o plano já dizem.
        for campo, texto in sugestoes_iniciais_rt(prestacao).items():
            if not (getattr(relatorio, campo) or "").strip():
                initial[campo] = texto
        form = RelatorioTecnicoForm(instance=relatorio, relatorio=relatorio, initial=initial)

    servidores_ctx = [_servidor_rt_ctx(ps)]
    rt_url = reverse("viagens_prestacoes:rt_servidor", args=[ps.pk])
    from .view_common import opcoes
    campos_custeio = _build_campos_custeio(form)
    for campo in campos_custeio:
        if campo["uses_other"]:
            campo["opcoes"] = opcoes(campo["field"].field.choices)
            campo["valor"] = form[campo["campo"]].value() or ""
            campo["valor_outro"] = form[f"{campo['campo']}_outro"].value() or ""
            campo["erros_outro"] = form.errors.get(f"{campo['campo']}_outro")
        campo["erros"] = form.errors.get(campo["campo"])
    campos_modelo = _build_campos_modelo(form, return_url=rt_url)
    for campo in campos_modelo:
        campo["opcoes"] = [{"valor": str(m.pk), "rotulo": m.nome} for m in campo["select"].field.queryset]
        campo["valor_modelo"] = form[f"modelo_{campo['campo']}"].value() or ""
        campo["texto"] = form[campo["campo"]].value() or ""
        campo["erros"] = form.errors.get(campo["campo"])

    return render(
        request,
        "pages/viagens_prestacoes/relatorio_tecnico_form.html",
        {
            "page_title": f"Relatório Técnico — {ps.servidor.nome}",
            "form": form,
            "campos_modelo": campos_modelo,
            "campos_custeio": campos_custeio,
            "valor_diaria": form["diaria"].value() or "",
            "erros_diaria": form.errors.get("diaria"),
            "modelos_url": reverse("viagens_cadastros:lista", args=["modelos-texto-rt"]),
            "relatorio": relatorio,
            "prestacao": prestacao,
            "ps": ps,
            "identificacao": identificacao,
            "servidores": servidores_ctx,
            **contexto_do_fluxo(ps, "rt"),
            "diaria_info": diaria_info(prestacao),
            "back_url": reverse("viagens_prestacoes:index"),
            "documentos_url": reverse("viagens_prestacoes:documentos_servidor", args=[ps.pk]),
            "diario_url": reverse("viagens_prestacoes:diario_servidor", args=[ps.pk]),
            "autosave_url": reverse("viagens_prestacoes:rt_servidor_autosave", args=[ps.pk]),
            "preview_inline_url": servidores_ctx[0]["preview_inline_url"],
            # m097: copiar os textos de outra prestação do mesmo evento ou destino, e salvar um texto como modelo.
            "rts_copiar": rts_para_copiar(prestacao),
            "modelo_criar_url": reverse("viagens_prestacoes:modelo_criar_do_campo"),
        },
    )


def modelo_criar_do_campo(request):
    """"Salvar como modelo" ao lado de um texto do RT (m097): grava e devolve o modelo novo."""
    from django.http import JsonResponse

    try:
        modelo = criar_modelo_do_campo(
            request.POST.get("campo", ""), request.POST.get("nome", ""), request.POST.get("texto", "")
        )
    except ValueError as exc:
        return JsonResponse({"ok": False, "message": str(exc)}, status=400)
    return JsonResponse({"ok": True, "id": modelo.pk, "nome": modelo.nome, "campo": modelo.campo})


def rt_servidor_autosave(request, ps_pk):
    ps = get_object_or_404(_prestacao_servidor_queryset().select_related("prestacao"), pk=ps_pk)
    relatorio = get_object_or_404(_relatorio_queryset(), prestacao=ps.prestacao)
    try:
        payload = parse_autosave_payload(request, expected_model="relatorio_tecnico")
    except AutosavePayloadError as exc:
        return autosave_json_response(ok=False, message=str(exc))

    resultado = salvar_rt_do_autosave(
        relatorio,
        ps.prestacao,
        fields=payload.fields,
        dirty_fields=payload.dirty_fields,
        escopo=ESCOPO_SERVIDOR,
        servidor_prestacao=ps,
    )
    if resultado.erros:
        return autosave_json_response(
            ok=False,
            errors=resultado.erros,
            message="O valor da diária não foi salvo.",
        )
    return autosave_json_response(
        ok=True,
        object_id=relatorio.pk,
        version=_autosave_version(relatorio),
    )


def rt_autosave(request, pk):
    relatorio = get_object_or_404(_relatorio_queryset(), pk=pk)
    try:
        payload = parse_autosave_payload(request, expected_model="relatorio_tecnico")
    except AutosavePayloadError as exc:
        return autosave_json_response(ok=False, message=str(exc))

    resultado = salvar_rt_do_autosave(
        relatorio,
        relatorio.prestacao,
        fields=payload.fields,
        dirty_fields=payload.dirty_fields,
        escopo=ESCOPO_EQUIPE,
    )
    if resultado.erros:
        # O texto do RT já foi salvo acima; o que não entrou foi só o valor
        # recusado. Salvar automaticamente um valor que a regra proíbe seria
        # pior que devolver erro: ninguém revisa o que salvou sozinho.
        return autosave_json_response(
            ok=False,
            errors=resultado.erros,
            message="O valor da diária não foi salvo.",
        )
    return autosave_json_response(
        ok=True,
        object_id=relatorio.pk,
        version=_autosave_version(relatorio),
    )


def rt_download_servidor(request, ps_pk, formato="docx"):
    ps = get_object_or_404(
        _prestacao_servidor_queryset().select_related(
            "prestacao__oficio__roteiro", "servidor"
        ),
        pk=ps_pk,
    )
    inline = _is_inline_request(request)
    formato = (formato or "docx").strip().lower()
    if formato not in {"pdf", "docx"}:
        formato = "docx"
    return gerar_resposta_documento(
        request,
        tipo="prestacao_rt",
        parametros={"object_id": ps.pk, "formato": formato},
        disposicao="inline" if inline and formato == "pdf" else "attachment",
    )

from .ui import render
