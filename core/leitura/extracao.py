"""Os dados de cada documento, tirados do texto.

`dados_do_documento(tipo, texto)` devolve um dicionário com o que achou;
chave ausente = não achou (nunca volta chave com None ou ""). Convenções:

- protocolo do eProtocolo: só os 9 dígitos ("266136668");
- CPF completo: 11 dígitos; CPF mascarado: `cpf_meio` (6 dígitos, `cpf[3:9]`)
  ou `cpf_pontas` (5 dígitos, `cpf[:3] + cpf[9:]`);
- valores: `Decimal`; datas: `date`; data com hora: `datetime` com fuso
  (horário de Brasília, como está no documento);
- nº de ofício, OS e plano: `int` (numero e ano separados); nº de nota
  fiscal, contrato e empenho: texto, como o sistema guarda.

Os textos de referência são os que o próprio sistema imprime (ofício, RT,
diário, termo, justificativa, OS, plano; Coffee Break) e os dos órgãos que
aparecem no processo de pagamento (DANFE, certidões, SIAFIC). Comprovantes
bancários seguem o que os bancos mais comuns escrevem (Caixa, BB, Itaú,
Bradesco, Santander, Nubank, Sicredi, Inter…): rótulos variam muito, então
cada campo tem vários rótulos e um plano B sem rótulo.
"""

from __future__ import annotations

import re
from datetime import date
from datetime import datetime
from datetime import timedelta
from decimal import Decimal

from core.utils.masks import normalize_placa

from . import classificacao as tipos
from .texto import achar_cnpjs
from .texto import achar_cpfs
from .texto import achar_cpfs_mascarados
from .texto import achar_datas
from .texto import achar_protocolos
from .texto import normalizar
from .texto import valor_de

__all__ = ["dados_do_documento", "data_hora"]

_VALOR = r"(\d{1,3}(?:\.\d{3})+,\d{2}|\d+,\d{2})"
_PROTO = r"(\d{2}\.?\d{3}\.?\d{3}\s?-\s?\d)"
_N = r"(?:N\s*[O°º.]*\s*:?\s*)?"  # "Nº", "N.º", "n°", "No" (normalizado: "NO")


def _linha_unica(texto: str) -> str:
    return " ".join(str(texto or "").split())


def _digitos(valor: str) -> str:
    return re.sub(r"\D", "", valor or "")


def _sem_zeros(numero: str) -> str:
    digitos = _digitos(numero)
    return str(int(digitos)) if digitos else ""


def data_hora(dia: str, hora: str = "") -> datetime | date | None:
    """"21/09/2026" + "10:03" → datetime com fuso (se o projeto usa fuso); só a data → date."""
    datas = achar_datas(dia)
    if not datas:
        return None
    if not hora:
        return datas[0]
    m = re.match(r"(\d{1,2}):(\d{2})(?::(\d{2}))?", hora.strip())
    if not m:
        return datas[0]
    momento = datetime.combine(datas[0], datetime.min.time()).replace(
        hour=int(m.group(1)), minute=int(m.group(2)), second=int(m.group(3) or 0)
    )
    try:
        from django.conf import settings
        from django.utils import timezone

        if getattr(settings, "USE_TZ", False):
            return timezone.make_aware(momento)
    except Exception:  # fora do Django (script): fica sem fuso
        pass
    return momento


def _limpar(dados: dict) -> dict:
    return {chave: valor for chave, valor in dados.items() if valor not in (None, "", [], {}, ())}


def _numero_ano(m) -> tuple[int, int] | None:
    try:
        return int(m.group(1)), int(m.group(2))
    except (TypeError, ValueError, IndexError):
        return None


# ─────────────────────────────────────────────────────────────────
# Nomes
# ─────────────────────────────────────────────────────────────────

# Onde o nome acaba: o próximo rótulo do comprovante/documento.
_FIM_DO_NOME = re.compile(
    r"\s*(?:\b(?:CPF|CNPJ|CHAVE|INSTITUI[CÇ][AÃ]O|BANCO|AG[EÊ]NCIA|AG\.?|CONTA|C/C|VALOR|DATA|HORA|HOR[AÁ]RIO|TIPO|ID|NSU|"
    r"TERMINAL|AUTENTICA[CÇ][AÃ]O|DOCUMENTO|C[OÓ]DIGO|SALDO|TARIFA|E-?MAIL|TELEFONE|RG|MATR[IÍ]CULA|LOTA[CÇ][AÃ]O|"
    r"CARGO|PIX|DESTINO|ORIGEM|PARA|QUEM)\b|[:(\d*•]).*$",
    re.IGNORECASE,
)
_LIGACOES = {"de", "da", "do", "das", "dos", "e", "del", "di", "van", "von"}
_SO_ROTULO = re.compile(r"^(?:NOME|NOME COMPLETO|FAVORECIDO|RECEBEDOR|PAGADOR|CLIENTE|TITULAR|DESTINO|ORIGEM|DE|PARA)$", re.I)


def _nome(valor: str) -> str:
    """Um nome de pessoa limpo (≥ 2 palavras, só letras); "" se não parecer nome."""
    valor = re.sub(r"^\s*(?:nome(?: completo)?|raz[aã]o social)\s*:?\s*", "", str(valor or ""), flags=re.I)
    valor = _FIM_DO_NOME.sub("", valor).strip(" .,;:-/|\t")
    valor = " ".join(valor.split())
    if not valor or _SO_ROTULO.match(valor):
        return ""
    palavras = valor.split()
    if len(palavras) < 2 or len(valor) > 90:
        return ""
    if not re.fullmatch(r"[A-Za-zÀ-ÿ' .-]+", valor):
        return ""
    # Nome próprio: toda palavra começa com maiúscula, menos as ligações.
    if any(p[:1].islower() and p.lower() not in _LIGACOES for p in palavras):
        return ""
    return valor


def _depois_do_rotulo(linhas: list[str], rotulo: re.Pattern, *, seguintes: int = 2) -> tuple[str, int] | None:
    """(o que vem depois do rótulo na mesma linha — ou nas próximas —, índice da linha)."""
    for i, linha in enumerate(linhas):
        m = rotulo.search(linha)
        if not m:
            continue
        resto = linha[m.end():].strip(" :-\t")
        if resto and not _SO_ROTULO.match(resto):
            return resto, i
        for j in range(i + 1, min(len(linhas), i + 1 + seguintes)):
            candidato = linhas[j].strip(" :-\t")
            if candidato and not _SO_ROTULO.match(candidato):
                return candidato, j
    return None


def _nome_por_rotulo(linhas: list[str], rotulo: re.Pattern) -> tuple[str, int] | None:
    for i, linha in enumerate(linhas):
        m = rotulo.search(linha)
        if not m:
            continue
        resto = linha[m.end():].strip(" :-\t")
        candidatos = [resto] if resto else []
        candidatos += [linhas[j] for j in range(i + 1, min(len(linhas), i + 3))]
        for candidato in candidatos:
            nome = _nome(candidato)
            if nome:
                return nome, i
    return None


# ─────────────────────────────────────────────────────────────────
# Por tipo
# ─────────────────────────────────────────────────────────────────

_OF_TITULO = re.compile(r"^(?!.*ASSUNTO:)(?!.*\bREF(?:ERENTE|\.)? AO\b).*?\bOF(?:ICIO|\.)\s*" + _N + r"(\d{1,4})\s*/\s*(\d{4})", re.M)
_OF_QUALQUER = re.compile(r"\bOF(?:ICIO|\.)\s*" + _N + r"(\d{1,4})\s*/\s*(\d{4})")


def _oficio(texto: str) -> dict:
    linhas = "\n".join(normalizar(linha) for linha in texto.splitlines())
    plano = normalizar(texto)
    dados: dict = {}
    m = _OF_TITULO.search(linhas[:1500]) or _OF_QUALQUER.search(plano)
    if m and _numero_ano(m):
        dados["numero"], dados["ano"] = _numero_ano(m)
    m = re.search(r"(?<!PCPR )PROTOCOLO\s*" + _N + _PROTO, plano)
    if m:
        dados["protocolo"] = _digitos(m.group(1))
    m = re.search(r"PCPR PROTOCOLO N[^:]{0,4}:\s*(\d[\d.]*\d)", plano)
    if m:
        dados["pcpr_protocolo"] = m.group(1)
    dados["cpfs"] = achar_cpfs(texto)
    if re.search(r"\(CONVALIDACAO\)|SOLICITACAO DE CONVALIDACAO|SOLICITO (?:A )?CONVALIDACAO", plano):
        dados["convalidacao"] = True
    elif re.search(r"\(AUTORIZACAO\)|SOLICITACAO DE AUTORIZACAO|SOLICITO (?:A )?AUTORIZACAO", plano):
        dados["convalidacao"] = False
    m = re.search(r"\bDATA:\s*(.{0,30})", plano)
    datas = achar_datas(m.group(1)) if m else []
    if not datas:
        m = re.search(r"[A-Za-zÀ-ÿ]+(?:/[A-Z]{2})?,\s*(\d{1,2}(?:º|°)? de [A-Za-zçÇ]+ de \d{4})", _linha_unica(texto))
        datas = achar_datas(m.group(1)) if m else []
    if datas:
        dados["data"] = datas[0]
    m = re.search(r"NOTAS? FISCA(?:L|IS)\s*" + _N + r"((?:\d[\d.]*(?:\s*(?:,|E)\s*)?)+)", plano)
    if m:
        dados["notas_fiscais"] = [_sem_zeros(n) for n in re.findall(r"\d[\d.]*\d|\d", m.group(1)) if _sem_zeros(n)]
    m = re.search(r"\bCONTRATO\s*" + _N + r"(\d{3,4}/\d{4})", plano)
    if m:
        dados["contrato"] = m.group(1)
    return dados


def _rt(texto: str) -> dict:
    plano = normalizar(texto)
    linhas = [linha.strip() for linha in texto.splitlines() if linha.strip()]
    dados: dict = {}
    m = re.search(r"REF\.? AO OFICIO\s*" + _N + r"(\d{1,4})\s*/\s*(\d{4})", plano)
    if m and _numero_ano(m):
        dados["oficio_numero"], dados["oficio_ano"] = _numero_ano(m)
    achado = _nome_por_rotulo(linhas, re.compile(r"^\s*nome\b\s*:?", re.I))
    if achado:
        dados["nome"] = achado[0]
    cpfs = achar_cpfs(texto)
    if cpfs:
        dados["cpf"] = cpfs[0]
    m = re.search(r"DIARIA:\s*(?:R\$\s*)?" + _VALOR, plano)
    if m:
        dados["diaria"] = valor_de(m.group(1))
    return dados


def _diario(texto: str) -> dict:
    plano = normalizar(texto)
    dados: dict = {}
    m = re.search(r"REFERENTE AO OFICIO:?\s*" + _N + r"(\d{1,4})\s*/\s*(\d{4})", plano)
    if m and _numero_ano(m):
        dados["oficio_numero"], dados["oficio_ano"] = _numero_ano(m)
    m = re.search(r"E-?PROTOCOLO:?\s*" + _PROTO, plano)
    if m:
        dados["protocolo"] = _digitos(m.group(1))
    m = re.search(r"PLACA OFICIAL:?\s*([A-Z]{3}\s?-?\s?\d[A-Z0-9]\d{2})\b", plano)
    if m:
        dados["placa"] = normalize_placa(m.group(1))
    m = re.search(r"\bNOME:\s*([A-Z][A-Z .'-]{3,80}?)\s*(?:CPF\b|ASSINATURA|$)", plano)
    if m and _nome(m.group(1)):
        dados["motorista"] = _nome(m.group(1))
    m = re.search(r"\bCPF:\s*(\d{3}\.?\d{3}\.?\d{3}-?\d{2})", plano)
    if m:
        dados["cpf_motorista"] = _digitos(m.group(1))
    return dados


def _termo(texto: str) -> dict:
    corrido = _linha_unica(texto)
    dados: dict = {}
    m = re.search(r"\bEu\s*:?\s+([^,\n]{3,90}?)\s*,\s*(?:RG|CPF|portador)", corrido, re.I)
    if m and _nome(m.group(1)):
        dados["nome"] = _nome(m.group(1))
    cpfs = achar_cpfs(texto)
    if cpfs:
        dados["cpf"] = cpfs[0]
    m = re.search(r"\bRG\s*:?\s*" + r"(?:n[º°o.]*\s*)?([0-9Xx](?:[0-9Xx.\-/ ]{3,14})[0-9Xx])\b", corrido, re.I)
    if m:
        rg = re.sub(r"[^0-9X]", "", m.group(1).upper())
        if len(rg) >= 5:
            dados["rg"] = rg
    m = re.search(r"lotad[oa](?:\s*\(a\))?\s+n[ao](?:\s*\(o\))?\s+(.+?)\s*,\s*manifesto", corrido, re.I)
    if m and m.group(1).strip("_ ").strip():
        dados["lotacao"] = m.group(1).strip("_ ").strip()
    return dados


def _despacho(texto: str) -> dict:
    corrido = _linha_unica(texto)
    linhas = [linha.strip() for linha in texto.splitlines() if linha.strip()]
    dados: dict = {}
    m = re.search(r"Protocolo:\s*" + _PROTO, corrido, re.I)
    if m:
        dados["protocolo"] = _digitos(m.group(1))
    m = re.search(r"(\d{2}/\d{2}/\d{4})(?:\s+(\d{2}:\d{2}))?\s*Data:", corrido) or re.search(
        r"Data:\s*(\d{2}/\d{2}/\d{4})(?:\s+(\d{2}:\d{2}))?", corrido
    )
    if m:
        dados["data"] = data_hora(m.group(1))
        if m.group(2):
            dados["data_hora"] = data_hora(m.group(1), m.group(2))
    for linha in linhas:
        m = re.match(r"^(?:Ao|Aos|À|Às|A)\s+(.{2,60}?)\s*,$", linha, re.I)
        if m and not re.search(r"\d{2}/\d{2}/\d{4}", linha):
            dados["destino"] = m.group(1).strip()
            break
    # Assunto: da linha "Assunto:" até a linha do "Interessado:" (o valor do
    # interessado pode vir antes ou depois do rótulo, na mesma linha).
    for i, linha in enumerate(linhas):
        m = re.search(r"Assunto:\s*(.*)$", linha, re.I)
        if not m:
            continue
        partes = [m.group(1).strip()]
        for seguinte in linhas[i + 1:i + 6]:
            if re.search(r"Interessado:", seguinte, re.I):
                antes, _, depois = seguinte.partition(":")
                antes = re.sub(r"Interessado$", "", antes, flags=re.I).strip()
                depois = depois.strip()
                if depois:
                    interessado = depois
                    if antes:
                        partes.append(antes)
                elif antes:
                    interessado = antes
                elif len(partes) > 1:  # rótulo sozinho: o valor é a linha de cima
                    interessado = partes.pop()
                else:
                    interessado = ""
                if interessado:
                    dados["interessado"] = interessado
                break
            partes.append(seguinte)
        assunto = " ".join(p for p in partes if p)
        if assunto:
            dados["assunto"] = assunto
        break
    return dados


def _nota_fiscal(texto: str) -> dict:
    from coffee_break.nota_fiscal import _CHAVE
    from coffee_break.nota_fiscal import numero_no_texto

    corrido = _linha_unica(texto)
    dados: dict = {"numero": numero_no_texto(texto)}
    m = re.search(r"S[ÉE]RIE:?\s*(\d{1,3})\b", corrido, re.I)
    if m:
        dados["serie"] = m.group(1)
    m = (
        re.search(r"EMISS[ÃA]O:?\s*(\d{2}/\d{2}/\d{4})", corrido, re.I)
        or re.search(r"DATA (?:E HORA )?D[AE] EMISS[ÃA]O:?\s*(\d{2}/\d{2}/\d{4})", corrido, re.I)
        or re.search(r"EMITIDA EM:?\s*(\d{2}/\d{2}/\d{4})", corrido, re.I)
    )
    if m:
        dados["emissao"] = data_hora(m.group(1))
    m = (
        re.search(r"VALOR TOTAL(?: DA NOTA)?:?\s*(?:R\$\s*)?" + _VALOR, corrido, re.I)
        or re.search(r"VALOR (?:TOTAL |L[ÍI]QUIDO )?(?:DOS? )?SERVI[ÇC]OS?:?\s*(?:R\$\s*)?" + _VALOR, corrido, re.I)
        or re.search(r"VALOR L[ÍI]QUIDO(?: DA NOTA)?:?\s*(?:R\$\s*)?" + _VALOR, corrido, re.I)
    )
    if m:
        dados["valor"] = valor_de(m.group(1))
    cnpjs = achar_cnpjs(texto)
    if cnpjs:
        dados["cnpj"] = cnpjs[0]
    for achado in _CHAVE.finditer(texto):
        chave = _digitos(achado.group(1))
        if len(chave) == 44:
            dados["chave"] = chave
            break
    return dados


def _certifico(texto: str) -> dict:
    plano = normalizar(texto)
    dados: dict = {}
    m = re.search(r"NOTA FISCAL\s*" + _N + r"(\d[\d.]*)", plano)
    if m:
        dados["nota_fiscal"] = _sem_zeros(m.group(1))
    cnpjs = achar_cnpjs(texto)
    if cnpjs:
        dados["cnpj"] = cnpjs[0]
    m = re.search(r"\bCONTRATO\s*" + _N + r"(\d{3,4}/\d{4})", plano)
    if m:
        dados["contrato"] = m.group(1)
    return dados


def _certidao(texto: str) -> dict:
    from coffee_break.certidoes import tipo_do_texto
    from coffee_break.certidoes import validade_do_texto

    dados: dict = {"tipos": [str(t) for t in tipo_do_texto(texto)], "validade": validade_do_texto(texto)}
    cnpjs = achar_cnpjs(texto)
    if cnpjs:
        dados["cnpj"] = cnpjs[0]
    return dados


def _contrato(texto: str) -> dict:
    plano = normalizar(texto)
    dados: dict = {}
    m = re.search(r"\bCONTRATO\W{0,6}" + _N + r"(\d{3,4}/\d{4})", plano)
    if m:
        dados["numero"] = m.group(1)
    m = re.search(r"PROTOCOLO\s*" + _N + _PROTO, plano)
    if m:
        dados["protocolo"] = _digitos(m.group(1))
    dados["cnpjs"] = achar_cnpjs(texto)
    return dados


def _aditivo(texto: str) -> dict:
    plano = normalizar(texto)
    dados = _contrato(texto)
    dados.pop("numero", None)
    m = re.search(r"TERMO ADITIVO\s*" + _N + r"(\d{3,4}/\d{4})", plano)
    if m:
        dados["numero"] = m.group(1)
    m = re.search(r"\bCONTRATO\s*" + _N + r"(\d{3,4}/\d{4})", plano)
    if m:
        dados["contrato"] = m.group(1)
    return dados


def _empenho_ou_liquidacao(texto: str, sigla: str) -> dict:
    corrido = _linha_unica(texto)
    dados: dict = {}
    m = re.search(rf"\b(\d{{4}}{sigla}\d{{6}})\b\s*(\d{{2}}/\d{{2}}/\d{{2,4}})?", corrido)
    if m:
        dados["numero"] = m.group(1)
        if m.group(2):
            dados["emissao"] = data_hora(m.group(2))
    return dados


def _nota_empenho(texto: str) -> dict:
    dados = _empenho_ou_liquidacao(texto, "NE")
    m = re.search(r"(?m)^\s*Valor\s+" + _VALOR, texto) or re.search(r"\bValor\s+" + _VALOR, _linha_unica(texto))
    if m:
        dados["valor"] = valor_de(m.group(1))
    cnpjs = re.findall(r"Credor\s+(\d{14})", texto)
    if cnpjs:
        dados["cnpj"] = cnpjs[0]
    return dados


def _nota_liquidacao(texto: str) -> dict:
    corrido = _linha_unica(texto)
    dados = _empenho_ou_liquidacao(texto, "NL")
    m = re.search(r"Valor Bruto\s+Valor L[íi]quido\s+" + _VALOR, corrido, re.I) or re.search(
        r"Total Documentos Comprobat[óo]rios\s+" + _VALOR, corrido, re.I
    )
    if m:
        dados["valor"] = valor_de(m.group(1))
    m = re.search(r"Nota de Empenho\s+(\d{4}NE\d{6})", corrido, re.I)
    if m:
        dados["empenho"] = m.group(1)
    notas = []
    for m in re.finditer(
        r"(?<![\d.])(\d{1,3}(?:\.\d{3})+|\d{1,9})\s+" + _PROTO + r"\s+\d{2}/\d{4}\s+(\d{2}/\d{2}/\d{4})\s+" + _VALOR,
        corrido,
    ):
        notas.append({"numero": _sem_zeros(m.group(1)), "data": data_hora(m.group(3)), "valor": valor_de(m.group(4))})
    if notas:
        dados["notas_fiscais"] = notas
    return dados


def _numero_do_titulo(texto: str, titulo: str) -> dict:
    plano = normalizar(texto)
    m = re.search(titulo + r"\s*" + _N + r"(\d{1,4})(?:\s*/\s*(\d{4}))?", plano)
    if not m:
        return {}
    dados = {"numero": int(m.group(1))}
    if m.group(2):
        dados["ano"] = int(m.group(2))
    return dados


def _justificativa(texto: str) -> dict:
    datas = achar_datas(texto[:600])
    dados: dict = {"data": datas[0]} if datas else {}
    m = _OF_QUALQUER.search(normalizar(texto))
    if m and _numero_ano(m):
        dados["oficio_numero"], dados["oficio_ano"] = _numero_ano(m)
    return dados


def _email(texto: str) -> dict:
    dados: dict = {}
    m = re.search(r"(?mi)^\s*(?:Assunto|Subject)\s*:\s*(.+)$", texto)
    if m:
        dados["assunto"] = m.group(1).strip()
    m = re.search(r"(?mi)^\s*(?:De|From)\s*:\s*(.+)$", texto)
    if m:
        dados["remetente"] = m.group(1).strip()
    return dados


def _capa(texto: str) -> dict:
    """Plano B da capa, sem coordenadas: o texto sai com o valor ANTES do rótulo ("123/2026Nº/Ano")."""
    corrido = _linha_unica(texto)
    dados: dict = {}
    m = re.search(r"Protocolo:\s*" + _PROTO, corrido, re.I)
    if m:
        dados["protocolo"] = _digitos(m.group(1))
    m = re.search(r"(\d{1,4}/\d{4})\s*N[º°o]\s*/\s*Ano", corrido, re.I) or re.search(
        r"N[º°o]\s*/\s*Ano:?\s*(\d{1,4}/\d{4})", corrido, re.I
    )
    if m:
        dados["numero_ano"] = m.group(1)
    m = re.search(r"Em:\s*(\d{2}/\d{2}/\d{4})(?:\s+(\d{2}:\d{2}))?", corrido)
    if m:
        dados["em"] = data_hora(m.group(1), m.group(2) or "")
    return dados


# ─────────────────────────────────────────────────────────────────
# Comprovante bancário
# ─────────────────────────────────────────────────────────────────

_BANCOS = (
    ("Caixa", r"CAIXA ECONOMICA|\bCAIXA\b"),
    ("Banco do Brasil", r"BANCO DO BRASIL|\bSISBB\b|\bBB\b"),
    ("Itaú", r"\bITAU\b"),
    ("Bradesco", r"BRADESCO"),
    ("Santander", r"SANTANDER"),
    ("Nubank", r"NUBANK|NU PAGAMENTOS"),
    ("Sicredi", r"SICREDI"),
    ("Sicoob", r"SICOOB"),
    ("Inter", r"BANCO INTER|INTER ?& ?CO|\bINTER\b"),
    ("C6 Bank", r"\bC6 ?BANK\b|BANCO C6"),
    ("Mercado Pago", r"MERCADO ?PAGO"),
    ("PicPay", r"PICPAY"),
    ("Banrisul", r"BANRISUL"),
    ("PagBank", r"PAGBANK|PAGSEGURO"),
    ("BTG Pactual", r"\bBTG\b"),
    ("Banco Original", r"BANCO ORIGINAL"),
    ("Cresol", r"CRESOL"),
)

_OPERACOES = (
    ("saque", r"\bSAQUE\b"),
    ("pix", r"\bPIX\b"),
    ("ted", r"\bTED\b"),
    ("doc", r"(?<!N[O°.] )\bDOC\b(?![.:])"),
    ("deposito", r"\bDEPOSITO\b"),
    ("transferencia", r"TRANSFERENCIA|\bTRANSF\b"),
)

_ROTULO_VALOR = re.compile(
    r"(?:\bVALOR(?: D[OA])?(?: (?:DO |DA )?(?:SAQUE|PIX|TRANSFERENCIA|TED|DOC|PAGO|PAGAMENTO|TOTAL|DEPOSITO|OPERACAO|"
    r"TRANSACAO|ENVIADO|DEBITADO|SACADO|TRANSFERIDO|RECEBIDO))?|\bQUANTIA|\bIMPORTANCIA|\bTOTAL)"
    r"\s*:?\s*(?:\(?R\$\)?)?\s*" + _VALOR
)
_NAO_E_O_VALOR = re.compile(r"SALDO|TARIFA|LIMITE|JUROS|MULTA|IOF|ENCARGO|DISPONIVEL")
_ROTULO_DATA = re.compile(
    r"(?:\bDATA(?: E HORA)?(?: D[AOE])?(?: (?:OPERACAO|TRANSACAO|TRANSFERENCIA|SAQUE|PAGAMENTO|DEPOSITO|EFETIVACAO|"
    r"MOVIMENTO|MOVIMENTACAO|EMISSAO|DEBITO))?|REALIZAD[OA] EM|EFETUAD[OA] EM|EFETIVAD[OA] EM|EMITIDO EM|"
    r"AGENDAD[OA] PARA|ENVIADO EM|PAGO EM)\s*:?\s*"
)
_ROTULO_FAVORECIDO = re.compile(
    r"^\s*(?:nome\s+(?:do\s+|da\s+)?)?(?:favorecid[oa]|destinat[aá]ri[oa]|recebedor(?:a)?|benefici[aá]ri[oa]|"
    r"quem recebeu|para|destino|dados do (?:recebedor|favorecido|destinat[aá]rio))\b\s*:?",
    re.I,
)
_ROTULO_PAGADOR = re.compile(
    r"^\s*(?:nome\s+(?:do\s+|da\s+)?)?(?:pagador(?:a)?|remetente|depositante|ordenante|quem pagou|de|origem|"
    r"dados do pagador)\b\s*:?",
    re.I,
)
_ROTULO_TITULAR = re.compile(
    r"^\s*(?:nome\s+(?:do\s+|da\s+)?(?:cliente|titular|correntista|sacador)|cliente|titular|sacador|portador|"
    r"correntista|nome)\b\s*:?",
    re.I,
)


def _valor_comprovante(plano: str) -> Decimal | None:
    for m in _ROTULO_VALOR.finditer(plano):
        if not _NAO_E_O_VALOR.search(plano[max(0, m.start() - 20):m.start() + 8]):
            return valor_de(m.group(1))
    for m in re.finditer(r"R\$\s*" + _VALOR, plano):
        if not _NAO_E_O_VALOR.search(plano[max(0, m.start() - 25):m.start()]):
            return valor_de(m.group(1))
    return None


def _data_plausivel_comprovante(dia: date) -> bool:
    """Comprovante de diária é recente: nem futuro, nem de anos atrás."""
    hoje = date.today()
    return hoje - timedelta(days=730) <= dia <= hoje + timedelta(days=1)


def _com_ano_corrigido(dia: date) -> date | None:
    """O OCR troca dígitos do ano ("2026" vira "2020", "202t"): mesmo dia/mês,
    no ano mais recente que não fique no futuro."""
    hoje = date.today()
    for ano in (hoje.year, hoje.year - 1):
        try:
            candidato = dia.replace(year=ano)
        except ValueError:  # 29/02
            continue
        if _data_plausivel_comprovante(candidato):
            return candidato
    return None


def _data_comprovante(plano: str) -> tuple[date | None, str]:
    """(data da operação, hora). Prefere a data do rótulo ("DATA DA TRANSFERÊNCIA");
    entre as lidas, a que faz sentido para um comprovante de diária. Uma data
    de ano impossível (erro de OCR) vale com o ano corrigido se o dia e o mês
    batem com outra data do comprovante — ou se é a única."""
    rotuladas: list[tuple[date, str]] = []
    for m in _ROTULO_DATA.finditer(plano):
        trecho = plano[m.end():m.end() + 40]
        if re.match(r"(?:DE )?(?:NASCIMENTO|VALIDADE|VENCIMENTO)", trecho):
            continue
        datas = achar_datas(trecho)
        if datas:
            hora = re.search(r"(\d{2}:\d{2}(?::\d{2})?)", plano[m.end():m.end() + 60])
            rotuladas.append((datas[0], hora.group(1) if hora else ""))
    hora_solta = re.search(r"\b(\d{2}:\d{2}(?::\d{2})?)\b", plano)
    soltas = [(d, hora_solta.group(1) if hora_solta else "") for d in achar_datas(plano)]
    todas = rotuladas + soltas
    if not todas:
        return None, ""
    for dia, hora in todas:
        if _data_plausivel_comprovante(dia):
            return dia, hora
    # Nenhuma plausível: o ano foi mal lido. Dia e mês repetidos reforçam a leitura.
    dias_meses = [(d.day, d.month) for d, _ in todas]
    for dia, hora in todas:
        corrigida = _com_ano_corrigido(dia)
        if corrigida and (dias_meses.count((dia.day, dia.month)) > 1 or len(set(dias_meses)) == 1):
            return corrigida, hora
    return todas[0]


def _operacao(plano: str) -> str:
    for trecho in (plano[:400], plano):
        for nome, padrao in _OPERACOES:
            if re.search(padrao, trecho):
                return nome
    return ""


def _banco(texto: str) -> str:
    """O banco que emitiu o comprovante.

    O do cabeçalho, se houver; senão o que aparece com a razão social
    ("NU PAGAMENTOS S.A.", "BANCO INTER S.A." — o rodapé de quem emite); senão
    o primeiro citado. O banco do recebedor ("Instituição: CAIXA ECONOMICA
    FEDERAL") aparece no corpo, sem "S.A.".
    """
    cabecalho = normalizar(" ".join([linha for linha in texto.splitlines() if linha.strip()][:2]))
    for nome, padrao in _BANCOS:
        if re.search(padrao, cabecalho):
            return nome
    plano = normalizar(texto)
    achados = []
    for nome, padrao in _BANCOS:
        for m in re.finditer(padrao, plano):
            achados.append((m.start(), m.end(), nome))
    if not achados:
        return ""
    achados.sort()
    for _inicio, fim, nome in achados:
        if re.match(r"[^.]{0,25}?\bS\.? ?/?A\b", plano[fim:fim + 30]):
            return nome
    return achados[0][2]


_RX_NOME_ROTULADO = re.compile(
    r"^(?:.*\b)?(?:CLIENTE|NOME|FAVORECIDO|TITULAR|DESTINATARIO|RECEBEDOR|BENEFICIARIO|PAGADOR|SACADOR|CORRENTISTA)"
    r"\s*:?\s*([A-Z][A-Z ]{5,})$"
)
_NAO_E_PESSOA = re.compile(r"\b(?:CARTAO|CREDITO|DEBITO|CONTA|BANCO|AGENCIA|PAGAMENTOS|LTDA|S A|INSTITUICAO)\b")


def _nomes_de_pessoa(linhas: list[str]) -> list[str]:
    nomes = []
    for linha in linhas:
        m = _RX_NOME_ROTULADO.match(normalizar(linha))
        if not m:
            continue
        nome = " ".join(m.group(1).split())
        if len(nome.split()) >= 2 and not _NAO_E_PESSOA.search(nome) and nome not in nomes:
            nomes.append(nome)
    return nomes


def _comprovante(texto: str) -> dict:
    # OCR de foto separa os centavos ("958, 82", "958 ,82"): junta antes de ler o valor.
    texto = re.sub(r"(\d)\s*([,.])\s+(\d{2})(?!\d)", r"\1\2\3", texto or "")
    texto = re.sub(r"(\d)\s+([,.])(\d{2})(?!\d)", r"\1\2\3", texto)
    plano = normalizar(texto)
    linhas = [linha.strip() for linha in texto.splitlines() if linha.strip()]
    dados: dict = {}
    dados["valor"] = _valor_comprovante(plano)
    dia, hora = _data_comprovante(plano)
    dados["data"] = dia
    if hora:
        dados["hora"] = hora
    dados["operacao"] = _operacao(plano)
    dados["banco"] = _banco(texto)

    favorecido = _nome_por_rotulo(linhas, _ROTULO_FAVORECIDO)
    pagador = _nome_por_rotulo(linhas, _ROTULO_PAGADOR)
    titular = _nome_por_rotulo(linhas, _ROTULO_TITULAR)
    if favorecido:
        dados["favorecido"] = favorecido[0]
    if pagador:
        dados["pagador"] = pagador[0]
    if dados["operacao"] == "saque":
        escolhido = titular or favorecido or pagador
    else:
        escolhido = favorecido or titular or pagador
    if escolhido:
        dados["nome"] = escolhido[0]
    # Todos os nomes de pessoa do comprovante: no caixa do BB, o cartão sai no
    # nome curto ("CLIENTE: FULANA PEREIRA") e a conta em outro ("TRANSFERIDO
    # PARA: CLIENTE: FULANA VILLELA DE"); qualquer um pode ser o do cadastro.
    nomes = _nomes_de_pessoa(linhas)
    if nomes:
        dados["nomes"] = nomes

    # O CPF da pessoa escolhida: o mascarado mais próximo depois do nome;
    # sem isso, o primeiro do comprovante.
    mascarados = []
    if escolhido:
        perto = "\n".join(linhas[escolhido[1]:escolhido[1] + 5])
        mascarados = achar_cpfs_mascarados(perto) or achar_cpfs_mascarados(perto, tolerante=True)
    mascarados = mascarados or achar_cpfs_mascarados(texto) or achar_cpfs_mascarados(texto, tolerante=True)
    for formato, digitos in mascarados:
        dados.setdefault(f"cpf_{formato}", digitos)
    cpfs = achar_cpfs(texto)
    if cpfs:
        dados["cpfs"] = cpfs
    return dados


# ─────────────────────────────────────────────────────────────────

_EXTRATORES = {
    tipos.CAPA: _capa,
    tipos.OFICIO: _oficio,
    tipos.DESPACHO: _despacho,
    tipos.JUSTIFICATIVA: _justificativa,
    tipos.TERMO_AUTORIZACAO: _termo,
    tipos.RT: _rt,
    tipos.DIARIO_BORDO: _diario,
    tipos.COMPROVANTE: _comprovante,
    tipos.ORDEM_SERVICO: lambda texto: _numero_do_titulo(texto, r"ORDEM DE SERVICO"),
    tipos.PLANO_TRABALHO: lambda texto: _numero_do_titulo(texto, r"PLANO DE TRABALHO"),
    tipos.NOTA_FISCAL: _nota_fiscal,
    tipos.CERTIFICO: _certifico,
    tipos.CERTIDAO: _certidao,
    tipos.CONTRATO: _contrato,
    tipos.ADITIVO: _aditivo,
    tipos.NOTA_EMPENHO: _nota_empenho,
    tipos.NOTA_LIQUIDACAO: _nota_liquidacao,
    tipos.EMAIL: _email,
}


def dados_do_documento(tipo: str, texto: str) -> dict:
    """O que dá para tirar do texto de um documento do `tipo` (ver o topo do módulo).

    Tipo sem extrator (ou DESCONHECIDO) devolve só os protocolos citados, se houver.
    """
    texto = str(texto or "")
    extrator = _EXTRATORES.get(tipo)
    if extrator is None:
        return _limpar({"protocolos": achar_protocolos(texto)})
    return _limpar(extrator(texto))
