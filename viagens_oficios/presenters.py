"""Apresentação do resumo documental do GV nos componentes V3.2."""
from django.utils.formats import number_format
from core.utils.masks import format_protocolo
from .services import build_oficio_document_payload


def apresentar_oficio(oficio):
    resumo = build_oficio_document_payload(oficio)
    diarias = oficio.diarias_para_servidores()
    resumo['protocolo'] = format_protocolo(oficio.protocolo)
    resumo['diarias'] = diarias
    resumo['valor_diarias'] = number_format(diarias['valor_decimal'], 2, force_grouping=True) if diarias and diarias['valor_decimal'] is not None else '—'
    return resumo
