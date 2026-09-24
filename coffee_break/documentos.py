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


def juntar(itens):
    """"8952", "8952 e 8954", "8950, 8952 e 8954"."""
    itens = [str(i) for i in itens if str(i).strip()]
    if len(itens) <= 1:
        return "".join(itens)
    return ", ".join(itens[:-1]) + " e " + itens[-1]


def notas_do_pagamento(solicitacao):
    """Os números das notas de todas as OS do mesmo pagamento, na ordem da OS."""
    return [s.numero_nota_fiscal.strip() for s in solicitacao.grupo_pagamento() if s.numero_nota_fiscal.strip()]


def pendencias_oficio(solicitacao):
    faltas = []
    for membro in solicitacao.grupo_pagamento():
        if not membro.numero_nota_fiscal.strip():
            quem = f" da OS {membro.numero}" if membro.pk != solicitacao.pk else ""
            faltas.append(f"Informe o número da nota fiscal{quem}.")
    if not solicitacao.numero_oficio.strip():
        faltas.append("Informe o número do ofício.")
    return faltas


def itens_do_oficio(solicitacao):
    """Um item por OS do pagamento: "• <evento> - Coffee Break para N (extenso) pessoas."."""
    from viagens_roteiros.services.valor_extenso import _numero_por_extenso

    return [
        {"s": membro, "quantidade_extenso": _numero_por_extenso(membro.quantidade or 0)}
        for membro in solicitacao.grupo_pagamento()
    ]


def oficio_pdf(solicitacao):
    """Um ofício para todas as OS do mesmo pagamento (um item por evento e as
    notas no plural, como no Of. 123/2026 do processo 26.613.666-8)."""
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
    contexto["itens"] = itens_do_oficio(solicitacao)
    notas = notas_do_pagamento(solicitacao)
    contexto["notas"] = juntar(notas)
    contexto["varias_notas"] = len(notas) > 1
    # O texto do ofício é do pagamento: mora na OS principal.
    contexto["b"], contexto["quebras"] = textos_do_documento(TipoCoffee.OFICIO, solicitacao.principal_do_pagamento)
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
    # Uma nota e um certifico por OS do pagamento (ofício único), na ordem do
    # processo 26.613.666-8: NF 8952, certifico 8952, NF 8954, certifico 8954.
    grupo = solicitacao.grupo_pagamento()
    varias = len(grupo) > 1
    for membro in grupo:
        nf_m = membro.numero_nota_fiscal.strip()
        sufixo = f"-{membro.pk}" if varias else ""
        da_os = f" — OS {membro.numero}" if varias else ""
        faltas = []
        if not nf_m:
            faltas.append("Informe o número da nota fiscal.")
        if not membro.arquivo_nota_fiscal:
            faltas.append("Anexe o PDF da nota fiscal.")
        itens.append({
            "chave": f"nota{sufixo}",
            "titulo": f"Nota fiscal {nf_m}".strip() + da_os,
            "detalhe": "PDF enviado pelo fornecedor",
            "pronto": not faltas,
            "falta": " ".join(faltas),
            "url": _url("nota_fiscal", membro.pk),
            "url_corrigir": _url("etapa_nota", membro.pk),
            "arquivo": f"NF{nf_m} coffee break {fornecedor.nome_curto_efetivo}.pdf",
            "conteudo": (lambda m=membro: _ler(m.arquivo_nota_fiscal)),
        })
        itens.append({
            "chave": f"certifico{sufixo}",
            "titulo": ("Certifico digital" + (f" — NF {nf_m}" if varias and nf_m else "")) + (da_os if varias and not nf_m else ""),
            "detalhe": f"Atesto da fiscal {contrato.fiscal_responsavel}".strip(),
            "pronto": bool(nf_m),
            "falta": "" if nf_m else "Informe o número da nota fiscal.",
            "url": _url("certifico", membro.pk),
            "url_corrigir": _url("etapa_nota", membro.pk),
            "arquivo": f"CERTIFICO DIGITAL {fornecedor.nome_curto_efetivo} {nf_m}.pdf",
            "conteudo": (lambda m=membro: certifico_pdf(m)),
        })
    atuais = certidoes.vigentes(fornecedor)
    rotulos = dict(TipoCertidao.choices)
    for tipo in ORDEM_CERTIDOES:
        certidao = atuais.get(tipo)
        vencida = False
        if certidao is None:
            pronto, falta, detalhe = False, "Certidão não cadastrada.", "Não cadastrada"
        elif certidao.validade < hoje:
            # Vencida ainda entra no PDF único, mas com aviso: é para trocar.
            pronto, falta, vencida = False, f"Vencida em {certidao.validade:%d/%m/%Y}.", True
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
            "vencida": vencida,
            "disponivel": certidao is not None and bool(certidao.arquivo),
            "arquivo": f"Certidao {rotulos[tipo]} {fornecedor.nome_curto_efetivo}.pdf",
            "conteudo": (lambda c=certidao: _ler(c.arquivo)),
        })
    # Todos os termos aditivos, do mais antigo ao mais novo (não só o último).
    aditivos = list(contrato.aditivos.order_by("vigencia_inicio", "numero"))
    if aditivos:
        for aditivo in aditivos:
            tem = bool(aditivo.arquivo)
            itens.append({
                "chave": f"aditivo-{aditivo.pk}",
                "titulo": f"Termo aditivo {aditivo.numero}",
                "detalhe": (f"Vigência até {aditivo.vigencia_fim:%d/%m/%Y}" if aditivo.vigencia_fim else f"Do contrato {contrato.numero}"),
                "pronto": tem,
                "falta": "" if tem else "Anexe o PDF do termo aditivo em Cadastros › Contratos.",
                "url": _url("aditivo_arquivo", aditivo.pk) if tem else "",
                "url_corrigir": _url("cadastro_lista", "contratos"),
                "arquivo": f"Termo aditivo {aditivo.numero.replace('/', '-')} {fornecedor.nome_curto_efetivo}.pdf",
                "conteudo": (lambda a=aditivo: _ler(a.arquivo)),
            })
    elif contrato.termo_aditivo:
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
        # Disponível: tem arquivo para mostrar e juntar (pronto, ou certidão vencida).
        item.setdefault("disponivel", item["pronto"])
        item.setdefault("vencida", False)
        item["arquivo"] = f"{posicao:02d} - {item['arquivo'].replace('/', '-')}"
    return itens


def pendencias_pacote(solicitacao, hoje=None):
    """Tudo que falta para montar o anexo do protocolo; vazio = pronto."""
    return [
        f"{item['titulo']}: {item['falta']}"
        for item in itens_anexo(solicitacao, hoje)
        if not item["pronto"]
    ]


def avisos_do_pacote(itens):
    """O que a tela avisa sobre o PDF único: certidão vencida (entra, mas é
    para trocar) e documento que falta (fica de fora)."""
    vencidas = [f"{item['titulo']}: {item['falta']}" for item in itens if item["vencida"]]
    faltando = [f"{item['titulo']}: {item['falta']}" for item in itens if not item["disponivel"]]
    return {"vencidas": vencidas, "faltando": faltando}


# Os quatro arquivos da etapa 3, como vão ao protocolo.
PARTES = ("os", "oficio", "notas", "contratos")


def partes_do_anexo(solicitacao, hoje=None):
    """Os quatro arquivos para baixar: a OS (de todas as OS do pagamento), o
    ofício, as notas com os certificos (nota, certifico, nota, certifico...) e
    os contratos com todos os aditivos e as certidões."""
    itens = itens_anexo(solicitacao, hoje)
    grupo = solicitacao.grupo_pagamento()
    os_itens = []
    for membro in grupo:
        faltas = pendencias_ordem_servico(membro)
        os_itens.append({
            "chave": f"os-{membro.pk}",
            "titulo": f"Ordem de serviço {membro.numero}",
            "pronto": not faltas,
            "disponivel": not faltas,
            "vencida": False,
            "falta": " ".join(faltas),
            "conteudo": (lambda m=membro: ordem_servico_pdf(m)),
        })
    notas = [i for i in itens if i["chave"].startswith(("nota", "certifico"))]
    contratos = [i for i in itens if i["chave"].startswith(("contrato", "aditivo"))]
    # Contrato primeiro, depois os aditivos, depois as certidões.
    contratos.sort(key=lambda i: 0 if i["chave"] == "contrato" else 1)
    contratos += [i for i in itens if i["chave"].startswith("certidao")]
    partes = [
        ("os", "Ordem de serviço" if len(grupo) == 1 else "Ordens de serviço", os_itens),
        ("oficio", "Ofício", [i for i in itens if i["chave"] == "oficio"]),
        ("notas", "Notas fiscais e certificos", notas),
        ("contratos", "Contrato, aditivos e certidões", contratos),
    ]
    saida = []
    for chave, titulo, lista in partes:
        faltando = [i for i in lista if not i["disponivel"]]
        saida.append({
            "chave": chave,
            "titulo": titulo,
            "itens": lista,
            "disponivel": any(i["disponivel"] for i in lista),
            "pronto": bool(lista) and all(i["pronto"] for i in lista),
            "vencida": any(i["vencida"] for i in lista),
            "faltando": len(faltando),
            "conteudo_texto": ", ".join(i["titulo"] for i in lista),
        })
    return saida


def parte_pdf(solicitacao, chave, hoje=None):
    """Um dos quatro arquivos: os documentos dele que existem, num PDF só."""
    from pypdf import PdfWriter

    if chave not in PARTES:
        raise ValidationError(["Arquivo desconhecido."])
    parte = next(p for p in partes_do_anexo(solicitacao, hoje) if p["chave"] == chave)
    disponiveis = [i for i in parte["itens"] if i["disponivel"]]
    if not disponiveis:
        raise ValidationError([f"{parte['titulo']}: nenhum documento disponível ainda."])
    escritor = PdfWriter()
    for item in disponiveis:
        _anexar(escritor, item["conteudo"]())
    saida = io.BytesIO()
    escritor.write(saida)
    return saida.getvalue()


def _disponiveis(solicitacao, hoje):
    itens = [item for item in itens_anexo(solicitacao, hoje) if item["disponivel"]]
    if not itens:
        raise ValidationError(["Nenhum documento do anexo está disponível ainda."])
    return itens


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
    """O anexo completo num PDF só, na ordem em que vai ao protocolo: todos os
    documentos que existem, com as certidões (as vencidas também)."""
    from pypdf import PdfWriter

    # Junta tudo o que existe, na ordem do protocolo — certidão vencida
    # inclusive; a tela avisa o que está vencido e o que ficou de fora.
    escritor = PdfWriter()
    for item in _disponiveis(solicitacao, hoje):
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

    saida = io.BytesIO()
    with zipfile.ZipFile(saida, "w", zipfile.ZIP_DEFLATED) as pacote:
        for item in _disponiveis(solicitacao, hoje):
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
    notas = notas_do_pagamento(solicitacao)
    nf = juntar(notas) or "____"
    if len(notas) > 1:
        # Várias notas no mesmo protocolo, como o 26.613.666-8.
        detalhamento = f"ENVIO P/ PAGAMENTO DAS NOTAS FISCAIS N {nf.replace(' e ', ' E ')} - ({fornecedor.nome_curto_efetivo})"
        pagamento = f"o pagamento das Notas fiscais n° {nf}."
    else:
        detalhamento = f"ENVIO P/ PAGAMENTO DA NOTA FISCAL N {nf} - ({fornecedor.nome_curto_efetivo})"
        pagamento = f"o pagamento da Nota fiscal n° {nf}."
    contrato = solicitacao.lote.contrato
    assunto_despacho = f"CONTRATO {contrato.numero}"
    if contrato.numero_gms:
        assunto_despacho += f" - GMS {contrato.numero_gms}"
    if contrato.termo_aditivo:
        assunto_despacho += f" - TERMO ADITIVO No {contrato.termo_aditivo}"
    despacho = (
        f"{config.despacho_destino}\n"
        "Encaminhamos o presente protocolado com as devidas informações para "
        + pagamento
    )
    return {
        "detalhamento": detalhamento,
        "despacho": despacho,
        # O despacho como o do processo 26.613.666-8: assunto com o contrato
        # e o aditivo, o interessado e o texto.
        "despacho_campos": [
            {"rotulo": "Assunto do despacho", "valor": assunto_despacho, "copiar": assunto_despacho},
            {"rotulo": "Interessado", "valor": fornecedor.razao_social, "copiar": fornecedor.razao_social},
        ],
        "campos": [
            # O interessado em dois: o CNPJ e o nome, cada um com o seu copiar.
            {"rotulo": "CNPJ do interessado", "valor": fornecedor.cnpj_formatado or "—", "copiar": fornecedor.cnpj_formatado},
            {"rotulo": "Nome do interessado", "valor": fornecedor.razao_social, "copiar": fornecedor.razao_social},
            {"rotulo": "Assunto", "valor": config.eprotocolo_assunto, "copiar": config.eprotocolo_assunto},
            {"rotulo": "Palavras-chave", "valor": config.eprotocolo_palavras_chave, "copiar": config.eprotocolo_palavras_chave},
            {"rotulo": "Nº/Ano", "valor": solicitacao.numero_oficio or "—", "copiar": solicitacao.numero_oficio},
        ],
    }


def nome_arquivo(prefixo, solicitacao):
    numero = (solicitacao.numero or str(solicitacao.pk)).replace("/", "-")
    fornecedor = solicitacao.lote.contrato.fornecedor.razao_social.split()[0:4]
    return f"{prefixo} {numero} - Lote {solicitacao.lote.numero} - {' '.join(fornecedor)}.pdf"
