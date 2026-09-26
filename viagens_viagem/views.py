"""Viagens — a lista e o painel de cinco etapas.

O app `eventos` da origem: "Nova viagem" cria o registro e abre a etapa 1
(o cadastro); as etapas 2 a 5 listam os documentos daquele tipo — roteiros,
ofícios, PT/OS com os documentos de solicitação, termos — com o botão de
criar cada um já preso à viagem. Cancelar cancela os documentos vinculados;
reativar os traz de volta.
"""

from django.contrib import messages
from django.core.paginator import Paginator
from django.http import Http404
from django.shortcuts import redirect, render
from django.urls import NoReverseMatch, reverse
from django.views.decorators.http import require_POST, require_http_methods

from core.conflitos import conflitos_da_viagem
from core.deletion import DelecaoProtegidaError
from core.listagens import ITENS_POR_PAGINA
from core.private_media import private_file_response
from core.retorno import com_next, daqui, voltar_para
from solicitacoes.integracao_viagens import aviso_para_o_painel
from viagens_cadastros.permissions import acesso_ao_modulo, pode_editar_cadastros
from viagens_oficios.views import exigir_operador

from . import abas as abas_de_viagem
from .forms import ViagemForm
from .models import Viagem
from .presenters import abas_de_documentos, linha_da_lista, selo_situacao, titulo_da_viagem
from .selectors import (
    buscar_documento_solicitacao, get_documento_solicitacao_by_id, get_viagem_by_id, listar_oficios_da_viagem,
    listar_roteiros_da_viagem, listar_termos_da_viagem, listar_viagens,
)
from .services import (
    anexar_documentos_solicitacao, contexto_das_etapas, converter_para_pdf_se_necessario, excluir_documento_solicitacao,
    excluir_viagem, normalizar_etapa, salvar_identificacao_viagem,
)


@acesso_ao_modulo
def lista(request):
    q = request.GET.get("q", "").strip()
    escolhidas = abas_de_viagem.normalizar_abas(request.GET.getlist("situacao"))
    base = listar_viagens(q)
    queryset = listar_viagens(q, situacoes=escolhidas)
    paginator = Paginator(queryset, ITENS_POR_PAGINA)
    pagina = paginator.get_page(request.GET.get("pagina"))
    parametros = request.GET.copy()
    parametros.pop("pagina", None)
    linhas = [linha_da_lista(v) for v in pagina]

    # Situações como chips da trilha, iguais às outras listas do módulo.
    def url_da_situacao(aba=None):
        destino = parametros.copy()
        destino.pop("situacao", None)
        if aba:
            destino["situacao"] = aba
        return "?" + destino.urlencode()

    icones = {
        abas_de_viagem.ABA_FUTURAS: "calendar",
        abas_de_viagem.ABA_ATUAIS: "clock",
        abas_de_viagem.ABA_FINALIZADOS: "check-circle",
        abas_de_viagem.ABA_CANCELADOS: "ban",
    }
    contagem = abas_de_viagem.contar_por_aba(base)
    situacoes = [{"slug": "todas", "titulo": "Todas", "total": base.count(), "icone": "checklist", "url": url_da_situacao()}] + [
        {"slug": chave, "titulo": rotulo, "total": contagem[chave], "icone": icones[chave], "url": url_da_situacao(chave)}
        for chave, rotulo in abas_de_viagem.ABA_ROTULOS
    ]
    return render(request, "pages/viagens_viagem/lista.html", {
        "linhas": linhas, "pagina": pagina, "querystring": parametros.urlencode(), "q": q,
        "paginas_visiveis": list(paginator.get_elided_page_range(pagina.number, on_each_side=1, on_ends=1)),
        "elipse": paginator.ELLIPSIS,
        "situacoes": situacoes, "situacoes_escolhidas": escolhidas,
        "situacao_ativa": "todas" if not escolhidas else escolhidas[0] if len(escolhidas) == 1 else "",
        "tem_filtros": bool(q or escolhidas), "url_atual": daqui(request),
        "pode_editar": pode_editar_cadastros(request.user),
    })


@acesso_ao_modulo
@require_http_methods(["GET", "POST"])
def criar(request):
    """"Nova viagem" da origem: o POST cria e abre a etapa 1; o GET só devolve a lista."""
    if request.method == "GET":
        return redirect("viagens_viagem:lista")
    exigir_operador(request)
    from .services import criar_viagem_rascunho

    viagem = criar_viagem_rascunho()
    return redirect("viagens_viagem:etapa", pk=viagem.pk, etapa=1)


@acesso_ao_modulo
def painel(request, pk):
    return redirect("viagens_viagem:etapa", pk=pk, etapa=1)


def _url_criar(nome, viagem, *, metodo="get"):
    """URL de "Novo ..." já presa à viagem; sem a rota (módulo em construção) fica vazia."""
    try:
        url = reverse(nome)
    except NoReverseMatch:
        return ""
    return url if metodo == "post" else f"{url}?viagem={viagem.pk}"


def _contexto_da_etapa_1(request, viagem, form):
    from cadastros.busca_municipios import opcoes_dos_municipios
    from cadastros.models import Estado
    from viagens_oficios.models import ModeloMotivoOficio

    valor = lambda nome: (str(getattr(form[nome].value(), "pk", form[nome].value())) if form[nome].value() not in (None, "") else "")
    escolhidos = {str(getattr(v, "pk", v)) for v in (form["tipos"].value() or [])}
    adicionais = [{
        "i": i, "nome_estado": f"extra_estado_{i}", "nome_cidade": f"extra_cidade_{i}", "id_estado": f"id_extra_estado_{i}",
        "estado": valor(f"extra_estado_{i}"), "cidade": valor(f"extra_cidade_{i}"),
        "erros_estado": form.errors.get(f"extra_estado_{i}"), "erros_cidade": form.errors.get(f"extra_cidade_{i}"),
    } for i in range(form.quantidade_destinos)]
    volta = daqui(request)
    return {
        "form": form,
        "valores": {n: valor(n) for n in ["modelo_motivo", "data_inicio", "data_fim", "destino_estado", "destino_municipio"]},
        "motivo": form["motivo"].value() or "",
        "erros": {n: form.errors.get(n) for n in form.fields},
        "tipos": [{"valor": str(t.pk), "rotulo": t.nome, "selecionado": str(t.pk) in escolhidos} for t in form.fields["tipos"].queryset],
        "opcoes_motivos": [{"valor": str(m.pk), "rotulo": m.nome} for m in form.fields["modelo_motivo"].queryset],
        "modelos_texto": dict(ModeloMotivoOficio.objects.values_list("pk", "texto")),
        "estados": [{"valor": str(e.pk), "rotulo": f"{e.sigla} — {e.nome}"} for e in Estado.objects.order_by("sigla")],
        # Só os municípios já escolhidos; o seletor busca o resto ao digitar (m075).
        "municipios": opcoes_dos_municipios([valor("destino_municipio")] + [a["cidade"] for a in adicionais]),
        "remoto_municipios": reverse("cadastros:municipios_buscar"),
        "adicionais": adicionais, "quantidade_destinos": str(form.quantidade_destinos),
        "abas_documentos": abas_de_documentos(form),
        "url_tipos": com_next(reverse("viagens_cadastros:lista", args=["tipos-viagem"]), volta),
        "url_modelos_motivo": com_next(reverse("viagens_cadastros:lista", args=["motivos-oficio"]), volta),
    }


def _contexto_da_etapa_2(request, viagem):
    from viagens_roteiros.presenters import linha_da_lista as linha_de_roteiro

    volta = reverse("viagens_viagem:etapa", args=[viagem.pk, 2])
    return {
        "roteiros": [
            linha_de_roteiro(r, editar_url=com_next(reverse("viagens_roteiros:editar", args=[r.pk]), volta),
                             excluir_url=reverse("viagens_roteiros:excluir", args=[r.pk]))
            for r in listar_roteiros_da_viagem(viagem)
        ],
        "url_novo_roteiro": _url_criar("viagens_roteiros:novo", viagem),
    }


def _contexto_da_etapa_3(request, viagem):
    from viagens_oficios.presenters import artefatos_pdf_por_oficio, linha_da_lista as linha_de_oficio

    oficios = list(listar_oficios_da_viagem(viagem))
    artefatos = artefatos_pdf_por_oficio(oficios)
    return {
        "oficios": [linha_de_oficio(o, artefatos_pdf=artefatos.get(o.pk, {})) for o in oficios],
        "url_novo_oficio": _url_criar("viagens_oficios:criar", viagem, metodo="post"),
    }


def _contexto_da_etapa_4(request, viagem):
    from viagens_ordens.presenters import artefatos_pdf_por_ordem, assinante_da_ordem, linha_da_lista as linha_de_ordem
    from viagens_planos.presenters import linha_da_lista as linha_de_plano

    # As linhas das listas de PT e de OS, as mesmas das telas de cada módulo.
    planos = list(viagem.planos_trabalho.all().order_by("-criado_em"))
    ordens = list(viagem.ordens_servico.all().order_by("-criado_em"))
    assinante = assinante_da_ordem()
    artefatos = artefatos_pdf_por_ordem(ordens)
    return {
        "solicitacoes": [{
            "pk": a.pk, "nome": a.nome_original or a.arquivo.name.split("/")[-1],
            "url": reverse("viagens_viagem:solicitacao_conteudo", args=[viagem.pk, a.pk]),
            "url_excluir": reverse("viagens_viagem:solicitacao_excluir", args=[viagem.pk, a.pk]),
        } for a in viagem.documentos_solicitacao.all()],
        "url_anexar": reverse("viagens_viagem:solicitacao_anexar", args=[viagem.pk]),
        "planos": [linha_de_plano(p) for p in planos],
        "ordens": [linha_de_ordem(o, assinante=assinante, artefato_pdf=artefatos.get(o.pk)) for o in ordens],
        "url_nova_ordem": _url_criar("viagens_ordens:novo", viagem),
        "url_novo_plano": _url_criar("viagens_planos:criar", viagem, metodo="post"),
    }


def _contexto_da_etapa_5(request, viagem):
    from viagens_termos.presenters import artefatos_pdf_por_termo, linha_da_lista as linha_de_termo

    termos = list(listar_termos_da_viagem(viagem))
    artefatos = artefatos_pdf_por_termo(termos)
    return {
        "termos": [linha_de_termo(t, artefatos_pdf=artefatos.get(t.pk, {})) for t in termos],
        "url_novo_termo": _url_criar("viagens_termos:novo", viagem),
    }


@acesso_ao_modulo
@require_http_methods(["GET", "POST"])
def etapa(request, pk, etapa):
    etapa = normalizar_etapa(etapa)
    viagem = get_viagem_by_id(pk)
    form = None
    if etapa == 1:
        if request.method == "POST":
            exigir_operador(request)
            form = ViagemForm(request.POST, instance=viagem)
            if request.POST.get("acao") != "adicionar_destino":
                if form.is_valid():
                    viagem = salvar_identificacao_viagem(form)
                    messages.success(request, "Dados da viagem atualizados.")
                    return redirect("viagens_viagem:etapa", pk=viagem.pk, etapa=2)
                messages.error(request, "Não foi possível salvar a viagem. Revise os campos indicados.")
        else:
            form = ViagemForm(instance=viagem)
    elif request.method == "POST":
        raise Http404
    selo, tom = selo_situacao(viagem)
    contexto = {
        "viagem": viagem, "titulo": titulo_da_viagem(viagem), "selo": selo, "selo_tom": tom,
        "pode_editar": pode_editar_cadastros(request.user), "url_atual": daqui(request),
        "url_lista": reverse("viagens_viagem:lista"),
        "url_reativar": reverse("viagens_viagem:acao", args=[viagem.pk, "reativar"]),
        # De qual solicitação a viagem veio e se ela mudou depois.
        "origem_solicitacao": aviso_para_o_painel(viagem),
        # A equipe, o motorista ou a viatura dos ofícios já estão em outro
        # compromisso no mesmo horário (core/conflitos.py): só aviso.
        "conflitos": [] if viagem.cancelado else conflitos_da_viagem(viagem),
        **contexto_das_etapas(viagem, etapa),
    }
    if contexto["pode_editar"] and not viagem.cancelado:
        import json

        from .downloads import itens_para_baixar

        # "Baixar documentos" do cabeçalho: o mesmo modal das listas, com tudo o que a viagem reúne.
        contexto["url_baixar"] = reverse("viagens_viagem:baixar", args=[viagem.pk])
        contexto["url_baixar_tudo"] = reverse("viagens_viagem:baixar_tudo", args=[viagem.pk])
    if contexto["pode_editar"] and not viagem.cancelado:
        contexto["url_gerar_documentos"] = reverse("viagens_viagem:gerar_documentos", args=[viagem.pk])
        contexto["itens_baixar"] = json.dumps(itens_para_baixar(viagem), ensure_ascii=False)
    if etapa == 1:
        contexto.update(_contexto_da_etapa_1(request, viagem, form))
    else:
        contexto.update({2: _contexto_da_etapa_2, 3: _contexto_da_etapa_3, 4: _contexto_da_etapa_4, 5: _contexto_da_etapa_5}[etapa](request, viagem))
    return render(request, "pages/viagens_viagem/painel.html", contexto)


@acesso_ao_modulo
@require_POST
def baixar(request, pk):
    """Os documentos marcados no modal "Baixar documentos" da viagem.

    `itens`: os valores de `downloads.itens_para_baixar`. `formato`: pdf ou
    docx. `saida`: `separados` (um arquivo, ou ZIP) ou `unico` (um PDF só, na
    ordem do modal). `versao`: `assinado` (padrão) ou `original`. Os anexos
    de solicitação já são PDF e vão como estão.
    """
    import io
    from zipfile import ZipFile

    from django.core.exceptions import ValidationError
    from django.http import HttpResponse

    from documentos.services.exceptions import DocumentError
    from documentos.services.types import DocumentoFormato
    from viagens_oficios.views import resposta_documento
    from viagens_termos.views import resposta_pdf_consolidado

    from .downloads import gerar_marcados

    exigir_operador(request)
    viagem = get_viagem_by_id(pk)
    retorno = voltar_para(request, reverse("viagens_viagem:etapa", args=[pk, 1]))
    if viagem.cancelado:
        messages.error(request, "Reative a viagem antes de baixar documentos.")
        return redirect(retorno)
    formato = request.POST.get("formato", "pdf")
    if formato not in ("pdf", "docx"):
        raise Http404
    fmt = DocumentoFormato(formato)
    marcados = request.POST.getlist("itens")
    if not marcados:
        messages.error(request, "Marque ao menos um documento para baixar.")
        return redirect(retorno)
    try:
        documentos = gerar_marcados(viagem, marcados, fmt, usar_assinado=request.POST.get("versao", "assinado") != "original")
    except KeyError:
        raise Http404
    except (ValidationError, DocumentError) as exc:
        messages.error(request, "; ".join(exc.messages) if isinstance(exc, ValidationError) else str(exc))
        return redirect(retorno)

    referencia = f"viagem-{viagem.pk}"
    if len(documentos) == 1:
        doc = documentos[0]
        if getattr(doc, "anexo", False):
            resposta = HttpResponse(doc.conteudo, content_type="application/pdf")
            resposta["Content-Disposition"] = f'attachment; filename="{doc.nome_arquivo}"'
            resposta["Cache-Control"] = "no-store"
            return resposta
        return resposta_documento(request, doc)
    if fmt == DocumentoFormato.PDF and request.POST.get("saida") == "unico":
        return resposta_pdf_consolidado(documentos, f"{referencia}-documentos.pdf")
    # Nomes repetidos no ZIP (dois termos do mesmo servidor, dois anexos iguais) ganham um sufixo.
    buffer, usados = io.BytesIO(), set()
    with ZipFile(buffer, "w") as zipfile:
        for doc in documentos:
            nome, n = doc.nome_arquivo, 2
            base, ponto, ext = nome.rpartition(".")
            while nome in usados:
                nome = f"{base} ({n}).{ext}" if ponto else f"{doc.nome_arquivo} ({n})"
                n += 1
            usados.add(nome)
            zipfile.writestr(nome, doc.conteudo)
    resposta = HttpResponse(buffer.getvalue(), content_type="application/zip")
    resposta["Content-Disposition"] = f'attachment; filename="{referencia}-documentos.zip"'
    resposta["Cache-Control"] = "no-store"
    return resposta


def _ler_equipes(post, quantidade):
    """As equipes do formulário "Gerar documentos": uma por ofício, na ordem da tela."""
    from viagens_cadastros.models import Servidor, Viatura

    from .pacote import EquipeDoOficio

    equipes = []
    for i in range(quantidade):
        pks = [v for v in post.getlist(f"oficio-{i}-servidores") if v.isdigit()]
        por_pk = {s.pk: s for s in Servidor.objects.filter(pk__in=pks)}
        servidores = [por_pk[int(v)] for v in dict.fromkeys(pks) if int(v) in por_pk]
        motorista_pk = post.get(f"oficio-{i}-motorista", "")
        viatura_pk = post.get(f"oficio-{i}-viatura", "")
        motorista = Servidor.objects.filter(pk=motorista_pk).first() if motorista_pk.isdigit() else None
        viatura = Viatura.objects.filter(pk=viatura_pk).first() if viatura_pk.isdigit() else None
        equipes.append(EquipeDoOficio(servidores=servidores, motorista=motorista, viatura=viatura))
    return equipes


def _contexto_gerar_documentos(viagem, equipes, opcoes, erros):
    from viagens_cadastros.models import Servidor, Viatura
    from viagens_oficios.presenters import iniciais

    from .meta_equipe import contador_de_servidores
    from .pacote import servidores_ja_em_oficios

    servidores = list(Servidor.objects.select_related("cargo", "unidade").order_by("nome"))
    viaturas = list(Viatura.objects.order_by("placa"))
    ja_em_oficios = servidores_ja_em_oficios(viagem)

    def detalhes(s):
        partes = [str(s.cargo) if s.cargo_id else "", (s.unidade.sigla or s.unidade.nome) if s.unidade_id else ""]
        if s.pk in ja_em_oficios:
            partes.append(f"já no ofício {ja_em_oficios[s.pk].numero_formatado}")
        return " · ".join(p for p in partes if p)

    blocos = []
    for i, equipe in enumerate(equipes):
        escolhidos = {s.pk for s in equipe.servidores}
        blocos.append({
            "i": i, "numero": i + 1,
            "nome_servidores": f"oficio-{i}-servidores", "nome_motorista": f"oficio-{i}-motorista", "nome_viatura": f"oficio-{i}-viatura",
            "servidores": [{"valor": str(s.pk), "rotulo": s.nome, "detalhes": detalhes(s), "selecionado": s.pk in escolhidos,
                            "dados": {"iniciais": iniciais(s.nome)}} for s in servidores],
            "motoristas": [{"valor": str(s.pk), "rotulo": s.nome} for s in servidores],
            "viaturas": [{"valor": str(v.pk), "rotulo": " — ".join(p for p in [v.placa_formatada, v.modelo] if p)} for v in viaturas],
            "motorista": str(equipe.motorista.pk) if equipe.motorista else "",
            "viatura": str(equipe.viatura.pk) if equipe.viatura else "",
        })
    contador = contador_de_servidores(viagem)
    return {
        "viagem": viagem, "titulo": titulo_da_viagem(viagem), "blocos": blocos, "quantidade": len(blocos),
        "opcoes": opcoes, "erros": erros, "contador": contador,
        # Para o contador ao vivo: quantos já estão em ofícios e a meta da DG.
        "meta_previstos": contador["previstos"] if contador else 0,
        "ja_em_oficios": sorted(ja_em_oficios),
        "oficios_existentes": list(viagem.oficios.filter(cancelado=False).prefetch_related("servidores").order_by("pk")),
        "tem_roteiro": viagem.roteiros.filter(cancelado=False).exists(),
        "ordem_existente": viagem.ordens_servico.filter(cancelado=False).first(),
        "plano_existente": viagem.planos_trabalho.filter(cancelado=False).first(),
        "url_painel": reverse("viagens_viagem:etapa", args=[viagem.pk, 3]),
        "url_roteiro": reverse("viagens_viagem:etapa", args=[viagem.pk, 2]),
    }


@acesso_ao_modulo
@require_http_methods(["GET", "POST"])
def gerar_documentos(request, pk):
    """"Gerar documentos" (m064): monta os ofícios, cada um com a sua equipe, e cria tudo em rascunho."""
    from viagens_cadastros.models import ConfiguracaoSistema

    from .pacote import EquipeDoOficio, PacoteInvalido, gerar_pacote
    from .services import semente_de_documentos

    exigir_operador(request)
    viagem = get_viagem_by_id(pk)
    if viagem.cancelado:
        messages.error(request, "Reative a viagem antes de gerar documentos.")
        return redirect("viagens_viagem:etapa", pk=pk, etapa=1)
    erros = []
    if request.method == "GET":
        # Um ofício para começar; o motorista designado na solicitação já vem nele.
        semente = semente_de_documentos(viagem)
        motorista = semente["motorista"] if not viagem.oficios.filter(cancelado=False).exists() else None
        equipes = [EquipeDoOficio(servidores=[motorista] if motorista else [], motorista=motorista)]
        opcoes = {"termos": True, "ordem": True, "plano": True}
    else:
        try:
            quantidade = max(1, min(int(request.POST.get("quantidade_oficios", 1)), 20))
        except (TypeError, ValueError):
            quantidade = 1
        equipes = _ler_equipes(request.POST, quantidade)
        opcoes = {chave: bool(request.POST.get(f"gerar_{chave}")) for chave in ("termos", "ordem", "plano")}
        acao = request.POST.get("acao", "")
        if acao == "adicionar":
            equipes.append(EquipeDoOficio(servidores=[]))
        elif acao.startswith("remover-") and acao[8:].isdigit() and len(equipes) > 1:
            equipes.pop(min(int(acao[8:]), len(equipes) - 1))
        elif acao == "gerar":
            try:
                resultado = gerar_pacote(
                    viagem, equipes, gerar_ordem=opcoes["ordem"], gerar_plano=opcoes["plano"], gerar_termos=opcoes["termos"],
                    unidade_emissora=ConfiguracaoSistema.para_usuario(request.user).unidade_id,
                )
            except PacoteInvalido as exc:
                erros = exc.erros
            else:
                partes = [f"{len(resultado.oficios)} ofício{'s' if len(resultado.oficios) != 1 else ''} ("
                          + ", ".join(o.numero_formatado for o in resultado.oficios) + ")"]
                if resultado.ordem is not None:
                    partes.append(resultado.ordem.numero_formatado)
                if resultado.plano is not None:
                    partes.append(f"Plano de Trabalho {resultado.plano.numero_formatado}")
                messages.success(request, "Documentos gerados em rascunho: " + ", ".join(partes)
                                 + ". Revise e finalize cada um no seu módulo.")
                for aviso in resultado.avisos:
                    messages.warning(request, aviso)
                return redirect("viagens_viagem:etapa", pk=pk, etapa=3)
    return render(request, "pages/viagens_viagem/gerar_documentos.html",
                  _contexto_gerar_documentos(viagem, equipes, opcoes, erros))


@acesso_ao_modulo
@require_POST
def baixar_tudo(request, pk):
    """"Baixar tudo" (m065): um ZIP com cada documento da viagem em arquivo separado."""
    from django.http import HttpResponse

    from .downloads import pacote_do_processo

    exigir_operador(request)
    viagem = get_viagem_by_id(pk)
    retorno = voltar_para(request, reverse("viagens_viagem:etapa", args=[pk, 1]))
    if viagem.cancelado:
        messages.error(request, "Reative a viagem antes de baixar documentos.")
        return redirect(retorno)
    conteudo, quantos = pacote_do_processo(viagem, usar_assinado=request.POST.get("versao", "assinado") != "original")
    if not quantos:
        messages.error(request, "Nenhum documento pronto para baixar ainda.")
        return redirect(retorno)
    resposta = HttpResponse(conteudo, content_type="application/zip")
    resposta["Content-Disposition"] = f'attachment; filename="viagem-{viagem.pk}-processo.zip"'
    resposta["Cache-Control"] = "no-store"
    return resposta


@acesso_ao_modulo
@require_POST
def repetir(request, pk):
    """Repete a viagem em outra data (e cidade), com os documentos em rascunho."""
    from datetime import date

    from cadastros.models import Municipio

    from .duplicar import ViagemSemData, repetir_viagem

    exigir_operador(request)
    viagem = get_viagem_by_id(pk)
    volta = voltar_para(request, reverse("viagens_viagem:lista"))
    try:
        nova_data = date.fromisoformat((request.POST.get("nova_data") or "").strip())
    except ValueError:
        messages.error(request, "Informe a data da nova edição.")
        return redirect(volta)
    # Na lista, cada linha nomeia o campo com o id da viagem (ids únicos na página).
    cidade_id = (request.POST.get(f"nova_cidade_{pk}") or request.POST.get("nova_cidade") or "").strip()
    nova_cidade = Municipio.objects.filter(pk=cidade_id).first() if cidade_id.isdigit() else None
    try:
        nova = repetir_viagem(viagem, nova_data, nova_cidade)
    except ViagemSemData as erro:
        messages.error(request, str(erro))
        return redirect(volta)
    messages.success(
        request,
        "Viagem repetida em rascunho, com roteiro, ofícios, plano, ordem de serviço e termos. "
        "Números e protocolos são novos; confira os documentos antes de emitir.",
    )
    return redirect("viagens_viagem:etapa", nova.pk, 1)


@acesso_ao_modulo
@require_POST
def acao(request, pk, acao):
    exigir_operador(request)
    viagem = get_viagem_by_id(pk)
    destino = voltar_para(request, reverse("viagens_viagem:etapa", args=[pk, 1]))
    if acao == "cancelar":
        if viagem.cancelado:
            messages.error(request, "Esta viagem já está cancelada.")
            return redirect(destino)
        motivo = (request.POST.get("motivo") or "").strip()
        if not motivo:
            messages.error(request, "Informe o motivo do cancelamento.")
            return redirect(destino)
        viagem.cancelar(motivo)
        messages.success(request, "Viagem cancelada. Todos os documentos vinculados também foram cancelados.")
    elif acao == "reativar":
        if not viagem.cancelado:
            messages.error(request, "Esta viagem não está cancelada.")
            return redirect(destino)
        viagem.reativar()
        messages.success(request, "Viagem reativada. Os documentos cancelados junto com ela também foram reativados.")
    elif acao == "excluir":
        titulo = viagem.titulo or f"Viagem #{pk}"
        try:
            excluir_viagem(viagem)
        except DelecaoProtegidaError as exc:
            messages.error(request, str(exc))
            return redirect(voltar_para(request, reverse("viagens_viagem:lista")))
        messages.success(request, f'Viagem "{titulo}" excluída.')
        return redirect(voltar_para(request, reverse("viagens_viagem:lista")))
    else:
        raise Http404
    return redirect(destino)


@acesso_ao_modulo
@require_POST
def solicitacao_anexar(request, pk):
    from django.core.exceptions import ValidationError
    from PIL import UnidentifiedImageError

    from core.uploads import validate_private_document_upload

    exigir_operador(request)
    viagem = get_viagem_by_id(pk)
    retorno = voltar_para(request, reverse("viagens_viagem:etapa", args=[pk, 4]))
    arquivos = request.FILES.getlist("arquivo")
    if not arquivos:
        messages.error(request, "Nenhum arquivo selecionado.")
        return redirect(retorno)
    # A política central de anexos (m070): PDF de verdade ou imagem legível,
    # dentro do limite. O nome terminar em ".pdf" não basta. Cada recusado
    # ganha a sua mensagem; os bons entram mesmo assim.
    convertidos, recusados = [], []
    for arquivo in arquivos:
        nome = arquivo.name
        try:
            validate_private_document_upload(arquivo)
            convertidos.append(converter_para_pdf_se_necessario(arquivo))
        except ValidationError as exc:
            recusados.append(f"{nome}: {' '.join(exc.messages)}")
        except (UnidentifiedImageError, OSError, ValueError):
            recusados.append(f"{nome}: formato inválido. Envie um PDF ou arquivo de imagem.")
    for texto in recusados:
        messages.error(request, f"Arquivo recusado — {texto}")
    if convertidos:
        anexar_documentos_solicitacao(viagem, convertidos)
        messages.success(request, "Documentos de solicitação anexados com sucesso." if not recusados
                         else f"{len(convertidos)} documento(s) anexado(s); os demais foram recusados.")
    return redirect(retorno)


@acesso_ao_modulo
def solicitacao_conteudo(request, pk, anexo_pk):
    viagem = get_viagem_by_id(pk)
    anexo = get_documento_solicitacao_by_id(viagem, anexo_pk)
    return private_file_response(anexo.arquivo)


@acesso_ao_modulo
@require_POST
def solicitacao_excluir(request, pk, anexo_pk):
    exigir_operador(request)
    viagem = get_viagem_by_id(pk)
    anexo = buscar_documento_solicitacao(viagem, anexo_pk)
    if anexo is None:
        messages.error(request, "Documento não encontrado.")
    else:
        excluir_documento_solicitacao(anexo)
        messages.success(request, "Documento removido.")
    return redirect(voltar_para(request, reverse("viagens_viagem:etapa", args=[pk, 4])))
