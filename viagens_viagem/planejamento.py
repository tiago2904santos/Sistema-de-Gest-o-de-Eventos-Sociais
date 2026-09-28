"""Planejamento semiautomático: o que as viagens já feitas ensinam.

Ninguém escreveu as regras de como a equipe vai a cada cidade — elas estão
nos ofícios já emitidos. Aqui o sistema lê esse histórico (o do próprio
banco: nada sai do servidor) e devolve o planejamento de uma viagem nova:

- os horários do roteiro (`planejar_horarios`): a que horas e em que dia a
  equipe costuma sair e voltar, primeiro das viagens à mesma cidade, depois
  das de distância parecida e, sem histórico, a regra de sempre (ida às 08:00
  do primeiro dia, volta às 16:00 do último);
- quem costuma ir e em qual viatura (`sugestoes_de_equipe`): só ordena a
  lista da tela "Gerar documentos" — escolher a equipe continua sendo da
  pessoa;
- o que o ofício pede além da equipe (`completar_oficio`): motivo pelo modelo
  padrão, custeio quando as viagens àquela cidade sempre tiveram o mesmo, e a
  justificativa (quando o prazo a exige) com o modelo mais usado.

Conta como exemplo toda viagem que chegou a ter ofício: é a que alguém
revisou. Viagem cancelada, ofício cancelado e roteiro cancelado ficam fora.
"""

from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, time, timedelta

from django.utils import timezone

IDA_PADRAO = time(8, 0)
VOLTA_PADRAO = time(16, 0)

#: Faixas de tempo de viagem (min) que contam como "distância parecida".
FAIXAS_DE_TEMPO = (90, 180, 300, 480)

#: Uma saída a mais de 3 dias do evento não é padrão, é outra coisa (erro de
#: digitação, viagem remarcada): não ensina nada.
DESLOCAMENTO_MAXIMO = 3

#: O custeio só é copiado quando as viagens à cidade concordam.
CUSTEIO_MINIMO_AMOSTRAS = 2
CUSTEIO_CONCORDANCIA = 0.6


@dataclass
class Amostra:
    """Um roteiro de viagem feita: para onde, de onde, quanto tempo e os horários."""

    roteiro_id: int
    sede_id: int | None
    destinos: set
    tempo_min: int | None
    ida: tuple | None  # (dias em relação ao 1º dia do evento ou None, "HH:MM")
    volta: tuple | None  # (dias em relação ao último dia ou None, "HH:MM")


@dataclass
class PlanoDeHorarios:
    ida: datetime
    volta: datetime
    base: str  # "cidade", "distancia" ou "padrao"
    amostras: int = 0
    explicacao: str = ""


@dataclass
class SugestoesDeEquipe:
    servidores: Counter = field(default_factory=Counter)
    motoristas: Counter = field(default_factory=Counter)
    viaturas: Counter = field(default_factory=Counter)
    viagens: int = 0


# ── O histórico ────────────────────────────────────────────────────────────


def _hora(dt):
    """A hora local arredondada a 15 minutos, como a pessoa digita."""
    local = timezone.localtime(dt)
    minutos = int(round((local.hour * 60 + local.minute) / 15.0) * 15)
    minutos = min(minutos, 23 * 60 + 45)
    return f"{minutos // 60:02d}:{minutos % 60:02d}"


def _deslocamento(dt, referencia):
    if referencia is None:
        return None
    dias = (timezone.localdate(dt) - referencia).days
    return dias if abs(dias) <= DESLOCAMENTO_MAXIMO else None


def _periodo_do_evento(oficio, roteiro):
    viagem = oficio.viagem if oficio.viagem_id else None
    if viagem is not None and viagem.data_inicio:
        return viagem.data_inicio, viagem.data_fim or viagem.data_inicio
    solicitacao = roteiro.solicitacao if roteiro.solicitacao_id else None
    if solicitacao is not None and solicitacao.data_inicio_evento:
        return solicitacao.data_inicio_evento, solicitacao.data_fim_evento or solicitacao.data_inicio_evento
    return None, None


def _amostra(oficio):
    from viagens_roteiros.models import RoteiroTrecho

    roteiro = oficio.roteiro
    trechos = sorted(roteiro.trechos.all(), key=lambda t: (t.ordem, t.pk))
    idas = [t for t in trechos if t.sentido != RoteiroTrecho.Sentido.RETORNO]
    voltas = [t for t in trechos if t.sentido == RoteiroTrecho.Sentido.RETORNO]
    saida_ida = next((t.saida_dt for t in idas if t.saida_dt), None) or roteiro.saida_dt
    saida_volta = next((t.saida_dt for t in reversed(voltas) if t.saida_dt), None) or roteiro.retorno_saida_dt
    if saida_ida is None and saida_volta is None:
        return None
    destinos = {d.municipio_id for d in roteiro.destinos.all()} | {t.destino_municipio_id for t in idas if t.destino_municipio_id}
    destinos.discard(roteiro.origem_municipio_id)
    tempo = next((t.tempo_viagem_min or t.duracao_min for t in idas if t.tempo_viagem_min or t.duracao_min), None)
    inicio, fim = _periodo_do_evento(oficio, roteiro)
    return Amostra(
        roteiro_id=roteiro.pk,
        sede_id=roteiro.origem_municipio_id,
        destinos=destinos,
        tempo_min=tempo,
        ida=(_deslocamento(saida_ida, inicio), _hora(saida_ida)) if saida_ida else None,
        volta=(_deslocamento(saida_volta, fim), _hora(saida_volta)) if saida_volta else None,
    )


def _oficios_feitos(excluir_viagem=None):
    from viagens_oficios.models import Oficio

    oficios = Oficio.objects.filter(cancelado=False).exclude(viagem__cancelado=True)
    if excluir_viagem is not None and getattr(excluir_viagem, "pk", None):
        oficios = oficios.exclude(viagem=excluir_viagem)
    return oficios


def amostras_de_roteiros(excluir_viagem=None):
    """Um exemplo por roteiro de viagem feita (vários ofícios dividem o roteiro)."""
    oficios = (
        _oficios_feitos(excluir_viagem)
        .filter(roteiro__isnull=False, roteiro__cancelado=False)
        .select_related("viagem", "roteiro__solicitacao")
        .prefetch_related("roteiro__trechos", "roteiro__destinos")
        .order_by("roteiro_id", "pk")
    )
    amostras, vistos = [], set()
    for oficio in oficios:
        if oficio.roteiro_id in vistos:
            continue
        vistos.add(oficio.roteiro_id)
        amostra = _amostra(oficio)
        if amostra is not None:
            amostras.append(amostra)
    return amostras


# ── Horários do roteiro ────────────────────────────────────────────────────


def _faixa(tempo_min):
    if not tempo_min:
        return None
    return sum(1 for limite in FAIXAS_DE_TEMPO if tempo_min > limite)


def _padrao(pontos):
    """(deslocamento, hora) mais comum. O dia vem de quem tem data; a hora, dos daquele dia."""
    pontos = [p for p in pontos if p is not None]
    if not pontos:
        return None
    dias = Counter(d for d, _ in pontos if d is not None)
    dia = dias.most_common(1)[0][0] if dias else 0
    horas = Counter(h for d, h in pontos if d == dia) or Counter(h for _, h in pontos)
    return dia, horas.most_common(1)[0][0]


def _dia_por_extenso(dias, *, volta):
    if dias == 0:
        return "do último dia" if volta else "do dia do evento"
    if dias < 0:
        return "da véspera" if dias == -1 else f"de {-dias} dias antes"
    return "do dia seguinte" if dias == 1 else f"de {dias} dias depois"


def _quando(padrao, referencia, hora_padrao):
    dias, hora = padrao if padrao else (0, f"{hora_padrao:%H:%M}")
    h, m = (int(p) for p in hora.split(":"))
    return timezone.make_aware(datetime.combine(referencia + timedelta(days=dias), time(h, m)))


def planejar_horarios(sede, municipio, inicio, fim, *, tempo_min=None, amostras=None, excluir_viagem=None):
    """Quando a equipe sai e quando volta, pelo que as viagens feitas mostram."""
    fim = fim or inicio
    if amostras is None:
        amostras = amostras_de_roteiros(excluir_viagem)
    mesma_sede = [a for a in amostras if sede is None or a.sede_id in (None, getattr(sede, "pk", None))]
    base, grupo = "padrao", []
    if municipio is not None:
        grupo = [a for a in mesma_sede if municipio.pk in a.destinos]
        base = "cidade" if grupo else base
    if not grupo and _faixa(tempo_min) is not None:
        faixa = _faixa(tempo_min)
        grupo = [a for a in mesma_sede if _faixa(a.tempo_min) == faixa]
        base = "distancia" if grupo else base
    ida_padrao = _padrao([a.ida for a in grupo])
    volta_padrao = _padrao([a.volta for a in grupo])
    ida = _quando(ida_padrao, inicio, IDA_PADRAO)
    volta = _quando(volta_padrao, fim, VOLTA_PADRAO)
    # A volta tem de caber depois da chegada; senão o histórico não serve aqui.
    if volta <= ida + timedelta(minutes=tempo_min or 0):
        ida = _quando(None, inicio, IDA_PADRAO)
        volta = _quando(None, fim, VOLTA_PADRAO)
        base, grupo, ida_padrao, volta_padrao = "padrao", [], None, None
    return PlanoDeHorarios(ida=ida, volta=volta, base=base, amostras=len(grupo),
                           explicacao=_explicar(base, len(grupo), municipio, ida_padrao, volta_padrao, ida, volta))


def _explicar(base, quantas, municipio, ida_padrao, volta_padrao, ida, volta):
    ida_txt = f"saída às {timezone.localtime(ida):%H:%M} {_dia_por_extenso(ida_padrao[0] if ida_padrao else 0, volta=False)}"
    volta_txt = f"volta às {timezone.localtime(volta):%H:%M} {_dia_por_extenso(volta_padrao[0] if volta_padrao else 0, volta=True)}"
    plural = "viagem" if quantas == 1 else "viagens"
    if base == "cidade":
        return f"Como {'na' if quantas == 1 else 'nas'} {quantas} {plural} a {municipio.nome}: {ida_txt}, {volta_txt}."
    if base == "distancia":
        return f"Sem viagem anterior a {municipio.nome}; como {'na' if quantas == 1 else 'nas'} {quantas} {plural} de distância parecida: {ida_txt}, {volta_txt}."
    return f"Sem histórico parecido: {ida_txt}, {volta_txt} (o horário de sempre)."


# ── A equipe que costuma ir ────────────────────────────────────────────────


def sugestoes_de_equipe(viagem):
    """Quem foi, quem dirigiu e qual viatura saiu nas viagens parecidas com esta.

    Parecida: mesmo tipo de viagem ou mesma cidade. Quem foi à mesma cidade
    conta em dobro (conhece o caminho, o local, o contato).
    """
    sugestoes = SugestoesDeEquipe()
    tipos = list(viagem.tipos.values_list("pk", flat=True)) if viagem.pk else []
    cidade = viagem.destino_municipio_id
    oficios = (
        _oficios_feitos(viagem)
        .filter(viagem__isnull=False)
        .select_related("roteiro")
        .prefetch_related("servidores", "viagem__tipos", "roteiro__destinos")
    )
    viagens = set()
    for oficio in oficios:
        mesma_cidade = bool(cidade) and (
            oficio.viagem.destino_municipio_id == cidade
            or (oficio.roteiro_id and any(d.municipio_id == cidade for d in oficio.roteiro.destinos.all()))
        )
        mesmo_tipo = bool(tipos) and any(t.pk in tipos for t in oficio.viagem.tipos.all())
        if not (mesma_cidade or mesmo_tipo):
            continue
        peso = 2 if mesma_cidade else 1
        viagens.add(oficio.viagem_id)
        for servidor in oficio.servidores.all():
            sugestoes.servidores[servidor.pk] += peso
        if oficio.motorista_id:
            sugestoes.motoristas[oficio.motorista_id] += peso
        if oficio.viatura_id:
            sugestoes.viaturas[oficio.viatura_id] += peso
    sugestoes.viagens = len(viagens)
    return sugestoes


# ── O que o ofício pede além da equipe ─────────────────────────────────────


def _custeio_da_cidade(oficio):
    """O custeio em que as viagens à mesma cidade concordam, ou None."""
    viagem = oficio.viagem
    if viagem is None or not viagem.destino_municipio_id:
        return None
    anteriores = list(
        _oficios_feitos(viagem).filter(viagem__destino_municipio_id=viagem.destino_municipio_id)
        .values_list("custeio", "custeio_observacao")
    )
    if len(anteriores) < CUSTEIO_MINIMO_AMOSTRAS:
        return None
    custeio, n = Counter(c for c, _ in anteriores).most_common(1)[0]
    if n / len(anteriores) < CUSTEIO_CONCORDANCIA:
        return None
    observacoes = Counter(o.strip() for c, o in anteriores if c == custeio and o.strip())
    observacao = observacoes.most_common(1)[0][0] if observacoes else ""
    return custeio, observacao, n


def modelo_de_justificativa():
    """O modelo que as justificativas já escritas mais usaram; sem uso, o padrão."""
    from viagens_oficios.models import Justificativa, ModeloJustificativa

    usados = Counter(
        Justificativa.objects.filter(modelo__isnull=False).exclude(texto="").exclude(oficio__cancelado=True)
        .values_list("modelo_id", flat=True)
    )
    if usados:
        modelo = ModeloJustificativa.objects.filter(pk=usados.most_common(1)[0][0]).first()
        if modelo is not None:
            return modelo
    return ModeloJustificativa.objects.filter(is_padrao=True).first()


def completar_oficio(oficio):
    """Preenche o que o histórico permite e devolve o que foi preenchido (textos curtos)."""
    from viagens_oficios.campos_modelo import aplicar, valores_do_oficio
    from viagens_oficios.justificativas_services import (
        get_or_create_justificativa_oficio, justificativa_oficio_esta_completa, oficio_exige_justificativa,
    )
    from viagens_oficios.models import ModeloMotivoOficio, Oficio

    feito, campos = [], []
    if not (oficio.motivo or "").strip():
        modelo = ModeloMotivoOficio.objects.filter(is_padrao=True).first()
        if modelo is not None:
            oficio.motivo = aplicar(modelo.texto, valores_do_oficio(oficio))
            campos.append("motivo")
            feito.append(f"motivo pelo modelo {modelo.nome}")
    custeio = _custeio_da_cidade(oficio)
    if custeio is not None:
        valor, observacao, n = custeio
        if valor != oficio.custeio or (observacao and not oficio.custeio_observacao):
            oficio.custeio = valor
            if valor == Oficio.CUSTEIO_OUTRA_INSTITUICAO and observacao and not oficio.custeio_observacao:
                oficio.custeio_observacao = observacao
            campos += ["custeio", "custeio_observacao"]
            rotulo = dict(Oficio.CUSTEIO_CHOICES).get(valor, valor)
            feito.append(f"custeio \"{rotulo}\", como nas {n} viagens anteriores a {oficio.viagem.destino_municipio.nome}")
    if campos:
        oficio.save(update_fields=[*dict.fromkeys(campos), "atualizado_em"])
    if oficio_exige_justificativa(oficio) and not justificativa_oficio_esta_completa(oficio):
        modelo = modelo_de_justificativa()
        if modelo is not None:
            justificativa = get_or_create_justificativa_oficio(oficio)
            justificativa.modelo = modelo
            justificativa.texto = aplicar(modelo.texto, valores_do_oficio(oficio))
            justificativa.save(update_fields=["modelo", "texto", "atualizado_em"])
            feito.append(f"justificativa pelo modelo {modelo.nome} (o prazo exige)")
    return feito
