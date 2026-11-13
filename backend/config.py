"""Validated backend configuration from process environment variables."""

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    host: str = "127.0.0.1"
    port: int = 8000
    log_level: str = "info"

    def __post_init__(self) -> None:
        if self.host not in {"127.0.0.1", "::1", "localhost"}:
            raise ValueError("JARVIS_HOST must be a loopback address or localhost")
        if isinstance(self.port, bool) or not isinstance(self.port, int) or not 1 <= self.port <= 65535:
            raise ValueError("JARVIS_PORT must be an integer between 1 and 65535")
        if self.log_level not in {"critical", "error", "warning", "info", "debug"}:
            raise ValueError("JARVIS_LOG_LEVEL must be critical, error, warning, info, or debug")

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
        )
