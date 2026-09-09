import time
from unittest import mock

from django.test import SimpleTestCase

from documentos.services import timing as timing_mod
from documentos.services.timing import measure_step


class MeasureStepTests(SimpleTestCase):
    def test_duration_ms_positivo_com_sleep(self):
        with mock.patch.object(timing_mod.logger, "info") as m_info:
            with measure_step("test_sleep", {"x": 1}):
                time.sleep(0.02)
        m_info.assert_called_once()
        msg = m_info.call_args[0][0]
        self.assertIn("etapa=test_sleep", msg)
        self.assertIn("duration_ms=", msg)
        self.assertIn("x=1", msg)
        # extrai duration_ms do texto
        part = [p for p in msg.split() if p.startswith("duration_ms=")][0]
        ms = int(part.split("=", 1)[1])
        self.assertGreaterEqual(ms, 15)

    def test_logging_falha_nao_impede_contexto(self):
        def boom(*_a, **_k):
            raise RuntimeError("logger off")

        with mock.patch.object(timing_mod.logger, "info", side_effect=boom):
            with measure_step("test_ok", {"a": "b"}):
                x = 1 + 1
        self.assertEqual(x, 2)
