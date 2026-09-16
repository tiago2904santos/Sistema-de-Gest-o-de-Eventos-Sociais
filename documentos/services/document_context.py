"""Contexto único de um documento: o que a prévia A4 e o PDF recebem.

Uma regra só para os textos do documento, em um lugar só. Para o ofício, o
contexto reaproveita as duas fontes que já existem — o payload canônico
(`build_canonical_document_payload`) e as regras de texto do documento que
hoje vivem em `viagens_oficios.docxtpl_context` (assunto, órgão de destino,
custeio, motorista, roteiro de ida e volta, diárias por extenso). Elas são
funções puras sobre o ofício; o nome do módulo é herança do DOCX, não uma
dependência dele.

Chaves do contexto:
- `doc`: payload canônico (institucional, oficio, justificativa);
- `tx`: textos calculados do documento;
- `institucional`: cabeçalho e rodapé já formatados para a folha;
- `imagens`: brasão e marca resolvidos para o modo (arquivo local no PDF,
  `/static/` na tela);
- `campos_editaveis`: o que o editor pode marcar (registro explícito);
- `blocos`: overrides de conteúdo documental, por chave.
"""

from __future__ import annotations

from pathlib import Path

from django.conf import settings
from django.templatetags.static import static

from documentos.services.timing import measure_step
from documentos.services.types import DocumentoTipo

IMAGENS = {"brasao": "img/brasao-pcpr.png", "marca": "img/marca-pcpr.png"}


def imagens_para(modo: str) -> dict[str, str]:
    """No PDF a imagem é lida do disco; na tela, servida como estático."""
    if modo == "pdf":
        raiz = Path(settings.BASE_DIR) / "static"
        return {nome: (raiz / rel).resolve().as_uri() for nome, rel in IMAGENS.items()}
    return {nome: static(rel) for nome, rel in IMAGENS.items()}


def _conteudo_documental(tipo, doc, objeto, blocos):
    """Blocos e quebras: do payload (`documento`, posto por quem gerou), do
    banco (prévia na tela) ou do que o chamador passou explicitamente."""
    from documentos.services.document_blocks import completar_blocos, conteudo_documental

    documental = doc.get("documento")
    if documental is None and objeto is not None and getattr(objeto, "pk", None):
        documental = conteudo_documental(tipo, objeto)
    documental = dict(documental or {})
    finais = completar_blocos(tipo, blocos if blocos is not None else documental.get("blocos"))
    return finais, set(documental.get("quebras") or ())


def contexto_do_oficio(oficio=None, *, modo: str = "pdf", campos_editaveis=None, blocos=None, edicao=None, doc=None, tx=None) -> dict:
    """Contexto do ofício. Aceita `doc`/`tx` já calculados (a façade os recebe
    prontos de quem pediu o documento) e só calcula o que faltar. `edicao`
    liga as marcações de bloco e de ponto de quebra no modo editor; por
    padrão acompanha a presença de campos editáveis."""
    if doc is None or tx is None:
        from viagens_oficios.documents import build_canonical_document_payload
        from viagens_oficios.docxtpl_context import build_oficio_docxtpl_context

        with measure_step("contexto_do_oficio", {"oficio_id": oficio.pk, "modo": modo}):
            if doc is None:
                doc = build_canonical_document_payload(oficio, DocumentoTipo.OFICIO)
            if tx is None:
                tx = build_oficio_docxtpl_context(oficio)
    institucional = {
        "unidade_cabecalho": tx.get("unidade_cabecalho", ""),
        "nome_destinatario": tx.get("nome_destinatario", ""),
        "cargo_destinatario": tx.get("cargo_destinatario", ""),
        "cidade_rodape": doc.get("institucional", {}).get("cidade_endereco") or "",
        "unidade_rodape": tx.get("unidade_rodape", ""),
        "endereco": tx.get("endereco", ""),
        "telefone": tx.get("telefone", ""),
        "email": tx.get("email", ""),
    }
    blocos_finais, quebras = _conteudo_documental(DocumentoTipo.OFICIO, doc, oficio, blocos)
    return {
        "doc": doc,
        "tx": tx,
        "institucional": institucional,
        "imagens": imagens_para(modo),
        "campos_editaveis": dict(campos_editaveis or {}),
        "blocos": blocos_finais,
        "quebras": quebras,
        "edicao": bool(campos_editaveis) if edicao is None else bool(edicao),
        "modo": modo,
    }


def contexto_de_payload(tipo, payload, docxtpl_context, *, modo: str = "pdf", **opcoes) -> dict:
    """Contexto a partir dos insumos que a façade já tem em mãos (sem nova
    consulta ao banco): o payload canônico e os textos calculados."""
    if tipo == DocumentoTipo.OFICIO:
        return contexto_do_oficio(modo=modo, doc=dict(payload), tx=dict(docxtpl_context or {}), **opcoes)
    raise NotImplementedError(f"Contexto HTML ainda não existe para {getattr(tipo, 'value', tipo)}")


def contexto_do_documento(tipo, objeto, **opcoes) -> dict:
    """Ponto de entrada por tipo; cada documento migrado ganha a sua função."""
    if tipo == DocumentoTipo.OFICIO:
        return contexto_do_oficio(objeto, **opcoes)
    raise NotImplementedError(f"Contexto HTML ainda não existe para {getattr(tipo, 'value', tipo)}")
