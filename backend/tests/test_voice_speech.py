"""Speech pipeline tests independent of the wake detector, audio devices, and downloads."""

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from backend.voice.config import VoiceSettings
from backend.voice.engines import FasterWhisperRecognizer, availability
from backend.voice.session import VoiceSession
from backend.tests.test_voice_wake import Recognizer, SILENCE, SPEECH


class SpeechTests(unittest.TestCase):
    def test_manual_mode_bypasses_wake_detector(self):
        recognizer = Recognizer()
        session = VoiceSession("manual", VoiceSettings(), recognizer)
        for _ in range(3):
            session.process(SPEECH)
        self.assertEqual(session.finish(), [{"type": "transcript", "text": "Test-only transcript"}])
        self.assertEqual(recognizer.calls, [SPEECH * 3])
        self.assertEqual(session.frames, [])

    def test_silence_and_single_click_never_invoke_whisper(self):
        for click in [False, True]:
            recognizer = Recognizer()
            session = VoiceSession("manual", VoiceSettings(), recognizer)
            if click:
                session.process(SPEECH)
            for _ in range(63):
                session.process(SILENCE)
            self.assertEqual(session.finish()[0]["type"], "no_speech")
            self.assertEqual(recognizer.calls, [])

    def test_capture_limit_is_twelve_seconds(self):
        recognizer = Recognizer()
        session = VoiceSession("manual", VoiceSettings(), recognizer)
        for _ in range(149):
            self.assertEqual(session.process(SPEECH), [])
        self.assertEqual(session.process(SPEECH), [{"type": "ready_to_transcribe"}])
        session.finish()
        self.assertEqual(len(recognizer.calls[0]), 16000 * 2 * 12)

    def test_transcription_failure_clears_raw_audio(self):
        recognizer = Recognizer()
        recognizer.transcribe = Mock(side_effect=RuntimeError("test-only failure"))
        session = VoiceSession("manual", VoiceSettings(), recognizer)
        for _ in range(3):
            session.process(SPEECH)
        with self.assertRaises(RuntimeError):
            session.finish()
        self.assertEqual(session.frames, [])

    def test_whisper_loading_is_cpu_int8_and_local_only(self):
        constructor = Mock()
        with patch.dict('sys.modules', {'faster_whisper': SimpleNamespace(WhisperModel=constructor)}):
            FasterWhisperRecognizer(VoiceSettings())
        options = constructor.call_args.kwargs
        self.assertEqual(options['device'], 'cpu')
        self.assertEqual(options['compute_type'], 'int8')
        self.assertTrue(options['local_files_only'])
        self.assertTrue(constructor.call_args.args[0].endswith('whisper-tiny.en'))

    def test_missing_models_do_not_load_or_download(self):
        with tempfile.TemporaryDirectory() as directory:
            status = availability(VoiceSettings(models_dir=Path(directory)))
        self.assertFalse(status['manual_available'])
        self.assertFalse(status['wake_available'])
        self.assertIn('No downloads', status['message'])
