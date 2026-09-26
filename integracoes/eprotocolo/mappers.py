"""Ofício → payload do eProtocolo.

Lemos atributos do model e completamos com os códigos institucionais do
``.env``. Nenhuma regra de documento é reescrita aqui: o assunto, o motivo e
os destinos já existem no ofício, este módulo só traduz.

Duas funções, de propósito:

``mapear_oficio_para_protocolo``
    nunca quebra — campo ausente vira vazio. É o que o modo simulado usa.

``mapear_oficio_para_payload_eprotocolo``
    valida antes de sair para a rede. Um protocolo aberto com assunto vazio
    ou sem os códigos institucionais é um processo errado dentro do
    eProtocolo, e apagar de lá não é trivial: é melhor recusar aqui.
"""

from __future__ import annotations

from core.errors import capture

from . import settings as cfg
from .exceptions import EProtocoloValidationError

#: Códigos sem os quais a API recusa a criação. Conferidos antes da chamada,
#: para o erro chegar em português e não como HTTP 400.
CAMPOS_INSTITUCIONAIS_OBRIGATORIOS = {
    "codOrgao": "EPROTOCOLO_COD_ORGAO_PADRAO",
    "codLocalOrigem": "EPROTOCOLO_COD_LOCAL_ORIGEM_PADRAO",
    "codAssunto": "EPROTOCOLO_COD_ASSUNTO_VIAGEM",
    "codEspecie": "EPROTOCOLO_COD_ESPECIE_OFICIO",
}


class _Vazio:
    """Manager ausente não pode derrubar o payload."""

    def all(self):
        return []


def _defaults_institucionais() -> dict:
    return {
        "codOrgao": cfg.get("COD_ORGAO_PADRAO", ""),
        "nomeOrgao": cfg.get("NOME_ORGAO_PADRAO", ""),
        "codLocalOrigem": cfg.get("COD_LOCAL_ORIGEM_PADRAO", ""),
        "codLocalDestino": cfg.get("COD_LOCAL_DESTINO_PADRAO", ""),
        "codAssunto": cfg.get("COD_ASSUNTO_VIAGEM", ""),
        "codEspecie": cfg.get("COD_ESPECIE_OFICIO", ""),
        "codPalavraChave": cfg.get("COD_PALAVRA_CHAVE_VIAGEM", ""),
        "cpfInteressado": cfg.get("CPF_USUARIO_SISTEMA", ""),
    }


def _truncar(texto, limite=255) -> str:
    return (texto or "").strip()[:limite]


def _servidores_resumo(qs) -> list[dict]:
    servidores = []
    try:
        for servidor in qs.all():
            servidores.append({
                "nome": getattr(servidor, "nome", "") or str(servidor),
                "cpf": getattr(servidor, "cpf", "") or "",
            })
    except Exception as exc:  # noqa: BLE001 - relação ausente não derruba o payload
        capture(exc, "eprotocolo.mappers.servidores")
    return servidores


def _destinos(oficio) -> list[str]:
    roteiro = getattr(oficio, "roteiro", None)
    if roteiro is None:
        return []
    try:
        return [str(destino.municipio) for destino in roteiro.destinos.all()]
    except Exception as exc:  # noqa: BLE001 - roteiro sem destinos legíveis idem
        capture(exc, "eprotocolo.mappers.destinos")
        return []


def _assunto(oficio) -> str:
    """A linha de assunto do documento, com o campo livre como reserva.

    O documento resolve o assunto por data (autorização/convalidação); é essa
    frase que descreve o processo no eProtocolo, não o texto livre do wizard.
    """
    try:
        from viagens_oficios.assunto_oficio import resolver_assunto_oficio

        resolvido = resolver_assunto_oficio(oficio)
        linha = (resolvido.get("assunto_linha") or "").strip()
        rotulo = (resolvido.get("assunto_rotulo") or "").strip()
        if linha:
            return f"{linha} {rotulo}".strip()
    except Exception as exc:  # noqa: BLE001 - ofício incompleto cai no campo livre
        capture(exc, "eprotocolo.mappers.assunto")
    return (getattr(oficio, "assunto", "") or "").strip()


def mapear_oficio_para_protocolo(oficio) -> dict:
    """Payload mínimo do ofício. Tolerante: nunca levanta."""
    payload = _defaults_institucionais()
    payload.update({
        "tipoOrigem": "OFICIO",
        "numeroDocumento": getattr(oficio, "numero", None),
        "anoDocumento": getattr(oficio, "ano", None),
        "referenciaDocumento": getattr(oficio, "numero_formatado", "") or "",
        "assunto": _truncar(_assunto(oficio)),
        "descricao": _truncar(getattr(oficio, "motivo", "") or _assunto(oficio), 1000),
        "custeio": getattr(oficio, "custeio", "") or "",
        "unidadeSolicitante": str(getattr(oficio, "solicitante", "") or ""),
        "servidores": _servidores_resumo(getattr(oficio, "servidores", None) or _Vazio()),
        "destinos": _destinos(oficio),
    })
    return payload


def validar_payload_institucional(payload: dict) -> list[str]:
    """Códigos institucionais obrigatórios ainda vazios, com o nome da variável."""
    return [
        f"{campo} ({env})"
        for campo, env in CAMPOS_INSTITUCIONAIS_OBRIGATORIOS.items()
        if not str(payload.get(campo) or "").strip()
    ]


def mapear_oficio_para_payload_eprotocolo(oficio) -> dict:
    """Payload validado — o que sai para a rede no modo real."""
    payload = mapear_oficio_para_protocolo(oficio)

    if not str(payload.get("numeroDocumento") or "").strip():
        raise EProtocoloValidationError(
            "Ofício sem número definido — não é possível abrir o protocolo."
        )
    if not (payload.get("assunto") or "").strip():
        raise EProtocoloValidationError("Ofício sem assunto para o protocolo.")
    if not (payload.get("descricao") or "").strip():
        raise EProtocoloValidationError(
            "Ofício sem motivo — o eProtocolo exige a descrição do processo."
        )

    faltantes = validar_payload_institucional(payload)
    if faltantes:
        raise EProtocoloValidationError(
            "Códigos institucionais ausentes no .env: " + ", ".join(faltantes)
        )
    return payload


def mapear_pagamento_coffee(*, textos: dict, partes: list, fornecedor, numero_oficio: str = "") -> dict:
    """Protocolo de pagamento do Coffee Break → payload do eProtocolo.

    Ponto de entrada da integração futura (hoje o protocolo se abre à mão;
    ver coffee_break/protocolo_pagamento.py). Recebe o que a etapa 3 já
    mostra para copiar (``documentos.textos_eprotocolo``) e os quatro
    arquivos do anexo na ordem (``documentos.partes_do_anexo``), e só traduz
    — nunca quebra. Antes de ir para a rede, falta o equivalente de
    ``mapear_oficio_para_payload_eprotocolo`` (validação e códigos
    institucionais de assunto/espécie do pagamento, que ainda não existem no
    ``.env``) e o cliente de ``Endpoints.DOCUMENTOS`` para os anexos.
    """
    campos = {c.get("rotulo"): c.get("valor") for c in textos.get("campos", [])}
    payload = _defaults_institucionais()
    payload.update({
        "numeroDocumento": _truncar(numero_oficio, 40),
        "assunto": _truncar(campos.get("Assunto")),
        "palavrasChave": _truncar(campos.get("Palavras-chave")),
        "descricao": _truncar(textos.get("detalhamento"), 1000),
        "interessado": {
            "nome": _truncar(getattr(fornecedor, "razao_social", "")),
            "cnpj": getattr(fornecedor, "cnpj", "") or "",
        },
        "despacho": _truncar(textos.get("despacho"), 2000),
        # A ordem dos anexos é a do processo; cada parte vira um documento.
        "documentos": [
            {"ordem": ordem, "titulo": parte.get("titulo", ""), "chave": parte.get("chave", "")}
            for ordem, parte in enumerate(partes, start=1)
            if parte.get("disponivel")
        ],
    })
    return payload
