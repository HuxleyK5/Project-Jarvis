"""ASGI voice tests require neither installed voice extras nor real microphone consent."""

import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from backend.config import Settings
from backend.main import create_app
from backend.tests.test_api import UnavailableProvider
from backend.tests.test_voice_wake import Detector, Recognizer, SPEECH
from backend.voice.session import VoiceSession

ORIGIN = {"origin": "http://127.0.0.1:5173"}


class VoiceAPITests(unittest.TestCase):
    def setUp(self):
        self.app = create_app(Settings(), UnavailableProvider())
        self.client = self.enterContext(TestClient(self.app))

    def test_status_without_models_is_not_a_server_failure(self):
        response = self.client.get('/voice/status')
        self.assertEqual(response.status_code, 200)
        self.assertIn('wake_available', response.json())
        self.assertEqual(response.json()['wake_phrase'], 'Hey JARVIS')

    def test_no_consent_means_no_model_work(self):
        with patch.object(self.app.state.voice, 'create_session') as create:
            with self.client.websocket_connect('/voice/listen', headers=ORIGIN) as socket:
                socket.send_json({'consent': False, 'mode': 'manual'})
                self.assertEqual(socket.receive_json()['type'], 'error')
            create.assert_not_called()

    def test_remote_or_missing_origins_are_rejected(self):
        for headers in [{}, {'origin': 'https://example.com'}, {'origin': 'http://localhost:bad'}]:
            with self.subTest(headers=headers), self.assertRaises(WebSocketDisconnect):
                with self.client.websocket_connect('/voice/listen', headers=headers):
                    pass

    def test_manual_audio_transcription_and_cleanup(self):
        service = self.app.state.voice
        recognizer = Recognizer()
        session = VoiceSession('manual', service.settings, recognizer)
        with patch('backend.voice.api.availability', return_value={'manual_available': True, 'wake_available': True}), patch.object(service, 'create_session', return_value=session):
            with self.client.websocket_connect('/voice/listen', headers=ORIGIN) as socket:
                socket.send_json({'consent': True, 'mode': 'manual'})
                self.assertEqual(socket.receive_json()['state'], 'recording')
                for _ in range(3):
                    socket.send_bytes(SPEECH)
                socket.send_json({'type': 'finish'})
                self.assertEqual(socket.receive_json()['state'], 'transcribing')
                self.assertEqual(socket.receive_json()['text'], 'Test-only transcript')
        self.assertEqual(session.frames, [])
        self.assertFalse(service.lock.locked())

    def test_wake_resume_and_stop_are_explicit(self):
        service = self.app.state.voice
        recognizer, detector = Recognizer(), Detector(1)
        service.recognizer = recognizer
        session = VoiceSession('wake', service.settings, recognizer, detector)
        with patch('backend.voice.api.availability', return_value={'manual_available': True, 'wake_available': True}), patch.object(service, 'create_session', return_value=session):
            with self.client.websocket_connect('/voice/listen', headers=ORIGIN) as socket:
                socket.send_json({'consent': True, 'mode': 'wake'})
                self.assertEqual(socket.receive_json()['state'], 'listening')
                socket.send_bytes(SPEECH)
                self.assertEqual(socket.receive_json()['state'], 'recording')
                for _ in range(3):
                    socket.send_bytes(SPEECH)
                socket.send_json({'type': 'finish'})
                self.assertEqual(socket.receive_json()['state'], 'transcribing')
                self.assertEqual(socket.receive_json()['type'], 'transcript')
                self.assertEqual(socket.receive_json()['state'], 'paused')
                socket.send_json({'type': 'resume'})
                self.assertEqual(socket.receive_json()['state'], 'listening')
                socket.send_json({'type': 'stop'})
        self.assertFalse(service.lock.locked())
