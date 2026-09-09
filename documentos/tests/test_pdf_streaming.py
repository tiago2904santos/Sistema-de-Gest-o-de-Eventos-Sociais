import io
import tempfile
from pathlib import Path

from django.test import RequestFactory
from django.test import SimpleTestCase

from documentos.services.pdf_streaming import PdfStreamBackend
from documentos.services.pdf_streaming import build_pdf_inline_from_file_object
from documentos.services.pdf_streaming import build_pdf_inline_response


class PdfStreamingTests(SimpleTestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)

    @property
    def tempdir(self) -> str:
        return self._tmp.name

    def test_full_file_missing_raises(self):
        with self.assertRaises(FileNotFoundError):
            build_pdf_inline_response(
                self.factory.get("/"),
                file_path="/nonexistent/nope.pdf",
                filename="x.pdf",
            )

    def test_inline_headers_and_range_206(self):
        content = b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n" + b"x" * 100
        path = Path(self.tempdir) / "sample.pdf"
        path.write_bytes(content)

        req = self.factory.get("/", HTTP_RANGE="bytes=0-9")
        resp = build_pdf_inline_response(req, file_path=path, filename="meu doc.pdf")
        self.assertEqual(resp.status_code, 206)
        self.assertEqual(resp["Content-Type"], "application/pdf")
        self.assertIn("inline", resp["Content-Disposition"])
        self.assertIn("UTF-8''", resp["Content-Disposition"])
        self.assertEqual(resp["Accept-Ranges"], "bytes")
        self.assertEqual(resp["X-Content-Type-Options"], "nosniff")
        self.assertEqual(resp["X-Frame-Options"], "SAMEORIGIN")
        self.assertEqual(resp["Content-Range"], f"bytes 0-9/{len(content)}")
        self.assertEqual(resp.content, content[:10])

    def test_range_200_without_range_header(self):
        content = b"hello-pdf-bytes"
        path = Path(self.tempdir) / "a.pdf"
        path.write_bytes(content)
        req = self.factory.get("/")
        resp = build_pdf_inline_response(req, file_path=path, filename="a.pdf")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp["Accept-Ranges"], "bytes")
        _ = b"".join(resp.streaming_content)

    def test_range_416(self):
        content = b"abc"
        path = Path(self.tempdir) / "b.pdf"
        path.write_bytes(content)
        req = self.factory.get("/", HTTP_RANGE="bytes=10-20")
        resp = build_pdf_inline_response(req, file_path=path, filename="b.pdf")
        self.assertEqual(resp.status_code, 416)
        self.assertEqual(resp["Content-Range"], "bytes */3")

    def test_suffix_range(self):
        content = b"0123456789"
        path = Path(self.tempdir) / "c.pdf"
        path.write_bytes(content)
        req = self.factory.get("/", HTTP_RANGE="bytes=-3")
        resp = build_pdf_inline_response(req, file_path=path, filename="c.pdf")
        self.assertEqual(resp.status_code, 206)
        self.assertEqual(resp.content, b"789")

    def test_s3_backend_raises(self):
        path = Path(self.tempdir) / "d.pdf"
        path.write_bytes(b"x")
        req = self.factory.get("/")
        with self.assertRaises(NotImplementedError):
            build_pdf_inline_response(
                req,
                file_path=path,
                filename="d.pdf",
                backend=PdfStreamBackend.S3,
            )

    def test_from_file_object_206(self):
        content = b"0123456789abcdef"
        buf = io.BytesIO(content)
        req = self.factory.get("/", HTTP_RANGE="bytes=0-3")
        resp = build_pdf_inline_from_file_object(
            req,
            file_obj=buf,
            file_size=len(content),
            filename="f.pdf",
        )
        self.assertEqual(resp.status_code, 206)
        self.assertEqual(resp.content, b"0123")
