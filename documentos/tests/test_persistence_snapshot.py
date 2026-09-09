import datetime
import uuid
from decimal import Decimal

from django.test import SimpleTestCase

from documentos.services.persistence import _payload_snapshot_json_seguro
from documentos.services.persistence import _sanear_objeto_para_json


class PersistenceSnapshotSanitizeTests(SimpleTestCase):
    def test_model_like_nested_vira_string(self):
        class CidadeFake:
            def __str__(self) -> str:
                return "Cidade X"

        out = _payload_snapshot_json_seguro(
            {"institucional": {"cidade_sede_padrao": CidadeFake()}, "n": 1},
        )
        self.assertEqual(out["institucional"]["cidade_sede_padrao"], "Cidade X")
        self.assertEqual(out["n"], 1)

    def test_tipos_comuns(self):
        d = {
            "d": datetime.date(2026, 5, 11),
            "u": uuid.UUID("550e8400-e29b-41d4-a716-446655440000"),
            "dec": Decimal("1.5"),
        }
        s = _sanear_objeto_para_json(d)
        self.assertEqual(s["d"], "2026-05-11")
        self.assertEqual(s["u"], "550e8400-e29b-41d4-a716-446655440000")
        self.assertEqual(s["dec"], "1.5")
