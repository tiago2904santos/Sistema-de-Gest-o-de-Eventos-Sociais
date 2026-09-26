import json
from pathlib import Path

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.http import HttpResponse
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from core.autosave import autosave_json_response
from core.private_media import private_file_response
from core.uploads import validate_private_document_upload
from core.retorno import voltar_para

from .forms import PrestacaoDespachoForm, PrestacaoServidorDocumentosForm, PrestacaoSolicitacaoForm
from .models import PrestacaoDocumentoAnexo
from .presenters import _anexo_assinado_info
from .anexo_services import endireitar_diario_anexado
from .anexo_services import excluir_anexo
from .anexo_services import restaurar_anexo
from .anexo_services import substituir_anexo_assinado
from .carimbo_services import anexo_do_oficio_assinado
from .carimbo_services import caixas_para_ajuste
from .carimbo_services import preparar_e_carimbar
from .carimbo_services import salvar_posicoes
from .presenters import kinds_de_anexo_assinado
from .presenters import kinds_de_anexo_assinado_json
from .download_services import payload_downloads
from .services import marcar_servidor_em_preenchimento
from .services import marcar_servidores_pendentes
from .services import pendencias_consolidado
from .services import pendencias_para_finalizar
from .services import dados_eprotocolo_prestacao
from .prazos import selo_da_prestacao
from .view_common import (
    _autosave_form_errors,
    _autosave_version,
    _build_identificacao,
    contexto_do_fluxo,
    _prestacao_queryset,
    _prestacao_servidor_full,
    _prestacao_servidor_queryset,
    _redirect_primeiro_servidor,
    _servidor_identificacao,
)


def _anexos_rows(prestacao, anexos_qs):
    rows = []
    for anexo in anexos_qs.order_by("criado_em", "pk"):
        rows.append(
            {
                "id": anexo.pk,
                "nome": anexo.nome_original or Path(anexo.arquivo.name).name,
                "url": reverse(
                    "viagens_prestacoes:prestacao_documento_conteudo",
                    args=[prestacao.pk, anexo.pk],
                ),
                "delete_url": reverse(
                    "viagens_prestacoes:prestacao_documento_delete",
                    args=[prestacao.pk, anexo.pk],
                ),
            },
        )
    return rows


def prestacao_documento_conteudo(request, pc_pk, anexo_pk):
    prestacao = get_object_or_404(_prestacao_queryset(), pk=pc_pk)
    # `todos`: as versões anteriores (m084) também se abrem, para conferir antes de voltar.
    anexo = get_object_or_404(
        PrestacaoDocumentoAnexo.todos,
        pk=anexo_pk,
        prestacao=prestacao,
    )
    return private_file_response(anexo.arquivo)


def prestacao_oficio_assinado_cru(request, pc_pk):
    """Serve o PDF **sem** os números, que é o que a tela de ajuste desenha por cima.

    Mostrar o carimbado ali faria o operador arrastar uma caixa sobre um número que já
    está impresso, e ver dois — o desenhado e o da caixa.
    """
    prestacao = get_object_or_404(_prestacao_queryset(), pk=pc_pk)
    anexo = anexo_do_oficio_assinado(prestacao)
    if anexo is None:
        return HttpResponse(status=404)
    return private_file_response(anexo.arquivo_para_carimbar)


def _servidor_documentos_ctx(prestacao, ps):
    form = PrestacaoSolicitacaoForm(instance=ps, prefix=f"ps-{ps.pk}")
    anexos_ps = list(ps.documentos_anexos.all())
    anexos_pc = list(
        prestacao.documentos_anexos.filter(tipo=PrestacaoDocumentoAnexo.TIPO_DB_ASSINADO)
    )
    return {
        "ps": ps,
        "ps_pk": ps.pk,
        "name": ps.servidor.nome,
        "identificacao": _servidor_identificacao(ps),
        "form": form,
        "solicitacao_autosave_url": reverse(
            "viagens_prestacoes:prestacao_servidor_solicitacao_autosave", args=[ps.pk]
        ),
        "rt_assinado": _anexo_assinado_info(
            anexos_ps,
            tipo=PrestacaoDocumentoAnexo.TIPO_RT_ASSINADO,
            anexar_url=reverse(
                "viagens_prestacoes:prestacao_servidor_assinado_anexar",
                args=[ps.pk, PrestacaoDocumentoAnexo.TIPO_RT_ASSINADO],
            ),
            prestacao_pk=prestacao.pk,
        ),
        "comprovante_anexo": _anexo_assinado_info(
            anexos_ps,
            tipo=PrestacaoDocumentoAnexo.TIPO_COMPROVANTE,
            anexar_url=reverse(
                "viagens_prestacoes:prestacao_servidor_assinado_anexar",
                args=[ps.pk, PrestacaoDocumentoAnexo.TIPO_COMPROVANTE],
            ),
            prestacao_pk=prestacao.pk,
        ),
        "diario_assinado": _anexo_assinado_info(
            anexos_pc,
            tipo=PrestacaoDocumentoAnexo.TIPO_DB_ASSINADO,
            anexar_url=reverse(
                "viagens_prestacoes:prestacao_servidor_assinado_anexar",
                args=[ps.pk, PrestacaoDocumentoAnexo.TIPO_DB_ASSINADO],
            ),
            prestacao_pk=prestacao.pk,
        ),
    }


def documentos(request, pc_pk):
    """Compatibilidade: redireciona para o primeiro servidor."""
    prestacao = get_object_or_404(_prestacao_queryset(), pk=pc_pk)
    return _redirect_primeiro_servidor(request, prestacao, "viagens_prestacoes:documentos_servidor")


def documentos_servidor(request, ps_pk):
    """Etapa 3: despacho compartilhado + documentos do servidor atual."""
    ps = _prestacao_servidor_full(ps_pk)
    prestacao = ps.prestacao
    servidor = _servidor_documentos_ctx(prestacao, ps)
    anexos_compartilhados = list(
        prestacao.documentos_anexos.filter(
            tipo__in=(
                PrestacaoDocumentoAnexo.TIPO_DESPACHO,
                PrestacaoDocumentoAnexo.TIPO_OFICIO_ASSINADO,
            )
        )
    )
    despacho_assinado = _anexo_assinado_info(
        anexos_compartilhados,
        tipo=PrestacaoDocumentoAnexo.TIPO_DESPACHO,
        anexar_url=reverse(
            "viagens_prestacoes:prestacao_despacho_assinado_anexar",
            args=[prestacao.pk],
        ),
        prestacao_pk=prestacao.pk,
    )
    oficio_assinado = _anexo_assinado_info(
        anexos_compartilhados,
        tipo=PrestacaoDocumentoAnexo.TIPO_OFICIO_ASSINADO,
        anexar_url=reverse(
            "viagens_prestacoes:prestacao_oficio_assinado_anexar",
            args=[prestacao.pk],
        ),
        prestacao_pk=prestacao.pk,
        ajustar_url=reverse(
            "viagens_prestacoes:prestacao_carimbo_ajustar",
            args=[prestacao.pk],
        ),
    )
    identificacao = _build_identificacao(prestacao)
    numero = identificacao.get("numero") or ""

    # `H-03`: eram cinco chaves ordinais (`primary`…`quinary`) — nome que dizia a
    # POSIÇÃO, não o documento. Cada uma virava 6 atributos `data-*` planos no
    # gatilho, 30 no total. Ver `kinds_de_anexo_assinado`.
    # Na ordem da prestação (`ORDEM_DOCUMENTOS_PRESTACAO`).
    attach_kinds = kinds_de_anexo_assinado(
        [
            ("oficio", "Ofício", f"o ofício {numero}", oficio_assinado),
            ("despacho", "Despacho", f"o despacho do ofício {numero}", despacho_assinado),
            (
                "rt",
                "RT",
                f"o relatório técnico de {servidor['name']}",
                servidor["rt_assinado"],
            ),
            (
                "diario",
                "DB",
                f"o diário de bordo do ofício {numero}",
                servidor["diario_assinado"],
            ),
            (
                "comprovante",
                "Comprovante",
                (
                    "o comprovante de saque ou transferência de "
                    f"{servidor['name']}"
                ),
                servidor["comprovante_anexo"],
            ),
        ]
    )

    return render(
        request,
        "pages/viagens_prestacoes/documentos_form.html",
        {
            "page_title": f"Documentos — {ps.servidor.nome}",
            "prestacao": prestacao,
            "ps": ps,
            "servidor": servidor,
            "servidores": [servidor],
            "identificacao": identificacao,
            "despacho_assinado": despacho_assinado,
            "oficio_assinado": oficio_assinado,
            "attach_kinds": attach_kinds,
            # Um payload só, no gatilho, em vez de 30 atributos planos. Sai como
            # string e o template escapa: quem monta o HTML não é o Python.
            "attach_kinds_json": kinds_de_anexo_assinado_json(attach_kinds),
            # `contexto_do_fluxo` já entrega `wizard_page_steps` junto com os
            # metadados de cabeçalho (H-02).
            **contexto_do_fluxo(ps, "documentos"),
            "back_url": reverse("viagens_prestacoes:index"),
            # A etapa anterior é o RT desde a inversão de 2026-08-28 (diário → RT → documentos).
            "rt_url": reverse("viagens_prestacoes:rt_servidor", args=[ps.pk]),
            # O fechamento (pacote final, downloads e finalização) virou o fim
            # desta etapa: a tela de PDF final deixou de existir.
            "pendencias": pendencias_consolidado(ps),
            # m092: o que falta para finalizar (o pacote é só uma parte disso).
            "pendencias_finalizar": [] if ps.finalizada else pendencias_para_finalizar(ps),
            # m094: 3 dias úteis depois do fim do prazo de saque, contando feriados.
            "selo_prestacao": selo_da_prestacao(ps),
            # m052: os campos para protocolar a prestação, cada um com Copiar.
            "eprotocolo": dados_eprotocolo_prestacao(ps),
            "hoje_iso": timezone.localdate().isoformat(),
            "downloads": payload_downloads(ps)["itens"],
            # O modal "Baixar documentos" (o mesmo da lista), no botão de ação do cartão.
            "url_baixar": reverse("viagens_prestacoes:prestacao_baixar", args=[ps.pk]),
            "itens_baixar": json.dumps([
                {"valor": d["id"], "nome": d["titulo"], "detalhe": d["subtitulo"],
                 "estado": "Assinado" if d["versoes"]["assinado"] else "Original", "assinado": bool(d["versoes"]["assinado"])}
                for d in payload_downloads(ps)["itens"]
            ], ensure_ascii=False),
        },
    )


def prestacao_arquivo_autosave(request, pc_pk):
    """Autosave do despacho (compartilhado)."""
    prestacao = get_object_or_404(_prestacao_queryset(), pk=pc_pk)
    form = PrestacaoDespachoForm(request.POST, request.FILES, instance=prestacao)
    if not form.is_valid():
        return autosave_json_response(
            ok=False,
            message="Alguns anexos ainda precisam de ajuste antes do autosave.",
            errors=_autosave_form_errors(form),
        )
    form.save()
    marcar_servidores_pendentes(prestacao)
    return autosave_json_response(
        ok=True,
        object_id=prestacao.pk,
        version=_autosave_version(prestacao),
    )


def prestacao_servidor_arquivo_autosave(request, ps_pk):
    """Autosave do comprovante de saque (individual do servidor).

    Salva apenas os anexos — não reescreve o ``numero_solicitacao`` (que tem seu
    próprio autosave), evitando apagá-lo quando o POST traz só o arquivo.
    """
    ps = get_object_or_404(_prestacao_servidor_queryset().select_related("prestacao"), pk=ps_pk)
    form = PrestacaoServidorDocumentosForm(request.POST, request.FILES, instance=ps, prefix=f"ps-{ps.pk}")
    if not form.is_valid():
        return autosave_json_response(
            ok=False,
            message="Alguns anexos ainda precisam de ajuste antes do autosave.",
            errors=_autosave_form_errors(form),
        )
    form.save_anexos(ps)
    marcar_servidor_em_preenchimento(ps)
    return autosave_json_response(
        ok=True,
        object_id=ps.pk,
        version=_autosave_version(ps),
    )


def _upload_recusado(request, destino, mensagens):
    """A recusa do upload, dita no idioma de quem perguntou.

    `NOVO-20260824-133423-35fbd4d59a84`: o modal de anexar assinado envia por
    `fetch` quando há mais de um documento na mesma janela, e `fetch` SEGUE o
    redirect. A página de destino era renderizada dentro da resposta do XHR — e
    renderizar consome as `messages`. Resultado medido: arquivo recusado (PDF
    corrompido, extensão errada, limite de tamanho), redirect 302, `response.ok`
    verdadeiro, `window.location.reload()` e uma tela idêntica à de antes, sem
    anexo e sem uma palavra. O operador só via "não anexou".

    Para o XHR a recusa vira 400 com o motivo no corpo; o caminho de formulário
    comum continua sendo mensagem + redirect.
    """
    if request.headers.get("X-Requested-With") == "XMLHttpRequest":
        # `error` e `message` com o mesmo texto: o modal lê um, o cartão da Etapa 3
        # (que também fala com o autosave) lê o outro.
        texto = " ".join(mensagens)
        return JsonResponse({"ok": False, "error": texto, "message": texto}, status=400)
    for mensagem in mensagens:
        messages.error(request, mensagem)
    return redirect(destino)


def _prestacao_assinado_upload(
    request,
    *,
    prestacao,
    tipo,
    servidor_prestacao=None,
    substituir_todos_do_tipo=False,
    pos_anexo=None,
    adicionar=False,
):
    fallback_url = reverse("viagens_prestacoes:index")
    destino = voltar_para(request, fallback_url)
    arquivo = request.FILES.get("arquivo")
    if not arquivo:
        return _upload_recusado(
            request,
            destino,
            ["Selecione um arquivo PDF para anexar."],
        )

    nome_original = Path(getattr(arquivo, "name", "") or "").name
    # QA-04: a política central (tamanho, magic bytes, bomba de descompressão,
    # antivírus) precisa rodar antes de qualquer escrita. Conferir só o sufixo
    # aceitava arquivo que mente sobre o próprio conteúdo — e ele ainda era
    # sincronizado com o Google Drive depois.
    try:
        validate_private_document_upload(arquivo)
    except ValidationError as exc:
        return _upload_recusado(request, destino, list(exc.messages))

    if adicionar and _ja_anexado(prestacao, tipo, servidor_prestacao, arquivo):
        return _upload_recusado(request, destino, ["Este arquivo já está anexado."])
    anteriores = PrestacaoDocumentoAnexo.objects.filter(prestacao=prestacao, tipo=tipo, servidor_prestacao=servidor_prestacao).count() if adicionar else 0

    # A validação vem antes da exclusão dos anteriores de propósito: recusar um
    # arquivo novo não pode custar o que já estava anexado.
    resultado = substituir_anexo_assinado(
        prestacao,
        tipo=tipo,
        arquivo=arquivo,
        nome_original=nome_original,
        servidor_prestacao=servidor_prestacao,
        substituir_todos_do_tipo=substituir_todos_do_tipo,
        adicionar=adicionar,
    )
    if pos_anexo is not None and resultado.anexo is not None:
        pos_anexo(resultado.anexo)
    elif anteriores:
        plural = "s" if anteriores > 1 else ""
        messages.success(request, f"Documento assinado anexado. O{plural} {anteriores} anterior{'es' if plural else ''} continua{'m' if plural else ''} anexado{plural}.")
    else:
        messages.success(request, "Documento assinado anexado.")
    if request.headers.get("X-Requested-With") == "XMLHttpRequest":
        # Sem renderizar o destino, as `messages` sobrevivem na sessão e aparecem
        # no recarregamento que o modal dispara — inclusive os avisos do carimbo,
        # que o redirect seguido pelo `fetch` engolia junto com os erros.
        return JsonResponse({"ok": True})
    return redirect(destino)


def _ja_anexado(prestacao, tipo, servidor_prestacao, arquivo) -> bool:
    """O mesmo arquivo (byte a byte) já está entre os anexos deste tipo e escopo.

    Só para os tipos que somam (m081): sem substituir, um duplo clique ou o mesmo PDF
    enviado duas vezes duplicaria o documento no pacote final.
    """
    import hashlib

    def resumo(leitor):
        h = hashlib.sha256()
        for bloco in iter(lambda: leitor.read(1 << 16), b""):
            h.update(bloco)
        return h.hexdigest()

    tamanho = getattr(arquivo, "size", None)
    anteriores = PrestacaoDocumentoAnexo.objects.filter(prestacao=prestacao, tipo=tipo, servidor_prestacao=servidor_prestacao)
    candidatos = []
    for anexo in anteriores:
        try:
            if tamanho is None or anexo.arquivo.size == tamanho:
                candidatos.append(anexo)
        except OSError:
            continue
    if not candidatos:
        return False
    arquivo.seek(0)
    novo = resumo(arquivo)
    arquivo.seek(0)
    for anexo in candidatos:
        try:
            with anexo.arquivo.open("rb") as leitor:
                if resumo(leitor) == novo:
                    return True
        except OSError:
            continue
    return False


def prestacao_despacho_assinado_anexar(request, pc_pk):
    # O despacho pode vir em mais de um arquivo (despacho + folha de assinatura): soma.
    prestacao = get_object_or_404(_prestacao_queryset(), pk=pc_pk)
    return _prestacao_assinado_upload(
        request,
        prestacao=prestacao,
        tipo=PrestacaoDocumentoAnexo.TIPO_DESPACHO,
        adicionar=True,
    )


def prestacao_oficio_assinado_anexar(request, pc_pk):
    """Anexa o ofício que voltou do eProtocolo e já grava os números de solicitação.

    O carimbo não é um passo à parte: o assinado volta com a coluna de solicitação em
    branco, e é essa versão que o consolidado usa. Sem carimbar aqui, anexar o assinado
    faria a prestação PERDER os números que a versão gerada tinha.
    """
    prestacao = get_object_or_404(_prestacao_queryset(), pk=pc_pk)

    def carimbar(anexo):
        resultado = preparar_e_carimbar(anexo, prestacao=prestacao)
        for mensagem, nivel in _mensagens_do_carimbo(resultado):
            nivel(request, mensagem)

    return _prestacao_assinado_upload(
        request,
        prestacao=prestacao,
        tipo=PrestacaoDocumentoAnexo.TIPO_OFICIO_ASSINADO,
        pos_anexo=carimbar,
    )


def _mensagens_do_carimbo(resultado):
    """Traduz o resultado do carimbo no que o operador precisa saber.

    Sempre diz o que ENTROU antes do que faltou: anexar com metade dos números é um
    avanço, e abrir com a pendência faria parecer recusa.
    """
    if resultado.erro:
        return [(f"Documento anexado, mas o carimbo falhou: {resultado.erro}", messages.warning)]

    saida = []
    if resultado.carimbados:
        plural = "s" if resultado.carimbados > 1 else ""
        saida.append(
            (
                f"Ofício assinado anexado com {resultado.carimbados} número{plural} "
                f"de solicitação gravado{plural}.",
                messages.success,
            )
        )
    else:
        saida.append(("Ofício assinado anexado.", messages.success))

    if resultado.sem_numero:
        saida.append(
            (
                "Sem número de solicitação, e por isso fora do carimbo: "
                + ", ".join(resultado.sem_numero)
                + ". Preencha o número e o ofício é recarimbado sozinho.",
                messages.warning,
            )
        )
    if resultado.sem_posicao:
        saida.append(
            (
                "Não foi possível descobrir onde carimbar: "
                + ", ".join(resultado.sem_posicao)
                + ". Use “Ajustar posição” para posicionar à mão.",
                messages.warning,
            )
        )
    elif resultado.incertos:
        saida.append(
            (
                "A posição de alguns números foi estimada — confira o documento e use "
                "“Ajustar posição” se algum saiu fora do lugar.",
                messages.info,
            )
        )
    return saida


def prestacao_servidor_assinado_anexar(request, ps_pk, tipo):
    servidor_prestacao = get_object_or_404(
        _prestacao_servidor_queryset().select_related("prestacao__oficio"),
        pk=ps_pk,
    )
    tipos_permitidos = {
        PrestacaoDocumentoAnexo.TIPO_RT_ASSINADO,
        PrestacaoDocumentoAnexo.TIPO_COMPROVANTE,
        PrestacaoDocumentoAnexo.TIPO_DB_ASSINADO,
    }
    if tipo not in tipos_permitidos:
        return HttpResponse(status=404)
    diario_compartilhado = tipo == PrestacaoDocumentoAnexo.TIPO_DB_ASSINADO

    def endireitar(anexo):
        # O diário entra em pé (paisagem, nunca de cabeça para baixo), como pelo importador.
        if endireitar_diario_anexado(anexo):
            messages.success(request, "Diário de bordo anexado, com as páginas giradas para ficar em pé.")
        else:
            messages.success(request, "Documento assinado anexado.")

    return _prestacao_assinado_upload(
        request,
        prestacao=servidor_prestacao.prestacao,
        servidor_prestacao=None if diario_compartilhado else servidor_prestacao,
        tipo=tipo,
        substituir_todos_do_tipo=diario_compartilhado,
        pos_anexo=endireitar if diario_compartilhado else None,
        # Vários comprovantes por servidor (saque + transferência): soma, não troca.
        adicionar=tipo == PrestacaoDocumentoAnexo.TIPO_COMPROVANTE,
    )


def prestacao_carimbo_ajustar(request, pc_pk):
    """Tela de ajuste: arrastar cada número sobre o ofício assinado.

    Existe porque o automático pode errar — eProtocolo que recompõe o texto, ou PDF
    escaneado, em que não há âncora para transportar a posição. É a saída manual, e não
    o caminho comum.
    """
    prestacao = get_object_or_404(_prestacao_queryset(), pk=pc_pk)
    anexo = anexo_do_oficio_assinado(prestacao)
    if anexo is None:
        messages.error(request, "Anexe o ofício assinado antes de ajustar o carimbo.")
        return redirect(voltar_para(request, reverse("viagens_prestacoes:index")))

    caixas = caixas_para_ajuste(prestacao, anexo)

    if request.method == "POST":
        posicoes, erro = _posicoes_do_post(request.POST, caixas)
        if erro:
            messages.error(request, erro)
        else:
            resultado = salvar_posicoes(anexo, posicoes)
            if resultado.erro:
                messages.error(request, resultado.erro)
            else:
                messages.success(request, "Carimbo reposicionado.")
        return redirect(voltar_para(request, reverse("viagens_prestacoes:index")))

    return render(
        request,
        "pages/viagens_prestacoes/carimbo_ajustar.html",
        {
            "page_title": "Ajustar posição do número de solicitação",
            "prestacao": prestacao,
            "anexo": anexo,
            "caixas": caixas,
            "caixas_json": json.dumps(caixas, ensure_ascii=False),
            "pdf_url": reverse(
                "viagens_prestacoes:prestacao_oficio_assinado_cru", args=[prestacao.pk]
            ),
            "voltar_url": voltar_para(request, reverse("viagens_prestacoes:index")),
        },
    )


def _posicoes_do_post(post, caixas):
    """Lê `caixa-<ps>-<campo>` do POST. Só forma; a faixa quem valida é o service.

    Recebe o `QueryDict`, não o `request` (`docs/PADRAO_SERVICES.md`). Caixa ausente do
    POST é ignorada em silêncio — o navegador pode não ter mandado a de uma página que o
    operador não abriu, e apagar a posição dela seria perder trabalho anterior.
    """
    posicoes = {}
    for caixa in caixas:
        prefixo = f"caixa-{caixa['ps_pk']}-"
        if f"{prefixo}x" not in post:
            continue
        try:
            posicoes[caixa["ps_pk"]] = (
                int(post.get(f"{prefixo}pagina") or 0),
                float(post.get(f"{prefixo}x") or 0),
                float(post.get(f"{prefixo}y") or 0),
                float(post.get(f"{prefixo}tamanho") or 0),
            )
        except (TypeError, ValueError):
            return {}, "Posição inválida; refaça o ajuste."
    return posicoes, ""


@require_POST
def prestacao_documento_excluir(request, pc_pk, anexo_pk):
    prestacao = get_object_or_404(_prestacao_queryset(), pk=pc_pk)
    anexo = get_object_or_404(
        PrestacaoDocumentoAnexo,
        pk=anexo_pk,
        prestacao=prestacao,
    )
    # m084: não apaga — guarda em "Versões anteriores", de onde dá para restaurar.
    excluir_anexo(anexo, prestacao)
    messages.success(
        request,
        f"“{anexo.nome_original or 'Arquivo'}” removido. Para desfazer, use “Restaurar” em Versões anteriores.",
    )
    return autosave_json_response(
        ok=True,
        object_id=prestacao.pk,
        version=_autosave_version(prestacao),
    )


@require_POST
def prestacao_documento_restaurar(request, pc_pk, anexo_pk):
    """Volta um anexo removido ou substituído (m084)."""
    prestacao = get_object_or_404(_prestacao_queryset(), pk=pc_pk)
    anexo = get_object_or_404(PrestacaoDocumentoAnexo.todos, pk=anexo_pk, prestacao=prestacao)
    resultado = restaurar_anexo(anexo)
    nome = anexo.nome_original or "Arquivo"
    if resultado.substituidos:
        messages.success(request, f"“{nome}” voltou a ser o documento em uso; o que estava no lugar ficou em Versões anteriores.")
    else:
        messages.success(request, f"“{nome}” restaurado.")
    return redirect(voltar_para(request, reverse("viagens_prestacoes:index")))

from .ui import render
