"""Wake detection/state tests, independent of speech recognition or model weights."""

import struct
import unittest

from backend.voice.config import VoiceSettings
from backend.voice.engines import VoiceError
from backend.voice.session import VoiceSession

SILENCE = bytes(2560)
SPEECH = struct.pack("<1280h", *([1000] * 1280))  # Synthetic constant samples, not a recording.


class Detector:
    def __init__(self, score=0):
        self.value = score
        self.calls = 0

    def score(self, pcm):
        self.calls += 1
        return self.value

    def reset(self):
        pass


class Recognizer:
    def __init__(self):
        self.calls = []

    def transcribe(self, pcm):
        self.calls.append(pcm)
        return "Test-only transcript"


class WakeTests(unittest.TestCase):
    def test_background_never_reaches_transcription(self):
        detector, recognizer = Detector(0.49), Recognizer()
        session = VoiceSession("wake", VoiceSettings(), recognizer, detector)
        for _ in range(200):
            self.assertEqual(session.process(SPEECH), [])
        self.assertEqual(session.frames, [])
        self.assertEqual(recognizer.calls, [])

    def test_threshold_opens_capture_without_transcribing_wake_audio(self):
        detector, recognizer = Detector(0.5), Recognizer()
        session = VoiceSession("wake", VoiceSettings(), recognizer, detector)
        self.assertEqual(session.process(SPEECH)[0]["state"], "recording")
        self.assertEqual(session.frames, [])
        self.assertEqual(recognizer.calls, [])
        for _ in range(3):
            session.process(SPEECH)
        for _ in range(11):
            self.assertEqual(session.process(SILENCE), [])
        self.assertEqual(session.process(SILENCE), [{"type": "ready_to_transcribe"}])
        self.assertEqual(session.finish()[0]["type"], "transcript")
        self.assertEqual(detector.calls, 1)

    def test_stop_discards_an_utterance_without_transcription(self):
        recognizer = Recognizer()
        session = VoiceSession("manual", VoiceSettings(), recognizer)
        session.process(SPEECH)
        session.clear()
        self.assertEqual(session.frames, [])
        self.assertEqual(session.finish(), [])
        self.assertEqual(recognizer.calls, [])

    def test_audio_size_and_phrase_validation(self):
        session = VoiceSession("manual", VoiceSettings(), Recognizer())
        with self.assertRaises(VoiceError):
            session.process(b"bad")
        for options in [{"wake_phrase": "Computer"}, {"threshold": 0}, {"threshold": float('nan')}]:
            with self.subTest(options=options), self.assertRaises(ValueError):
                VoiceSettings(**options)
