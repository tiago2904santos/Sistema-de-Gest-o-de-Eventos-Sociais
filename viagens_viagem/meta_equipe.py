"""O contador "servidores designados x servidores em ofícios" da viagem.

A DG designa equipes com quantidade ("ASCOM: 2"); quem monta a viagem faz um
ofício com um servidor, depois outro — ou põe os dois no mesmo ofício. Até a
soma dos ofícios não cancelados bater a meta, a viagem mostra quantos faltam
e de qual equipe. O servidor conta uma vez só, mesmo em dois ofícios.

Com uma equipe prevista, todo servidor dos ofícios conta para ela. Com mais
de uma, o servidor é atribuído pela lotação (unidade com o nome ou a sigla da
equipe); quem não se encaixa completa as equipes que ainda têm falta, na
ordem — ninguém fica de fora da conta por causa de cadastro incompleto.
"""

from __future__ import annotations

import re
import unicodedata


def chave_de_nome(texto) -> str:
    """Nome comparável: sem acento, sem pontuação, maiúsculo."""
    texto = unicodedata.normalize("NFKD", str(texto or ""))
    texto = "".join(c for c in texto if not unicodedata.combining(c)).upper()
    return " ".join(re.sub(r"[^A-Z0-9]+", " ", texto).split())


def nomes_combinam(nome, *candidatos) -> bool:
    """"ASCOM" combina com "ASCOM", "Assessoria de Comunicação (ASCOM)" etc.

    Igual, ou um contido no outro como palavra inteira — sigla solta dentro
    do nome por extenso é o caso comum.
    """
    alvo = chave_de_nome(nome)
    if not alvo:
        return False
    for candidato in candidatos:
        outro = chave_de_nome(candidato)
        if not outro:
            continue
        if alvo == outro:
            return True
        maior, menor = sorted((alvo, outro), key=len, reverse=True)
        if f" {menor} " in f" {maior} ":
            return True
    return False


def _plural(n, singular, plural):
    return singular if n == 1 else plural


def servidores_em_oficios(viagem) -> list:
    """Servidores distintos dos ofícios não cancelados (aproveita o prefetch)."""
    vistos = {}
    for oficio in viagem.oficios.all():
        if oficio.cancelado:
            continue
        for servidor in oficio.servidores.all():
            vistos.setdefault(servidor.pk, servidor)
    return list(vistos.values())


def contador_de_servidores(viagem):
    """A meta por equipe e o que os ofícios já cobrem; None sem equipe prevista.

    Devolve {linhas, previstos, em_oficios, faltam, completo, texto, tom}. Cada
    linha: {nome, previstos (None = sem quantidade), em_oficios, faltam}.
    """
    if viagem is None or not viagem.pk:
        return None
    previstas = sorted(viagem.equipes_previstas.all(), key=lambda p: str(p.equipe))
    if not previstas:
        return None
    servidores = servidores_em_oficios(viagem)
    linhas = [
        {"nome": str(p.equipe), "previstos": p.quantidade or None, "em_oficios": 0, "faltam": None}
        for p in previstas
    ]

    if len(linhas) == 1:
        linhas[0]["em_oficios"] = len(servidores)
    else:
        sobras = []
        for servidor in servidores:
            unidade = servidor.unidade if servidor.unidade_id else None
            linha = None
            if unidade is not None:
                linha = next(
                    (l for l in linhas if nomes_combinam(l["nome"], unidade.nome, unidade.sigla)),
                    None,
                )
            if linha is None:
                sobras.append(servidor)
            else:
                linha["em_oficios"] += 1
        for linha in linhas:
            while sobras and linha["previstos"] and linha["em_oficios"] < linha["previstos"]:
                sobras.pop()
                linha["em_oficios"] += 1
        # O que sobrou (equipe sem quantidade ou meta já batida) fica na
        # primeira sem quantidade, se houver; senão só entra no total.
        sem_meta = next((l for l in linhas if not l["previstos"]), None)
        if sem_meta is not None:
            sem_meta["em_oficios"] += len(sobras)

    for linha in linhas:
        if linha["previstos"]:
            linha["faltam"] = max(linha["previstos"] - linha["em_oficios"], 0)

    com_meta = [l for l in linhas if l["previstos"]]
    previstos = sum(l["previstos"] for l in com_meta)
    faltam = sum(l["faltam"] for l in com_meta)
    total = len(servidores)
    sem_quantidade = [l["nome"] for l in linhas if not l["previstos"]]

    if faltam:
        pendentes = [l for l in com_meta if l["faltam"]]
        if len(pendentes) == 1:
            nome = pendentes[0]["nome"]
            texto = f"Faltam {faltam} servidores da {nome}." if faltam > 1 else f"Falta 1 servidor da {nome}."
        else:
            partes = ", ".join(f"{l['nome']} {l['faltam']}" for l in pendentes)
            texto = f"Faltam {faltam} servidores ({partes})."
        tom = "pendente"
    elif com_meta:
        texto = "Equipe completa: os ofícios já somam os servidores designados."
        tom = "atendido"
    else:
        texto = (
            f"{total} {_plural(total, 'servidor', 'servidores')} em ofícios; "
            "a DG não fixou quantidade."
        )
        tom = "neutro"
    if faltam == 0 and com_meta and sem_quantidade:
        texto += f" Sem quantidade definida: {', '.join(sem_quantidade)}."

    return {
        "linhas": linhas,
        "previstos": previstos,
        "em_oficios": total,
        "faltam": faltam,
        "completo": bool(com_meta) and not faltam,
        "texto": texto,
        "tom": tom,
    }
