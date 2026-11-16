"""Validated backend configuration from process environment variables."""

import os
from dataclasses import dataclass
from urllib.parse import urlsplit


@dataclass(frozen=True)
class Settings:
    host: str = "127.0.0.1"
    port: int = 8000
    log_level: str = "info"
    model_provider: str = "ollama"
    ollama_url: str = "http://127.0.0.1:11434"
    model: str = "qwen3:4b"
    context_window: int = 4096
    max_output_tokens: int = 512
    generation_timeout: int = 120

    def __post_init__(self) -> None:
        if self.host not in {"127.0.0.1", "::1", "localhost"}:
            raise ValueError("JARVIS_HOST must be a loopback address or localhost")
        if isinstance(self.port, bool) or not isinstance(self.port, int) or not 1 <= self.port <= 65535:
            raise ValueError("JARVIS_PORT must be an integer between 1 and 65535")
        if self.log_level not in {"critical", "error", "warning", "info", "debug"}:
            raise ValueError("JARVIS_LOG_LEVEL must be critical, error, warning, info, or debug")
        if self.model_provider != "ollama":
            raise ValueError("JARVIS_MODEL_PROVIDER currently supports only ollama")
        url = urlsplit(self.ollama_url)
        if (url.scheme != "http" or url.hostname not in {"127.0.0.1", "::1", "localhost"}
                or url.username or url.password or url.path not in {"", "/"} or url.query or url.fragment):
            raise ValueError("JARVIS_OLLAMA_URL must be a local HTTP origin without credentials")
        try:
            url.port
        except ValueError as exc:
            raise ValueError("Invalid Ollama port") from exc
        if not self.model.strip() or len(self.model) > 128 or any(char.isspace() for char in self.model):
            raise ValueError("JARVIS_MODEL must be a nonempty local model name without spaces")
        if self.model.endswith((":cloud", "-cloud")):
            raise ValueError("Select an installed local model, not an Ollama cloud model")
        for name, value, lower, upper in [
            ("JARVIS_CONTEXT_WINDOW", self.context_window, 2048, 8192),
            ("JARVIS_MAX_OUTPUT_TOKENS", self.max_output_tokens, 64, 2048),
            ("JARVIS_GENERATION_TIMEOUT", self.generation_timeout, 10, 600),
        ]:
            if isinstance(value, bool) or not isinstance(value, int) or not lower <= value <= upper:
                raise ValueError(f"{name} must be between {lower} and {upper}")
        if self.max_output_tokens >= self.context_window:
            raise ValueError("Output token limit must be smaller than the context window")

    @classmethod
    def from_env(cls) -> "Settings":
        try:
            port = int(os.environ.get("JARVIS_PORT", "8000"))
        except ValueError as exc:
            raise ValueError("JARVIS_PORT must be an integer between 1 and 65535") from exc
        return cls(
            host=os.environ.get("JARVIS_HOST", "127.0.0.1"),
            port=port,
            log_level=os.environ.get("JARVIS_LOG_LEVEL", "info"),
            model_provider=os.environ.get("JARVIS_MODEL_PROVIDER", "ollama"),
            ollama_url=os.environ.get("JARVIS_OLLAMA_URL", "http://127.0.0.1:11434"),
            model=os.environ.get("JARVIS_MODEL", "qwen3:4b"),
            context_window=int(os.environ.get("JARVIS_CONTEXT_WINDOW", "4096")),
            max_output_tokens=int(os.environ.get("JARVIS_MAX_OUTPUT_TOKENS", "512")),
            generation_timeout=int(os.environ.get("JARVIS_GENERATION_TIMEOUT", "120")),
        )
