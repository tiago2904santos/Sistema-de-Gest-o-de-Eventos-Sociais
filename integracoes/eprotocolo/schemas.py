"""Caminhos dos endpoints e o resultado normalizado das operações.

Os paths ficam centralizados porque a documentação oficial muda de versão:
trocar aqui propaga para todos os services. Em modo simulado eles não são
usados — nenhuma chamada sai.
"""

from __future__ import annotations

from dataclasses import dataclass, field


class Endpoints:
    """Caminhos relativos à ``BASE_URL`` do barramento ``spi-servicos`` (v3).

    A ``BASE_URL`` (host e eventual segmento ``spi-servicos``) vem do ``.env``.
    Confirme os paths na documentação oficial antes de ligar em produção.
    """

    CRIAR_PROTOCOLO = "/v3/protocolos"
    CONSULTAR_PROTOCOLO = "/v3/protocolos/{numero}"
    DOCUMENTOS = "/v3/protocolos/{numero}/documentos"
    MOVIMENTACOES = "/v3/protocolos/{numero}/movimentacoes"

    # Tabelas auxiliares — usadas só pelo diagnóstico.
    ORGAOS = "/v3/orgaos"
    LOCAIS = "/v3/locais"
    ASSUNTOS = "/v3/assuntos"
    ESPECIES = "/v3/especies"


#: Escopos OAuth2 a pedir à Celepar/SEAP. Não entram em chamada nenhuma —
#: servem de documentação e de saída do comando de diagnóstico.
ESCOPOS_ESPERADOS = (
    "spiserv.protocolos.consultar",
    "spiserv.protocolos.incluir",
    "spiserv.protocolos.documentos.consultar",
    "spiserv.protocolos.documentos.incluir",
    "spiserv.protocolos.movimentacoes.consultar",
    "spiserv.orgaos.consultar",
    "spiserv.locais.consultar",
    "spiserv.assuntos.consultar",
    "spiserv.especies.consultar",
)


@dataclass
class ResultadoOperacao:
    """Resultado de uma operação, com a marca de simulado.

    Quem chama sabe se o número veio do eProtocolo ou do modo simulado sem
    precisar inspecionar credencial nem payload bruto.
    """

    sucesso: bool
    dados: dict = field(default_factory=dict)
    mock: bool = False
    mensagem: str = ""
