"""Provider contract; transports stay outside application coordination."""

from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Protocol


class ModelError(Exception):
    def __init__(self, code: str, message: str, status_code: int = 503):
        super().__init__(message)
        self.code = code
        self.status_code = status_code


@dataclass(frozen=True)
class ModelStatus:
    ready: bool
    code: str
    message: str


class ModelProvider(Protocol):
    async def status(self) -> ModelStatus: ...
    def stream(self, messages: list[dict[str, str]]) -> AsyncIterator[str]: ...
    async def close(self) -> None: ...
