"""Local API and configuration regression tests; no network services required."""

import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from backend.config import Settings
from backend.core.assistant import Assistant
from backend.core.providers import ModelStatus
from backend.main import create_app


class SettingsTests(unittest.TestCase):
    def test_defaults(self):
        with patch.dict("os.environ", {}, clear=True):
            self.assertEqual(Settings.from_env(), Settings())

    def test_environment_overrides(self):
        with patch.dict("os.environ", {"JARVIS_HOST": "::1", "JARVIS_PORT": "8123",
                                       "JARVIS_LOG_LEVEL": "warning"}, clear=True):
            self.assertEqual(Settings.from_env(), Settings("::1", 8123, "warning"))

    def test_model_environment_overrides(self):
        with patch.dict("os.environ", {"JARVIS_MODEL": "qwen3:1.7b", "JARVIS_CONTEXT_WINDOW": "2048",
                                       "JARVIS_MAX_OUTPUT_TOKENS": "256"}, clear=True):
            settings = Settings.from_env()
            self.assertEqual(settings.model, "qwen3:1.7b")
            self.assertEqual(settings.context_window, 2048)
            self.assertEqual(settings.max_output_tokens, 256)

    def test_rejects_nonlocal_hosts(self):
        for host in ["0.0.0.0", "192.168.1.5", "example.com", "::"]:
            with self.subTest(host=host), self.assertRaises(ValueError):
                Settings(host=host)

    def test_rejects_invalid_configuration(self):
        for name, value in [("JARVIS_PORT", "abc"), ("JARVIS_PORT", "0"),
                            ("JARVIS_PORT", "65536"), ("JARVIS_LOG_LEVEL", "trace")]:
            with self.subTest(name=name, value=value):
                with patch.dict("os.environ", {name: value}, clear=True):
                    with self.assertRaises(ValueError):
                        Settings.from_env()


class UnavailableProvider:
    async def status(self):
        return ModelStatus(False, "ollama_unavailable", "Ollama is unavailable.")

    async def close(self):
        pass


class APITests(unittest.TestCase):
    def setUp(self):
        self.app = create_app(Settings(), UnavailableProvider())
        self.client = self.enterContext(TestClient(self.app, raise_server_exceptions=False))

    def test_health(self):
        response = self.client.get("/health")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "ok")
        self.assertFalse(response.json()["ai_connected"])
        self.assertEqual(response.json()["model"], "qwen3:4b")
        self.assertEqual(response.json()["ai_status"], "ollama_unavailable")

    def test_http_errors(self):
        for method, path, status in [("GET", "/missing", 404), ("POST", "/health", 405)]:
            with self.subTest(status=status):
                response = self.client.request(method, path)
                self.assertEqual(response.status_code, status)
                self.assertEqual(response.json()["error"]["code"], f"http_{status}")
                if status == 405:
                    self.assertIn("GET", response.headers["allow"])

    def test_validation_errors(self):
        @self.app.get("/test-validation")
        async def validation_route(count: int):
            return {"count": count}

        response = self.client.get("/test-validation?count=invalid")
        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()["error"]["code"], "validation_error")

    def test_unexpected_errors_do_not_expose_details(self):
        with patch.object(Assistant, "health", side_effect=RuntimeError("private-detail")):
            with self.assertLogs("backend.main", level="ERROR"):
                response = self.client.get("/health")
        self.assertEqual(response.status_code, 500)
        self.assertEqual(response.json(), {"error": {"code": "internal_error", "message": "Internal server error"}})
        self.assertNotIn("private-detail", response.text)

    def test_documentation_and_schema(self):
        response = self.client.get("/docs")
        self.assertEqual(response.status_code, 200)
        self.assertIn("/openapi.json", response.text)
        self.assertNotIn("https://", response.text)
        schema = self.client.get("/openapi.json")
        self.assertEqual(schema.status_code, 200)
        self.assertIn("/health", schema.json()["paths"])


if __name__ == "__main__":
    unittest.main()
