"""Como a solicitação de coffee break se apresenta na lista.

A listagem deixou de espalhar o pedido por dez colunas (nº, lote, evento,
data, quantidade, solicitada em, nota fiscal, situação, ações, abrir) em
favor da composição das listas de Viagens: uma célula só, com o evento no
título ao lado dos selos — a situação financeira e o quando do evento — e os
fatos com ícone logo abaixo.
"""

import json
from django.urls import reverse
from django.utils import timezone

from .models import SituacaoFinanceira



ITENS_BAIXAR = json.dumps([
    {"valor": "os", "nome": "Ordem de serviço", "detalhe": "Todas as OS do pagamento"},
    {"valor": "oficio", "nome": "Ofício", "detalhe": "O ofício ao GAF"},
    {"valor": "notas", "nome": "Notas fiscais e certificos", "detalhe": "Nota, certifico, nota, certifico…"},
    {"valor": "contratos", "nome": "Contrato, aditivos e certidões", "detalhe": "Todos os termos aditivos e as cinco certidões"},
], ensure_ascii=False)

def titulo_da_solicitacao(solicitacao):
    """O evento é o que identifica o pedido; o número vem colado nele."""
    numero = solicitacao.numero or f"#{solicitacao.pk}"
    evento = solicitacao.descricao_evento or "Evento sem descrição"
    return f"{numero} · {evento}"


def selo_temporal(solicitacao, hoje=None):
    """Quando o evento acontece — a mesma régua dos termos e dos roteiros."""
    inicio = solicitacao.data_inicio_evento
    if not inicio:
        return "", ""
    fim = solicitacao.data_fim_evento or inicio
    hoje = hoje or timezone.localdate()
    if fim < hoje:
        return "Realizado", "atendido"
    if inicio <= hoje:
        return "Acontecendo", "em_andamento"
    return "Previsto", "aguardando"


def fatos_da_solicitacao(solicitacao):
    """Os dados que estavam nas colunas, agora como itens com ícone."""
    periodo = solicitacao.periodo_evento_display
    lote = solicitacao.lote.rotulo_curto if solicitacao.lote_id else ""
    return [
        {
            "icone": "calendar",
            "rotulo": "Data do evento",
            "texto": periodo or "Sem data",
            "ausente": not periodo,
        },
        {
            "icone": "coffee",
            "rotulo": "Quantidade",
            "texto": f"{solicitacao.quantidade} unidade{'s' if solicitacao.quantidade != 1 else ''}",
            "ausente": False,
        },
        {
            "icone": "clipboard",
            "rotulo": "Lote",
            "texto": lote or "Sem lote",
            "ausente": not lote,
        },
        {
            "icone": "document",
            "rotulo": "Nota fiscal",
            "texto": solicitacao.numero_nota_fiscal or "Sem nota fiscal",
            "ausente": not solicitacao.numero_nota_fiscal,
        },
        {
            "icone": "clock",
            "rotulo": "Solicitada em",
            "texto": f"Solicitada em {solicitacao.data_solicitacao:%d/%m/%Y}",
            "ausente": False,
        },
    ]


def linha_da_lista(solicitacao, hoje=None):
    """Tudo o que a linha da lista precisa, montado fora do template."""
    quando, quando_tom = selo_temporal(solicitacao, hoje)
    # "Parada há N dias": só quando a consulta trouxe o último registro do
    # histórico (a lista anota; as demais telas não pagam a consulta).
    parada = ""
    if hasattr(solicitacao, "ultimo_historico"):
        from .services import selo_parada

        parada = selo_parada(solicitacao, hoje)
    return {
        "solicitacao": solicitacao,
        "titulo": titulo_da_solicitacao(solicitacao),
        "selo": solicitacao.situacao_financeira_display,
        "selo_tom": solicitacao.situacao_financeira_css,
        "quando": quando,
        "quando_tom": quando_tom,
        "parada": parada,
        "fatos": fatos_da_solicitacao(solicitacao),
        "url_editar": reverse("coffee_break:editar", args=[solicitacao.pk]),
        "url_andamento": reverse("coffee_break:andamento", args=[solicitacao.pk]),
        "url_certificado": reverse("coffee_break:certificado", args=[solicitacao.pk]),
        # O modal "Baixar documentos" de Viagens: os quatro arquivos do protocolo.
        "url_baixar": reverse("coffee_break:baixar_arquivos", args=[solicitacao.pk]),
        "itens_baixar": ITENS_BAIXAR,
        "cancelada": solicitacao.cancelada,
        # Quem já foi concluída ou cancelada só se abre para consulta.
        "editavel": not solicitacao.cancelada and not solicitacao.concluida,
    }


def linha_da_acao(item, chave, hoje=None):
    """A linha da fila "o que fazer hoje": a da lista, com o botão que resolve.

    Na entrega da semana vão o local, o horário e quem recebe (o que se
    confirma com o fornecedor); nos demais grupos, há quantos dias parada.
    """
    solicitacao = item["s"]
    linha = linha_da_lista(solicitacao, hoje)
    linha.update({"acao_url": item["url"], "acao_botao": item["botao"], "parada": ""})
    if chave == "entrega":
        horario = solicitacao.horario_evento
        linha["fatos"] = [
            {"icone": "calendar", "rotulo": "Data do evento", "texto": solicitacao.periodo_evento_display, "ausente": False},
            {
                "icone": "clock", "rotulo": "Horário",
                "texto": f"{horario:%H:%M}" if horario else "Sem horário", "ausente": not horario,
            },
            {"icone": "coffee", "rotulo": "Quantidade", "texto": f"{solicitacao.quantidade} pessoas", "ausente": False},
            {
                "icone": "map-pin", "rotulo": "Local de entrega",
                "texto": solicitacao.local_entrega or "Sem local de entrega", "ausente": not solicitacao.local_entrega,
            },
            {
                "icone": "user", "rotulo": "Responsável pelo recebimento",
                "texto": solicitacao.responsavel_recebimento or "Sem responsável",
                "ausente": not solicitacao.responsavel_recebimento,
            },
            {"icone": "landmark", "rotulo": "Fornecedor", "texto": solicitacao.lote.contrato.fornecedor.razao_social, "ausente": False},
        ]
    else:
        dias = item["dias"]
        linha["parada"] = "Parada hoje" if dias == 0 else f"Parada há {dias} dia{'s' if dias != 1 else ''}"
    return linha


def filas_de_situacao(itens):
    """As situações financeiras com contagem, para a trilha lateral.

    A situação é derivada (não está no banco): a contagem sai da própria
    lista já filtrada por banco, como o recorte da listagem faz.
    """
    contagens = {}
    for solicitacao in itens:
        chave = solicitacao.situacao_financeira
        contagens[chave] = contagens.get(chave, 0) + 1
    return [
        {"chave": valor, "rotulo": rotulo, "total": contagens.get(valor, 0)}
        for valor, rotulo in SituacaoFinanceira.choices
    ]


def selo_do_consumo(lote):
    """Quanto do lote já foi gasto, com o tom subindo junto com o aperto."""
    if not lote.quantidade_total:
        return "Sem capacidade", "neutro"
    pct = round(lote.consumido * 100 / lote.quantidade_total)
    if pct >= 90:
        return f"{pct}% consumido", "cancelada"
    if pct >= 70:
        return f"{pct}% consumido", "aguardando"
    return f"{pct}% consumido", "atendido"


def linha_do_lote(lote):
    """A linha da lista de lotes, na composição das listas de Viagens."""
    fornecedor = lote.contrato.fornecedor.razao_social
    consumo, consumo_tom = selo_do_consumo(lote)
    municipios = lote.municipios_texto
    return {
        "lote": lote,
        "titulo": f"Lote {lote.numero} · {fornecedor.upper()}",
        "selo": "Ativo" if lote.ativo else "Inativo",
        "selo_tom": "ativo" if lote.ativo else "inativo",
        "quando": consumo,
        "quando_tom": consumo_tom,
        "fatos": [
            {"icone": "calendar", "rotulo": "Exercício", "texto": f"Exercício {lote.exercicio}", "ausente": False},
            {"icone": "document", "rotulo": "Contrato", "texto": f"Contrato {lote.contrato.numero}", "ausente": False},
            {"icone": "coffee", "rotulo": "Saldo", "texto": f"{lote.restante} de {lote.quantidade_total} unidades", "ausente": False},
            {
                "icone": "map-pin",
                "rotulo": "Municípios",
                "texto": municipios or "Sem municípios",
                "ausente": not municipios,
            },
        ],
        "url_detalhe": reverse("coffee_break:lote_detalhe", args=[lote.pk]),
        "cancelada": not lote.ativo,
    }


def _vigencia(contrato):
    if not contrato.vigencia_fim:
        return "Vigência não informada"
    from django.utils import timezone

    prefixo = "Vencido em" if contrato.vigencia_fim < timezone.localdate() else "Vigente até"
    texto = f"{prefixo} {contrato.vigencia_fim:%d/%m/%Y}"
    return f"{texto} (estimada)" if contrato.vigencia_estimada else texto


def _selo_contrato(contrato, tom=False):
    from django.utils import timezone

    if not contrato.vigencia_fim:
        return ""
    vigente = contrato.vigencia_fim >= timezone.localdate()
    if tom:
        return "ativo" if vigente else "inativo"
    return "Vigente" if vigente else "Vencido"


def linha_do_cadastro(item, tipo):
    """A linha dos cadastros do módulo (fornecedor, contrato ou lote).

    Os três moram na mesma tela e mudam só o que dizem de si: por isso o
    título e os fatos saem daqui, e não de três templates diferentes.
    """
    if tipo == "fornecedores":
        titulo = item.razao_social
        fatos = [
            {"icone": "document", "rotulo": "CNPJ", "texto": item.cnpj_formatado or "Sem CNPJ", "ausente": not item.cnpj_formatado},
            {"icone": "user", "rotulo": "Contato", "texto": item.contato or "Sem contato", "ausente": not item.contato},
            {"icone": "mail", "rotulo": "E-mail", "texto": item.email or "Sem e-mail", "ausente": not item.email},
        ]
    elif tipo == "contratos":
        titulo = f"Contrato {item.numero}"
        fatos = [
            {"icone": "landmark", "rotulo": "Fornecedor", "texto": item.fornecedor.razao_social, "ausente": False},
            {"icone": "clipboard", "rotulo": "GMS", "texto": f"GMS {item.numero_gms}" if item.numero_gms else "Sem GMS", "ausente": not item.numero_gms},
            {"icone": "shield", "rotulo": "Fiscal", "texto": item.fiscal_responsavel or "Sem fiscal", "ausente": not item.fiscal_responsavel},
            {"icone": "clock", "rotulo": "Vigência", "texto": _vigencia(item), "ausente": not item.vigencia_fim},
        ]
        if item.termo_aditivo:
            fatos.insert(2, {"icone": "document", "rotulo": "Termo aditivo", "texto": f"Aditivo {item.termo_aditivo}", "ausente": False})
        if item.quantidade_contratada:
            fatos.append({"icone": "coffee", "rotulo": "Quantidade", "texto": f"{item.quantidade_contratada:,} unidades".replace(",", "."), "ausente": False})
    elif tipo == "oficio":
        titulo = "Ofício de pagamento e eProtocolo"
        fatos = [
            {"icone": "user", "rotulo": "Assina", "texto": f"{item.oficio_assinante} · {item.oficio_cargo_assinante}", "ausente": False},
            {"icone": "landmark", "rotulo": "Destinatário", "texto": " · ".join(item.oficio_destinatario.splitlines()[1:3]) or item.oficio_destinatario, "ausente": False},
            {"icone": "clipboard", "rotulo": "eProtocolo", "texto": f"{item.eprotocolo_assunto} · {item.eprotocolo_palavras_chave}", "ausente": False},
        ]
    else:
        titulo = item.rotulo_curto
        fatos = [
            {"icone": "document", "rotulo": "Contrato", "texto": str(item.contrato), "ausente": False},
            {"icone": "coffee", "rotulo": "Saldo", "texto": f"{item.restante} de {item.quantidade_total} unidades", "ausente": False},
            {"icone": "chart", "rotulo": "Consumido", "texto": f"{item.consumido} consumidas", "ausente": False},
        ]
    return {
        "item": item,
        "titulo": titulo,
        # Só o lote tem vigência (é ela que decide quem recebe pelo município).
        "selo": ("Vigente" if item.ativo else "Encerrado") if tipo == "lotes" else _selo_contrato(item) if tipo == "contratos" else "",
        "selo_tom": ("ativo" if item.ativo else "inativo") if tipo == "lotes" else _selo_contrato(item, tom=True) if tipo == "contratos" else "",
        "fatos": fatos,
        "url_editar": reverse("coffee_break:cadastro_editar", args=[tipo, item.pk]),
        "url_excluir": reverse("coffee_break:cadastro_excluir", args=[tipo, item.pk]),
        "cancelada": tipo == "lotes" and not item.ativo,
        "excluivel": tipo != "oficio",
    }
