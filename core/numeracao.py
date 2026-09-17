"""Reserva de número de documento oficial, em um lugar só.

Portado do Gerenciador de Viagens na Fase 4. Aqui mora a **mecânica** —
serializar o escopo e repetir a escolha quando outro processo venceu a corrida.
A **política** (reuso de lacuna, piso, contador) fica em cada documento, porque
é diferente de propósito: o ofício e a ordem de serviço reusam lacunas, o plano
de trabalho tem contador na configuração.

O escopo é **global por ano**: o sistema de origem numerava por área de trabalho
e aqui não há área, então a unicidade é `(ano, numero)`, que é a versão mais
forte.

O que está aqui, e por quê:

**Serializar o escopo, não a linha.** Bloquear as linhas existentes não protege
o próximo número, porque ele ainda não existe. No PostgreSQL o advisory lock
transacional cobre exatamente esse intervalo lógico, "a numeração do ano Y", sem
exigir uma tabela de contadores. Fora do PostgreSQL cai no `select_for_update`,
que é o que sustenta o ambiente de desenvolvimento e a metade SQLite da suíte.

**Repetir quando perder a corrida.** Mesmo com o lock, um processo antigo (de
antes do deploy, ou de outro nó sem o lock) pode ter gravado o número escolhido.
A `UniqueConstraint` pega, e a tentativa seguinte já enxerga o número que venceu.

## A colisão é detectada perguntando ao banco, não lendo a mensagem dele

A implementação original fazia `if "<nome_da_constraint>" not in str(exc): raise`.
**Isso só funciona no PostgreSQL.** As mensagens dos dois bancos:

- PostgreSQL, medido nesta instalação: `duplicar valor da chave viola a restrição
  de unicidade "viagens_oficio_ano_numero_unique"` — traduzida, porque o servidor
  responde no idioma configurado. Ler texto aqui é ainda mais frágil que na
  origem, onde a mensagem saía em inglês.
- SQLite: `UNIQUE constraint failed: viagens_oficios_oficio.ano, viagens_oficios_oficio.numero`

A do SQLite **não contém o nome da constraint**, então o `not in` era sempre
verdadeiro e o retry re-levantava na primeira colisão: em produção o laço
funcionava, em metade da suíte era código morto.

Aqui a identificação tem duas fontes, nesta ordem:

1. **O metadado estruturado da exceção**, quando o driver oferece. No PostgreSQL
   o psycopg expõe `exc.__cause__.diag.constraint_name` já com o nome exato
   (`sqlstate` 23505). É comparação de igualdade, não substring, e não depende de
   o texto da mensagem manter o formato entre versões.
2. **A ocupação atual do número**, quando não há metadado (SQLite). Se aquele
   número está tomado agora, foi colisão e vale repetir.

**Por que o metadado vem primeiro.** A ocupação é prova *indireta*: se a linha
que causou a colisão for apagada entre o `INSERT` que falhou e a consulta
seguinte — e a rota de exclusão de ofício não toma este lock, com `READ
COMMITTED` a consulta enxerga a exclusão —, a resposta vira "não está ocupado" e
um `IntegrityError` que merecia nova tentativa sobe cru. A janela é estreita, mas
existe, e no PostgreSQL não é preciso conviver com ela. No SQLite o resíduo
permanece; lá não há metadado, e o ambiente não é produção.
"""
from __future__ import annotations

from collections.abc import Callable

from django.db import IntegrityError
from django.db import connection
from django.db import transaction

#: Namespaces do advisory lock, um por documento. Precisam ser distintos: iguais, a
#: numeração de dois documentos passaria a se serializar mutuamente sem necessidade.
#: Os valores são os ASCII dos apelidos, mantidos como estavam para não mudar o
#: comportamento de nenhum nó que esteja no ar durante o deploy.
NAMESPACE_OFICIO = 0x4F464943  # "OFIC"
NAMESPACE_ORDEM_SERVICO = 0x4F534E55  # "OSNU"
NAMESPACE_PLANO_TRABALHO = 0x50544E55  # "PTNU"

TENTATIVAS_PADRAO = 3


def escopo_do_lock(*, ano: int) -> int:
    """Escopo anual global, estável entre processos."""
    return ano % 4096


def bloquear_escopo_numeracao(*, namespace: int, ano: int, modelo) -> None:
    """Advisory lock transacional no PostgreSQL; fallback do GV nos demais."""
    if connection.vendor == "postgresql":
        with connection.cursor() as cursor:
            cursor.execute("SELECT pg_advisory_xact_lock(%s, %s)",
                           [namespace, escopo_do_lock(ano=ano)])
        return
    list(modelo.objects.select_for_update().filter(ano=ano).exclude(numero__isnull=True))


def colisao_de_numero(
    exc: IntegrityError, *, constraint: str, ja_ocupado: Callable[[int], bool], numero: int
) -> bool:
    """A violação foi a corrida por este número, ou é outra coisa?

    Prioriza o nome da constraint; sem metadado, verifica a ocupação.
    """
    diagnostico = getattr(getattr(exc, "__cause__", None), "diag", None)
    nome = getattr(diagnostico, "constraint_name", None)
    if nome:
        return nome == constraint
    return ja_ocupado(numero)


def reservar_numero(
    *,
    namespace: int,
    ano: int,
    modelo,
    constraint: str,
    escolher: Callable[[], int],
    gravar: Callable[[int], None],
    ja_ocupado: Callable[[int], bool],
    apos_colisao: Callable[[], None] | None = None,
    tentativas: int = TENTATIVAS_PADRAO,
) -> int:
    """Escolhe e grava o próximo número, serializado e à prova de corrida perdida.

    - `escolher()` devolve o candidato — é onde mora a **política** de cada documento
      (menor lacuna, `max+1`, contador), e por isso ela não vem para cá.
    - `gravar(numero)` persiste. Roda dentro de um `atomic()` próprio: é **savepoint**, para
      que uma colisão não inutilize a transação de quem chamou.
    - `constraint` é o nome da `UniqueConstraint` que guarda o número. Comparado por
      igualdade contra o metadado da exceção quando o driver o oferece.
    - `ja_ocupado(numero)` responde se aquele número está tomado **agora**. É o segundo
      recurso, para bancos sem metadado.
    - `apos_colisao()` desfaz o que a tentativa perdida deixou no objeto em memória (o pk
      atribuído pelo `INSERT` que falhou, tipicamente).

    Devolve o número gravado.
    """
    bloquear_escopo_numeracao(namespace=namespace, ano=ano, modelo=modelo)

    ultimo_erro: IntegrityError | None = None
    for _tentativa in range(tentativas):
        try:
            with transaction.atomic():
                # Escolha e gravação compartilham o mesmo savepoint.
                numero = escolher()
                gravar(numero)
            return numero
        except IntegrityError as exc:
            if not colisao_de_numero(
                exc, constraint=constraint, ja_ocupado=ja_ocupado, numero=numero
            ):
                # Não foi corrida por este número: a violação é outra e não é nossa.
                raise
            ultimo_erro = exc
            if apos_colisao is not None:
                apos_colisao()

    assert ultimo_erro is not None
    raise ultimo_erro
