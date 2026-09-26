"""Acesso documental pelo módulo VIAGENS, sem recorte por área."""

from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404

from accounts.modulos import usuario_tem_modulo
from documentos.models import DocumentoArtefato


def usuario_pode_baixar_documento(usuario) -> bool:
    return usuario_tem_modulo(usuario, "VIAGENS")


def obter_artefato_para_download(usuario, pk) -> DocumentoArtefato:
    if not usuario_pode_baixar_documento(usuario):
        raise PermissionDenied
    # As vias do Coffee Break são do módulo Coffee Break (coffee_break:via_arquivo).
    return get_object_or_404(DocumentoArtefato.objects.exclude(tipo__startswith="coffee_break_"), pk=pk)
