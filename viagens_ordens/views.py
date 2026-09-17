"""Ordens de serviço — lista, cadastro numa página só, documento e ações.

O app `ordens_servico` da origem na pele V3.2: lista com situações e busca,
formulário com os seis blocos do GV em cartões numerados (ofícios, necessidade,
motivo, período, destinos, equipe), DOCX/PDF pela façade documental, anexação
do PDF assinado, cancelar/reativar/excluir. A OS pode nascer de uma viagem
(`?viagem=`), que a semeia e para onde ela volta ao salvar.
"""

from django import forms
from django.contrib import messages
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.http import Http404, JsonResponse
from django.shortcuts import redirect, render
from django.urls import NoReverseMatch, reverse
from django.views.decorators.http import require_GET, require_POST, require_http_methods

from core.deletion import DelecaoProtegidaError
from core.listagens import ITENS_POR_PAGINA
from core.retorno import com_next, daqui, next_valido, voltar_para
from core.utils.masks import format_protocolo
from documentos.services.exceptions import DocumentError
from documentos.services.types import DocumentoFormato
from viagens_cadastros.permissions import acesso_ao_modulo, pode_editar_cadastros
from viagens_oficios.picker import LIMITE_BUSCA, pks_ja_escolhidos
from viagens_oficios.presenters import iniciais
from viagens_oficios.roteiro_context import periodo_roteiro
from viagens_oficios.views import exigir_operador, resposta_documento
from viagens_viagem.services import destinos_para_formulario, semente_de_documentos, viagem_do_request

from . import abas as abas_de_ordem
from .forms import OrdemServicoForm
from .models import OrdemServico
from .presenters import artefatos_pdf_por_ordem, assinante_da_ordem, linha_da_lista, selo_temporal
from .selectors import get_ordem_by_id, listar_ordens
from .services import excluir_ordem_servico, gerar_ordem_servico

# Título e dica de cada cartão de necessidade, como na origem (`_motivo_body.html`).
DICAS_DE_NECESSIDADE = {
    OrdemServico.TIPO_PADRAO: "Mantém o texto livre usado nas OS atuais.",
    OrdemServico.TIPO_OPERACAO_RETORNO_POSTERIOR: "Justifica permanência da equipe policial um dia após a operação.",
    OrdemServico.TIPO_CAMINHAO: "Inclui motorista, técnico e apoios de montagem/escolta, com dois dias antes e depois.",
    OrdemServico.TIPO_MICROONIBUS: "Inclui motorista, técnico e apoios de montagem/escolta, sem regra de dois dias.",
    OrdemServico.TIPO_CERIMONIAL_ANTECIPADO: "Justifica ida antecipada da equipe de cerimonial para organizar a solenidade.",
}


def _digitos(valor):
    return "".join(c for c in str(valor or "") if c.isdigit())


def _municipio_label(m):
    return f"{m.nome}/{m.estado.sigla}" if m is not None else ""


def resumo_do_oficio(oficio):
    """O que a tela copia do ofício ao vinculá-lo: datas, servidores, motivo e destino.

    É o `_build_oficio_summary` da origem. As chaves são as que o script da
    página lê; o resto alimenta a busca e a segunda linha da opção.
    """
    data_inicio = data_fim = periodo = ""
    cidade_ids, estado_id, cidade_id = [], "", ""
    destino = roteiro_label = sede = ""
    roteiro = oficio.roteiro if oficio.roteiro_id else None
    if roteiro is not None:
        sede = _municipio_label(roteiro.origem_municipio) if roteiro.origem_municipio_id else ""
        destinos = sorted((d for d in roteiro.destinos.all() if d.municipio_id), key=lambda d: (d.ordem, d.pk))
        primeiro = destinos[0] if destinos else None
        destino = _municipio_label(primeiro.municipio) if primeiro else ""
        destinos_label = ", ".join(_municipio_label(d.municipio) for d in destinos)
        roteiro_label = " -> ".join(p for p in [sede, destinos_label or destino] if p)
        if primeiro:
            estado_id, cidade_id = primeiro.municipio.estado_id, primeiro.municipio_id
        cidade_ids = [d.municipio_id for d in destinos]
        saida, retorno = periodo_roteiro(roteiro)
        if saida:
            inicio_txt = saida.strftime("%d/%m/%Y")
            data_inicio = saida.date().isoformat()
            fim_txt = retorno.strftime("%d/%m/%Y") if retorno else inicio_txt
            data_fim = retorno.date().isoformat() if retorno else data_inicio
            periodo = inicio_txt if fim_txt == inicio_txt else f"{inicio_txt} a {fim_txt}"

    servidores = list(oficio.servidores.all())
    servidores_nomes = [s.nome for s in servidores]
    viatura = ""
    viatura_modelo = ""
    if oficio.viatura_id:
        viatura = " ".join(p for p in [oficio.viatura.placa_formatada, oficio.viatura.modelo] if p)
        viatura_modelo = oficio.viatura.modelo or ""
    numero = oficio.numero_formatado
    protocolo = format_protocolo(oficio.protocolo) or ""
    return {
        "id": oficio.pk,
        "label": f"Ofício {numero}",
        "numero": numero,
        "numero_busca": " ".join(p for p in [str(oficio.numero or ""), str(oficio.ano or ""), _digitos(numero)] if p),
        "protocolo": protocolo,
        "protocolo_busca": _digitos(oficio.protocolo),
        "sede": sede,
        "destino": destino,
        "roteiro": roteiro_label,
        "periodo": periodo,
        "data_inicio": data_inicio,
        "data_fim": data_fim,
        "cidade_ids": cidade_ids,
        "estado_id": estado_id,
        "cidade_id": cidade_id,
        "servidor_ids": [s.pk for s in servidores],
        "viatura_id": oficio.viatura_id or "",
        "servidores": len(servidores),
        "servidores_nomes": servidores_nomes,
        "servidores_label": ", ".join(servidores_nomes),
        "viatura": viatura,
        "viatura_modelo": viatura_modelo,
        "motivo": oficio.motivo or "",
        "search_text": " ".join(p for p in [
            numero, str(oficio.numero or ""), str(oficio.ano or ""), _digitos(numero), protocolo, _digitos(oficio.protocolo),
            sede, destino, roteiro_label, periodo, viatura, viatura_modelo, " ".join(servidores_nomes), oficio.assunto or "",
        ] if p),
    }


def _oficios_com_o_que_o_resumo_le(queryset):
    return queryset.select_related("roteiro__origem_municipio__estado", "viatura").prefetch_related(
        "roteiro__destinos__municipio__estado", "servidores",
    )


@acesso_ao_modulo
@require_GET
def api_buscar_oficios(request):
    """Busca de ofícios para o seletor da OS: até 30, nunca cancelados."""
    from viagens_oficios.selectors import _filtro_busca, base_oficios

    q = request.GET.get("q", "").strip()
    queryset = base_oficios().filter(cancelado=False)
    if q:
        queryset = queryset.filter(_filtro_busca(q)).distinct()
    queryset = _oficios_com_o_que_o_resumo_le(queryset).order_by("-ano", "-numero", "-pk")[:LIMITE_BUSCA]
    return JsonResponse({"resultados": [resumo_do_oficio(o) for o in queryset]})


def _detalhes_da_opcao(resumo):
    rota = resumo["roteiro"] or resumo["destino"]
    return " · ".join(p for p in [resumo["protocolo"], rota, resumo["periodo"], resumo["viatura"], resumo["servidores_label"]] if p)


def opcoes_de_oficio(form):
    """Ofícios do seletor da seção 1 e o resumo de cada um, que a tela copia ao marcar."""
    escolhidos = set(pks_ja_escolhidos(form, "oficios"))
    opcoes, resumos = [], {}
    for oficio in _oficios_com_o_que_o_resumo_le(form.fields["oficios"].queryset):
        resumo = resumo_do_oficio(oficio)
        resumos[str(oficio.pk)] = resumo
        opcoes.append({"valor": str(oficio.pk), "rotulo": resumo["label"], "detalhes": _detalhes_da_opcao(resumo),
                       "selecionado": str(oficio.pk) in escolhidos})
    return opcoes, resumos


def opcoes_de_servidor(form):
    escolhidos = set(pks_ja_escolhidos(form, "servidores"))
    opcoes = []
    for s in form.fields["servidores"].queryset:
        detalhes = " · ".join(p for p in [str(s.cargo) if s.cargo_id else "", (s.unidade.sigla or s.unidade.nome) if s.unidade_id else ""] if p)
        opcoes.append({"valor": str(s.pk), "rotulo": s.nome, "detalhes": detalhes, "selecionado": str(s.pk) in escolhidos,
                       "iniciais": iniciais(s.nome), "dados": {"iniciais": iniciais(s.nome)}})
    return opcoes


def _valor(form, nome):
    valor = form[nome].value()
    if valor in (None, ""):
        return ""
    if hasattr(valor, "isoformat"):
        return valor.isoformat()
    return str(getattr(valor, "pk", valor))


def ordem_esta_completa(form):
    """Decide o rótulo do botão: "Finalizar Ordem de Serviço" ou "Salvar como rascunho".

    A régua da origem: período, destino, equipe, tipo e motivo preenchidos. A
    equipe é a lista de servidores em qualquer tipo — o script da página já
    decidia assim, e os papéis fixos não têm mais campo na tela.
    """
    if form.is_bound:
        dados = form.data
        tem_datas = bool(dados.get("data_evento_inicio")) and bool(dados.get("data_evento_fim"))
        tem_destino = bool(dados.get("destino_cidade"))
        tem_equipe = bool(dados.getlist("servidores"))
        tem_tipo = bool((dados.get("tipo_necessidade") or "").strip())
        tem_motivo = bool((dados.get("motivo") or "").strip())
    else:
        ordem = form.instance
        tem_datas = bool(ordem.data_evento_inicio) and bool(ordem.data_evento_fim)
        tem_destino = bool(form.initial.get("destino_cidade"))
        tem_equipe = ordem.servidores.exists() if ordem.pk else bool(form.initial.get("servidores"))
        tem_tipo = bool((ordem.tipo_necessidade or "").strip())
        tem_motivo = bool((ordem.motivo or "").strip())
    return tem_datas and tem_destino and tem_equipe and tem_tipo and tem_motivo


def _contexto_form(form, ordem, request):
    from cadastros.models import Estado, Municipio

    estados = [{"valor": str(e.pk), "rotulo": f"{e.sigla} — {e.nome}"} for e in Estado.objects.order_by("sigla")]
    municipios = [{"valor": str(m.pk), "rotulo": m.nome, "estado": str(m.estado_id)} for m in Municipio.objects.order_by("nome")]
    adicionais = [
        {"i": i, "nome_estado": f"extra_estado_{i}", "nome_cidade": f"extra_cidade_{i}", "id_estado": f"id_extra_estado_{i}",
         "estado": _valor(form, f"extra_estado_{i}"), "cidade": _valor(form, f"extra_cidade_{i}"),
         "erros_estado": form.errors.get(f"extra_estado_{i}"), "erros_cidade": form.errors.get(f"extra_cidade_{i}")}
        for i in range(form.quantidade_destinos)
    ]
    oficios, resumos = opcoes_de_oficio(form)
    modelos = list(form.fields["modelo_motivo"].queryset)
    tipo_atual = _valor(form, "tipo_necessidade") or OrdemServico.TIPO_PADRAO
    aqui = daqui(request)
    if ordem.pk:
        selo, selo_tom = ("Cancelada", "cancelada") if ordem.cancelado else selo_temporal(ordem)
    else:
        selo, selo_tom = "", ""
    return {
        "form": form, "ordem": ordem,
        "valores": {n: _valor(form, n) for n in ["destino_estado", "destino_cidade", "data_evento_inicio", "data_evento_fim", "modelo_motivo", "motivo"]},
        "erros": {n: form.errors.get(n) for n in form.fields},
        "erros_gerais": form.non_field_errors(),
        "tipos_necessidade": [{"valor": chave, "rotulo": rotulo, "dica": DICAS_DE_NECESSIDADE.get(chave, ""), "marcado": chave == tipo_atual}
                              for chave, rotulo in OrdemServico.TIPO_NECESSIDADE_CHOICES],
        "servidores": opcoes_de_servidor(form),
        "oficios": oficios, "resumos_oficios": resumos,
        "estados": estados, "municipios": municipios,
        "adicionais": adicionais, "quantidade_destinos": str(form.quantidade_destinos),
        "opcoes_motivos": [{"valor": str(m.pk), "rotulo": m.nome} for m in modelos],
        "modelos_texto": {str(m.pk): m.texto for m in modelos},
        "url_modelos_motivo": com_next(reverse("viagens_cadastros:lista", args=["motivos-oficio"]), aqui),
        "url_novo_servidor": com_next(reverse("viagens_cadastros:novo", args=["servidores"]), aqui),
        "funcoes_servidores": dict(ordem.funcoes_servidores or {}) if ordem.pk else {},
        "os_completa": ordem_esta_completa(form),
        "next": next_valido(request),
        "url_voltar": voltar_para(request, _url_da_lista(ordem)),
        "titulo": f"Editar {ordem.numero_formatado}" if ordem.pk else "Nova Ordem de Serviço",
        "selo": selo, "selo_tom": selo_tom,
        "pode_editar": pode_editar_cadastros(request.user),
        "url_atual": aqui,
    }


def _url_da_lista(ordem):
    """A lista, ou a etapa 4 da viagem quando a OS nasceu de uma — que é a lista daquele fluxo."""
    if ordem is not None and ordem.viagem_id:
        try:
            return reverse("viagens_viagem:etapa", args=[ordem.viagem_id, 4])
        except NoReverseMatch:
            pass
    return reverse("viagens_ordens:lista")


@acesso_ao_modulo
def lista(request):
    q = request.GET.get("q", "").strip()
    escolhidas = abas_de_ordem.normalizar_abas(request.GET.getlist("situacao"))
    base = listar_ordens(q)
    queryset = listar_ordens(q, situacoes=escolhidas)
    paginator = Paginator(queryset, ITENS_POR_PAGINA)
    pagina = paginator.get_page(request.GET.get("pagina"))
    parametros = request.GET.copy()
    parametros.pop("pagina", None)
    assinante = assinante_da_ordem()
    artefatos = artefatos_pdf_por_ordem(pagina.object_list)
    linhas = [linha_da_lista(o, assinante=assinante, artefato_pdf=artefatos.get(o.pk)) for o in pagina]

    def url_da_situacao(aba=None):
        destino = parametros.copy()
        destino.pop("situacao", None)
        if aba:
            destino["situacao"] = aba
        return "?" + destino.urlencode()

    icones = {
        abas_de_ordem.ABA_FUTURAS: "calendar",
        abas_de_ordem.ABA_ATUAIS: "clock",
        abas_de_ordem.ABA_FINALIZADOS: "check-circle",
        abas_de_ordem.ABA_CANCELADOS: "ban",
    }
    situacoes = [{"slug": "todas", "titulo": "Todas", "total": base.count(), "icone": "checklist", "url": url_da_situacao()}] + [
        {"slug": chave, "titulo": rotulo, "total": base.filter(abas_de_ordem.q_da_aba(chave)).count(),
         "icone": icones[chave], "url": url_da_situacao(chave)}
        for chave, rotulo in abas_de_ordem.ABA_ROTULOS
    ]
    return render(request, "pages/viagens_ordens/lista.html", {
        "linhas": linhas, "pagina": pagina, "querystring": parametros.urlencode(), "q": q,
        "paginas_visiveis": list(paginator.get_elided_page_range(pagina.number, on_each_side=1, on_ends=1)),
        "elipse": paginator.ELLIPSIS,
        "situacoes": situacoes,
        "situacoes_escolhidas": escolhidas,
        "situacao_ativa": "todas" if not escolhidas else escolhidas[0] if len(escolhidas) == 1 else "",
        "tem_filtros": bool(q or escolhidas), "url_atual": daqui(request),
        "pode_editar": pode_editar_cadastros(request.user),
    })


def _ordem_nova(request):
    """A OS em branco, ou semeada pela viagem de `?viagem=` — como `nova()` na origem."""
    viagem = viagem_do_request(request)
    semente = semente_de_documentos(viagem) if viagem is not None else None
    if semente is None:
        return OrdemServico(), {}
    ordem = OrdemServico(
        viagem=viagem,
        data_evento_inicio=semente.get("data_inicio"),
        data_evento_fim=semente.get("data_fim") or semente.get("data_inicio"),
        motivo=semente.get("motivo") or "",
    )
    initial = {}
    if semente.get("estado"):
        initial["destino_estado"] = semente["estado"].pk
    if semente.get("cidade"):
        initial["destino_cidade"] = semente["cidade"].pk
    destinos = destinos_para_formulario(semente)
    if len(destinos) > 1:
        initial["destinos_seed"] = destinos
    if semente.get("servidores"):
        initial["servidores"] = [s.pk for s in semente["servidores"]]
    if semente.get("oficios"):
        initial["oficios"] = [o.pk for o in semente["oficios"]]
    return ordem, initial


@acesso_ao_modulo
@require_http_methods(["GET", "POST"])
def editar(request, pk=None):
    # Sem tela de detalhe, esta é a única tela da OS: quem só consulta precisa
    # poder abri-la. Criar e gravar seguem exigindo operador.
    if request.method == "POST" or not pk:
        exigir_operador(request)
    if pk:
        ordem, initial = get_ordem_by_id(pk), {}
    else:
        ordem, initial = _ordem_nova(request)
    form = OrdemServicoForm(request.POST or None, instance=ordem, initial=initial)
    if request.method == "POST" and request.POST.get("acao") != "adicionar_destino":
        if form.is_valid():
            nova = ordem.pk is None
            ordem = form.save()
            messages.success(request, "Ordem de Serviço cadastrada." if nova else "Ordem de Serviço atualizada.")
            return redirect(voltar_para(request, _url_da_lista(ordem)))
        messages.error(request, "Não foi possível salvar a Ordem de Serviço. Revise os campos indicados.")
    return render(request, "pages/viagens_ordens/form.html", _contexto_form(form, ordem, request))


@acesso_ao_modulo
@require_POST
def gerar(request, pk, formato):
    exigir_operador(request)
    ordem = get_ordem_by_id(pk)
    if formato not in ["docx", "pdf"]:
        raise Http404
    if ordem.cancelado:
        messages.error(request, "Reative a Ordem de Serviço antes de gerar documentos.")
        return redirect(voltar_para(request, reverse("viagens_ordens:editar", args=[pk])))
    try:
        return resposta_documento(request, gerar_ordem_servico(ordem, DocumentoFormato(formato)))
    except (ValidationError, DocumentError) as exc:
        messages.error(request, "; ".join(exc.messages) if isinstance(exc, ValidationError) else str(exc))
        return redirect(voltar_para(request, reverse("viagens_ordens:editar", args=[pk])))


@acesso_ao_modulo
@require_POST
def acao(request, pk, acao):
    exigir_operador(request)
    ordem = get_ordem_by_id(pk)
    numero = ordem.numero_formatado
    destino = voltar_para(request, reverse("viagens_ordens:lista"))
    if acao == "cancelar":
        ordem.cancelar(request.POST.get("motivo", ""))
        messages.success(request, f"Ordem de Serviço {numero} cancelada. O histórico foi mantido.")
    elif acao == "reativar":
        ordem.reativar()
        messages.success(request, f"Ordem de Serviço {numero} reativada.")
    elif acao == "excluir":
        destino = voltar_para(request, _url_da_lista(ordem))
        try:
            excluir_ordem_servico(ordem)
        except DelecaoProtegidaError as exc:
            messages.error(request, str(exc))
            return redirect(destino)
        messages.success(request, f"Ordem de Serviço {numero} excluída.")
    else:
        raise Http404
    return redirect(destino)


@acesso_ao_modulo
def assinatura_artefato(request, pk):
    """Anexar (ou remover) o PDF assinado de uma OS — o mesmo fluxo do ofício, para artefatos de OS."""
    from documentos.services.access import obter_artefato_para_download
    from documentos.services.persistence import anexar_arquivo_assinado, remover_arquivo_assinado

    exigir_operador(request)
    artefato = obter_artefato_para_download(request.user, pk)
    if artefato.formato != "pdf" or not artefato.ordem_servico_id:
        raise Http404
    voltar = reverse("viagens_ordens:editar", args=[artefato.ordem_servico_id])

    class UploadForm(forms.Form):
        arquivo = forms.FileField(label="Documento assinado (PDF)")

    form = UploadForm(request.POST or None, request.FILES or None)
    # Pelo modal, o POST traz `next` (a página de onde se abriu): o retorno vai
    # para lá, e um erro volta como mensagem em vez de abrir esta página.
    do_modal = request.method == "POST" and bool(next_valido(request))
    retorno = voltar_para(request, voltar)
    if request.method == "POST":
        try:
            if request.POST.get("acao") == "remover":
                remover_arquivo_assinado(artefato)
                messages.success(request, "Versão assinada removida. O PDF gerado volta a valer.")
                return redirect(retorno)
            if form.is_valid():
                anexar_arquivo_assinado(artefato, form.cleaned_data["arquivo"])
                messages.success(request, "Documento assinado anexado. A versão anterior permanece no histórico.")
                return redirect(retorno)
        except DocumentError as exc:
            form.add_error("arquivo", str(exc))
        if do_modal:
            messages.error(request, " ".join(form.errors.get("arquivo", [])) or "Não foi possível anexar o documento.")
            return redirect(retorno)
    return render(request, "pages/viagens_oficios/assinatura.html", {"form": form, "artefato": artefato, "url_voltar": voltar})
