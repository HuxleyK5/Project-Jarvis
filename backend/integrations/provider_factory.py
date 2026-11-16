"""Single composition point for supported model providers."""

from backend.config import Settings
from backend.core.providers import ModelProvider
from backend.integrations.ollama import OllamaProvider


def create_provider(settings: Settings) -> ModelProvider:
    if settings.model_provider == "ollama":
        return OllamaProvider(settings)
    raise ValueError(f"Unsupported model provider: {settings.model_provider}")
