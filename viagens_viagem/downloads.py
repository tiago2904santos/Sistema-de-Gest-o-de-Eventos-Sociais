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
    from documentos.services.assinados import versao_assinada_vigente
    from viagens_planos.services import avaliar_pendencias_documento, referencia_do_plano
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
        assinado = versao_assinada_vigente(
            DocumentoTipo.PLANO_TRABALHO, plano_trabalho_id=plano.pk, reference=referencia_do_plano(plano)) is not None
        itens.append({"valor": f"pt-{plano.pk}", "nome": f"Plano de Trabalho {plano.numero_formatado}",
                      "detalhe": "Plano de trabalho", "estado": "Assinado" if assinado else "", "assinado": assinado})

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
    validos = [i["valor"] for i in itens_para_baixar(viagem)]
    pedidos = [v for v in validos if v in marcados]
    if set(marcados) - set(validos):
        raise KeyError("item fora da viagem")
    gerar = _gerador(viagem, formato, usar_assinado)
    return [gerar(valor) for valor in pedidos]


def _gerador(viagem, formato, usar_assinado):
    """Função que gera um item (pelo valor do modal) com o gerador do módulo dele."""
    from viagens_oficios.document_generation import gerar_documento
    from viagens_ordens.services import gerar_ordem_servico
    from viagens_planos.services import gerar_plano_documento
    from viagens_termos.services import gerar_termo_cadastro_um, gerar_termo_um

    oficios = {o.pk: o for o in listar_oficios_da_viagem(viagem)}
    termos = {t.pk: t for t in listar_termos_da_viagem(viagem)}

    def gerar(valor):
        origem, _, parte = valor.partition(":")
        tipo, _, pk = origem.partition("-")
        pk = int(pk)
        if tipo == "oficio":
            oficio = oficios[pk]
            if parte in ("oficio", "justificativa"):
                doc_tipo = DocumentoTipo.OFICIO if parte == "oficio" else DocumentoTipo.JUSTIFICATIVA
                return gerar_documento(oficio, formato, doc_tipo, usar_assinado=usar_assinado)
            servidor = oficio.servidores_termo_autorizacao.get(pk=int(parte.removeprefix("termo-")))
            return gerar_termo_um(oficio, servidor, formato, usar_assinado=usar_assinado)
        if tipo == "termo":
            termo = termos[pk]
            servidor = next(s for s in termo.servidores_efetivos() if str(s.pk) == parte)
            return gerar_termo_cadastro_um(termo, servidor, formato, usar_assinado=usar_assinado)
        if tipo == "pt":
            return gerar_plano_documento(viagem.planos_trabalho.get(pk=pk), formato, usar_assinado=usar_assinado)
        if tipo == "os":
            return gerar_ordem_servico(viagem.ordens_servico.get(pk=pk), formato, usar_assinado=usar_assinado)
        if tipo == "sol":
            # O anexo já é PDF: vai como está, em qualquer formato pedido.
            anexo = viagem.documentos_solicitacao.get(pk=pk)
            with anexo.arquivo.open("rb") as arquivo:
                conteudo = arquivo.read()
            nome = anexo.nome_original or anexo.arquivo.name.split("/")[-1]
            return SimpleNamespace(conteudo=conteudo, nome_arquivo=nome, formato=DocumentoFormato.PDF, anexo=True)
        raise KeyError(valor)

    return gerar


def _nome_seguro(texto):
    """Nome de arquivo sem barra (o "12/2026" do número viraria pasta no ZIP)."""
    return " ".join(str(texto).replace("/", "-").replace("\\", "-").split())


def pacote_do_processo(viagem, *, usar_assinado=True):
    """O "Baixar tudo" (m065): cada documento da viagem num arquivo, num ZIP.

    Não é um PDF único de propósito: cada documento é assinado no eProtocolo,
    às vezes por pessoas diferentes, e precisa subir separado. Os arquivos
    saem numerados na ordem do modal (ofício com justificativa e termos, PT,
    OS, termos, documentos de solicitação), sempre em PDF e na versão
    assinada quando há. O que não pôde ser gerado (documento incompleto) e o
    que ainda não está assinado vão listados no "00 - LEIA-ME.txt".

    Devolve (bytes do ZIP, quantos documentos entraram).
    """
    import io
    from zipfile import ZIP_DEFLATED, ZipFile

    from django.core.exceptions import ValidationError

    from documentos.services.exceptions import DocumentError

    itens = itens_para_baixar(viagem)
    gerar = _gerador(viagem, DocumentoFormato.PDF, usar_assinado)
    arquivos, falhas, sem_assinatura = [], [], []
    for item in itens:
        rotulo = item["nome"] if item["detalhe"] in item["nome"] else f"{item['detalhe']} · {item['nome']}"
        try:
            doc = gerar(item["valor"])
        except (ValidationError, DocumentError) as exc:
            motivo = "; ".join(exc.messages) if isinstance(exc, ValidationError) else str(exc)
            falhas.append(f"- {rotulo}: {motivo}")
            continue
        arquivos.append((rotulo, doc))
        if not item.get("assinado") and not getattr(doc, "anexo", False):
            sem_assinatura.append(f"- {rotulo}")

    largura = max(2, len(str(len(arquivos))))
    nomeados = []
    for n, (rotulo, doc) in enumerate(arquivos, 1):
        extensao = doc.nome_arquivo.rpartition(".")[2].lower() if "." in doc.nome_arquivo else "pdf"
        base = _nome_seguro(rotulo)
        if base.lower().endswith(f".{extensao}"):
            base = base[: -len(extensao) - 1]
        nomeados.append((f"{n:0{largura}d} - {base[:120]}.{extensao}", doc))
    linhas = [f"Viagem: {viagem}", f"Período: {viagem.periodo_display}", f"Destino: {viagem.destino_display}", "",
              "Cada documento está num arquivo, na ordem do processo, para subir e assinar no eProtocolo.", ""]
    linhas += [nome for nome, _ in nomeados]
    if sem_assinatura:
        linhas += ["", "Ainda sem a versão assinada anexada no sistema:", *sem_assinatura]
    if falhas:
        linhas += ["", "Não entraram (complete o documento e baixe de novo):", *falhas]
    buffer = io.BytesIO()
    with ZipFile(buffer, "w", ZIP_DEFLATED) as zipfile:
        zipfile.writestr("00 - LEIA-ME.txt", "\r\n".join(linhas).encode("utf-8"))
        for nome, doc in nomeados:
            zipfile.writestr(nome, doc.conteudo)
    return buffer.getvalue(), len(arquivos)
