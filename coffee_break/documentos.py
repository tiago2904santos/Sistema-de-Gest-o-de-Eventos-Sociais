"""Documentos do Coffee Break: ordem de serviço, ofício, certifico e o anexo
do protocolo de pagamento.

OS, ofício e certifico saem de HTML pelo WeasyPrint, no papel timbrado da
ASCOM. O anexo segue a ordem do processo 26.617.058-0: ofício, nota fiscal,
certifico, as cinco certidões (FGTS, trabalhista, municipal, estadual e
federal), termo aditivo (se houver) e contrato.
"""

import io
from pathlib import Path

from django.conf import settings
from django.core.exceptions import ValidationError
from django.template.loader import render_to_string
from django.utils import timezone

from . import certidoes
from .models import TipoCertidao

MESES = (
    "janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho",
    "agosto", "setembro", "outubro", "novembro", "dezembro",
)


def data_extenso(data):
    return f"{data.day} de {MESES[data.month - 1]} de {data.year}"


def data_extenso_oficio(data):
    """Como no ofício do processo: "21 de Setembro de 2026" (mês com maiúscula)."""
    return f"{data.day} de {MESES[data.month - 1].capitalize()} de {data.year}"


def _imagens():
    raiz = Path(settings.BASE_DIR) / "static" / "img"
    return {
        # Brasão e marca PCPR em alta, tirados do PDF do modelo da OS.
        "brasao": (raiz / "brasao-pcpr-timbre.png").resolve().as_uri(),
        "marca": (raiz / "marca-pcpr-timbre.png").resolve().as_uri(),
    }


def _imagens_web():
    """Os mesmos arquivos, pelo endereço estático (a tela não lê file://)."""
    from django.templatetags.static import static

    return {
        "brasao": static("img/brasao-pcpr-timbre.png"),
        "marca": static("img/marca-pcpr-timbre.png"),
    }


def _previa(template, contexto):
    """A folha em HTML para o visualizador da tela: o mesmo modelo do PDF.

    Não depende de leitor de PDF no navegador (há os que não mostram PDF
    dentro de um quadro, como os de celular).
    """
    return render_to_string(template, {**contexto, "imagens": _imagens_web(), "previa": True})


def _contexto_os(solicitacao):
    """A OS com o que se editou no editor de documentos: os textos do modelo
    reescritos (`b`, por chave) e as quebras de página."""
    from .editor import TipoCoffee, textos_do_documento

    contexto = _contexto(solicitacao)
    contexto["data_extenso"] = data_extenso(solicitacao.data_solicitacao)
    contexto["b"], contexto["quebras"] = textos_do_documento(TipoCoffee.ORDEM_SERVICO, solicitacao)
    return contexto


def ordem_servico_previa(solicitacao):
    faltas = pendencias_ordem_servico(solicitacao)
    if faltas:
        raise ValidationError(faltas)
    return _previa("coffee_break/documentos/ordem_servico.html", _contexto_os(solicitacao))


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
    return _pdf("coffee_break/documentos/ordem_servico.html", _contexto_os(solicitacao))


def _sem_quebra(texto, trecho):
    """O texto escapado, com `trecho` numa linha só (o Writer não quebra na
    barra; o navegador quebraria)."""
    from django.utils.html import escape
    from django.utils.safestring import mark_safe

    return mark_safe(escape(texto).replace(escape(trecho), f'<span class="inteiro">{escape(trecho)}</span>'))


def pendencias_certifico(solicitacao):
    return [] if solicitacao.numero_nota_fiscal.strip() else ["Informe o número da nota fiscal."]


def certifico_pdf(solicitacao):
    from .editor import TipoCoffee, textos_do_documento

    if not solicitacao.numero_nota_fiscal.strip():
        raise ValidationError(["Informe o número da nota fiscal antes do certifico."])
    contexto = _contexto(solicitacao)
    contexto["b"], contexto["quebras"] = textos_do_documento(TipoCoffee.CERTIFICO, solicitacao)
    contexto["atesto_texto"] = _sem_quebra(contexto["b"]["cb_atesto_texto"], "executados/entregues")
    return _pdf("coffee_break/documentos/certifico.html", contexto)


def pendencias_oficio(solicitacao):
    faltas = []
    if not solicitacao.numero_nota_fiscal.strip():
        faltas.append("Informe o número da nota fiscal.")
    if not solicitacao.numero_oficio.strip():
        faltas.append("Informe o número do ofício.")
    return faltas


def oficio_pdf(solicitacao):
    from viagens_roteiros.services.valor_extenso import _numero_por_extenso

    from .editor import TipoCoffee, textos_do_documento
    from .models import ConfiguracaoCoffeeBreak

    faltas = pendencias_oficio(solicitacao)
    if faltas:
        raise ValidationError(faltas)
    contexto = _contexto(solicitacao)
    contexto["config"] = ConfiguracaoCoffeeBreak.atual()
    contexto["data_extenso"] = data_extenso_oficio(
        solicitacao.data_oficio or timezone.localdate()
    )
    contexto["quantidade_extenso"] = _numero_por_extenso(solicitacao.quantidade)
    contexto["b"], contexto["quebras"] = textos_do_documento(TipoCoffee.OFICIO, solicitacao)
    return _pdf("coffee_break/documentos/oficio.html", contexto)


# ---------------------------------------------------------------------------
# Anexo do protocolo de pagamento
# ---------------------------------------------------------------------------

# A ordem das certidões no processo: FGTS, trabalhista, municipal, estadual, federal.
ORDEM_CERTIDOES = (
    TipoCertidao.FGTS,
    TipoCertidao.TRABALHISTA,
    TipoCertidao.MUNICIPAL,
    TipoCertidao.ESTADUAL,
    TipoCertidao.FEDERAL,
)


def _url(nome, *args):
    from django.urls import reverse

    return reverse(f"coffee_break:{nome}", args=args)


def itens_anexo(solicitacao, hoje=None):
    """Os documentos do anexo, na ordem do protocolo.

    Cada item diz se está pronto e, quando não, o que falta — é a lista que a
    etapa 3 mostra e a mesma que monta o PDF e o ZIP. ``conteudo`` devolve os
    bytes do documento (só chamado quando ``pronto``).
    """
    hoje = hoje or timezone.localdate()
    contrato = solicitacao.lote.contrato
    fornecedor = contrato.fornecedor
    pk = solicitacao.pk
    nf = solicitacao.numero_nota_fiscal.strip()
    itens = []

    faltas = pendencias_oficio(solicitacao)
    itens.append({
        "chave": "oficio",
        "titulo": f"Ofício {solicitacao.numero_oficio}".strip(),
        "detalhe": "Gerado pelo sistema — encaminha a nota ao GAF",
        "pronto": not faltas,
        "falta": " ".join(faltas),
        "url": _url("oficio", pk),
        "arquivo": f"Of.{solicitacao.numero_oficio.split('/')[0]} coffee break {fornecedor.nome_curto_efetivo}.pdf",
        "conteudo": lambda: oficio_pdf(solicitacao),
    })
    faltas = []
    if not nf:
        faltas.append("Informe o número da nota fiscal.")
    if not solicitacao.arquivo_nota_fiscal:
        faltas.append("Anexe o PDF da nota fiscal.")
    itens.append({
        "chave": "nota",
        "titulo": f"Nota fiscal {nf}".strip(),
        "detalhe": "PDF enviado pelo fornecedor",
        "pronto": not faltas,
        "falta": " ".join(faltas),
        "url": _url("nota_fiscal", pk),
        "arquivo": f"NF{nf} coffee break {fornecedor.nome_curto_efetivo}.pdf",
        "conteudo": lambda: _ler(solicitacao.arquivo_nota_fiscal),
    })
    itens.append({
        "chave": "certifico",
        "titulo": "Certifico digital",
        "detalhe": f"Atesto da fiscal {contrato.fiscal_responsavel}".strip(),
        "pronto": bool(nf),
        "falta": "" if nf else "Informe o número da nota fiscal.",
        "url": _url("certifico", pk),
        "arquivo": f"CERTIFICO DIGITAL {fornecedor.nome_curto_efetivo} {nf}.pdf",
        "conteudo": lambda: certifico_pdf(solicitacao),
    })
    atuais = certidoes.vigentes(fornecedor)
    rotulos = dict(TipoCertidao.choices)
    for tipo in ORDEM_CERTIDOES:
        certidao = atuais.get(tipo)
        if certidao is None:
            pronto, falta, detalhe = False, "Certidão não cadastrada.", "Não cadastrada"
        elif certidao.validade < hoje:
            pronto, falta = False, f"Vencida em {certidao.validade:%d/%m/%Y}."
            detalhe = f"Vencida em {certidao.validade:%d/%m/%Y}"
        else:
            pronto, falta, detalhe = True, "", f"Válida até {certidao.validade:%d/%m/%Y}"
        itens.append({
            "chave": f"certidao-{tipo.lower()}",
            "titulo": f"Certidão {rotulos[tipo]}",
            "detalhe": detalhe,
            "pronto": pronto,
            "falta": falta,
            "url": _url("certidao_arquivo", certidao.pk) if certidao else "",
            "url_corrigir": _url("certidoes") + f"#fornecedor-{fornecedor.pk}",
            "arquivo": f"Certidao {rotulos[tipo]} {fornecedor.nome_curto_efetivo}.pdf",
            "conteudo": (lambda c=certidao: _ler(c.arquivo)),
        })
    if contrato.termo_aditivo:
        tem = bool(contrato.arquivo_termo_aditivo)
        itens.append({
            "chave": "aditivo",
            "titulo": f"Termo aditivo {contrato.termo_aditivo}",
            "detalhe": f"Do contrato {contrato.numero}",
            "pronto": tem,
            "falta": "" if tem else "Anexe o PDF no cadastro do contrato.",
            "url": _url("contrato_arquivo", contrato.pk, "arquivo_termo_aditivo") if tem else "",
            "url_corrigir": _url("cadastro_lista", "contratos") + f"?editar={contrato.pk}",
            "arquivo": f"Termo aditivo {contrato.termo_aditivo.replace('/', '-')} {fornecedor.nome_curto_efetivo}.pdf",
            "conteudo": lambda: _ler(contrato.arquivo_termo_aditivo),
        })
    tem = bool(contrato.arquivo_contrato)
    itens.append({
        "chave": "contrato",
        "titulo": f"Contrato {contrato.numero}",
        "detalhe": f"GMS {contrato.numero_gms}" if contrato.numero_gms else fornecedor.razao_social,
        "pronto": tem,
        "falta": "" if tem else "Anexe o PDF no cadastro do contrato.",
        "url": _url("contrato_arquivo", contrato.pk, "arquivo_contrato") if tem else "",
        "url_corrigir": _url("cadastro_lista", "contratos") + f"?editar={contrato.pk}",
        "arquivo": f"Contrato {contrato.numero.replace('/', '-')} {fornecedor.nome_curto_efetivo}.pdf",
        "conteudo": lambda: _ler(contrato.arquivo_contrato),
    })
    for posicao, item in enumerate(itens, start=1):
        item["posicao"] = posicao
        item["arquivo"] = f"{posicao:02d} - {item['arquivo'].replace('/', '-')}"
    return itens


def pendencias_pacote(solicitacao, hoje=None):
    """Tudo que falta para montar o anexo do protocolo; vazio = pronto."""
    return [
        f"{item['titulo']}: {item['falta']}"
        for item in itens_anexo(solicitacao, hoje)
        if not item["pronto"]
    ]


def _ler(origem):
    origem.open("rb")
    try:
        return origem.read()
    finally:
        origem.close()


def _anexar(escritor, dados):
    from pypdf import PdfReader

    escritor.append(PdfReader(io.BytesIO(dados)))


def pacote_protocolo_pdf(solicitacao, hoje=None):
    """O anexo completo num PDF só, na ordem em que vai ao protocolo."""
    from pypdf import PdfWriter

    faltas = pendencias_pacote(solicitacao, hoje)
    if faltas:
        raise ValidationError(faltas)
    escritor = PdfWriter()
    for item in itens_anexo(solicitacao, hoje):
        _anexar(escritor, item["conteudo"]())
    saida = io.BytesIO()
    escritor.write(saida)
    return saida.getvalue()


def pacote_protocolo_zip(solicitacao, hoje=None):
    """Os mesmos documentos, um arquivo cada, numerados na ordem do protocolo.

    O eProtocolo recebe um documento por vez (cada um é assinado à parte):
    o ZIP poupa baixar um por um.
    """
    import zipfile

    faltas = pendencias_pacote(solicitacao, hoje)
    if faltas:
        raise ValidationError(faltas)
    saida = io.BytesIO()
    with zipfile.ZipFile(saida, "w", zipfile.ZIP_DEFLATED) as pacote:
        for item in itens_anexo(solicitacao, hoje):
            pacote.writestr(item["arquivo"], item["conteudo"]())
    return saida.getvalue()


# ---------------------------------------------------------------------------
# Textos do eProtocolo
# ---------------------------------------------------------------------------

def textos_eprotocolo(solicitacao):
    """Os campos do cadastro do protocolo e o despacho, prontos para colar.

    Espelham a capa e o despacho do processo 26.617.058-0: "ENVIO P/
    PAGAMENTO DA NOTA FISCAL N 8957 - (FAVO E MEL)" e "Ao GAF, Encaminhamos
    o presente protocolado...".
    """
    from .models import ConfiguracaoCoffeeBreak

    config = ConfiguracaoCoffeeBreak.atual()
    fornecedor = solicitacao.lote.contrato.fornecedor
    nf = solicitacao.numero_nota_fiscal.strip() or "____"
    detalhamento = (
        f"ENVIO P/ PAGAMENTO DA NOTA FISCAL N {nf} - ({fornecedor.nome_curto_efetivo})"
    )
    despacho = (
        f"{config.despacho_destino}\n"
        "Encaminhamos o presente protocolado com as devidas informações para "
        f"o pagamento da Nota fiscal n° {nf}."
    )
    return {
        "detalhamento": detalhamento,
        "despacho": despacho,
        "campos": [
            {"rotulo": "Interessado", "valor": f"{fornecedor.cnpj_formatado} {fornecedor.razao_social}".strip(), "copiar": fornecedor.cnpj_formatado or fornecedor.razao_social},
            {"rotulo": "Assunto", "valor": config.eprotocolo_assunto, "copiar": config.eprotocolo_assunto},
            {"rotulo": "Palavras-chave", "valor": config.eprotocolo_palavras_chave, "copiar": config.eprotocolo_palavras_chave},
            {"rotulo": "Nº/Ano", "valor": solicitacao.numero_oficio or "—", "copiar": solicitacao.numero_oficio},
        ],
    }


def nome_arquivo(prefixo, solicitacao):
    numero = (solicitacao.numero or str(solicitacao.pk)).replace("/", "-")
    fornecedor = solicitacao.lote.contrato.fornecedor.razao_social.split()[0:4]
    return f"{prefixo} {numero} - Lote {solicitacao.lote.numero} - {' '.join(fornecedor)}.pdf"
