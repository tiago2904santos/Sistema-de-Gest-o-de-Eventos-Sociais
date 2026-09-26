"""Coerência entre a viagem e os documentos dela (m071).

Cada documento (OS, plano de trabalho, termo) copia datas, destinos e equipe
da viagem só quando nasce. Se o evento é adiado, muda de cidade ou a equipe
troca, era preciso corrigir documento por documento — e é fácil esquecer um,
o que devolve o processo. Aqui a viagem é a referência:

- período: o da viagem (etapa 1) contra o de cada OS, plano e termo;
- destinos: as cidades da viagem contra as de cada OS, plano e termo;
- equipe: os servidores dos ofícios contra os da OS (e os ofícios dela);
- viatura: a do ofício contra a do termo preso a ele;
- roteiro: saída depois do início ou volta antes do fim do evento (só aviso:
  horário de deslocamento não se corrige sozinho).

`verificar_coerencia(viagem)` lista as diferenças; `aplicar_coerencia`
sincroniza as que dá para aplicar, só nos documentos ainda sem versão
assinada — documento assinado não muda por baixo de quem assinou.
Usa `.all()` nas relações para aproveitar o prefetch da lista.
"""

from django.db import transaction
from django.utils import timezone


def _periodo(inicio, fim):
    if not inicio:
        return "sem período"
    fim = fim or inicio
    return inicio.strftime("%d/%m/%Y") if fim == inicio else f"{inicio:%d/%m/%Y} a {fim:%d/%m/%Y}"


def _cidades(ids):
    from cadastros.models import Municipio

    nomes = [f"{m.nome}/{m.estado.sigla}" for m in Municipio.objects.select_related("estado").filter(pk__in=ids).order_by("nome")]
    return ", ".join(nomes) or "sem destino"


def _destinos_da_viagem(viagem):
    return {municipio for _, municipio in viagem.destinos_pares() if municipio}


def _destinos_do_termo(termo):
    ids = {termo.destino_cidade_id} if termo.destino_cidade_id else set()
    for extra in termo.destinos_extras or []:
        if isinstance(extra, dict) and str(extra.get("cidade_id", "")).isdigit():
            ids.add(int(extra["cidade_id"]))
    return ids


def _destinos_do_plano(plano):
    ids = {d.cidade_id for d in plano.destinos.all() if d.cidade_id and not d.evento_id}
    if plano.destino_cidade_id:
        ids.add(plano.destino_cidade_id)
    return ids


def _item(chave, documento, campo, esperado, atual, *, aplicavel=True):
    return {"chave": chave, "documento": documento, "campo": campo, "esperado": esperado, "atual": atual,
            "aplicavel": aplicavel}


def verificar_coerencia(viagem):
    """As diferenças entre a viagem e os documentos ativos dela."""
    diferencas = []
    inicio, fim = viagem.data_inicio, viagem.data_fim or viagem.data_inicio
    destinos = _destinos_da_viagem(viagem)
    oficios = [o for o in viagem.oficios.all() if not o.cancelado]
    equipe = {}
    for oficio in oficios:
        for servidor in oficio.servidores.all():
            equipe.setdefault(servidor.pk, servidor)

    for ordem in viagem.ordens_servico.all():
        if ordem.cancelado:
            continue
        nome = ordem.numero_formatado
        if inicio and (ordem.data_evento_inicio, ordem.data_evento_fim or ordem.data_evento_inicio) != (inicio, fim):
            diferencas.append(_item(f"os-{ordem.pk}:periodo", nome, "Período", _periodo(inicio, fim),
                                    _periodo(ordem.data_evento_inicio, ordem.data_evento_fim)))
        atuais = {m.pk for m in ordem.destinos.all()}
        if destinos and atuais != destinos:
            diferencas.append(_item(f"os-{ordem.pk}:destinos", nome, "Destinos", _cidades(destinos), _cidades(atuais)))
        da_os = {s.pk for s in ordem.servidores.all()}
        if equipe and da_os != set(equipe):
            diferencas.append(_item(f"os-{ordem.pk}:equipe", nome, "Equipe",
                                    ", ".join(sorted(s.nome for s in equipe.values())),
                                    ", ".join(sorted(s.nome for s in ordem.servidores.all())) or "sem equipe"))

    for plano in viagem.planos_trabalho.all():
        if plano.cancelado or plano.is_multi_evento:
            # Plano de vários eventos tem datas e destinos por evento: não há um par para comparar.
            continue
        nome = f"Plano {plano.numero_formatado}"
        if inicio and (plano.data_evento_inicio, plano.data_evento_fim or plano.data_evento_inicio) != (inicio, fim):
            diferencas.append(_item(f"pt-{plano.pk}:periodo", nome, "Período", _periodo(inicio, fim),
                                    _periodo(plano.data_evento_inicio, plano.data_evento_fim)))
        atuais = _destinos_do_plano(plano)
        if destinos and atuais != destinos:
            diferencas.append(_item(f"pt-{plano.pk}:destinos", nome, "Destinos", _cidades(destinos), _cidades(atuais)))

    for termo in viagem.termos_autorizacao.all():
        if termo.cancelado:
            continue
        nome = f"Termo #{termo.pk}"
        if inicio and termo.data_evento_inicio and (termo.data_evento_inicio, termo.data_evento_fim or termo.data_evento_inicio) != (inicio, fim):
            diferencas.append(_item(f"termo-{termo.pk}:periodo", nome, "Período", _periodo(inicio, fim),
                                    _periodo(termo.data_evento_inicio, termo.data_evento_fim)))
        atuais = _destinos_do_termo(termo)
        if destinos and atuais and atuais != destinos:
            diferencas.append(_item(f"termo-{termo.pk}:destinos", nome, "Destinos", _cidades(destinos), _cidades(atuais)))
        oficio = termo.oficio if termo.oficio_id else None
        if oficio is not None and termo.viatura_id and oficio.viatura_id and termo.viatura_id != oficio.viatura_id:
            diferencas.append(_item(f"termo-{termo.pk}:viatura", nome, "Viatura", str(oficio.viatura), str(termo.viatura)))

    for roteiro in viagem.roteiros.all():
        if roteiro.cancelado or not inicio:
            continue
        saida = timezone.localdate(roteiro.saida_dt) if roteiro.saida_dt else None
        volta = roteiro.retorno_chegada_dt or roteiro.retorno_saida_dt
        volta = timezone.localdate(volta) if volta else None
        if saida and saida > inicio:
            diferencas.append(_item(f"roteiro-{roteiro.pk}:saida", f"Roteiro #{roteiro.pk}", "Saída",
                                    f"até {inicio:%d/%m/%Y}", saida.strftime("%d/%m/%Y"), aplicavel=False))
        if volta and volta < fim:
            diferencas.append(_item(f"roteiro-{roteiro.pk}:volta", f"Roteiro #{roteiro.pk}", "Retorno",
                                    f"a partir de {fim:%d/%m/%Y}", volta.strftime("%d/%m/%Y"), aplicavel=False))
    return diferencas


def _assinados(viagem):
    """{"os-1", "pt-2", "termo-3"}: documentos com versão assinada (não se mexe neles)."""
    from documentos.services.assinados import versao_assinada_vigente
    from documentos.services.types import DocumentoTipo
    from viagens_ordens.presenters import artefatos_pdf_por_ordem
    from viagens_planos.services import referencia_do_plano
    from viagens_termos.presenters import artefatos_pdf_por_termo

    travados = set()
    ordens = [o for o in viagem.ordens_servico.all() if not o.cancelado]
    for pk, artefato in artefatos_pdf_por_ordem(ordens).items():
        if artefato and artefato.get("assinado"):
            travados.add(f"os-{pk}")
    termos = [t for t in viagem.termos_autorizacao.all() if not t.cancelado]
    for pk, artefatos in artefatos_pdf_por_termo(termos).items():
        if any((a or {}).get("assinado") for a in (artefatos or {}).values()):
            travados.add(f"termo-{pk}")
    for plano in viagem.planos_trabalho.all():
        if not plano.cancelado and versao_assinada_vigente(
                DocumentoTipo.PLANO_TRABALHO, plano_trabalho_id=plano.pk, reference=referencia_do_plano(plano)):
            travados.add(f"pt-{plano.pk}")
    return travados


@transaction.atomic
def aplicar_coerencia(viagem, chaves=None):
    """Sincroniza as diferenças aplicáveis (todas, ou só as `chaves`). Devolve (aplicadas, puladas)."""
    from cadastros.models import Municipio

    diferencas = [d for d in verificar_coerencia(viagem) if d["aplicavel"] and (chaves is None or d["chave"] in chaves)]
    travados = _assinados(viagem)
    inicio, fim = viagem.data_inicio, viagem.data_fim or viagem.data_inicio
    destinos = list(dict.fromkeys(m for _, m in viagem.destinos_pares() if m))
    por_pk = {m.pk: m for m in Municipio.objects.select_related("estado").filter(pk__in=destinos)}
    cidades = [por_pk[pk] for pk in destinos if pk in por_pk]
    oficios = [o for o in viagem.oficios.all() if not o.cancelado]
    aplicadas, puladas = [], []
    for d in diferencas:
        documento, _, campo = d["chave"].partition(":")
        if documento in travados:
            puladas.append(d)
            continue
        tipo, _, pk = documento.partition("-")
        pk = int(pk)
        if tipo == "os":
            ordem = viagem.ordens_servico.get(pk=pk)
            if campo == "periodo":
                ordem.data_evento_inicio, ordem.data_evento_fim = inicio, fim
                ordem.save(update_fields=["data_evento_inicio", "data_evento_fim", "atualizado_em"])
            elif campo == "destinos":
                ordem.definir_destinos(destinos)
            elif campo == "equipe":
                servidores = []
                for oficio in oficios:
                    servidores += [s for s in oficio.servidores.all() if s not in servidores]
                ordem.servidores.set(servidores)
                ordem.oficios.add(*oficios)
        elif tipo == "pt":
            plano = viagem.planos_trabalho.get(pk=pk)
            if campo == "periodo":
                plano.data_evento_inicio, plano.data_evento_fim = inicio, fim
                plano.save(update_fields=["data_evento_inicio", "data_evento_fim", "atualizado_em"])
            elif campo == "destinos":
                # Como o rascunho que nasce da viagem: o principal nos campos e,
                # com dois ou mais, todos como linhas de destino.
                from viagens_planos.models import PlanoDestino

                cidade = cidades[0]
                plano.destino_cidade, plano.destino_estado = cidade, cidade.estado
                plano.save(update_fields=["destino_cidade", "destino_estado", "atualizado_em"])
                plano.destinos.filter(evento__isnull=True).delete()
                if len(cidades) > 1:
                    PlanoDestino.objects.bulk_create([
                        PlanoDestino(plano=plano, estado_id=c.estado_id, cidade=c, ordem=n) for n, c in enumerate(cidades, 1)
                    ])
        elif tipo == "termo":
            termo = viagem.termos_autorizacao.get(pk=pk)
            if campo == "periodo":
                termo.data_evento_inicio, termo.data_evento_fim = inicio, fim
                termo.save(update_fields=["data_evento_inicio", "data_evento_fim", "atualizado_em"])
            elif campo == "destinos":
                cidade = cidades[0]
                termo.destino_cidade, termo.destino_estado = cidade, cidade.estado
                # O formato que a tela do termo grava para os adicionais.
                termo.destinos_extras = [{"cidade_id": c.pk, "estado_id": c.estado_id, "cidade": c.nome, "estado": c.estado.sigla}
                                         for c in cidades[1:]]
                termo.save(update_fields=["destino_cidade", "destino_estado", "destinos_extras", "atualizado_em"])
            elif campo == "viatura":
                termo.viatura = termo.oficio.viatura
                termo.save(update_fields=["viatura", "atualizado_em"])
        aplicadas.append(d)
    return aplicadas, puladas
