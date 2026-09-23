"""Leitura e gravação de `DocumentoBloco`: overrides de parágrafo e quebras.

`conteudo_documental(tipo, objeto)` é o que entra no payload e no contexto:
`blocos` (chave → texto em vigor, padrão e se foi editado) e `quebras` (as
chaves de ponto de quebra ativas). Por entrar no payload, o override muda a
chave de cache do PDF — um documento com texto alterado nunca é servido de
um artefato antigo.

Conteúdo é texto simples com quebras de linha; a renderização escapa. O
DOCX (renderizador à parte, pelo docxtpl) não conhece overrides: sai sempre
com o texto do modelo.
"""

from __future__ import annotations

from django.utils import timezone

from documentos.editor.blocos import blocos_do_tipo, quebras_do_tipo

# Dono dos blocos de um documento, pelo model: o ofício (ofício, justificativa
# e o termo tirado do ofício), o termo do cadastro, a prestação (relatório
# técnico e diário de bordo), a ordem de serviço e o plano de trabalho. O
# tipo do documento separa os blocos de documentos do mesmo dono.
CAMPO_DO_MODELO = {
    "viagens_oficios.oficio": "oficio",
    "viagens_termos.termoautorizacao": "termo",
    "viagens_prestacoes.prestacaocontas": "prestacao",
    "viagens_ordens.ordemservico": "ordem_servico",
    "viagens_planos.planotrabalho": "plano_trabalho",
    "coffee_break.solicitacaocoffeebreak": "coffee_break_solicitacao",
}


def _campo_do_dono(objeto):
    meta = getattr(objeto, "_meta", None)
    return CAMPO_DO_MODELO.get(meta.label_lower) if meta is not None else None


def _filtro(tipo, objeto) -> dict:
    campo = _campo_do_dono(objeto)
    if campo is None:
        raise ValueError(f"Sem vínculo de bloco para {getattr(tipo, 'value', tipo)}")
    # Tipo de outro módulo (a OS do Coffee Break) não está em DocumentoTipo: vale o valor.
    return {"tipo_documento": str(getattr(tipo, "value", tipo)), campo: objeto}


def blocos_gravados(tipo, objeto):
    from documentos.models import DocumentoBloco

    return DocumentoBloco.objects.filter(**_filtro(tipo, objeto)).select_related("editado_por")


def completar_blocos(tipo, dados=None) -> dict[str, dict]:
    """Começa do registro (texto padrão) e aplica o que veio por cima."""
    blocos = {chave: {"conteudo": b.padrao, "padrao": b.padrao, "editado": False} for chave, b in blocos_do_tipo(tipo).items()}
    for chave, valor in (dados or {}).items():
        base = blocos.setdefault(chave, {"conteudo": None, "padrao": "", "editado": False})
        base.update({k: v for k, v in dict(valor).items() if v is not None})
    return blocos


def conteudo_documental(tipo, objeto) -> dict:
    blocos = completar_blocos(tipo)
    pontos = quebras_do_tipo(tipo)
    quebras = []
    if objeto is None or not getattr(objeto, "pk", None) or _campo_do_dono(objeto) is None:
        return {"blocos": blocos, "quebras": quebras}
    for gravado in blocos_gravados(tipo, objeto):
        if gravado.tipo == gravado.Tipo.QUEBRA_PAGINA:
            if gravado.chave in pontos:
                quebras.append(gravado.chave)
        elif gravado.chave in blocos and gravado.editado_manualmente:
            blocos[gravado.chave].update({
                "conteudo": gravado.conteudo_atual,
                "editado": True,
                "editado_por": str(gravado.editado_por) if gravado.editado_por_id else "",
                "editado_em": gravado.editado_em.isoformat() if gravado.editado_em else "",
            })
    return {"blocos": blocos, "quebras": sorted(quebras)}


def bloco_gravado(tipo, objeto, chave):
    return blocos_gravados(tipo, objeto).filter(chave=chave).first()


def versao_do_bloco(tipo, objeto, chave) -> str:
    gravado = bloco_gravado(tipo, objeto, chave)
    return gravado.atualizado_em.isoformat() if gravado and gravado.atualizado_em else ""


def gravar_override(tipo, objeto, chave, conteudo: str, usuario):
    from documentos.models import DocumentoBloco

    definicao = blocos_do_tipo(tipo)[chave]
    # Uma escrita só: o primeiro override é uma criação na trilha de
    # auditoria, os seguintes são atualizações com o delta do texto.
    bloco, _ = DocumentoBloco.objects.update_or_create(**_filtro(tipo, objeto), chave=chave, defaults={
        "tipo": DocumentoBloco.Tipo.PARAGRAFO,
        "conteudo_original": definicao.padrao,
        "conteudo_atual": conteudo,
        "editado_manualmente": True,
        "editado_por": usuario if getattr(usuario, "is_authenticated", False) else None,
        "editado_em": timezone.now(),
    })
    return bloco


def restaurar(tipo, objeto, chave):
    """Volta ao texto do modelo. O registro fica, sem override; a trilha de
    auditoria guarda o que foi alterado e quando."""
    bloco = bloco_gravado(tipo, objeto, chave)
    if bloco is None or not bloco.editado_manualmente:
        return bloco
    bloco.conteudo_atual = bloco.conteudo_original
    bloco.editado_manualmente = False
    bloco.editado_por = None
    bloco.editado_em = None
    bloco.save()
    return bloco


def definir_quebra(tipo, objeto, chave, ativa: bool, usuario) -> bool:
    from documentos.models import DocumentoBloco

    if chave not in quebras_do_tipo(tipo):
        raise ValueError(f"Ponto de quebra desconhecido: {chave}")
    existente = bloco_gravado(tipo, objeto, chave)
    if ativa and existente is None:
        DocumentoBloco.objects.create(
            **_filtro(tipo, objeto), chave=chave, tipo=DocumentoBloco.Tipo.QUEBRA_PAGINA,
            editado_manualmente=True, editado_por=usuario if getattr(usuario, "is_authenticated", False) else None,
            editado_em=timezone.now(),
        )
    elif not ativa and existente is not None:
        existente.delete()
    return ativa
