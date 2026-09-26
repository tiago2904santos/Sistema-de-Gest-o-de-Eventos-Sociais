"""Preencher um formulário novo a partir de um e-mail: a parte comum às telas.

A tela manda o arquivo do e-mail (ou o texto colado) para o endpoint
`.../ler-email/` do próprio módulo. A view do módulo só chama
`responder_leitura`, que lê a mensagem (`core.leitura.mensagem`), pede ao
`preenchimento.py` do app as sugestões de cada campo e devolve o JSON que
`static/js/preencher-por-email.js` aplica nos campos vazios:

    {"campos": {"municipio": {"valor": "12", "exibir": "Ponta Grossa/PR",
                              "confianca": "A", "trecho": "...", "rotulo": "Município"}},
     "avisos": ["..."], "duplicados": [{"titulo": "...", "url": "..."}],
     "mensagem": {"assunto": "...", "remetente": "...", "enviado_em": "24/09/2026 14:32"},
     "arquivo": {"token": "...", "nome": "pedido.eml", "anexos": ["oficio.pdf"]}}

Nada é gravado na leitura. O original fica numa pasta temporária do
servidor, apontado por um token guardado na sessão (o padrão da importação
de planilha do Coffee Break), até o formulário ser salvo: aí a view chama
`origem_do_pedido`, anexa o original quando o módulo tem anexo, registra no
histórico (`texto_de_origem`) e chama `concluir_origem`.

Também moram aqui leituras de domínio comuns às telas — a data do e-mail,
quem pede (pela assinatura) e o local citado —, puras como `core.leitura`.

LGPD: nada do texto do e-mail vai para o log; só contagens e o módulo.
"""

from __future__ import annotations

import logging
import re
import tempfile
import time as relogio
import uuid
from dataclasses import dataclass, replace
from datetime import date, datetime, time
from pathlib import Path, PurePath
from typing import Any, Callable

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db.models import Model
from django.forms import ModelMultipleChoiceField, MultipleChoiceField
from django.http import JsonResponse
from django.utils import timezone

from core.leitura.casamento import Achado, format_protocolo, municipio_no_texto, protocolo_no_texto, telefone_no_texto
from core.leitura.datas import Quando, dobrar, quando_do_evento
from core.leitura.mensagem import Mensagem, MensagemIlegivel, ler_mensagem, ler_texto_colado
from core.leitura.triagem import MODULOS, triar_mensagem

logger = logging.getLogger(__name__)

__all__ = [
    "EXTENSOES_EMAIL",
    "MODULOS_TRIAGEM",
    "MODULO_TRIAGEM",
    "EmailRecusado",
    "Origem",
    "avisar_equipe",
    "Pessoa",
    "Sugestao",
    "Sugestoes",
    "candidatos_de_triagem",
    "concluir_origem",
    "data_do_email",
    "ler_do_pedido",
    "ler_guardado",
    "local_no_texto",
    "modulos_de_triagem",
    "municipio_do_pedido",
    "opcoes_de_triagem",
    "origem_da_tela",
    "origem_do_pedido",
    "protocolo_do_pedido",
    "origem_pendente",
    "quando_do_pedido",
    "quem_pede",
    "reencaminhar",
    "registrar_cadastro",
    "responder_leitura",
    "texto_da_origem",
    "texto_de_origem",
    "url_da_tela_nova",
]

MIB = 1024 * 1024
# O arquivo do e-mail: o mesmo teto do leitor (e do nginx). Ajustável no settings.
LEITURA_EMAIL_MAX_BYTES = 25 * MIB
# Texto colado: bem mais que qualquer e-mail de pedido.
LEITURA_EMAIL_MAX_CARACTERES = 200_000
# Quantos e-mails lidos e ainda não salvos cada sessão guarda (o mais antigo sai).
_MAX_PENDENTES = 5
# Arquivo temporário esquecido (tela fechada sem salvar) some depois disto.
_VALIDADE_SEGUNDOS = 24 * 60 * 60
_CHAVE_SESSAO = "preencher_por_email"
_R_TOKEN = re.compile(r"^[0-9a-f]{32}$")

# Extensão aceita -> o que o conteúdo precisa parecer (o tipo real manda).
EXTENSOES_EMAIL = {".eml": "texto", ".msg": "ole", ".pdf": "pdf", ".txt": "texto"}
_MAGIC_OLE = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"
NOME_TEXTO_COLADO = "texto-do-email.txt"


def _ajuste(nome: str, padrao):
    return getattr(settings, nome, padrao)


# ---------------------------------------------------------------------------
# Sugestões: o contrato com a tela
# ---------------------------------------------------------------------------


def _valor_para_tela(valor) -> Any:
    """O valor como o campo HTML espera: texto, ou lista de textos (caixas)."""
    if valor is None:
        return ""
    if isinstance(valor, bool):
        return "1" if valor else "0"
    if isinstance(valor, Model):
        return str(valor.pk)
    if isinstance(valor, datetime):
        return timezone.localtime(valor).date().isoformat() if timezone.is_aware(valor) else valor.date().isoformat()
    if isinstance(valor, date):
        return valor.isoformat()
    if isinstance(valor, time):
        return valor.strftime("%H:%M")
    if isinstance(valor, (list, tuple, set)):
        return [_valor_para_tela(item) for item in valor]
    return str(valor)


@dataclass(frozen=True)
class Sugestao:
    """O que o e-mail diz para um campo.

    `valor` é o que vai para o campo (texto, data, hora, número, objeto do
    cadastro ou lista deles, para caixas de marcar); `exibir`, como mostrar;
    `confianca`: "A" (âncora explícita: preenche), "M" (preenche e destaca
    para conferência) ou "B" (só sugestão: a tela oferece, não preenche);
    `trecho`, de onde saiu, para a pessoa conferir.
    """

    valor: Any
    exibir: str
    confianca: str = "M"
    trecho: str = ""

    @classmethod
    def de_achado(cls, achado: Achado | None, *, valor=None, exibir=None, confianca=None):
        """A sugestão de um `Achado` de `core.leitura.casamento` (None passa direto)."""
        if achado is None:
            return None
        return cls(
            valor=achado.valor if valor is None else valor,
            exibir=achado.exibir if exibir is None else exibir,
            confianca=confianca or achado.confianca,
            trecho=achado.trecho,
        )

    def como_json(self) -> dict:
        return {
            "valor": _valor_para_tela(self.valor),
            "exibir": str(self.exibir or ""),
            "confianca": self.confianca,
            "trecho": " ".join(str(self.trecho or "").split())[:300],
        }


class Sugestoes(dict):
    """{campo: Sugestao}, na ordem em que a tela deve aplicar, e os avisos.

    A ordem conta: o estado antes do município (trocar o estado limpa o
    município), o tipo do evento antes do solicitante (Paraná em Ação
    sobrescreve o solicitante).
    """

    def __init__(self):
        super().__init__()
        self.avisos: list[str] = []

    def por(self, campo: str, sugestao: Sugestao | None) -> None:
        """Guarda a sugestão do campo; None (não achou) não entra."""
        if sugestao is not None and sugestao.valor not in (None, "", [], ()):
            self[campo] = sugestao

    def avisar(self, texto: str) -> None:
        if texto and texto not in self.avisos:
            self.avisos.append(texto)


# ---------------------------------------------------------------------------
# Leituras comuns: data do e-mail, quem pede, local
# ---------------------------------------------------------------------------


def _local(valor: datetime | None) -> datetime | None:
    if valor is None:
        return None
    return timezone.localtime(valor) if timezone.is_aware(valor) else valor


def data_do_email(mensagem: Mensagem) -> Sugestao | None:
    """A data em que o pedido foi enviado (a da mensagem mais interna). Nunca "hoje"."""
    enviado = _local(mensagem.enviado_em)
    if enviado is None:
        return None
    return Sugestao(enviado.date(), f"{enviado:%d/%m/%Y}", "A", f"Enviado em {enviado:%d/%m/%Y %H:%M}")


#: Evento a menos de tantos dias da leitura merece aviso: a agenda é curta.
DIAS_DE_PRAZO_CURTO = 10
_DIAS_DA_SEMANA = ("segunda-feira", "terça-feira", "quarta-feira", "quinta-feira", "sexta-feira", "sábado", "domingo")


def quando_do_pedido(mensagem: Mensagem) -> tuple[Quando | None, list[str]]:
    """(quando é o evento, avisos) pelo que o pedido diz.

    Procura no assunto e no corpo; sem data ali, na conversa anterior
    (`citado`) — a resposta "segue o ofício" não repete a data que o
    primeiro e-mail deu — com confiança rebaixada e aviso. A data de envio
    do e-mail nunca serve de data do evento (`datas.quando_do_evento` a
    descarta), então sem data no texto o campo fica vazio, com aviso.

    Também avisa quando o pedido oferece mais de uma data ("05, 07 ou 09 de
    outubro"), quando a data já passou, cai no fim de semana ou está a menos
    de `DIAS_DE_PRAZO_CURTO` dias.
    """
    avisos: list[str] = []
    referencia = mensagem.data_referencia or timezone.localdate()
    quando = quando_do_evento(mensagem.texto_para_busca, referencia)
    if quando is None and (mensagem.citado or "").strip():
        anterior = quando_do_evento(mensagem.citado, referencia)
        if anterior is not None:
            quando = replace(anterior, confianca="M")
            avisos.append(
                f"A data do evento ({quando.inicio:%d/%m/%Y}) veio de uma mensagem anterior da conversa, "
                "não desta: confira."
            )
    if quando is None:
        if mensagem.enviado_em is not None:
            avisos.append(
                "O e-mail não diz a data do evento: o período ficou em branco (a data de envio "
                "não é a data do evento). Pergunte ao solicitante."
            )
        return None, avisos
    if not mensagem.data_referencia:
        quando = replace(quando, confianca="M")
    if quando.alternativas:
        opcoes = ", ".join(f"{d:%d/%m}" for d in quando.alternativas[:-1]) + f" ou {quando.alternativas[-1]:%d/%m}"
        avisos.append(
            f"O pedido oferece mais de uma data ({opcoes}): preenchi a primeira. Confirme com o solicitante."
        )
    hoje = timezone.localdate()
    if quando.inicio < hoje:
        avisos.append(f"A data do evento lida ({quando.inicio:%d/%m/%Y}) já passou: confira.")
    else:
        faltam = (quando.inicio - hoje).days
        if faltam <= DIAS_DE_PRAZO_CURTO:
            quando_texto = "é hoje" if faltam == 0 else ("é amanhã" if faltam == 1 else f"é em {faltam} dias")
            avisos.append(
                f"Prazo curto: o evento {quando_texto} ({quando.inicio:%d/%m/%Y}). Priorize o despacho e a equipe."
            )
        fim_de_semana = [d for d in (quando.dias or (quando.inicio,)) if d.weekday() >= 5]
        if fim_de_semana:
            lista = ", ".join(f"{_DIAS_DA_SEMANA[d.weekday()]} {d:%d/%m}" for d in fim_de_semana[:3])
            avisos.append(f"O evento cai em fim de semana ({lista}): confira a data e o tipo de operação.")
    return quando, avisos


def municipio_do_pedido(mensagem: Mensagem, municipios, *, ddd: str = "") -> Achado | None:
    """O município do evento: o citado no texto; na falta, o da capa do processo do
    eProtocolo (a cidade de quem pede, por isso só como plano B, para conferir)."""
    achado = municipio_no_texto(mensagem.texto_para_busca, municipios, ddd=ddd)
    if achado is not None:
        return achado
    cidade = (mensagem.extras or {}).get("cidade", "")
    if not cidade:
        return None
    achado = municipio_no_texto(f"em {cidade}", municipios, ddd=ddd)
    if achado is None:
        return None
    return Achado(achado.valor, achado.exibir, f"Cidade da capa do processo: {cidade}", "M", achado.detalhes)


def protocolo_do_pedido(mensagem: Mensagem) -> Achado | None:
    """O nº do protocolo: o do processo do eProtocolo lido, ou o citado no texto."""
    numero = (mensagem.extras or {}).get("protocolo", "")
    if numero:
        formatado = format_protocolo(re.sub(r"\D", "", numero))
        return Achado(formatado, formatado, "Capa do processo do eProtocolo", "A")
    return protocolo_no_texto(mensagem.texto_para_busca)


@dataclass(frozen=True)
class Pessoa:
    """Quem pede, pela assinatura (ou pelo remetente)."""

    nome: str
    cargo: str
    unidade: str
    telefone: Achado | None
    trecho: str

    @property
    def cargo_e_unidade(self) -> str:
        return " / ".join(x for x in (self.cargo, self.unidade) if x)


_R_TEM_CONTATO = re.compile(
    r"@|https?://|www\.|\b(?:tel|fone|telefone|celular|cel|whats?app|ramal|e-?mail|cep)\b|\d{4}[-.\s]?\d{4}"
)
_R_ENDERECO = re.compile(r"^\s*(?:rua|r\.|av\.?|avenida|travessa|rodovia|alameda|praca|estrada)\s")
_R_INSTITUICAO = re.compile(
    r"\b(?:prefeitura|secretaria|colegio|escola|departamento|policia|delegacia|municipio|governo|camara|"
    r"associacao|instituto|universidade|faculdade|nucleo|coordenacao|diretoria|divisao|setor|gabinete|"
    r"assessoria|ministerio|tribunal|fundacao|conselho|centro|batalhao|comando|companhia|sindicato|"
    r"igreja|paroquia|cras|creas|ong|ltda|s/?a|eireli|me)s?\b"
)
_CARGOS = (
    r"(?:diretor|diretora|coordenador|coordenadora|secretari[oa]|prefeit[oa]|assessor|assessora|chefe|"
    r"delegad[oa]|investigador|investigadora|escriva|escrivao|professor|professora|pedagog[oa]|presidente|"
    r"gerente|analista|tecnic[oa]|agente|supervisor|supervisora|orientador|orientadora|vereador|vereadora|"
    r"comandante|capitao|tenente|sargento|major|coronel|reporter|produtor|produtora|jornalista|editor|"
    r"editora|assistente|auxiliar|servidor|servidora|policial|papiloscopista|perito|perita|psicolog[oa]|"
    r"vice|responsavel|organizador|organizadora|pastor|padre|vigario|lider|conselheir[oa])\b"
)
_R_CARGO = re.compile(r"\b" + _CARGOS)
# A linha do cargo começa por ele ("Delegado de Polícia", "Diretora do Colégio X").
_R_CARGO_NO_INICIO = re.compile(r"^(?:[a-z]{1,4}\.\s*)?" + _CARGOS)
_R_NOME_PROPRIO = re.compile(r"^[A-ZÀ-Ý][\w'.-]+(?:\s+(?:d[aeo]s?|e|[A-ZÀ-Ý][\w'.-]*)){1,6}$")
_R_SAUDACAO = re.compile(r"^\s*(?:att|atte|atenciosamente|cordialmente|respeitosamente|obrigad[oa]|abs|grat[oa])\b")


def _linhas_uteis(assinatura: str) -> list[str]:
    linhas = []
    for linha in (assinatura or "").split("\n"):
        linha = " ".join(linha.split()).strip(" -–—|•*_")
        if not linha or _R_SAUDACAO.match(dobrar(linha)):
            continue
        linhas.append(linha)
    return linhas


def _parece_nome(linha: str) -> bool:
    dobrada = dobrar(linha)
    return (
        len(linha) <= 80
        and not any(c.isdigit() for c in linha)
        and not _R_TEM_CONTATO.search(dobrada)
        and not _R_INSTITUICAO.search(dobrada)
        and not _R_CARGO.search(dobrada)
        and bool(_R_NOME_PROPRIO.match(linha) or (linha.isupper() and 2 <= len(linha.split()) <= 7))
    )


_R_SOBRENOME_PRIMEIRO = re.compile(r"^\s*(?P<sobrenome>[^,\d@]{2,60}),\s*(?P<nome>[^,\d@]{2,60})\s*$")


def _nome_na_ordem(nome: str) -> str:
    """"PAIS, Andres" (o catálogo corporativo) vira "Andres Pais"."""
    nome = " ".join((nome or "").split())
    m = _R_SOBRENOME_PRIMEIRO.match(nome)
    if not m:
        return nome
    sobrenome, primeiro = m.group("sobrenome").strip(), m.group("nome").strip()
    if sobrenome.isupper() and len(sobrenome.split()) <= 3:
        sobrenome = " ".join(p.lower() if p.lower() in ("de", "da", "do", "das", "dos", "e") else p.capitalize() for p in sobrenome.split())
    return f"{primeiro} {sobrenome}"


def quem_pede(mensagem: Mensagem) -> Pessoa | None:
    """Nome, cargo, unidade e telefone de quem pede.

    O nome é a 1ª linha da assinatura quando ela parece nome de gente; senão,
    o nome do remetente. Das linhas seguintes, a que começa pelo cargo vira o
    cargo e a primeira de instituição vira a unidade; telefone, e-mail, site e
    endereço ficam de fora. O telefone prefere o celular da assinatura (e,
    sem assinatura, o do corpo).
    """
    linhas = _linhas_uteis(mensagem.assinatura)
    nome = ""
    resto = linhas
    if linhas and _parece_nome(linhas[0]):
        nome, resto = linhas[0], linhas[1:]
    if not nome:
        nome = _nome_na_ordem(mensagem.remetente_nome)
    cargo, unidade = "", ""
    for linha in resto:
        dobrada = dobrar(linha)
        if _R_TEM_CONTATO.search(dobrada) or _R_ENDERECO.match(dobrada) or len(linha) > 120:
            continue
        # "Secretaria Municipal de…" é o órgão, não a secretária: instituição no começo vence.
        if not cargo and _R_CARGO_NO_INICIO.match(dobrada) and not _R_INSTITUICAO.match(dobrada):
            cargo = linha
        elif not unidade and (_R_INSTITUICAO.search(dobrada) or cargo):
            unidade = linha
        if cargo and unidade:
            break
    telefone = telefone_no_texto(mensagem.assinatura) or telefone_no_texto(mensagem.corpo)
    if not (nome or cargo or unidade or telefone):
        return None
    trecho = " · ".join(linhas[:4]) if linhas else (mensagem.remetente or "")
    return Pessoa(nome=nome[:150], cargo=cargo, unidade=unidade, telefone=telefone, trecho=trecho)


_LUGARES = (
    r"colegio|escola|ginasio|praca|centro|salao|igreja|camara|prefeitura|auditorio|teatro|parque|"
    r"associacao|clube|sede|paroquia|cras|creas|estadio|espaco|casa|barracao|pavilhao|sala|quadra|"
    r"biblioteca|universidade|faculdade|instituto|hospital|delegacia|batalhao|shopping|hotel|restaurante|"
    r"cmei|ubs|terminal|rodoviaria|forum|tribunal|assembleia|academia|anfiteatro|galpao|"
    r"complexo|conjunto|capela|aldeia|assentamento|cooperativa|sindicato|secretaria"
)
_R_LOCAL_ROTULO = re.compile(
    r"(?m)^[ \t*•-]*(?:local(?:\s+(?:do\s+evento|de\s+entrega|da\s+entrega|da\s+acao))?|"
    r"endereco(?:\s+(?:do\s+evento|de\s+entrega|para\s+entrega))?|onde|entregar\s+(?:em|no|na))"
    r"\s*[:–-]\s*(?P<valor>[^\n]{3,255})$"
)
_R_LOCAL_PREPOSICAO = re.compile(
    r"\b(?:no|na|nos|nas|em)\s+(?P<valor>(?:" + _LUGARES + r")\b[^,.;:!?\n()]{0,120})"
)
_R_LOCAL_ENDERECO = re.compile(
    r"\b(?P<valor>(?P<tipo>rua|r\.|av\.|avenida|rodovia|travessa|alameda|estrada)\s+[^\n;()]{3,150})"
)
# Pedaços que continuam um local: ", Rua X", ", nº 500", ", Bairro Y", ", 500".
# Param no fim da frase (ponto seguido de espaço), não no ponto de "Av.".
_R_CONTINUA_LOCAL = re.compile(
    r"^,\s*(?:(?:rua|r\.|av\.|avenida|rodovia|travessa|alameda|estrada|bairro|jardim|jd\.|vila|"
    r"n[o.]?\s*\d|numero|centro|cep|s/n|km)\b|\d{1,5}\b)(?:[^,;.\n]|\.(?=\S)){0,80}"
)
_R_FIM_ENDERECO = re.compile(r"\.(?:\s|$)|[;\n]")


def _estender_local(dobrado: str, fim: int) -> int:
    """Junta ao local os pedaços de endereço logo depois (", Rua X, 500")."""
    for _ in range(4):
        m = _R_CONTINUA_LOCAL.match(dobrado[fim:fim + 100])
        if not m:
            break
        fim += m.end()
    return fim


def _limpar_local(valor: str) -> str:
    valor = " ".join(valor.split()).strip(" ,.;:-–")
    return valor[:255]


def local_no_texto(texto: str) -> Achado | None:
    """O local do evento (ou da entrega) citado no texto.

    Com rótulo ("Local:", "Endereço:", "Local de entrega:") é "A". Sem
    rótulo, "no Ginásio X, Rua Y, 500" ou um endereço solto ("Rua X, 123")
    é "M". Passe só o corpo: o endereço da assinatura é o de quem pede.
    """
    texto = texto or ""
    dobrado = dobrar(texto)
    m = _R_LOCAL_ROTULO.search(dobrado)
    if m:
        valor = _limpar_local(texto[m.start("valor"):m.end("valor")])
        if valor:
            return Achado(valor, valor, texto[m.start():m.end()].strip(), "A")
    for regex in (_R_LOCAL_PREPOSICAO, _R_LOCAL_ENDERECO):
        m = regex.search(dobrado)
        if not m:
            continue
        inicio, fim = m.start("valor"), m.end("valor")
        if regex is _R_LOCAL_ENDERECO:
            corte = _R_FIM_ENDERECO.search(dobrado, m.end("tipo"))
            fim = min(fim, corte.start()) if corte else fim
        else:
            fim = _estender_local(dobrado, fim)
        valor = _limpar_local(texto[inicio:fim])
        # "na escola", "no centro": o tipo do lugar sem o nome não diz onde é.
        if len(valor.split()) >= 2:
            comeco = max(texto.rfind("\n", 0, m.start()) + 1, m.start() - 80)
            return Achado(valor, valor, texto[comeco:fim + 1].strip(), "M")
    return None


# ---------------------------------------------------------------------------
# Leitura do pedido (arquivo ou texto colado)
# ---------------------------------------------------------------------------


class EmailRecusado(Exception):
    """O e-mail enviado não pode ser lido. A mensagem é para a tela."""


def _tipo_real(dados: bytes) -> str:
    if dados.startswith(_MAGIC_OLE):
        return "ole"
    if b"%PDF-" in dados[:1024]:
        return "pdf"
    return "texto"


def _verificar_antivirus(arquivo) -> None:
    if not getattr(settings, "PRIVATE_UPLOAD_REQUIRE_ANTIVIRUS", False):
        return
    from core.uploads import _scan_with_clamav  # a mesma política dos anexos privados

    try:
        _scan_with_clamav(arquivo)
    except ValidationError as erro:
        raise EmailRecusado(" ".join(erro.messages)) from erro


def _nome_seguro(nome: str) -> str:
    """Só o nome do arquivo (sem pasta), sem caracteres de controle, até 150 caracteres."""
    nome = re.split(r"[\\/]", str(nome or ""))[-1]
    nome = "".join(c for c in nome if c.isprintable() and c not in '<>:"|?*').strip(" .")
    if len(nome) > 150:
        base, _, extensao = nome.rpartition(".")
        nome = f"{base[:140]}.{extensao[:8]}"
    return nome or "email"


def ler_do_pedido(request) -> tuple[Mensagem, str, bytes]:
    """(mensagem, nome do arquivo, bytes do original) do POST.

    O POST traz `arquivo` (.eml, .msg, .pdf impresso ou .txt) ou `texto`
    (o e-mail colado). Confere tamanho, extensão e se o conteúdo é mesmo do
    tipo da extensão (um .msg renomeado para .pdf é recusado), passa pelo
    antivírus quando ele é exigido e só então lê. Levanta `EmailRecusado`.
    """
    arquivo = request.FILES.get("arquivo")
    if arquivo is not None:
        nome = _nome_seguro(arquivo.name)
        extensao = PurePath(nome).suffix.lower()
        if extensao not in EXTENSOES_EMAIL:
            raise EmailRecusado("Envie o e-mail em .eml, .msg, .pdf ou .txt — ou cole o texto.")
        limite = int(_ajuste("LEITURA_EMAIL_MAX_BYTES", LEITURA_EMAIL_MAX_BYTES))
        if arquivo.size > limite:
            raise EmailRecusado(f"O arquivo passa do limite de {limite // MIB} MB.")
        if not arquivo.size:
            raise EmailRecusado("O arquivo está vazio.")
        arquivo.seek(0)
        dados = arquivo.read()
        arquivo.seek(0)
        if _tipo_real(dados) != EXTENSOES_EMAIL[extensao]:
            raise EmailRecusado(
                f"O conteúdo de {nome} não corresponde a um arquivo {extensao}. "
                "Salve o e-mail de novo pelo programa de e-mail e tente outra vez."
            )
        _verificar_antivirus(arquivo)
        try:
            return ler_mensagem(nome, dados), nome, dados
        except MensagemIlegivel as erro:
            raise EmailRecusado(str(erro)) from erro
    texto = (request.POST.get("texto") or "").strip()
    if not texto:
        raise EmailRecusado("Escolha o arquivo do e-mail ou cole o texto dele.")
    limite = int(_ajuste("LEITURA_EMAIL_MAX_CARACTERES", LEITURA_EMAIL_MAX_CARACTERES))
    if len(texto) > limite:
        raise EmailRecusado("O texto colado é longo demais. Cole só o e-mail do pedido.")
    try:
        return ler_texto_colado(texto), NOME_TEXTO_COLADO, texto.encode("utf-8")
    except MensagemIlegivel as erro:
        raise EmailRecusado(str(erro)) from erro


# ---------------------------------------------------------------------------
# O original até o formulário ser salvo: pasta temporária + sessão
# ---------------------------------------------------------------------------


def _pasta() -> Path:
    base = _ajuste("PREENCHER_EMAIL_PASTA", "") or tempfile.gettempdir()
    pasta = Path(base) / "preencher-por-email"
    pasta.mkdir(parents=True, exist_ok=True)
    return pasta


def _faxina(pasta: Path) -> None:
    """Apaga os originais esquecidos (tela fechada sem salvar)."""
    limite = relogio.time() - _VALIDADE_SEGUNDOS
    for arquivo in pasta.glob("*.bin"):
        try:
            if arquivo.stat().st_mtime < limite:
                arquivo.unlink(missing_ok=True)
        except OSError:
            continue


def _data_iso(valor: datetime | None) -> str:
    return valor.isoformat() if valor else ""


def _guardar(request, modulo: str, nome: str, dados: bytes, mensagem: Mensagem) -> str:
    pasta = _pasta()
    _faxina(pasta)
    token = uuid.uuid4().hex
    caminho = pasta / f"{token}.bin"
    caminho.write_bytes(dados)
    try:
        caminho.chmod(0o600)
    except OSError:  # Windows não tem o mesmo modelo de permissão
        pass
    pendentes = dict(request.session.get(_CHAVE_SESSAO) or {})
    pendentes[token] = {
        "modulo": modulo,
        "nome": nome,
        "assunto": mensagem.assunto_limpo[:300],
        "remetente": (mensagem.remetente or "")[:200],
        "remetente_email": (mensagem.remetente_email or "")[:200],
        "enviado_em": _data_iso(mensagem.enviado_em),
        "message_id": (mensagem.message_id or "")[:300],
        "origem": mensagem.origem,
        "quando": relogio.time(),
    }
    while len(pendentes) > _MAX_PENDENTES:
        antigo = min(pendentes, key=lambda t: pendentes[t].get("quando", 0))
        pendentes.pop(antigo)
        (pasta / f"{antigo}.bin").unlink(missing_ok=True)
    request.session[_CHAVE_SESSAO] = pendentes
    return token


@dataclass(frozen=True)
class Origem:
    """O e-mail de onde saiu um registro novo, ainda não gravado."""

    token: str
    modulo: str
    nome: str
    dados: bytes
    assunto: str
    remetente: str
    enviado_em: datetime | None
    message_id: str
    origem: str
    remetente_email: str = ""

    @property
    def colado(self) -> bool:
        return self.nome == NOME_TEXTO_COLADO

    def mensagem(self) -> Mensagem | None:
        """O e-mail lido de novo (para pegar os anexos dele), ou None se não der."""
        try:
            if self.colado:
                return ler_texto_colado(self.dados.decode("utf-8", "replace"))
            return ler_mensagem(self.nome, self.dados)
        except MensagemIlegivel:
            return None


def _entrada(request, modulo: str, token: str) -> dict | None:
    token = (token or "").strip().lower()
    if not _R_TOKEN.match(token):
        return None
    entrada = (request.session.get(_CHAVE_SESSAO) or {}).get(token)
    if not entrada or entrada.get("modulo") != modulo:
        return None
    return entrada


def origem_pendente(request, modulo: str, campo: str = "email_origem", *, token: str | None = None) -> dict | None:
    """{token, nome, assunto} do e-mail já lido que o POST aponta — para a
    tela que volta com erro não perder o vínculo com o e-mail.

    Com `token` (o `?email_origem=` da triagem da página inicial), vale ele,
    e `auto` diz à tela para ler o e-mail sozinha ao abrir.
    """
    auto = token is not None
    token = (token if auto else (request.POST.get(campo) or "")).strip().lower()
    entrada = _entrada(request, modulo, token)
    if entrada is None and auto:
        entrada = _entrada(request, MODULO_TRIAGEM, token)  # ainda não assumido pela tela
    if entrada is None or not (_pasta() / f"{token}.bin").exists():
        return None
    return {"token": token, "nome": entrada["nome"], "assunto": entrada.get("assunto", ""), "auto": auto}


def origem_da_tela(request, modulo: str) -> dict | None:
    """O e-mail que a tela nova deve ler ao abrir: o `?email_origem=` da triagem
    (GET) ou o oculto do formulário que voltou com erro (POST)."""
    if request.method == "POST":
        return origem_pendente(request, modulo)
    token = (request.GET.get("email_origem") or "").strip()
    return origem_pendente(request, modulo, token=token) if token else None


def reencaminhar(request, token: str, modulo: str) -> bool:
    """Passa o e-mail guardado nesta sessão (em qualquer módulo) para `modulo`:
    o clique em "abrir este e-mail como coffee break" na tela de palestras."""
    token = (token or "").strip().lower()
    if not _R_TOKEN.match(token):
        return False
    pendentes = dict(request.session.get(_CHAVE_SESSAO) or {})
    entrada = pendentes.get(token)
    if not entrada or not (_pasta() / f"{token}.bin").exists():
        return False
    pendentes[token] = {**entrada, "modulo": modulo}
    request.session[_CHAVE_SESSAO] = pendentes
    return True


def ler_guardado(request, modulo: str, token: str) -> tuple[Mensagem, str, bytes] | None:
    """(mensagem, nome, bytes) do e-mail já guardado nesta sessão, lido de novo.

    O token vale no módulo dado ou vindo da triagem ("triagem"): a triagem da
    página inicial guarda o e-mail antes de saber o módulo, e a tela do módulo
    o assume ao ler.
    """
    token = (token or "").strip().lower()
    entrada = _entrada(request, modulo, token) or _entrada(request, MODULO_TRIAGEM, token)
    if entrada is None:
        return None
    try:
        dados = (_pasta() / f"{token}.bin").read_bytes()
    except OSError:
        return None
    nome = entrada["nome"]
    try:
        mensagem = ler_texto_colado(dados.decode("utf-8", "replace")) if nome == NOME_TEXTO_COLADO else ler_mensagem(nome, dados)
    except MensagemIlegivel:
        return None
    if entrada.get("modulo") != modulo:
        pendentes = dict(request.session.get(_CHAVE_SESSAO) or {})
        pendentes[token] = {**entrada, "modulo": modulo}
        request.session[_CHAVE_SESSAO] = pendentes
    return mensagem, nome, dados


def origem_do_pedido(request, modulo: str, campo: str = "email_origem") -> Origem | None:
    """O e-mail lido nesta sessão que o formulário salvo aponta (ou None).

    O token só vale na sessão de quem leu e no mesmo módulo; token de outra
    pessoa, de outro módulo ou expirado é ignorado.
    """
    token = (request.POST.get(campo) or "").strip().lower()
    entrada = _entrada(request, modulo, token)
    if entrada is None:
        return None
    try:
        dados = (_pasta() / f"{token}.bin").read_bytes()
    except OSError:
        return None
    enviado_em = None
    if entrada.get("enviado_em"):
        try:
            enviado_em = datetime.fromisoformat(entrada["enviado_em"])
        except ValueError:
            enviado_em = None
    return Origem(
        token=token,
        modulo=modulo,
        nome=entrada["nome"],
        dados=dados,
        assunto=entrada.get("assunto", ""),
        remetente=entrada.get("remetente", ""),
        enviado_em=enviado_em,
        message_id=entrada.get("message_id", ""),
        origem=entrada.get("origem", ""),
        remetente_email=entrada.get("remetente_email", ""),
    )


def registrar_cadastro(request, origem: Origem | None, modulo: str, form, campos_aprendidos, *,
                       titulo: str = "", mensagem: str = "", link: str = "") -> None:
    """Depois de salvo um registro que veio de e-mail: o sistema aprende com ele
    (`core.aprendizado`) e avisa a equipe do módulo no sino (`titulo`, `mensagem`,
    `link`), menos quem salvou. Sem `origem`, não faz nada."""
    if origem is None:
        return
    from core import aprendizado

    aprendizado.aprender_do_formulario(origem, modulo, form, campos_aprendidos)
    if titulo:
        avisar_equipe(request, modulo, titulo, mensagem, link)


def avisar_equipe(request, modulo: str, titulo: str, mensagem: str = "", link: str = "") -> None:
    """Aviso no sino para quem trabalha no módulo (pelos setores), menos o autor."""
    from django.contrib.auth import get_user_model

    from core.notificacoes import notificar

    codigo = MODULOS_TRIAGEM.get(modulo, {}).get("codigo")
    if not codigo:
        return  # módulo aberto a todos (Eventos Sociais): o fluxo de despacho já avisa
    equipe = get_user_model().objects.filter(
        is_active=True, setores__ativo=True, setores__modulos__codigo=codigo, setores__modulos__ativo=True
    ).distinct()
    notificar(equipe, titulo, mensagem, link=link, exceto=getattr(request, "user", None))


def concluir_origem(request, origem: Origem | None) -> None:
    """Tira o e-mail da sessão e apaga o temporário (depois de salvo o registro)."""
    if origem is None:
        return
    pendentes = dict(request.session.get(_CHAVE_SESSAO) or {})
    if pendentes.pop(origem.token, None) is not None:
        request.session[_CHAVE_SESSAO] = pendentes
    (_pasta() / f"{origem.token}.bin").unlink(missing_ok=True)


def texto_de_origem(assunto: str, remetente: str, enviado_em: datetime | None, *,
                    verbo: str = "Criada", origem: str = "") -> str:
    """"Criada a partir do e-mail 'Assunto' de Fulano (24/09/2026 14:32)" — para o histórico."""
    fonte = "da conversa do WhatsApp" if origem == "whatsapp" else "do e-mail"
    partes = [f"{verbo} a partir {fonte}"]
    if assunto:
        partes.append(f"'{assunto}'")
    if remetente:
        partes.append(f"de {remetente}")
    enviado = _local(enviado_em)
    if enviado:
        partes.append(f"({enviado:%d/%m/%Y %H:%M})")
    return " ".join(partes)


def texto_da_origem(origem: Origem, *, verbo: str = "Criada") -> str:
    """`texto_de_origem` de uma `Origem` já lida."""
    return texto_de_origem(origem.assunto, origem.remetente, origem.enviado_em, verbo=verbo, origem=origem.origem)


# ---------------------------------------------------------------------------
# O endpoint
# ---------------------------------------------------------------------------


def _rotulo(formulario, campo: str) -> str:
    campos = getattr(formulario, "base_fields", {}) if formulario is not None else {}
    rotulo = str(getattr(campos.get(campo), "label", "") or "")
    return rotulo[:1].upper() + rotulo[1:] if rotulo else campo.replace("_", " ").capitalize()


#: O módulo "dono" do token enquanto a triagem da página inicial ainda não
#: decidiu para onde o e-mail vai.
MODULO_TRIAGEM = "triagem"

#: Para cada módulo que lê e-mail: o código de acesso (None = aberto a todo
#: usuário) e a rota da tela nova, que recebe `?email_origem=<token>`.
MODULOS_TRIAGEM = {
    "solicitacoes": {"codigo": None, "nova": "solicitacoes:nova"},
    "demandas_eventos": {"codigo": "ASCOM_DEMANDAS_EVENTOS", "nova": "demandas_eventos:nova"},
    "coffee_break": {"codigo": "ASCOM_COFFEE_BREAK", "nova": "coffee_break:nova"},
    "publicacoes": {"codigo": "ASCOM_PUBLICACOES", "nova": "publicacoes:nova"},
    "atendimento_imprensa": {"codigo": "ASCOM_ATENDIMENTO_IMPRENSA", "nova": "atendimento_imprensa:novo"},
}


def modulos_de_triagem(usuario) -> list[str]:
    """Os módulos (chaves de `MODULOS`) que o usuário pode abrir."""
    from accounts.modulos import usuario_tem_modulo

    return [
        modulo for modulo, dados in MODULOS_TRIAGEM.items()
        if dados["codigo"] is None or usuario_tem_modulo(usuario, dados["codigo"])
    ]


def url_da_tela_nova(modulo: str, token: str = "") -> str:
    """A tela nova do módulo; com `token`, passando por `core:triagem_encaminhar`,
    que passa o e-mail guardado para o módulo e abre a tela com `?email_origem=`."""
    from django.urls import reverse

    if not token:
        return reverse(MODULOS_TRIAGEM[modulo]["nova"])
    return f"{reverse('core:triagem_encaminhar')}?token={token}&modulo={modulo}"


def candidatos_de_triagem(mensagem: Mensagem, usuario, token: str = "") -> list[dict]:
    """Os módulos candidatos ao e-mail, do mais ao menos provável, só os que o
    usuário acessa: {modulo, rotulo, confianca, sinais, url}.

    Aos sinais do texto (`core.leitura.triagem`) somam-se os da memória
    (`core.aprendizado`): para onde foram os pedidos anteriores deste
    remetente, deste domínio e com estas palavras no assunto.
    """
    from core import aprendizado

    permitidos = modulos_de_triagem(usuario)
    if not permitidos:
        return []
    extras = aprendizado.pesos_de_triagem(mensagem)
    destinos = triar_mensagem(mensagem, modulos=permitidos, extras=extras)
    return [
        {
            "modulo": d.modulo,
            "rotulo": d.rotulo,
            "confianca": d.confianca,
            "sinais": list(d.sinais),
            "url": url_da_tela_nova(d.modulo, token),
        }
        for d in destinos
    ]


def opcoes_de_triagem(mensagem: Mensagem, usuario, token: str = "") -> list[dict]:
    """Os candidatos (`candidatos_de_triagem`) seguidos dos outros módulos do
    usuário, sem sinal: tudo o que a pessoa pode escolher, do mais ao menos provável."""
    candidatos = candidatos_de_triagem(mensagem, usuario, token)
    vistos = {c["modulo"] for c in candidatos}
    return candidatos + [
        {"modulo": m, "rotulo": MODULOS[m], "confianca": 0, "sinais": [], "url": url_da_tela_nova(m, token)}
        for m in modulos_de_triagem(usuario) if m not in vistos
    ]


def _aviso_de_triagem(mensagem: Mensagem, modulo: str) -> str:
    """"Este e-mail parece de outro módulo" quando a triagem aponta outro com folga."""
    destinos = triar_mensagem(mensagem)
    if not destinos or destinos[0].modulo == modulo or modulo not in MODULOS:
        return ""
    primeiro = destinos[0]
    deste = next((d for d in destinos if d.modulo == modulo), None)
    if primeiro.confianca < 0.5 or (deste and deste.pontos >= primeiro.pontos * 0.6):
        return ""
    sinais = ", ".join(primeiro.sinais[:3])
    return (
        f"Este e-mail parece um pedido de {primeiro.rotulo} ({sinais}). "
        "Confira se está na tela certa antes de salvar."
    )


def responder_leitura(
    request,
    *,
    modulo: str,
    sugerir: Callable[[Mensagem, Any], Sugestoes],
    formulario=None,
    anexa_original: bool = False,
    duplicados: Callable[[str], list[dict]] | None = None,
    verbo: str = "Criada",
) -> JsonResponse:
    """Lê o e-mail do POST e responde com as sugestões para a tela.

    `modulo` é o namespace do app (o token só vale nele); `sugerir(mensagem,
    usuario)` devolve as `Sugestoes` do `preenchimento.py` do app;
    `formulario` (a classe do form) dá o rótulo de cada campo;
    `anexa_original` diz se o módulo guarda o e-mail como anexo ao salvar;
    `duplicados(texto_de_origem)` lista registros já criados deste e-mail.
    Erro de leitura volta com status 400 e `{"erro": "..."}`.
    """
    token = (request.POST.get("token") or "").strip().lower()
    guardado = ler_guardado(request, modulo, token) if token else None
    if guardado is not None:
        mensagem, nome, dados = guardado
    else:
        try:
            mensagem, nome, dados = ler_do_pedido(request)
        except EmailRecusado as erro:
            if token:
                return JsonResponse({"erro": "O e-mail lido na página inicial não está mais disponível; envie-o de novo."}, status=400)
            return JsonResponse({"erro": str(erro)}, status=400)
        token = _guardar(request, modulo, nome, dados, mensagem)
    sugestoes = sugerir(mensagem, request.user)
    avisos = list(mensagem.avisos) + list(getattr(sugestoes, "avisos", []))
    triagem = _aviso_de_triagem(mensagem, modulo)
    if triagem:
        avisos.insert(0, triagem)
    outros_modulos = [
        {"modulo": c["modulo"], "rotulo": c["rotulo"], "url": c["url"]}
        for c in opcoes_de_triagem(mensagem, request.user, token)
        if c["modulo"] != modulo
    ][:3] if guardado is not None else []
    campos = {}
    for campo, sugestao in sugestoes.items():
        campos[campo] = {**sugestao.como_json(), "rotulo": _rotulo(formulario, campo)}
    # O que o texto não disse e a memória sabe deste remetente.
    from core import aprendizado

    base_fields = (getattr(formulario, "base_fields", {}) or {}) if formulario is not None else {}
    for campo, aprendida in aprendizado.sugestoes_aprendidas(mensagem, modulo, campos).items():
        if base_fields and campo not in base_fields:
            continue
        if isinstance(base_fields.get(campo), (MultipleChoiceField, ModelMultipleChoiceField)) and isinstance(aprendida["valor"], str):
            aprendida = {**aprendida, "valor": aprendida["valor"].split(",")}
        campos[campo] = {**aprendida, "rotulo": _rotulo(formulario, campo)}
    enviado = _local(mensagem.enviado_em)
    lista_duplicados = []
    if duplicados and enviado and (mensagem.assunto_limpo or mensagem.remetente):
        lista_duplicados = duplicados(
            texto_de_origem(mensagem.assunto_limpo, mensagem.remetente, mensagem.enviado_em, verbo=verbo,
                            origem=mensagem.origem)
        )
    logger.info(
        "Leitura de e-mail em %s: origem=%s, %d campo(s) sugerido(s), %d aviso(s).",
        modulo, mensagem.origem, len(campos), len(avisos),
    )
    return JsonResponse({
        "campos": campos,
        "avisos": avisos,
        "outros_modulos": outros_modulos,
        "duplicados": lista_duplicados,
        "mensagem": {
            "assunto": mensagem.assunto_limpo,
            "remetente": mensagem.remetente,
            "enviado_em": f"{enviado:%d/%m/%Y %H:%M}" if enviado else "",
        },
        "arquivo": {
            "token": token,
            "nome": nome,
            "anexos": [anexo for anexo, _ in mensagem.anexos] if anexa_original else [],
        },
    })
