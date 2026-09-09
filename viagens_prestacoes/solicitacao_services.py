"""Persistência do número de solicitação, da data de liberação e do prazo limite.

`BE-14` extraiu as duas rotas que gravam esses três campos para uma transação.
O `NOVO-103` fecha a divergência que restou entre elas:

- toda data é validada antes da primeira escrita;
- erro de validação rejeita a requisição inteira;
- qualquer alteração efetiva marca o servidor em preenchimento;
- os três campos do autosave são persistidos juntos.
"""

from __future__ import annotations

import datetime
import re
from dataclasses import dataclass

from django.db import transaction

from core.normalizers import normalize_spaces

from .services import marcar_servidor_em_preenchimento


def _agendar_recarimbo(prestacoes) -> None:
    """Redesenha o ofício assinado depois do commit, uma vez por prestação.

    O número carimbado no anexo é lido de `numero_solicitacao` na hora de desenhar, e
    não copiado — então mudar o número aqui deixa o anexo desatualizado até que alguém
    redesenhe. Quem redesenha é isto.

    Depois do commit, e não dentro: carimbar abre arquivo no storage, que não desfaz com
    `ROLLBACK`. É o mesmo motivo pelo qual `anexo_services` adia a remoção de arquivo.
    """
    if not prestacoes:
        return

    from .carimbo_services import recarimbar_prestacao

    def rodar():
        for prestacao in prestacoes:
            recarimbar_prestacao(prestacao)

    transaction.on_commit(rodar)

_CAMPOS_DO_LOTE = {
    "numero_solicitacao": re.compile(r"^ps-(\d+)-numero_solicitacao$"),
    "data_liberacao_diarias": re.compile(r"^ps-(\d+)-data_liberacao_diarias$"),
    "prazo_limite_saque": re.compile(r"^ps-(\d+)-prazo_limite_saque$"),
}

#: Mensagem por campo de data, como o autosave sempre respondeu.
MENSAGEM_DATA_INVALIDA = {
    "data_liberacao_diarias": "Data de liberação inválida.",
    "prazo_limite_saque": "Data de prazo limite inválida.",
}


@dataclass(frozen=True)
class ResultadoSolicitacao:
    """O que a gravação fez. A view traduz isto em JSON ou em `messages`."""

    erro: str = ""
    campos_gravados: tuple[str, ...] = ()
    servidores_gravados: int = 0

    @property
    def ok(self) -> bool:
        return not self.erro


def _parse_iso_date(texto):
    """Converte ``'AAAA-MM-DD'`` em ``date``; ``''`` vira ``None``."""
    if not texto:
        return None
    return datetime.date.fromisoformat(texto)


def _datas_validadas(campos) -> tuple[dict[str, datetime.date | None], str]:
    """Valida todas as datas recebidas sem alterar o objeto persistente."""
    validadas = {}
    for campo in ("data_liberacao_diarias", "prazo_limite_saque"):
        bruto = campos.get(campo)
        if bruto is None:
            continue
        try:
            validadas[campo] = _parse_iso_date(bruto)
        except ValueError:
            return {}, MENSAGEM_DATA_INVALIDA[campo]
    return validadas, ""


def valores_do_lote(post) -> dict[int, dict[str, str]]:
    """Lê `ps-<pk>-<campo>` do POST e agrupa por servidor.

    Recebe o `QueryDict`, não o `request` (`docs/PADRAO_SERVICES.md:20`). Só leitura:
    nada aqui grava, e é isso que permite a view decidir se há o que fazer antes de
    abrir transação.
    """
    por_servidor: dict[int, dict[str, str]] = {}
    for nome, valor in post.items():
        for campo, padrao in _CAMPOS_DO_LOTE.items():
            match = padrao.match(str(nome or ""))
            if not match:
                continue
            texto = normalize_spaces(valor or "") if campo == "numero_solicitacao" else (valor or "").strip()
            por_servidor.setdefault(int(match.group(1)), {})[campo] = texto
            break
    return por_servidor


@transaction.atomic
def salvar_solicitacoes_em_lote(servidores, valores) -> ResultadoSolicitacao:
    """Grava os três campos de N servidores, um `UPDATE` por servidor.

    Atômica porque grava **em laço**: sem ela, uma falha no meio deixa parte da lista com
    o valor novo e parte com o antigo, e o operador volta para uma tela que não diz qual
    é qual.

    A preparação inteira ocorre antes da primeira escrita. Assim uma data inválida em
    qualquer linha rejeita o lote inteiro, como o autosave rejeita sua requisição.
    """
    preparados = []
    for servidor_prestacao in servidores:
        campos = valores.get(servidor_prestacao.pk)
        if not campos:
            continue
        datas, erro = _datas_validadas(campos)
        if erro:
            return ResultadoSolicitacao(erro=erro)
        preparados.append((servidor_prestacao, campos, datas))

    gravados = 0
    # Um recarimbo por prestação, não por servidor: o lote costuma ser a equipe inteira
    # do mesmo ofício, e redesenhar N vezes o mesmo PDF é trabalho jogado fora.
    recarimbo: dict[int, object] = {}
    for servidor_prestacao, campos, datas in preparados:
        update_fields = []
        if "numero_solicitacao" in campos:
            novo = campos["numero_solicitacao"]
            if servidor_prestacao.numero_solicitacao != novo:
                servidor_prestacao.numero_solicitacao = novo
                update_fields.append("numero_solicitacao")
        for campo, novo_valor in datas.items():
            if getattr(servidor_prestacao, campo) != novo_valor:
                setattr(servidor_prestacao, campo, novo_valor)
                update_fields.append(campo)
        if update_fields:
            servidor_prestacao.save(update_fields=[*update_fields, "atualizado_em"])
            marcar_servidor_em_preenchimento(servidor_prestacao)
            gravados += 1
            if "numero_solicitacao" in update_fields:
                recarimbo[servidor_prestacao.prestacao_id] = servidor_prestacao.prestacao
    _agendar_recarimbo(list(recarimbo.values()))
    return ResultadoSolicitacao(servidores_gravados=gravados)


@transaction.atomic
def salvar_solicitacao_do_autosave(
    servidor_prestacao, *, numero=None, datas=None
) -> ResultadoSolicitacao:
    """Valida e grava em conjunto o que veio sujo do autosave.

    `numero` e cada entrada de `datas` valem `None` quando **não vieram no payload** — o
    autosave manda só o que mudou, e ausência não é ordem de apagar.

    Uma data inválida é detectada antes da primeira escrita; portanto o retorno de erro
    nunca convive com número ou outra data parcialmente persistidos.
    """
    datas_validadas, erro = _datas_validadas(datas or {})
    if erro:
        return ResultadoSolicitacao(erro=erro)

    gravados: list[str] = []
    if numero is not None and servidor_prestacao.numero_solicitacao != numero:
        servidor_prestacao.numero_solicitacao = numero
        gravados.append("numero_solicitacao")

    for campo, novo_valor in datas_validadas.items():
        if getattr(servidor_prestacao, campo) != novo_valor:
            setattr(servidor_prestacao, campo, novo_valor)
            gravados.append(campo)

    if gravados:
        servidor_prestacao.save(update_fields=[*gravados, "atualizado_em"])
        marcar_servidor_em_preenchimento(servidor_prestacao)
        if "numero_solicitacao" in gravados:
            _agendar_recarimbo([servidor_prestacao.prestacao])

    return ResultadoSolicitacao(campos_gravados=tuple(gravados))
