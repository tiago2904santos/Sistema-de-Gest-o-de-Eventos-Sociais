from dataclasses import dataclass

from .exceptions import DocumentValidationError
from .exceptions import DocumentTemplateNotFound
from .types import DocumentoFormato
from .types import DocumentoTipo


@dataclass(frozen=True)
class DocumentTemplateDefinition:
    tipo: DocumentoTipo
    formato: DocumentoFormato
    template_path: str
    required_placeholders: tuple[str, ...] = ()
    # Para PDF (WeasyPrint): caminhos relativos ao BASE_DIR ou paths absolutos para CSS.
    stylesheet_paths: tuple[str, ...] = ()


class DocumentTemplateRegistry:
    def __init__(self):
        self._items: dict[tuple[DocumentoTipo, DocumentoFormato], DocumentTemplateDefinition] = {}

    def register(self, definition: DocumentTemplateDefinition) -> None:
        key = (definition.tipo, definition.formato)
        if key in self._items:
            raise DocumentValidationError(
                "Template documental já registrado para "
                f"tipo={definition.tipo.value} e formato={definition.formato.value}",
            )
        self._items[key] = definition

    def get(self, tipo: DocumentoTipo, formato: DocumentoFormato) -> DocumentTemplateDefinition:
        key = (tipo, formato)
        if key not in self._items:
            raise DocumentTemplateNotFound(
                f"Template não encontrado para tipo={tipo.value} e formato={formato.value}",
            )
        return self._items[key]

    def has(self, tipo: DocumentoTipo, formato: DocumentoFormato) -> bool:
        return (tipo, formato) in self._items

    def all(self) -> tuple[DocumentTemplateDefinition, ...]:
        return tuple(self._items.values())


def build_default_template_registry() -> DocumentTemplateRegistry:
    registry = DocumentTemplateRegistry()
    for tipo in DocumentoTipo:
        if tipo == DocumentoTipo.DIARIO_BORDO:
            for formato in (DocumentoFormato.XLSX, DocumentoFormato.PDF):
                registry.register(DocumentTemplateDefinition(tipo=tipo, formato=formato, template_path="diario_bordo.xlsx"))
            continue
        registry.register(
            DocumentTemplateDefinition(
                tipo=tipo,
                formato=DocumentoFormato.DOCX,
                template_path="relatorio-tecnico.docx" if tipo == DocumentoTipo.RELATORIO_TECNICO else f"{tipo.value}.docx",
                required_placeholders=(),
                stylesheet_paths=(),
            ),
        )
        registry.register(
            DocumentTemplateDefinition(
                tipo=tipo,
                formato=DocumentoFormato.PDF,
                template_path=f"documentos/pdf/{tipo.value}.html",
                required_placeholders=(),
                stylesheet_paths=(
                    f"templates/documentos/pdf/{tipo.value}.css",
                    "templates/documentos/pdf/_base.css",
                ),
            ),
        )
    return registry


def canonical_required_keys(tipo: DocumentoTipo) -> tuple[str, ...]:
    """Chaves obrigatórias no payload canônico usadas pela façade de geração."""
    return _required_for_tipo(tipo)


def _required_for_tipo(tipo: DocumentoTipo) -> tuple[str, ...]:
    """Chaves mínimas esperadas no payload canônico (validação leve na façade)."""
    if tipo == DocumentoTipo.RELATORIO_TECNICO:
        return ("oficio", "nome_servidor")
    if tipo == DocumentoTipo.DIARIO_BORDO:
        return ("header", "trechos")
    base = ("institucional", "oficio")
    if tipo in (DocumentoTipo.ORDEM_SERVICO, DocumentoTipo.PLANO_TRABALHO):
        # Entidades próprias: não derivam de ofício.
        return ("institucional",)
    if tipo == DocumentoTipo.JUSTIFICATIVA:
        return ("institucional", "oficio", "justificativa")
    if tipo == DocumentoTipo.TERMO_AUTORIZACAO:
        return ("institucional", "oficio", "termo")
    return base


default_template_registry = build_default_template_registry()
