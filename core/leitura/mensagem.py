"""O e-mail (ou o texto colado) de um pedido, lido para preencher o formulário.

Aceita .eml e .mht (biblioteca padrão), .msg do Outlook (olefile, lendo os
streams MAPI e os cabeçalhos de transporte), PDF impresso do Outlook (em
português ou inglês) ou do Gmail, .txt e texto colado — inclusive conversa
do WhatsApp ("[24/09/2026 14:32] Maria: ...").

O que interessa é a mensagem de quem pediu. Num encaminhamento vale a mais
interna, e quem encaminhou fica em `encaminhada_por`. As citações de
respostas anteriores saem do corpo (ficam em `citado`), e a assinatura
também — guardada à parte, porque é dela que saem nome, cargo, unidade e
telefone.

Segurança: o HTML do e-mail nunca é renderizado nem tem link ou imagem
seguidos — um parser só junta o texto. Há limite de tamanho para a
mensagem e para os anexos, e nada sai do servidor. Para registrar algo em
log, use `mascarar_para_log` (CPF, telefone e e-mail mascarados).
"""

from __future__ import annotations

import codecs
import io
import logging
import re
import struct
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone as tz_utc
from email import policy
from email.parser import BytesParser, HeaderParser
from email.utils import getaddresses, parsedate_to_datetime
from html.parser import HTMLParser
from pathlib import PurePath

from .datas import data_hora_de_cabecalho, dobrar

logger = logging.getLogger(__name__)

__all__ = [
    "Mensagem",
    "MensagemIlegivel",
    "assunto_sem_prefixos",
    "html_para_texto",
    "ler_mensagem",
    "ler_texto_colado",
    "mascarar_para_log",
    "separar_assinatura",
]

MIB = 1024 * 1024
# Padrões; cada um pode ser ajustado no settings com o mesmo nome.
LEITURA_EMAIL_MAX_BYTES = 25 * MIB          # o arquivo inteiro (igual ao nginx)
LEITURA_EMAIL_ANEXO_MAX_BYTES = 15 * MIB    # cada anexo
LEITURA_EMAIL_MAX_ANEXOS = 20
_MAX_CARACTERES = 300_000                   # texto do corpo que se analisa
_MAX_PARTES_MIME = 300
_MAX_PROFUNDIDADE = 5                       # e-mail anexado dentro de e-mail anexado...
_MAX_PAGINAS_PDF = 15
_MAX_PAGINAS_OCR = 3
_MAX_RTF_BYTES = 5 * MIB
_MAGIC_OLE = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"
# Linha maior que isto não é cabeçalho, marca de encaminhamento nem fecho.
_MAX_LINHA_CABECALHO = 400


def _ajuste(nome: str, padrao: int) -> int:
    try:
        from django.conf import settings

        return int(getattr(settings, nome, padrao))
    except Exception:  # sem Django configurado (uso fora do projeto)
        return padrao


class MensagemIlegivel(ValueError):
    """O arquivo não é um e-mail que dê para ler. A mensagem é para a tela."""


@dataclass
class Mensagem:
    """O que se leu do e-mail: cabeçalhos da mensagem de quem pediu e o corpo limpo.

    `enviado_em` tem fuso quando o e-mail diz (sem fuso no texto, vale o do
    sistema). `corpo` já vem sem citações e sem assinatura; a `assinatura`
    fica à parte. `anexos` são (nome, bytes), dentro dos limites; os que
    passaram do limite viram aviso. `origem`: "eml", "mht", "msg", "pdf",
    "txt", "texto" (colado) ou "whatsapp".
    """

    assunto: str = ""
    remetente_nome: str = ""
    remetente_email: str = ""
    enviado_em: datetime | None = None
    corpo: str = ""
    assinatura: str = ""
    anexos: list[tuple[str, bytes]] = field(default_factory=list)
    message_id: str = ""
    origem: str = ""
    encaminhada_por: str = ""
    citado: str = ""
    anexos_citados: list[str] = field(default_factory=list)
    avisos: list[str] = field(default_factory=list)

    @property
    def assunto_limpo(self) -> str:
        """O assunto sem "RES:", "ENC:", "FW:", "[EXTERNO]"."""
        return assunto_sem_prefixos(self.assunto)

    @property
    def remetente(self) -> str:
        """Nome do remetente (ou o e-mail, sem nome), para o histórico."""
        return self.remetente_nome or self.remetente_email

    @property
    def data_referencia(self):
        """A data do e-mail no fuso do sistema: referência de "amanhã", "próxima terça"."""
        if self.enviado_em is None:
            return None
        if self.enviado_em.tzinfo is None:
            return self.enviado_em.date()
        try:
            from django.utils import timezone

            return timezone.localtime(self.enviado_em).date()
        except Exception:
            return self.enviado_em.date()

    @property
    def texto_para_busca(self) -> str:
        """Assunto e corpo juntos: onde procurar datas, município, quantidade."""
        return "\n".join(x for x in (self.assunto_limpo, self.corpo) if x)


# ---------------------------------------------------------------------------
# Entrada
# ---------------------------------------------------------------------------


def ler_mensagem(nome_arquivo: str, dados: bytes) -> Mensagem:
    """Lê um e-mail salvo em arquivo (.eml, .mht, .msg, .pdf impresso, .txt).

    O tipo sai do conteúdo, não só da extensão (um .msg renomeado para .eml
    ainda é lido como .msg). Levanta `MensagemIlegivel`, com mensagem para a
    tela, se o arquivo estiver vazio, passar do limite ou não for e-mail.
    """
    dados = bytes(dados or b"")
    if not dados:
        raise MensagemIlegivel("O arquivo está vazio.")
    limite = _ajuste("LEITURA_EMAIL_MAX_BYTES", LEITURA_EMAIL_MAX_BYTES)
    if len(dados) > limite:
        raise MensagemIlegivel(f"O arquivo passa do limite de {limite / MIB:.0f} MB para leitura de e-mail.")
    extensao = PurePath(nome_arquivo or "").suffix.lower()
    if dados.startswith(_MAGIC_OLE):
        origem, leitor = "msg", _ler_msg
    elif b"%PDF-" in dados[:1024]:
        origem, leitor = "pdf", _ler_pdf
    elif extensao in (".eml", ".mht", ".mhtml") or _parece_mime(dados):
        origem, leitor = ("mht" if extensao in (".mht", ".mhtml") else "eml"), _ler_eml
    elif _parece_texto(dados):
        origem, leitor = "txt", _ler_txt
    else:
        raise MensagemIlegivel("Formato não reconhecido. Envie o e-mail em .eml, .msg, .mht, .pdf ou .txt, ou cole o texto.")
    try:
        mensagem = leitor(dados, origem)
    except MensagemIlegivel:
        raise
    except Exception as exc:  # arquivo corrompido: recusa com mensagem, sem 500
        logger.warning("Leitura de e-mail falhou (%s): %s", origem, type(exc).__name__)
        raise MensagemIlegivel(f"Não foi possível ler este arquivo ({_NOME_ORIGEM[origem]}).") from exc
    return _finalizar(mensagem)


def ler_texto_colado(texto: str) -> Mensagem:
    """Lê o texto de um e-mail (ou de uma conversa do WhatsApp) colado na tela."""
    texto = (texto or "").replace("\x00", "")
    if not texto.strip():
        raise MensagemIlegivel("Cole o texto do e-mail.")
    return _finalizar(_mensagem_de_texto(texto, "texto"))


_NOME_ORIGEM = {"msg": ".msg do Outlook", "pdf": "PDF", "eml": ".eml", "mht": ".mht", "txt": ".txt"}


def _parece_mime(dados: bytes) -> bool:
    """Cabeçalho de e-mail cru no começo (e não um "From:/Sent:/To:" colado do Outlook)."""
    inicio = dados[:4096].decode("latin-1", "replace")
    cabecalho = inicio.split("\n\n", 1)[0].split("\r\n\r\n", 1)[0]
    rotulos = [
        r.lower() for r in re.findall(
            r"^(from|to|subject|date|mime-version|received|return-path|message-id|content-type|x-[\w-]+):",
            cabecalho, re.IGNORECASE | re.MULTILINE,
        )
    ]
    tecnicos = [r for r in rotulos if r not in ("from", "to", "subject", "date")]
    return len(rotulos) >= 2 and bool(tecnicos)


def _parece_texto(dados: bytes) -> bool:
    amostra = dados[:8192]
    if b"\x00" in amostra:
        return False
    try:
        amostra.decode("utf-8")
        return True
    except UnicodeDecodeError as exc:
        if exc.start >= len(amostra) - 4:
            return True  # caractere cortado no fim da amostra
    texto = amostra.decode("cp1252", "replace")
    imprimiveis = sum(c.isprintable() or c in "\r\n\t" for c in texto)
    return imprimiveis >= 0.95 * max(1, len(texto))


def _decodificar_texto(dados: bytes) -> str:
    for codificacao in ("utf-8-sig", "cp1252"):
        try:
            return dados.decode(codificacao)
        except UnicodeDecodeError:
            continue
    return dados.decode("latin-1", "replace")


def _ler_txt(dados: bytes, origem: str) -> Mensagem:
    return _mensagem_de_texto(_decodificar_texto(dados).replace("\x00", ""), origem)


# ---------------------------------------------------------------------------
# Montagem comum: do "bruto" (cabeçalhos + texto) para a Mensagem
# ---------------------------------------------------------------------------


@dataclass
class _Bruto:
    assunto: str = ""
    remetente: tuple[str, str] = ("", "")
    enviado_em: datetime | None = None
    texto: str = ""
    anexos: list[tuple[str, bytes]] = field(default_factory=list)
    message_id: str = ""
    internas: list["_Bruto"] = field(default_factory=list)
    citado: str = ""
    avisos: list[str] = field(default_factory=list)


def _mensagem_de_texto(texto: str, origem: str) -> Mensagem:
    """Texto solto (colado, .txt, PDF): WhatsApp, impressão do Gmail ou e-mail comum."""
    whatsapp = _ler_whatsapp(texto)
    if whatsapp is not None:
        return whatsapp
    bruto = _ler_impressao_gmail(texto) or _Bruto(texto=texto)
    return _montar(bruto, origem)


def _montar(bruto: _Bruto, origem: str, profundidade: int = 0) -> Mensagem:
    if len(bruto.texto) > _MAX_CARACTERES:
        bruto.avisos.append("O texto do e-mail é muito longo; só o começo foi lido.")
    texto = _limpar_texto(bruto.texto)
    niveis, interno, citado = _desembrulhar(texto, bruto.assunto)

    # E-mail encaminhado "como anexo" (.eml ou .msg dentro do e-mail): se a
    # mensagem de fora é só um "segue", quem pediu é a de dentro.
    if bruto.internas and profundidade < _MAX_PROFUNDIDADE:
        corpo_externo, _ = separar_assinatura(interno)
        if _eh_encaminhamento(bruto.assunto) or len(corpo_externo.strip()) < 400:
            mensagem = _montar(bruto.internas[0], origem, profundidade + 1)
            mensagem.encaminhada_por = mensagem.encaminhada_por or _exibir(*bruto.remetente)
            mensagem.anexos = mensagem.anexos + bruto.anexos
            mensagem.avisos = bruto.avisos + mensagem.avisos
            mensagem.message_id = bruto.message_id or mensagem.message_id
            return mensagem

    remetente, assunto, enviado_em = bruto.remetente, bruto.assunto, bruto.enviado_em
    encaminhada_por, anexos_citados = "", []
    for nivel in niveis:
        novo = _remetente(nivel.get("de", ""))
        if any(novo):
            if any(remetente):
                encaminhada_por = _exibir(*remetente)
            remetente = novo
        assunto = nivel.get("assunto") or assunto
        enviado_em = data_hora_de_cabecalho(nivel.get("data", "")) or enviado_em
        if nivel.get("anexos"):
            anexos_citados = [n.strip() for n in re.split(r"[;,]\s*|\s{2,}", nivel["anexos"]) if n.strip()]

    interno, citado_linhas = _cortar_citacoes(interno)
    corpo, assinatura = separar_assinatura(interno)
    partes_citadas = [x for x in (bruto.citado, citado, citado_linhas) if x.strip()]
    mensagem = Mensagem(
        assunto=" ".join(assunto.split()),
        remetente_nome=remetente[0],
        remetente_email=remetente[1],
        enviado_em=_com_fuso(enviado_em),
        corpo=_arrumar_linhas(corpo),
        assinatura=_arrumar_linhas(assinatura),
        anexos=list(bruto.anexos),
        message_id=bruto.message_id.strip(),
        origem=origem,
        encaminhada_por=encaminhada_por,
        citado="\n\n".join(partes_citadas)[:_MAX_CARACTERES],
        anexos_citados=anexos_citados,
        avisos=list(bruto.avisos),
    )
    return mensagem


def _finalizar(mensagem: Mensagem) -> Mensagem:
    """Aplica os limites dos anexos e os avisos finais."""
    limite = _ajuste("LEITURA_EMAIL_ANEXO_MAX_BYTES", LEITURA_EMAIL_ANEXO_MAX_BYTES)
    maximo = _ajuste("LEITURA_EMAIL_MAX_ANEXOS", LEITURA_EMAIL_MAX_ANEXOS)
    aceitos, grandes = [], []
    for nome, dados in mensagem.anexos:
        nome = _nome_de_arquivo(nome, len(aceitos) + len(grandes) + 1)
        if len(dados) > limite:
            grandes.append(nome)
        elif len(aceitos) < maximo:
            aceitos.append((nome, dados))
    sobra = len(mensagem.anexos) - len(aceitos) - len(grandes)
    if grandes:
        mensagem.avisos.append(
            f"Anexo(s) acima de {limite / MIB:.0f} MB não foram lidos: {', '.join(grandes)}."
        )
    if sobra > 0:
        mensagem.avisos.append(f"O e-mail tem mais de {maximo} anexos; só os {maximo} primeiros foram lidos.")
    if mensagem.anexos_citados and not aceitos:
        mensagem.avisos.append(
            "O e-mail cita anexos que não vieram junto ("
            + ", ".join(mensagem.anexos_citados[:5])
            + "); se precisar deles, anexe os arquivos à parte."
        )
    mensagem.anexos = aceitos
    if not mensagem.corpo.strip() and not any("texto" in a for a in mensagem.avisos):
        mensagem.avisos.append("Não achei texto no corpo da mensagem.")
    return mensagem


def _nome_de_arquivo(nome: str, numero: int) -> str:
    nome = re.split(r"[\\/]", str(nome or ""))[-1]
    nome = "".join(c for c in nome if c.isprintable() and c not in '<>:"|?*').strip(" .")
    if not nome:
        return f"anexo-{numero}"
    if len(nome) > 150:
        base, ponto, extensao = nome.rpartition(".")
        nome = (base[:140] + "." + extensao[:9]) if ponto and len(extensao) <= 9 else nome[:150]
    return nome


def _com_fuso(valor: datetime | None) -> datetime | None:
    if valor is None or valor.tzinfo is not None:
        return valor
    try:
        from django.utils import timezone

        return timezone.make_aware(valor, timezone.get_default_timezone())
    except Exception:
        return valor


def _exibir(nome: str, email: str) -> str:
    if nome and email:
        return f"{nome} <{email}>"
    return nome or email


_R_EMAIL = re.compile(r"[\w.+'-]+@[\w-]+(?:\.[\w-]+)+")


def _remetente(valor: str) -> tuple[str, str]:
    """(nome, e-mail) de "Maria <m@x>", "Maria [mailto:m@x]", "m@x" ou "Maria"."""
    valor = " ".join(str(valor or "").split())
    if not valor:
        return "", ""
    email = ""
    mailto = re.search(r"\[mailto:([^\]]+)\]", valor, re.IGNORECASE)
    if mailto:
        email = mailto.group(1)
        valor = valor[:mailto.start()] + valor[mailto.end():]
    elif "<" in valor:
        nome, endereco = getaddresses([valor])[0] if getaddresses([valor]) else ("", "")
        if "@" in endereco:
            return nome.strip(" '\""), endereco.lower()
    if not email:
        achado = _R_EMAIL.search(valor)
        if achado:
            email = achado.group(0)
            valor = valor[:achado.start()] + valor[achado.end():]
    nome = re.sub(r"[<>()\[\]]", " ", valor)
    nome = " ".join(nome.split()).strip(" '\";,")
    email = email.strip().lower() if "@" in email else ""
    if nome.lower() == email or nome.startswith("/o="):
        nome = ""  # X.500 do Exchange ("/O=EXCHANGELABS/...") não é nome
    return nome, email


# ---------------------------------------------------------------------------
# Limpeza do texto
# ---------------------------------------------------------------------------

_INVISIVEIS = dict.fromkeys(map(ord, "\u200b\u200c\u200d\u2060\ufeff\u00ad"), None)


def _limpar_texto(texto: str) -> str:
    texto = (texto or "").replace("\r\n", "\n").replace("\r", "\n").translate(_INVISIVEIS)
    texto = re.sub(r"[\u00a0\u2007\u2009\u202f]", " ", texto)
    # Rastros do texto simples do Outlook: "[cid:image001.png@...]", "<mailto:...>", "<https://...>".
    texto = re.sub(r"\[cid:[^\]\n]{0,200}\]", "", texto)
    texto = re.sub(r"<(?:mailto:|https?://)[^>\s]{0,500}>", "", texto)
    texto = "\n".join(linha.rstrip(" \t") for linha in texto.split("\n"))
    if len(texto) > _MAX_CARACTERES:
        texto = texto[:_MAX_CARACTERES]
    return texto


def _arrumar_linhas(texto: str) -> str:
    linhas = [" ".join(linha.split()) if linha.strip() else "" for linha in (texto or "").split("\n")]
    return re.sub(r"\n{3,}", "\n\n", "\n".join(linhas)).strip()


_R_PREFIXO_ASSUNTO = re.compile(
    r"^\s*(?:\[[^\]]{0,30}\]\s*|(?:re|res|resp|fw|fwd|enc|tr|aw|wg|rv|encaminhar|encaminhado|encaminhada)"
    r"\s*(?:\[\d+\])?\s*:\s*)",
    re.IGNORECASE,
)


def assunto_sem_prefixos(assunto: str) -> str:
    """"RES: ENC: [EXTERNO] Pedido" vira "Pedido"."""
    assunto = " ".join((assunto or "").split())
    anterior = None
    while anterior != assunto:
        anterior = assunto
        assunto = _R_PREFIXO_ASSUNTO.sub("", assunto, count=1)
    return assunto.strip()


def _eh_encaminhamento(assunto: str) -> bool:
    return bool(re.match(r"^\s*(?:\[[^\]]*\]\s*)*(?:enc|fw|fwd|tr|encaminhar|encaminhad[oa])\s*:", dobrar(assunto or "")))


def _eh_resposta(assunto: str) -> bool:
    return bool(re.match(r"^\s*(?:\[[^\]]*\]\s*)*(?:res|re|resp|aw|rv)\s*:", dobrar(assunto or "")))


# ---------------------------------------------------------------------------
# HTML para texto (sem executar nada, sem seguir link)
# ---------------------------------------------------------------------------

_INICIO_CITACAO, _FIM_CITACAO = "\x0e", "\x0f"


class _ConversorHtml(HTMLParser):
    """Junta só o texto do HTML, com quebra de linha onde o navegador quebraria."""

    BLOCOS = frozenset({
        "address", "article", "aside", "blockquote", "center", "dd", "div", "dl", "dt", "fieldset",
        "figcaption", "figure", "footer", "form", "h1", "h2", "h3", "h4", "h5", "h6", "header", "hr",
        "li", "main", "nav", "ol", "pre", "section", "table", "tbody", "thead", "tfoot", "tr", "ul",
    })
    IGNORADOS = frozenset({"script", "style", "head", "title", "noscript", "template", "svg", "object", "iframe", "xml"})

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.saida: list[str] = []
        self.quebras = 2  # começo do documento conta como linha em branco
        self.ignorando = 0
        self.pre = 0

    def _escrever(self, texto: str):
        if not texto:
            return
        self.saida.append(texto)
        conteudo = texto.rstrip(" ")
        if conteudo.strip(" "):
            self.quebras = len(conteudo) - len(conteudo.rstrip("\n"))

    def _quebrar(self, quantas: int = 1):
        while self.quebras < quantas:
            self.saida.append("\n")
            self.quebras += 1

    def handle_starttag(self, tag, attrs):
        if tag in self.IGNORADOS:
            self.ignorando += 1
            return
        if self.ignorando:
            return
        if tag == "br":
            self.saida.append("\n")
            self.quebras += 1
        elif tag == "p":
            classe = (dict(attrs).get("class") or "").lower()
            # O "MsoNormal" do Outlook é uma linha, não um parágrafo com espaço.
            self._quebrar(1 if "msonormal" in classe else 2)
        elif tag in self.BLOCOS:
            self._quebrar(1)
        if tag == "blockquote":
            self.saida.append(_INICIO_CITACAO)
        elif tag in ("td", "th"):
            self.saida.append(" ")
        elif tag == "li":
            self._escrever("- ")
        elif tag == "pre":
            self.pre += 1

    def handle_endtag(self, tag):
        if tag in self.IGNORADOS:
            self.ignorando = max(0, self.ignorando - 1)
            return
        if self.ignorando:
            return
        if tag == "blockquote":
            self._quebrar(1)
            self.saida.append(_FIM_CITACAO)
        elif tag == "p":
            self._quebrar(1)
        elif tag in self.BLOCOS:
            self._quebrar(1)
        if tag == "pre":
            self.pre = max(0, self.pre - 1)

    def handle_data(self, data):
        if self.ignorando:
            return
        data = data.replace(_INICIO_CITACAO, "").replace(_FIM_CITACAO, "")
        if not self.pre:
            data = re.sub(r"[ \t\r\n\f]+", " ", data)
        self._escrever(data)

    def texto(self) -> str:
        bruto = "".join(self.saida).replace("\u00a0", " ")
        linhas, profundidade = [], 0
        for linha in bruto.split("\n"):
            no_inicio = profundidade
            conteudo = []
            for caractere in linha:
                if caractere == _INICIO_CITACAO:
                    profundidade += 1
                elif caractere == _FIM_CITACAO:
                    profundidade = max(0, profundidade - 1)
                else:
                    conteudo.append(caractere)
            conteudo = "".join(conteudo).strip()
            nivel = max(no_inicio, profundidade)
            linhas.append(("> " * nivel + conteudo) if nivel and conteudo else conteudo)
        return re.sub(r"\n{3,}", "\n\n", "\n".join(linhas)).strip()


def html_para_texto(html: str) -> str:
    """O texto de um HTML de e-mail, com as quebras de linha preservadas.

    Parágrafos, <br>, <div>, linhas de tabela e itens de lista viram quebra
    de linha (sem isso os parágrafos grudam: "Bom dia,Solicitamos"). Script,
    estilo e cabeçalho são descartados; links e imagens nunca são seguidos.
    Texto dentro de <blockquote> (resposta citada) sai prefixado com "> ".
    """
    conversor = _ConversorHtml()
    try:
        conversor.feed(html or "")
        conversor.close()
    except Exception:  # HTML muito quebrado: fica o que já foi lido
        logger.info("HTML de e-mail malformado; usando o texto parcial.")
    return conversor.texto()


# ---------------------------------------------------------------------------
# Encaminhamentos, citações e cabeçalhos no meio do texto
# ---------------------------------------------------------------------------

_ROTULOS = {
    "de": "de", "from": "de",
    "enviado em": "data", "enviada em": "data", "enviado": "data", "enviada": "data", "sent": "data",
    "data": "data", "date": "data",
    "para": "para", "to": "para", "cc": "cc", "cco": "cc", "bcc": "cc",
    "assunto": "assunto", "subject": "assunto",
    "anexos": "anexos", "anexo": "anexos", "attachments": "anexos",
    "importancia": "outro", "importance": "outro", "prioridade": "outro",
    "responder a": "outro", "reply-to": "outro",
}
_R_ROTULO = re.compile(
    r"^[\s*]*(" + "|".join(re.escape(r) for r in sorted(_ROTULOS, key=len, reverse=True)) + r")[\s*]*:[\s*]*"
)
_R_MARCA_ENCAMINHADA = re.compile(
    r"^\s*(?:-{2,}\s*)?(?:forwarded message|mensagem encaminhada|begin forwarded message|"
    r"inicio da mensagem encaminhada)\s*:?[\s-]*$"
)
_R_MARCA_ORIGINAL = re.compile(r"^\s*-{2,}\s*(?:original message|mensagem original)\s*-{2,}\s*$")
_R_SEPARADOR = re.compile(r"^\s*_{8,}\s*$")
_R_ESCREVEU = re.compile(r"^\s*(?:em|on|no dia)\s.{4,400}?(?:escreveu|wrote|a ecrit)\s*:\s*$")


_R_LISTA_DE_ARQUIVOS = re.compile(r"^(?:[^;:]{1,120}\.[A-Za-z0-9]{2,5}\s*(?:\(\s*[\d.,]+\s*[KMG]?B\s*\))?\s*;?\s*)+$")


def _continua_o_cabecalho(chave: str | None, valor: str, linha: str) -> bool:
    """A linha continua "Para:", "Cc:" ou "Anexos:" da linha de cima?

    O texto de PDF não tem linha em branco depois do cabeçalho: sem esta
    conferência, o corpo inteiro viraria destinatário ou anexo.
    """
    linha = linha.strip()
    if chave in ("para", "cc"):
        return valor.rstrip().endswith((";", ",")) or ("@" in linha and len(linha.split()) <= 12)
    if chave == "anexos":
        return bool(_R_LISTA_DE_ARQUIVOS.match(linha))
    return False


def _bloco_de_cabecalho(linhas, dobradas, i, *, minimo: int = 3):
    """(fim, campos) do bloco "De:/Enviado em:/Para:/Assunto:" que começa na linha i."""
    campos: dict[str, str] = {}
    ultimo = None
    j = i
    while j < len(linhas) and j < i + 25:
        m = _R_ROTULO.match(dobradas[j]) if len(dobradas[j]) <= _MAX_LINHA_CABECALHO else None
        if m:
            chave = _ROTULOS[m.group(1)]
            if chave != "outro" and chave in campos:
                break
            campos[chave] = linhas[j][m.end():].strip()
            ultimo = chave
            j += 1
            continue
        if not linhas[j].strip():
            break
        if _continua_o_cabecalho(ultimo, campos.get(ultimo, ""), linhas[j]):
            campos[ultimo] += " " + linhas[j].strip()
            j += 1
            continue
        break
    campos.pop("outro", None)
    if "de" in campos and ("data" in campos or "assunto" in campos) and len(campos) >= minimo:
        return j, campos
    return None


def _proxima_fronteira(linhas: list[str]):
    """O primeiro encaminhamento, cabeçalho ou citação do texto.

    Devolve (tipo, início, fim, campos): tipo "encaminhada" (marca explícita),
    "bloco" (cabeçalho De:/Assunto:, com ou sem "-----Mensagem original-----")
    ou "resposta" ("Em ..., Fulano escreveu:").
    """
    dobradas = [dobrar(linha) for linha in linhas]
    for i, linha in enumerate(dobradas):
        if not linha.strip() or len(linha) > _MAX_LINHA_CABECALHO:
            continue
        if _R_MARCA_ENCAMINHADA.match(linha):
            for k in range(i + 1, min(i + 4, len(linhas))):
                if not linhas[k].strip():
                    continue
                desquotadas = [re.sub(r"^\s*>\s?", "", x) for x in linhas]
                bloco = _bloco_de_cabecalho(desquotadas, [dobrar(x) for x in desquotadas], k, minimo=2)
                if bloco:
                    return "encaminhada", i, bloco[0], bloco[1]
                break
            return "encaminhada", i, i + 1, {}
        if _R_MARCA_ORIGINAL.match(linha) or _R_SEPARADOR.match(linha):
            k = next((k for k in range(i + 1, min(i + 4, len(linhas))) if linhas[k].strip()), None)
            bloco = _bloco_de_cabecalho(linhas, dobradas, k, minimo=2) if k is not None else None
            if bloco:
                return "bloco", i, bloco[0], bloco[1]
            if _R_MARCA_ORIGINAL.match(linha):
                return "resposta", i, None, None
            continue
        if linha.lstrip().startswith(("em ", "on ", "no dia ")):
            # "Em qui., 24 de set. de 2026 às 14:32, Maria <m@x>\nescreveu:" pode quebrar a linha.
            for fim in range(i, min(i + 3, len(linhas))):
                if _R_ESCREVEU.match(" ".join(dobradas[i:fim + 1])):
                    return "resposta", i, None, None
        if _R_ROTULO.match(linha):
            bloco = _bloco_de_cabecalho(linhas, dobradas, i)
            if bloco:
                return "bloco", i, bloco[0], bloco[1]
    return None


def _desembrulhar(texto: str, assunto: str) -> tuple[list[dict], str, str]:
    """Desce até a mensagem mais interna e corta a resposta citada.

    Devolve (cabeçalhos achados no texto, do mais externo ao mais interno;
    texto da mensagem mais interna; o que foi cortado como citação).
    Cabeçalho depois de texto, com assunto "RES:", é resposta citada (corta);
    com "ENC:", marca de encaminhamento ou sem pista, é encaminhamento (desce).
    """
    linhas = texto.split("\n")
    niveis: list[dict] = []
    citado: list[str] = []
    assunto_atual = assunto
    for _ in range(12):
        fronteira = _proxima_fronteira(linhas)
        if fronteira is None:
            break
        tipo, inicio, fim, campos = fronteira
        antes = "\n".join(linhas[:inicio]).strip()
        if tipo == "resposta" or (tipo == "bloco" and antes and _eh_resposta(assunto_atual)):
            citado.append("\n".join(linhas[inicio:]).strip())
            linhas = linhas[:inicio]
            break
        seguintes = linhas[fim:]
        if tipo == "encaminhada":
            citadas = [x for x in seguintes if x.strip()]
            if citadas and sum(x.lstrip().startswith(">") for x in citadas) >= 0.8 * len(citadas):
                seguintes = [re.sub(r"^\s*>\s?", "", x) for x in seguintes]  # Apple Mail
        if campos:
            niveis.append(campos)
            assunto_atual = campos.get("assunto") or assunto_atual
        linhas = seguintes
    return niveis, "\n".join(linhas), "\n\n".join(citado)


def _cortar_citacoes(texto: str) -> tuple[str, str]:
    """Tira as linhas citadas ("> ...") que sobraram no meio do texto."""
    ficam, citadas = [], []
    for linha in texto.split("\n"):
        (citadas if linha.lstrip().startswith(">") else ficam).append(linha)
    return "\n".join(ficam), "\n".join(citadas)


# ---------------------------------------------------------------------------
# Assinatura e rodapé
# ---------------------------------------------------------------------------

_R_FECHO = re.compile(
    r"^\s*(?:att\.?|atte\.?|atenciosamente|cordialmente|respeitosamente|saudacoes|abracos?|abs\.?|"
    r"um abraco|grat[oa]|obrigad[oa]|agradeco(?: desde ja)?|sds\.?|best regards|kind regards|regards)"
    r"(?=[\s,.!;:]|$)[\s,.!;:]*(?P<resto>.*)$"
)
_R_ENVIADO_DO = re.compile(r"^\s*(?:enviado do meu|enviado de meu|enviado a partir d|sent from my|obter o outlook|get outlook)\b")
_R_RODAPE = re.compile(
    r"(?:confidencial|confidential|destinatario\(?s?\)?\s+(?:indicado|exclusivo|especific)|mensagem\s+e\s+seus\s+anexos|"
    r"this\s+(?:e-?mail|message)\s+(?:and|is|may)|antes\s+de\s+imprimir|aviso\s+legal|privilegiad|sigilos|"
    r"informacao\s+protegida|lgpd)"
)
_R_CARGO = re.compile(
    r"\b(?:diretor|diretora|coordenador|coordenadora|secretari|prefeit|assessor|chefe|delegad|investigador|"
    r"escriva|professor|pedagog|presidente|gerente|analista|tecnic|agente|supervisor|orientador|vereador|"
    r"comandante|capitao|tenente|sargento|reporter|produtor|jornalista|editor|redacao|assistente|auxiliar|"
    r"servidor|policial|papiloscopista|perito|psicolog|assistente social|vice)"
)
_R_CONTATO = re.compile(r"(?:\(?\d{2}\)?\s*9?\d{4}[-.\s]?\d{4})|@[\w-]+\.|\b(?:tel|fone|telefone|celular|cel|whatsapp|ramal)\b")
_R_NOME = re.compile(r"^[A-ZÀ-Ý][\w'.-]+(?:\s+(?:d[aeo]s?|e|[A-ZÀ-Ý][\w'.-]*)){1,7}$")


def separar_assinatura(texto: str) -> tuple[str, str]:
    """(corpo, assinatura) de uma mensagem.

    A assinatura começa depois do fecho ("Att", "Atenciosamente",
    "Cordialmente", "Respeitosamente", "--"); sem fecho, é o último bloco
    curto que começa com um nome e tem telefone, e-mail ou cargo. O rodapé
    legal ("mensagem confidencial…") e o "Enviado do meu iPhone" saem dos dois.
    """
    linhas = [linha for linha in (texto or "").split("\n") if not _R_ENVIADO_DO.match(dobrar(linha))]
    dobradas = [dobrar(linha) for linha in linhas]
    # Rodapé legal: do parágrafo que o contém até o fim (só na segunda metade).
    inicio_paragrafo = 0
    for i, linha in enumerate(dobradas):
        if not linha.strip():
            inicio_paragrafo = i + 1
            continue
        if i >= len(linhas) * 0.4 and _R_RODAPE.search(linha):
            linhas, dobradas = linhas[:inicio_paragrafo], dobradas[:inicio_paragrafo]
            break

    # Do fim para o começo: quantas linhas com texto restam e a maior delas.
    restantes, maior = [0] * (len(linhas) + 1), [0] * (len(linhas) + 1)
    for k in range(len(linhas) - 1, -1, -1):
        tamanho = len(linhas[k].strip())
        restantes[k] = restantes[k + 1] + (1 if tamanho else 0)
        maior[k] = max(maior[k + 1], tamanho)

    def curto_ate_o_fim(k: int) -> bool:
        return restantes[k] <= 12 and maior[k] <= 120

    tem_texto_antes = False
    for i, linha in enumerate(dobradas):
        if len(linha) > _MAX_LINHA_CABECALHO:
            tem_texto_antes = True
            continue
        if re.fullmatch(r"\s*--\s*", linha) and tem_texto_antes:
            return "\n".join(linhas[:i]).strip(), "\n".join(linhas[i + 1:]).strip()
        tem_texto_antes = tem_texto_antes or bool(linha.strip())
        fecho = _R_FECHO.match(linha)
        if fecho and curto_ate_o_fim(i + 1):
            resto = linhas[i][len(linhas[i]) - len(fecho.group("resto")):].strip() if fecho.group("resto") else ""
            assinatura = "\n".join(([resto] if resto else []) + linhas[i + 1:]).strip()
            return "\n".join(linhas[:i]).strip(), assinatura

    # Sem fecho: o último bloco, se parecer assinatura.
    texto_limpo = "\n".join(linhas).strip()
    blocos = re.split(r"\n\s*\n", texto_limpo)
    if len(blocos) >= 2:
        ultimo = [x.strip() for x in blocos[-1].split("\n") if x.strip()]
        ultimo_dobrado = dobrar("\n".join(ultimo))
        if (
            2 <= len(ultimo) <= 7
            and all(len(x) <= 80 for x in ultimo)
            and _R_NOME.match(ultimo[0])
            and (_R_CONTATO.search(ultimo_dobrado) or _R_CARGO.search(ultimo_dobrado))
        ):
            return "\n\n".join(blocos[:-1]).strip(), "\n".join(ultimo)
    return texto_limpo, ""


# ---------------------------------------------------------------------------
# .eml e .mht
# ---------------------------------------------------------------------------


def _ler_eml(dados: bytes, origem: str) -> Mensagem:
    email = BytesParser(policy=policy.default).parsebytes(dados)
    return _montar(_bruto_de_email(email, 0), origem)


def _cabecalho(email, nome: str) -> str:
    try:
        valor = email.get(nome)
        return str(valor) if valor is not None else ""
    except Exception:  # cabeçalho malformado
        return ""


def _texto_da_parte(parte) -> str:
    try:
        conteudo = parte.get_content()
        if isinstance(conteudo, bytes):
            raise LookupError
        return conteudo
    except Exception:
        dados = parte.get_payload(decode=True) or b""
        charset = parte.get_content_charset() or "utf-8"
        try:
            return dados.decode(charset, "replace")
        except LookupError:
            return dados.decode("latin-1", "replace")


def _partes_folha(email):
    """As partes que não são multipart, em ordem, sem entrar em e-mail anexado."""
    pendentes = [email]
    contadas = 0
    while pendentes and contadas < _MAX_PARTES_MIME:
        parte = pendentes.pop(0)
        contadas += 1
        if parte.is_multipart() and parte.get_content_maintype() == "multipart":
            pendentes[0:0] = list(parte.iter_parts())
            continue
        yield parte


def _bruto_de_email(email, profundidade: int) -> _Bruto:
    bruto = _Bruto(
        assunto=_cabecalho(email, "subject"),
        remetente=_remetente(_cabecalho(email, "from")),
        message_id=_cabecalho(email, "message-id"),
    )
    data = _cabecalho(email, "date")
    if data:
        try:
            bruto.enviado_em = parsedate_to_datetime(data)
        except (TypeError, ValueError, IndexError):
            bruto.enviado_em = data_hora_de_cabecalho(data)
    try:
        corpo = email.get_body(preferencelist=("plain", "html"))
    except Exception:
        corpo = None
    if corpo is not None:
        texto = _texto_da_parte(corpo)
        if corpo.get_content_type() == "text/html":
            texto = html_para_texto(texto)
        elif not texto.strip():
            try:
                html = email.get_body(preferencelist=("html",))
            except Exception:
                html = None
            if html is not None:
                texto = html_para_texto(_texto_da_parte(html))
        bruto.texto = texto
    numero = 0
    for parte in _partes_folha(email):
        if parte is corpo:
            continue
        tipo = parte.get_content_type()
        disposicao = parte.get_content_disposition()
        if tipo == "message/rfc822":
            if profundidade < _MAX_PROFUNDIDADE:
                carga = parte.get_payload()
                interna = carga[0] if isinstance(carga, list) and carga else None
                if interna is not None:
                    bruto.internas.append(_bruto_de_email(interna, profundidade + 1))
            continue
        nome = parte.get_filename()
        if tipo in ("text/plain", "text/html") and not nome and disposicao != "attachment":
            continue  # a outra versão do corpo (multipart/alternative)
        if parte.get("Content-ID") and disposicao != "attachment" and parte.get_content_maintype() == "image":
            continue  # imagem da assinatura, no corpo do HTML
        numero += 1
        dados = parte.get_payload(decode=True) or b""
        bruto.anexos.append((nome or f"anexo-{numero}", dados))
    return bruto


# ---------------------------------------------------------------------------
# .msg do Outlook (OLE2/CFB, streams MAPI)
# ---------------------------------------------------------------------------

# Propriedades MAPI (id de 4 dígitos hexa) usadas aqui.
_PR_ASSUNTO = "0037"
_PR_CABECALHOS_TRANSPORTE = "007D"
_PR_NOME_REMETENTE = ("0C1A", "0042")
_PR_EMAIL_REMETENTE = ("5D01", "5D02", "0C1F", "0065")
_PR_MESSAGE_ID = "1035"
_PR_CORPO = "1000"
_PR_HTML = "1013"
_PR_RTF_COMPRIMIDO = "1009"
_PR_ANEXO_DADOS = "3701"
_PR_ANEXO_NOMES = ("3707", "3704", "3001")
_PR_ANEXO_CONTENT_ID = "3712"
_PR_ANEXO_MIME = "370E"
_ID_METODO_ANEXO = 0x3705
_ID_ANEXO_OCULTO = 0x7FFE
_IDS_DATA = (0x0039, 0x0E06, 0x3007)   # envio, entrega, criação
_ID_CODEPAGE = (0x3FFD, 0x3FDE)
_TIPO_DATA = 0x0040
_ANEXO_EMBUTIDO = 5


class _LeitorMsg:
    """Lê streams e propriedades MAPI de um .msg aberto com olefile."""

    def __init__(self, ole):
        self.ole = ole

    def stream(self, caminho: list[str]) -> bytes | None:
        try:
            if not self.ole.exists("/".join(caminho)):
                return None
            with self.ole.openstream(caminho) as fluxo:
                return fluxo.read()
        except Exception:
            return None

    def texto(self, base: list[str], propriedade: str, codepage: str) -> str:
        dados = self.stream(base + [f"__substg1.0_{propriedade}001F"])
        if dados is not None:
            return dados.decode("utf-16-le", "replace").rstrip("\x00")
        dados = self.stream(base + [f"__substg1.0_{propriedade}001E"])
        if dados is not None:
            return dados.decode(codepage, "replace").rstrip("\x00")
        return ""

    def binario(self, base: list[str], propriedade: str) -> bytes | None:
        return self.stream(base + [f"__substg1.0_{propriedade}0102"])

    def propriedades(self, base: list[str], cabecalho: int) -> dict[int, tuple[int, bytes]]:
        """{id: (tipo, 8 bytes do valor)} do stream "__properties_version1.0"."""
        dados = self.stream(base + ["__properties_version1.0"]) or b""
        props = {}
        for inicio in range(cabecalho, len(dados) - 15, 16):
            etiqueta, _flags = struct.unpack_from("<II", dados, inicio)
            props[etiqueta >> 16] = (etiqueta & 0xFFFF, dados[inicio + 8:inicio + 16])
        return props

    def armazenamentos(self, base: list[str], prefixo: str) -> list[list[str]]:
        filhos = []
        for caminho in self.ole.listdir(streams=False, storages=True):
            if len(caminho) == len(base) + 1 and [c.lower() for c in caminho[:-1]] == [c.lower() for c in base]:
                if caminho[-1].lower().startswith(prefixo.lower()):
                    filhos.append(caminho)
        return sorted(filhos, key=lambda c: c[-1].lower())


def _codec(numero: int | None, padrao: str = "cp1252") -> str:
    if not numero:
        return padrao
    nome = {65001: "utf-8", 28591: "latin-1", 20127: "ascii", 1200: "utf-16-le"}.get(numero, f"cp{numero}")
    try:
        codecs.lookup(nome)
        return nome
    except LookupError:
        return padrao


def _inteiro(valor: tuple[int, bytes] | None) -> int | None:
    return struct.unpack_from("<I", valor[1])[0] if valor else None


def _filetime(valor: tuple[int, bytes] | None) -> datetime | None:
    if not valor or valor[0] != _TIPO_DATA:
        return None
    centenas_de_ns = struct.unpack_from("<Q", valor[1])[0]
    if not centenas_de_ns:
        return None
    try:
        return datetime(1601, 1, 1, tzinfo=tz_utc.utc) + timedelta(microseconds=centenas_de_ns // 10)
    except OverflowError:
        return None


def _ler_msg(dados: bytes, origem: str) -> Mensagem:
    import olefile

    if not olefile.isOleFile(data=dados):
        raise MensagemIlegivel("O arquivo .msg está corrompido.")
    ole = olefile.OleFileIO(dados)
    try:
        leitor = _LeitorMsg(ole)
        if not leitor.stream(["__properties_version1.0"]) and not ole.exists("__substg1.0_0037001F") \
                and not ole.exists("__substg1.0_0037001E") and not ole.exists("__substg1.0_1000001F"):
            raise MensagemIlegivel("Este arquivo do Office não é um e-mail do Outlook (.msg).")
        bruto = _bruto_de_msg(leitor, [], 32, 0)
    finally:
        ole.close()
    return _montar(bruto, origem)


def _bruto_de_msg(leitor: _LeitorMsg, base: list[str], cabecalho: int, profundidade: int) -> _Bruto:
    props = leitor.propriedades(base, cabecalho)
    codepage = _codec(next((_inteiro(props.get(i)) for i in _ID_CODEPAGE if props.get(i)), None))
    bruto = _Bruto(assunto=leitor.texto(base, _PR_ASSUNTO, codepage))
    transporte = leitor.texto(base, _PR_CABECALHOS_TRANSPORTE, codepage)
    cabecalhos = HeaderParser(policy=policy.default).parsestr(transporte) if transporte.strip() else None
    de_cabecalho = _remetente(_cabecalho(cabecalhos, "from")) if cabecalhos is not None else ("", "")
    nome = next((n for n in (leitor.texto(base, p, codepage) for p in _PR_NOME_REMETENTE) if n.strip()), "")
    emails = [leitor.texto(base, p, codepage) for p in _PR_EMAIL_REMETENTE]
    email = next((e.strip().lower() for e in [emails[0], emails[1], de_cabecalho[1], *emails[2:]] if "@" in e), "")
    bruto.remetente = (nome.strip() or de_cabecalho[0], email)
    if cabecalhos is not None and _cabecalho(cabecalhos, "date"):
        try:
            bruto.enviado_em = parsedate_to_datetime(_cabecalho(cabecalhos, "date"))
        except (TypeError, ValueError, IndexError):
            bruto.enviado_em = None
    if bruto.enviado_em is None:
        bruto.enviado_em = next((d for d in (_filetime(props.get(i)) for i in _IDS_DATA) if d), None)
    bruto.message_id = leitor.texto(base, _PR_MESSAGE_ID, codepage) or (
        _cabecalho(cabecalhos, "message-id") if cabecalhos is not None else ""
    )

    texto = leitor.texto(base, _PR_CORPO, codepage)
    if not texto.strip():
        html = leitor.binario(base, _PR_HTML)
        html_texto = _decodificar_html(html, codepage) if html else leitor.texto(base, _PR_HTML, codepage)
        texto = html_para_texto(html_texto) if html_texto.strip() else ""
    if not texto.strip():
        rtf = leitor.binario(base, _PR_RTF_COMPRIMIDO)
        if rtf:
            try:
                texto = _rtf_para_texto(_descomprimir_rtf(rtf))
            except ValueError:
                bruto.avisos.append("O corpo do .msg está num formato que não deu para ler.")
    bruto.texto = texto

    for numero, armazenamento in enumerate(leitor.armazenamentos(base, "__attach_version1.0_"), start=1):
        aprops = leitor.propriedades(armazenamento, 8)
        embutida = armazenamento + ["__substg1.0_3701000D"]
        if _inteiro(aprops.get(_ID_METODO_ANEXO)) == _ANEXO_EMBUTIDO or leitor.ole.exists("/".join(embutida)):
            if profundidade < _MAX_PROFUNDIDADE and leitor.ole.exists("/".join(embutida)):
                bruto.internas.append(_bruto_de_msg(leitor, embutida, 24, profundidade + 1))
            continue
        dados = leitor.binario(armazenamento, _PR_ANEXO_DADOS)
        if dados is None:
            continue
        mime = leitor.texto(armazenamento, _PR_ANEXO_MIME, codepage).lower()
        oculto = bool(_inteiro(aprops.get(_ID_ANEXO_OCULTO)))
        if mime.startswith("image/") and (oculto or leitor.texto(armazenamento, _PR_ANEXO_CONTENT_ID, codepage)):
            continue  # imagem da assinatura, no corpo do HTML
        nome_anexo = next((n for n in (leitor.texto(armazenamento, p, codepage) for p in _PR_ANEXO_NOMES) if n.strip()), "")
        bruto.anexos.append((nome_anexo or f"anexo-{numero}", dados))
    return bruto


def _decodificar_html(html: bytes, codepage: str) -> str:
    declarado = re.search(rb"charset\s*=\s*[\"']?([\w-]+)", html[:4096], re.IGNORECASE)
    candidatos = [declarado.group(1).decode("ascii", "ignore")] if declarado else []
    for codificacao in candidatos + ["utf-8", codepage]:
        try:
            return html.decode(codificacao)
        except (UnicodeDecodeError, LookupError):
            continue
    return html.decode("latin-1", "replace")


# RTF comprimido (MS-OXRTFCP): dicionário de 4096 bytes que começa com este texto.
_PREFIXO_RTF = (
    b"{\\rtf1\\ansi\\mac\\deff0\\deftab720{\\fonttbl;}{\\f0\\fnil \\froman \\fswiss \\fmodern \\fscript "
    b"\\fdecor MS Sans SerifSymbolArialTimes New RomanCourier{\\colortbl\\red0\\green0\\blue0\r\n\\par "
    b"\\pard\\plain\\f0\\fs20\\b\\i\\u\\tab\\tx"
)
_RTF_COMPRIMIDO = 0x75465A4C    # "LZFu"
_RTF_SEM_COMPRESSAO = 0x414C454D  # "MELA"


def _descomprimir_rtf(dados: bytes) -> bytes:
    """Descomprime o PR_RTF_COMPRESSED do Outlook (LZFu, MS-OXRTFCP)."""
    if len(dados) < 16:
        raise ValueError("RTF comprimido curto demais")
    tamanho_comprimido, tamanho_bruto, assinatura, _crc = struct.unpack_from("<IIII", dados)
    corpo = dados[16:4 + tamanho_comprimido]
    maximo = min(tamanho_bruto, _MAX_RTF_BYTES)
    if assinatura == _RTF_SEM_COMPRESSAO:
        return corpo[:maximo]
    if assinatura != _RTF_COMPRIMIDO:
        raise ValueError("RTF comprimido com assinatura desconhecida")
    dicionario = bytearray(4096)
    dicionario[:len(_PREFIXO_RTF)] = _PREFIXO_RTF
    escrita = len(_PREFIXO_RTF)
    saida = bytearray()
    i, n = 0, len(corpo)
    while i < n and len(saida) < maximo:
        controle = corpo[i]
        i += 1
        for bit in range(8):
            if i >= n:
                break
            if controle & (1 << bit):
                if i + 2 > n:
                    return bytes(saida[:maximo])
                referencia = (corpo[i] << 8) | corpo[i + 1]
                i += 2
                deslocamento, comprimento = referencia >> 4, (referencia & 0xF) + 2
                if deslocamento == escrita:
                    return bytes(saida[:maximo])  # fim marcado pelo próprio fluxo
                for k in range(comprimento):
                    byte = dicionario[(deslocamento + k) % 4096]
                    saida.append(byte)
                    dicionario[escrita] = byte
                    escrita = (escrita + 1) % 4096
            else:
                byte = corpo[i]
                i += 1
                saida.append(byte)
                dicionario[escrita] = byte
                escrita = (escrita + 1) % 4096
    return bytes(saida[:maximo])


_R_TOKEN_RTF = re.compile(
    rb"\\([a-zA-Z]{1,32})(-?\d{1,10})? ?|\\'([0-9a-fA-F]{2})|\\([^a-zA-Z])|([{}])|([^\\{}\r\n]+)|[\r\n]+"
)
_DESTINOS_RTF_IGNORADOS = frozenset({
    b"fonttbl", b"colortbl", b"stylesheet", b"info", b"pict", b"object", b"header", b"footer", b"headerl",
    b"headerr", b"footerl", b"footerr", b"themedata", b"colorschememapping", b"latentstyles", b"datastore",
    b"xmlnstbl", b"listtable", b"listoverridetable", b"rsidtbl", b"generator", b"filetbl", b"revtbl",
    b"fldinst", b"mmathPr", b"pntext", b"pntxta", b"pntxtb",
})
_PALAVRAS_RTF = {
    b"par": "\n", b"line": "\n", b"row": "\n", b"sect": "\n", b"page": "\n", b"tab": "\t", b"cell": " ",
    b"emdash": "—", b"endash": "–", b"bullet": "•", b"lquote": "‘", b"rquote": "’",
    b"ldblquote": "“", b"rdblquote": "”", b"emspace": " ", b"enspace": " ", b"qmspace": " ",
}


def _rtf_para_texto(rtf: bytes) -> str:
    """O texto de um RTF (inclusive o HTML encapsulado pelo Outlook, \\fromhtml1)."""
    declarado = re.search(rb"\\ansicpg(\d+)", rtf[:4096])
    codepage = _codec(int(declarado.group(1)) if declarado else None)
    pilha: list[tuple[bool, int]] = []
    ignorar, uc, pular = False, 1, 0
    saida: list[str] = []
    pendentes = bytearray()
    novo_grupo = False

    def escrever(texto: str):
        if pendentes:
            saida.append(pendentes.decode(codepage, "replace"))
            pendentes.clear()
        saida.append(texto)

    for m in _R_TOKEN_RTF.finditer(rtf):
        palavra, parametro, hexa, simbolo, chave, trecho = m.groups()
        if chave == b"{":
            pilha.append((ignorar, uc))
            novo_grupo = True
            continue
        if chave == b"}":
            ignorar, uc = pilha.pop() if pilha else (False, 1)
            novo_grupo = False
            continue
        comeco_de_grupo, novo_grupo = novo_grupo, False
        if simbolo == b"*":
            ignorar = ignorar or comeco_de_grupo
            continue
        if palavra is not None:
            if comeco_de_grupo and palavra in _DESTINOS_RTF_IGNORADOS:
                ignorar = True
            if ignorar:
                continue
            if palavra == b"uc" and parametro:
                uc = int(parametro)
            elif palavra == b"u" and parametro:
                codigo = int(parametro)
                escrever(chr(codigo + 65536 if codigo < 0 else codigo))
                pular = uc
            elif palavra in _PALAVRAS_RTF:
                escrever(_PALAVRAS_RTF[palavra])
            continue
        if ignorar:
            continue
        if pular:
            if hexa is not None or simbolo is not None:
                pular -= 1
                continue
            if trecho:
                corte = min(pular, len(trecho))
                trecho, pular = trecho[corte:], pular - corte
                if not trecho:
                    continue
        if hexa is not None:
            pendentes.append(int(hexa, 16))
        elif simbolo is not None:
            escrever({b"~": " ", b"-": "", b"_": "-"}.get(simbolo, simbolo.decode("latin-1")))
        elif trecho:
            escrever(trecho.decode(codepage, "replace"))
    escrever("")
    return "".join(saida)


# ---------------------------------------------------------------------------
# PDF impresso (Outlook, Gmail)
# ---------------------------------------------------------------------------

_R_RUIDO_IMPRESSAO = [
    re.compile(r"^\s*https?://\S+\s*(?:\d+/\d+\s*)?$"),             # rodapé do navegador
    re.compile(r"^\s*\d+/\d+\s*$"),                                  # "1/2"
    re.compile(r"^\s*about:blank\s*(?:\d+/\d+\s*)?$"),
    re.compile(r"^\s*\d{1,2}/\d{1,2}/\d{2,4},?\s+\d{1,2}:\d{2}(?:\s*[ap]m)?\s+.*\b(?:gmail|outlook|mail)\b.*$"),
    re.compile(r"^\s*\[(?:texto das mensagens anteriores oculto|quoted text hidden)\]\s*$"),
]


def _ler_pdf(dados: bytes, origem: str) -> Mensagem:
    from pypdf import PdfReader

    try:
        leitor = PdfReader(io.BytesIO(dados))
        if leitor.is_encrypted and not leitor.decrypt(""):
            raise MensagemIlegivel("O PDF está protegido por senha.")
        total = len(leitor.pages)
        textos = [(pagina.extract_text() or "") for pagina in leitor.pages[:_MAX_PAGINAS_PDF]]
    except MensagemIlegivel:
        raise
    except Exception as exc:
        raise MensagemIlegivel("Não foi possível abrir o PDF.") from exc
    avisos = []
    if total > _MAX_PAGINAS_PDF:
        avisos.append(f"Só as primeiras {_MAX_PAGINAS_PDF} páginas do PDF foram lidas.")
    texto = "\n".join(textos)
    if not texto.strip():
        texto = _texto_por_ocr(dados, min(total, _MAX_PAGINAS_OCR))
        if texto.strip():
            avisos.append("O PDF é imagem: o texto foi lido por OCR e pode ter erros. Confira os campos.")
        else:
            avisos.append("O PDF não tem texto (parece imagem escaneada); preencha os campos à mão.")
    linhas = [
        linha for linha in texto.replace("\r", "\n").split("\n")
        if len(linha) > _MAX_LINHA_CABECALHO or not any(r.match(dobrar(linha)) for r in _R_RUIDO_IMPRESSAO)
    ]
    mensagem = _mensagem_de_texto("\n".join(linhas), origem)
    mensagem.avisos = avisos + mensagem.avisos
    return mensagem


def _texto_por_ocr(dados: bytes, paginas: int) -> str:
    """OCR das primeiras páginas, se o módulo de OCR existir e o tesseract estiver instalado."""
    try:
        from . import ocr
    except ImportError:
        return ""
    try:
        if not ocr.disponivel():
            return ""
        return "\n".join(ocr.texto_da_pagina(dados, indice) or "" for indice in range(paginas))
    except Exception as exc:
        logger.warning("OCR do e-mail em PDF falhou: %s", type(exc).__name__)
        return ""


_R_GMAIL_CONTAGEM = re.compile(r"^\s*\d+\s+(?:mensage(?:m|ns)|messages?)\s*$")
_R_GMAIL_REMETENTE = re.compile(r"^\s*(?P<nome>[^<>\n]{0,120}?)\s*<(?P<email>[^<>\s@]+@[^<>\s]+)>\s*(?P<resto>.*)$")
_R_GMAIL_CABECALHO = re.compile(r"^\s*(?:para|to|cc|cco|bcc|responder a|reply-to)\s*:", re.IGNORECASE)


def _ler_impressao_gmail(texto: str) -> _Bruto | None:
    """A conversa impressa do Gmail: assunto, "N mensagens" e cada mensagem.

    Vale a primeira mensagem (o pedido original); as seguintes vão para as
    citações.
    """
    linhas = texto.replace("\r", "\n").split("\n")
    contagem = next((i for i, linha in enumerate(linhas[:25]) if _R_GMAIL_CONTAGEM.match(dobrar(linha))), None)
    if contagem is None:
        return None
    assunto = next((linhas[k].strip() for k in range(contagem - 1, -1, -1) if linhas[k].strip()), "")
    inicios = []
    for i in range(contagem + 1, len(linhas)):
        m = _R_GMAIL_REMETENTE.match(linhas[i])
        if not m:
            continue
        data = data_hora_de_cabecalho(m.group("resto")) or (
            data_hora_de_cabecalho(linhas[i + 1]) if i + 1 < len(linhas) else None
        )
        if data is not None:
            inicios.append((i, m, data))
    if not inicios:
        return None
    mensagens = []
    for n, (i, m, data) in enumerate(inicios):
        fim = inicios[n + 1][0] if n + 1 < len(inicios) else len(linhas)
        k = i + 1
        while k < fim and (
            _R_GMAIL_CABECALHO.match(linhas[k])
            or (not m.group("resto").strip() and k == i + 1)
            or not linhas[k].strip()
        ):
            k += 1
        mensagens.append((m, data, "\n".join(linhas[k:fim])))
    primeira, data, corpo = mensagens[0]
    return _Bruto(
        assunto=assunto,
        remetente=(primeira.group("nome").strip(" \"'"), primeira.group("email").lower()),
        enviado_em=data,
        texto=corpo,
        citado="\n\n".join(c for _, _, c in mensagens[1:]),
    )


# ---------------------------------------------------------------------------
# WhatsApp
# ---------------------------------------------------------------------------

_R_WHATSAPP = [
    # "[24/09/2026 14:32] Maria:", "[24/09/26, 14:32:10] Maria:", "24/09/2026 14:32 - Maria:"
    re.compile(
        r"^\s*\[?(?P<data>\d{1,2}/\d{1,2}/\d{2,4}),?\s+(?P<hora>\d{1,2}:\d{2})(?::\d{2})?\]?\s*(?:-\s*)?"
        r"(?P<nome>[^:\n\]]{1,60}?):\s?(?P<texto>.*)$"
    ),
    # WhatsApp Web copiado: "[14:32, 24/09/2026] Maria:"
    re.compile(
        r"^\s*\[(?P<hora>\d{1,2}:\d{2}),\s*(?P<data>\d{1,2}/\d{1,2}/\d{2,4})\]\s*(?P<nome>[^:\n]{1,60}?):\s?(?P<texto>.*)$"
    ),
]
_R_WHATSAPP_SISTEMA = re.compile(
    r"(?:protegidas com a criptografia|<midia oculta>|<arquivo de midia oculto>|mensagem (?:foi )?apagada|"
    r"imagem ocultada|<media omitted>|end-to-end encrypted)"
)


def _linha_whatsapp(linha: str):
    for regex in _R_WHATSAPP:
        m = regex.match(linha)
        if m:
            return m
    return None


def _ler_whatsapp(texto: str) -> Mensagem | None:
    linhas = texto.replace("\r", "\n").split("\n")
    marcadas = [(i, _linha_whatsapp(linha)) for i, linha in enumerate(linhas)]
    marcadas = [(i, m) for i, m in marcadas if m]
    primeira = next((linha for linha in linhas if linha.strip()), "")
    if not marcadas or (len(marcadas) < 2 and not _linha_whatsapp(primeira)):
        return None
    falas: list[tuple[str, str, str, list[str]]] = []
    for i, linha in enumerate(linhas):
        m = _linha_whatsapp(linha)
        if m:
            falas.append((m.group("nome").strip(), m.group("data"), m.group("hora"), [m.group("texto")]))
        elif falas:
            falas[-1][3].append(linha)
    corpo = []
    for _nome, _data, _hora, partes in falas:
        fala = "\n".join(partes).strip()
        if fala and not _R_WHATSAPP_SISTEMA.search(dobrar(fala)):
            corpo.append(fala)
    nome, data, hora, _ = falas[0]
    enviado_em = data_hora_de_cabecalho(f"{data} {hora}")
    return Mensagem(
        remetente_nome=nome,
        enviado_em=_com_fuso(enviado_em),
        corpo=_arrumar_linhas("\n".join(corpo)),
        origem="whatsapp",
    )


# ---------------------------------------------------------------------------
# Log
# ---------------------------------------------------------------------------


def mascarar_para_log(texto: str, limite: int = 200) -> str:
    """O texto com CPF, telefone e e-mail mascarados, para ir ao log (LGPD)."""
    texto = " ".join(str(texto or "").split())
    texto = re.sub(r"\d{3}\.?\d{3}\.?\d{3}-?\d{2}", "***.***.***-**", texto)
    texto = re.sub(r"(?:\(?\d{2}\)?\s*)?9?\s?\d{4}[-.\s]?\d{4}", "(**) ****-****", texto)
    texto = re.sub(r"([\w.+-])[\w.+-]*@([\w-]+)", r"\1***@\2", texto)
    return texto[:limite]
