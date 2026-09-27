"""Consulta de endereço sem persistência, com o contrato JSON usado pelo GV.

`consultar_cep` (CEP → endereço) e `consultar_logradouro` (UF + cidade + rua →
lista de CEPs) usam o ViaCEP. O buscador de endereço das telas de eventos
(`core.buscar_endereco`) usa os dois com timeout curto.
"""
import json
from urllib.error import URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

from cadastros.models import Estado


class CEPIndisponivel(Exception):
    pass


class CEPNaoEncontrado(Exception):
    pass


def _buscar_json(url, timeout):
    # O projeto já usa urllib para o IBGE; não exige uma dependência adicional.
    requisicao = Request(url, headers={"Accept": "application/json"})
    try:
        with urlopen(requisicao, timeout=timeout) as resposta:
            return json.loads(resposta.read().decode("utf-8"))
    except (URLError, OSError, ValueError) as exc:
        raise CEPIndisponivel from exc


def consultar_cep(cep, timeout=5):
    dados = _buscar_json(f"https://viacep.com.br/ws/{cep}/json/", timeout)
    if not isinstance(dados, dict):
        raise CEPIndisponivel
    if dados.get("erro"):
        raise CEPNaoEncontrado
    uf = (dados.get("uf") or "").strip().upper()
    estado = Estado.objects.filter(sigla=uf).values_list("nome", flat=True).first() if uf else ""
    return {
        "cep": dados.get("cep") or f"{cep[:5]}-{cep[5:]}",
        "logradouro": dados.get("logradouro") or "",
        "bairro": dados.get("bairro") or "",
        "cidade": dados.get("localidade") or "",
        "uf": uf,
        "estado": estado or dados.get("estado") or "",
    }


def consultar_logradouro(uf, cidade, rua, timeout=5):
    """Endereços do ViaCEP pelo nome da rua numa cidade (lista, talvez vazia).

    O ViaCEP exige UF, cidade e ao menos 3 letras da rua; cada item traz
    `cep`, `logradouro`, `bairro`, `cidade` e `uf`. Falha de rede ou resposta
    estranha: `CEPIndisponivel`.
    """
    uf = (uf or "").strip().upper()
    cidade = (cidade or "").strip()
    rua = (rua or "").strip()
    if len(uf) != 2 or not cidade or len(rua) < 3:
        return []
    url = "https://viacep.com.br/ws/{}/{}/{}/json/".format(
        quote(uf, safe=""), quote(cidade, safe=""), quote(rua, safe="")
    )
    dados = _buscar_json(url, timeout)
    if isinstance(dados, dict) and dados.get("erro"):
        return []
    if not isinstance(dados, list):
        raise CEPIndisponivel
    return [
        {
            "cep": item.get("cep") or "",
            "logradouro": item.get("logradouro") or "",
            "bairro": item.get("bairro") or "",
            "cidade": item.get("localidade") or "",
            "uf": (item.get("uf") or "").strip().upper(),
        }
        for item in dados
        if isinstance(item, dict)
    ]
