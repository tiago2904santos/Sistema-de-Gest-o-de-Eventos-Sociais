"""Leitura da configuração da integração, em um lugar só.

O resto do pacote não fala com ``django.conf.settings`` diretamente: pergunta
aqui. Assim a decisão "isto vai à rede ou é simulado?" tem uma única fonte, e
a ausência de credencial nunca vira exceção no meio de um cadastro.
"""

from __future__ import annotations

from django.conf import settings

AMBIENTE_MOCK = "mock"
AMBIENTE_TREINAMENTO = "treinamento"
AMBIENTE_HOMOLOGACAO = "homologacao"
AMBIENTE_PRODUCAO = "producao"

#: Ambientes que disparam chamadas HTTP reais quando há credenciais.
AMBIENTES_REAIS = (AMBIENTE_TREINAMENTO, AMBIENTE_HOMOLOGACAO, AMBIENTE_PRODUCAO)

#: Sem estes campos o modo real não tem como operar.
CAMPOS_OBRIGATORIOS_REAL = (
    "BASE_URL", "TOKEN_URL", "CLIENT_ID", "CLIENT_SECRET", "CONSUMER_ID",
)


def get_config() -> dict:
    """Cópia rasa da configuração — segura para leitura e para teste."""
    return dict(getattr(settings, "EPROTOCOLO", {}) or {})


def get(chave: str, default=None):
    return get_config().get(chave, default)


def ambiente() -> str:
    return (get("AMBIENTE") or AMBIENTE_MOCK).strip().lower()


def is_producao() -> bool:
    return ambiente() == AMBIENTE_PRODUCAO


def is_real() -> bool:
    """O ambiente configurado pretende falar com a API real."""
    return ambiente() in AMBIENTES_REAIS


def numero_e_oficial() -> bool:
    """O número aberto neste ambiente vale como protocolo oficial?

    Só em produção. Treinamento e homologação abrem processo de verdade no
    barramento de teste — número existe, mas não serve para protocolar; e o
    modo simulado nem sai daqui. A distinção é do ambiente, não da chamada,
    então mora aqui e não em quem chama.
    """
    return is_producao() and not em_modo_mock()


def real_readonly() -> bool:
    """Trava de segurança: no modo real, só consulta (padrão)."""
    return bool(get("REAL_READONLY", True))


def _tem_credenciais() -> bool:
    cfg = get_config()
    return all((cfg.get(chave) or "").strip() for chave in CAMPOS_OBRIGATORIOS_REAL)


def em_modo_mock() -> bool:
    """True quando o client não deve tocar a rede.

    Vale tanto para o ambiente declarado ``mock`` quanto para a falta de
    credencial: sem ela não há chamada real possível, e o sistema segue
    funcionando com números simulados, claramente marcados como tal.
    """
    if ambiente() == AMBIENTE_MOCK:
        return True
    return not _tem_credenciais()


def mutacao_real_liberada() -> bool:
    """Abrir protocolo é mutação: exige modo real, credencial e a trava aberta."""
    return is_real() and _tem_credenciais() and not real_readonly()


def campos_faltantes() -> list[str]:
    cfg = get_config()
    return [c for c in CAMPOS_OBRIGATORIOS_REAL if not (cfg.get(c) or "").strip()]


def eprotocolo_esta_configurado() -> bool:
    """Há credencial real e o ambiente não é mock (usado na UI/diagnóstico)."""
    return is_real() and _tem_credenciais()


def auto_protocolo_oficio() -> bool:
    """O ofício abre protocolo sozinho ao ser gravado?"""
    return bool(get("AUTO_PROTOCOLO_OFICIO", True))


def descricao_ambiente() -> str:
    """Frase curta do estado atual da integração, para a tela e o diagnóstico."""
    if eprotocolo_esta_configurado():
        if real_readonly():
            return f"Integração ativa ({ambiente()}, somente consulta)"
        if not is_producao():
            return f"Integração ativa ({ambiente()}) — números de teste, não oficiais"
        return f"Integração ativa ({ambiente()})"
    if ambiente() == AMBIENTE_MOCK:
        return "Modo simulado (sem integração real)"
    return f"Modo simulado — credenciais do eProtocolo ausentes ({ambiente()})"


def mascarar_segredo(valor: str | None, *, visiveis: int = 4) -> str:
    """``abcd****`` — nunca o valor inteiro. Vazio vira ``(não configurado)``."""
    texto = (valor or "").strip()
    if not texto:
        return "(não configurado)"
    if len(texto) <= visiveis:
        return "*" * len(texto)
    return f"{texto[:visiveis]}{'*' * min(4, len(texto) - visiveis)}"


def validar_configuracao() -> dict:
    """Resumo seguro da configuração para o comando de diagnóstico.

    Não chama a rede e não expõe segredo: diz apenas o que está presente.
    """
    cfg = get_config()
    amb = ambiente()
    faltantes = campos_faltantes()
    real = amb in AMBIENTES_REAIS
    return {
        "ambiente": amb,
        "modo_real": real,
        "producao": amb == AMBIENTE_PRODUCAO,
        "base_url_configurada": bool((cfg.get("BASE_URL") or "").strip()),
        "token_url_configurada": bool((cfg.get("TOKEN_URL") or "").strip()),
        "client_id": mascarar_segredo(cfg.get("CLIENT_ID")),
        "client_secret_configurado": bool((cfg.get("CLIENT_SECRET") or "").strip()),
        "consumer_id": mascarar_segredo(cfg.get("CONSUMER_ID")),
        "timeout": cfg.get("TIMEOUT", 30),
        "verify_ssl": bool(cfg.get("VERIFY_SSL", True)),
        "read_only": real_readonly(),
        "mutacao_liberada": mutacao_real_liberada(),
        "numero_oficial": numero_e_oficial(),
        "auto_protocolo_oficio": auto_protocolo_oficio(),
        "campos_faltantes": faltantes,
        "ok": (not real) or not faltantes,
    }
