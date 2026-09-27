"""Limpeza dos arquivos que se acumulam (m128): PDFs antigos, órfãos,
importações temporárias e sessões vencidas.

Cada vez que um ofício, termo ou plano muda e o PDF é gerado de novo, o
sistema guarda uma cópia nova e nunca apagava as anteriores — cada uma com
dados pessoais (nome, CPF, lotação). Aqui sai o que ficou velho, e só ele:

1. **artefatos documentais** com mais de `dias` que não são a via emitida
   (m113), não têm versão assinada nem arquivo assinado, não são a geração
   mais recente do seu documento e não são apontados por nenhum outro
   registro — linha e arquivo;
2. **arquivos órfãos** no storage privado (todas as pastas de `upload_to`),
   com mais de um dia, que nenhum FileField vivo referencia, e os anexos de
   prestação removidos há mais de 30 dias (`limpar_arquivos_orfaos`);
3. a **pasta temporária** das planilhas importadas do Coffee Break;
4. as **sessões vencidas** (`clearsessions`).

Roda uma vez por semana pelas rotinas diárias (`core.rotinas`), idempotente,
e a administração recebe no sino o resumo do que saiu. O comando
`manage.py limpar_arquivos` faz o mesmo à mão (sem `--apagar`, só simula).
"""

from __future__ import annotations

import logging
import re
import tempfile
from datetime import timedelta
from pathlib import Path

from django.core.cache import cache
from django.core.files.storage import default_storage
from django.db.models import Q
from django.utils import timezone

logger = logging.getLogger(__name__)

#: Artefatos documentais mais velhos que isto são candidatos a sair.
DIAS_GUARDA_ARTEFATOS = 90
#: Arquivo (órfão ou temporário) mais novo que isto pode ser um envio em
#: andamento: fica.
HORAS_DE_CARENCIA = 24
#: A limpeza automática roda no máximo uma vez a cada tantos dias.
DIAS_ENTRE_LIMPEZAS = 7
#: Pasta temporária das planilhas do Coffee Break (nome dentro do tempdir).
PASTA_IMPORTACAO_COFFEE = "coffee-break-importacao"

_CHAVE_ULTIMA = "limpeza-arquivos:ultima"
_DATA_NO_NOME = re.compile(r"_\d{8}-\d{6}(?=\.\w+$)")

# Os vínculos que identificam "o mesmo documento" de um artefato.
_CAMPOS_DO_DOCUMENTO = (
    "tipo", "formato", "oficio_id", "termo_id", "prestacao_id", "ordem_servico_id",
    "plano_trabalho_id", "coffee_break_solicitacao_id", "servidor_id", "roteiro_id",
)


def pasta_importacao_coffee() -> Path:
    return Path(tempfile.gettempdir()) / PASTA_IMPORTACAO_COFFEE


def _referencia(nome_exibicao: str) -> str:
    """`oficio_12-2026_20260901-101010.pdf` → `oficio_12-2026`: a referência
    separa documentos com os mesmos vínculos (o termo vazio e o da viatura)."""
    return _DATA_NO_NOME.sub("", nome_exibicao or "")


def _protegidos():
    """A condição do que nunca sai: via emitida, assinado ou apontado por outro registro."""
    from documentos.models import DocumentoArtefato

    condicao = Q(versao_emitida__isnull=False) | ~Q(arquivo_assinado="")
    for relacao in DocumentoArtefato._meta.related_objects:
        condicao |= Q(**{f"{relacao.field.related_query_name()}__isnull": False})
    return condicao


def _mais_recentes_por_documento() -> set:
    from documentos.models import DocumentoArtefato

    ultimo = {}
    linhas = DocumentoArtefato.objects.values_list(*_CAMPOS_DO_DOCUMENTO, "nome_exibicao", "criado_em", "pk")
    for linha in linhas.iterator():
        *vinculos, nome, criado_em, pk = linha
        chave = (*vinculos, _referencia(nome))
        if chave not in ultimo or criado_em > ultimo[chave][0]:
            ultimo[chave] = (criado_em, pk)
    return {pk for _, pk in ultimo.values()}


def artefatos_vencidos(dias=DIAS_GUARDA_ARTEFATOS):
    """Os artefatos que podem sair: velhos, sem proteção e não os mais recentes."""
    from documentos.models import DocumentoArtefato

    limite = timezone.now() - timedelta(days=dias)
    manter = _mais_recentes_por_documento()
    candidatos = DocumentoArtefato.objects.filter(criado_em__lt=limite).exclude(_protegidos()).order_by("criado_em")
    return [artefato for artefato in candidatos if artefato.pk not in manter]


def expurgar_artefatos(*, dias=DIAS_GUARDA_ARTEFATOS, apagar=False) -> list:
    """Apaga (com `apagar`) os artefatos vencidos, linha e arquivo; devolve-os."""
    vencidos = artefatos_vencidos(dias)
    if not apagar:
        return vencidos
    for artefato in vencidos:
        nome = artefato.arquivo.name if artefato.arquivo else ""
        storage = artefato.arquivo.storage if artefato.arquivo else default_storage
        try:
            artefato.delete()
        except Exception:
            logger.exception("Não foi possível apagar o artefato %s.", artefato.pk)
            continue
        if nome:
            try:
                storage.delete(nome)
            except Exception:
                logger.warning("Arquivo do artefato %s não pôde ser apagado (%s).", artefato.pk, nome)
    return vencidos


def _antigo(nome: str) -> bool:
    """Só o que tem mais de `HORAS_DE_CARENCIA` sai; sem data conhecida, fica."""
    try:
        modificado = default_storage.get_modified_time(nome)
    except (NotImplementedError, OSError, ValueError):
        return False
    if timezone.is_naive(modificado):
        modificado = timezone.make_aware(modificado)
    return timezone.now() - modificado > timedelta(hours=HORAS_DE_CARENCIA)


def arquivos_orfaos() -> list[str]:
    """Arquivos de todas as pastas de upload que nenhum FileField referencia,
    com mais de um dia (um envio em andamento ainda não tem registro)."""
    from viagens_prestacoes.management.commands.limpar_arquivos_orfaos import PREFIXOS, _arquivos_referenciados, _listar_arquivos

    orfaos = []
    for prefixo in PREFIXOS:
        referenciados = _arquivos_referenciados(prefixo)
        orfaos.extend(nome for nome in sorted(set(_listar_arquivos(prefixo)) - referenciados) if _antigo(nome))
    return orfaos


def limpar_orfaos(*, apagar=False) -> list[str]:
    orfaos = arquivos_orfaos()
    if apagar:
        for nome in orfaos:
            try:
                default_storage.delete(nome)
            except Exception:
                logger.warning("Arquivo órfão %s não pôde ser apagado.", nome)
    return orfaos


def limpar_importacoes_coffee(*, apagar=False) -> list[str]:
    """As planilhas enviadas para importar, depois da carência."""
    pasta = pasta_importacao_coffee()
    if not pasta.is_dir():
        return []
    limite = timezone.now().timestamp() - HORAS_DE_CARENCIA * 3600
    vencidos = []
    for arquivo in sorted(pasta.iterdir()):
        try:
            if arquivo.is_file() and arquivo.stat().st_mtime < limite:
                vencidos.append(arquivo.name)
                if apagar:
                    arquivo.unlink()
        except OSError:
            logger.warning("Importação temporária %s não pôde ser apagada.", arquivo)
    return vencidos


def limpar(*, dias=DIAS_GUARDA_ARTEFATOS, apagar=False) -> dict:
    """Tudo de uma vez; devolve o resumo (listas do que saiu ou sairia)."""
    from django.core.management import call_command

    from viagens_prestacoes.anexo_services import purgar_anexos_removidos

    resumo = {
        "artefatos": expurgar_artefatos(dias=dias, apagar=apagar),
        "anexos_removidos": purgar_anexos_removidos(apagar=apagar),
        "orfaos": limpar_orfaos(apagar=apagar),
        "importacoes_coffee": limpar_importacoes_coffee(apagar=apagar),
        "sessoes": False,
    }
    if apagar:
        try:
            call_command("clearsessions", verbosity=0)
            resumo["sessoes"] = True
        except Exception:
            logger.exception("clearsessions falhou.")
    return resumo


def descrever(resumo: dict) -> str:
    partes = [
        f"{len(resumo['artefatos'])} PDF/DOCX antigo(s) de documentos",
        f"{len(resumo['anexos_removidos'])} anexo(s) de prestação removido(s) há mais de 30 dias",
        f"{len(resumo['orfaos'])} arquivo(s) órfão(s)",
        f"{len(resumo['importacoes_coffee'])} planilha(s) temporária(s) do Coffee Break",
    ]
    if resumo.get("sessoes"):
        partes.append("sessões vencidas")
    return "; ".join(partes)


def total(resumo: dict) -> int:
    return sum(len(resumo[chave]) for chave in ("artefatos", "anexos_removidos", "orfaos", "importacoes_coffee"))


def _avisar_administracao(resumo: dict) -> None:
    from django.contrib.auth import get_user_model

    from core.notificacoes import notificar

    administradores = get_user_model().objects.filter(is_active=True).filter(Q(is_staff=True) | Q(is_superuser=True))
    notificar(administradores, "Limpeza semanal de arquivos", f"Removidos: {descrever(resumo)}.")


def rotina_semanal(hoje=None) -> str:
    """A limpeza pelas rotinas diárias: no máximo uma vez a cada
    `DIAS_ENTRE_LIMPEZAS` dias (a data da última fica no cache compartilhado)."""
    hoje = hoje or timezone.localdate()
    ultima = cache.get(_CHAVE_ULTIMA)
    if ultima and (hoje - timezone.datetime.fromisoformat(ultima).date()).days < DIAS_ENTRE_LIMPEZAS:
        return f"já rodou em {ultima}"
    cache.set(_CHAVE_ULTIMA, hoje.isoformat(), 60 * 24 * 60 * 60)
    resumo = limpar(apagar=True)
    if total(resumo):
        _avisar_administracao(resumo)
    return descrever(resumo)
