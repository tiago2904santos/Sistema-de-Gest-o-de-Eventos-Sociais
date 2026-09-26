"""Projeção do roteiro da F2 para o contrato documental do GV."""


def trechos_do_roteiro(roteiro):
    """Os trechos na ordem do editor (`ordem`, `pk`), sem consultar quando a lista já os pré-carregou.

    m101: `roteiro.trechos.all()` lê o `prefetch_related` das listas; sem ele, é
    uma consulta só — antes eram duas por chamada (`saida_dt` e `chegada_dt`),
    e a mesma função era chamada três vezes por cartão.
    """
    if roteiro is None:
        return []
    return sorted(roteiro.trechos.all(), key=lambda t: (t.ordem, t.pk or 0))


def periodo_roteiro(roteiro):
    if roteiro is None:
        return None, None
    saida = roteiro.saida_dt
    retorno = roteiro.retorno_chegada_dt or roteiro.retorno_saida_dt
    # O editor F2 pode persistir os horários somente nos trechos.
    if saida is None or retorno is None:
        trechos = trechos_do_roteiro(roteiro)
        if saida is None:
            saida = next((t.saida_dt for t in trechos if t.saida_dt is not None), None)
        if retorno is None:
            retorno = next((t.chegada_dt for t in reversed(trechos) if t.chegada_dt is not None), None)
    return saida, retorno
