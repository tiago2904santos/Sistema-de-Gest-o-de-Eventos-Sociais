from dataclasses import dataclass
from enum import Enum


class DocumentoFormato(str, Enum):
    DOCX = "docx"
    PDF = "pdf"
    XLSX = "xlsx"


class DocumentoTipo(str, Enum):
    OFICIO = "oficio"
    TERMO_AUTORIZACAO = "termo_autorizacao"
    JUSTIFICATIVA = "justificativa"
    RELATORIO_TECNICO = "relatorio_tecnico"
    DIARIO_BORDO = "diario_bordo"
    ORDEM_SERVICO = "ordem_servico"
    PLANO_TRABALHO = "plano_trabalho"


@dataclass(frozen=True)
class DocumentoTipoDefinicao:
    tipo: DocumentoTipo
    label: str
    descricao: str
    formatos_permitidos: tuple[DocumentoFormato, ...]

    def supports_format(self, formato: DocumentoFormato) -> bool:
        return formato in self.formatos_permitidos
