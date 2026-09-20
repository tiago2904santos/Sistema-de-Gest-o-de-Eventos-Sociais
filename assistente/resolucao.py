"""Resolver o que a pessoa disse contra o que existe no banco.

"vai o Silva" não é um dado: é um apelido. Antes de qualquer coisa ser gravada,
ele precisa virar um ``Servidor`` com id. Esta é a parte do assistente que
**não** pode ser feita por um modelo de linguagem, e por isso é código comum,
determinístico e testável.

A regra que sustenta o resto: **na dúvida, perguntar.** Se "Silva" casa com
três servidores, a resolução devolve ``AMBIGUO`` com os três candidatos e o
orquestrador pergunta qual. Nunca escolhe o primeiro, nunca escolhe o "mais
provável". Escolher errado aqui produz documento oficial com a pessoa errada —
o tipo de erro que só aparece depois de assinado.

A busca desce em três degraus, e para no primeiro que encontrar alguém: igual,
começa com, contém. O degrau existe para que "SILVA" não fique ambíguo quando
há um servidor chamado exatamente SILVA e outros cinco com Silva no sobrenome.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from core.normalizers import normalize_spaces, remove_accents

UNICO = "UNICO"
AMBIGUO = "AMBIGUO"
NENHUM = "NENHUM"

# Acima disso a lista de candidatos vira ruído: a pergunta passa a ser "seja
# mais específico" em vez de um menu.
MAXIMO_CANDIDATOS = 6


def chave(valor: str) -> str:
    """Forma comparável: sem acento, sem espaço duplicado, em maiúsculas."""
    return remove_accents(normalize_spaces(valor or "")).upper()


@dataclass
class Resolucao:
    termo: str
    tipo: str
    escolhido: object | None = None
    candidatos: list = field(default_factory=list)
    excedeu: bool = False

    @property
    def status(self) -> str:
        if self.escolhido is not None:
            return UNICO
        return AMBIGUO if self.candidatos else NENHUM

    @property
    def resolvido(self) -> bool:
        return self.status == UNICO


def _resolver(termo: str, tipo: str, registros, rotulo):
    """Três degraus de aproximação sobre uma lista já carregada.

    Recebe a lista pronta (e não um queryset) porque os cadastros envolvidos
    são pequenos — servidores, viaturas e os 399 municípios do PR — e comparar
    sem acento no Python evita depender de `unaccent` no PostgreSQL, que não
    está instalado e não existe no SQLite da suíte.
    """
    alvo = chave(termo)
    if not alvo:
        return Resolucao(termo=termo, tipo=tipo)

    degraus = (
        lambda k: k == alvo,
        lambda k: k.startswith(alvo),
        lambda k: alvo in k,
    )
    for casa in degraus:
        achados = [r for r in registros if casa(chave(rotulo(r)))]
        if len(achados) == 1:
            return Resolucao(termo=termo, tipo=tipo, escolhido=achados[0])
        if achados:
            return Resolucao(
                termo=termo,
                tipo=tipo,
                candidatos=achados[:MAXIMO_CANDIDATOS],
                excedeu=len(achados) > MAXIMO_CANDIDATOS,
            )
    return Resolucao(termo=termo, tipo=tipo)


def resolver_municipio(termo: str, *, uf: str = "") -> Resolucao:
    from cadastros.models import Municipio

    registros = Municipio.objects.select_related("estado")
    if uf:
        registros = registros.filter(estado__sigla__iexact=uf)
    return _resolver(termo, "municipio", list(registros), lambda m: m.nome)


def resolver_servidor(termo: str, *, apenas_motoristas: bool = False) -> Resolucao:
    from viagens_cadastros.models import Servidor

    registros = Servidor.objects.select_related("cargo", "unidade")
    if apenas_motoristas:
        # Motorista não é cadastro à parte: é o servidor que figura como
        # motorista de alguma viatura (ver a docstring de `Servidor`).
        registros = registros.filter(viaturas_que_dirige__isnull=False).distinct()
    return _resolver(
        termo,
        "motorista" if apenas_motoristas else "servidor",
        list(registros),
        lambda s: s.nome,
    )


def resolver_viatura(termo: str) -> Resolucao:
    from viagens_cadastros.models import Viatura

    registros = list(Viatura.objects.select_related("unidade"))
    # A placa identifica sem ambiguidade; o modelo ("Duster") quase nunca.
    por_placa = _resolver(termo, "viatura", registros, lambda v: v.placa)
    if por_placa.status != NENHUM:
        return por_placa
    return _resolver(termo, "viatura", registros, lambda v: f"{v.modelo} {v.placa}")


def resolver_unidade(termo: str) -> Resolucao:
    from viagens_cadastros.models import Unidade

    return _resolver(termo, "unidade", list(Unidade.objects.all()), lambda u: u.nome)


RESOLVEDORES = {
    "municipio": resolver_municipio,
    "servidor": resolver_servidor,
    "motorista": lambda termo: resolver_servidor(termo, apenas_motoristas=True),
    "viatura": resolver_viatura,
    "unidade": resolver_unidade,
}


def descrever(registro) -> str:
    """Rótulo de um candidato na pergunta de desambiguação.

    Mostra o que distingue duas pessoas de nome parecido — cargo e unidade —
    porque sem isso o menu "1) SILVA 2) SILVA" não ajuda ninguém.
    """
    from cadastros.models import Municipio
    from viagens_cadastros.models import Servidor, Unidade, Viatura

    if isinstance(registro, Municipio):
        return f"{registro.nome}/{registro.estado.sigla}"
    if isinstance(registro, Servidor):
        detalhes = [d for d in (
            getattr(registro.cargo, "nome", ""),
            getattr(registro.unidade, "nome", ""),
        ) if d]
        return f"{registro.nome}" + (f" ({' — '.join(detalhes)})" if detalhes else "")
    if isinstance(registro, Viatura):
        return f"{registro.placa}" + (f" — {registro.modelo}" if registro.modelo else "")
    if isinstance(registro, Unidade):
        return registro.nome
    return str(registro)
