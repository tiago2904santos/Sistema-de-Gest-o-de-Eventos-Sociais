from dataclasses import dataclass
from typing import Mapping
from typing import Protocol

from .exceptions import DocumentValidationError
from .types import DocumentoTipo


@dataclass(frozen=True)
class ValidationResult:
    ok: bool
    errors: tuple[str, ...] = ()


class DocumentValidator(Protocol):
    tipo: DocumentoTipo

    def validate(self, payload: Mapping[str, object]) -> ValidationResult:
        ...


def ensure_required_fields(payload: Mapping[str, object], required_fields: tuple[str, ...]) -> ValidationResult:
    errors: list[str] = []
    for field in required_fields:
        value = payload.get(field)
        if value in (None, "", []):
            errors.append(f"Campo obrigatório ausente: {field}")
    return ValidationResult(ok=not errors, errors=tuple(errors))


class NoopDocumentValidator:
    def __init__(self, tipo: DocumentoTipo):
        self.tipo = tipo

    def validate(self, payload: Mapping[str, object]) -> ValidationResult:
        _ = payload
        return ValidationResult(ok=True, errors=())


class DocumentValidatorRegistry:
    def __init__(self):
        self._validators: dict[DocumentoTipo, DocumentValidator] = {}

    def register(self, validator: DocumentValidator) -> None:
        if validator.tipo in self._validators:
            raise DocumentValidationError(
                f"Validador já registrado para o tipo: {validator.tipo.value}",
            )
        self._validators[validator.tipo] = validator

    def validate(self, tipo: DocumentoTipo, payload: Mapping[str, object]) -> ValidationResult:
        validator = self._validators.get(tipo)
        if validator is None:
            validator = NoopDocumentValidator(tipo=tipo)
        return validator.validate(payload)
