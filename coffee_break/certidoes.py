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
