"""O laço da conversa: interpretar, perguntar o que falta, confirmar, executar.

A ordem importa e é sempre a mesma:

1. Se há uma ação esperando **confirmação**, a mensagem só pode ser confirmar
   ou cancelar. Não se reinterpreta nada por cima de um resumo já mostrado —
   isso é o que evita "eu disse outra coisa e ele fez assim mesmo".
2. Se há uma ação **coletando**, a mensagem é a resposta da última pergunta.
3. Só então a mensagem é um pedido novo, e vai ao interpretador.

Nenhuma ferramenta que grava é executada direto. Quando o preenchimento fecha,
o assistente monta o resumo com os valores **resolvidos** e para. Executa na
mensagem seguinte, se ela for um "confirmar" — e registra quem confirmou.

Tudo que acontece aqui vale para o painel e para o WhatsApp sem alteração: o
canal entra como texto e sai como texto, e é por isso que o WhatsApp acaba
sendo a menor parte do trabalho.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from django.utils import timezone

from core.normalizers import normalize_spaces, remove_accents

from . import formulario
from .ferramentas import ErroDeParametro, PermissaoNegada, disponiveis, obter, todas
from .llm import obter_interpretador
from .models import AcaoPendente, Conversa, Mensagem

CONFIRMACOES = {"confirmar", "confirma", "confirmo", "sim", "ok", "pode", "isso", "s", "beleza"}
CANCELAMENTOS = {"cancelar", "cancela", "nao", "n", "para", "esquece", "deixa"}

AJUDA = (
    "Posso consultar e preparar coisas do módulo Viagens. Por exemplo:\n"
    "• “quem vai para Maringá em setembro?”\n"
    "• “quais viagens desta semana?”\n"
    "• “o que está pendente?”\n"
    "• “faça os documentos para um evento em Maringá dia 18, vai o Silva com o motorista Pereira”"
)


def _chave(texto: str) -> str:
    return remove_accents(normalize_spaces(texto or "")).lower().strip(" .!?")


@dataclass
class Resposta:
    texto: str
    conversa: Conversa = None
    ferramenta: str = ""
    opcoes: list[str] = field(default_factory=list)
    aguardando_confirmacao: bool = False
    acao: AcaoPendente = None


def _registrar(conversa, autor, texto, ferramenta=""):
    return Mensagem.objects.create(
        conversa=conversa, autor=autor, texto=texto, ferramenta=ferramenta
    )


def _responder(conversa, texto, *, ferramenta="", **extra) -> Resposta:
    _registrar(conversa, Mensagem.Autor.ASSISTENTE, texto, ferramenta)
    return Resposta(texto=texto, conversa=conversa, ferramenta=ferramenta, **extra)


def _perguntar(conversa, acao, pendencia) -> Resposta:
    acao.aguardando_campo = pendencia.campo
    acao.status = AcaoPendente.Status.COLETANDO
    acao.save(update_fields=["aguardando_campo", "status", "rascunho"])
    corpo = pendencia.texto
    if pendencia.opcoes:
        corpo += "\n" + "\n".join(f"{i}) {o}" for i, o in enumerate(pendencia.opcoes, 1))
    return _responder(conversa, corpo, ferramenta=acao.ferramenta, opcoes=pendencia.opcoes)


def _pedir_confirmacao(conversa, acao) -> Resposta:
    acao.status = AcaoPendente.Status.AGUARDANDO
    acao.aguardando_campo = ""
    acao.save(update_fields=["status", "aguardando_campo", "rascunho"])
    linhas = formulario.resumo(acao.rascunho)
    corpo = "Vou criar com estes dados:\n" + "\n".join(f"• {l}" for l in linhas)
    corpo += "\n\nConfirma? (responda “confirmar” ou “cancelar”)"
    return _responder(
        conversa, corpo, ferramenta=acao.ferramenta, aguardando_confirmacao=True, acao=acao
    )


def _drenar(acao):
    """Aplica o que o pedido original trouxe e ainda não foi gravado.

    Roda depois de cada resposta, e não só no começo: uma ambiguidade no meio
    do preenchimento ("qual Silva?") interrompia a varredura e o que vinha
    depois — motorista, viatura — sumia sem aviso. Quem falou "com o motorista
    Pereira" leria o resumo sem motorista e poderia confirmar assim mesmo.
    """
    restantes = dict(acao.extraidos or {})
    for campo in formulario.CAMPOS_VIAGEM:
        valor = restantes.pop(campo.nome, None)
        if not valor or acao.rascunho.get(campo.nome):
            continue
        pendencia = formulario.aplicar(acao.rascunho, campo.nome, valor)
        if pendencia:
            # O valor já virou pergunta; a resposta da pessoa toma o lugar dele.
            acao.extraidos = restantes
            acao.save(update_fields=["rascunho", "extraidos"])
            return pendencia
    acao.extraidos = restantes
    acao.save(update_fields=["rascunho", "extraidos"])
    return None


def _avancar(conversa, acao) -> Resposta:
    """Próxima pergunta obrigatória ou, se o formulário fechou, o resumo."""
    pendencia = formulario.proxima_pergunta(acao.rascunho)
    if pendencia:
        return _perguntar(conversa, acao, pendencia)
    return _pedir_confirmacao(conversa, acao)


def _executar_confirmada(usuario, conversa, acao) -> Resposta:
    from auditoria.models import LogAuditoria

    ferramenta = obter(acao.ferramenta)
    argumentos = dict(acao.rascunho)
    # O rascunho guarda a equipe como lista de ids; a ferramenta recebe texto,
    # porque é o mesmo formato que viria de um interpretador remoto.
    if isinstance(argumentos.get("servidores"), list):
        argumentos["servidores"] = ",".join(str(i) for i in argumentos["servidores"])

    try:
        resultado = ferramenta.executar(usuario, **argumentos)
    except PermissaoNegada as exc:
        acao.status = AcaoPendente.Status.CANCELADA
        acao.resolvido_em = timezone.now()
        acao.save(update_fields=["status", "resolvido_em"])
        return _responder(conversa, str(exc), ferramenta=acao.ferramenta)

    acao.status = AcaoPendente.Status.CONFIRMADA
    acao.resultado = resultado.dados
    acao.resolvido_em = timezone.now()
    acao.resolvido_por = usuario
    acao.save(update_fields=["status", "resultado", "resolvido_em", "resolvido_por"])

    LogAuditoria.objects.create(
        usuario=usuario,
        acao=f"assistente:{acao.ferramenta}",
        descricao=f"Confirmado pelo canal {conversa.get_canal_display()}. Resultado: {resultado.dados}",
    )
    return _responder(conversa, resultado.texto(), ferramenta=acao.ferramenta)


def _tratar_confirmacao(usuario, conversa, acao, texto) -> Resposta:
    alvo = _chave(texto)
    if alvo in CONFIRMACOES:
        return _executar_confirmada(usuario, conversa, acao)
    if alvo in CANCELAMENTOS:
        acao.status = AcaoPendente.Status.CANCELADA
        acao.resolvido_em = timezone.now()
        acao.resolvido_por = usuario
        acao.save(update_fields=["status", "resolvido_em", "resolvido_por"])
        return _responder(conversa, "Cancelado. Nada foi gravado.", ferramenta=acao.ferramenta)
    return _responder(
        conversa,
        "Ainda não gravei nada. Responda “confirmar” para criar ou “cancelar” para descartar.",
        ferramenta=acao.ferramenta,
        aguardando_confirmacao=True,
        acao=acao,
    )


def _tratar_coleta(conversa, acao, texto) -> Resposta:
    campo = acao.aguardando_campo
    alvo = _chave(texto)
    if alvo in CANCELAMENTOS:
        acao.status = AcaoPendente.Status.CANCELADA
        acao.resolvido_em = timezone.now()
        acao.save(update_fields=["status", "resolvido_em"])
        return _responder(conversa, "Cancelado. Nada foi gravado.", ferramenta=acao.ferramenta)

    valor = texto.strip()
    # Resposta por número escolhe entre as opções que a pergunta ofereceu.
    escolha = re.fullmatch(r"(\d+)\)?", valor)
    if escolha:
        ultima = acao.conversa.mensagens.filter(
            autor=Mensagem.Autor.ASSISTENTE
        ).last()
        linhas = (ultima.texto if ultima else "").splitlines()
        indice = int(escolha.group(1))
        rotulos = [l for l in linhas if re.match(rf"^{indice}\)\s", l)]
        if rotulos:
            # O rótulo traz detalhes entre parênteses; o nome é o que vem antes.
            valor = re.sub(r"^\d+\)\s*", "", rotulos[0]).split(" (")[0].strip()

    if campo in {"data_inicio", "data_fim"}:
        from . import periodos

        inicio, fim = periodos.interpretar(valor)
        if not inicio:
            return _responder(
                conversa,
                "Não entendi a data. Escreva no formato dd/mm/aaaa.",
                ferramenta=acao.ferramenta,
            )
        valor = (fim if campo == "data_fim" and fim else inicio).isoformat()

    pendencia = formulario.aplicar(acao.rascunho, campo, valor)
    acao.save(update_fields=["rascunho"])
    if pendencia:
        return _perguntar(conversa, acao, pendencia)
    pendencia = _drenar(acao)
    if pendencia:
        return _perguntar(conversa, acao, pendencia)
    return _avancar(conversa, acao)


def _iniciar_preparo(conversa, intencao) -> Resposta:
    acao = AcaoPendente.objects.create(
        conversa=conversa, ferramenta=intencao.ferramenta, extraidos=dict(intencao.campos)
    )
    pendencia = _drenar(acao)
    if pendencia:
        return _perguntar(conversa, acao, pendencia)
    return _avancar(conversa, acao)


def responder(usuario, texto, *, conversa=None, canal=Conversa.Canal.PAINEL, interpretador=None) -> Resposta:
    """Ponto único de entrada: uma mensagem entra, uma resposta sai."""
    conversa = conversa or Conversa.objects.create(usuario=usuario, canal=canal)
    _registrar(conversa, Mensagem.Autor.PESSOA, texto)

    pendente = conversa.pendente
    if pendente and pendente.status == AcaoPendente.Status.AGUARDANDO:
        return _tratar_confirmacao(usuario, conversa, pendente, texto)
    if pendente and pendente.aguardando_campo:
        return _tratar_coleta(conversa, pendente, texto)

    catalogo = disponiveis(usuario)
    if not catalogo:
        return _responder(
            conversa,
            "Você não tem acesso a nenhum módulo que eu saiba consultar. "
            "Procure o administrador do sistema.",
        )

    interpretador = interpretador or obter_interpretador()
    intencao = interpretador.interpretar(texto, ferramentas=todas(), usuario=usuario)
    if not intencao.entendida:
        return _responder(conversa, f"{intencao.explicacao}\n\n{AJUDA}")

    ferramenta = obter(intencao.ferramenta)
    if not ferramenta.pode(usuario):
        return _responder(
            conversa,
            "Isso está fora do seu acesso — eu uso exatamente as suas permissões.",
            ferramenta=ferramenta.nome,
        )

    if ferramenta.mutante:
        return _iniciar_preparo(conversa, intencao)

    try:
        resultado = ferramenta.executar(usuario, **intencao.argumentos)
    except (ErroDeParametro, PermissaoNegada) as exc:
        return _responder(conversa, str(exc), ferramenta=ferramenta.nome)
    return _responder(conversa, resultado.texto() or "Sem resultados.", ferramenta=ferramenta.nome)
