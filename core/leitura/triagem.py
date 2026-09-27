"""Para qual módulo vai um e-mail: coffee break, imprensa, publicações, evento social ou palestra.

Pontuação por sinais no assunto (vale o dobro), no corpo, na assinatura e
no domínio do remetente. A tela mostra os dois melhores para o usuário
confirmar; nada é decidido sozinho. Puro: não consulta banco.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable

from .datas import dobrar

__all__ = ["Destino", "MODULOS", "triar", "triar_mensagem"]

MODULOS = {
    "coffee_break": "Coffee break",
    "atendimento_imprensa": "Atendimento à imprensa",
    "publicacoes": "Publicações",
    "solicitacoes": "Evento social",
    "demandas_eventos": "Palestras e eventos",
}

# (expressão no texto dobrado, peso, rótulo do sinal)
_SINAIS: dict[str, list[tuple[re.Pattern, float, str]]] = {
    "coffee_break": [
        (re.compile(r"\bcof+e+\b|\bcof+e+[\s-]?break\b"), 3, "coffee break"),
        (re.compile(r"\bcafe\b"), 1.5, "café"),
        (re.compile(r"\bkits?\s+(?:de\s+)?lanches?\b|\blanches?\b"), 2, "lanche"),
        (re.compile(r"\bsalgad(?:o|os|inhos)\b"), 1.5, "salgados"),
        (re.compile(r"\bbuffet\b|\bcoquetel\b"), 1, "buffet"),
        (re.compile(r"\blocal\s+de\s+entrega\b|\bentregar\s+n[oa]\b|\bhorario\s+(?:da|de)\s+entrega\b"), 3, "entrega"),
        (re.compile(r"\brecebe\s*:|\bresponsavel\s+(?:pelo\s+)?recebimento\b|\bquem\s+(?:vai\s+)?receber?\b"), 2, "quem recebe"),
        (re.compile(r"\b(?:coffee|cafe|lanches?|kits?)\s+(?:break\s+)?(?:para|p/|pra)\s+\d+"), 3, "lanche para N pessoas"),
    ],
    "atendimento_imprensa": [
        (re.compile(r"\bentrevistas?\b"), 2, "entrevista"),
        (re.compile(r"\bposicionamento\b"), 2, "posicionamento"),
        (re.compile(r"\bnota\b(?!\s+fiscal)|\bnota\s+oficial\b"), 1, "nota"),
        (re.compile(r"\bdeadline\b"), 2, "deadline"),
        (re.compile(r"\bmaterias?\b|\breportage[mn]s?\b"), 1.5, "matéria"),
        (re.compile(r"\bimprensa\b"), 1, "imprensa"),
        (re.compile(r"\bsonora\b|\bvai\s+ao\s+ar\b|\bfechamento\s+da\s+(?:edicao|materia)\b"), 1.5, "fechamento"),
        # Quem pergunta à polícia (o jornalista) e não quem manda o release.
        (_R_PERGUNTA_IMPRENSA := re.compile(
            r"\b(?:voces|vcs)\s+(?:ja\s+)?(?:confirma\w*|sabem|tem\s+(?:alguma\s+)?(?:informac|posicionamento|dados|nota|numero)\w*|teriam\s+(?:dados|informac)\w*)"
            r"|\b(?:voces|vcs)\s+(?:podem|poderiam|conseguem)\s+(?:me\s+)?(?:confirmar|informar|passar|enviar|mandar)\b"
            r"|\bconsegue[m]?\s+(?:me\s+)?(?:passar|enviar|mandar|informar|confirmar|os\s+dados|o\s+numero|dados)\b"
            r"|\bgostaria\s+de\s+(?:saber|confirmar|informac\w*|um\s+posicionamento|uma\s+nota)\b"
            r"|\bpoderiam\s+(?:me\s+)?(?:informar|confirmar|passar|enviar)\b|\bpedido\s+de\s+informac\w*\b"
            r"|\bsolicito\s+(?:o\s+numero|os\s+dados|dados|nota|um\s+posicionamento|sonora|informac\w*)\b"
            r"|\bja\s+(?:tem|ha|existe)\s+(?:suspeit|laudo|previsao|informac)\w*"
            r"|\b(?:consigo|conseguimos|podemos|queremos|quero|queria|gostariamos\s+de)\s+(?:uma\s+|um\s+)?(?:entrevista|sonora|gravar|posicionamento|nota)\b"
            r"|\b(?:preciso|precisamos)\s+(?:de\s+)?(?:confirmar|uma\s+nota|um\s+posicionamento|de\s+uma\s+sonora|saber)\b"
            r"|\bpode(?:m)?\s+(?:me\s+)?responder\b"), 2.5, "pergunta à polícia"),
        (re.compile(r"\bpodcasts?\b|\bepisodios?\b|\bcanal\s+(?:do|no)\s+youtube\b|\bprograma\s+de\s+(?:radio|tv)\b"), 2, "podcast/programa"),
        (re.compile(r"\b(?:queria|vamos|vou|pretendo|pretendemos)\s+publicar\b|\bpublicamos\b|\bnossa\s+materia\b"
                    r"|\bestamos\s+fechando\b|\bfechamos\b|\btelejornal\b|\bedicao\s+d[eoa]\b|\bao\s+vivo\b"), 2, "veiculação"),
        (re.compile(r"\bdados\s+(?:de|sobre|estatisticos|do|da)\b|\bestatisticas?\b|\blevantamento\s+d[eo]s?\b"
                    r"|\bnumero\s+de\s+(?:presos|mandados|casos|ocorrencias|pessoas|homicidios|boletins|vitimas)\b"), 1.5, "pedido de dados"),
        (re.compile(r"\b(?:do|da|no|na)\s+(?:portal|jornal|gazeta|radio|tv|agencia|revista|folha|diario|tribuna|blog|site\s+de\s+noticias|programa|emissora)\b"
                    r"|\bagencia\s+\w+\s+de\s+noticias\b|\b\d{2,3}[,.]?\d?\s*fm\b|\b(?:radio|tv)\s+[a-z]"), 2, "veículo de imprensa"),
    ],
    "publicacoes": [
        (re.compile(r"\breleases?\b"), 3, "release"),
        (re.compile(r"\bpara\s+(?:a\s+)?divulgacao\b|\bdivulgar\b|\bdivulgacao\b"), 2, "para divulgação"),
        (re.compile(r"\b(?:segue|seguem|encaminho)\s+(?:\w+\s+){0,3}(?:para|p/)\s+(?:publicac|divulgac|o\s+site|as\s+redes)\w*"
                    r"|\b(?:favor|por\s+favor)\s+(?:publicar|divulgar)\b|\bpara\s+publicac\w*\b|\bsugest\w+\s+de\s+titulo\b|\btitulo\s+sugest\w*\b"
                    r"|\bfazer\s+uma\s+materia\b|\bsem\s+(?:divulgar\s+)?nomes\b"), 3, "pedido de publicação"),
        (re.compile(r"\b(?:pcpr|policia\s+civil|[a-z]{3,}|\d+a?\s+sdp)\s+(?:prende|apreende|esclarece|cumpre|deflagra|recupera|localiza|resgata|indicia|identifica|desarticula|prendem|resgatam|apreendem|cumprem|deflagram|recuperam)\b"), 3, "título de release"),
        (re.compile(r"\bprend(?:e|eu|eram|em|emos)\b|\bapreend(?:e|eu|eram|em)\b|\bcumpri(?:u|ram)\s+mandados?\b"), 1.5, "prisão"),
        (re.compile(r"\boperac(?:ao|oes)\b"), 1.5, "operação"),
        (re.compile(r"\bpris(?:ao|oes)\b|\bpres[oa]s?\b|\bflagrante\b"), 1.5, "prisão"),
        (re.compile(r"\bmandados?\b"), 1.5, "mandado"),
        (re.compile(r"\bapreens(?:ao|oes)\b|\bapreendid[oa]s?\b"), 1, "apreensão"),
    ],
    "solicitacoes": [
        (re.compile(r"\bcin\b|\brg\b|\bcarteiras?\s+de\s+identidade\b|\bidentidade\b"), 2, "RG/CIN"),
        (re.compile(r"\bemiss(?:ao|oes)\s+d[aeo]s?\s+(?:cin|rg|carteiras?|documentos?|identidade|nova\s+identidade)\b"), 3, "emissão de identidade"),
        (re.compile(r"\bidentificacao\s+civil\b|\binstituto\s+de\s+identificacao\b|\biipr\b"), 3, "identificação civil"),
        (re.compile(r"\bposto\s+(?:movel|de\s+atendimento)\b|\batendimento\s+in\s+loco\b|\bkits?\s+biometric"), 2, "posto de atendimento"),
        (re.compile(r"\bcrianca\s+e\s+adolescente\s+protegidos\b"), 3, "Criança e Adolescente Protegidos"),
        (re.compile(r"\bunidade\s+movel\b|\bonibus\s+(?:d[aoe]\s+)?(?:cidadania|identificacao|pcpr|policia|atendimento)\b|\bcarreta\b"), 3, "unidade móvel"),
        (re.compile(r"\bparana\s+em\s+acao\b"), 3, "Paraná em Ação"),
        (re.compile(r"\bjustica\s+no\s+bairro\b"), 3, "Justiça no Bairro"),
        (re.compile(r"\bmutirao\b"), 2, "mutirão"),
        (re.compile(r"\bacao\s+social\b|\bacao\s+de\s+cidadania\b"), 2, "ação social"),
        (re.compile(r"\bfeiras?\b"), 1, "feira"),
        (re.compile(r"\bemissao\s+de\s+documentos\b|\bcoleta\s+de\s+digitais\b|\bbiometria\b"), 2, "emissão de documentos"),
        # Os serviços que só a unidade móvel / o evento social leva.
        (re.compile(r"\bfotos?\s+3\s?x\s?4\b|\bfotografia\s+para\s+documento\b"), 2, "fotos para documento"),
        (re.compile(r"\borientac\w+\s+juridica\b|\batendimento\s+juridico\b"), 1.5, "orientação jurídica"),
        (re.compile(r"\bviaturas?\b[^.\n]{0,60}\b(?:expo\w*|desfil\w*|antigas?|historic\w*|exibi\w*)|"
                    r"\b(?:expo\w*|desfil\w*|encontro\s+de\s+(?:carros|veiculos|motociclistas|viaturas))\b[^.\n]{0,60}\bviaturas?\b"), 3, "exposição de viaturas"),
        (re.compile(r"\bcarteiras\b"), 1.5, "carteiras"),
        (re.compile(r"\bdigitais\b|\bsegunda\s+via\b|\b1a\s+via\b|\bprimeira\s+via\b"), 1.5, "documentos"),
    ],
    "demandas_eventos": [
        (re.compile(r"\bpalestras?\b"), 3, "palestra"),
        (re.compile(r"\bescolas?\b|\bcolegios?\b"), 1.5, "escola"),
        (re.compile(r"\balun[oa]s?\b|\bestudantes\b"), 1.5, "alunos"),
        (re.compile(r"\bpcpr\s+na\s+comunidade\b"), 3, "PCPR na Comunidade"),
        (re.compile(r"\bbate[\s-]?papo\b|\broda\s+de\s+conversa\b"), 2, "bate-papo"),
        (re.compile(r"\bconscientizacao\b|\borientacao\s+sobre\b"), 1, "conscientização"),
        (re.compile(r"\btemas?\b"), 0.5, "tema"),
        (re.compile(r"\bcapacitac\w+|\bcursos?\b|\boficinas?\b|\bworkshops?\b|\binstrutor\w*|\bministrar\b|\bseminarios?\b|\bforum\b|\bcongresso\b|\bsimposio\b"), 2, "capacitação/seminário"),
        (re.compile(r"\b(?:tem\s+a\s+honra\s+de\s+)?convid\w+\s+(?:a\s+|o\s+)?(?:policia\s+civil|pcpr|vossa|v\.?\s*s\.?|delegad\w+)|\bconvites?\b"), 2, "convite"),
        (re.compile(r"\bsessao\s+solene\b|\bformatura\b|\bdesfile\b|\bcompor\s+a\s+mesa\b|\bmesa\s+de\s+abertura\b|\baudiencia\s+publica\b|\bhomenage\w+|\bmoc(?:ao|oes)\s+de\b|\bsolenidade\b|\bcerimonia\w*"), 2, "cerimônia"),
        (re.compile(r"\b(?:falar|conversar|orientar|explicar)\s+(?:sobre|com|os|as)\b|\bpalestrantes?\b|"
                    r"\bfala\s+(?:rapida\s+)?(?:\([^)]{0,20}\)\s*)?sobre\b"), 1.5, "fala de policial"),
        (re.compile(r"\bdds\b|\bdialogo\s+(?:diario\s+)?de\s+seguranca\b|\bsipat\b|\bsemana\s+(?:interna|academica|de\s+prevencao)\b"), 2, "semana/DDS"),
    ],
}

# Domínio de veículo de imprensa (os mais comuns no Paraná e os genéricos).
_R_DOMINIO_IMPRENSA = re.compile(
    r"@(?:[\w-]+\.)*(?:globo|g1|rpc|rpctv|band|bandab|bandnews|sbt|record|r7|ric|ricmais|gazetadopovo|"
    r"tribunapr|bemparana|cbn|jovempan|uol|folha|folhadelondrina|estadao|cnnbrasil|metropoles|plural|"
    r"massa|paranaportal|tnonline|arede|diariodoscampos|odiario|cgn|catve|lance|terra|ig|bandnewsfm|"
    r"[\w-]*(?:jornal|radio|tv|news|noticias|portal|revista|gazeta|diario|tribuna|folha|agencia|fm|pauta)[\w-]*)"
    r"\.(?:com|jor|net|org|tv|radio|info)(?:\.br)?\b"
)
_R_ASSINATURA_IMPRENSA = re.compile(
    r"\b(?:reporter|produtor[a]?|produc[ao]|redacao|jornalista|editor[a]?|pauteir[oa]|chefe\s+de\s+reportagem|"
    r"assessoria\s+de\s+imprensa|apresentador[a]?)\b"
)
_SINAIS_DE_SERVICO = {
    "RG/CIN", "emissão de identidade", "identificação civil", "unidade móvel", "Paraná em Ação", "Justiça no Bairro",
    "emissão de documentos", "fotos para documento", "orientação jurídica", "exposição de viaturas",
    "documentos", "posto de atendimento", "carteiras",
}
_SINAIS_DE_LANCHE = {"coffee break", "lanche", "entrega", "quem recebe", "lanche para N pessoas", "salgados"}
_R_VEICULO_NO_NOME = re.compile(r"\b(?:portal|jornal|gazeta|radio|tv|agencia|revista|folha|diario|tribuna|blog|redacao|noticias|fm|am)\b")
_R_REMETENTE_PCPR = re.compile(r"@(?:[\w-]+\.)*(?:pc|policiacivil)\.pr\.gov\.br$")


@dataclass(frozen=True)
class Destino:
    """Um módulo candidato, com os pontos, a confiança (0 a 1) e os sinais achados."""

    modulo: str
    rotulo: str
    pontos: float
    confianca: float
    sinais: tuple[str, ...]


def triar(
    *,
    assunto: str = "",
    corpo: str = "",
    assinatura: str = "",
    remetente_email: str = "",
    remetente_nome: str = "",
    modulos: Iterable[str] | None = None,
    extras: dict[str, list[tuple[float, str]]] | None = None,
) -> list[Destino]:
    """Os módulos candidatos, do mais provável ao menos provável (só os com pontos).

    `modulos` limita aos módulos que o usuário acessa. `extras` são pontos de
    fora do texto — {modulo: [(pontos, sinal), ...]} — como a memória dos
    pedidos anteriores do mesmo remetente. A confiança do primeiro cai
    quando o segundo está perto ou quando há poucos sinais.
    """
    permitidos = set(modulos) if modulos is not None else set(MODULOS)
    assunto_d, corpo_d, assinatura_d = dobrar(assunto), dobrar(corpo), dobrar(assinatura)
    email = (remetente_email or "").strip().lower()
    pontos: dict[str, float] = {}
    sinais: dict[str, list[str]] = {}

    def somar(modulo, valor, sinal):
        pontos[modulo] = pontos.get(modulo, 0) + valor
        sinais.setdefault(modulo, []).append(sinal)

    for modulo, regras in _SINAIS.items():
        for regex, peso, rotulo in regras:
            if regex.search(assunto_d):
                somar(modulo, 2 * peso, f"{rotulo} (assunto)")
            elif regex.search(corpo_d):
                somar(modulo, peso, rotulo)
    if email and _R_DOMINIO_IMPRENSA.search(email):
        somar("atendimento_imprensa", 4, "remetente de veículo de imprensa")
    if remetente_nome and _R_VEICULO_NO_NOME.search(dobrar(remetente_nome)):
        somar("atendimento_imprensa", 2, "remetente é veículo de imprensa")
    if _R_ASSINATURA_IMPRENSA.search(assinatura_d):
        somar("atendimento_imprensa", 3, "assinatura de jornalista")
    if email and _R_REMETENTE_PCPR.search(email) and pontos.get("publicacoes"):
        somar("publicacoes", 2, "remetente da PCPR")
    # O convite, o seminário e a palestra descrevem o evento; o que se pede
    # nele decide a tela: serviço da unidade móvel (CIN, fotos, viaturas em
    # exposição…) é Evento social; lanche e entrega é Coffee break.
    if pontos.get("demandas_eventos"):
        if any(s.split(" (")[0] in _SINAIS_DE_SERVICO for s in sinais.get("solicitacoes", [])) and not any(
            s.startswith(("palestra", "bate-papo")) for s in sinais.get("demandas_eventos", [])
        ):
            somar("solicitacoes", 4, "serviço pedido no evento")
            pontos["demandas_eventos"] /= 2
        if any(s.split(" (")[0] in _SINAIS_DE_LANCHE for s in sinais.get("coffee_break", [])):
            somar("coffee_break", 4, "pedido de lanche para o evento")
    # Quem pergunta sobre a prisão é o jornalista; o release conta a prisão.
    # Sem pedido de publicação, as palavras de ocorrência valem metade.
    if pontos.get("publicacoes") and _R_PERGUNTA_IMPRENSA.search(assunto_d + "\n" + corpo_d) and not (
        email and _R_REMETENTE_PCPR.search(email)
    ) and not any(s.startswith(("pedido de publicação", "release", "para divulgação", "título de release")) for s in sinais.get("publicacoes", [])):
        pontos["publicacoes"] /= 2
    for modulo, itens in (extras or {}).items():
        for valor, sinal in itens:
            if modulo in MODULOS and valor:
                somar(modulo, valor, sinal)

    candidatos = sorted(
        ((m, p) for m, p in pontos.items() if p > 0 and m in permitidos), key=lambda c: -c[1]
    )
    total = sum(p for _, p in candidatos)
    destinos = []
    for posicao, (modulo, valor) in enumerate(candidatos):
        segundo = candidatos[posicao + 1][1] if posicao + 1 < len(candidatos) else 0
        margem = valor / (valor + segundo) if posicao == 0 else valor / total
        forca = min(1.0, valor / 6)
        destinos.append(Destino(modulo, MODULOS[modulo], round(valor, 2), round(margem * forca, 2), tuple(sinais[modulo])))
    return destinos


def triar_mensagem(mensagem, *, modulos: Iterable[str] | None = None, extras=None) -> list[Destino]:
    """`triar` a partir de uma `Mensagem` já lida (mensagem.py)."""
    return triar(
        assunto=mensagem.assunto_limpo,
        corpo=mensagem.corpo,
        assinatura=mensagem.assinatura,
        remetente_email=mensagem.remetente_email,
        remetente_nome=getattr(mensagem, "remetente_nome", "") or "",
        modulos=modulos,
        extras=extras,
    )
