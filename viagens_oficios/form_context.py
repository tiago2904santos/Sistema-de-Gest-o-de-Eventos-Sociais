"""Contexto do cadastro de ofício, no desenho do Gerenciador de Viagens.

A origem é um assistente de quatro etapas (dados e viajantes, roteiro e
diárias, justificativa, documentos). Aqui as quatro são partes de uma página
só, com os mesmos blocos, campos e rótulos: o que muda é a pele e o fato de
haver um único "Salvar". Nada aqui é renderizado por laço genérico.
"""

from django.urls import reverse

from documentos.services.types import DocumentoTipo

from .models import Oficio
from .picker import pks_ja_escolhidos
from .presenters import iniciais


def _valor(form, nome):
    valor = form[nome].value()
    if valor is None:
        return ""
    return str(getattr(valor, "pk", valor))


def _descricao_servidor(servidor):
    partes = []
    if servidor.cargo_id:
        partes.append(str(servidor.cargo))
    if servidor.unidade_id:
        partes.append(servidor.unidade.sigla or servidor.unidade.nome)
    return " • ".join(partes)


def _servidores(form):
    """Todos os servidores, com o que a equipe e o motorista precisam na tela."""
    equipe = pks_ja_escolhidos(form, "servidores")
    com_termo = set(pks_ja_escolhidos(form, "servidores_termo_autorizacao"))
    opcoes = []
    for servidor in form.fields["servidores"].queryset.select_related("cargo", "unidade").order_by("nome"):
        valor = str(servidor.pk)
        opcoes.append({
            "valor": valor,
            "rotulo": servidor.nome,
            "iniciais": iniciais(servidor.nome),
            "detalhes": _descricao_servidor(servidor),
            "busca": " ".join(p for p in [servidor.cpf or "", servidor.rg or ""] if p),
            "unidade": str(servidor.unidade_id or ""),
            "selecionado": valor in equipe,
            "termo": valor in com_termo,
        })
    # A equipe aparece na ordem em que foi montada.
    ordem = {valor: indice for indice, valor in enumerate(equipe)}
    escolhidos = sorted((o for o in opcoes if o["selecionado"]), key=lambda o: ordem[o["valor"]])
    return opcoes, escolhidos


def _opcoes_servidores(form):
    """Servidores com cargo e unidade, no formato dos componentes globais —
    as opções do campo de equipe do editor documental."""
    return [
        {"valor": str(s.pk), "rotulo": s.nome, "iniciais": iniciais(s.nome),
         "detalhes": _descricao_servidor(s).replace(" • ", " · ")}
        for s in form.fields["servidores"].queryset.select_related("cargo", "unidade")
    ]


def _viaturas(form):
    """"AAA-1234 - DUSTER", com combustível, tipo e unidade embaixo."""
    opcoes = []
    for viatura in form.fields["viatura"].queryset.select_related("combustivel", "unidade").order_by("placa"):
        detalhes = [
            str(viatura.combustivel) if viatura.combustivel_id else "",
            viatura.get_tipo_display() if viatura.tipo else "",
            (viatura.unidade.sigla or viatura.unidade.nome) if viatura.unidade_id else "",
        ]
        opcoes.append({
            "valor": str(viatura.pk),
            "rotulo": " - ".join(p for p in [viatura.placa_formatada, viatura.modelo] if p),
            "detalhes": " - ".join(p for p in detalhes if p),
            "busca": viatura.placa,
            # Para as sugestões pela unidade da equipe, no navegador.
            "dados": {
                "unidade": str(viatura.unidade_id or ""),
                "sigla": (viatura.unidade.sigla or viatura.unidade.nome) if viatura.unidade_id else "",
            },
        })
    return opcoes


def _choices(form, campo):
    return [{"valor": str(chave), "rotulo": str(rotulo)} for chave, rotulo in form.fields[campo].choices if chave != ""]


def contexto_dados_viajantes(form, oficio):
    """Etapa 1 da origem: identificação, finalidade, equipe, viatura e motorista."""
    servidores, equipe = _servidores(form)
    equipe_ids = {s["valor"] for s in equipe}
    motorista = _valor(form, "motorista")
    modo = _valor(form, "motorista_modo") or Oficio.MOTORISTA_MODO_SERVIDOR
    motorista_na_equipe = modo != Oficio.MOTORISTA_MODO_MANUAL and motorista in equipe_ids
    viatura = _valor(form, "viatura")
    ano = oficio.ano or form.ano
    return {
        "valores": {nome: _valor(form, nome) for nome in form.fields},
        "erros": {nome: form.errors.get(nome) for nome in form.fields},
        "ano": ano,
        "opcoes_custeio": _choices(form, "custeio"),
        "outra_instituicao": Oficio.CUSTEIO_OUTRA_INSTITUICAO,
        "mostrar_instituicao": _valor(form, "custeio") == Oficio.CUSTEIO_OUTRA_INSTITUICAO,
        "opcoes_motivos": [{"valor": str(m.pk), "rotulo": m.nome} for m in form.fields["modelo_motivo"].queryset],
        "servidores": servidores,
        "equipe": equipe,
        # O motorista do sistema é a lista de escolha, com a unidade para as sugestões de viatura.
        "motoristas": [
            {"valor": o["valor"], "rotulo": o["rotulo"], "detalhes": o["detalhes"], "busca": o["busca"],
             "dados": {"unidade": o["unidade"]}}
            for o in servidores
        ],
        "motorista_equipe": motorista if motorista_na_equipe else "",
        "viaturas": _viaturas(form),
        "motorista_modo": modo,
        # O cartão do motorista aparece com viatura escolhida e ninguém da equipe ao volante.
        "mostrar_motorista": bool(viatura) and not motorista_na_equipe,
        "url_modelos_motivo": reverse("viagens_cadastros:lista", args=["motivos-oficio"]),
        "url_novo_servidor": reverse("viagens_cadastros:novo", args=["servidores"]),
        "url_nova_viatura": reverse("viagens_cadastros:novo", args=["viaturas"]),
    }


def contexto_justificativa(jform):
    return {
        "modelo": _valor(jform, "modelo"),
        "texto": _valor(jform, "texto"),
        "erros_modelo": jform.errors.get("modelo"),
        "erros_texto": jform.errors.get("texto"),
        "opcoes_modelo": [{"valor": str(m.pk), "rotulo": m.nome} for m in jform.fields["modelo"].queryset],
        "url_modelos": reverse("viagens_cadastros:lista", args=["modelos-justificativa"]),
    }


def contexto_conferencia(oficio, artefatos_pdf):
    """Etapa 4 da origem: os documentos para conferência."""
    from .services import validar_oficio_para_documento

    pendencias = list(validar_oficio_para_documento(oficio)["pendencias"])
    completo = not pendencias and not oficio.cancelado
    mensagem = "" if completo else "Complete o ofício para gerar e consultar os documentos."

    def documento(tipo, titulo, rota_tipo, servidor=None):
        chave = (tipo.value, servidor.pk if servidor else None)
        artefato = artefatos_pdf.get(chave)
        base = {
            "titulo": titulo,
            "disponivel": completo,
            "mensagem": mensagem,
            "assinado": bool(artefato and artefato["assinado"]),
            "url_anexar": reverse("viagens_oficios:assinatura_artefato", args=[artefato["pk"]]) if artefato else "",
        }
        if servidor is None:
            base.update(
                src=reverse("viagens_oficios:visualizar", args=[oficio.pk, rota_tipo]),
                url_pdf=reverse("viagens_oficios:gerar", args=[oficio.pk, rota_tipo, "pdf"]),
                url_docx=reverse("viagens_oficios:gerar", args=[oficio.pk, rota_tipo, "docx"]),
            )
        else:
            base.update(
                src=reverse("viagens_oficios:visualizar_termo", args=[oficio.pk, servidor.pk]),
                url_pdf=reverse("viagens_oficios:termo", args=[oficio.pk, servidor.pk, "pdf"]),
                url_docx=reverse("viagens_oficios:termo", args=[oficio.pk, servidor.pk, "docx"]),
                servidor=servidor.nome,
            )
        return base

    termos = [
        documento(DocumentoTipo.TERMO_AUTORIZACAO, f"Termo de Autorização — {s.nome}", "termo", servidor=s)
        for s in oficio.servidores_termo_autorizacao.select_related("cargo", "unidade").order_by("nome")
    ]

    return {
        "pendencias": pendencias,
        "completo": completo,
        "oficio": documento(DocumentoTipo.OFICIO, "Documento original (Ofício)", "oficio"),
        "justificativa": documento(DocumentoTipo.JUSTIFICATIVA, "Justificativa", "justificativa"),
        "termos": termos,
        "url_termos_pdf": reverse("viagens_oficios:termos_todos_pdf", args=[oficio.pk]),
        "url_termos_docx": reverse("viagens_oficios:termos_lote", args=[oficio.pk, "docx"]),
    }
