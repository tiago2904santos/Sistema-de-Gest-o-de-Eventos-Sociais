"""Documentos do Coffee Break: ordem de serviço, certifico e o pacote do
protocolo de pagamento.

OS e certifico saem de HTML pelo WeasyPrint, no papel timbrado da ASCOM. O
pacote junta, nesta ordem, o que vai anexado ao protocolo: nota fiscal,
certifico, contrato do lote, termo aditivo (se houver) e as cinco
certidões vigentes do fornecedor.
"""

import io
from pathlib import Path

from django.conf import settings
from django.core.exceptions import ValidationError
from django.template.loader import render_to_string

from . import certidoes
from .models import TipoCertidao

MESES = (
    "janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho",
    "agosto", "setembro", "outubro", "novembro", "dezembro",
)


def data_extenso(data):
    return f"{data.day} de {MESES[data.month - 1]} de {data.year}"


def _imagens():
    raiz = Path(settings.BASE_DIR) / "static" / "img"
    return {
        "brasao": (raiz / "brasao-pcpr.png").resolve().as_uri(),
        "marca": (raiz / "marca-pcpr.png").resolve().as_uri(),
    }


def _pdf(template, contexto):
    try:
        from weasyprint import HTML
    except OSError as exc:  # GTK/Pango ausentes
        raise ValidationError(
            "O gerador de PDF (WeasyPrint) não está disponível neste servidor."
        ) from exc
    html = render_to_string(template, {**contexto, "imagens": _imagens()})
    base = Path(settings.BASE_DIR).resolve().as_uri() + "/"
    return HTML(string=html, base_url=base).write_pdf(presentational_hints=False)


def _contexto(solicitacao):
    lote = solicitacao.lote
    return {
        "s": solicitacao,
        "lote": lote,
        "contrato": lote.contrato,
        "fornecedor": lote.contrato.fornecedor,
    }


def pendencias_ordem_servico(solicitacao):
    faltas = []
    if not solicitacao.numero:
        faltas.append("Informe o número da solicitação (é o número da OS).")
    if not solicitacao.local_entrega.strip():
        faltas.append("Informe o local de entrega.")
    if not solicitacao.responsavel_recebimento.strip():
        faltas.append("Informe o responsável pelo recebimento.")
    return faltas


def ordem_servico_pdf(solicitacao):
    faltas = pendencias_ordem_servico(solicitacao)
    if faltas:
        raise ValidationError(faltas)
    contexto = _contexto(solicitacao)
    contexto["data_extenso"] = data_extenso(solicitacao.data_solicitacao)
    return _pdf("coffee_break/documentos/ordem_servico.html", contexto)


def certifico_pdf(solicitacao):
    if not solicitacao.numero_nota_fiscal.strip():
        raise ValidationError(["Informe o número da nota fiscal antes do certifico."])
    return _pdf("coffee_break/documentos/certifico.html", _contexto(solicitacao))


def pendencias_pacote(solicitacao, hoje=None):
    """Tudo que falta para montar o pacote do protocolo; vazio = pronto."""
    contrato = solicitacao.lote.contrato
    faltas = []
    if not solicitacao.numero_nota_fiscal.strip():
        faltas.append("Informe o número da nota fiscal.")
    if not solicitacao.arquivo_nota_fiscal:
        faltas.append("Anexe o PDF da nota fiscal.")
    if not contrato.arquivo_contrato:
        faltas.append(f"Anexe o PDF do contrato {contrato.numero} no cadastro do contrato.")
    if contrato.termo_aditivo and not contrato.arquivo_termo_aditivo:
        faltas.append(
            f"Anexe o PDF do termo aditivo {contrato.termo_aditivo} no cadastro do contrato."
        )
    faltas.extend(certidoes.pendencias(contrato.fornecedor, hoje))
    return faltas


def _anexar(escritor, origem):
    from pypdf import PdfReader

    if hasattr(origem, "open"):
        origem.open("rb")
        try:
            dados = origem.read()
        finally:
            origem.close()
    else:
        dados = origem
    escritor.append(PdfReader(io.BytesIO(dados)))


def pacote_protocolo_pdf(solicitacao, hoje=None):
    """Um PDF só, na ordem em que os documentos vão ao protocolo."""
    from pypdf import PdfWriter

    faltas = pendencias_pacote(solicitacao, hoje)
    if faltas:
        raise ValidationError(faltas)
    contrato = solicitacao.lote.contrato
    atuais = certidoes.vigentes(contrato.fornecedor)
    escritor = PdfWriter()
    _anexar(escritor, solicitacao.arquivo_nota_fiscal)
    _anexar(escritor, certifico_pdf(solicitacao))
    _anexar(escritor, contrato.arquivo_contrato)
    if contrato.termo_aditivo and contrato.arquivo_termo_aditivo:
        _anexar(escritor, contrato.arquivo_termo_aditivo)
    for tipo in TipoCertidao.values:
        _anexar(escritor, atuais[tipo].arquivo)
    saida = io.BytesIO()
    escritor.write(saida)
    return saida.getvalue()


def nome_arquivo(prefixo, solicitacao):
    numero = (solicitacao.numero or str(solicitacao.pk)).replace("/", "-")
    fornecedor = solicitacao.lote.contrato.fornecedor.razao_social.split()[0:4]
    return f"{prefixo} {numero} - Lote {solicitacao.lote.numero} - {' '.join(fornecedor)}.pdf"
