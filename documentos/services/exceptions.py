class DocumentError(Exception):
    """Erro base para o núcleo documental."""


class UnsupportedDocumentType(DocumentError):
    """Tipo documental não suportado pelo registry."""


class UnsupportedDocumentFormat(DocumentError):
    """Formato não suportado para o tipo solicitado."""


class DocumentValidationError(DocumentError):
    """Payload documental inválido."""


class DocumentTemplateNotFound(DocumentError):
    """Template documental não encontrado para tipo/formato."""


class DocumentRendererUnavailable(DocumentError):
    """Renderer não disponível para o formato solicitado."""


class UnresolvedPlaceholderError(DocumentError):
    """Placeholders não resolvidos após renderização/substituição."""


class ArquivoAssinadoInvalido(DocumentError):
    """Upload de documento assinado rejeitado (formato ou tamanho inválido)."""
