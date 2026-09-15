"""Justificativas de prazo — a tela do app `justificativas` da origem.

Uma justificativa por ofício, criada ao lado do ofício ou aqui, em lote, pela
inclusão rápida: escolhe-se um ou mais ofícios (busca no servidor, até 30 por
vez), um modelo que preenche o texto, e o texto vai para todos de uma vez.
A lista mostra cada justificativa com a regra de prazo que a exige (ou não),
o estado do texto e as ações de editar, documentos e excluir.
"""

from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from core.listagens import ITENS_POR_PAGINA
from core.retorno import com_next, daqui, voltar_para
from core.utils.masks import format_protocolo
from documentos.services.types import DocumentoTipo
from viagens_cadastros.permissions import acesso_ao_modulo, pode_editar_cadastros

from .forms import JustificativaQuickAddForm
from .justificativas_services import avaliar_justificativa_oficio, criar_justificativas_quick_add
from .models import Justificativa, ModeloJustificativa, Oficio
from .picker import LIMITE_BUSCA, dados_do_option
from .presenters import selo_do_cartao, subtitulo_do_cartao, titulo_do_cartao
from .selectors import _filtro_busca, base_oficios
from .views import exigir_operador


def rotulo_do_oficio(oficio):
    return f"Ofício {oficio.numero_formatado}"


def resumo_para_busca(oficio):
    """O que a busca do seletor enxerga: número, protocolo, viajantes e destinos."""
    partes = [oficio.numero_formatado, format_protocolo(oficio.protocolo), oficio.assunto, oficio.motivo]
    partes += [s.nome for s in oficio.servidores.all()]
    if oficio.roteiro_id:
        partes += [str(d.municipio) for d in oficio.roteiro.destinos.all() if d.municipio_id]
    return {"search_text": " ".join(p for p in partes if p)}


def opcao_do_oficio(oficio):
    dados = dados_do_option(oficio, resumo=resumo_para_busca(oficio), rotulo=rotulo_do_oficio, decorar=True)
    dados["id"] = oficio.pk
    dados["meta"] = " · ".join(p for p in [subtitulo_do_cartao(oficio), dados["meta"]] if p)
    return dados


def _oficios_para_escolha():
    return base_oficios().filter(cancelado=False).order_by("-ano", "-numero", "-pk")


@acesso_ao_modulo
@require_GET
def buscar_oficios(request):
    """`api_buscar_oficios` da origem: até 30 ofícios que casam com o termo."""
    termo = request.GET.get("q", "").strip()
    queryset = _oficios_para_escolha()
    if termo:
        queryset = queryset.filter(_filtro_busca(termo)).distinct()
    resultados = [opcao_do_oficio(o) for o in queryset[:LIMITE_BUSCA]]
    return JsonResponse({"results": resultados, "limite": LIMITE_BUSCA, "truncado": queryset.count() > LIMITE_BUSCA})


def linha_da_justificativa(justificativa, *, volta):
    oficio = justificativa.oficio
    regra = avaliar_justificativa_oficio(oficio)
    selo, tom = selo_do_cartao(oficio)
    texto = (justificativa.texto or "").strip()
    return {
        "justificativa": justificativa,
        "oficio": oficio,
        "titulo": titulo_do_cartao(oficio),
        "subtitulo": subtitulo_do_cartao(oficio),
        "selo": selo,
        "selo_tom": tom,
        "preenchida": bool(texto),
        "texto": texto or "Nenhuma justificativa informada.",
        "regra": regra,
        "modelo": justificativa.modelo.nome if justificativa.modelo_id else "",
        "editar_url": com_next(reverse("viagens_oficios:editar", args=[oficio.pk]), volta) + "#justificativa",
        "excluir_url": reverse("viagens_oficios:justificativa_excluir", args=[justificativa.pk]),
        "gerar_pdf_url": reverse("viagens_oficios:gerar", args=[oficio.pk, "justificativa", "pdf"]),
        "gerar_docx_url": reverse("viagens_oficios:gerar", args=[oficio.pk, "justificativa", "docx"]),
    }


@acesso_ao_modulo
@require_http_methods(["GET", "POST"])
def index(request):
    pode_editar = pode_editar_cadastros(request.user)
    form = JustificativaQuickAddForm(request.POST or None, prefix="rapida")
    if request.method == "POST":
        exigir_operador(request)
        if form.is_valid():
            criadas = criar_justificativas_quick_add(form)
            messages.success(request, f"Justificativa aplicada a {len(criadas)} ofício{'s' if len(criadas) != 1 else ''}.")
            return redirect(voltar_para(request, reverse("viagens_oficios:justificativas")))
        messages.error(request, "Não foi possível aplicar a justificativa. Revise os campos indicados.")

    termo = request.GET.get("q", "").strip()
    situacao = request.GET.get("situacao", "")
    queryset = (
        Justificativa.objects.select_related("oficio__roteiro__origem_municipio__estado", "modelo")
        .prefetch_related("oficio__roteiro__destinos__municipio__estado", "oficio__servidores")
        .filter(oficio__cancelado=False)
        .order_by("-oficio__ano", "-oficio__numero", "-pk")
    )
    if termo:
        oficios = Oficio.objects.filter(_filtro_busca(termo)).values("pk")
        queryset = queryset.filter(Q(texto__icontains=termo) | Q(modelo__nome__icontains=termo) | Q(oficio__in=oficios)).distinct()
    if situacao == "pendentes":
        queryset = queryset.filter(texto="")
    elif situacao == "preenchidas":
        queryset = queryset.exclude(texto="")

    paginator = Paginator(queryset, ITENS_POR_PAGINA)
    pagina = paginator.get_page(request.GET.get("page"))
    parametros = request.GET.copy()
    parametros.pop("page", None)
    volta = daqui(request)
    linhas = [linha_da_justificativa(j, volta=volta) for j in pagina]
    escolhidos = [opcao_do_oficio(o) for o in form.oficios_escolhidos()]
    return render(request, "pages/viagens_oficios/justificativas.html", {
        "form": form, "linhas": linhas, "pagina": pagina,
        "paginas_visiveis": list(paginator.get_elided_page_range(pagina.number, on_each_side=1, on_ends=1)),
        "elipse": paginator.ELLIPSIS, "querystring": parametros.urlencode(),
        "q": termo, "situacao": situacao, "tem_filtros": bool(termo or situacao),
        "opcoes_situacao": [{"valor": "", "rotulo": "Todas"}, {"valor": "pendentes", "rotulo": "Pendentes"}, {"valor": "preenchidas", "rotulo": "Preenchidas"}],
        "opcoes_modelo": [{"valor": str(m.pk), "rotulo": m.nome} for m in form.fields["modelo"].queryset],
        "modelos_texto": {"rapida-modelo": dict(ModeloJustificativa.objects.filter(ativo=True).values_list("pk", "texto"))},
        "escolhidos": escolhidos, "limite_busca": LIMITE_BUSCA,
        "url_busca": reverse("viagens_oficios:justificativas_buscar_oficios"),
        "url_atual": volta, "pode_editar": pode_editar,
        "abrir_inclusao": request.method == "POST",
    })


@acesso_ao_modulo
@require_POST
def excluir(request, pk):
    """`justificativa_delete` da origem: apaga o texto e o modelo; a regra de prazo fica."""
    exigir_operador(request)
    justificativa = get_object_or_404(Justificativa.objects.select_related("oficio"), pk=pk)
    numero = justificativa.oficio.numero_formatado
    justificativa.texto = ""
    justificativa.modelo = None
    justificativa.status = Justificativa.STATUS_RASCUNHO
    justificativa.save(update_fields=["texto", "modelo", "status", "atualizado_em"])
    messages.success(request, f"Justificativa do ofício {numero} excluída.")
    return redirect(voltar_para(request, reverse("viagens_oficios:justificativas")))
