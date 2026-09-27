"""Em que setor o processo do ofício está no eProtocolo (m105).

A integração (`integracoes.eprotocolo`) já sabia consultar um protocolo —
situação, setor atual e última movimentação — mas nenhuma tela usava isso. Aqui
a consulta é guardada na prestação e mostrada na linha do ofício ("Processo em:
[setor] desde dd/mm"), atualizada uma vez por dia pela rotina de `core/rotinas.py`
e na hora pelo botão "Atualizar".

**Lembrete:** enquanto a instalação não tiver as credenciais da Celepar, a
integração responde em modo simulado — o setor e a situação são fictícios, e a
prestação guarda `protocolo_simulado=True` para a tela dizer SIMULADO. Nada aqui
grava no eProtocolo: é só consulta.

Quando o processo chega ao setor configurado em `ConfiguracaoSistema.
setor_despacho_eprotocolo` (o que emite o despacho das diárias), a equipe recebe
um aviso no sino: sinal de que já dá para baixar o processo e importá-lo na
prestação. O aviso sai uma vez por chegada.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime

from django.urls import reverse
from django.utils import timezone

from core.normalizers import remove_accents
from integracoes.eprotocolo import services as epro
from integracoes.eprotocolo.exceptions import EProtocoloError

from .models import PrestacaoContas


@dataclass(frozen=True)
class ResultadoConsulta:
    """O que a consulta fez: `erro` vazio quando gravou; `avisou` quando o processo chegou ao setor."""

    erro: str = ""
    simulado: bool = False
    avisou: bool = False

    @property
    def ok(self) -> bool:
        return not self.erro


def _situacao_legivel(valor) -> str:
    texto = str(valor or "").replace("_", " ").strip()
    return texto[:1].upper() + texto[1:].lower() if texto else ""


def _momento(valor):
    if not valor:
        return None
    try:
        momento = datetime.fromisoformat(str(valor).replace("Z", "+00:00"))
    except ValueError:
        return None
    return momento if timezone.is_aware(momento) else timezone.make_aware(momento, timezone.utc)


def consultar_protocolo_da_prestacao(prestacao: PrestacaoContas) -> ResultadoConsulta:
    """Consulta o protocolo do ofício e guarda situação, setor e data na prestação. Nunca levanta exceção."""
    numero = re.sub(r"\D", "", prestacao.oficio.protocolo or "")
    if not numero:
        return ResultadoConsulta(erro="O ofício ainda não tem número de protocolo.")
    try:
        resultado = epro.consultar_protocolo(numero)
    except EProtocoloError as exc:
        return ResultadoConsulta(erro=f"Não foi possível consultar o eProtocolo agora: {exc}")
    except Exception:  # noqa: BLE001 - a lista e a rotina não podem cair por causa da consulta
        return ResultadoConsulta(erro="Não foi possível consultar o eProtocolo agora.")
    dados = resultado.dados or {}
    prestacao.protocolo_situacao = _situacao_legivel(dados.get("situacao"))[:60]
    prestacao.protocolo_local = str(dados.get("nomeLocalAtual") or dados.get("codLocalAtual") or "")[:160]
    prestacao.protocolo_movimentado_em = _momento(dados.get("ultimaMovimentacao"))
    prestacao.protocolo_consultado_em = timezone.now()
    prestacao.protocolo_simulado = bool(resultado.mock)
    prestacao.save(update_fields=[
        "protocolo_situacao", "protocolo_local", "protocolo_movimentado_em",
        "protocolo_consultado_em", "protocolo_simulado", "atualizado_em",
    ])
    return ResultadoConsulta(simulado=bool(resultado.mock), avisou=avisar_chegada_no_setor(prestacao))


def setores_do_despacho() -> list[str]:
    """Os setores configurados (na configuração global e nas dos setores), sem repetir."""
    from viagens_cadastros.models import ConfiguracaoSistema

    valores = ConfiguracaoSistema.objects.exclude(setor_despacho_eprotocolo="").values_list("setor_despacho_eprotocolo", flat=True)
    return list(dict.fromkeys(v.strip() for v in valores if v.strip()))


def _mesmo_setor(local: str, configurado: str) -> bool:
    """"DAF/DP" bate com "DAF/DP - Divisão de Pessoal": sem acento, sem caixa, por conter."""
    a, b = remove_accents(local).casefold().strip(), remove_accents(configurado).casefold().strip()
    return bool(a and b) and (a == b or b in a or a in b)


def chegou_ao_setor_do_despacho(prestacao: PrestacaoContas, setores=None) -> bool:
    """`setores` é a lista de `setores_do_despacho()` já lida — a lista passa a mesma para todos os ofícios."""
    setores = setores_do_despacho() if setores is None else setores
    return any(_mesmo_setor(prestacao.protocolo_local, setor) for setor in setores)


def avisar_chegada_no_setor(prestacao: PrestacaoContas) -> bool:
    """O aviso no sino quando o processo está no setor do despacho. Uma vez por chegada."""
    from .avisos import _avisar_uma_vez

    if not chegou_ao_setor_do_despacho(prestacao):
        return False
    ps = prestacao.servidores_prestacao.order_by("pk").first()
    if ps is None:
        return False
    quando = prestacao.protocolo_movimentado_em or prestacao.protocolo_consultado_em
    quando = timezone.localtime(quando).strftime("%d/%m") if quando else ""
    marca = " (simulado)" if prestacao.protocolo_simulado else ""
    return _avisar_uma_vez(
        ps,
        f"Processo do Ofício {prestacao.oficio.numero_formatado} chegou em {prestacao.protocolo_local}{f' em {quando}' if quando else ''}{marca}",
        "O despacho deve estar saindo: baixe o processo no eProtocolo e importe-o na prestação.",
        link=reverse("viagens_prestacoes:index") + f"#pc-{prestacao.pk}-titulo",
    )


def prestacoes_para_consultar(hoje=None):
    """As prestações em aberto com protocolo que ainda não foram consultadas hoje."""
    hoje = hoje or timezone.localdate()
    inicio = timezone.make_aware(datetime.combine(hoje, datetime.min.time()), timezone.get_current_timezone())
    from django.db.models import Exists, OuterRef, Q

    from .models import PrestacaoServidor

    em_aberto = PrestacaoServidor.objects.filter(prestacao=OuterRef("pk"), finalizada=False, arquivada=False)
    return (
        PrestacaoContas.objects.filter(oficio__cancelado=False)
        .exclude(oficio__protocolo="")
        .exclude(oficio__protocolo__isnull=True)
        .filter(Exists(em_aberto))
        .filter(Q(protocolo_consultado_em__isnull=True) | Q(protocolo_consultado_em__lt=inicio))
        .select_related("oficio")
        .order_by("pk")
    )


def atualizar_protocolos(hoje=None) -> int:
    """A rotina diária: consulta cada prestação em aberto uma vez por dia. Devolve quantas consultou."""
    consultadas = 0
    for prestacao in prestacoes_para_consultar(hoje):
        if consultar_protocolo_da_prestacao(prestacao).ok:
            consultadas += 1
    return consultadas


def andamento_do_protocolo(prestacao: PrestacaoContas, setores=None) -> dict:
    """O que a linha do ofício mostra: "Processo em: [setor] desde dd/mm", a marca SIMULADO e o botão."""
    desde = prestacao.protocolo_movimentado_em or prestacao.protocolo_consultado_em
    return {
        "consultado": prestacao.protocolo_consultado_em is not None,
        "local": prestacao.protocolo_local,
        "situacao": prestacao.protocolo_situacao,
        "desde": timezone.localtime(desde).strftime("%d/%m") if desde else "",
        "consultado_em": timezone.localtime(prestacao.protocolo_consultado_em).strftime("%d/%m/%Y %H:%M") if prestacao.protocolo_consultado_em else "",
        "simulado": prestacao.protocolo_simulado,
        "no_setor_do_despacho": bool(prestacao.protocolo_local) and chegou_ao_setor_do_despacho(prestacao, setores),
        "atualizar_url": reverse("viagens_prestacoes:prestacao_protocolo_atualizar", args=[prestacao.pk]),
        "tem_protocolo": bool((prestacao.oficio.protocolo or "").strip()),
    }
