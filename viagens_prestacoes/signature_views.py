from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse

from core.retorno import voltar_para
from documentos.services.exceptions import DocumentValidationError

from .assinatura_services import (
    AssinaturaError,
    assinatura_db,
    assinatura_rt,
    cancelar_assinatura_db,
    cancelar_assinatura_rt,
    emitir_link_db,
    emitir_link_rt,
    signer_db,
    signer_rt,
)
from .models import AssinaturaDocumento
from .view_common import (
    _prestacao_queryset,
    _prestacao_servidor_queryset,
    _primeiro_servidor,
)


def _fallback_da_prestacao(prestacao) -> str:
    """Para onde voltar quando o `next` não vier — ou vier apontando para fora (BE-08)."""
    ps = _primeiro_servidor(prestacao)
    if ps is not None:
        return reverse("viagens_prestacoes:documentos_servidor", args=[ps.pk])
    return reverse("viagens_prestacoes:index")


def _whatsapp_data(link_absoluto, signer, doc_labels) -> dict:
    """Telefone (com DDI) e mensagem; o front monta a URL por app/aparelho no clique."""
    docs_txt = " e ".join(doc_labels)
    msg = (
        "Olá! Para concluir a prestação de contas, preciso da sua assinatura no "
        f"{docs_txt}. Acesse o link, confirme sua identidade e assine: {link_absoluto}"
    )
    telefone = (getattr(signer, "telefone", "") or "").strip() if signer else ""
    fone = f"55{telefone}" if (len(telefone) == 11 and telefone.isdigit()) else ""
    return {"phone": fone, "msg": msg}


def _assinatura_card(request, *, doc, signer, tipo, label, motivo_sem_signer, gerar_url, cancelar_url) -> dict:
    cpf_ok = bool(signer and len((getattr(signer, "cpf", "") or "").strip()) == 11)
    motivo = ""
    if signer is None:
        motivo = motivo_sem_signer
    elif not cpf_ok:
        quem = "motorista" if tipo == AssinaturaDocumento.TIPO_DB else "servidor"
        motivo = f"Cadastre o CPF do {quem} ({signer}) para gerar o link de assinatura."

    assinada = bool(doc and doc.status == AssinaturaDocumento.STATUS_ASSINADA)
    link_ativo = bool(doc and doc.link_ativo)
    link_abs = ""
    wa = {"phone": "", "msg": ""}

    return {
        "tipo": tipo,
        "label": label,
        "signatario": str(signer) if signer else "—",
        "assinada": assinada,
        "assinado_em": doc.assinado_em if assinada else None,
        "codigo": doc.codigo_verificacao if assinada else "",
        "pode_assinar": cpf_ok,
        "motivo": motivo,
        "link_ativo": link_ativo,
        "link_absoluto": link_abs,
        "expira_em": doc.link_expira_em if link_ativo else None,
        "whatsapp_phone": wa["phone"],
        "whatsapp_msg": wa["msg"],
        "gerar_url": gerar_url,
        "cancelar_url": cancelar_url,
    }


def _assinatura_rt_card(request, ps) -> dict:
    return _assinatura_card(
        request,
        doc=assinatura_rt(ps),
        signer=signer_rt(ps),
        tipo=AssinaturaDocumento.TIPO_RT,
        label=f"Relatório Técnico — {ps.servidor.nome}",
        motivo_sem_signer="Servidor da prestação não definido.",
        gerar_url=reverse("viagens_prestacoes:assinatura_rt_gerar", args=[ps.pk]),
        cancelar_url=reverse("viagens_prestacoes:assinatura_rt_cancelar", args=[ps.pk]),
    )


def _assinatura_db_card(request, prestacao) -> dict:
    return _assinatura_card(
        request,
        doc=assinatura_db(prestacao),
        signer=signer_db(prestacao),
        tipo=AssinaturaDocumento.TIPO_DB,
        label="Diário de Bordo",
        motivo_sem_signer="Defina o motorista do ofício para gerar o link.",
        gerar_url=reverse("viagens_prestacoes:assinatura_db_gerar", args=[prestacao.pk]),
        cancelar_url=reverse("viagens_prestacoes:assinatura_db_cancelar", args=[prestacao.pk]),
    )


def assinatura_rt_gerar(request, ps_pk):
    ps = get_object_or_404(
        _prestacao_servidor_queryset().select_related("prestacao__oficio", "servidor"), pk=ps_pk
    )
    forcar = request.POST.get("forcar") == "1"
    next_url = voltar_para(
        request, reverse("viagens_prestacoes:documentos_servidor", args=[ps.pk])
    )
    try:
        token, _docs = emitir_link_rt(ps, dias=request.POST.get("dias", 7), forcar=forcar)
    except (AssinaturaError, DocumentValidationError) as exc:
        messages.error(request, str(exc))
        return redirect(next_url)
    link = request.build_absolute_uri(
        reverse("viagens_assinaturas:assinatura_landing", args=[token])
    )
    from .ui import render
    response = render(request, "viagens_prestacoes/assinatura/link_emitido.html", {"page_title": "Link de assinatura", "link": link, "expira_em": _docs[0].link_expira_em, "voltar_url": next_url})
    response["Cache-Control"] = "private, no-store"
    response["Referrer-Policy"] = "no-referrer"
    return response


def assinatura_db_gerar(request, pc_pk):
    prestacao = get_object_or_404(
        _prestacao_queryset().select_related("oficio__motorista"), pk=pc_pk
    )
    forcar = request.POST.get("forcar") == "1"
    next_url = voltar_para(request, _fallback_da_prestacao(prestacao))
    try:
        token, _docs = emitir_link_db(prestacao, dias=request.POST.get("dias", 7), forcar=forcar)
    except (AssinaturaError, DocumentValidationError) as exc:
        messages.error(request, str(exc))
        return redirect(next_url)
    link = request.build_absolute_uri(
        reverse("viagens_assinaturas:assinatura_landing", args=[token])
    )
    from .ui import render
    response = render(request, "viagens_prestacoes/assinatura/link_emitido.html", {"page_title": "Link de assinatura", "link": link, "expira_em": _docs[0].link_expira_em, "voltar_url": next_url})
    response["Cache-Control"] = "private, no-store"
    response["Referrer-Policy"] = "no-referrer"
    return response


def assinatura_rt_cancelar(request, ps_pk):
    ps = get_object_or_404(_prestacao_servidor_queryset(), pk=ps_pk)
    next_url = voltar_para(
        request, reverse("viagens_prestacoes:documentos_servidor", args=[ps.pk])
    )
    cancelar_assinatura_rt(ps)
    messages.success(request, "Link/assinatura revogados. Os arquivos anteriores foram preservados.")
    return redirect(next_url)


def assinatura_db_cancelar(request, pc_pk):
    prestacao = get_object_or_404(_prestacao_queryset(), pk=pc_pk)
    next_url = voltar_para(request, _fallback_da_prestacao(prestacao))
    cancelar_assinatura_db(prestacao)
    messages.success(request, "Link/assinatura revogados. Os arquivos anteriores foram preservados.")
    return redirect(next_url)
