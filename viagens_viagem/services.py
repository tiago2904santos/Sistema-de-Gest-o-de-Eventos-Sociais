"""Regras da viagem (o agrupador) que os outros módulos consomem.

`semente_de_documentos(viagem)` é o que um documento novo herda da viagem:
destinos, datas, motivo e, dos ofícios já vinculados, servidores, viatura e
motorista. Cada fonte só preenche o que ainda está vazio, nesta ordem:
ofícios, roteiro direto, plano de trabalho, ordem de serviço, termo.
`viagem_do_request(request)` lê `?viagem=<pk>` (GET ou POST).
"""

from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from core.deletion import excluir_com_protecao

# Uma viagem aberta e abandonada não fica enchendo a lista: a próxima "Nova
# viagem" reaproveita a que ninguém preencheu. A folga evita entregar a outra
# pessoa a viagem que alguém acabou de abrir e ainda vai preencher.
FOLGA_RASCUNHO_VAZIO = timedelta(minutes=30)


def rascunho_vazio_disponivel():
    from .models import Viagem

    limite = timezone.now() - FOLGA_RASCUNHO_VAZIO
    return (
        Viagem.objects.filter(
            cancelado=False, legado_pk__isnull=True, titulo="", motivo="", descricao="",
            destino_municipio__isnull=True, destino_estado__isnull=True,
            data_inicio__isnull=True, atualizado_em__lt=limite,
        )
        .exclude(tipos__isnull=False)
        .exclude(oficios__isnull=False)
        .exclude(roteiros__isnull=False)
        .exclude(ordens_servico__isnull=False)
        .exclude(planos_trabalho__isnull=False)
        .exclude(termos_autorizacao__isnull=False)
        .exclude(documentos_solicitacao__isnull=False)
        .order_by("pk")
        .first()
    )


@transaction.atomic
def criar_viagem_rascunho():
    """A viagem que "Nova viagem" abre: uma vazia esquecida, ou uma nova."""
    from .models import Viagem

    vazia = rascunho_vazio_disponivel()
    if vazia is not None:
        return vazia
    return Viagem.objects.create()


def viagem_do_request(request):
    """A viagem indicada em `viagem` (GET ou POST), ou None se ausente/inválida."""
    from .models import Viagem

    valor = request.POST.get("viagem") if request.method == "POST" else None
    valor = valor or request.GET.get("viagem")
    try:
        pk = int(valor)
    except (TypeError, ValueError):
        return None
    return Viagem.objects.select_related("unidade_responsavel", "responsavel").filter(pk=pk).first()


def _destinos_da_viagem(viagem):
    """[(municipio, estado)] de todos os destinos, o principal primeiro."""
    from cadastros.models import Estado, Municipio

    pares = []
    for estado_id, municipio_id in viagem.destinos_pares():
        municipio = Municipio.objects.select_related("estado").filter(pk=municipio_id).first() if municipio_id else None
        estado = municipio.estado if municipio else (Estado.objects.filter(pk=estado_id).first() if estado_id else None)
        pares.append((municipio, estado))
    return pares


def _aplicar_roteiro(semente, roteiro):
    primeiro = roteiro.destinos.select_related("municipio__estado").order_by("ordem", "pk").first()
    if primeiro is not None and primeiro.municipio_id and semente["cidade"] is None:
        semente["cidade"], semente["estado"] = primeiro.municipio, primeiro.municipio.estado
    if semente["data_inicio"] is None and roteiro.saida_dt:
        semente["data_inicio"] = roteiro.saida_dt.date()
    fim = roteiro.retorno_chegada_dt or roteiro.retorno_saida_dt or roteiro.chegada_dt
    if semente["data_fim"] is None and fim:
        semente["data_fim"] = fim.date()


def semente_de_documentos(viagem):
    if viagem is None:
        return None
    destinos = _destinos_da_viagem(viagem)
    cidade, estado = destinos[0] if destinos else (None, None)
    semente = {
        "viagem": viagem,
        "cidade": cidade,
        "estado": estado,
        "destinos": destinos,
        "data_inicio": viagem.data_inicio,
        "data_fim": viagem.data_fim or viagem.data_inicio,
        "motivo": (viagem.motivo or viagem.descricao or "").strip(),
        "servidores": [],
        "servidores_termo": [],
        "viatura": None,
        "motorista": None,
        "oficio": None,
        "oficios": [],
    }

    # 1. Ofícios: até 20 mais recentes; equipe é a união de todos, viatura do primeiro.
    oficios = list(
        viagem.oficios.filter(cancelado=False).select_related("roteiro", "viatura", "motorista")
        .prefetch_related("servidores", "servidores_termo_autorizacao").order_by("-atualizado_em", "-criado_em")[:20]
    )
    if oficios:
        primeiro = oficios[0]
        semente["oficio"], semente["oficios"] = primeiro, oficios
        if not semente["motivo"]:
            semente["motivo"] = (primeiro.motivo or "").strip()
        vistos, vistos_termo = set(), set()
        for oficio in oficios:
            for servidor in oficio.servidores.all():
                if servidor.pk not in vistos:
                    vistos.add(servidor.pk)
                    semente["servidores"].append(servidor)
            for servidor in oficio.servidores_termo_autorizacao.all():
                if servidor.pk not in vistos_termo:
                    vistos_termo.add(servidor.pk)
                    semente["servidores_termo"].append(servidor)
        semente["viatura"], semente["motorista"] = primeiro.viatura, primeiro.motorista
        if primeiro.roteiro_id:
            _aplicar_roteiro(semente, primeiro.roteiro)

    # 2. Roteiro ligado direto à viagem.
    roteiro = viagem.roteiros.filter(cancelado=False).order_by("-atualizado_em").first()
    if roteiro is not None:
        _aplicar_roteiro(semente, roteiro)

    # 3. Plano de trabalho.
    plano = viagem.planos_trabalho.filter(cancelado=False).select_related("destino_cidade__estado", "destino_estado").order_by("-atualizado_em").first()
    if plano is not None:
        if semente["cidade"] is None and plano.destino_cidade_id:
            semente["cidade"], semente["estado"] = plano.destino_cidade, plano.destino_cidade.estado
        elif semente["estado"] is None and plano.destino_estado_id:
            semente["estado"] = plano.destino_estado
        semente["data_inicio"] = semente["data_inicio"] or plano.data_evento_inicio
        semente["data_fim"] = semente["data_fim"] or plano.data_evento_fim
        if not semente["motivo"]:
            semente["motivo"] = (plano.contextualizacao or "").strip()

    # 4. Ordem de serviço.
    ordem = viagem.ordens_servico.filter(cancelado=False).prefetch_related("destinos__estado", "servidores").order_by("-atualizado_em").first()
    if ordem is not None:
        destino = sorted(ordem.destinos.all(), key=lambda d: d.nome)[:1]
        if semente["cidade"] is None and destino:
            semente["cidade"], semente["estado"] = destino[0], destino[0].estado
        semente["data_inicio"] = semente["data_inicio"] or ordem.data_evento_inicio
        semente["data_fim"] = semente["data_fim"] or ordem.data_evento_fim
        if not semente["servidores"]:
            semente["servidores"] = list(ordem.servidores.all())
        if not semente["motivo"]:
            semente["motivo"] = (ordem.motivo or "").strip()

    # 5. Termo de autorização.
    termo = viagem.termos_autorizacao.filter(cancelado=False).select_related("destino_cidade__estado", "destino_estado", "viatura").prefetch_related("servidores").order_by("-atualizado_em").first()
    if termo is not None:
        if semente["cidade"] is None and termo.destino_cidade_id:
            semente["cidade"], semente["estado"] = termo.destino_cidade, termo.destino_cidade.estado
        elif semente["estado"] is None and termo.destino_estado_id:
            semente["estado"] = termo.destino_estado
        semente["data_inicio"] = semente["data_inicio"] or termo.data_evento_inicio
        semente["data_fim"] = semente["data_fim"] or termo.data_evento_fim
        if not semente["servidores"]:
            semente["servidores"] = list(termo.servidores.all())
        if not semente["servidores_termo"]:
            semente["servidores_termo"] = list(termo.servidores.all())
        if semente["viatura"] is None:
            semente["viatura"] = termo.viatura

    if semente["data_fim"] is None:
        semente["data_fim"] = semente["data_inicio"]
    return semente


def destinos_para_formulario(semente):
    """[(estado_id, municipio_id)] dos destinos resolvidos, para linhas de destino."""
    if not semente:
        return []
    return [(estado.pk, cidade.pk) for cidade, estado in semente["destinos"] if cidade is not None and estado is not None]


@transaction.atomic
def excluir_viagem(viagem):
    """Apaga a viagem e os documentos só dela; roteiro usado fora dela é desvinculado."""
    from viagens_prestacoes.models import PrestacaoContas

    for roteiro in list(viagem.roteiros.all()):
        usado_fora = roteiro.oficios.exclude(viagem=viagem).exists() or PrestacaoContas.objects.filter(
            roteiro_ajustado=roteiro).exclude(oficio__viagem=viagem).exists()
        if usado_fora:
            roteiro.viagem = None
            roteiro.save(update_fields=["viagem", "atualizado_em"])
    excluir_com_protecao(viagem)


# ── Etapa 1: identificação, vínculos e o termo automático ─────────────────


def _sincronizar_documentos_vinculados(form, viagem):
    """O que a tela marcou ganha `viagem`; o que desmarcou perde — por `update`, sem `save()`."""
    from .forms import DOCUMENTOS_VINCULAVEIS

    for campo, relacao in DOCUMENTOS_VINCULAVEIS:
        if campo not in form.cleaned_data:
            continue
        gerente = getattr(viagem, relacao)
        escolhidos = {obj.pk for obj in form.cleaned_data[campo]}
        atuais = set(gerente.values_list("pk", flat=True))
        base = gerente.model.objects
        if escolhidos - atuais:
            base.filter(pk__in=escolhidos - atuais).update(viagem=viagem)
        if atuais - escolhidos:
            base.filter(pk__in=atuais - escolhidos).update(viagem=None)


@transaction.atomic
def salvar_identificacao_viagem(form):
    """Grava a etapa 1 inteira ou nada: o título nasce dos tipos ("Nova viagem" sem eles)."""
    viagem = form.save(commit=False)
    nomes = [tipo.nome for tipo in form.cleaned_data.get("tipos") or []]
    viagem.titulo = " / ".join(nomes) if nomes else "Nova viagem"
    viagem.save()
    form.save_m2m()
    _sincronizar_documentos_vinculados(form, viagem)
    garantir_termo_automatico(viagem)
    return viagem


def garantir_termo_automatico(viagem):
    """Cria um termo vazio da viagem se ainda não houver nenhum — como na origem."""
    from viagens_termos.models import TermoAutorizacao

    from .selectors import existe_termo_da_viagem

    if existe_termo_da_viagem(viagem):
        return
    semente = semente_de_documentos(viagem)
    TermoAutorizacao.objects.create(
        viagem=viagem, destino_estado=semente["estado"], destino_cidade=semente["cidade"],
        data_evento_inicio=viagem.data_inicio, data_evento_fim=viagem.data_fim or viagem.data_inicio,
    )


# ── Etapa 4: documentos de solicitação ─────────────────────────────────────


def converter_para_pdf_se_necessario(arquivo):
    """Imagem reconhecida pelo Pillow vira PDF; PDF passa direto.

    A foto ou o print é conveniência de upload; o que fica guardado é sempre
    PDF, no mesmo formato dos demais documentos da viagem.
    """
    from io import BytesIO
    from pathlib import Path

    from django.core.files.base import ContentFile
    from PIL import Image

    if Path(arquivo.name).suffix.lower() == ".pdf":
        return arquivo
    imagem = Image.open(arquivo)
    if imagem.mode != "RGB":
        imagem = imagem.convert("RGB")
    buffer = BytesIO()
    imagem.save(buffer, format="PDF")
    return ContentFile(buffer.getvalue(), name=f"{Path(arquivo.name).stem}.pdf")


def anexar_documentos_solicitacao(viagem, arquivos_pdf):
    from pathlib import Path

    from .models import ViagemDocumentoSolicitacao

    for arquivo in arquivos_pdf:
        ViagemDocumentoSolicitacao.objects.create(viagem=viagem, arquivo=arquivo, nome_original=Path(arquivo.name).name)


def excluir_documento_solicitacao(anexo):
    """Apaga o arquivo do disco antes do registro — a ordem importa."""
    anexo.arquivo.delete(save=False)
    anexo.delete()


# ── O painel: as cinco etapas ──────────────────────────────────────────────

TOTAL_ETAPAS = 5


def normalizar_etapa(etapa):
    try:
        return max(1, min(int(etapa or 1), TOTAL_ETAPAS))
    except (TypeError, ValueError):
        return 1


def _dados_completos(viagem):
    return bool(viagem.titulo and viagem.data_inicio and (viagem.destino_municipio_id or viagem.destino_estado_id))


def contexto_das_etapas(viagem, etapa_atual=1):
    """As cinco etapas do painel, todas navegáveis: a viagem é um hub, não um wizard."""
    from django.urls import reverse

    etapa_atual = normalizar_etapa(etapa_atual)
    definicao = [
        (1, "Dados da viagem", _dados_completos(viagem)),
        (2, "Roteiros", viagem.roteiros.exists()),
        (3, "Ofícios / Justificativas", viagem.oficios.exists()),
        (4, "PT / OS", viagem.planos_trabalho.exists() or viagem.ordens_servico.exists()),
        (5, "Termos", viagem.termos_autorizacao.exists()),
    ]
    etapas = []
    for numero, titulo, concluida in definicao:
        atual = numero == etapa_atual
        etapas.append({
            "numero": numero, "titulo": titulo, "atual": atual, "concluida": concluida and not atual,
            "estado": "Atual" if atual else ("Concluída" if concluida else "Pendente"),
            "url": reverse("viagens_viagem:etapa", args=[viagem.pk, numero]),
        })
    return {
        "etapa_atual": etapa_atual,
        "etapas": etapas,
        "titulo_da_etapa": next(e["titulo"] for e in etapas if e["atual"]),
        "total_etapas": TOTAL_ETAPAS,
    }
