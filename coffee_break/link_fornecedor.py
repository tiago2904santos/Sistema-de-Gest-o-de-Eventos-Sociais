"""Link seguro para o fornecedor enviar a nota fiscal da OS e as certidões.

Fluxo:

1. Na etapa 2, "Enviar link ao fornecedor" abre a tela de e-mail ao
   fornecedor que já existe (m030): o texto traz ``{link}``, trocado pelo
   endereço só no envio confirmado. É aí que o link nasce — o token
   (``secrets.token_urlsafe``) vai só no e-mail; o banco guarda o hash. Gerar
   um novo revoga o anterior da mesma OS; a validade é
   ``COFFEE_LINK_FORNECEDOR_DIAS`` (30 por padrão) e dá para revogar na tela.
2. A página do link (/fornecedor/<token>/, sem login, fora do namespace do
   módulo) mostra só o que o fornecedor precisa: número da OS, evento, data e
   valor, e a situação das certidões dele — nenhum dado de servidor.
3. O que chega passa pela validação central de upload (tipo real, tamanho,
   antivírus se ligado) e pela mesma conferência do anexo da etapa 2 (m026:
   CNPJ, valor, data e duplicidade da nota; tipo e CNPJ da certidão), fica
   "recebido, aguardando conferência", vai para o histórico e avisa quem
   gerou o link e quem criou a OS. Só entra na OS (ou nas certidões do
   fornecedor) quando alguém da ASCOM aceita.
"""

import hashlib
import secrets
from datetime import timedelta

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import transaction
from django.urls import reverse
from django.utils import timezone

from core.notificacoes import notificar

from . import certidoes, services
from .models import (
    TIPO_ENVIO_NOTA,
    AcaoHistoricoCoffeeBreak,
    EnvioFornecedor,
    LinkFornecedor,
    StatusEnvioFornecedor,
    TipoCertidao,
)

# Tentativas por IP (tokens errados e envios) e envios por link, numa janela.
JANELA_LIMITE = 60 * 60


def dias_de_validade():
    return int(getattr(settings, "COFFEE_LINK_FORNECEDOR_DIAS", 30) or 30)


def limite_de_tokens_invalidos():
    return getattr(settings, "COFFEE_LINK_LIMITE_INVALIDOS", 20)


def limite_de_envios():
    return getattr(settings, "COFFEE_LINK_LIMITE_ENVIOS", 30)


def hash_do_token(token):
    return hashlib.sha256((token or "").encode()).hexdigest()


# ---------------------------------------------------------------------------
# Gerar, achar e revogar
# ---------------------------------------------------------------------------

def link_ativo(solicitacao):
    return next((link for link in solicitacao.links_fornecedor.all() if link.ativo), None)


def pode_receber(solicitacao):
    """OS cancelada ou concluída não recebe mais nada pelo link."""
    return not solicitacao.bloqueada_para_edicao


def gerar(solicitacao, usuario):
    """Cria o link (revogando o anterior da OS). Devolve (link, token)."""
    if not pode_receber(solicitacao):
        raise ValidationError("Solicitações canceladas ou concluídas não recebem envio do fornecedor.")
    token = secrets.token_urlsafe(32)
    agora = timezone.now()
    with transaction.atomic():
        LinkFornecedor.objects.filter(solicitacao=solicitacao, revogado_em__isnull=True).update(
            revogado_em=agora, revogado_por=usuario
        )
        link = LinkFornecedor.objects.create(
            solicitacao=solicitacao,
            token_hash=hash_do_token(token),
            expira_em=agora + timedelta(days=dias_de_validade()),
            criado_por=usuario,
        )
    return link, token


def revogar(link, usuario):
    if link.revogado_em is None:
        link.revogado_em = timezone.now()
        link.revogado_por = usuario
        link.save(update_fields=["revogado_em", "revogado_por"])
        services.registrar_historico(
            link.solicitacao, usuario, AcaoHistoricoCoffeeBreak.FORNECEDOR,
            "Link de envio do fornecedor revogado.",
        )


def link_do_token(token):
    """O link válido do token, ou None (inexistente, expirado, revogado, ou a
    OS já não recebe envio). Token de formato impossível nem vai ao banco."""
    if not token or len(token) < 32 or len(token) > 128:
        return None
    link = (
        LinkFornecedor.objects.select_related("solicitacao__lote__contrato__fornecedor")
        .filter(token_hash=hash_do_token(token))
        .first()
    )
    if link is None or not link.ativo or not pode_receber(link.solicitacao):
        return None
    return link


def url_publica(request, token):
    return request.build_absolute_uri(reverse("fornecedor_publico:envio", args=[token]))


# ---------------------------------------------------------------------------
# O que a página do link mostra
# ---------------------------------------------------------------------------

def resumo_publico(link):
    """Só o mínimo para o fornecedor saber o que enviar."""
    solicitacao = link.solicitacao
    fornecedor = solicitacao.lote.contrato.fornecedor
    hoje = timezone.localdate()
    vigentes = {}
    for certidao in fornecedor.certidoes.order_by("tipo", "-validade"):
        vigentes.setdefault(certidao.tipo, certidao.validade)
    pendentes = {
        envio.tipo
        for envio in EnvioFornecedor.objects.filter(
            link__solicitacao=solicitacao, status=StatusEnvioFornecedor.RECEBIDO
        )
    }
    certidoes_situacao = []
    for tipo, rotulo in TipoCertidao.choices:
        validade = vigentes.get(tipo)
        if tipo in pendentes:
            situacao = "Recebida, aguardando conferência"
        elif validade and validade >= hoje:
            situacao = f"Válida até {validade:%d/%m/%Y}"
        elif validade:
            situacao = f"Vencida em {validade:%d/%m/%Y} — envie a renovada"
        else:
            situacao = "Não enviada"
        certidoes_situacao.append({"tipo": tipo, "rotulo": rotulo, "situacao": situacao})
    if TIPO_ENVIO_NOTA in pendentes:
        nota = "Recebida, aguardando conferência"
    elif solicitacao.arquivo_nota_fiscal:
        nota = "Já anexada pela ASCOM"
    else:
        nota = "Aguardando envio"
    return {
        "numero_os": solicitacao.numero or f"#{solicitacao.pk}",
        "evento": solicitacao.descricao_evento,
        "data": solicitacao.periodo_evento_display,
        "valor": services.formatar_reais(solicitacao.valor),
        "fornecedor": fornecedor.razao_social,
        "vale_ate": timezone.localtime(link.expira_em),
        "nota": nota,
        "certidoes": certidoes_situacao,
    }


# ---------------------------------------------------------------------------
# Recebimento (página pública)
# ---------------------------------------------------------------------------

def _avisar(link, titulo, mensagem):
    solicitacao = link.solicitacao
    notificar(
        [usuario for usuario in (link.criado_por, solicitacao.criado_por) if usuario],
        titulo,
        mensagem,
        link=reverse("coffee_break:etapa_nota", args=[solicitacao.pk]) + "#envios-fornecedor",
    )


def receber_nota(link, arquivo):
    """Nota enviada pelo fornecedor: validada, conferida e guardada como
    recebida. Devolve o envio (com os avisos da conferência). Levanta
    ValidationError quando o arquivo não serve."""
    from .forms import validar_pdf

    validar_pdf(arquivo)
    arquivo.seek(0)
    lidos = services.ler_nota(arquivo.read())
    arquivo.seek(0)
    solicitacao = link.solicitacao
    avisos = services.avisos_da_nota_lida(solicitacao, lidos)
    with transaction.atomic():
        # Um novo envio da nota substitui o que ainda não foi conferido.
        EnvioFornecedor.objects.filter(
            link__solicitacao=solicitacao, tipo=TIPO_ENVIO_NOTA, status=StatusEnvioFornecedor.RECEBIDO
        ).update(status=StatusEnvioFornecedor.RECUSADO, motivo_recusa="Substituída por novo envio do fornecedor.")
        envio = EnvioFornecedor.objects.create(
            link=link,
            tipo=TIPO_ENVIO_NOTA,
            arquivo=arquivo,
            numero_nota=lidos["numero"][:30],
            valor_nota=lidos["valor"],
            emissao_nota=lidos["emissao"],
            cnpj_nota=lidos["cnpj"] or "",
            avisos="\n".join(avisos),
        )
        rotulo = solicitacao.numero or f"#{solicitacao.pk}"
        numero = f" {envio.numero_nota}" if envio.numero_nota else ""
        services.registrar_historico(
            solicitacao, None, AcaoHistoricoCoffeeBreak.FORNECEDOR,
            f"O fornecedor enviou a nota fiscal{numero} pelo link seguro; aguardando conferência."
            + (f" Pontos a conferir: {' '.join(avisos)}" if avisos else ""),
        )
        _avisar(
            link,
            f"Nota fiscal da OS {rotulo} recebida do fornecedor",
            "Chegou pelo link seguro e aguarda conferência na etapa 2."
            + (" A conferência apontou pontos a verificar." if avisos else ""),
        )
    return envio


def receber_certidao(link, tipo, arquivo, validade_informada=None):
    """Certidão enviada pelo fornecedor: tem de ser do tipo pedido, do CNPJ
    dele e estar válida (certidoes.conferir); fica recebida até a conferência."""
    from .forms import validar_pdf

    if tipo not in TipoCertidao.values:
        raise ValidationError("Tipo de certidão inválido.")
    validar_pdf(arquivo)
    fornecedor = link.solicitacao.lote.contrato.fornecedor
    validade, aviso = certidoes.conferir(fornecedor, tipo, arquivo, validade_informada)
    if validade < timezone.localdate():
        raise ValidationError(f"Esta certidão venceu em {validade:%d/%m/%Y}. Envie a certidão renovada.")
    rotulo = dict(TipoCertidao.choices)[tipo]
    solicitacao = link.solicitacao
    with transaction.atomic():
        EnvioFornecedor.objects.filter(
            link__solicitacao=solicitacao, tipo=tipo, status=StatusEnvioFornecedor.RECEBIDO
        ).update(status=StatusEnvioFornecedor.RECUSADO, motivo_recusa="Substituída por novo envio do fornecedor.")
        envio = EnvioFornecedor.objects.create(
            link=link, tipo=tipo, arquivo=arquivo, validade_certidao=validade, avisos=aviso,
        )
        services.registrar_historico(
            solicitacao, None, AcaoHistoricoCoffeeBreak.FORNECEDOR,
            f"O fornecedor enviou a certidão {rotulo} (válida até {validade:%d/%m/%Y}) pelo link seguro; "
            "aguardando conferência." + (f" {aviso}" if aviso else ""),
        )
        _avisar(
            link,
            f"Certidão {rotulo} de {fornecedor.razao_social} recebida",
            f"Chegou pelo link seguro da OS {solicitacao.numero or '#' + str(solicitacao.pk)} e aguarda conferência.",
        )
    return envio


# ---------------------------------------------------------------------------
# Conferência (equipe)
# ---------------------------------------------------------------------------

def aceitar(envio, usuario):
    """Leva o arquivo conferido para a OS (nota) ou para as certidões do
    fornecedor, pelos mesmos caminhos do anexo feito pela equipe."""
    if envio.status != StatusEnvioFornecedor.RECEBIDO:
        raise ValidationError("Este envio já foi conferido.")
    solicitacao = envio.link.solicitacao
    if solicitacao.bloqueada_para_edicao:
        raise ValidationError("Solicitações canceladas ou concluídas ficam bloqueadas para edição.")
    from django.core.files.base import ContentFile
    from pathlib import Path

    with envio.arquivo.open("rb") as aberto:
        conteudo = ContentFile(aberto.read(), name=Path(envio.arquivo.name).name)
    with transaction.atomic():
        if envio.eh_nota:
            lidos = {
                "numero": envio.numero_nota,
                "valor": envio.valor_nota,
                "emissao": envio.emissao_nota,
                "cnpj": envio.cnpj_nota,
            }
            services.aplicar_nota(solicitacao, conteudo, usuario, lidos=lidos, origem="(enviada pelo fornecedor pelo link seguro)")
        else:
            fornecedor = solicitacao.lote.contrato.fornecedor
            certidoes.registrar(fornecedor, envio.tipo, conteudo, envio.validade_certidao, usuario)
            services.registrar_historico(
                solicitacao, usuario, AcaoHistoricoCoffeeBreak.FORNECEDOR,
                f"{envio.get_tipo_display()} enviada pelo fornecedor conferida e aceita "
                f"(válida até {envio.validade_certidao:%d/%m/%Y}).",
            )
        envio.status = StatusEnvioFornecedor.ACEITO
        envio.conferido_por = usuario
        envio.conferido_em = timezone.now()
        envio.save(update_fields=["status", "conferido_por", "conferido_em"])
    return envio


def recusar(envio, usuario, motivo=""):
    if envio.status != StatusEnvioFornecedor.RECEBIDO:
        raise ValidationError("Este envio já foi conferido.")
    motivo = " ".join((motivo or "").split())[:255]
    envio.status = StatusEnvioFornecedor.RECUSADO
    envio.conferido_por = usuario
    envio.conferido_em = timezone.now()
    envio.motivo_recusa = motivo
    envio.save(update_fields=["status", "conferido_por", "conferido_em", "motivo_recusa"])
    services.registrar_historico(
        envio.link.solicitacao, usuario, AcaoHistoricoCoffeeBreak.FORNECEDOR,
        f"{envio.get_tipo_display()} enviada pelo fornecedor recusada" + (f": {motivo}" if motivo else "."),
    )
    return envio


def envios_pendentes(solicitacao):
    return list(
        EnvioFornecedor.objects.filter(link__solicitacao=solicitacao, status=StatusEnvioFornecedor.RECEBIDO)
        .order_by("criado_em")
    )


# O texto do e-mail com o link, na tela de e-mail ao fornecedor. {link} e
# {validade} são trocados só no envio; os outros campos, como nos e-mails da OS.
EMAIL_ASSUNTO = "Envio da nota fiscal e certidões — OS {numero}"
EMAIL_TEXTO = (
    "Prezados,\n\n"
    "Para o pagamento da OS {numero} ({evento}, {data}), envie a nota fiscal e as "
    "certidões atualizadas da empresa pelo link abaixo. Não é preciso login; o link "
    "é pessoal e vale até {validade}.\n\n"
    "{link}\n\n"
    "Atenciosamente,\nAssessoria de Comunicação — PCPR"
)
