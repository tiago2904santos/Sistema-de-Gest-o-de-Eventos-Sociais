"""O pedido de coffee break aberto a partir do evento ou da palestra.

O "Pedir coffee break" da solicitação de evento (app `solicitacoes`) e da
palestra (app `demandas_eventos`) leva à nova solicitação com
``?solicitacao=<pk>`` ou ``?demanda=<pk>``: a tela abre já preenchida com o
município (que escolhe o lote), a data, o horário, a descrição, o local, quem
recebe e o público. As duas ficam ligadas: a OS mostra de onde veio e avisa
quando o evento foi remarcado.

Só vale a origem que quem pede enxerga (a permissão de ver de cada módulo).
"""

from django.urls import reverse

PARAMETROS = {"solicitacao": "solicitacao_evento", "demanda": "demanda_evento"}


def _visivel(tipo, pk, usuario):
    if tipo == "solicitacao":
        from solicitacoes.models import SolicitacaoEvento
        from solicitacoes.permissions import pode_ver

        objeto = SolicitacaoEvento.objects.select_related("municipio", "tipo_evento").filter(pk=pk).first()
    else:
        from demandas_eventos.models import DemandaEvento
        from demandas_eventos.permissions import pode_ver

        objeto = DemandaEvento.objects.select_related("municipio").prefetch_related("temas").filter(pk=pk).first()
    return objeto if objeto is not None and pode_ver(usuario, objeto) else None


def origem_do_pedido(dados, usuario):
    """(campo, objeto) da origem pedida em ``dados`` (GET ou POST), ou (None, None)."""
    for parametro, campo in PARAMETROS.items():
        valor = (dados.get(parametro) or "").strip()
        if valor.isdigit():
            objeto = _visivel(parametro, int(valor), usuario)
            if objeto is not None:
                return campo, objeto
    return None, None


def _juntar(*partes, separador=" – "):
    return separador.join(p.strip() for p in partes if p and str(p).strip())


def valores_iniciais(campo, objeto):
    """Os campos do pedido que a origem já sabe."""
    iniciais = {}
    if objeto.municipio_id:
        iniciais["municipio"] = objeto.municipio_id
    if objeto.data_inicio_evento:
        iniciais["data_inicio_evento"] = objeto.data_inicio_evento
    if campo == "solicitacao_evento":
        tipo = str(objeto.tipo_evento) if objeto.tipo_evento_id else "Evento"
        iniciais["descricao_evento"] = _juntar(tipo, objeto.local_evento, objeto.municipio.nome if objeto.municipio_id else "")
        iniciais["local_entrega"] = objeto.local_evento
        iniciais["responsavel_recebimento"] = _juntar(objeto.solicitante_nome, objeto.contato, separador=" ")
    else:
        temas = ", ".join(t.nome for t in objeto.temas.all())
        iniciais["descricao_evento"] = _juntar(
            objeto.get_evento_display(), temas, objeto.municipio.nome if objeto.municipio_id else objeto.municipio_texto
        )
        if objeto.hora_inicio:
            iniciais["horario_evento"] = objeto.hora_inicio
        iniciais["responsavel_recebimento"] = _juntar(objeto.solicitante[:100], objeto.telefone, separador=" ")
        if objeto.quantidade_publico:
            iniciais["quantidade"] = objeto.quantidade_publico
    iniciais["descricao_evento"] = iniciais["descricao_evento"][:255]
    iniciais["local_entrega"] = (iniciais.get("local_entrega") or "")[:255]
    iniciais["responsavel_recebimento"] = iniciais["responsavel_recebimento"][:150]
    return {chave: valor for chave, valor in iniciais.items() if valor not in ("", None)}


def rotulo(campo, objeto):
    if campo == "solicitacao_evento":
        return f"Solicitação de evento #{objeto.pk}"
    return f"{objeto.get_evento_display()} #{objeto.pk}"


def url(campo, objeto):
    rota = "solicitacoes:editar" if campo == "solicitacao_evento" else "demandas_eventos:editar"
    return reverse(rota, args=[objeto.pk])


def cartao(solicitacao, usuario):
    """O que a etapa 1 mostra da origem: rótulo, link (se quem vê enxerga a
    origem) e o aviso de remarcação (a data da origem mudou depois do pedido)."""
    for campo in PARAMETROS.values():
        objeto = getattr(solicitacao, campo)
        if objeto is None:
            continue
        parametro = next(p for p, c in PARAMETROS.items() if c == campo)
        visivel = _visivel(parametro, objeto.pk, usuario) is not None
        aviso = ""
        if (
            objeto.data_inicio_evento and solicitacao.data_inicio_evento
            and objeto.data_inicio_evento != solicitacao.data_inicio_evento
            and not solicitacao.cancelada
        ):
            aviso = (
                f"O evento foi remarcado para {objeto.data_inicio_evento:%d/%m/%Y}, e a OS está com "
                f"{solicitacao.data_inicio_evento:%d/%m/%Y}. Confira a data e avise o fornecedor."
            )
        return {"rotulo": rotulo(campo, objeto), "url": url(campo, objeto) if visivel else "", "aviso": aviso}
    return None
