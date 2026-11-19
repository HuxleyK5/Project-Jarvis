"""Piper API/lifecycle tests without Piper, voice downloads, or audible playback."""

import asyncio
import io
import threading
import unittest
import wave
from types import SimpleNamespace
from unittest.mock import Mock, patch

from fastapi import HTTPException
from fastapi.testclient import TestClient

from backend.config import Settings
from backend.main import create_app
from backend.tests.test_api import UnavailableProvider
from backend.voice.tts import PiperSynthesizer, SpeechService, SpeechSettings


def wav_fixture():
    output = io.BytesIO()
    with wave.open(output, 'wb') as audio:
        audio.setnchannels(1); audio.setsampwidth(2); audio.setframerate(22050)
        audio.writeframes(bytes(2205 * 2))
    return output.getvalue()


class SpeechOutputTests(unittest.TestCase):
    def test_missing_piper_is_a_clear_error_and_chat_remains_healthy(self):
        with TestClient(create_app(Settings(), UnavailableProvider())) as client:
            with patch('backend.voice.tts.importlib.util.find_spec', return_value=None):
                self.assertFalse(client.get('/speech/status').json()['available'])
                response = client.post('/speech/synthesize', json={'text': 'Hello'})
                self.assertEqual(response.status_code, 503)
                self.assertIn('missing', response.json()['error']['message'])
            self.assertEqual(client.get('/health').status_code, 200)

    def test_audio_response_has_no_store_and_uses_injected_local_engine(self):
        app = create_app(Settings(), UnavailableProvider())
        with TestClient(app) as client:
            app.state.speech.engine = SimpleNamespace(synthesize=Mock(return_value=wav_fixture()))
            with patch.object(app.state.speech, 'status', return_value={'available': True}):
                response = client.post('/speech/synthesize', json={'text': 'Test response'})
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.headers['content-type'], 'audio/wav')
                self.assertEqual(response.headers['cache-control'], 'no-store')
                self.assertTrue(response.content.startswith(b'RIFF'))
                app.state.speech.engine.synthesize.assert_called_once_with('Test response')

    def test_blank_oversized_and_model_path_fields_are_rejected(self):
        with TestClient(create_app(Settings(), UnavailableProvider())) as client:
            for body in [{'text': ' '}, {'text': 'x' * 1001}, {'text': 'Hi', 'model': 'remote'}]:
                self.assertEqual(client.post('/speech/synthesize', json=body).status_code, 422)

    def test_native_error_does_not_expose_internal_details(self):
        app = create_app(Settings(), UnavailableProvider())
        with TestClient(app) as client:
            app.state.speech.engine = SimpleNamespace(synthesize=Mock(side_effect=RuntimeError('private-path')))
            with patch.object(app.state.speech, 'status', return_value={'available': True}):
                response = client.post('/speech/synthesize', json={'text': 'Hello'})
                self.assertEqual(response.status_code, 502)
                self.assertNotIn('private-path', response.text)

    def test_piper_loads_only_explicit_local_files_on_cpu(self):
        def synthesize(text, target, syn_config):
            target.setnchannels(1); target.setsampwidth(2); target.setframerate(22050)
            target.writeframes(bytes(2205 * 2))
        voice = SimpleNamespace(synthesize_wav=Mock(side_effect=synthesize))
        loader, config = Mock(return_value=voice), Mock()
        with patch.dict('sys.modules', {'piper': SimpleNamespace(PiperVoice=SimpleNamespace(load=loader), SynthesisConfig=config)}):
            engine = PiperSynthesizer(SpeechSettings())
            self.assertTrue(engine.synthesize('One').startswith(b'RIFF'))
            engine.synthesize('Two')
        self.assertEqual(loader.call_count, 1)
        self.assertFalse(loader.call_args.kwargs['use_cuda'])
        self.assertTrue(loader.call_args.kwargs['config_path'].endswith('.onnx.json'))

    def test_invalid_configuration_fails_early(self):
        for options in [{'length_scale': 0}, {'noise_scale': float('nan')}, {'speaker': -1}]:
            with self.subTest(options=options), self.assertRaises(ValueError):
                SpeechSettings(**options)


class SpeechConcurrencyTests(unittest.IsolatedAsyncioTestCase):
    async def test_cancelled_request_does_not_allow_overlapping_native_jobs(self):
        started, release = threading.Event(), threading.Event()
        def synthesize(text):
            started.set(); release.wait(3)
            return wav_fixture()
        service = SpeechService(SpeechSettings(), SimpleNamespace(synthesize=synthesize))
        try:
            with patch.object(service, 'status', return_value={'available': True}):
                pending = asyncio.create_task(service.synthesize('First'))
                self.assertTrue(await asyncio.to_thread(started.wait, 2))
                pending.cancel()
                with self.assertRaises(asyncio.CancelledError):
                    await pending
                with self.assertRaises(HTTPException) as error:
                    await service.synthesize('Second')
                self.assertEqual(error.exception.status_code, 429)
                release.set()
                await asyncio.wrap_future(service.job)
                self.assertTrue((await service.synthesize('Third')).startswith(b'RIFF'))
        finally:
            release.set(); service.close()
