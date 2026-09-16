"""Justificativas de prazo — lista no padrão das listas de cadastros, roteiros
e termos, com cadastro e edição num modal (como "Novo servidor").

Uma justificativa por ofício. A lista mostra cada uma numa célula só: o
ofício com o selo temporal e o estado do texto, os fatos (período e
destinos, regra de prazo, modelo) e o texto. A trilha à esquerda filtra por
situação. "Nova justificativa" e "Editar" abrem o modal; sem JavaScript, a
própria lista abre com o modal aberto.
"""

from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_http_methods, require_POST

from core.listagens import ITENS_POR_PAGINA
from core.retorno import daqui, voltar_para
from viagens_cadastros.permissions import acesso_ao_modulo, pode_editar_cadastros

from .forms import JustificativaCadastroForm
from .justificativas_services import avaliar_justificativa_oficio, salvar_justificativa
from .models import Justificativa, ModeloJustificativa, Oficio
from .presenters import selo_do_cartao, subtitulo_do_cartao, titulo_do_cartao
from .selectors import _filtro_busca
from .views import exigir_operador

SITUACOES = (
    ("", "Todas", "checklist"),
    ("pendentes", "Pendentes", "clock"),
    ("preenchidas", "Preenchidas", "check-circle"),
)


def _base():
    return (
        Justificativa.objects.select_related("oficio__roteiro__origem_municipio__estado", "modelo")
        .prefetch_related("oficio__roteiro__destinos__municipio__estado", "oficio__servidores", "oficio__roteiro__trechos")
        .filter(oficio__cancelado=False)
        .order_by("-oficio__ano", "-oficio__numero", "-pk")
    )


def _filtrar_situacao(queryset, situacao):
    if situacao == "pendentes":
        return queryset.filter(texto="")
    if situacao == "preenchidas":
        return queryset.exclude(texto="")
    return queryset


def _regra(oficio):
    """A regra de prazo em palavras curtas, para o fato da linha."""
    regra = avaliar_justificativa_oficio(oficio)
    if regra["status"] == "unknown":
        return {"texto": "Sem data de saída", "ausente": True, "regra": regra}
    exigida = "Exigida" if regra["obrigatoria"] else "Não exigida"
    return {"texto": f"{exigida} · {regra['dias_antecedencia']} dias de antecedência (mínimo {regra['prazo_dias']})",
            "ausente": False, "regra": regra}


def linha_da_justificativa(justificativa):
    oficio = justificativa.oficio
    selo, tom = selo_do_cartao(oficio)
    texto = (justificativa.texto or "").strip()
    regra = _regra(oficio)
    periodo_destinos = subtitulo_do_cartao(oficio)
    return {
        "justificativa": justificativa,
        "oficio": oficio,
        "titulo": f"Ofício {titulo_do_cartao(oficio)}",
        "selo": selo,
        "selo_tom": tom,
        "preenchida": bool(texto),
        "texto": texto,
        "exigida": regra["regra"]["obrigatoria"],
        "fatos": [
            {"icone": "calendar", "rotulo": "Período e destinos", "texto": periodo_destinos or "Sem roteiro", "ausente": not periodo_destinos},
            {"icone": "clock", "rotulo": "Regra de prazo", "texto": regra["texto"], "ausente": regra["ausente"]},
            {"icone": "document", "rotulo": "Modelo", "texto": justificativa.modelo.nome if justificativa.modelo_id else "Sem modelo",
             "ausente": not justificativa.modelo_id},
        ],
        "url_editar": reverse("viagens_oficios:justificativa_editar", args=[justificativa.pk]),
        "url_excluir": reverse("viagens_oficios:justificativa_excluir", args=[justificativa.pk]),
        "url_oficio": reverse("viagens_oficios:editar", args=[oficio.pk]),
        "url_pdf": reverse("viagens_oficios:gerar", args=[oficio.pk, "justificativa", "pdf"]),
        "url_docx": reverse("viagens_oficios:gerar", args=[oficio.pk, "justificativa", "docx"]),
    }


def _rotulo_oficio_para_escolha(oficio):
    partes = [f"Ofício {oficio.numero_formatado}", subtitulo_do_cartao(oficio)]
    return " — ".join(p for p in partes if p)


def _contexto_modal(form, justificativa):
    """O que o modal precisa: título, destino do envio, campos e o ofício fixo na edição."""
    editando = justificativa is not None
    oficio = justificativa.oficio if editando else None
    erros_gerais = [str(e) for e in form.non_field_errors()]
    modelos = ModeloJustificativa.objects.filter(ativo=True).order_by("ordem", "nome")
    dados = {
        "titulo": "Editar justificativa" if editando else "Nova justificativa",
        "url_acao": (reverse("viagens_oficios:justificativa_editar", args=[justificativa.pk]) if editando
                     else reverse("viagens_oficios:justificativa_nova")),
        "erros_gerais": erros_gerais,
        "erros_total": len(form.errors),
        "oficio": oficio,
        "oficio_titulo": f"Ofício {titulo_do_cartao(oficio)}" if oficio else "",
        "oficio_subtitulo": subtitulo_do_cartao(oficio) if oficio else "",
        "oficio_regra": _regra(oficio)["texto"] if oficio else "",
        "modelos": [{"valor": str(m.pk), "rotulo": m.nome} for m in modelos],
        "modelos_texto": {str(m.pk): m.texto for m in modelos},
        "modelo_valor": str(form["modelo"].value() or ""),
        "texto_valor": form["texto"].value() or "",
        "erros": {nome: form.errors.get(nome) for nome in ("oficio", "modelo", "texto")},
    }
    if not editando:
        dados["oficios"] = [{"valor": str(o.pk), "rotulo": _rotulo_oficio_para_escolha(o)} for o in form.fields["oficio"].queryset]
        dados["oficio_valor"] = str(form["oficio"].value() or "")
    return dados


@acesso_ao_modulo
@require_http_methods(["GET"])
def index(request):
    return _lista(request)


def _lista(request, modal=None):
    """A página da lista; `modal` vem pronto quando um envio sem JavaScript volta com erro."""
    pode_editar = pode_editar_cadastros(request.user)
    termo = request.GET.get("q", "").strip()
    situacao = request.GET.get("situacao", "")
    if situacao not in {s[0] for s in SITUACOES}:
        situacao = ""

    base = _base()
    if termo:
        oficios = Oficio.objects.filter(_filtro_busca(termo)).values("pk")
        base = base.filter(Q(texto__icontains=termo) | Q(modelo__nome__icontains=termo) | Q(oficio__in=oficios)).distinct()
    queryset = _filtrar_situacao(base, situacao)

    paginator = Paginator(queryset, ITENS_POR_PAGINA)
    pagina = paginator.get_page(request.GET.get("pagina"))
    parametros = request.GET.copy()
    for chave in ("pagina", "nova", "editar"):
        parametros.pop(chave, None)

    def url_da_situacao(valor):
        destino = parametros.copy()
        destino.pop("situacao", None)
        if valor:
            destino["situacao"] = valor
        return "?" + destino.urlencode()

    situacoes = [
        {"slug": valor or "todas", "titulo": rotulo, "icone": icone, "url": url_da_situacao(valor),
         "total": _filtrar_situacao(base, valor).count()}
        for valor, rotulo, icone in SITUACOES
    ]

    # Sem JavaScript, "Nova" e "Editar" voltam para cá com o modal já aberto.
    if modal is None and pode_editar:
        if request.GET.get("nova"):
            modal = _contexto_modal(JustificativaCadastroForm(), None)
        elif request.GET.get("editar", "").isdigit():
            justificativa = Justificativa.objects.filter(pk=request.GET["editar"], oficio__cancelado=False).first()
            if justificativa:
                modal = _contexto_modal(JustificativaCadastroForm(justificativa=justificativa), justificativa)

    return render(request, "pages/viagens_oficios/justificativas.html", {
        "linhas": [linha_da_justificativa(j) for j in pagina],
        "pagina": pagina,
        "paginas_visiveis": list(paginator.get_elided_page_range(pagina.number, on_each_side=1, on_ends=1)),
        "elipse": paginator.ELLIPSIS,
        "querystring": parametros.urlencode(),
        "q": termo,
        "situacao": situacao,
        "situacao_ativa": situacao or "todas",
        "situacoes": situacoes,
        "tem_filtros": bool(termo or situacao),
        "url_atual": daqui(request),
        "pode_editar": pode_editar,
        "modal": modal,
    })


@acesso_ao_modulo
@require_http_methods(["GET", "POST"])
def editar(request, pk=None):
    """Nova (sem `pk`) ou edição de uma justificativa, no modal da lista."""
    exigir_operador(request)
    justificativa = get_object_or_404(Justificativa.objects.select_related("oficio"), pk=pk, oficio__cancelado=False) if pk else None
    via_modal = request.headers.get("X-Cadastro-Modal") == "1"
    if request.method == "GET" and not via_modal:
        chave, valor = ("editar", str(pk)) if pk else ("nova", "1")
        return redirect(f"{reverse('viagens_oficios:justificativas')}?{chave}={valor}")

    form = JustificativaCadastroForm(request.POST or None, justificativa=justificativa)
    if request.method == "POST" and form.is_valid():
        oficio = justificativa.oficio if justificativa else form.cleaned_data["oficio"]
        salvar_justificativa(oficio, form.cleaned_data.get("modelo"), form.cleaned_data["texto"])
        messages.success(request, f"Justificativa do ofício {oficio.numero_formatado} {'atualizada' if justificativa else 'salva'}.")
        if via_modal:
            return JsonResponse({"ok": True})
        return redirect(voltar_para(request, reverse("viagens_oficios:justificativas")))

    modal = _contexto_modal(form, justificativa)
    if via_modal:
        return render(request, "pages/viagens_oficios/_justificativa_modal.html", {"dados": modal})
    return _lista(request, modal=modal)


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
