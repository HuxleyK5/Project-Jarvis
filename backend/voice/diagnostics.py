"""Opt-in model checks on an existing WAV fixture. Never captures or saves audio."""

import argparse
import sys
import wave

from backend.voice.config import VoiceSettings
from backend.voice.engines import FasterWhisperRecognizer, OpenWakeWordDetector


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=["wake", "speech"])
    parser.add_argument("wav", help="Existing authorized/synthetic mono PCM16 16kHz WAV, at most 12 seconds")
    args = parser.parse_args()
    try:
        with wave.open(args.wav, "rb") as audio:
            if (audio.getnchannels(), audio.getsampwidth(), audio.getframerate()) != (1, 2, 16000):
                raise ValueError("Fixture must be mono 16-bit PCM at 16000 Hz")
            if not 0 < audio.getnframes() <= 16000 * 12:
                raise ValueError("Fixture must be between 0 and 12 seconds")
            pcm = audio.readframes(audio.getnframes())
        settings = VoiceSettings.from_env()
        if args.mode == "wake":
            for filename in ("hey_jarvis_v0.1.onnx", "melspectrogram.onnx", "embedding_model.onnx"):
                if not (settings.models_dir / "wake" / filename).is_file():
                    raise ValueError(f"Missing local wake asset: {filename}. See docs/VOICE_SETUP.md")
            detector = OpenWakeWordDetector(settings)
            scores = [detector.score(pcm[index:index + 2560].ljust(2560, b"\0")) for index in range(0, len(pcm), 2560)]
            peak = max(scores, default=0)
            print(f"Peak wake score: {peak:.3f}; threshold: {settings.threshold}; detected: {peak >= settings.threshold}")
        else:
            if not (settings.models_dir / "whisper-tiny.en" / "model.bin").is_file():
                raise ValueError("Missing local Whisper model. See docs/VOICE_SETUP.md")
            print(FasterWhisperRecognizer(settings).transcribe(pcm) or "No clear speech recognized")
    except (ImportError, OSError, ValueError, RuntimeError, wave.Error) as exc:
        print(f"Voice diagnostic unavailable: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
