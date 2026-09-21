"""O paradeiro completo de um compromisso, montado no servidor.

Quando alguém clica num compromisso da agenda, quer o dossiê inteiro sem sair
de onde está: os dados, quem vai (com cargo, unidade, documentos), cada
documento gerado com o PDF para abrir, a prestação de contas, o histórico. Este
módulo junta tudo isso a partir dos modelos de cada área e devolve um
dicionário que o template ``_detalhe.html`` desenha dentro do modal.

Montar no servidor, e não no navegador, é o que mantém a regra de acesso num
lugar só: cada construtor confere a permissão do módulo de origem antes de
tocar em qualquer coisa, e o que a pessoa não pode ver nem é serializado.
Um JSON generoso "para o front filtrar" seria uma brecha esperando acontecer.

Tudo aqui é leitura. Editar continua sendo na tela do módulo, que é para onde
o botão "Abrir no sistema" leva.
"""

from __future__ import annotations

from django.core.exceptions import PermissionDenied
from django.http import Http404
from django.urls import reverse

LIMITE_HISTORICO = 40


# ---------------------------------------------------------------------------
# Peças reaproveitadas pelos construtores
# ---------------------------------------------------------------------------


def _pessoa(servidor, *, motorista=False) -> dict:
    """Um servidor com tudo o que o dossiê mostra dele."""
    rg = (servidor.rg or "").strip()
    return {
        "pk": servidor.pk,
        "nome": servidor.nome,
        "cargo": str(servidor.cargo) if servidor.cargo_id else "",
        "unidade": str(servidor.unidade) if servidor.unidade_id else "",
        "cpf": servidor.cpf_formatado if servidor.cpf else "",
        "rg": "" if not rg or rg.upper().startswith("NAO") else rg,
        "telefone": servidor.telefone_formatado if hasattr(servidor, "telefone_formatado") and servidor.telefone else (servidor.telefone or ""),
        "motorista": motorista,
        "documentos": [],
        "oficios": [],
    }


def _fatos_da_pessoa(p: dict) -> list[dict]:
    """A linha de fatos do servidor, no mesmo formato das listagens."""
    return _campos([
        ("Cargo", p["cargo"]),
        ("Unidade", p["unidade"]),
        ("CPF", p["cpf"]),
        ("RG", p["rg"]),
        ("Contato", p["telefone"]),
        ("Documentos", ", ".join(p["oficios"])),
    ])


ROTULOS_DE_TIPO = {
    "oficio": "Ofício",
    "justificativa": "Justificativa",
    "termo_autorizacao": "Termo de autorização",
    "plano_trabalho": "Plano de trabalho",
    "ordem_servico": "Ordem de serviço",
    "relatorio_tecnico": "Relatório técnico",
    "diario_bordo": "Diário de bordo",
}

# Ícone por rótulo de campo — os mesmos das listagens do sistema, para o
# dossiê não inventar um vocabulário visual próprio.
ICONES = {
    "destino": "map-pin", "município": "map-pin", "local": "map-pin",
    "destinos": "map-pin", "sai de": "map-pin", "região": "map-pin",
    "período": "calendar", "evento": "calendar", "data da solicitação": "calendar",
    "criada em": "calendar", "atesto gaf": "calendar", "ordem bancária": "calendar",
    "envio à empresa": "calendar",
    "saída": "clock", "retorno": "clock", "horário": "clock",
    "servidores": "users", "equipe": "users", "servidores previstos": "users",
    "público previsto": "users", "quantidade": "users",
    "motorista": "volante", "viatura": "truck", "transporte": "truck",
    "diárias": "chart", "resumo das diárias": "chart", "custeio": "chart",
    "unidade": "landmark", "unidade responsável": "landmark",
    "órgão responsável": "landmark", "setores": "landmark",
    "solicitante": "user", "responsável": "user", "criada por": "user",
    "decidido por": "user", "responsável pelo atendimento": "user",
    "responsável pela organização": "user", "fiscal responsável": "user",
    "decisão da dg": "gavel", "observação da dg": "gavel",
    "contato": "mail", "e-mail": "mail", "assunto do e-mail": "mail",
    "protocolo": "clipboard", "número": "clipboard", "nota fiscal": "clipboard",
    "protocolo de pagamento": "clipboard", "empenho": "clipboard",
    "contrato": "clipboard", "gms": "clipboard", "lote": "clipboard",
    "cancelada": "ban", "cancelado": "ban",
    "tipo de evento": "activity", "tema": "activity", "programa": "activity",
    "subtema / escopo": "activity", "canal": "activity", "necessidade": "activity",
    "tipo de operação": "activity",
    "cargo": "shield", "cpf": "user", "rg": "user", "documentos": "document",
    "anexos": "document", "motivo": "document", "descrição": "document",
    "assunto": "document", "observações": "document", "briefing": "document",
    "pedido": "document", "andamento": "activity", "matéria no site": "mail",
    "informações prévias": "info", "descrição complementar": "document",
    "distância calculada": "map-pin", "cin previstas": "clipboard",
    "unidade móvel": "truck", "unidade móvel designada": "truck",
    "fornecedor": "landmark", "cnpj": "clipboard",
    "contato do fornecedor": "mail", "termo aditivo": "clipboard",
    "quantidade contratada": "chart", "municípios": "map-pin",
    "servidor": "user", "por extenso": "chart",
}


def _icone(rotulo: str) -> str:
    return ICONES.get((rotulo or "").strip().lower(), "info")


def _nome_legivel(artefato) -> str:
    """O nome do documento para gente ler, não o nome do arquivo em disco."""
    base = ROTULOS_DE_TIPO.get(artefato.tipo) or artefato.tipo.replace("_", " ").capitalize()
    if artefato.servidor_id:
        return f"{base} — {artefato.servidor.nome}"
    return base


def _artefatos(consulta) -> list[dict]:
    """Os PDFs já gerados de um documento, com o link para baixar cada um.

    Só PDF: o DOCX é intermediário de edição, e quem abre a agenda quer ver o
    documento, não editá-lo. "Assinado" vale quando há arquivo assinado
    anexado — é o que diferencia o documento pronto do documento gerado.
    """
    saida = []
    for a in consulta.filter(formato="pdf").select_related("servidor").order_by("criado_em"):
        saida.append(
            {
                # "Termo de autorização" em vez de
                # "termo_autorizacao_termo-3-cadastro-..._20260918-161403.pdf":
                # o nome do arquivo é do sistema, não de quem lê.
                "nome": _nome_legivel(a),
                "arquivo": (a.arquivo_efetivo.name or "").rsplit("/", 1)[-1] if a.arquivo_efetivo else "",
                "tipo": a.tipo,
                "servidor": a.servidor.nome if a.servidor_id else "",
                "assinado": bool(a.arquivo_assinado),
                "criado_em": a.criado_em,
                # Abrir mostra no navegador; baixar guarda o arquivo. Quem
                # confere um documento quer o primeiro.
                "url": reverse("documentos:abrir", args=[a.pk]),
                "url_baixar": reverse("documentos:baixar", args=[a.pk]),
            }
        )
    return saida


def _historico(consulta) -> list[dict]:
    """Linha do tempo genérica: os módulos guardam histórico com nomes parecidos."""
    saida = []
    for h in consulta.order_by("-criado_em")[:LIMITE_HISTORICO]:
        acao = h.get_acao_display() if hasattr(h, "get_acao_display") else getattr(h, "acao", "")
        de, para = getattr(h, "status_anterior", ""), getattr(h, "status_novo", "")
        saida.append(
            {
                "quando": h.criado_em,
                "acao": acao,
                "quem": str(h.usuario) if getattr(h, "usuario_id", None) else "",
                "transicao": f"{de} → {para}" if de and para and de != para else "",
                "texto": getattr(h, "observacao", "") or getattr(h, "descricao", "") or "",
            }
        )
    return saida


def _campos(pares) -> list[dict]:
    """Só o que tem valor, já com o ícone do rótulo.

    Linha em branco no dossiê é ruído; e o ícone é o que faz a lista parecer
    com as células das listagens do sistema em vez de uma tabela de banco.
    """
    return [
        {"icone": _icone(rotulo), "rotulo": rotulo, "texto": str(valor),
         "longo": len(str(valor)) > 120}
        for rotulo, valor in pares
        if valor not in (None, "", 0, "0")
    ]


TONS = {
    # Situações que o sistema já trata como encerradas ou de atenção; o resto
    # fica neutro. Reusa os tons do design system (.st--*) para o selo do
    # dossiê ser o mesmo selo das listagens.
    "rascunho": "rascunho", "em_preparacao": "rascunho", "RASCUNHO": "rascunho",
    "deferida_em_andamento": "atendido", "atendida": "atendido",
    "finalizado": "atendido", "em_execucao": "atendido", "ativa": "atendido",
    "aguardando_despacho": "pendente", "devolvida": "pendente",
    "pendente": "pendente", "em_andamento": "pendente",
    "aguardando_retorno": "pendente", "evento_agendado": "pendente",
}


def _tom(slug: str, encerrado: bool) -> str:
    if encerrado:
        return "neutro"
    return TONS.get((slug or "").lower(), "neutro")


def _base(*, fonte, rotulo, titulo, subtitulo, situacao, situacao_slug, encerrado, url_abrir) -> dict:
    return {
        "fonte": fonte,
        "fonte_rotulo": rotulo,
        "titulo": titulo,
        "subtitulo": subtitulo,
        "situacao": situacao,
        "situacao_slug": (situacao_slug or "").lower(),
        "selo_tom": _tom(situacao_slug, encerrado),
        "encerrado": encerrado,
        "url_abrir": url_abrir,
        "campos": [],
        "secoes": [],  # blocos extras do Resumo: {"titulo", "campos"} ou {"titulo", "linhas"}
        "pessoas": [],
        "pessoas_rotulo": "Servidores",
        "documentos": [],  # grupos: {"titulo", "itens": [{"titulo","situacao","url","artefatos","fatos","extras"}]}
        "historico": [],
        "origem": None,  # {"rotulo", "url"} — de onde este compromisso veio
    }


def _periodo(inicio, fim) -> str:
    if not inicio:
        return ""
    if not fim or fim == inicio:
        return inicio.strftime("%d/%m/%Y")
    return f"{inicio:%d/%m/%Y} a {fim:%d/%m/%Y}"


# ---------------------------------------------------------------------------
# Viagem — o dossiê mais fundo, porque é onde os documentos moram
# ---------------------------------------------------------------------------


def _viagem(usuario, pk) -> dict:
    from viagens_cadastros.permissions import pode_acessar
    from viagens_viagem.models import Viagem

    if not pode_acessar(usuario):
        raise PermissionDenied

    v = (
        Viagem.objects.select_related(
            "destino_municipio__estado", "destino_estado", "unidade_responsavel", "responsavel"
        )
        .filter(pk=pk)
        .first()
    )
    if v is None:
        raise Http404

    d = _base(
        fonte="viagem",
        rotulo="Viagem",
        titulo=v.destino_display,
        subtitulo=v.periodo_display,
        situacao=v.get_status_display(),
        situacao_slug=v.status,
        encerrado=bool(v.cancelado),
        url_abrir=reverse("viagens_viagem:painel", args=[v.pk]),
    )
    d["campos"] = _campos([
        ("Motivo", (v.motivo or "").strip()),
        ("Descrição", (v.descricao or "").strip()),
        ("Unidade responsável", str(v.unidade_responsavel) if v.unidade_responsavel_id else ""),
        ("Responsável", str(v.responsavel) if v.responsavel_id else ""),
        ("Horário", f"{v.horario_inicio:%H:%M} às {v.horario_fim:%H:%M}" if v.horario_inicio and v.horario_fim else ""),
        ("Cancelada", v.motivo_cancelamento if v.cancelado else ""),
        ("Criada em", v.criado_em.strftime("%d/%m/%Y %H:%M") if v.criado_em else ""),
    ])

    # Roteiro: de onde sai, por onde passa, quanto custa em diária.
    roteiro = v.roteiros.filter(cancelado=False).select_related("origem_municipio__estado", "solicitacao").order_by("id").first()
    if roteiro is not None:
        destinos = " → ".join(str(x.municipio) for x in roteiro.destinos.select_related("municipio__estado").order_by("ordem"))
        trechos = [
            f"{t.origem_municipio} → {t.destino_municipio}" + (f" ({t.distancia_km} km)" if t.distancia_km else "")
            for t in roteiro.trechos.select_related("origem_municipio__estado", "destino_municipio__estado").order_by("ordem")
        ]
        d["secoes"].append({
            "titulo": "Roteiro",
            "campos": _campos([
                ("Sai de", str(roteiro.origem_municipio) if roteiro.origem_municipio_id else ""),
                ("Saída", roteiro.saida_dt.strftime("%d/%m/%Y %H:%M") if roteiro.saida_dt else ""),
                ("Retorno", roteiro.retorno_chegada_dt.strftime("%d/%m/%Y %H:%M") if roteiro.retorno_chegada_dt else ""),
                ("Destinos", destinos),
                ("Servidores previstos", str(roteiro.quantidade_servidores or "")),
                ("Diárias", f"R$ {roteiro.valor_diarias}" if roteiro.valor_diarias else ""),
                ("Resumo das diárias", roteiro.resumo_diarias or ""),
                ("Distância calculada", f"{roteiro.rota_distancia_km} km" if roteiro.rota_distancia_km else ""),
                ("Observações", (roteiro.observacoes or "").strip()),
            ]),
            "linhas": trechos,
        })
        if roteiro.solicitacao_id:
            d["origem"] = {
                "rotulo": f"Solicitação de Evento #{roteiro.solicitacao_id}",
                "url": reverse("solicitacoes:editar", args=[roteiro.solicitacao_id]),
            }

    # Pessoas: a união das equipes dos ofícios, com motorista marcado e o
    # termo de cada um listado junto — é o que "quem vai" significa aqui.
    oficios = list(
        v.oficios.filter(cancelado=False)
        .select_related("roteiro", "viatura", "motorista__cargo", "motorista__unidade", "prestacao_contas")
        .prefetch_related("servidores__cargo", "servidores__unidade", "servidores_termo_autorizacao")
        .order_by("id")
    )
    pessoas: dict[int, dict] = {}
    for o in oficios:
        rotulo = f"Ofício {o.numero_formatado}" if o.numero else f"Ofício #{o.pk}"
        for s in o.servidores.all():
            pessoas.setdefault(s.pk, _pessoa(s))["oficios"].append(rotulo)
        if o.motorista_id:
            p = pessoas.setdefault(o.motorista_id, _pessoa(o.motorista))
            p["motorista"] = True
            if rotulo not in p["oficios"]:
                p["oficios"].append(rotulo)
        for a in _artefatos(o.artefatos.filter(servidor__isnull=False)):
            alvo = next((p for p in pessoas.values() if p["nome"] == a["servidor"]), None)
            if alvo is not None:
                alvo["documentos"].append(a)
    # Termos e ordens também nomeiam gente — e às vezes são o único lugar
    # onde a equipe está (ofício ainda sem servidores, termo já emitido).
    for t in v.termos_autorizacao.filter(cancelado=False).prefetch_related("servidores__cargo", "servidores__unidade"):
        for s in t.servidores.all():
            pessoas.setdefault(s.pk, _pessoa(s))["oficios"].append(f"Termo #{t.pk}")
    for o in v.ordens_servico.filter(cancelado=False).prefetch_related("servidores__cargo", "servidores__unidade"):
        for s in o.servidores.all():
            pessoas.setdefault(s.pk, _pessoa(s))["oficios"].append(f"Ordem {o.numero_formatado}")
    d["pessoas"] = sorted(pessoas.values(), key=lambda p: (not p["motorista"], p["nome"]))
    for p in d["pessoas"]:
        p["fatos"] = _fatos_da_pessoa(p)

    # Documentos: um grupo por tipo, cada item com seus PDFs.
    itens_oficio = []
    for o in oficios:
        prestacao = getattr(o, "prestacao_contas", None)
        extras = []
        if prestacao is not None:
            por_servidor = list(prestacao.servidores_prestacao.select_related("servidor"))
            resumo = ", ".join(
                f"{ps.servidor.nome.split()[0]}: {'finalizada' if ps.finalizada else ps.get_status_display()}"
                for ps in por_servidor
            )
            extras.append({
                "rotulo": "Prestação de contas",
                "texto": resumo or "aberta, sem servidores",
                "url": reverse("viagens_prestacoes:abrir_oficio", args=[o.pk]),
                "n": prestacao.documentos_anexos.count(),
            })
        itens_oficio.append({
            "titulo": f"Ofício {o.numero_formatado}" if o.numero else f"Ofício #{o.pk} (sem número)",
            "situacao": o.status,
            "url": reverse("viagens_oficios:editar", args=[o.pk]),
            "fatos": _campos([
                ("Assunto", o.assunto),
                ("Equipe", ", ".join(s.nome for s in o.servidores.all())),
                ("Motorista", o.motorista.nome if o.motorista_id else o.motorista_manual_nome),
                ("Viatura", o.viatura.placa_formatada if o.viatura_id else o.transporte_placa_manual),
                ("Custeio", o.get_custeio_display() if o.custeio else ""),
                ("Protocolo", o.protocolo),
            ]),
            "artefatos": _artefatos(o.artefatos.filter(servidor__isnull=True)),
            "extras": extras,
        })
    if itens_oficio:
        d["documentos"].append({"titulo": "Ofícios", "itens": itens_oficio})

    itens = []
    for t in v.termos_autorizacao.filter(cancelado=False).prefetch_related("servidores").order_by("id"):
        itens.append({
            "titulo": f"Termo de autorização #{t.pk}",
            "situacao": "",
            "url": reverse("viagens_termos:editar", args=[t.pk]),
            "fatos": _campos([
                ("Servidores", ", ".join(s.nome for s in t.servidores.all())),
                ("Período", _periodo(t.data_evento_inicio, t.data_evento_fim)),
                ("Viatura", str(t.viatura) if t.viatura_id else ""),
            ]),
            "artefatos": _artefatos(t.artefatos),
            "extras": [{"rotulo": "Todos em PDF", "texto": "", "url": reverse("viagens_termos:todos_pdf", args=[t.pk]), "n": 0}],
        })
    if itens:
        d["documentos"].append({"titulo": "Termos de autorização", "itens": itens})

    itens = []
    for p in v.planos_trabalho.filter(cancelado=False).order_by("id"):
        itens.append({
            "titulo": f"Plano de trabalho {p.numero_formatado}",
            "situacao": p.get_status_display(),
            "url": reverse("viagens_planos:editar", args=[p.pk]),
            "fatos": _campos([
                ("Programa", str(p.programa) if p.programa_id else p.programa_outros),
                ("Destino", str(p.destino_cidade) if p.destino_cidade_id else ""),
                ("Período", _periodo(p.data_evento_inicio, p.data_evento_fim)),
                ("Diárias", f"R$ {p.diarias_valor_total}" if p.diarias_valor_total else ""),
            ]),
            "artefatos": _artefatos(p.artefatos),
            "extras": [{"rotulo": "Visualizar", "texto": "", "url": reverse("viagens_planos:visualizar", args=[p.pk]), "n": 0}],
        })
    if itens:
        d["documentos"].append({"titulo": "Planos de trabalho", "itens": itens})

    itens = []
    for o in v.ordens_servico.filter(cancelado=False).prefetch_related("servidores").order_by("id"):
        itens.append({
            "titulo": f"Ordem de serviço {o.numero_formatado}",
            "situacao": "",
            "url": reverse("viagens_ordens:editar", args=[o.pk]),
            "fatos": _campos([
                ("Período", _periodo(o.data_evento_inicio, o.data_evento_fim)),
                ("Necessidade", o.tipo_necessidade),
                ("Servidores", ", ".join(s.nome for s in o.servidores.all())),
                ("Motivo", (o.motivo or "").strip()),
            ]),
            "artefatos": _artefatos(o.artefatos),
            "extras": [],
        })
    if itens:
        d["documentos"].append({"titulo": "Ordens de serviço", "itens": itens})

    anexos = []
    for a in v.documentos_solicitacao.all():
        nome = (a.arquivo.name or "").rsplit("/", 1)[-1] or f"Anexo #{a.pk}"
        url = reverse("viagens_viagem:solicitacao_conteudo", args=[v.pk, a.pk])
        anexos.append({
            "titulo": nome,
            "situacao": "",
            "url": url,
            "fatos": [],
            # O anexo é o próprio arquivo: ele abre, não "não tem PDF".
            "artefatos": [{"nome": nome, "tipo": "anexo", "servidor": "", "assinado": False,
                           "criado_em": getattr(a, "criado_em", None), "url": url,
                           "url_baixar": url, "arquivo": nome}],
            "extras": [],
        })
    if anexos:
        d["documentos"].append({"titulo": "Documentos da solicitação (anexos)", "itens": anexos})

    return d


# ---------------------------------------------------------------------------
# Solicitação de evento
# ---------------------------------------------------------------------------


def _solicitacao(usuario, pk) -> dict:
    from solicitacoes import integracao_viagens, permissions
    from solicitacoes.models import SolicitacaoEvento

    s = (
        SolicitacaoEvento.objects.select_related(
            "municipio", "regiao", "tipo_evento", "orgao_responsavel",
            "unidade_movel_designada", "motorista", "decidido_por", "criado_por",
        )
        .filter(pk=pk)
        .first()
    )
    if s is None:
        raise Http404
    if not permissions.pode_ver(usuario, s):
        raise PermissionDenied

    lugar = str(s.municipio) if s.municipio_id else "Sem município"
    d = _base(
        fonte="solicitacao",
        rotulo="Solicitação de evento",
        titulo=lugar + (f" — {s.tipo_evento}" if s.tipo_evento_id else ""),
        subtitulo=_periodo(s.data_inicio_evento, s.data_fim_evento),
        situacao=s.get_status_display(),
        situacao_slug=s.status,
        encerrado=s.status in {"CANCELADA", "NAO_ATENDIDA"},
        url_abrir=reverse("solicitacoes:editar", args=[s.pk]),
    )
    d["campos"] = _campos([
        ("Decisão da DG", s.get_decisao_dg_display() if s.decisao_dg else ""),
        ("Observação da DG", s.observacoes_dg),
        ("Decidido por", f"{s.decidido_por} em {s.decidido_em:%d/%m/%Y %H:%M}" if s.decidido_por_id and s.decidido_em else ""),
        ("Data da solicitação", s.data_solicitacao.strftime("%d/%m/%Y") if s.data_solicitacao else ""),
        ("Região", str(s.regiao) if s.regiao_id else ""),
        ("Local", s.local_evento),
        ("Solicitante", s.solicitante_nome),
        ("Cargo / unidade", s.solicitante_cargo_unidade),
        ("Contato", s.contato),
        ("Órgão responsável", str(s.orgao_responsavel) if s.orgao_responsavel_id else ""),
        # `unidade_movel` é valor (a solicitação pede?), não relação.
        ("Unidade móvel", ("Sim" if s.unidade_movel is True else "") if isinstance(s.unidade_movel, bool) else str(s.unidade_movel or "")),
        ("Unidade móvel designada", str(s.unidade_movel_designada) if s.unidade_movel_designada_id else ""),
        ("Servidores previstos", str(s.quantidade_servidores or "")),
        ("Tipo de operação", s.get_tipo_operacao_display() if s.tipo_operacao else ""),
        ("CIN previstas", str(s.quantidade_cin or "")),
        ("Motorista", str(s.motorista) if s.motorista_id else ""),
        ("Descrição complementar", (s.descricao_complementar or "").strip()),
        ("Criada por", f"{s.criado_por} em {s.criado_em:%d/%m/%Y %H:%M}" if s.criado_por_id and s.criado_em else ""),
    ])

    equipes = [
        f"{i.equipe}: {i.quantidade_servidores or 'sem quantidade'}" + (f" — {i.observacao}" if i.observacao else "")
        for i in s.itens_equipe.select_related("equipe")
    ]
    if equipes:
        d["secoes"].append({"titulo": "Equipes autorizadas", "campos": [], "linhas": equipes})
    servicos = [str(i.servico) + (f" — {i.observacao}" if i.observacao else "") for i in s.itens_servico.select_related("servico")]
    if servicos:
        d["secoes"].append({"titulo": "Serviços", "campos": [], "linhas": servicos})

    anexos = []
    for a in s.anexos.select_related("enviado_por").order_by("-criado_em"):
        nome = a.nome_original or f"Anexo #{a.pk}"
        url = reverse("solicitacoes:anexo_baixar", args=[s.pk, a.pk])
        anexos.append({
            "titulo": nome,
            "situacao": f"{round(a.tamanho / 1024)} KB" if a.tamanho else "",
            "url": url,
            "fatos": _campos([
                ("Enviado por", str(a.enviado_por) if a.enviado_por_id else ""),
                ("Em", a.criado_em.strftime("%d/%m/%Y %H:%M") if a.criado_em else ""),
            ]),
            "artefatos": [{"nome": nome, "tipo": "anexo", "servidor": "", "assinado": False,
                           "criado_em": a.criado_em, "url": url, "url_baixar": url,
                           "arquivo": nome}],
            "extras": [],
        })
    if anexos:
        d["documentos"].append({"titulo": "Anexos", "itens": anexos})

    viagem = integracao_viagens.viagem_da_solicitacao(s)
    if viagem is not None:
        d["origem"] = {"rotulo": f"Viagem gerada: #{viagem.pk} — {viagem}", "url": reverse("viagens_viagem:painel", args=[viagem.pk])}

    d["historico"] = _historico(s.historico.select_related("usuario"))
    return d


# ---------------------------------------------------------------------------
# Coffee break
# ---------------------------------------------------------------------------


def _coffee(usuario, pk) -> dict:
    from coffee_break import services
    from coffee_break.models import SituacaoFinanceira, SolicitacaoCoffeeBreak
    from coffee_break.permissions import pode_acessar

    if not pode_acessar(usuario):
        raise PermissionDenied
    c = (
        SolicitacaoCoffeeBreak.objects.select_related("lote__contrato__fornecedor", "criado_por", "cancelada_por")
        .filter(pk=pk)
        .first()
    )
    if c is None:
        raise Http404

    situacao_valor = services.situacao_financeira(c)
    try:
        situacao = SituacaoFinanceira(situacao_valor).label
    except (ValueError, TypeError):
        situacao = str(situacao_valor)

    descricao = (c.descricao_evento or "").strip()
    d = _base(
        fonte="coffee",
        rotulo="Coffee break",
        titulo=descricao or "Coffee break",
        subtitulo=_periodo(c.data_inicio_evento, c.data_fim_evento) or (c.periodo_evento_texto or ""),
        situacao="Cancelada" if c.cancelada else situacao,
        situacao_slug="cancelada" if c.cancelada else str(situacao_valor).lower(),
        encerrado=bool(c.cancelada),
        url_abrir=reverse("coffee_break:editar", args=[c.pk]),
    )
    d["campos"] = _campos([
        ("Quantidade", f"{c.quantidade or 0} unidade(s)"),
        ("Número", c.numero),
        ("Data da solicitação", c.data_solicitacao.strftime("%d/%m/%Y") if c.data_solicitacao else ""),
        ("Nota fiscal", c.numero_nota_fiscal),
        ("Protocolo de pagamento", c.protocolo_pagamento),
        ("Atesto GAF", c.data_atesto_gaf.strftime("%d/%m/%Y") if c.data_atesto_gaf else ""),
        ("Ordem bancária", c.data_ordem_bancaria.strftime("%d/%m/%Y") if c.data_ordem_bancaria else ""),
        ("Envio à empresa", c.data_envio_empresa.strftime("%d/%m/%Y") if c.data_envio_empresa else ""),
        ("Observações", (c.observacoes or "").strip()),
        ("Cancelada", f"{c.motivo_cancelamento or 'sem motivo'} ({c.cancelada_por}, {c.cancelada_em:%d/%m/%Y})" if c.cancelada and c.cancelada_em else (c.motivo_cancelamento if c.cancelada else "")),
        ("Criada por", str(c.criado_por) if c.criado_por_id else ""),
    ])
    lote = c.lote
    if lote is not None:
        contrato = lote.contrato
        fornecedor = contrato.fornecedor if contrato is not None else None
        d["secoes"].append({
            "titulo": "Lote e contrato",
            "campos": _campos([
                ("Lote", f"{lote.numero}/{lote.exercicio}"),
                ("Empenho", lote.empenho),
                ("Quantidade contratada", str(lote.quantidade_total or "")),
                ("Municípios", lote.municipios_texto),
                ("Contrato", contrato.numero if contrato else ""),
                ("GMS", contrato.numero_gms if contrato else ""),
                ("Termo aditivo", contrato.termo_aditivo if contrato else ""),
                ("Fiscal responsável", contrato.fiscal_responsavel if contrato else ""),
                ("Fornecedor", fornecedor.razao_social if fornecedor else ""),
                ("CNPJ", fornecedor.cnpj if fornecedor else ""),
                ("Contato do fornecedor", " · ".join(x for x in [fornecedor.contato, fornecedor.telefone, fornecedor.email] if x) if fornecedor else ""),
            ]),
            "linhas": [],
        })
    historico = getattr(c, "historico", None)
    if historico is not None:
        d["historico"] = _historico(historico.all())
    return d


# ---------------------------------------------------------------------------
# Palestra ou evento da ASCOM
# ---------------------------------------------------------------------------


def _demanda(usuario, pk) -> dict:
    from demandas_eventos import permissions
    from demandas_eventos.models import DemandaEvento

    dm = (
        DemandaEvento.objects.select_related("municipio", "tema", "criado_por")
        .filter(pk=pk)
        .first()
    )
    if dm is None:
        raise Http404
    if not permissions.pode_ver(usuario, dm):
        raise PermissionDenied

    lugar = dm.municipio_display or "Sem município"
    d = _base(
        fonte="demanda",
        rotulo=dm.get_evento_display(),
        titulo=lugar + (f" — {dm.tema}" if dm.tema_id else ""),
        subtitulo=_periodo(dm.data_inicio_evento, dm.data_fim_evento) or (dm.periodo_evento_texto or ""),
        situacao=dm.get_status_display(),
        situacao_slug=dm.status,
        encerrado=dm.status == "CANCELADA",
        url_abrir=reverse("demandas_eventos:editar", args=[dm.pk]),
    )
    # As colunas da planilha, na ordem dela.
    d["campos"] = _campos([
        ("Hora (período)", dm.periodo_evento_texto),
        ("Andamento", (dm.andamento or "").strip()),
        ("Informações prévias", (dm.informacoes_previas or "").strip()),
        ("Solicitante", dm.solicitante),
        ("Contato", dm.contato),
        ("Data da solicitação", dm.data_solicitacao.strftime("%d/%m/%Y") if dm.data_solicitacao else ""),
        ("Foi solicitado via", dm.canal_solicitacao),
        ("Descrição", (dm.descricao or "").strip()),
        ("Quantidade de público", str(dm.quantidade_publico or "")),
        ("Assunto e-mail", dm.assunto_email),
        ("Pedido/Contato", (dm.pedido_contato or "").strip()),
        ("Servidor", dm.servidor),
        ("Criada por", f"{dm.criado_por} em {dm.criado_em:%d/%m/%Y %H:%M}" if dm.criado_por_id and dm.criado_em else ""),
    ])
    d["historico"] = _historico(dm.historico.select_related("usuario"))
    return d


CONSTRUTORES = {
    "viagem": _viagem,
    "solicitacao": _solicitacao,
    "coffee": _coffee,
    "demanda": _demanda,
}


def montar(usuario, fonte: str, pk: int) -> dict:
    """O dossiê de um compromisso — ou ``Http404``/``PermissionDenied``."""
    construtor = CONSTRUTORES.get(fonte)
    if construtor is None:
        raise Http404
    return construtor(usuario, pk)
