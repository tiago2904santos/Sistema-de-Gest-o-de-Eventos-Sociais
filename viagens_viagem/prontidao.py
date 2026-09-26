"""O que falta para a viagem ficar pronta (m066), etapa por etapa.

O painel marcava a etapa como "Concluída" só porque existia algum documento,
mesmo incompleto, e o que faltava vivia espalhado: a lista "falta completar"
do cartão da solicitação, o contador de equipe, as pendências de cada
documento na tela dele. Aqui tudo vira um quadro só, na ordem do processo —
dados, roteiro, ofícios, equipe x meta, OS, plano, termos, assinaturas e
protocolo —, cada pendência com o link de onde se resolve.

`quadro_de_prontidao(viagem)` devolve {etapas, total, pronta}; cada etapa:
{chave, titulo, ok, itens: [{texto, url}]}. O stepper do painel usa o `ok`
das etapas para marcar "Concluída".
"""

from django.urls import NoReverseMatch, reverse

from core.retorno import com_next


def _url(nome, *args, volta=None, query=""):
    try:
        url = reverse(nome, args=args)
    except NoReverseMatch:
        return ""
    url = f"{url}?{query}" if query else url
    return com_next(url, volta) if volta else url


def _servidor_incompleto(servidor):
    faltam = []
    if not servidor.cpf:
        faltam.append("CPF")
    if not servidor.cargo_id:
        faltam.append("cargo")
    if not servidor.unidade_id:
        faltam.append("unidade")
    return faltam


def _etapa_dados(viagem, volta):
    itens = []
    etapa1 = _url("viagens_viagem:etapa", viagem.pk, 1)
    if not viagem.tipos.exists():
        itens.append({"texto": "Informe o tipo da viagem.", "url": etapa1})
    if not viagem.data_inicio:
        itens.append({"texto": "Informe o período da viagem.", "url": etapa1})
    if not (viagem.destino_municipio_id or viagem.destino_estado_id):
        itens.append({"texto": "Informe o destino da viagem.", "url": etapa1})
    return itens


def _etapa_roteiro(viagem, volta):
    from viagens_roteiros.models import Roteiro

    roteiros = [r for r in viagem.roteiros.all() if not r.cancelado]
    # O roteiro que os ofícios usam também vale, mesmo sem estar preso à viagem.
    for oficio in viagem.oficios.all():
        if not oficio.cancelado and oficio.roteiro_id and oficio.roteiro not in roteiros:
            roteiros.append(oficio.roteiro)
    if not roteiros:
        return [{"texto": "Crie o roteiro da viagem (sede, saída, destinos e retorno).",
                 "url": _url("viagens_roteiros:novo", volta=volta, query=f"viagem={viagem.pk}")}]
    itens = []
    for roteiro in roteiros:
        editar = _url("viagens_roteiros:editar", roteiro.pk, volta=volta)
        nome = f"Roteiro #{roteiro.pk}"
        if not roteiro.origem_municipio_id:
            itens.append({"texto": f"{nome}: informe a sede (de onde a equipe sai).", "url": editar})
        if not roteiro.saida_dt:
            itens.append({"texto": f"{nome}: informe a data e a hora da saída.", "url": editar})
        if not roteiro.destinos.exists() and not roteiro.trechos.exists():
            itens.append({"texto": f"{nome}: informe os destinos.", "url": editar})
        if roteiro.rota_status == Roteiro.RotaStatus.DESATUALIZADA:
            itens.append({"texto": f"{nome}: a rota está desatualizada; recalcule.", "url": editar})
        if roteiro.valor_diarias is None:
            itens.append({"texto": f"{nome}: as diárias ainda não foram calculadas.", "url": editar})
    return itens


def _etapa_oficios(viagem, oficios, volta):
    from viagens_oficios.models import Oficio
    from viagens_oficios.services import validar_oficio_para_documento

    if not oficios:
        return [{"texto": "Nenhum ofício ainda: monte os ofícios com a equipe de cada um.",
                 "url": _url("viagens_viagem:gerar_documentos", viagem.pk)}]
    itens = []
    for oficio in oficios:
        if oficio.status != Oficio.STATUS_RASCUNHO:
            continue
        editar = _url("viagens_oficios:editar", oficio.pk, volta=volta)
        # O protocolo tem etapa própria no quadro; aqui fica o resto.
        pendencias = [p for p in validar_oficio_para_documento(oficio)["pendencias"] if "protocolo" not in p.lower()
                      or "motorista" in p.lower()]
        if pendencias:
            resumo = pendencias[0] + (f" (e mais {len(pendencias) - 1})" if len(pendencias) > 1 else "")
            itens.append({"texto": f"Ofício {oficio.numero_formatado}: {resumo}", "url": editar})
        else:
            itens.append({"texto": f"Ofício {oficio.numero_formatado} em rascunho: revise e finalize.", "url": editar})
    return itens


def _etapa_equipe(viagem, oficios, volta):
    from .meta_equipe import contador_de_servidores

    itens = []
    contador = contador_de_servidores(viagem)
    if contador and contador["faltam"]:
        itens.append({"texto": contador["texto"], "url": _url("viagens_viagem:gerar_documentos", viagem.pk)})
    vistos = set()
    viaturas = set()
    for oficio in oficios:
        for servidor in oficio.servidores.all():
            if servidor.pk in vistos:
                continue
            vistos.add(servidor.pk)
            faltam = _servidor_incompleto(servidor)
            if faltam:
                itens.append({"texto": f"Cadastro de {servidor.nome} sem {', '.join(faltam)}.",
                              "url": _url("viagens_cadastros:editar", "servidores", servidor.pk, volta=volta)})
        viatura = oficio.viatura
        if viatura is not None and viatura.pk not in viaturas:
            viaturas.add(viatura.pk)
            if viatura.status != viatura.Status.COMPLETO:
                itens.append({"texto": f"Cadastro da viatura {viatura.placa_formatada} incompleto (modelo, combustível ou tipo).",
                              "url": _url("viagens_cadastros:editar", "viaturas", viatura.pk, volta=volta)})
    return itens


def _etapa_ordem(viagem, volta):
    ordens = [o for o in viagem.ordens_servico.all() if not o.cancelado]
    if not ordens:
        return [{"texto": "Crie a ordem de serviço.", "url": _url("viagens_ordens:novo", volta=volta, query=f"viagem={viagem.pk}")}]
    itens = []
    for ordem in ordens:
        editar = _url("viagens_ordens:editar", ordem.pk, volta=volta)
        if not ordem.servidores.exists():
            itens.append({"texto": f"{ordem.numero_formatado}: sem equipe.", "url": editar})
        if not ordem.data_evento_inicio:
            itens.append({"texto": f"{ordem.numero_formatado}: sem período.", "url": editar})
        if not ordem.destinos.exists():
            itens.append({"texto": f"{ordem.numero_formatado}: sem destino.", "url": editar})
    return itens


def _etapa_plano(viagem, volta):
    from viagens_planos.services import avaliar_pendencias_documento

    planos = [p for p in viagem.planos_trabalho.all() if not p.cancelado]
    if not planos:
        return [{"texto": "Crie o plano de trabalho.", "url": _url("viagens_viagem:etapa", viagem.pk, 4)}]
    itens = []
    for plano in planos:
        editar = _url("viagens_planos:editar", plano.pk, volta=volta)
        pendencias = avaliar_pendencias_documento(plano)
        if pendencias:
            resumo = pendencias[0] + (f" (e mais {len(pendencias) - 1})" if len(pendencias) > 1 else "")
            itens.append({"texto": f"Plano {plano.numero_formatado}: {resumo}", "url": editar})
    return itens


def _etapa_termos(viagem, oficios, volta):
    """Quem viaja num ofício e precisaria de termo, mas não está marcado em nenhum."""
    from viagens_cadastros.models import ConfiguracaoSistema

    if not oficios:
        return [{"texto": "Os termos saem com os ofícios: monte os ofícios primeiro.",
                 "url": _url("viagens_viagem:gerar_documentos", viagem.pk)}]
    emissora = ConfiguracaoSistema.get_singleton().unidade_id
    com_termo = set()
    for oficio in oficios:
        com_termo |= {s.pk for s in oficio.servidores_termo_autorizacao.all()}
    for termo in viagem.termos_autorizacao.all():
        if not termo.cancelado:
            com_termo |= {s.pk for s in termo.servidores.all()}
    itens = []
    for oficio in oficios:
        sem = [s.nome for s in oficio.servidores.all()
               if s.pk not in com_termo and not (emissora and s.unidade_id == emissora)]
        if sem:
            itens.append({"texto": f"Ofício {oficio.numero_formatado}: sem termo para {', '.join(sem)}.",
                          "url": _url("viagens_oficios:editar", oficio.pk, volta=volta)})
    return itens


def _etapa_assinaturas(viagem):
    from .downloads import itens_para_baixar

    etapas = {"Ofício": 3, "Justificativa": 3, "Termo de autorização": 3, "Plano de trabalho": 4, "Ordem de serviço": 4}
    itens = []
    for item in itens_para_baixar(viagem):
        if item["detalhe"] == "Documento de solicitação" or item.get("assinado"):
            continue
        etapa = next((n for rotulo, n in etapas.items() if item["detalhe"].startswith(rotulo)), 5)
        itens.append({"texto": f"{item['nome']}: falta anexar a versão assinada.",
                      "url": _url("viagens_viagem:etapa", viagem.pk, etapa)})
    return itens


def _etapa_protocolo(viagem, oficios, volta):
    from viagens_oficios.models import Oficio

    if not oficios:
        return [{"texto": "O protocolo é aberto para cada ofício: monte os ofícios primeiro.",
                 "url": _url("viagens_viagem:gerar_documentos", viagem.pk)}]
    itens = []
    for oficio in oficios:
        editar = _url("viagens_oficios:editar", oficio.pk, volta=volta)
        if not oficio.protocolo:
            itens.append({"texto": f"Ofício {oficio.numero_formatado}: sem protocolo.", "url": editar})
        elif oficio.protocolo_origem in Oficio.PROTOCOLO_ORIGENS_NAO_OFICIAIS:
            itens.append({"texto": f"Ofício {oficio.numero_formatado}: protocolo {oficio.get_protocolo_origem_display().lower()}, não vale como oficial.",
                          "url": editar})
    return itens


def quadro_de_prontidao(viagem):
    volta = _url("viagens_viagem:etapa", viagem.pk, 1)
    oficios = [o for o in viagem.oficios.select_related("roteiro", "viatura", "motorista")
               .prefetch_related("servidores__cargo", "servidores__unidade", "servidores_termo_autorizacao").order_by("pk")
               if not o.cancelado]
    definicao = [
        ("dados", "Dados da viagem", 1, _etapa_dados(viagem, volta)),
        ("roteiro", "Roteiro", 2, _etapa_roteiro(viagem, volta)),
        ("oficios", "Ofícios", 3, _etapa_oficios(viagem, oficios, volta)),
        ("equipe", "Equipe x meta da DG", 3, _etapa_equipe(viagem, oficios, volta)),
        ("ordem", "Ordem de serviço", 4, _etapa_ordem(viagem, volta)),
        ("plano", "Plano de trabalho", 4, _etapa_plano(viagem, volta)),
        ("termos", "Termos de autorização", 5, _etapa_termos(viagem, oficios, volta)),
        ("assinaturas", "Assinaturas", None, _etapa_assinaturas(viagem)),
        ("protocolo", "Protocolo", 3, _etapa_protocolo(viagem, oficios, volta)),
    ]
    etapas = [{"chave": chave, "titulo": titulo, "painel": painel, "itens": itens, "ok": not itens}
              for chave, titulo, painel, itens in definicao]
    total = sum(len(e["itens"]) for e in etapas)
    return {"etapas": etapas, "total": total, "pronta": total == 0,
            "resolvidas": sum(1 for e in etapas if e["ok"]), "quantidade": len(etapas)}


def etapas_do_painel_prontas(quadro):
    """{número da etapa do painel: ok} — o que o stepper marca como concluída."""
    prontas = {}
    for etapa in quadro["etapas"]:
        if etapa["painel"] is None:
            continue
        prontas[etapa["painel"]] = prontas.get(etapa["painel"], True) and etapa["ok"]
    return prontas
