"""A data própria dos documentos datados na emissão (OS, justificativa e
plano de trabalho).

O ofício nasce datado (`data_criacao`) e o relatório técnico tem regra própria;
os três acima saíam sempre com a data do dia da geração, e cada via de um
mesmo número podia sair com uma data diferente. Agora a data nasce na
primeira emissão, fica gravada em `data_documento` e só muda quando alguém a
ajusta na folha — todas as vias saem iguais, e a chave de cache do PDF para
de mudar todo dia.
"""

from django.utils import timezone


def data_do_documento(registro):
    """A data que o documento mostra: a gravada ou, antes da primeira
    emissão (a prévia), a de hoje."""
    return getattr(registro, "data_documento", None) or timezone.localdate()


def fixar_data_documento(registro):
    """Na primeira emissão, grava a data do dia como a data do documento;
    depois disso, não mexe."""
    if registro is None or getattr(registro, "data_documento", None):
        return registro
    registro.data_documento = timezone.localdate()
    campos = ["data_documento"]
    if hasattr(registro, "atualizado_em"):
        campos.append("atualizado_em")
    registro.save(update_fields=campos)
    return registro
