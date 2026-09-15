from functools import wraps
from .arquivos import transacao_de_arquivos
from django.shortcuts import render as django_render
from django.http import HttpResponse
from django.utils.http import content_disposition_header
from viagens_oficios.view_helpers import campos_v32
from viagens_cadastros.permissions import acesso_ao_modulo
from viagens_oficios.views import exigir_operador
from documentos.services.exceptions import DocumentValidationError
from documentos.services.types import DocumentoFormato
from documentos.services.responses import get_content_type_for_format


def acesso(view):
    @wraps(view)
    @acesso_ao_modulo
    def wrapper(request, *args, **kwargs):
        if request.method not in {"GET", "HEAD", "OPTIONS"}:
            exigir_operador(request)
        from .carimbo_services import CarimboError
        try:
            with transacao_de_arquivos():
                return view(request, *args, **kwargs)
        except CarimboError as exc:
            from .view_common import _preview_error_response
            return _preview_error_response(exc)
    return wrapper


def render(request, template, context, **kwargs):
    context = dict(context)
    context.setdefault("page_title", "Prestações de contas")
    if template.endswith("documentos_form.html"):
        from django.urls import reverse
        from .models import PrestacaoDocumentoAnexo as Anexo
        ps = context["ps"]; pc = ps.prestacao
        context.update(numero_name=f"ps-{ps.pk}-numero_solicitacao", liberacao_name=f"ps-{ps.pk}-data_liberacao_diarias", prazo_name=f"ps-{ps.pk}-prazo_limite_saque", liberacao_iso=ps.data_liberacao_diarias.isoformat() if ps.data_liberacao_diarias else "", prazo_iso=ps.prazo_limite_saque.isoformat() if ps.prazo_limite_saque else "")
        specs = [("despacho", "Despacho assinado", Anexo.TIPO_DESPACHO, "prestacao_despacho_assinado_anexar", [pc.pk]), ("oficio", "Ofício assinado", Anexo.TIPO_OFICIO_ASSINADO, "prestacao_oficio_assinado_anexar", [pc.pk]), ("comprovante", "Comprovante de saque ou transferência", Anexo.TIPO_COMPROVANTE, "prestacao_servidor_assinado_anexar", [ps.pk, "comprovante"]), ("rt", "Relatório técnico assinado", Anexo.TIPO_RT_ASSINADO, "prestacao_servidor_assinado_anexar", [ps.pk, Anexo.TIPO_RT_ASSINADO])]
        specs.append(("diario", "Diário de bordo assinado", Anexo.TIPO_DB_ASSINADO, "prestacao_servidor_assinado_anexar", [ps.pk, Anexo.TIPO_DB_ASSINADO]))
        context["uploads"] = [{"id": id_, "titulo": titulo, "url": reverse("viagens_prestacoes:"+rota, args=args), "anexos": pc.documentos_anexos.filter(tipo=tipo) if tipo in [Anexo.TIPO_DESPACHO, Anexo.TIPO_OFICIO_ASSINADO, Anexo.TIPO_DB_ASSINADO] else ps.documentos_anexos.filter(tipo=tipo)} for id_,titulo,tipo,rota,args in specs]
        for item in context["uploads"]:
            item["campo"] = "arquivo"
            if item["id"] in {"despacho", "comprovante"}:
                item["multiplo"] = True
                item["campo"] = "despacho_arquivos" if item["id"] == "despacho" else f"ps-{ps.pk}-comprovante_arquivos"
                item["url"] = reverse("viagens_prestacoes:" + ("prestacao_arquivo_autosave" if item["id"] == "despacho" else "prestacao_servidor_arquivo_autosave"), args=[pc.pk if item["id"] == "despacho" else ps.pk])
    if context.get("ps"):
        from .services import diaria_recebida_display
        context["diaria_name"] = f"ps-{context['ps'].pk}-diaria_valor_override"
        context["diaria_recebida"] = diaria_recebida_display(context['ps'])
    if context.get("relatorio"):
        from .models import ModeloTextoRelatorioTecnico
        context["modelos_texto"] = {str(m.pk): m.texto for m in ModeloTextoRelatorioTecnico.objects.all()}
    if "form" in context:
        context["campos"] = campos_v32(context["form"])
        if template.endswith("relatorio_tecnico_form.html"):
            por_nome = {c["name"]: c for c in context["campos"]}
            ordem = ["diaria", "translado", "translado_outro", "combustivel", "combustivel_outro", "passagem", "passagem_outro"]
            for nome in ["motivo", "atividade", "conclusao", "medidas", "info_complementares"]:
                ordem.extend(["modelo_" + nome, nome])
            context["campos"] = [por_nome[n] for n in ordem if n in por_nome]
    if "oficios_prefill" in context:
        context["opcoes_prefill"] = [{"valor": str(o["id"]), "rotulo": o["label"]} for o in context["oficios_prefill"]]
    for trecho in context.get("trechos", []):
        trecho["campos"] = campos_v32(trecho["form"])
    return django_render(request, template, context, **kwargs)


def resposta_bytes(request, content, filename, formato):
    response = HttpResponse(content, content_type=get_content_type_for_format(DocumentoFormato(formato)))
    response["Content-Disposition"] = content_disposition_header(request.GET.get("inline") != "1", filename)
    response["Cache-Control"] = "private, no-store"
    response["X-Content-Type-Options"] = "nosniff"
    return response


def gerar_resposta_documento(request, *, tipo, parametros, disposicao="attachment"):
    from .view_common import _prestacao_servidor_full, _diario_queryset, _preview_error_response
    from django.shortcuts import get_object_or_404
    from .services import gerar_relatorio_tecnico_documento
    from .rt_services import obter_ou_criar_relatorio_tecnico
    from .diario_services import gerar_diario_bordo_documento
    formato = DocumentoFormato(parametros["formato"])
    try:
        if tipo == "prestacao_rt":
            ps = _prestacao_servidor_full(parametros["object_id"])
            doc = gerar_relatorio_tecnico_documento(obter_ou_criar_relatorio_tecnico(ps.prestacao), ps, formato)
        else:
            diario = get_object_or_404(_diario_queryset(), pk=parametros["object_id"])
            doc = gerar_diario_bordo_documento(diario, formato)
    except DocumentValidationError as exc:
        return _preview_error_response(exc)
    return resposta_bytes(request, doc.conteudo, doc.nome_arquivo, formato.value)
