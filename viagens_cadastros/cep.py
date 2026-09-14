"""Consulta de endereço sem persistência, com o contrato JSON usado pelo GV."""
import json
from urllib.error import URLError
from urllib.request import Request, urlopen

from cadastros.models import Estado


class CEPIndisponivel(Exception):
    pass


class CEPNaoEncontrado(Exception):
    pass


def consultar_cep(cep):
    # O projeto já usa urllib para o IBGE; não exige uma dependência adicional.
    requisicao = Request(f"https://viacep.com.br/ws/{cep}/json/", headers={"Accept": "application/json"})
    try:
        with urlopen(requisicao, timeout=5) as resposta:
            dados = json.loads(resposta.read().decode("utf-8"))
    except (URLError, OSError, ValueError) as exc:
        raise CEPIndisponivel from exc
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
