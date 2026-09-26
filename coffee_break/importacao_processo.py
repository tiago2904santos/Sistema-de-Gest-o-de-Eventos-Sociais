"""Importar o processo de pagamento do eProtocolo no Coffee Break.

O operador solta o PDF inteiro do processo ("Processo_26.613.666-8_1.pdf") na
lista de solicitações (ou na etapa 3 de uma delas). O sistema:

1. **lê** o processo com `core.leitura` (sem gravar, fora de transação): capa,
   ofício, notas fiscais com a folha de assinatura, certificos, certidões,
   termo aditivo, contrato, despacho ao GAF, empenho e liquidação;
2. **identifica** a(s) solicitação(ões) — inclusive o pagamento conjunto —
   por sinais independentes: o nº do processo (já gravado como protocolo de
   pagamento ou como o protocolo do ofício), o "PCPR Protocolo n.º" escrito
   no ofício, o nº/ano do ofício (capa "Nº/Ano" e título "OFÍCIO 123/2026") e
   o número de cada nota fiscal (do mesmo fornecedor, pelo CNPJ);
3. **aplica** (`aplicar`, atômico, arquivos novos desfeitos se falhar): anexa
   a nota de cada solicitação que ainda não tem o PDF, com o número lido;
   grava o protocolo de pagamento com o nº do processo e o atesto e envio ao
   GAF com a data do despacho — nessa ordem, a que o `clean()` do modelo
   exige, validando com `full_clean` —, espelha no pagamento conjunto
   (`services.espelhar`) e registra as certidões do fornecedor que vierem
   mais novas que as cadastradas (conferidas por `certidoes.conferir`).

A view aplica sozinha quando a identificação é segura e toda nota do
processo tem solicitação (`Plano.seguro`); senão abre a conferência já
preenchida. Nada sobrescreve o que foi digitado: nota ou protocolo diferente
do processo vira pendência no resultado. A única troca é a do protocolo de
pagamento que é cópia do "PCPR Protocolo n.º" do ofício (o número interno da
PCPR, "2026.050731.000", que a etapa 2 copiava): o do pagamento é o do
processo.

Protocolos: `protocolo_pagamento` e `protocolo_pcpr_oficio` ficam com a
máscara do eProtocolo ("26.613.666-8") ou como vieram (legado); a comparação
é sempre pelos dígitos, dos dois lados.

Sem modelo novo: o processo não fica guardado (a nota e as certidões, sim,
recortadas dele). O histórico de cada solicitação diz o que veio de qual
processo e leva uma referência do arquivo (início do SHA-256), que reconhece
o mesmo arquivo enviado de novo.

LGPD: o texto do processo não é guardado nem registrado em log; o histórico
leva só números (protocolo, notas, páginas, datas).
"""

from __future__ import annotations

import hashlib
import logging
import re
from collections import defaultdict
from dataclasses import dataclass
from dataclasses import field
from datetime import date
from datetime import datetime
from decimal import Decimal
from io import BytesIO

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.db.models import Q
from django.urls import reverse
from django.utils import timezone

from core.leitura import classificacao as tipos
from core.leitura.eprotocolo import Processo
from core.leitura.eprotocolo import ler_processo
from core.leitura.pdf import recortar
from core.leitura.pdf import rotacao_para_ficar_em_pe
from core.leitura.texto import achar_cnpjs
from core.leitura.texto import normalizar
from core.uploads import validate_private_document_upload
from core.utils.masks import format_protocolo
from core.utils.masks import normalize_protocolo
from viagens_prestacoes.arquivos import registrar_arquivo_criado
from viagens_prestacoes.arquivos import transacao_de_arquivos

from . import certidoes
from . import services
from .models import AcaoHistoricoCoffeeBreak
from .models import Fornecedor
from .models import HistoricoCoffeeBreak
from .models import SolicitacaoCoffeeBreak
from .models import TipoCertidao

__all__ = [
    "Escolhas",
    "Plano",
    "Resultado",
    "analisar",
    "aplicar",
    "hash_do_arquivo",
    "importacao_anterior",
    "limite_de_bytes",
    "validar_arquivo",
]

logger = logging.getLogger(__name__)

_MIB = 1024 * 1024
#: Quantos caracteres do SHA-256 vão para o histórico ("ref. …"): o bastante
#: para reconhecer o mesmo arquivo enviado de novo.
TAMANHO_REFERENCIA = 16
_CENTAVO = Decimal("0.01")
#: Solicitações oferecidas na conferência quando nada foi identificado.
MAX_CANDIDATAS = 20

_ROTULO_CERTIDAO = dict(TipoCertidao.choices)
_SITUACOES_CERTIDAO = {
    "atualiza": "mais nova que a cadastrada — entra nas certidões",
    "igual": "a mesma já está cadastrada",
    "antiga": "a cadastrada vale por mais tempo",
    "imagem": "é imagem: a validade não se confere sozinha — anexe em Certidões se for mais nova",
    "sem_validade": "não achei a validade",
    "outro_cnpj": "é de outro CNPJ",
    "sem_fornecedor": "sem o fornecedor do pagamento para conferir",
    "sem_tipo": "tipo não reconhecido",
}


# ─────────────────────────────────────────────────────────────────
# Entrada
# ─────────────────────────────────────────────────────────────────

def limite_de_bytes() -> int:
    """Tamanho máximo do processo enviado (`IMPORTACAO_MAX_BYTES`, padrão 25 MiB, o do nginx)."""
    try:
        return int(getattr(settings, "IMPORTACAO_MAX_BYTES", 25 * _MIB))
    except (TypeError, ValueError):
        return 25 * _MIB


def validar_arquivo(arquivo) -> None:
    """A política central de anexo privado, com o limite de tamanho do importador.

    O processo inteiro passa fácil do limite geral de anexo (10 MB). O
    tamanho é conferido aqui; a função central confere o resto (tipo real,
    PDF que abre, antivírus se ligado) vendo o arquivo com tamanho zero.
    """
    if not str(getattr(arquivo, "name", "") or "").lower().endswith(".pdf"):
        raise ValidationError("Envie o PDF do processo, como o eProtocolo gera (Processo_….pdf).")
    limite = limite_de_bytes()
    tamanho = int(getattr(arquivo, "size", 0) or 0)
    if tamanho > limite:
        raise ValidationError(f"O arquivo passa do limite de {limite // _MIB} MB para importar um processo.")
    try:
        arquivo.size = 0
        validate_private_document_upload(arquivo)
    finally:
        arquivo.size = tamanho


def hash_do_arquivo(dados: bytes) -> str:
    return hashlib.sha256(dados).hexdigest()


def _marca(hash_sha256: str) -> str:
    return f"ref. {hash_sha256[:TAMANHO_REFERENCIA]}"


def importacao_anterior(hash_sha256: str) -> dict | None:
    """Quando e em quais solicitações o mesmo arquivo já foi importado (pelo histórico); None se nunca."""
    registros = list(
        HistoricoCoffeeBreak.objects.filter(descricao__contains=_marca(hash_sha256))
        .select_related("solicitacao")
        .order_by("-criado_em", "-pk")[:10]
    )
    if not registros:
        return None
    vistas, solicitacoes = set(), []
    for registro in registros:
        if registro.solicitacao_id not in vistas:
            vistas.add(registro.solicitacao_id)
            solicitacoes.append(_resumo_da_solicitacao(registro.solicitacao))
    return {"quando": _momento(registros[0].criado_em), "solicitacoes": solicitacoes}


# ─────────────────────────────────────────────────────────────────
# Formatos
# ─────────────────────────────────────────────────────────────────

def _sem_zeros(valor) -> str:
    """Nº de nota fiscal para comparar: só dígitos, sem os zeros da frente ("000.008.952" → "8952")."""
    digitos = re.sub(r"\D", "", str(valor or ""))
    return str(int(digitos)) if digitos else ""


def _reais(valor) -> str:
    if valor is None:
        return ""
    inteiro, _, centavos = f"{Decimal(valor):,.2f}".partition(".")
    return f"R$ {inteiro.replace(',', '.')},{centavos}"


def _dia(valor) -> str:
    if isinstance(valor, datetime):
        valor = timezone.localtime(valor).date() if timezone.is_aware(valor) else valor.date()
    return f"{valor:%d/%m/%Y}" if valor else ""


def _momento(valor) -> str:
    if not valor:
        return ""
    return timezone.localtime(valor).strftime("%d/%m/%Y %H:%M") if timezone.is_aware(valor) else f"{valor:%d/%m/%Y %H:%M}"


def _como_data(valor) -> date | None:
    if isinstance(valor, datetime):
        return timezone.localtime(valor).date() if timezone.is_aware(valor) else valor.date()
    return valor if isinstance(valor, date) else None


def _paginas(indices) -> str:
    """Índices do PDF (a partir de 0) como a pessoa vê: "pág. 4", "págs. 4–5", "págs. 3, 7–9"."""
    numeros = sorted({int(i) + 1 for i in indices})
    if not numeros:
        return ""
    trechos, inicio, anterior = [], numeros[0], numeros[0]
    for numero in numeros[1:] + [None]:
        if numero is not None and numero == anterior + 1:
            anterior = numero
            continue
        trechos.append(f"{inicio}" if inicio == anterior else f"{inicio}–{anterior}")
        if numero is not None:
            inicio = anterior = numero
    rotulo = "pág." if len(numeros) == 1 else "págs."
    return f"{rotulo} {', '.join(trechos)}"


def _rotulo(solicitacao) -> str:
    return f"Solicitação {solicitacao.numero or '#' + str(solicitacao.pk)}"


def _url(solicitacao) -> str:
    return reverse("coffee_break:etapa_protocolo", args=[solicitacao.pk])


def _resumo_da_solicitacao(solicitacao) -> dict:
    return {"pk": solicitacao.pk, "rotulo": _rotulo(solicitacao), "url": _url(solicitacao)}


def _grupo(solicitacao) -> int:
    """A principal do pagamento (a própria, sem pagamento conjunto)."""
    return solicitacao.pagamento_com_id or solicitacao.pk


def _juntar(itens) -> str:
    itens = [str(i) for i in itens if i]
    if len(itens) <= 1:
        return "".join(itens)
    return ", ".join(itens[:-1]) + " e " + itens[-1]


# ─────────────────────────────────────────────────────────────────
# O plano
# ─────────────────────────────────────────────────────────────────

@dataclass
class NotaDoProcesso:
    """Uma nota fiscal do processo e a solicitação que a recebe."""

    ordem: int
    numero: str
    valor: Decimal | None
    emissao: date | None
    cnpjs: list[str]
    paginas: list[int]
    rotacoes: dict[int, int] = field(default_factory=dict)
    solicitacao_id: int | None = None
    como: str = ""
    nao_anexar: bool = False

    @property
    def rotulo(self) -> str:
        return f"Nota fiscal {self.numero}" if self.numero else "Nota fiscal sem número lido"


@dataclass
class CertidaoDoProcesso:
    """Uma certidão do processo e se ela atualiza a do fornecedor."""

    ordem: int
    tipo: str
    validade: date | None
    cnpj: str
    paginas: list[int]
    por_ocr: bool
    fornecedor_id: int | None = None
    situacao: str = ""
    atual: date | None = None

    @property
    def rotulo(self) -> str:
        return f"Certidão {_ROTULO_CERTIDAO.get(self.tipo, '')}".strip()


@dataclass
class Escolhas:
    """O que a pessoa decidiu na conferência.

    `solicitacoes`: as marcadas (o pagamento conjunto de cada uma entra
    inteiro); `notas`: ordem do documento → pk da solicitação que recebe a
    nota (0 = não anexar; ausente = pelo número, como na leitura).
    """

    solicitacoes: list[int] = field(default_factory=list)
    notas: dict[int, int] = field(default_factory=dict)
    outras: list[str] = field(default_factory=list)

    @classmethod
    def do_formulario(cls, dados) -> "Escolhas":
        """Lê `solicitacoes` (várias), `outras` ("41/2026, 42/2026") e `nota-<ordem>` do POST."""
        escolhas = cls()
        for valor in dados.getlist("solicitacoes"):
            if str(valor).isdigit():
                escolhas.solicitacoes.append(int(valor))
        escolhas.outras = [n for n in re.split(r"[\s,;]+", dados.get("outras") or "") if n]
        for chave in dados.keys():
            m = re.fullmatch(r"nota-(\d{1,4})", chave)
            valor = str(dados.get(chave) or "").strip()
            if m and valor.isdigit():
                escolhas.notas[int(m.group(1))] = int(valor)
        return escolhas


@dataclass
class Plano:
    """O que a leitura achou e o que a importação vai fazer (nada gravado ainda)."""

    nome_arquivo: str
    hash_sha256: str
    protocolo: str = ""
    volume: int | None = None
    eh_eprotocolo: bool = False
    total_paginas: int = 0
    oficio: tuple[int, int] | None = None
    pcpr: str = ""
    data_oficio: date | None = None
    despacho_gaf: date | None = None
    notas_citadas: list[str] = field(default_factory=list)
    notas: list[NotaDoProcesso] = field(default_factory=list)
    certidoes: list[CertidaoDoProcesso] = field(default_factory=list)
    documentos: list[dict] = field(default_factory=list)
    lidos: list[str] = field(default_factory=list)
    cnpjs: set[str] = field(default_factory=set)
    solicitacoes: list[SolicitacaoCoffeeBreak] = field(default_factory=list)
    candidatas: list[SolicitacaoCoffeeBreak] = field(default_factory=list)
    evidencias: dict[int, list[str]] = field(default_factory=lambda: defaultdict(list))
    conferir: list[str] = field(default_factory=list)
    #: Solicitações do pagamento em que algo desmente o processo: a conferência as mostra desmarcadas.
    contraditas: set[int] = field(default_factory=set)
    avisos: list[str] = field(default_factory=list)
    anterior: dict | None = None

    @property
    def protocolo_formatado(self) -> str:
        return format_protocolo(self.protocolo) if self.protocolo else ""

    @property
    def oficio_formatado(self) -> str:
        return f"{self.oficio[0]}/{self.oficio[1]}" if self.oficio else ""

    @property
    def referencia(self) -> str:
        return self.hash_sha256[:TAMANHO_REFERENCIA]

    @property
    def reconhecido(self) -> bool:
        """Achou algo de um processo de pagamento: ofício, nota ou a moldura do eProtocolo com o número.

        O número tirado só do nome do arquivo ("Processo_….pdf") não basta.
        """
        return bool(
            self.oficio or self.pcpr or self.notas or self.notas_citadas or (self.protocolo and self.eh_eprotocolo)
        )

    @property
    def seguro(self) -> bool:
        """Identificação sem dúvida e toda nota com destino: aplica sem conferência."""
        return bool(self.solicitacoes) and not self.conferir

    def para_tela(self) -> dict:
        """O plano para a tela de conferência e resultado (só texto e números: vai para a sessão)."""
        alvo = {s.pk for s in self.solicitacoes}
        por_pk = {s.pk: s for s in [*self.solicitacoes, *self.candidatas]}
        candidatas = []
        for s in self.candidatas:
            dicas = [s.descricao_evento[:80]]
            if s.numero_nota_fiscal:
                dicas.append(f"nota {s.numero_nota_fiscal}")
            if s.protocolo_pagamento:
                dicas.append(f"protocolo {s.protocolo_pagamento}")
            if s.em_pagamento_conjunto:
                dicas.append("pagamento conjunto")
            if s.cancelada:
                dicas.append("cancelada")
            elif s.concluida:
                dicas.append("concluída")
            evidencias = self.evidencias.get(s.pk) or []
            candidatas.append({
                "pk": s.pk,
                "rotulo": _rotulo(s),
                "url": _url(s),
                "dica": " · ".join(d for d in dicas if d),
                "evidencias": list(evidencias),
                "marcada": s.pk in alvo and s.pk not in self.contraditas,
            })
        notas = []
        for nf in self.notas:
            destino = por_pk.get(nf.solicitacao_id)
            notas.append({
                "ordem": nf.ordem,
                "campo": f"nota-{nf.ordem}",
                "rotulo": nf.rotulo,
                "valor": _reais(nf.valor),
                "emissao": _dia(nf.emissao),
                "paginas": _paginas(nf.paginas),
                "solicitacao": str(nf.solicitacao_id) if nf.solicitacao_id else ("0" if nf.nao_anexar else ""),
                "destino": _rotulo(destino) if destino else "",
                "como": nf.como,
            })
        return {
            "arquivo": self.nome_arquivo,
            "referencia": self.referencia,
            "protocolo": self.protocolo_formatado,
            "volume": self.volume,
            "paginas": self.total_paginas,
            "eprotocolo": self.eh_eprotocolo,
            "oficio": self.oficio_formatado,
            "pcpr": self.pcpr,
            "data_oficio": _dia(self.data_oficio),
            "despacho_gaf": _dia(self.despacho_gaf),
            "seguro": self.seguro,
            "solicitacoes": [_resumo_da_solicitacao(s) for s in self.solicitacoes],
            "candidatas": candidatas,
            "notas": notas,
            "documentos": [dict(d) for d in self.documentos],
            "conferir": list(self.conferir),
            "avisos": list(self.avisos),
            "lidos": list(self.lidos),
            "anterior": self.anterior,
        }


# ─────────────────────────────────────────────────────────────────
# Leitura: o que o processo traz
# ─────────────────────────────────────────────────────────────────

def _texto(processo: Processo, indices) -> str:
    return "\n".join(processo.paginas[i].corpo for i in indices if 0 <= i < len(processo.paginas))


def _rotacoes(processo: Processo, indices) -> dict[int, int]:
    """O /Rotate que deixa cada página em pé, só onde muda (NF deitada numa digitalização)."""
    saida = {}
    for indice in indices:
        pagina = processo.paginas[indice]
        rotacao = rotacao_para_ficar_em_pe(pagina)
        if rotacao is not None and rotacao != pagina.rotacao:
            saida[indice] = rotacao
    return saida


def _extrair(plano: Plano, processo: Processo) -> None:
    """Os fatos do processo e a linha de cada documento na tela (o destino vem depois)."""
    plano.protocolo = processo.protocolo or ""
    plano.volume = processo.volume
    plano.eh_eprotocolo = processo.eh_eprotocolo
    plano.total_paginas = len(processo.paginas)
    plano.avisos.extend(processo.avisos)
    oficio_da_capa = None
    for doc in processo.documentos:
        dados = doc.dados or {}
        conteudo = doc.paginas_de_conteudo or doc.paginas
        linha = {
            "ordem": doc.ordem,
            "tipo": doc.tipo,
            "rotulo": tipos.ROTULOS.get(doc.tipo, tipos.ROTULOS[tipos.DESCONHECIDO]),
            "paginas": _paginas(doc.paginas),
            "titulo": doc.titulo,
            "resumo": "",
            "destino": "Só leitura",
            "tom": "neutro",
        }
        if doc.tipo == tipos.CAPA:
            oficio_da_capa = services.partes_numero(dados.get("numero_ano", ""))
            linha["resumo"] = f"Nº/Ano {dados['numero_ano']}" if dados.get("numero_ano") else ""
            linha["destino"] = "Identifica o pagamento"
        elif doc.tipo == tipos.OFICIO:
            if plano.oficio is None and dados.get("numero") and dados.get("ano"):
                plano.oficio = (int(dados["numero"]), int(dados["ano"]))
                plano.pcpr = str(dados.get("pcpr_protocolo") or "")
                plano.data_oficio = _como_data(dados.get("data"))
            plano.notas_citadas.extend(_sem_zeros(n) for n in dados.get("notas_fiscais") or [])
            partes = []
            if dados.get("numero") and dados.get("ano"):
                partes.append(f"{dados['numero']}/{dados['ano']}")
            if dados.get("pcpr_protocolo"):
                partes.append(f"PCPR {dados['pcpr_protocolo']}")
            if dados.get("data"):
                partes.append(_dia(dados["data"]))
            linha["resumo"] = " · ".join(partes)
            linha["destino"] = "Identifica o pagamento"
        elif doc.tipo == tipos.NOTA_FISCAL:
            nota = NotaDoProcesso(
                ordem=doc.ordem,
                numero=_sem_zeros(dados.get("numero")),
                valor=dados.get("valor"),
                emissao=_como_data(dados.get("emissao")),
                cnpjs=achar_cnpjs(_texto(processo, conteudo)),
                paginas=list(conteudo),
                rotacoes=_rotacoes(processo, conteudo),
            )
            plano.notas.append(nota)
            plano.cnpjs.update(nota.cnpjs)
            partes = [f"Nº {nota.numero}" if nota.numero else "número não lido"]
            if nota.valor is not None:
                partes.append(_reais(nota.valor))
            if nota.emissao:
                partes.append(f"emitida em {_dia(nota.emissao)}")
            linha["resumo"] = " · ".join(partes)
        elif doc.tipo == tipos.CERTIFICO:
            if dados.get("nota_fiscal"):
                plano.notas_citadas.append(_sem_zeros(dados["nota_fiscal"]))
                linha["resumo"] = f"da nota {dados['nota_fiscal']}"
            if dados.get("cnpj"):
                plano.cnpjs.add(dados["cnpj"])
            linha["destino"] = "Só leitura (o sistema gera o certifico)"
        elif doc.tipo == tipos.CERTIDAO:
            lidos = [t for t in dados.get("tipos") or [] if t in _ROTULO_CERTIDAO]
            certidao = CertidaoDoProcesso(
                ordem=doc.ordem,
                tipo=lidos[0] if len(lidos) == 1 else "",
                validade=_como_data(dados.get("validade")),
                cnpj=str(dados.get("cnpj") or ""),
                paginas=list(conteudo),
                por_ocr=any(processo.paginas[i].ocr or processo.paginas[i].sem_texto for i in conteudo),
            )
            plano.certidoes.append(certidao)
            if certidao.cnpj:
                plano.cnpjs.add(certidao.cnpj)
            partes = [_ROTULO_CERTIDAO.get(certidao.tipo, "tipo não reconhecido")]
            if certidao.validade:
                partes.append(f"válida até {_dia(certidao.validade)}")
            linha["resumo"] = " · ".join(partes)
        elif doc.tipo == tipos.DESPACHO:
            destino = str(dados.get("destino") or "")
            dia = _como_data(dados.get("data"))
            linha["resumo"] = " · ".join(p for p in (f"Ao {destino}" if destino else "", _dia(dia)) if p)
            if dia and re.search(r"\bGAF\b", normalizar(destino)):
                plano.despacho_gaf = min(plano.despacho_gaf or dia, dia)
                linha["destino"] = "Atesto e envio ao GAF"
        elif doc.tipo in (tipos.NOTA_EMPENHO, tipos.NOTA_LIQUIDACAO):
            numero = dados.get("numero") or ""
            partes = [numero, _reais(dados.get("valor"))]
            if doc.tipo == tipos.NOTA_LIQUIDACAO and dados.get("notas_fiscais"):
                citadas = [_sem_zeros(n.get("numero")) for n in dados["notas_fiscais"]]
                plano.notas_citadas.extend(citadas)
                partes.append("notas " + _juntar(citadas))
            if doc.tipo == tipos.NOTA_EMPENHO and dados.get("cnpj"):
                plano.cnpjs.add(dados["cnpj"])
            linha["resumo"] = " · ".join(p for p in partes if p)
            linha["destino"] = "Só leitura (sem campo no sistema)"
            if numero:
                plano.lidos.append(f"{linha['rotulo']} {numero}" + (f" ({_reais(dados.get('valor'))})" if dados.get("valor") else "") + ": lida, sem campo no sistema.")
        elif doc.tipo in (tipos.CONTRATO, tipos.ADITIVO):
            partes = [dados.get("numero") or ""]
            if doc.tipo == tipos.ADITIVO and dados.get("contrato"):
                partes.append(f"do contrato {dados['contrato']}")
            linha["resumo"] = " ".join(p for p in partes if p)
            linha["destino"] = "Só leitura (vem do cadastro do contrato)"
        elif doc.tipo == tipos.DESCONHECIDO:
            linha["destino"] = "Não identificado"
        plano.documentos.append(linha)

    if oficio_da_capa and plano.oficio and oficio_da_capa != plano.oficio:
        plano.avisos.append(
            f"A capa diz Nº/Ano {oficio_da_capa[0]}/{oficio_da_capa[1]} e o ofício, {plano.oficio_formatado}: vale o do ofício."
        )
    plano.oficio = plano.oficio or oficio_da_capa
    plano.notas_citadas = list(dict.fromkeys(n for n in plano.notas_citadas if n))
    if not plano.protocolo:
        plano.avisos.append(
            "Não achei o número do processo do eProtocolo: o protocolo de pagamento não é preenchido."
            if not plano.eh_eprotocolo
            else "O número do processo não foi lido: o protocolo de pagamento não é preenchido."
        )
    faltam = [n for n in plano.notas_citadas if n not in {nf.numero for nf in plano.notas}]
    if faltam and plano.notas:
        plano.avisos.append(f"Nota{'s' if len(faltam) > 1 else ''} {_juntar(faltam)} citada{'s' if len(faltam) > 1 else ''} no processo, mas o PDF da nota não está nele.")


# ─────────────────────────────────────────────────────────────────
# Identificação
# ─────────────────────────────────────────────────────────────────

def _valores(consulta, *campos):
    return consulta.values_list("pk", *campos).iterator()


def _identificar(plano: Plano, ancora, escolhas: Escolhas | None) -> None:
    """Acha as solicitações do processo e decide se precisa de conferência."""
    evidencias = plano.evidencias
    pelo_processo: set[int] = set()
    pela_nota: set[int] = set()
    # Nota só citada (no ofício, no certifico, na liquidação), sem o PDF dela no
    # processo: pista fraca — sozinha, identifica só com conferência.
    pela_citacao: set[int] = set()
    base = SolicitacaoCoffeeBreak.objects.filter(cancelada=False)
    com_protocolo = base.exclude(protocolo_pagamento="", protocolo_pcpr_oficio="")

    if plano.protocolo:
        for pk, pagamento, do_oficio in _valores(com_protocolo, "protocolo_pagamento", "protocolo_pcpr_oficio"):
            if normalize_protocolo(pagamento) == plano.protocolo:
                evidencias[pk].append(f"o protocolo de pagamento já é o {plano.protocolo_formatado}")
                pelo_processo.add(pk)
            elif normalize_protocolo(do_oficio) == plano.protocolo:
                evidencias[pk].append(f"o protocolo do ofício é o do processo ({plano.protocolo_formatado})")
                pelo_processo.add(pk)
    pcpr = normalize_protocolo(plano.pcpr)
    if len(pcpr) >= 9 and pcpr != plano.protocolo:
        for pk, pagamento, do_oficio in _valores(com_protocolo, "protocolo_pagamento", "protocolo_pcpr_oficio"):
            if pcpr in (normalize_protocolo(do_oficio), normalize_protocolo(pagamento)):
                evidencias[pk].append(f"PCPR protocolo n.º {plano.pcpr}, do ofício")
                pelo_processo.add(pk)
    if plano.oficio:
        numero, ano = plano.oficio
        for pk, valor in _valores(base.filter(numero_oficio__endswith=f"/{ano}"), "numero_oficio"):
            if services.partes_numero(valor) == (numero, ano):
                evidencias[pk].append(f"ofício {numero}/{ano}")
                pelo_processo.add(pk)

    lidas = {nf.numero for nf in plano.notas if nf.numero}
    citadas = set(plano.notas_citadas) - lidas
    por_nota: dict[str, set[int]] = defaultdict(set)
    if lidas or citadas:
        for pk, valor in _valores(base.exclude(numero_nota_fiscal=""), "numero_nota_fiscal"):
            numero = _sem_zeros(valor)
            if numero in lidas:
                por_nota[numero].add(pk)
            elif numero in citadas:
                evidencias[pk].append(f"nota fiscal {numero}, citada no processo")
                pela_citacao.add(pk)

    pks = set(evidencias) | {pk for grupo in por_nota.values() for pk in grupo}
    if ancora is not None:
        pks.add(ancora.pk)
    if escolhas is not None:
        pks.update(escolhas.solicitacoes)
    objetos = {
        s.pk: s
        for s in SolicitacaoCoffeeBreak.objects.filter(pk__in=pks).select_related("lote__contrato__fornecedor")
    }

    # A mesma numeração de nota em outro fornecedor não conta.
    for nf in plano.notas:
        for pk in sorted(por_nota.get(nf.numero, ())):
            cnpj = objetos[pk].lote.contrato.fornecedor.cnpj
            if nf.cnpjs and cnpj and cnpj not in nf.cnpjs:
                continue
            evidencias[pk].append(f"nota fiscal {nf.numero}")
            pela_nota.add(pk)

    grupos_processo = {_grupo(objetos[pk]) for pk in pelo_processo if pk in objetos}
    grupos_nota = {_grupo(objetos[pk]) for pk in pela_nota}
    grupos_citacao = {_grupo(objetos[pk]) for pk in pela_citacao if pk in objetos}
    achadas = pelo_processo | pela_nota | pela_citacao

    def nomes(grupos):
        return _juntar(sorted({_rotulo(objetos[pk]) for pk in achadas if _grupo(objetos[pk]) in grupos}))

    alvo: set[int] = set()
    if escolhas is not None:
        numeros = [n for n in escolhas.outras if n]
        extras = {s.numero: s for s in SolicitacaoCoffeeBreak.objects.filter(numero__in=numeros)} if numeros else {}
        for numero in numeros:
            if numero in extras:
                objetos.setdefault(extras[numero].pk, extras[numero])
            else:
                plano.avisos.append(f"Não achei a solicitação {numero}.")
        escolhidas = [objetos[pk] for pk in escolhas.solicitacoes if pk in objetos] + list(extras.values())
        alvo = {_grupo(s) for s in escolhidas}
    elif ancora is not None:
        alvo = {_grupo(ancora)}
        outros = (grupos_processo | grupos_nota) - alvo
        if outros:
            plano.conferir.append(
                f"O processo parece ser de {nomes(outros)}, não da {_rotulo(ancora)}: confira antes de aplicar."
            )
    elif len(grupos_processo) == 1:
        alvo = set(grupos_processo)
        fora = grupos_nota - alvo
        if fora:
            plano.conferir.append(
                f"Uma nota do processo está em {nomes(fora)}, que não é do mesmo pagamento: confira."
            )
    elif len(grupos_processo) > 1:
        comuns = grupos_processo & grupos_nota
        alvo = comuns if len(comuns) == 1 else set()
        plano.conferir.append(f"Mais de um pagamento combina com o processo ({nomes(grupos_processo)}): marque o certo.")
    elif grupos_nota:
        alvo = set(grupos_nota)
        if len(grupos_nota) > 1:
            plano.avisos.append(
                f"As notas do processo estão em {nomes(grupos_nota)}, que não estão em pagamento conjunto no "
                "sistema: o protocolo vai para todas. Se for o caso, vincule-as na etapa 2."
            )
    elif grupos_citacao:
        alvo = set(grupos_citacao)
        plano.conferir.append(
            f"{nomes(grupos_citacao)} só combina{'m' if len(pela_citacao) > 1 else ''} pelo número da nota citado no "
            "processo (o PDF da nota não está nele): confira."
        )
    else:
        plano.conferir.append(
            "Nenhuma solicitação combina com o processo (protocolo, ofício, PCPR ou notas fiscais): escolha abaixo."
        )

    membros = []
    if alvo:
        membros = list(
            SolicitacaoCoffeeBreak.objects.filter(Q(pk__in=alvo) | Q(pagamento_com_id__in=alvo))
            .select_related("lote__contrato__fornecedor")
            .order_by("numero", "pk")
        )
    plano.solicitacoes = membros

    if escolhas is None:
        _contradicoes(plano, membros, lidas)

    # A conferência oferece as identificadas e as do fornecedor do processo ainda sem protocolo.
    candidatas = {s.pk: s for s in membros}
    for pk in sorted(achadas):
        candidatas.setdefault(pk, objetos[pk])
    if ancora is not None:
        candidatas.setdefault(ancora.pk, objetos.get(ancora.pk, ancora))
    if len(candidatas) < MAX_CANDIDATAS:
        abertas = base.filter(data_envio_empresa__isnull=True, protocolo_pagamento="").exclude(pk__in=candidatas)
        if plano.cnpjs:
            abertas = abertas.filter(lote__contrato__fornecedor__cnpj__in=plano.cnpjs)
        limite = MAX_CANDIDATAS - len(candidatas)
        for s in abertas.select_related("lote__contrato__fornecedor").order_by("-data_solicitacao", "-pk")[:limite]:
            candidatas[s.pk] = s
    plano.candidatas = sorted(candidatas.values(), key=lambda s: (s.numero or "", s.pk))


def _contradicoes(plano: Plano, membros, lidas: set[str]) -> None:
    """O que, nas solicitações achadas, desmente o processo: vai para a conferência, desmarcado.

    - o fornecedor do pagamento não aparece no processo (nota, certidão, empenho);
    - a solicitação já tem uma nota que o processo não traz nem cita;
    - a solicitação já tem o protocolo de pagamento de outro processo.
    """
    if membros and plano.cnpjs:
        for fornecedor in {s.lote.contrato.fornecedor for s in membros}:
            if fornecedor.cnpj and fornecedor.cnpj not in plano.cnpjs:
                plano.conferir.append(
                    f"O CNPJ de {fornecedor.razao_social} ({fornecedor.cnpj_formatado}), o fornecedor da solicitação, "
                    "não aparece no processo: confira."
                )
    do_processo = lidas | set(plano.notas_citadas)
    for s in membros:
        if s.cancelada:
            continue
        nota = _sem_zeros(s.numero_nota_fiscal)
        if lidas and nota and nota not in do_processo:
            plano.contraditas.add(s.pk)
            plano.conferir.append(
                f"{_rotulo(s)} tem a nota {s.numero_nota_fiscal}, que não está no processo: confira se o processo é dela."
            )
        protocolo = normalize_protocolo(s.protocolo_pagamento)
        if plano.protocolo and protocolo and protocolo != plano.protocolo and not _copia_do_pcpr(s, plano):
            plano.contraditas.add(s.pk)
            plano.conferir.append(
                f"{_rotulo(s)} já tem o protocolo de pagamento {s.protocolo_pagamento}, de outro processo: confira."
            )


def _valor_esperado(solicitacao) -> Decimal | None:
    """Quantidade × valor unitário do contrato — o que a nota da OS deve valer."""
    unitario = solicitacao.lote.contrato.valor_unitario
    if not unitario or not solicitacao.quantidade:
        return None
    return (Decimal(solicitacao.quantidade) * unitario).quantize(_CENTAVO)


def _atribuir_notas(plano: Plano, escolhas: Escolhas | None) -> None:
    """A solicitação de cada nota: a escolhida, a de mesmo número, a de valor igual ou a única sem nota."""
    alvo = [s for s in plano.solicitacoes if not s.cancelada]
    por_pk = {s.pk: s for s in alvo}
    usadas: set[int] = set()

    def atribuir(nota, solicitacao, como):
        nota.solicitacao_id, nota.como = solicitacao.pk, como
        usadas.add(solicitacao.pk)

    for nota in plano.notas:
        escolhida = escolhas.notas.get(nota.ordem) if escolhas else None
        if escolhida is not None:
            if escolhida == 0:
                nota.nao_anexar, nota.como = True, "não anexar"
            elif escolhida in por_pk:
                atribuir(nota, por_pk[escolhida], "escolhida na conferência")
            else:
                nota.nao_anexar = True
                plano.avisos.append(f"{nota.rotulo}: a solicitação escolhida não está entre as marcadas; a nota não foi anexada.")
            continue
        iguais = [s for s in alvo if nota.numero and _sem_zeros(s.numero_nota_fiscal) == nota.numero and s.pk not in usadas]
        if iguais:
            atribuir(nota, iguais[0], "pelo número")

    def livres():
        return [n for n in plano.notas if n.solicitacao_id is None and not n.nao_anexar]

    def sem_nota():
        return [s for s in alvo if not s.numero_nota_fiscal.strip() and s.pk not in usadas]

    for nota in livres():
        if nota.valor is None:
            continue
        mesmas = [s for s in sem_nota() if _valor_esperado(s) == nota.valor]
        if len(mesmas) == 1:
            atribuir(nota, mesmas[0], "pelo valor (quantidade × valor unitário)")
    if len(livres()) == 1 and len(sem_nota()) == 1:
        atribuir(livres()[0], sem_nota()[0], "a única do pagamento ainda sem nota")

    for nota in livres():
        mensagem = f"{nota.rotulo} ({_paginas(nota.paginas)}) não tem solicitação neste pagamento"
        if escolhas is None and plano.solicitacoes:
            plano.conferir.append(mensagem + ": escolha abaixo quem a recebe, ou “Não anexar”.")
        elif plano.solicitacoes:
            plano.avisos.append(mensagem + ": não foi anexada.")


def _conferir_certidoes(plano: Plano) -> None:
    """Se cada certidão do processo é do fornecedor do pagamento e mais nova que a cadastrada."""
    fornecedores = {s.lote.contrato.fornecedor.pk: s.lote.contrato.fornecedor for s in plano.solicitacoes}
    por_cnpj = {f.cnpj: f for f in fornecedores.values() if f.cnpj}
    vigentes = {pk: certidoes.vigentes(f) for pk, f in fornecedores.items()}
    for certidao in plano.certidoes:
        if not certidao.tipo:
            certidao.situacao = "sem_tipo"
            continue
        fornecedor = por_cnpj.get(certidao.cnpj) if certidao.cnpj else None
        if fornecedor is None and len(fornecedores) == 1:
            unico = next(iter(fornecedores.values()))
            if not certidao.cnpj or not unico.cnpj:
                fornecedor = unico
        if fornecedor is None:
            certidao.situacao = "outro_cnpj" if fornecedores else "sem_fornecedor"
            continue
        certidao.fornecedor_id = fornecedor.pk
        atual = vigentes[fornecedor.pk].get(certidao.tipo)
        certidao.atual = atual.validade if atual else None
        if certidao.validade is None:
            certidao.situacao = "sem_validade"
        elif certidao.atual and certidao.atual >= certidao.validade:
            certidao.situacao = "igual" if certidao.atual == certidao.validade else "antiga"
        elif certidao.por_ocr:
            certidao.situacao = "imagem"
        else:
            certidao.situacao = "atualiza"


def _destinos(plano: Plano) -> None:
    """O destino de cada documento na tela, depois da identificação."""
    por_ordem = {linha["ordem"]: linha for linha in plano.documentos}
    por_pk = {s.pk: s for s in [*plano.solicitacoes, *plano.candidatas]}
    for nota in plano.notas:
        linha = por_ordem.get(nota.ordem)
        if linha is None:
            continue
        if nota.solicitacao_id in por_pk:
            linha["destino"] = f"{_rotulo(por_pk[nota.solicitacao_id])} — {nota.como}"
            linha["tom"] = "ok"
        elif nota.nao_anexar:
            linha["destino"] = "Não entra"
        else:
            linha["destino"], linha["tom"] = "Sem solicitação", "pendente"
    for certidao in plano.certidoes:
        linha = por_ordem.get(certidao.ordem)
        if linha is not None:
            linha["destino"] = _SITUACOES_CERTIDAO.get(certidao.situacao, "Só leitura").capitalize()
            linha["tom"] = "ok" if certidao.situacao == "atualiza" else "neutro"


def analisar(dados: bytes, nome_arquivo: str = "", *, ancora=None, escolhas: Escolhas | None = None) -> Plano:
    """Lê o processo e diz o que a importação faria. Não grava nada.

    `ancora`: a solicitação de onde a importação foi aberta (etapa 3, ⋮ da
    lista). `escolhas`: as decisões da conferência. Levanta
    `core.leitura.pdf.ArquivoIlegivel` se o PDF não abrir.
    """
    processo = ler_processo(dados, nome_arquivo)
    plano = Plano(nome_arquivo=nome_arquivo, hash_sha256=hash_do_arquivo(dados))
    _extrair(plano, processo)
    _identificar(plano, ancora, escolhas)
    _atribuir_notas(plano, escolhas)
    _conferir_certidoes(plano)
    _destinos(plano)
    plano.anterior = importacao_anterior(plano.hash_sha256)
    if plano.anterior and escolhas is None:
        plano.conferir.append(
            f"Este mesmo arquivo já foi importado em {plano.anterior['quando']}. Aplicar de novo não duplica nada: "
            "só completa o que ainda faltar."
        )
    return plano


# ─────────────────────────────────────────────────────────────────
# Aplicação
# ─────────────────────────────────────────────────────────────────

@dataclass
class Resultado:
    """O que a importação fez, por solicitação, e o que ficou para a pessoa."""

    protocolo: str
    solicitacoes: list[dict] = field(default_factory=list)
    certidoes: list[str] = field(default_factory=list)
    pendencias: list[str] = field(default_factory=list)
    resumo: str = ""

    def para_json(self) -> dict:
        return {
            "protocolo": self.protocolo,
            "solicitacoes": self.solicitacoes,
            "certidoes": self.certidoes,
            "pendencias": self.pendencias,
            "resumo": self.resumo,
        }


def _copia_do_pcpr(solicitacao, plano: Plano) -> bool:
    """O protocolo de pagamento é só a cópia do "PCPR Protocolo n.º" do ofício (número interno, não o do eProtocolo)."""
    atual = normalize_protocolo(solicitacao.protocolo_pagamento)
    pcpr = normalize_protocolo(plano.pcpr)
    return bool(atual) and len(atual) != 9 and atual == pcpr and atual == normalize_protocolo(solicitacao.protocolo_pcpr_oficio or pcpr)


def _aplicar_na_solicitacao(solicitacao, plano: Plano, dados: bytes, usuario, herdado: dict) -> dict:
    """Completa uma solicitação com o processo; devolve {feito, pendente} para a tela.

    `herdado` (pk → frases) é o que outra OS do mesmo pagamento já gravou nesta
    pelo espelhamento (protocolo, atesto): entra no resultado e no histórico dela.
    """
    herdadas = herdado.pop(solicitacao.pk, [])
    feito: list[str] = list(herdadas)
    pendente: list[str] = []
    saida = {**_resumo_da_solicitacao(solicitacao), "feito": feito, "pendente": pendente}
    origem = (
        f"Processo de pagamento {plano.protocolo_formatado or 'sem número'} importado "
        f"({plano.nome_arquivo}; {_marca(plano.hash_sha256)})"
    )
    if herdadas:
        services.registrar_historico(solicitacao, usuario, AcaoHistoricoCoffeeBreak.ATUALIZACAO, f"{origem}: " + " ".join(herdadas))
    if solicitacao.cancelada or solicitacao.concluida:
        situacao = "Cancelada" if solicitacao.cancelada else "Pagamento concluído"
        pendente.append(f"{situacao}: " + ("só recebeu o que é do pagamento conjunto." if herdadas else "nada foi alterado."))
        return saida

    campos: list[str] = []
    notas = [n for n in plano.notas if n.solicitacao_id == solicitacao.pk]
    nota = notas[0] if notas else None
    if len(notas) > 1:
        pendente.append(f"O processo trouxe {len(notas)} notas para esta solicitação: só a {nota.numero or 'primeira'} foi usada.")
    pdf_da_nota = None
    if nota is not None:
        atual = _sem_zeros(solicitacao.numero_nota_fiscal)
        if not atual and nota.numero:
            solicitacao.numero_nota_fiscal = nota.numero
            campos.append("numero_nota_fiscal")
            feito.append(f"Nota fiscal {nota.numero} registrada (lida do processo).")
        elif atual and nota.numero and atual != nota.numero:
            pendente.append(
                f"A nota do processo é a {nota.numero}, mas a solicitação tem a {solicitacao.numero_nota_fiscal}: nada foi trocado."
            )
            nota = None
        if nota is not None and not solicitacao.arquivo_nota_fiscal:
            pdf_da_nota = recortar(dados, nota.paginas, nota.rotacoes)
    elif not solicitacao.numero_nota_fiscal.strip():
        pendente.append("O processo não traz a nota fiscal desta solicitação.")

    # O protocolo de pagamento vem depois da nota (é a ordem do clean()).
    if plano.protocolo:
        atual = normalize_protocolo(solicitacao.protocolo_pagamento)
        if atual == plano.protocolo:
            pass
        elif not atual and not solicitacao.numero_nota_fiscal.strip():
            pendente.append("Sem a nota fiscal, o protocolo de pagamento fica para depois (a nota vem antes dele).")
        elif not atual:
            solicitacao.protocolo_pagamento = plano.protocolo_formatado
            campos.append("protocolo_pagamento")
            feito.append(f"Protocolo de pagamento: {plano.protocolo_formatado} (o nº do processo).")
        elif _copia_do_pcpr(solicitacao, plano):
            anterior = solicitacao.protocolo_pagamento
            solicitacao.protocolo_pagamento = plano.protocolo_formatado
            campos.append("protocolo_pagamento")
            feito.append(
                f"Protocolo de pagamento trocado de {anterior} (o PCPR do ofício) para {plano.protocolo_formatado} (o nº do processo)."
            )
        else:
            pendente.append(
                f"Já tem o protocolo de pagamento {solicitacao.protocolo_pagamento}, diferente do processo "
                f"({plano.protocolo_formatado}): nada foi trocado."
            )

    # O atesto e envio ao GAF é o dia do despacho ao GAF — só com o protocolo deste
    # processo gravado (a ordem do clean()), e uma vez.
    if (
        plano.despacho_gaf
        and not solicitacao.data_atesto_gaf
        and normalize_protocolo(solicitacao.protocolo_pagamento) == plano.protocolo
    ):
        if solicitacao.data_ordem_bancaria and solicitacao.data_ordem_bancaria < plano.despacho_gaf:
            pendente.append("O despacho ao GAF é posterior à ordem bancária registrada: o atesto não foi preenchido.")
        else:
            solicitacao.data_atesto_gaf = plano.despacho_gaf
            campos.append("data_atesto_gaf")
            feito.append(f"Atesto e envio ao GAF: {_dia(plano.despacho_gaf)} (data do despacho ao GAF).")

    if not campos and pdf_da_nota is None:
        if not feito and not pendente:
            feito.append("Já estava completa: nada a mudar.")
        return saida
    try:
        solicitacao.full_clean(exclude=["lote", "municipio", "criado_por"])
    except ValidationError as erro:
        mensagens = [m for lista in erro.message_dict.values() for m in lista] if hasattr(erro, "error_dict") else erro.messages
        pendente.append("Não foi gravado: " + " ".join(mensagens))
        feito[:] = herdadas
        solicitacao.refresh_from_db()
        return saida
    if pdf_da_nota is not None:
        nome = f"NF{nota.numero or solicitacao.pk}.pdf"
        solicitacao.arquivo_nota_fiscal.save(nome, ContentFile(pdf_da_nota), save=False)
        registrar_arquivo_criado(solicitacao.arquivo_nota_fiscal.storage, solicitacao.arquivo_nota_fiscal.name)
        campos.append("arquivo_nota_fiscal")
        feito.append(f"PDF da nota fiscal {nota.numero} anexado ({_paginas(nota.paginas)} do processo).")
    solicitacao.save(update_fields=[*dict.fromkeys(campos), "atualizado_em"])
    # O que é do pagamento vale para todas as OS do mesmo pagamento.
    espelhados = [c for c in campos if c in services.CAMPOS_ESPELHADOS]
    if espelhados and services.espelhar(solicitacao, espelhados, usuario, registrar=False):
        frases = {
            "protocolo_pagamento": f"Protocolo de pagamento: {solicitacao.protocolo_pagamento} (o do pagamento conjunto, com a {_rotulo(solicitacao)}).",
            "data_atesto_gaf": f"Atesto e envio ao GAF: {_dia(solicitacao.data_atesto_gaf)} (o do pagamento conjunto).",
        }
        for outra in solicitacao.grupo_pagamento():
            if outra.pk != solicitacao.pk:
                herdado.setdefault(outra.pk, []).extend(frases[c] for c in espelhados if c in frases)
    services.registrar_historico(
        solicitacao, usuario, AcaoHistoricoCoffeeBreak.ATUALIZACAO, f"{origem}: " + " ".join(feito[len(herdadas):])
    )
    return saida


def _aplicar_certidao(certidao: CertidaoDoProcesso, dados: bytes, usuario) -> str:
    """Registra a certidão do processo se, conferida pelo leitor das certidões, for mais nova."""
    fornecedor = Fornecedor.objects.get(pk=certidao.fornecedor_id)
    pdf = recortar(dados, certidao.paginas)
    try:
        validade, _aviso = certidoes.conferir(fornecedor, certidao.tipo, BytesIO(pdf), None)
    except ValidationError as erro:
        return f"{certidao.rotulo} de {fornecedor.razao_social} não entrou: {' '.join(erro.messages)}"
    vigente = certidoes.vigentes(fornecedor).get(certidao.tipo)
    if vigente and vigente.validade >= validade:
        return ""
    nova = certidoes.registrar(
        fornecedor, certidao.tipo, ContentFile(pdf, name=f"{certidao.tipo.lower()}.pdf"), validade, usuario
    )
    registrar_arquivo_criado(nova.arquivo.storage, nova.arquivo.name)
    antes = f" (a anterior valia até {_dia(vigente.validade)})" if vigente else ""
    return f"{certidao.rotulo} de {fornecedor.razao_social} atualizada: válida até {_dia(validade)}{antes}."


def aplicar(plano: Plano, dados: bytes, usuario=None) -> Resultado:
    """Grava o plano: nota, protocolo, atesto e certidões. Atômico, com os arquivos novos.

    Cada solicitação é relida com trava (`select_for_update`): o que outra
    pessoa gravou entre a leitura e a aplicação vale, e o que o processo traz
    só completa o que falta.
    """
    resultado = Resultado(protocolo=plano.protocolo_formatado)
    usuario = usuario if getattr(usuario, "is_authenticated", False) else None
    com_nota = {n.solicitacao_id for n in plano.notas if n.solicitacao_id}
    # Quem tem (ou recebe) a nota primeiro: grava o protocolo, que o espelhamento
    # leva às OS do mesmo pagamento ainda sem nota.
    ordem = sorted(
        plano.solicitacoes,
        key=lambda s: (not (s.numero_nota_fiscal.strip() or s.pk in com_nota), s.numero or "", s.pk),
    )
    herdado: dict[int, list[str]] = {}
    feitos: dict[int, dict] = {}
    with transacao_de_arquivos():
        for alvo in ordem:
            solicitacao = (
                SolicitacaoCoffeeBreak.objects.select_for_update()
                .select_related("lote__contrato__fornecedor")
                .get(pk=alvo.pk)
            )
            feitos[alvo.pk] = _aplicar_na_solicitacao(solicitacao, plano, dados, usuario, herdado)
        resultado.solicitacoes = [feitos[s.pk] for s in plano.solicitacoes]
        for certidao in plano.certidoes:
            if certidao.situacao == "atualiza":
                texto = _aplicar_certidao(certidao, dados, usuario)
                if texto:
                    (resultado.certidoes if "atualizada" in texto else resultado.pendencias).append(texto)
            elif certidao.situacao in ("imagem", "sem_validade", "outro_cnpj", "sem_tipo"):
                resultado.pendencias.append(f"{certidao.rotulo or 'Certidão'} ({_paginas(certidao.paginas)}): {_SITUACOES_CERTIDAO[certidao.situacao]}.")
    for nota in plano.notas:
        if nota.solicitacao_id is None and not nota.nao_anexar:
            resultado.pendencias.append(f"{nota.rotulo} ({_paginas(nota.paginas)}): nenhuma solicitação a recebeu.")
    resultado.resumo = _resumo(plano, resultado)
    logger.info(
        "coffee_break.importacao_processo aplicada",
        extra={"solicitacoes": len(resultado.solicitacoes), "notas": len(plano.notas), "certidoes": len(resultado.certidoes)},
    )
    return resultado


def _resumo(plano: Plano, resultado: Resultado) -> str:
    """Uma frase para a mensagem do topo."""
    rotulos = [s["rotulo"].replace("Solicitação ", "") for s in resultado.solicitacoes]
    quem = ("na solicitação " if len(rotulos) == 1 else "nas solicitações ") + _juntar(rotulos) if rotulos else "sem solicitação"
    feitos = [f for s in resultado.solicitacoes for f in s["feito"] if not f.startswith("Já estava")]
    partes = []
    anexadas = sum(1 for f in feitos if f.startswith("PDF da nota"))
    if anexadas:
        partes.append(f"{anexadas} nota{'s' if anexadas > 1 else ''} anexada{'s' if anexadas > 1 else ''}")
    if any(f.startswith("Protocolo de pagamento") for f in feitos):
        partes.append("protocolo de pagamento gravado")
    if any(f.startswith("Atesto") for f in feitos):
        partes.append(f"atesto em {_dia(plano.despacho_gaf)}")
    if resultado.certidoes:
        n = len(resultado.certidoes)
        partes.append("1 certidão atualizada" if n == 1 else f"{n} certidões atualizadas")
    processo = f"Processo {plano.protocolo_formatado}" if plano.protocolo else "Processo"
    if not partes:
        return f"{processo} ({quem.removeprefix('na ').removeprefix('nas ')}): nada a completar — os dados já estavam no sistema."
    return f"{processo} importado {quem}: " + ", ".join(partes) + "."
