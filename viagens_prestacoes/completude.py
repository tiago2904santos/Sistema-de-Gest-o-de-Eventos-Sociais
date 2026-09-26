"""Quando o diário e o relatório técnico estão prontos — e quando estão assinados (m091).

Antes, o selo "Diário ✓" e "Relatório ✓" acendia porque a LINHA existia, e ela é
criada por `get_or_create` na primeira visita à tela: bastava abrir para parecer
pronto, com km e textos em branco. Aqui são três estados:

- `ASSINADO`: o documento assinado foi anexado (só então o "✓");
- `GERADO`: preenchido por inteiro, o PDF sai completo, mas o assinado ainda não voltou;
- `""`: falta preencher.

As funções leem as relações já carregadas quando a lista as pré-carregou
(`prefetch_related`), e consultam o banco só quando não.
"""

from __future__ import annotations

from django.core.exceptions import ObjectDoesNotExist

from .models import PrestacaoDocumentoAnexo as Anexo

ASSINADO = "assinado"
GERADO = "gerado"


def _anexos(dono, tipo) -> bool:
    return any(a.tipo == tipo for a in dono.documentos_anexos.all())


def diario_preenchido(prestacao) -> bool:
    """Todos os trechos do diário com km inicial e final."""
    try:
        diario = prestacao.diario_bordo
    except ObjectDoesNotExist:
        return False
    trechos = list(diario.trechos.all())
    return bool(trechos) and all(t.km_inicial is not None and t.km_final is not None for t in trechos)


def rt_preenchido(prestacao) -> bool:
    """Descrição do evento, objetivo da participação e conclusão escritos."""
    try:
        rt = prestacao.relatorio_tecnico
    except ObjectDoesNotExist:
        return False
    return all(str(getattr(rt, campo) or "").strip() for campo in ("motivo", "atividade", "conclusao"))


def situacao_diario(prestacao) -> str:
    if _anexos(prestacao, Anexo.TIPO_DB_ASSINADO):
        return ASSINADO
    return GERADO if diario_preenchido(prestacao) else ""


def situacao_rt(servidor_prestacao) -> str:
    if _anexos(servidor_prestacao, Anexo.TIPO_RT_ASSINADO):
        return ASSINADO
    return GERADO if rt_preenchido(servidor_prestacao.prestacao) else ""


def diario_completo(prestacao) -> bool:
    """Diário pronto para o pacote: assinado anexado ou preenchido por inteiro."""
    return bool(situacao_diario(prestacao))


def rt_completo(servidor_prestacao) -> bool:
    """RT pronto para o pacote: assinado anexado ou os textos obrigatórios escritos."""
    return bool(situacao_rt(servidor_prestacao))
