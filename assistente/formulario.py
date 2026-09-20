"""Preenchimento conversado: descobrir o que falta e perguntar, um de cada vez.

O assistente não "gera documentos". Ele preenche um formulário conversando e,
no fim, chama os mesmos ``services`` que as telas chamam. A diferença importa:
se o modelo de linguagem entender mal, o estrago é um **campo** errado, que
aparece no resumo antes de qualquer gravação — não um documento inventado.

A lista do que falta sai **dos campos declarados aqui**, não do prompt. Quando
um campo novo virar obrigatório, o assistente passa a perguntar por ele
sozinho, sem ninguém reescrever instrução nenhuma.

Ordem das perguntas: primeiro o que identifica (destino, data), depois quem vai,
por último o acessório. Quem responde no WhatsApp desiste de um interrogatório
longo, então o obrigatório vem antes e o opcional só é perguntado se sobrar
contexto.
"""

from __future__ import annotations

from dataclasses import dataclass

from .resolucao import AMBIGUO, NENHUM, RESOLVEDORES, descrever


@dataclass(frozen=True)
class Campo:
    nome: str
    rotulo: str
    tipo: str  # municipio | servidor | motorista | viatura | data | texto | lista_servidores
    pergunta: str
    obrigatorio: bool = True


CAMPOS_VIAGEM: tuple[Campo, ...] = (
    Campo("destino", "Destino", "municipio", "Para qual município é a viagem?"),
    Campo("data_inicio", "Data de início", "data", "Em que dia começa? (dd/mm/aaaa)"),
    Campo("origem", "Município sede", "municipio", "De qual município a equipe sai?"),
    Campo("servidores", "Servidores", "lista_servidores", "Quem vai? (nomes separados por vírgula)"),
    Campo("motivo", "Motivo", "texto", "Qual o motivo da viagem?"),
    Campo("data_fim", "Data de término", "data", "Em que dia termina?", obrigatorio=False),
    Campo("motorista", "Motorista", "motorista", "Quem dirige?", obrigatorio=False),
    Campo("viatura", "Viatura", "viatura", "Qual viatura? (placa)", obrigatorio=False),
)

CAMPOS_POR_NOME = {c.nome: c for c in CAMPOS_VIAGEM}


@dataclass
class Pendencia:
    """Uma pergunta que precisa de resposta antes de seguir."""

    campo: str
    texto: str
    opcoes: list[str] = None

    def __post_init__(self):
        if self.opcoes is None:
            self.opcoes = []


def aplicar(rascunho: dict, campo_nome: str, valor) -> Pendencia | None:
    """Tenta gravar um valor no rascunho; devolve a pergunta se não der.

    O rascunho guarda **ids**, nunca o texto que a pessoa falou: é o que
    garante que o resumo de confirmação mostre a pessoa de verdade, e não a
    aproximação que o assistente fez dela.
    """
    campo = CAMPOS_POR_NOME[campo_nome]

    if campo.tipo in {"data", "texto"}:
        rascunho[campo_nome] = valor.isoformat() if hasattr(valor, "isoformat") else str(valor).strip()
        return None

    if campo.tipo == "lista_servidores":
        termos = [t.strip() for t in str(valor).replace(" e ", ",").split(",") if t.strip()]
        escolhidos = list(rascunho.get(campo_nome) or [])
        for termo in termos:
            resolucao = RESOLVEDORES["servidor"](termo)
            if resolucao.status == NENHUM:
                return Pendencia(campo_nome, f"Não achei nenhum servidor com “{termo}”. Qual o nome completo?")
            if resolucao.status == AMBIGUO:
                return Pendencia(
                    campo_nome,
                    f"“{termo}” casa com mais de um servidor. Qual deles?",
                    [descrever(c) for c in resolucao.candidatos],
                )
            if resolucao.escolhido.pk not in escolhidos:
                escolhidos.append(resolucao.escolhido.pk)
        rascunho[campo_nome] = escolhidos
        return None

    resolucao = RESOLVEDORES[campo.tipo](str(valor))
    if resolucao.status == NENHUM:
        return Pendencia(campo_nome, f"Não encontrei “{valor}” no cadastro de {campo.rotulo.lower()}. Como se escreve?")
    if resolucao.status == AMBIGUO:
        return Pendencia(
            campo_nome,
            f"“{valor}” casa com mais de um registro. Qual deles?",
            [descrever(c) for c in resolucao.candidatos],
        )
    rascunho[campo_nome] = resolucao.escolhido.pk
    return None


def proxima_pergunta(rascunho: dict) -> Pendencia | None:
    """O primeiro campo obrigatório ainda vazio."""
    for campo in CAMPOS_VIAGEM:
        if not campo.obrigatorio:
            continue
        if not rascunho.get(campo.nome):
            return Pendencia(campo.nome, campo.pergunta)
    return None


def completo(rascunho: dict) -> bool:
    return proxima_pergunta(rascunho) is None


def _descrever_valor(campo: Campo, valor):
    from cadastros.models import Municipio
    from viagens_cadastros.models import Servidor, Viatura

    if campo.tipo == "municipio":
        municipio = Municipio.objects.select_related("estado").filter(pk=valor).first()
        return descrever(municipio) if municipio else "—"
    if campo.tipo in {"servidor", "motorista"}:
        servidor = Servidor.objects.filter(pk=valor).first()
        return servidor.nome if servidor else "—"
    if campo.tipo == "viatura":
        viatura = Viatura.objects.filter(pk=valor).first()
        return descrever(viatura) if viatura else "—"
    if campo.tipo == "lista_servidores":
        nomes = list(Servidor.objects.filter(pk__in=valor).values_list("nome", flat=True))
        return ", ".join(nomes) if nomes else "—"
    if campo.tipo == "data":
        import datetime as dt

        try:
            return dt.date.fromisoformat(valor).strftime("%d/%m/%Y")
        except (TypeError, ValueError):
            return str(valor)
    return str(valor)


def resumo(rascunho: dict) -> list[str]:
    """As linhas que a pessoa lê antes de confirmar.

    Mostra o valor **resolvido** — nome completo do servidor, município com UF,
    data por extenso. É aqui que se percebe que "Pereira" virou "Ferreira".
    """
    linhas = []
    for campo in CAMPOS_VIAGEM:
        valor = rascunho.get(campo.nome)
        if not valor:
            continue
        linhas.append(f"{campo.rotulo}: {_descrever_valor(campo, valor)}")
    return linhas
