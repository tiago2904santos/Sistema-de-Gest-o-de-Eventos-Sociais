from .types import DocumentoFormato
from .types import DocumentoTipo
from .types import DocumentoTipoDefinicao
from .exceptions import DocumentValidationError
from .exceptions import UnsupportedDocumentType


class DocumentoRegistry:
    def __init__(self):
        self._items: dict[DocumentoTipo, DocumentoTipoDefinicao] = {}

    def register(self, definicao: DocumentoTipoDefinicao) -> None:
        if definicao.tipo in self._items:
            raise DocumentValidationError(f"Tipo documental já registrado: {definicao.tipo.value}")
        self._items[definicao.tipo] = definicao

    def get(self, tipo: DocumentoTipo) -> DocumentoTipoDefinicao:
        if tipo not in self._items:
            raise UnsupportedDocumentType(f"Tipo documental não suportado: {tipo.value}")
        return self._items[tipo]

    def all(self) -> tuple[DocumentoTipoDefinicao, ...]:
        return tuple(self._items.values())

    def has(self, tipo: DocumentoTipo) -> bool:
        return tipo in self._items


def build_default_registry() -> DocumentoRegistry:
    registry = DocumentoRegistry()
    registry.register(
        DocumentoTipoDefinicao(
            tipo=DocumentoTipo.OFICIO,
            label="Ofício",
            descricao="Documento principal de autorização institucional.",
            formatos_permitidos=(DocumentoFormato.DOCX, DocumentoFormato.PDF),
        )
    )
    registry.register(
        DocumentoTipoDefinicao(
            tipo=DocumentoTipo.TERMO_AUTORIZACAO,
            label="Termo de autorização",
            descricao="Documento de autorização formal por servidor/participante.",
            formatos_permitidos=(DocumentoFormato.DOCX, DocumentoFormato.PDF),
        )
    )
    registry.register(
        DocumentoTipoDefinicao(
            tipo=DocumentoTipo.JUSTIFICATIVA,
            label="Justificativa",
            descricao="Documento textual de suporte para validações de prazo.",
            formatos_permitidos=(DocumentoFormato.DOCX, DocumentoFormato.PDF),
        )
    )
    registry.register(DocumentoTipoDefinicao(
        tipo=DocumentoTipo.RELATORIO_TECNICO, label="Relatório técnico",
        descricao="Relatório técnico individual da prestação.",
        formatos_permitidos=(DocumentoFormato.DOCX, DocumentoFormato.PDF),
    ))
    registry.register(DocumentoTipoDefinicao(
        tipo=DocumentoTipo.ORDEM_SERVICO, label="Ordem de serviço",
        descricao="Designação da equipe para a atividade.",
        formatos_permitidos=(DocumentoFormato.DOCX, DocumentoFormato.PDF),
    ))
    registry.register(DocumentoTipoDefinicao(
        tipo=DocumentoTipo.PLANO_TRABALHO, label="Plano de trabalho",
        descricao="Documento de planejamento operacional e financeiro.",
        formatos_permitidos=(DocumentoFormato.DOCX, DocumentoFormato.PDF),
    ))
    registry.register(DocumentoTipoDefinicao(
        tipo=DocumentoTipo.DIARIO_BORDO, label="Diário de bordo",
        descricao="Diário do motorista, gerado da planilha oficial.",
        formatos_permitidos=(DocumentoFormato.XLSX, DocumentoFormato.PDF),
    ))
    return registry


default_document_registry = build_default_registry()
