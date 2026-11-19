"""Optional Piper synthesis. All generated audio stays in memory; no downloads."""

import asyncio
import importlib.util
import io
import math
import os
import wave
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import Response
from pydantic import BaseModel, ConfigDict, Field, field_validator

from backend.voice.config import DEFAULT_MODELS


@dataclass(frozen=True)
class SpeechSettings:
    model: Path = DEFAULT_MODELS / "piper" / "en_US-lessac-medium.onnx"
    length_scale: float = 1.0
    noise_scale: float = 0.667
    noise_w_scale: float = 0.8
    speaker: int = 0

    def __post_init__(self):
        for name, value, low, high in [("length_scale", self.length_scale, 0.5, 2),
                                       ("noise_scale", self.noise_scale, 0, 2),
                                       ("noise_w_scale", self.noise_w_scale, 0, 2)]:
            if not math.isfinite(value) or not low <= value <= high:
                raise ValueError(f"Invalid Piper {name}: expected {low}–{high}")
        if self.speaker < 0:
            raise ValueError("Piper speaker must be nonnegative")

    @classmethod
    def from_env(cls):
        return cls(model=Path(os.environ.get("JARVIS_PIPER_MODEL", str(cls.model))).resolve(),
                   length_scale=float(os.environ.get("JARVIS_PIPER_LENGTH_SCALE", "1")),
                   noise_scale=float(os.environ.get("JARVIS_PIPER_NOISE_SCALE", "0.667")),
                   noise_w_scale=float(os.environ.get("JARVIS_PIPER_NOISE_W_SCALE", "0.8")),
                   speaker=int(os.environ.get("JARVIS_PIPER_SPEAKER", "0")))


class PiperSynthesizer:
    def __init__(self, settings: SpeechSettings):
        self.settings = settings
        self.voice = None

    def synthesize(self, text: str) -> bytes:
        from piper import PiperVoice, SynthesisConfig
        if self.voice is None:
            self.voice = PiperVoice.load(str(self.settings.model),
                                         config_path=str(self.settings.model) + ".json", use_cuda=False)
        output = io.BytesIO()
        with wave.open(output, "wb") as wav:
            self.voice.synthesize_wav(text, wav, syn_config=SynthesisConfig(
                speaker_id=self.settings.speaker, length_scale=self.settings.length_scale,
                noise_scale=self.settings.noise_scale, noise_w_scale=self.settings.noise_w_scale))
        data = output.getvalue()
        if not 44 < len(data) <= 20_000_000:
            raise ValueError("Invalid synthesized audio size")
        return data


class SpeechService:
    def __init__(self, settings: SpeechSettings, engine=None):
        self.settings = settings
        self.engine = engine if engine is not None else PiperSynthesizer(settings)
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="jarvis-piper")
        self.job = None

    def status(self):
        installed = importlib.util.find_spec("piper") is not None
        assets = self.settings.model.is_file() and Path(str(self.settings.model) + ".json").is_file()
        return {"available": installed and assets, "voice": self.settings.model.stem,
                "message": "Piper and local voice assets are present; synthesis compatibility is checked on use."
                if installed and assets else "Piper or its local voice model/configuration is missing. See docs/SPEECH_OUTPUT.md. No models are downloaded automatically."}

    async def synthesize(self, text: str):
        status = self.status()
        if not status["available"]:
            raise HTTPException(503, status["message"])
        # Track the native worker itself: cancelling HTTP cannot stop ONNX inference.
        # Reject another job until it actually finishes, rather than accumulating work.
        if self.job is not None and not self.job.done():
            raise HTTPException(429, "Piper is still generating another utterance. Please try again shortly.")
        self.job = self.executor.submit(self.engine.synthesize, text)
        try:
            return await asyncio.wait_for(asyncio.wrap_future(self.job), timeout=60)
        except TimeoutError as exc:
            raise HTTPException(504, "Local speech generation timed out. Try a shorter response.") from exc
        except Exception as exc:
            raise HTTPException(502, "Piper synthesis failed. Check the local voice, speaker setting, and native runtime compatibility.") from exc

    def close(self):
        self.executor.shutdown(wait=False, cancel_futures=True)


class SpeechRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text: str = Field(min_length=1, max_length=1000)

    @field_validator("text")
    @classmethod
    def nonblank(cls, value):
        if not value.strip():
            raise ValueError("Speech text must not be blank")
        return value


router = APIRouter(prefix="/speech", tags=["Speech output"])


@router.get("/status")
async def speech_status(request: Request):
    return request.app.state.speech.status()


@router.post("/synthesize", responses={200: {"content": {"audio/wav": {"schema": {"type": "string", "format": "binary"}}}}})
async def synthesize(body: SpeechRequest, request: Request):
    audio = await request.app.state.speech.synthesize(body.text)
    return Response(audio, media_type="audio/wav", headers={"Cache-Control": "no-store"})
