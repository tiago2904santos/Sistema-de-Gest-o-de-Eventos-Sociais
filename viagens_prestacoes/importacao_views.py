"""Telas do importador de processo do eProtocolo (ver `importacao/`).

- `importacao_enviar`: recebe o PDF — da lista de Prestações, de Ofícios ou de
  Termos, ou do ⋮ de um ofício/termo com o registro já escolhido —, analisa fora
  da transação, registra e — se a leitura for segura — aplica sozinho; senão
  abre a conferência. A mesma tela serve às três listas: a volta é para a lista
  de onde o processo veio;
- `importacao_detalhe`: conferência (antes) e resultado (depois), na mesma tela;
- `importacao_aplicar`: grava com as escolhas da conferência, ou relê o processo
  com a prestação escolhida;
- `importacao_descartar`, `importacao_desfazer` (tira da prestação o que a
  importação gravou, quando só acrescentou), `importacao_arquivo` (o PDF para as miniaturas).

Permissões: as de anexar documento assinado (`ui.acesso`: módulo; operador para
gravar). As rotas que analisam não abrem transação no `acesso`: a leitura roda
fora dela e cada gravação abre a sua.
"""

from __future__ import annotations

import json
from pathlib import Path

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.http import HttpResponse
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.shortcuts import redirect
from django.urls import reverse

from core.retorno import com_next
from core.retorno import next_valido
from core.retorno import voltar_para
from core.utils.masks import format_protocolo
from viagens_cadastros.permissions import pode_editar_cadastros

from .importacao import ImportacaoRecusada
from .importacao import aplicar_escolhas
from .importacao import aplicar_importacao
from .importacao import descartar
from .importacao import desfazer
from .importacao import hash_do_arquivo
from .importacao import importacao_do_mesmo_arquivo
from .importacao import limite_de_bytes
from .importacao import pode_desfazer
from .importacao import reanalisar
from .importacao import registrar_importacao
from .importacao import validar_arquivo_do_processo
from .importacao.analise import analisar
from .importacao.montagem import descrever_paginas
from .importacao.plano import DESTINO_JUSTIFICATIVA
from .importacao.plano import DESTINOS
from .importacao.plano import DESTINOS_DOCUMENTO
from .importacao.plano import IGNORAR
from .importacao.plano import ORIGENS
from .importacao.plano import ROTULO_DESTINO
from .importacao.plano import Plano
from .models import OPERACAO_CHOICES
from .models import ImportacaoProcesso
from .models import PrestacaoContas
from .ui import render
from .view_common import _prestacao_queryset

__all__ = [
    "importacao_enviar",
    "importacao_detalhe",
    "importacao_aplicar",
    "importacao_descartar",
    "importacao_desfazer",
    "importacao_arquivo",
]


def _xhr(request) -> bool:
    return request.headers.get("X-Requested-With") == "XMLHttpRequest"


def _recusar(request, destino, mensagem):
    """A recusa no idioma de quem perguntou: JSON 400 para o fetch, mensagem + volta para o formulário."""
    if _xhr(request):
        return JsonResponse({"ok": False, "error": mensagem, "message": mensagem}, status=400)
    messages.error(request, mensagem)
    return redirect(destino)


def _ir(request, url, importacao=None, *, situacao=""):
    """Para o fetch (o envio em lote de vários arquivos), o resultado em JSON —
    com as mensagens, que assim não sobram para a próxima página; senão, a tela."""
    if _xhr(request):
        from django.contrib.messages import get_messages

        mensagens = [str(m) for m in get_messages(request)]
        if not situacao and importacao is not None:
            situacao = importacao.situacao
        destino = ""
        if importacao is not None and importacao.prestacao_id:
            destino = f"Ofício {importacao.prestacao.oficio.numero_formatado}"
        return JsonResponse({"ok": True, "url": url, "situacao": situacao, "destino": destino, "mensagens": mensagens})
    return redirect(url)


#: A lista de cada origem: a volta da conferência e do resultado.
_LISTA_DA_ORIGEM = {
    "prestacoes": "viagens_prestacoes:index",
    "oficios": "viagens_oficios:lista",
    "termos": "viagens_termos:lista",
}


def _url(importacao, request=None) -> str:
    """A tela da importação, levando adiante o `next` (a lista de onde se veio)."""
    url = reverse("viagens_prestacoes:importacao_detalhe", args=[importacao.pk])
    return com_next(url, next_valido(request)) if request is not None else url


def _lista_da_origem(origem: str) -> str:
    return reverse(_LISTA_DA_ORIGEM.get(origem, _LISTA_DA_ORIGEM["prestacoes"]))


def _mensagens_do_resultado(request, resultado) -> None:
    """A mensagem-resumo. Os avisos (carimbo, convalidação, protocolo) ficam no cartão
    do resultado, que continua lá quando a importação é reaberta."""
    messages.success(request, resultado.resumo)
    if resultado.resumo_documentos:
        messages.success(request, resultado.resumo_documentos)
    if resultado.avisos:
        messages.warning(request, "Há avisos sobre esta importação: veja em “Atenção”.")


def _origem(request, *, oficio_pk=None, termo_pk=None) -> str:
    """De que lista veio: o campo `origem` do formulário, ou o que a rota diz."""
    origem = request.POST.get("origem", "")
    if origem in ORIGENS:
        return origem
    return "termos" if termo_pk else "oficios" if oficio_pk else "prestacoes"


def importacao_enviar(request, pc_pk=None, oficio_pk=None, termo_pk=None):
    """Recebe o processo; aplica sozinho quando a leitura é segura.

    O registro pode vir escolhido: a prestação (⋮ do ofício na lista de
    Prestações), o ofício (⋮ na lista de Ofícios) ou o termo (⋮ na lista de Termos).
    """
    origem = _origem(request, oficio_pk=oficio_pk, termo_pk=termo_pk)
    voltar = voltar_para(request, _lista_da_origem(origem))
    prestacao = termo = None
    if pc_pk:
        prestacao = get_object_or_404(_prestacao_queryset().select_related("oficio"), pk=pc_pk)
    elif oficio_pk:
        prestacao = get_object_or_404(_prestacao_queryset().select_related("oficio"), oficio_id=oficio_pk)
    elif termo_pk:
        from viagens_termos.models import TermoAutorizacao

        termo = get_object_or_404(TermoAutorizacao.objects.select_related("oficio"), pk=termo_pk)
        if termo.cancelado:
            return _recusar(request, voltar, "Este termo está cancelado.")
    if prestacao is not None and prestacao.oficio.cancelado:
        return _recusar(request, voltar, "Este ofício está cancelado.")
    arquivo = request.FILES.get("arquivo")
    if not arquivo:
        return _recusar(request, voltar, "Escolha o PDF do processo do eProtocolo.")
    nome = Path(getattr(arquivo, "name", "") or "processo.pdf").name
    try:
        validar_arquivo_do_processo(arquivo)
    except ValidationError as exc:
        return _recusar(request, voltar, " ".join(exc.messages))
    arquivo.seek(0)
    dados = arquivo.read()

    anterior = importacao_do_mesmo_arquivo(hash_do_arquivo(dados))
    if anterior is not None:
        quando = anterior.criado_em.strftime("%d/%m/%Y %H:%M") if anterior.criado_em else ""
        destino = f" na prestação do Ofício {anterior.prestacao.oficio.numero_formatado}" if anterior.prestacao_id else ""
        situacao = "importado" if anterior.situacao == ImportacaoProcesso.SITUACAO_APLICADA else "enviado"
        messages.warning(request, f"Este mesmo arquivo já foi {situacao} em {quando}{destino}. Veja abaixo a importação anterior.")
        return _ir(request, _url(anterior, request), anterior, situacao="repetido")

    from core.errors import capture
    from core.leitura.pdf import ArquivoIlegivel

    try:
        plano = analisar(dados, nome, prestacao=prestacao, termo=termo, origem=origem)
    except ArquivoIlegivel as exc:
        return _recusar(request, voltar, str(exc))
    except Exception as exc:  # PDF que a leitura não entende: recusa com frase, não 500
        capture(exc, "prestacoes.importacao.analisar")
        return _recusar(request, voltar, "Não foi possível ler este processo. Confira se é o PDF baixado do eProtocolo.")
    duplicados = [item for item in plano.itens if item.duplicado]
    if duplicados and all(item.duplicado or item.destino == IGNORAR for item in plano.itens):
        # O mesmo comprovante em outro arquivo (o WhatsApp recomprime a foto): não grava de novo.
        messages.warning(request, " ".join(item.motivo for item in duplicados))
        destino = PrestacaoContas.objects.select_related("oficio").filter(pk=plano.prestacao_id).first()
        url = voltar
        if _xhr(request):
            return JsonResponse({
                "ok": True, "url": "", "situacao": "repetido",
                "destino": f"Ofício {destino.oficio.numero_formatado}" if destino else "",
                "mensagens": [str(m) for m in messages.get_messages(request)],
            })
        return redirect(url)
    importacao = registrar_importacao(dados, nome, plano, usuario=request.user)

    if plano.pronto:
        try:
            resultado = aplicar_importacao(importacao, plano=plano)
        except ImportacaoRecusada as exc:
            messages.error(request, str(exc))
        else:
            _mensagens_do_resultado(request, resultado)
            importacao.refresh_from_db()
            return _ir(request, _url(importacao, request), importacao)
    messages.info(request, "Confira os documentos do processo e clique em “Aplicar”.")
    return _ir(request, _url(importacao, request), importacao)


# ─────────────────────────────────────────────────────────────────
# Conferência e resultado
# ─────────────────────────────────────────────────────────────────

def _opcoes_destino(*, com_prestacao: bool = True):
    """Para onde um documento pode ir. Sem prestação (termo avulso), só os termos e a OS."""
    prestacao = list(DESTINOS) if com_prestacao else []
    documentos = [d for d in DESTINOS_DOCUMENTO if com_prestacao or d != DESTINO_JUSTIFICATIVA]
    return [{"valor": d, "rotulo": ROTULO_DESTINO[d]} for d in (*prestacao, *documentos, IGNORAR)]


def _termo_do_plano(plano):
    if not plano.termo_id:
        return None
    from viagens_termos.models import TermoAutorizacao

    return TermoAutorizacao.objects.select_related("oficio").filter(pk=plano.termo_id).first()


def _servidores_termo(prestacao, termo) -> list:
    from .importacao.artefatos import servidores_com_termo

    if prestacao is None and termo is None:
        return []
    return servidores_com_termo(prestacao.oficio if prestacao is not None else None, termo)


def _ordens_possiveis(plano, prestacao) -> list:
    """As OS que a conferência oferece: as do ofício e as que a leitura propôs."""
    from viagens_ordens.models import OrdemServico

    from django.db.models import Q

    ids = {item.ordem_servico_id for item in plano.itens if item.ordem_servico_id}
    consulta = OrdemServico.objects.filter(cancelado=False)
    filtro = Q(pk__in=ids)
    if prestacao is not None:
        filtro |= Q(oficios=prestacao.oficio_id)
    return list(consulta.filter(filtro).distinct().order_by("-ano", "-numero", "-pk"))


def _rotulo_da_ordem(ordem) -> str:
    numero = f"{ordem.numero:02d}/{ordem.ano}" if ordem.numero and ordem.ano else f"#{ordem.pk}"
    return f"Ordem de Serviço {numero}"


def _contexto(request, importacao) -> dict:
    plano = Plano.de_json(importacao.plano)
    prestacao = (
        PrestacaoContas.objects.select_related("oficio").filter(pk=plano.prestacao_id).first()
        if plano.prestacao_id else None
    )
    termo = _termo_do_plano(plano)
    equipe = list(prestacao.servidores_prestacao.select_related("servidor").order_by("pk")) if prestacao else []
    nomes = {ps.pk: ps.servidor.nome for ps in equipe}
    servidores_termo = _servidores_termo(prestacao, termo)
    nomes_termo = {s.pk: s.nome for s in servidores_termo}
    ordens = _ordens_possiveis(plano, prestacao)
    rotulos_os = {o.pk: _rotulo_da_ordem(o) for o in ordens}
    editavel = pode_editar_cadastros(request.user) and importacao.situacao != ImportacaoProcesso.SITUACAO_DESCARTADA
    aplicados = {item["ordem"]: item for item in (importacao.resultado or {}).get("anexos", [])}
    assinados: dict[int, list[dict]] = {}
    for entrada in (importacao.resultado or {}).get("documentos", []):
        if entrada.get("artefato"):
            entrada = {**entrada, "ver_url": reverse("viagens_oficios:preview_artefato", args=[entrada["artefato"]])}
        assinados.setdefault(entrada["ordem"], []).append(entrada)
    documentos = []
    for item in plano.itens:
        primeira = item.paginas[0] if item.paginas else 0
        documentos.append({
            "item": item,
            "ordem": item.ordem,
            "rotulo": item.rotulo or "Documento",
            "destino_rotulo": ROTULO_DESTINO.get(item.destino, "A definir"),
            "folhas": descrever_paginas(item.paginas),
            "primeira": primeira,
            "paginas_csv": ",".join(str(p) for p in item.paginas),
            "rotacao": item.rotacao_de(primeira) if item.paginas else 0,
            "rotacao_planejada": int(item.rotacoes.get(str(primeira), 0) or 0),
            "servidor_nome": nomes.get(item.servidor_prestacao_id, "") or nomes_termo.get(item.servidor_id, ""),
            "os_rotulo": rotulos_os.get(item.ordem_servico_id, ""),
            "valor_br": _valor_br(item.valor),
            "data_br": _data_br(item.data),
            "anexo": aplicados.get(item.ordem),
            "assinados": assinados.get(item.ordem, []),
            "nomes": {
                campo: f"doc-{item.ordem}-{campo}"
                for campo in ("destino", "servidor", "termo_servidor", "os", "valor", "data", "operacao")
            },
        })
    opcoes_servidor = [{"valor": str(ps.pk), "rotulo": ps.servidor.nome} for ps in equipe]
    candidatos = [{"valor": c.valor, "rotulo": c.rotulo} for c in plano.candidatos]
    if prestacao and not any(c["valor"] == str(prestacao.pk) for c in candidatos):
        from .importacao.analise import rotulo_do_oficio

        candidatos.insert(0, {"valor": str(prestacao.pk), "rotulo": rotulo_do_oficio(prestacao.oficio)})
    if not prestacao and termo is not None and not any(c["valor"] == f"termo:{termo.pk}" for c in candidatos):
        candidatos.insert(0, {"valor": f"termo:{termo.pk}", "rotulo": plano.termo_rotulo or f"Termo #{termo.pk}"})
    escolhido = str(plano.prestacao_id) if plano.prestacao_id else (f"termo:{plano.termo_id}" if plano.termo_id else "")
    voltar_url = voltar_para(request, _lista_da_origem(plano.origem))
    return {
        "page_title": "Importar processo do eProtocolo",
        "importacao": importacao,
        "plano": plano,
        "prestacao_escolhida": prestacao,
        "termo_escolhido": termo,
        "protocolo_display": format_protocolo(plano.protocolo) or plano.protocolo,
        "documentos": documentos,
        "opcoes_destino": _opcoes_destino(com_prestacao=prestacao is not None or termo is None),
        "opcoes_servidor": opcoes_servidor,
        "opcoes_servidor_termo": [{"valor": str(s.pk), "rotulo": s.nome} for s in servidores_termo],
        "opcoes_os": [{"valor": str(o.pk), "rotulo": rotulos_os[o.pk]} for o in ordens],
        "opcoes_operacao": [{"valor": v, "rotulo": r} for v, r in OPERACAO_CHOICES],
        "candidatos": candidatos,
        "candidato_escolhido": escolhido,
        # Com a leitura segura e um candidato só, trocar de prestação é exceção: o
        # seletor só aparece quando há dúvida (ou pelo "Trocar" discreto).
        "perguntar_prestacao": bool(candidatos) and (
            not plano.identificacao_segura or len(candidatos) > 1 or not plano.tem_registro
        ),
        "motivos_candidatos": [
            c for c in plano.candidatos
            if c.motivos and not (c.prestacao_id and c.prestacao_id == plano.prestacao_id)
            and not (c.termo_id and c.prestacao_id is None and c.termo_id == plano.termo_id)
        ][:4],
        "editavel": editavel,
        "aplicada": importacao.situacao == ImportacaoProcesso.SITUACAO_APLICADA,
        "pode_desfazer": editavel and pode_desfazer(importacao),
        "descartada": importacao.situacao == ImportacaoProcesso.SITUACAO_DESCARTADA,
        "resultado": importacao.resultado or {},
        "pendencias": plano.pendencias,
        "pdf_url": reverse("viagens_prestacoes:importacao_arquivo", args=[importacao.pk]),
        "voltar_url": voltar_url,
        # Os formulários da tela levam o `next` adiante: a volta continua a da lista de origem.
        "next_url": next_valido(request),
        "origem": plano.origem,
        # A Etapa 3 do primeiro servidor: é onde os documentos anexados aparecem.
        "prestacao_url": (
            reverse("viagens_prestacoes:documentos_servidor", args=[equipe[0].pk]) if equipe else ""
        ),
        "termo_url": reverse("viagens_termos:editar", args=[termo.pk]) if termo is not None else "",
        # Para a trilha do topo ("Prestações de Contas / Ofício 12/2026").
        "prestacao": prestacao,
        "miniaturas_json": json.dumps(
            [{"ordem": d["ordem"], "pagina": d["primeira"], "rotacao": d["rotacao_planejada"]} for d in documentos],
            ensure_ascii=False,
        ),
    }


def _valor_br(valor: str) -> str:
    from documentos.services.formatters import format_currency_br

    from .importacao.plano import _decimal

    numero = _decimal(valor)
    return format_currency_br(numero).replace("R$", "R$ ").replace("R$  ", "R$ ") if numero is not None else ""


def _data_br(iso: str) -> str:
    from .importacao.plano import _data

    dia = _data(iso)
    return dia.strftime("%d/%m/%Y") if dia else ""


def importacao_detalhe(request, pk):
    importacao = get_object_or_404(ImportacaoProcesso.objects.select_related("prestacao__oficio"), pk=pk)
    return render(request, "pages/viagens_prestacoes/importacao.html", _contexto(request, importacao))


def _escolha_de_registro(valor: str, plano):
    """O que o seletor da conferência mandou: (prestação, termo). ("", "") se nada válido.

    "12" é a prestação 12; "termo:5", o termo avulso 5. O termo do plano continua
    valendo com a prestação do ofício dele.
    """
    from viagens_termos.models import TermoAutorizacao

    if valor.startswith("termo:") and valor[6:].isdigit():
        termo = TermoAutorizacao.objects.select_related("oficio").filter(pk=valor[6:], cancelado=False).first()
        return (None, termo) if termo is not None else (None, None)
    if not valor.isdigit():
        return None, None
    prestacao = PrestacaoContas.objects.select_related("oficio").filter(pk=valor, oficio__cancelado=False).first()
    if prestacao is None:
        return None, None
    termo = _termo_do_plano(plano)
    return prestacao, (termo if termo is not None and termo.oficio_id == prestacao.oficio_id else None)


def importacao_aplicar(request, pk):
    """Aplica com as escolhas da conferência — ou relê o processo com outra prestação (ou termo)."""
    importacao = get_object_or_404(ImportacaoProcesso, pk=pk)
    url = _url(importacao, request)
    if importacao.situacao == ImportacaoProcesso.SITUACAO_DESCARTADA:
        messages.error(request, "Esta importação foi descartada. Envie o processo de novo.")
        return redirect(url)
    plano = Plano.de_json(importacao.plano)

    escolhida = request.POST.get("prestacao") or ""
    atual = str(plano.prestacao_id) if plano.prestacao_id else (f"termo:{plano.termo_id}" if plano.termo_id else "")
    if request.POST.get("acao") == "reanalisar" or (escolhida and escolhida != atual):
        prestacao, termo = _escolha_de_registro(escolhida, plano)
        if prestacao is None and termo is None:
            messages.error(request, "Escolha a prestação de contas deste processo.")
            return redirect(url)
        from core.leitura.pdf import ArquivoIlegivel

        try:
            reanalisar(importacao, prestacao, termo=termo)
        except ArquivoIlegivel as exc:
            messages.error(request, str(exc))
            return redirect(url)
        destino = f"a prestação do Ofício {prestacao.oficio.numero_formatado}" if prestacao else f"o Termo #{termo.pk}"
        messages.info(request, f"Documentos conferidos com {destino}: confira e clique em “Aplicar”.")
        return redirect(url)

    from .models import PrestacaoServidor

    equipe_ids = set()
    if plano.prestacao_id:
        equipe_ids = set(PrestacaoServidor.objects.filter(prestacao_id=plano.prestacao_id).values_list("pk", flat=True))
    prestacao = PrestacaoContas.objects.select_related("oficio").filter(pk=plano.prestacao_id).first() if plano.prestacao_id else None
    termo = _termo_do_plano(plano)
    plano = aplicar_escolhas(
        plano, request.POST, equipe_ids=equipe_ids,
        servidores_termo_ids={s.pk for s in _servidores_termo(prestacao, termo)},
        ordens_ids={o.pk for o in _ordens_possiveis(plano, prestacao)},
    )
    try:
        resultado = aplicar_importacao(importacao, plano=plano)
    except ImportacaoRecusada as exc:
        messages.error(request, str(exc))
        return redirect(url)
    _mensagens_do_resultado(request, resultado)
    return redirect(url)


def importacao_descartar(request, pk):
    importacao = get_object_or_404(ImportacaoProcesso, pk=pk)
    if importacao.situacao == ImportacaoProcesso.SITUACAO_APLICADA:
        messages.error(request, "Esta importação já foi aplicada: os documentos estão gravados.")
        return redirect(_url(importacao, request))
    descartar(importacao)
    messages.success(request, "Importação descartada. Nada foi gravado.")
    return redirect(voltar_para(request, _lista_da_origem(Plano.de_json(importacao.plano).origem)))


def importacao_desfazer(request, pk):
    """Tira da prestação o que a importação gravou; ela volta para a conferência."""
    importacao = get_object_or_404(ImportacaoProcesso, pk=pk)
    if not pode_desfazer(importacao):
        messages.error(request, "Esta importação não pode ser desfeita: ela substituiu documentos que já estavam na prestação.")
        return redirect(_url(importacao, request))
    removidos = desfazer(importacao)
    messages.success(
        request,
        f"Importação desfeita: {removidos} documento{'s' if removidos != 1 else ''} saíram da prestação. "
        "Escolha a prestação certa e aplique de novo, ou descarte.",
    )
    return redirect(_url(importacao, request))


def importacao_arquivo(request, pk):
    """O processo em PDF, para as miniaturas (imagem enviada vira PDF de uma página)."""
    from core.leitura.pdf import como_pdf

    importacao = get_object_or_404(ImportacaoProcesso, pk=pk)
    importacao.arquivo.open("rb")
    try:
        conteudo = como_pdf(importacao.arquivo.read())
    except Exception:
        return HttpResponse(status=404)
    finally:
        importacao.arquivo.close()
    resposta = HttpResponse(conteudo, content_type="application/pdf")
    resposta["Content-Disposition"] = "inline"
    resposta["Cache-Control"] = "private, no-store"
    resposta["X-Content-Type-Options"] = "nosniff"
    return resposta


def limite_em_mb() -> int:
    return limite_de_bytes() // (1024 * 1024)
