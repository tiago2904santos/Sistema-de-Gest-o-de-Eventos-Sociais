"""Como a viagem se apresenta na lista e no painel.

Do `eventos/presenters.py` da origem vêm os dois selos — a SITUAÇÃO do
documento (Cancelado, Finalizado, Pronto, Rascunho) e o QUANDO (falta tanto,
em andamento, realizado, pela saída do roteiro mais próximo) —, a regra de
"pronto" e os resumos dos documentos vinculáveis do seletor da etapa 1.

O cartão da lista segue o padrão da casa: título com destino, os selos ao
lado, fatos com ícone (período, ofícios, documentos, servidores) numa célula
só, e o menu de ações.
"""

from django.urls import reverse
from django.utils import timezone

from viagens_oficios.presenters import iniciais  # noqa: F401 — reexportado para os templates


def _viagem_pronta(viagem):
    """Nenhum ofício nem plano em rascunho, e há OS, plano ou documento de solicitação."""
    from viagens_oficios.models import Oficio
    from viagens_planos.models import PlanoTrabalho

    oficios = [o for o in viagem.oficios.all() if not o.cancelado]
    if any(o.status == Oficio.STATUS_RASCUNHO for o in oficios):
        return False
    planos = [p for p in viagem.planos_trabalho.all() if not p.cancelado]
    if any(p.status == PlanoTrabalho.STATUS_RASCUNHO for p in planos):
        return False
    tem_os = any(not o.cancelado for o in viagem.ordens_servico.all())
    tem_solicitacao = bool(list(viagem.documentos_solicitacao.all()))
    return tem_os or bool(planos) or tem_solicitacao


def _data_local(valor):
    if not valor:
        return None
    return timezone.localtime(valor).date() if timezone.is_aware(valor) else valor.date()


def saida_do_roteiro(viagem):
    """(saída, fim) do roteiro da viagem com a saída mais próxima; ignora cancelados e sem data."""
    candidatos = list(viagem.roteiros.all())
    for oficio in viagem.oficios.all():
        if oficio.roteiro_id and oficio.roteiro:
            candidatos.append(oficio.roteiro)
    validos = {r.pk: r for r in candidatos if not r.cancelado and r.saida_dt}
    if not validos:
        return None, None
    roteiro = min(validos.values(), key=lambda r: r.saida_dt)
    saida = _data_local(roteiro.saida_dt)
    fim = _data_local(roteiro.retorno_chegada_dt or roteiro.chegada_dt) or saida
    return saida, fim


def selo_situacao(viagem):
    """Cancelado, Finalizado (prestações encerradas), Pronto ou Rascunho."""
    if viagem.cancelado:
        return "Cancelado", "cancelada"
    if getattr(viagem, "_tem_prestacao", False) and not getattr(viagem, "_tem_prestacao_pendente", False):
        return "Finalizado", "atendido"
    if _viagem_pronta(viagem):
        return "Pronto", "atendido"
    return "Rascunho", "pendente"


def selo_quando(viagem):
    """Quanto falta, em andamento ou realizado. Viagem cancelada não recebe este selo."""
    if viagem.cancelado:
        return None
    saida, fim = saida_do_roteiro(viagem)
    if not saida:
        return None
    hoje = timezone.localdate()
    if hoje < saida:
        dias = (saida - hoje).days
        return ("falta 1 dia" if dias == 1 else f"faltam {dias} dias"), "em_andamento"
    if saida <= hoje <= fim:
        return "Em andamento", "em_andamento"
    return "Realizado", "atendido"


def fatos_da_viagem(viagem):
    """Período, ofícios, documentos e servidores — cada um com o seu ícone."""
    oficios = [o for o in viagem.oficios.all()]
    documentos = len(viagem.planos_trabalho.all()) + len(viagem.ordens_servico.all()) + len(viagem.documentos_solicitacao.all())
    servidores = []
    for oficio in oficios:
        for s in oficio.servidores.all():
            if s.nome not in servidores:
                servidores.append(s.nome)
    tem_periodo = bool(viagem.data_inicio)
    return [
        {"icone": "calendar", "rotulo": "Período", "texto": viagem.periodo_display, "ausente": not tem_periodo},
        {"icone": "document", "rotulo": "Ofícios", "texto": f"{len(oficios)} ofício{'s' if len(oficios) != 1 else ''}" if oficios else "Nenhum ofício vinculado", "ausente": not oficios},
        {"icone": "clipboard", "rotulo": "Documentos", "texto": f"{documentos} documento{'s' if documentos != 1 else ''}" if documentos else "Nenhum plano, OS ou solicitação", "ausente": not documentos},
        {"icone": "users", "rotulo": "Servidores", "texto": ", ".join(servidores) if servidores else "Sem servidores", "ausente": not servidores},
    ]


def titulo_da_viagem(viagem):
    return (viagem.titulo or "").strip() or "Nova viagem"


def linha_da_lista(viagem):
    situacao, tom = selo_situacao(viagem)
    quando = selo_quando(viagem)
    destino = viagem.destino_display
    return {
        "viagem": viagem,
        "titulo": " · ".join(p for p in [titulo_da_viagem(viagem), destino if destino != "Destino não informado" else ""] if p),
        "selo": situacao,
        "selo_tom": tom,
        "quando": quando[0] if quando else "",
        "quando_tom": quando[1] if quando else "",
        "fatos": fatos_da_viagem(viagem),
        "url_editar": reverse("viagens_viagem:etapa", args=[viagem.pk, 1]),
        "url_painel": reverse("viagens_viagem:etapa", args=[viagem.pk, 3]),
        "url_cancelar": reverse("viagens_viagem:acao", args=[viagem.pk, "cancelar"]),
        "url_reativar": reverse("viagens_viagem:acao", args=[viagem.pk, "reativar"]),
        "url_excluir": reverse("viagens_viagem:acao", args=[viagem.pk, "excluir"]),
    }


# ── Documentos vinculáveis: resumos para o seletor da etapa 1 ─────────────

_PLACEHOLDERS_META = ("nao informado", "nao informada", "periodo nao informado", "destino nao informado")


def _sem_acento(texto):
    import unicodedata

    return "".join(c for c in unicodedata.normalize("NFD", texto or "") if unicodedata.category(c) != "Mn")


def _meta_limpa(texto):
    texto = (texto or "").strip()
    base = _sem_acento(texto).lower()
    if not texto or any(base == p or base.endswith(p) for p in _PLACEHOLDERS_META):
        return ""
    return texto


def _iso(valor):
    data = valor.date() if valor is not None and hasattr(valor, "hour") else valor
    return data.isoformat() if data else ""


def _periodo_texto(inicio, fim):
    if not inicio:
        return ""
    inicio, fim = (v.date() if hasattr(v, "hour") else v for v in (inicio, fim))
    if not fim or fim == inicio:
        return f"{inicio:%d/%m/%Y}"
    return f"{inicio:%d/%m/%Y} a {fim:%d/%m/%Y}"


def _datas_roteiro(roteiro):
    from viagens_roteiros.presenters import periodo_do_roteiro

    inicio, fim = periodo_do_roteiro(roteiro)
    return _data_local(inicio), _data_local(fim) or _data_local(inicio)


def _opcao(pk, titulo, meta, busca, inicio, fim, selecionados):
    return {
        "valor": str(pk), "rotulo": titulo, "detalhes": meta, "busca": busca,
        "selecionado": str(pk) in selecionados,
        "dados": {"inicio": _iso(inicio), "fim": _iso(fim)},
    }


def _resumo_oficio(oficio, selecionados):
    from viagens_roteiros.presenters import titulo_da_rota

    roteiro = oficio.roteiro
    destino = titulo_da_rota(roteiro) if roteiro else ""
    inicio, fim = _datas_roteiro(roteiro) if roteiro else (None, None)
    servidores = list(oficio.servidores.all())
    primeiros = ", ".join(s.nome.split()[0] for s in servidores if s.nome.strip())
    viatura = ""
    if oficio.viatura_id:
        viatura = " ".join(p for p in [oficio.viatura.placa_formatada, oficio.viatura.modelo or ""] if p)
    titulo = " ".join(p for p in [f"Ofício {oficio.numero_formatado}", destino] if p and destino != "—")
    meta = " · ".join(p for p in [_periodo_texto(inicio, fim), primeiros, viatura] if p) or "Sem informações disponíveis"
    busca = " ".join(p for p in [oficio.numero_formatado, oficio.protocolo or "", destino, " ".join(s.nome for s in servidores), viatura] if p)
    return _opcao(oficio.pk, titulo, meta, busca, inicio, fim, selecionados)


def _resumo_roteiro(roteiro, selecionados):
    from viagens_roteiros.presenters import titulo_da_rota

    inicio, fim = _datas_roteiro(roteiro)
    titulo = titulo_da_rota(roteiro)
    meta = _periodo_texto(inicio, fim) or "Sem período definido"
    return _opcao(roteiro.pk, titulo, meta, f"{titulo} {meta}", inicio, fim, selecionados)


def _resumo_ordem(ordem, selecionados):
    inicio, fim = ordem.data_evento_inicio, ordem.data_evento_fim or ordem.data_evento_inicio
    titulo = ordem.numero_formatado
    meta = " · ".join(p for p in [_meta_limpa(ordem.periodo_display), _meta_limpa(ordem.destinos_display)] if p) or "Sem período definido"
    return _opcao(ordem.pk, titulo, meta, f"{titulo} {meta}", inicio, fim, selecionados)


def _resumo_plano(plano, selecionados):
    inicio, fim = plano.data_evento_inicio, plano.data_evento_fim or plano.data_evento_inicio
    titulo = f"PT {plano.numero_formatado}"
    meta = " · ".join(p for p in [_meta_limpa(plano.programa_display), _meta_limpa(plano.periodo_display)] if p) or "Sem período definido"
    return _opcao(plano.pk, titulo, meta, f"{titulo} {meta}", inicio, fim, selecionados)


def _resumo_termo(termo, selecionados):
    inicio, fim = termo.periodo_efetivo()
    titulo = f"Termo #{termo.pk}"
    meta = " · ".join(p for p in [_meta_limpa(termo.destino_display), _meta_limpa(termo.periodo_display)] if p) or "Sem período definido"
    return _opcao(termo.pk, titulo, meta, f"{titulo} {meta}", inicio, fim, selecionados)


def _selecionados(form, campo):
    valor = form[campo].value() or []
    if isinstance(valor, (str, int)):
        valor = [valor]
    return {str(getattr(v, "pk", v)) for v in valor}


def opcoes_de_documentos(form):
    """As cinco listas do seletor "Documentos vinculados", no formato do multi_pick."""
    return {
        "oficios": [_resumo_oficio(o, _selecionados(form, "oficios_vinculados")) for o in form.fields["oficios_vinculados"].queryset],
        "roteiros": [_resumo_roteiro(r, _selecionados(form, "roteiros_vinculados")) for r in form.fields["roteiros_vinculados"].queryset],
        "pt": [_resumo_plano(p, _selecionados(form, "planos_trabalho_vinculados")) for p in form.fields["planos_trabalho_vinculados"].queryset],
        "os": [_resumo_ordem(o, _selecionados(form, "ordens_servico_vinculadas")) for o in form.fields["ordens_servico_vinculadas"].queryset],
        "termos": [_resumo_termo(t, _selecionados(form, "termos_vinculados")) for t in form.fields["termos_vinculados"].queryset],
    }


# As cinco abas do seletor, na ordem da origem: chave, rótulo do alternador,
# campo do formulário, rótulo do seletor, placeholder da busca e texto vazio.
ABAS_DE_DOCUMENTOS = [
    ("oficios", "Ofícios", "oficios_vinculados", "Adicionar ofício", "Buscar por número, protocolo, destino ou servidor", "Nenhum ofício disponível para o período."),
    ("roteiros", "Roteiros", "roteiros_vinculados", "Adicionar roteiro", "Buscar por origem, destino ou período", "Nenhum roteiro disponível para o período."),
    ("pt", "Plano de Trabalho", "planos_trabalho_vinculados", "Adicionar plano de trabalho", "Buscar por número, programa ou período", "Nenhum plano de trabalho disponível para o período."),
    ("os", "Ordem de Serviço", "ordens_servico_vinculadas", "Adicionar ordem de serviço", "Buscar por número, destino ou período", "Nenhuma ordem de serviço disponível para o período."),
    ("termos", "Termos", "termos_vinculados", "Adicionar termo", "Buscar por destino ou período", "Nenhum termo disponível para o período."),
]


def abas_de_documentos(form):
    opcoes = opcoes_de_documentos(form)
    abas = []
    for chave, rotulo, campo, rotulo_seletor, placeholder, vazio in ABAS_DE_DOCUMENTOS:
        itens = opcoes[chave]
        abas.append({
            "chave": chave, "rotulo": rotulo, "campo": campo, "rotulo_seletor": rotulo_seletor,
            "placeholder": placeholder, "vazio": vazio, "opcoes": itens,
            "vinculados": sum(1 for o in itens if o["selecionado"]),
            "erros": form.errors.get(campo),
        })
    # Abre na primeira aba que já tem documento vinculado; senão, na primeira.
    inicial = next((a["chave"] for a in abas if a["vinculados"]), abas[0]["chave"])
    for aba in abas:
        aba["ativa"] = aba["chave"] == inicial
    return abas
