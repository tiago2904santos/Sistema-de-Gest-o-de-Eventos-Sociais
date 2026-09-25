"""O integrante da equipe que é o usuário logado, pelo nome.

Os cadastros de equipe da ASCOM (o `Responsavel` do Atendimento à Imprensa
e o das Publicações) só têm o nome curto que a planilha usava — "Mariana",
"João P" — e não se ligam ao usuário do sistema. Para sugerir "quem está
registrando" num formulário novo, o nome do usuário é casado com esses
cadastros: nome inteiro, primeiro nome, ou nome com a inicial do sobrenome.

Só responde quando um integrante casa melhor que todos os outros: com dois
"Mariana" no cadastro e uma usuária Mariana, não há sugestão.
"""

from __future__ import annotations

import re
from typing import Iterable

from core.leitura.casamento import Achado
from core.leitura.datas import dobrar

__all__ = ["integrante_do_usuario"]


def _palavras(texto: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", dobrar(texto or ""))


def _nomes_do_usuario(usuario) -> list[list[str]]:
    """As formas do nome do usuário, da mais completa para a mais curta."""
    completo = _palavras(" ".join(x for x in (getattr(usuario, "first_name", ""), getattr(usuario, "last_name", "")) if x))
    if not completo:
        # Sem nome no cadastro, o login costuma ser "nome.sobrenome".
        completo = _palavras(re.sub(r"[._-]+", " ", getattr(usuario, "username", "") or ""))
        completo = [p for p in completo if not p.isdigit()]
    return [completo] if completo else []


def _casa(integrante: list[str], usuario: list[str]) -> int:
    """Quantas palavras do integrante casam, em ordem, com o nome do usuário (0 = não casa).

    A primeira palavra tem de ser o primeiro nome; as outras podem pular
    sobrenomes do meio, e uma letra só ("João P") vale como inicial.
    """
    if not integrante or not usuario or integrante[0] != usuario[0]:
        return 0
    posicao = 1
    for palavra in integrante[1:]:
        while posicao < len(usuario):
            candidato = usuario[posicao]
            posicao += 1
            if candidato == palavra or (len(palavra) == 1 and candidato.startswith(palavra)):
                break
        else:
            return 0
    return len(integrante)


def integrante_do_usuario(usuario, integrantes: Iterable) -> Achado | None:
    """O integrante (do queryset ou lista `integrantes`) que é o `usuario`, ou None.

    O mais parecido ganha ("Mariana C" vence "Mariana" para Mariana Costa);
    empate entre dois é dúvida, e dúvida não vira sugestão. Confiança "M":
    preenche e destaca para conferir.
    """
    if usuario is None or not getattr(usuario, "is_authenticated", False):
        return None
    nomes = _nomes_do_usuario(usuario)
    if not nomes:
        return None
    melhores: list = []
    maior = 0
    for integrante in integrantes:
        pontos = max(_casa(_palavras(integrante.nome), nome) for nome in nomes)
        if not pontos:
            continue
        if pontos > maior:
            melhores, maior = [integrante], pontos
        elif pontos == maior:
            melhores.append(integrante)
    if len(melhores) != 1:
        return None
    integrante = melhores[0]
    rotulo = usuario.get_full_name() or usuario.get_username()
    return Achado(integrante, integrante.nome, f"Usuário que está registrando: {rotulo}", "M")
