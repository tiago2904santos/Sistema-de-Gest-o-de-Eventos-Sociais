from datetime import timedelta
from django.db import transaction
from django.utils import timezone
from core.numeracao import NAMESPACE_OFICIO, reservar_numero
from core.deletion import excluir_com_protecao, DelecaoProtegidaError
from .models import Oficio, OficioNumeroLacuna, CONSTRAINT_NUMERO_OFICIO

def get_next_available_numero_oficio(ano):
    # Fonte única da lógica de numeração (inclui o piso por ano via settings).
    return Oficio.get_next_available_numero(ano)


def _numero_de_oficio_ocupado(oficio, *, numero: int, ano: int) -> bool:
    """Verifica ocupação global quando o banco não informa a constraint."""
    return (
        Oficio.objects.filter(ano=ano, numero=numero)
        .exclude(pk=oficio.pk)
        .exists()
    )


@transaction.atomic
def reservar_numero_oficio(oficio, ano=None):
    if oficio.numero and oficio.ano:
        return oficio

    resolved_year = ano or timezone.localdate().year
    original_pk = oficio.pk
    original_adding = oficio._state.adding

    def escolher():
        return get_next_available_numero_oficio(resolved_year)

    def gravar(numero):
        oficio.ano = resolved_year
        oficio.numero = numero
        oficio.save()

    def limpar():
        oficio.numero = None
        oficio.ano = None
        if original_adding:
            oficio.pk = original_pk
            oficio._state.adding = True

    reservar_numero(
        namespace=NAMESPACE_OFICIO,
        ano=resolved_year,
        modelo=Oficio,
        constraint=CONSTRAINT_NUMERO_OFICIO,
        escolher=escolher,
        gravar=gravar,
        ja_ocupado=lambda numero: _numero_de_oficio_ocupado(
            oficio, numero=numero, ano=resolved_year
        ),
        apos_colisao=limpar,
    )
    return oficio

# Um rascunho aberto e abandonado não pode prender outro número: o próximo
# "Novo ofício" o reaproveita. A folga evita entregar a outra pessoa o
# rascunho que alguém acabou de abrir e ainda vai preencher.
FOLGA_RASCUNHO_VAZIO = timedelta(minutes=30)


def rascunho_vazio_disponivel(ano):
    from django.db.models import Q
    limite = timezone.now() - FOLGA_RASCUNHO_VAZIO
    return (
        Oficio.objects.filter(
            status=Oficio.STATUS_RASCUNHO, cancelado=False, ano=ano, numero__isnull=False,
            legado_pk__isnull=True, roteiro__isnull=True, viatura__isnull=True, motorista__isnull=True,
            protocolo="", motivo="", motorista_manual_nome="", atualizado_em__lt=limite,
        )
        .exclude(Q(servidores__isnull=False) | Q(artefatos__isnull=False) | Q(justificativa__isnull=False))
        .order_by("numero")
        .first()
    )


@transaction.atomic
def criar_oficio_rascunho(viagem=None):
    """O rascunho já numerado do "Novo ofício".

    Com `viagem`, o ofício nasce preso a ela e herda só o motivo da semente
    e a unidade responsável como solicitante — como na origem: servidores e
    viatura não vêm de outros ofícios da mesma viagem, cada um tem a sua
    equipe.
    """
    hoje = timezone.localdate()
    heranca = {}
    if viagem is not None:
        from viagens_viagem.services import semente_de_documentos

        semente = semente_de_documentos(viagem)
        heranca = {"viagem": viagem, "motivo": semente["motivo"] or "", "solicitante": viagem.unidade_responsavel}
    vazio = rascunho_vazio_disponivel(hoje.year)
    if vazio is not None:
        # Reaberto como novo: a data volta a ser a de hoje.
        vazio.data_criacao = hoje
        for campo, valor in heranca.items():
            setattr(vazio, campo, valor)
        vazio.save(update_fields=["data_criacao", "atualizado_em", *heranca])
        return vazio
    oficio = Oficio.objects.create(**heranca)
    return reservar_numero_oficio(oficio, ano=oficio.data_criacao.year)


class OficioVinculadoError(DelecaoProtegidaError):
    pass


@transaction.atomic
def excluir_oficio(instance):
    numero, ano = instance.numero, instance.ano
    try:
        excluir_com_protecao(instance)
    except DelecaoProtegidaError as exc:
        raise OficioVinculadoError from exc
    if numero and ano:
        OficioNumeroLacuna.objects.get_or_create(ano=ano, numero=numero)

import re
from core.utils.masks import format_placa, format_protocolo, normalize_protocolo
from .assunto_oficio import resolver_assunto_oficio

def avaliar_oficio_transporte(oficio):
    if oficio is None:
        return {"status": "not_started", "pendencias": []}
    tem_viatura = bool(oficio.viatura_id) or bool((oficio.transporte_placa_manual or "").strip())
    tem_motorista = bool(oficio.motorista_id) or (
        oficio.motorista_modo == Oficio.MOTORISTA_MODO_MANUAL and (oficio.motorista_manual_nome or "").strip()
    )
    if tem_viatura and tem_motorista:
        status = "complete"
    elif not tem_viatura and not tem_motorista:
        status = "not_started"
    else:
        status = "incomplete"
    return {"status": status, "pendencias": []}

def avaliar_oficio_dados_viajantes(oficio=None, form=None):
    if form is not None:
        values = _dados_viajantes_from_form(form)
    elif oficio is not None:
        values = _dados_viajantes_from_oficio(oficio)
    else:
        values = {}

    pendencias = []
    if not values.get("protocolo"):
        pendencias.append("Informe o protocolo.")
    if not values.get("motivo"):
        pendencias.append("Informe o motivo.")
    if not values.get("custeio"):
        pendencias.append("Informe o custeio.")
    if values.get("custeio") == Oficio.CUSTEIO_OUTRA_INSTITUICAO and not values.get("custeio_observacao"):
        pendencias.append("Informe a observação de custeio.")
    if not values.get("servidores_count"):
        pendencias.append("Selecione ao menos um viajante.")

    if not values.get("has_started"):
        status = "not_started"
    elif pendencias:
        status = "incomplete"
    else:
        status = "complete"
    return {"status": status, "pendencias": pendencias}

def pendencias_motorista_documento(oficio):
    pendencias = []
    modo = oficio.motorista_modo or Oficio.MOTORISTA_MODO_SERVIDOR
    if modo == Oficio.MOTORISTA_MODO_MANUAL:
        nome = (oficio.motorista_manual_nome or "").strip()
        if not nome:
            pendencias.append("Informe o nome do motorista.")
            return pendencias
        pendencias.extend(_pendencias_oficio_protocolo_motorista(oficio))
        return pendencias
    if oficio.motorista_id:
        equipe = set(oficio.servidores.values_list("pk", flat=True))
        if oficio.motorista_id not in equipe:
            pendencias.extend(_pendencias_oficio_protocolo_motorista(oficio))
    return pendencias

def _pendencias_oficio_protocolo_motorista(oficio):
    pendencias = []
    ref = (oficio.motorista_oficio_referencia or "").strip()
    if not ref or not re.match(r"^\d{1,3}/\d{4}$", ref):
        pendencias.append("Informe o ofício do motorista no formato número/ano.")
    proto = normalize_protocolo(oficio.motorista_protocolo_ref or "")
    if len(proto) != 9:
        pendencias.append("Informe o protocolo do motorista com 9 dígitos.")
    return pendencias

def _pendencias_transporte_documento(oficio):
    av = avaliar_oficio_transporte(oficio)
    if av["status"] == "complete":
        return []
    return ["Complete o transporte (viatura ou placa manual e motorista)."]

def _pendencias_roteiro_documento(oficio):
    from viagens_oficios.justificativas_services import get_primeira_saida_oficio

    pendencias = []
    if not oficio.roteiro_id:
        pendencias.append("Associe um roteiro ao ofício.")
        return pendencias
    roteiro = oficio.roteiro
    if not (roteiro.origem_municipio_id or getattr(roteiro.origem_municipio, "estado_id", None)):
        pendencias.append("Informe a sede ou origem do roteiro.")
    if get_primeira_saida_oficio(oficio) is None:
        pendencias.append("Informe a data da primeira saída no roteiro.")
    if not roteiro.destinos.exists() and not roteiro.trechos.exists():
        pendencias.append("Informe destinos ou trechos no roteiro.")
    return pendencias

def _pendencias_justificativa_documento(oficio):
    from viagens_oficios.justificativas_services import justificativa_oficio_esta_completa
    from viagens_oficios.justificativas_services import oficio_exige_justificativa

    if not oficio_exige_justificativa(oficio):
        return []
    if not justificativa_oficio_esta_completa(oficio):
        return ["Informe a justificativa obrigatória para este ofício."]
    return []

def validar_oficio_para_documento(oficio):
    dados = avaliar_oficio_dados_viajantes(oficio=oficio)
    pendencias = list(dados["pendencias"])
    checks = {"dados_viajantes": dados["status"]}

    mot = pendencias_motorista_documento(oficio)
    pendencias.extend(mot)
    checks["motorista_documento"] = "complete" if not mot else "incomplete"

    transp_extra = _pendencias_transporte_documento(oficio)
    pendencias.extend(transp_extra)
    checks["transporte"] = avaliar_oficio_transporte(oficio)["status"]

    rot_extra = _pendencias_roteiro_documento(oficio)
    pendencias.extend(rot_extra)
    checks["roteiro"] = "complete" if not rot_extra else "incomplete"

    just_extra = _pendencias_justificativa_documento(oficio)
    pendencias.extend(just_extra)
    checks["justificativa"] = "complete" if not just_extra else "incomplete"

    checks["documento"] = "complete"

    status = "complete" if not pendencias else "incomplete"
    return {"status": status, "pendencias": pendencias, "checks": checks}

def oficio_esta_completo_para_finalizar(oficio: Oficio) -> bool:
    """Indica se o ofício cumpre requisitos documentais, sem considerar assinatura digital."""
    return validar_oficio_para_documento(oficio)["status"] == "complete"

def _dados_viajantes_from_form(form):
    if form.is_bound:
        data = form.cleaned_data if form.is_valid() else form.data
        get_value = data.get
        servidores = (
            list(get_value("servidores") or [])
            if hasattr(data, "get")
            else []
        )
        if not servidores and hasattr(form.data, "getlist"):
            servidores = form.data.getlist("servidores")
        text_values = [
            get_value("assunto", ""),
            get_value("motivo", ""),
            get_value("protocolo", ""),
            get_value("custeio_observacao", ""),
        ]
        has_started = form.is_bound or any(str(value).strip() for value in text_values) or bool(servidores)
        return {
            "data_criacao": get_value("data_criacao"),
            "motivo": str(get_value("motivo", "") or "").strip(),
            "protocolo": str(get_value("protocolo", "") or "").strip(),
            "custeio": get_value("custeio"),
            "custeio_observacao": str(get_value("custeio_observacao", "") or "").strip(),
            "servidores_count": len(servidores),
            "has_started": has_started,
        }
    instance = getattr(form, "instance", None)
    return _dados_viajantes_from_oficio(instance) if instance and instance.pk else {}

def _dados_viajantes_from_oficio(oficio):
    if oficio is None:
        return {}
    text_values = [oficio.motivo, oficio.protocolo, oficio.custeio_observacao]
    servidores_count = oficio.servidores.count() if oficio.pk else 0
    return {
        "data_criacao": oficio.data_criacao,
        "motivo": oficio.motivo.strip(),
        "protocolo": oficio.protocolo.strip(),
        "custeio": oficio.custeio,
        "custeio_observacao": oficio.custeio_observacao.strip(),
        "servidores_count": servidores_count,
        "has_started": bool(oficio.pk) or any(value.strip() for value in text_values) or bool(servidores_count),
    }

def cancelar_oficio(instance: Oficio, motivo: str) -> Oficio:
    """Cancela o ofício, preservando seu número e seu histórico."""
    instance.cancelar(motivo)
    return instance

def retificar_oficio(instance: Oficio) -> Oficio:
    """Marca o ofício como retificado: o documento passa a exibir "Retificado"
    ao lado do número no lugar de "Autorização". Mutuamente exclusivo com a
    marcação de complementar."""
    instance.retificado_documento = True
    instance.complementar_documento = False
    instance.save(update_fields=["retificado_documento", "complementar_documento"])
    return instance

def desfazer_retificacao_oficio(instance: Oficio) -> Oficio:
    instance.retificado_documento = False
    instance.save(update_fields=["retificado_documento"])
    return instance

def marcar_oficio_complementar(instance: Oficio) -> Oficio:
    """Marca o ofício como complementar: o documento passa a exibir "Complementar"
    ao lado do número. Mutuamente exclusivo com a retificação."""
    instance.complementar_documento = True
    instance.retificado_documento = False
    instance.save(update_fields=["retificado_documento", "complementar_documento"])
    return instance

def desfazer_complementar_oficio(instance: Oficio) -> Oficio:
    instance.complementar_documento = False
    instance.save(update_fields=["complementar_documento"])
    return instance

def build_oficio_document_payload(oficio):
    viatura_label = ""
    if oficio.viatura_id:
        viatura_label = oficio.viatura.placa_formatada
    elif (oficio.transporte_placa_manual or "").strip():
        viatura_label = format_placa(oficio.transporte_placa_manual)
    motorista_label = ""
    if oficio.motorista_id:
        motorista_label = oficio.motorista.nome
    elif oficio.motorista_modo == Oficio.MOTORISTA_MODO_MANUAL:
        motorista_label = (oficio.motorista_manual_nome or "").strip()
    assunto_doc = resolver_assunto_oficio(oficio)
    return {
        "numero": oficio.numero,
        "ano": oficio.ano,
        "numero_formatado": oficio.numero_formatado,
        "protocolo": format_protocolo(oficio.protocolo),
        "assunto": oficio.assunto,
        "assunto_oficio": assunto_doc["assunto_oficio"],
        "assunto_linha": assunto_doc["assunto_linha"],
        "motivo": oficio.motivo,
        "data_criacao": oficio.data_criacao,
        "status": oficio.status,
        "roteiro": str(oficio.roteiro) if oficio.roteiro else "",
        "servidores": [servidor.nome for servidor in oficio.servidores.all()],
        "viatura": viatura_label,
        "motorista": motorista_label,
        "custeio": oficio.custeio,
    }

