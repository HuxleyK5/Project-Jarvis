"""Local Ollama adapter. Only lists installed models and generates chat; never pulls."""

import json
from collections.abc import AsyncIterator

import httpx

from backend.config import Settings
from backend.core.providers import ModelError, ModelStatus


class OllamaProvider:
    def __init__(self, settings: Settings, client: httpx.AsyncClient | None = None):
        self.settings = settings
        self.client = client or httpx.AsyncClient(
            base_url=settings.ollama_url.rstrip("/"),
            timeout=httpx.Timeout(30, connect=2),
            trust_env=False,
            follow_redirects=False,
        )

    async def close(self) -> None:
        await self.client.aclose()

    async def status(self) -> ModelStatus:
        try:
            response = await self.client.get("/api/tags", timeout=2)
            response.raise_for_status()
            data = response.json()
            if not isinstance(data, dict) or not isinstance(data.get("models"), list):
                raise ValueError("Invalid model list")
            names = {model.get("name") for model in data["models"] if isinstance(model, dict)
                     and isinstance(model.get("name"), str)}
            name = self.settings.model
            selected = next((item for item in data["models"] if isinstance(item, dict)
                             and item.get("name") in {name, f"{name}:latest"}), None)
            if selected and (selected.get("remote_host") or selected.get("remote_model")):
                return ModelStatus(False, "remote_model", "The selected Ollama entry points to a remote model. Select a downloaded local model instead.")
            if name not in names and (":" in name or f"{name}:latest" not in names):
                return ModelStatus(False, "model_missing", f"Model {name} is not installed. See docs/OLLAMA_SETUP.md; JARVIS never downloads models.")
            return ModelStatus(True, "ready", f"Ollama is reachable and {name} is installed. Inference runs when you send a message.")
        except httpx.TimeoutException:
            return ModelStatus(False, "ollama_timeout", "Ollama did not respond in time. Check the local service.")
        except httpx.RequestError:
            return ModelStatus(False, "ollama_unavailable", "Ollama is unavailable. Start the local service; see docs/OLLAMA_SETUP.md.")
        except (httpx.HTTPStatusError, ValueError, TypeError):
            return ModelStatus(False, "ollama_error", "Ollama returned an invalid model list. Check its version and local service.")

    async def stream(self, messages: list[dict[str, str]]) -> AsyncIterator[str]:
        payload = {
            "model": self.settings.model, "messages": messages, "stream": True,
            "think": False, "keep_alive": "5m",
            "options": {"num_ctx": self.settings.context_window,
                        "num_predict": self.settings.max_output_tokens, "temperature": 0.6},
        }
        try:
            async with self.client.stream("POST", "/api/chat", json=payload) as response:
                if response.status_code == 404:
                    raise ModelError("model_missing", "The configured model is missing. Select an installed model; JARVIS will not download it.")
                if response.status_code >= 300:
                    raise ModelError("ollama_error", "Ollama could not generate a response. Check model compatibility and available memory.", 502)
                content_received = False
                async for line in response.aiter_lines():
                    if not line.strip():
                        continue
                    try:
                        chunk = json.loads(line)
                        if not isinstance(chunk, dict):
                            raise ValueError("Invalid chunk")
                        if chunk.get("error"):
                            raise ModelError("ollama_error", "Ollama reported a generation error. Check the local Ollama logs.", 502)
                        message = chunk.get("message", {})
                        if not isinstance(message, dict):
                            raise ValueError("Invalid message")
                        content = message.get("content", "")
                        if not isinstance(content, str):
                            raise ValueError("Invalid content")
                    except (ValueError, TypeError) as exc:
                        raise ModelError("invalid_stream", "Ollama returned an invalid response stream.", 502) from exc
                    if content:
                        content_received = True
                        yield content
                    if chunk.get("done") is True:
                        if chunk.get("done_reason") == "length":
                            raise ModelError("output_limit", "The answer reached the output limit and is incomplete. Ask a narrower question or increase JARVIS_MAX_OUTPUT_TOKENS.", 502)
                        if not content_received:
                            raise ModelError("empty_response", "The model returned no answer. Try a shorter prompt or another installed model.", 502)
                        return
                raise ModelError("incomplete_stream", "The response was interrupted before completion. Please retry.", 502)
        except httpx.TimeoutException as exc:
            raise ModelError("ollama_timeout", "Ollama stopped responding. The model may need more time or memory.", 504) from exc
        except httpx.RequestError as exc:
            raise ModelError("ollama_unavailable", "Connection to Ollama was lost. Check that the local service is running.") from exc
