"""O plano de uma importação: o que a leitura propôs, pronto para a tela e para o banco.

É o que fica em `ImportacaoProcesso.plano` (JSON) e o que a conferência edita.
Leva só o necessário para gravar e para mostrar — tipo, folhas, destino,
servidor, valor, data, operação e giro de cada documento —, nunca o texto do
documento nem CPF (LGPD): as evidências são frases como "CPF mascarado confere
com FULANO", sem o número.
"""

from __future__ import annotations

from dataclasses import asdict
from dataclasses import dataclass
from dataclasses import field
from datetime import date
from decimal import Decimal
from decimal import InvalidOperation

from ..models import PrestacaoDocumentoAnexo as Anexo

__all__ = [
    "IGNORAR",
    "DESTINOS",
    "DESTINOS_INDIVIDUAIS",
    "DESTINO_JUSTIFICATIVA",
    "DESTINO_TERMO",
    "DESTINO_ORDEM_SERVICO",
    "DESTINOS_DOCUMENTO",
    "ORIGENS",
    "ROTULO_DESTINO",
    "Candidato",
    "ItemPlano",
    "Plano",
]

#: O documento fica no processo e não vira anexo da prestação (capa, NF, termo…).
IGNORAR = "ignorar"

#: Para onde um documento pode ir, na ordem da prestação.
DESTINOS = (
    Anexo.TIPO_OFICIO_ASSINADO,
    Anexo.TIPO_DESPACHO,
    Anexo.TIPO_RT_ASSINADO,
    Anexo.TIPO_DB_ASSINADO,
    Anexo.TIPO_COMPROVANTE,
)
#: Os que são de um servidor (os outros são do ofício, compartilhados pela equipe).
DESTINOS_INDIVIDUAIS = frozenset({Anexo.TIPO_RT_ASSINADO, Anexo.TIPO_COMPROVANTE})

#: Documentos que o sistema gerou e que voltam assinados para o próprio documento
#: (versão assinada do PDF gerado — ver `artefatos`), não para a prestação. O
#: ofício assinado vai para os dois: a prestação e o documento do ofício.
DESTINO_JUSTIFICATIVA = "justificativa"
DESTINO_TERMO = "termo_autorizacao"
DESTINO_ORDEM_SERVICO = "ordem_servico"
DESTINOS_DOCUMENTO = (DESTINO_JUSTIFICATIVA, DESTINO_TERMO, DESTINO_ORDEM_SERVICO)

#: De que lista o processo foi enviado: decide a volta e o que a tela pergunta.
ORIGENS = ("prestacoes", "oficios", "termos")

ROTULO_DESTINO = {
    Anexo.TIPO_OFICIO_ASSINADO: "Ofício assinado",
    Anexo.TIPO_DESPACHO: "Despacho",
    Anexo.TIPO_RT_ASSINADO: "Relatório técnico",
    Anexo.TIPO_DB_ASSINADO: "Diário de bordo",
    Anexo.TIPO_COMPROVANTE: "Comprovante",
    DESTINO_JUSTIFICATIVA: "Justificativa (ofício)",
    DESTINO_TERMO: "Termo de autorização",
    DESTINO_ORDEM_SERVICO: "Ordem de serviço",
    IGNORAR: "Não entra",
}


def _decimal(valor) -> Decimal | None:
    if valor in (None, ""):
        return None
    try:
        numero = Decimal(str(valor).replace(",", "."))
    except (InvalidOperation, ValueError):
        return None
    return numero if numero.is_finite() else None


def _data(valor) -> date | None:
    if not valor:
        return None
    if isinstance(valor, date):
        return valor
    try:
        return date.fromisoformat(str(valor)[:10])
    except ValueError:
        return None


@dataclass
class Candidato:
    """Uma prestação (ou um termo do cadastro) a que o processo pode pertencer, com o porquê.

    O candidato comum é o ofício e a sua prestação. Um termo avulso (sem ofício),
    achado pelos servidores e pela data dos termos do PDF, vem com `termo_id` e
    sem prestação.
    """

    prestacao_id: int | None
    oficio_id: int | None
    rotulo: str
    pontos: float = 0.0
    motivos: list[str] = field(default_factory=list)
    fontes: list[str] = field(default_factory=list)
    termo_id: int | None = None

    @property
    def valor(self) -> str:
        """O valor no seletor da conferência: a prestação ("12") ou o termo ("termo:5")."""
        return f"termo:{self.termo_id}" if self.prestacao_id is None and self.termo_id else str(self.prestacao_id)


@dataclass
class ItemPlano:
    """Um documento do processo e o destino dele.

    - `paginas`: índices no PDF do processo (a partir de 0), com a folha de assinatura;
    - `rotacoes`: /Rotate final de cada página, pela leitura (chave = índice em texto,
      como o JSON guarda); `giro` soma o que a conferência pediu (↺ ↻), igual para
      todas as páginas do documento;
    - `destino`: um de `DESTINOS` (anexo da prestação), de `DESTINOS_DOCUMENTO`
      (versão assinada do documento gerado), `IGNORAR`, ou "" (não se sabe — a
      tela pergunta);
    - `servidor_id`: no termo, o servidor (cadastro), que decide qual termo recebe;
    - `ordem_servico_id`: na OS, qual ordem de serviço de Viagens;
    - `conferir`: por que a tela precisa ver este documento antes de gravar.
    """

    ordem: int
    paginas: list[int]
    titulo: str = ""
    tipo_lido: str = ""
    rotulo: str = ""
    confianca: float = 0.0
    destino: str = ""
    servidor_prestacao_id: int | None = None
    valor: str = ""
    data: str = ""
    operacao: str = ""
    rotacoes: dict[str, int] = field(default_factory=dict)
    #: O /Rotate de cada página como veio no processo (para saber se girou).
    rotacoes_originais: dict[str, int] = field(default_factory=dict)
    giro: int = 0
    rotacao_incerta: bool = False
    assinado: bool = False
    assinado_por: list[str] = field(default_factory=list)
    sem_texto: bool = False
    motivo: str = ""
    evidencias: list[str] = field(default_factory=list)
    conferir: list[str] = field(default_factory=list)
    servidor_id: int | None = None
    ordem_servico_id: int | None = None

    # -- leitura --------------------------------------------------------------
    @property
    def valor_decimal(self) -> Decimal | None:
        return _decimal(self.valor)

    @property
    def data_operacao(self) -> date | None:
        return _data(self.data)

    @property
    def individual(self) -> bool:
        return self.destino in DESTINOS_INDIVIDUAIS

    @property
    def entra(self) -> bool:
        """Vira anexo da prestação."""
        return self.destino in DESTINOS

    @property
    def vai_para_documento(self) -> bool:
        """Vira a versão assinada de um documento gerado (o ofício assinado também)."""
        return self.destino in DESTINOS_DOCUMENTO or self.destino == Anexo.TIPO_OFICIO_ASSINADO

    @property
    def grava(self) -> bool:
        """Grava alguma coisa: anexo da prestação ou versão assinada."""
        return self.entra or self.destino in DESTINOS_DOCUMENTO

    @property
    def decidido(self) -> bool:
        """O destino está definido e completo (quem, no caso de RT, comprovante e termo; qual OS)."""
        if self.destino == IGNORAR:
            return True
        if self.destino == DESTINO_TERMO:
            return bool(self.servidor_id)
        if self.destino == DESTINO_ORDEM_SERVICO:
            return bool(self.ordem_servico_id)
        if self.destino == DESTINO_JUSTIFICATIVA:
            return True
        if self.destino not in DESTINOS:
            return False
        return not self.individual or bool(self.servidor_prestacao_id)

    def rotacao_de(self, indice: int) -> int:
        """O /Rotate que a página `indice` recebe no anexo."""
        planejada = int(self.rotacoes.get(str(indice), self.rotacoes.get(indice, 0)) or 0)
        return (planejada + int(self.giro or 0)) % 360

    @property
    def rotacoes_finais(self) -> dict[int, int]:
        return {int(i): self.rotacao_de(int(i)) for i in self.paginas}

    @property
    def girado(self) -> bool:
        """Alguma página sai com /Rotate diferente do que tinha no processo."""
        return any(self.rotacao_de(i) != int(self.rotacoes_originais.get(str(i), 0)) for i in self.paginas)

    def para_json(self) -> dict:
        return asdict(self)

    @classmethod
    def de_json(cls, dados: dict) -> ItemPlano:
        conhecidos = {nome for nome in cls.__dataclass_fields__}
        return cls(**{chave: valor for chave, valor in (dados or {}).items() if chave in conhecidos})


@dataclass
class Plano:
    """O processo lido e o que fazer com ele.

    `pronto` diz se dá para aplicar sem conferência: identificação segura e todo
    documento com destino certo.
    """

    protocolo: str = ""
    volume: int | None = None
    eh_eprotocolo: bool = False
    total_paginas: int = 0
    prestacao_id: int | None = None
    oficio_id: int | None = None
    oficio_rotulo: str = ""
    camada: str = ""
    identificacao_segura: bool = False
    evidencias: list[str] = field(default_factory=list)
    candidatos: list[Candidato] = field(default_factory=list)
    protocolo_para_gravar: str = ""
    convalidacao_no_texto: bool | None = None
    itens: list[ItemPlano] = field(default_factory=list)
    avisos: list[str] = field(default_factory=list)
    #: O termo do cadastro de onde o processo veio (⋮ da lista de Termos) ou que os
    #: termos do PDF apontaram; o avulso (sem ofício) é o único caso sem prestação.
    termo_id: int | None = None
    termo_rotulo: str = ""
    origem: str = "prestacoes"

    @property
    def tem_registro(self) -> bool:
        """Sabe-se de quem é o processo: da prestação (ofício) ou, ao menos, de um termo."""
        return bool(self.prestacao_id or self.termo_id)

    @property
    def pronto(self) -> bool:
        return bool(
            self.identificacao_segura
            and self.tem_registro
            and self.itens
            and all(item.decidido and not item.conferir for item in self.itens)
            and any(item.grava for item in self.itens)
            and not self.pendencias
        )

    @property
    def pendencias(self) -> list[str]:
        """O que falta para aplicar, em frases para a tela."""
        saida = []
        if not self.tem_registro:
            saida.append("Escolha a prestação de contas deste processo.")
        for item in self.itens:
            if item.destino == "":
                saida.append(f"Documento {item.ordem}: diga o que ele é (ou marque para não entrar).")
            elif item.individual and not item.servidor_prestacao_id:
                saida.append(f"Documento {item.ordem}: escolha o servidor.")
            elif item.destino == DESTINO_TERMO and not item.servidor_id:
                saida.append(f"Documento {item.ordem}: escolha de quem é o termo.")
            elif item.destino == DESTINO_ORDEM_SERVICO and not item.ordem_servico_id:
                saida.append(f"Documento {item.ordem}: escolha a ordem de serviço.")
            elif self.tem_registro and not self.prestacao_id and (item.entra or item.destino == DESTINO_JUSTIFICATIVA):
                saida.append(
                    f"Documento {item.ordem}: o termo #{self.termo_id} não tem ofício, então não há prestação "
                    "nem ofício para este documento (marque para não entrar)."
                )
        if self.itens and not any(item.grava for item in self.itens):
            saida.append("Nenhum documento do processo entra na prestação nem nos documentos do ofício.")
        return saida

    def item(self, ordem: int) -> ItemPlano | None:
        return next((item for item in self.itens if item.ordem == int(ordem)), None)

    def para_json(self) -> dict:
        dados = asdict(self)
        dados["versao"] = 1
        return dados

    @classmethod
    def de_json(cls, dados: dict) -> Plano:
        dados = dict(dados or {})
        dados.pop("versao", None)
        conhecidos = {nome for nome in cls.__dataclass_fields__}
        plano = cls(**{chave: valor for chave, valor in dados.items() if chave in conhecidos and chave not in {"itens", "candidatos"}})
        plano.itens = [ItemPlano.de_json(item) for item in dados.get("itens") or []]
        plano.candidatos = [
            Candidato(**{c: v for c, v in candidato.items() if c in Candidato.__dataclass_fields__})
            for candidato in dados.get("candidatos") or []
        ]
        return plano
