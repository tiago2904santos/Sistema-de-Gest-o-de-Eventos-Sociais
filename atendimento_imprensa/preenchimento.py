"""Sugestões para o atendimento novo a partir do e-mail do jornalista.

As regras do domínio da imprensa (mapas/demandas.md §2.4):

- data e horário do pedido são os do e-mail (a tela traz "agora" como padrão);
- o jornalista preenche quando o nome já está no histórico de atendimentos
  (mantém a grafia usada); nome novo fica como sugestão, para conferir;
- o veículo é sempre só sugestão: o do cadastro que aparece na assinatura,
  no domínio do remetente (aprendido dos atendimentos anteriores) ou no
  texto; se não houver no cadastro, o nome lido vai como sugestão para
  "Outro veículo" — que cria o cadastro ao salvar, então só a pessoa decide;
- o prazo ("até às 17h de hoje", "vai ao ar amanhã") vira o deadline, e a
  hora dele, que não tem campo, entra no texto do pedido;
- o responsável é quem está registrando, quando o nome casa com a equipe.

Fontes, resposta e horários de resposta não se extraem: são o que acontece
depois do pedido. Nada aqui grava.
"""

from __future__ import annotations

import re

from django.db.models import Count
from django.utils import timezone

from core.equipe import integrante_do_usuario
from core.leitura.casamento import cadastros_no_texto
from core.leitura.datas import dobrar, prazo_do_texto
from core.leitura.mensagem import Mensagem
from core.preencher_por_email import Sugestao, Sugestoes, data_do_email, quem_pede

from .models import Atendimento, Responsavel, Veiculo

LIMITE_PEDIDO = 6000

# Provedores de e-mail pessoal: o domínio não diz o veículo.
DOMINIOS_GENERICOS = frozenset({
    "gmail.com", "googlemail.com", "hotmail.com", "hotmail.com.br", "outlook.com", "outlook.com.br",
    "live.com", "msn.com", "yahoo.com", "yahoo.com.br", "icloud.com", "me.com", "uol.com.br",
    "bol.com.br", "terra.com.br", "ig.com.br", "protonmail.com", "proton.me",
})
# Linha do cargo na assinatura: "Repórter | RPC Curitiba", "Produtora - Banda B".
_R_CARGO_IMPRENSA = re.compile(
    r"^(?:reporter|produtor[a]?|producao|jornalista|editor[a]?(?:[\s-]+chefe)?|pauteir[oa]|"
    r"chefe\s+de\s+reportagem|apresentador[a]?|redator[a]?|redacao|correspondente|colunista|"
    r"assistente\s+de\s+producao|rep\.)\b"
)
# No corpo: "sou repórter da RPC", "aqui é a Juliana, produtora do Bom Dia Paraná".
_R_SOU_DO_VEICULO = re.compile(
    r"\b(?:reporter|produtor[a]?|jornalista|editor[a]?|pauteir[oa]|apresentador[a]?|redator[a]?)\s+"
    r"(?:d[aeo]s?|n[ao]s?)\s+"
)
_R_NOME_PROPRIO = re.compile(r"[A-ZÀ-Ý0-9][\wÀ-ÿ&'.-]*(?:\s+(?:d[aeo]s?\s+)?[A-ZÀ-Ý0-9][\wÀ-ÿ&'.-]*){0,4}")
# O que liga o cargo ao veículo: "Repórter | RPC", "Repórter da RPC", "Produtora na Banda B".
_R_LIGACAO = re.compile(r"^(?:\s*[|/,:·•–—-]\s*|\s+(?:d[aeo]s?|n[ao]s?|em)\s+)", re.IGNORECASE)
_R_CONTATO = re.compile(r"@|https?://|www\.|\d{4}[-.\s]?\d{4}|\b(?:tel|fone|telefone|celular|cel|whats?app|ramal)\b")


def _chave(texto: str) -> str:
    return " ".join(re.findall(r"[a-z0-9]+", dobrar(texto or "")))


# ---------------------------------------------------------------------------
# Jornalista e veículo
# ---------------------------------------------------------------------------


def _jornalista(pessoa, mensagem: Mensagem) -> Sugestao | None:
    """O nome de quem pede, na grafia que o histórico já usa.

    Casou com um jornalista já atendido (nome inteiro, ou o primeiro e o
    último nome): preenche. Nome novo: sugestão.
    """
    nome = (pessoa.nome if pessoa else "") or mensagem.remetente_nome
    nome = " ".join((nome or "").split())[:150]
    chave = _chave(nome)
    if not chave:
        return None
    palavras = chave.split()
    curto = f"{palavras[0]} {palavras[-1]}" if len(palavras) > 2 else ""
    conhecidos = Atendimento.objects.order_by("jornalista").values_list("jornalista", flat=True).distinct()
    trecho = pessoa.trecho if pessoa else mensagem.remetente
    for conhecido in conhecidos:
        if _chave(conhecido) in (chave, curto):
            return Sugestao(conhecido, conhecido, "M", f"Já atendido antes · {trecho}")
    return Sugestao(nome, nome, "B", f"Jornalista ainda não atendido · {trecho}")


def _texto_do_veiculo(mensagem: Mensagem) -> tuple[str, str]:
    """(nome do veículo como escrito, trecho) pela assinatura ou pela apresentação no corpo."""
    linhas = [" ".join(linha.split()).strip(" -–—|•*_") for linha in (mensagem.assinatura or "").split("\n")]
    linhas = [linha for linha in linhas if linha]
    for i, linha in enumerate(linhas):
        m = _R_CARGO_IMPRENSA.match(dobrar(linha))
        if not m:
            continue
        resto = _R_LIGACAO.sub("", linha[m.end():]).strip(" |-–—/,:·•")
        if resto and not _R_CONTATO.search(dobrar(resto)):
            return resto[:150], linha
        seguinte = linhas[i + 1] if i + 1 < len(linhas) else ""
        if seguinte and not _R_CONTATO.search(dobrar(seguinte)) and len(seguinte) <= 80:
            return seguinte[:150], f"{linha} · {seguinte}"
    corpo = mensagem.corpo or ""
    m = _R_SOU_DO_VEICULO.search(dobrar(corpo))
    if m:
        nome = _R_NOME_PROPRIO.match(corpo, m.end())
        if nome:
            return nome.group(0).strip(" .,")[:150], corpo[max(0, m.start() - 20):nome.end()].strip()
    return "", ""


def _veiculo_pelo_dominio(email: str) -> Veiculo | None:
    """O veículo que mais aparece nos atendimentos com contato no mesmo domínio."""
    dominio = (email or "").rpartition("@")[2].strip().lower()
    if not dominio or dominio in DOMINIOS_GENERICOS:
        return None
    linha = (
        Atendimento.objects.filter(contato__icontains=f"@{dominio}", veiculo__isnull=False)
        .values("veiculo")
        .annotate(total=Count("pk"))
        .order_by("-total", "veiculo")
        .first()
    )
    return Veiculo.objects.filter(pk=linha["veiculo"]).first() if linha else None


def _veiculo(s: Sugestoes, mensagem: Mensagem) -> None:
    """O veículo, sempre como sugestão: do cadastro, ou o nome lido para "Outro veículo"."""
    veiculos = list(Veiculo.objects.order_by("nome"))
    escrito, trecho = _texto_do_veiculo(mensagem)
    if escrito:
        achados = cadastros_no_texto(escrito, veiculos)
        if achados:
            s.por("veiculo", Sugestao(achados[0].valor, achados[0].exibir, "B", trecho))
            return
    pelo_dominio = _veiculo_pelo_dominio(mensagem.remetente_email)
    if pelo_dominio is not None:
        dominio = mensagem.remetente_email.rpartition("@")[2]
        s.por("veiculo", Sugestao(pelo_dominio, pelo_dominio.nome, "B", f"Atendimentos anteriores de @{dominio}"))
        return
    achados = cadastros_no_texto(mensagem.texto_para_busca, veiculos)
    if achados:
        s.por("veiculo", Sugestao(achados[0].valor, achados[0].exibir, "B", achados[0].trecho))
        return
    if escrito:
        s.por("veiculo_novo", Sugestao(escrito, escrito, "B", trecho))


# ---------------------------------------------------------------------------
# Contato, pedido e prazo
# ---------------------------------------------------------------------------


def _contato(pessoa, mensagem: Mensagem) -> Sugestao | None:
    """"e-mail / telefone" de quem pediu."""
    partes = [(mensagem.remetente_email or "").strip().lower()]
    if pessoa is not None and pessoa.telefone is not None:
        partes.append(pessoa.telefone.valor)
    valor = " / ".join(p for p in partes if p)[:150]
    if not valor:
        return None
    return Sugestao(valor, valor, "A", pessoa.trecho if pessoa else mensagem.remetente)


def _pedido(mensagem: Mensagem, prazo) -> Sugestao | None:
    """O assunto e o corpo limpo; a hora do prazo, que não tem campo, no fim."""
    corpo = (mensagem.corpo or "").strip()
    assunto = mensagem.assunto_limpo
    if not corpo and not assunto:
        return None
    partes = []
    if assunto:
        partes.append(f"Assunto: {assunto}")
    if corpo:
        partes.append(corpo)
    if prazo is not None and prazo.hora:
        partes.append(f"Prazo pedido: até {prazo.hora:%H:%M} de {prazo.data:%d/%m/%Y}.")
    texto = "\n\n".join(partes)
    if len(texto) > LIMITE_PEDIDO:
        texto = texto[:LIMITE_PEDIDO].rstrip() + "…"
    exibir = " ".join((corpo or assunto).split())[:120]
    return Sugestao(texto, exibir, "A", assunto or mensagem.remetente)


def _deadline(mensagem: Mensagem, prazo) -> Sugestao | None:
    if prazo is None:
        return None
    confianca = "A" if mensagem.data_referencia else "M"
    exibir = f"{prazo.data:%d/%m/%Y}" + (f" até {prazo.hora:%H:%M}" if prazo.hora else "")
    return Sugestao(prazo.data, exibir, confianca, prazo.trecho)


def _horario_do_email(mensagem: Mensagem) -> Sugestao | None:
    enviado = mensagem.enviado_em
    if enviado is None:
        return None
    if timezone.is_aware(enviado):
        enviado = timezone.localtime(enviado)
    hora = enviado.time().replace(second=0, microsecond=0)
    return Sugestao(hora, f"{hora:%H:%M}", "A", f"Enviado em {enviado:%d/%m/%Y %H:%M}")


# ---------------------------------------------------------------------------
# Todas as sugestões
# ---------------------------------------------------------------------------


def sugestoes(mensagem: Mensagem, usuario=None) -> Sugestoes:
    """As sugestões para a tela "Novo atendimento", campo a campo."""
    s = Sugestoes()
    referencia = mensagem.data_referencia or timezone.localdate()
    pessoa = quem_pede(mensagem)
    prazo = prazo_do_texto(mensagem.texto_para_busca, referencia)

    s.por("data", data_do_email(mensagem))
    s.por("horario", _horario_do_email(mensagem))
    s.por("jornalista", _jornalista(pessoa, mensagem))
    _veiculo(s, mensagem)
    s.por("contato", _contato(pessoa, mensagem))
    s.por("pedido", _pedido(mensagem, prazo))
    s.por("deadline", _deadline(mensagem, prazo))
    s.por("responsavel", Sugestao.de_achado(integrante_do_usuario(usuario, Responsavel.objects.order_by("nome"))))
    if prazo is not None and prazo.data < timezone.localdate():
        s.avisar(f"O prazo pedido ({prazo.data:%d/%m/%Y}) já passou: confira.")
    return s
