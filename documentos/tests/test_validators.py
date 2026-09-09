from django.test import SimpleTestCase

from documentos.services.types import DocumentoTipo
from documentos.services.validators import DocumentValidatorRegistry
from documentos.services.validators import ValidationResult
from documentos.services.validators import ensure_required_fields


class _OficioValidator:
    tipo = DocumentoTipo.OFICIO

    def validate(self, payload):
        if payload.get("numero"):
            return ValidationResult(ok=True)
        return ValidationResult(ok=False, errors=("Campo obrigatório ausente: numero",))


class ValidatorsTests(SimpleTestCase):
    def test_ensure_required_fields(self):
        result = ensure_required_fields({"numero": ""}, ("numero", "assunto"))
        self.assertFalse(result.ok)
        self.assertIn("Campo obrigatório ausente: numero", result.errors)
        self.assertIn("Campo obrigatório ausente: assunto", result.errors)

    def test_registry_uses_specific_validator_when_registered(self):
        registry = DocumentValidatorRegistry()
        registry.register(_OficioValidator())

        ok = registry.validate(DocumentoTipo.OFICIO, {"numero": "15"})
        fail = registry.validate(DocumentoTipo.OFICIO, {"numero": ""})

        self.assertTrue(ok.ok)
        self.assertFalse(fail.ok)
