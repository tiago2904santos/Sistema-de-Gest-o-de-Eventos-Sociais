"""A pauta da semana: a agenda em PDF, para a reunião e para o e-mail (m136).

"Baixar pauta" gera um PDF limpo do período visível no calendário (ou do
que a URL pedir): um bloco por dia, e em cada compromisso o horário, o
local, a equipe e a situação. É o que antes era montado à mão ou tirado
por print de tela. O mesmo HTML sai como página quando o PDF não pode ser
gerado (WeasyPrint sem as bibliotecas nativas) — imprimível do navegador.

Toda segunda a rotina diária (`core.rotinas`) manda a pauta da semana a
quem ligou a opção (`accounts.PautaSemanal`), com o PDF anexo. Não há
cron: a rotina roda no primeiro acesso do dia, e `enviada_para_semana`
garante uma pauta por semana, mesmo que a segunda passe sem ninguém entrar
e o envio aconteça na terça.
"""

from __future__ import annotations

import datetime as dt
import logging

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.core.mail import EmailMessage
from django.http import HttpResponse
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone

from .fontes import FONTES, eventos_de

logger = logging.getLogger(__name__)

#: Teto do período da pauta: dois meses já é um planejamento, não uma pauta.
MAX_DIAS = 62

_ROTULOS = {f.slug: f.rotulo for f in FONTES}
_DIAS_SEMANA = ("segunda-feira", "terça-feira", "quarta-feira", "quinta-feira", "sexta-feira", "sábado", "domingo")


def _data(valor) -> dt.date | None:
    try:
        return dt.date.fromisoformat((valor or "")[:10])
    except ValueError:
        return None


def semana_de(dia: dt.date) -> tuple[dt.date, dt.date]:
    """Segunda e domingo da semana do dia."""
    segunda = dia - dt.timedelta(days=dia.weekday())
    return segunda, segunda + dt.timedelta(days=6)


def _detalhe(props: dict, rotulo: str) -> str:
    for r, valor in props.get("detalhes") or ():
        if r == rotulo:
            return valor
    return ""


def montar(usuario, inicio: dt.date, fim: dt.date, *, slugs=None, so_meus=False, hoje: dt.date | None = None) -> dict:
    """Os dias do período [inicio, fim], cada um com os seus compromissos.

    Um compromisso de vários dias aparece em cada dia que toca, marcado
    como "continua" a partir do segundo — na pauta de terça a viagem que
    começou segunda ainda está acontecendo.
    """
    hoje = hoje or timezone.localdate()
    eventos = eventos_de(usuario, inicio, fim + dt.timedelta(days=1), slugs)
    if so_meus:
        eventos = [e for e in eventos if e["extendedProps"].get("meu")]
    dias = []
    d = inicio
    while d <= fim:
        itens = []
        for ev in eventos:
            props = ev["extendedProps"]
            if props.get("encerrado"):
                continue
            ev_inicio = dt.date.fromisoformat(ev["start"])
            ev_fim = dt.date.fromisoformat(ev["end"]) - dt.timedelta(days=1)
            if not (ev_inicio <= d <= ev_fim):
                continue
            itens.append({
                "fonte": props["fonte"],
                "rotulo": _ROTULOS.get(props["fonte"], props["fonte"]),
                "titulo": ev["title"],
                "horario": _detalhe(props, "Horário"),
                "local": _detalhe(props, "Local") or props.get("municipio", ""),
                "equipe": ", ".join(props.get("pessoas") or ()),
                "situacao": props.get("situacao", ""),
                "continua": ev_inicio < d,
                "ate": ev_fim if ev_fim > d else None,
                "url": props.get("url", ""),
            })
        itens.sort(key=lambda i: (i["continua"], i["horario"] or "~", i["titulo"]))
        dias.append({"data": d, "semana": _DIAS_SEMANA[d.weekday()], "hoje": d == hoje, "itens": itens})
        d += dt.timedelta(days=1)
    return {
        "inicio": inicio, "fim": fim, "dias": dias,
        "total": sum(len(dia["itens"]) for dia in dias),
        "usuario": usuario, "gerada_em": timezone.localtime(),
        "titulo": "Pauta da semana" if (fim - inicio).days == 6 and inicio.weekday() == 0 else "Pauta do período",
    }


def html(contexto: dict) -> str:
    return render_to_string("pages/agenda/pauta.html", contexto)


def pdf(contexto: dict) -> bytes | None:
    """O PDF pelo WeasyPrint (já no projeto); None se as bibliotecas nativas faltarem."""
    try:
        from weasyprint import HTML
    except (ImportError, OSError):
        logger.warning("Pauta: WeasyPrint indisponível; a pauta sai como HTML.")
        return None
    try:
        return HTML(string=html(contexto), base_url=str(settings.BASE_DIR)).write_pdf()
    except Exception:
        logger.exception("Pauta: falha ao gerar o PDF.")
        return None


def _nome_do_arquivo(inicio: dt.date, fim: dt.date, extensao: str) -> str:
    return f"pauta_{inicio:%Y-%m-%d}_{fim:%Y-%m-%d}.{extensao}"


@login_required
def baixar(request):
    """agenda/pauta.pdf?inicio=&fim=&fontes=&meus=1 (&formato=html para ver na tela)."""
    hoje = timezone.localdate()
    padrao_inicio, padrao_fim = semana_de(hoje)
    inicio = _data(request.GET.get("inicio")) or padrao_inicio
    fim = _data(request.GET.get("fim")) or padrao_fim
    if fim < inicio:
        fim = inicio
    if (fim - inicio).days >= MAX_DIAS:
        fim = inicio + dt.timedelta(days=MAX_DIAS - 1)
    slugs = [s for s in (request.GET.get("fontes") or "").split(",") if s.strip()]
    contexto = montar(request.user, inicio, fim, slugs=slugs, so_meus=request.GET.get("meus") == "1", hoje=hoje)
    if request.GET.get("formato") != "html":
        conteudo = pdf(contexto)
        if conteudo is not None:
            resposta = HttpResponse(conteudo, content_type="application/pdf")
            resposta["Content-Disposition"] = f'attachment; filename="{_nome_do_arquivo(inicio, fim, "pdf")}"'
            return resposta
        contexto["aviso"] = "O PDF não pôde ser gerado neste servidor; use Imprimir → Salvar como PDF."
    return HttpResponse(html(contexto))


# ---------------------------------------------------------------------------
# Envio semanal
# ---------------------------------------------------------------------------


def _texto(contexto: dict) -> str:
    linhas = [f"{contexto['titulo']}: {contexto['inicio']:%d/%m} a {contexto['fim']:%d/%m/%Y}", ""]
    for dia in contexto["dias"]:
        if not dia["itens"]:
            continue
        linhas.append(f"{dia['semana'].capitalize()}, {dia['data']:%d/%m}")
        for i in dia["itens"]:
            partes = [i["titulo"]]
            if i["horario"]:
                partes.append(i["horario"])
            if i["local"]:
                partes.append(i["local"])
            if i["equipe"]:
                partes.append("equipe: " + i["equipe"])
            partes.append(i["situacao"])
            linhas.append("  - " + " · ".join(p for p in partes if p) + (" (continua)" if i["continua"] else ""))
        linhas.append("")
    if contexto["total"] == 0:
        linhas.append("Nenhum compromisso na semana com o que você tem acesso.")
    base = (getattr(settings, "SITE_URL", "") or "").rstrip("/")
    linhas += ["", f"Agenda: {base}{reverse('agenda:painel')}"]
    return "\n".join(linhas)


def enviar_pauta_semanal(hoje: dt.date | None = None) -> int:
    """Manda a pauta da semana a quem ligou a opção; uma vez por semana.

    Devolve quantos e-mails saíram. Roda em qualquer dia útil: se ninguém
    entrou na segunda, a pauta sai no primeiro acesso seguinte da semana.
    """
    from accounts.models import PautaSemanal

    hoje = hoje or timezone.localdate()
    if hoje.weekday() >= 5:
        return 0
    segunda, domingo = semana_de(hoje)
    pendentes = (
        PautaSemanal.objects.filter(ativa=True, usuario__is_active=True)
        .exclude(enviada_para_semana=segunda)
        .exclude(usuario__email="")
        .select_related("usuario")
    )
    enviados = 0
    for pref in pendentes:
        contexto = montar(pref.usuario, segunda, domingo, hoje=hoje)
        mensagem = EmailMessage(
            subject=f"[Eventos Sociais] Pauta da semana — {segunda:%d/%m} a {domingo:%d/%m}",
            body=_texto(contexto),
            from_email=getattr(settings, "DEFAULT_FROM_EMAIL", None),
            to=[pref.usuario.email],
        )
        conteudo = pdf(contexto)
        if conteudo is not None:
            mensagem.attach(_nome_do_arquivo(segunda, domingo, "pdf"), conteudo, "application/pdf")
        try:
            mensagem.send(fail_silently=False)
        except Exception:
            logger.exception("Pauta semanal: falha ao enviar para %s.", pref.usuario)
            continue
        pref.enviada_para_semana = segunda
        pref.save(update_fields=["enviada_para_semana"])
        enviados += 1
    return enviados
