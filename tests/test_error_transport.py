import json
import os
import subprocess
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


class FakeProvider(BaseHTTPRequestHandler):
    status = 429
    body = b'{"error":{"type":"rate_limit_exceeded","code":"rate_limit_exceeded"}}'
    retry_after = "7"
    calls = 0

    def do_POST(self):
        type(self).calls += 1
        self.rfile.read(int(self.headers["Content-Length"]))
        self.send_response(type(self).status)
        if type(self).retry_after is not None:
            self.send_header("Retry-After", type(self).retry_after)
        self.end_headers()
        self.wfile.write(type(self).body)

    def log_message(self, *args):
        pass


class ErrorTransportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), FakeProvider)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join()

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.auth = self.root / "auth.json"
        self.auth.write_text(json.dumps({"tokens": {"access_token": "synthetic-token"}}))
        FakeProvider.status = 429
        FakeProvider.body = b'{"error":{"type":"rate_limit_exceeded","code":"rate_limit_exceeded"}}'
        FakeProvider.retry_after = "7"
        FakeProvider.calls = 0

    def invoke(self, *extra):
        return subprocess.run(
            [sys.executable, "-m", "gpt_image.cli", "generate", "--prompt", "test",
             "--base-url", f"http://127.0.0.1:{self.server.server_port}",
             "--out", str(self.root / "image.png"), *extra],
            capture_output=True, text=True, env={**os.environ, "GPT_IMAGE_AUTH_FILE": str(self.auth)},
            timeout=5,
        )

    def test_explicit_http_denial_and_success_are_single_attempts(self):
        result = self.invoke("--error-json")
        self.assertEqual(result.returncode, 1)
        self.assertEqual(json.loads(result.stderr), {
            "version": 1, "kind": "rate_limit_rejected", "status": 429, "retry_after": "7",
        })
        self.assertEqual(FakeProvider.calls, 1)
        FakeProvider.status = 200
        FakeProvider.body = b'data: {"type":"response.output_item.done","item":{"type":"image_generation_call","result":"YWJj"}}\n\n'
        result = self.invoke("--error-json")
        self.assertEqual(result.returncode, 0)
        self.assertEqual((self.root / "image.png").read_bytes(), b"abc")
        self.assertEqual(FakeProvider.calls, 2)

    def test_ambiguous_quota_auth_and_accepted_stream_errors_are_not_rejections(self):
        cases = [
            (429, b'{"error":{"type":"insufficient_quota","code":"insufficient_quota"}}', "7"),
            (429, b'{"error":{"type":"rate_limit_exceeded","code":"insufficient_quota"}}', "7"),
            (429, b'{"error":', "7"),
            (429, FakeProvider.body, "not-a-date"),
            (401, FakeProvider.body, "7"),
            (200, b'data: {"type":"error","error":{"code":"rate_limit_exceeded"}}\n\n', "7"),
        ]
        for status, body, header in cases:
            with self.subTest(status=status, body=body, header=header):
                FakeProvider.status, FakeProvider.body, FakeProvider.retry_after = status, body, header
                result = self.invoke("--error-json")
                self.assertEqual(result.returncode, 1)
                self.assertEqual(json.loads(result.stderr), {"version": 1, "kind": "failed"})
        self.assertEqual(FakeProvider.calls, len(cases))

    def test_default_error_remains_human_readable(self):
        result = self.invoke()
        self.assertEqual(result.returncode, 1)
        self.assertTrue(result.stderr.startswith("Error: Request failed (HTTP 429):"))
        self.assertEqual(FakeProvider.calls, 1)

    def test_bucketed_rate_limits_preserve_retry_interval(self):
        for kind in ("requests", "tokens"):
            with self.subTest(kind=kind):
                FakeProvider.body = json.dumps({
                    "error": {"type": kind, "code": "rate_limit_exceeded"},
                }).encode()
                result = self.invoke("--error-json")
                self.assertEqual(result.returncode, 1)
                self.assertEqual(json.loads(result.stderr), {
                    "version": 1, "kind": "rate_limit_rejected",
                    "status": 429, "retry_after": "7",
                })
        self.assertEqual(FakeProvider.calls, 2)

    def test_optional_and_http_date_retry_after_are_preserved(self):
        for header in (None, "Wed, 21 Oct 2037 07:28:00 GMT"):
            with self.subTest(header=header):
                FakeProvider.retry_after = header
                result = self.invoke("--error-json")
                self.assertEqual(result.returncode, 1)
                self.assertEqual(json.loads(result.stderr)["retry_after"], header)
        self.assertEqual(FakeProvider.calls, 2)


if __name__ == "__main__":
    unittest.main()
