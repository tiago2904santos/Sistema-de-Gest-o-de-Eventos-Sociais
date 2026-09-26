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
from django.utils import timezone
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
    """Tira de uso os anexos de um (tipo, escopo), guardando-os como "substituídos".

    Escopo: os do `servidor_prestacao` (vazio = os compartilhados do ofício) ou,
    com `todos_do_tipo`, todos os daquele tipo na prestação.

    m084: a linha fica, marcada, e o arquivo também — o anterior aparece em
    "Versões anteriores" e dá para voltar a ele. Quem apaga de vez é
    `purgar_anexos_removidos`, depois do período de guarda.
    """
    anteriores = PrestacaoDocumentoAnexo.objects.filter(prestacao=prestacao, tipo=tipo)
    if not todos_do_tipo:
        anteriores = anteriores.filter(servidor_prestacao=servidor_prestacao)
    return anteriores.update(removido_em=timezone.now(), removido_motivo=PrestacaoDocumentoAnexo.REMOVIDO_SUBSTITUIDO)


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

    A ordem antiga apagava os arquivos anteriores do disco **antes** de criar a linha
    nova: um `create` que falhasse destruía o documento assinado anterior para sempre.
    Desde o m084 o anterior só é marcado como substituído (arquivo intacto), dentro da
    mesma transação: uma falha na criação o devolve ao uso.

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
    """Tira o anexo de uso, guardando-o em "Versões anteriores" (m084).

    Antes a linha e o arquivo saíam na hora, sem volta: um clique errado no "x"
    destruía o despacho ou o comprovante que chegou pelo eProtocolo. O arquivo só
    sai de vez em `purgar_anexos_removidos`.
    """
    servidor_prestacao = anexo.servidor_prestacao
    anexo.removido_em = timezone.now()
    anexo.removido_motivo = PrestacaoDocumentoAnexo.REMOVIDO_EXCLUIDO
    anexo.save(update_fields=["removido_em", "removido_motivo"])

    if servidor_prestacao is not None:
        marcar_servidor_em_preenchimento(servidor_prestacao)
    else:
        marcar_servidores_pendentes(prestacao)
    return ResultadoAnexo(substituidos=1)


@atomico_com_arquivos
def restaurar_anexo(anexo) -> ResultadoAnexo:
    """Volta um anexo removido ou substituído (o "Desfazer" e o "voltar para esta versão").

    Nos tipos de arquivo único (ofício, RT, diário), o que estiver em uso no mesmo
    escopo passa a ser a versão anterior — trocam de lugar. No ofício, os carimbos
    do número de solicitação nunca saíram da linha, e voltam junto; o PDF é
    redesenhado depois do commit, porque o número pode ter mudado nesse meio-tempo.
    """
    if anexo.removido_em is None:
        return ResultadoAnexo(anexo=anexo)
    substituidos = 0
    if anexo.tipo in PrestacaoDocumentoAnexo.TIPOS_UNICOS:
        substituidos = remover_anexos_do_tipo(
            anexo.prestacao,
            tipo=anexo.tipo,
            servidor_prestacao=anexo.servidor_prestacao,
            todos_do_tipo=anexo.servidor_prestacao_id is None,
        )
    anexo.removido_em = None
    anexo.removido_motivo = ""
    anexo.save(update_fields=["removido_em", "removido_motivo"])
    if anexo.servidor_prestacao_id is not None:
        marcar_servidor_em_preenchimento(anexo.servidor_prestacao)
    else:
        marcar_servidores_pendentes(anexo.prestacao)
    if anexo.tipo == PrestacaoDocumentoAnexo.TIPO_OFICIO_ASSINADO:
        from .carimbo_services import recarimbar_prestacao

        prestacao = anexo.prestacao
        transaction.on_commit(lambda: recarimbar_prestacao(prestacao))
    return ResultadoAnexo(anexo=anexo, substituidos=substituidos)


def versoes_anteriores(queryset):
    """Os removidos/substituídos ainda guardados, do mais recente para o mais antigo."""
    from datetime import timedelta

    from .models import DIAS_GUARDA_ANEXO_REMOVIDO

    limite = timezone.now() - timedelta(days=DIAS_GUARDA_ANEXO_REMOVIDO)
    return queryset.filter(removido_em__isnull=False, removido_em__gte=limite).order_by("-removido_em", "-pk")


def purgar_anexos_removidos(*, dias=None, apagar=False) -> list[PrestacaoDocumentoAnexo]:
    """Os anexos removidos há mais de `dias`; com `apagar`, saem de vez (linha e arquivos).

    Os arquivos saem depois do commit, pelo mesmo motivo de sempre: rollback do
    banco não devolve arquivo apagado.
    """
    from datetime import timedelta

    from .models import DIAS_GUARDA_ANEXO_REMOVIDO

    dias = DIAS_GUARDA_ANEXO_REMOVIDO if dias is None else dias
    limite = timezone.now() - timedelta(days=dias)
    vencidos = list(PrestacaoDocumentoAnexo.todos.filter(removido_em__isnull=False, removido_em__lt=limite))
    if not apagar:
        return vencidos
    with transaction.atomic():
        for anexo in vencidos:
            campos = [campo for campo in (anexo.arquivo, anexo.arquivo_original) if campo]
            anexo.delete()
            for campo_arquivo in campos:
                _apagar_arquivo_apos_commit(campo_arquivo)
    return vencidos


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
