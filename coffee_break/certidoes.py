"""Certidões de regularidade dos fornecedores de coffee break.

Os portais emissores (Receita, Sefa-PR, prefeituras, TST e Caixa) exigem
CAPTCHA, então a emissão continua sendo feita por uma pessoa: o sistema
acompanha a validade de cada certidão, avisa antes de vencer, leva direto ao
portal certo com o CNPJ à mão e lê a validade do PDF enviado.
"""

import re
import unicodedata
from datetime import date, timedelta

from .models import CertidaoFornecedor, TipoCertidao

# Portais comuns a todos os fornecedores; o municipal é do cadastro do
# fornecedor (a prefeitura da sede).
PORTAIS = {
    TipoCertidao.FEDERAL: "https://servicos.receitafederal.gov.br/servico/certidoes/#/home/cnpj",
    TipoCertidao.ESTADUAL: "https://cdwfazenda.paas.pr.gov.br/cdwportal/certidao/automatica",
    TipoCertidao.TRABALHISTA: "https://cndt-certidao.tst.jus.br/gerarCertidao",
    TipoCertidao.FGTS: "https://consulta-crf.caixa.gov.br/consultacrf/pages/consultaEmpregador.jsf",
}

# A partir de quantos dias antes do vencimento a certidão aparece como "vencendo".
DIAS_AVISO = 15


def portal(fornecedor, tipo):
    if tipo == TipoCertidao.MUNICIPAL:
        return fornecedor.url_certidao_municipal
    return PORTAIS.get(tipo, "")


def vigentes(fornecedor):
    """A certidão de maior validade de cada tipo (vencida ou não)."""
    atuais = {}
    for certidao in fornecedor.certidoes.order_by("tipo", "-validade", "-criado_em"):
        atuais.setdefault(certidao.tipo, certidao)
    return atuais


def quadro(fornecedor, hoje=None):
    """Uma linha por tipo de certidão, com a situação e o portal de emissão."""
    hoje = hoje or date.today()
    atuais = vigentes(fornecedor)
    linhas = []
    for tipo, rotulo in TipoCertidao.choices:
        certidao = atuais.get(tipo)
        if certidao is None:
            situacao, dias = "faltando", None
        else:
            dias = (certidao.validade - hoje).days
            if dias < 0:
                situacao = "vencida"
            elif dias <= DIAS_AVISO:
                situacao = "vencendo"
            else:
                situacao = "vigente"
        linhas.append(
            {
                "tipo": tipo,
                "rotulo": rotulo,
                "certidao": certidao,
                "situacao": situacao,
                "dias": dias,
                "portal": portal(fornecedor, tipo),
            }
        )
    return linhas


def pendencias(fornecedor, hoje=None):
    """Mensagens das certidões que impedem o protocolo (faltando ou vencidas)."""
    mensagens = []
    for linha in quadro(fornecedor, hoje):
        if linha["situacao"] == "faltando":
            mensagens.append(f"Certidão {linha['rotulo']} não cadastrada.")
        elif linha["situacao"] == "vencida":
            mensagens.append(
                f"Certidão {linha['rotulo']} vencida em {linha['certidao'].validade:%d/%m/%Y}."
            )
    return mensagens


def fornecedores_com_alerta(fornecedores, hoje=None):
    """[(fornecedor, [linhas vencidas/vencendo/faltando])] para o painel."""
    resultado = []
    for fornecedor in fornecedores:
        alertas = [l for l in quadro(fornecedor, hoje) if l["situacao"] != "vigente"]
        if alertas:
            resultado.append((fornecedor, alertas))
    return resultado


# ---------------------------------------------------------------------------
# Leitura da validade no PDF
# ---------------------------------------------------------------------------

_DATA = r"(\d{2})/(\d{2})/(\d{4})"
# "Válida até 17/03/2027", "Validade: 16/03/2027 - 180 dias",
# "Validade:14/09/2026 a 13/10/2026" (FGTS: vale o fim do intervalo).
_VALIDADE = re.compile(
    r"(?:valid[ao]|validade)[^0-9]{0,40}?" + _DATA + r"(?:\s*(?:a|ate)\s*" + _DATA + r")?"
)
# "válida por 90 dias" ... "emitida em 01/09/2026" — prefeituras.
_PRAZO = re.compile(r"(?:valid[ao]|validade)\D{0,30}?(\d{1,3})\s*(?:\([^)]*\)\s*)?dias")
_EMISSAO = re.compile(r"(?:emitid[ao]|emissao|expedid[ao]|expedicao)[^0-9]{0,40}?" + _DATA)


def _sem_acentos(texto):
    texto = unicodedata.normalize("NFKD", texto)
    return "".join(c for c in texto if not unicodedata.combining(c)).lower()


def _data(d, m, a):
    try:
        return date(int(a), int(m), int(d))
    except ValueError:
        return None


def validade_do_texto(texto):
    """A validade escrita na certidão, ou None quando não dá para saber."""
    texto = re.sub(r"\s+", " ", _sem_acentos(texto or ""))
    candidatas = []
    for achado in _VALIDADE.finditer(texto):
        grupos = achado.groups()
        fim = _data(*grupos[3:6]) if grupos[3] else None
        candidatas.append(fim or _data(*grupos[0:3]))
    candidatas = [c for c in candidatas if c]
    if candidatas:
        return max(candidatas)
    prazo = _PRAZO.search(texto)
    emissao = _EMISSAO.search(texto)
    if prazo and emissao:
        inicio = _data(*emissao.groups())
        if inicio:
            return inicio + timedelta(days=int(prazo.group(1)))
    return None


# O que identifica cada certidão no texto (sem acentos, minúsculo).
MARCAS = {
    TipoCertidao.FEDERAL: ("receita federal", "divida ativa da uniao", "tributos federais"),
    TipoCertidao.ESTADUAL: ("receita estadual", "divida ativa estadual", "secretaria de estado da fazenda"),
    TipoCertidao.MUNICIPAL: ("municip", "prefeitura", "cnd-cidadao"),
    TipoCertidao.TRABALHISTA: ("debitos trabalhistas", "cndt"),
    TipoCertidao.FGTS: ("fgts", "regularidade do empregador"),
}


def texto_do_pdf(arquivo, paginas=3):
    """O texto das primeiras páginas do PDF ("" se for imagem ou não abrir)."""
    from pypdf import PdfReader

    posicao = arquivo.tell() if hasattr(arquivo, "tell") else 0
    try:
        arquivo.seek(0)
        leitor = PdfReader(arquivo)
        return "\n".join((pagina.extract_text() or "") for pagina in leitor.pages[:paginas])
    except Exception:
        return ""
    finally:
        arquivo.seek(posicao)


def tipo_do_texto(texto):
    """Os tipos de certidão cujas marcas aparecem no texto."""
    limpo = _sem_acentos(texto)
    return [tipo for tipo, marcas in MARCAS.items() if any(marca in limpo for marca in marcas)]


def conferir(fornecedor, tipo, arquivo, validade_informada=None):
    """Confere a certidão enviada e diz até quando vale.

    Com texto no PDF: tem de ser do tipo pedido e do CNPJ do fornecedor, e a
    validade sai do próprio documento. PDF só de imagem (um print da página
    da prefeitura, por exemplo) não dá para conferir: vale a data informada.
    Devolve (validade, aviso); erro vira ValidationError com o motivo.
    """
    from django.core.exceptions import ValidationError

    rotulos = dict(TipoCertidao.choices)
    texto = texto_do_pdf(arquivo)
    # Sem o texto da certidão (só imagem, às vezes com o carimbo do protocolo por cima).
    if not re.search(r"\bcertid[aã]o\b|\bcertifica", _sem_acentos(texto).replace("ã", "a")):
        if validade_informada:
            return validade_informada, "O PDF é uma imagem: não deu para conferir o conteúdo; vale a data informada."
        raise ValidationError(
            "Não deu para ler este PDF (parece uma imagem). Anexe de novo informando até quando ele é válido."
        )
    tipos = tipo_do_texto(texto)
    if tipo not in tipos:
        if tipos:
            raise ValidationError(
                f"Este PDF parece ser a certidão {rotulos[tipos[0]]}, não a {rotulos[tipo]}."
            )
        raise ValidationError(f"Este PDF não parece ser a certidão {rotulos[tipo]}.")
    cnpj = re.sub(r"\D", "", fornecedor.cnpj or "")
    if cnpj:
        numeros = {re.sub(r"\D", "", achado) for achado in re.findall(r"\d{2}\.?\d{3}\.?\d{3}(?:/?\d{4}-?\d{2})?", texto)}
        if cnpj not in numeros and cnpj[:8] not in numeros:
            raise ValidationError(
                f"Esta certidão não é de {fornecedor.razao_social}: o CNPJ {fornecedor.cnpj_formatado} não aparece nela."
            )
    validade = validade_do_texto(texto) or validade_informada
    if validade is None:
        raise ValidationError("Não achei a validade nesta certidão. Anexe de novo informando até quando ela é válida.")
    return validade, ""


def validade_do_pdf(arquivo):
    """Lê o texto do PDF enviado e procura a validade."""
    from pypdf import PdfReader

    posicao = arquivo.tell() if hasattr(arquivo, "tell") else 0
    try:
        arquivo.seek(0)
        leitor = PdfReader(arquivo)
        texto = "\n".join((pagina.extract_text() or "") for pagina in leitor.pages[:3])
    except Exception:
        return None
    finally:
        arquivo.seek(posicao)
    return validade_do_texto(texto)


def registrar(fornecedor, tipo, arquivo, validade, usuario=None):
    return CertidaoFornecedor.objects.create(
        fornecedor=fornecedor,
        tipo=tipo,
        arquivo=arquivo,
        validade=validade,
        enviada_por=usuario,
    )
