"""Camada de ferramentas: a única porta pela qual o assistente toca o sistema.

Uma ferramenta declara os parâmetros que aceita, quem pode chamá-la e se ela
grava alguma coisa. Por dentro, chama os ``selectors``/``services`` que as
telas já usam — não há caminho do interpretador de linguagem para o ORM. Ele
escolhe o **nome** de uma ferramenta e os **valores** dos parâmetros; o resto
é código comum, testável sem modelo nenhum.

Duas garantias moram aqui, e são o motivo de a camada existir:

**A permissão é a do usuário.** ``Ferramenta.pode`` recebe o usuário da conversa
e delega ao ``permissions.py`` do módulo correspondente. O assistente não tem
identidade nem acesso próprios: o que ele consegue fazer é exatamente o que
aquela pessoa já conseguia fazer sozinha, pelas telas.

**O que grava pede confirmação.** ``mutante=True`` faz o orquestrador parar,
montar o resumo do que vai acontecer e esperar um "confirmar" explícito. Não
existe gravação silenciosa, nem em lote.

Os parâmetros chegam como texto (de uma regex ou de um modelo de linguagem) e
são convertidos aqui, por tipo declarado. Valor que não converte vira
``ErroDeParametro`` — nunca um filtro silenciosamente vazio, que pareceria
"não encontrei nada" quando na verdade foi a pergunta que não foi entendida.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Callable
from dataclasses import dataclass, field


class ErroDeParametro(ValueError):
    """Parâmetro ausente, sobrando ou impossível de converter."""


class PermissaoNegada(PermissionError):
    """O usuário da conversa não pode usar esta ferramenta."""


@dataclass(frozen=True)
class Parametro:
    nome: str
    tipo: str  # texto | inteiro | data | booleano
    descricao: str
    obrigatorio: bool = False


def _converter(parametro: Parametro, valor):
    if valor is None or valor == "":
        return None
    if parametro.tipo == "texto":
        return str(valor).strip()
    if parametro.tipo == "inteiro":
        try:
            return int(str(valor).strip())
        except ValueError as exc:
            raise ErroDeParametro(
                f"'{parametro.nome}' precisa ser um número inteiro; veio {valor!r}."
            ) from exc
    if parametro.tipo == "booleano":
        return str(valor).strip().lower() in {"1", "true", "sim", "s", "on"}
    if parametro.tipo == "data":
        if isinstance(valor, dt.date):
            return valor
        texto = str(valor).strip()
        for formato in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y"):
            try:
                return dt.datetime.strptime(texto, formato).date()
            except ValueError:
                continue
        raise ErroDeParametro(
            f"'{parametro.nome}' precisa ser uma data (dd/mm/aaaa); veio {valor!r}."
        )
    raise ErroDeParametro(f"Tipo de parâmetro desconhecido: {parametro.tipo}.")


@dataclass
class Resultado:
    """O que uma ferramenta devolve: já pronto para virar texto de resposta.

    ``linhas`` é o corpo legível. ``dados`` é o mesmo conteúdo em estrutura,
    para quem precisa dele (a confirmação de uma ação, um teste, uma tela).
    """

    titulo: str = ""
    linhas: list[str] = field(default_factory=list)
    dados: dict = field(default_factory=dict)

    @property
    def vazio(self) -> bool:
        return not self.linhas and not self.dados

    def texto(self) -> str:
        partes = [self.titulo] if self.titulo else []
        partes.extend(self.linhas)
        return "\n".join(partes).strip()


@dataclass(frozen=True)
class Ferramenta:
    nome: str
    descricao: str
    funcao: Callable
    parametros: tuple[Parametro, ...] = ()
    mutante: bool = False
    permissao: Callable | None = None

    def pode(self, usuario) -> bool:
        if self.permissao is None:
            return bool(usuario and usuario.is_authenticated)
        return bool(self.permissao(usuario))

    def preparar(self, argumentos: dict) -> dict:
        """Converte e valida os argumentos, sem executar nada."""
        por_nome = {p.nome: p for p in self.parametros}
        sobrando = set(argumentos) - set(por_nome)
        if sobrando:
            raise ErroDeParametro(
                f"Parâmetro desconhecido para '{self.nome}': {', '.join(sorted(sobrando))}."
            )
        preparados = {}
        for parametro in self.parametros:
            valor = _converter(parametro, argumentos.get(parametro.nome))
            if valor is None and parametro.obrigatorio:
                raise ErroDeParametro(
                    f"'{parametro.nome}' é obrigatório para '{self.nome}'."
                )
            preparados[parametro.nome] = valor
        return preparados

    def executar(self, usuario, **argumentos) -> Resultado:
        if not self.pode(usuario):
            raise PermissaoNegada(
                f"Você não tem acesso a '{self.nome}' neste sistema."
            )
        return self.funcao(usuario, **self.preparar(argumentos))


REGISTRO: dict[str, Ferramenta] = {}


def registrar(
    nome: str,
    *,
    descricao: str,
    parametros: tuple[Parametro, ...] = (),
    mutante: bool = False,
    permissao: Callable | None = None,
):
    """Decorator que publica uma função como ferramenta do assistente."""

    def decorador(funcao):
        if nome in REGISTRO:
            raise RuntimeError(f"Ferramenta '{nome}' já registrada.")
        REGISTRO[nome] = Ferramenta(
            nome=nome,
            descricao=descricao,
            funcao=funcao,
            parametros=parametros,
            mutante=mutante,
            permissao=permissao,
        )
        return funcao

    return decorador


def obter(nome: str) -> Ferramenta:
    try:
        return REGISTRO[nome]
    except KeyError as exc:
        raise ErroDeParametro(f"Ferramenta desconhecida: '{nome}'.") from exc


def todas() -> list[Ferramenta]:
    """O catálogo inteiro, em ordem estável — o que o interpretador enxerga.

    Ele recebe tudo de propósito. Recortar aqui pela permissão faria o pedido
    de quem não tem acesso cair no "não entendi", que é enganoso: a pessoa
    concluiria que o assistente está quebrado em vez de saber que a ação está
    fora do acesso dela. A recusa continua acontecendo — em
    ``Ferramenta.executar``, que é onde ela não pode ser contornada.
    """
    return [f for _, f in sorted(REGISTRO.items())]


def disponiveis(usuario) -> list[Ferramenta]:
    """As ferramentas que este usuário pode de fato usar — o que a tela lista."""
    return [f for f in todas() if f.pode(usuario)]
