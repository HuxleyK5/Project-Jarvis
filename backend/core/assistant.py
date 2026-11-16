"""Application coordination independent of the HTTP transport."""

from backend.core.brain import Brain


class Assistant:
    def __init__(self, brain: Brain) -> None:
        self.brain = brain

    async def health(self) -> dict[str, str | bool]:
        status = await self.brain.provider.status()
        return {"status": "ok", "service": "JARVIS", "ai_connected": status.ready,
                "provider": self.brain.settings.model_provider, "model": self.brain.settings.model,
                "ai_status": status.code, "ai_message": status.message}
