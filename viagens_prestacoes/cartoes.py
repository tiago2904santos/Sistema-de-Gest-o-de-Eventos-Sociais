"""O cartão da lista de prestações — Meta 6 de paridade com a origem.

A origem (`prestacoes_contas/index`) mostra um cartão por servidor, com o
cabeçalho do ofício, o selo da situação, a linha do servidor (número da
solicitação editável, período das diárias, motorista, comprovante, cargo e
unidade, aviso por WhatsApp), placa e modelo, os trechos, o valor total por
extenso, a quantidade de diárias e os comandos: abrir na etapa 1, escolher
documentos para baixar, anexar documentos assinados, finalizar e arquivar.

`apresentar_prestacao_servidor_card` (presenters.py) já monta quase tudo; aqui
entram só o que a tela precisa por cima: os menus e o texto do WhatsApp.
"""

from datetime import date
from urllib.parse import quote

from django.urls import reverse

from .download_services import payload_downloads
from .presenters import _iniciais_nome_servidor, apresentar_prestacao_servidor_card, kinds_de_anexo_assinado

SITUACOES = [
    ("nao_liberadas", "Não liberadas"),
    ("liberadas", "Liberadas"),
    ("arquivados", "Arquivados"),
    ("finalizados", "Finalizados"),
]

TITULOS_DOWNLOAD = {"oficio": "Ofício", "despacho": "Despacho", "diario": "Diário de bordo", "rt": "Relatório técnico", "comprovante": "Comprovante"}


def _data_br(iso):
    if not iso:
        return ""
    return date.fromisoformat(iso).strftime("%d/%m/%Y")


def periodo_das_diarias(servidor):
    """"10/08 → 24/08/2026" como a origem; vazio quando nada foi definido."""
    inicio, fim = servidor["data_liberacao_diarias"], servidor["prazo_limite_saque"]
    if not inicio and not fim:
        return ""
    if inicio and fim:
        return f"{date.fromisoformat(inicio):%d/%m} → {date.fromisoformat(fim):%d/%m/%Y}"
    return f"{_data_br(inicio or fim)}"


def mensagem_whatsapp(servidor, card):
    """O aviso de liberação das diárias que a origem manda pelo WhatsApp."""
    partes = [f"Olá, {servidor['name']}!"]
    evento = servidor.get("whatsapp_evento") or ""
    partes.append(f"As diárias do ofício {servidor['whatsapp_oficio']}" + (f" ({evento})" if evento else "") + " foram liberadas.")
    if servidor.get("whatsapp_diaria"):
        partes.append(f"Valor: {servidor['whatsapp_diaria']}.")
    if servidor["data_liberacao_diarias"]:
        partes.append(f"Liberação em {_data_br(servidor['data_liberacao_diarias'])}.")
    if servidor["prazo_limite_saque"]:
        partes.append(f"Prazo para saque: {_data_br(servidor['prazo_limite_saque'])}.")
    if servidor.get("whatsapp_unidade"):
        partes.append(servidor["whatsapp_unidade"])
    return " ".join(partes)


def url_whatsapp(servidor, card):
    texto = quote(mensagem_whatsapp(servidor, card))
    telefone = servidor.get("whatsapp_phone") or ""
    return f"https://wa.me/{telefone}?text={texto}" if telefone else f"https://wa.me/?text={texto}"


def documentos_para_baixar(ps):
    """Os itens do menu "Escolher documentos para baixar": original e assinado de cada documento."""
    itens = []
    for item in payload_downloads(ps)["itens"]:
        versoes = []
        for formato, url in item["versoes"].get("original", {}).items():
            versoes.append({"rotulo": f"Original · {formato.upper()}", "url": url, "formato": formato})
        for formato, url in item["versoes"].get("assinado", {}).items():
            versoes.append({"rotulo": f"Assinado · {formato.upper()}", "url": url, "formato": formato})
        itens.append({"id": item["id"], "titulo": item["titulo"], "subtitulo": item["subtitulo"], "versoes": versoes})
    return itens


def anexos_do_cartao(card):
    """Os cinco documentos assinados que o cartão da origem anexa direto."""
    import json
    return json.loads(card["attach_kinds_json"])


def titulo_do_cartao(oficio):
    """"161/2026 · 12.345.678-9 · ALMIRANTE TAMANDARÉ/PR, ANTONINA/PR · 25/08 a 30/08/2026", como a origem."""
    from core.utils.masks import format_protocolo
    from viagens_oficios.presenters import destinos_resumidos, periodo_curto
    from viagens_oficios.roteiro_context import periodo_roteiro
    roteiro = oficio.roteiro if oficio.roteiro_id else None
    saida, retorno = periodo_roteiro(roteiro) if roteiro else (None, None)
    partes = [oficio.numero_formatado, format_protocolo(oficio.protocolo) or "", destinos_resumidos(roteiro), periodo_curto(saida, retorno)]
    return " · ".join(p for p in partes if p)


def moeda(texto):
    """"R$ 1.452,75" — o formatador dos documentos não põe o espaço; a tela da origem põe."""
    return texto.replace("R$", "R$ ").replace("R$  ", "R$ ") if texto else texto


def cartao_da_lista(ps, *, configuracao=None):
    card = apresentar_prestacao_servidor_card(ps, configuracao=configuracao)
    card["titulo"] = titulo_do_cartao(ps.prestacao.oficio)
    card["valor_diarias_display"] = moeda(card["valor_diarias_display"])
    servidor = card["servidores"][0]
    servidor["iniciais"] = _iniciais_nome_servidor(servidor["name"])
    servidor["nome_liberacao"] = f"ps-{ps.pk}-data_liberacao_diarias"
    servidor["nome_prazo"] = f"ps-{ps.pk}-prazo_limite_saque"
    servidor["periodo"] = periodo_das_diarias(servidor)
    servidor["whatsapp_url"] = url_whatsapp(servidor, card)
    card["downloads"] = documentos_para_baixar(ps)
    card["anexos"] = anexos_do_cartao(card)
    card["rotulo_anexar"] = "Gerenciar documentos assinados" if card["tem_documento_assinado"] else "Anexar documentos assinados"
    return card
