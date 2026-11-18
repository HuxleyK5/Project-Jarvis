"""Lazy local-only model adapters. Loading cannot initiate model downloads."""

import importlib.util
from typing import Protocol

from backend.voice.config import VoiceSettings

FRAME_SAMPLES = 1280
SAMPLE_RATE = 16000


class VoiceError(Exception):
    pass


class WakeDetector(Protocol):
    def score(self, pcm: bytes) -> float: ...
    def reset(self) -> None: ...


class Recognizer(Protocol):
    def transcribe(self, pcm: bytes) -> str: ...


def availability(settings: VoiceSettings) -> dict:
    dependencies = all(importlib.util.find_spec(name) is not None
                       for name in ("faster_whisper", "numpy", "websockets"))
    wake_dependencies = all(importlib.util.find_spec(name) is not None for name in ("openwakeword", "onnxruntime"))
    wake = all((settings.models_dir / "wake" / name).is_file()
               for name in ("hey_jarvis_v0.1.onnx", "melspectrogram.onnx", "embedding_model.onnx"))
    stt = all((settings.models_dir / "whisper-tiny.en" / name).is_file()
              for name in ("model.bin", "config.json", "tokenizer.json", "vocabulary.json"))
    return {"manual_available": dependencies and stt, "wake_available": dependencies and wake_dependencies and wake and stt,
            "wake_phrase": settings.wake_phrase, "sample_rate": SAMPLE_RATE, "frame_samples": FRAME_SAMPLES,
            "message": "Local voice assets present; microphone access still requires session consent."
            if dependencies and wake_dependencies and wake and stt else "Voice dependencies or local models are missing. See docs/VOICE_SETUP.md. No downloads occur automatically."}


class OpenWakeWordDetector:
    def __init__(self, settings: VoiceSettings):
        from openwakeword.model import Model
        root = settings.models_dir / "wake"
        self.model = Model(wakeword_models=[str(root / "hey_jarvis_v0.1.onnx")], inference_framework="onnx",
                           melspec_model_path=str(root / "melspectrogram.onnx"),
                           embedding_model_path=str(root / "embedding_model.onnx"), ncpu=1)

    def score(self, pcm: bytes) -> float:
        import numpy as np
        prediction = self.model.predict(np.frombuffer(pcm, dtype="<i2").copy())
        return max((float(value) for value in prediction.values()), default=0.0)

    def reset(self):
        self.model.reset()


class FasterWhisperRecognizer:
    def __init__(self, settings: VoiceSettings):
        from faster_whisper import WhisperModel
        # A directory path plus local_files_only prevents implicit Hugging Face pulls.
        self.model = WhisperModel(str(settings.models_dir / "whisper-tiny.en"), device="cpu",
                                  compute_type="int8", cpu_threads=4, num_workers=1, local_files_only=True)

    def transcribe(self, pcm: bytes) -> str:
        import numpy as np
        audio = np.frombuffer(pcm, dtype="<i2").astype(np.float32) / 32768.0
        segments, _ = self.model.transcribe(audio, language="en", beam_size=3, vad_filter=False,
                                             condition_on_previous_text=False)
        text = " ".join(segment.text.strip() for segment in segments
                        if segment.no_speech_prob < 0.6 and segment.avg_logprob > -1).strip()
        return text[:4000]
