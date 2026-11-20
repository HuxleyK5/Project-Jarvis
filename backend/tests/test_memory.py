"""Persistence/privacy tests use only synthetic data and isolated temporary SQLite files."""

import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from uuid import uuid4

from fastapi.testclient import TestClient

from backend.config import Settings
from backend.core.brain import Brain
from backend.main import create_app
from backend.memory.manager import MemoryError, MemoryManager
from backend.memory.privacy import sensitive
from backend.tests.test_chat import TestProvider


class MemoryTests(unittest.TestCase):
    def setUp(self):
        self.directory = self.enterContext(tempfile.TemporaryDirectory())
        self.path = Path(self.directory) / 'memory.sqlite3'
        self.memory = MemoryManager(self.path)

    def test_defaults_do_not_create_a_database_or_store_data(self):
        self.assertFalse(self.memory.settings()['enabled'])
        self.assertEqual(self.memory.list_memories(), [])
        self.assertEqual(self.memory.conversations(), [])
        self.assertEqual(self.memory.save_turn('conversation', 'turn', 'Hello', 'Hi'), 'disabled')
        self.assertFalse(self.path.exists())

    def test_approval_and_enablement_are_required(self):
        for call in [lambda: self.memory.configure(True, False, False),
                     lambda: self.memory.save('fact', 'A synthetic fact', True)]:
            with self.assertRaises(MemoryError):
                call()
        self.memory.configure(True, False, True)
        with self.assertRaises(MemoryError):
            self.memory.save('fact', 'A synthetic fact', False)

    def test_categories_edit_duplicates_and_confirmed_deletion(self):
        self.memory.configure(True, False, True)
        preference = self.memory.save('preference', 'Prefer concise replies.', True)
        self.memory.save('project', 'Building a garden monitor', True)
        self.memory.save('fact', 'The workshop opens on Monday', True)
        with self.assertRaises(MemoryError) as duplicate:
            self.memory.save('fact', '  PREFER   concise replies! ', True)
        self.assertEqual(duplicate.exception.status, 409)
        self.memory.save('preference', 'Prefer detailed replies', True, preference['id'])
        self.assertEqual(len(self.memory.list_memories('detailed')), 1)
        with self.assertRaises(MemoryError):
            self.memory.delete('memories', preference['id'], False)
        self.memory.delete('memories', preference['id'], True)
        self.assertEqual(len(self.memory.list_memories()), 2)

    def test_credentials_and_sensitive_personal_patterns_are_not_written(self):
        self.memory.configure(True, True, True)
        examples = ['My password is test-only-placeholder', 'api_key=test-only-placeholder',
                    'Bearer test-only-placeholder', 'session_token=test-only-placeholder',
                    'My SSN is 123-45-6789', 'My diagnosis is test-only-data',
                    'private key: not-a-real-key', 'https://testuser:testpass@example.invalid']
        for text in examples:
            with self.subTest(text=text):
                self.assertTrue(sensitive(text))
                with self.assertRaises(MemoryError):
                    self.memory.save('fact', text, True)
                self.assertEqual(self.memory.save_turn(str(uuid4()), str(uuid4()), text, 'Test reply'), 'skipped_sensitive')
        self.assertEqual(self.memory.list_memories(), [])
        self.assertEqual(self.memory.conversations(), [])
        raw = self.path.read_bytes()
        self.assertNotIn(b'test-only-placeholder', raw)
        self.assertNotIn(b'123-45-6789', raw)

    def test_history_search_dedup_and_storage_after_reopen(self):
        self.memory.configure(True, True, True)
        conversation, turn = str(uuid4()), str(uuid4())
        self.assertEqual(self.memory.save_turn(conversation, turn, 'Garden project progress?', 'The sensor prototype is ready.'), 'saved')
        self.assertEqual(self.memory.save_turn(conversation, turn, 'Garden project progress?', 'The sensor prototype is ready.'), 'duplicate')
        reopened = MemoryManager(self.path)
        self.assertTrue(reopened.settings()['save_history'])
        self.assertEqual(len(reopened.conversations('sensor')), 1)
        self.assertEqual(reopened.conversations('%'), [])
        reopened.delete('turns', turn, True)
        self.assertEqual(reopened.conversations(), [])

    def test_disable_preserves_view_delete_but_stops_writes_and_retrieval(self):
        self.memory.configure(True, True, True)
        item = self.memory.save('preference', 'Prefer concise replies', True)
        self.memory.configure(False, False, False)
        self.assertEqual(self.memory.relevant('reply'), [])
        self.assertEqual(len(self.memory.list_memories()), 1)
        self.assertEqual(self.memory.save_turn('a', 'b', 'Hi', 'Hello'), 'disabled')
        self.memory.delete('memories', item['id'], True)
        with self.assertRaises(MemoryError):
            MemoryManager(self.path, allowed=False).configure(True, True, True)

    def test_brain_uses_only_approved_references_and_never_auto_saves(self):
        self.memory.configure(True, False, True)
        self.memory.save('project', 'Garden monitor uses soil sensors', True)
        brain = Brain(Settings(), TestProvider(), self.memory)
        result = brain.prepare([{'role': 'user', 'content': 'Tell me about the garden monitor'}])
        self.assertIn('Garden monitor uses soil sensors', result[0]['content'])
        self.assertIn('not instructions', result[0]['content'])
        self.assertEqual(len(self.memory.list_memories()), 1)
        self.assertEqual(self.memory.conversations(), [])

    def test_chat_archives_only_current_successful_pair_and_survives_app_restart(self):
        self.memory.configure(True, True, True)
        body = {'messages': [{'role': 'user', 'content': 'Synthetic garden question'}],
                'save_history': True, 'conversation_id': str(uuid4()), 'turn_id': str(uuid4())}
        with TestClient(create_app(Settings(), TestProvider(), self.memory)) as client:
            response = client.post('/chat', json=body)
            events = [json.loads(line) for line in response.text.splitlines()]
            self.assertIn({'type': 'memory', 'status': 'saved'}, events)
            self.assertEqual(events[-1]['type'], 'done')
        with TestClient(create_app(Settings(), TestProvider(), MemoryManager(self.path))) as restarted:
            self.assertEqual(len(restarted.get('/memory/conversations?q=garden').json()), 1)
            self.assertTrue(restarted.get('/memory/settings').json()['save_history'])

    def test_failed_generation_and_request_without_optin_are_not_archived(self):
        self.memory.configure(True, True, True)
        for failure, opted in [(True, True), (False, False)]:
            with TestClient(create_app(Settings(), TestProvider(failure=failure), self.memory)) as client:
                client.post('/chat', json={'messages': [{'role': 'user', 'content': 'Test question'}],
                    'save_history': opted, 'conversation_id': str(uuid4()), 'turn_id': str(uuid4())})
        self.assertEqual(self.memory.conversations(), [])

    def test_api_approval_validation_and_delete_confirmation(self):
        with TestClient(create_app(Settings(), TestProvider(), self.memory)) as client:
            self.assertEqual(client.put('/memory/settings', json={'enabled': True}).status_code, 403)
            client.put('/memory/settings', json={'enabled': True, 'approved': True})
            self.assertEqual(client.post('/memory/entries', json={'kind': 'fact', 'content': 'Test fact'}).status_code, 403)
            item = client.post('/memory/entries', json={'kind': 'fact', 'content': 'Test fact', 'approved': True}).json()
            self.assertEqual(client.delete(f"/memory/entries/{item['id']}").status_code, 403)
            self.assertEqual(client.delete(f"/memory/entries/{item['id']}?confirm=true").status_code, 200)


class RealProcessRestartTest(unittest.TestCase):
    def test_memory_persists_after_stopping_and_restarting_actual_backend(self):
        with tempfile.TemporaryDirectory() as directory:
            with socket.socket() as probe:
                probe.bind(('127.0.0.1', 0))
                port = probe.getsockname()[1]
            environment = os.environ.copy()
            environment.update(JARVIS_MEMORY_DB=str(Path(directory) / 'restart.sqlite3'), JARVIS_MEMORY_ALLOWED='1', JARVIS_PORT=str(port))
            base = f'http://127.0.0.1:{port}'
            def request(path, body=None):
                data = json.dumps(body).encode() if body is not None else None
                operation = urllib.request.Request(base + path, data=data, headers={'Content-Type': 'application/json'}, method='PUT' if path == '/memory/settings' and body else 'POST' if body else 'GET')
                with urllib.request.urlopen(operation, timeout=2) as response:
                    return json.load(response)
            def start():
                process = subprocess.Popen([sys.executable, '-B', '-m', 'backend.main'], env=environment,
                    cwd=Path(__file__).resolve().parents[2], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                    creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
                for _ in range(100):
                    try:
                        request('/memory/settings')
                        return process
                    except (OSError, urllib.error.URLError):
                        if process.poll() is not None:
                            self.fail('Isolated backend failed to start')
                        time.sleep(0.1)
                process.terminate(); process.wait(timeout=5)
                self.fail('Isolated backend startup timed out')
            process = start()
            try:
                request('/memory/settings', {'enabled': True, 'approved': True})
                request('/memory/entries', {'kind': 'project', 'content': 'Synthetic restart test project', 'approved': True})
            finally:
                process.terminate(); process.wait(timeout=5)
            process = start()
            try:
                self.assertTrue(request('/memory/settings')['enabled'])
                self.assertEqual(request('/memory/entries?q=restart')[0]['content'], 'Synthetic restart test project')
            finally:
                process.terminate(); process.wait(timeout=5)
