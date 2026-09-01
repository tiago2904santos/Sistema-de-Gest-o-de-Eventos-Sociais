"""Fábricas das regras que o banco defende por conta própria.

Existem para que constraints que dizem a mesma coisa sejam escritas do mesmo
jeito. Cada uma à mão convida à divergência silenciosa: um ``gt`` onde as
outras usam ``gte``, um sinal trocado — e o banco deixa passar período
invertido ou dinheiro negativo vindo de um caminho que não é o formulário
(importador, comando de gestão, migração de dados, correção manual).

**Nulo passa, e a condição não precisa dizer isso.** Um ``CHECK`` cujo
resultado é ``NULL`` é aceito em SQL, e o caminho Python (``full_clean``) chega
ao mesmo resultado. Escrever ``Q(campo__isnull=True) | ...`` seria código
inerte com aparência de carga útil.

**Por que ``gte`` e não ``gt`` nos períodos.** Evento de um dia tem fim igual
ao início e viagem de ida e volta no mesmo horário é degenerada, não
impossível. O defeito que se quer barrar é a **inversão**.
"""

from django.db import models
from django.db.models import F, Q


def periodo_ordenado(inicio, fim, *, name, mensagem=None):
    """``fim`` nunca antes de ``inicio``.

    ``mensagem`` é o texto mostrado quando a regra é violada pelo caminho
    Python (formulário, comando). Sem ele o Django monta uma frase com o nome
    técnico da constraint, que serve para o log e não para a tela.
    """
    extra = {"violation_error_message": mensagem} if mensagem else {}
    return models.CheckConstraint(
        condition=Q(**{f"{fim}__gte": F(inicio)}), name=name, **extra
    )


def nao_negativo(campo, *, name):
    """Zero vale, negativo não. Para valor calculado que pode dar zero."""
    return models.CheckConstraint(condition=Q(**{f"{campo}__gte": 0}), name=name)


def positivo(campo, *, name):
    """Nem zero nem negativo. Para valor que, existindo, tem de valer algo."""
    return models.CheckConstraint(condition=Q(**{f"{campo}__gt": 0}), name=name)
