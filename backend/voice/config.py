"""Voice configuration is independent from AI-provider configuration."""

import os
from dataclasses import dataclass
from pathlib import Path

DEFAULT_MODELS = Path(__file__).resolve().parents[2] / "data" / "models" / "voice"


@dataclass(frozen=True)
class VoiceSettings:
    models_dir: Path = DEFAULT_MODELS
    wake_phrase: str = "Hey JARVIS"
    threshold: float = 0.5
    silence_frames: int = 12  # 960ms after speech
    max_frames: int = 150  # 12 seconds at 80ms/frame
    speech_rms: int = 350

    def __post_init__(self):
        if self.wake_phrase.casefold() != "hey jarvis":
            raise ValueError("The included pretrained model supports only 'Hey JARVIS'; another phrase requires its own model")
        if not 0.1 <= self.threshold <= 0.99:
            raise ValueError("JARVIS_WAKE_THRESHOLD must be between 0.1 and 0.99")

    @classmethod
    def from_env(cls):
        return cls(models_dir=Path(os.environ.get("JARVIS_VOICE_MODELS", str(DEFAULT_MODELS))).resolve(),
                   wake_phrase=os.environ.get("JARVIS_WAKE_PHRASE", "Hey JARVIS"),
                   threshold=float(os.environ.get("JARVIS_WAKE_THRESHOLD", "0.5")))
