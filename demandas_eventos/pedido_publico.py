"""Formulário público de pedido de palestra, PCPR na Comunidade ou evento.

Página sem login (/pedido/), fora do namespace do módulo — o middleware de
autorização não a enxerga. Por isso a defesa fica toda aqui, sem serviço
externo:

- campo isca (``site``): invisível para pessoas; robô que preenche recebe a
  mesma tela de "recebido" e nada é gravado;
- tempo mínimo de preenchimento, pelo carimbo assinado que a página entrega
  (quem envia em menos de alguns segundos não leu o formulário) e validade
  máxima do carimbo;
- limite de tentativas e de pedidos aceitos por IP numa janela, no cache do
  Django;
- tamanho máximo em todos os campos; anexo opcional pela política central de
  upload (``core.uploads``: tipo real, tamanho, antivírus se ligado);
- CSRF ativo como em qualquer POST do sistema.

Nada do banco sai daqui: a página não lista nada, não sugere solicitantes, não
mostra temas nem palestrantes. O pedido entra como "Pendente" (aguardando
triagem) em Palestras e Eventos, com o canal "Formulário público", para os
setores do módulo — nunca agendado nem atendido automaticamente — e a equipe é
avisada pelo sino. O solicitante recebe só o número do pedido e um link de
acompanhamento (token aleatório; no banco fica só o hash).
"""

import hashlib
import secrets
import time

from django import forms
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core import signing
from django.db import transaction
from django.urls import reverse
from django.utils import timezone

from core import limite
from core.notificacoes import notificar
from core.uploads import validate_private_document_upload

from .models import AcaoHistoricoDemanda, CanalSolicitacao, DemandaEvento, StatusDemanda, TipoEventoPalestra
from .permissions import CODIGO_MODULO

SALT_CARIMBO = "demandas_eventos.pedido_publico.carimbo"


def _ajuste(nome, padrao):
    return getattr(settings, nome, padrao)


def tempo_minimo():
    """Segundos mínimos entre abrir a página e enviar."""
    return _ajuste("PEDIDO_PUBLICO_TEMPO_MINIMO", 4)


def validade_do_carimbo():
    """Depois disso a página aberta expira e é preciso recarregar."""
    return _ajuste("PEDIDO_PUBLICO_VALIDADE_FORMULARIO", 2 * 60 * 60)


def janela():
    return _ajuste("PEDIDO_PUBLICO_JANELA", 60 * 60)


def limite_de_pedidos():
    """Pedidos aceitos por IP dentro da janela."""
    return _ajuste("PEDIDO_PUBLICO_LIMITE", 5)


def limite_de_tentativas():
    """Envios (válidos ou não) por IP dentro da janela."""
    return _ajuste("PEDIDO_PUBLICO_LIMITE_TENTATIVAS", 20)


# ---------------------------------------------------------------------------
# Proteções
# ---------------------------------------------------------------------------

ip_do_cliente = limite.ip_do_cliente


def bloqueado(ip):
    """IP que já passou do limite de tentativas ou de pedidos aceitos."""
    return limite.excedeu("pedido_tentativas", ip, limite_de_tentativas()) or limite.excedeu(
        "pedido_aceitos", ip, limite_de_pedidos()
    )


def registrar_tentativa(ip):
    limite.somar("pedido_tentativas", ip, janela())


def registrar_pedido_aceito(ip):
    limite.somar("pedido_aceitos", ip, janela())


def novo_carimbo():
    return signing.dumps({"t": time.time()}, salt=SALT_CARIMBO)


def conferir_carimbo(valor):
    """"" quando o tempo de preenchimento é plausível; senão o motivo."""
    try:
        dados = signing.loads(valor or "", salt=SALT_CARIMBO, max_age=validade_do_carimbo())
        inicio = float(dados["t"])
    except (signing.BadSignature, KeyError, TypeError, ValueError):
        return "expirado"
    if time.time() - inicio < tempo_minimo():
        return "rapido"
    return ""


# ---------------------------------------------------------------------------
# Formulário
# ---------------------------------------------------------------------------

AVISO_LGPD = (
    "Os dados informados aqui (nome, instituição, telefone e e-mail) serão usados "
    "apenas pela Assessoria de Comunicação da Polícia Civil do Paraná para analisar "
    "este pedido e entrar em contato sobre ele, conforme a Lei Geral de Proteção de "
    "Dados (Lei nº 13.709/2018). Não são publicados nem compartilhados com terceiros."
)


class PedidoPublicoForm(forms.Form):
    evento = forms.ChoiceField(
        label="O que você quer pedir", choices=TipoEventoPalestra.choices, widget=forms.RadioSelect,
    )
    instituicao = forms.CharField(label="Instituição ou entidade", max_length=200)
    nome_contato = forms.CharField(label="Seu nome", max_length=150)
    telefone = forms.CharField(label="Telefone (com DDD)", max_length=20)
    email = forms.EmailField(label="E-mail", max_length=254)
    municipio = forms.ModelChoiceField(
        label="Município", queryset=None, empty_label="Selecione o município",
    )
    data_desejada = forms.DateField(label="Data desejada", required=False, widget=forms.DateInput(attrs={"type": "date"}))
    horario = forms.TimeField(label="Horário", required=False, widget=forms.TimeInput(attrs={"type": "time"}))
    local = forms.CharField(label="Local (endereço)", max_length=200)
    publico_estimado = forms.IntegerField(label="Público estimado", min_value=1, max_value=100000)
    tema = forms.CharField(label="Tema ou assunto desejado", max_length=300, required=False)
    descricao = forms.CharField(
        label="Conte mais sobre o pedido", max_length=2000, required=False,
        widget=forms.Textarea(attrs={"rows": 5, "maxlength": 2000}),
    )
    anexo = forms.FileField(
        label="Anexo (opcional)", required=False,
        help_text="Ofício ou convite em PDF, PNG ou JPG, até 10 MB.",
    )
    aceite_lgpd = forms.BooleanField(
        label="Li o aviso acima e concordo com o uso dos meus dados para este pedido.",
        error_messages={"required": "Para enviar, marque a ciência do uso dos dados."},
    )
    # Campo isca: escondido por CSS e fora da ordem de tabulação.
    site = forms.CharField(required=False, max_length=200)
    carimbo = forms.CharField(required=False, widget=forms.HiddenInput)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from cadastros.models import Municipio

        self.fields["municipio"].queryset = Municipio.objects.filter(ativo=True, estado__sigla="PR").order_by("nome")
        for nome, campo in self.fields.items():
            if not isinstance(campo.widget, (forms.RadioSelect, forms.CheckboxInput, forms.HiddenInput)):
                campo.widget.attrs.setdefault("class", "form-controle")
        # A isca não deve ser preenchida nem pelo autocompletar do navegador.
        self.fields["site"].widget.attrs.update({"tabindex": "-1", "autocomplete": "off"})

    def clean_data_desejada(self):
        data = self.cleaned_data.get("data_desejada")
        if data and data < timezone.localdate():
            raise forms.ValidationError("A data desejada não pode estar no passado.")
        return data

    def clean_anexo(self):
        anexo = self.cleaned_data.get("anexo")
        if anexo:
            validate_private_document_upload(anexo)
        return anexo

    @property
    def isca_preenchida(self):
        return bool((self.data.get("site") or "").strip())


# ---------------------------------------------------------------------------
# Gravação
# ---------------------------------------------------------------------------

def hash_do_token(token):
    return hashlib.sha256((token or "").encode()).hexdigest()


def _setores_do_modulo():
    from accounts.models import Setor

    return Setor.objects.filter(ativo=True, modulos__codigo=CODIGO_MODULO, modulos__ativo=True).distinct()


def criar_pedido(dados):
    """Grava o pedido como Pendente para a triagem e avisa a equipe.

    Devolve (demanda, token do acompanhamento). Nenhum status além de
    Pendente: agendar, atender ou recusar é sempre de alguém da equipe.
    """
    from . import services

    token = secrets.token_urlsafe(32)
    partes = [f"Local: {dados['local']}"]
    if dados.get("tema"):
        partes.append(f"Tema desejado: {dados['tema']}")
    if dados.get("descricao"):
        partes.append("")
        partes.append(dados["descricao"])
    with transaction.atomic():
        demanda = DemandaEvento(
            evento=dados["evento"],
            status=StatusDemanda.PENDENTE,
            solicitante=dados["instituicao"],
            telefone=dados["telefone"][:20],
            email=dados["email"],
            municipio=dados["municipio"],
            data_inicio_evento=dados.get("data_desejada"),
            hora_inicio=dados.get("horario"),
            quantidade_publico=dados["publico_estimado"],
            data_solicitacao=timezone.localdate(),
            canal_solicitacao=CanalSolicitacao.PORTAL,
            descricao="\n".join(partes),
            pedido_contato=f"Pedido feito pelo formulário público por {dados['nome_contato']}.",
            token_acompanhamento=hash_do_token(token),
        )
        if dados.get("anexo"):
            demanda.anexo_pedido = dados["anexo"]
        demanda.save()
        setores = list(_setores_do_modulo())
        demanda.setores.set(setores)
        services.registrar_historico(
            demanda, None, AcaoHistoricoDemanda.CRIACAO,
            "Pedido recebido pelo formulário público; aguardando triagem.",
            status_novo=demanda.status,
        )
        equipe = get_user_model().objects.filter(is_active=True, setores__in=setores).distinct()
        notificar(
            equipe,
            f"Novo pedido pelo formulário público: {demanda.get_evento_display()} #{demanda.pk}",
            f"{demanda.solicitante} ({demanda.municipio_display}) pediu {demanda.get_evento_display().lower()}. "
            "Está como Pendente, aguardando triagem.",
            link=reverse("demandas_eventos:editar", args=[demanda.pk]),
        )
    return demanda, token


# O que o solicitante enxerga da situação: só o essencial, sem andamento interno.
SITUACAO_PUBLICA = {
    StatusDemanda.PENDENTE: "Recebido, aguardando análise",
    StatusDemanda.EM_ANDAMENTO: "Em análise",
    StatusDemanda.AGUARDANDO_RETORNO: "Em análise",
    StatusDemanda.EVENTO_AGENDADO: "Agendado",
    StatusDemanda.ATENDIDA: "Atendido",
    StatusDemanda.CANCELADA: "Encerrado sem atendimento",
}


def demanda_do_token(token):
    """O pedido do link de acompanhamento, ou None. Só pedidos do formulário
    público têm token; token vazio ou curto nem vai ao banco."""
    if not token or len(token) < 32:
        return None
    return (
        DemandaEvento.objects.filter(
            token_acompanhamento=hash_do_token(token), canal_solicitacao=CanalSolicitacao.PORTAL
        )
        .only("pk", "evento", "status", "data_solicitacao", "data_inicio_evento", "hora_inicio")
        .first()
    )
