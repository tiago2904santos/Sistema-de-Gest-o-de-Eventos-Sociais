"""Certificado da solicitação de coffee break: contexto e PDF.

A folha é a institucional de ``documentos`` — o mesmo brasão, cabeçalho e
rodapé ASCOM dos documentos de Viagens —, e o PDF nasce do HTML pelo
renderizador que já serve os outros tipos (``documentos.services.pdf_renderer``).

Nada é gravado: o certificado é recalculado do registro a cada pedido, para
nunca divergir do que a tela mostra. Por isso ele também não passa pela
façade documental (que existe para persistir artefato e versionar template) —
aqui basta o par ``renderizar_html`` + ``render_pdf``.
"""

from __future__ import annotations

from django.utils import timezone

TIPO = "coffee_break_certificado"


def _texto(valor) -> str:
    return str(valor or "").strip()


def _institucional() -> dict:
    """Cabeçalho e rodapé da folha, da configuração do setor de quem gera.

    A configuração é a mesma dos documentos de Viagens
    (``ConfiguracaoSistema.atual()``): o coffee break é da ASCOM e usa o
    papel timbrado da unidade, não um cabeçalho próprio.
    """
    from core.normalizers import normalize_upper
    from documentos.services.formatters import (
        format_document_display,
        format_institucional_rodape_linha,
    )
    from viagens_cadastros.selectors import build_configuracao_context

    inst = build_configuracao_context()
    cidade = _texto(inst.get("cidade_endereco"))
    return {
        # Caixa alta como nos demais cabeçalhos institucionais; o rodapé tem
        # regra própria (`format_institucional_rodape_linha`) e vem pronto.
        "nome_orgao": normalize_upper(_texto(inst.get("nome_orgao"))),
        # Só a unidade, sem cair para o órgão: o template já imprime o órgão na
        # linha de cima, e o atalho fazia o cabeçalho repetir o mesmo nome.
        "unidade_cabecalho": normalize_upper(_texto(inst.get("unidade"))),
        "unidade_rodape": format_institucional_rodape_linha(inst),
        "sede": format_document_display(cidade) if cidade else "",
    }


def _por_extenso(momento) -> str:
    """``21 de setembro de 2026, às 19:13``.

    Mês em minúscula, como nos demais documentos institucionais — o filtro
    ``date`` do Django capitaliza ("Setembro"), que não é a convenção. Os
    nomes dos meses vêm da localização, sem tabela duplicada aqui.
    """
    from django.utils.formats import date_format

    mes = date_format(momento, "F").lower()
    return f"{momento.day} de {mes} de {momento.year}, às {momento:%H:%M}"


def _marcos(solicitacao) -> list[dict]:
    """O fluxo financeiro em linha do tempo: cada marco e a data que o fechou.

    A ordem é a do fluxo real (NF → protocolo → atesto → OB → envio), a mesma
    que ``services.situacao_financeira`` lê para derivar a situação. Marco sem
    data é o que ainda falta — sai no certificado como pendente, porque o
    documento serve justamente para mostrar até onde o pedido chegou.
    """
    return [
        {"rotulo": "Nota fiscal", "valor": _texto(solicitacao.numero_nota_fiscal)},
        {"rotulo": "Protocolo de pagamento", "valor": _texto(solicitacao.protocolo_pagamento)},
        {"rotulo": "Atesto e envio ao GAF", "data": solicitacao.data_atesto_gaf},
        {"rotulo": "Ordem bancária emitida", "data": solicitacao.data_ordem_bancaria},
        {"rotulo": "Ordem bancária enviada à empresa", "data": solicitacao.data_envio_empresa},
    ]


def contexto(solicitacao, *, usuario=None, modo: str = "pdf") -> dict:
    """O que a folha recebe. ``modo`` é ``pdf`` ou ``editor`` (prévia A4)."""
    from documentos.services.document_context import imagens_para

    lote = solicitacao.lote
    contrato = lote.contrato
    fornecedor = contrato.fornecedor
    return {
        "modo": modo,
        "imagens": imagens_para(modo),
        "institucional": _institucional(),
        "cb": {
            "numero": solicitacao.numero or f"#{solicitacao.pk}",
            "situacao": solicitacao.situacao_financeira_display,
            "cancelada": solicitacao.cancelada,
            "motivo_cancelamento": _texto(solicitacao.motivo_cancelamento),
            "cancelada_em": solicitacao.cancelada_em,
            "data_solicitacao": solicitacao.data_solicitacao,
            "evento": _texto(solicitacao.descricao_evento),
            "periodo": solicitacao.periodo_evento_display,
            "quantidade": solicitacao.quantidade,
            "lote": lote.rotulo_curto,
            "exercicio": lote.exercicio,
            "empenho": _texto(lote.empenho),
            "municipios": _texto(lote.municipios_texto),
            "contrato": contrato.numero,
            "gms": _texto(contrato.numero_gms),
            "fiscal": _texto(contrato.fiscal_responsavel),
            "fornecedor": fornecedor.razao_social,
            "cnpj": fornecedor.cnpj_formatado,
            "marcos": _marcos(solicitacao),
            "observacoes": _texto(solicitacao.observacoes),
            "criado_por": _texto(solicitacao.criado_por),
            "emitido_extenso": _por_extenso(timezone.localtime()),
            "emitido_por": _texto(usuario) if usuario else "",
        },
    }


def nome_arquivo(solicitacao) -> str:
    """Nome do arquivo baixado.

    O número institucional é texto livre (``02/2026``): passa pelo mesmo
    saneamento dos demais documentos, que tira acento, barra e aspas — o que
    iria parar, sem filtro, dentro do cabeçalho ``Content-Disposition``.
    """
    from documentos.services.filenames import slugify_filename_part

    identificador = slugify_filename_part(solicitacao.numero or str(solicitacao.pk))
    return f"certificado-coffee-break-{identificador}.pdf"


def gerar_pdf(solicitacao, *, usuario=None) -> bytes:
    """PDF do certificado.

    Levanta ``DocumentRendererUnavailable`` quando o WeasyPrint não carrega
    (servidor sem o runtime GTK) — quem chama decide o que dizer na tela.
    """
    from documentos.services.pdf_renderer import render_pdf, renderizar_html

    html = renderizar_html(TIPO, contexto(solicitacao, usuario=usuario), modo="pdf")
    return render_pdf(html, tipo=TIPO)
