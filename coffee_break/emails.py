"""E-mails ao fornecedor enviados do próprio sistema.

A ordem de serviço (e, depois, a ordem bancária) vai para o e-mail do
cadastro do fornecedor, com cópia para a ASCOM, pelo envio de e-mail do
Django configurado no projeto (``EMAIL_BACKEND`` em ``config/settings.py``).
A tela sempre mostra o e-mail antes (destinatários, assunto, texto e
anexos, tudo editável) e só envia com a confirmação; o que foi enviado, para
quem e quando fica no histórico da solicitação.
"""

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.mail import EmailMessage
from django.core.validators import validate_email
from django.utils import timezone

from .models import AcaoHistoricoCoffeeBreak, ConfiguracaoCoffeeBreak


def lista_de_emails(texto):
    """Os endereços de um campo livre (vírgula, ponto e vírgula ou espaço);
    levanta ValidationError no primeiro inválido."""
    import re

    enderecos = []
    for endereco in re.split(r"[,;\s]+", texto or ""):
        endereco = endereco.strip()
        if not endereco:
            continue
        try:
            validate_email(endereco)
        except ValidationError as exc:
            raise ValidationError(f"E-mail inválido: {endereco}") from exc
        if endereco.lower() not in {e.lower() for e in enderecos}:
            enderecos.append(endereco)
    return enderecos


class _Campos(dict):
    """Campo desconhecido no modelo do texto fica como está (``{campo}``)."""

    def __missing__(self, chave):
        return "{" + chave + "}"


def campos_do_texto(solicitacao):
    """Os valores que o assunto e o texto do e-mail podem usar."""
    horario = solicitacao.horario_evento
    return _Campos(
        numero=solicitacao.numero or f"#{solicitacao.pk}",
        evento=solicitacao.descricao_evento,
        data=solicitacao.periodo_evento_display or "a combinar",
        horario=f"{horario:%H:%M}" if horario else "a combinar",
        local=solicitacao.local_entrega or "a combinar",
        responsavel=solicitacao.responsavel_recebimento or "a combinar",
        quantidade=solicitacao.quantidade,
        fornecedor=solicitacao.lote.contrato.fornecedor.razao_social,
        # Pagamento conjunto: as notas de todas as OS pagas pela mesma OB.
        nota=_notas(solicitacao) or "—",
        ordem_bancaria=getattr(solicitacao, "numero_ordem_bancaria", "") or "—",
        data_ordem_bancaria=(
            f"{solicitacao.data_ordem_bancaria:%d/%m/%Y}" if solicitacao.data_ordem_bancaria else "—"
        ),
    )


def _notas(solicitacao):
    from .documentos import notas_do_pagamento

    notas = notas_do_pagamento(solicitacao) if solicitacao.pk else []
    if len(notas) > 1:
        return ", ".join(notas[:-1]) + " e " + notas[-1]
    return notas[0] if notas else ""


def preencher(modelo, solicitacao):
    return (modelo or "").format_map(campos_do_texto(solicitacao))


def rascunho(solicitacao, assunto, texto):
    """O e-mail como a tela abre: para o fornecedor, com cópia para a ASCOM."""
    config = ConfiguracaoCoffeeBreak.atual()
    return {
        "para": solicitacao.lote.contrato.fornecedor.email,
        "copia": config.email_copia,
        "assunto": preencher(assunto, solicitacao),
        "texto": preencher(texto, solicitacao),
    }


def enviar(solicitacao, usuario, *, para, copia, assunto, texto, anexos, o_que, tambem_em=()):
    """Envia o e-mail com os anexos e registra no histórico.

    ``anexos``: lista de (nome, conteúdo em bytes, tipo). ``o_que``: como o
    histórico chama o envio ("Ordem de serviço 11/2026"); ``tambem_em``: outras
    OS que registram o mesmo envio (as do mesmo pagamento). Levanta
    ValidationError com o que falta (destinatário, assunto) e deixa passar o
    erro do servidor de e-mail, para a tela dizer que não foi enviado.
    """
    destinatarios = lista_de_emails(para)
    copias = [e for e in lista_de_emails(copia) if e.lower() not in {d.lower() for d in destinatarios}]
    if not destinatarios:
        raise ValidationError("Informe o e-mail do fornecedor.")
    assunto = " ".join((assunto or "").split())
    if not assunto:
        raise ValidationError("Informe o assunto do e-mail.")
    mensagem = EmailMessage(
        subject=assunto,
        body=texto or "",
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=destinatarios,
        cc=copias,
        reply_to=copias[:1] or None,
    )
    for nome, conteudo, tipo in anexos:
        mensagem.attach(nome, conteudo, tipo)
    mensagem.send(fail_silently=False)
    from . import services

    quando = timezone.localtime()
    descricao = f"{o_que} enviada por e-mail em {quando:%d/%m/%Y às %H:%M} para {', '.join(destinatarios)}"
    if copias:
        descricao += f" (cópia: {', '.join(copias)})"
    descricao += f". Assunto: {assunto}."
    if anexos:
        descricao += " Anexos: " + ", ".join(nome for nome, *_ in anexos) + "."
    for registro in (solicitacao, *tambem_em):
        services.registrar_historico(registro, usuario, AcaoHistoricoCoffeeBreak.EMAIL, descricao)
    return {"para": destinatarios, "copia": copias, "quando": quando}
