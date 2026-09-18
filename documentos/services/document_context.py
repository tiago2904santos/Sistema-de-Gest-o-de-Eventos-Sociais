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


_SEM_VALOR = {"", "-", "—"}


def _valor(tx, chave) -> str:
    """Texto do campo, ou vazio quando o payload marcou a falta com traço —
    o template transforma vazio em lacuna para preencher à mão."""
    texto = str(tx.get(chave) or "").strip()
    return "" if texto in _SEM_VALOR else texto


def contexto_do_termo(payload, tx, *, modo: str = "pdf") -> dict:
    """Contexto do termo de autorização. `payload` é o de `build_termo_payload`
    ou `build_termo_cadastro_payload`; `tx` são os textos planos que o DOCX
    também recebe (`viagens_termos.services._legacy_docx_context`), para as
    duas saídas lerem a mesma regra."""
    from viagens_oficios.documents import VarianteTermo

    tx = dict(tx or {})
    variante = ((payload or {}).get("termo") or {}).get("variante") or VarianteTermo.SEMIPREENCHIDO
    termo = {
        chave: _valor(tx, chave)
        for chave in (
            "nome_servidor", "cpf_servidor", "telefone", "lotacao",
            "data_do_evento", "destino", "viatura", "placa", "combustivel",
        )
    }
    semipreenchido = variante == VarianteTermo.SEMIPREENCHIDO
    com_viatura = variante == VarianteTermo.COMPLETO_COM_VIATURA
    # O que a variante deixa para preencher à mão não sai no documento, nem
    # no título da aba, mesmo que o payload traga o dado.
    apagar = (("nome_servidor", "cpf_servidor", "telefone", "lotacao") if semipreenchido else ())
    apagar += () if com_viatura else ("viatura", "placa", "combustivel")
    termo.update(dict.fromkeys(apagar, ""), variante=variante, semipreenchido=semipreenchido, com_viatura=com_viatura)
    servidor = [termo[c] for c in ("nome_servidor", "cpf_servidor", "telefone", "lotacao")]
    # Sem nenhum dado do servidor (termo só da viatura), as linhas para preencher
    # são as do semipreenchido; com um dado faltando, a lacuna fica na frase.
    termo["servidor_em_branco"] = not semipreenchido and not any(servidor)
    termo["tem_lacuna"] = not semipreenchido and any(servidor) and not all(servidor)
    return {
        "doc": payload,
        "termo": termo,
        "institucional": {
            "unidade_cabecalho": tx.get("unidade", ""),
            "unidade_rodape": tx.get("unidade_rodape", ""),
        },
        "imagens": imagens_para(modo),
        "campos_editaveis": {},
        "blocos": {},
        "quebras": set(),
        "edicao": False,
        "modo": modo,
    }


def contexto_da_justificativa(payload, tx, *, modo: str = "pdf") -> dict:
    """Contexto da justificativa. `tx` são os textos que o DOCX também recebe
    (`build_justificativa_docxtpl_context`): sede, data por extenso, texto,
    assinante e cargo. Cada linha do texto é um parágrafo do documento."""
    tx = dict(tx or {})
    texto = str(tx.get("justificativa") or "")
    return {
        "doc": payload,
        "justificativa": {
            "sede": str(tx.get("sede") or "").strip(),
            "data_extenso": str(tx.get("data_extenso") or "").strip(),
            "paragrafos": [linha.strip() for linha in texto.splitlines() if linha.strip()],
            "assinante": str(tx.get("assinante_justificativa") or "").strip(),
            "cargo": str(tx.get("cargo_assinante_justificativa") or "").strip(),
        },
        "institucional": {
            "unidade_cabecalho": tx.get("unidade", ""),
            "unidade_rodape": tx.get("unidade_rodape", ""),
        },
        "imagens": imagens_para(modo),
        "campos_editaveis": {},
        "blocos": {},
        "quebras": set(),
        "edicao": False,
        "modo": modo,
    }


def _destacar(texto: str, trechos) -> str:
    """Texto pronto (escapado) com os trechos dados em negrito, onde aparecerem.
    Serve aos parágrafos que o contexto já entrega montados, como a
    determinação da OS, em que destino e período vêm no meio da frase."""
    from django.utils.html import escape
    from django.utils.safestring import mark_safe

    html = str(escape(texto))
    for trecho in trechos:
        if trecho:
            alvo = str(escape(trecho))
            html = html.replace(alvo, f"<strong>{alvo}</strong>")
    return mark_safe(html)


def _linha_de_rodape(tx) -> str:
    """Unidade, endereço, telefone e e-mail numa linha, pulando o que faltar."""
    unidade = str(tx.get("unidade_rodape") or "").strip()
    endereco = str(tx.get("endereco") or "").strip()
    contato = " – ".join(p for p in (str(tx.get("telefone") or "").strip(), str(tx.get("email") or "").strip()) if p)
    return " - ".join(p for p in (unidade, " ".join(p for p in (endereco, contato) if p)) if p)


def contexto_da_ordem_servico(payload, tx, *, modo: str = "pdf") -> dict:
    """Contexto da Ordem de Serviço. `tx` são os textos que o DOCX também recebe
    (`viagens_ordens.docxtpl_context.build_os_docxtpl_context`); o tipo padrão
    usa o parágrafo único de deslocamento, os demais os textos do modelo."""
    from viagens_ordens.models import OrdemServico

    tx = dict(tx or {})
    texto = lambda chave: str(tx.get(chave) or "").strip()  # noqa: E731
    padrao = (tx.get("tipo_necessidade") or OrdemServico.TIPO_PADRAO) == OrdemServico.TIPO_PADRAO
    os_ = {
        chave: texto(chave)
        for chave in (
            "unidade_abreviado", "nome_chefia", "cargo_chefia", "equipe_deslocamento", "destino",
            "data_extenso", "motivo", "determinacao", "finalidade", "sede", "data_atual_extenso",
        )
    }
    os_.update(
        numero=texto("ordem_de_servico"),
        determinacao=_destacar(texto("determinacao"), (texto("destino"), texto("data_extenso"))),
        padrao=padrao,
        referencia="Diligências" if padrao else texto("referencia"),
        competencias_equipe=[str(i).strip() for i in (tx.get("competencias_equipe") or []) if str(i).strip()],
        justificativas=[str(i).strip() for i in (tx.get("justificativas") or []) if str(i).strip()],
        rodape=_linha_de_rodape(tx),
    )
    return {
        "doc": payload,
        "os": os_,
        "institucional": {"unidade_cabecalho": tx.get("unidade", ""), "unidade_rodape": tx.get("unidade_rodape", "")},
        "imagens": imagens_para(modo),
        "campos_editaveis": {},
        "blocos": {},
        "quebras": set(),
        "edicao": False,
        "modo": modo,
    }


def _paragrafos(texto) -> list[str]:
    """Texto livre em parágrafos: linha em branco separa parágrafo; quebra
    simples fica dentro dele (o template a desenha com `linhas`)."""
    blocos = str(texto or "").replace("\r\n", "\n").split("\n\n")
    return [bloco.strip("\n") for bloco in blocos if bloco.strip()]


def contexto_do_plano_trabalho(payload, tx, *, modo: str = "pdf") -> dict:
    """Contexto do Plano de Trabalho. `tx` são os textos que o DOCX também
    recebe (`viagens_planos.docxtpl_context.build_plano_docxtpl_context`); o
    valor do plano de vários eventos chega em `valor_blocos`, texto simples,
    porque o DOCX o recebe como RichText."""
    tx = dict(tx or {})
    texto = lambda chave: str(tx.get(chave) or "").strip()  # noqa: E731
    valor = tx.get("valor_do_plano")
    plano = {
        chave: texto(chave)
        for chave in (
            "unidade", "metas", "atividades", "data_evento", "destinos", "horario_de_atendimento", "efetivos",
            "unidade_movel", "recursos_necessarios", "sede", "data_extenso", "nome_chefia", "cargo_chefia",
        )
    }
    plano.update(
        numero=texto("numero_plano_trabalho"),
        multi=bool(tx.get("is_multi_evento")),
        eventos=[dict(ev) for ev in (tx.get("eventos") or [])],
        contextualizacao=_paragrafos(tx.get("contextualizacao")),
        coordenacao=_paragrafos(tx.get("coordenacao")),
        consideracao_final=_paragrafos(tx.get("consideracao_final")),
        valor_blocos=[dict(b) for b in (tx.get("valor_blocos") or [])],
        valor_do_plano=valor.strip() if isinstance(valor, str) else "",
        rodape=_linha_de_rodape(tx),
    )
    if plano["multi"] and len(plano["eventos"]) == 1:
        # Plano de vários eventos com um evento só: a divisão por evento (data
        # sobre cada lista, valor do evento e valor total iguais) não diz nada;
        # sai como o plano de um evento, com os textos desse evento.
        ev = plano["eventos"][0]
        plano.update(
            multi=False,
            metas=str(ev.get("metas") or "").strip(),
            atividades=str(ev.get("atividades") or "").strip(),
            recursos_necessarios=str(ev.get("recursos") or "").strip(),
            destinos=str(ev.get("local") or "").strip() or plano["destinos"],
            horario_de_atendimento=str(ev.get("horario") or "").strip() or plano["horario_de_atendimento"],
            efetivos=str(ev.get("efetivo") or "").strip() or plano["efetivos"],
            unidade_movel=str(ev.get("unidade_movel") or "").strip(),
            valor_blocos=plano["valor_blocos"][-1:],
        )
    if not plano["valor_blocos"] and plano["valor_do_plano"].startswith("Valor total:"):
        # O de um evento traz o valor numa frase só; o rótulo sai em negrito,
        # como no de vários eventos.
        plano["valor_blocos"] = [{"rotulo": "Valor total:", "texto": plano["valor_do_plano"][len("Valor total:"):]}]
    return {
        "doc": payload,
        "plano": plano,
        "institucional": {"unidade_cabecalho": tx.get("unidade", ""), "unidade_rodape": tx.get("unidade_rodape", "")},
        "imagens": imagens_para(modo),
        "campos_editaveis": {},
        "blocos": {},
        "quebras": set(),
        "edicao": False,
        "modo": modo,
    }


_SECOES_RELATORIO_TECNICO = (
    ("Descrição do evento", "motivo"),
    ("Objetivo da participação", "atividade"),
    ("Conclusão", "conclusao"),
    ("Medidas a serem adotadas pelo órgão", "medidas"),
    ("Informações complementares", "info_complementares"),
)


def contexto_do_relatorio_tecnico(payload, tx, *, modo: str = "pdf") -> dict:
    """Contexto do Relatório Técnico. `tx` é o mesmo contexto que o DOCX recebe
    (`viagens_prestacoes.services.build_relatorio_tecnico_context`). O .docx
    traz "Cartão Prime" escrito no lugar do combustível; aqui vale o campo
    do relatório, com "Cartão Prime" quando ele vier vazio."""
    tx = dict(tx or {})
    texto = lambda chave: str(tx.get(chave) or "").strip()  # noqa: E731
    rt = {
        chave: texto(chave)
        for chave in ("oficio", "sede", "data_atual_extenso", "nome_servidor", "cpf_servidor", "diaria", "translado", "passagem")
    }
    rt.update(
        combustivel=texto("combustivel") or "Cartão Prime",
        secoes=[{"titulo": titulo, "texto": texto(chave)} for titulo, chave in _SECOES_RELATORIO_TECNICO],
        rodape=_linha_de_rodape(tx),
    )
    return {
        "doc": payload,
        "rt": rt,
        "institucional": {"unidade_cabecalho": tx.get("unidade_cabecalho", ""), "unidade_rodape": tx.get("unidade_rodape", "")},
        "imagens": imagens_para(modo),
        "campos_editaveis": {},
        "blocos": {},
        "quebras": set(),
        "edicao": False,
        "modo": modo,
    }


def contexto_do_diario_bordo(payload, *, modo: str = "pdf") -> dict:
    """Contexto do Diário de Bordo. O payload é o mesmo que preenche a planilha
    (`build_diario_bordo_context`): `header` com ofício, viatura e motorista e
    `trechos`, uma linha por trecho do roteiro."""
    header = dict((payload or {}).get("header") or {})
    texto = lambda chave: str(header.get(chave) or "").strip()  # noqa: E731
    numero, ano = texto("oficio_motorista"), texto("ano")
    diario = {
        "oficio": f"{numero}/{ano}" if numero and ano else numero,
        "protocolo": texto("protocolo_motorista"),
        "viatura": texto("viatura"),
        "combustivel": texto("combustivel"),
        "placa": texto("placa"),
        "placa_reservada": texto("placa_reservada"),
        "motorista": texto("motorista"),
        "cpf_motorista": texto("cpf_motorista"),
        "trechos": [
            {chave: str(t.get(chave) if t.get(chave) is not None else "").strip() for chave in (
                "data_saida", "hora_saida", "km_inicial", "data_chegada", "hora_chegada", "km_final",
                "origem", "destino", "abastecimento",
            )}
            for t in ((payload or {}).get("trechos") or [])
        ],
    }
    return {
        "doc": payload,
        "diario": diario,
        "institucional": {"divisao_cabecalho": texto("divisao"), "unidade_cabecalho": texto("unidade_cabecalho")},
        "imagens": imagens_para(modo),
        "campos_editaveis": {},
        "blocos": {},
        "quebras": set(),
        "edicao": False,
        "modo": modo,
    }


def contexto_de_payload(tipo, payload, docxtpl_context, *, modo: str = "pdf", **opcoes) -> dict:
    """Contexto a partir dos insumos que a façade já tem em mãos (sem nova
    consulta ao banco): o payload canônico e os textos calculados."""
    if tipo == DocumentoTipo.OFICIO:
        return contexto_do_oficio(modo=modo, doc=dict(payload), tx=dict(docxtpl_context or {}), **opcoes)
    if tipo == DocumentoTipo.TERMO_AUTORIZACAO:
        return contexto_do_termo(dict(payload), docxtpl_context, modo=modo)
    if tipo == DocumentoTipo.JUSTIFICATIVA:
        return contexto_da_justificativa(dict(payload), docxtpl_context, modo=modo)
    if tipo == DocumentoTipo.ORDEM_SERVICO:
        return contexto_da_ordem_servico(dict(payload), docxtpl_context, modo=modo)
    if tipo == DocumentoTipo.PLANO_TRABALHO:
        return contexto_do_plano_trabalho(dict(payload), docxtpl_context, modo=modo)
    if tipo == DocumentoTipo.RELATORIO_TECNICO:
        return contexto_do_relatorio_tecnico(dict(payload), docxtpl_context, modo=modo)
    if tipo == DocumentoTipo.DIARIO_BORDO:
        return contexto_do_diario_bordo(dict(payload), modo=modo)
    raise NotImplementedError(f"Contexto HTML ainda não existe para {getattr(tipo, 'value', tipo)}")


def contexto_do_documento(tipo, objeto, **opcoes) -> dict:
    """Ponto de entrada por tipo; cada documento migrado ganha a sua função."""
    if tipo == DocumentoTipo.OFICIO:
        return contexto_do_oficio(objeto, **opcoes)
    raise NotImplementedError(f"Contexto HTML ainda não existe para {getattr(tipo, 'value', tipo)}")
