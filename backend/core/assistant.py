"""Application coordination independent of the HTTP transport."""

from backend.core.brain import Brain


class Assistant:
    def __init__(self, brain: Brain | None = None) -> None:
        self.brain = brain if brain is not None else Brain()

    def health(self) -> dict[str, str | bool]:
        return {"status": "ok", "service": "JARVIS", "ai_connected": self.brain.connected}
