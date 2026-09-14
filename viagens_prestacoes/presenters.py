import json

from django.urls import reverse

from viagens_oficios.roteiro_context import periodo_roteiro

from django.utils import timezone

def _iniciais_nome_servidor(nome):
    return "".join(p[0] for p in (nome or "").split()[:2])

def _destino_display_oficio(oficio):
    if not oficio.roteiro_id:
        return ""
    destinos = list(oficio.roteiro.destinos.select_related("municipio__estado").order_by("ordem", "pk"))
    return ", ".join(str(d.municipio) for d in destinos[:2]) + (f" +{len(destinos)-2}" if len(destinos)>2 else "")

def _data_evento_display_oficio(oficio):
    if not oficio.roteiro_id:
        return ""
    saida, retorno = periodo_roteiro(oficio.roteiro)
    def fmt(dt):
        return timezone.localtime(dt).strftime("%d/%m/%Y") if dt else ""
    return " a ".join(dict.fromkeys(v for v in (fmt(saida), fmt(retorno)) if v))

def _anexo_assinado_info(anexos, *, tipo, anexar_url, prestacao_pk, ajustar_url=""):
    """Estado do anexo assinado de um tipo, para o cartão da tela de documentos.

    `ajustar_url` só é passado pelo ofício: é ele que recebe o carimbo do número de
    solicitação, e é dele o botão de reposicionar. Vazio nos demais, e o cartão não
    mostra o botão — despacho e comprovante não têm o que ajustar.
    """
    atual = next(
        (anexo for anexo in reversed(list(anexos)) if anexo.tipo == tipo),
        None,
    )
    if atual is None:
        return {
            "assinado": False,
            "anexar_url": anexar_url,
            "nome_original": "",
            "view_url": "",
            "remover_url": "",
            "ajustar_url": "",
        }
    return {
        "assinado": True,
        "anexar_url": anexar_url,
        "nome_original": atual.nome_original or atual.arquivo.name.rsplit("/", 1)[-1],
        "view_url": reverse(
            "viagens_prestacoes:prestacao_documento_conteudo",
            args=[prestacao_pk, atual.pk],
        ),
        "remover_url": reverse(
            "viagens_prestacoes:prestacao_documento_delete",
            args=[prestacao_pk, atual.pk],
        ),
        "ajustar_url": ajustar_url,
    }

def kinds_de_anexo_assinado(documentos):
    """Payload do modal de anexo assinado: uma lista ordenada, com chave semântica.

    `H-03`. Antes, cada documento anexável era identificado por **ordinal latino**
    (`primary`…`quinary`) e viajava como 6 atributos `data-*` planos no gatilho.
    Duas consequências:

    - o mesmo ordinal significava documentos **diferentes** em telas diferentes —
      `primary` era o despacho na etapa Documentos e o relatório técnico no card
      da lista, contra o mesmo modal;
    - o JS carregava uma lista fixa dos cinco ordinais e o modal tinha os cinco
      botões escritos à mão, então um sexto documento exigia editar view,
      template, modal e JS.

    `documentos` é uma lista de `(key, option_label, doc_label, info)`, onde
    `info` é o retorno de `_anexo_assinado_info`. A ordem da lista é a ordem em
    que os botões aparecem no modal.
    """
    return [
        {
            "key": key,
            "option_label": option_label,
            "doc_label": doc_label,
            "url": info["anexar_url"],
            "current_name": info["nome_original"],
            "current_view_url": info["view_url"],
            "current_remove_url": info["remover_url"],
        }
        for key, option_label, doc_label, info in documentos
        if info and info.get("anexar_url")
    ]

def kinds_de_anexo_assinado_json(kinds):
    """Serializa os tipos para o atributo `data-attach-signed-kinds` do gatilho.

    `NOVO-20260826-111043-802915c4fd6a` (`PF-07`): o payload viaja ESCAPADO dentro de um atributo HTML — cada
    aspa vira `&quot;`, seis bytes. Com cinco tipos por cartão e vinte cartões, os
    campos `current_*` vazios (o caso comum: nada anexado ainda) custavam 13,5 KB
    de `&quot;&quot;` na lista de prestações.

    Campo vazio não viaja. É seguro porque todo leitor no
    `attach-signed-modal.js` já tem valor padrão (`item.current_name || ""`), e a
    lista Python continua intacta — quem a consome é a etapa Documentos, que
    renderiza um cartão por tipo e conta com as chaves presentes.
    """
    return json.dumps(
        [{chave: valor for chave, valor in kind.items() if valor} for kind in kinds],
        ensure_ascii=False,
        separators=(",", ":"),
    )
from django.core.exceptions import ObjectDoesNotExist
from core.presenters.text import join_non_empty
from core.utils.masks import format_protocolo
from .forms import PrestacaoSolicitacaoForm
from .models import PrestacaoDocumentoAnexo
from .services import diaria_recebida_display
from viagens_cadastros.models import ConfiguracaoSistema
from documentos.services.formatters import format_currency_br


def get_configuracao_sistema():
    return ConfiguracaoSistema.get_singleton()


def _temporal_badge_oficio(oficio):
    return "", ""


def _format_brl_diarias(valor):
    return format_currency_br(valor)


def _format_dt_trecho(dt):
    return timezone.localtime(dt).strftime("%d/%m/%Y %H:%M") if dt else "—"


def _label_cidade_uf_trecho(cidade):
    """"CURITIBA/PR", como os trechos do cartão da origem."""
    if not cidade:
        return "—"
    sigla = cidade.estado.sigla if getattr(cidade, "estado_id", None) else ""
    return f"{str(cidade).upper()}/{sigla}" if sigla else str(cidade).upper()


def _whatsapp_phone(servidor):
    """Telefone com DDI 55, só quando tem os 11 dígitos (DDD + celular); senão vazio."""
    telefone = (getattr(servidor, "telefone", "") or "").strip()
    return f"55{telefone}" if len(telefone) == 11 and telefone.isdigit() else ""

def _servidor_row(ps, solicitacao_form=None, prestacao_anexos=None, diario_pdf_url=""):
    """Dados de um servidor no card: identificação + solicitação inline + status."""
    servidor = ps.servidor
    cargo_nome = servidor.cargo.nome if servidor.cargo_id and servidor.cargo else ""
    unidade_nome = str(servidor.unidade) if servidor.unidade_id else ""

    anexos = list(ps.documentos_anexos.all())
    comprovante_ok = any(
        anexo.tipo == PrestacaoDocumentoAnexo.TIPO_COMPROVANTE
        for anexo in anexos
    )

    if solicitacao_form is None:
        solicitacao_form = PrestacaoSolicitacaoForm(instance=ps, prefix=f"ps-{ps.pk}")

    row = {
        "ps_pk": ps.pk,
        "name": servidor.nome,
        "cargo": cargo_nome,
        "unidade": unidade_nome,
        "meta": join_non_empty([cargo_nome, unidade_nome]),
        "is_motorista": ps.is_motorista,
        "numero_solicitacao": ps.numero_solicitacao,
        "data_liberacao_diarias": (
            ps.data_liberacao_diarias.isoformat() if ps.data_liberacao_diarias else ""
        ),
        "prazo_limite_saque": ps.prazo_limite_saque.isoformat() if ps.prazo_limite_saque else "",
        "solicitacao_form": solicitacao_form,
        "solicitacao_autosave_url": reverse(
            "viagens_prestacoes:prestacao_servidor_solicitacao_autosave", args=[ps.pk]
        ),
        "comprovante_ok": comprovante_ok,
        "pacote_url": reverse("viagens_prestacoes:consolidado_download", args=[ps.pk]),
        "rt_download_url": reverse(
            "viagens_prestacoes:rt_download_servidor_formato", args=[ps.pk, "pdf"]
        ),
        "diario_pdf_url": diario_pdf_url,
        "whatsapp_phone": _whatsapp_phone(servidor),
        "whatsapp_diaria_override": diaria_recebida_display(ps),
    }
    row["rt_assinado"] = _anexo_assinado_info(
        anexos,
        tipo=PrestacaoDocumentoAnexo.TIPO_RT_ASSINADO,
        anexar_url=reverse(
            "viagens_prestacoes:prestacao_servidor_assinado_anexar",
            args=[ps.pk, PrestacaoDocumentoAnexo.TIPO_RT_ASSINADO],
        ),
        prestacao_pk=ps.prestacao_id,
    )
    row["comprovante_anexo"] = _anexo_assinado_info(
        anexos,
        tipo=PrestacaoDocumentoAnexo.TIPO_COMPROVANTE,
        anexar_url=reverse(
            "viagens_prestacoes:prestacao_servidor_assinado_anexar",
            args=[ps.pk, PrestacaoDocumentoAnexo.TIPO_COMPROVANTE],
        ),
        prestacao_pk=ps.prestacao_id,
    )
    row["diario_assinado"] = _anexo_assinado_info(
        prestacao_anexos or [],
        tipo=PrestacaoDocumentoAnexo.TIPO_DB_ASSINADO,
        anexar_url=reverse(
            "viagens_prestacoes:prestacao_servidor_assinado_anexar",
            args=[ps.pk, PrestacaoDocumentoAnexo.TIPO_DB_ASSINADO],
        ),
        prestacao_pk=ps.prestacao_id,
    )
    return row

def apresentar_prestacao_servidor_card(
    ps, *, group_position="alone", solicitacao_form=None, configuracao=None,
    menus_sob_demanda=True,
):
    """Monta o card de um único servidor, com cabeçalho do ofício compartilhado.

    ``group_position``: ``alone`` | ``start`` | ``middle`` | ``end`` — usado para
    agrupar visualmente cards consecutivos do mesmo ofício.
    """
    menus_src = ""

    prestacao = ps.prestacao
    oficio = prestacao.oficio
    prestacao_anexos = list(prestacao.documentos_anexos.all())

    diario = None
    try:
        diario = prestacao.diario_bordo
    except ObjectDoesNotExist:
        diario = None
    diario_pdf_url = (
        reverse("viagens_prestacoes:diario_download_formato", args=[diario.pk, "pdf"])
        if diario is not None
        else ""
    )

    servidor = _servidor_row(
        ps,
        solicitacao_form,
        prestacao_anexos,
        diario_pdf_url=diario_pdf_url,
    )

    data_criacao_display = ""
    if oficio.data_criacao:
        try:
            data_criacao_display = oficio.data_criacao.strftime("%d/%m/%Y")
        except (AttributeError, TypeError, ValueError):
            data_criacao_display = ""

    destino_display = _destino_display_oficio(oficio)
    data_evento_display = _data_evento_display_oficio(oficio)
    temporal_label, temporal_tone = _temporal_badge_oficio(oficio)

    veiculo_placa = ""
    veiculo_modelo = ""
    if oficio.viatura_id:
        v = oficio.viatura
        veiculo_placa = v.placa_formatada
        veiculo_modelo = (v.modelo or "").strip()
    elif (oficio.transporte_placa_manual or "").strip():
        from core.utils.masks import format_placa

        veiculo_placa = format_placa(oficio.transporte_placa_manual)
        veiculo_modelo = (oficio.transporte_modelo_manual or "").strip()

    trechos_display = []
    valor_diarias_display = ""
    valor_diarias_extenso = ""
    quantidade_diarias_display = ""
    if oficio.roteiro_id:
        roteiro = oficio.roteiro
        for t in roteiro.trechos.all():
            orig = _label_cidade_uf_trecho(t.origem_municipio)
            dest = _label_cidade_uf_trecho(t.destino_municipio)
            trechos_display.append({
                "rota": f"{orig} → {dest}",
                "saida": _format_dt_trecho(t.saida_dt),
                "chegada": _format_dt_trecho(t.chegada_dt),
            })
        if roteiro.valor_diarias:
            valor_diarias_display = _format_brl_diarias(roteiro.valor_diarias / roteiro.quantidade_servidores)
            valor_diarias_extenso = (roteiro.valor_diarias_extenso or "").strip()
        quantidade_diarias_display = (roteiro.resumo_diarias or "").strip()

    # `NOVO-08`: era uma consulta por card. A configuração é por área e a área
    # é fixa no request, então os 20 cards da página resolviam sempre o mesmo
    # objeto. O `None` mantém os demais chamadores (e `tests.py:290`) de pé.
    if configuracao is None:
        configuracao = get_configuracao_sistema()
    unidade_sede_display = configuracao.unidade.nome if configuracao.unidade_id else ""
    if destino_display and data_evento_display:
        evento_wa_display = f"{destino_display}, de {data_evento_display}"
    else:
        evento_wa_display = destino_display or data_evento_display

    servidor["whatsapp_oficio"] = oficio.numero_formatado
    servidor["whatsapp_unidade"] = unidade_sede_display
    servidor["whatsapp_evento"] = evento_wa_display
    servidor["whatsapp_diaria"] = servidor.pop("whatsapp_diaria_override") or valor_diarias_display

    rt = None
    try:
        rt = prestacao.relatorio_tecnico
    except ObjectDoesNotExist:
        rt = None

    despacho_assinado = _anexo_assinado_info(
        prestacao_anexos,
        tipo=PrestacaoDocumentoAnexo.TIPO_DESPACHO,
        anexar_url=reverse(
            "viagens_prestacoes:prestacao_despacho_assinado_anexar",
            args=[prestacao.pk],
        ),
        prestacao_pk=prestacao.pk,
    )
    oficio_assinado = _anexo_assinado_info(
        prestacao_anexos,
        tipo=PrestacaoDocumentoAnexo.TIPO_OFICIO_ASSINADO,
        anexar_url=reverse(
            "viagens_prestacoes:prestacao_oficio_assinado_anexar",
            args=[prestacao.pk],
        ),
        prestacao_pk=prestacao.pk,
    )
    attach_kinds = kinds_de_anexo_assinado(
        [
            (
                "oficio",
                "Ofício assinado",
                f"o ofício assinado {oficio.numero_formatado}",
                oficio_assinado,
            ),
            (
                "despacho",
                "Despacho",
                f"o despacho do ofício {oficio.numero_formatado}",
                despacho_assinado,
            ),
            (
                "diario",
                "Diário de bordo",
                f"o diário de bordo do ofício {oficio.numero_formatado}",
                servidor["diario_assinado"],
            ),
            (
                "rt",
                "Relatório técnico",
                f"o relatório técnico de {servidor['name']}",
                servidor["rt_assinado"],
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

    protocolo_display = format_protocolo(oficio.protocolo) or ""
    header_value = " · ".join(
        p
        for p in [oficio.numero_formatado, protocolo_display, destino_display, data_evento_display]
        if p
    )
    equipe_count = len(list(prestacao.servidores_prestacao.all()))

    return {
        "ps_pk": ps.pk,
        "prestacao_pk": prestacao.pk,
        "group_position": group_position,
        "group_class": f"prestacao-card-group--{group_position}" if group_position != "alone" else "",
        "status_variant": ps.status or "outro",
        "ps": ps,
        "numero_display": oficio.numero_formatado,
        # A ação única do card reúne documentos compartilhados pelo ofício e
        # documentos próprios deste servidor, na ordem exibida pelo modal.
        "attach_kinds_json": kinds_de_anexo_assinado_json(attach_kinds),
        "tem_documento_assinado": any(kind["current_name"] for kind in attach_kinds),
        "protocolo_display": protocolo_display,
        "destino_display": destino_display,
        "data_evento_display": data_evento_display,
        "data_criacao_display": data_criacao_display,
        "temporal_label": temporal_label,
        "temporal_tone": temporal_tone,
        "status_label": ps.status_display,
        "status_tone": ps.status_variant,
        "status_value": ps.status,
        "arquivada": ps.arquivada,
        "finalizada": ps.finalizada,
        "arquivar_url": reverse("viagens_prestacoes:prestacao_servidor_arquivar", args=[ps.pk]),
        "finalizar_url": reverse("viagens_prestacoes:prestacao_servidor_finalizar", args=[ps.pk]),
        "downloads_url": reverse("viagens_prestacoes:prestacao_downloads", args=[ps.pk]),
        # Os gatilhos de menu do `_prestacao_card_body.html` apontam para cá (PF-04).
        "menus_url": menus_src,
        "servidores": [servidor],
        "servidores_count": 1,
        "equipe_count": equipe_count,
        "veiculo_placa": veiculo_placa,
        "veiculo_modelo": veiculo_modelo,
        "trechos": trechos_display,
        "valor_diarias_display": valor_diarias_display,
        "valor_diarias_extenso": valor_diarias_extenso,
        "quantidade_diarias_display": quantidade_diarias_display,
        "resumo_diarias_display": quantidade_diarias_display,
        "documentos_url": reverse("viagens_prestacoes:documentos_servidor", args=[ps.pk]),
        "rt_url": reverse("viagens_prestacoes:rt_servidor", args=[ps.pk]),
        "tem_rt": rt is not None,
        "diario_url": reverse("viagens_prestacoes:diario_servidor", args=[ps.pk]),
        "consolidado_url": reverse("viagens_prestacoes:consolidado_servidor", args=[ps.pk]),
        "despacho_assinado": despacho_assinado,
        "search_text": " ".join(
            p for p in [oficio.numero_formatado, protocolo_display, servidor["name"], ps.numero_solicitacao] if p
        ),
    }

def apresentar_prestacao_card(prestacao, solicitacao_forms=None):
    """Compatibilidade: gera cards individuais para todos os servidores do ofício."""
    servidores = list(prestacao.servidores_prestacao.all())
    total = len(servidores)
    cards = []
    for index, ps in enumerate(servidores):
        if total <= 1:
            position = "alone"
        elif index == 0:
            position = "start"
        elif index == total - 1:
            position = "end"
        else:
            position = "middle"
        form = (solicitacao_forms or {}).get(ps.pk)
        cards.append(apresentar_prestacao_servidor_card(ps, group_position=position, solicitacao_form=form))
    return cards

def marcar_agrupamento_cards(cards):
    """Ajusta ``group_position`` em uma lista já ordenada de cards por servidor."""
    if not cards:
        return cards

    i = 0
    while i < len(cards):
        j = i + 1
        while j < len(cards) and cards[j]["prestacao_pk"] == cards[i]["prestacao_pk"]:
            j += 1
        tamanho = j - i
        for offset in range(tamanho):
            if tamanho == 1:
                position = "alone"
            elif offset == 0:
                position = "start"
            elif offset == tamanho - 1:
                position = "end"
            else:
                position = "middle"
            cards[i + offset]["group_position"] = position
            cards[i + offset]["group_class"] = (
                f"prestacao-card-group--{position}" if position != "alone" else ""
            )
        i = j
    return cards
