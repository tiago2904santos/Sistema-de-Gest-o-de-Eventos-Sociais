"""O "Baixar documentos" da viagem: tudo o que ela reúne num modal só.

Os itens seguem a ordem das etapas — ofícios (com justificativa e termos de
cada um), planos de trabalho, ordens de serviço, termos de autorização e os
documentos de solicitação anexados. Cada valor carrega o documento de origem
(`oficio-12:justificativa`, `termo-3:45`, `pt-7`, `os-9`, `sol-2`) e a
geração reaproveita o gerador de cada módulo, com a mesma regra de "versão"
(assinado ou original) das listas. Documento cancelado, ou plano ainda
incompleto, não entra: não haveria o que gerar.
"""
from types import SimpleNamespace

from documentos.services.types import DocumentoFormato, DocumentoTipo

from .selectors import listar_oficios_da_viagem, listar_termos_da_viagem


def _estado(artefato):
    if not artefato:
        return "Sem PDF", False
    return ("Assinado" if artefato["assinado"] else "PDF gerado"), bool(artefato["assinado"])


def itens_para_baixar(viagem):
    """Os itens do modal, no formato do `baixar-documentos.js`."""
    import json

    from viagens_oficios.presenters import artefatos_pdf_por_oficio, documentos_do_oficio
    from viagens_ordens.presenters import artefatos_pdf_por_ordem
    from viagens_planos.services import avaliar_pendencias_documento
    from viagens_termos.presenters import artefatos_pdf_por_termo, documentos_do_termo

    itens = []
    oficios = [o for o in listar_oficios_da_viagem(viagem) if not o.cancelado]
    artefatos = artefatos_pdf_por_oficio(oficios)
    for oficio in oficios:
        for item in json.loads(documentos_do_oficio(oficio, artefatos.get(oficio.pk, {}))["itens_baixar"]):
            if item["valor"] == "oficio":
                item = {**item, "nome": f"Ofício {oficio.numero_formatado}", "detalhe": "Ofício"}
            else:
                item = {**item, "nome": f"{item['nome']} · Ofício {oficio.numero_formatado}"}
            itens.append({**item, "valor": f"oficio-{oficio.pk}:{item['valor']}"})

    for plano in viagem.planos_trabalho.filter(cancelado=False).order_by("criado_em"):
        if avaliar_pendencias_documento(plano):
            continue
        itens.append({"valor": f"pt-{plano.pk}", "nome": f"Plano de Trabalho {plano.numero_formatado}",
                      "detalhe": "Plano de trabalho", "estado": "", "assinado": False})

    ordens = list(viagem.ordens_servico.filter(cancelado=False).order_by("criado_em"))
    artefatos = artefatos_pdf_por_ordem(ordens)
    for ordem in ordens:
        estado, assinado = _estado(artefatos.get(ordem.pk))
        itens.append({"valor": f"os-{ordem.pk}", "nome": ordem.numero_formatado,
                      "detalhe": "Ordem de serviço", "estado": estado, "assinado": assinado})

    termos = [t for t in listar_termos_da_viagem(viagem) if not t.cancelado]
    artefatos = artefatos_pdf_por_termo(termos)
    for termo in termos:
        # O termo vazio fica de fora: aqui interessam os termos de quem viaja.
        for item in json.loads(documentos_do_termo(termo, artefatos.get(termo.pk, {}))["itens_baixar"])[1:]:
            itens.append({**item, "valor": f"termo-{termo.pk}:{item['valor']}", "nome": f"Termo · {item['nome']}"})

    for anexo in viagem.documentos_solicitacao.all().order_by("pk"):
        nome = anexo.nome_original or anexo.arquivo.name.split("/")[-1]
        itens.append({"valor": f"sol-{anexo.pk}", "nome": nome, "detalhe": "Documento de solicitação",
                      "estado": "PDF anexado", "assinado": False})
    return itens


def gerar_marcados(viagem, marcados, formato, *, usar_assinado=True):
    """Os documentos pedidos, na ordem do modal. Valor desconhecido: `KeyError`."""
    from viagens_oficios.document_generation import gerar_documento
    from viagens_ordens.services import gerar_ordem_servico
    from viagens_planos.services import gerar_plano_documento
    from viagens_termos.services import gerar_termo_cadastro_um, gerar_termo_um

    validos = [i["valor"] for i in itens_para_baixar(viagem)]
    pedidos = [v for v in validos if v in marcados]
    if set(marcados) - set(validos):
        raise KeyError("item fora da viagem")

    oficios = {o.pk: o for o in listar_oficios_da_viagem(viagem)}
    termos = {t.pk: t for t in listar_termos_da_viagem(viagem)}
    documentos = []
    for valor in pedidos:
        origem, _, parte = valor.partition(":")
        tipo, _, pk = origem.partition("-")
        pk = int(pk)
        if tipo == "oficio":
            oficio = oficios[pk]
            if parte in ("oficio", "justificativa"):
                doc_tipo = DocumentoTipo.OFICIO if parte == "oficio" else DocumentoTipo.JUSTIFICATIVA
                documentos.append(gerar_documento(oficio, formato, doc_tipo, usar_assinado=usar_assinado))
            else:
                servidor = oficio.servidores_termo_autorizacao.get(pk=int(parte.removeprefix("termo-")))
                documentos.append(gerar_termo_um(oficio, servidor, formato, usar_assinado=usar_assinado))
        elif tipo == "termo":
            termo = termos[pk]
            servidor = next(s for s in termo.servidores_efetivos() if str(s.pk) == parte)
            documentos.append(gerar_termo_cadastro_um(termo, servidor, formato, usar_assinado=usar_assinado))
        elif tipo == "pt":
            documentos.append(gerar_plano_documento(viagem.planos_trabalho.get(pk=pk), formato, usar_assinado=usar_assinado))
        elif tipo == "os":
            documentos.append(gerar_ordem_servico(viagem.ordens_servico.get(pk=pk), formato, usar_assinado=usar_assinado))
        elif tipo == "sol":
            # O anexo já é PDF: vai como está, em qualquer formato pedido.
            anexo = viagem.documentos_solicitacao.get(pk=pk)
            with anexo.arquivo.open("rb") as arquivo:
                conteudo = arquivo.read()
            nome = anexo.nome_original or anexo.arquivo.name.split("/")[-1]
            documentos.append(SimpleNamespace(conteudo=conteudo, nome_arquivo=nome, formato=DocumentoFormato.PDF, anexo=True))
    return documentos
