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


def remover_anexos_do_tipo(prestacao, *, tipo, servidor_prestacao=None, todos_do_tipo=False) -> int:
    """Apaga os anexos de um (tipo, escopo): as linhas agora, os arquivos depois do commit.

    Escopo: os do `servidor_prestacao` (vazio = os compartilhados do ofício) ou,
    com `todos_do_tipo`, todos os daquele tipo na prestação. Chamada dentro de uma
    transação de quem vai criar os novos — sozinha, um rollback depois dela
    devolveria as linhas, e os arquivos continuam lá porque só saem no commit.
    """
    anteriores = PrestacaoDocumentoAnexo.objects.filter(prestacao=prestacao, tipo=tipo)
    if not todos_do_tipo:
        anteriores = anteriores.filter(servidor_prestacao=servidor_prestacao)

    arquivos_antigos = [
        campo
        for anexo in anteriores
        for campo in (anexo.arquivo, anexo.arquivo_original)
        if campo
    ]
    removidos = anteriores.count()
    anteriores.delete()
    for campo_arquivo in arquivos_antigos:
        _apagar_arquivo_apos_commit(campo_arquivo)
    return removidos


@atomico_com_arquivos
def substituir_anexo_assinado(
    prestacao,
    *,
    tipo,
    arquivo,
    nome_original,
    servidor_prestacao=None,
    substituir_todos_do_tipo=False,
    adicionar=False,
) -> ResultadoAnexo:
    """Troca o documento assinado de um tipo, preservando o anterior se algo falhar.

    Com `adicionar` (comprovante e despacho, que têm mais de um arquivo — m081), o
    novo se soma aos que já estavam lá: anexar um terceiro comprovante pela lista não
    pode apagar os dois primeiros.

    A ordem de hoje apagava os arquivos anteriores do disco **antes** de criar a linha
    nova: um `create` que falhasse destruía o documento assinado anterior para sempre.
    Aqui as linhas antigas saem dentro da transação e os arquivos só depois do commit,
    então uma falha na criação devolve tudo — linha e arquivo.

    A validação do arquivo continua na view, antes de chamar esta função: recusar um
    arquivo novo não pode custar o que já estava anexado, e esse era o motivo escrito no
    código antes desta fatia.
    """
    substituidos = 0 if adicionar else remover_anexos_do_tipo(
        prestacao,
        tipo=tipo,
        servidor_prestacao=servidor_prestacao,
        todos_do_tipo=substituir_todos_do_tipo,
    )

    anexo = PrestacaoDocumentoAnexo.objects.create(
        prestacao=prestacao,
        servidor_prestacao=servidor_prestacao,
        tipo=tipo,
        arquivo=arquivo,
        nome_original=nome_original,
    )

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


@atomico_com_arquivos
def endireitar_diario_anexado(anexo) -> bool:
    """Deixa em pé o diário de bordo anexado à mão; devolve se girou alguma página.

    O diário é A4 deitado e costuma voltar do eProtocolo ou do scanner "achatado"
    numa página retrato, de lado. Com texto, a direção dele decide o /Rotate — em
    pé, em paisagem, nunca de cabeça para baixo. O PDF como veio fica em
    `arquivo_original` (o mesmo par do ofício carimbado); o girado vira o `arquivo`.
    Página só de imagem, sem OCR, fica como veio: aqui não há conferência para
    perguntar o lado. Imagem (PNG/JPG) também fica: o pacote a converte como está.
    """
    from django.core.files.base import ContentFile

    from .importacao.montagem import diario_em_pe

    if anexo.tipo != PrestacaoDocumentoAnexo.TIPO_DB_ASSINADO or not anexo.arquivo:
        return False
    anexo.arquivo.open("rb")
    try:
        cru = anexo.arquivo.read()
    finally:
        anexo.arquivo.close()
    girado, mudou = diario_em_pe(cru)
    if not mudou:
        return False
    # O arquivo enviado passa a ser o cru (sem cópia); o girado entra no lugar dele.
    # Num rollback, o girado recém-gravado sai com a transação de arquivos e a linha
    # volta a apontar para o enviado.
    anexo.arquivo_original.name = anexo.arquivo.name
    anexo.arquivo.save(f"diario_de_bordo_{anexo.pk}.pdf", ContentFile(girado), save=False)
    anexo.save(update_fields=["arquivo", "arquivo_original"])
    return True
