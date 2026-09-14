"""Consulta de cidades sobre os municípios compartilhados com Eventos."""
import csv

from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.http import HttpResponse
from django.shortcuts import render
from django.utils.http import urlencode
from django.views.decorators.http import require_GET

from cadastros.models import Municipio
from solicitacoes.permissions import eh_administrador
from .permissions import acesso_ao_modulo
from .views import _iniciais_catalogo, _texto_busca


def _listar_cidades(termo=""):
    cidades = Municipio.objects.select_related("estado").order_by("estado__sigla", "nome")
    if termo:
        busca = _texto_busca(termo)
        # Mesma pesquisa por nome/UF/estado nos dois bancos, sem extensão SQL.
        campos = ("pk", "nome", "estado__sigla", "estado__nome")
        ids = [linha[0] for linha in cidades.values_list(*campos)
               if any(busca in _texto_busca(valor) for valor in linha[1:])]
        cidades = cidades.filter(pk__in=ids)
    return cidades


def _exigir_acesso(usuario):
    # Preserva a permissão do catálogo de municípios já existente em Eventos.
    if not eh_administrador(usuario):
        raise PermissionDenied


@acesso_ao_modulo
@require_GET
def lista(request):
    _exigir_acesso(request.user)
    termo = request.GET.get("q", "").strip()
    pagina = Paginator(_listar_cidades(termo), 15).get_page(request.GET.get("page"))
    return render(request, "pages/viagens_cadastros/cidades/lista.html", {
        "termo": termo, "pagina": pagina,
        "cidades": [{"objeto": cidade, "iniciais": _iniciais_catalogo(cidade.nome)} for cidade in pagina],
        "querystring": urlencode({"q": termo}) if termo else "",
        "paginas_visiveis": list(pagina.paginator.get_elided_page_range(pagina.number, on_each_side=1, on_ends=1)),
        "elipse": pagina.paginator.ELLIPSIS,
    })


@acesso_ao_modulo
@require_GET
def exportar_csv(request):
    _exigir_acesso(request.user)
    response = HttpResponse(content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = 'attachment; filename="cidades.csv"'
    response.write("\ufeff")
    writer = csv.writer(response)
    writer.writerow(["Cidade", "UF"])
    # O contrato do GV exporta a base inteira, independentemente de q/page.
    for cidade in _listar_cidades():
        writer.writerow([cidade.nome, cidade.estado.sigla])
    return response
