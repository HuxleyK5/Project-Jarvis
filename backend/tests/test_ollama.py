"""Ollama adapter tests use HTTPX's in-process transport; no models are downloaded."""

import json
import unittest

import httpx

from backend.config import Settings
from backend.core.providers import ModelError
from backend.integrations.ollama import OllamaProvider


class OllamaTests(unittest.IsolatedAsyncioTestCase):
    def provider(self, handler, **settings):
        client = httpx.AsyncClient(base_url="http://127.0.0.1:11434", transport=httpx.MockTransport(handler))
        self.addAsyncCleanup(client.aclose)
        return OllamaProvider(Settings(**settings), client)

    async def test_status_ready_missing_and_invalid(self):
        for body, code in [({"models": [{"name": "qwen3:4b"}]}, "ready"),
                           ({"models": [{"name": "qwen3:4b", "remote_host": "https://example.com"}]}, "remote_model"),
                           ({"models": []}, "model_missing"), ({"bad": []}, "ollama_error")]:
            with self.subTest(code=code):
                provider = self.provider(lambda request: httpx.Response(200, json=body))
                status = await provider.status()
                self.assertEqual(status.code, code)
                self.assertEqual(status.ready, code == "ready")

    async def test_connection_and_timeout(self):
        for exception, code in [(httpx.ConnectError, "ollama_unavailable"), (httpx.ReadTimeout, "ollama_timeout")]:
            def fail(request):
                raise exception("private transport details", request=request)
            provider = self.provider(fail)
            self.assertEqual((await provider.status()).code, code)
            with self.assertRaises(ModelError) as caught:
                _ = [part async for part in provider.stream([])]
            self.assertEqual(caught.exception.code, code)
            self.assertNotIn("private", str(caught.exception))

    async def test_stream_contract_and_options(self):
        captured = []
        def handler(request):
            captured.append(request)
            return httpx.Response(200, content='{"message":{"content":"Hello "},"done":false}\n{"message":{"content":"世界"},"done":true}\n'.encode())
        provider = self.provider(handler)
        self.assertEqual([part async for part in provider.stream([{"role": "user", "content": "Hi"}])], ["Hello ", "世界"])
        payload = json.loads(captured[0].content)
        self.assertEqual(captured[0].url.path, "/api/chat")
        self.assertEqual(payload["model"], "qwen3:4b")
        self.assertTrue(payload["stream"])
        self.assertFalse(payload["think"])
        self.assertEqual(payload["options"]["num_ctx"], 4096)
        self.assertNotIn("tools", payload)

    async def test_failures_never_look_like_a_completed_response(self):
        examples = [(404, '', "model_missing"), (500, 'private details', "ollama_error"),
                    (200, 'not json\n', "invalid_stream"),
                    (200, '{"error":"out of memory"}\n', "ollama_error"),
                    (200, '{"message":{"content":"partial"}}\n', "incomplete_stream"),
                    (200, '{"done":true}\n', "empty_response"),
                    (200, '{"message":{"content":"partial"},"done":true,"done_reason":"length"}\n', "output_limit")]
        for status, body, code in examples:
            with self.subTest(code=code):
                provider = self.provider(lambda request: httpx.Response(status, content=body.encode()))
                with self.assertRaises(ModelError) as caught:
                    _ = [part async for part in provider.stream([])]
                self.assertEqual(caught.exception.code, code)

    async def test_no_proxy_environment_or_redirects(self):
        provider = OllamaProvider(Settings())
        try:
            self.assertFalse(provider.client.trust_env)
            self.assertFalse(provider.client.follow_redirects)
        finally:
            await provider.close()
