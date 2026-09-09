"""Projeção do roteiro da F2 para o contrato documental do GV."""


def periodo_roteiro(roteiro):
    if roteiro is None:
        return None, None
    saida = roteiro.saida_dt
    retorno = roteiro.retorno_chegada_dt or roteiro.retorno_saida_dt
    # O editor F2 pode persistir os horários somente nos trechos.
    if saida is None:
        saida = roteiro.trechos.exclude(saida_dt=None).order_by('ordem', 'pk').values_list('saida_dt', flat=True).first()
    if retorno is None:
        retorno = roteiro.trechos.exclude(chegada_dt=None).order_by('-ordem', '-pk').values_list('chegada_dt', flat=True).first()
    return saida, retorno
