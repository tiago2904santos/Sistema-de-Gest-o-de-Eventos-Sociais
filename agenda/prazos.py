"""A camada de prazos e pautas da agenda (m129).

As fontes de ``agenda.fontes`` são compromissos: alguém vai a algum lugar num
dia. As daqui são datas-limite: o dia em que algo deixa de valer se ninguém
fizer nada — o saque das diárias de cada servidor, o deadline de um pedido da
imprensa, o fim da vigência de um contrato ou termo aditivo do coffee break, a
validade das certidões de cada fornecedor. E as pautas de Publicações, que têm
dia e horário e por isso cabem no calendário do mesmo jeito.

Cada prazo vira um evento de um dia, com ``ag-prazo`` e, conforme a distância
de hoje, ``ag-prazo--vencido`` (já passou) ou ``ag-prazo--proximo`` (vence em
até ``DIAS_DE_AVISO`` dias). A permissão é a do módulo de origem, como nas
outras fontes: quem não abre Coffee Break não vê contrato nenhum aqui.

Os dossiês (``CONSTRUTORES``) seguem o formato de ``agenda.detalhes`` e são
registrados lá.
"""

from __future__ import annotations

import datetime as dt

from django.core.exceptions import PermissionDenied
from django.http import Http404
from django.urls import reverse
from django.utils import timezone

from .fontes import Fonte, _evento

#: Até quantos dias antes o prazo entra em destaque.
DIAS_DE_AVISO = 7


def _hoje() -> dt.date:
    return timezone.localdate()


def _situacao_do_prazo(data: dt.date, hoje: dt.date | None = None) -> tuple[str, str, list[str]]:
    """(rótulo, slug, classes extras) de um prazo em relação a hoje."""
    hoje = hoje or _hoje()
    faltam = (data - hoje).days
    if faltam < 0:
        return "Vencido", "vencido", ["ag-prazo", "ag-prazo--vencido"]
    if faltam == 0:
        return "Vence hoje", "proximo", ["ag-prazo", "ag-prazo--proximo"]
    if faltam <= DIAS_DE_AVISO:
        return f"Vence em até {DIAS_DE_AVISO} dias", "proximo", ["ag-prazo", "ag-prazo--proximo"]
    return "No prazo", "no_prazo", ["ag-prazo"]


def _prazo(*, fonte, pk, chave="", titulo, data, url, detalhes, encerrado=False, situacao=None,
           tipo="", meu=False, hoje=None, **extras) -> dict:
    """Um prazo no formato do calendário: evento de um dia com as classes de prazo.

    ``situacao`` em branco usa a distância de hoje (vencido, próximo, no prazo);
    um prazo encerrado (pedido atendido, pauta cancelada) traz a situação do
    módulo e não recebe destaque, porque já não há o que fazer.
    """
    rotulo, slug, classes = _situacao_do_prazo(data, hoje)
    if encerrado:
        classes = ["ag-prazo"]
    if situacao is not None:
        rotulo, slug = situacao
    ev = _evento(
        fonte=fonte, pk=pk, titulo=titulo, inicio=data, fim=None, situacao=rotulo, situacao_slug=slug,
        url=url, detalhes=detalhes, encerrado=encerrado, tipo=tipo, meu=meu, chave=chave, **extras,
    )
    ev["classNames"].extend(classes)
    ev["extendedProps"]["prazo"] = data.isoformat()
    return ev


def _dentro(campo: str, inicio: dt.date, fim: dt.date) -> dict:
    return {f"{campo}__gte": inicio, f"{campo}__lt": fim}


# ---------------------------------------------------------------------------
# Prazo de saque das diárias (viagens_prestacoes)
# ---------------------------------------------------------------------------


def _pode_diarias(usuario) -> bool:
    from viagens_cadastros.permissions import pode_acessar

    return pode_acessar(usuario)


def _diarias(usuario, inicio, fim) -> list[dict]:
    from viagens_prestacoes.models import PrestacaoServidor

    consulta = (
        PrestacaoServidor.objects.filter(finalizada=False, prestacao__oficio__cancelado=False)
        .filter(**_dentro("prazo_limite_saque", inicio, fim))
        .select_related("servidor", "prestacao__oficio__viagem")
        .order_by("prazo_limite_saque", "id")
    )
    hoje = _hoje()
    saida = []
    for ps in consulta:
        oficio = ps.prestacao.oficio
        rotulo_oficio = f"Ofício {oficio.numero_formatado}" if oficio.numero else f"Ofício #{oficio.pk}"
        viagem = oficio.viagem if oficio.viagem_id else None
        saida.append(_prazo(
            fonte="prazo_diarias", pk=ps.pk,
            titulo=f"Saque das diárias — {ps.servidor.nome} · {rotulo_oficio}",
            data=ps.prazo_limite_saque,
            url=reverse("viagens_prestacoes:abrir_oficio", args=[oficio.pk]),
            tipo="Prazo de saque", hoje=hoje,
            detalhes=[
                ("Servidor", ps.servidor.nome),
                ("Ofício", rotulo_oficio),
                ("Viagem", viagem.destino_display if viagem else ""),
                ("Prazo de saque", ps.prazo_limite_saque.strftime("%d/%m/%Y")),
                ("Situação da prestação", ps.get_status_display()),
            ],
        ))
    return saida


# ---------------------------------------------------------------------------
# Deadlines da imprensa (atendimento_imprensa)
# ---------------------------------------------------------------------------


def _pode_imprensa(usuario) -> bool:
    from atendimento_imprensa.permissions import pode_acessar

    return pode_acessar(usuario)


def _imprensa(usuario, inicio, fim) -> list[dict]:
    from atendimento_imprensa.models import SITUACOES_ABERTAS, Atendimento

    consulta = (
        Atendimento.objects.filter(**_dentro("deadline", inicio, fim))
        .select_related("veiculo", "responsavel")
        .order_by("deadline", "id")
    )
    hoje = _hoje()
    saida = []
    for a in consulta:
        veiculo = str(a.veiculo) if a.veiculo_id else ""
        aberto = a.situacao in SITUACOES_ABERTAS
        saida.append(_prazo(
            fonte="imprensa", pk=a.pk,
            titulo=f"Deadline — {a.jornalista}" + (f" ({veiculo})" if veiculo else ""),
            data=a.deadline,
            url=reverse("atendimento_imprensa:editar", args=[a.pk]),
            encerrado=not aberto,
            situacao=None if aberto else (a.get_situacao_display(), a.situacao.lower()),
            tipo="Deadline da imprensa", hoje=hoje,
            meu=a.criado_por_id == getattr(usuario, "pk", None),
            detalhes=[
                ("Jornalista", a.jornalista),
                ("Veículo", veiculo),
                ("Pedido", (a.pedido or "").strip()[:200]),
                ("Responsável", str(a.responsavel) if a.responsavel_id else ""),
                ("Situação", a.get_situacao_display()),
                ("Deadline", a.deadline.strftime("%d/%m/%Y")),
            ],
        ))
    return saida


# ---------------------------------------------------------------------------
# Pautas (publicacoes)
# ---------------------------------------------------------------------------


def _pode_pautas(usuario) -> bool:
    from publicacoes.permissions import pode_acessar

    return pode_acessar(usuario)


def _pautas(usuario, inicio, fim) -> list[dict]:
    from publicacoes.models import Publicacao, StatusPublicacao

    consulta = (
        Publicacao.objects.filter(**_dentro("data", inicio, fim))
        .select_related("jornalista", "unidade")
        .order_by("data", "inicio_pauta", "id")
    )
    saida = []
    for p in consulta:
        hora = f"{p.inicio_pauta:%H:%M}" if p.inicio_pauta else ""
        saida.append(_prazo(
            fonte="pauta", pk=p.pk,
            titulo=(f"{hora} " if hora else "") + f"Pauta — {p.titulo}",
            data=p.data,
            url=reverse("publicacoes:editar", args=[p.pk]),
            encerrado=p.status == StatusPublicacao.CANCELADA,
            # Pauta é compromisso, não prazo: a situação é a do módulo.
            situacao=(p.get_status_display(), p.status.lower()),
            tipo="Pauta",
            meu=p.criado_por_id == getattr(usuario, "pk", None),
            detalhes=[
                ("Jornalista", str(p.jornalista) if p.jornalista_id else ""),
                ("Unidade", str(p.unidade) if p.unidade_id else ""),
                ("Horário", hora),
                ("Fonte", p.fonte),
                ("Situação", p.get_status_display()),
            ],
        ))
    return saida


# ---------------------------------------------------------------------------
# Contratos, termos aditivos e certidões do coffee break
# ---------------------------------------------------------------------------


def _pode_coffee(usuario) -> bool:
    from coffee_break.permissions import pode_acessar

    return pode_acessar(usuario)


def _vigencia(inicio, fim) -> str:
    if inicio and fim:
        return f"{inicio:%d/%m/%Y} a {fim:%d/%m/%Y}"
    return fim.strftime("%d/%m/%Y") if fim else ""


def _contratos(usuario, inicio, fim) -> list[dict]:
    from coffee_break.models import AditivoContrato, ContratoCoffeeBreak

    hoje = _hoje()
    saida = []
    contratos = (
        ContratoCoffeeBreak.objects.filter(**_dentro("vigencia_fim", inicio, fim))
        .select_related("fornecedor").order_by("vigencia_fim", "numero")
    )
    for c in contratos:
        saida.append(_prazo(
            fonte="contratos", pk=c.pk,
            titulo=f"Fim da vigência — Contrato {c.numero} ({c.fornecedor.razao_social})",
            data=c.vigencia_fim,
            url=reverse("coffee_break:cadastro_editar", args=["contratos", c.pk]),
            tipo="Contrato", hoje=hoje,
            detalhes=[
                ("Contrato", c.numero),
                ("Fornecedor", c.fornecedor.razao_social),
                ("Vigência", _vigencia(c.vigencia_inicio, c.vigencia_fim)),
                ("Estimada", "Sim — conferir no termo aditivo" if c.vigencia_estimada else ""),
            ],
        ))
    aditivos = (
        AditivoContrato.objects.filter(**_dentro("vigencia_fim", inicio, fim))
        .select_related("contrato__fornecedor").order_by("vigencia_fim", "numero")
    )
    for a in aditivos:
        c = a.contrato
        # O dossiê é o do contrato (pk); a chave só distingue o evento.
        saida.append(_prazo(
            fonte="contratos", pk=c.pk, chave=f"a{a.pk}",
            titulo=f"Fim da vigência — Termo aditivo {a.numero} · Contrato {c.numero} ({c.fornecedor.razao_social})",
            data=a.vigencia_fim,
            url=reverse("coffee_break:cadastro_editar", args=["contratos", c.pk]),
            tipo="Termo aditivo", hoje=hoje,
            detalhes=[
                ("Termo aditivo", a.numero),
                ("Contrato", c.numero),
                ("Fornecedor", c.fornecedor.razao_social),
                ("Vigência", _vigencia(a.vigencia_inicio, a.vigencia_fim)),
            ],
        ))
    return saida


def _certidoes_vigentes():
    """A certidão de maior validade de cada tipo, por fornecedor — a única que vale.

    As anteriores ficam no histórico do módulo; aqui, uma certidão renovada não
    pode continuar marcando o dia em que a antiga venceria.
    """
    from coffee_break.models import CertidaoFornecedor

    atuais = {}
    consulta = CertidaoFornecedor.objects.select_related("fornecedor").order_by("fornecedor_id", "tipo", "-validade", "-criado_em")
    for certidao in consulta:
        atuais.setdefault((certidao.fornecedor_id, certidao.tipo), certidao)
    return list(atuais.values())


def _certidoes(usuario, inicio, fim) -> list[dict]:
    hoje = _hoje()
    saida = []
    for c in _certidoes_vigentes():
        if not (inicio <= c.validade < fim):
            continue
        # O dossiê é o do fornecedor (pk), com o quadro de todas as certidões.
        saida.append(_prazo(
            fonte="certidoes", pk=c.fornecedor_id, chave=str(c.pk),
            titulo=f"Certidão {c.get_tipo_display().lower()} vence — {c.fornecedor.razao_social}",
            data=c.validade,
            url=reverse("coffee_break:certidoes"),
            tipo=f"Certidão {c.get_tipo_display().lower()}", hoje=hoje,
            detalhes=[
                ("Fornecedor", c.fornecedor.razao_social),
                ("Certidão", c.get_tipo_display()),
                ("Validade", c.validade.strftime("%d/%m/%Y")),
            ],
        ))
    saida.sort(key=lambda e: (e["start"], e["title"]))
    return saida


FONTES: tuple[Fonte, ...] = (
    Fonte("prazo_diarias", "Prazos de saque das diárias", _pode_diarias, _diarias),
    Fonte("imprensa", "Deadlines da imprensa", _pode_imprensa, _imprensa),
    Fonte("pauta", "Pautas", _pode_pautas, _pautas),
    Fonte("contratos", "Contratos e termos aditivos", _pode_coffee, _contratos),
    Fonte("certidoes", "Certidões dos fornecedores", _pode_coffee, _certidoes),
)


# ---------------------------------------------------------------------------
# Dossiês (o modal da agenda), no formato de ``agenda.detalhes``
# ---------------------------------------------------------------------------

TOM_DO_PRAZO = {"vencido": "cancelada", "proximo": "pendente", "no_prazo": "atendido"}


def _prazo_no_dossie(d: dict, data: dt.date, *, encerrado=False) -> dict:
    """Situação e tom do selo pela distância de hoje, como no calendário."""
    if not encerrado:
        rotulo, slug, _ = _situacao_do_prazo(data)
        d["situacao"], d["situacao_slug"] = rotulo, slug
        d["selo_tom"] = TOM_DO_PRAZO[slug]
    return d


def _dossie_diarias(usuario, pk) -> dict:
    from viagens_cadastros.permissions import pode_acessar
    from viagens_prestacoes.models import PrestacaoServidor
    from viagens_prestacoes.prazos import prazo_para_prestar

    from .detalhes import _base, _campos

    if not pode_acessar(usuario):
        raise PermissionDenied
    ps = (
        PrestacaoServidor.todos.select_related("servidor__cargo", "servidor__unidade", "prestacao__oficio__viagem")
        .filter(pk=pk).first()
    )
    if ps is None:
        raise Http404
    oficio = ps.prestacao.oficio
    rotulo_oficio = f"Ofício {oficio.numero_formatado}" if oficio.numero else f"Ofício #{oficio.pk}"
    d = _base(
        fonte="prazo_diarias", rotulo="Prazo de saque das diárias",
        titulo=ps.servidor.nome,
        subtitulo=f"Saque até {ps.prazo_limite_saque:%d/%m/%Y}" if ps.prazo_limite_saque else "Sem prazo de saque",
        situacao="Finalizada" if ps.finalizada else ps.get_status_display(),
        situacao_slug="finalizado" if ps.finalizada else ps.status,
        encerrado=ps.finalizada,
        url_abrir=reverse("viagens_prestacoes:abrir_oficio", args=[oficio.pk]),
    )
    if ps.prazo_limite_saque:
        _prazo_no_dossie(d, ps.prazo_limite_saque, encerrado=ps.finalizada)
    limite_prestar = prazo_para_prestar(ps.prazo_limite_saque)
    d["campos"] = _campos([
        ("Cargo", str(ps.servidor.cargo) if ps.servidor.cargo_id else ""),
        ("Unidade", str(ps.servidor.unidade) if ps.servidor.unidade_id else ""),
        ("Ofício", rotulo_oficio),
        ("Destino", oficio.viagem.destino_display if oficio.viagem_id else ""),
        ("Liberação das diárias", ps.data_liberacao_diarias.strftime("%d/%m/%Y") if ps.data_liberacao_diarias else ""),
        ("Prazo de saque", ps.prazo_limite_saque.strftime("%d/%m/%Y") if ps.prazo_limite_saque else ""),
        ("Prestar contas até", limite_prestar.strftime("%d/%m/%Y") if limite_prestar else ""),
        ("Número da solicitação", ps.numero_solicitacao),
        ("Situação da prestação", ps.get_status_display()),
    ])
    if oficio.viagem_id:
        d["origem"] = {
            "rotulo": f"Viagem: {oficio.viagem.destino_display}",
            "url": reverse("viagens_viagem:painel", args=[oficio.viagem_id]),
        }
    return d


def _dossie_imprensa(usuario, pk) -> dict:
    from atendimento_imprensa.models import SITUACOES_ABERTAS, Atendimento
    from atendimento_imprensa.permissions import pode_acessar

    from .detalhes import _base, _campos

    if not pode_acessar(usuario):
        raise PermissionDenied
    a = Atendimento.objects.select_related("veiculo", "responsavel").filter(pk=pk).first()
    if a is None:
        raise Http404
    aberto = a.situacao in SITUACOES_ABERTAS
    d = _base(
        fonte="imprensa", rotulo="Atendimento à imprensa",
        titulo=a.jornalista + (f" — {a.veiculo}" if a.veiculo_id else ""),
        subtitulo=f"Deadline {a.deadline:%d/%m/%Y}" if a.deadline else "Sem deadline",
        situacao=a.get_situacao_display(), situacao_slug=a.situacao.lower(),
        encerrado=not aberto,
        url_abrir=reverse("atendimento_imprensa:editar", args=[a.pk]),
    )
    if a.deadline:
        _prazo_no_dossie(d, a.deadline, encerrado=not aberto)
    d["campos"] = _campos([
        ("Data da solicitação", a.data.strftime("%d/%m/%Y") + (f" {a.horario:%H:%M}" if a.horario else "")),
        ("Contato", a.contato),
        ("Pedido", (a.pedido or "").strip()),
        ("Responsável pelo atendimento", str(a.responsavel) if a.responsavel_id else ""),
        ("Situação", a.get_situacao_display()),
        ("Deadline", a.deadline.strftime("%d/%m/%Y") if a.deadline else ""),
        ("Andamento", (a.andamento or "").strip()),
    ])
    return d


def _dossie_pauta(usuario, pk) -> dict:
    from publicacoes.models import Publicacao, StatusPublicacao
    from publicacoes.permissions import pode_acessar

    from .detalhes import _base, _campos

    if not pode_acessar(usuario):
        raise PermissionDenied
    p = Publicacao.objects.select_related("jornalista", "unidade").filter(pk=pk).first()
    if p is None:
        raise Http404
    d = _base(
        fonte="pauta", rotulo="Pauta",
        titulo=p.titulo,
        subtitulo=p.data.strftime("%d/%m/%Y") + (f" às {p.inicio_pauta:%H:%M}" if p.inicio_pauta else ""),
        situacao=p.get_status_display(), situacao_slug=p.status.lower(),
        encerrado=p.status == StatusPublicacao.CANCELADA,
        url_abrir=reverse("publicacoes:editar", args=[p.pk]),
    )
    d["campos"] = _campos([
        ("Jornalista", str(p.jornalista) if p.jornalista_id else ""),
        ("Unidade", str(p.unidade) if p.unidade_id else ""),
        ("Fonte", p.fonte),
        ("Horário", f"{p.inicio_pauta:%H:%M}" if p.inicio_pauta else ""),
        ("Andamento", (p.andamento or "").strip()),
        ("Publicada em", p.data_publicacao.strftime("%d/%m/%Y") if p.data_publicacao else ""),
    ])
    return d


def _dossie_contrato(usuario, pk) -> dict:
    from coffee_break.models import ContratoCoffeeBreak
    from coffee_break.permissions import pode_acessar

    from .detalhes import _base, _campos

    if not pode_acessar(usuario):
        raise PermissionDenied
    c = ContratoCoffeeBreak.objects.select_related("fornecedor").prefetch_related("aditivos").filter(pk=pk).first()
    if c is None:
        raise Http404
    d = _base(
        fonte="contratos", rotulo="Contrato de coffee break",
        titulo=f"Contrato {c.numero}",
        subtitulo=f"Vigência até {c.vigencia_fim:%d/%m/%Y}" if c.vigencia_fim else "Sem vigência informada",
        situacao="Vigente", situacao_slug="no_prazo", encerrado=False,
        url_abrir=reverse("coffee_break:cadastro_editar", args=["contratos", c.pk]),
    )
    if c.vigencia_fim:
        _prazo_no_dossie(d, c.vigencia_fim)
    d["campos"] = _campos([
        ("Fornecedor", c.fornecedor.razao_social),
        ("CNPJ", c.fornecedor.cnpj),
        ("GMS", c.numero_gms),
        ("Termo aditivo", c.termo_aditivo),
        ("Vigência", _vigencia(c.vigencia_inicio, c.vigencia_fim)),
        ("Estimada", "Sim — conferir no termo aditivo" if c.vigencia_estimada else ""),
        ("Quantidade contratada", str(c.quantidade_contratada or "")),
        ("Fiscal responsável", c.fiscal_responsavel),
        ("Objeto", c.objeto),
    ])
    aditivos = [
        f"Termo aditivo {a.numero}" + (f" — até {a.vigencia_fim:%d/%m/%Y}" if a.vigencia_fim else "")
        for a in c.aditivos.all()
    ]
    if aditivos:
        d["secoes"].append({"titulo": "Termos aditivos", "campos": [], "linhas": aditivos})
    return d


def _dossie_certidoes(usuario, pk) -> dict:
    from coffee_break import certidoes
    from coffee_break.models import Fornecedor
    from coffee_break.permissions import pode_acessar

    from .detalhes import _base, _campos

    if not pode_acessar(usuario):
        raise PermissionDenied
    f = Fornecedor.objects.filter(pk=pk).first()
    if f is None:
        raise Http404
    quadro = certidoes.quadro(f, _hoje())
    situacoes = {linha["situacao"] for linha in quadro}
    if "vencida" in situacoes:
        situacao, slug = "Certidão vencida", "vencido"
    elif "vencendo" in situacoes:
        situacao, slug = "Certidão a vencer", "proximo"
    else:
        situacao, slug = "Certidões em dia", "no_prazo"
    d = _base(
        fonte="certidoes", rotulo="Certidões do fornecedor",
        titulo=f.razao_social, subtitulo=f.cnpj,
        situacao=situacao, situacao_slug=slug, encerrado=False,
        url_abrir=reverse("coffee_break:certidoes"),
    )
    d["selo_tom"] = TOM_DO_PRAZO[slug]
    d["campos"] = _campos([
        ("Contato do fornecedor", " · ".join(x for x in [f.contato, f.telefone, f.email] if x)),
    ])
    rotulos = {"vigente": "vigente", "vencendo": "vence em breve", "vencida": "VENCIDA", "faltando": "não anexada"}
    linhas = []
    for linha in quadro:
        texto = f"{linha['rotulo']}: {rotulos[linha['situacao']]}"
        if linha["certidao"] is not None:
            texto += f" (até {linha['certidao'].validade:%d/%m/%Y})"
        linhas.append(texto)
    d["secoes"].append({"titulo": "Certidões", "campos": [], "linhas": linhas})
    return d


CONSTRUTORES = {
    "prazo_diarias": _dossie_diarias,
    "imprensa": _dossie_imprensa,
    "pauta": _dossie_pauta,
    "contratos": _dossie_contrato,
    "certidoes": _dossie_certidoes,
}
