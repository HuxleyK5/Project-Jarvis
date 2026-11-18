"""Bounded in-memory utterance state machine; no devices, files, or network access."""

import math
import struct

from backend.voice.config import VoiceSettings
from backend.voice.engines import FRAME_SAMPLES, Recognizer, VoiceError, WakeDetector


class VoiceSession:
    def __init__(self, mode: str, settings: VoiceSettings, recognizer: Recognizer, detector: WakeDetector | None = None):
        if mode not in {"manual", "wake"} or (mode == "wake" and detector is None):
            raise VoiceError("Unsupported voice mode or missing wake detector")
        self.mode = mode
        self.settings = settings
        self.recognizer = recognizer
        self.detector = detector
        self.capturing = mode == "manual"
        self.frames: list[bytes] = []
        self.quiet = 0
        self.spoken = False
        self.finished = False
        self.speech_frames = 0

    def process(self, pcm: bytes) -> list[dict]:
        if len(pcm) != FRAME_SAMPLES * 2:
            raise VoiceError("Audio must contain exactly 1280 signed 16-bit mono samples at 16kHz")
        if self.finished:
            return []
        if not self.capturing:
            if self.detector.score(pcm) >= self.settings.threshold:
                self.capturing = True
                return [{"type": "state", "state": "recording", "message": "Wake phrase detected. Speak your command now."}]
            return []
        self.frames.append(pcm)
        samples = struct.unpack("<1280h", pcm)
        rms = math.sqrt(sum(value * value for value in samples) / FRAME_SAMPLES)
        if rms >= self.settings.speech_rms:
            self.speech_frames += 1
            self.spoken = self.speech_frames >= 3  # Ignore isolated clicks/spikes.
            self.quiet = 0
        else:
            self.quiet += 1
        if (self.spoken and self.quiet >= self.settings.silence_frames) or len(self.frames) >= self.settings.max_frames:
            return [{"type": "ready_to_transcribe"}]
        if not self.spoken and len(self.frames) >= 63:  # five seconds without speech
            return [{"type": "ready_to_transcribe"}]
        return []

    def finish(self) -> list[dict]:
        if not self.capturing or self.finished:
            return []
        try:
            text = self.recognizer.transcribe(b"".join(self.frames)) if self.spoken else ""
        finally:
            self.frames.clear()
        self.finished = True
        return [{"type": "transcript", "text": text}] if text else [{"type": "no_speech", "message": "No clear speech recognized. Try again closer to the microphone."}]

    def clear(self):
        self.frames.clear()
        self.finished = True
