"""Persistência dos anexos assinados: linha no banco, arquivo no storage.

`BE-14` fatia 3, e a única das quatro em que **a transação sozinha piora o sistema**.

O motivo é que aqui o estado mora em dois lugares e só um deles desfaz: o banco tem
`ROLLBACK`, o storage não. Envolver estas funções em `@atomico_com_arquivos` e parar por aí
faria `FieldFile.delete()` rodar dentro da transação, e um rollback depois dela devolveria
a **linha viva apontando para um arquivo destruído** — o inverso exato do órfão que o
`BE-07` corrigiu, e igualmente irrecuperável.

O par correto é **linha na transação, arquivo no `transaction.on_commit`**:

    commit acontece   ->  callback roda  ->  linha e arquivo somem juntos
    rollback acontece ->  callback nunca roda -> linha e arquivo ficam juntos

O padrão já existe no repositório — `core/audit.py:156,170` adia a escrita do evento de
auditoria, e `integracoes/google_drive` adia o envio. Aqui ele passa a valer para
`FieldFile.delete`, que é uso novo.

**O que isto não promete.** Se o callback falhar *depois* do commit, a linha já foi e
sobra arquivo órfão no storage — igual a hoje. `on_commit` não conserta isso e fingir o
contrário seria mentira. A garantia que ele dá é a outra, e é a que importa: **linha viva
apontando para arquivo destruído nunca acontece.**

**A ordem do `BE-07` continua valendo, e por dentro fica ainda mais firme.** A linha sai
primeiro porque apagar o arquivo antes zera `FieldFile.name`, e com `nome_original` vazio
o `__str__` do anexo devolvia `None`, derrubando o sinal de auditoria no `pre_delete`.
Com o arquivo no callback, ele passa a sair **necessariamente** depois — a ordem deixou de
depender de duas linhas escritas na sequência certa.
"""

from __future__ import annotations

from dataclasses import dataclass

from django.db import transaction
from .arquivos import atomico_com_arquivos

from .models import PrestacaoDocumentoAnexo
from .services import marcar_servidor_em_preenchimento
from .services import marcar_servidores_pendentes


@dataclass(frozen=True)
class ResultadoAnexo:
    """O que a operação gravou. A view traduz isto em `messages` ou em JSON."""

    anexo: PrestacaoDocumentoAnexo | None = None
    substituidos: int = 0


def _apagar_arquivo_apos_commit(campo_arquivo) -> None:
    """Agenda a remoção do arquivo para depois do commit.

    `save=False` porque a linha ou já foi apagada, ou já foi salva com o campo novo —
    gravar de novo aqui reabriria escrita fora da transação.
    """
    if not campo_arquivo:
        return
    transaction.on_commit(lambda: campo_arquivo.delete(save=False))


@atomico_com_arquivos
def substituir_anexo_assinado(
    prestacao,
    *,
    tipo,
    arquivo,
    nome_original,
    servidor_prestacao=None,
    substituir_todos_do_tipo=False,
) -> ResultadoAnexo:
    """Troca o documento assinado de um tipo, preservando o anterior se algo falhar.

    A ordem de hoje apagava os arquivos anteriores do disco **antes** de criar a linha
    nova: um `create` que falhasse destruía o documento assinado anterior para sempre.
    Aqui as linhas antigas saem dentro da transação e os arquivos só depois do commit,
    então uma falha na criação devolve tudo — linha e arquivo.

    A validação do arquivo continua na view, antes de chamar esta função: recusar um
    arquivo novo não pode custar o que já estava anexado, e esse era o motivo escrito no
    código antes desta fatia.
    """
    anteriores = PrestacaoDocumentoAnexo.objects.filter(prestacao=prestacao, tipo=tipo)
    if not substituir_todos_do_tipo:
        anteriores = anteriores.filter(servidor_prestacao=servidor_prestacao)

    arquivos_antigos = [
        campo
        for anexo in anteriores
        for campo in (anexo.arquivo, anexo.arquivo_original)
        if campo
    ]
    substituidos = anteriores.count()
    anteriores.delete()

    anexo = PrestacaoDocumentoAnexo.objects.create(
        prestacao=prestacao,
        servidor_prestacao=servidor_prestacao,
        tipo=tipo,
        arquivo=arquivo,
        nome_original=nome_original,
    )
    for campo_arquivo in arquivos_antigos:
        _apagar_arquivo_apos_commit(campo_arquivo)

    if servidor_prestacao is not None:
        marcar_servidor_em_preenchimento(servidor_prestacao)
    else:
        marcar_servidores_pendentes(prestacao)
    return ResultadoAnexo(anexo=anexo, substituidos=substituidos)


@atomico_com_arquivos
def excluir_anexo(anexo, prestacao) -> ResultadoAnexo:
    """Apaga a linha e agenda o arquivo para depois do commit.

    `BE-07`: a linha sai primeiro. Antes isso dependia de duas chamadas na sequência
    certa; agora o arquivo sai no callback, então sair depois deixou de ser convenção e
    virou consequência de onde a chamada está.
    """
    servidor_prestacao = anexo.servidor_prestacao
    # Os DOIS arquivos: o entregue e o cru de onde o carimbo parte. Esquecer o cru
    # deixaria órfão o PDF do eProtocolo, que é o maior dos dois.
    campos = [campo for campo in (anexo.arquivo, anexo.arquivo_original) if campo]
    anexo.delete()
    for campo_arquivo in campos:
        _apagar_arquivo_apos_commit(campo_arquivo)

    if servidor_prestacao is not None:
        marcar_servidor_em_preenchimento(servidor_prestacao)
    else:
        marcar_servidores_pendentes(prestacao)
    return ResultadoAnexo(substituidos=1)
